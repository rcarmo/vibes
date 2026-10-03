"""HTTP integration contracts with a synthetic backend; no model or auth."""
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from vibes.routes import agents, sessions
from vibes import agent_attachments


@pytest.fixture
def config(monkeypatch):
    from vibes.config import get_config
    c = get_config()
    monkeypatch.setattr(c, 'default_agent', 'copilot-ffi')
    monkeypatch.setattr(c, 'pi_enabled', False)
    # Each route fixture represents a running dispatcher, independent of
    # shutdown-state tests in other modules.
    monkeypatch.setattr(agents, '_ffi_closing', False)
    monkeypatch.setattr(agents, 'get_config', lambda: c)
    monkeypatch.setattr(sessions, 'get_config', lambda: c)
    return c


@pytest.mark.asyncio
async def test_route_rejects_unsupported_before_storing(aiohttp_client, db, config, monkeypatch):
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    app = web.Application()
    agents.setup_routes(app)
    client = await aiohttp_client(app)
    for payload, expected in [({'content':'/restart'}, 409), ({'content':'read this','media_ids':[1]}, 400)]:
        response = await client.post('/agent/default/message',json=payload)
        assert response.status == expected
    response = await client.get('/agents')
    rows = await response.json()
    assert len(rows['agents']) == 1
    assert rows['agents'][0]['backend_status']['transport'] == 'ffi'
    catalogue_response = await client.get('/agent/commands')
    assert catalogue_response.status == 200
    catalogue = await catalogue_response.json()
    assert catalogue['commands'] == [] and catalogue['authoritative'] is True
    assert catalogue['native_execution_supported'] is False
    assert catalogue['native_catalogue']['available'] is False


@pytest.mark.asyncio
async def test_dispatch_uses_ffi_and_persists_once(db, config, monkeypatch):
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    root = await db.create_interaction({'type':'user_message','content':'hello'})
    events = []
    async def broadcast(kind, data):
        events.append((kind, data))
    monkeypatch.setattr(agents, 'broadcast_event', broadcast)
    async def send(content, thread_id, callback, **kw):
        assert kw['attachment_context']['mode'] == 'copilot-ffi'
        assert kw['chat_id'] == 'default'
        await callback({'type':'message_chunk','text':'Test reply','delta':'Test reply','mode':'append'})
        return {'text':'Test reply','content':[], 'cancelled':False}
    monkeypatch.setattr(agents.copilot_backend, 'send', send)
    no_acp = AsyncMock(side_effect=AssertionError('ACP must not run'))
    monkeypatch.setattr(agents, '_dispatch_acp_thread', no_acp)
    await agents.process_agent_response(root, 'hello', 'default')
    assert sum(k == 'agent_response' for k, _ in events) == 1
    assert not await db.get_active_turns()
    assert agent_attachments.active is None
    no_acp.assert_not_called()


@pytest.mark.asyncio
async def test_pending_and_expired_decisions(aiohttp_client, db, config, monkeypatch):
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    app = web.Application()
    agents.setup_routes(app)
    client = await aiohttp_client(app)
    monkeypatch.setattr(agents.copilot_backend, 'pending_requests', lambda chat_id: [{'request_id':'ffi-test','session_id':'default'}])
    status = await (await client.get('/agents/status?session_id=default')).json()
    assert status['pending_requests'][0]['request_id'] == 'ffi-test'
    response = await client.post('/agent/respond',json={'request_id':'ffi-expired','outcome':'allow'})
    assert response.status == 409


@pytest.mark.asyncio
async def test_cancel_keeps_queued_followups_and_errors_are_redacted(db, config, monkeypatch):
    from unittest.mock import Mock
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    root = await db.create_interaction({'type':'user_message','content':'hello'})
    broadcast = AsyncMock()
    monkeypatch.setattr(agents, 'broadcast_event', broadcast)
    consume = Mock()
    monkeypatch.setattr(agents, 'consume_next_followup', consume)
    monkeypatch.setattr(agents.copilot_backend, 'send', AsyncMock(return_value={'text':'', 'content':[], 'cancelled':True,'cancel_reason':'abort'}))
    await agents.process_agent_response(root, 'hello', 'default')
    consume.assert_not_called()
    monkeypatch.setattr(agents.copilot_backend, 'send', AsyncMock(side_effect=RuntimeError('private-synthetic-token')))
    await agents.process_agent_response(root, 'hello', 'default')
    assert 'private-synthetic-token' not in str(broadcast.call_args_list)


@pytest.mark.asyncio
async def test_model_route_does_not_invoke_pi(aiohttp_client, db, config, monkeypatch):
    monkeypatch.setattr(sessions, 'get_db', AsyncMock(return_value=db))
    from vibes.copilot_host import backend
    monkeypatch.setattr(backend, 'model', AsyncMock(side_effect=RuntimeError('unavailable')))
    app=web.Application()
    sessions.setup_routes(app)
    client=await aiohttp_client(app)
    assert (await client.post('/sessions/default/model',json={'model_id':'test'})).status == 409
    assert (await (await client.get('/sessions/default/model-state')).json())['available'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('cancelled', [False, True])
@pytest.mark.parametrize('steer', [False, True])
async def test_ffi_followup_lookup_failure_restores_item(db, config, monkeypatch, cancelled, steer):
    import asyncio
    from vibes import followups
    followups.reset_state()
    agents._ffi_tasks.clear()
    agents._ffi_closing = False
    from vibes.followup_store import FollowupStore
    store = FollowupStore(db)
    item = await store.enqueue(thread_id=1, agent_id='default', message_id=1, content='queued', steer=steer)
    later = await store.enqueue(thread_id=1, agent_id='default', message_id=2, content='later', steer=steer)
    failure = asyncio.CancelledError() if cancelled else RuntimeError('lookup unavailable')
    monkeypatch.setattr(db, 'get_interaction', AsyncMock(side_effect=failure))
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(agents, 'process_agent_response', AsyncMock(return_value=True))
    broadcast = AsyncMock()
    monkeypatch.setattr(agents, 'broadcast_event', broadcast)
    try:
        agents._enqueue_ffi('chat', 1, 'first', 'default', [])
        task = agents._ffi_tasks['chat']
        if cancelled:
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await task
        remaining = await store.list(thread_id=1, agent_id='default')
        assert [row['row_id'] for row in remaining] == [item['row_id'], later['row_id']]
        assert all(row['state'] == 'pending' and row['mode'] == ('steer' if steer else 'queue') for row in remaining)
        broadcast.assert_not_awaited()
    finally:
        followups.reset_state()
        agents._ffi_tasks.clear()


@pytest.mark.asyncio
async def test_native_predefined_action_never_uses_generic_worker(aiohttp_client, db, config, monkeypatch):
    from unittest.mock import Mock
    enqueue = Mock()
    monkeypatch.setattr(agents, 'enqueue', enqueue)
    app = web.Application()
    agents.setup_routes(app)
    client = await aiohttp_client(app)
    response = await client.post('/agent/default/action/test', json={'thread_id': 1})
    assert response.status == 409
    assert (await response.json())['admitted'] is False
    enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_ffi_consumed_notification_failure_restores_prepared_followup(db, config, monkeypatch):
    import asyncio
    from vibes import followups
    from vibes.followup_store import FollowupStore
    store = FollowupStore(db)
    agents._ffi_closing = False
    item = await store.enqueue(thread_id=1, agent_id='default', message_id=1, content='queued')
    fake_db = type('Lookup', (), {'get_interaction': AsyncMock(return_value={'data': {'session_id': 'notify-chat', 'thread_id': 1}})})()
    monkeypatch.setattr(db, 'get_interaction', fake_db.get_interaction)
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    process = AsyncMock(return_value=True)
    monkeypatch.setattr(agents, 'process_agent_response', process)
    monkeypatch.setattr(agents, 'broadcast_event', AsyncMock(side_effect=asyncio.CancelledError()))
    try:
        agents._enqueue_ffi('notify-chat', 1, 'first', 'default', [])
        task = agents._ffi_tasks['notify-chat']
        with pytest.raises(asyncio.CancelledError):
            await task
        rows = await store.list()
        assert [(row['row_id'], row['state']) for row in rows] == [(item['row_id'], 'pending')]
        process.assert_awaited_once()
    finally:
        agents._ffi_tasks.clear()


@pytest.mark.asyncio
async def test_ffi_missing_followup_source_is_preserved_not_dispatched(db, config, monkeypatch):
    from vibes import followups
    from vibes.followup_store import FollowupStore
    store = FollowupStore(db)
    agents._ffi_closing = False
    item = await store.enqueue(thread_id=1, agent_id='default', message_id=99, content='queued')
    fake_db = type('Lookup', (), {'get_interaction': AsyncMock(return_value=None)})()
    monkeypatch.setattr(db, 'get_interaction', fake_db.get_interaction)
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    process = AsyncMock(return_value=True)
    monkeypatch.setattr(agents, 'process_agent_response', process)
    broadcast = AsyncMock()
    monkeypatch.setattr(agents, 'broadcast_event', broadcast)
    try:
        agents._enqueue_ffi('missing-source-chat', 1, 'first', 'default', [])
        await agents._ffi_tasks['missing-source-chat']
        rows = await store.list()
        assert [(row['row_id'], row['state']) for row in rows] == [(item['row_id'], 'pending')]
        process.assert_awaited_once()
        broadcast.assert_not_awaited()
    finally:
        agents._ffi_tasks.clear()


@pytest.mark.asyncio
async def test_ffi_foreign_followup_source_never_supplies_lane_attachments(db, config, monkeypatch):
    from vibes import followups
    from vibes.followup_store import FollowupStore
    store = FollowupStore(db)
    agents._ffi_closing = False
    item = await store.enqueue(thread_id=1, agent_id='default', message_id=99, content='queued')
    fake_db = type('Lookup', (), {'get_interaction': AsyncMock(return_value={'data': {'session_id': 'foreign', 'media_ids': [42]}})})()
    monkeypatch.setattr(db, 'get_interaction', fake_db.get_interaction)
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    process = AsyncMock(return_value=True)
    monkeypatch.setattr(agents, 'process_agent_response', process)
    broadcast = AsyncMock()
    monkeypatch.setattr(agents, 'broadcast_event', broadcast)
    try:
        agents._enqueue_ffi('own', 1, 'first', 'default', [])
        await agents._ffi_tasks['own']
        rows = await store.list()
        assert [(row['row_id'], row['state']) for row in rows] == [(item['row_id'], 'pending')]
        process.assert_awaited_once_with(1, 'first', 'default', media_ids=[])
        broadcast.assert_not_awaited()
    finally:
        agents._ffi_tasks.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize('root_source', [False, True])
async def test_ffi_same_chat_followup_promotes_once_with_source_attachments(db, config, monkeypatch, root_source):
    from vibes import followups
    from vibes.followup_store import FollowupStore
    store = FollowupStore(db)
    agents._ffi_closing = False
    await store.enqueue(thread_id=1, agent_id='default', message_id=1 if root_source else 99, content='queued')
    source = {'id': 1 if root_source else 99, 'data': {'session_id': 'own-success', 'media_ids': [42]}}
    if not root_source:
        source['data']['thread_id'] = 1
    fake_db = type('Lookup', (), {'get_interaction': AsyncMock(return_value=source)})()
    monkeypatch.setattr(db, 'get_interaction', fake_db.get_interaction)
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    process = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(agents, 'process_agent_response', process)
    broadcast = AsyncMock()
    monkeypatch.setattr(agents, 'broadcast_event', broadcast)
    try:
        agents._enqueue_ffi('own-success', 1, 'first', 'default', [])
        await agents._ffi_tasks['own-success']
        rows = await store.list()
        assert len(rows) == 1 and rows[0]['state'] == 'uncertain'
        assert await store.claim(1, 'default') is None
        assert process.await_count == 2
        assert process.await_args_list[1].args == (1, 'queued', 'default')
        assert process.await_args_list[1].kwargs == {'media_ids': [42]}
        broadcast.assert_awaited_once()
        assert broadcast.await_args.args[0] == 'agent_followup_consumed'
    finally:
        agents._ffi_tasks.clear()


@pytest.mark.asyncio
async def test_ffi_same_chat_foreign_thread_source_is_not_promoted(db, config, monkeypatch):
    from vibes import followups
    from vibes.followup_store import FollowupStore
    store = FollowupStore(db)
    agents._ffi_closing = False
    item = await store.enqueue(thread_id=1, agent_id='default', message_id=99, content='queued')
    fake_db = type('Lookup', (), {'get_interaction': AsyncMock(return_value={'id': 99, 'data': {'session_id': 'thread-check', 'thread_id': 2}})})()
    monkeypatch.setattr(db, 'get_interaction', fake_db.get_interaction)
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    process = AsyncMock(return_value=True)
    monkeypatch.setattr(agents, 'process_agent_response', process)
    broadcast = AsyncMock()
    monkeypatch.setattr(agents, 'broadcast_event', broadcast)
    try:
        agents._enqueue_ffi('thread-check', 1, 'first', 'default', [])
        await agents._ffi_tasks['thread-check']
        rows = await store.list()
        assert [(row['row_id'], row['state']) for row in rows] == [(item['row_id'], 'pending')]
        process.assert_awaited_once()
        broadcast.assert_not_awaited()
    finally:
        agents._ffi_tasks.clear()
