from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

from .config import GIB, CODE_ROOT, PROJECT, WORK, check_mounts, within
from .errors import FFV2Error
from .io import capture, digest, fingerprint, publish_json_new, rename_directory_new, sha256_file, write_json
from .resources import Policy, snapshot
from .store import Store

CORE_ROOT = WORK / "Work/ffmpeg-v2-core"
LOCK_PATH = CODE_ROOT / "upstream.lock.json"
AUTHOR = "Jillur Rahman"
EMAIL = "22579419+developerjillur@users.noreply.github.com"
NATIVE_FLAGS = ["--disable-autodetect", "--disable-network", "--disable-debug", "--disable-doc",
                "--disable-ffplay", "--enable-pthreads", "--enable-videotoolbox", "--enable-audiotoolbox", "--enable-neon"]
BASELINE_FLAGS = ["--enable-shared", "--enable-pthreads", "--enable-version3", "--disable-debug",
                  "--disable-doc", "--enable-ffplay", "--enable-gpl", "--enable-libsvtav1", "--enable-libopus",
                  "--enable-libx264", "--enable-libmp3lame", "--enable-libdav1d", "--enable-libvmaf",
                  "--enable-libvpx", "--enable-libx265", "--enable-openssl", "--enable-videotoolbox",
                  "--enable-audiotoolbox", "--enable-neon", "--enable-metal-runtime", "--enable-libzimg", "--enable-libass", "--extra-cflags=-I/opt/homebrew/include",
                  "--extra-ldflags=-L/opt/homebrew/lib"]
PKG_PATH = ":".join((str(CORE_ROOT / "tools/zimg-3.0.6/lib/pkgconfig"), str(CORE_ROOT / "tools/libass-0.17.5/lib/pkgconfig"), "/opt/homebrew/lib/pkgconfig", "/opt/homebrew/share/pkgconfig",
                     "/opt/homebrew/opt/openssl@3/lib/pkgconfig"))


def lock():
    value = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if (value.get("source_repository") != "https://github.com/FFmpeg/FFmpeg.git" or
            not re.fullmatch(r"n\d+\.\d+(?:\.\d+)?", value.get("release_tag", "")) or
            not re.fullmatch(r"[0-9a-f]{40}", value.get("commit", "")) or
            not re.fullmatch(r"[0-9a-f]{40}", value.get("tag_object", ""))):
        raise FFV2Error("invalid_upstream_lock", "Upstream lock-এর repository/tag/commit যাচাই করুন।")
    return {key: value[key] for key in ("source_repository", "release_tag", "commit", "tag_object")}


def workspace(settings):
    check_mounts(CORE_ROOT)
    resolved = CORE_ROOT.resolve()
    if CORE_ROOT.is_symlink() or not any(within(resolved, root.resolve()) for root in settings.output_roots):
        raise FFV2Error("core_workspace_denied", "Core workspace project/NexaWork-এর অনুমোদিত স্থানে হতে হবে।")
    return resolved


def command(argv, *, timeout=10, strip=True, env=None):
    code, out, err = capture(argv, timeout=timeout, env=env)
    if code:
        raise FFV2Error("upstream_inspection_failed", "Source/tool inspection ব্যর্থ।",
                        details={"argv": argv, "exit_code": code, "stderr": err[-2000:]})
    return out.strip() if strip else out


def tool_info(name, *, required=True):
    selected = shutil.which(name)
    if name in ("pkg-config", "pkgconf"):
        local = Path(os.environ.get("FFV2_PKG_CONFIG", CORE_ROOT / "tools/pkgconf-3.0.10/bin/pkgconf"))
        if local.is_file() and os.access(local, os.X_OK):
            selected = str(local)
    if not selected:
        if required:
            raise FFV2Error("build_tool_missing", "Native build-এর প্রয়োজনীয় tool পাওয়া যায়নি।", details={"tool": name})
        return {"present": False, "name": name}
    path = str(Path(selected).resolve())
    version = command([path, "--version"]).splitlines()[0]
    return {"present": True, "path": path, "version": version, "identity": fingerprint(Path(path))}


def source_state(settings, *, source=None):
    source = source or workspace(settings) / "ffmpeg"
    if not source.is_dir() or not (source / ".git").is_dir():
        raise FFV2Error("upstream_source_missing", "Locked source checkout আগে prepare করুন।", details={"source": str(source)})
    git = tool_info("git")["path"]
    base = lock()
    head = command([git, "-C", str(source), "rev-parse", "HEAD"])
    code, _, _ = capture([git, "-C", str(source), "merge-base", "--is-ancestor", base["commit"], head])
    if code:
        raise FFV2Error("upstream_lineage_mismatch", "Source HEAD locked release-এর descendant নয়।")
    status = command([git, "-C", str(source), "status", "--porcelain", "--untracked-files=normal"])
    if any(line.startswith("??") for line in status.splitlines()):
        raise FFV2Error("untracked_core_source", "Untracked core source আছে; patch identity সম্পূর্ণ করা প্রয়োজন।")
    diff = command([git, "-C", str(source), "diff", "--no-ext-diff", "--no-textconv", "HEAD", "--binary"], strip=False)
    return {"path": str(source), "head": head, "locked_base": base["commit"], "tracked_diff_sha256": digest(diff),
            "dirty": bool(status), "status": status, "branch": command([git, "-C", str(source), "branch", "--show-current"])}


def finish_plan(plan):
    plan["plan_id"] = digest(plan)
    return plan


def prepare_plan(settings):
    root = workspace(settings)
    upstream = lock()
    git = tool_info("git")
    if os.path.lexists(root / "ffmpeg"):
        raise FFV2Error("upstream_source_exists", "Existing source রাখা হয়েছে; upstream status দেখুন।")
    return finish_plan({"schema_version": 1, "kind": "upstream_prepare", "upstream_lock": upstream,
                        "spec": {"operation": "upstream_prepare", "output": str(root / "ffmpeg")}, "tools": {"git": git},
                        "argv_template": [git["path"], "clone", "--depth", "1", "--single-branch", "--branch",
                                          upstream["release_tag"], upstream["source_repository"], "<STAGING_CHECKOUT>"],
                        "estimates": {"job_memory_bytes": 512 * 1024 ** 2, "output_budget_bytes": GIB},
                        "timeout_seconds": 900, "affected_paths": [str(root / "ffmpeg"), str(root / ".staging")],
                        "source_publish": "macOS RENAME_EXCL; preserve failed staging; never replace destination"})


def build_plan(settings, profile="native", *, jobs=2):
    if type(jobs) is not int or jobs not in (1, 2):
        raise FFV2Error("invalid_build_jobs", "Build concurrency 1 অথবা 2 দিন।")
    if profile not in ("native", "baseline", "m4"):
        raise FFV2Error("invalid_build_profile", "Build profile native, baseline অথবা m4 দিন।")
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise FFV2Error("build_platform_unsupported", "এই build profile Apple Silicon macOS-এর জন্য।")
    root = workspace(settings)
    state = source_state(settings)
    tools = {name: tool_info(name) for name in ("git", "clang", "make", "xcrun")}
    pkg = tool_info("pkg-config", required=False)
    if not pkg["present"]:
        pkg = tool_info("pkgconf", required=False)
    dependencies = {}
    if profile in ("baseline", "m4"):
        if not pkg["present"]:
            raise FFV2Error("build_tool_missing", "Baseline feature build-এর জন্য existing pkg-config/pkgconf প্রয়োজন; automatic install হয়নি।",
                            details={"tool": "pkg-config"})
        for module in ("x264", "x265", "libvmaf", "opus", "vpx", "dav1d", "SvtAv1Enc", "openssl", "zimg", "libass", "sdl2"):
            dependencies[module] = command([pkg["path"], "--modversion", module], env={**os.environ, "PKG_CONFIG_PATH": PKG_PATH})
    sdk = command([tools["xcrun"]["path"], "--show-sdk-path"])
    flags = list(NATIVE_FLAGS if profile == "native" else BASELINE_FLAGS)
    if profile == "m4":
        brand = command(["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"])
        if not brand.startswith("Apple M4"):
            raise FFV2Error("cpu_profile_mismatch", "m4 profile-এর জন্য Apple M4 computer প্রয়োজন।")
        flags += ["--cpu=apple-m4", "--extra-version=ffmpeg-v2-m4"]
    flags += ["--cc=" + tools["clang"]["path"]]
    if profile in ("baseline", "m4"):
        flags += ["--pkg-config=" + pkg["path"]]
    identity = digest({"source": state, "profile": profile, "tools": tools, "dependencies": dependencies, "sdk": sdk, "flags": flags, "jobs": jobs})[:20]
    candidate = root / "candidates" / (profile + "-" + identity)
    plan = {"schema_version": 1, "kind": "upstream_build", "upstream_lock": lock(),
            "spec": {"operation": "upstream_build", "input": state["path"], "output": str(candidate / "candidate.json")},
            "source": state, "profile": profile, "tools": tools, "pkg_config": pkg, "dependencies": dependencies,
            "sdk": sdk, "configure_flags": flags, "timeout_seconds": 5400, "build_jobs": jobs,
            "estimates": {"job_memory_bytes": (2 if jobs == 1 else 3) * GIB, "output_budget_bytes": 6 * GIB},
            "steps_template": [
                {"name": "configure", "argv": [str(Path(state["path"]) / "configure"), "--prefix=<INSTALL_PREFIX>", *flags]},
                {"name": "compile", "argv": [tools["make"]["path"], "-j" + str(jobs)]},
                {"name": "install", "argv": [tools["make"]["path"], "-j" + str(jobs), "install"]},
                {"name": "fate-list", "argv": [tools["make"]["path"], "-s", "fate-list"]},
                {"name": "fate-local", "argv": [tools["make"]["path"], "-j" + str(jobs), "fate"]}],
            "fate_scope": "available local tests only; external samples not acquired; full FATE unverified",
            "feature_parity_target": "installed_codec_libraries" if profile != "native" else "native_bootstrap",
            "feature_parity_verified": False,
            "notices": ["Native profile is a bootstrap build, not feature parity with Homebrew.",
                        "No speedup or release acceptance follows from a successful build."]}
    if profile in ("baseline", "m4"):
        for index, surface in enumerate(("nv12", "p010le")):
            graph = "format=" + surface + ",hwupload,yadif_videotoolbox,hwdownload,format=" + surface
            plan["steps_template"].insert(3 + index, {"name":"metal-smoke-" + surface, "argv":[
                "<INSTALL_PREFIX>/bin/ffmpeg", "-v", "error", "-nostdin", "-filter_threads", "1", "-threads", "1",
                "-init_hw_device", "videotoolbox=vt", "-filter_hw_device", "vt", "-f", "lavfi", "-i",
                "testsrc2=size=64x64:rate=4:duration=1", "-vf", graph, "-threads", "1", "-f", "null", "-"]})
    return finish_plan(plan)


def status(settings):
    root = workspace(settings)
    result = {"workspace": str(root), "upstream_lock": lock(), "source_present": False,
              "pkg_config": tool_info("pkg-config", required=False), "candidates": []}
    if (root / "ffmpeg").exists():
        result.update(source_present=True, source=source_state(settings))
    for path in sorted((root / "candidates").glob("*/candidate.json"))[:20]:
        if path.stat().st_size > 2 * 1024 ** 2:
            continue
        value = json.loads(path.read_text(encoding="utf-8"))
        result["candidates"].append({"manifest": str(path), "profile": value["profile"],
                                     "install_prefix": value["install_prefix"], "release_accepted": False})
    return result


def check_plan(plan, settings):
    if digest({k: v for k, v in plan.items() if k != "plan_id"}) != plan["plan_id"]:
        raise FFV2Error("plan_modified", "Core plan digest মেলেনি।")
    if plan["upstream_lock"] != lock():
        raise FFV2Error("upstream_lock_changed", "Planning-এর পর upstream lock বদলেছে।")
    workspace(settings)
    for name, saved in plan["tools"].items():
        if saved != tool_info(name):
            raise FFV2Error("build_tool_changed", "Planning-এর পর build tool বদলেছে।", details={"tool": name})
    if plan["kind"] == "upstream_prepare":
        if os.path.lexists(plan["spec"]["output"]):
            raise FFV2Error("upstream_source_exists", "Source destination আগে থেকেই আছে।")
    elif source_state(settings) != plan["source"]:
        raise FFV2Error("core_source_changed", "Planning-এর পর core source বা tracked patch বদলেছে।")


def ensure_running(baseline, destination, store, job_id):
    if store.cancelled(job_id):
        raise FFV2Error("cancelled", "Core job বাতিল হয়েছে।", exit_code=130)
    reasons = Policy().running(snapshot(destination), baseline)
    if reasons:
        raise FFV2Error("resource_stopped", "Core job resource gate-এ থেমেছে।", details={"reasons": reasons}, exit_code=75)


def candidate_version_matches(text, expected):
    version = re.search(r"\bversion\s+(\S+)", text)
    return bool(version and re.match(r"n?" + re.escape(expected) + r"(?:$|[-+.])", version.group(1)))


def perform_upstream(job, settings, lock_fd, store):
    from .worker import hash_guarded, supervised
    plan = job["plan"]
    directory = store.root / "jobs" / job["id"] / ("attempt-%03d" % job["attempt"])
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    receipt = {"job_id": job["id"], "attempt": job["attempt"], "kind": plan["kind"],
               "system_memory_checks_ignored": Policy().ignore_system_memory,
               "plan_id": plan["plan_id"], "directory": str(directory), "steps": []}
    phase = "preflight"
    try:
        check_plan(plan, settings)
        root = workspace(settings)
        existing = root if root.is_dir() else root.parent
        baseline = snapshot(existing)
        reasons = Policy().admission(baseline, plan["estimates"]["job_memory_bytes"], plan["estimates"]["output_budget_bytes"])
        if reasons:
            raise FFV2Error("resource_not_admitted", "Source download/build-এর নিরাপদ headroom নেই।",
                            details={"reasons": reasons, "snapshot": baseline.json()}, retryable=True, exit_code=75)
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        write_json(directory / "plan.json", plan)
        receipt["baseline"] = baseline.json()
        if plan["kind"] == "upstream_prepare":
            phase = "source-clone"
            staging_parent = root / ".staging"
            staging_parent.mkdir(mode=0o700, exist_ok=True)
            staging = staging_parent / (job["id"] + "-a" + str(job["attempt"]))
            if os.path.lexists(staging):
                raise FFV2Error("staging_exists", "Source attempt-এর staging directory আছে; রাখা হয়েছে।")
            receipt["staging_source"] = str(staging)
            argv = [str(staging) if item == "<STAGING_CHECKOUT>" else item for item in plan["argv_template"]]
            step = supervised(argv, phase, job, directory, settings, baseline, lock_fd, staging, process_kind="source")
            receipt["steps"].append({"name": phase, "receipt": step})
            git = plan["tools"]["git"]["path"]
            if command([git, "-C", str(staging), "rev-parse", "HEAD"]) != plan["upstream_lock"]["commit"]:
                raise FFV2Error("upstream_commit_mismatch", "Downloaded source locked commit-এর সমান নয়।")
            if command([git, "-C", str(staging), "rev-parse", "refs/tags/" + plan["upstream_lock"]["release_tag"]]) != plan["upstream_lock"]["tag_object"]:
                raise FFV2Error("upstream_tag_mismatch", "Downloaded release tag object lock-এর সঙ্গে মেলেনি।")
            if command([git, "-C", str(staging), "status", "--porcelain", "--untracked-files=normal"]):
                raise FFV2Error("unexpected_source_changes", "Fresh checkout clean পাওয়া যায়নি।")
            for key, value in (("user.name", AUTHOR), ("user.email", EMAIL), ("user.useConfigOnly", "true")):
                command([git, "-C", str(staging), "config", key, value])
            command([git, "-C", str(staging), "switch", "-c", "ffmpeg-v2-main"])
            ensure_running(baseline, root, store, job["id"])
            phase = "source-publish"
            rename_directory_new(staging, Path(plan["spec"]["output"]))
            receipt["source"] = source_state(settings)
        else:
            candidate = Path(plan["spec"]["output"]).parent
            if plan.get("reuse_build_dir"):
                build_dir = Path(plan["reuse_build_dir"])
                prefix = Path(plan["reuse_install_prefix"])
                attempt = build_dir.parent
                if (build_dir.name != "build" or prefix != attempt / "install" or attempt.parent != candidate or
                        not build_dir.is_dir() or build_dir.is_symlink() or prefix.is_symlink()):
                    raise FFV2Error("invalid_build_checkpoint", "Saved build checkpoint path গ্রহণযোগ্য নয়।")
            else:
                attempt = candidate / ("attempt-%03d" % job["attempt"])
                build_dir, prefix = attempt / "build", attempt / "install"
                build_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
            environment = {"LC_ALL": "C", "MAKEFLAGS": "-j" + str(plan.get("build_jobs", 2)), "PKG_CONFIG_PATH": PKG_PATH, "FATE_SAMPLES": "", "SAMPLES": "",
                           "CLANG_MODULE_CACHE_PATH": str(attempt / "module-cache")}
            receipt.update(install_prefix=str(prefix), profile=plan["profile"], fate_scope=plan["fate_scope"],
                           full_fate_verified=False, release_accepted=False)
            listed_tests = None
            for item in plan["steps_template"]:
                phase = "core-" + item["name"]
                argv = [arg.replace("<INSTALL_PREFIX>", str(prefix)) for arg in item["argv"]]
                step = supervised(argv, phase, job, directory, settings, baseline, lock_fd, attempt,
                                  admission_budget=plan["estimates"]["output_budget_bytes"], cwd=build_dir,
                                  process_kind="build", environment=environment)
                receipt["steps"].append({"name": phase, "receipt": step})
                write_json(directory / "progress-receipt.json", receipt)
                if item["name"] == "fate-list":
                    log = build_dir / (phase + "-" + job["id"][:8] + "-a" + str(job["attempt"]) + ".stderr.log")
                    text = log.read_text(errors="replace") if log.is_file() and log.stat().st_size <= 1024 ** 2 else step.get("stdout_tail", "")
                    if step.get("log_truncated"):
                        raise FFV2Error("fate_list_truncated", "পূর্ণ local FATE list capture হয়নি।")
                    listed_tests = [line for line in text.splitlines() if re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.+-]+", line)]
                    if not listed_tests:
                        raise FFV2Error("fate_no_tests", "FATE list-এ test পাওয়া যায়নি; শূন্য test success নয়।")
            phase = "candidate-inspection"
            identities = {}
            expected_version = plan["upstream_lock"]["release_tag"][1:]
            for name in ("ffmpeg", "ffprobe") + (("ffplay",) if "--enable-ffplay" in plan["configure_flags"] else ()):
                binary = prefix / "bin" / name
                if not binary.is_file() or not os.access(binary, os.X_OK):
                    raise FFV2Error("candidate_binary_missing", "Built candidate binary পাওয়া যায়নি।", details={"binary": str(binary)})
                text = command([str(binary), "-hide_banner", "-version"])
                if not candidate_version_matches(text, expected_version):
                    raise FFV2Error("candidate_version_mismatch", "Candidate version locked source-এর সঙ্গে মেলেনি।")
                identities[name] = {"path": str(binary), "sha256": hash_guarded(binary, settings, baseline, store, job["id"]),
                                    "version_output": text, "identity": fingerprint(binary)}
            if source_state(settings) != plan["source"]:
                raise FFV2Error("core_source_changed", "Build চলার সময় core source বদলেছে।")
            ensure_running(baseline, attempt, store, job["id"])
            manifest = {"schema_version": 1, "job_id": job["id"], "profile": plan["profile"],
                        "source": plan["source"], "tools": plan["tools"], "sdk": plan["sdk"],
                        "configure_flags": plan["configure_flags"], "dependencies": plan["dependencies"], "build_jobs": plan.get("build_jobs", 2),
                        "install_prefix": str(prefix), "binaries": identities, "fate_scope": plan["fate_scope"],
                        "fate_list_observed_count": len(listed_tests or []), "full_fate_verified": False,
                        "release_accepted": False, "speedup_measured": False, "feature_parity_verified": False,
                        "receipt": str(directory / "receipt.json")}
            publish_json_new(Path(plan["spec"]["output"]), manifest)
            receipt["candidate"] = manifest
        receipt.update(status="completed", phase=phase)
        store.update(job["id"], "completed", receipt=receipt)
    except (FFV2Error, OSError, ValueError, subprocess.SubprocessError, KeyboardInterrupt) as caught:
        error = caught if isinstance(caught, FFV2Error) else FFV2Error("core_job_error", "Core job সম্পূর্ণ হয়নি; staged source/build রাখা হয়েছে।",
                                                                    details={"type": type(caught).__name__, "message": str(caught)[:1000]})
        state = "waiting_resources" if error.code == "resource_not_admitted" else "cancelled" if error.code == "cancelled" else "interrupted" if error.code == "resource_stopped" else "failed"
        receipt.update(status=state, phase=phase, error=error.payload())
        store.update(job["id"], state, error=error.payload(), receipt=receipt)
    write_json(directory / "receipt.json", receipt)
    return store.get(job["id"], plan=False)


def resume_plan(settings, job_id):
    previous = Store(settings).get(job_id)
    if previous["plan"].get("kind") != "upstream_build" or previous["status"] not in ("failed", "interrupted", "cancelled"):
        raise FFV2Error("build_not_resumable", "Failed/interrupted build checkpoint প্রয়োজন।")
    old = previous["plan"]
    prefix = Path((previous.get("receipt") or {}).get("install_prefix", ""))
    build_dir = prefix.parent / "build"
    if not build_dir.is_dir():
        raise FFV2Error("build_checkpoint_missing", "Compiled build directory পাওয়া যায়নি।")
    plan = build_plan(settings, old["profile"], jobs=old.get("build_jobs", 2))
    for name in ("source", "tools", "configure_flags", "dependencies", "sdk", "spec"):
        if plan[name] != old[name]:
            raise FFV2Error("build_checkpoint_changed", "Checkpoint-এর source/tool/configuration বদলেছে।", details={"field": name})
    plan.pop("plan_id")
    plan.update(parent_job_id=job_id, reuse_build_dir=str(build_dir), reuse_install_prefix=str(prefix))
    plan["steps_template"] = [step for step in plan["steps_template"] if step["name"] not in ("configure", "compile")]
    return finish_plan(plan)


def run(settings, action, *, profile="native", plan_only=False, key=None, jobs=2, job_id=None):
    if action == "status":
        return status(settings)
    plan = resume_plan(settings, job_id) if action == "resume" else prepare_plan(settings) if action == "prepare" else build_plan(settings, profile, jobs=jobs)
    if plan_only:
        return plan
    if action == "build" and Path(plan["spec"]["output"]).is_file():
        check_plan(plan, settings)
        existing = json.loads(Path(plan["spec"]["output"]).read_text())
        for name in ("source", "profile", "tools", "sdk", "configure_flags", "dependencies", "build_jobs"):
            if existing.get(name) != plan[name]:
                raise FFV2Error("candidate_identity_mismatch", "Existing candidate-এর source/tool/configuration মেলেনি।")
        for value in existing["binaries"].values():
            if sha256_file(Path(value["path"])) != value["sha256"]:
                raise FFV2Error("candidate_binary_changed", "Existing candidate binary বদলেছে।")
        return {"status": "already_built", "manifest": plan["spec"]["output"], "candidate": existing,
                "message": "Verified source/configuration/binary cache reused; release/media acceptance পৃথক।"}
    store = Store(settings)
    job = store.enqueue(plan, key)
    if job["status"] in ("queued", "waiting_resources"):
        from .worker import work
        work(settings, job_id=job["id"])
    return store.get(job["id"], plan=False)
