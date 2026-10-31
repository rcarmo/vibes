"""Shutdown denies late terminal opens and closes acquired PTYs."""

import asyncio
import importlib
import os

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

terminal = importlib.import_module('vibes.routes.terminal')
pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Local PTY service is POSIX-only')


@pytest.mark.asyncio
async def test_shutdown_joins_pending_open_and_closes_late_pty(tmp_path, monkeypatch):
    adapter = terminal.TerminalAdapter(str(tmp_path), enabled=True)
    original = adapter.service.open
    entered, cancelled = asyncio.Event(), asyncio.Event()
    acquired = []

    async def late_open(owner):
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # Model process acquisition completing as shutdown cancels its waiter.
            session = await original(owner)
            acquired.append(session)
            cancelled.set()
            return session

    monkeypatch.setattr(adapter.service, 'open', late_open)
    app = web.Application()
    app.router.add_get('/terminal/session', adapter.info)
    app.router.add_get('/terminal/ws', adapter.websocket)
    app.on_shutdown.append(adapter.cleanup)
    async with TestClient(TestServer(app)) as client:
        await client.get('/terminal/session')
        headers = {'Origin': str(client.make_url('/')).rstrip('/')}
        socket = await client.ws_connect('/terminal/ws', headers=headers)
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.wait_for(adapter.cleanup(app), 3)
        assert cancelled.is_set()
        assert socket.closed or (await asyncio.wait_for(socket.receive(), 1)).type in {
            web.WSMsgType.CLOSE, web.WSMsgType.CLOSED, web.WSMsgType.CLOSING}
        assert not adapter.service.sessions and not adapter.sockets and not adapter.opening_tasks
        assert all(session.closed and session.process.returncode is not None for session in acquired)
        response = await client.get('/terminal/session')
        assert response.status == 503
        await socket.close()


@pytest.mark.asyncio
async def test_service_open_rejected_after_shutdown(tmp_path):
    from vibes.terminal import TerminalService
    service = TerminalService(str(tmp_path))
    await service.shutdown()
    with pytest.raises(RuntimeError):
        await service.open('late')
    assert service.sessions == {}


@pytest.mark.asyncio
async def test_cancel_during_spawn_settles_and_reaps_acquired_process(tmp_path, monkeypatch):
    from vibes.terminal import TerminalService
    original = asyncio.create_subprocess_exec
    entered, release = asyncio.Event(), asyncio.Event()
    processes = []

    async def delayed(*args, **kwargs):
        process = await original(*args, **kwargs)
        processes.append(process)
        entered.set()
        await release.wait()
        return process

    monkeypatch.setattr(asyncio, 'create_subprocess_exec', delayed)
    service = TerminalService(str(tmp_path))
    task = asyncio.create_task(service.open('spawn-race'))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()  # Repeated cancellation must not bypass acquisition cleanup.
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 4)
        assert len(processes) == 1 and processes[0].returncode is not None
        assert not service.sessions
    finally:
        release.set()
        await service.shutdown()


@pytest.mark.asyncio
async def test_cancel_close_still_reaps_and_removes_session(tmp_path, monkeypatch):
    from vibes.terminal import TerminalService
    service = TerminalService(str(tmp_path))
    session = await service.open('close-race')
    entered, release = asyncio.Event(), asyncio.Event()
    original = service._reap

    async def delayed(process):
        entered.set()
        await release.wait()
        await original(process)

    monkeypatch.setattr(service, '_reap', delayed)
    task = asyncio.create_task(service.close(session))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 4)
        assert session.process.returncode is not None and not service.sessions
        await service.close(session)  # Joining an already completed close is safe.
    finally:
        release.set()
        await service.shutdown()


@pytest.mark.asyncio
async def test_handoff_during_initial_open_rejected(tmp_path, monkeypatch):
    adapter = terminal.TerminalAdapter(str(tmp_path), enabled=True)
    entered, release = asyncio.Event(), asyncio.Event()
    original = adapter.service.open

    async def delayed(owner):
        entered.set()
        await release.wait()
        return await original(owner)

    monkeypatch.setattr(adapter.service, 'open', delayed)
    app = web.Application()
    app.router.add_get('/terminal/session', adapter.info)
    app.router.add_get('/terminal/ws', adapter.websocket)
    app.router.add_post('/terminal/handoff', adapter.handoff)
    app.on_shutdown.append(adapter.cleanup)
    async with TestClient(TestServer(app)) as client:
        await client.get('/terminal/session')
        headers = {'Origin': str(client.make_url('/')).rstrip('/')}
        socket = await client.ws_connect('/terminal/ws', headers=headers)
        await asyncio.wait_for(entered.wait(), 1)
        response = await client.post('/terminal/handoff', headers=headers)
        assert response.status == 409 and len(adapter.opening_tasks) == 1
        release.set()
        assert (await socket.receive_json())['type'] == 'session'
        await socket.close()


@pytest.mark.asyncio
async def test_failed_handoff_upgrade_restores_live_original_attachment(tmp_path, monkeypatch):
    from aiohttp import WSServerHandshakeError
    adapter = terminal.TerminalAdapter(str(tmp_path), enabled=True, grace=.02)
    app = web.Application()
    app.router.add_get('/terminal/session', adapter.info)
    app.router.add_get('/terminal/ws', adapter.websocket)
    app.router.add_post('/terminal/handoff', adapter.handoff)
    app.on_shutdown.append(adapter.cleanup)
    async with TestClient(TestServer(app)) as client:
        await client.get('/terminal/session')
        headers = {'Origin': str(client.make_url('/')).rstrip('/')}
        original_socket = await client.ws_connect('/terminal/ws', headers=headers)
        await original_socket.receive_json()
        owner = next(iter(adapter.sockets))
        old = adapter.sockets[owner]
        token = (await (await client.post('/terminal/handoff', headers=headers)).json())['handoff']['token']
        original_prepare = web.WebSocketResponse.prepare

        async def fail_replacement(socket, request):
            if request.query.get('handoff'):
                raise web.HTTPBadRequest(reason='fixture replacement failure')
            return await original_prepare(socket, request)

        monkeypatch.setattr(web.WebSocketResponse, 'prepare', fail_replacement)
        with pytest.raises(WSServerHandshakeError):
            await client.ws_connect('/terminal/ws?handoff=' + token, headers=headers)
        await asyncio.sleep(.05)
        assert adapter.sockets[owner] is old and not old.closed
        assert owner in adapter.service.sessions and owner not in adapter.timers
        await original_socket.send_json({'type': 'ping', 'ts': 'still-live'})
        async with asyncio.timeout(2):
            while True:
                event = await original_socket.receive_json()
                if event['type'] == 'pong':
                    assert event['ts'] == 'still-live'
                    break
        await original_socket.close()


@pytest.mark.asyncio
async def test_shutdown_during_handoff_closes_original_and_replacement(tmp_path, monkeypatch):
    adapter = terminal.TerminalAdapter(str(tmp_path), enabled=True)
    app = web.Application()
    app.router.add_get('/terminal/session', adapter.info)
    app.router.add_get('/terminal/ws', adapter.websocket)
    app.router.add_post('/terminal/handoff', adapter.handoff)
    app.on_shutdown.append(adapter.cleanup)
    async with TestClient(TestServer(app)) as client:
        await client.get('/terminal/session')
        headers = {'Origin': str(client.make_url('/')).rstrip('/')}
        original_socket = await client.ws_connect('/terminal/ws', headers=headers)
        await original_socket.receive_json()
        owner = next(iter(adapter.sockets))
        old = adapter.sockets[owner]
        token = (await (await client.post('/terminal/handoff', headers=headers)).json())['handoff']['token']
        entered = asyncio.Event()
        original_close = old.close
        calls = 0

        async def delayed_close(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                entered.set()
                await asyncio.Event().wait()
            return await original_close(*args, **kwargs)

        monkeypatch.setattr(old, 'close', delayed_close)
        replacement = await client.ws_connect('/terminal/ws?handoff=' + token, headers=headers)
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.wait_for(adapter.cleanup(app), 4)
        assert old.closed and not adapter.sockets and not adapter.service.sessions
        assert not adapter.opening_tasks
        await original_socket.close()
        await replacement.close()
