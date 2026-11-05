#!/usr/bin/env python3
"""একটি 32 KiB synthetic audio fixture দিয়ে CLI/MCP এবং live admission যাচাই।"""
from __future__ import annotations

import json
import hashlib
import math
import subprocess
import sys
import time
import uuid
import wave
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ffv2.config import Settings
from ffv2.io import sha256_file, write_json


def main():
    identity = time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex[:8]
    directory = Settings.load().ensure_state() / "verification" / identity
    directory.mkdir(parents=True, mode=0o700)
    state = directory / "state"
    source = directory / "one-second.wav"
    samples = array("h", (int(9000 * math.sin(2 * math.pi * 440 * index / 16000)) for index in range(16000)))
    samples[4000], samples[12000] = 24000, -24000
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(source), "wb") as target:
        target.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        target.writeframes(samples.tobytes())
    original = sha256_file(source)
    spec = {"operation": "audio", "input": str(source), "output": str(directory / "output.wav")}
    spec_path = directory / "job.json"
    write_json(spec_path, spec)
    command = [str(ROOT / "bin/ffv2"), "--state-dir", str(state)]

    def cli(arguments, accepted=(0,)):
        run = subprocess.run(command + arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        if run.returncode not in accepted:
            raise RuntimeError(run.stderr[-4000:] or run.stdout[-4000:])
        return run.returncode, json.loads(run.stdout)

    _, doctor = cli(["doctor"])
    write_json(directory / "doctor.json", doctor)
    _, probed = cli(["probe", str(source)])
    _, planned = cli(["plan", str(spec_path)])
    key = "smoke-" + identity
    _, queued = cli(["submit", str(spec_path), "--key", key])
    _, replayed = cli(["submit", str(spec_path), "--key", key])
    if queued["id"] != replayed["id"] or not replayed["replayed"]:
        raise RuntimeError("Idempotency failed")
    worker_code, worked = cli(["worker", "--job-id", queued["id"]], accepted=(0, 75))
    _, status = cli(["status", queued["id"], "--events"])
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "ffv2_job_status", "arguments": {"job_id": queued["id"]}}},
    ]
    wire = subprocess.run(command + ["mcp"], input="\n".join(json.dumps(value) for value in requests) + "\n",
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
    if wire.returncode or wire.stderr:
        raise RuntimeError("MCP wire process failed: " + wire.stderr[-1000:])
    responses = [json.loads(line) for line in wire.stdout.splitlines()]
    if len(responses) != 3 or len(responses[1]["result"]["tools"]) != 8 or responses[2]["result"].get("isError"):
        raise RuntimeError("MCP handshake/status failed")
    unchanged = original == sha256_file(source)
    if not unchanged:
        raise RuntimeError("Source changed")
    pcm_verified = False
    pcm_digest = None
    if status["status"] == "waiting_resources":
        if Path(spec["output"]).exists() or any((state / "jobs").glob("*/*/encode.request.json")):
            raise RuntimeError("A resource-refused job reached encode")
        cli(["cancel", queued["id"]])
    elif status["status"] != "completed":
        raise RuntimeError("Unexpected job state: " + status["status"])
    else:
        with wave.open(str(source), "rb") as original_pcm, wave.open(spec["output"], "rb") as result_pcm:
            params = lambda stream: (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getnframes())
            original_frames = original_pcm.readframes(original_pcm.getnframes())
            output_frames = result_pcm.readframes(result_pcm.getnframes())
            pcm_verified = params(original_pcm) == params(result_pcm) and original_frames == output_frames
            pcm_digest = hashlib.sha256(output_frames).hexdigest()
            if not pcm_verified:
                raise RuntimeError("PCM content or parameters changed")
    report = {"schema_version": 1, "verified_at_unix": time.time(), "receipt_directory": str(directory),
              "fixture_bytes": source.stat().st_size, "source_unchanged": unchanged,
              "fixture_signal": "440 Hz sine with positive/negative impulses; nonzero PCM",
              "pcm_content_verified": pcm_verified, "output_pcm_sha256": pcm_digest,
              "probe_duration_seconds": probed["duration_seconds"], "plan_id": planned["plan_id"],
              "idempotency_replay": True, "mcp_wire_handshake": "pass", "mcp_tools": 8,
              "worker_exit_code": worker_code, "worker_status": status["status"],
              "resource_admission_reasons": (status.get("error") or {}).get("details", {}).get("reasons", []),
              "actual_encode_completed": status["status"] == "completed",
              "speedup_measured": False, "source_fork_build_tested": False}
    write_json(directory / "control-plane.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
