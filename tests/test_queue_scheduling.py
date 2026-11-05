from __future__ import annotations

from unittest.mock import patch
from contextlib import closing
import json
import subprocess
import sqlite3

from ffv2.config import GIB, PROJECT
from ffv2.io import digest
from ffv2.resources import Policy, Snapshot
from ffv2.store import Store
from ffv2.worker import work
from test_safety import BAD, GOOD, Workspace

LIMITED = Snapshot("normal", int(10.5 * GIB), GOOD.swap_bytes, GOOD.boot_free_bytes,
                   GOOD.boot_used_bytes, GOOD.output_free_bytes)


class SchedulingTests(Workspace):
    def test_priority_orders_jobs_and_aging_prevents_new_jobs_overtaking_forever(self):
        store = Store(self.settings)
        with patch("ffv2.store.time.time", return_value=1000):
            low = store.enqueue(self.plan(priority=-10, output=str(self.root / "low.mp4")))
        with patch("ffv2.store.time.time", return_value=1001):
            urgent = store.enqueue(self.plan(priority=10, output=str(self.root / "urgent.mp4")))
        self.assertEqual(store.claim()["id"], urgent["id"])
        with patch("ffv2.store.time.time", return_value=2201):
            late = store.enqueue(self.plan(priority=10, output=str(self.root / "late.mp4")))
        self.assertEqual(store.claim()["id"], low["id"])
        self.assertEqual(store.claim()["id"], late["id"])

    def test_priority_persists_on_restart_and_explicit_selection_wins(self):
        store = Store(self.settings)
        low = store.enqueue(self.plan(priority=-10, output=str(self.root / "low.mp4")))
        high = store.enqueue(self.plan(priority=10, output=str(self.root / "high.mp4")))
        restarted = Store(self.settings)
        self.assertEqual(restarted.get(high["id"])["priority"], 10)
        self.assertEqual(restarted.claim(low["id"])["id"], low["id"])
        self.assertEqual(restarted.claim()["id"], high["id"])

    def test_legacy_database_migrates_without_losing_jobs(self):
        root = self.settings.ensure_state()
        with closing(sqlite3.connect(root / "jobs.sqlite3")) as db:
            db.execute("CREATE TABLE jobs(id TEXT PRIMARY KEY,idempotency_key TEXT UNIQUE NOT NULL,plan_id TEXT NOT NULL,"
                       "output TEXT NOT NULL,plan TEXT NOT NULL,status TEXT NOT NULL,attempt INTEGER NOT NULL DEFAULT 0,"
                       "cancel_requested INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL,updated REAL NOT NULL,"
                       "progress TEXT,error TEXT,receipt TEXT)")
            plan = self.plan()
            db.execute("INSERT INTO jobs(id,idempotency_key,plan_id,output,plan,status,created,updated) VALUES(?,?,?,?,?,'queued',1,1)",
                       ("a" * 32, "legacy", plan["plan_id"], plan["spec"]["output"], json.dumps(plan)))
            db.commit()
        store = Store(self.settings)
        self.assertEqual(store.get("a" * 32)["priority"], 0)
        self.assertEqual(store.claim()["id"], "a" * 32)

    def test_priority_is_typed_and_affects_idempotency(self):
        from ffv2.errors import FFV2Error
        for priority in (True, 11, -11, 1.5):
            with self.assertRaises(FFV2Error):
                self.plan(priority=priority)
        store = Store(self.settings)
        store.enqueue(self.plan(priority=1), "same")
        with self.assertRaises(FFV2Error) as error:
            store.enqueue(self.plan(priority=2), "same")
        self.assertEqual(error.exception.code, "idempotency_conflict")

    def queued_pair(self):
        store = Store(self.settings)
        heavy = self.plan(output=str(self.root / "heavy.mp4"))
        heavy["estimates"]["job_memory_bytes"] = 3 * GIB
        heavy["plan_id"] = digest({k: v for k, v in heavy.items() if k not in ("plan_id", "display_command")})
        first = store.enqueue(heavy)
        second = store.enqueue(self.plan(output=str(self.root / "small.mp4")))
        return store, first["id"], second["id"]

    @staticmethod
    def controlled_execution(sample):
        def execute(job, settings, lock_fd, store, *, session=None):
            estimate = job["plan"]["estimates"]
            reasons = Policy().admission(sample, estimate["job_memory_bytes"], estimate["output_budget_bytes"])
            if reasons:
                store.update(job["id"], "waiting_resources", error={"code": "resource_not_admitted", "details": {"reasons": reasons}})
            else:
                store.update(job["id"], "completed", receipt={"controlled_execution": True})
            return store.get(job["id"], plan=False)
        return execute

    def test_unfit_first_job_does_not_block_a_smaller_admissible_job(self):
        store, heavy, small = self.queued_pair()
        with patch("ffv2.worker.perform", side_effect=self.controlled_execution(LIMITED)), \
             patch("ffv2.worker.snapshot", return_value=LIMITED):
            result = work(self.settings, drain=True)
        self.assertEqual(store.get(heavy)["status"], "waiting_resources")
        self.assertEqual(store.get(small)["status"], "completed")
        self.assertEqual(store.get(heavy)["attempt"], 1)
        self.assertEqual(result["processed"], 2)
        self.assertEqual(result["deferred_job_ids"], [heavy])

    def test_system_warning_stops_the_batch_without_trying_later_jobs(self):
        store, heavy, small = self.queued_pair()
        with patch("ffv2.worker.perform", side_effect=self.controlled_execution(BAD)) as execute, \
             patch("ffv2.worker.snapshot", return_value=BAD):
            work(self.settings, drain=True)
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(store.get(small)["status"], "queued")

    def test_explicit_job_selection_never_runs_an_unrequested_job(self):
        store, heavy, small = self.queued_pair()
        with patch("ffv2.worker.perform", side_effect=self.controlled_execution(LIMITED)), \
             patch("ffv2.worker.snapshot", return_value=LIMITED):
            work(self.settings, job_id=heavy, drain=True)
        self.assertEqual(store.get(small)["status"], "queued")

    def test_empty_or_invalid_job_id_does_not_claim_another_job(self):
        store, heavy, small = self.queued_pair()
        from ffv2.errors import FFV2Error
        for job_id in ("", 0, False):
            with self.subTest(job_id=job_id), self.assertRaises(FFV2Error):
                store.claim(job_id)
        result = subprocess.run([str(PROJECT / "bin/ffv2"), "--state-dir", str(self.settings.state), "worker", "--job-id", ""],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)["error"]["code"], "invalid_job_id")
        self.assertEqual(store.get(heavy)["status"], "queued")
        self.assertEqual(store.get(small)["status"], "queued")
