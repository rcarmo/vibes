"""Canonical compaction uses real lane ownership and durable no-replay admission."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from vibes.compaction import KEY, Compactions
from vibes.copilot_host import CopilotHost
from vibes.db import Database
from vibes.routes import classic, agents
from vibes.sessions import SessionStore


async def setup(db, monkeypatch):
    host = CopilotHost()
    host.client = object()
    lane = host.lane('default')
    lane.client = host.client
    entered, finish = asyncio.Event(), asyncio.Event()
    calls = []

    async def compact(**kwargs):
        assert lane.turn_lock.locked()
        calls.append('compact')
        entered.set()
        await finish.wait()
        return {'success': True, 'messagesRemoved': 3, 'tokensRemoved': 100, 'summaryContent': 'private-summary'}

    async def abort(**kwargs):
        calls.append('abort')
        return {'aborted': True}

    history = SimpleNamespace(compact=compact, abort_manual_compaction=abort)
    session = SimpleNamespace(rpc=SimpleNamespace(history=history))
    lane.sessions['default'] = session
    monkeypatch.setattr(classic, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(agents, 'copilot_backend', host)
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda _: 'copilot-ffi')
    monkeypatch.setattr(agents, '_ffi_tasks', {})
    monkeypatch.setattr(agents, '_ffi_admission_locks', {})
    app = web.Application()
    classic.setup_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client, app[KEY], host, lane, history, entered, finish, calls


async def settled(manager):
    await asyncio.gather(*list(manager.tasks.values()))


@pytest.mark.asyncio
async def test_real_native_operation_id_activity_duplicate_and_completion(db, monkeypatch):
    client, manager, _, lane, _, entered, finish, calls = await setup(db, monkeypatch)
    try:
        capability = await (await client.get('/api/sessions/default/compaction')).json()
        assert capability['available'] and capability['token']
        token = capability['token']
        responses = await asyncio.gather(*[client.post('/api/sessions/default/compaction', json={'token': token}) for _ in range(2)])
        bodies = [await response.json() for response in responses]
        assert [response.status for response in responses] == [202, 202]
        assert bodies[0]['turn_id'] == bodies[1]['turn_id']
        await asyncio.wait_for(entered.wait(), 1)
        activity = await (await client.get('/api/sessions/default/activity')).json()
        assert activity['status'] == 'running' and activity['intent_key'] == 'compaction'
        assert activity['turn_id'] == bodies[0]['turn_id'] and lane.turn_lock.locked()
        # No prompt/message is created for native compaction.
        assert await db.get_timeline() == []
        finish.set()
        await settled(manager)
        data = await (await client.get('/api/sessions/default/compaction')).json()
        assert data['operation']['state'] == 'completed'
        assert data['operation']['result'] == {'messagesRemoved': 3, 'tokensRemoved': 100}
        assert 'private' not in str(data) and calls == ['compact']
        retry = await client.post('/api/sessions/default/compaction', json={'token': token})
        assert retry.status == 202 and (await retry.json())['state'] == 'completed'
        assert calls == ['compact'] and not lane.turn_lock.locked()
        assert (await (await client.get('/api/sessions/default/activity')).json())['status'] == 'idle'
    finally:
        finish.set()
        await client.close()


@pytest.mark.asyncio
async def test_cancel_exact_owner_remains_active_until_native_settlement(db, monkeypatch):
    client, manager, _, _, _, entered, finish, calls = await setup(db, monkeypatch)
    try:
        token = (await (await client.get('/api/sessions/default/compaction')).json())['token']
        operation = await (await client.post('/api/sessions/default/compaction', json={'token': token})).json()
        await asyncio.wait_for(entered.wait(), 1)
        other = await SessionStore(db).create('Other')
        response = await client.post(f"/api/sessions/{other['id']}/activity", json={'turn_id': operation['turn_id']})
        assert response.status == 409 and calls == ['compact']
        response = await client.post('/api/sessions/default/activity', json={'turn_id': operation['turn_id']})
        assert response.status == 202 and calls == ['compact', 'abort']
        data = await (await client.get('/api/sessions/default/activity')).json()
        assert data['status'] == 'cancelling'
        # Abort is an applied signal, not confirmation of compaction completion.
        assert manager.tasks
        finish.set()
        await settled(manager)
        assert not manager.tasks and await db.compaction_blocked('default')
        data = await (await client.get('/api/sessions/default/compaction')).json()
        assert data['operation']['state'] == 'uncertain'
    finally:
        finish.set()
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['session', 'client', 'message', 'busy'])
async def test_stale_capability_never_compacts(db, monkeypatch, change):
    client, manager, host, lane, _, _, finish, calls = await setup(db, monkeypatch)
    try:
        token = (await (await client.get('/api/sessions/default/compaction')).json())['token']
        if change == 'session':
            lane.sessions['default'] = object()
        elif change == 'client':
            host.client = object()
        elif change == 'message':
            await db.create_interaction({'type': 'user_message', 'content': 'new work'})
        else:
            await lane.turn_lock.acquire()
        response = await client.post('/api/sessions/default/compaction', json={'token': token})
        assert response.status == 409 and not calls and not manager.tasks
        if change == 'busy':
            lane.turn_lock.release()
    finally:
        finish.set()
        await client.close()


@pytest.mark.asyncio
async def test_timeout_marks_uncertain_poisoned_and_blocks_future_admission(db, monkeypatch):
    client, manager, host, lane, history, _, finish, calls = await setup(db, monkeypatch)
    history.compact = AsyncMock(side_effect=TimeoutError('private native error'))
    try:
        token = (await (await client.get('/api/sessions/default/compaction')).json())['token']
        response = await client.post('/api/sessions/default/compaction', json={'token': token})
        assert response.status == 202
        await settled(manager)
        data = await (await client.get('/api/sessions/default/compaction')).json()
        assert not data['available'] and data['operation']['state'] == 'uncertain'
        assert lane.poisoned and not lane.turn_lock.locked() and 'private' not in str(data)
        retry = await client.post('/api/sessions/default/compaction', json={'token': token})
        assert retry.status == 202 and history.compact.await_count == 1
        reopened = Database(db.db_path)
        await reopened.connect()
        try:
            assert await reopened.compaction_blocked('default')
            fresh = Compactions()
            assert not (await fresh.capability(reopened, host, 'default'))['available']
            assert (await fresh.admit(reopened, host, 'default', token))['state'] == 'uncertain'
        finally:
            await reopened.close()
    finally:
        finish.set()
        await client.close()


@pytest.mark.asyncio
async def test_recovery_and_shutdown_do_not_replay(db, monkeypatch):
    client, manager, host, lane, _, entered, finish, calls = await setup(db, monkeypatch)
    try:
        token = (await (await client.get('/api/sessions/default/compaction')).json())['token']
        response = await client.post('/api/sessions/default/compaction', json={'token': token})
        assert response.status == 202
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.wait_for(manager.close(db, host), 3)
        assert not manager.tasks and not lane.turn_lock.locked() and lane.poisoned
        assert calls == ['compact', 'abort']
        async with db.transaction() as connection:
            await connection.execute("INSERT INTO compaction_operations(token,session_id,turn_id,state) VALUES('crash','default','compact-crash','pending')")
        await Compactions().recover(db)
        async with db._connection.execute("SELECT state FROM compaction_operations WHERE token='crash'") as cursor:
            assert (await cursor.fetchone())[0] == 'uncertain'
    finally:
        finish.set()
        await client.close()


@pytest.mark.asyncio
async def test_transcript_and_archive_mutations_block_during_operation(db, monkeypatch):
    root = await db.create_interaction({'type': 'user_message', 'content': 'history'})
    client, manager, _, _, _, entered, finish, _ = await setup(db, monkeypatch)
    try:
        token = (await (await client.get('/api/sessions/default/compaction')).json())['token']
        assert (await client.post('/api/sessions/default/compaction', json={'token': token})).status == 202
        await asyncio.wait_for(entered.wait(), 1)
        with pytest.raises(ValueError, match='Compaction'):
            await db.create_interaction({'type': 'user_message', 'content': 'too late'})
        with pytest.raises(ValueError, match='Compaction'):
            await db.delete_interactions([root])
        with pytest.raises(ValueError, match='Compaction'):
            await db.set_interaction_thread_id(root, root)
        finish.set()
        await settled(manager)
        assert await db.create_interaction({'type': 'user_message', 'content': 'after'})
    finally:
        finish.set()
        await client.close()


@pytest.mark.asyncio
async def test_late_abort_retains_lane_until_signal_settles(db, monkeypatch):
    client, manager, host, lane, history, entered, finish, _ = await setup(db, monkeypatch)
    abort_entered, abort_finish = asyncio.Event(), asyncio.Event()

    async def abort(**kwargs):
        abort_entered.set()
        await abort_finish.wait()
        assert lane.turn_lock.locked()
        return {'aborted': True}

    history.abort_manual_compaction = abort
    try:
        token = (await (await client.get('/api/sessions/default/compaction')).json())['token']
        operation = await (await client.post('/api/sessions/default/compaction', json={'token': token})).json()
        await asyncio.wait_for(entered.wait(), 1)
        cancel = asyncio.create_task(manager.cancel(db, host, 'default', operation['turn_id']))
        await asyncio.wait_for(abort_entered.wait(), 1)
        finish.set()
        await asyncio.sleep(.02)
        assert lane.turn_lock.locked() and manager.tasks and await db.compaction_blocked('default')
        activity = await manager.activity(db, 'default')
        assert activity['status'] == 'cancelling'
        abort_finish.set()
        assert (await cancel)['status'] == 'cancelling'
        await settled(manager)
        assert not lane.turn_lock.locked() and lane.poisoned
        assert await db.compaction_blocked('default')
    finally:
        abort_finish.set()
        finish.set()
        await client.close()


@pytest.mark.asyncio
async def test_admission_disconnect_still_registers_single_native_owner(db, monkeypatch):
    from aiohttp.test_utils import make_mocked_request
    client, manager, _, _, _, entered, finish, calls = await setup(db, monkeypatch)
    token = (await (await client.get('/api/sessions/default/compaction')).json())['token']
    commit_entered, commit_finish = asyncio.Event(), asyncio.Event()
    original_commit = db._connection.commit

    async def delayed_commit():
        commit_entered.set()
        await commit_finish.wait()
        await original_commit()

    monkeypatch.setattr(db._connection, 'commit', delayed_commit)
    request = make_mocked_request('POST', '/compaction', app=client.server.app, match_info={'id': 'default'})
    request.json = AsyncMock(return_value={'token': token})
    task = asyncio.create_task(classic.compaction(request))
    try:
        await asyncio.wait_for(commit_entered.wait(), 1)
        task.cancel()
        commit_finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(entered.wait(), 1)
        finish.set()
        await settled(manager)
        assert calls == ['compact']
    finally:
        commit_finish.set()
        finish.set()
        await client.close()


@pytest.mark.asyncio
async def test_native_unsuccessful_completion_is_uncertain_not_replayable(db, monkeypatch):
    client, manager, _, lane, history, _, finish, _ = await setup(db, monkeypatch)
    history.compact = AsyncMock(return_value={'success': False, 'tokensRemoved': 0})
    try:
        token = (await (await client.get('/api/sessions/default/compaction')).json())['token']
        assert (await client.post('/api/sessions/default/compaction', json={'token': token})).status == 202
        await settled(manager)
        assert lane.poisoned and await db.compaction_blocked('default')
        state = await (await client.get('/api/sessions/default/compaction')).json()
        assert state['operation']['state'] == 'uncertain' and not state['available']
    finally:
        finish.set()
        await client.close()


@pytest.mark.asyncio
async def test_schema14_upgrade_preserves_history_and_no_replay_identity(tmp_path):
    path = str(tmp_path / 'upgrade.db')
    original = Database(path)
    await original.connect()
    root = await original.create_interaction({'type': 'user_message', 'content': 'preserve'})
    async with original.transaction() as connection:
        await connection.execute('DROP TABLE compaction_operations')
        await connection.execute('UPDATE schema_version SET version=14')
    await original.close()
    migrated = Database(path)
    await migrated.connect()
    try:
        assert (await migrated.get_interaction(root))['data']['content'] == 'preserve'
        async with migrated.transaction() as connection:
            await connection.execute("INSERT INTO compaction_operations(token,session_id,turn_id,state) VALUES('owned','default','compact-upgrade','pending')")
    finally:
        await migrated.close()
    reopened = Database(path)
    await reopened.connect()
    try:
        await Compactions().recover(reopened)
        assert await reopened.compaction_blocked('default')
        host = CopilotHost()
        recovered = await Compactions().admit(reopened, host, 'default', 'owned')
        assert recovered == {'turn_id': 'compact-upgrade', 'state': 'uncertain', 'recovered': True}
        assert not host.lanes  # Recovery never starts a native session.
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_cancel_false_is_uncertain_and_never_clears_durable_protection(db, monkeypatch):
    client, manager, _, lane, history, entered, finish, _ = await setup(db, monkeypatch)
    history.abort_manual_compaction = AsyncMock(return_value={'aborted': False})
    try:
        token = (await (await client.get('/api/sessions/default/compaction')).json())['token']
        op = await (await client.post('/api/sessions/default/compaction', json={'token': token})).json()
        await asyncio.wait_for(entered.wait(), 1)
        response = await client.post('/api/sessions/default/activity', json={'turn_id': op['turn_id']})
        assert response.status == 409 and lane.poisoned
        finish.set()
        await settled(manager)
        assert await db.compaction_blocked('default')
        capability = await (await client.get('/api/sessions/default/compaction')).json()
        assert capability['operation']['state'] == 'uncertain'
    finally:
        finish.set()
        await client.close()


@pytest.mark.asyncio
async def test_registry_and_archive_follow_durable_compaction_state(db):
    store = SessionStore(db)
    other = await store.create('Compacting')
    async with db.transaction() as connection:
        await connection.execute("INSERT INTO compaction_operations(token,session_id,turn_id,state) VALUES('registry',?,'compact-registry','running')", (other['id'],))
    rows = {row['id']: row for row in await store.list(True)}
    assert rows[other['id']]['is_running'] and not rows['default']['is_running']
    with pytest.raises(ValueError, match='Compaction'):
        await store.update(other['id'], archived=True)
    with pytest.raises(ValueError, match='Compaction'):
        await store.delete_empty(other['id'])
    await Compactions().recover(db)
    assert not (await store.list(True, session_id=other['id']))[0]['is_running']
    assert await db.compaction_blocked(other['id'])
