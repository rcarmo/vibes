"""Canonical queue compare-and-set preserves durable identities and ownership."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from vibes.db import Database
from vibes.followup_store import FollowupStore
from vibes.routes import classic_queue as routes
from vibes.sessions import SessionStore


async def client_for(db, monkeypatch):
    monkeypatch.setattr(routes, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(routes, 'broadcast_session_event', AsyncMock())
    app = web.Application()
    routes.setup_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


async def queued(db, content='work', session='default', root=None, steer=False):
    if root is None:
        root = await db.create_interaction({'type': 'user_message', 'content': 'root', 'session_id': session})
    message = await db.create_interaction({'type': 'user_message', 'content': content, 'session_id': session, 'thread_id': root})
    return await FollowupStore(db).enqueue(thread_id=root, agent_id='default', message_id=message, content=content, steer=steer)


@pytest.mark.asyncio
async def test_queue_snapshot_and_atomic_order_scope(db, monkeypatch):
    first = await queued(db, 'one')
    other = await SessionStore(db).create('Other')
    foreign = await queued(db, 'foreign', other['id'])
    second = await queued(db, 'two')
    steer = await queued(db, 'steer', steer=True)
    uncertain = await queued(db, 'uncertain')
    async with db.transaction() as connection:
        await connection.execute("UPDATE followup_queue SET state='uncertain' WHERE sequence=?", (-uncertain['row_id'],))
    await db.begin_turn('owned-turn', first['thread_id'], 'default')
    client = await client_for(db, monkeypatch)
    try:
        response = await client.get('/api/sessions/default/queue')
        data = await response.json()
        assert data['active_turn_id'] == 'owned-turn'
        assert [row['id'] for row in data['items']] == [str(first['row_id']), str(second['row_id'])]
        assert [row['id'] for row in data['pending_steers']] == [str(steer['row_id'])]
        assert [row['id'] for row in data['uncertain']] == [str(uncertain['row_id'])]
        assert 'claim_token' not in str(data) and 'foreign' not in str(data)
        expected = [row['id'] for row in data['items']]
        response = await client.patch('/api/sessions/default/queue', json={'expected': expected, 'order': expected[::-1]})
        assert response.status == 200 and [row['id'] for row in (await response.json())['items']] == expected[::-1]
        stale = await client.patch('/api/sessions/default/queue', json={'expected': expected, 'order': expected[::-1]})
        assert stale.status == 409
        rows = await FollowupStore(db).list()
        assert next(row for row in rows if row['row_id'] == foreign['row_id'])['content'] == 'foreign'
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_concurrent_reorder_one_wins_and_reopen_retains_order(db, monkeypatch):
    rows = [await queued(db, str(i)) for i in range(3)]
    expected = [str(row['row_id']) for row in rows]
    client = await client_for(db, monkeypatch)
    try:
        responses = await asyncio.gather(*[client.patch('/api/sessions/default/queue', json={'expected': expected, 'order': expected[::-1]}) for _ in range(2)])
        assert sorted(response.status for response in responses) == [200, 409]
        reopened = Database(db.db_path)
        await reopened.connect()
        try:
            actual = await FollowupStore(reopened).list()
            assert [str(row['row_id']) for row in actual] == expected[::-1]
        finally:
            await reopened.close()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_claim_or_new_enqueue_invalidates_expected_and_preserves_every_item(db, monkeypatch):
    first = await queued(db)
    client = await client_for(db, monkeypatch)
    try:
        expected = [str(first['row_id'])]
        added = await queued(db, 'added')
        response = await client.patch('/api/sessions/default/queue', json={'expected': expected, 'order': expected})
        assert response.status == 409
        claimed = await FollowupStore(db).claim(thread_id=first['thread_id'], agent_id='default')
        expected.append(str(added['row_id']))
        response = await client.patch('/api/sessions/default/queue', json={'expected': expected, 'order': expected[::-1]})
        assert response.status == 409
        assert claimed['state'] == 'claimed'
        assert len(await FollowupStore(db).list()) == 2
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_remove_preserves_transcript_and_uncertain_or_foreign_work(db, monkeypatch):
    first = await queued(db)
    uncertain = await queued(db)
    async with db.transaction() as connection:
        await connection.execute("UPDATE followup_queue SET state='uncertain' WHERE sequence=?", (-uncertain['row_id'],))
    other = await SessionStore(db).create('Other')
    foreign = await queued(db, session=other['id'])
    client = await client_for(db, monkeypatch)
    try:
        response = await client.delete(f"/api/sessions/default/queue/{foreign['row_id']}")
        assert response.status == 404
        response = await client.delete(f"/api/sessions/default/queue/{uncertain['row_id']}")
        assert response.status == 409
        response = await client.delete(f"/api/sessions/default/queue/{first['row_id']}")
        assert response.status == 200
        assert await db.get_interaction(first['message_id'])
        assert len(await FollowupStore(db).list()) == 2
        response = await client.post(f"/api/sessions/default/queue/{uncertain['row_id']}/steer", json={'active_turn_id': 'captured'})
        assert response.status == 409
        assert len(await FollowupStore(db).list()) == 2
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_strict_ids_queries_missing_sessions_and_reorder_sets(db, monkeypatch):
    row = await queued(db)
    client = await client_for(db, monkeypatch)
    key = str(row['row_id'])
    try:
        for data in ({}, [], {'expected': [key], 'order': [key, key]}, {'expected': [key], 'order': []},
                     {'expected': [row['row_id']], 'order': [row['row_id']]}, {'expected': ['-0'], 'order': ['-0']},
                     {'expected': [key], 'order': [key], 'session_id': 'foreign'}):
            response = await client.patch('/api/sessions/default/queue', json=data)
            assert response.status == 400
        response = await client.get('/api/sessions/default/queue?agent_id=foreign')
        assert response.status == 400
        response = await client.get('/api/sessions/missing/queue')
        assert response.status == 404
        for key in ('0', '1', 'true', '-01'):
            response = await client.delete('/api/sessions/default/queue/' + key)
            assert response.status == 400
        response = await client.post(f"/api/sessions/default/queue/{row['row_id']}/steer", json={})
        assert response.status == 400
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_receipt_identity_projected_but_unrelated_source_and_tokens_not_exposed(db, monkeypatch):
    good = await queued(db, 'good')
    invalid = await queued(db, 'invalid')
    async with db.transaction() as connection:
        await connection.execute("INSERT INTO prompt_receipts(session_id,client_request_id,fingerprint,state,message_id) VALUES('default','request-one','private-fingerprint','pending',?)", (good['message_id'],))
        await connection.execute('UPDATE followup_queue SET message_id=? WHERE sequence=?', (good['message_id'], -invalid['row_id']))
    client = await client_for(db, monkeypatch)
    try:
        response = await client.get('/api/sessions/default/queue')
        data = await response.json()
        assert len(data['items']) == 1
        assert data['items'][0]['metadata'] == {'client_request_id': 'request-one'}
        assert 'private-fingerprint' not in str(data)
        response = await client.delete(f"/api/sessions/default/queue/{invalid['row_id']}")
        assert response.status == 404
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_tied_ordinals_reject_swap_instead_of_false_ack(db, monkeypatch):
    first, second = await queued(db, 'one'), await queued(db, 'two')
    async with db.transaction() as connection:
        await connection.execute('UPDATE followup_queue SET ordinal=1')
    ids = [str(first['row_id']), str(second['row_id'])]
    client = await client_for(db, monkeypatch)
    try:
        response = await client.patch('/api/sessions/default/queue', json={'expected': ids, 'order': ids[::-1]})
        assert response.status == 409
        assert [row['row_id'] for row in await FollowupStore(db).list()] == [first['row_id'], second['row_id']]
    finally:
        await client.close()
