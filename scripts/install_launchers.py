#!/usr/bin/python3 -B
"""Verified project launchers-এর জন্য user-local নতুন symlink তৈরি করে।"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    destination = Path.home() / ".local/bin"
    plans = []
    for name in ("ffv2", "ffmpeg-v2", "ffprobe-v2", "ffplay-v2"):
        source, target = ROOT / "bin" / name, destination / name
        same = target.is_symlink() and target.resolve() == source
        if os.path.lexists(target) and not same:
            raise SystemExit("Existing launcher রাখা হয়েছে: " + str(target))
        plans.append({"source": str(source), "target": str(target), "already_installed": same})
    print(json.dumps({"action": "apply" if args.apply else "plan", "launchers": plans}, ensure_ascii=False, indent=2), flush=True)
    if args.apply:
        destination.mkdir(parents=True, exist_ok=True)
        for plan in plans:
            if not plan["already_installed"]:
                os.symlink(plan["source"], plan["target"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
