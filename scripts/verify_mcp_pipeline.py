#!/usr/bin/python3 -B
"""বাস্তব stdio client থেকে queue/worker/status/output round trip।"""
from __future__ import annotations

import argparse
import json
import math
import os
import selectors
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True)
    parser.add_argument('--launcher', type=Path, default=ROOT/'bin/ffv2')
    parser.add_argument('--client-config', type=Path, help='Python 3.11+: existing ffmpeg-v2 entry দিয়ে fresh isolated connection')
    args = parser.parse_args()
    prefix = Path(args.prefix).resolve()
    directory = Settings.load(use_active=False).ensure_state() / "verification" / (
        "mcp-pipeline-" + time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True, mode=0o700)
    source = directory / "reference.wav"
    samples = array("h", (round(8000 * math.sin(2 * math.pi * 440 * i / 16000)) for i in range(16000)))
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(source), "wb") as audio:
        audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        audio.writeframes(samples.tobytes())
    canonical_source = directory/'reference\nline.wav'
    canonical_source.write_bytes(source.read_bytes())
    source_alias = directory/'reference-alias.wav'
    source_alias.symlink_to(canonical_source.name)
    canonical_output = directory/'output\nline'
    canonical_output.mkdir()
    output_alias = directory/'output-alias'
    output_alias.symlink_to(canonical_output.name, target_is_directory=True)
    environment = os.environ.copy()
    environment.pop('FFV2_IGNORE_SYSTEM_MEMORY', None)
    environment.update(FFV2_FFMPEG=str(prefix / "bin/ffmpeg"), FFV2_FFPROBE=str(prefix / "bin/ffprobe"))
    report = {"schema_version": 1, "directory": str(directory), "install_prefix":str(prefix), "launcher":str(args.launcher), "status": "running", "checks": {}}
    identity = 0
    buffer = bytearray()
    server_command = [str(args.launcher), '--state-dir', str(directory/'state'), 'mcp']
    if args.client_config:
        import tomllib
        entry = tomllib.loads(args.client_config.read_text())['mcp_servers']['ffmpeg-v2']
        if Path(entry['command']).resolve() != (ROOT/'bin/ffv2-release').resolve() or not isinstance(entry.get('args'), list) or entry['args'][-1:] != ['mcp']:
            raise RuntimeError('Known installed launcher and existing stdio entry required')
        server_command = [entry['command'], '--state-dir', str(directory/'state'), *entry['args']]
        report['client_configuration'] = {'path':str(args.client_config), 'entry':'ffmpeg-v2', 'command':entry['command'],
                                          'arguments':entry['args'], 'isolated_state':str(directory/'state')}
    with (directory / "server.stderr.log").open("wb") as log:
        process = subprocess.Popen(server_command,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, env=environment, bufsize=0)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        def send(value):
            process.stdin.write((json.dumps(value) + "\n").encode())
            process.stdin.flush()
        def receive():
            nonlocal buffer
            deadline = time.monotonic() + 30
            while b"\n" not in buffer:
                ready = selector.select(max(0, deadline - time.monotonic()))
                if not ready:
                    raise RuntimeError("MCP response timeout")
                data = os.read(process.stdout.fileno(), 65536)
                if not data:
                    raise RuntimeError("MCP server closed unexpectedly")
                buffer.extend(data)
                if len(buffer) > 1024 ** 2:
                    raise RuntimeError("MCP response exceeded budget")
            line, _, rest = buffer.partition(b"\n")
            buffer = bytearray(rest)
            return json.loads(line)
        def request(method, params):
            nonlocal identity
            identity += 1
            send({"jsonrpc": "2.0", "id": identity, "method": method, "params": params})
            response = receive()
            if response.get("id") != identity or response.get("error"):
                raise RuntimeError("Invalid MCP response: " + json.dumps(response)[:1000])
            return response["result"]
        def call(name, arguments, *, error=False):
            response = request("tools/call", {"name": name, "arguments": arguments})
            if bool(response.get("isError")) != error:
                raise RuntimeError("Unexpected tool result: " + json.dumps(response)[:2000])
            return response.get("structuredContent") if not error else json.loads(response["content"][0]["text"])
        try:
            initialized = request("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                                 "clientInfo": {"name": "ffmpeg-v2-check", "version": "1"}})
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            report['server_info'] = initialized['serverInfo']
            listed = request("tools/list", {})
            if len(listed["tools"]) != 8:
                raise RuntimeError("Tool inventory mismatch")
            planning = next(tool for tool in listed["tools"] if tool["name"] == "ffv2_plan")
            fields = planning["inputSchema"]["properties"]["spec"]["properties"]
            if not {"sampling", "deinterlace", "hdr_policy", "source_peak_nits", "priority", "filter_backend"} <= set(fields):
                raise RuntimeError("Phase 3 typed fields missing from MCP schema")
            if not {'checkpoint_seconds','decoder_threads','filter_threads','validation_threads','tracks','subtitle_file','additional_inputs','image_bit_depth'} <= set(fields):
                raise RuntimeError('Phase 4–6 typed fields missing from MCP schema')
            if not {'concat','subtitle','audio_mix','image'} <= set(fields['operation']['enum']):
                raise RuntimeError('Advanced operations missing from MCP schema')
            report["checks"]["handshake"] = {"status": "pass", "tools": len(listed["tools"]),
                                               "protocol_version": initialized["protocolVersion"], "phase2_schema_fields":True, "phase3_schema_fields":True}
            doctor = call("ffv2_doctor", {})
            report["binary_version"] = doctor["capabilities"]["ffmpeg_version"]
            if not doctor["capabilities"]["native_jsonl_progress"]:
                raise RuntimeError("MCP did not select native fork")
            call("ffv2_probe", {"path": str(source)})
            spec = {"operation": "audio", "input": str(source), "output": str(directory / "output.wav"), "priority": -10}
            input_refusal = call('ffv2_probe', {'path':str(source_alias)}, error=True)
            output_refusal = call('ffv2_plan', {'spec':{**spec, 'output':str(output_alias/'mix.wav')}}, error=True)
            if input_refusal['code'] != 'invalid_input' or output_refusal['code'] != 'invalid_output':
                raise RuntimeError('Canonical path alias refusal failed')
            report['checks']['canonical_path_aliases'] = {'status':'pass', 'input':input_refusal['code'], 'output':output_refusal['code']}
            call("ffv2_plan", {"spec": spec})
            key = "mcp-" + directory.name
            queued = call("ffv2_submit", {"spec": spec, "idempotency_key": key})
            replay = call("ffv2_submit", {"spec": spec, "idempotency_key": key})
            if replay["id"] != queued["id"] or not replay["replayed"]:
                raise RuntimeError("MCP idempotency failed")
            urgent = call("ffv2_submit", {"spec": {**spec, "output": str(directory / "urgent.wav"), "priority": 10}})
            call("ffv2_worker_start", {'ignore_system_memory':True})
            deadline = time.monotonic() + 45
            while True:
                result = call("ffv2_job_status", {"job_id": queued["id"]})
                if result["status"] in ("completed", "failed", "interrupted", "cancelled", "waiting_resources"):
                    break
                if time.monotonic() >= deadline:
                    call("ffv2_job_cancel", {"job_id": queued["id"]})
                    raise RuntimeError("MCP worker completion timeout")
                time.sleep(0.2)
            if result["status"] != "completed":
                raise RuntimeError(json.dumps(result.get("error")))
            if not result['receipt']['encoding']['resource_policy']['ignore_system_memory']:
                raise RuntimeError('Explicit worker-only memory waiver was not applied')
            urgent_result = call("ffv2_job_status", {"job_id": urgent["id"]})
            if (urgent_result["status"] != "completed" or urgent_result["priority"] != 10 or
                    urgent_result["receipt"]["verified_at"] > result["receipt"]["verified_at"]):
                raise RuntimeError("MCP priority ordering failed")
            if sha256_file(Path(spec["output"])) != result["receipt"]["output_sha256"]:
                raise RuntimeError("MCP output checksum mismatch")
            with wave.open(spec["output"], "rb") as audio:
                if audio.readframes(audio.getnframes()) != samples.tobytes():
                    raise RuntimeError("MCP PCM content changed")
            report["checks"]["queue_worker_output"] = {"status": "pass", "job_id": queued["id"],
                                                         "idempotency_replay": True, "pcm_bit_exact": True, "priority_order_verified": True}
            report["checks"]["input_root"] = call("ffv2_probe", {"path": "/etc/hosts"}, error=True)
            report["checks"]["unknown_field"] = call("ffv2_plan", {"spec": {**spec, "raw_argv": []}}, error=True)
            if report["checks"]["input_root"]["code"] != "input_path_denied" or report["checks"]["unknown_field"]["code"] != "invalid_spec":
                raise RuntimeError("MCP input/schema refusal mismatch")
            cancelled_spec = {**spec, "output": str(directory / "cancelled.wav")}
            queued_cancel = call("ffv2_submit", {"spec": cancelled_spec})
            call("ffv2_job_cancel", {"job_id": queued_cancel["id"]})
            cancelled = call("ffv2_job_status", {"job_id": queued_cancel["id"]})
            if cancelled["status"] != "cancelled" or Path(cancelled_spec["output"]).exists():
                raise RuntimeError("MCP queued cancellation failed")
            report["checks"]["queued_cancel"] = {"status": "pass"}
            mixed = call('ffv2_submit', {'spec': {'operation':'audio_mix','input':str(source),'output':str(directory/'mix.wav'),
                'audio_rate':16000,'audio_channels':1,'tracks':[{'input':str(source),'gain_db':-6,'offset':.25}],
                'mix_normalize':False,'primary_gain_db':-6}})
            call('ffv2_worker_start',{'ignore_system_memory':True})
            mix_deadline=time.monotonic()+45
            while True:
                mix_result=call('ffv2_job_status',{'job_id':mixed['id']})
                if mix_result['status'] not in ('queued','running','validating'):
                    break
                if time.monotonic()>mix_deadline:
                    raise RuntimeError('Advanced MCP mix timed out')
                time.sleep(.2)
            if mix_result['status']!='completed':
                raise RuntimeError('Advanced MCP mix failed: '+str(mix_result.get('error')))
            with wave.open(mix_result['output'],'rb') as mixed_audio:
                if (mixed_audio.getframerate(),mixed_audio.getnchannels(),mixed_audio.getnframes())!=(16000,1,16000):
                    raise RuntimeError('Advanced MCP mix output contract mismatch')
            report['checks']['advanced_mix']={'status':'pass','job_id':mixed['id'],'scoped_worker_waiver':True,'samples':16000}
            if fields['threads']['maximum'] == 8:
                if fields['validation_threads']['maximum'] != 8 or fields['decoder_threads']['maximum'] != 4:
                    raise RuntimeError('Phase 8 bounded pool schema mismatch')
                from verify_phase2 import Verification
                proof = Verification(prefix, directory/'video-fixture')
                video = proof.generate('software-threads', 'testsrc2=size=160x90:rate=12:duration=1', '',
                                       duration=1, codec='libx264', extra=('-preset','veryfast'))
                high_spec = {'operation':'transcode','input':str(video),'output':str(directory/'threads8.mp4'),
                             'encoder':'software','threads':8,'decoder_threads':2,'filter_threads':2,
                             'validation_threads':8,'fps':12,'duration':1}
                planned = call('ffv2_plan',{'spec':high_spec})
                if planned['runtime_tuning']['encode_thread_budget'] != 13:
                    raise RuntimeError('MCP high-pool plan exceeded declared budget')
                bad = call('ffv2_plan',{'spec':{**high_spec,'encoder':'videotoolbox'}},error=True)
                over = call('ffv2_plan',{'spec':{**high_spec,'decoder_threads':4,'filter_threads':4}},error=True)
                if bad['code'] != 'invalid_spec' or over['code'] != 'thread_budget_exceeded':
                    raise RuntimeError('MCP high-pool refusal mismatch')
                high = call('ffv2_submit',{'spec':high_spec})
                call('ffv2_worker_start',{'ignore_system_memory':True})
                deadline=time.monotonic()+45
                while True:
                    result=call('ffv2_job_status',{'job_id':high['id']})
                    if result['status'] not in ('queued','running','validating'):
                        break
                    if time.monotonic()>deadline:
                        raise RuntimeError('MCP high-pool media timed out')
                    time.sleep(.2)
                if (result['status']!='completed' or result['receipt']['runtime_tuning']['encoder_threads']!=8 or
                        result['receipt']['runtime_tuning']['validation_threads']!=8 or
                        int(result['receipt']['validation']['full_decode']['last_progress']['frame'])!=12 or
                        sha256_file(Path(result['output']))!=result['receipt']['output_sha256']):
                    raise RuntimeError('MCP high-pool actual output mismatch')
                report['checks']['bounded_software_threads8']={'status':'pass','job_id':high['id'],'frames':12,
                    'output_sha256':result['receipt']['output_sha256'],'schema_threads_max':8,'validation_threads_max':8,
                    'total_encode_budget':13,'hardware_refused':True,'over_budget_refused':True}
            report["tests"] = {"mcp_pipeline":{"status":"pass", "queue_worker_pcm":True,"phase2_schema":True,"phase3_schema":True,
                                              "phase4_6_schema":True,"advanced_mix":True,"priority_order_verified":True,"typed_refusals":True,"queued_cancel":True,"canonical_path_aliases":True}}
            report["status"] = "completed"
        except BaseException as error:
            report.update(status="failed", error=str(error)[:5000])
            raise
        finally:
            write_json(directory / "report.json", report)
            process.stdin.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
            selector.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
