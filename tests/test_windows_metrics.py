"""Win32 metrics decoding with injected API and one opt-in-by-platform live check."""

import ctypes as c
import os

import pytest
from vibes.windows_metrics import FileTime, MemoryStatus, ProcessMemory, read_windows
from vibes.system_metrics import SystemMetrics


class API:
    def GetSystemTimes(self, idle, kernel, user):
        c.cast(idle, c.POINTER(FileTime)).contents.low = 60
        c.cast(kernel, c.POINTER(FileTime)).contents.low = 80
        c.cast(user, c.POINTER(FileTime)).contents.low = 20
        return True

    def GlobalMemoryStatusEx(self, value):
        memory = c.cast(value, c.POINTER(MemoryStatus)).contents
        assert memory.length == c.sizeof(MemoryStatus)
        memory.total_physical = 16 * 1024**3
        memory.available_physical = 4 * 1024**3
        return True

    def GetCurrentProcess(self):
        return 42

    def K32GetProcessMemoryInfo(self, handle, value, size):
        assert handle == 42 and size == c.sizeof(ProcessMemory)
        c.cast(value, c.POINTER(ProcessMemory)).contents.working_set = 128 * 1024**2
        return True


def test_windows_counters_and_byte_units():
    sample = read_windows(API())
    assert sample["cpu_ticks"] == (100, 60)  # idle already included in kernel time
    assert sample["ram_percent"] == 75
    assert sample["ram_total_bytes"] == 16 * 1024**3
    assert sample["ram_used_bytes"] == 12 * 1024**3
    assert sample["process_rss_bytes"] == 128 * 1024**2
    assert "swap_percent" not in sample and "vram_percent" not in sample
    assert FileTime(3, 2).ticks() == (2 << 32) + 3
    assert c.sizeof(MemoryStatus) == 64


def test_windows_failed_apis_not_fictitious_zeroes():
    class Failed(API):
        def GetSystemTimes(self, *args):
            return False

        def GlobalMemoryStatusEx(self, *args):
            return False

        def K32GetProcessMemoryInfo(self, *args):
            return False

    assert read_windows(Failed()) == {}


def test_partial_failure_keeps_available_memory():
    class Partial(API):
        def GetSystemTimes(self, *args):
            raise OSError("unavailable")

    sample = read_windows(Partial())
    assert "cpu_ticks" not in sample and sample["ram_percent"] == 75


@pytest.mark.asyncio
async def test_windows_reader_selection_and_delta(monkeypatch):
    import vibes.windows_metrics as windows

    tick = [0]
    sample = {"cpu_ticks": (100, 60), "ram_percent": 75, "process_rss_bytes": 1024}
    monkeypatch.setattr(windows, "read_windows", lambda: dict(sample))
    meter = SystemMetrics(system="windows", clock=lambda: tick[0])
    assert (await meter.get())["available"]
    tick[0] = 2
    sample["cpu_ticks"] = (200, 100)
    result = await meter.get()
    assert result["cpu_percent"] == 60
    assert result["ram_percent"] == 75
    assert result["swap_percent"] is None and result["vram_percent"] is None


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows API smoke")
def test_real_windows_memory_and_cpu_counters():
    sample = read_windows()
    assert sample["cpu_ticks"][0] > 0
    assert 0 <= sample["ram_percent"] <= 100
    assert 0 < sample["ram_used_bytes"] <= sample["ram_total_bytes"]
    assert sample["process_rss_bytes"] > 0
