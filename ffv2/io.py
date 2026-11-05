from __future__ import annotations

import hashlib
import ctypes
import json
import os
import platform
import selectors
import signal
import subprocess
import time
import uuid
from pathlib import Path

from .config import check_mounts, within
from .errors import FFV2Error


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".pending")
    with temporary.open("w", encoding="utf-8") as target:
        os.chmod(temporary, 0o600)
        json.dump(value, target, ensure_ascii=False, indent=2, allow_nan=False)
        target.write("\n")
        target.flush()
        os.fsync(target.fileno())
    os.replace(temporary, path)


def publish_json_new(path, value):
    """নতুন artifact atomically প্রকাশ; existing নাম বা rollback file বদলায় না।"""
    path = Path(path)
    temporary = path.with_name("." + path.name + "-" + uuid.uuid4().hex + ".staging")
    write_json(temporary, value)
    os.link(temporary, path, follow_symlinks=False)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return temporary


def rename_directory_new(source, destination):
    if platform.system() != "Darwin":
        raise FFV2Error("exclusive_rename_unsupported", "Source publish-এর জন্য macOS exclusive rename প্রয়োজন।")
    library = ctypes.CDLL(None, use_errno=True)
    library.renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    library.renamex_np.restype = ctypes.c_int
    # macOS SDK sys/stdio.h: RENAME_EXCL = 0x4। Existing destination থাকলে replace হয় না।
    if library.renamex_np(os.fsencode(source), os.fsencode(destination), 4):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(destination))


def fingerprint(path):
    stat = path.stat()
    return {"device": stat.st_dev, "inode": stat.st_ino, "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns}


def sha256_file(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def input_path(raw, settings, *, restricted=False):
    if not isinstance(raw, str) or not raw or any(x in raw for x in ("\0", "\n", "\r")) or "://" in raw:
        raise FFV2Error("invalid_input", "একটি স্থানীয় regular file-এর path দিন।")
    path = Path(raw).expanduser().absolute()
    check_mounts(path)
    path = path.resolve(strict=True)
    if any(character in str(path) for character in ("\0", "\n", "\r")):
        raise FFV2Error("invalid_input", "Resolved input path-এ control character গ্রহণযোগ্য নয়।")
    check_mounts(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise FFV2Error("invalid_input", "Input regular ও nonempty file হতে হবে।")
    if restricted and not any(within(path, root) for root in settings.input_roots):
        raise FFV2Error("input_path_denied", "এই MCP session-এর অনুমোদিত input root-এর বাইরে।")
    return path


def output_path(raw, source, settings, *, allow_existing=False):
    if not isinstance(raw, str) or not raw or any(x in raw for x in ("\0", "\n", "\r")):
        raise FFV2Error("invalid_output", "Output-এর স্থানীয় path দিন।")
    path = Path(raw).expanduser().absolute()
    check_mounts(path)
    if not path.parent.is_dir():
        raise FFV2Error("output_directory_missing", "Output directory আগে তৈরি করুন।")
    path = path.parent.resolve() / path.name
    if any(character in str(path) for character in ("\0", "\n", "\r")):
        raise FFV2Error("invalid_output", "Resolved output path-এ control character গ্রহণযোগ্য নয়।")
    check_mounts(path)
    if not any(within(path, root.resolve()) for root in settings.output_roots):
        raise FFV2Error("output_path_denied", "Output project বা mounted NexaWork/Work-এর মধ্যে থাকতে হবে।")
    if path == source or (path.exists() and os.path.samefile(path, source)):
        raise FFV2Error("source_overwrite", "Source-এর ওপর output লেখা যাবে না।")
    if path.is_symlink() or (os.path.lexists(path) and not allow_existing):
        raise FFV2Error("output_exists", "Output আগে থেকেই আছে; নতুন path দিন।")
    return path


def terminate(process):
    if process.poll() is not None:
        return
    def signal_owned(number):
        try:
            os.killpg(process.pid, number)
        except ProcessLookupError:
            pass
        except PermissionError:
            # macOS can reject a group signal while a short child exits.
            # Popen guards direct signalling against an already-reaped PID.
            if process.poll() is None:
                process.send_signal(number)
    signal_owned(signal.SIGTERM)
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        signal_owned(signal.SIGKILL)
        process.wait(timeout=3)


def capture(argv, *, timeout=10, limit=2 * 1024 * 1024, memory_limit=256 * 1024 ** 2, env=None):
    """ছোট metadata/capability command; stdout ও stderr একসঙ্গে drain হয়।"""
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True, env=env)
    selector = selectors.DefaultSelector()
    chunks = {"stdout": bytearray(), "stderr": bytearray()}
    for pipe, name in ((process.stdout, "stdout"), (process.stderr, "stderr")):
        selector.register(pipe, selectors.EVENT_READ, name)
    start = time.monotonic()
    next_memory_check = 0.0
    try:
        while selector.get_map():
            if time.monotonic() - start > timeout:
                raise FFV2Error("probe_timeout", "Metadata command সময়সীমা পেরিয়েছে।", retryable=True)
            if time.monotonic() >= next_memory_check and process.poll() is None:
                from .resources import process_memory
                memory, method = process_memory(process.pid)
                if memory > memory_limit:
                    raise FFV2Error("probe_memory_limit", "Metadata process memory budget অতিক্রম করেছে।",
                                    details={"bytes": memory, "measurement": method})
                if method != "physical_footprint":
                    # A short helper can exit between poll and proc_pidinfo.
                    # Confirm/reap that exit; an unmeasurable live helper still stops.
                    try:
                        process.wait(timeout=0.02)
                    except subprocess.TimeoutExpired as error:
                        raise FFV2Error("probe_memory_unavailable", "Metadata process-এর physical footprint নির্ভরযোগ্যভাবে পাওয়া যায়নি।") from error
                next_memory_check = time.monotonic() + 0.25
            for key, _ in selector.select(0.1):
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    selector.unregister(key.fileobj)
                else:
                    chunks[key.data].extend(data)
                    if sum(map(len, chunks.values())) > limit:
                        raise FFV2Error("probe_output_limit", "Metadata output নির্ধারিত সীমার বেশি।")
        process.wait(timeout=1)
    finally:
        try:
            terminate(process)
        finally:
            selector.close()
            process.stdout.close()
            process.stderr.close()
    return process.returncode, *(chunks[k].decode("utf-8", "replace") for k in ("stdout", "stderr"))
