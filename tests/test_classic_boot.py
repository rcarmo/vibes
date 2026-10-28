"""Classic boot policy and registry adapters preserve legacy/session boundaries."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from vibes.middleware import create_auth_middleware, create_cors_middleware, create_security_middleware
from vibes.routes import classic, sessions
from vibes.sessions import SessionStore


async def client_for(db, monkeypatch, authenticate=None):
    monkeypatch.setattr(classic, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(sessions, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(sessions, 'broadcast_event', AsyncMock())
    auth = create_auth_middleware() if authenticate is None else create_auth_middleware(authenticate)
    app = web.Application(middlewares=[create_cors_middleware(), create_security_middleware(), auth])
    sessions.setup_routes(app)
    classic.setup_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


@pytest.mark.asyncio
async def test_auth_free_policy_and_no_fake_login(db, monkeypatch):
    client = await client_for(db, monkeypatch)
    try:
        for path in ('/api/auth/status', '/api/auth/policy'):
            response = await client.get(path)
            assert response.status == 200 and response.headers['Cache-Control'] == 'no-store'
            assert response.headers['X-Content-Type-Options'] == 'nosniff'
            assert await response.json() == {'mode': 'single-user', 'enrolled': False, 'authenticated': True,
                                             'totp_enabled': False, 'browser_login_available': False,
                                             'setup_available': False, 'totp_login_available': False,
                                             'passkeys_enabled': False, 'passkey_login_available': False}
        response = await client.post('/api/auth/session', json={'code': '123456'})
        assert response.status == 404
        response = await client.get('/api/auth/status', headers={'Origin': 'https://foreign.invalid'})
        assert response.status == 403
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('allowed', [True, False])
async def test_external_auth_gate_cannot_be_reported_as_auth_free(db, monkeypatch, allowed):
    async def authenticate(request):
        return None if allowed else web.json_response({'error': 'Unauthorized'}, status=401)

    client = await client_for(db, monkeypatch, authenticate)
    try:
        response = await client.get('/api/auth/status')
        assert response.status == (501 if allowed else 401)
        assert 'authenticated' not in await response.json()
        response = await client.get('/api/sessions')
        assert response.status == (200 if allowed else 401)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_runtime_config_is_passive_allowlist_with_no_secret_or_model_claim(db, monkeypatch):
    client = await client_for(db, monkeypatch)
    config = SimpleNamespace(agent_name='Assistant', agent_avatar='https://private.invalid/?key=secret',
                             acp_agent_command='private-command', pi_model='private/model',
                             secret='not-returned')
    monkeypatch.setattr(classic, 'get_config', lambda: config)
    monkeypatch.setattr(classic.agents, '_resolve_agent_mode', lambda _: 'pi')
    try:
        response = await client.get('/api/runtime/config')
        assert response.status == 200 and response.headers['Cache-Control'] == 'no-store'
        assert await response.json() == {'assistant_name': 'Assistant',
                                         'agent': {'id': 'web', 'backend': 'pi'},
                                         'provider': None, 'model_id': None, 'thinking': None,
                                         'models': [], 'thinking_levels': [], 'model_state_available': False}
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_registry_projects_real_activity_ancestry_and_preserves_legacy(db, monkeypatch):
    store = SessionStore(db)
    child = await store.create('Child', 'default')
    archived = await store.create('Archived')
    await store.update(archived['id'], archived=True)
    root = await db.create_interaction({'type': 'user_message', 'content': 'private body', 'session_id': child['id']})
    await db.begin_turn('owned-turn', root, 'default')
    client = await client_for(db, monkeypatch)
    try:
        response = await client.get('/api/sessions')
        result = await response.json()
        rows = {row['id']: row for row in result['sessions']}
        assert rows[child['id']]['title'] == rows[child['id']]['name'] == 'Child'
        assert rows[child['id']]['parent_session_id'] == 'default'
        assert rows[child['id']]['scope'] == {'agent_id': 'web'}
        assert rows[child['id']]['state']['status'] == 'running'
        assert rows[archived['id']]['state']['archived_at']
        assert rows[archived['id']]['state']['archived_at_source'] == 'mutation'
        assert rows['default']['state']['status'] == 'idle'
        assert rows['default']['state']['archived_at'] is None
        assert rows['default']['state']['pinned'] is False
        assert rows['default']['capabilities']['fork'] is False
        assert 'private body' not in str(result)
        response = await client.get(f"/api/sessions/{child['id']}")
        assert (await response.json())['session'] == rows[child['id']]
        response = await client.get('/api/sessions?include_archived=false')
        assert archived['id'] not in {row['id'] for row in (await response.json())['sessions']}
        response = await client.get('/sessions')
        legacy = await response.json()
        assert archived['id'] not in {row['id'] for row in legacy['sessions']}
        assert all('title' not in row for row in legacy['sessions'])
        assert legacy['runtime_isolation'] is False
        response = await client.get('/api/sessions/missing')
        assert response.status == 404
        for suffix in ('?include_archived=1', '?agent_id=foreign', '?offset=2'):
            response = await client.get('/api/sessions' + suffix)
            assert response.status == 400
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_canonical_mutations_are_durable_and_fork_fails_without_child(db, monkeypatch):
    client = await client_for(db, monkeypatch)
    try:
        response = await client.post('/api/sessions', json={'title': 'New', 'agent_id': 'web'})
        assert response.status == 201
        session = (await response.json())['session']
        key = session['id']
        assert session['title'] == 'New' and session['scope']['agent_id'] == 'web'
        for action, update, field, expected in (
            ('rename', {'title': 'Renamed'}, 'title', 'Renamed'),
            ('pin', {'pinned': True}, 'pinned', True),
            ('archive', {}, 'archived', True), ('restore', {}, 'archived', False),
        ):
            response = await client.patch(f'/api/sessions/{key}', json={'action': action, **update})
            assert response.status == 200
            assert (await response.json())['session'][field] == expected
        before = len(await SessionStore(db).list(True))
        response = await client.post(f'/api/sessions/{key}/fork', json={'title': 'Not real fork'})
        assert response.status == 501
        assert len(await SessionStore(db).list(True)) == before
        response = await client.get(f'/api/sessions/{key}')
        stored = (await response.json())['session']
        assert stored['title'] == 'Renamed' and stored['pinned'] and not stored['archived']
        response = await client.patch('/api/sessions/missing', json={'action': 'archive'})
        assert response.status == 404
        response = await client.post('/api/sessions/missing/fork', json={})
        assert response.status == 404
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_mutations_reject_foreign_scope_invalid_and_silent_field_loss(db, monkeypatch):
    client = await client_for(db, monkeypatch)
    try:
        for payload in ([], {'title': 'New', 'agent_id': 'foreign'}, {'title': 'New', 'agent_id': []},
                        {'title': 'New', 'parent_session_id': 'default'}, {'name': 'legacy'}, {'title': ''}):
            response = await client.post('/api/sessions', json=payload)
            assert response.status == 400
        for payload in ({'action': 'pin', 'pinned': 'true'}, {'action': 'rename', 'title': None},
                        {'action': 'pin', 'pinned': None}, {'action': 'rename', 'title': ''},
                        {'action': 'archive', 'agent_id': 'foreign'}, {'action': []},
                        {'action': 'pin'}, {'name': 'legacy'}, []):
            response = await client.patch('/api/sessions/default', json=payload)
            assert response.status == 400
        response = await client.post('/api/sessions', data='{bad')
        assert response.status == 400
        assert len(await SessionStore(db).list(True)) == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_archive_rejects_live_descendants_and_retains_timestamp_until_restore(db, monkeypatch):
    store = SessionStore(db)
    parent = await store.create('Parent')
    child = await store.create('Child', parent['id'])
    grandchild = await store.create('Grandchild', child['id'])
    client = await client_for(db, monkeypatch)
    try:
        response = await client.patch(f"/api/sessions/{parent['id']}", json={'action': 'archive'})
        assert response.status == 400
        assert not (await store.get(parent['id']))['archived']
        await store.update(grandchild['id'], archived=True)
        await store.update(child['id'], archived=True)
        response = await client.patch(f"/api/sessions/{parent['id']}", json={'action': 'archive'})
        assert response.status == 200
        state = (await response.json())['session']['state']
        assert state['archived_at'] and state['archived_at_source'] == 'mutation'
        response = await client.patch(f"/api/sessions/{parent['id']}", json={'action': 'archive'})
        assert (await response.json())['session']['state']['archived_at'] == state['archived_at']
        response = await client.patch(f"/api/sessions/{child['id']}", json={'action': 'restore'})
        assert response.status == 400
        assert (await store.get(child['id']))['archived']
        await store.update(parent['id'], archived=False)
        assert (await store.get(parent['id']))['archived_at'] is None
        await store.update(child['id'], archived=False)
        assert not (await store.get(child['id']))['archived']
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_v13_archive_migration_preserves_rows_and_marks_observation_time(tmp_path):
    from vibes.db import Database, SCHEMA_VERSION
    path = str(tmp_path / 'v13.db')
    database = Database(path)
    await database.connect()
    store = SessionStore(database)
    archived = await store.create('Archived')
    await store.update(archived['id'], archived=True)
    async with database.transaction() as connection:
        await connection.execute('ALTER TABLE chat_sessions DROP COLUMN archived_at')
        await connection.execute('ALTER TABLE chat_sessions DROP COLUMN archived_at_source')
        await connection.execute('UPDATE schema_version SET version=13')
    await database.close()
    migrated = Database(path)
    await migrated.connect()
    try:
        row = await SessionStore(migrated).get(archived['id'])
        assert row['archived'] and row['name'] == 'Archived'
        assert row['archived_at'] and row['archived_at_source'] == 'migration-observed'
        assert (await SessionStore(migrated).get('default'))['archived_at'] is None
        async with migrated._connection.execute('SELECT version FROM schema_version') as cursor:
            assert (await cursor.fetchone())[0] == SCHEMA_VERSION
    finally:
        await migrated.close()
    reopened = Database(path)
    await reopened.connect()
    try:
        assert (await SessionStore(reopened).get(archived['id']))['archived_at'] == row['archived_at']
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_runtime_config_redacts_unknown_backend(db, monkeypatch):
    client = await client_for(db, monkeypatch)
    monkeypatch.setattr(classic.agents, '_resolve_agent_mode', lambda _: 'secret-command-value')
    try:
        response = await client.get('/api/runtime/config')
        data = await response.json()
        assert data['agent']['backend'] is None
        assert 'secret-command-value' not in str(data)
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('partial', ['one-column', 'both-columns'])
async def test_interrupted_v14_migration_recovers_without_overwriting_observation(tmp_path, partial):
    from vibes.db import Database, SCHEMA_VERSION
    path = str(tmp_path / 'partial.db')
    database = Database(path)
    await database.connect()
    row = await SessionStore(database).create('Archived')
    await SessionStore(database).update(row['id'], archived=True)
    async with database.transaction() as connection:
        if partial == 'one-column':
            await connection.execute('ALTER TABLE chat_sessions DROP COLUMN archived_at_source')
        await connection.execute("UPDATE chat_sessions SET archived_at='2026-01-02 03:04:05' WHERE id=?", (row['id'],))
        await connection.execute('UPDATE schema_version SET version=13')
    await database.close()
    migrated = Database(path)
    await migrated.connect()
    try:
        value = await SessionStore(migrated).get(row['id'])
        assert value['archived_at'] == '2026-01-02 03:04:05'
        assert value['archived_at_source'] == ('migration-observed' if partial == 'one-column' else 'mutation')
        async with migrated._connection.execute('SELECT version FROM schema_version') as cursor:
            assert (await cursor.fetchone())[0] == SCHEMA_VERSION
    finally:
        await migrated.close()


@pytest.mark.asyncio
async def test_deleted_during_update_is_404_not_false_success(db, monkeypatch):
    row = await SessionStore(db).create('Race')
    client = await client_for(db, monkeypatch)
    original = SessionStore.get
    reads = 0

    async def disappear(store, key):
        nonlocal reads
        result = await original(store, key)
        if key == row['id']:
            reads += 1
            if reads == 2:  # After adapter check, before store's write transaction.
                async with db.transaction() as connection:
                    await connection.execute('DELETE FROM chat_sessions WHERE id=?', (key,))
        return result

    monkeypatch.setattr(SessionStore, 'get', disappear)
    try:
        response = await client.patch(f"/api/sessions/{row['id']}", json={'action': 'rename', 'title': 'Gone'})
        assert response.status == 404
        sessions.broadcast_event.assert_not_awaited()
    finally:
        await client.close()
