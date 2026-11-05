import ctypes
import os
import subprocess
import sys
from unittest.mock import patch

from ffv2 import darwin
from ffv2.errors import FFV2Error
from ffv2.resources import process_memory, snapshot
from test_safety import Workspace


class NativeResourceTests(Workspace):
    def test_sdk_abi_prefix_and_real_footprint(self):
        self.assertEqual(ctypes.sizeof(darwin.VMStatistics), 160)
        self.assertEqual(darwin.VMStatistics.compressor.offset, 128)
        self.assertEqual(ctypes.sizeof(darwin.SwapUsage), 32)
        record = darwin.process_info(os.getpid())
        self.assertGreater(record["physical_footprint_bytes"], 0)
        self.assertGreater(record["start_abstime"], 0)
        self.assertEqual(record["exit_abstime"], 0)

    def test_native_backend_samples_without_spawning_helpers(self):
        with patch.dict(os.environ, {"FFV2_RESOURCE_BACKEND": "native"}), \
             patch("ffv2.resources.subprocess.check_output", side_effect=AssertionError("helper spawned")):
            sample = snapshot(self.root)
            memory, method = process_memory(os.getpid())
        self.assertEqual(sample.backend, "darwin_native")
        self.assertGreater(sample.headroom_bytes, 0)
        self.assertGreater(memory, 0)
        self.assertEqual(method, "physical_footprint")

    def test_native_api_failure_falls_back_and_forced_native_fails_closed(self):
        with patch("ffv2.darwin.memory_snapshot", side_effect=OSError("fixture")), \
             patch.dict(os.environ, {"FFV2_RESOURCE_BACKEND": "auto"}):
            self.assertEqual(snapshot(self.root).backend, "darwin_cli")
        with patch("ffv2.darwin.memory_snapshot", side_effect=OSError("fixture")), \
             patch.dict(os.environ, {"FFV2_RESOURCE_BACKEND": "native"}), self.assertRaises(FFV2Error):
            snapshot(self.root)
        with patch("ffv2.darwin.process_tree_memory", side_effect=OSError("fixture")), \
             patch.dict(os.environ, {"FFV2_RESOURCE_BACKEND": "native"}):
            self.assertEqual(process_memory(os.getpid()), (0, "unavailable"))

    def test_recursive_tree_includes_grandchildren_and_disappearing_children(self):
        with patch("ffv2.darwin.children", side_effect=lambda pid: {1: {2, 3}, 2: {4}}.get(pid, set())), \
             patch("ffv2.darwin.process_info", side_effect=lambda pid: None if pid == 3 else
                   {"physical_footprint_bytes": pid * 10, "exit_abstime": 0}):
            self.assertEqual(darwin.process_tree_memory(1, (5,)), (120, "physical_footprint"))

    def test_real_child_is_discovered_and_reaped(self):
        child = subprocess.Popen([sys.executable, "-c", "import sys; print('ready', flush=True); sys.stdin.read()"],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "ready")
            self.assertIn(child.pid, darwin.children(os.getpid()))
            own = darwin.process_info(os.getpid())["physical_footprint_bytes"]
            tree, method = darwin.process_tree_memory(os.getpid())
            self.assertGreater(tree, own)
            self.assertEqual(method, "physical_footprint")
        finally:
            child.communicate(timeout=5)

    def test_metadata_measurement_failure_stops_and_reaps_own_helper(self):
        from ffv2.io import capture
        original, children = subprocess.Popen, []
        def spawn(*args, **kwargs):
            child = original(*args, **kwargs)
            children.append(child)
            return child
        with patch("ffv2.resources.process_memory", return_value=(0, "unavailable")), \
             patch("ffv2.io.subprocess.Popen", side_effect=spawn), self.assertRaises(FFV2Error) as error:
            capture([sys.executable, "-c", "import time;time.sleep(10)"])
        self.assertEqual(error.exception.code, "probe_memory_unavailable")
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].returncode)
