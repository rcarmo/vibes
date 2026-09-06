import importlib
from unittest.mock import AsyncMock
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
