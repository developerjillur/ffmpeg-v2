#!/usr/bin/python3 -B
"""Pinned static zimg library, project-specific prefix; global package state অক্ষুণ্ণ।"""
from __future__ import annotations
from public_paths import lab_path, project_path
import json
import os
import sys
import tarfile
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ffv2.config import Settings, check_mounts
from ffv2.io import digest, rename_directory_new, sha256_file, write_json
from ffv2.resources import snapshot
from ffv2.store import Store
from ffv2.worker import host_lock, supervised

VERSION = "3.0.6"
SHA = "8015c851b2c81c3131ab91b18e957140e2b129379bf27a7036e5d3eb03a15954"
URL = "https://ghcr.io/v2/homebrew/core/zimg/blobs/sha256:" + SHA
AREA = Path(str(lab_path('ffmpeg-v2-core/tools/zimg-bootstrap-3.0.6')))
PREFIX = AREA.parent / "zimg-3.0.6"

def fetch():
    AREA.mkdir(parents=True, exist_ok=True)
    archive = AREA / "zimg-3.0.6.arm64_golden_gate.bottle.tar.gz"
    if not archive.is_file() or sha256_file(archive) != SHA:
        endpoint = "https://ghcr.io/token?service=ghcr.io&scope=repository:homebrew/core/zimg:pull"
        with urllib.request.urlopen(endpoint, timeout=20) as response:
            token = json.loads(response.read(65536))["token"]
        request = urllib.request.Request(URL, headers={"Authorization": "Bearer " + token})
        with urllib.request.urlopen(request, timeout=30) as response, archive.open("wb") as output:
            total = 0
            while True:
                chunk = response.read(128 * 1024)
                if not chunk: break
                total += len(chunk)
                if total > 16 * 1024 ** 2: raise RuntimeError("Bottle download budget exceeded")
                output.write(chunk)
    if sha256_file(archive) != SHA: raise RuntimeError("Bottle checksum mismatch")
    stage = AREA / ("install-" + uuid.uuid4().hex)
    stage.mkdir()
    allowed = []
    with tarfile.open(archive) as package:
        for member in package.getmembers():
            parts = Path(member.name).parts
            if member.name.startswith("/") or ".." in parts: raise RuntimeError("Unsafe archive member")
            prefix = "zimg/" + VERSION + "/"
            if not member.isfile() or not member.name.startswith(prefix): continue
            relative = member.name[len(prefix):]
            if relative == "lib/libzimg.a" or relative.startswith("include/") or "/licenses/" in relative:
                target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.extractfile(member) as source, target.open("xb") as out:
                    out.write(source.read())
                allowed.append(relative)
    if "lib/libzimg.a" not in allowed: raise RuntimeError("Pinned bottle has no static archive")
    licence = ROOT / "third_party/zimg/COPYING"
    if sha256_file(licence) != "7637386b5f81e8a719ca336233149005e5fa28b5e6054ea7b67de49355b0ad40":
        raise RuntimeError("zimg licence checksum mismatch")
    target = stage / "share/licenses/zimg/COPYING"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(licence.read_bytes())
    allowed.append("share/licenses/zimg/COPYING")
    pc = stage / "lib/pkgconfig/zimg.pc"
    pc.parent.mkdir(parents=True, exist_ok=True)
    pc.write_text("prefix=" + str(PREFIX) + "\nName: zimg\nDescription: zimg\nVersion: " + VERSION +
                  "\nLibs: -L" + str(PREFIX / "lib") + " -lzimg -lc++\nCflags: -I" + str(PREFIX / "include") + "\n")
    report = {"version": VERSION, "archive_url": URL, "archive_sha256": SHA,
              "source_url": "https://github.com/sekrit-twc/zimg/archive/refs/tags/release-3.0.6.tar.gz",
              "source_sha256": "be89390f13a5c9b2388ce0f44a5e89364a20c1c57ce46d382b1fcc3967057577",
              "library_sha256": sha256_file(stage / "lib/libzimg.a"), "files": allowed,
              "provenance": "https://formulae.brew.sh/api/formula/zimg.json", "license": "WTFPL"}
    write_json(stage / "install.json", report)
    rename_directory_new(stage, PREFIX)

def main():
    check_mounts(AREA)
    if "--fetch" in sys.argv:
        fetch()
        return 0
    if (PREFIX / "install.json").is_file():
        saved = json.loads((PREFIX / "install.json").read_text())
        if sha256_file(PREFIX / "lib/libzimg.a") != saved["library_sha256"]:
            raise RuntimeError("Retained zimg archive changed")
        print(json.dumps({"status":"reused","prefix":str(PREFIX)}))
        return 0
    print(json.dumps({"affected_paths":[str(AREA),str(PREFIX)],"archive_sha256":SHA}),flush=True)
    AREA.mkdir(parents=True, exist_ok=True)
    settings=Settings.load(state=ROOT / ".runtime/zimg-bootstrap")
    store=Store(settings)
    plan={"kind":"bootstrap_zimg","spec":{"operation":"bootstrap_zimg","output":str(PREFIX/"install.json")},
          "estimates":{"job_memory_bytes":512*1024**2,"output_budget_bytes":64*1024**2},"timeout_seconds":180}
    plan["plan_id"]=digest(plan)
    queued=store.enqueue(plan)
    job=store.claim(queued["id"])
    directory=store.root/"jobs"/job["id"]/"attempt-001";directory.mkdir(parents=True)
    try:
        with host_lock(settings) as lock_fd:
            receipt=supervised([sys.executable,"-B",str(Path(__file__).resolve()),"--fetch"],
                               "zimg-install",job,directory,settings,snapshot(AREA),lock_fd,AREA,process_kind="tool")
        store.update(job["id"],"completed",receipt=receipt)
    except BaseException as error:
        store.update(job["id"],"failed",error={"code":"bootstrap_failed","message":str(error)[:1000]})
        raise
    print(json.dumps({"status":"completed","prefix":str(PREFIX)}))
    return 0

if __name__=="__main__": raise SystemExit(main())
