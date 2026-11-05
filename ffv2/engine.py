from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from .config import PROJECT, WORK, check_mounts, within
from .errors import FFV2Error
from .io import capture, digest, fingerprint, sha256_file, write_json

ACTIVE = PROJECT / ".runtime/active-engine.json"
PHASE2_REQUIRED = ("metal_nv12", "metal_p010le", "deinterlace", "tone_map_smpte2084", "tone_map_arib-std-b67",
                   "pq_analytic_ramp", "vfr", "rotation", "truncated", "network_playlist", "natural_talking", "natural_motion",
                   "sparse_sampling", "main10_4k", "parent-loss", "cancel", "timeout", "wall_clock_soak", "mcp_pipeline")


def read_json(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 2 * 1024 ** 2:
        raise FFV2Error("engine_manifest_invalid", "ছোট regular engine manifest প্রয়োজন।")
    return json.loads(path.read_text(encoding="utf-8"))


def library_closure(binaries):
    pending = list(binaries)
    result = {}
    while pending:
        requested = Path(pending.pop())
        path = requested.resolve(strict=True)
        if str(path) in result:
            if str(requested) not in result[str(path)]["load_paths"]:
                result[str(path)]["load_paths"].append(str(requested))
            continue
        if len(result) >= 128:
            raise FFV2Error("engine_library_limit", "Library dependency budget অতিক্রম করেছে।")
        result[str(path)] = {"identity": fingerprint(path), "sha256": sha256_file(path),
                             "load_paths": [str(requested)]}
        code, out, err = capture(["/usr/bin/otool", "-L", str(path)])
        if code:
            raise FFV2Error("engine_library_inspection_failed", "Native library inspection ব্যর্থ।",
                            details={"path": str(path), "stderr": err[-1000:]})
        for line in out.splitlines()[1:]:
            name = line.strip().split(" (", 1)[0]
            if name.startswith(("/usr/lib/", "/System/Library/")):
                continue
            if not name.startswith("/"):
                raise FFV2Error("engine_library_unresolved", "Unresolved dylib install name পাওয়া গেছে।",
                                details={"name": name, "binary": str(path)})
            pending.append(name)
    for record in result.values():
        record["load_paths"].sort()
    return result


def selection(*, verify_hashes=False, path=None):
    selected_path = Path(path or os.environ.get('FFV2_PINNED_ENGINE', str(ACTIVE)))
    if not selected_path.exists():
        if path or os.environ.get('FFV2_PINNED_ENGINE'):
            raise FFV2Error('engine_manifest_missing', 'Pinned release engine manifest পাওয়া যায়নি।')
        return None
    value = read_json(selected_path)
    if (not isinstance(value, dict) or value.get("schema_version") != 1 or
            not isinstance(value.get("files"), dict) or not value["files"] or
            not isinstance(value.get("binaries"), dict) or not {"ffmpeg", "ffprobe"} <= set(value["binaries"]) <= {"ffmpeg", "ffprobe", "ffplay"} or
            not isinstance(value.get("install_prefix"), str) or
            digest({k: v for k, v in value.items() if k != "selection_id"}) != value.get("selection_id")):
        raise FFV2Error("engine_manifest_invalid", "Active engine manifest identity মেলেনি।")
    check_mounts(Path(value["install_prefix"]))
    for name, record in value["files"].items():
        path = Path(name)
        moved = any(Path(alias).resolve() != path for alias in record.get("load_paths", [name]))
        if moved or not path.is_file() or fingerprint(path) != record["identity"] or (verify_hashes and sha256_file(path) != record["sha256"]):
            raise FFV2Error("engine_changed", "Selected binary/library বদলেছে; পুনরায় verify ও activate করুন।",
                            details={"path": name})
    return value


def verify_extended(verification, prefix):
    link = verification.get("phase2_acceptance", {})
    if not link.get("path") or not Path(link["path"]).is_file() or sha256_file(Path(link["path"])) != link.get("sha256"):
        raise FFV2Error("engine_extended_unverified", "Runtime Metal candidate-এর Phase 2 acceptance index প্রয়োজন।")
    extended = read_json(link["path"])
    if (extended.get("status") != "completed" or extended.get("install_prefix") != str(prefix) or
            extended.get("binary_version") != verification["binary_version"] or not extended.get("reports") or
            any(extended.get("tests", {}).get(name, {}).get("status") != "pass" for name in PHASE2_REQUIRED)):
        raise FFV2Error("engine_extended_unverified", "একই candidate-এর Phase 2 media/GPU/fault/soak acceptance অসম্পূর্ণ।")
    observed = {}
    for proof in extended["reports"]:
        path = Path(proof["path"])
        if not path.is_file() or sha256_file(path) != proof["sha256"]:
            raise FFV2Error("engine_extended_changed", "Extended acceptance report বদলেছে।")
        report = read_json(path)
        if (report.get("status") != "completed" or report.get("install_prefix") != str(prefix) or
                report.get("binary_version") != verification["binary_version"]):
            raise FFV2Error("engine_extended_unverified", "Extended report একই verified candidate-এর নয়।")
        observed.update(report.get("tests", {}))
    if any(observed.get(name) != extended["tests"][name] for name in PHASE2_REQUIRED):
        raise FFV2Error("engine_extended_unverified", "Acceptance index ও actual test report মেলেনি।")
    return extended


def activate(manifest_path, verification_path):
    manifest_path = Path(manifest_path).resolve(strict=True)
    candidate = read_json(manifest_path)
    prefix = Path(candidate["install_prefix"])
    check_mounts(prefix)
    if (not within(prefix.resolve(), (WORK / "Work/ffmpeg-v2-core/candidates").resolve()) or
            candidate.get("schema_version") != 1 or not candidate.get("fate_list_observed_count")):
        raise FFV2Error("engine_candidate_invalid", "Verified local candidate manifest প্রয়োজন।")
    receipt = read_json(candidate["receipt"])
    if receipt.get("status") != "completed" or not any(
            step["name"] == "core-fate-local" and step.get("receipt", {}).get("exit_code") == 0
            for step in receipt.get("steps", [])):
        raise FFV2Error("engine_fate_unverified", "Local FATE success receipt প্রয়োজন।")
    verification_path = Path(verification_path).resolve(strict=True)
    verification = read_json(verification_path)
    expected = ("fixture", "audio", "software", "videotoolbox", "frame", "contact_sheet",
                "remux", "audio_signal", "remux_packets", "native_progress_jsonl", "native_progress_kv", "mcp_native")
    if "ffplay" in candidate["binaries"]:
        expected += ("ffplay",)
    if (verification.get("status") != "completed" or
            verification.get("binary_version") != candidate["binaries"]["ffmpeg"]["version_output"].split("version ", 1)[1].split()[0] or
            verification.get("install_prefix") != str(prefix) or
            any(verification.get("tests", {}).get(name, {}).get("status") != "pass" for name in expected)):
        raise FFV2Error("engine_media_unverified", "একই candidate-এর completed native-media verification প্রয়োজন।")
    binaries = {name: str(prefix / "bin" / name) for name in ("ffmpeg", "ffprobe", "ffplay") if name in candidate["binaries"]}
    files = library_closure(binaries.values())
    if "ffplay" in binaries and verification.get("verified_files") != files:
        raise FFV2Error("engine_library_unverified", "Media test-এর পর binary/library set বদলেছে অথবা library proof নেই।")
    if "--enable-metal-runtime" in candidate.get("configure_flags", []):
        verify_extended(verification, prefix)
    for name, path in binaries.items():
        if files[str(Path(path).resolve())]["sha256"] != candidate["binaries"][name]["sha256"]:
            raise FFV2Error("engine_changed", "Candidate inspection-এর পর binary বদলেছে।")
    value = {"schema_version": 1, "activated_at": time.time(), "install_prefix": str(prefix),
             "manifest": str(manifest_path), "manifest_sha256": sha256_file(manifest_path),
             "verification": str(verification_path), "verification_sha256": sha256_file(verification_path),
             "source": candidate["source"], "profile": candidate["profile"], "binaries": binaries, "files": files,
             "scope": "এই computer-এর local acceptance; full external-sample FATE বা সব workload acceptance নয়।"}
    value["selection_id"] = digest(value)
    ACTIVE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    previous = None
    from .config import Settings
    from .worker import host_lock
    from .releases import quiescent, lifecycle_lock
    from .checkpoints import sync_directory
    settings = Settings.load(use_active=False)
    with host_lock(settings), lifecycle_lock(settings,exclusive=True):
        quiescent(settings)
        if ACTIVE.exists():
            previous = ACTIVE.with_name("active-engine-" + uuid.uuid4().hex + ".previous.json")
            os.link(ACTIVE, previous, follow_symlinks=False)
        write_json(ACTIVE, value)
        sync_directory(ACTIVE.parent)
    return {"status": "activated", "selection": str(ACTIVE), "selection_id": value["selection_id"],
            "binaries": binaries, "verified_files": len(files), "previous_selection": str(previous) if previous else None}


def status():
    selected = selection(verify_hashes=True)
    return {"status": "active" if selected else "system_default", "selection": selected}


def assert_selection(identity):
    if identity:
        selected = selection()
        if not selected or selected["selection_id"] != identity:
            raise FFV2Error("engine_changed", "Planning-এর পর selected engine/library set বদলেছে; নতুন plan প্রয়োজন।")


def deactivate():
    if not ACTIVE.exists():
        return {"status": "system_default"}
    from .config import Settings
    from .worker import host_lock
    from .releases import quiescent, lifecycle_lock
    from .checkpoints import sync_directory
    settings = Settings.load(use_active=False)
    with host_lock(settings), lifecycle_lock(settings,exclusive=True):
        quiescent(settings)
        retained = ACTIVE.with_name("active-engine-" + uuid.uuid4().hex + ".deactivated.json")
        os.link(ACTIVE, retained, follow_symlinks=False)
        ACTIVE.unlink()
        sync_directory(ACTIVE.parent)
    return {"status": "system_default", "retained_selection": str(retained)}


def native_main(name):
    import sys
    try:
        selected = selection()
        if not selected:
            raise FFV2Error("engine_not_active", "আগে ffv2 engine activate দিয়ে verified candidate নির্বাচন করুন।")
        if name not in selected["binaries"]:
            raise FFV2Error("engine_program_missing", "Selected candidate-এ এই program build করা হয়নি।", details={"program": name})
        os.execv(selected["binaries"][name], [selected["binaries"][name], *sys.argv[1:]])
    except (FFV2Error, OSError, ValueError, KeyError) as error:
        payload = error.payload() if isinstance(error, FFV2Error) else {"code": "native_launch_failed", "message": str(error)[:1000]}
        print(json.dumps({"error": payload}, ensure_ascii=False), file=sys.stderr)
        return 1
