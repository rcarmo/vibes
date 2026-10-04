import importlib
from unittest.mock import AsyncMock
from aiohttp import web
import pytest

from vibes.routes import pi_tools
from vibes.agent_attachments import pi_token


@pytest.mark.asyncio
async def test_pi_messages_tool_uses_active_session_scope(db, aiohttp_client, monkeypatch):
    from vibes.sessions import SessionStore
    other = await SessionStore(db).create('Other')
    current_id = await db.create_interaction({'type': 'user_message', 'content': 'current secret', 'session_id': 'default'})
    other_id = await db.create_interaction({'type': 'user_message', 'content': 'other secret', 'session_id': other['id']})
    pi = importlib.import_module('vibes.pi_client')
    pi._state.session_selector.active = 'default'
    pi._state.session_selector.uncertain = False
    monkeypatch.setattr(pi_tools, 'get_db', AsyncMock(return_value=db))
    app = web.Application()
    pi_tools.setup_routes(app)
    client = await aiohttp_client(app)
    response = await client.post('/internal/pi-tools/messages', headers={'Authorization': 'Bearer ' + pi_token('default')}, json={'action': 'get', 'row_ids': [current_id, other_id]})
    assert response.status == 200
    result = await response.json()
    assert [item['row_id'] for item in result['messages']] == [current_id]
    assert result['missing_row_ids'] == [other_id]
    window = await client.post('/internal/pi-tools/messages', headers={'Authorization': 'Bearer ' + pi_token('default')}, json={
        'action': 'get', 'row_ids': [current_id], 'context_before': 1, 'context_after': 1,
    })
    assert window.status == 200
    assert all(item['row_id'] != other_id for item in (await window.json())['messages'])


@pytest.mark.asyncio
async def test_pi_messages_tool_rejects_uncertain_session(db, aiohttp_client, monkeypatch):
    pi = importlib.import_module('vibes.pi_client')
    pi._state.session_selector.active = 'default'
    pi._state.session_selector.uncertain = True
    monkeypatch.setattr(pi_tools, 'get_db', AsyncMock(return_value=db))
    app = web.Application()
    pi_tools.setup_routes(app)
    client = await aiohttp_client(app)
    assert (await client.post('/internal/pi-tools/messages', headers={'Authorization': 'Bearer ' + pi_token('default')}, json={'action': 'get', 'row_ids': [1]})).status == 409


@pytest.mark.asyncio
async def test_named_pi_token_cannot_read_other_chat(db, aiohttp_client, monkeypatch):
    from vibes import pi_client
    from vibes.sessions import SessionStore
    other = await SessionStore(db).create('Named')
    public = await db.create_interaction({'content': 'default secret'})
    private = await db.create_interaction({'content': 'named secret', 'session_id': other['id']})
    owner = pi_client._runtimes.get(other['id'])
    owner.session_selector.active = other['id']
    owner.session_selector.uncertain = False
    pi_client._runtimes.get('default').session_selector.active = 'default'
    monkeypatch.setattr(pi_tools, 'get_db', AsyncMock(return_value=db))
    app = web.Application()
    pi_tools.setup_routes(app)
    client = await aiohttp_client(app)
    payload = {'action': 'get', 'row_ids': [public, private]}
    assert (await client.post('/internal/pi-tools/messages', json=payload)).status == 403
    response = await client.post('/internal/pi-tools/messages', json=payload,
                                 headers={'Authorization': 'Bearer ' + pi_token(other['id'])})
    assert response.status == 200
    result = await response.json()
    assert [row['row_id'] for row in result['messages']] == [private]
    assert result['missing_row_ids'] == [public]
    assert (await client.post('/internal/pi-tools/messages', json=payload,
            headers={'Authorization': 'Bearer ' + pi_token(other['id']), 'Origin': 'http://localhost'})).status == 403
