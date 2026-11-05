#!/usr/bin/env python3
"""Pinned pkgconf prerequisite, own external prefix ও monitored serial build।"""
from __future__ import annotations
from public_paths import lab_path, project_path

import json
import os
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ffv2.config import GIB, Settings, check_mounts
from ffv2.io import capture, digest, sha256_file, write_json
from ffv2.resources import Policy, snapshot
from ffv2.store import Store
from ffv2.worker import host_lock, supervised

VERSION = "3.0.10"
URL = "https://distfiles.ariadne.space/pkgconf/pkgconf-3.0.10.tar.xz"
SHA = "9371b2f6372da574d4c6dc96fe9b1463037bcf6afcb6671c1555afde7b17e2de"
AREA = Path(str(lab_path('ffmpeg-v2-core/tools')))
PREFIX = AREA / ("pkgconf-" + VERSION)


def main():
    check_mounts(AREA)
    binary = PREFIX / "bin/pkgconf"
    if binary.is_file():
        code, version, _ = capture([str(binary), "--version"])
        if code == 0 and version.strip() == VERSION:
            print(json.dumps({"status": "reused", "prefix": str(PREFIX), "version": VERSION}))
            return 0
        raise RuntimeError("Existing prefix identity differs; preserved")
    root = AREA / ("pkgconf-bootstrap-" + VERSION)
    print(json.dumps({"affected_paths": [str(root), str(PREFIX)], "source_sha256": SHA}), flush=True)
    root.mkdir(parents=True, exist_ok=True)
    settings = Settings.load(state=ROOT / ".runtime/pkgconf-bootstrap")
    store = Store(settings)
    plan = {"kind": "bootstrap_pkgconf", "spec": {"operation": "bootstrap_pkgconf", "output": str(PREFIX / "install.json")},
            "estimates": {"job_memory_bytes": 512 * 1024 ** 2, "output_budget_bytes": 128 * 1024 ** 2}, "timeout_seconds": 300}
    plan["plan_id"] = digest(plan)
    queued = store.enqueue(plan, "pkgconf-" + VERSION)
    if queued["status"] in ("failed", "cancelled", "interrupted"):
        store.retry(queued["id"])
    job = store.claim(queued["id"])
    if not job:
        raise RuntimeError("Bootstrap job is not claimable")
    directory = store.root / "jobs" / job["id"] / ("attempt-%03d" % job["attempt"])
    directory.mkdir(parents=True, exist_ok=False)
    baseline = snapshot(root)
    reasons = Policy().admission(baseline, plan["estimates"]["job_memory_bytes"], plan["estimates"]["output_budget_bytes"])
    if reasons:
        store.update(job["id"], "waiting_resources", error={"code": "resource_not_admitted", "details": {"reasons": reasons}})
        raise RuntimeError(str(reasons))
    receipts = []
    try:
        with host_lock(settings) as lock_fd:
            archive = root / ("pkgconf-" + VERSION + ".tar.xz")
            if not archive.is_file() or sha256_file(archive) != SHA:
                receipts.append(supervised(["/usr/bin/curl", "--fail", "--location", "--silent", "--show-error", "--connect-timeout", "20", "--max-time", "120", "--output", str(archive), URL],
                                           "download", job, directory, settings, baseline, lock_fd, root, process_kind="tool"))
            if sha256_file(archive) != SHA:
                raise RuntimeError("Source archive checksum mismatch")
            source = root / ("pkgconf-" + VERSION)
            if not source.exists():
                with tarfile.open(archive) as package:
                    members = package.getmembers()
                    for member in members:
                        parts = Path(member.name).parts
                        if not parts or parts[0] != source.name or ".." in parts or member.name.startswith("/") or member.issym() or member.islnk():
                            raise RuntimeError("Unexpected archive path/link: " + member.name)
                    print(json.dumps({"extract_root": str(root), "members": len(members)}), flush=True)
                    package.extractall(root)
            build = root / "build"
            build.mkdir(exist_ok=True)
            commands = [("configure", [str(source / "configure"), "--prefix=" + str(PREFIX), "--disable-shared", "--enable-static"]),
                        ("compile", ["/usr/bin/make", "-j1"]), ("install", ["/usr/bin/make", "-j1", "install"])]
            for name, command in commands:
                receipts.append(supervised(command, name, job, directory, settings, baseline, lock_fd, root,
                                           cwd=build, process_kind="tool", environment={"MAKEFLAGS": "-j1", "LC_ALL": "C"}))
            code, version, err = capture([str(binary), "--version"])
            if code or version.strip() != VERSION:
                raise RuntimeError(err or "Installed version mismatch")
            report = {"status": "completed", "version": VERSION, "source_url": URL, "source_sha256": SHA,
                      "prefix": str(PREFIX), "binary_sha256": sha256_file(binary), "system_memory_checks_ignored": Policy().ignore_system_memory,
                      "receipts": receipts, "finished_at": time.time()}
            write_json(PREFIX / "install.json", report)
            store.update(job["id"], "completed", receipt=report)
            print(json.dumps({k: v for k, v in report.items() if k != "receipts"}, indent=2))
    except BaseException as error:
        store.update(job["id"], "failed", error={"code": "bootstrap_failed", "message": str(error)[:2000]})
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
