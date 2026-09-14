import asyncio
from unittest.mock import AsyncMock

import pytest
from aiohttp import web

from vibes.system_metrics import SystemMetrics, read_linux
from vibes.routes.system_metrics import setup_routes
from vibes.middleware import create_auth_middleware


@pytest.mark.asyncio
async def test_sampler_delta_cache_bounded_history_and_reset():
    tick = [0]
    cpu = [100, 60]
    calls = []
    def reader():
        calls.append(True)
        return {'cpu_ticks': tuple(cpu), 'ram_percent': 25, 'process_rss_bytes': 2048}
    meter = SystemMetrics(reader=reader, clock=lambda: tick[0], system='linux')
    first = await meter.get()
    assert first['cpu_percent'] is None
    assert first['vram_percent'] is None
    assert len(await asyncio.gather(*(meter.get() for _ in range(10)))) == 10
    assert len(calls) == 1
    tick[0] = 2
    cpu[:] = [200, 80]
    assert (await meter.get())['cpu_percent'] == 80
    for _ in range(40):
        tick[0] += 2
        cpu[0] += 100
        cpu[1] += 50
        result = await meter.get()
    assert len(result['cpu_series']) == 30
    assert result['cpu_percent'] == 50
    tick[0] += 2
    cpu[:] = [1, 1]
    assert (await meter.get())['cpu_percent'] is None


def test_linux_counters_and_drm_gpu(tmp_path):
    proc = tmp_path / 'proc'
    (proc / 'self').mkdir(parents=True)
    # guest time must not be double-counted, iowait is idle.
    (proc / 'stat').write_text('cpu 10 5 10 50 5 10 5 5 10 5\n')
    (proc / 'meminfo').write_text('MemTotal: 1000 kB\nMemAvailable: 750 kB\nBuffers: 20 kB\nCached: 100 kB\nSReclaimable: 10 kB\nShmem: 5 kB\nSwapTotal: 500 kB\nSwapFree: 100 kB\n')
    (proc / 'self/status').write_text('Name: python\nVmRSS: 200 kB\n')
    drm = tmp_path / 'drm'
    (drm / 'card0/device').mkdir(parents=True)
    (drm / 'card0/device/mem_info_vram_total').write_text('1000')
    (drm / 'card0/device/mem_info_vram_used').write_text('250')
    sample = read_linux(proc, drm)
    assert sample['cpu_ticks'] == (100, 55)
    assert sample['ram_percent'] == 25
    assert sample['swap_percent'] == 80
    assert sample['buffer_cache_bytes'] == 125 * 1024
    assert sample['process_rss_bytes'] == 200 * 1024
    assert sample['vram_percent'] == 25
    assert sample['gpu_provider'] == 'Linux DRM'


def test_missing_or_corrupt_metrics_not_zero(tmp_path):
    (tmp_path / 'stat').write_text('broken counters')
    (tmp_path / 'meminfo').write_text('MemTotal: 1000 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n')
    data = read_linux(tmp_path, tmp_path / 'missing')
    assert data.get('cpu_ticks') is None
    assert data['ram_percent'] is None
    assert data['swap_percent'] is None
    assert data.get('vram_percent') is None


@pytest.mark.asyncio
async def test_unsupported_platform_returns_unavailable():
    meter = SystemMetrics(reader=lambda: pytest.fail('must not read Linux proc'), system='darwin')
    result = await meter.get()
    assert not result['available']
    assert result['cpu_percent'] is None
    assert result['ram_percent'] is None


@pytest.mark.asyncio
async def test_metrics_endpoint_cache_and_auth(aiohttp_client):
    app = web.Application()
    setup_routes(app)
    client = await aiohttp_client(app)
    response = await client.get('/system/metrics')
    assert response.status == 200
    assert response.headers['Cache-Control'] == 'no-store'
    data = await response.json()
    assert data['scope'] == 'server-os'
    assert len(data['cpu_series']) <= 30
    denied = web.Application(middlewares=[create_auth_middleware(authenticate=AsyncMock(return_value=web.json_response({'error': 'Unauthorized'}, status=401)))])
    setup_routes(denied)
    denied_client = await aiohttp_client(denied)
    assert (await denied_client.get('/system/metrics')).status == 401


@pytest.mark.asyncio
async def test_app_registers_metrics_with_normal_middlewares(aiohttp_client):
    from vibes.app import create_app
    app = create_app()
    app.on_startup.clear()
    app.on_cleanup.clear()
    client = await aiohttp_client(app)
    assert (await client.get('/system/metrics')).status == 200


@pytest.mark.asyncio
async def test_resume_after_long_gap_does_not_claim_instantaneous_cpu():
    now = [0]
    cpu = [100, 10]
    meter = SystemMetrics(reader=lambda: {'cpu_ticks': tuple(cpu)}, clock=lambda: now[0], system='linux')
    await meter.get()
    now[0] = 60
    cpu[:] = [1000, 100]
    assert (await meter.get())['cpu_percent'] is None
    now[0] = 62
    cpu[:] = [1100, 150]
    assert (await meter.get())['cpu_percent'] == 50
