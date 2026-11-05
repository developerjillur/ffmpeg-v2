#!/usr/bin/env python3
"""Built fork-এর real codec/CLI/MCP acceptance; generated local fixture only।"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import uuid
import wave
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ffv2.capabilities import capabilities
from ffv2.config import Settings
from ffv2.engine import library_closure
from ffv2.io import capture, digest, write_json
from ffv2.media import probe_path
from ffv2.planner import build_plan
from ffv2.resources import snapshot
from ffv2.store import Store
from ffv2.worker import host_lock, supervised, work


def checked(argv):
    code, out, err = capture(argv, timeout=30)
    if code:
        raise RuntimeError(err[-3000:])
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True)
    args = parser.parse_args()
    prefix = Path(args.prefix).resolve()
    directory = Settings.load(use_active=False).ensure_state() / "verification" / ("native-media-" + time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True)
    settings = Settings(state=directory / "state", ffmpeg=str(prefix / "bin/ffmpeg"), ffprobe=str(prefix / "bin/ffprobe"))
    store = Store(settings)
    caps = capabilities(settings)
    report = {"schema_version": 1, "directory": str(directory), "install_prefix": str(prefix), "binary_version": caps["ffmpeg_version"],
              "native_jsonl_progress": caps["native_jsonl_progress"], "tests": {}, "status": "running"}
    programs = [prefix / "bin" / name for name in ("ffmpeg", "ffprobe", "ffplay") if (prefix / "bin" / name).is_file()]
    report["verified_files"] = library_closure(programs)
    write_json(directory / "report.json", report)
    ffmpeg, ffprobe = caps["ffmpeg"], caps["ffprobe"]
    reference = directory / "reference.mkv"
    fixture = {"kind": "diagnostic_fixture", "spec": {"operation": "diagnostic_fixture", "output": str(reference)},
               "estimates": {"job_memory_bytes": 512 * 1024 ** 2, "output_budget_bytes": 64 * 1024 ** 2}, "timeout_seconds": 120}
    fixture["plan_id"] = digest(fixture)
    queued = store.enqueue(fixture)
    job = store.claim(queued["id"])
    attempt = store.root / "jobs" / job["id"] / "attempt-001"
    attempt.mkdir(parents=True)
    base = snapshot(directory)
    try:
        with host_lock(settings) as lock_fd:
            command = [ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-n", "-nostats", "-progress_format", "jsonl", "-progress", "pipe:1",
                       "-filter_threads", "1", "-filter_complex_threads", "1", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=4",
                       "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=4", "-map", "0:v:0", "-map", "1:a:0",
                       "-c:v", "ffv1", "-level", "3", "-threads:v", "1", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", "-threads:a", "1",
                       "-t", "4", "-fs", str(64 * 1024 ** 2), "-f", "matroska", str(reference)]
            generated = supervised(command, "fixture", job, attempt, settings, base, lock_fd, reference)
        metadata = probe_path(reference, ffprobe)
        if metadata["duration_seconds"] != 4 or metadata["video"]["codec_name"] != "ffv1":
            raise RuntimeError("Reference fixture mismatch")
        store.update(job["id"], "completed", receipt={"generation": generated, "metadata": metadata})
        report["tests"]["fixture"] = {"status": "pass", "bytes": reference.stat().st_size}
        specifications = [
            ("audio", {"operation": "audio", "input": str(reference), "output": str(directory / "audio.wav"), "audio_rate": 16000}),
            ("software", {"operation": "transcode", "input": str(reference), "output": str(directory / "software.mp4"), "encoder": "software", "video_bitrate": 1_000_000, "rate_control": "bitrate", "fps": 30}),
            ("videotoolbox", {"operation": "transcode", "input": str(reference), "output": str(directory / "videotoolbox.mp4"), "encoder": "videotoolbox", "video_bitrate": 1_000_000, "rate_control": "bitrate", "fps": 30}),
            ("frame", {"operation": "frame", "input": str(directory / "software.mp4"), "output": str(directory / "frame.jpg"), "start": 1}),
            ("contact_sheet", {"operation": "contact_sheet", "input": str(directory / "software.mp4"),
                               "output": str(directory / "sheet.jpg"), "count": 16, "columns": 4,
                               "max_width": 320, "max_height": 180}),
            ("remux", {"operation": "remux", "input": str(directory / "software.mp4"), "output": str(directory / "remux.mkv")}),
        ]
        for name, spec in specifications:
            plan = build_plan(spec, settings, caps)
            queued = store.enqueue(plan)
            work(settings, job_id=queued["id"])
            result = store.get(queued["id"], plan=False)
            write_json(directory / (name + ".job.json"), result)
            if result["status"] != "completed":
                raise RuntimeError(name + ": " + json.dumps(result.get("error"), ensure_ascii=False))
            report["tests"][name] = {"status": "pass", "job_id": result["id"], "bytes": result["receipt"]["output_bytes"],
                                       "encode_wall_seconds": result["receipt"]["encode_wall_seconds"],
                                       "encoding_progress_format": (result["receipt"]["encoding"].get("last_progress") or {}).get("source_format"),
                                       "last_job_progress_phase": (result.get("progress") or {}).get("phase")}
            if name == "contact_sheet":
                sheet = result["receipt"]["contact_sheet"]
                if len(sheet["source_pts_seconds"]) != 16 or any(abs(a - t) > 1 / 30 + 0.002 for a, t in zip(sheet["actual_seconds"], sheet["targets_seconds"])):
                    raise RuntimeError("Contact sheet sample timestamps are inaccurate")
                report["tests"][name]["samples"] = sheet
            write_json(directory / "report.json", report)
        with wave.open(str(directory / "audio.wav"), "rb") as audio:
            samples = array("h", audio.readframes(audio.getnframes()))
            if sys.byteorder != "little": samples.byteswap()
            rms = math.sqrt(sum(value * value for value in samples) / len(samples))
            crossings = sum(a <= 0 < b for a, b in zip(samples, samples[1:]))
            frequency = crossings / (len(samples) / audio.getframerate())
            if not 2000 < rms < 4000 or abs(frequency - 440) > 2:
                raise RuntimeError("Nonzero audio signal changed")
            report["tests"]["audio_signal"] = {"status": "pass", "rms": rms, "frequency_hz": frequency, "frames": len(samples)}
        def packets(path):
            raw = checked([ffprobe, "-v", "error", "-show_packets", "-show_data_hash", "sha256", "-show_entries", "packet=codec_type,stream_index,data_hash", "-of", "json", str(path)])
            data = json.loads(raw)["packets"]
            return {kind: [p["data_hash"] for p in data if p["codec_type"] == kind] for kind in ("video", "audio")}
        before, after = packets(directory / "software.mp4"), packets(directory / "remux.mkv")
        if before != after: raise RuntimeError("Remux packet payload changed")
        report["tests"]["remux_packets"] = {"status": "pass", "video_packets": len(before["video"]), "audio_packets": len(before["audio"])}
        for name, mode in (("jsonl", "jsonl"), ("kv", "kv")):
            raw = checked([ffmpeg, "-v", "error", "-nostdin", "-nostats", "-progress_format", mode, "-progress", "pipe:1", "-f", "lavfi", "-i", "color=size=32x32:rate=2:duration=1", "-threads", "1", "-f", "null", "-"])
            if name == "jsonl":
                rows = [json.loads(line) for line in raw.splitlines()]
                if not rows or rows[-1].get("progress") != "end" or any(r.get("schema_version") != 1 for r in rows): raise RuntimeError("Invalid JSONL progress")
            elif "progress=end\n" not in raw:
                raise RuntimeError("Legacy key/value progress changed")
            report["tests"]["native_progress_" + name] = {"status": "pass"}
        code, _, error = capture([ffmpeg, "-v", "error", "-progress_format", "invalid", "-version"])
        if code == 0 or "invalid" not in error.lower():
            raise RuntimeError("Unknown native progress format was accepted")
        report["tests"]["native_progress_invalid"] = {"status": "pass"}
        env = os.environ.copy(); env.update(FFV2_FFMPEG=ffmpeg, FFV2_FFPROBE=ffprobe)
        requests = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "ffmpeg-v2-verifier", "version": "1"}}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "ffv2_doctor", "arguments": {}}}]
        process = subprocess.run([str(ROOT / "bin/ffv2"), "--state-dir", str(settings.state), "mcp"], input="\n".join(json.dumps(r) for r in requests) + "\n",
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, timeout=20)
        rows = [json.loads(line) for line in process.stdout.splitlines()]
        if process.returncode or rows[-1]["result"].get("isError") or not rows[-1]["result"]["structuredContent"]["capabilities"]["native_jsonl_progress"]:
            raise RuntimeError("Native MCP capability integration failed")
        report["tests"]["mcp_native"] = {"status": "pass"}
        if (prefix / "bin/ffplay").is_file():
            spec = {"kind": "diagnostic_playback", "spec": {"operation": "ffplay", "output": str(directory / "ffplay-receipt.json")},
                    "estimates": {"job_memory_bytes": 512 * 1024 ** 2, "output_budget_bytes": 16 * 1024 ** 2}, "timeout_seconds": 20}
            spec["plan_id"] = digest(spec)
            queued = store.enqueue(spec); job = store.claim(queued["id"])
            attempt = store.root / "jobs" / job["id"] / "attempt-001"; attempt.mkdir(parents=True)
            with host_lock(settings) as lock_fd:
                playback = supervised([str(prefix / "bin/ffplay"), "-hide_banner", "-loglevel", "error", "-nodisp", "-autoexit",
                                       "-t", "0.5", str(directory / "audio.wav")], "ffplay", job, attempt, settings,
                                      snapshot(directory), lock_fd, directory / "audio.wav",
                                      environment={"SDL_AUDIODRIVER": "dummy", "SDL_VIDEODRIVER": "dummy"})
            store.update(job["id"], "completed", receipt=playback)
            write_json(directory / "ffplay-receipt.json", playback)
            report["tests"]["ffplay"] = {"status": "pass", "scope": "Headless SDL dummy audio playback; GUI display not reviewed",
                                             "wall_seconds": playback["wall_seconds"]}
        if library_closure(programs) != report["verified_files"]:
            raise RuntimeError("Native runtime library set changed during media verification")
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed", error=str(error)[:6000])
        write_json(directory / "report.json", report)
        raise
    write_json(directory / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
