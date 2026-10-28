"""VNC transport safety tests: fixed endpoints and no uncertain byte replay."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from vibes.routes.vnc import VNCAdapter, _Tunnel, MAX_FRAME


@pytest.mark.parametrize('host,port,configured', [
    ('127.0.0.1', 5901, True), ('localhost', 5901, True), ('::1', 5901, True),
    ('192.168.1.1', 5901, False), ('example.com', 5901, False), ('0.0.0.0', 5901, False),
    ('127.0.0.1', 0, False), ('127.0.0.1', 65536, False),
])
def test_target_is_numeric_loopback_only(host, port, configured):
    adapter = VNCAdapter(enabled=True, host=host, port=port)
    assert adapter.configured is configured
    assert adapter.enabled is configured


@pytest.mark.asyncio
async def test_uncertain_websocket_output_closes_tcp_without_replay():
    reader = AsyncMock()
    reader.read.return_value = b'RFB one chunk'
    writer = AsyncMock()
    writer.close = lambda: None
    tunnel = _Tunnel('owner', reader, writer)
    websocket = AsyncMock()
    websocket.closed = False
    websocket.send_bytes.side_effect = ConnectionError('partly delivered')
    tunnel.socket = websocket
    tunnel.attached.set()
    adapter = VNCAdapter(enabled=True)
    adapter.tunnels['owner'] = tunnel
    await asyncio.wait_for(adapter._forward(tunnel), 1)
    websocket.send_bytes.assert_awaited_once_with(b'RFB one chunk')
    assert tunnel.closed
    assert not adapter.tunnels


@pytest.mark.asyncio
async def test_oversize_or_text_frames_close_and_expired_handoff_is_rejected():
    writers = []
    async def upstream(reader, writer):
        writers.append(writer)
        try:
            await reader.read()
        finally:
            writer.close()
            await writer.wait_closed()
    server = await asyncio.start_server(upstream, '127.0.0.1', 0)
    adapter = VNCAdapter(enabled=True, port=server.sockets[0].getsockname()[1], grace=.01, handoff_ttl=-1)
    app = web.Application()
    app.router.add_get('/vnc/session', adapter.info)
    app.router.add_post('/vnc/handoff', adapter.handoff)
    app.router.add_get('/vnc/ws', adapter.websocket)
    app.on_shutdown.append(adapter.cleanup)
    try:
        async with TestClient(TestServer(app)) as client:
            origin = {'Origin': str(client.make_url('/')).rstrip('/')}
            await client.get('/vnc/session')
            ws = await client.ws_connect('/vnc/ws', headers=origin)
            handoff = (await (await client.post('/vnc/handoff', headers=origin)).json())['handoff']['token']
            assert (await client.get('/vnc/session?host=example.com')).status == 400
            from aiohttp import WSServerHandshakeError
            with pytest.raises(WSServerHandshakeError):
                await client.ws_connect('/vnc/ws?handoff='+handoff, headers=origin)
            await ws.send_str('not binary')
            await ws.receive()
            assert ws.close_code == 1003
            await asyncio.sleep(.05)
            ws = await client.ws_connect('/vnc/ws', headers=origin)
            await ws.send_bytes(b'x' * (MAX_FRAME + 1))
            await ws.receive()
            assert ws.close_code == 1009
    finally:
        server.close()
        await server.wait_closed()
        for writer in writers:
            writer.close()
            await writer.wait_closed()
