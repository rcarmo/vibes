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
