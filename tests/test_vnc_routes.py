import asyncio

import aiohttp
import pytest
import pytest_asyncio
from aiohttp import WSMsgType, web

from vibes.routes.vnc import COOKIE, VNCAdapter


async def vnc_client(aiohttp_client, server, *, enabled=True, grace=0.1):
    port = server.sockets[0].getsockname()[1]
    adapter = VNCAdapter(enabled=enabled, host="127.0.0.1", port=port, grace=grace)
    app = web.Application()
    app.router.add_get("/vnc/session", adapter.info)
    app.router.add_post("/vnc/handoff", adapter.handoff)
    app.router.add_get("/vnc/ws", adapter.websocket)
    app.on_shutdown.append(adapter.cleanup)
    client = await aiohttp_client(app)
    return client, adapter, {"Origin": str(client.make_url("/")).rstrip("/")}


@pytest_asyncio.fixture
async def echo_vnc_server():
    clients = []
    closed = asyncio.Event()

    async def echo(reader, writer):
        clients.append(writer)
        writer.write(b"RFB 003.008\n")
        await writer.drain()
        try:
            while data := await reader.read(65536):
                writer.write(data)
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            closed.set()

    server = await asyncio.start_server(echo, "127.0.0.1", 0)
    try:
        yield server, clients, closed
    finally:
        server.close()
        await server.wait_closed()
        for writer in clients:
            writer.close()
            await writer.wait_closed()


@pytest.mark.asyncio
async def test_disabled_origin_cookie_and_fixed_target(aiohttp_client, echo_vnc_server):
    server, _clients, _closed = echo_vnc_server
    client, adapter, headers = await vnc_client(aiohttp_client, server, enabled=False)
    response = await client.get("/vnc/session")
    body = await response.json()
    assert body["enabled"] is False
    assert body["direct_connect"] is False
    assert response.headers["Cache-Control"] == "no-store"
    assert (await client.post("/vnc/handoff", headers=headers)).status == 404
    assert adapter.tunnels == {}

    client, _adapter, headers = await vnc_client(aiohttp_client, server)
    assert (await client.get("/vnc/session", headers={"Origin": "https://evil.example"})).status == 403
    assert (await client.get("/vnc/session?target=127.0.0.1:1")).status == 403
    response = await client.get("/vnc/session")
    assert response.status == 200
    assert response.cookies[COOKIE]["httponly"]
    assert response.cookies[COOKIE]["samesite"].lower() == "strict"
    with pytest.raises(aiohttp.WSServerHandshakeError):
        await client.ws_connect("/vnc/ws", headers={"Origin": "https://evil.example"})
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as stranger:
        with pytest.raises(aiohttp.WSServerHandshakeError):
            await stranger.ws_connect(client.make_url("/vnc/ws"), headers=headers)


@pytest.mark.asyncio
async def test_binary_proxy_handoff_and_reconnect(aiohttp_client, echo_vnc_server):
    server, clients, _closed = echo_vnc_server
    client, adapter, headers = await vnc_client(aiohttp_client, server, grace=0.3)
    info = await (await client.get("/vnc/session")).json()
    assert info["target"] == f"127.0.0.1:{server.sockets[0].getsockname()[1]}"
    assert info["configured"] is True
    ws = await client.ws_connect("/vnc/ws", headers=headers)
    assert (await ws.receive()).data == b"RFB 003.008\n"
    await ws.send_bytes(b"\x00RFB\xff")
    assert (await ws.receive()).data == b"\x00RFB\xff"
    assert len(clients) == 1

    handoff = await (await client.post("/vnc/handoff", headers=headers)).json()
    moved = await client.ws_connect("/vnc/ws?handoff=" + handoff["handoff"]["token"], headers=headers)
    await moved.send_bytes(b"after-handoff")
    assert (await moved.receive()).data == b"after-handoff"
    assert len(clients) == 1
    with pytest.raises(aiohttp.WSServerHandshakeError):
        await client.ws_connect("/vnc/ws?handoff=" + handoff["handoff"]["token"], headers=headers)

    await moved.close()
    await asyncio.sleep(0.03)
    resumed = await client.ws_connect("/vnc/ws", headers=headers)
    await resumed.send_bytes(b"after-reconnect")
    assert (await resumed.receive()).data == b"after-reconnect"
    assert len(clients) == 1
    await resumed.close()
    await asyncio.sleep(0.4)
    assert not adapter.tunnels


@pytest.mark.asyncio
async def test_upstream_failure_is_websocket_close_and_cleanup(aiohttp_client, unused_tcp_port):
    adapter = VNCAdapter(enabled=True, host="127.0.0.1", port=unused_tcp_port, grace=0.01)
    app = web.Application()
    app.router.add_get("/vnc/session", adapter.info)
    app.router.add_get("/vnc/ws", adapter.websocket)
    app.on_shutdown.append(adapter.cleanup)
    client = await aiohttp_client(app)
    headers = {"Origin": str(client.make_url("/")).rstrip("/")}
    await client.get("/vnc/session")
    ws = await client.ws_connect("/vnc/ws", headers=headers)
    message = await ws.receive()
    assert message.type in {WSMsgType.CLOSE, WSMsgType.CLOSED}
    assert ws.close_code == 1011


@pytest.mark.asyncio
async def test_cleanup_closes_retained_tcp_connection(aiohttp_client, echo_vnc_server):
    server, _clients, closed = echo_vnc_server
    client, _adapter, headers = await vnc_client(aiohttp_client, server, grace=10)
    await client.get("/vnc/session")
    ws = await client.ws_connect("/vnc/ws", headers=headers)
    await ws.receive()
    await client.close()
    async with asyncio.timeout(2):
        await closed.wait()
