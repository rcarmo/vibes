"""Receipt identity and no-replay states survive new database instances."""

import asyncio
import sqlite3
from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer, make_mocked_request

from vibes.db import Database, SCHEMA_VERSION
from vibes.routes import agents, classic
from vibes.sessions import SessionStore


async def client_for(database, monkeypatch, enqueue):
    monkeypatch.setattr(classic, 'get_db', AsyncMock(return_value=database))
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=database))
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
async def test_same_request_id_in_two_sessions_is_independent(db, monkeypatch):
    enqueue = Mock(return_value=True)
    client = await client_for(db, monkeypatch, enqueue)
    other = await SessionStore(db).create('Other')
    originals = {}
    try:
        for session in ('default', other['id']):
            response = await client.post(f'/api/sessions/{session}/prompt',
                                         json={'prompt': f'for {session}', 'client_request_id': 'same-id'})
            assert response.status == 201
            originals[session] = await response.json()
        assert enqueue.call_count == 2
        for session in originals:
            response = await client.get(f'/api/sessions/{session}/send-receipt?client_request_id=same-id')
            receipt = (await response.json())['receipt']
            assert receipt['source_session_id'] == session and receipt['result'] == originals[session]
            response = await client.post(f'/api/sessions/{session}/prompt',
                                         json={'prompt': f'for {session}', 'client_request_id': 'same-id'})
            assert response.status == 201 and await response.json() == originals[session]
        assert enqueue.call_count == 2
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['confirmed', 'rejected', 'pending', 'uncertain', 'exception'])
async def test_no_replay_after_fresh_database_instance(tmp_path, monkeypatch, state):
    path = str(tmp_path / 'receipts.db')
    database = Database(path)
    await database.connect()
    enqueue = Mock(return_value=state != 'rejected')
    client = await client_for(database, monkeypatch, enqueue)
    body = {'prompt': 'durable request', 'client_request_id': 'restart'}
    original_result = None
    try:
        if state in {'pending', 'uncertain', 'exception'}:
            # Interrupt at the real shared admission seam before any provider I/O.
            if state == 'pending':
                original_claim = classic._claim

                async def crash_after_commit(*args):
                    await original_claim(*args)
                    raise RuntimeError('simulated abrupt boundary')

                with monkeypatch.context() as patch:
                    patch.setattr(classic, '_claim', crash_after_commit)
                    request = make_mocked_request('POST', '/api/sessions/default/prompt', match_info={'id': 'default'})
                    request.json = AsyncMock(return_value=body)
                    with pytest.raises(RuntimeError):
                        await classic.prompt(request)
            else:
                failure = asyncio.CancelledError() if state == 'uncertain' else RuntimeError('after message write')
                with monkeypatch.context() as patch:
                    patch.setattr(agents, 'broadcast_event', AsyncMock(side_effect=failure))
                    request = make_mocked_request('POST', '/api/sessions/default/prompt', match_info={'id': 'default'})
                    request.json = AsyncMock(return_value=body)
                    with pytest.raises(type(failure)):
                        await classic.prompt(request)
            row = await classic._receipt(database, 'default', 'restart')
            assert row['state'] == ('pending' if state == 'pending' else 'uncertain')
            if state != 'pending':
                assert row['message_id'] is not None
        else:
            response = await client.post('/api/sessions/default/prompt', json=body)
            assert response.status == (201 if state == 'confirmed' else 503)
            original_result = await response.json()
    finally:
        await client.close()
        await database.close()
    reopened = Database(path)
    assert reopened is not database
    await reopened.connect()
    never_enqueue = Mock(side_effect=AssertionError('replayed after reopen'))
    client = await client_for(reopened, monkeypatch, never_enqueue)
    try:
        response = await client.get('/api/sessions/default/send-receipt?client_request_id=restart')
        assert response.status == 200
        receipt = (await response.json())['receipt']
        assert receipt['status'] == ('uncertain' if state == 'exception' else state)
        response = await client.post('/api/sessions/default/prompt', json=body)
        expected = 201 if state == 'confirmed' else 503 if state == 'rejected' else 409
        assert response.status == expected
        result = await response.json()
        if original_result is not None:
            assert result == original_result == receipt['result']
        else:
            assert result['code'] == 'admission_uncertain'
        never_enqueue.assert_not_called()
    finally:
        await client.close()
        await reopened.close()


@pytest.mark.asyncio
async def test_v12_migration_creates_session_scoped_receipts_without_losing_messages(tmp_path):
    path = str(tmp_path / 'v12.db')
    database = Database(path)
    await database.connect()
    message = await database.create_interaction({'type': 'user_message', 'content': 'preserve'})
    other = await SessionStore(database).create('Other')
    async with database.transaction() as connection:
        await connection.execute('DROP TABLE prompt_receipts')
        await connection.execute('UPDATE schema_version SET version = 12')
    await database.close()
    migrated = Database(path)
    await migrated.connect()
    try:
        assert (await migrated.get_interaction(message))['data']['content'] == 'preserve'
        async with migrated.transaction() as connection:
            async with connection.execute('SELECT version FROM schema_version') as cursor:
                assert (await cursor.fetchone())[0] == SCHEMA_VERSION
            for session in ('default', other['id']):
                await connection.execute('INSERT INTO prompt_receipts '
                                         '(session_id,client_request_id,fingerprint,state) VALUES (?,?,?,?)',
                                         (session, 'same-id', 'request-fingerprint', 'pending'))
        with pytest.raises(sqlite3.IntegrityError):
            async with migrated.transaction() as connection:
                await connection.execute('INSERT INTO prompt_receipts '
                                         '(session_id,client_request_id,fingerprint,state) VALUES (?,?,?,?)',
                                         ('default', 'same-id', 'request-fingerprint', 'pending'))
    finally:
        await migrated.close()
    reopened = Database(path)
    await reopened.connect()
    try:
        assert (await classic._receipt(reopened, 'default', 'same-id'))['state'] == 'pending'
        assert (await classic._receipt(reopened, other['id'], 'same-id'))['state'] == 'pending'
        assert (await reopened.get_interaction(message))['data']['content'] == 'preserve'
    finally:
        await reopened.close()
