#!/usr/bin/env python3
"""Guarded upstream acquisition-এর real CLI receipt; pressure bypass নেই।"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ffv2.config import Settings
from ffv2.io import write_json


def main():
    directory = Settings.load().ensure_state() / "verification" / ("upstream-" + time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex[:8])
    directory.mkdir(mode=0o700, parents=True)
    prefix = [str(ROOT / "bin/ffv2"), "--state-dir", str(directory / "state")]
    def run(args, accepted=(0,)):
        process = subprocess.run(prefix + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=960)
        if process.returncode not in accepted:
            raise RuntimeError(process.stderr[-3000:] or process.stdout[-3000:])
        return process.returncode, json.loads(process.stdout)
    _, before = run(["upstream", "status"])
    if before["source_present"]:
        report = {"status": "existing_source_preserved", "source": before["source"]}
    else:
        _, plan = run(["upstream", "prepare", "--plan"])
        write_json(directory / "prepare-plan.json", plan)
        code, result = run(["upstream", "prepare", "--key", directory.name], accepted=(0, 75))
        _, after = run(["upstream", "status"])
        error = result.get("error") or {}
        refused = result["status"] == "waiting_resources"
        if refused:
            if after["source_present"] or Path(after["workspace"]).exists():
                raise RuntimeError("Refused preparation created a core workspace")
            run(["cancel", result["id"]])
        report = {"schema_version": 1, "verified_at_unix": time.time(), "receipt_directory": str(directory),
                  "worker_status": result["status"], "exit_code": code, "source_present": after["source_present"],
                  "workspace_created": Path(after["workspace"]).exists(), "resource_refusal_verified": refused,
                  "reasons": error.get("details", {}).get("reasons", []),
                  "resources": error.get("details", {}).get("snapshot"), "pkg_config_present": after["pkg_config"]["present"],
                  "core_build_completed": False, "speedup_measured": False}
    write_json(directory / "upstream-control-plane.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
