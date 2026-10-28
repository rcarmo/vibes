"""Turn-captured steering signals exactly one native owner, never idle work."""

import asyncio
import json
from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer, make_mocked_request

from vibes.db import Database
from vibes.followup_store import FollowupStore
from vibes.routes import classic_queue as routes, agents
from vibes.sessions import SessionStore


async def setup(db, monkeypatch, session='default'):
    from vibes import pi_client
    monkeypatch.setattr(routes, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(routes, 'broadcast_session_event', AsyncMock())
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda _: 'pi')
    root = await db.create_interaction({'type': 'user_message', 'content': 'root', 'session_id': session})
    message = await db.create_interaction({'type': 'user_message', 'content': 'steer me', 'session_id': session, 'thread_id': root})
    item = await FollowupStore(db).enqueue(thread_id=root, message_id=message, agent_id='default', content='steer me')
    await db.begin_turn('captured', root, 'default')
    runtime = pi_client._runtimes.get(session)
    lock = asyncio.Lock()
    await lock.acquire()
    monkeypatch.setattr(runtime, 'request_lock', lock)
    monkeypatch.setattr(runtime, 'active_turn_id', 'captured')
    task = Mock(done=Mock(return_value=False))
    monkeypatch.setattr(runtime, 'current_request_task', task)
    monkeypatch.setattr(runtime, 'agent_proc', Mock(returncode=None))
    writer = Mock()
    monkeypatch.setattr(runtime, 'agent_writer', writer)
    monkeypatch.setattr(runtime.session_selector, 'active', session)
    monkeypatch.setattr(runtime.session_selector, 'uncertain', False)
    app = web.Application()
    routes.setup_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client, item, runtime, writer


@pytest.mark.asyncio
async def test_real_native_signal_once_and_uncertain_after_fresh_reopen(db, monkeypatch):
    client, item, _, writer = await setup(db, monkeypatch)
    path = f"/api/sessions/default/queue/{item['row_id']}/steer"
    try:
        responses = await asyncio.gather(*[client.post(path, json={'active_turn_id': 'captured'}) for _ in range(2)])
        assert sorted(result.status for result in responses) == [202, 409]
        writer.write.assert_called_once()
        assert json.loads(writer.write.call_args.args[0]) == {'type': 'steer', 'message': 'steer me'}
        rows = await FollowupStore(db).list()
        assert rows[0]['state'] == 'uncertain'
        reopened = Database(db.db_path)
        await reopened.connect()
        try:
            assert (await FollowupStore(reopened).list())[0]['state'] == 'uncertain'
            assert await FollowupStore(reopened).claim(thread_id=item['thread_id'], agent_id='default') is None
        finally:
            await reopened.close()
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['turn', 'task', 'idle', 'selector', 'dead', 'no-writer'])
async def test_runtime_changes_after_db_claim_preserve_provably_unsent_item(db, monkeypatch, mutation):
    from vibes import pi_client
    client, item, runtime, writer = await setup(db, monkeypatch)
    original = pi_client.steer_chat_turn

    def race(*args):
        if mutation == 'turn':
            runtime.active_turn_id = 'promoted'
        elif mutation == 'task':
            runtime.current_request_task = Mock(done=Mock(return_value=False))
        elif mutation == 'idle':
            runtime.request_lock.release()
        elif mutation == 'selector':
            runtime.session_selector.uncertain = True
        elif mutation == 'dead':
            runtime.agent_proc.returncode = 1
        else:
            runtime.agent_writer = None
        return original(*args)

    monkeypatch.setattr(pi_client, 'steer_chat_turn', race)
    try:
        response = await client.post(f"/api/sessions/default/queue/{item['row_id']}/steer", json={'active_turn_id': 'captured'})
        assert response.status == 409
        assert (await FollowupStore(db).list())[0]['state'] == 'pending'
        writer.write.assert_not_called()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_write_failure_is_ambiguous_never_replay(db, monkeypatch):
    client, item, _, writer = await setup(db, monkeypatch)
    writer.write.side_effect = OSError('private transport error')
    path = f"/api/sessions/default/queue/{item['row_id']}/steer"
    try:
        response = await client.post(path, json={'active_turn_id': 'captured'})
        assert response.status == 409 and 'private' not in await response.text()
        assert (await FollowupStore(db).list())[0]['state'] == 'uncertain'
        response = await client.post(path, json={'active_turn_id': 'captured'})
        assert response.status == 409
        writer.write.assert_called_once()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_disconnect_waits_for_shielded_admission_without_replay(db, monkeypatch):
    client, item, _, writer = await setup(db, monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()
    original = routes._settle_steer

    async def delayed(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(routes, '_settle_steer', delayed)
    request = make_mocked_request('POST', '/steer', match_info={'id': 'default', 'item_id': str(item['row_id'])})
    request.json = AsyncMock(return_value={'active_turn_id': 'captured'})
    task = asyncio.create_task(routes.steer(request))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (await FollowupStore(db).list())[0]['state'] == 'uncertain'
        writer.write.assert_called_once()
    finally:
        release.set()
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['acp', 'copilot-ffi'])
async def test_other_backends_unsupported_and_item_preserved(db, monkeypatch, mode):
    client, item, _, writer = await setup(db, monkeypatch)
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda _: mode)
    try:
        response = await client.post(f"/api/sessions/default/queue/{item['row_id']}/steer", json={'active_turn_id': 'captured'})
        assert response.status == 501
        assert (await FollowupStore(db).list())[0]['state'] == 'pending'
        writer.write.assert_not_called()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_foreign_stale_archived_attachment_and_ambiguous_turn_rejected(db, monkeypatch):
    client, item, _, writer = await setup(db, monkeypatch)
    other = await SessionStore(db).create('Foreign')
    try:
        response = await client.post(f"/api/sessions/{other['id']}/queue/{item['row_id']}/steer", json={'active_turn_id': 'captured'})
        assert response.status == 404
        response = await client.post(f"/api/sessions/default/queue/{item['row_id']}/steer", json={'active_turn_id': 'stale'})
        assert response.status == 409
        await db.begin_turn('another', item['thread_id'], 'default')
        response = await client.post(f"/api/sessions/default/queue/{item['row_id']}/steer", json={'active_turn_id': 'captured'})
        assert response.status == 409
        await db.end_turn('another')
        async with db.transaction() as connection:
            await connection.execute("UPDATE interactions SET data=json_set(data,'$.media_ids',json('[123]')) WHERE id=?", (item['message_id'],))
        response = await client.post(f"/api/sessions/default/queue/{item['row_id']}/steer", json={'active_turn_id': 'captured'})
        assert response.status == 409
        assert (await FollowupStore(db).list())[0]['state'] == 'pending'
        writer.write.assert_not_called()
    finally:
        await client.close()
