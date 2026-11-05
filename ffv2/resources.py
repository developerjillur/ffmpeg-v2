from __future__ import annotations

import ctypes
import errno
import os
import platform
import re
import shutil
import struct
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import GIB, check_mounts
from .errors import FFV2Error


@dataclass(frozen=True)
class Snapshot:
    pressure: str
    headroom_bytes: int
    swap_bytes: int
    boot_free_bytes: int
    boot_used_bytes: int
    output_free_bytes: int
    backend: str = "darwin_cli"

    def json(self):
        return asdict(self)


def configured_boot_limit():
    raw = os.environ.get('FFV2_BOOT_USED_LIMIT_BYTES', '')
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError as error:
        raise FFV2Error('resource_policy_invalid', 'FFV2_BOOT_USED_LIMIT_BYTES requires a positive byte count.') from error
    if value <= 0:
        raise FFV2Error('resource_policy_invalid', 'FFV2_BOOT_USED_LIMIT_BYTES requires a positive byte count.')
    return value


@dataclass(frozen=True)
class Policy:
    ignore_system_memory: bool = field(default_factory=lambda: os.environ.get("FFV2_IGNORE_SYSTEM_MEMORY") == "1")
    admission_headroom: int = 10 * GIB
    running_headroom: int = 8 * GIB
    admission_boot_free: int = 20 * GIB
    running_boot_free: int = 15 * GIB
    swap_growth_limit: int = GIB
    job_memory_limit: int = 12 * GIB
    boot_used_limit: int | None = field(default_factory=configured_boot_limit)
    output_reserve: int = 15 * GIB

    def admission(self, sample, estimated_memory=0, output_budget=0):
        reasons = []
        if not self.ignore_system_memory:
            if sample.pressure != "normal":
                reasons.append("memory_pressure_" + sample.pressure)
            if sample.headroom_bytes < max(self.admission_headroom, estimated_memory + self.running_headroom):
                reasons.append("physical_headroom")
        if estimated_memory > self.job_memory_limit:
            reasons.append("estimated_job_memory")
        if sample.boot_free_bytes < self.admission_boot_free:
            reasons.append("boot_disk_free")
        if self.boot_used_limit is not None and sample.boot_used_bytes >= self.boot_used_limit:
            reasons.append("boot_disk_used_limit")
        if sample.output_free_bytes < output_budget + self.output_reserve:
            reasons.append("output_disk_budget")
        return reasons

    def running(self, sample, baseline, job_memory=0, output_bytes=0, output_budget=None):
        reasons = []
        if not self.ignore_system_memory:
            if sample.pressure != "normal":
                reasons.append("memory_pressure_" + sample.pressure)
            if sample.headroom_bytes < self.running_headroom:
                reasons.append("physical_headroom_below_8gib")
            if sample.swap_bytes - baseline.swap_bytes > self.swap_growth_limit:
                reasons.append("swap_growth_over_1gib")
        if sample.boot_free_bytes < self.running_boot_free:
            reasons.append("boot_disk_free_below_15gib")
        if self.boot_used_limit is not None and sample.boot_used_bytes >= self.boot_used_limit:
            reasons.append("boot_disk_used_limit")
        if sample.output_free_bytes < self.output_reserve:
            reasons.append("output_disk_reserve")
        if job_memory > self.job_memory_limit:
            reasons.append("job_memory_over_12gib")
        if output_budget is not None and output_bytes > output_budget:
            reasons.append("output_size_budget")
        return reasons


def parse_darwin(sysctl, vmstat, boot, output):
    values = dict(re.findall(r"^([^:\n]+):\s*(.+)$", sysctl, re.M))
    page_size = int(re.search(r"page size of (\d+)", vmstat).group(1))
    pages = {key.strip(): int(value) for key, value in re.findall(r"([^\n:]+):\s*(\d+)\.", vmstat)}
    used = sum(pages[key] for key in ("Pages active", "Pages wired down", "Pages occupied by compressor")) * page_size
    pressure = {1: "normal", 2: "warning", 4: "critical"}.get(int(values["kern.memorystatus_vm_pressure_level"]), "unknown")
    swap = re.search(r"used = ([\d.]+)([MG])", values["vm.swapusage"])
    swap_bytes = int(float(swap.group(1)) * (1024 ** (2 if swap.group(2) == "M" else 3)))
    return Snapshot(pressure, max(0, int(values["hw.memsize"]) - used), swap_bytes,
                    boot.free, boot.used, output.free)


def snapshot(destination):
    check_mounts(Path(destination).absolute())
    boot = shutil.disk_usage("/")
    output = shutil.disk_usage(destination)
    if platform.system() != "Darwin":
        raise FFV2Error("resource_platform_unsupported", "এই release-এর live resource guard macOS-এর জন্য।", exit_code=75)
    backend = os.environ.get("FFV2_RESOURCE_BACKEND", "auto")
    if backend not in ("auto", "native", "cli"):
        raise FFV2Error("resource_backend_invalid", "Resource backend auto, native অথবা cli দিন।")
    if backend != "cli":
        try:
            from .darwin import memory_snapshot
            memory = memory_snapshot()
            return Snapshot(**memory, boot_free_bytes=boot.free, boot_used_bytes=boot.used,
                            output_free_bytes=output.free, backend="darwin_native")
        except (OSError, ValueError, AttributeError) as error:
            if backend == "native":
                raise FFV2Error("resource_snapshot_failed", "Native resource API পাওয়া যায়নি।", exit_code=75) from error
    try:
        sc = subprocess.check_output(["/usr/sbin/sysctl", "hw.memsize", "kern.memorystatus_vm_pressure_level", "vm.swapusage"],
                                     text=True, stderr=subprocess.PIPE, timeout=3)
        vm = subprocess.check_output(["/usr/bin/vm_stat"], text=True, stderr=subprocess.PIPE, timeout=3)
        return parse_darwin(sc, vm, boot, output)
    except (ValueError, KeyError, AttributeError, OSError, subprocess.SubprocessError) as error:
        raise FFV2Error("resource_snapshot_failed", "Resource snapshot নির্ভরযোগ্যভাবে পাওয়া যায়নি।",
                        details={"type": type(error).__name__}, exit_code=75) from error


def process_memory(root_pid, additional=()):
    if platform.system() == "Darwin" and os.environ.get("FFV2_RESOURCE_BACKEND", "auto") != "cli":
        try:
            from .darwin import process_tree_memory
            return process_tree_memory(root_pid, additional)
        except (OSError, ValueError, AttributeError):
            if os.environ.get("FFV2_RESOURCE_BACKEND") == "native":
                return 0, "unavailable"
    return process_memory_cli(root_pid, additional)


def process_memory_cli(root_pid, additional=()):
    """Child tree ও controller-এর physical footprint; macOS-এ compressed pages-সহ।"""
    raw = subprocess.check_output(["/bin/ps", "-axo", "pid=,ppid=,rss="], text=True, timeout=3)
    rows = {}
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) == 3:
            pid, parent, rss = map(int, fields)
            rows[pid] = (parent, rss * 1024)
    included = {root_pid}
    while True:
        found = {pid for pid, (parent, _) in rows.items() if parent in included}
        if found <= included:
            break
        included |= found
    included |= set(additional)
    total = 0
    method = "physical_footprint"
    library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True) if platform.system() == "Darwin" else None
    if library:
        library.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
        library.proc_pid_rusage.restype = ctypes.c_int
    for pid in included:
        if pid not in rows:
            continue
        buffer = ctypes.create_string_buffer(4096)
        if library and library.proc_pid_rusage(pid, 2, ctypes.byref(buffer)) == 0:
            total += struct.unpack_from("Q", buffer.raw, 72)[0]
        else:
            if library and ctypes.get_errno() == errno.ESRCH:
                continue  # ps-এ দেখা স্বল্পস্থায়ী child ইতিমধ্যে শেষ হয়েছে।
            method = "rss_fallback"
            total += rows[pid][1]
    return total, method
