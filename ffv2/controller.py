"""এক worker pass-এর phase-গুলোর জন্য reusable স্বাধীন supervisor।"""
from __future__ import annotations

import json
import os
import selectors
import subprocess
import sys
import time
import uuid

from .config import CODE_ROOT, PROJECT, WORK
from .errors import FFV2Error


class SupervisorSession:
    def __init__(self, settings, lock_fd):
        self.settings, self.lock_fd = settings, lock_fd
        self.process = None
        self.diagnostic = None
        self.selector = None
        self.buffer = bytearray()

    def __enter__(self):
        return self

    def start(self):
        if self.process:
            return
        diagnostic_path = self.settings.ensure_state() / ("supervisor-" + uuid.uuid4().hex + ".log")
        self.diagnostic = diagnostic_path.open("wb")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(CODE_ROOT)
        env.update(FFV2_PROJECT_ROOT=str(PROJECT), FFV2_WORK_ROOT=str(WORK))
        self.process = subprocess.Popen([sys.executable, "-B", "-m", "ffv2.supervisor", "--session"],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.diagnostic,
                                        env=env, cwd=CODE_ROOT, start_new_session=True, pass_fds=(self.lock_fd,))
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)

    def wait_ack(self, path, deadline):
        while True:
            if b"\n" in self.buffer:
                line, _, remaining = self.buffer.partition(b"\n")
                self.buffer = bytearray(remaining)
                try:
                    value = json.loads(line)
                except ValueError as error:
                    raise FFV2Error("supervisor_protocol_invalid", "Supervisor acknowledgement পড়া যায়নি।") from error
                if value != {"receipt": str(path.with_suffix(".receipt.json"))}:
                    raise FFV2Error("supervisor_protocol_invalid", "Supervisor receipt identity মেলেনি।")
                return
            if len(self.buffer) > 8192:
                raise FFV2Error("supervisor_protocol_invalid", "Supervisor protocol message সীমার বাইরে।")
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired("supervisor", 0)
            ready = self.selector.select(min(0.15, max(0, deadline - time.monotonic())))
            if ready:
                part = os.read(self.process.stdout.fileno(), 8192)
                if not part:
                    raise FFV2Error("supervisor_failed", "Supervisor receipt পাঠানোর আগে বন্ধ হয়েছে।")
                self.buffer.extend(part)

    def run(self, path, timeout, job_id):
        from .store import Store
        from .recovery import stop_registered
        self.start()
        request = json.loads(path.read_text())
        try:
            self.process.stdin.write((json.dumps({"request": str(path)}) + "\n").encode())
            self.process.stdin.flush()
            try:
                self.wait_ack(path, time.monotonic() + timeout + 30)
            except KeyboardInterrupt:
                Store(self.settings).cancel(job_id)
                self.wait_ack(path, time.monotonic() + 10)
        except (BrokenPipeError, subprocess.TimeoutExpired, FFV2Error, KeyboardInterrupt) as error:
            try:
                self.close()
            finally:
                try:
                    cleanup = stop_registered(request, self.process.pid)
                except (OSError, ValueError, KeyError, TypeError) as cleanup_error:
                    cleanup = {"status": "cleanup_failed", "error": type(cleanup_error).__name__}
            raise FFV2Error("supervisor_failed", "Supervisor receipt পাওয়া যায়নি; নিবন্ধিত process recovery পরীক্ষা করা হয়েছে।",
                            details={"owned_process_recovery": cleanup}, retryable=True) from error

    def close(self):
        if self.process:
            if self.process.stdin and not self.process.stdin.closed:
                try:
                    self.process.stdin.close()
                except BrokenPipeError:
                    pass
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=3)
            self.process.stdout.close()
        if self.selector:
            self.selector.close()
        if self.diagnostic:
            self.diagnostic.close()

    def __exit__(self, *args):
        self.close()
