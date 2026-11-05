from __future__ import annotations

import fcntl
import json
import math
import os
import re
import subprocess
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .capabilities import capabilities
from .bindings import assert_current, assert_sources, assert_workflow
from .config import check_mounts
from .controller import SupervisorSession
from .errors import FFV2Error
from .io import digest, fingerprint, output_path, sha256_file, write_json
from .media import INPUT_LIMITS, probe_path, rational
from .resources import Policy, process_memory, snapshot
from .store import Store


@contextmanager
def host_lock(settings):
    path = settings.host_lock
    check_mounts(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise FFV2Error("worker_busy", "এই Mac-এ আরেকটি FFmpeg-v2 worker চলছে।", retryable=True, exit_code=75) from error
        yield fd
    finally:
        # fd supervisor-এ inherited; worker crash হলেও watchdog শেষ না হওয়া পর্যন্ত lock থাকে।
        os.close(fd)


def checked_plan(job, settings):
    plan = job["plan"]
    assert_workflow(plan)
    unhashed = {k: v for k, v in plan.items() if k not in ("plan_id", "display_command")}
    if digest(unhashed) != plan["plan_id"]:
        raise FFV2Error("plan_modified", "Saved plan-এর digest মেলেনি।")
    source = Path(plan["source"]["path"])
    check_mounts(source)
    assert_sources(plan)
    output_path(plan["spec"]["output"], source, settings)
    current = capabilities(settings, identity_only=True)
    # Unchanged file identities already bind the probed versions; no repeated help/list processes.
    if any(current.get(k) != value for k, value in plan["binary"].items() if k not in ("ffmpeg_version", "ffprobe_version", "runtime_binding")):
        raise FFV2Error("binary_changed", "Planning-এর পর FFmpeg/ffprobe বদলেছে; নতুন plan প্রয়োজন।")
    if plan["binary"].get("runtime_binding"):
        assert_current(plan["binary"]["runtime_binding"])
    return plan


def supervised(argv, phase, job, directory, settings, baseline, lock_fd, target, *, admission_budget=None,
               cwd=None, process_kind="media", timeout=None, environment=None, session=None):
    plan = job["plan"]
    process_timeout = timeout or plan['timeout_seconds']
    if job.get('_deadline'):
        process_timeout = min(process_timeout, job['_deadline'] - time.monotonic())
        if process_timeout <= 0:
            raise FFV2Error('job_timeout', 'Job-এর মোট elapsed-time budget শেষ; partial/checkpoint রাখা হয়েছে।', retryable=True)
    request_path = directory / (phase + ".request.json")
    request = {"argv": argv, "phase": phase, "cwd": str(cwd or directory),
               "log_name": phase + "-" + job["id"][:8] + "-a" + str(job["attempt"]) + ".stderr.log",
               "state": str(settings.state), "job_id": job["id"], "owner_pid": os.getpid(),
               "output": str(target), "estimated_memory": plan["estimates"]["job_memory_bytes"],
               "output_budget": plan["estimates"]["output_budget_bytes"],
               "admission_output_budget": plan["estimates"]["output_budget_bytes"] if admission_budget is None else admission_budget,
               "timeout_seconds": process_timeout, "baseline": baseline.json(),
               "capture_stdout": process_kind != "media", "environment": environment or {}, "host_lock_fd": lock_fd}
    request["live_process"] = {"path": str(request_path.with_suffix(".live.json")), "nonce": uuid.uuid4().hex}
    if process_kind != "media":
        request["budget_directory"] = str(target)
    write_json(request_path, request)
    if session:
        session.run(request_path, request["timeout_seconds"], job["id"])
    else:
        with SupervisorSession(settings, lock_fd) as controller:
            controller.run(request_path, request["timeout_seconds"], job["id"])
    receipt_path = request_path.with_suffix(".receipt.json")
    if not receipt_path.exists():
        raise FFV2Error("supervisor_failed", "Supervisor-এর নির্ভরযোগ্য receipt নেই।", details={"diagnostic": str(directory / (phase + ".supervisor.log"))})
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt["status"] != "completed":
        reason = receipt.get("reasons", [])
        code = "resource_not_admitted" if receipt["status"] == "not_admitted" else "cancelled" if "cancelled" in reason else "resource_stopped" if receipt["status"] == "stopped" else "ffmpeg_failed"
        if code == "ffmpeg_failed":
            if process_kind != "media":
                code = "upstream_process_failed"
            elif any(t in receipt.get("stderr_tail", "").lower() for t in ("compression session", "videotoolbox", "hardware encoder", "hwdownload", "hardware frames")):
                code = "hardware_unavailable"
        raise FFV2Error(code, "Media process সম্পূর্ণ হয়নি; receipt ও partial রাখা হয়েছে।",
                        details={"receipt": str(receipt_path), "reasons": reason, "stderr": receipt.get("stderr_tail", "")[-4000:],
                                 "stdout": receipt.get("stdout_tail", "")[-2000:]},
                        retryable=True, exit_code=75 if code.startswith("resource_") else 130 if code == "cancelled" else 1)
    return receipt


def validate_metadata(plan, media):
    expected = plan["expected"]
    operation = plan["spec"]["operation"]
    problems = []
    if operation == "remux" or expected.get("stream_codecs") is not None:
        actual = sorted((s["codec_type"], s["codec_name"]) for s in media["streams"])
        if actual != [tuple(s) for s in expected["stream_codecs"]]:
            problems.append("stream_codecs")
    else:
        for name in ("video", "audio"):
            stream = media[name]
            codec = expected.get(name + "_codec")
            if (stream or {}).get("codec_name") != codec:
                problems.append(name + "_codec")
            count = sum(s["codec_type"] == name for s in media["streams"])
            if count != expected.get(name + "_streams", 0):
                problems.append(name + "_stream_count")
        for name in ("width", "height"):
            if name in expected and (media["video"] or {}).get(name) != expected[name]:
                problems.append(name)
        for key, actual in (("audio_rate", (media["audio"] or {}).get("sample_rate")),
                            ("audio_channels", (media["audio"] or {}).get("channels"))):
            if key in expected and int(actual or 0) != expected[key]:
                problems.append(key)
        if "audio_samples" in expected:
            audio = media["audio"] or {}
            try:
                samples = round(int(audio["duration_ts"]) * rational(audio["time_base"]) * int(audio["sample_rate"]))
            except (KeyError, TypeError, ValueError):
                samples = None
            if samples != expected["audio_samples"]:
                problems.append("audio_samples")
        if expected.get("fps"):
            actual_fps = rational((media["video"] or {}).get("avg_frame_rate"))
            if abs(actual_fps - expected["fps"]) > 0.01:
                problems.append("fps")
        if expected.get("progressive") and operation not in ("frame", "contact_sheet", "image") and (media["video"] or {}).get("field_order") != "progressive":
            problems.append("field_order")
        for key in ("color_primaries", "color_transfer", "color_space", "color_range"):
            if key in expected and (media["video"] or {}).get(key) != expected[key]:
                problems.append(key)
    if operation not in ("frame", "contact_sheet", "image"):
        duration = expected["duration_seconds"]
        tolerance = 0.5 if operation == "remux" else max(0.2, 2 / (expected.get("fps") or 24) + 0.1)
        if abs(media["duration_seconds"] - duration) > tolerance:
            problems.append("duration")
    if problems:
        raise FFV2Error("output_validation_failed", "Output metadata পরিকল্পনার সঙ্গে মেলেনি।", details={"mismatches": problems, "actual": media})


def hash_guarded(path, settings, baseline, store, job_id):
    import hashlib
    result = hashlib.sha256()
    next_check = 0.0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            if store.cancelled(job_id):
                raise FFV2Error("cancelled", "Hash যাচাইয়ের সময় job বাতিল হয়েছে।", exit_code=130)
            if time.monotonic() >= next_check:
                sample = snapshot(path.parent)
                memory, method = process_memory(os.getpid())
                reasons = Policy().running(sample, baseline, memory)
                if method != "physical_footprint":
                    reasons.append("job_memory_measurement_unavailable")
                if reasons:
                    raise FFV2Error("resource_stopped", "Hash যাচাই resource gate-এ থেমেছে।", details={"reasons": reasons}, exit_code=75)
                next_check = time.monotonic() + 1
            result.update(chunk)
    return result.hexdigest()


def perform(job, settings, lock_fd, store, *, session=None):
    started = checkpoint = time.monotonic()
    timings = {}
    def mark(name):
        nonlocal checkpoint
        now = time.monotonic()
        timings[name] = round(now - checkpoint, 6)
        checkpoint = now
    supervisor_options = {"session": session} if session else {}
    directory = store.root / "jobs" / job["id"] / ("attempt-%03d" % job["attempt"])
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    job_receipt = {"job_id": job["id"], "attempt": job["attempt"], "status": "started", "directory": str(directory),
                   "system_memory_checks_ignored": Policy().ignore_system_memory}
    phase = "planning"
    try:
        plan = checked_plan(job, settings)
        job['_deadline'] = started + plan['timeout_seconds']
        job_receipt["runtime_tuning"] = plan.get("runtime_tuning", {"validation_threads": 2, "profile": "legacy"})
        write_json(directory / "plan.json", plan)
        destination = Path(plan["spec"]["output"])
        baseline = snapshot(destination.parent)
        reasons = Policy().admission(baseline, plan["estimates"]["job_memory_bytes"], plan["estimates"].get("admission_output_budget_bytes", plan["estimates"]["output_budget_bytes"]))
        if reasons:
            raise FFV2Error("resource_not_admitted", "Media job চালানোর headroom নেই।",
                            details={"reasons": reasons, "snapshot": baseline.json()}, retryable=True, exit_code=75)
        staging_directory = destination.parent / f".ffv2-{job['id']}-a{job['attempt']}"
        if os.path.lexists(staging_directory):
            raise FFV2Error("staging_exists", "এই attempt-এর staging output আছে; সেটি রাখা হয়েছে।")
        staging_directory.mkdir(mode=0o700)
        stage = staging_directory / ("output" + destination.suffix)
        job_receipt.update(staging_output=str(stage), baseline=baseline.json(), plan_id=plan["plan_id"])
        if plan.get("preparation"):
            from .advanced import prepare_inputs
            phase = "preparation"
            job_receipt["preparation"] = prepare_inputs(plan, job, directory, settings, baseline, lock_fd, session=session)
        phase = "encode"
        replacements = {"<STAGING_OUTPUT>": str(stage), "<CONCAT_MANIFEST>": "ffv2-inputs.ffconcat"}
        command = [replacements.get(item, item) for item in plan["argv"]]
        if plan.get('checkpoint'):
            from .checkpoints import execute, assembly
            phase = 'checkpoints'
            job_receipt['checkpoints'] = execute(plan, job, directory, settings, baseline, lock_fd, store, session=session)
            command = assembly(plan, job_receipt['checkpoints'], stage)
            phase = 'encode'
        mark("preparation")
        encoding = supervised(command, phase, job, directory, settings, baseline, lock_fd, stage, **supervisor_options)
        mark("encode_supervised")
        job_receipt["encoding"] = encoding
        if not stage.is_file() or stage.stat().st_size <= 0:
            raise FFV2Error("output_missing", "FFmpeg nonempty output তৈরি করেনি।")
        phase = "validation"
        from .engine import assert_selection
        assert_selection(plan["binary"].get("engine_selection_id"))
        if plan["binary"].get("runtime_binding"):
            assert_current(plan["binary"]["runtime_binding"])
        store.update(job["id"], "validating", receipt=job_receipt)
        output = probe_path(stage, plan["binary"]["ffprobe"], image=plan["spec"]["operation"] in ("frame", "contact_sheet", "image"))
        validate_metadata(plan, output)
        limits = list(INPUT_LIMITS)
        if plan["spec"]["operation"] == "image":
            limits[-1] += ",image2,jpeg_pipe,png_pipe,webp_pipe"
        if plan["spec"]["operation"] in ("frame", "contact_sheet"):
            limits[-1] += ",image2,jpeg_pipe,png_pipe,webp_pipe"
            samples = encoding.get("decoded_source_pts_samples") or []
            if plan["expected"].get("sampling_method") == "seek":
                by_sample = encoding.get("decoded_source_pts_by_sample", {})
                samples = [by_sample[str(i)] for i in range(plan["expected"]["sample_count"]) if str(i) in by_sample]
            pts = samples[0] if samples else encoding.get("decoded_source_pts")
            if pts is None or not math.isfinite(pts):
                raise FFV2Error("frame_timestamp_unverified", "Decoded frame-এর source PTS পাওয়া যায়নি।")
            actual = pts - plan["expected"]["source_video_start"]
            if actual < plan["expected"]["requested_seconds"] - 0.15 or actual > plan["source"]["duration_seconds"] + 0.15:
                raise FFV2Error("frame_timestamp_mismatch", "Decoded frame-এর timestamp প্রত্যাশিত range-এর বাইরে।", details={"actual_seconds": actual})
            job_receipt["frame"] = {"requested_seconds": plan["expected"]["requested_seconds"], "actual_seconds": actual, "source_pts_seconds": pts}
            if plan["spec"]["operation"] == "contact_sheet":
                expected = plan["expected"]
                if len(samples) != expected["sample_count"]:
                    raise FFV2Error("sheet_samples_incomplete", "প্রত্যাশিত সংখ্যক decoded frame পাওয়া যায়নি।",
                                    details={"expected": expected["sample_count"], "observed": len(samples)})
                targets = [expected["requested_seconds"] + i * expected["sample_interval_seconds"]
                           for i in range(expected["sample_count"])]
                actuals = [value - expected["source_video_start"] for value in samples]
                if any(a < t - 0.001 or a >= plan["source"]["duration_seconds"] + 0.15 for a, t in zip(actuals, targets)):
                    raise FFV2Error("sheet_timestamp_mismatch", "Contact sheet-এর source PTS target range-এর সঙ্গে মেলেনি।")
                if any(b <= a for a, b in zip(samples, samples[1:])):
                    raise FFV2Error("sheet_timestamp_mismatch", "Contact sheet-এর frame timestamps increasing হতে হবে।")
                job_receipt["contact_sheet"] = {"targets_seconds": targets, "actual_seconds": actuals,
                                                "source_pts_seconds": samples, "columns": expected["columns"],
                                                "rows": expected["rows"], "cell_width": expected["cell_width"],
                                                "cell_height": expected["cell_height"], "sampling_method": expected.get("sampling_method", "single_pass")}
        validation_threads = str(plan.get("runtime_tuning", {}).get("validation_threads", 2))
        decode = [plan["binary"]["ffmpeg"], "-nostdin", "-hide_banner", "-v", "error", "-xerror",
                  "-nostats", "-progress", "pipe:1", *limits, "-threads", validation_threads, "-err_detect", "explode", "-i", str(stage),
                  "-map", "0:v?", "-map", "0:a?", "-threads", validation_threads, "-f", "null", "-"]
        mark("metadata_validation")
        validation = supervised(decode, phase, job, directory, settings, baseline, lock_fd, stage, admission_budget=0, **supervisor_options)
        if "video_frames" in plan["expected"]:
            progress = validation.get("last_progress") or {}
            if int(progress.get("frame", -1)) != plan["expected"]["video_frames"]:
                raise FFV2Error("output_frame_count_mismatch", "পূর্ণ decode-এ expected frame count মেলেনি।")
        if "audio_samples" in plan["expected"]:
            progress = validation.get("last_progress") or {}
            decoded_samples = round(int(progress.get("out_time_us", -1)) * plan["expected"]["audio_rate"] / 1000000)
            if decoded_samples != plan["expected"]["audio_samples"]:
                raise FFV2Error("output_sample_count_mismatch", "পূর্ণ decode-এর audio sample endpoint মেলেনি।")
        mark("decode_supervised")
        job_receipt["validation"] = {"metadata": output, "full_decode": validation}
        assert_sources(plan)
        checksum = hash_guarded(stage, settings, baseline, store, job["id"])
        assert_selection(plan["binary"].get("engine_selection_id"))
        if plan["binary"].get("runtime_binding"):
            assert_current(plan["binary"]["runtime_binding"])
        assert_sources(plan)
        if store.cancelled(job["id"]):
            raise FFV2Error("cancelled", "Output publish-এর আগে job বাতিল হয়েছে।", exit_code=130)
        assert_workflow(plan)
        if time.monotonic() >= job['_deadline']:
            raise FFV2Error('job_timeout', 'Publication-এর আগে job time budget শেষ হয়েছে।', retryable=True)
        output_path(str(destination), Path(plan["source"]["path"]), settings)
        with stage.open("rb") as file:
            os.fsync(file.fileno())
        intent = {**job_receipt, 'status': 'completed', 'output': str(destination), 'output_bytes': stage.stat().st_size,
                  'output_sha256': checksum, 'verified_at': time.time(), 'publish_identity': fingerprint(stage),
                  'encode_wall_seconds': encoding['wall_seconds'], 'validation_wall_seconds': validation['wall_seconds'],
                  'hardware_runtime_verified': plan['encoder'] == 'h264_videotoolbox',
                  'hardware_decode_runtime_verified': bool(plan['expected'].get('hardware_decode_required')),
                  'hardware_filter_runtime_verified': bool(plan['expected'].get('hardware_filter_required'))}
        write_json(directory / 'publish-intent.json', {'receipt': intent, 'digest': digest(intent)})
        from .checkpoints import sync_directory
        sync_directory(directory)
        # Same-volume hard link নতুন নামটি atomically তৈরি করে; existing path বদলায় না।
        os.link(stage, destination, follow_symlinks=False)
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        mark("integrity_publish")
        timings["total"] = round(time.monotonic() - started, 6)
        job_receipt.update(status="completed", output=str(destination), output_bytes=destination.stat().st_size,
                           output_sha256=checksum, verified_at=time.time(),
                           hardware_runtime_verified=plan["encoder"] == "h264_videotoolbox",
                           hardware_decode_runtime_verified=bool(plan["expected"].get("hardware_decode_required")),
                           hardware_filter_runtime_verified=bool(plan["expected"].get("hardware_filter_required")),
                           encode_wall_seconds=encoding["wall_seconds"], validation_wall_seconds=validation["wall_seconds"],
                           phase_timings_seconds=timings)
        # Staging hard link রাখা হয়: publish-এর পর crash হলেও recovery-তে identity মেলানো যায়।
        store.update(job["id"], "completed", receipt=job_receipt)
    except (FFV2Error, OSError, ValueError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        if not isinstance(error, FFV2Error):
            error = FFV2Error("worker_interrupted" if isinstance(error, KeyboardInterrupt) else "worker_error",
                              "Job সম্পূর্ণ হয়নি; diagnostic ও partial রাখা হয়েছে।",
                              details={"type": type(error).__name__, "message": str(error)[:1000]})
        state = "queued" if error.code == "checkpoint_yielded" else "waiting_resources" if error.code == "resource_not_admitted" else "cancelled" if error.code == "cancelled" else "interrupted" if error.code in ("worker_interrupted", "resource_stopped", "checkpoint_timeout", "job_timeout") else "failed"
        job_receipt.update(status=state, phase=phase, error=error.payload())
        store.update(job["id"], state, error=error.payload(), receipt=job_receipt)
    write_json(directory / "receipt.json", job_receipt)
    return store.get(job["id"], plan=False)


def work(settings, *, job_id=None, drain=False, max_jobs=100):
    if job_id is not None:
        Store.check_id(job_id)
    if type(max_jobs) is not int or not 1 <= max_jobs <= 100:
        raise FFV2Error("invalid_worker_limit", "Worker pass-এ 1–100টি job দিন।")
    store = Store(settings)
    results = []
    deferred = set()
    stop_reasons = []
    with host_lock(settings) as lock_fd, SupervisorSession(settings, lock_fd) as session:
        store.recover()
        while True:
            job = store.claim(job_id, exclude_ids=deferred)
            if not job:
                break
            if job["plan"].get("kind") in ("upstream_prepare", "upstream_build"):
                from .upstream import perform_upstream
                result = perform_upstream(job, settings, lock_fd, store)
            else:
                result = perform(job, settings, lock_fd, store, session=session)
            results.append({key: result[key] for key in ("id", "status", "attempt", "output", "error")})
            if result["status"] == "waiting_resources":
                deferred.add(job["id"])
            if not drain or job_id is not None or len(results) >= max_jobs:
                break
            if result["status"] == "waiting_resources":
                # একই job retry নয়: কম demand-এর পরের job-এর আগে global safeguards আবার দেখি।
                try:
                    stop_reasons = Policy().admission(snapshot(store.root))
                except FFV2Error as error:
                    stop_reasons = [error.code]
                except OSError:
                    stop_reasons = ["resource_recheck_failed"]
                if stop_reasons:
                    break
            elif result["status"] not in ("completed", "queued"):
                break
    return {"jobs": results, "processed": len(results), "completed": sum(job["status"] == "completed" for job in results),
            "deferred_job_ids": sorted(deferred), "stop_reasons": stop_reasons}
