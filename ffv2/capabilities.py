from __future__ import annotations

import platform
import json
import os
import re
import shutil
import uuid
from pathlib import Path

from .errors import FFV2Error
from .io import capture, digest, fingerprint, write_json
from .resources import Policy, snapshot


def binary(raw):
    selected = shutil.which(raw)
    if not selected:
        raise FFV2Error("binary_missing", "FFmpeg ও ffprobe আগে থেকে installed থাকতে হবে।",
                        details={"binary": raw})
    return str(Path(selected).resolve())


def capabilities(settings, *, identity_only=False, refresh=False):
    from .bindings import assert_current, build as build_binding
    from .engine import assert_selection
    assert_selection(settings.engine_selection_id)
    ffmpeg, ffprobe = binary(settings.ffmpeg), binary(settings.ffprobe)
    identity = {"ffmpeg": ffmpeg, "ffprobe": ffprobe,
                "ffmpeg_identity": fingerprint(Path(ffmpeg)), "ffprobe_identity": fingerprint(Path(ffprobe))}
    if settings.engine_selection_id:
        identity["engine_selection_id"] = settings.engine_selection_id
    if identity_only:
        return identity
    cache = None
    try:
        cache_directory = settings.ensure_state() / "capabilities"
        if not cache_directory.is_symlink():
            cache_directory.mkdir(mode=0o700, exist_ok=True)
            cache = cache_directory / (digest(identity) + ".json")
        if cache and not refresh and cache.is_file() and not cache.is_symlink() and cache.stat().st_size <= 2 * 1024 ** 2:
            saved = json.loads(cache.read_text())
            if (saved.get("schema_version") == 2 and saved["identity"] == identity and
                    all(saved["capabilities"].get(k) == v for k, v in identity.items()) and
                    saved["sha256"] == digest(saved["capabilities"])):
                assert_current(saved["capabilities"]["runtime_binding"])
                return saved["capabilities"]
    except (ValueError, OSError, KeyError, TypeError, FFV2Error):
        pass
    binding = None
    try:
        binding = build_binding(settings, (ffmpeg, ffprobe))
    except FFV2Error as error:
        if error.code in ("engine_changed", "binary_changed"):
            raise
        # Dependency inspection unsupported হলে query হয়, unverifiable cache নয়।
    except OSError:
        pass
    result = {**identity, "machine": platform.machine(),
              "system": platform.system(), "runtime_acceleration_verified": False}
    if binding:
        result["runtime_binding"] = binding
    for name, path in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe)):
        code, out, err = capture([path, "-hide_banner", "-version"])
        version = re.search(r"\bversion\s+(\S+)", out)
        if code or not version:
            raise FFV2Error("binary_invalid", "Binary version পরীক্ষা ব্যর্থ।", details={"binary": path, "stderr": err[-2000:]})
        result[name + "_version"] = version.group(1)
        result[name + "_identity"] = fingerprint(Path(path))
        if name == "ffmpeg":
            result["build_configuration"] = next((line for line in out.splitlines() if line.startswith("configuration:")), "")
    if result["ffmpeg_version"] != result["ffprobe_version"]:
        raise FFV2Error("binary_version_mismatch", "FFmpeg ও ffprobe-এর একই version ব্যবহার করুন।")
    for option, name, pattern in (
        ("-encoders", "encoders", r"^\s*[VAS][A-Z.]{5}\s+(\S+)"),
        ("-filters", "filters", r"^\s*[TSC.]{2,3}\s+(\S+)"),
    ):
        code, out, err = capture([ffmpeg, "-hide_banner", option])
        if code:
            raise FFV2Error("capability_query_failed", "FFmpeg capability query ব্যর্থ।", details={"option": option, "stderr": err[-2000:]})
        result[name] = sorted(re.findall(pattern, out, re.M))
    code, out, _ = capture([ffmpeg, "-hide_banner", "-h", "long"])
    result["native_jsonl_progress"] = code == 0 and bool(re.search(r"(?m)^\s*-progress_format\s", out))
    if binding:
        assert_current(binding)
    if cache and binding and not cache.is_symlink():
        temporary = cache.with_name("." + uuid.uuid4().hex + ".json")
        try:
            write_json(temporary, {"schema_version": 2, "identity": identity, "capabilities": result, "sha256": digest(result)})
            os.replace(temporary, cache)
        except OSError:
            pass
    return result


def doctor(settings, *, refresh=False):
    info = capabilities(settings, refresh=refresh)
    sample = snapshot(settings.state.parent)
    policy = Policy()
    relevant = {"h264_videotoolbox", "hevc_videotoolbox", "prores_videotoolbox", "libx264", "libx265", "aac", "pcm_s16le"}
    return {"schema_version": 1, "system_memory_checks_ignored": policy.ignore_system_memory,
            "capabilities": {k: v for k, v in info.items() if k not in ("encoders", "filters", "build_configuration", "runtime_binding")},
            "dependency_binding_id": info.get("runtime_binding", {}).get("binding_id"),
            "listed_encoders": [e for e in info["encoders"] if e in relevant],
            "listed_quality_filters": [f for f in info["filters"] if f in ("libvmaf", "ssim", "psnr", "zscale", "tonemap")],
            "resources": sample.json(), "media_job_admitted": not policy.admission(sample),
            "admission_reasons": policy.admission(sample),
            "notices": ["Encoder listing runtime hardware verification নয়।",
                        "Boot disk-এর 300 GB ব্যবহার-লক্ষ্য অতিক্রান্ত।" if sample.boot_used_bytes > 300_000_000_000 else "Boot disk 300 GB লক্ষ্যের মধ্যে।",
                        "MPS model job এই release চালায় না; VideoToolbox-এর system pressure আলাদাভাবে দেখা হয়।"]}
