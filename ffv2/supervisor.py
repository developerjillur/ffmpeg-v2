"""Worker-এর private request-এর জন্য স্বাধীন resource watchdog process।"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .config import Settings
from .io import write_json
from .process import execute
from .store import Store


def run_request(path):
    request = json.loads(path.read_text(encoding="utf-8"))
    store = Store(Settings.load(state=request["state"]))
    receipt = execute(request, cancelled=lambda: store.cancelled(request["job_id"]),
                      progress=lambda value: store.progress(request["job_id"], value))
    write_json(path.with_suffix(".receipt.json"), receipt)
    return 0 if receipt["status"] == "completed" else 75 if receipt["status"] == "not_admitted" else 1


def main():
    os.nice(10)
    if sys.argv[1:] == ["--session"]:
        while True:
            line = sys.stdin.buffer.readline(8193)
            if not line:
                return 0
            if len(line) > 8192 or not line.endswith(b"\n"):
                raise ValueError("Supervisor request message exceeds limit")
            message = json.loads(line)
            if not isinstance(message, dict) or set(message) != {"request"}:
                raise ValueError("Invalid supervisor request")
            path = Path(message["request"])
            run_request(path)
            try:
                os.write(sys.stdout.fileno(), (json.dumps({"receipt": str(path.with_suffix(".receipt.json"))}) + "\n").encode())
            except BrokenPipeError:
                return 0
    return run_request(Path(sys.argv[1]))


if __name__ == "__main__":
    raise SystemExit(main())
