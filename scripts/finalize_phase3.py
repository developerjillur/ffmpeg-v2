#!/usr/bin/python3 -B
"""Completed raw receipts যাচাই করে portable Phase 3 evidence index লিখুন।"""
from __future__ import annotations
from public_paths import lab_path, project_path

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ffv2 import __version__
from ffv2.engine import selection
from ffv2.io import digest, publish_json_new, sha256_file


def main():
    parser = argparse.ArgumentParser()
    for name in ("pipeline", "cli", "acceptance", "regressions", "control", "cache", "preliminary"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/verification/phase3-2026-11-03.json")
    args = parser.parse_args()
    evidence = []
    def read(path):
        if not path.is_file() or path.stat().st_size > 2 * 1024**2:
            raise RuntimeError("Expected bounded report: " + str(path))
        value = json.loads(path.read_text())
        if value.get("status") != "completed":
            raise RuntimeError("Incomplete report: " + str(path))
        evidence.append({"path": str(path), "sha256": sha256_file(path)})
        return value
    reports = {name: read(getattr(args, name)) for name in ("pipeline", "cli", "acceptance", "regressions", "control", "cache", "preliminary")}
    checks = {}
    for run in reports["regressions"]["runs"]:
        if run["exit_code"]:
            raise RuntimeError("Regression runner failed")
        value = json.loads(Path(run["stdout"]).read_text())
        path = Path(value["report"]) if "report" in value else Path(value["directory"]) / "report.json"
        actual = read(path)
        for name, case in actual["tests"].items():
            if case.get("status") != "pass":
                raise RuntimeError("Acceptance failed: " + name)
            checks[run["name"] + "/" + name] = {"status": "pass", "report": str(path)}
    for name, case in reports["acceptance"]["tests"].items():
        if case.get("status") != "pass":
            raise RuntimeError("New acceptance failed: " + name)
        checks["phase3/" + name] = {"status": "pass", "report": str(args.acceptance)}
    if len(checks) != 32:
        raise RuntimeError("Expected 32 actual acceptance checks")
    for run in reports["control"]["runs"]:
        log = Path(run["log"])
        text = log.read_text()
        if run["exit_code"] or not re.search(r"Ran 102 tests.*\n\nOK", text, re.S) or "ResourceWarning" in text:
            raise RuntimeError("Control test evidence mismatch")
        evidence.append({"path": str(log), "sha256": sha256_file(log)})
    pipeline, cli = reports["pipeline"], reports["cli"]
    if len(pipeline["cases"]) != 64 or len(cli["cases"]) != 40:
        raise RuntimeError("Expected warmup-inclusive 64 pipeline and 40 CLI outputs")
    hashes = {row["sha256"] for report in (pipeline, cli) for row in report["cases"]}
    if len(hashes) != 1 or any(row["bytes"] != 3082562 for report in (pipeline, cli) for row in report["cases"]):
        raise RuntimeError("Software output identity changed")
    previous_path = Path(str(lab_path('ffmpeg-v2-phase2/benchmark-core-20261102T180441-2a20e025/report.json')))
    previous = read(previous_path)
    previous_software = [r for r in previous["cases"] if "-software-" in r["output"]]
    if {r["sha256"] for r in previous_software} != hashes or previous["source_sha256"] != pipeline["source_sha256"]:
        raise RuntimeError("Retained quality evidence does not match new files")
    selected = selection(verify_hashes=True)
    code = {str(path.relative_to(ROOT)): sha256_file(path) for path in sorted((ROOT / "ffv2").glob("*.py"))}
    code["pyproject.toml"] = sha256_file(ROOT / "pyproject.toml")
    hardware = reports["acceptance"]["tests"]["hardware_frame_scaling"]
    value = {"schema_version": 1, "status": "completed", "release": __version__, "date_local": "2026-11-03",
             "maintainer": "Jillur Rahman", "baseline_commit": pipeline["baseline_commit"],
             "production_source_sha256": code, "production_source_digest": digest(code),
             "native_engine": {"selection_id": selected["selection_id"], "source": selected["source"],
                               "verified_files": len(selected["files"]), "changed_in_phase3": False,
                               "local_fate_records": 2893, "fate_evidence": "retained Phase 2; not a new FATE run"},
             "control": {"count_per_runtime": 102, "runtimes": [r["version"] for r in reports["control"]["runs"]]},
             "actual_checks": checks,
             "pipeline": {"n": 15, "summary": pipeline["summary"], "comparisons": pipeline["comparisons"]},
             "actual_cli": {"n": 9, "summary": cli["summary"], "comparisons": cli["comparisons"]},
             "software_target_status": "startup_overhead_reduced; stable_stock_native_advantage_unresolved",
             "output": {"pipeline_outputs": 64, "cli_outputs": 40, "bytes": 3082562, "sha256": next(iter(hashes)),
                        "all_files_equal": True, "stock_native_180_frame_hashes_equal": True, "additional_compression_percent": 0,
                        "quality": previous["quality"]["native-software"], "quality_reused_from_identical_file": str(previous_path)},
             "hardware_scaling": {"mechanism_status": "pass", "promoted_to_default": False, "default": "software",
                                  "summary": hardware["summary"], "quality": hardware["quality"], "limits": hardware["limits"]},
             "supervisor_loss": reports["acceptance"]["tests"]["supervisor_loss"],
             "capability_cache": reports["cache"],
             "system_memory_checks_ignored": True, "job_memory_limit_bytes": 12 * 1024**3,
             "evidence": evidence,
             "limits": ["Shared busy host; short synthetic timing, intervals span stock/native equality.",
                        "Initial dependency hashing/cold inspection retained; warm cache is the repeated workload measure.",
                        "Hardware scaler was slower and lower quality in measured fixture; explicit option only.",
                        "Stat/ctime bindings are not a hostile same-user filesystem sandbox or full source snapshot.",
                        "Supervisor registration window and simultaneous worker/supervisor hard kill have no kernel guarantee.",
                        "Private HD/HDR/perceptual/overnight, full external FATE, typed concat/subtitles, preemption and production integration remain."]}
    # Baseline checkout identity is independently checked before publishing the index.
    baseline = Path(str(lab_path('ffmpeg-v2-phase3/baseline')))
    head = subprocess.check_output(["git", "-C", str(baseline), "rev-parse", "HEAD"], text=True).strip()
    if not head.startswith(pipeline["baseline_commit"]):
        raise RuntimeError("Frozen baseline checkout changed")
    publish_json_new(args.output, value)
    print(json.dumps({"status": "completed", "output": str(args.output), "checks": len(checks), "tests_per_runtime": 102,
                      "production_source_digest": value["production_source_digest"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
