"""Bounded detached buffering and shutdown while VNC output is stalled."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from vibes.routes import vnc


@pytest.mark.asyncio
async def test_detached_forwarder_holds_one_chunk_and_cleanup_does_not_read_more():
    reader = AsyncMock()
    reader.read.return_value = b'x' * vnc.MAX_FRAME
    writer = AsyncMock()
    writer.close = Mock()
    tunnel = vnc._Tunnel('owner', reader, writer)
    adapter = vnc.VNCAdapter(enabled=True)
    adapter.tunnels['owner'] = tunnel
    tunnel.forwarder = asyncio.create_task(adapter._forward(tunnel))
    try:
        for _ in range(10):
            await asyncio.sleep(0)
        reader.read.assert_awaited_once_with(vnc.MAX_FRAME)
        assert not tunnel.attached.is_set()
        await asyncio.wait_for(adapter.cleanup(None), .5)
        assert tunnel.forwarder.done() and not adapter.tunnels
        writer.close.assert_called_once()
        reader.read.assert_awaited_once()
    finally:
        tunnel.forwarder.cancel()
        await asyncio.gather(tunnel.forwarder, return_exceptions=True)


@pytest.mark.asyncio
async def test_cleanup_cancels_stalled_send_before_waiting_for_tunnel_lock(monkeypatch):
    entered, cancelled = asyncio.Event(), asyncio.Event()
    reader = AsyncMock()
    reader.read.return_value = b'bounded-frame'
    writer = AsyncMock()
    writer.close = Mock()
    websocket = AsyncMock()
    websocket.closed = False

    async def stalled(data):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    websocket.send_bytes = stalled
    monkeypatch.setattr(vnc, 'WRITE_TIMEOUT', 60)
    tunnel = vnc._Tunnel('owner', reader, writer)
    tunnel.socket = websocket
    tunnel.attached.set()
    adapter = vnc.VNCAdapter(enabled=True)
    adapter.tunnels['owner'] = tunnel
    tunnel.forwarder = asyncio.create_task(adapter._forward(tunnel))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.wait_for(adapter.cleanup(None), .5)
        assert cancelled.is_set() and tunnel.forwarder.done() and not adapter.tunnels
        writer.close.assert_called_once()
        websocket.close.assert_awaited_once()
    finally:
        tunnel.forwarder.cancel()
        await asyncio.gather(tunnel.forwarder, return_exceptions=True)
