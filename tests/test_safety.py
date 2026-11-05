from __future__ import annotations
import sys as _path_sys
from pathlib import Path as _Path
_path_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "scripts"))
from public_paths import lab_path, project_path

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from ffv2.config import GIB, PROJECT, Settings, check_mounts
from ffv2.errors import FFV2Error
from ffv2.io import capture, fingerprint, input_path, output_path, terminate
from ffv2.mcp import Server, serve
from ffv2.planner import build_plan, validate_spec
from ffv2.process import execute
from ffv2.resources import Policy, Snapshot, parse_darwin
from ffv2.store import Store
from ffv2.worker import checked_plan, host_lock, perform, validate_metadata

TEST_BASE = PROJECT / ".test-work"
check_mounts(TEST_BASE)
TEST_BASE.mkdir(exist_ok=True)
SESSION = Path(tempfile.mkdtemp(prefix="suite-", dir=TEST_BASE))
GOOD = Snapshot("normal", 16 * GIB, 2 * GIB, 100 * GIB, 200 * GIB, 200 * GIB)
BAD = Snapshot("warning", 7 * GIB, 2 * GIB, 100 * GIB, 200 * GIB, 200 * GIB)


class Workspace(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="case-", dir=SESSION))
        self.settings = Settings(state=self.root / "state", output_roots=(self.root,), input_roots=(self.root,),
                                 host_lock=self.root / "host.lock")
        self.source = self.root / "source.dat"
        self.source.write_bytes(b"bounded test fixture, not encoded media")
        self.caps = {"ffmpeg": "/usr/bin/false", "ffprobe": "/usr/bin/false", "ffmpeg_version": "test",
                     "ffprobe_version": "test", "ffmpeg_identity": {"test": 1}, "ffprobe_identity": {"test": 1},
                     "system": "Darwin", "machine": "arm64", "encoders": ["libx264", "h264_videotoolbox"], "filters": ["ssim"]}
        self.metadata = {"path": str(self.source), "fingerprint": fingerprint(self.source), "duration_seconds": 2.0,
                         "format": {"format_name": "mov,mp4"},
                         "video": {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 640, "height": 360,
                                   "avg_frame_rate": "30/1", "sample_aspect_ratio": "1:1", "field_order": "progressive"},
                         "audio": {"index": 1, "codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2}}
        self.metadata["streams"] = [self.metadata["video"], self.metadata["audio"]]

    def spec(self, **kw):
        return {"operation": "transcode", "input": str(self.source), "output": str(self.root / "out.mp4"), **kw}

    def plan(self, **kw):
        with patch("ffv2.planner.probe", return_value=self.metadata):
            return build_plan(self.spec(**kw), self.settings, self.caps)

    def job(self):
        store = Store(self.settings)
        queued = store.enqueue(self.plan())
        return store, store.claim(queued["id"])


class ResourceTests(Workspace):
    def test_darwin_parser_includes_compressed_memory_and_actual_pressure(self):
        disk = shutil._ntuple_diskusage(500 * GIB, 200 * GIB, 300 * GIB)
        sc = "hw.memsize: 38654705664\nkern.memorystatus_vm_pressure_level: 2\nvm.swapusage: total = 20480.00M used = 18432.00M free = 2048.00M (encrypted)\n"
        vm = "Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages active: 400000.\nPages wired down: 400000.\nPages occupied by compressor: 900000.\nPages inactive: 300000.\n"
        result = parse_darwin(sc, vm, disk, disk)
        self.assertEqual(result.pressure, "warning")
        self.assertEqual(result.swap_bytes, 18 * GIB)
        self.assertEqual(result.headroom_bytes, 36 * GIB - 1700000 * 16384)

    def test_admission_fails_for_warning_and_insufficient_headroom(self):
        self.assertEqual(Policy().admission(GOOD, GIB, GIB), [])
        reasons = Policy().admission(BAD, GIB, GIB)
        self.assertIn("physical_headroom", reasons)
        self.assertIn("memory_pressure_warning", reasons)

    def test_running_checks_swap_disk_and_job_footprint(self):
        sample = Snapshot("normal", 7 * GIB, 4 * GIB, 14 * GIB, 200 * GIB, 14 * GIB)
        reasons = Policy().running(sample, GOOD, 13 * GIB)
        for reason in ("swap_growth_over_1gib", "physical_headroom_below_8gib", "job_memory_over_12gib", "boot_disk_free_below_15gib", "output_disk_reserve"):
            self.assertIn(reason, reasons)

    def test_internal_disk_hard_limit(self):
        sample = Snapshot("normal", 16 * GIB, 0, 40 * GIB, 401_000_000_000, 40 * GIB)
        self.assertIn("boot_disk_used_limit", Policy(boot_used_limit=400_000_000_000).admission(sample))

    def test_unmounted_workspace_never_created(self):
        with patch("ffv2.config.os.path.ismount", return_value=False), patch.dict(os.environ, {'FFV2_REQUIRED_MOUNTS':str(lab_path())}):
            with self.assertRaises(FFV2Error) as error:
                check_mounts(Path(str(lab_path('example'))))
        self.assertEqual(error.exception.code, "storage_unmounted")


class PlanTests(Workspace):
    def test_contact_sheet_uses_single_decode_and_bounds_sample_density_and_size(self):
        plan = self.plan(operation="contact_sheet", output=str(self.root / "sheet.jpg"),
                         count=16, columns=4, max_width=320, max_height=180)
        self.assertEqual(plan["expected"]["width"], 1280)
        self.assertEqual(plan["expected"]["height"], 720)
        self.assertEqual(plan["expected"]["sample_count"], 16)
        self.assertEqual(plan["argv"].count("-i"), 1)
        filters = plan["argv"][plan["argv"].index("-vf") + 1]
        self.assertIn("selected_n", filters)
        self.assertIn("tile=4x4", filters)
        with self.assertRaises(FFV2Error) as error:
            self.plan(operation="contact_sheet", output=str(self.root / "short.jpg"), duration=0.1, count=16)
        self.assertEqual(error.exception.code, "sample_density_exceeded")
        self.metadata["duration_seconds"] = 4
        self.metadata["video"].update(width=3840, height=2160)
        with self.assertRaises(FFV2Error) as error:
            self.plan(operation="contact_sheet", output=str(self.root / "large.jpg"), count=64,
                      max_width=3840, max_height=2160)
        self.assertEqual(error.exception.code, "sheet_size_exceeded")

    def test_reject_raw_commands_bool_numeric_and_nan(self):
        for change in ({"argv": ["sh", "-c", "echo x"]}, {"threads": True}, {"start": float("nan")}, {"max_width": 5000}):
            with self.subTest(change=change), self.assertRaises(FFV2Error):
                validate_spec(self.spec(**change))

    def test_acceleration_is_candidate_not_claimed_verification(self):
        plan = self.plan(encoder="videotoolbox")
        self.assertEqual(plan["encoder"], "h264_videotoolbox")
        self.assertFalse(plan["hardware_runtime_verified"])
        self.assertIn("-allow_sw", plan["argv"])
        self.assertNotIn("-hwaccel", plan["argv"])

    def test_auto_avoids_hardware_startup_for_measured_small_clip_class(self):
        self.assertEqual(self.plan()["encoder"], "libx264")
        self.metadata["duration_seconds"] = 6
        self.metadata["video"].update(width=1280, height=720)
        self.assertEqual(self.plan()["encoder"], "h264_videotoolbox")

    def test_explicit_quality_request_is_honoured_or_refused(self):
        self.metadata["duration_seconds"] = 6
        self.metadata["video"].update(width=1280, height=720)
        self.assertEqual(self.plan(encoder="auto", rate_control="quality")["encoder"], "libx264")
        with self.assertRaises(FFV2Error) as error:
            self.plan(encoder="videotoolbox", rate_control="quality")
        self.assertEqual(error.exception.code, "rate_control_unsupported")

    def test_software_limits_decoder_encoder_and_filter_threads(self):
        plan = self.plan(encoder="software", threads=2)
        self.assertEqual(plan["encoder"], "libx264")
        self.assertIn("-threads:v", plan["argv"])
        self.assertIn("-filter_complex_threads", plan["argv"])

    def test_explicit_bitrate_is_not_silently_ignored(self):
        plan = self.plan(encoder="software", video_bitrate=2_000_000)
        self.assertIn("-b:v", plan["argv"])
        self.assertNotIn("-crf", plan["argv"])
        with self.assertRaises(FFV2Error):
            self.plan(encoder="software", video_bitrate=2_000_000, rate_control="quality")

    def test_hdr_conversion_fails_but_remux_is_allowed(self):
        self.metadata["video"]["color_transfer"] = "smpte2084"
        with self.assertRaises(FFV2Error) as error:
            self.plan()
        self.assertEqual(error.exception.code, "hdr_policy_required")
        plan = self.plan(operation="remux", output=str(self.root / "out.mkv"))
        self.assertIn("copy", plan["argv"])
        self.assertNotIn("-vf", plan["argv"])

    def test_trim_cannot_silently_become_keyframe_remux(self):
        with self.assertRaises(FFV2Error):
            self.plan(operation="remux", output=str(self.root / "out.mkv"), start=0.5)

    def test_rotation_and_sar_have_square_pixel_output(self):
        self.metadata["video"].update(width=720, height=480, sample_aspect_ratio="4:3", side_data_list=[{"rotation": -90}])
        plan = self.plan(max_width=1080, max_height=1920)
        width, height = plan["expected"]["width"], plan["expected"]["height"]
        self.assertAlmostEqual(width / height, 0.5, places=2)
        self.assertIn(f"scale={width}:{height},setsar=1", plan["argv"])

    def test_attached_picture_does_not_change_explicit_stream_mapping(self):
        self.metadata["video"]["index"] = 2
        plan = self.plan()
        self.assertIn("0:2", plan["argv"])

    def test_input_url_and_mcp_outside_root_denied(self):
        with self.assertRaises(FFV2Error):
            input_path("https://example.com/a.mp4", self.settings)
        other = self.root.parent / (self.root.name + ".dat")
        other.write_bytes(b"outside root fixture")
        with self.assertRaises(FFV2Error) as error:
            input_path(str(other), self.settings, restricted=True)
        self.assertEqual(error.exception.code, "input_path_denied")

    def test_source_hardlink_and_symlink_outputs_never_overwritten(self):
        hard = self.root / "hard.mp4"
        os.link(self.source, hard)
        symlink = self.root / "symlink.mp4"
        symlink.symlink_to(self.source)
        for path in (self.source, hard, symlink):
            with self.subTest(path=path), self.assertRaises(FFV2Error):
                output_path(str(path), self.source, self.settings)
        self.assertEqual(self.source.read_bytes(), b"bounded test fixture, not encoded media")

    def test_symlink_cannot_hide_canonical_manifest_line_characters(self):
        for index, character in enumerate(("\n", "\r")):
            source = self.root / ('source-' + str(index) + character + 'line.dat')
            source.write_bytes(b'owned canonical-path fixture')
            alias = self.root / ('input-alias-' + str(index))
            alias.symlink_to(source.name)
            with self.subTest(kind='input', character=repr(character)), self.assertRaises(FFV2Error) as error:
                input_path(str(alias), self.settings, restricted=True)
            self.assertEqual(error.exception.code, 'invalid_input')
            directory = self.root / ('directory-' + str(index) + character + 'line')
            directory.mkdir()
            output_alias = self.root / ('output-alias-' + str(index))
            output_alias.symlink_to(directory.name, target_is_directory=True)
            with self.subTest(kind='output', character=repr(character)), self.assertRaises(FFV2Error) as error:
                output_path(str(output_alias/'joined.mkv'), self.source, self.settings)
            self.assertEqual(error.exception.code, 'invalid_output')
            with self.subTest(kind='state', character=repr(character)), self.assertRaises(FFV2Error) as error:
                Settings(state=output_alias/'state', output_roots=(self.root,)).ensure_state()
            self.assertEqual(error.exception.code, 'invalid_state')
            self.assertFalse((directory/'state').exists())


class QueueTests(Workspace):
    def test_idempotency_durable_and_conflict_is_not_replayed(self):
        store = Store(self.settings)
        plan = self.plan()
        first = store.enqueue(plan, "one")
        second = Store(self.settings).enqueue(plan, "one")
        self.assertEqual(first["id"], second["id"])
        self.assertTrue(second["replayed"])
        with self.assertRaises(FFV2Error) as error:
            store.enqueue(self.plan(encoder="software"), "one")
        self.assertEqual(error.exception.code, "idempotency_conflict")
        for key in ("", 0, False):
            with self.subTest(key=key), self.assertRaises(FFV2Error):
                store.enqueue(plan, key)

    def test_active_output_unique(self):
        store = Store(self.settings)
        store.enqueue(self.plan(), "one")
        with self.assertRaises(FFV2Error) as error:
            store.enqueue(self.plan(), "two")
        self.assertEqual(error.exception.code, "output_reserved")

    def test_simultaneous_claim_has_one_winner(self):
        store = Store(self.settings)
        store.enqueue(self.plan())
        results, errors = [], []
        barrier = threading.Barrier(2)
        def claim():
            try:
                barrier.wait()
                results.append(store.claim())
            except BaseException as error:
                errors.append(error)
        workers = [threading.Thread(target=claim) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=5)
        self.assertFalse(errors)
        self.assertEqual(sum(value is not None for value in results), 1)

    def test_cancel_retry_retains_attempt_and_event_history(self):
        store = Store(self.settings)
        job = store.enqueue(self.plan())
        self.assertEqual(store.cancel(job["id"])["status"], "cancelled")
        self.assertIsNone(store.claim(job["id"]))
        store.retry(job["id"])
        self.assertEqual(store.claim(job["id"])["attempt"], 1)
        self.assertGreaterEqual(len(store.events(job["id"])), 4)

    def test_global_lock_excludes_other_worker(self):
        with host_lock(self.settings):
            with self.assertRaises(FFV2Error) as error:
                with host_lock(self.settings):
                    pass
        self.assertEqual(error.exception.code, "worker_busy")

    def test_changed_source_never_reaches_execution(self):
        store, job = self.job()
        self.source.write_bytes(b"replacement")
        with patch("ffv2.worker.supervised") as run:
            result = perform(job, self.settings, 0, store)
        self.assertEqual(result["error"]["code"], "source_changed")
        run.assert_not_called()

    def test_warning_refuses_job_before_ffmpeg_and_preserves_receipt(self):
        store, job = self.job()
        with patch("ffv2.worker.capabilities", return_value=self.caps), patch("ffv2.worker.snapshot", return_value=BAD), patch("ffv2.worker.supervised") as run:
            result = perform(job, self.settings, 0, store)
        self.assertEqual(result["status"], "waiting_resources")
        self.assertEqual(result["error"]["code"], "resource_not_admitted")
        run.assert_not_called()
        self.assertFalse(Path(job["output"]).exists())
        self.assertTrue((Path(result["receipt"]["directory"]) / "receipt.json").is_file())

    def test_output_duration_and_codec_mismatch_fail(self):
        plan = self.plan()
        output = json.loads(json.dumps(self.metadata))
        output["duration_seconds"] = 0.25
        output["video"]["codec_name"] = "hevc"
        with self.assertRaises(FFV2Error) as error:
            validate_metadata(plan, output)
        self.assertIn("duration", error.exception.details["mismatches"])
        self.assertIn("video_codec", error.exception.details["mismatches"])

    def test_plan_digest_tampering_rejected(self):
        store, job = self.job()
        job["plan"]["argv"] = ["/usr/bin/true"]
        with self.assertRaises(FFV2Error) as error:
            checked_plan(job, self.settings)
        self.assertEqual(error.exception.code, "plan_modified")

    def fake_execution(self, argv, phase, job, directory, settings, baseline, lock_fd, target, **kwargs):
        if phase == "encode":
            target.write_bytes(b"stub media for publish control-flow test")
        return {"status": "completed", "wall_seconds": 0.01, "decoded_source_pts": None}

    def test_publish_requires_validation_and_records_digest(self):
        store, job = self.job()
        with patch("ffv2.worker.capabilities", return_value=self.caps), patch("ffv2.worker.snapshot", return_value=GOOD), \
             patch("ffv2.worker.process_memory", return_value=(1000, "physical_footprint")), \
             patch("ffv2.worker.supervised", side_effect=self.fake_execution), \
             patch("ffv2.worker.probe_path", return_value=self.metadata):
            result = perform(job, self.settings, 0, store)
        self.assertEqual(result["status"], "completed")
        output = Path(result["output"])
        self.assertEqual(output.read_bytes(), b"stub media for publish control-flow test")
        self.assertEqual(output.stat().st_ino, Path(result["receipt"]["staging_output"]).stat().st_ino)
        self.assertTrue(result["receipt"]["output_sha256"])

    def test_validation_failure_retains_staging_and_publishes_nothing(self):
        store, job = self.job()
        invalid = {**self.metadata, "duration_seconds": 0.1}
        with patch("ffv2.worker.capabilities", return_value=self.caps), patch("ffv2.worker.snapshot", return_value=GOOD), \
             patch("ffv2.worker.supervised", side_effect=self.fake_execution), \
             patch("ffv2.worker.probe_path", return_value=invalid):
            result = perform(job, self.settings, 0, store)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["code"], "output_validation_failed")
        self.assertTrue(Path(result["receipt"]["staging_output"]).is_file())
        self.assertFalse(Path(job["output"]).exists())

    def test_atomic_publish_race_never_replaces_other_file(self):
        store, job = self.job()
        original_link = os.link
        def raced_link(source, destination, **kwargs):
            Path(destination).write_bytes(b"other output created after validation")
            return original_link(source, destination, **kwargs)
        with patch("ffv2.worker.capabilities", return_value=self.caps), patch("ffv2.worker.snapshot", return_value=GOOD), \
             patch("ffv2.worker.process_memory", return_value=(1000, "physical_footprint")), \
             patch("ffv2.worker.supervised", side_effect=self.fake_execution), \
             patch("ffv2.worker.probe_path", return_value=self.metadata), patch("ffv2.worker.os.link", side_effect=raced_link):
            result = perform(job, self.settings, 0, store)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(Path(job["output"]).read_bytes(), b"other output created after validation")


class ProcessTests(Workspace):
    def test_group_signal_permission_race_falls_back_to_owned_child_and_reaps(self):
        process = subprocess.Popen([sys.executable, "-B", "-c", "import time; time.sleep(10)"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            with patch("ffv2.io.os.killpg", side_effect=PermissionError("group closing")):
                terminate(process)
            self.assertIsNotNone(process.returncode)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=3)

    def test_source_timestamp_records_survive_split_stderr_reads(self):
        code = ("import os,time; "
                "os.write(2,b'[showinfo@ffv2_samples @ 0x0] n: 0 pts: 30 pts_t'); "
                "time.sleep(0.03); os.write(2,b'ime:1.0 pos:0\\n'); "
                "os.write(2,b'[showinfo@ffv2_samples @ 0x0] n: 1 pts: 60 pts_time:2.0 pos:0\\n')")
        result = self.execute(self.request(code))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["decoded_source_pts_samples"], [1.0, 2.0])

    def test_sparse_timestamps_keep_sample_identity_when_decoder_messages_arrive_out_of_order(self):
        result = self.execute(self.request("import os; os.write(2,b'[showinfo@ffv2_sample_1 @ 0x0] n: 0 pts: 90 pts_time:3.0\\n[showinfo@ffv2_sample_0 @ 0x0] n: 0 pts: 30 pts_time:1.0\\n')"))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["decoded_source_pts_by_sample"], {"1":3.0, "0":1.0})

    def request(self, script, **kw):
        return {"argv": [sys.executable, "-B", "-c", script], "cwd": str(self.root), "log_name": "stderr.log",
                "output": str(self.root / "stage.dat"), "output_budget": GIB, "estimated_memory": GIB,
                "timeout_seconds": 3, "owner_pid": os.getppid(), "baseline": GOOD.json(), "phase": "test", **kw}

    def execute(self, request, **kw):
        return execute(request, snapshot_fn=lambda path: GOOD, memory_fn=lambda *a: (50 * 1024 ** 2, "physical_footprint"), **kw)

    def test_progress_microseconds_and_large_stderr_no_deadlock(self):
        progress = []
        request = self.request("import sys; sys.stderr.write('x'*200000); print('out_time_ms=1500000'); print('progress=end')")
        result = self.execute(request, progress=progress.append)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(progress[0]["out_seconds"], 1.5)
        self.assertLessEqual(len(result["stderr_tail"]), 65536)

    def test_warning_stops_only_child_and_preserves_failure(self):
        samples = iter((GOOD, BAD))
        result = execute(self.request("import time; time.sleep(4)"), snapshot_fn=lambda path: next(samples), memory_fn=lambda *a: (0, "fixture"))
        self.assertEqual(result["status"], "stopped")
        self.assertIn("memory_pressure_warning", result["reasons"])

    def test_cancel_and_timeout_terminate_child(self):
        start = time.monotonic()
        result = self.execute(self.request("import time; time.sleep(4)"), cancelled=lambda: time.monotonic() - start > 0.1)
        self.assertIn("cancelled", result["reasons"])
        result = self.execute(self.request("import time; time.sleep(4)", timeout_seconds=0.15))
        self.assertIn("timeout", result["reasons"])

    def test_parent_death_watchdog(self):
        result = self.execute(self.request("import time; time.sleep(4)", owner_pid=99999999))
        self.assertEqual(result["status"], "stopped")
        self.assertIn("worker_parent_lost", result["reasons"])

    def test_closed_pipes_do_not_bypass_watchdog_timeout(self):
        result = self.execute(self.request("import os,time; os.close(1); os.close(2); time.sleep(5)", timeout_seconds=0.1))
        self.assertEqual(result["status"], "stopped")
        self.assertIn("timeout", result["reasons"])

    def test_build_stdout_is_recorded_without_unbounded_output(self):
        result = self.execute(self.request("print('compile fixture output')", capture_stdout=True))
        self.assertEqual(result["status"], "completed")
        self.assertIn("compile fixture output", result["stdout_tail"])

    def test_native_jsonl_progress_microseconds(self):
        progress = []
        result = self.execute(self.request("print('{\"schema_version\":1,\"out_time_us\":\"2500000\",\"progress\":\"end\"}')"), progress=progress.append)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(progress[0]["out_seconds"], 2.5)
        self.assertEqual(progress[0]["source_format"], "jsonl")

    def test_build_directory_budget_without_large_files(self):
        with patch("ffv2.process.subprocess.check_output", return_value=str(2 * GIB // 1024) + "\tfixture\n"):
            result = self.execute(self.request("import time; time.sleep(4)", budget_directory=str(self.root)))
        self.assertEqual(result["status"], "stopped")
        self.assertIn("output_size_budget", result["reasons"])

    def test_snapshot_failure_stops_child(self):
        calls = []
        def sample(path):
            calls.append(1)
            if len(calls) > 1:
                raise RuntimeError("snapshot unavailable")
            return GOOD
        result = execute(self.request("import time; time.sleep(4)"), snapshot_fn=sample)
        self.assertEqual(result["status"], "stopped")
        self.assertIn("watchdog_error", result["reasons"])

    def test_metadata_capture_bounded_output(self):
        with self.assertRaises(FFV2Error) as error:
            capture([sys.executable, "-B", "-c", "print('x'*20000)"], limit=1024)
        self.assertEqual(error.exception.code, "probe_output_limit")

    def test_metadata_capture_memory_budget_kills_without_large_allocation(self):
        with patch("ffv2.resources.process_memory", return_value=(300 * 1024 ** 2, "test_fixture")):
            with self.assertRaises(FFV2Error) as error:
                capture([sys.executable, "-B", "-c", "import time; time.sleep(4)"])
        self.assertEqual(error.exception.code, "probe_memory_limit")

    def test_metadata_capture_handles_exit_between_poll_and_memory_measurement(self):
        import subprocess
        factory=subprocess.Popen
        created=[]
        def launch(*args,**kwargs):
            child=factory(*args,**kwargs);created.append(child);return child
        def expired(pid,*args):
            created[0].wait(timeout=3)
            return 0,'unavailable'
        with patch('ffv2.io.subprocess.Popen',side_effect=launch),patch('ffv2.resources.process_memory',side_effect=expired):
            code,out,err=capture([sys.executable,'-B','-c',"import time; time.sleep(.05); print('complete')"])
        self.assertEqual((code,out.strip(),err),(0,'complete',''))


class MCPTests(Workspace):
    def test_lifecycle_schema_and_json_only_stream(self):
        requests = [
            {"jsonrpc": "2.0", "id": 0, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "ffv2_doctor", "arguments": {}}},
        ]
        raw = io.BytesIO(("\n".join(json.dumps(r) for r in requests) + "\n").encode())
        output = io.StringIO()
        with patch("ffv2.mcp.doctor", return_value={"media_job_admitted": False}):
            serve(self.settings, raw, output)
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(responses), 4)
        self.assertEqual(responses[0]["error"]["code"], -32002)
        self.assertEqual(len(responses[2]["result"]["tools"]), 8)
        self.assertFalse(responses[3]["result"]["isError"])
        self.assertEqual(responses[3]["result"]["structuredContent"], {"media_job_admitted": False})

    def test_bad_json_unknown_tool_and_unknown_arguments(self):
        server = Server(self.settings)
        server.initialized = server.ready = True
        response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "nope"}})
        self.assertEqual(response["error"]["code"], -32602)
        response = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "ffv2_doctor", "arguments": {"raw_argv": []}}})
        self.assertTrue(response["result"]["isError"])
        output = io.StringIO()
        serve(self.settings, io.BytesIO(b"not json\n"), output)
        self.assertEqual(json.loads(output.getvalue())["error"]["code"], -32700)

    def test_existing_mcp_process_rejects_source_edit_before_planning(self):
        server = Server(self.settings)
        server.initialized = server.ready = True
        with patch('ffv2.bindings.workflow_identity', return_value='changed-source'), patch('ffv2.mcp.call') as dispatch:
            for name, arguments in (('ffv2_probe', {'path': str(self.source)}), ('ffv2_plan', {'spec': self.spec()}),
                                    ('ffv2_submit', {'spec': self.spec()}), ('ffv2_worker_start', {}),
                                    ('ffv2_job_retry', {'job_id': 'a'*32})):
                response = server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}})
                self.assertTrue(response['result']['isError'])
                self.assertEqual(json.loads(response['result']['content'][0]['text'])['code'], 'runtime_code_changed')
            dispatch.assert_not_called()
            dispatch.return_value = {'status': 'cancelled'}
            response = server.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'ffv2_job_cancel', 'arguments': {'job_id': 'a'*32}}})
            self.assertEqual(response['result']['structuredContent']['status'], 'cancelled')

    def test_wire_subprocess_real_handshake(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ]
        result = subprocess.run([str(PROJECT / "bin/ffv2"), "--state-dir", str(self.settings.state), "mcp"],
                                input="\n".join(json.dumps(r) for r in requests) + "\n", text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(len(lines[1]["result"]["tools"]), 8)


if __name__ == "__main__":
    unittest.main()
