from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from ffv2 import upstream
from ffv2.errors import FFV2Error
from ffv2.io import publish_json_new, rename_directory_new
from ffv2.store import Store
from test_safety import BAD, GOOD, Workspace


class UpstreamTests(Workspace):
    def test_candidate_version_accepts_pinned_tag_describe_without_accepting_other_releases(self):
        for version in ("9.0.2", "n9.0.2-1-g3f0d329-ffmpeg-v2-m4", "9.0.2-custom"):
            self.assertTrue(upstream.candidate_version_matches("ffmpeg version " + version, "9.0.2"))
        for version in ("9.0.20", "9.0.1", "master", "n9.0.3"):
            self.assertFalse(upstream.candidate_version_matches("ffmpeg version " + version, "9.0.2"))

    def setUp(self):
        super().setUp()
        self.core = self.root / "core"
        root_patch = patch("ffv2.upstream.CORE_ROOT", self.core)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.source = {"path": str(self.core / "ffmpeg"), "head": upstream.lock()["commit"],
                       "locked_base": upstream.lock()["commit"], "tracked_diff_sha256": "abc", "dirty": False,
                       "status": "", "branch": "ffmpeg-v2-main"}

    def tool(self, name, *, required=True):
        if name in ("pkg-config", "pkgconf"):
            return {"present": False, "name": name}
        return {"present": True, "path": "/usr/bin/" + name, "version": "fixture", "identity": {"fixture": True}}

    def build_plan(self, profile="native", *, jobs=2):
        with patch("ffv2.upstream.source_state", return_value=self.source), \
             patch("ffv2.upstream.tool_info", side_effect=self.tool), \
             patch("ffv2.upstream.command", return_value="/fixture/sdk"):
            return upstream.build_plan(self.settings, profile, jobs=jobs)

    def claim(self, plan):
        store = Store(self.settings)
        queued = store.enqueue(plan)
        return store, store.claim(queued["id"])

    def test_prepare_preview_is_pinned_and_does_not_create_source(self):
        plan = upstream.prepare_plan(self.settings)
        self.assertEqual(plan["upstream_lock"]["commit"], upstream.lock()["commit"])
        self.assertIn("--depth", plan["argv_template"])
        self.assertFalse(self.core.exists())

    def test_prepare_warning_runs_no_download_and_creates_no_workspace(self):
        plan = upstream.prepare_plan(self.settings)
        store, job = self.claim(plan)
        with patch("ffv2.upstream.snapshot", return_value=BAD), patch("ffv2.worker.supervised") as run:
            result = upstream.perform_upstream(job, self.settings, 0, store)
        self.assertEqual(result["status"], "waiting_resources")
        self.assertFalse(self.core.exists())
        run.assert_not_called()

    def test_wrong_downloaded_commit_is_retained_and_never_published(self):
        plan = upstream.prepare_plan(self.settings)
        store, job = self.claim(plan)
        def clone(argv, *args, **kwargs):
            stage = Path(argv[-1])
            stage.mkdir()
            (stage / "kept.txt").write_text("partial checkout fixture")
            return {"status": "completed"}
        original_command = upstream.command
        def inspect(argv, **kwargs):
            return "0" * 40 if "rev-parse" in argv else original_command(argv, **kwargs)
        with patch("ffv2.upstream.snapshot", return_value=GOOD), patch("ffv2.worker.supervised", side_effect=clone), \
             patch("ffv2.upstream.command", side_effect=inspect):
            result = upstream.perform_upstream(job, self.settings, 0, store)
        self.assertEqual(result["error"]["code"], "upstream_commit_mismatch")
        self.assertFalse((self.core / "ffmpeg").exists())
        self.assertTrue((Path(result["receipt"]["staging_source"]) / "kept.txt").is_file())

    def test_native_plan_has_fate_two_jobs_and_no_auto_install(self):
        plan = self.build_plan()
        self.assertFalse(plan["pkg_config"]["present"])
        self.assertFalse(plan["feature_parity_verified"])
        self.assertEqual([step["name"] for step in plan["steps_template"]], ["configure", "compile", "install", "fate-list", "fate-local"])
        self.assertIn("-j2", plan["steps_template"][1]["argv"])
        self.assertIn("--enable-videotoolbox", plan["configure_flags"])
        self.assertFalse(any(Path(step["argv"][0]).name in ("brew", "pip", "curl", "wget") for step in plan["steps_template"]))

    def test_changed_tag_object_is_never_published(self):
        plan = upstream.prepare_plan(self.settings)
        store, job = self.claim(plan)
        def clone(argv, *args, **kwargs):
            Path(argv[-1]).mkdir()
            return {"status": "completed"}
        original_command = upstream.command
        def inspect(argv, **kwargs):
            if "rev-parse" in argv:
                return plan["upstream_lock"]["commit"] if argv[-1] == "HEAD" else "0" * 40
            return original_command(argv, **kwargs)
        with patch("ffv2.upstream.snapshot", return_value=GOOD), patch("ffv2.worker.supervised", side_effect=clone), \
             patch("ffv2.upstream.command", side_effect=inspect):
            result = upstream.perform_upstream(job, self.settings, 0, store)
        self.assertEqual(result["error"]["code"], "upstream_tag_mismatch")
        self.assertFalse((self.core / "ffmpeg").exists())

    def test_baseline_profile_reports_missing_pkg_config(self):
        with self.assertRaises(FFV2Error) as error:
            self.build_plan("baseline")
        self.assertEqual(error.exception.code, "build_tool_missing")

    def test_serial_build_reduces_estimate_without_reducing_features_or_guard(self):
        serial, parallel = self.build_plan(jobs=1), self.build_plan(jobs=2)
        self.assertEqual(serial["configure_flags"], parallel["configure_flags"])
        self.assertEqual(serial["estimates"]["job_memory_bytes"], 2 * 1024 ** 3)
        self.assertEqual(parallel["estimates"]["job_memory_bytes"], 3 * 1024 ** 3)
        self.assertIn("-j1", serial["steps_template"][1]["argv"])
        self.assertNotEqual(serial["spec"]["output"], parallel["spec"]["output"])
        for jobs in (0, 3, True):
            with self.subTest(jobs=jobs), self.assertRaises(FFV2Error):
                self.build_plan(jobs=jobs)

    def test_resume_reuses_compilation_and_installs_before_shared_library_tests(self):
        plan = self.build_plan()
        store, job = self.claim(plan)
        build = Path(plan["spec"]["output"]).parent / "attempt-001/build"
        build.mkdir(parents=True)
        prefix = build.parent / "install"
        store.update(job["id"], "failed", receipt={"install_prefix": str(prefix)})
        with patch("ffv2.upstream.build_plan", return_value=self.build_plan()):
            resumed = upstream.resume_plan(self.settings, job["id"])
        self.assertEqual(resumed["reuse_build_dir"], str(build))
        self.assertEqual(resumed["reuse_install_prefix"], str(prefix))
        self.assertEqual([s["name"] for s in resumed["steps_template"]], ["install", "fate-list", "fate-local"])
        changed = self.build_plan()
        changed["source"] = {**self.source, "head": "1" * 40}
        with patch("ffv2.upstream.build_plan", return_value=changed), self.assertRaises(FFV2Error) as error:
            upstream.resume_plan(self.settings, job["id"])
        self.assertEqual(error.exception.code, "build_checkpoint_changed")

    def test_empty_fate_list_does_not_create_candidate(self):
        plan = self.build_plan()
        store, job = self.claim(plan)
        with patch("ffv2.upstream.check_plan"), patch("ffv2.upstream.snapshot", return_value=GOOD), \
             patch("ffv2.worker.supervised", return_value={"status": "completed", "stdout_tail": ""}):
            result = upstream.perform_upstream(job, self.settings, 0, store)
        self.assertEqual(result["error"]["code"], "fate_no_tests")
        self.assertFalse(Path(plan["spec"]["output"]).exists())

    def test_build_manifest_never_claims_release_or_full_fate(self):
        plan = self.build_plan()
        store, job = self.claim(plan)
        def build(argv, phase, *args, **kwargs):
            if phase == "core-install":
                bin_dir = Path(kwargs["cwd"]).parent / "install/bin"
                bin_dir.mkdir(parents=True)
                for name in ("ffmpeg", "ffprobe"):
                    binary = bin_dir / name
                    binary.write_bytes(b"test-only candidate stub")
                    binary.chmod(0o700)
            return {"status": "completed", "stdout_tail": "one-test\nanother-test\n"}
        version = "ffmpeg version " + upstream.lock()["release_tag"][1:]
        with patch("ffv2.upstream.check_plan"), patch("ffv2.upstream.snapshot", return_value=GOOD), \
             patch("ffv2.upstream.source_state", return_value=self.source), patch("ffv2.upstream.command", return_value=version), \
             patch("ffv2.worker.supervised", side_effect=build), patch("ffv2.worker.hash_guarded", side_effect=lambda binary, *args: upstream.sha256_file(binary)):
            result = upstream.perform_upstream(job, self.settings, 0, store)
        self.assertEqual(result["status"], "completed")
        manifest = json.loads(Path(plan["spec"]["output"]).read_text())
        self.assertFalse(manifest["release_accepted"])
        self.assertFalse(manifest["full_fate_verified"])
        self.assertFalse(manifest["speedup_measured"])
        self.assertEqual(manifest["fate_list_observed_count"], 2)
        with patch("ffv2.upstream.build_plan", return_value=plan), patch("ffv2.upstream.check_plan"):
            reused = upstream.run(self.settings, "build")
            self.assertEqual(reused["status"], "already_built")
            Path(manifest["binaries"]["ffmpeg"]["path"]).write_bytes(b"changed candidate fixture")
            with self.assertRaises(FFV2Error) as error:
                upstream.run(self.settings, "build")
        self.assertEqual(error.exception.code, "candidate_binary_changed")

    def test_native_exclusive_directory_rename_rejects_existing_even_empty(self):
        source, destination = self.root / "stage", self.root / "existing"
        source.mkdir()
        destination.mkdir()
        (source / "retained.txt").write_text("source")
        with self.assertRaises(FileExistsError):
            rename_directory_new(source, destination)
        self.assertTrue((source / "retained.txt").is_file())
        self.assertEqual(list(destination.iterdir()), [])
        new = self.root / "new"
        rename_directory_new(source, new)
        self.assertTrue((new / "retained.txt").is_file())

    def test_manifest_publish_race_never_overwrites(self):
        path = self.root / "candidate.json"
        path.write_text("existing artifact")
        with self.assertRaises(FileExistsError):
            publish_json_new(path, {"new": True})
        self.assertEqual(path.read_text(), "existing artifact")

    def test_source_identity_detects_real_git_diff_and_untracked_file(self):
        source = self.core / "ffmpeg"
        source.mkdir(parents=True)
        def git(*args):
            return subprocess.check_output(["/usr/bin/git", "-C", str(source), *args], text=True, stderr=subprocess.PIPE).strip()
        git("init", "-b", "main")
        git("config", "user.name", upstream.AUTHOR)
        git("config", "user.email", upstream.EMAIL)
        (source / "core.c").write_text("int value = 1;\n")
        git("add", "core.c")
        git("commit", "-m", "Add identity test fixture")
        fake_lock = {**upstream.lock(), "commit": git("rev-parse", "HEAD")}
        with patch("ffv2.upstream.lock", return_value=fake_lock):
            clean = upstream.source_state(self.settings)
            (source / "core.c").write_text("int value = 2;\n")
            changed = upstream.source_state(self.settings)
            self.assertNotEqual(clean["tracked_diff_sha256"], changed["tracked_diff_sha256"])
            self.assertTrue(changed["dirty"])
            (source / "untracked.c").write_text("int other;\n")
            with self.assertRaises(FFV2Error) as error:
                upstream.source_state(self.settings)
        self.assertEqual(error.exception.code, "untracked_core_source")
