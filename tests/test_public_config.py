import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory

from ffv2.config import check_mounts, GIB
from ffv2.errors import FFV2Error
from ffv2.resources import Policy, Snapshot


class PublicConfigurationTests(unittest.TestCase):
    def test_spawned_worker_preserves_workspace_when_launch_directory_changes(self):
        from ffv2.config import Settings, PROJECT, WORK
        from ffv2.service import start_worker
        with TemporaryDirectory() as directory:
            settings=Settings(state=Path(directory),output_roots=(Path(directory),))
            with patch('ffv2.releases.assert_current'), patch('ffv2.service.subprocess.Popen') as spawn:
                spawn.return_value.pid=123
                start_worker(settings)
            env=spawn.call_args.kwargs['env']
            self.assertEqual(env['FFV2_PROJECT_ROOT'],str(PROJECT))
            self.assertEqual(env['FFV2_WORK_ROOT'],str(WORK))

    def test_ordinary_workspace_does_not_require_an_external_volume(self):
        with patch.dict(os.environ, {'FFV2_REQUIRED_MOUNTS':''}), patch('ffv2.config.os.path.ismount',return_value=False):
            check_mounts(Path('/tmp/ordinary-project/output.mp4'))

    def test_external_volume_is_checked_before_any_directory_creation(self):
        with patch.dict(os.environ, {'FFV2_REQUIRED_MOUNTS':''}), patch('ffv2.config.os.path.ismount',return_value=False):
            with self.assertRaises(FFV2Error):check_mounts(Path('/Volumes/ExampleMedia/jobs/output.mp4'))

    def test_public_default_has_free_space_guard_without_owner_disk_ceiling(self):
        with patch.dict(os.environ, {'FFV2_BOOT_USED_LIMIT_BYTES':''}):
            policy=Policy()
        large=Snapshot('normal',32*GIB,0,100*GIB,900*GIB,100*GIB)
        self.assertEqual(policy.admission(large,GIB,GIB),[])
        scarce=Snapshot('normal',32*GIB,0,10*GIB,900*GIB,100*GIB)
        self.assertIn('boot_disk_free',policy.admission(scarce))

    def test_configured_disk_ceiling_and_invalid_values_fail_closed(self):
        with patch.dict(os.environ, {'FFV2_BOOT_USED_LIMIT_BYTES':'400000000000'}):
            self.assertEqual(Policy().boot_used_limit,400000000000)
        for value in ('-1','nope','0'):
            with patch.dict(os.environ, {'FFV2_BOOT_USED_LIMIT_BYTES':value}), self.assertRaises(FFV2Error):Policy()

    def test_fresh_process_uses_caller_project_and_configured_work_root(self):
        root=Path(__file__).resolve().parents[1]
        env=dict(os.environ,FFV2_PROJECT_ROOT=str(root),FFV2_WORK_ROOT=str(root/'.ffv2-work'),PYTHONPATH=str(root))
        code='import json;from ffv2.config import PROJECT,WORK;print(json.dumps([str(PROJECT),str(WORK)]))'
        value=json.loads(subprocess.check_output([sys.executable,'-B','-c',code],env=env,text=True))
        self.assertEqual(value,[str(root),str(root/'.ffv2-work')])
