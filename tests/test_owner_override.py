from __future__ import annotations

import contextlib
import io
import os
import unittest
from unittest.mock import patch

from ffv2.cli import main
from ffv2.config import GIB
from ffv2.resources import Policy, Snapshot


class OwnerOverrideTests(unittest.TestCase):
    def test_override_ignores_system_memory_and_swap_but_not_other_limits(self):
        baseline = Snapshot("normal", 12 * GIB, GIB, 80 * GIB, 200 * GIB, 100 * GIB)
        pressured = Snapshot("critical", 2 * GIB, 20 * GIB, 80 * GIB, 200 * GIB, 100 * GIB)
        policy = Policy(ignore_system_memory=True, boot_used_limit=400_000_000_000)
        self.assertEqual(policy.admission(pressured, GIB, GIB), [])
        self.assertEqual(policy.running(pressured, baseline, GIB), [])
        self.assertIn("job_memory_over_12gib", policy.running(pressured, baseline, 13 * GIB))
        disk = Snapshot("critical", 2 * GIB, 20 * GIB, 10 * GIB, 410_000_000_000, 5 * GIB)
        self.assertIn("boot_disk_used_limit", policy.admission(disk))
        self.assertIn("output_disk_reserve", policy.running(disk, baseline))

    def test_environment_override_is_explicit(self):
        with patch.dict(os.environ, {"FFV2_IGNORE_SYSTEM_MEMORY": "0"}):
            self.assertFalse(Policy().ignore_system_memory)
        with patch.dict(os.environ, {"FFV2_IGNORE_SYSTEM_MEMORY": "1"}):
            self.assertTrue(Policy().ignore_system_memory)

    def test_cli_override_is_scoped_and_restored(self):
        observed = []
        def doctor(settings, *, refresh=False):
            self.assertFalse(refresh)
            observed.append(Policy().ignore_system_memory)
            return {"system_memory_checks_ignored": Policy().ignore_system_memory}
        with patch.dict(os.environ, {"FFV2_IGNORE_SYSTEM_MEMORY": "0"}), \
             patch("ffv2.cli.doctor", side_effect=doctor), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--ignore-system-memory", "doctor"]), 0)
            self.assertFalse(Policy().ignore_system_memory)
        self.assertEqual(observed, [True])
