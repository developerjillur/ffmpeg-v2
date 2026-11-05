#!/usr/bin/python3 -B
"""একই fixture-এ installed/native encoding ও batched frame workflow পরিমাপ।"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ffv2.capabilities import capabilities
from ffv2.config import Settings
from ffv2.io import digest, sha256_file, write_json
from ffv2.planner import build_plan
from ffv2.resources import snapshot
from ffv2.store import Store
from ffv2.worker import host_lock, supervised, work


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--trials", type=int, choices=(2, 3, 4, 5), default=3)
    parser.add_argument("--quality-only", type=Path, help="Existing report-এর outputs reuse করে aligned quality report তৈরি")
    args = parser.parse_args()
    prefix = Path(args.prefix).resolve(strict=True)
    directory = args.quality_only.resolve().parent if args.quality_only else Settings.load(use_active=False).ensure_state() / "verification" / (
        "benchmark-native-" + time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex[:8])
    if not args.quality_only:
        directory.mkdir(mode=0o700, parents=True)
    settings = {
        "installed": Settings(state=directory / "installed-state", ffmpeg="/opt/homebrew/bin/ffmpeg", ffprobe="/opt/homebrew/bin/ffprobe"),
        "native": Settings(state=directory / "native-state", ffmpeg=str(prefix / "bin/ffmpeg"), ffprobe=str(prefix / "bin/ffprobe")),
    }
    caps = {key: capabilities(value) for key, value in settings.items()}
    ffmpeg = caps["native"]["ffmpeg"]
    report = {"schema_version": 1, "status": "running", "directory": str(directory), "install_prefix": str(prefix),
              "source_kind": "generated testsrc2 plus 440 Hz sine; 6 seconds, 1280x720, 30 fps, FFV1/PCM",
              "binaries": {key: {k: value[k] for k in ("ffmpeg", "ffmpeg_version", "build_configuration")} for key, value in caps.items()},
              "trials": args.trials, "seed": 20261102, "encoder_results": [], "frame_trials": [],
              "limits": ["Synthetic short workload on a busy computer; no all-workload or long-form speed claim.",
                         "Same settings are used; compiler/config differences exist between installed and native builds.",
                         "No warmup exclusion; medians retain cold-start/metadata/validation overhead.",
                         "Frame baseline excludes final mosaic assembly, favouring the old per-frame approach."]}

    def save():
        write_json(directory / "report.json", report)

    def aux(argv, name, output, *, budget=64 * 1024 ** 2, timeout=120):
        config = settings["native"]
        store = Store(config)
        plan = {"kind": "diagnostic", "spec": {"operation": name, "output": str(output)},
                "estimates": {"job_memory_bytes": 1024 ** 3, "output_budget_bytes": budget}, "timeout_seconds": timeout}
        plan["plan_id"] = digest(plan)
        queued = store.enqueue(plan)
        job = store.claim(queued["id"])
        attempt = store.root / "jobs" / job["id"] / "attempt-001"
        attempt.mkdir(parents=True)
        with host_lock(config) as lock_fd:
            receipt = supervised(argv, name, job, attempt, config, snapshot(directory), lock_fd, output)
        store.update(job["id"], "completed", receipt=receipt)
        return receipt

    def media(engine, spec):
        started = time.monotonic()
        config = settings[engine]
        plan = build_plan(spec, config, caps[engine])
        store = Store(config)
        queued = store.enqueue(plan)
        work(config, job_id=queued["id"])
        result = store.get(queued["id"], plan=False)
        if result["status"] != "completed":
            raise RuntimeError(json.dumps(result.get("error"), ensure_ascii=False))
        return result, time.monotonic() - started

    def quality(engine, encoder, output, reference, metric_path):
        # Matroska millisecond timestamps and MP4 rational timestamps differ.
        # This known 30fps fixture is compared by decoded frame number.
        graph = ("[0:v]settb=AVTB,setpts=N/(30*TB)[main];[1:v]settb=AVTB,setpts=N/(30*TB)[ref];"
                 "[main][ref]libvmaf=log_fmt=json:log_path=" + str(metric_path) +
                 ":n_threads=2:feature=name=psnr|name=float_ssim:shortest=1")
        aux([ffmpeg, "-v", "error", "-nostdin", "-filter_complex_threads", "1",
             "-threads", "2", "-i", str(output), "-threads", "2", "-i", str(reference),
             "-filter_complex", graph, "-an", "-threads", "2", "-f", "null", "-"], "quality", metric_path)
        data = json.loads(metric_path.read_text())
        if len(data["frames"]) != 180:
            raise RuntimeError("Quality comparison must contain exactly 180 aligned frames")
        return {"frames": len(data["frames"]), "pooled_metrics": data["pooled_metrics"], "metric_path": str(metric_path)}

    if args.quality_only:
        cached = json.loads(args.quality_only.read_text())
        reference = directory / "reference.mkv"
        if cached["status"] != "completed" or cached["install_prefix"] != str(prefix) or sha256_file(reference) != cached["reference_sha256"]:
            raise RuntimeError("Completed matching benchmark receipt required")
        measured = {}
        token = uuid.uuid4().hex[:8]
        for row in cached["encoder_results"]:
            key = row["engine"] + "-" + row["encoder"]
            if key in measured:
                continue
            output = directory / (key + "-" + str(row["trial"]) + ".mp4")
            if sha256_file(output) != row["sha256"]:
                raise RuntimeError("Retained benchmark output changed")
            measured[key] = quality(row["engine"], row["encoder"], output, reference, directory / (key + "-aligned-" + token + ".json"))
        result = {"schema_version": 1, "status": "completed", "benchmark_report": str(args.quality_only.resolve()),
                  "alignment": "decoded frame number, 30fps, exactly 180 frames", "quality": measured,
                  "supersedes": "Original timestamp-only quality comparison had 181 frame-sync samples"}
        output = directory / ("quality-aligned-report-" + token + ".json")
        write_json(output, result)
        print(json.dumps({"status": "completed", "report": str(output)}, ensure_ascii=False, indent=2))
        return 0

    try:
        save()
        reference = directory / "reference.mkv"
        aux([ffmpeg, "-v", "error", "-nostdin", "-n", "-filter_threads", "1", "-filter_complex_threads", "1",
             "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=6",
             "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=6",
             "-c:v", "ffv1", "-level", "3", "-pix_fmt", "yuv420p", "-threads:v", "1",
             "-c:a", "pcm_s16le", "-threads:a", "1", "-t", "6", "-fs", str(256 * 1024 ** 2), str(reference)],
            "benchmark-fixture", reference, budget=256 * 1024 ** 2)
        report["reference_sha256"] = sha256_file(reference)
        order = [(engine, encoder, trial) for trial in range(args.trials)
                 for engine in ("installed", "native") for encoder in ("software", "videotoolbox")]
        random.Random(report["seed"]).shuffle(order)
        report["encoder_order"] = order
        first_outputs = {}
        for engine, encoder, trial in order:
            output = directory / (f"{engine}-{encoder}-{trial}.mp4")
            spec = {"operation": "transcode", "input": str(reference), "output": str(output), "duration": 6,
                    "encoder": encoder, "video_bitrate": 4_000_000, "rate_control": "bitrate", "fps": 30,
                    "max_width": 1280, "max_height": 720, "threads": 2}
            result, elapsed = media(engine, spec)
            receipt = result["receipt"]
            row = {"engine": engine, "encoder": encoder, "trial": trial, "job_id": result["id"],
                   "encode_seconds": receipt["encode_wall_seconds"], "validation_seconds": receipt["validation_wall_seconds"],
                   "pipeline_seconds": elapsed, "bytes": receipt["output_bytes"], "sha256": receipt["output_sha256"]}
            report["encoder_results"].append(row)
            if (engine, encoder) not in first_outputs:
                first_outputs[engine, encoder] = output
            save()
        for (engine, encoder), output in first_outputs.items():
            metric_path = directory / (engine + "-" + encoder + "-quality.json")
            report.setdefault("quality", {})[engine + "-" + encoder] = quality(engine, encoder, output, reference, metric_path)
            save()
        source = first_outputs["native", "software"]
        sample_targets = [i * 6 / 16 for i in range(16)]
        frame_order = [(mode, trial) for trial in range(args.trials) for mode in ("individual", "batch")]
        random.Random(report["seed"] + 1).shuffle(frame_order)
        report["frame_order"] = frame_order
        expected_pts = None
        for mode, trial in frame_order:
            started = time.monotonic()
            actuals = []
            if mode == "individual":
                for index, target in enumerate(sample_targets):
                    result, _ = media("native", {"operation": "frame", "input": str(source),
                                                "output": str(directory / f"frame-{trial}-{index}.jpg"), "start": target,
                                                "max_width": 320, "max_height": 180, "threads": 2})
                    actuals.append(result["receipt"]["frame"]["actual_seconds"])
            else:
                result, _ = media("native", {"operation": "contact_sheet", "input": str(source),
                                            "output": str(directory / f"sheet-{trial}.jpg"), "count": 16, "columns": 4,
                                            "duration": 6, "max_width": 320, "max_height": 180, "threads": 2})
                actuals = result["receipt"]["contact_sheet"]["actual_seconds"]
            if expected_pts is not None and any(abs(a - b) > 0.00001 for a, b in zip(actuals, expected_pts)):
                raise RuntimeError("Batched and individually decoded source timestamps differ")
            expected_pts = actuals
            report["frame_trials"].append({"mode": mode, "trial": trial, "pipeline_seconds": time.monotonic() - started,
                                            "actual_seconds": actuals})
            save()
        report["encoder_medians"] = {
            engine + "-" + encoder: statistics.median(row["encode_seconds"] for row in report["encoder_results"]
                                                       if row["engine"] == engine and row["encoder"] == encoder)
            for engine in settings for encoder in ("software", "videotoolbox")}
        report["installed_over_native_encode_ratio"] = {
            encoder: report["encoder_medians"]["installed-" + encoder] / report["encoder_medians"]["native-" + encoder]
            for encoder in ("software", "videotoolbox")}
        report["frame_medians"] = {
            mode: statistics.median(row["pipeline_seconds"] for row in report["frame_trials"] if row["mode"] == mode)
            for mode in ("individual", "batch")}
        report["individual_over_batch_ratio"] = report["frame_medians"]["individual"] / report["frame_medians"]["batch"]
        report.update(status="completed", same_frame_timestamps=True)
        save()
    except BaseException as error:
        report.update(status="failed", error=str(error)[:6000])
        save()
        raise
    print(json.dumps({k: report[k] for k in ("status", "directory", "encoder_medians",
                                           "installed_over_native_encode_ratio", "frame_medians",
                                           "individual_over_batch_ratio")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
