#!/usr/bin/python3 -B
"""Publisher-এর bounded, resumable HD/4K benchmark corpus acquisition।"""
from __future__ import annotations
from public_paths import lab_path, project_path

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ffv2.config import check_mounts
from ffv2.io import sha256_file, write_json
from ffv2.resources import Policy, process_memory, snapshot

SOURCES = {
    "bbb-1080": {"url": "https://download.blender.org/demo/movies/BBB/bbb_sunflower_1080p_30fps_normal.mp4.zip",
                 "archive_bytes": 275524128, "width": 1920, "height": 1080},
    "bbb-2160": {"url": "https://download.blender.org/demo/movies/BBB/bbb_sunflower_2160p_30fps_normal.mp4.zip",
                 "archive_bytes": 632204510, "width": 3840, "height": 2160},
    "tos-1080": {"url": "https://media.xiph.org/tearsofsteel/tears_of_steel_1080p.webm",
                 "archive_bytes": 650 * 1024**2, "width": 1920, "height": None, "direct": True},
    "tos-1080-blender": {"url": "https://download.blender.org/demo/movies/ToS/tears_of_steel_1080p.webm.zip",
                         "archive_bytes": 571346776, "width": 1920, "height": None, "video_suffix": ".webm"},
}


class Guard:
    def __init__(self, root):
        self.root = root
        self.baseline = snapshot(root)
        self.policy = Policy()
        reasons = self.policy.admission(self.baseline, 256 * 1024**2, 5 * 1024**3)
        if reasons:
            raise RuntimeError(str(reasons))
        self.next_check = 0

    def check(self):
        if time.monotonic() < self.next_check:
            return
        memory, method = process_memory(os.getpid())
        reasons = self.policy.running(snapshot(self.root), self.baseline, memory)
        if method != "physical_footprint":
            reasons.append("job_memory_measurement_unavailable")
        if reasons:
            raise RuntimeError(str(reasons))
        self.next_check = time.monotonic() + 1


def download(url, destination, maximum, guard):
    if destination.is_file():
        if not 0 < destination.stat().st_size <= maximum:
            raise RuntimeError("Existing fixture exceeds source bound")
        return {"status": "reused", "bytes": destination.stat().st_size, "sha256": sha256_file(destination)}
    part = destination.with_suffix(destination.suffix + ".part")
    metadata = destination.with_suffix(destination.suffix + ".download.json")
    request = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(request, timeout=30) as response:
        total = int(response.headers["Content-Length"])
        identity = {"url": url, "bytes": total, "etag": response.headers.get("ETag"), "last_modified": response.headers.get("Last-Modified")}
    if not 0 < total <= maximum:
        raise RuntimeError("Publisher response exceeds declared download budget")
    offset = part.stat().st_size if part.is_file() else 0
    if offset and (not metadata.is_file() or json.loads(metadata.read_text()) != identity):
        raise RuntimeError("Partial download identity changed; retained without overwrite")
    write_json(metadata, identity)
    if offset > total:
        raise RuntimeError("Partial download longer than publisher object")
    if offset < total:
        headers = {"Range": "bytes=" + str(offset) + "-"} if offset else {}
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
            if offset and (response.status != 206 or not response.headers.get("Content-Range", "").startswith("bytes " + str(offset) + "-")):
                raise RuntimeError("Publisher did not honor the resumable range")
            if response.headers.get("ETag") != identity["etag"]:
                raise RuntimeError("Publisher object changed between HEAD and GET")
            with part.open("ab" if offset else "xb") as output:
                os.chmod(part, 0o600)
                last_progress = 0
                for block in iter(lambda: response.read(1024**2), b""):
                    guard.check()
                    offset += len(block)
                    if offset > total:
                        raise RuntimeError("Publisher exceeded advertised size")
                    output.write(block)
                    if time.monotonic() - last_progress >= 15:
                        print(json.dumps({"file": destination.name, "bytes": offset, "total": total}), flush=True)
                        last_progress = time.monotonic()
                output.flush()
                os.fsync(output.fileno())
    if part.stat().st_size != total:
        raise RuntimeError("Incomplete download retained")
    checksum = sha256_file(part)
    os.link(part, destination, follow_symlinks=False)
    return {"status": "downloaded", **identity, "sha256": checksum,
            "checksum_scope": "observed HTTPS object SHA256; not a publisher-signed digest"}


def extract(archive, destination, guard):
    if destination.is_file():
        return {"status": "reused", "sha256": sha256_file(destination), "bytes": destination.stat().st_size}
    with zipfile.ZipFile(archive) as source:
        members = source.infolist()
        videos = [entry for entry in members if Path(entry.filename).suffix in (".mp4", ".webm")]
        if len(members) > 32 or len(videos) != 1 or not 0 < videos[0].file_size <= 2 * 1024**3:
            raise RuntimeError("Unexpected archive membership/size")
        entry = videos[0]
        if stat.S_ISLNK(entry.external_attr >> 16):
            raise RuntimeError("Archive video is a symlink")
        pending = destination.with_suffix(".extracting")
        if pending.exists():
            raise RuntimeError("Interrupted extraction retained; use a new output path")
        digest = hashlib.sha256()
        with source.open(entry) as incoming, pending.open("xb") as output:
            os.chmod(pending, 0o600)
            for block in iter(lambda: incoming.read(1024**2), b""):
                guard.check()
                digest.update(block)
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
        if pending.stat().st_size != entry.file_size:
            raise RuntimeError("Archive extraction size mismatch")
        os.link(pending, destination, follow_symlinks=False)
        return {"status": "extracted", "member": entry.filename, "bytes": entry.file_size,
                "sha256": digest.hexdigest(), "zip_crc32_verified": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", choices=tuple(SOURCES), required=True)
    parser.add_argument("--directory", type=Path, default=Path(str(lab_path('ffmpeg-v2-phase4/corpus'))))
    args = parser.parse_args()
    check_mounts(args.directory)
    args.directory.mkdir(parents=True, exist_ok=True)
    guard = Guard(args.directory)
    spec = SOURCES[args.name]
    archive = args.directory / (args.name + (".webm" if spec.get("direct") else ".zip"))
    path = args.directory / (args.name + ".receipt.json")
    if path.is_file():
        saved = json.loads(path.read_text())
        if saved.get("source") != spec:
            raise RuntimeError("Existing corpus source declaration changed")
        if saved.get("download") and archive.exists() and sha256_file(archive) != saved["download"]["sha256"]:
            raise RuntimeError("Retained publisher archive changed")
        if saved.get("status") == "completed":
            video = Path(saved["video"])
            expected = saved.get("extraction", saved["download"])["sha256"]
            if sha256_file(video) != expected:
                raise RuntimeError("Retained native movie changed")
            print(json.dumps({"status": "reused", "receipt": str(path), "video": str(video)}))
            return 0
    receipt = {"status": "running", "owner_pid": os.getpid(), "name": args.name, "publisher": "Blender Foundation",
               "source": spec, "publisher_page": "https://peach.blender.org/" if args.name.startswith("bbb") else "https://mango.blender.org/",
               "license": "CC-BY-3.0", "license_reference": "https://peach.blender.org/about/" if args.name.startswith("bbb") else "https://mango.blender.org/about/",
               "attribution": "(c) copyright 2008, Blender Foundation / www.bigbuckbunny.org" if args.name.startswith("bbb") else "(CC) Blender Foundation | mango.blender.org",
               "system_memory_checks_ignored": guard.policy.ignore_system_memory,
               "estimated_peak_bytes": 256 * 1024**2, "estimated_total_new_storage_bytes": 5 * 1024**3}
    write_json(path, receipt)
    try:
        receipt["download"] = download(spec["url"], archive, spec["archive_bytes"], guard)
        video = archive if spec.get("direct") else args.directory / (args.name + spec.get("video_suffix", ".mp4"))
        if not spec.get("direct"):
            receipt["extraction"] = extract(archive, video, guard)
        from ffv2.engine import selection
        from ffv2.media import probe_path
        media = probe_path(video, selection()["binaries"]["ffprobe"])
        if media["video"]["width"] != spec["width"] or spec["height"] and media["video"]["height"] != spec["height"] or media["duration_seconds"] < 120:
            raise RuntimeError("Native dimensions/long duration gate failed")
        receipt.update(status="completed", video=str(video), media=media, final_resources=snapshot(args.directory).json())
    except BaseException as error:
        receipt.update(status="failed", error=str(error)[:2000], error_type=type(error).__name__)
        raise
    finally:
        write_json(path, receipt)
    print(json.dumps({"status": "completed", "receipt": str(path), "video": str(video),
                      "duration_seconds": media["duration_seconds"], "dimensions": [media["video"]["width"], media["video"]["height"]]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
