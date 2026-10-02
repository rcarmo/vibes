"""Read-only Windows host counters through documented Win32 APIs.

No subprocesses, WMI, privileges, dependency installs or process enumeration.
CPU is cumulative kernel+user time (kernel includes idle); physical memory and
this process's working set are bytes. Windows commit is NOT reported as swap.
"""

import ctypes as c
import os


class FileTime(c.Structure):
    _fields_ = [("low", c.c_uint32), ("high", c.c_uint32)]

    def ticks(self):
        return (self.high << 32) | self.low


class MemoryStatus(c.Structure):
    _fields_ = [
        ("length", c.c_uint32),
        ("load", c.c_uint32),
        ("total_physical", c.c_uint64),
        ("available_physical", c.c_uint64),
        ("total_page_file", c.c_uint64),
        ("available_page_file", c.c_uint64),
        ("total_virtual", c.c_uint64),
        ("available_virtual", c.c_uint64),
        ("available_extended_virtual", c.c_uint64),
    ]


class ProcessMemory(c.Structure):
    _fields_ = [
        ("size", c.c_uint32),
        ("page_fault_count", c.c_uint32),
        ("peak_working_set", c.c_size_t),
        ("working_set", c.c_size_t),
        ("quota_peak_paged_pool", c.c_size_t),
        ("quota_paged_pool", c.c_size_t),
        ("quota_peak_nonpaged_pool", c.c_size_t),
        ("quota_nonpaged_pool", c.c_size_t),
        ("page_file_usage", c.c_size_t),
        ("peak_page_file_usage", c.c_size_t),
        ("private_usage", c.c_size_t),
    ]


def _windows_api():
    if os.name != "nt":
        return None
    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.GetSystemTimes.argtypes = [c.POINTER(FileTime)] * 3
    kernel.GetSystemTimes.restype = c.c_int
    kernel.GlobalMemoryStatusEx.argtypes = [c.POINTER(MemoryStatus)]
    kernel.GlobalMemoryStatusEx.restype = c.c_int
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = c.c_void_p
    kernel.K32GetProcessMemoryInfo.argtypes = [
        c.c_void_p,
        c.POINTER(ProcessMemory),
        c.c_uint32,
    ]
    kernel.K32GetProcessMemoryInfo.restype = c.c_int
    return kernel


def read_windows(api=None):
    """Return only counters that succeeded. Missing counters remain unavailable."""
    try:
        api = api if api is not None else _windows_api()
    except (OSError, AttributeError):
        return {}
    if api is None:
        return {}
    result = {}
    idle, kernel, user = FileTime(), FileTime(), FileTime()
    try:
        if api.GetSystemTimes(c.byref(idle), c.byref(kernel), c.byref(user)):
            total, inactive = kernel.ticks() + user.ticks(), idle.ticks()
            if total > 0 and 0 <= inactive <= total:
                result["cpu_ticks"] = (total, inactive)
    except OSError:
        pass
    memory = MemoryStatus()
    memory.length = c.sizeof(memory)
    try:
        if api.GlobalMemoryStatusEx(c.byref(memory)):
            total, available = memory.total_physical, memory.available_physical
            if total > 0 and 0 <= available <= total:
                used = total - available
                result.update(
                    ram_total_bytes=total,
                    ram_used_bytes=used,
                    ram_percent=100.0 * used / total,
                )
    except OSError:
        pass
    process = ProcessMemory()
    process.size = c.sizeof(process)
    try:
        if api.K32GetProcessMemoryInfo(
            api.GetCurrentProcess(), c.byref(process), c.sizeof(process)
        ):
            result["process_rss_bytes"] = process.working_set
    except OSError:
        pass
    return result
