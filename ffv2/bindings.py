"""Binary ও non-system dylib-এর reusable runtime identity।"""
from __future__ import annotations

import os
import platform
from pathlib import Path

from .errors import FFV2Error
from .io import digest, fingerprint, sha256_file

def workflow_identity():
    from .config import CODE_ROOT
    return digest({p.name: sha256_file(p) for p in sorted((CODE_ROOT/'ffv2').glob('*.py'))})

def assert_workflow(plan):
    if plan.get('runtime_code_id') and plan['runtime_code_id'] != workflow_identity():
        raise FFV2Error('runtime_code_changed', 'Planning/checkpoint-এর পর workflow code বদলেছে; একই frozen release অথবা নতুন plan প্রয়োজন।')


def strong_identity(path):
    stat = Path(path).stat()
    return {"device": stat.st_dev, "inode": stat.st_ino, "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns, "ctime_ns": stat.st_ctime_ns}


def environment():
    uname = platform.uname()
    return {"system": uname.system, "release": uname.release, "version": uname.version,
            "machine": uname.machine,
            "dyld": {k: v for k, v in os.environ.items() if k.startswith("DYLD_")}}


def build(settings, binaries):
    from .engine import library_closure, selection
    if any(k.startswith("DYLD_") for k in os.environ):
        # otool-এর closure injected/search-path libraries-এর প্রমাণ নয়।
        raise FFV2Error("runtime_binding_unavailable", "DYLD override-সহ dependency cache ব্যবহার হয় না।")
    if settings.engine_selection_id:
        selected = selection(verify_hashes=True)
        if not selected or selected["selection_id"] != settings.engine_selection_id:
            raise FFV2Error("engine_changed", "Selected engine identity মেলেনি।")
        records = selected["files"]
    else:
        records = library_closure(binaries)
    files = {}
    for name, record in records.items():
        path = Path(name)
        identity = strong_identity(path)
        if (fingerprint(path) != record["identity"] or sha256_file(path) != record["sha256"] or
                strong_identity(path) != identity):
            raise FFV2Error("binary_changed", "Dependency inspection-এর সময় file বদলেছে।")
        files[name] = {"identity": identity, "sha256": record["sha256"], "load_paths": record["load_paths"]}
    value = {"schema_version": 1, "environment": environment(), "files": files}
    value["binding_id"] = digest(value)
    assert_current(value)
    return value


def assert_current(value):
    try:
        if (value["schema_version"] != 1 or value["environment"] != environment() or
                not 1 <= len(value["files"]) <= 128 or
                digest({k: v for k, v in value.items() if k != "binding_id"}) != value["binding_id"]):
            raise ValueError("Runtime binding signature changed")
        for name, record in value["files"].items():
            path = Path(name)
            if (not path.is_absolute() or not path.is_file() or
                    strong_identity(path) != record["identity"] or not record["load_paths"] or
                    any(Path(alias).resolve(strict=True) != path for alias in record["load_paths"])):
                raise ValueError("Runtime file changed: " + name)
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise FFV2Error("binary_changed", "Binary/library/OS identity বদলেছে; নতুন plan প্রয়োজন।") from error


def assert_sources(plan):
    from .config import check_mounts
    seen = set()
    for source in [plan["source"], *plan.get("sources", []), *plan.get("assets", [])]:
        path = Path(source["path"])
        if str(path) in seen:
            continue
        seen.add(str(path))
        check_mounts(path)
        try:
            if path.resolve(strict=True) != path or fingerprint(path) != source["fingerprint"]:
                raise ValueError("Source path/identity changed")
            if source.get("strong_identity") and strong_identity(path) != source["strong_identity"]:
                raise ValueError("Source ctime changed")
            if source.get("sha256") and sha256_file(path) != source["sha256"]:
                raise ValueError("Asset content changed")
        except (OSError, ValueError) as error:
            raise FFV2Error("source_changed", "Planning-এর পর media/subtitle/font source বদলেছে; নতুন plan প্রয়োজন।") from error
