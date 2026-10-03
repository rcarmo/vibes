"""Turn cancellation is scoped to both the conversation and runtime request."""
import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio

from vibes import acp_client, pi_client
from vibes.routes import agents
from vibes.sessions import SessionStore

@pytest_asyncio.fixture
async def client(aiohttp_client, db):
    from aiohttp import web
    routes = agents
    app = web.Application()
    routes.setup_routes(app)
    with patch.object(routes, 'get_db', AsyncMock(return_value=db)):
        yield await aiohttp_client(app)



async def active_turn(db, session_id='default', turn_id='turn-one'):
    root = await db.create_interaction({'type': 'user_message', 'content': 'work', 'session_id': session_id})
    await db.begin_turn(turn_id, root, 'default')


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['pi', 'acp'])
async def test_scoped_abort_sends_no_message_and_preserves_queue(client, db, mode):
    session = await SessionStore(db).create('Other')
    await active_turn(db, session['id'])
    # Other test modules purge package attributes during collection. Import the
    # same live module the route resolves instead of relying on package attributes.
    from vibes import pi_client as live_pi_client
    module = live_pi_client if mode == 'pi' else agents.acp_client
    with patch.object(agents, '_resolve_agent_mode', return_value=mode), \
         patch.object(module, 'abort_chat_turn', AsyncMock(return_value=True)) as abort, \
         patch.object(db, 'create_interaction', AsyncMock()) as post, \
         patch.object(agents, 'broadcast_event', AsyncMock()) as broadcast:
        response = await client.post('/agent/default/abort', json={'session_id': session['id'], 'turn_id': 'turn-one'})
        assert response.status == 202
        assert (await response.json())['status'] == 'cancelling'
        assert abort.await_args.args[0] == session['id']
        post.assert_not_awaited()
        broadcast.assert_not_awaited()
        assert len(await db.get_active_turns()) == 1  # Only actual completion ends it.


@pytest.mark.asyncio
async def test_stale_other_missing_and_invalid_abort_rejected(client, db):
    other = await SessionStore(db).create('Other')
    await active_turn(db)
    with patch.object(pi_client, 'abort_chat_turn', AsyncMock()) as abort_pi, \
         patch.object(acp_client, 'abort_chat_turn', AsyncMock()) as abort_acp:
        for payload, status in [({}, 400), ([], 400),
                                ({'session_id': 'missing', 'turn_id': 'turn-one'}, 404),
                                ({'session_id': other['id'], 'turn_id': 'turn-one'}, 409),
                                ({'session_id': 'default', 'turn_id': 'stale'}, 409)]:
            response = await client.post('/agent/default/abort', json=payload)
            assert response.status == status
        abort_pi.assert_not_awaited()
        abort_acp.assert_not_awaited()


@pytest.mark.asyncio
async def test_unconfirmed_runtime_abort_is_visible_error(client, db):
    await active_turn(db)
    with patch.object(agents, '_resolve_agent_mode', return_value='pi'), \
         patch('vibes.pi_client.abort_chat_turn', AsyncMock(return_value=False)):
        response = await client.post('/agent/default/abort', json={'session_id': 'default', 'turn_id': 'turn-one'})
        assert response.status == 409
        assert 'ownership' in (await response.json())['error']


@pytest.mark.asyncio
async def test_pi_abort_owns_exact_task_and_session():
    state = pi_client._state
    task = Mock(done=Mock(return_value=False))
    writer = Mock()
    lock = asyncio.Lock()
    await lock.acquire()
    with patch.object(state, 'request_lock', lock), patch.object(state, 'current_request_task', task), \
         patch.object(state, 'agent_writer', writer), patch.object(state.session_selector, 'active', 'private'), \
         patch.object(state.session_selector, 'uncertain', False):
        assert not await pi_client.abort_chat_turn('default', task)
        assert not await pi_client.abort_chat_turn('private', Mock())
        task.cancel.assert_not_called()
        writer.write.assert_not_called()
        assert await pi_client.abort_chat_turn('private', task)
        writer.write.assert_called_once_with(b'{"type":"abort"}\n')
        task.cancel.assert_called_once()
    lock.release()


@pytest.mark.asyncio
async def test_acp_abort_owns_exact_request_and_session():
    state = acp_client._state
    owner = asyncio.Event()
    writer = Mock()
    lock = asyncio.Lock()
    await lock.acquire()
    with patch.object(state, 'request_lock', lock), patch.object(state, 'cancel_event', owner), \
         patch.object(state, 'agent_writer', writer), patch.object(state, 'chat_id', 'private'), \
         patch.object(state, 'session_id', 'acp-private'), patch.object(state, '_cancelled', False, create=True), \
         patch.object(state, '_cancel_reason', '', create=True):
        assert not await acp_client.abort_chat_turn('default', owner)
        assert not await acp_client.abort_chat_turn('private', asyncio.Event())
        writer.write.assert_not_called()
        assert await acp_client.abort_chat_turn('private', owner)
        message = json.loads(writer.write.call_args.args[0])
        assert message['method'] == 'session/cancel'
        assert message['params']['sessionId'] == 'acp-private'
        assert state._cancelled and state._cancel_reason == 'abort'
    lock.release()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['pi', 'acp'])
@pytest.mark.parametrize('cancelled', [True, False])
async def test_followup_dispatch_requires_successful_turn(db, monkeypatch, mode, cancelled):
    from vibes import agent_attachments
    monkeypatch.setattr(agent_attachments, 'referenced_media', AsyncMock(return_value=[]))
    from vibes import followups
    import importlib
    agents = importlib.import_module('vibes.routes.agents')
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    root = await db.create_interaction({'type': 'user', 'content': 'abort', 'session_id': 'default'})
    followups.reset_state()
    item = followups.queue_followup(thread_id=root, agent_id='default', message_id=root, content='keep queued')
    async def dispatch(*args, **kwargs):
        return {'text': 'response', 'content': [], 'cancelled': cancelled, 'cancel_reason': 'abort' if cancelled else None}
    monkeypatch.setattr(agents, '_dispatch_pi_thread' if mode == 'pi' else '_dispatch_acp_thread', dispatch)
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda _: mode)
    monkeypatch.setattr(agents, 'broadcast_event', AsyncMock())
    enqueue = Mock()
    monkeypatch.setattr(agents, 'enqueue', enqueue)
    try:
        await agents.process_agent_response(root, 'abort', 'default')
        if cancelled:
            assert [row['row_id'] for row in followups.list_followups()] == [item['row_id']]
            enqueue.assert_not_called()
        else:
            assert followups.list_followups() == []
            enqueue.assert_called_once_with(agents.process_agent_response, root, 'keep queued', 'default')
    finally:
        followups.reset_state()


@pytest.mark.asyncio
@pytest.mark.parametrize('raises', [True, False])
@pytest.mark.parametrize('steer', [True, False])
async def test_followup_admission_failure_restores_same_item(db, monkeypatch, raises, steer):
    import importlib
    from vibes import followups, agent_attachments
    agents = importlib.import_module('vibes.routes.agents')
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(agent_attachments, 'referenced_media', AsyncMock(return_value=[]))
    root = await db.create_interaction({'type': 'user', 'content': 'run', 'session_id': 'default'})
    followups.reset_state()
    add = followups.defer_steer if steer else followups.queue_followup
    item = add(thread_id=root, agent_id='default', message_id=root, content='retry')
    later = add(thread_id=root, agent_id='default', message_id=root, content='later')
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda _: 'pi')
    monkeypatch.setattr(agents, '_dispatch_pi_thread', AsyncMock(return_value={'text': 'done', 'content': [], 'cancelled': False}))
    broadcast = AsyncMock()
    monkeypatch.setattr(agents, 'broadcast_event', broadcast)
    admission = Mock(side_effect=RuntimeError('worker unavailable')) if raises else Mock(return_value=False)
    monkeypatch.setattr(agents, 'enqueue', admission)
    try:
        await agents.process_agent_response(root, 'run', 'default')
        remaining = followups.list_pending_steers() if steer else followups.list_followups()
        assert remaining == [item, later]
        assert not any(call.args[0] == 'agent_followup_consumed' for call in broadcast.await_args_list)
    finally:
        followups.reset_state()
