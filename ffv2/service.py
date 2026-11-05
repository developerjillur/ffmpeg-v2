from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

from .capabilities import capabilities
from .config import CODE_ROOT, PROJECT, WORK
from .planner import build_plan
from .store import Store


def submit(spec, settings, *, key=None, restricted=False):
    from .releases import assert_current
    assert_current()
    plan = build_plan(spec, settings, capabilities(settings), restricted=restricted, allow_existing=True)
    return Store(settings).enqueue(plan, key)


def start_worker(settings, *, ignore_system_memory=False):
    from .releases import assert_current
    assert_current()
    root = settings.ensure_state()
    identity = uuid.uuid4().hex
    log_path = root / ("worker-" + identity + ".log")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(CODE_ROOT)
    env.update(FFV2_PROJECT_ROOT=str(PROJECT), FFV2_WORK_ROOT=str(WORK))
    if ignore_system_memory:
        env['FFV2_IGNORE_SYSTEM_MEMORY'] = '1'
    with log_path.open("wb") as log:
        process = subprocess.Popen([sys.executable, "-B", "-m", "ffv2", "--state-dir", str(settings.state), "worker", "--drain"],
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   cwd=CODE_ROOT, env=env, start_new_session=True)
    return {"worker_pid": process.pid, "launch_status": "spawned_not_verified", "log": str(log_path),
            "message": "Job status poll করুন; launch response encoding শুরু বা সফল হওয়ার প্রমাণ নয়।"}
