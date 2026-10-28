"""Explicit SSE subscriptions resolve event ownership through persisted messages."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from vibes.routes import sse
from vibes.sessions import SessionStore


@pytest.mark.asyncio
async def test_scoped_clients_do_not_receive_foreign_unknown_or_forged_events(db, monkeypatch):
    monkeypatch.setattr(sse, 'get_db', AsyncMock(return_value=db))
    other = await SessionStore(db).create('Other event stream')
    a = await db.create_interaction({'type': 'user', 'content': 'private-a'})
    b = await db.create_interaction({'type': 'user', 'content': 'private-b', 'session_id': other['id']})
    qa, qb, legacy = asyncio.Queue(100), asyncio.Queue(100), asyncio.Queue(100)
    sse._clients.update([qa, qb, legacy])
    sse._session_clients.update({qa: 'default', qb: other['id']})
    try:
        await sse.broadcast_event('new_post', await db.get_interaction(a))
        assert qa.qsize() == 1 and qb.empty() and legacy.qsize() == 1
        await sse.broadcast_event('agent_draft', {'thread_id': b, 'session_id': other['id'], 'text': 'draft-b'})
        assert qa.qsize() == 1 and qb.qsize() == 1
        await sse.broadcast_event('agent_thought', {'thread_id': b, 'session_id': 'default', 'text': 'forged'})
        await sse.broadcast_event('unknown_private_event', {'session_id': 'default', 'text': 'unowned'})
        await sse.broadcast_event('agent_followup_queued', {'thread_id': 999999, 'content': 'missing'})
        assert qa.qsize() == 1 and qb.qsize() == 1
        await sse.broadcast_event('agent_queue_reordered', {'items': [{'thread_id': a}, {'thread_id': b}]})
        assert qa.qsize() == 1 and qb.qsize() == 1
        await sse.broadcast_event('agent_queue_reordered', {'items': [{'thread_id': a}]})
        assert qa.qsize() == 2 and qb.qsize() == 1
        await sse.broadcast_event('plan_updated', {'session_id': other['id'], 'markdown': 'plan-b', 'revision': 1})
        assert qa.qsize() == 2 and qb.qsize() == 2
        assert 'private-b' not in ''.join(list(qa._queue))
        assert 'draft-b' not in ''.join(list(qa._queue))
        await sse.broadcast_event('ui_theme', {'theme': 'default'})
        assert qa.qsize() == 3 and qb.qsize() == 3
    finally:
        for queue in [qa, qb, legacy]:
            sse._clients.discard(queue)
            sse._session_clients.pop(queue, None)


@pytest.mark.parametrize('query,expected', [({}, None), ({'chat_jid':'gi:default'}, 'default'),
    ({'session_id':'default'}, 'default'), ({'chat_jid':'gi:default','session_id':'default'}, 'default')])
def test_valid_session_selectors(query, expected):
    assert sse._requested_session(query) == expected


@pytest.mark.parametrize('query', [{'chat_jid':'foreign'}, {'chat_jid':'gi:'}, {'session_id':''},
    {'chat_jid':'gi:one','session_id':'two'}])
def test_invalid_session_selectors(query):
    with pytest.raises(ValueError):
        sse._requested_session(query)


@pytest.mark.asyncio
async def test_sse_http_validates_session_and_delivers_only_owned_event(db, monkeypatch):
    monkeypatch.setattr(sse, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(sse, '_schedule_restart_if_needed', lambda: None)
    other = await SessionStore(db).create('Foreign SSE')
    a = await db.create_interaction({'type':'user','content':'only-a'})
    b = await db.create_interaction({'type':'user','content':'only-b','session_id':other['id']})
    app = web.Application()
    sse.setup_routes(app)
    async with TestClient(TestServer(app, shutdown_timeout=.01)) as client:
        assert (await client.get('/sse/stream?chat_jid=bad')).status == 400
        assert (await client.get('/sse/stream?chat_jid=gi:missing')).status == 404
        stream = await client.get('/sse/stream?chat_jid=gi:default')
        assert stream.status == 200
        assert (await stream.content.readuntil(b'\n\n')).startswith(b'event: connected')
        await sse.broadcast_event('new_post', await db.get_interaction(b))
        await sse.broadcast_event('new_post', await db.get_interaction(a))
        event = await asyncio.wait_for(stream.content.readuntil(b'\n\n'), 1)
        payload = json.loads(event.decode().split('data: ')[1])
        assert payload['id'] == a and b'only-b' not in event
        stream.close()
