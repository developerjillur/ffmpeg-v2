#!/usr/bin/python3 -B
"""4K Main10 hardware path এবং 600-second timeline-এর bounded acceptance।"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ffv2.capabilities import capabilities
from ffv2.config import Settings
from ffv2.io import digest, sha256_file, write_json
from ffv2.media import probe_path
from ffv2.planner import build_plan
from ffv2.resources import snapshot
from ffv2.store import Store
from ffv2.worker import host_lock, supervised, work


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--reference", required=True, help="4-second FFV1/PCM native-media fixture")
    parser.add_argument("--resume", type=Path, help="Retained verification directory পুনর্ব্যবহার")
    args = parser.parse_args()
    prefix, reference = Path(args.prefix).resolve(), Path(args.reference).resolve(strict=True)
    directory = args.resume.resolve() if args.resume else Settings.load(use_active=False).ensure_state() / "verification" / (
        "large-media-" + time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex[:8])
    if not args.resume:
        directory.mkdir(parents=True, mode=0o700)
    settings = Settings(state=directory / "state", ffmpeg=str(prefix / "bin/ffmpeg"), ffprobe=str(prefix / "bin/ffprobe"))
    caps = capabilities(settings)
    ffmpeg, ffprobe = caps["ffmpeg"], caps["ffprobe"]
    report = {"schema_version": 1, "directory": str(directory), "status": "running", "tests": {},
              "limits": ["Generated fixtures only; a 600-second media timeline is not a 600-second wall-clock soak.",
                         "SDR Main10 path; HDR tone mapping and perceptual colour correctness remain separate."]}
    if args.resume:
        report = json.loads((directory / "report.json").read_text())
        report.update(status="running")
        report.pop("error", None)
    report["install_prefix"] = str(prefix)
    store = Store(settings)
    def save():
        write_json(directory / "report.json", report)
    def aux(argv, name, target, *, budget=192 * 1024 ** 2):
        previous = report["tests"].get(name)
        if previous and previous["status"] == "pass" and target.is_file():
            checksum = sha256_file(target)
            if previous.get("target_sha256", checksum) != checksum:
                raise RuntimeError("Retained diagnostic target changed")
            previous["target_sha256"] = checksum
            return previous
        receipt_path = directory / (name + "-" + uuid.uuid4().hex[:8] + ".diagnostic.json")
        plan = {"kind": "diagnostic", "spec": {"operation": name, "output": str(receipt_path)},
                "estimates": {"job_memory_bytes": 2 * 1024 ** 3, "output_budget_bytes": budget}, "timeout_seconds": 300}
        plan["plan_id"] = digest(plan)
        queued = store.enqueue(plan)
        job = store.claim(queued["id"])
        attempt = store.root / "jobs" / job["id"] / "attempt-001"
        attempt.mkdir(parents=True)
        try:
            with host_lock(settings) as lock_fd:
                receipt = supervised(argv, name, job, attempt, settings, snapshot(directory), lock_fd, target)
        except BaseException as error:
            store.update(job["id"], "failed", error={"code": "diagnostic_failed", "message": str(error)[:1000]})
            raise
        write_json(receipt_path, receipt)
        store.update(job["id"], "completed", receipt=receipt)
        report["tests"][name] = {"status": "pass", "job_id": job["id"], "wall_seconds": receipt["wall_seconds"],
                                 "sampled_peak_footprint_bytes": receipt["peak_job_memory_bytes"]}
        if target.is_file():
            report["tests"][name]["target_sha256"] = sha256_file(target)
        save()
        return receipt
    def media(name, spec):
        previous = report["tests"].get(name)
        if previous and previous["status"] == "pass":
            result = store.get(previous["job_id"], plan=False)
            if result["status"] != "completed" or sha256_file(Path(result["receipt"]["output"])) != result["receipt"]["output_sha256"]:
                raise RuntimeError("Retained media output changed")
            return result
        plan = build_plan(spec, settings, caps)
        queued = store.enqueue(plan)
        work(settings, job_id=queued["id"])
        result = store.get(queued["id"], plan=False)
        if result["status"] != "completed":
            raise RuntimeError(name + ": " + json.dumps(result.get("error"), ensure_ascii=False))
        report["tests"][name] = {"status": "pass", "job_id": result["id"], "receipt": result["receipt"]}
        save()
        return result
    try:
        save()
        source_hash = sha256_file(reference)
        four_k = directory / "main10-4k.mp4"
        aux([ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-n", "-filter_threads", "1",
             "-f", "lavfi", "-i", "testsrc2=size=3840x2160:rate=30:duration=2",
             "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2",
             "-c:v", "hevc_videotoolbox", "-allow_sw", "0", "-profile:v", "main10", "-pix_fmt", "p010le",
             "-b:v", "12M", "-tag:v", "hvc1", "-threads:v", "2", "-color_primaries", "bt709",
             "-color_trc", "bt709", "-colorspace", "bt709", "-c:a", "aac", "-b:a", "128k",
             "-threads:a", "1", "-t", "2", "-movflags", "+faststart", "-fs", str(64 * 1024 ** 2), str(four_k)],
            "hevc_main10_4k_encode", four_k)
        metadata = probe_path(four_k, ffprobe)
        video = metadata["video"]
        if (video["width"], video["height"], video["codec_name"], video["pix_fmt"]) != (3840, 2160, "hevc", "yuv420p10le"):
            raise RuntimeError("4K Main10 output metadata mismatch")
        aux([ffmpeg, "-nostdin", "-v", "error", "-xerror", "-threads", "2", "-filter_threads", "1",
             "-hwaccel", "videotoolbox", "-hwaccel_output_format", "videotoolbox_vld",
             "-i", str(four_k), "-an", "-vf", "hwdownload,format=p010le", "-threads", "2", "-f", "null", "-"],
            "hevc_main10_4k_hwdecode", four_k)
        media("hevc_to_h264_1080p", {"operation": "transcode", "input": str(four_k),
                                    "output": str(directory / "h264-1080p.mp4"), "encoder": "videotoolbox",
                                    "decode": "videotoolbox", "max_width": 1920, "max_height": 1080,
                                    "fps": 30, "video_bitrate": 4_000_000, "rate_control": "bitrate"})
        media("hevc_4k_frame", {"operation": "frame", "input": str(four_k),
                               "output": str(directory / "hevc-frame.jpg"), "start": 1.2})
        remuxed = media("main10_remux", {"operation": "remux", "input": str(four_k),
                                        "output": str(directory / "main10-remux.mkv")})
        output_video = remuxed["receipt"]["validation"]["metadata"]["video"]
        for field in ("pix_fmt", "color_primaries", "color_transfer", "color_space", "width", "height"):
            if output_video.get(field) != video.get(field):
                raise RuntimeError("Main10 remux metadata changed: " + field)
        long_output = directory / "ten-minute.mp4"
        aux([ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-n", "-nostats",
             "-progress_format", "jsonl", "-progress", "pipe:1", "-filter_threads", "1",
             "-threads", "2", "-stream_loop", "149", "-i", str(reference), "-t", "600",
             "-map", "0:v:0", "-map", "0:a:0", "-c:v", "h264_videotoolbox", "-allow_sw", "0",
             "-b:v", "750k", "-pix_fmt", "yuv420p", "-threads:v", "2",
             "-c:a", "aac", "-b:a", "96k", "-threads:a", "1", "-movflags", "+faststart",
             "-fs", str(128 * 1024 ** 2), str(long_output)], "timeline_600s_encode", long_output)
        long_metadata = probe_path(long_output, ffprobe)
        v, a = long_metadata["video"], long_metadata["audio"]
        ends = [float(s.get("start_time", 0)) + float(s["duration"]) for s in (v, a)]
        if (abs(long_metadata["duration_seconds"] - 600) > 0.05 or int(v["nb_frames"]) != 18000 or
                abs(ends[0] - ends[1]) > 0.05):
            raise RuntimeError("Long timeline frame count or A/V endpoint mismatch")
        aux([ffmpeg, "-nostdin", "-v", "error", "-xerror", "-threads", "2", "-i", str(long_output),
             "-map", "0:v:0", "-map", "0:a:0", "-threads", "2", "-f", "null", "-"],
            "timeline_600s_full_decode", long_output)
        report["tests"]["timeline_metadata"] = {"status": "pass", "duration_seconds": long_metadata["duration_seconds"],
                                                 "video_frames": int(v["nb_frames"]), "stream_end_seconds": ends,
                                                 "endpoint_difference_seconds": abs(ends[0] - ends[1]),
                                                 "sha256": sha256_file(long_output), "bytes": long_output.stat().st_size}
        if sha256_file(reference) != source_hash:
            raise RuntimeError("Reference fixture changed")
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed", error=str(error)[:5000])
        save()
        raise
    save()
    print(json.dumps({"status": report["status"], "directory": str(directory),
                      "checks": list(report["tests"]), "timeline": report["tests"]["timeline_metadata"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
