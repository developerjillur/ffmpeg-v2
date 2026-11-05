"""macOS-এর readonly resource API; প্রতি sample-এ helper process লাগে না।"""
from __future__ import annotations

import ctypes as C
import errno
import functools
import os
import struct


class VMStatistics(C.Structure):
    # HOST_VM_INFO64_REV2 prefix; later SDK fields are deliberately not requested.
    _fields_ = ([(name, C.c_uint32) for name in ("free", "active", "inactive", "wired")] +
                [(name, C.c_uint64) for name in ("zero_fill", "reactivations", "pageins", "pageouts", "faults", "cow", "lookups", "hits", "purges")] +
                [("purgeable", C.c_uint32), ("speculative", C.c_uint32)] +
                [(name, C.c_uint64) for name in ("decompressions", "compressions", "swapins", "swapouts")] +
                [(name, C.c_uint32) for name in ("compressor", "throttled", "external", "internal")] +
                [("uncompressed", C.c_uint64), ("swapped", C.c_uint64)])


class SwapUsage(C.Structure):
    _fields_ = [("total", C.c_uint64), ("available", C.c_uint64), ("used", C.c_uint64),
                ("page_size", C.c_uint32), ("encrypted", C.c_uint32)]


@functools.lru_cache(maxsize=1)
def libraries():
    system = C.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    proc = C.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    signatures = (
        (system.sysctlbyname, [C.c_char_p, C.c_void_p, C.POINTER(C.c_size_t), C.c_void_p, C.c_size_t], C.c_int),
        (system.mach_host_self, [], C.c_uint32),
        (system.mach_port_deallocate, [C.c_uint32, C.c_uint32], C.c_int),
        (system.host_statistics64, [C.c_uint32, C.c_int, C.c_void_p, C.POINTER(C.c_uint32)], C.c_int),
        (system.host_page_size, [C.c_uint32, C.POINTER(C.c_uint32)], C.c_int),
        (proc.proc_listchildpids, [C.c_int, C.c_void_p, C.c_int], C.c_int),
        (proc.proc_pid_rusage, [C.c_int, C.c_int, C.c_void_p], C.c_int),
    )
    for function, arguments, result in signatures:
        function.argtypes, function.restype = arguments, result
    return system, proc


def sysctl(name, value_type):
    system, _ = libraries()
    value = value_type()
    size = C.c_size_t(C.sizeof(value))
    if system.sysctlbyname(name.encode(), C.byref(value), C.byref(size), None, 0) != 0:
        raise OSError(C.get_errno(), "sysctlbyname failed: " + name)
    if size.value != C.sizeof(value):
        raise ValueError("Unexpected sysctl ABI size: " + name)
    return value


@functools.lru_cache(maxsize=1)
def cpu_brand():
    system, _ = libraries()
    size = C.c_size_t()
    if system.sysctlbyname(b"machdep.cpu.brand_string", None, C.byref(size), None, 0) or not 1 <= size.value <= 1024:
        return "unknown"
    value = C.create_string_buffer(size.value)
    if system.sysctlbyname(b"machdep.cpu.brand_string", value, C.byref(size), None, 0):
        return "unknown"
    return value.value.decode("utf-8", "replace")


def memory_snapshot():
    system, _ = libraries()
    host = system.mach_host_self()
    task = C.c_uint32.in_dll(system, "mach_task_self_").value
    try:
        pages = VMStatistics()
        count = C.c_uint32(C.sizeof(pages) // C.sizeof(C.c_int32))
        page_size = C.c_uint32()
        if (system.host_page_size(host, C.byref(page_size)) or
                system.host_statistics64(host, 4, C.byref(pages), C.byref(count)) or count.value < 33):
            raise OSError("host VM statistics unavailable")
        total = sysctl("hw.memsize", C.c_uint64).value
        pressure = sysctl("kern.memorystatus_vm_pressure_level", C.c_int32).value
        swap = sysctl("vm.swapusage", SwapUsage).used
        if page_size.value <= 0 or total <= 0:
            raise ValueError("Invalid host VM values")
        used = (pages.active + pages.wired + pages.compressor) * page_size.value
        return {"pressure": {1:"normal", 2:"warning", 4:"critical"}.get(pressure, "unknown"),
                "headroom_bytes": max(0, total - used), "swap_bytes": swap}
    finally:
        system.mach_port_deallocate(task, host)


def process_info(pid):
    _, proc = libraries()
    buffer = C.create_string_buffer(4096)
    C.set_errno(0)
    if proc.proc_pid_rusage(pid, 2, C.byref(buffer)):
        code = C.get_errno()
        if code in (errno.ESRCH, errno.ENOENT):
            return None
        raise OSError(code, "Process footprint unavailable")
    footprint, started, exited = struct.unpack_from("QQQ", buffer.raw, 72)
    return {"physical_footprint_bytes": footprint, "start_abstime": started, "exit_abstime": exited}


def children(pid):
    _, proc = libraries()
    buffer = (C.c_int32 * 4096)()
    C.set_errno(0)
    count = proc.proc_listchildpids(pid, buffer, C.sizeof(buffer))
    error = C.get_errno()
    if count < 0 or (count == 0 and error not in (0, errno.ESRCH, errno.ENOENT)):
        raise OSError(error, "Child process enumeration failed")
    # proc_listchildpids returns a PID count, unlike proc_listpids' byte count.
    if count >= len(buffer):
        raise ValueError("Child process enumeration exceeded its bound")
    return {int(pid) for pid in buffer[:count] if pid > 0}


def process_tree_memory(root_pid, additional=()):
    included, pending = {root_pid}, [root_pid]
    while pending:
        found = children(pending.pop()) - included
        if len(included) + len(found) > 8192:
            raise ValueError("Process tree exceeds its bound")
        included.update(found)
        pending.extend(found)
    included.update(additional)
    total = 0
    for pid in included:
        record = process_info(pid)
        if record and not record["exit_abstime"]:
            total += record["physical_footprint_bytes"]
    return total, "physical_footprint"
