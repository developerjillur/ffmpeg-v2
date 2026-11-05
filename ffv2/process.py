from __future__ import annotations

import os
import json
import re
import selectors
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from .errors import FFV2Error
from .io import terminate
from .resources import Policy, Snapshot, process_memory, snapshot


def execute(request, *, snapshot_fn=snapshot, memory_fn=process_memory,
            cancelled=lambda: False, progress=lambda value: None):
    """স্বাধীন supervisor-এর loop; parent হারালেও নিজের encode বন্ধ করতে পারে।"""
    policy = Policy()
    target = Path(request["output"])
    started = time.monotonic()
    baseline = Snapshot(**request["baseline"])
    current = snapshot_fn(target.parent)
    admission = policy.admission(current, request["estimated_memory"], request.get("admission_output_budget", request["output_budget"]))
    admission += policy.running(current, baseline)
    receipt = {"schema_version": 1, "status": "not_admitted", "argv": request["argv"],
               "supervisor_pid": os.getpid(), "worker_pid": request["owner_pid"], "process_pid": None,
               "resource_policy": asdict(policy),
               "baseline": baseline.json(), "last_snapshot": current.json(), "reasons": sorted(set(admission)),
               "exit_code": None, "peak_job_memory_bytes": 0, "memory_measurement": None,
               "resource_sample_count": 0,
               "job_memory_samples": [], "first_sampled_job_memory_bytes": None, "last_sampled_job_memory_bytes": None,
               "stderr_tail": "", "stdout_tail": "", "wall_seconds": 0.0,
               "decoded_source_pts": None, "decoded_source_pts_samples": [], "decoded_source_pts_by_sample": {}, "last_progress": None}
    def push_progress(value):
        receipt["last_progress"] = value
        progress(value)
    if admission:
        return receipt
    if cancelled():
        receipt.update(status="stopped", reasons=["cancelled"])
        return receipt
    env = os.environ.copy()
    env.update(TMPDIR=request["cwd"], TMP=request["cwd"], TEMP=request["cwd"])
    allowed_env = {"PKG_CONFIG_PATH", "CLANG_MODULE_CACHE_PATH", "MAKEFLAGS", "LC_ALL", "FATE_SAMPLES", "SAMPLES",
                   "SDL_AUDIODRIVER", "SDL_VIDEODRIVER", "PATH", "PYTHONPATH", "FFV2_PINNED_ENGINE", "FFV2_PROJECT_ROOT"}
    extras = request.get("environment", {})
    if not isinstance(extras, dict) or set(extras) - allowed_env or not all(isinstance(v, str) for v in extras.values()):
        raise FFV2Error("invalid_process_environment", "Process environment override অনুমোদিত নয়।")
    env.update(extras)
    process = None
    selector = selectors.DefaultSelector()
    previous = {}
    signalled = []

    def on_signal(number, frame):
        signalled.append(number)

    for sig in (signal.SIGTERM, signal.SIGINT):
        previous[sig] = signal.signal(sig, on_signal)
    tail = bytearray()
    stdout_tail = bytearray()
    line_buffer = bytearray()
    pts_line_buffer = bytearray()
    progress_block = {}
    next_sample = 0.0
    next_disk_sample = 0.0
    next_memory_record = 0.0
    directory_bytes = 0
    log_bytes = 0
    log_limit = 1024 * 1024
    reasons = []
    try:
        from .io import sha256_file, write_json
        trace_path = Path(request["cwd"]) / (request["log_name"] + '.' + uuid.uuid4().hex[:8] + '.resources.jsonl')
        with (Path(request["cwd"]) / request["log_name"]).open("wb") as log, trace_path.open('xb') as trace:
            argv, descriptors = request["argv"], ()
            if request.get('live_process') and 'host_lock_fd' in request:
                from .darwin import process_info
                owner, supervisor = process_info(request['owner_pid']), process_info(os.getpid())
                if not owner or not supervisor:
                    raise OSError('Launcher owner birth identity unavailable')
                launch = {**request, 'owner_birth': owner['start_abstime'], 'supervisor_pid': os.getpid(),
                          'supervisor_birth': supervisor['start_abstime']}
                launch_path = Path(request['live_process']['path']).with_suffix('.launch.json')
                write_json(launch_path, launch)
                argv = [sys.executable, '-B', '-m', 'ffv2.guardian', 'launch', str(launch_path)]
                descriptors = (request['host_lock_fd'],)
                receipt['guardian_launch'] = str(launch_path)
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       cwd=request["cwd"], env=env, start_new_session=True, pass_fds=descriptors)
            receipt["process_pid"] = process.pid
            from .recovery import register
            if not descriptors:
                register(request, process)
            for pipe, name in ((process.stdout, "stdout"), (process.stderr, "stderr")):
                selector.register(pipe, selectors.EVENT_READ, name)
            while selector.get_map() or process.poll() is None:
                now = time.monotonic()
                if signalled:
                    reasons = ["supervisor_signal"]
                elif os.getppid() != request["owner_pid"]:
                    reasons = ["worker_parent_lost"]
                elif cancelled():
                    reasons = ["cancelled"]
                elif now - started > request["timeout_seconds"]:
                    reasons = ["timeout"]
                if not reasons and now >= next_sample:
                    current = snapshot_fn(target.parent)
                    receipt["resource_sample_count"] += 1
                    memory, method = memory_fn(process.pid, (os.getpid(), request["owner_pid"]))
                    receipt["peak_job_memory_bytes"] = max(receipt["peak_job_memory_bytes"], memory)
                    if receipt["first_sampled_job_memory_bytes"] is None:
                        receipt["first_sampled_job_memory_bytes"] = memory
                    receipt["last_sampled_job_memory_bytes"] = memory
                    if now >= next_memory_record:
                        points = receipt["job_memory_samples"]
                        if len(points) >= 64:
                            del points[1]
                        points.append({"elapsed_seconds": round(now - started, 3), "physical_footprint_bytes": memory})
                        trace.write((json.dumps({'elapsed_seconds': round(now-started, 3), 'physical_footprint_bytes': memory,
                            'snapshot': current.json()}, allow_nan=False) + '\n').encode())
                        trace.flush()
                        os.fsync(trace.fileno())
                        next_memory_record = now + 5
                    receipt["memory_measurement"] = method
                    receipt["last_snapshot"] = current.json()
                    if request.get("budget_directory") and now >= next_disk_sample:
                        budget_directory = Path(request["budget_directory"])
                        if budget_directory.is_symlink():
                            raise FFV2Error("budget_directory_changed", "Job-এর storage directory symlink হয়েছে।")
                        if budget_directory.is_dir():
                            raw_size = subprocess.check_output(["/usr/bin/du", "-sk", str(budget_directory)], text=True, timeout=3)
                            directory_bytes = int(raw_size.split()[0]) * 1024
                        next_disk_sample = now + 5
                    size = directory_bytes if request.get("budget_directory") else target.stat().st_size if target.exists() else 0
                    reasons = policy.running(current, baseline, memory, size, request["output_budget"])
                    if method != "physical_footprint":
                        reasons.append("job_memory_measurement_unavailable")
                    next_sample = now + 1.0
                if reasons:
                    terminate(process)
                    break
                if not selector.get_map():
                    # Closed pipes may precede process exit. An empty selector's 150ms
                    # sleep needlessly extends short validation jobs; keep guards live.
                    try:
                        process.wait(timeout=0.02)
                    except subprocess.TimeoutExpired:
                        pass
                    continue
                for key, _ in selector.select(0.15):
                    data = os.read(key.fileobj.fileno(), 16384)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    if key.data == "stderr":
                        tail.extend(data)
                        if len(tail) > 65536:
                            del tail[:-65536]
                        if log_bytes < log_limit:
                            part = data[:log_limit - log_bytes]
                            log.write(part)
                            log_bytes += len(part)
                        pts_line_buffer.extend(data)
                        while b"\n" in pts_line_buffer:
                            pts_line, _, rest = pts_line_buffer.partition(b"\n")
                            pts_line_buffer = bytearray(rest)
                            match = re.search(rb"\bn:\s*\d+.*?\bpts_time:([-+0-9.eE]+)", pts_line)
                            if b"showinfo" in pts_line and match:
                                try:
                                    pts = float(match.group(1))
                                    sample_name = re.search(rb"showinfo@ffv2_sample_(\d+)", pts_line)
                                    if sample_name and int(sample_name.group(1)) < 8:
                                        receipt["decoded_source_pts_by_sample"][sample_name.group(1).decode()] = pts
                                    receipt["decoded_source_pts"] = pts
                                    if len(receipt["decoded_source_pts_samples"]) < 64:
                                        receipt["decoded_source_pts_samples"].append(pts)
                                except ValueError:
                                    pass
                        if len(pts_line_buffer) > 16384:
                            pts_line_buffer.clear()
                    else:
                        if request.get("capture_stdout"):
                            stdout_tail.extend(data)
                            if len(stdout_tail) > 65536:
                                del stdout_tail[:-65536]
                            if log_bytes < log_limit:
                                part = data[:log_limit - log_bytes]
                                log.write(part)
                                log_bytes += len(part)
                        line_buffer.extend(data)
                        while b"\n" in line_buffer:
                            line, _, rest = line_buffer.partition(b"\n")
                            line_buffer = bytearray(rest)
                            text = line.decode("utf-8", "replace").strip()
                            if text.startswith("{") and len(text) <= 8192:
                                try:
                                    record = json.loads(text)
                                    if isinstance(record, dict) and record.get("schema_version") == 1 and record.get("progress") in ("continue", "end"):
                                        raw_time = record.get("out_time_us", record.get("out_time_ms", "0"))
                                        try:
                                            seconds = max(0, int(raw_time) / 1_000_000)
                                        except (ValueError, TypeError):
                                            seconds = 0
                                        push_progress({**record, "out_seconds": seconds, "phase": request["phase"], "source_format": "jsonl"})
                                except (ValueError, TypeError):
                                    pass
                                continue
                            if "=" not in text or len(text) > 8192:
                                continue
                            name, value = text.split("=", 1)
                            if name in ("frame", "fps", "out_time_us", "out_time_ms", "speed", "total_size", "progress"):
                                progress_block[name] = value
                            if name == "progress":
                                # out_time_ms নাম হলেও FFmpeg এটিও microseconds-এ দেয়।
                                raw_time = progress_block.get("out_time_us", progress_block.get("out_time_ms", "0"))
                                try:
                                    seconds = max(0, int(raw_time) / 1_000_000)
                                except ValueError:
                                    seconds = 0
                                push_progress({**progress_block, "out_seconds": seconds, "phase": request["phase"], "source_format": "kv"})
                                progress_block = {}
                        if len(line_buffer) > 8192:
                            line_buffer.clear()
            if process.poll() is None:
                process.wait(timeout=3)
            if descriptors:
                guardian_receipt = Path(request['live_process']['path']).with_suffix('.guardian-receipt.json')
                guardian_deadline = time.monotonic() + 3
                while not guardian_receipt.is_file() and time.monotonic() < guardian_deadline:
                    time.sleep(.01)
                if not guardian_receipt.is_file():
                    raise OSError('Guardian completion acknowledgement unavailable')
                receipt['guardian'] = json.loads(guardian_receipt.read_text())
        receipt['resource_trace'] = {'path': str(trace_path), 'sha256': sha256_file(trace_path),
                                     'bytes': trace_path.stat().st_size, 'interval_seconds': 5}
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            reasons = ["supervisor_interrupted"]
        else:
            reasons = ["watchdog_error"]
            receipt["watchdog_error"] = {"type": type(error).__name__, "message": str(error)[:1000]}
    finally:
        if process:
            terminate(process)
            for pipe in (process.stdout, process.stderr):
                if pipe:
                    pipe.close()
        selector.close()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    receipt.update(status="stopped" if reasons else ("completed" if process and process.returncode == 0 else "failed"),
                   reasons=reasons, exit_code=process.returncode if process else None,
                   wall_seconds=round(time.monotonic() - started, 6),
                   stderr_tail=tail.decode("utf-8", "replace"), log_truncated=log_bytes >= log_limit)
    receipt["stdout_tail"] = stdout_tail.decode("utf-8", "replace")
    if receipt["decoded_source_pts"] is None:
        matches = re.findall(r"pts_time:([-+0-9.eE]+)", receipt["stderr_tail"])
        if matches:
            receipt["decoded_source_pts"] = float(matches[-1])
    return receipt
