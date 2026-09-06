import importlib
from unittest.mock import AsyncMock, ANY
import pytest
from aiohttp import web

routes = importlib.import_module('vibes.routes.sessions')


@pytest.mark.asyncio
async def test_registry_routes_and_safe_deletion(db, aiohttp_client, monkeypatch):
    monkeypatch.setattr(routes, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(routes, 'broadcast_event', AsyncMock())
    app = web.Application()
    routes.setup_routes(app)
    client = await aiohttp_client(app)
    listing = await (await client.get('/sessions')).json()
    assert listing['runtime_isolation'] is False
    created = await client.post('/sessions', json={'name': 'Research'})
    assert created.status == 201
    key = (await created.json())['session']['id']
    response = await client.patch('/sessions/' + key, json={'name': 'Renamed', 'pinned': True})
    assert (await response.json())['session']['name'] == 'Renamed'
    assert (await client.delete('/sessions/default')).status == 400
    assert (await client.patch('/sessions/' + key, json={'runtime': 'fake'})).status == 400
    assert (await client.delete('/sessions/' + key)).status == 200
    created = await (await client.post('/sessions', json={'name': 'Nonempty'})).json()
    key = created['session']['id']
    await db.create_interaction({'type': 'user', 'session_id': key, 'content': 'preserve'})
    assert (await client.delete('/sessions/' + key)).status == 400
    assert (await client.post('/sessions', json=[])).status == 400


@pytest.mark.asyncio
async def test_worker_dispatch_uses_persisted_chat_identity(db, monkeypatch):
    agents = importlib.import_module('vibes.routes.agents')
    SessionStore = importlib.import_module('vibes.sessions').SessionStore
    store = SessionStore(db)
    session = await store.create('Other')
    root = await db.create_interaction({'type': 'user', 'content': 'hello', 'session_id': session['id']})
    default = await db.create_interaction({'type': 'user', 'content': 'default'})
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    sender = AsyncMock(return_value={'text': 'ok'})
    monkeypatch.setattr(agents, 'send_acp_message_multimodal', sender)
    await agents._dispatch_acp_thread('hello', root, None)
    sender.assert_awaited_with('hello', root, None, chat_id=session['id'], session_store=ANY)
    await agents._dispatch_acp_thread('default', default, None)
    sender.assert_awaited_with('default', default, None)
    await store.update(session['id'], archived=True)
    with pytest.raises(ValueError):
        await agents._dispatch_acp_thread('blocked', root, None)
    assert sender.await_count == 2


@pytest.mark.asyncio
async def test_pi_worker_dispatch_uses_persisted_session(db, monkeypatch):
    agents = importlib.import_module('vibes.routes.agents')
    SessionStore = importlib.import_module('vibes.sessions').SessionStore
    store = SessionStore(db)
    session = await store.create('Pi chat')
    root = await db.create_interaction({'type': 'user', 'content': 'hello', 'session_id': session['id']})
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    sender = AsyncMock(return_value={'text': 'ok'})
    monkeypatch.setattr(agents, 'send_pi_message_multimodal', sender)
    await agents._dispatch_pi_thread('hello', root, None)
    sender.assert_awaited_once_with('hello', root, None, chat_id=session['id'], session_store=ANY)
    await store.update(session['id'], archived=True)
    with pytest.raises(ValueError):
        await agents._dispatch_pi_thread('blocked', root, None)
    assert sender.await_count == 1


@pytest.mark.asyncio
async def test_worker_status_events_include_session_identity(db, monkeypatch):
    agents = importlib.import_module('vibes.routes.agents')
    store = importlib.import_module('vibes.sessions').SessionStore(db)
    session = await store.create('Status scope')
    root = await db.create_interaction({'type': 'user', 'content': 'hello', 'session_id': session['id']})
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda _: 'acp')
    sender = AsyncMock(return_value={'text': 'response', 'content': [], 'cancelled': False})
    monkeypatch.setattr(agents, '_dispatch_acp_thread', sender)
    events = AsyncMock()
    monkeypatch.setattr(agents, 'broadcast_event', events)
    await agents.process_agent_response(root, 'hello', 'default')
    statuses = [call.args[1] for call in events.call_args_list if call.args[0] == 'agent_status']
    assert statuses
    assert all(item['session_id'] == session['id'] for item in statuses)


@pytest.mark.asyncio
async def test_timeline_route_scope_excludes_other_sessions(db, aiohttp_client, monkeypatch):
    posts = importlib.import_module('vibes.routes.posts')
    SessionStore = importlib.import_module('vibes.sessions').SessionStore
    other = await SessionStore(db).create('Other')
    visible = await db.create_interaction({'type': 'user', 'content': 'default'})
    await db.create_interaction({'type': 'user', 'content': 'private', 'session_id': other['id']})
    monkeypatch.setattr(posts, 'get_db', AsyncMock(return_value=db))
    app = web.Application()
    posts.setup_routes(app)
    client = await aiohttp_client(app)
    response = await client.get('/timeline?session_id=default&limit=1')
    result = await response.json()
    assert [item['id'] for item in result['posts']] == [visible]
    assert result['has_more'] is False
    assert (await client.get('/timeline?session_id=missing')).status == 400


@pytest.mark.asyncio
async def test_queue_listing_filters_by_persisted_session(db, monkeypatch):
    from aiohttp.test_utils import make_mocked_request
    agents = importlib.import_module('vibes.routes.agents')
    followups = importlib.import_module('vibes.followups')
    store = importlib.import_module('vibes.sessions').SessionStore(db)
    other = await store.create('Queue scope')
    a = await db.create_interaction({'type': 'user', 'content': 'default'})
    b = await db.create_interaction({'type': 'user', 'content': 'other', 'session_id': other['id']})
    followups.reset_state()
    try:
        followups.queue_followup(thread_id=a, agent_id='default', message_id=a, content='visible')
        followups.queue_followup(thread_id=b, agent_id='default', message_id=b, content='hidden')
        followups.defer_steer(thread_id=b, agent_id='default', message_id=b, content='hidden steer')
        monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
        response = await agents.get_agent_queue(make_mocked_request('GET', '/agent/queue?session_id=default'))
        import json
        result = json.loads(response.text)
        assert [item['content'] for item in result['items']] == ['visible']
        assert result['pending_steers'] == []
    finally:
        followups.reset_state()
