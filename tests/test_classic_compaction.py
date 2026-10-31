"""Unavailable compaction is explicit and never becomes a prompt or reset."""

from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from vibes.routes import classic, agents
from vibes.sessions import SessionStore


@pytest.mark.asyncio
async def test_compaction_capability_never_fabricates_native_operation(db, monkeypatch):
    monkeypatch.setattr(classic, 'get_db', AsyncMock(return_value=db))
    send = AsyncMock(side_effect=AssertionError('unexpected prompt'))
    compact = AsyncMock(side_effect=AssertionError('unowned native operation'))
    monkeypatch.setattr(agents, '_send_message', send)
    monkeypatch.setattr(agents.copilot_backend, 'compact', compact)
    app = web.Application()
    classic.setup_routes(app)
    archived = await SessionStore(db).create('Archived')
    await SessionStore(db).update(archived['id'], archived=True)
    async with TestClient(TestServer(app)) as client:
        for session in ('default', archived['id']):
            response = await client.get(f'/api/sessions/{session}/compaction')
            data = await response.json()
            assert response.status == 200 and not data['available'] and data['token'] is None
            assert response.headers['Cache-Control'] == 'no-store'
            response = await client.post(f'/api/sessions/{session}/compaction', json={'token': 'stale'})
            assert response.status == 409 and 'no work was started' in (await response.json())['error']
        for payload in ({}, [], {'token': None}, {'token': 'x', 'session_id': 'foreign'}):
            response = await client.post('/api/sessions/default/compaction', json=payload)
            assert response.status == 400
        response = await client.get('/api/sessions/default/compaction?backend=pi')
        assert response.status == 400
        response = await client.get('/api/sessions/missing/compaction')
        assert response.status == 404
        assert await db.get_timeline() == []
        assert await db.get_active_turns() == []
        send.assert_not_awaited()
        compact.assert_not_awaited()
