"""Real admission path and durable receipt recovery; no model calls."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from vibes.routes import classic, agents
from vibes.sessions import SessionStore


async def client_for(db, monkeypatch, enqueue):
    monkeypatch.setattr(classic, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda _: 'pi')
    monkeypatch.setattr(agents, '_is_agent_busy', lambda _: False)
    monkeypatch.setattr(agents, 'broadcast_event', AsyncMock())
    monkeypatch.setattr(agents, 'queue_link_preview_fetch', lambda *args: None)
    monkeypatch.setattr(agents, 'enqueue', enqueue)
    app = web.Application()
    classic.setup_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


@pytest.mark.asyncio
async def test_real_prompt_admission_recovery_idempotence_and_reconnect(db, monkeypatch):
    enqueue = Mock(return_value=True)
    client = await client_for(db, monkeypatch, enqueue)
    try:
        body = {'prompt': 'real admission', 'client_request_id': 'same-id'}
        first, retry = await asyncio.gather(*(client.post('/api/sessions/default/prompt', json=body) for _ in range(2)))
        assert first.status == retry.status == 201
        result = await first.json()
        assert await retry.json() == result
        assert result['turn_id'].startswith('turn-')
        assert result['user_message_id'] == str(result['user_message']['id'])
        enqueue.assert_called_once()
        assert enqueue.call_args.kwargs['admitted_turn_id'] == result['turn_id']
        row = await db.get_interaction(int(result['user_message_id']))
        assert row['data']['content'] == 'real admission' and row['data']['session_id'] == 'default'
        receipt = await (await client.get('/api/sessions/default/send-receipt?client_request_id=same-id')).json()
        assert receipt['receipt']['status'] == 'confirmed'
        assert receipt['receipt']['result'] == result
        assert receipt['receipt']['source_session_id'] == 'default'
        await db.close()
        await db.connect()
        assert (await (await client.get('/api/sessions/default/send-receipt?client_request_id=same-id')).json()) == receipt
        assert (await client.post('/api/sessions/default/prompt', json={**body, 'prompt':'different'})).status == 409
        enqueue.assert_called_once()
        async with db._connection.execute("SELECT COUNT(*) AS n FROM interactions WHERE type='user_message'") as cursor:
            assert (await cursor.fetchone())['n'] == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_unavailable_dispatch_has_rejected_receipt_and_does_not_retry(db, monkeypatch):
    enqueue = Mock(return_value=False)
    client = await client_for(db, monkeypatch, enqueue)
    try:
        body = {'prompt':'not admitted', 'client_request_id':'rejected'}
        assert (await client.post('/api/sessions/default/prompt', json=body)).status == 503
        assert (await client.post('/api/sessions/default/prompt', json=body)).status == 503
        enqueue.assert_called_once()
        receipt = (await (await client.get('/api/sessions/default/send-receipt?client_request_id=rejected')).json())['receipt']
        assert receipt['status'] == 'rejected' and receipt['result']['admitted'] is False
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_interrupted_admission_is_uncertain_and_never_redispatched(db, monkeypatch):
    from aiohttp.test_utils import make_mocked_request
    enqueue = Mock(return_value=True)
    client = await client_for(db, monkeypatch, enqueue)
    try:
        async def interrupted(*args):
            raise asyncio.CancelledError()
        monkeypatch.setattr(agents, 'broadcast_event', interrupted)
        body = {'prompt':'saved before interruption', 'client_request_id':'uncertain'}
        request = make_mocked_request('POST', '/api/sessions/default/prompt', match_info={'id':'default'})
        request.json = AsyncMock(return_value=body)
        with pytest.raises(asyncio.CancelledError):
            await classic.prompt(request)
        enqueue.assert_not_called()
        row = await classic._receipt(db, 'default', 'uncertain')
        assert row['state'] == 'uncertain' and row['message_id'] is not None
        assert (await client.post('/api/sessions/default/prompt', json=body)).status == 409
        enqueue.assert_not_called()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_prompt_rejects_foreign_media_parent_agent_and_scopes_receipts(db, monkeypatch):
    enqueue = Mock(return_value=True)
    client = await client_for(db, monkeypatch, enqueue)
    other = await SessionStore(db).create('Foreign prompt')
    root = await db.create_interaction({'type':'user', 'content':'other', 'session_id':other['id']})
    await db.begin_turn('foreign-turn', root, 'default')
    media_id = await db.create_media('foreign.txt','text/plain',b'foreign',metadata={'session_id':other['id']})
    try:
        for extra, status in [({'media':[{'media_id':media_id}]},400), ({'parent_turn_id':'foreign-turn'},409),
                              ({'parent_turn_id':'missing'},409), ({'target_agent_id':'another'},400),
                              ({'intent':'invalid'},400), ({'session_id':other['id']},400)]:
            assert (await client.post('/api/sessions/default/prompt',json={'prompt':'blocked',**extra})).status == status
        enqueue.assert_not_called()
        assert (await client.get('/api/sessions/default/send-receipt?client_request_id=unknown')).status == 404
        assert (await client.post('/api/sessions/missing/prompt', json={'prompt':'no'})).status == 404
        response = await client.post('/api/sessions/default/prompt',json={'prompt':'own','client_request_id':'own'})
        assert response.status == 201
        assert (await client.get(f"/api/sessions/{other['id']}/send-receipt?client_request_id=own")).status == 404
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_pending_receipt_and_failed_message_link_fail_closed(db, monkeypatch):
    enqueue = Mock(return_value=True)
    client = await client_for(db, monkeypatch, enqueue)
    try:
        async with db.transaction() as connection:
            await connection.execute("INSERT INTO prompt_receipts(session_id,client_request_id,fingerprint,state) VALUES ('default','pending','unknown','pending')")
        response = await client.post('/api/sessions/default/prompt',json={'prompt':'no replay','client_request_id':'pending'})
        assert response.status == 409
        with pytest.raises(ValueError):
            await db.create_interaction({'type':'user_message','content':'no orphan'},send_receipt=('default','missing'))
        async with db._connection.execute("SELECT COUNT(*) AS n FROM interactions") as cursor:
            assert (await cursor.fetchone())['n'] == 0
        enqueue.assert_not_called()
    finally:
        await client.close()
