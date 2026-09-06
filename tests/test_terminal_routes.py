import asyncio
import importlib

import pytest
from aiohttp import web, WSServerHandshakeError

TerminalAdapter = importlib.import_module("vibes.routes.terminal").TerminalAdapter


async def client_for(aiohttp_client, tmp_path, enabled=True):
    adapter = TerminalAdapter(str(tmp_path), enabled=enabled, grace=0.05)
    app = web.Application()
    app.router.add_get('/terminal/session', adapter.info)
    app.router.add_post('/terminal/handoff', adapter.handoff)
    app.router.add_get('/terminal/ws', adapter.websocket)
    app.on_shutdown.append(adapter.cleanup)
    client = await aiohttp_client(app)
    return client, adapter, {"Origin": str(client.make_url('/')).rstrip('/')}


@pytest.mark.asyncio
async def test_disabled_and_origin(aiohttp_client, tmp_path):
    client, adapter, headers = await client_for(aiohttp_client, tmp_path, False)
    assert await (await client.get('/terminal/session')).json() == {"enabled": False}
    assert (await client.post('/terminal/handoff', headers=headers)).status == 404
    assert not adapter.service.sessions


@pytest.mark.asyncio
async def test_handoff_reconnect_and_expiry(aiohttp_client, tmp_path):
    client, adapter, headers = await client_for(aiohttp_client, tmp_path)
    assert (await client.get('/terminal/session')).status == 200
    with pytest.raises(WSServerHandshakeError):
        await client.ws_connect('/terminal/ws', headers={"Origin": "https://evil.example"})
    ws = await client.ws_connect('/terminal/ws', headers=headers)
    assert (await ws.receive_json())['type'] == 'session'
    session = next(iter(adapter.service.sessions.values()))
    token = (await (await client.post('/terminal/handoff', headers=headers)).json())['handoff']['token']
    moved = await client.ws_connect('/terminal/ws?handoff=' + token, headers=headers)
    assert (await moved.receive_json())['type'] == 'session'
    assert next(iter(adapter.service.sessions.values())) is session
    with pytest.raises(WSServerHandshakeError):
        await client.ws_connect('/terminal/ws?handoff=' + token, headers=headers)
    await moved.close()
    await ws.close()
    await asyncio.sleep(0.8)
    assert not adapter.service.sessions
    assert session.process.returncode is not None


@pytest.mark.asyncio
async def test_missing_owner_and_input(aiohttp_client, tmp_path):
    client, adapter, headers = await client_for(aiohttp_client, tmp_path)
    assert (await client.post('/terminal/handoff', headers=headers)).status == 401
    await client.get('/terminal/session')
    ws = await client.ws_connect('/terminal/ws', headers=headers)
    await ws.receive_json()
    await ws.send_json({"type": "input", "data": "printf 'route-%s\\n' verified\n"})
    text = ''
    async with asyncio.timeout(3):
        while 'route-verified' not in text:
            frame = await ws.receive_json()
            text += frame.get('data', '')
    await ws.send_json({"type": "resize", "cols": "bad", "rows": 20})
    await ws.receive()
    await ws.close()


@pytest.mark.asyncio
async def test_detached_reconnect_keeps_shell(aiohttp_client, tmp_path):
    client, adapter, headers = await client_for(aiohttp_client, tmp_path)
    adapter.grace = 1
    await client.get('/terminal/session')
    ws = await client.ws_connect('/terminal/ws', headers=headers)
    await ws.receive_json()
    session = next(iter(adapter.service.sessions.values()))
    await ws.close()
    await asyncio.sleep(0.05)
    resumed = await client.ws_connect('/terminal/ws', headers=headers)
    await resumed.receive_json()
    assert next(iter(adapter.service.sessions.values())) is session
    await resumed.close()


@pytest.mark.asyncio
async def test_expired_handoff_rejected(aiohttp_client, tmp_path):
    client, adapter, headers = await client_for(aiohttp_client, tmp_path)
    adapter.handoff_ttl = -1
    await client.get('/terminal/session')
    ws = await client.ws_connect('/terminal/ws', headers=headers)
    await ws.receive_json()
    token = (await (await client.post('/terminal/handoff', headers=headers)).json())['handoff']['token']
    with pytest.raises(WSServerHandshakeError):
        await client.ws_connect('/terminal/ws?handoff=' + token, headers=headers)
    await ws.close()


@pytest.mark.asyncio
async def test_deployed_client_metadata_ping_and_exit(aiohttp_client, tmp_path):
    client, adapter, headers = await client_for(aiohttp_client, tmp_path)
    await client.get('/terminal/session')
    ws = await client.ws_connect('/terminal/ws', headers=headers)
    metadata = await ws.receive_json()
    assert metadata['session_id']
    assert metadata['created_at']
    assert metadata['process_pid'] > 0
    await ws.send_json({'type': 'ping', 'ts': 123})
    async with asyncio.timeout(3):
        while True:
            event = await ws.receive_json()
            if event['type'] == 'pong':
                assert event['ts'] == 123
                break
    await ws.send_json({'type': 'input', 'data': 'exit 7\n'})
    async with asyncio.timeout(3):
        while True:
            event = await ws.receive_json()
            if event['type'] == 'exit':
                assert event['exit_code'] == 7
                break
    await ws.close()
