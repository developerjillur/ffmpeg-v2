import os
import signal
import subprocess
import sys
from unittest.mock import patch

from ffv2 import recovery
from ffv2.io import write_json
from test_safety import Workspace


class SupervisorRecoveryTests(Workspace):
    def registration(self, pid, started=123):
        path = self.root / "phase.live.json"
        value = {"nonce": "fixture", "worker_pid": os.getpid(), "supervisor_pid": 999,
                 "pid": pid, "start_abstime": started}
        write_json(path, value)
        return {"live_process": {"path": str(path), "nonce": "fixture"}}

    def test_reused_pid_or_wrong_nonce_never_receives_a_signal(self):
        request = self.registration(12345)
        with patch("ffv2.recovery.process_info", return_value={"start_abstime": 456, "exit_abstime": 0}), \
             patch("ffv2.recovery.os.killpg") as kill:
            self.assertEqual(recovery.stop_registered(request, 999)["status"], "identity_mismatch")
            request["live_process"]["nonce"] = "other"
            self.assertEqual(recovery.stop_registered(request, 999)["status"], "identity_mismatch")
            kill.assert_not_called()

    def test_already_exited_process_is_not_signalled(self):
        request = self.registration(12345)
        with patch("ffv2.recovery.process_info", return_value=None), patch("ffv2.recovery.os.killpg") as kill:
            self.assertEqual(recovery.stop_registered(request, 999)["status"], "already_exited")
            kill.assert_not_called()

    def test_real_registered_child_stops_and_other_child_survives(self):
        owned = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"], start_new_session=True)
        other = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"], start_new_session=True)
        try:
            birth = recovery.process_info(owned.pid)["start_abstime"]
            result = recovery.stop_registered(self.registration(owned.pid, birth), 999)
            owned.wait(timeout=4)
            self.assertIn(result["status"], ("stopped", "kill_sent"))
            self.assertEqual(owned.returncode, -signal.SIGTERM)
            self.assertIsNone(other.poll())
        finally:
            for child in (owned, other):
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=4)
