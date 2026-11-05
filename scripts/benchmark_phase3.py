#!/usr/bin/python3 -B
"""Frozen v0.3.0 এবং Phase 3-এর চারটি sequential, paired software case।"""
from __future__ import annotations
from public_paths import lab_path, project_path

import argparse
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def cli_case(request):
    import contextlib
    import io
    sys.path.insert(0, request["package"])
    from ffv2 import engine
    engine.ACTIVE = Path(request["state"]) / "no-active-selection.json"
    os.environ.update(FFV2_FFMPEG=request["ffmpeg"], FFV2_FFPROBE=request["ffprobe"])
    from ffv2.cli import main as cli
    spec_path = Path(request["spec"]["output"]).with_suffix(".spec.json")
    spec_path.write_text(json.dumps(request["spec"]))
    output = io.StringIO()
    start = time.monotonic()
    with contextlib.redirect_stdout(output):
        code = cli(["--state-dir", request["state"], "run", str(spec_path)])
    elapsed = time.monotonic() - start
    if code:
        raise RuntimeError("CLI run failed")
    result = json.loads(output.getvalue())
    if result["status"] != "completed":
        raise RuntimeError(str(result.get("error")))
    receipt = result["receipt"]
    print(json.dumps({"label": request["label"], "operation": "transcode", "trial": request["trial"], "warmup": request["warmup"],
                      "total_seconds": elapsed, "encode_seconds": receipt["encode_wall_seconds"],
                      "decode_seconds": receipt["validation_wall_seconds"], "phase_timings_seconds": receipt["phase_timings_seconds"],
                      "sha256": receipt["output_sha256"], "bytes": receipt["output_bytes"], "output": result["output"]}))
    return 0


def comparison(rows, before, after, field):
    a = {r["trial"]: r[field] for r in rows if r["label"] == before and not r["warmup"]}
    b = {r["trial"]: r[field] for r in rows if r["label"] == after and not r["warmup"]}
    keys = sorted(a.keys() & b.keys())
    rng = random.Random(20261103)
    intervals = []
    for _ in range(3000):
        sample = rng.choices(keys, k=len(keys))
        intervals.append(statistics.median(b[i] for i in sample) / statistics.median(a[i] for i in sample))
    intervals.sort()
    return {"before": before, "after": after, "field": field, "n_pairs": len(keys),
            "before_median": statistics.median(a.values()), "after_median": statistics.median(b.values()),
            "after_over_before": statistics.median(b.values()) / statistics.median(a.values()),
            "paired_bootstrap_ratio_95_percent": [intervals[75], intervals[2924]]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, choices=(9, 11, 15), default=15)
    parser.add_argument("--entry", choices=("pipeline", "cli"), default="pipeline")
    parser.add_argument("--case", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.case:
        request = json.loads(args.case)
        if request.get("entry") == "cli":
            return cli_case(request)
        from benchmark_phase2 import case
        return case(request)
    sys.path.insert(0, str(ROOT))
    from ffv2.config import check_mounts
    from ffv2.engine import selection
    from ffv2.io import capture, sha256_file, write_json
    from ffv2.resources import Policy, snapshot
    parent = Path(str(lab_path('ffmpeg-v2-phase3')))
    directory = parent / ("software-" + ("cli-" if args.entry == "cli" else "") + time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex[:8])
    check_mounts(directory)
    directory.mkdir(parents=True)
    sample = snapshot(directory)
    reasons = Policy().admission(sample, 2 * 1024**3, 1024**3)
    if reasons:
        raise RuntimeError(str(reasons))
    selected = selection(verify_hashes=True)
    source = ROOT / ".runtime/verification/benchmark-native-20261102T145507-9e28a965/reference.mkv"
    configurations = {}
    for phase, package in (("phase2", parent / "baseline"), ("phase3", ROOT)):
        for engine in ("stock", "native"):
            binaries = selected["binaries"] if engine == "native" else {name: "/opt/homebrew/bin/" + name for name in ("ffmpeg", "ffprobe")}
            configurations[phase + "-" + engine] = {"package": str(package), **{name: binaries[name] for name in ("ffmpeg", "ffprobe")}, "matched_progress": True}
    report = {"schema_version": 1, "status": "running", "directory": str(directory), "trials": args.trials, "entry": args.entry,
              "source": str(source), "source_sha256": sha256_file(source), "baseline_commit": "d3128af",
              "native_selection_id": selected["selection_id"], "configurations": configurations,
              "baseline_resources": sample.json(), "system_memory_checks_ignored": Policy().ignore_system_memory,
              "estimated_peak_job_bytes": 2 * 1024**3, "estimated_new_storage_bytes": 1024**3,
              "cases": [], "summary": {}, "comparisons": [],
              "limits": ["Busy shared host; 6s/720p/30fps synthetic input; no universal kernel speed claim.",
                         "Four cases run sequentially in seeded interleaved order, with one excluded warmup each.",
                         "Warmups include cold dependency inspection. Cold timings are retained separately.",
                         "Identical bitrate, encoder threads, legacy progress, full metadata/decode/hash/publication checks.",
                         "Bootstrap intervals resample paired trial blocks; shared-host interference remains possible."]}
    if args.entry == "cli":
        report["limits"].append("Actual cli.main parser/run/JSON output path with explicit binaries and no active selection; native default JSONL, stock kv. cli_process_seconds includes interpreter/import/entry overhead.")
    def save():
        write_json(directory / "report.json", report)
    rng = random.Random(20261103)
    try:
        save()
        for trial in range(args.trials + 1):
            labels = list(configurations)
            rng.shuffle(labels)
            for label in labels:
                spec = {"operation": "transcode", "input": str(source), "output": str(directory / (label + "-" + str(trial) + ".mp4")),
                        "encoder": "software", "video_bitrate": 4_000_000, "rate_control": "bitrate", "fps": 30}
                request = {**configurations[label], "entry": args.entry, "label": label, "spec": spec, "trial": trial,
                           "warmup": trial == 0, "state": str(directory / (label + "-state"))}
                started = time.monotonic()
                child = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--case", json.dumps(request)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=150)
                if child.returncode:
                    raise RuntimeError(child.stderr[-4000:])
                row = json.loads(child.stdout)
                row["cli_process_seconds"] = time.monotonic() - started
                report["cases"].append(row)
                save()
            print(json.dumps({"trial": trial, "completed_cases": len(report["cases"])}), flush=True)
        fields = ("capability_seconds", "planning_seconds", "queue_seconds", "work_seconds", "total_seconds",
                  "encode_seconds", "decode_seconds", "cli_process_seconds")
        if args.entry == "cli":
            fields = ("total_seconds", "encode_seconds", "decode_seconds", "cli_process_seconds")
        for label in configurations:
            rows = [r for r in report["cases"] if r["label"] == label and not r["warmup"]]
            report["summary"][label] = {"n": len(rows), "bytes": sorted({r["bytes"] for r in rows}),
                                        "unique_hashes": len({r["sha256"] for r in rows}),
                                        **{field: {"median": statistics.median(r[field] for r in rows),
                                                   "min": min(r[field] for r in rows), "max": max(r[field] for r in rows)} for field in fields}}
        for engine in ("stock", "native"):
            if len({r["sha256"] for r in report["cases"] if r["label"].endswith(engine)}) != 1:
                raise RuntimeError("Same-engine outputs changed between Phase 2 and Phase 3")
            report["comparisons"].append(comparison(report["cases"], "phase2-" + engine, "phase3-" + engine, "total_seconds"))
        for phase in ("phase2", "phase3"):
            for field in ("total_seconds", "cli_process_seconds", "encode_seconds"):
                report["comparisons"].append(comparison(report["cases"], phase + "-stock", phase + "-native", field))
        decoded = {}
        for engine in ("stock", "native"):
            row = next(r for r in report["cases"] if r["label"] == "phase3-" + engine)
            code, out, err = capture([selected["binaries"]["ffmpeg"], "-v", "error", "-xerror", "-nostdin", "-threads", "2",
                                      "-i", row["output"], "-map", "0:v:0", "-an", "-threads", "2", "-f", "framemd5", "-"], timeout=30)
            if code:
                raise RuntimeError(err[-2000:])
            frames = [line.split(",")[-1].strip() for line in out.splitlines() if line and not line.startswith("#")]
            if len(frames) != 180:
                raise RuntimeError("Expected exactly 180 decoded frames")
            decoded[engine] = frames
        if decoded["stock"] != decoded["native"]:
            raise RuntimeError("Stock/native decoded software pixels differ")
        report["output_acceptance"] = {"same_engine_phase2_phase3_file_hashes_equal": True,
                                       "stock_native_all_180_decoded_video_hashes_equal": True}
        report["status"] = "completed"
        report["final_resources"] = snapshot(directory).json()
        save()
    except BaseException as error:
        report.update(status="failed", error=str(error)[:5000])
        save()
        raise
    print(json.dumps({"report": str(directory / "report.json"), "comparisons": report["comparisons"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
