from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from functools import wraps

from .errors import FFV2Error
from .io import canonical, digest, fingerprint, sha256_file, write_json

ACTIVE = ("queued", "waiting_resources", "running", "validating")

def lifecycle_mutation(method):
    @wraps(method)
    def guarded(self,*args,**kwargs):
        from .releases import lifecycle_lock,assert_current
        with lifecycle_lock(self.settings):
            assert_current()
            return method(self,*args,**kwargs)
    return guarded


class Store:
    def __init__(self, settings):
        self.settings = settings
        self.root = settings.ensure_state()
        self.path = self.root / "jobs.sqlite3"
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
                    plan_id TEXT NOT NULL, output TEXT NOT NULL, plan TEXT NOT NULL,
                    status TEXT NOT NULL, attempt INTEGER NOT NULL DEFAULT 0,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created REAL NOT NULL, updated REAL NOT NULL,
                    progress TEXT, error TEXT, receipt TEXT);
                CREATE UNIQUE INDEX IF NOT EXISTS active_output ON jobs(output)
                    WHERE status IN ('queued','waiting_resources','running','validating');
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY, job_id TEXT NOT NULL, at REAL NOT NULL,
                    status TEXT NOT NULL, detail TEXT NOT NULL);
            """)
            db.execute("BEGIN IMMEDIATE")
            if "priority" not in {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}:
                db.execute("ALTER TABLE jobs ADD COLUMN priority INTEGER NOT NULL DEFAULT 0")
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def check_id(job_id):
        if not isinstance(job_id, str) or not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise FFV2Error("invalid_job_id", "Job ID গ্রহণযোগ্য নয়।")

    def event(self, db, job_id, status, detail):
        db.execute("INSERT INTO events(job_id,at,status,detail) VALUES(?,?,?,?)",
                   (job_id, time.time(), status, canonical(detail)))
        db.execute("DELETE FROM events WHERE job_id=? AND seq NOT IN (SELECT seq FROM events WHERE job_id=? ORDER BY seq DESC LIMIT 200)", (job_id, job_id))

    @staticmethod
    def decode(row, *, plan=True):
        value = dict(row)
        for key in ("plan", "progress", "error", "receipt"):
            value[key] = json.loads(value[key]) if value[key] else None
        if not plan:
            value.pop("plan")
        value["cancel_requested"] = bool(value["cancel_requested"])
        return value

    def get(self, job_id, *, plan=True):
        self.check_id(job_id)
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise FFV2Error("job_not_found", "Job পাওয়া যায়নি।")
        return self.decode(row, plan=plan)

    @lifecycle_mutation
    def enqueue(self, plan, key=None):
        key = plan["plan_id"] if key is None else key
        if not isinstance(key, str) or not 1 <= len(key) <= 128 or any(ord(c) < 32 for c in key):
            raise FFV2Error("invalid_idempotency_key", "Idempotency key 1–128টি printable character হতে হবে।")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM jobs WHERE idempotency_key=?", (key,)).fetchone()
            if existing:
                if existing["plan_id"] != plan["plan_id"]:
                    raise FFV2Error("idempotency_conflict", "একই key দিয়ে আলাদা job জমা দেওয়া যাবে না।")
                return {**self.decode(existing, plan=False), "replayed": True}
            if os.path.lexists(plan["spec"]["output"]):
                raise FFV2Error("output_exists", "Output আগে থেকেই আছে; overwrite হবে না।")
            identity = uuid.uuid4().hex
            now = time.time()
            try:
                priority = plan["spec"].get("priority", 0)
                if type(priority) is not int or not -10 <= priority <= 10:
                    raise FFV2Error("invalid_priority", "Priority -10 থেকে 10-এর মধ্যে integer দিন।")
                db.execute("INSERT INTO jobs(id,idempotency_key,plan_id,output,plan,status,created,updated,priority) VALUES(?,?,?,?,?,'queued',?,?,?)",
                           (identity, key, plan["plan_id"], plan["spec"]["output"], canonical(plan), now, now, priority))
            except sqlite3.IntegrityError as error:
                raise FFV2Error("output_reserved", "অন্য active job এই output path ব্যবহার করছে।") from error
            self.event(db, identity, "queued", {"plan_id": plan["plan_id"]})
        return {**self.get(identity, plan=False), "replayed": False}

    def claim(self, job_id=None, *, exclude_ids=()):
        if job_id is not None:
            self.check_id(job_id)
        if not isinstance(exclude_ids, (tuple, list, set)) or len(exclude_ids) > 100:
            raise FFV2Error("invalid_excluded_jobs", "এক pass-এ সর্বোচ্চ 100টি job বাদ দেওয়া যায়।")
        for identity in exclude_ids:
            self.check_id(identity)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            where, params = ("AND id=?", (job_id,)) if job_id is not None else ("", ())
            if exclude_ids:
                where += " AND id NOT IN (" + ",".join("?" for _ in exclude_ids) + ")"
                params += tuple(sorted(exclude_ids))
            # score = priority + age_seconds/60; shared 'now' cancels from the ordering.
            row = db.execute("SELECT * FROM jobs WHERE status IN ('queued','waiting_resources') AND cancel_requested=0 " + where +
                             " ORDER BY (priority * 60.0 - created) DESC,created,id LIMIT 1", params).fetchone()
            if not row:
                return None
            db.execute("UPDATE jobs SET status='running',attempt=attempt+1,error=NULL,progress=NULL,updated=? WHERE id=?", (time.time(), row["id"]))
            self.event(db, row["id"], "running", {"attempt": row["attempt"] + 1})
        return self.get(row["id"])

    def update(self, job_id, status, *, error=None, receipt=None):
        self.check_id(job_id)
        with self.connect() as db:
            db.execute("UPDATE jobs SET status=?,error=?,receipt=?,updated=? WHERE id=?",
                       (status, canonical(error) if error else None, canonical(receipt) if receipt else None, time.time(), job_id))
            self.event(db, job_id, status, error or {})

    def progress(self, job_id, progress):
        with self.connect() as db:
            db.execute("UPDATE jobs SET progress=?,updated=? WHERE id=?", (canonical(progress), time.time(), job_id))

    def cancelled(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
        return not row or bool(row[0])

    def higher_priority_waiting(self, job_id):
        self.check_id(job_id)
        with self.connect() as db:
            row = db.execute("SELECT priority * 60.0 - created AS score FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                return False
            return db.execute("SELECT 1 FROM jobs WHERE id != ? AND status IN ('queued','waiting_resources') AND cancel_requested=0 AND priority*60.0-created > ? LIMIT 1",
                              (job_id, row['score'])).fetchone() is not None

    def cancel(self, job_id):
        job = self.get(job_id, plan=False)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row[0] in ACTIVE:
                state = "cancelled" if row[0] in ("queued", "waiting_resources") else row[0]
                db.execute("UPDATE jobs SET cancel_requested=1,status=?,updated=? WHERE id=?", (state, time.time(), job_id))
                self.event(db, job_id, state, {"cancel_requested": True})
        return self.get(job_id, plan=False)

    @lifecycle_mutation
    def retry(self, job_id):
        from .bindings import assert_workflow
        assert_workflow(self.get(job_id)['plan'])
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status,output FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row["status"] not in ("failed", "interrupted", "cancelled", "waiting_resources"):
                raise FFV2Error("job_not_retryable", "শুধু stopped বা failed job retry করা যায়।")
            if os.path.lexists(row["output"]):
                raise FFV2Error("output_exists", "Output আছে; আগে তার পরিচয় যাচাই করুন।")
            try:
                db.execute("UPDATE jobs SET status='queued',cancel_requested=0,error=NULL,updated=? WHERE id=?", (time.time(), job_id))
            except sqlite3.IntegrityError as error:
                raise FFV2Error("output_reserved", "অন্য active job এই output ব্যবহার করছে।") from error
            self.event(db, job_id, "queued", {"retry_requested": True})
        return self.get(job_id, plan=False)

    def recover(self):
        # শুধু host lock পাওয়ার পরে call হয়; আগের supervisor/encoder আর lock ধরে নেই।
        with self.connect() as db:
            rows = db.execute("SELECT id,attempt,plan_id,output FROM jobs WHERE status IN ('running','validating')").fetchall()
            for row in rows:
                from pathlib import Path
                directory = self.root / 'jobs' / row['id'] / ('attempt-%03d' % row['attempt'])
                intent_path = directory / 'publish-intent.json'
                try:
                    if intent_path.is_file() and not intent_path.is_symlink() and intent_path.stat().st_size <= 2*1024**2:
                        intent = json.loads(intent_path.read_text())
                        receipt = intent['receipt']
                        output, stage = Path(row['output']), Path(receipt['staging_output'])
                        if (digest(receipt) == intent['digest'] and receipt['plan_id'] == row['plan_id'] and
                            receipt['output'] == str(output) and receipt['status'] == 'completed' and
                            receipt['validation']['full_decode']['status'] == 'completed' and
                            not output.is_symlink() and output.is_file() and os.path.samefile(output, stage) and
                            fingerprint(output) == receipt['publish_identity'] and sha256_file(output) == receipt['output_sha256']):
                            receipt['reconciled_publish'] = True
                            write_json(directory / 'receipt.json', receipt)
                            db.execute("UPDATE jobs SET status='completed',error=NULL,receipt=?,updated=? WHERE id=?", (canonical(receipt), time.time(), row['id']))
                            self.event(db, row['id'], 'completed', {'reconciled_publish': True})
                            continue
                except (OSError, ValueError, TypeError, KeyError):
                    pass
                error = {"code": "worker_interrupted", "message": "আগের worker শেষ হওয়ার receipt নেই; partial output রাখা হয়েছে।"}
                db.execute("UPDATE jobs SET status='interrupted',error=?,updated=? WHERE id=?", (canonical(error), time.time(), row["id"]))
                self.event(db, row["id"], "interrupted", error)

    def list(self, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise FFV2Error("invalid_limit", "Limit 1–100-এর মধ্যে দিন।")
        with self.connect() as db:
            rows = db.execute("SELECT * FROM jobs ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
        return [self.decode(row, plan=False) for row in rows]

    def events(self, job_id):
        self.get(job_id, plan=False)
        with self.connect() as db:
            return [{**dict(r), "detail": json.loads(r["detail"])} for r in db.execute("SELECT * FROM events WHERE job_id=? ORDER BY seq", (job_id,))]
