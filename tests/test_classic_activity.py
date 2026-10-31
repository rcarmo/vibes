"""Classic activity is persisted/session-scoped; cancel uses real ownership checks."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from vibes.routes import agents, classic
from vibes.sessions import SessionStore


async def client_for(db, monkeypatch):
    monkeypatch.setattr(classic, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    app = web.Application()
    classic.setup_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


async def active_turn(db, session_id='default', turn_id='turn-one', agent_id='default'):
    root = await db.create_interaction({'type': 'user_message', 'content': 'work', 'session_id': session_id})
    await db.begin_turn(turn_id, root, agent_id)
    return root


@pytest.mark.asyncio
async def test_activity_is_scoped_projects_safe_fields_and_never_starts_runtime(db, monkeypatch):
    client = await client_for(db, monkeypatch)
    foreign = await SessionStore(db).create('Other')
    await active_turn(db, foreign['id'], 'foreign')
    await active_turn(db, 'default', 'other-agent', 'unsupported')
    try:
        idle = await client.get('/api/sessions/default/activity')
        assert idle.status == 200 and idle.headers['Cache-Control'] == 'no-store'
        assert await idle.json() == {'status': 'idle', 'session_id': 'default',
                                     'source_session_id': 'default', 'turn_id': None}
        root = await active_turn(db)
        await db.update_turn_status('turn-one', {'status': 'running', 'turn_id': 'spoof',
                                               'session_id': foreign['id'], 'secret': 'private',
                                               'type': 'retry_wait', 'attempt': 2, 'delay_ms': 100,
                                               'max_attempts': True})
        response = await client.get('/api/sessions/default/activity')
        result = await response.json()
        assert result['status'] == 'running' and result['turn_id'] == 'turn-one'
        assert result['session_id'] == 'default' and result['thread_id'] == root
        assert result['type'] == 'retry_wait' and result['attempt'] == 2 and result['delay_ms'] == 100
        assert 'secret' not in result and 'max_attempts' not in result
        await db.update_turn_status('turn-one', {'status': 'cancelling'})
        response = await client.get('/api/sessions/default/activity')
        assert (await response.json())['status'] == 'cancelling'
        await db.end_turn('turn-one')
        response = await client.get('/api/sessions/default/activity')
        assert (await response.json())['status'] == 'idle'
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_activity_missing_archived_ambiguous_and_invalid_status(db, monkeypatch):
    client = await client_for(db, monkeypatch)
    archived = await SessionStore(db).create('Archived')
    await SessionStore(db).update(archived['id'], archived=True)
    try:
        for session in ('missing', archived['id']):
            response = await client.get(f'/api/sessions/{session}/activity')
            assert response.status == 404
        await active_turn(db)
        for value in ('{bad json', '["untrusted"]'):
            async with db.transaction() as connection:
                await connection.execute('UPDATE active_turns SET last_status = ?', (value,))
            response = await client.get('/api/sessions/default/activity')
            assert response.status == 200 and (await response.json())['turn_id'] == 'turn-one'
        await active_turn(db, turn_id='turn-two')
        response = await client.get('/api/sessions/default/activity')
        assert response.status == 409
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['pi', 'acp', 'copilot-ffi'])
async def test_cancel_calls_shared_abort_and_keeps_message_and_turn(db, monkeypatch, mode):
    client = await client_for(db, monkeypatch)
    await active_turn(db)
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda _: mode)
    from vibes import pi_client
    module = pi_client if mode == 'pi' else agents.acp_client if mode == 'acp' else agents.copilot_backend
    name = 'abort' if mode == 'copilot-ffi' else 'abort_chat_turn'
    if mode == 'copilot-ffi':
        monkeypatch.setattr(module, 'active_for', lambda _: {'turn_id': 'turn-one'})
    else:
        monkeypatch.setattr(module._runtimes.get('default'), 'active_turn_id', 'turn-one')
    abort = AsyncMock(return_value=True)
    monkeypatch.setattr(module, name, abort)
    post = AsyncMock()
    monkeypatch.setattr(db, 'create_interaction', post)
    try:
        response = await client.post('/api/sessions/default/activity', json={'turn_id': 'turn-one'})
        assert response.status == 202 and response.headers['Cache-Control'] == 'no-store'
        assert await response.json() == {'status': 'cancelling', 'session_id': 'default', 'turn_id': 'turn-one'}
        assert abort.await_args.args[0] == 'default'
        post.assert_not_awaited()
        assert len(await db.get_active_turns()) == 1
        poll = await client.get('/api/sessions/default/activity')
        assert (await poll.json())['status'] == 'cancelling'
        # Late callbacks and worker completion must not regress polling to running.
        for later in ({'type': 'cancelled'}, {'type': 'done'}, {'type': 'tool', 'title': 'late callback'}):
            await db.update_turn_status('turn-one', later)
            poll = await client.get('/api/sessions/default/activity')
            assert (await poll.json())['status'] == 'cancelling'
        await db.end_turn('turn-one')
        poll = await client.get('/api/sessions/default/activity')
        assert (await poll.json())['status'] == 'idle'
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_cancel_rejects_bad_scope_stale_owner_and_invalid_json(db, monkeypatch):
    client = await client_for(db, monkeypatch)
    other = await SessionStore(db).create('Other')
    await active_turn(db)
    from vibes import pi_client
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda _: 'pi')
    abort = AsyncMock(return_value=False)
    monkeypatch.setattr(pi_client._runtimes.get('default'), 'active_turn_id', 'turn-one')
    monkeypatch.setattr(pi_client, 'abort_chat_turn', abort)
    try:
        for payload in ({}, [], {'turn_id': ''}, {'turn_id': True}, {'turn_id': 'turn-one', 'session_id': 'default'}):
            response = await client.post('/api/sessions/default/activity', json=payload)
            assert response.status == 400
        response = await client.post('/api/sessions/default/activity', data='{bad')
        assert response.status == 400
        for session, turn, status in (('missing', 'turn-one', 404), (other['id'], 'turn-one', 409),
                                      ('default', 'stale', 409)):
            response = await client.post(f'/api/sessions/{session}/activity', json={'turn_id': turn})
            assert response.status == status
        abort.assert_not_awaited()
        response = await client.post('/api/sessions/default/activity', json={'turn_id': 'turn-one'})
        assert response.status == 409
        assert 'ownership' in (await response.json())['error']
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_actual_pi_abort_signals_only_captured_request(db, monkeypatch):
    client = await client_for(db, monkeypatch)
    await active_turn(db)
    from vibes import pi_client
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda _: 'pi')
    state = pi_client._runtimes.get('default')
    monkeypatch.setattr(state, 'active_turn_id', 'turn-one')
    task = Mock(done=Mock(return_value=False))
    lock = asyncio.Lock()
    await lock.acquire()
    monkeypatch.setattr(state, 'request_lock', lock)
    monkeypatch.setattr(state, 'current_request_task', task)
    writer = Mock()
    monkeypatch.setattr(state, 'agent_writer', writer)
    monkeypatch.setattr(state.session_selector, 'active', 'default')
    monkeypatch.setattr(state.session_selector, 'uncertain', False)
    try:
        response = await client.post('/api/sessions/default/activity', json={'turn_id': 'turn-one'})
        assert response.status == 202
        writer.write.assert_called_once_with(b'{"type":"abort"}\n')
        task.cancel.assert_called_once()
    finally:
        lock.release()
        await client.close()


@pytest.mark.asyncio
async def test_cancel_rechecks_turn_after_await_and_never_aborts_promoted_turn(db, monkeypatch):
    client = await client_for(db, monkeypatch)
    await active_turn(db)
    from vibes import pi_client
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda _: 'pi')
    abort = AsyncMock(return_value=True)
    monkeypatch.setattr(pi_client, 'abort_chat_turn', abort)
    original = db.get_interaction
    calls = 0

    async def promote_after_read(*args):
        nonlocal calls
        root = await original(*args)
        calls += 1
        if calls == 2:  # After helper's initial owner lookup, during root validation.
            await db.end_turn('turn-one')
            await db.begin_turn('promoted', root['id'], 'default')
        return root

    monkeypatch.setattr(db, 'get_interaction', promote_after_read)
    try:
        response = await client.post('/api/sessions/default/activity', json={'turn_id': 'turn-one'})
        assert response.status == 409
        abort.assert_not_awaited()
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['pi', 'acp', 'copilot-ffi'])
async def test_stale_persisted_turn_cannot_cancel_different_runtime_turn(db, monkeypatch, mode):
    client = await client_for(db, monkeypatch)
    await active_turn(db, turn_id='persisted-old')
    from vibes import pi_client
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda _: mode)
    module = pi_client if mode == 'pi' else agents.acp_client if mode == 'acp' else agents.copilot_backend
    if mode == 'copilot-ffi':
        monkeypatch.setattr(module, 'active_for', lambda _: {'turn_id': 'runtime-new'})
    else:
        monkeypatch.setattr(module._runtimes.get('default'), 'active_turn_id', 'runtime-new')
    abort = AsyncMock(return_value=True)
    monkeypatch.setattr(module, 'abort' if mode == 'copilot-ffi' else 'abort_chat_turn', abort)
    try:
        response = await client.post('/api/sessions/default/activity', json={'turn_id': 'persisted-old'})
        assert response.status == 409
        assert 'identity' in (await response.json())['error']
        abort.assert_not_awaited()
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['pi', 'acp'])
@pytest.mark.parametrize('failure', [False, True])
async def test_worker_runtime_identity_is_bound_and_cleared_even_on_failure(db, monkeypatch, mode, failure):
    root = await db.create_interaction({'type': 'user_message', 'content': 'work', 'session_id': 'default'})
    from vibes import pi_client
    module = pi_client if mode == 'pi' else agents.acp_client
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda _: mode)

    async def dispatch(*args, admitted_turn_id):
        assert module._runtimes.existing('default').active_turn_id == admitted_turn_id == 'reserved'
        if failure:
            raise asyncio.CancelledError()
        return True

    monkeypatch.setattr(agents, '_process_agent_response_locked', dispatch)
    if failure:
        with pytest.raises(asyncio.CancelledError):
            await agents.process_agent_response(root, 'work', 'default', admitted_turn_id='reserved')
    else:
        assert await agents.process_agent_response(root, 'work', 'default', admitted_turn_id='reserved')
    assert module._runtimes.existing('default').active_turn_id is None
