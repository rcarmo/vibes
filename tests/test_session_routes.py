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


@pytest.mark.asyncio
async def test_queue_cannot_steer_other_active_session(db, monkeypatch):
    from aiohttp.test_utils import make_mocked_request
    agents = importlib.import_module('vibes.routes.agents')
    followups = importlib.import_module('vibes.followups')
    store = importlib.import_module('vibes.sessions').SessionStore(db)
    other = await store.create('Other')
    a = await db.create_interaction({'type': 'user', 'content': 'default'})
    b = await db.create_interaction({'type': 'user', 'content': 'other', 'session_id': other['id']})
    followups.reset_state()
    try:
        item = followups.queue_followup(thread_id=b, agent_id='default', message_id=b, content='private')
        monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
        monkeypatch.setattr(agents, '_get_active_turn_for_agent', AsyncMock(return_value={'thread_id': a, 'turn_id': 'active'}))
        sender = AsyncMock()
        monkeypatch.setattr(agents, 'send_pi_rpc_fire_and_forget', sender)
        request = make_mocked_request('POST', '/agent/queue-steer')
        request.json = AsyncMock(return_value={'row_id': item['row_id']})
        response = await agents.steer_queue_item(request)
        assert response.status == 409
        assert followups.list_followups()[0]['row_id'] == item['row_id']
        sender.assert_not_awaited()
    finally:
        followups.reset_state()


@pytest.mark.asyncio
async def test_status_poll_excludes_other_session_turns(db, monkeypatch):
    from aiohttp.test_utils import make_mocked_request
    agents = importlib.import_module('vibes.routes.agents')
    store = importlib.import_module('vibes.sessions').SessionStore(db)
    other = await store.create('Status')
    root = await db.create_interaction({'type': 'user', 'content': 'work', 'session_id': other['id']})
    await db.begin_turn('scoped-poll', root, 'default')
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    import json
    result = json.loads((await agents.get_agent_status(make_mocked_request('GET', '/agents/status?session_id=default'))).text)
    assert result['active_turns'] == []
    result = json.loads((await agents.get_agent_status(make_mocked_request('GET', '/agents/status?session_id=' + other['id']))).text)
    assert result['active_turns'][0]['session_id'] == other['id']


@pytest.mark.asyncio
async def test_scoped_model_state_omits_raw_provider_configuration(db, aiohttp_client, monkeypatch):
    pi = importlib.import_module('vibes.pi_client')
    monkeypatch.setattr(routes, 'get_db', AsyncMock(return_value=db))
    inspect = AsyncMock(return_value={'success': True, 'data': {'model': {'id': 'model', 'provider': 'test', 'baseUrl': 'private-url', 'apiKey': 'secret'}, 'thinkingLevel': 'low', 'isCompacting': False}})
    monkeypatch.setattr(pi, 'inspect_model_state', inspect)
    app = web.Application()
    routes.setup_routes(app)
    client = await aiohttp_client(app)
    result = await (await client.get('/sessions/default/model-state')).json()
    assert result['model'] == {'id': 'model', 'provider': 'test'}
    assert result['thinking_level'] == 'low'
    inspect.assert_awaited_once_with('default')
    assert (await client.get('/sessions/missing/model-state')).status == 404


@pytest.mark.asyncio
async def test_model_mutation_route_scopes_validates_and_sanitizes(db, aiohttp_client, monkeypatch):
    pi = importlib.import_module('vibes.pi_client')
    monkeypatch.setattr(routes, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(routes, 'broadcast_event', AsyncMock())
    change = AsyncMock(return_value={'success': True, 'data': {'model': {'id': 'm', 'provider': 'p', 'baseUrl': 'private'}, 'thinkingLevel': 'low'}})
    monkeypatch.setattr(pi, 'change_chat_model', change)
    app = web.Application()
    routes.setup_routes(app)
    client = await aiohttp_client(app)
    result = await client.post('/sessions/default/model', json={'provider': 'p', 'model_id': 'm'})
    assert result.status == 200
    assert (await result.json())['model'] == {'id': 'm', 'provider': 'p'}
    change.assert_awaited_once_with('default', provider='p', model_id='m')
    assert (await client.post('/sessions/default/model', json={'unknown': True})).status == 400
    assert (await client.post('/sessions/missing/model', json={'thinking_level': 'low'})).status == 404
    change.side_effect = RuntimeError('busy')
    assert (await client.post('/sessions/default/model', json={'thinking_level': 'low'})).status == 409


@pytest.mark.asyncio
async def test_model_catalog_route_sanitizes_and_bounds(db, aiohttp_client, monkeypatch):
    pi = importlib.import_module('vibes.pi_client')
    monkeypatch.setattr(routes, 'get_db', AsyncMock(return_value=db))
    inspect = AsyncMock(return_value={'models': [{'id': 'm', 'provider': 'p', 'baseUrl': 'private'}] * 501, 'thinking_levels': ['off', 'low']})
    monkeypatch.setattr(pi, 'inspect_model_catalog', inspect)
    app = web.Application()
    routes.setup_routes(app)
    client = await aiohttp_client(app)
    result = await (await client.get('/sessions/default/models')).json()
    assert len(result['models']) == 500
    assert result['models'][0] == {'id': 'm', 'provider': 'p'}
    assert result['thinking_levels'] == ['off', 'low']
    inspect.return_value = None
    assert (await (await client.get('/sessions/default/models')).json())['available'] is False


@pytest.mark.asyncio
async def test_model_catalog_rejects_unusable_identities_and_metadata(db, aiohttp_client, monkeypatch):
    pi = importlib.import_module('vibes.pi_client')
    monkeypatch.setattr(routes, 'get_db', AsyncMock(return_value=db))
    inspect = AsyncMock(return_value={'models': [
        {'id': 'valid', 'provider': 'p', 'name': {'secret': 'no'}, 'reasoning': 'yes', 'contextWindow': True},
        {'id': '', 'provider': 'p'}, {'id': 'missing-provider'},
        {'id': 'bad\nidentity', 'provider': 'p'}, {'id': 123, 'provider': 'p'},
        {'id': 'full', 'provider': 'p', 'reasoning': False, 'contextWindow': 32000, 'name': 'Full'},
    ], 'thinking_levels': ['off', '', 'off', None, 'bad\nlevel', 'low']})
    monkeypatch.setattr(pi, 'inspect_model_catalog', inspect)
    app = web.Application()
    routes.setup_routes(app)
    client = await aiohttp_client(app)
    result = await (await client.get('/sessions/default/models')).json()
    assert result['models'] == [{'id': 'valid', 'provider': 'p'}, {'id': 'full', 'provider': 'p', 'reasoning': False, 'contextWindow': 32000, 'name': 'Full'}]
    assert result['thinking_levels'] == ['off', 'low']
    inspect.return_value = {'models': None, 'thinking_levels': None}
    result = await (await client.get('/sessions/default/models')).json()
    assert result == {'available': True, 'models': [], 'thinking_levels': []}


@pytest.mark.asyncio
async def test_archived_session_model_reads_do_not_inspect_live_backend(db, aiohttp_client, monkeypatch):
    from vibes.sessions import SessionStore
    pi = importlib.import_module('vibes.pi_client')
    store = SessionStore(db)
    session = await store.create('Archived model')
    await store.update(session['id'], archived=True)
    monkeypatch.setattr(routes, 'get_db', AsyncMock(return_value=db))
    state = AsyncMock()
    catalog = AsyncMock()
    monkeypatch.setattr(pi, 'inspect_model_state', state)
    monkeypatch.setattr(pi, 'inspect_model_catalog', catalog)
    app = web.Application()
    routes.setup_routes(app)
    client = await aiohttp_client(app)
    for suffix in ('model-state', 'models'):
        response = await client.get(f"/sessions/{session['id']}/{suffix}")
        assert response.status == 200
        assert (await response.json())['available'] is False
    state.assert_not_awaited()
    catalog.assert_not_awaited()
    assert (await client.post(f"/sessions/{session['id']}/model", json={'thinking_level': 'low'})).status == 404


@pytest.mark.asyncio
@pytest.mark.parametrize('thinking,compacting', [({'private': 'value'}, 'true'), ('bad\nlevel', 1), ('x' * 513, []), ('', {})])
async def test_model_state_rejects_malformed_thinking_and_compaction(db, aiohttp_client, monkeypatch, thinking, compacting):
    pi = importlib.import_module('vibes.pi_client')
    monkeypatch.setattr(routes, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(pi, 'inspect_model_state', AsyncMock(return_value={'success': True, 'data': {'thinkingLevel': thinking, 'isCompacting': compacting}}))
    app = web.Application()
    routes.setup_routes(app)
    client = await aiohttp_client(app)
    result = await (await client.get('/sessions/default/model-state')).json()
    assert result['thinking_level'] is None
    assert result['compacting'] is None


@pytest.mark.asyncio
async def test_model_mutation_filters_malformed_response_metadata(db, aiohttp_client, monkeypatch):
    pi = importlib.import_module('vibes.pi_client')
    monkeypatch.setattr(routes, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(pi, 'change_chat_model', AsyncMock(return_value={'success': True, 'data': {
        'model': {'id': 'm', 'provider': 'p', 'name': {'private': True}, 'reasoning': 'true', 'contextWindow': -1},
        'thinkingLevel': {'private': True},
    }}))
    app = web.Application()
    routes.setup_routes(app)
    client = await aiohttp_client(app)
    result = await (await client.post('/sessions/default/model', json={'provider': 'p', 'model_id': 'm'})).json()
    assert result['model'] == {'id': 'm', 'provider': 'p'}
    assert result['thinking_level'] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('values', [{'thinking_level': '   '}, {'thinking_level': 'low\n'}, {'provider': 'p\x7f', 'model_id': 'm'}, {'provider': 'p', 'model_id': '\x00m'}])
async def test_invalid_model_mutation_text_never_reaches_pi(db, aiohttp_client, monkeypatch, values):
    pi = importlib.import_module('vibes.pi_client')
    monkeypatch.setattr(routes, 'get_db', AsyncMock(return_value=db))
    change = AsyncMock()
    monkeypatch.setattr(pi, 'change_chat_model', change)
    app = web.Application()
    routes.setup_routes(app)
    client = await aiohttp_client(app)
    response = await client.post('/sessions/default/model', json=values)
    assert response.status == 400
    change.assert_not_awaited()


@pytest.mark.asyncio
async def test_model_preferences_api_is_bounded_and_does_not_mutate_runtime(db, aiohttp_client, monkeypatch):
    pi = importlib.import_module('vibes.pi_client')
    monkeypatch.setattr(routes, 'get_db', AsyncMock(return_value=db))
    change = AsyncMock()
    monkeypatch.setattr(pi, 'change_chat_model', change)
    app = web.Application()
    routes.setup_routes(app)
    client = await aiohttp_client(app)
    response = await client.get('/model-preferences')
    assert response.headers['Cache-Control'] == 'no-store'
    assert await response.json() == {'pins': [], 'scope': 'instance'}
    response = await client.put('/model-preferences', json={'pins': ['p/m', 'p/m']})
    assert await response.json() == {'pins': ['p/m'], 'scope': 'instance'}
    for payload in ({'pins': ['invalid']}, {'pins': [], 'secret': 'no'}, {}, [], {'pins': ['p/m'] * 101}):
        assert (await client.put('/model-preferences', json=payload)).status == 400
    assert (await (await client.get('/model-preferences')).json())['pins'] == ['p/m']
    change.assert_not_awaited()


@pytest.mark.asyncio
async def test_model_preferences_conditional_update_rejects_stale_snapshot(db, aiohttp_client, monkeypatch):
    monkeypatch.setattr(routes, 'get_db', AsyncMock(return_value=db))
    app = web.Application()
    routes.setup_routes(app)
    client = await aiohttp_client(app)
    initial = await client.get('/model-preferences')
    etag = initial.headers['ETag']
    first = await client.put('/model-preferences', json={'pins': ['p/first']}, headers={'If-Match': etag})
    assert first.status == 200
    assert first.headers['ETag'] != etag
    stale = await client.put('/model-preferences', json={'pins': ['p/stale']}, headers={'If-Match': etag})
    assert stale.status == 412
    assert (await (await client.get('/model-preferences')).json())['pins'] == ['p/first']
