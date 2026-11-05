"""Supervisor হারালে জীবিত worker শুধু নিবন্ধিত নিজস্ব process group থামায়।"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import time

from .darwin import process_info
from .io import write_json


def register(request, process):
    registration = request.get("live_process")
    if not registration:
        return
    info = process_info(process.pid)
    if not info:
        if process.poll() is not None:
            return
        raise OSError("Owned process birth identity unavailable")
    write_json(registration["path"], {"nonce": registration["nonce"], "worker_pid": request["owner_pid"],
                                    "supervisor_pid": os.getpid(), "pid": process.pid,
                                    "start_abstime": info["start_abstime"]})


def stop_registered(request, supervisor_pid):
    registration = request.get("live_process")
    if not registration:
        return {"status": "not_registered"}
    path = Path(registration["path"])
    if not path.exists():
        return {"status": "not_registered"}
    if path.is_symlink() or path.stat().st_size > 8192:
        return {"status": "invalid_registration"}
    value = json.loads(path.read_text())
    if (value.get("nonce") != registration["nonce"] or value.get("worker_pid") != os.getpid() or
            value.get("supervisor_pid") != supervisor_pid or type(value.get("pid")) is not int or value["pid"] <= 1 or
            type(value.get("start_abstime")) is not int or value["start_abstime"] <= 0):
        return {"status": "identity_mismatch"}
    pid = value["pid"]
    def current():
        info = process_info(pid)
        if not info or info["exit_abstime"]:
            return "exited"
        if info["start_abstime"] != value["start_abstime"] or os.getpgid(pid) != pid:
            return "changed"
        return "owned"
    try:
        state = current()
        if state != "owned":
            return {"status": "already_exited" if state == "exited" else "identity_mismatch", "pid": pid}
        os.killpg(pid, signal.SIGTERM)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            state = current()
            if state != "owned":
                return {"status": "stopped" if state == "exited" else "identity_mismatch", "pid": pid}
            time.sleep(0.02)
        if current() == "owned":
            os.killpg(pid, signal.SIGKILL)
        return {"status": "kill_sent", "pid": pid}
    except ProcessLookupError:
        return {"status": "stopped", "pid": pid}
