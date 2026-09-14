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
    import vibes
    module = vibes.pi_client if mode == 'pi' else agents.acp_client
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
