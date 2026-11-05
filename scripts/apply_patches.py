#!/usr/bin/python3 -B
"""Locked fresh checkout-এ checksum-verified local patch series প্রয়োগ।"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ffv2.config import Settings
from ffv2.io import sha256_file
from ffv2.upstream import AUTHOR, EMAIL, CORE_ROOT, lock, source_state
from ffv2.worker import host_lock


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    settings = Settings.load(use_active=False)
    manifest = json.loads((ROOT / "patches/manifest.json").read_text())
    if manifest["base_commit"] != lock()["commit"]:
        raise SystemExit("Patch base ও upstream lock মেলেনি।")
    series = [line.strip() for line in (ROOT / "patches/series").read_text().splitlines() if line.strip() and not line.startswith("#")]
    if series != [item["file"] for item in manifest["patches"]]:
        raise SystemExit("Patch series ও manifest মেলেনি।")
    paths = []
    for item in manifest["patches"]:
        path = ROOT / "patches" / item["file"]
        if path.parent != ROOT / "patches" or sha256_file(path) != item["sha256"]:
            raise SystemExit("Patch checksum/path মেলেনি।")
        paths.append(str(path))
    source = CORE_ROOT / "ffmpeg"
    with host_lock(settings):
        state = source_state(settings)
        if state["dirty"]:
            raise SystemExit("Existing source changes রাখা হয়েছে; fresh clean checkpoint প্রয়োজন।")
        tree = subprocess.check_output(["/usr/bin/git", "-C", str(source), "rev-parse", "HEAD^{tree}"], text=True).strip()
        if tree == manifest["patched_tree"]:
            print(json.dumps({"status": "already_applied", "head": state["head"]}))
            return 0
        if state["head"] != manifest["base_commit"]:
            raise SystemExit("Fresh locked base ছাড়া patch apply হবে না; existing branch রাখা হয়েছে।")
        print(json.dumps({"action": "apply" if args.apply else "plan", "source": str(source), "patches": paths}, ensure_ascii=False, indent=2), flush=True)
        subprocess.run(["/usr/bin/git", "-C", str(source), "apply", "--check", *paths], check=True)
        if args.apply:
            env = os.environ.copy()
            env.update(GIT_COMMITTER_NAME=AUTHOR, GIT_COMMITTER_EMAIL=EMAIL)
            subprocess.run(["/usr/bin/git", "-C", str(source), "am", "--committer-date-is-author-date", *paths], check=True, env=env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
