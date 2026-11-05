#!/usr/bin/python3 -B
"""Phase 3 hardware scaling, quality ও owned-supervisor-loss acceptance।"""
from __future__ import annotations
from public_paths import lab_path, project_path

import argparse
import json
import os
from pathlib import Path
import random
import signal
import statistics
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ffv2.darwin import process_info
from ffv2.errors import FFV2Error
from ffv2.io import capture, sha256_file, write_json
from ffv2.resources import Policy, snapshot
from ffv2.worker import host_lock
from verify_phase2 import Verification


def helper(prefix, directory):
    verify = Verification(prefix, directory)
    try:
        verify.aux("fault", [verify.caps["ffmpeg"], "-v", "error", "-nostdin", "-nostats", "-progress", "pipe:1", "-stats_period", "0.2",
                   "-re", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=30", "-c:v", "libx264", "-threads", "1", "-f", "null", "-"],
                   directory / "not-published", timeout=40)
    except FFV2Error as error:
        write_json(directory / "helper-result.json", {"error": error.payload()})
        return 0
    raise RuntimeError("Supervisor loss helper unexpectedly completed")


def supervisor_loss(verify):
    area = verify.directory / "supervisor-loss"
    area.mkdir()
    with (area / "helper.stderr").open("wb") as log:
        child = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve()), "--prefix", str(verify.prefix),
                                  "--directory", str(area), "--helper"], stdout=subprocess.DEVNULL, stderr=log, start_new_session=True)
        try:
            deadline = time.monotonic() + 20
            record = None
            while time.monotonic() < deadline:
                records = list((area / "state/jobs").glob("*/attempt-001/fault.request.live.json"))
                if records:
                    record = json.loads(records[0].read_text())
                    from ffv2.store import Store
                    from ffv2.config import Settings
                    store = Store(Settings(state=area / "state"))
                    if store.list(1)[0].get("progress"):
                        break
                if child.poll() is not None:
                    raise RuntimeError("Fault helper exited before live media")
                time.sleep(0.05)
            else:
                raise RuntimeError("Live supervisor registration/progress not available")
            if record["worker_pid"] != child.pid:
                raise RuntimeError("Unexpected supervisor owner")
            code, out, err = capture(["/bin/ps", "-p", str(record["supervisor_pid"]), "-o", "ppid="], timeout=3)
            if code or int(out.strip()) != child.pid:
                raise RuntimeError("Supervisor is not the helper's child")
            os.kill(record["supervisor_pid"], signal.SIGKILL)
            child.wait(timeout=12)
            result = json.loads((area / "helper-result.json").read_text())
            cleanup = result["error"].get("details", {}).get("owned_process_recovery", {})
            if result["error"]["code"] != "supervisor_failed" or cleanup.get("status") not in ("stopped", "kill_sent"):
                raise RuntimeError("Owned recovery did not run: " + str(result))
            info = process_info(record["pid"])
            if info and not info["exit_abstime"]:
                raise RuntimeError("Registered media survived supervisor loss")
            with host_lock(verify.settings):
                pass
            return {"status": "pass", "live_registration": record, "recovery": cleanup, "media_gone": True,
                    "host_lock_released": True, "output_not_published": not (area / "not-published").exists(),
                    "limits": "Worker remains alive; registration window and simultaneous worker+supervisor SIGKILL have no kernel guarantee."}
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=12)


def hardware(verify):
    source = verify.generate("source-4k8", "testsrc2=size=3840x2160:rate=30:duration=3",
                            "setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709",
                            duration=3, codec="h264_videotoolbox", pix_fmt="yuv420p",
                            extra=("-allow_sw", "0", "-b:v", "20000000"))
    from ffv2.media import probe_path
    metadata = probe_path(source, verify.caps["ffprobe"])
    if metadata["video"]["pix_fmt"] != "yuv420p" or metadata["video"]["color_range"] != "tv":
        raise RuntimeError("Expected 8bit limited-range fixture")
    rows = []
    rng = random.Random(20261103)
    for trial in range(8):
        backends = ["software", "videotoolbox"]
        rng.shuffle(backends)
        for backend in backends:
            start = time.monotonic()
            result = verify.media("scale-" + backend + "-" + str(trial),
                      {"operation": "transcode", "input": str(source), "output": str(verify.directory / ("scale-" + backend + "-" + str(trial) + ".mp4")),
                       "encoder": "videotoolbox", "decode": "videotoolbox", "filter_backend": backend,
                       "max_width": 1920, "max_height": 1080, "video_bitrate": 6_000_000, "fps": 30})
            receipt = result["receipt"]
            if not receipt["hardware_decode_runtime_verified"] or receipt["hardware_filter_runtime_verified"] != (backend == "videotoolbox"):
                raise RuntimeError("Hardware path runtime flag mismatch")
            rows.append({"trial": trial, "warmup": trial == 0, "backend": backend, "output": result["output"],
                         "total_seconds": time.monotonic() - start, "encode_seconds": receipt["encode_wall_seconds"],
                         "job_seconds": receipt["phase_timings_seconds"]["total"], "bytes": receipt["output_bytes"],
                         "peak_footprint": receipt["encoding"]["peak_job_memory_bytes"]})
    summary, quality = {}, {}
    for backend in ("software", "videotoolbox"):
        selected = [r for r in rows if r["backend"] == backend and not r["warmup"]]
        summary[backend] = {"n": len(selected), **{field: statistics.median(r[field] for r in selected)
                           for field in ("total_seconds", "job_seconds", "encode_seconds", "bytes", "peak_footprint")}}
        metric = verify.directory / ("quality-" + backend + ".json")
        graph = ("[0:v]settb=AVTB,setpts=N/(30*TB)[main];"
                 "[1:v]scale=1920:1080:flags=lanczos,settb=AVTB,setpts=N/(30*TB)[ref];"
                 "[main][ref]libvmaf=log_fmt=json:log_path=" + str(metric) + ":n_threads=2:feature=name=psnr|name=float_ssim:shortest=1")
        verify.aux("quality-" + backend, [verify.caps["ffmpeg"], "-v", "error", "-nostdin", "-filter_complex_threads", "1", "-threads", "2",
                    "-i", selected[0]["output"], "-threads", "2", "-i", str(source), "-filter_complex", graph, "-an", "-threads", "2", "-f", "null", "-"], metric)
        data = json.loads(metric.read_text())
        if len(data["frames"]) != 90:
            raise RuntimeError("Expected 90 aligned quality frames")
        quality[backend] = {"frames": 90, "pooled_metrics": data["pooled_metrics"]}
    return {"status": "pass", "source": str(source), "source_sha256": sha256_file(source), "rows": rows,
            "summary": summary, "quality": quality,
            "limits": "7 trials plus excluded warmup per path; synthetic 4K H264 8bit SDR ->1080p H264. Different interpolation, opt-in only; no universal zero-copy guarantee."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True, type=Path)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--helper", action="store_true")
    parser.add_argument("--mode", choices=("all", "hardware", "fault"), default="all")
    args = parser.parse_args()
    directory = args.directory or Path(str(lab_path('ffmpeg-v2-phase3'))) / ("acceptance-" + time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex[:8])
    if args.helper:
        return helper(args.prefix, directory)
    verify = Verification(args.prefix.resolve(), directory)
    sample = snapshot(directory)
    reasons = Policy().admission(sample, 3 * 1024**3, 512 * 1024**2)
    if reasons:
        raise RuntimeError(str(reasons))
    verify.report.update(phase=3, baseline_resources=sample.json(), estimated_peak_job_bytes=3 * 1024**3,
                         estimated_new_storage_bytes=512 * 1024**2, system_memory_checks_ignored=Policy().ignore_system_memory)
    try:
        if args.mode in ("all", "hardware"):
            verify.report["tests"]["hardware_frame_scaling"] = hardware(verify)
            verify.save()
        if args.mode in ("all", "fault"):
            verify.report["tests"]["supervisor_loss"] = supervisor_loss(verify)
            verify.save()
        verify.report["status"] = "completed"
        verify.save()
    except BaseException as error:
        verify.report.update(status="failed", error=str(error)[:5000])
        verify.save()
        raise
    print(json.dumps({"status": "completed", "report": str(directory / "report.json")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
