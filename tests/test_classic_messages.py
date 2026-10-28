"""Conversation adapters page and mutate only persisted session-owned rows."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from vibes.followup_store import FollowupStore
from vibes.routes import classic_messages as routes, sse
from vibes.sessions import SessionStore


async def client_for(db, monkeypatch):
    monkeypatch.setattr(routes, 'get_db', AsyncMock(return_value=db))
    app = web.Application()
    routes.setup_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


async def post(db, content='needle', session='default', kind='user_message', **extra):
    return await db.create_interaction({'type': kind, 'content': content, 'session_id': session, **extra})


@pytest.mark.asyncio
async def test_history_pages_visible_records_stable_ids_and_projection(db, monkeypatch):
    other = await SessionStore(db).create('Other')
    first = await post(db, 'first')
    await post(db, 'private tool output', kind='tool_result')
    await post(db, 'foreign', session=other['id'])
    middle = await post(db, 'reply', kind='agent_response', thread_id=first, content_blocks=[{'type': 'text', 'text': 'reply'}])
    last = await post(db, 'last', kind='reply', thread_id=first)
    client = await client_for(db, monkeypatch)
    try:
        response = await client.get('/api/sessions/default/messages?limit=2&view=conversation')
        data = await response.json()
        assert response.status == 200 and response.headers['Cache-Control'] == 'no-store'
        assert [row['id'] for row in data['messages']] == [str(middle), str(last)]
        assert data['has_more'] and data['before'] == str(middle) and data['after'] == str(last)
        row = data['messages'][0]
        assert row['display_row_id'] == middle and row['role'] == 'assistant'
        assert row['reply_to_id'] == str(first) and row['payload']['content_blocks']
        older = await client.get(f'/api/sessions/default/messages?limit=2&before={middle}')
        assert [row['id'] for row in (await older.json())['messages']] == [str(first)]
        newer = await client.get(f'/api/sessions/default/messages?limit=1&after={first}')
        data = await newer.json()
        assert [row['id'] for row in data['messages']] == [str(middle)] and data['has_more']
        assert 'foreign' not in str(data) and 'private tool output' not in str(data)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_history_and_search_validate_queries_missing_sessions_and_family(db, monkeypatch):
    child = await SessionStore(db).create('Child', 'default')
    foreign = await SessionStore(db).create('Foreign')
    root_id = await post(db)
    child_id = await post(db, session=child['id'])
    await post(db, session=foreign['id'])
    await post(db, kind='tool_result')
    client = await client_for(db, monkeypatch)
    try:
        for suffix in ('?limit=0', '?limit=101', '?before=bad', '?before=1&after=2', '?view=raw',
                       '?offset=2', '?limit=1&limit=2', '?before=-1'):
            response = await client.get('/api/sessions/default/messages' + suffix)
            assert response.status == 400
        for suffix in ('?q=', '?q=needle&scope=all', '?q=needle&offset=-1', '?q=needle&view=raw',
                       '?q=needle&limit=0', '?q=%22', '?q=needle&session_id=foreign'):
            response = await client.get('/api/sessions/default/search' + suffix)
            assert response.status == 400
        for resource in ('messages', 'search?q=needle'):
            response = await client.get('/api/sessions/missing/' + resource)
            assert response.status == 404
        response = await client.get(f"/api/sessions/{child['id']}/search?q=needle")
        assert [row['id'] for row in (await response.json())['messages']] == [str(child_id)]
        response = await client.get(f"/api/sessions/{child['id']}/search?q=needle&scope=root&limit=1")
        data = await response.json()
        assert data['has_more'] and len(data['messages']) == 1
        response = await client.get(f"/api/sessions/{child['id']}/search?q=needle&scope=root&offset=1")
        ids = {row['id'] for row in (await response.json())['messages']} | {data['messages'][0]['id']}
        assert ids == {str(root_id), str(child_id)}
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_delete_reply_never_deletes_root_and_cascade_requires_confirmation(db, monkeypatch):
    root = await post(db)
    reply = await post(db, kind='agent_response', thread_id=root)
    client = await client_for(db, monkeypatch)
    try:
        response = await client.delete(f'/api/sessions/default/messages/{root}')
        assert response.status == 409 and 'Replies exist' in (await response.json())['error']
        response = await client.delete(f'/api/sessions/default/messages/{reply}')
        assert response.status == 200 and (await response.json())['ids'] == [str(reply)]
        assert await db.get_interaction(root)
        reply = await post(db, kind='agent_response', thread_id=root)
        response = await client.delete(f'/api/sessions/default/messages/{root}?cascade=true')
        assert response.status == 200
        assert (await response.json())['deleted'] == 2
        assert await db.get_interaction(root) is None and await db.get_interaction(reply) is None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_delete_foreign_and_active_queued_messages_fail_closed(db, monkeypatch):
    other = await SessionStore(db).create('Other')
    foreign = await post(db, session=other['id'])
    root = await post(db)
    await db.begin_turn('active', root, 'default')
    client = await client_for(db, monkeypatch)
    try:
        response = await client.delete(f'/api/sessions/default/messages/{foreign}')
        assert response.status == 404 and await db.get_interaction(foreign)
        response = await client.delete(f'/api/sessions/default/messages/{root}')
        assert response.status == 409
        await db.end_turn('active')
        await FollowupStore(db).enqueue(thread_id=root, agent_id='default', content='queued', message_id=root)
        response = await client.delete(f'/api/sessions/default/messages/{root}')
        assert response.status == 409 and await db.get_interaction(root)
        for suffix in ('?cascade=1', '?cascade=TRUE', '?foreign=true'):
            response = await client.delete(f'/api/sessions/default/messages/{root}' + suffix)
            assert response.status == 400
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_delete_event_is_scoped_after_row_removed_media_and_receipts_retained(db, monkeypatch):
    other = await SessionStore(db).create('Other')
    media = await db.create_media('own.txt', 'text/plain', b'own', metadata={'session_id': 'default'})
    root = await post(db, media_ids=[media])
    async with db.transaction() as connection:
        await connection.execute("INSERT INTO prompt_receipts(session_id,client_request_id,fingerprint,state,message_id) VALUES('default','keep','fp','uncertain',?)", (root,))
    own_queue, foreign_queue, legacy_queue = [asyncio.Queue(maxsize=10) for _ in range(3)]
    monkeypatch.setattr(sse, '_clients', {own_queue, foreign_queue, legacy_queue})
    monkeypatch.setattr(sse, '_session_clients', {own_queue: 'default', foreign_queue: other['id']})
    client = await client_for(db, monkeypatch)
    try:
        response = await client.delete(f'/api/sessions/default/messages/{root}')
        assert response.status == 200
        event = own_queue.get_nowait()
        assert 'interaction_deleted' in event and 'gi:default' in event
        assert legacy_queue.qsize() == 1 and foreign_queue.empty()
        assert await db.get_media(media)
        async with db._connection.execute("SELECT state FROM prompt_receipts WHERE client_request_id='keep'") as cursor:
            assert (await cursor.fetchone())[0] == 'uncertain'
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_nested_cascade_and_active_reply_guard(db, monkeypatch):
    root = await post(db)
    reply = await post(db, kind='reply', thread_id=root)
    nested = await post(db, kind='reply', thread_id=reply)
    await db.begin_turn('busy', root, 'default')
    client = await client_for(db, monkeypatch)
    try:
        response = await client.delete(f'/api/sessions/default/messages/{reply}?cascade=true')
        assert response.status == 409 and await db.get_interaction(nested)
        await db.end_turn('busy')
        response = await client.delete(f'/api/sessions/default/messages/{root}?cascade=true')
        assert response.status == 200 and (await response.json())['deleted'] == 3
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_legacy_corrupt_cross_session_descendant_rejects_atomic_deletion(db, monkeypatch):
    other = await SessionStore(db).create('Other')
    root = await post(db)
    foreign = await post(db, session=other['id'])
    # Model legacy/import corruption bypassing current insertion checks.
    async with db.transaction() as connection:
        await connection.execute("UPDATE interactions SET data=json_set(data,'$.thread_id',?) WHERE id=?", (root, foreign))
    client = await client_for(db, monkeypatch)
    try:
        response = await client.delete(f'/api/sessions/default/messages/{root}?cascade=true')
        assert response.status == 409
        assert await db.get_interaction(root) and await db.get_interaction(foreign)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_semantic_hidden_records_do_not_consume_pages_and_media_is_owned(db, monkeypatch):
    other = await SessionStore(db).create('Other')
    own = await db.create_media('own.txt', 'text/plain', b'own', metadata={'session_id': 'default'})
    foreign = await db.create_media('foreign.txt', 'text/plain', b'foreign', metadata={'session_id': other['id']})
    await post(db, kind='agent_response', kind_override='unused')
    async with db.transaction() as connection:
        await connection.execute("UPDATE interactions SET data=json_set(data,'$.kind','tool_result')")
    hidden_queue = await post(db, kind='system')
    async with db.transaction() as connection:
        await connection.execute("UPDATE interactions SET data=json_set(data,'$.kind','queue') WHERE id=?", (hidden_queue,))
    visible = await post(db, media_ids=[own, foreign, True, 999999], source='local')
    client = await client_for(db, monkeypatch)
    try:
        for path in ('messages?limit=1', 'search?q=needle&limit=1'):
            response = await client.get('/api/sessions/default/' + path)
            data = await response.json()
            assert [row['id'] for row in data['messages']] == [str(visible)] and not data['has_more']
            assert data['messages'][0]['payload']['media'] == [
                {'media_id': own, 'session_id': 'default', 'name': 'own.txt', 'content_type': 'text/plain'}]
            assert data['messages'][0]['payload']['source'] == 'local'
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_response_local_media_batch_chunks_preserves_order_duplicates_and_fresh_reads(db):
    import json
    refs = [await db.create_media(str(i), 'text/plain', b'x', metadata={'session_id': 'default'})
            for i in range(510)]
    rows = [{'id': i + 1, 'timestamp': '2026-10-28',
             'data': json.dumps({'type': 'user_message', 'media_ids': refs[i * 30:(i + 1) * 30]})}
            for i in range(17)]
    rows.append({'id': 100, 'timestamp': '2026-10-28',
                 'data': json.dumps({'type': 'user_message', 'media_ids': [refs[-1], refs[0], refs[-1], True, -1]})})
    queries = []
    original = db._connection._execute

    async def execute(function, *args, **kwargs):
        if getattr(function, '__name__', '') == 'execute':
            queries.append(args[0])
        return await original(function, *args, **kwargs)

    db._connection._execute = execute
    try:
        result = await routes.project_page(db, rows)
        assert len(queries) == 2  # 510 distinct IDs, chunked below SQLite's parameter limit.
        assert [row['id'] for row in result] == [str(row['id']) for row in rows]
        assert [item['media_id'] for item in result[-1]['payload']['media']] == [refs[-1], refs[0], refs[-1]]
        # Nothing is cached across responses, and ownership remains per message.
        async with db.transaction() as connection:
            await connection.execute("UPDATE media SET metadata=json_object('session_id','foreign') WHERE id=?", (refs[0],))
        await db.delete_media([refs[-1]])
        assert (await routes.project(db, rows[-1]))['payload']['media'] == []
    finally:
        db._connection._execute = original
