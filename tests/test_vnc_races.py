"""Deterministic concurrent upgrade and shutdown/connect races."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from vibes.routes.vnc import VNCAdapter


@pytest.mark.asyncio
async def test_concurrent_upgrade_creates_only_one_upstream_and_shutdown_tracks_open(monkeypatch):
    writers = []
    async def echo(reader, writer):
        writers.append(writer)
        try:
            while data := await reader.read(1024):
                writer.write(data)
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
    server = await asyncio.start_server(echo, '127.0.0.1', 0)
    adapter = VNCAdapter(enabled=True, port=server.sockets[0].getsockname()[1])
    original_open = adapter._open_tunnel
    entered, release = asyncio.Event(), asyncio.Event()
    async def gated(owner):
        entered.set()
        await release.wait()
        return await original_open(owner)
    monkeypatch.setattr(adapter, '_open_tunnel', gated)
    app = web.Application()
    app.router.add_get('/vnc/session', adapter.info)
    app.router.add_get('/vnc/ws', adapter.websocket)
    app.on_shutdown.append(adapter.cleanup)
    try:
        async with TestClient(TestServer(app)) as client:
            await client.get('/vnc/session')
            headers = {'Origin': str(client.make_url('/')).rstrip('/')}
            first = await client.ws_connect('/vnc/ws', headers=headers)
            await asyncio.wait_for(entered.wait(), 1)
            from aiohttp import WSServerHandshakeError
            with pytest.raises(WSServerHandshakeError):
                await client.ws_connect('/vnc/ws', headers=headers)
            release.set()
            for _ in range(100):
                if adapter.tunnels and not adapter.opening:
                    break
                await asyncio.sleep(.01)
            assert len(writers) == 1 and len(adapter.tunnels) == 1
            await first.send_bytes(b'one')
            assert (await asyncio.wait_for(first.receive(), 1)).data == b'one'
            await first.close()
    finally:
        release.set()
        server.close()
        await server.wait_closed()
        for writer in writers:
            writer.close()
            await writer.wait_closed()


@pytest.mark.asyncio
async def test_shutdown_cancels_pending_open_and_closes_late_connection(monkeypatch):
    adapter = VNCAdapter(enabled=True)
    entered = asyncio.Event()
    cancelled = asyncio.Event()
    writer = AsyncMock()
    writer.close = lambda: cancelled.set()
    async def late_connect(*args, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # Simulate the OS connection completing as its awaiter is cancelled.
            return AsyncMock(), writer
    monkeypatch.setattr(asyncio, 'open_connection', late_connect)
    app = web.Application()
    app.router.add_get('/vnc/session', adapter.info)
    app.router.add_get('/vnc/ws', adapter.websocket)
    app.on_shutdown.append(adapter.cleanup)
    async with TestClient(TestServer(app)) as client:
        await client.get('/vnc/session')
        headers = {'Origin': str(client.make_url('/')).rstrip('/')}
        socket = await client.ws_connect('/vnc/ws', headers=headers)
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.wait_for(adapter.cleanup(app), 2)
        assert adapter.closing
        assert not adapter.tunnels and not adapter.opening and not adapter.opening_tasks
        assert cancelled.is_set()
        await socket.close()
