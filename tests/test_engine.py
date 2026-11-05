from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from ffv2 import engine
from ffv2.config import Settings
from ffv2.errors import FFV2Error
from ffv2.io import digest, fingerprint, sha256_file, write_json
from test_safety import Workspace


class EngineTests(Workspace):
    def setUp(self):
        super().setUp()
        active_patch = patch("ffv2.engine.ACTIVE", self.root / "active-engine.json")
        active_patch.start()
        self.addCleanup(active_patch.stop)

    def selected(self):
        binary = self.root / "ffmpeg"
        binary.write_bytes(b"local binary integrity fixture")
        value = {"schema_version": 1, "install_prefix": str(self.root),
                 "binaries": {"ffmpeg": str(binary), "ffprobe": str(binary)},
                 "files": {str(binary): {"identity": fingerprint(binary), "sha256": sha256_file(binary)}}}
        value["selection_id"] = digest(value)
        write_json(engine.ACTIVE, value)
        return value, binary

    def test_changed_binary_or_manifest_invalidates_selection(self):
        value, binary = self.selected()
        self.assertEqual(engine.selection(verify_hashes=True), value)
        engine.assert_selection(value["selection_id"])
        with self.assertRaises(FFV2Error):
            engine.assert_selection("different-selected-engine")
        binary.write_bytes(b"changed fixture")
        with self.assertRaises(FFV2Error) as error:
            engine.selection()
        self.assertEqual(error.exception.code, "engine_changed")
        value["profile"] = "tampered"
        write_json(engine.ACTIVE, value)
        with self.assertRaises(FFV2Error) as error:
            engine.selection()
        self.assertEqual(error.exception.code, "engine_manifest_invalid")

    def test_optional_ffplay_does_not_relax_required_programs(self):
        value, binary = self.selected()
        value["binaries"]["ffplay"] = str(binary)
        value["selection_id"] = digest({k:v for k,v in value.items() if k != "selection_id"})
        write_json(engine.ACTIVE, value)
        self.assertEqual(engine.selection(), value)
        value["binaries"].pop("ffprobe")
        value["selection_id"] = digest({k:v for k,v in value.items() if k != "selection_id"})
        write_json(engine.ACTIVE, value)
        with self.assertRaises(FFV2Error):
            engine.selection()

    def test_extended_gate_binds_real_reports_and_rejects_wrong_candidate_or_fabricated_index(self):
        tests = {name:{"status":"pass"} for name in engine.PHASE2_REQUIRED}
        proof = self.root / "proof.json"
        index = self.root / "index.json"
        report = {"status":"completed", "install_prefix":str(self.root), "binary_version":"fixture", "tests":tests}
        write_json(proof, report)
        extended = {**report, "reports":[{"path":str(proof), "sha256":sha256_file(proof)}]}
        def save():
            write_json(index, extended)
            return {"binary_version":"fixture", "phase2_acceptance":{"path":str(index), "sha256":sha256_file(index)}}
        engine.verify_extended(save(), self.root)
        with self.assertRaises(FFV2Error):
            engine.verify_extended(save(), self.root / "another-candidate")
        extended["tests"] = {**tests,"vfr":{"status":"pass","frames":999}}
        with self.assertRaises(FFV2Error):
            engine.verify_extended(save(), self.root)
        extended["tests"] = tests
        verified = save()
        proof.write_text("changed after acceptance")
        with self.assertRaises(FFV2Error) as caught:
            engine.verify_extended(verified, self.root)
        self.assertEqual(caught.exception.code, "engine_extended_changed")

    def test_deactivation_retains_exact_previous_selection_and_env_wins(self):
        value, _ = self.selected()
        with patch.dict(os.environ, {"FFV2_FFMPEG": "/explicit/ffmpeg", "FFV2_FFPROBE": "/explicit/ffprobe"}):
            self.assertEqual(Settings.load().ffmpeg, "/explicit/ffmpeg")
        with patch('ffv2.config.Settings.load',return_value=self.settings), patch('ffv2.releases.PROJECT',self.root):
            result = engine.deactivate()
        self.assertEqual(json.loads(Path(result["retained_selection"]).read_text()), value)
        self.assertIsNone(engine.selection())

    def test_library_closure_rejects_unresolved_runtime_paths(self):
        binary = self.root / "binary"
        binary.write_bytes(b"library fixture")
        with patch("ffv2.engine.capture", return_value=(0, "binary:\n\t@rpath/libmissing.dylib (compatibility version 1.0.0)\n", "")):
            with self.assertRaises(FFV2Error) as error:
                engine.library_closure([binary])
        self.assertEqual(error.exception.code, "engine_library_unresolved")

    def test_retargeted_library_symlink_invalidates_selection_even_if_old_file_is_kept(self):
        value, binary = self.selected()
        alias = self.root / "lib-current"
        alias.symlink_to(binary)
        value["files"][str(binary)]["load_paths"] = [str(alias)]
        value["selection_id"] = digest({k: v for k, v in value.items() if k != "selection_id"})
        write_json(engine.ACTIVE, value)
        self.assertEqual(engine.selection(), value)
        other = self.root / "updated-library"
        other.write_bytes(binary.read_bytes())
        alias.unlink()
        alias.symlink_to(other)
        with self.assertRaises(FFV2Error) as error:
            engine.selection()
        self.assertEqual(error.exception.code, "engine_changed")
