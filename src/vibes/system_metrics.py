"""Bounded, read-only Linux host metrics, shared between browser clients.

/proc describes the server's OS view, not cgroup limits or an inference endpoint.
No commands are spawned. Optional VRAM comes from kernel DRM counters only.
"""
import asyncio
from collections import deque
from pathlib import Path
import platform
import socket
import time

INTERVAL_MS = 2000
HISTORY_POINTS = 30


def read_fields(path):
    fields = {}
    for line in path.read_text().splitlines():
        name, _, value = line.partition(':')
        parts = value.split()
        if parts and parts[0].isdigit():
            fields[name] = int(parts[0]) * (1024 if len(parts) > 1 and parts[1] == 'kB' else 1)
    return fields


def percent(used, total):
    return min(100.0, max(0.0, 100.0 * used / total)) if total and used is not None else None


def read_linux(proc=Path('/proc'), drm=Path('/sys/class/drm')):
    result = {}
    try:
        line = proc.joinpath('stat').read_text().splitlines()[0].split()
        if line[0] == 'cpu' and len(line) >= 5:
            counters = [int(value) for value in line[1:9]]  # guest is already in user/nice
            result['cpu_ticks'] = (sum(counters), counters[3] + (counters[4] if len(counters) > 4 else 0))
    except (OSError, ValueError, IndexError):
        pass
    try:
        memory = read_fields(proc / 'meminfo')
        total, available = memory.get('MemTotal'), memory.get('MemAvailable')
        result['ram_total_bytes'] = total
        result['ram_used_bytes'] = max(0, total - available) if total and available is not None else None
        result['ram_percent'] = percent(result['ram_used_bytes'], total)
        swap, free = memory.get('SwapTotal'), memory.get('SwapFree')
        result['swap_total_bytes'] = swap
        result['swap_used_bytes'] = max(0, swap - free) if swap is not None and free is not None else None
        result['swap_percent'] = percent(result['swap_used_bytes'], swap)
        if 'Cached' in memory:
            result['buffer_cache_bytes'] = max(0, memory.get('Buffers', 0) + memory['Cached']
                                                + memory.get('SReclaimable', 0) - memory.get('Shmem', 0))
    except (OSError, ValueError):
        pass
    try:
        result['process_rss_bytes'] = read_fields(proc / 'self/status').get('VmRSS')
    except (OSError, ValueError):
        pass
    try:
        # Card entries only (not connector aliases); sum complete kernel counters.
        total, used = 0, 0
        paths = (path for path in sorted(drm.glob('card[0-9]*/device/mem_info_vram_total'))
                 if path.parent.parent.name.removeprefix('card').isdigit())
        for index, path in enumerate(paths):
            if index >= 16:
                break
            try:
                capacity = int(path.read_text().strip())
                usage = int(path.with_name('mem_info_vram_used').read_text().strip())
                if capacity > 0 and 0 <= usage <= capacity:
                    total += capacity
                    used += usage
            except (OSError, ValueError):
                continue
        if total:
            result.update(vram_total_bytes=total, vram_used_bytes=used, vram_percent=percent(used, total), gpu_provider='Linux DRM')
    except OSError:
        pass
    return result


class SystemMetrics:
    """Sample at most once per interval, without blocking aiohttp or using Pi RPC."""
    SERIES = {'cpu_percent': 'cpu_series', 'ram_percent': 'ram_series', 'swap_percent': 'swap_series',
              'buffer_cache_bytes': 'buffer_cache_series_bytes', 'process_rss_bytes': 'process_rss_series_bytes',
              'vram_percent': 'vram_series'}

    def __init__(self, reader=read_linux, clock=time.monotonic, system=None):
        self.reader, self.clock = reader, clock
        self.platform = system or platform.system().lower()
        self.host = socket.gethostname()
        self.lock = asyncio.Lock()
        self.previous_cpu = None
        self.last_sample = None
        self.snapshot = None
        self.history = {key: deque(maxlen=HISTORY_POINTS) for key in self.SERIES.values()}

    async def get(self):
        async with self.lock:
            now = self.clock()
            if self.snapshot is not None and now - self.last_sample < INTERVAL_MS / 1000:
                return self.snapshot
            try:
                sample = await asyncio.to_thread(self.reader) if self.platform == 'linux' else {}
            except (OSError, ValueError):
                sample = {}
            current = sample.pop('cpu_ticks', None)
            cpu = None
            if current and self.previous_cpu and now - self.last_sample <= 10:
                total = current[0] - self.previous_cpu[0]
                idle = current[1] - self.previous_cpu[1]
                if total > 0 and 0 <= idle <= total:
                    cpu = percent(total - idle, total)
            self.previous_cpu = current
            sample['cpu_percent'] = cpu
            for field, series in self.SERIES.items():
                # Keep gaps, not fictitious zeroes, for unsupported/failed samples.
                self.history[series].append(sample.get(field))
            self.last_sample = now
            self.snapshot = {
                'hostname': self.host, 'platform': self.platform, 'scope': 'server-os',
                'sampled_at': int(time.time() * 1000), 'sample_interval_ms': INTERVAL_MS,
                'available': any(sample.get(key) is not None for key in self.SERIES),
                **{key: sample.get(key) for key in self.SERIES}, **sample,
                **{key: list(values) for key, values in self.history.items()},
            }
            return self.snapshot
