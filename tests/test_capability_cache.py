from dataclasses import replace
import json
from unittest.mock import patch
import os

from ffv2.capabilities import capabilities
from ffv2 import bindings
from ffv2.bindings import environment, strong_identity
from ffv2.io import digest, fingerprint, sha256_file
from test_safety import Workspace


class CapabilityCacheTests(Workspace):
    def setUp(self):
        super().setUp()
        self.builder = patch("ffv2.bindings.build", side_effect=self.binding)
        self.builder.start()
        self.addCleanup(self.builder.stop)

    def binding(self, settings, binaries):
        files = {name: {"identity": strong_identity(name), "sha256": sha256_file(name), "load_paths": [name]}
                 for name in binaries}
        if getattr(self, "library", None):
            files[str(self.library)] = {"identity": strong_identity(self.library), "sha256": sha256_file(self.library),
                                        "load_paths": [str(self.alias)]}
        value = {"schema_version": 1, "environment": bindings.environment(), "files": files}
        value["binding_id"] = digest(value)
        return value

    def inspect(self, argv, **kwargs):
        if "-version" in argv:
            return 0, "ffmpeg version 9.0.2\nconfiguration: fixture", ""
        if "-encoders" in argv:
            return 0, " V..... libx264\n", ""
        if "-filters" in argv:
            return 0, " T.. scale\n", ""
        return 0, " -progress_format format\n", ""

    def test_verified_cache_skips_processes_and_refresh_or_corruption_reprobes(self):
        settings = replace(self.settings, ffmpeg="/usr/bin/false", ffprobe="/usr/bin/false",
                           engine_selection_id="fixture")
        with patch("ffv2.engine.assert_selection"), patch("ffv2.capabilities.capture", side_effect=self.inspect) as capture:
            first = capabilities(settings)
            self.assertEqual(capture.call_count, 5)
            self.assertEqual(capabilities(settings), first)
            self.assertEqual(capture.call_count, 5)
            fast = capabilities(settings, identity_only=True)
            self.assertEqual(fast["ffmpeg_identity"], first["ffmpeg_identity"])
            self.assertNotIn("ffmpeg_version", fast)
            self.assertEqual(capture.call_count, 5)
            capabilities(settings, refresh=True)
            self.assertEqual(capture.call_count, 10)
            cache = next((settings.state / "capabilities").glob("*.json"))
            saved = json.loads(cache.read_text())
            saved["capabilities"]["ffmpeg_version"] = "corrupted"
            cache.write_text(json.dumps(saved))
            self.assertEqual(capabilities(settings)["ffmpeg_version"], "9.0.2")
            self.assertEqual(capture.call_count, 15)

    def test_changed_binary_identity_cannot_hit_old_cache(self):
        executable = self.root / "ffmpeg"
        executable.write_text("first fixture")
        executable.chmod(0o700)
        settings = replace(self.settings, ffmpeg=str(executable), ffprobe=str(executable),
                           engine_selection_id="fixture")
        with patch("ffv2.engine.assert_selection"), patch("ffv2.capabilities.capture", side_effect=self.inspect) as capture:
            first = capabilities(settings)
            executable.write_text("modified executable fixture")
            second = capabilities(settings)
        self.assertNotEqual(first["ffmpeg_identity"], second["ffmpeg_identity"])
        self.assertEqual(capture.call_count, 10)

    def test_unusable_optional_cache_does_not_make_a_valid_engine_unavailable(self):
        settings = replace(self.settings, ffmpeg="/usr/bin/false", ffprobe="/usr/bin/false",engine_selection_id="fixture")
        settings.ensure_state().joinpath("capabilities").write_text("blocked cache directory")
        with patch("ffv2.engine.assert_selection"), patch("ffv2.capabilities.capture",side_effect=self.inspect) as capture:
            self.assertEqual(capabilities(settings)["ffmpeg_version"],"9.0.2")
            self.assertEqual(capture.call_count,5)

    def test_custom_binaries_cache_and_dependency_change_with_restored_mtime(self):
        self.library = self.root / "libfixture.dylib"
        self.library.write_bytes(b"first")
        self.alias = self.root / "alias.dylib"
        self.alias.symlink_to(self.library)
        settings = replace(self.settings, ffmpeg="/usr/bin/false", ffprobe="/usr/bin/false")
        with patch("ffv2.capabilities.capture", side_effect=self.inspect) as capture:
            first = capabilities(settings)
            self.assertEqual(capabilities(settings), first)
            self.assertEqual(capture.call_count, 5)
            before = self.library.stat()
            self.library.write_bytes(b"other")
            os.utime(self.library, ns=(before.st_atime_ns, before.st_mtime_ns))
            second = capabilities(settings)
            self.assertNotEqual(first["runtime_binding"]["binding_id"], second["runtime_binding"]["binding_id"])
            self.assertEqual(capture.call_count, 10)

    def test_alias_retarget_and_os_change_invalidate_cache(self):
        self.library = self.root / "first.dylib"
        self.library.write_bytes(b"first")
        self.alias = self.root / "alias.dylib"
        self.alias.symlink_to(self.library)
        settings = replace(self.settings, ffmpeg="/usr/bin/false", ffprobe="/usr/bin/false")
        with patch("ffv2.capabilities.capture", side_effect=self.inspect) as capture:
            capabilities(settings)
            other = self.root / "other.dylib"
            other.write_bytes(b"other")
            self.alias.unlink()
            self.alias.symlink_to(other)
            self.library = other
            capabilities(settings)
            with patch("ffv2.bindings.environment", return_value={"fixture": "new OS"}):
                capabilities(settings)
            self.assertEqual(capture.call_count, 15)

    def test_saved_plan_rejects_same_size_source_change_with_restored_mtime(self):
        from ffv2.worker import checked_plan
        from ffv2.errors import FFV2Error
        plan = self.plan()
        before = self.source.stat()
        self.source.write_bytes(b"x" * before.st_size)
        os.utime(self.source, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaises(FFV2Error) as error:
            checked_plan({"plan": plan}, self.settings)
        self.assertEqual(error.exception.code, "source_changed")

    def test_saved_binding_survives_cache_removal_and_rejects_changed_library(self):
        from ffv2.bindings import assert_current
        from ffv2.errors import FFV2Error
        self.library = self.root / "libfixture.dylib"
        self.library.write_bytes(b"first")
        self.alias = self.library
        settings = replace(self.settings, ffmpeg="/usr/bin/false", ffprobe="/usr/bin/false")
        with patch("ffv2.capabilities.capture", side_effect=self.inspect):
            binding = capabilities(settings)["runtime_binding"]
        next((settings.state / "capabilities").glob("*.json")).unlink()
        assert_current(binding)
        self.library.write_bytes(b"other")
        with self.assertRaises(FFV2Error):
            assert_current(binding)

    def test_cold_binding_rechecks_content_if_file_changes_after_closure_hash(self):
        from ffv2.errors import FFV2Error
        self.builder.stop()
        library = self.root / "libfixture.dylib"
        library.write_bytes(b"first")
        identity = fingerprint(library)
        before = library.stat()
        old_hash = sha256_file(library)
        def inspect(_):
            library.write_bytes(b"other")
            os.utime(library, ns=(before.st_atime_ns, before.st_mtime_ns))
            return {str(library): {"identity": identity, "sha256": old_hash, "load_paths": [str(library)]}}
        with patch("ffv2.engine.library_closure", side_effect=inspect), self.assertRaises(FFV2Error) as error:
            bindings.build(self.settings, (str(library),))
        self.assertEqual(error.exception.code, "binary_changed")
