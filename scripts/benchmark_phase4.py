#!/usr/bin/python3 -B
"""Long production-media thread calibration; quality gates declared before running।"""
from __future__ import annotations
from public_paths import lab_path, project_path

import argparse
import json
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
WORK = Path(str(lab_path('ffmpeg-v2-phase4')))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", help=argparse.SUPPRESS)
    parser.add_argument("--seconds", type=int, choices=(30, 60, 120, 180), default=60)
    parser.add_argument("--trials", type=int, choices=(3, 5, 7), default=3)
    parser.add_argument("--mode", choices=("calibrate", "balanced", "hardware", "acceptance"), default="calibrate")
    parser.add_argument("--profile", action="append", choices=("bbb-1080", "bbb-2160", "bbb-2160-to1080", "tos-liveaction"))
    parser.add_argument("--filter-threads", type=int, choices=(1, 2, 4), default=2)
    parser.add_argument("--quality-only", type=Path)
    parser.add_argument("--reuse-quality", type=Path)
    args = parser.parse_args()
    if args.case:
        import contextlib
        import io
        from benchmark_phase2 import case
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = case(json.loads(args.case))
        value = json.loads(output.getvalue())
        plan = json.loads((Path(value["receipt"]).parent / "plan.json").read_text())
        value.update(runtime_binding_id=plan["binary"].get("runtime_binding", {}).get("binding_id"),
                     runtime_tuning=plan.get("runtime_tuning"), plan_id=plan["plan_id"])
        print(json.dumps(value))
        return result
    sys.path.insert(0, str(ROOT))
    from ffv2.config import check_mounts
    from ffv2.engine import selection
    from ffv2.io import sha256_file, write_json
    from ffv2.resources import Policy, snapshot
    selected = selection(verify_hashes=True)
    if args.quality_only:
        directory = args.quality_only.parent
        report = json.loads(args.quality_only.read_text())
    else:
        directory = WORK / (args.mode + "-" + time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex[:8])
        check_mounts(directory)
        directory.mkdir(parents=True)
        sample = snapshot(directory)
        reasons = Policy().admission(sample, 3 * 1024**3, 10 * 1024**3)
        if reasons:
            raise RuntimeError(str(reasons))
        profiles = {}
        for name in ("bbb-1080", "bbb-2160"):
            receipt = json.loads((WORK / "corpus" / (name + ".receipt.json")).read_text())
            if receipt["status"] != "completed":
                raise RuntimeError("Corpus is not complete")
            source = Path(receipt["video"])
            profiles[name] = {"input": str(source), "source_sha256": sha256_file(source),
                              "width": receipt["media"]["video"]["width"], "height": receipt["media"]["video"]["height"], "fps": 30}
        if args.mode in ("balanced", "hardware", "acceptance"):
            profiles["bbb-2160-to1080"] = {**profiles["bbb-2160"], "width": 1920, "height": 1080}
            live_path = WORK / "corpus/tos-1080-blender.receipt.json"
            if live_path.is_file():
                live = json.loads(live_path.read_text())
                if live["status"] != "completed":
                    raise RuntimeError("Live-action corpus acquisition incomplete")
                from fractions import Fraction
                fps = Fraction(live["media"]["video"]["avg_frame_rate"])
                if fps.denominator != 1:
                    raise RuntimeError("This calibration requires a native integer-CFR reference")
                profiles["tos-liveaction"] = {"input": live["video"], "source_sha256": sha256_file(Path(live["video"])),
                    "width": live["media"]["video"]["width"], "height": live["media"]["video"]["height"], "fps": int(fps)}
        configurations = {"t2": {"package": str(WORK / "baseline"), "threads": 2},
                          "t4": {"package": str(WORK / "baseline"), "threads": 4}}
        if args.mode == "balanced":
            configurations = {"baseline": {"package": str(WORK / "baseline"), "threads": 2},
                              "balanced": {"package": str(ROOT), "threads": 4,
                                           "parameters": {"decoder_threads": 2, "filter_threads": args.filter_threads, "validation_threads": 4}},
                              "balanced-stock": {"package": str(ROOT), "engine": "stock", "threads": 4,
                                                 "parameters": {"decoder_threads": 2, "filter_threads": args.filter_threads, "validation_threads": 4}}}
        if args.mode == "hardware":
            profiles = {"bbb-2160-to1080": profiles["bbb-2160-to1080"]}
            configurations = {name: {"package": str(ROOT), "threads": 2, "parameters": {
                "encoder": "videotoolbox", "decode": "videotoolbox", "filter_backend": backend,
                "rate_control": "bitrate", "video_bitrate": 6000000, "validation_threads": 4}}
                for name, backend in (("cpu-scale", "software"), ("hardware-scale", "videotoolbox"))}
        if args.mode == "acceptance":
            configurations = {"baseline-native": {"package": str(WORK / "baseline"), "engine": "native"},
                              "candidate-native": {"package": str(ROOT), "engine": "native"},
                              "candidate-stock": {"package": str(ROOT), "engine": "stock"}}
        if args.profile:
            profiles = {name: profiles[name] for name in args.profile}
        report = {"schema_version": 1, "status": "running", "mode": args.mode, "directory": str(directory),
                  "seconds": args.seconds, "trials": args.trials, "start_seconds": 60, "profiles": profiles,
                  "configurations": configurations, "cases": [], "summary": {}, "quality": {},
                  "runner_sha256": sha256_file(Path(__file__).resolve()),
                  "package_source_sha256": {label: {path.name: sha256_file(path) for path in sorted((Path(config["package"]) / "ffv2").glob("*.py"))}
                                             for label, config in configurations.items()},
                  "quality_thresholds": {"vmaf_delta_min": -0.10, "psnr_y_delta_min": -0.05,
                                         "ssim_delta_min": -0.00001, "size_ratio_max": 1.02},
                  "resources": sample.json(), "system_memory_checks_ignored": Policy().ignore_system_memory,
                  "estimated_peak_job_bytes": 3 * 1024**3, "estimated_new_storage_bytes": 10 * 1024**3,
                  "scope": "Natural production animation at native HD/UHD, one excluded warmup/config/profile, sequential seeded paired trials. No universal throughput claim."}
    def save():
        write_json(directory / "report.json", report)
    try:
        if not args.quality_only:
            save()
            rng = random.Random(20261103)
            for trial in range(args.trials + 1):
                pairs = [(profile, label) for profile in profiles for label in configurations]
                rng.shuffle(pairs)
                for profile, label in pairs:
                    configuration = configurations[label]
                    source = profiles[profile]
                    binaries = selected["binaries"] if configuration.get("engine", "native") == "native" else {
                        name: "/opt/homebrew/bin/" + name for name in ("ffmpeg", "ffprobe")}
                    spec = {"operation": "transcode", "input": source["input"], "start": 60, "duration": args.seconds,
                            "output": str(directory / (profile + "-" + label + "-" + str(trial) + ".mp4")),
                            "encoder": "software", "rate_control": "quality", "fps": source.get("fps", 30),
                            "max_width": source["width"], "max_height": source["height"], "timeout_seconds": 1200}
                    if "threads" in configuration:
                        spec["threads"] = configuration["threads"]
                    spec.update(configuration.get("parameters", {}))
                    request = {"package": configuration["package"], "ffmpeg": binaries["ffmpeg"], "ffprobe": binaries["ffprobe"],
                               "state": str(directory / (label + "-state")), "spec": spec, "label": label,
                               "trial": trial, "warmup": trial == 0, "matched_progress": True}
                    start = time.monotonic()
                    child = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--case", json.dumps(request)],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1300)
                    if child.returncode:
                        raise RuntimeError(child.stderr[-4000:])
                    row = json.loads(child.stdout)
                    row.update(profile=profile, process_wall_seconds=time.monotonic() - start)
                    report["cases"].append(row)
                    save()
                    print(json.dumps({"trial": trial, "profile": profile, "label": label, "seconds": round(row["total_seconds"], 3)}), flush=True)
            for profile in profiles:
                for label in configurations:
                    rows = [r for r in report["cases"] if r["profile"] == profile and r["label"] == label and not r["warmup"]]
                    report["summary"][profile + "/" + label] = {"n": len(rows), **{field: statistics.median(r[field] for r in rows)
                        for field in ("total_seconds", "process_wall_seconds", "encode_seconds", "decode_seconds", "bytes")}}
            report["status"] = "timing_completed"
            save()
        from verify_phase2 import Verification
        verify = Verification(Path(selected["install_prefix"]), directory / "quality")
        reuse = json.loads(args.reuse_quality.read_text()) if args.reuse_quality else None
        if reuse and reuse["status"] != "completed":
            raise RuntimeError("Only completed same-file quality may be reused")
        for profile, source in report["profiles"].items():
            for label in report["configurations"]:
                row = next(r for r in report["cases"] if r["profile"] == profile and r["label"] == label and not r["warmup"])
                fps = source.get("fps", 30)
                expected_frames = report["seconds"] * fps
                current_match = next((old for old in report["cases"] if old["profile"] == profile and old["label"] != label and
                                      old["sha256"] == row["sha256"] and profile + "/" + old["label"] in report["quality"]), None)
                if current_match:
                    report["quality"][profile + "/" + label] = {
                        **report["quality"][profile + "/" + current_match["label"]], "reused_same_file_sha256": row["sha256"],
                        "source_index": str(directory / "report.json")}
                    save()
                    continue
                if reuse and reuse["seconds"] == report["seconds"] and reuse["start_seconds"] == report["start_seconds"]:
                    matched = next((old for old in reuse["cases"] if old["sha256"] == row["sha256"] and
                                    reuse["profiles"][old["profile"]]["source_sha256"] == source["source_sha256"]), None)
                    if matched:
                        report["quality"][profile + "/" + label] = {
                            **reuse["quality"][matched["profile"] + "/" + matched["label"]],
                            "reused_same_file_sha256": row["sha256"], "source_index": str(args.reuse_quality)}
                        save()
                        continue
                metric = directory / "quality" / (profile + "-" + label + ".json")
                if not metric.exists():
                    graph = (f"[0:v]trim=end_frame={expected_frames},settb=AVTB,setpts=N/({fps}*TB)[test];"
                             f"[1:v]trim=end_frame={expected_frames},scale={source['width']}:{source['height']}:flags=lanczos,settb=AVTB,setpts=N/({fps}*TB)[ref];"
                             "[test][ref]libvmaf=log_fmt=json:log_path=" + str(metric) + ":n_threads=2:feature=name=psnr|name=float_ssim:shortest=1")
                    verify.aux(profile + "-" + label, [selected["binaries"]["ffmpeg"], "-v", "error", "-nostdin", "-filter_complex_threads", "1",
                         "-threads", "2", "-i", row["output"], "-threads", "2", "-ss", str(report["start_seconds"]), "-i", source["input"],
                         "-filter_complex", graph, "-an", "-threads", "2", "-f", "null", "-"], metric, timeout=1200, budget=64 * 1024**2)
                data = json.loads(metric.read_text())
                if len(data["frames"]) != expected_frames:
                    raise RuntimeError("Quality frame alignment count mismatch")
                report["quality"][profile + "/" + label] = {"frames": len(data["frames"]), "metrics": data["pooled_metrics"], "report": str(metric)}
                save()
        report["status"] = "completed"
        save()
    except BaseException as error:
        report.update(status="failed", error=str(error)[:5000])
        save()
        raise
    print(json.dumps({"report": str(directory / "report.json"), "summary": report["summary"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
