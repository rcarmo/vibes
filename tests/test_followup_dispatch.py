from unittest.mock import AsyncMock
import pytest
from vibes.followup_store import FollowupStore
from vibes.routes import agents


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['confirmed', 'unconfirmed', 'error'])
async def test_claimed_worker_retains_ambiguous_ownership(outcome, db, monkeypatch):
    store = FollowupStore(db)
    await store.enqueue(thread_id=1, agent_id='pi', message_id=1, content='next')
    owner = await store.claim(1, 'pi')
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    async def process(*args, **kwargs):
        assert (await store.list(thread_id=1, agent_id='pi'))[0]['state'] == 'admitted'
        assert kwargs['media_ids'] == [17]
        if outcome == 'error':
            raise RuntimeError('unconfirmed execution')
        return outcome == 'confirmed'
    monkeypatch.setattr(agents, 'process_agent_response', process)
    if outcome == 'error':
        with pytest.raises(RuntimeError):
            await agents._run_claimed_followup(owner, media_ids=[17])
    else:
        assert await agents._run_claimed_followup(owner, media_ids=[17]) == (outcome == 'confirmed')
    rows = await store.list(thread_id=1, agent_id='pi')
    if outcome == 'confirmed':
        assert rows == []
    else:
        assert rows[0]['state'] == 'uncertain'
        with pytest.raises(ValueError, match='Admission no longer owned'):
            await store.complete(owner)
        await store.recover()
        assert (await store.list(thread_id=1, agent_id='pi'))[0]['state'] == 'uncertain'
        assert await store.claim(1, 'pi') is None


@pytest.mark.asyncio
@pytest.mark.parametrize('accepted', [False, True])
async def test_real_pi_completion_promotes_persisted_claim(db, monkeypatch, accepted):
    from unittest.mock import Mock
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr('vibes.agent_attachments.referenced_media', AsyncMock(return_value=[]))
    root = await db.create_interaction({'type': 'user', 'content': 'run', 'session_id': 'default'})
    store = FollowupStore(db)
    item = await store.enqueue(thread_id=root, agent_id='default', message_id=root, content='next')
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda _: 'pi')
    monkeypatch.setattr(agents, '_dispatch_pi_thread', AsyncMock(return_value={'text': 'done', 'content': []}))
    monkeypatch.setattr(agents, 'broadcast_event', AsyncMock())
    admission = Mock(return_value=accepted)
    monkeypatch.setattr(agents, 'enqueue', admission)
    await agents.process_agent_response(root, 'run', 'default')
    admission.assert_called_once()
    assert admission.call_args.args[0] is agents._run_claimed_followup
    owner = admission.call_args.args[1]
    assert owner['row_id'] == item['row_id'] and owner['claim_token']
    rows = await store.list(thread_id=root, agent_id='default')
    assert rows[0]['state'] == ('claimed' if accepted else 'pending')


@pytest.mark.asyncio
async def test_ffi_loop_promotes_persisted_owner_once(db, monkeypatch):
    import asyncio
    root = await db.create_interaction({'type': 'user', 'content': 'run', 'session_id': 'default'})
    store = FollowupStore(db)
    await store.enqueue(thread_id=root, agent_id='default', message_id=root, content='next')
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(agents, 'broadcast_event', AsyncMock())
    calls = []
    async def process(thread, prompt, agent, **kwargs):
        calls.append(prompt)
        if prompt == 'next':
            assert (await store.list(thread_id=root, agent_id=agent))[0]['state'] == 'admitted'
        return True
    monkeypatch.setattr(agents, 'process_agent_response', process)
    agents.start_ffi_dispatch()
    try:
        agents._enqueue_ffi('default', root, 'run', 'default', [])
        task = agents._ffi_tasks['default']
        await asyncio.wait_for(task, 2)
        assert calls == ['run', 'next']
        assert await store.list(thread_id=root, agent_id='default') == []
    finally:
        await agents.stop_ffi_dispatch()


@pytest.mark.asyncio
async def test_ffi_shutdown_before_next_iteration_releases_prepared_claim(db, monkeypatch):
    import asyncio
    root = await db.create_interaction({'type': 'user', 'content': 'run', 'session_id': 'default'})
    store = FollowupStore(db)
    item = await store.enqueue(thread_id=root, agent_id='default', message_id=root, content='next')
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    async def broadcast(event, payload):
        if event == 'agent_followup_consumed':
            agents._ffi_closing = True
    monkeypatch.setattr(agents, 'broadcast_event', broadcast)
    process = AsyncMock(return_value=True)
    monkeypatch.setattr(agents, 'process_agent_response', process)
    agents.start_ffi_dispatch()
    try:
        agents._enqueue_ffi('default', root, 'run', 'default', [])
        await asyncio.wait_for(agents._ffi_tasks['default'], 2)
        process.assert_awaited_once()
        rows = await store.list(thread_id=root, agent_id='default')
        assert rows[0]['row_id'] == item['row_id'] and rows[0]['state'] == 'pending'
        assert 'default' not in agents._ffi_tasks
    finally:
        await agents.stop_ffi_dispatch()


@pytest.mark.asyncio
@pytest.mark.parametrize('steer', [False, True])
async def test_busy_message_route_persists_followup_or_emulated_steer(db, monkeypatch, steer):
    import json
    from types import SimpleNamespace
    from aiohttp.test_utils import make_mocked_request
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(agents, 'get_config', lambda: SimpleNamespace(default_agent='acp'))
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda _: 'acp')
    monkeypatch.setattr(agents, '_is_agent_busy', lambda _: True)
    root = await db.create_interaction({'type': 'user', 'content': 'active'})
    monkeypatch.setattr(agents, '_get_active_turn_for_agent', AsyncMock(return_value={'thread_id': root, 'turn_id': 'active'}))
    monkeypatch.setattr(agents, 'broadcast_event', AsyncMock())
    request = make_mocked_request('POST', '/agent/default/message', match_info={'agent_id': 'default'})
    request.json = AsyncMock(return_value={'content': 'persist me', 'mode': 'steer' if steer else 'queue'})
    response = await agents.send_message(request)
    assert response.status == 201
    payload = json.loads(response.body)
    rows = await FollowupStore(db).list(thread_id=payload['thread_id'], agent_id='default')
    assert len(rows) == 1
    assert rows[0]['content'] == 'persist me'
    assert rows[0]['mode'] == ('steer' if steer else 'queue')
    assert rows[0]['state'] == 'pending'
    assert rows[0]['emulated'] is steer
    assert (await db.get_interaction(rows[0]['message_id']))['data']['content'] == 'persist me'


@pytest.mark.asyncio
async def test_queue_route_separates_uncertain_rows_without_owner_tokens(db, monkeypatch):
    import json
    from aiohttp.test_utils import make_mocked_request
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    store = FollowupStore(db)
    await store.enqueue(thread_id=1, agent_id='pi', message_id=1, content='uncertain')
    await store.claim(1, 'pi')
    await store.recover()
    pending = await store.enqueue(thread_id=1, agent_id='pi', message_id=2, content='pending')
    response = await agents.get_agent_queue(make_mocked_request('GET', '/agent/queue?thread_id=1&agent_id=pi'))
    result = json.loads(response.body)
    assert [row['row_id'] for row in result['items']] == [pending['row_id']]
    assert result['uncertain'][0]['state'] == 'uncertain'
    assert result['pending_steers'] == []
    assert 'claim_token' not in response.text


@pytest.mark.asyncio
async def test_session_count_uses_only_persisted_pending_work(db):
    from vibes.sessions import SessionStore
    root = await db.create_interaction({'type': 'user', 'content': 'root', 'session_id': 'default'})
    store = FollowupStore(db)
    await store.enqueue(thread_id=root, agent_id='pi', message_id=root, content='uncertain')
    await store.claim(root, 'pi')
    await store.recover()
    await store.enqueue(thread_id=root, agent_id='pi', message_id=root, content='normal')
    await store.enqueue(thread_id=root, agent_id='pi', message_id=root, content='steer', steer=True)
    rows = await SessionStore(db).list()
    assert next(row for row in rows if row['id'] == 'default')['queued_count'] == 2


@pytest.mark.asyncio
async def test_persisted_mutation_routes_check_chat_and_claim_state(db, monkeypatch):
    import json
    from aiohttp.test_utils import make_mocked_request
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    broadcast = AsyncMock()
    monkeypatch.setattr(agents, 'broadcast_event', broadcast)
    root = await db.create_interaction({'type': 'user', 'content': 'root', 'session_id': 'default'})
    store = FollowupStore(db)
    rows = [await store.enqueue(thread_id=root, agent_id='pi', message_id=root, content=str(i)) for i in range(2)]
    async def request(handler, row_id, **fields):
        req = make_mocked_request('POST', '/agent/queue')
        req.json = AsyncMock(return_value={'row_id': row_id, **fields})
        return await handler(req)
    response = await request(agents.remove_queue_item, rows[0]['row_id'], session_id='foreign')
    assert response.status == 404
    broadcast.assert_not_awaited()
    response = await request(agents.reorder_queue_item, rows[0]['row_id'], direction='down', session_id='default')
    assert response.status == 200
    assert [row['row_id'] for row in json.loads(response.body)['items']] == [rows[1]['row_id'], rows[0]['row_id']]
    claim = await store.claim(root, 'pi')
    response = await request(agents.remove_queue_item, claim['row_id'], session_id='default')
    assert response.status == 404
    response = await request(agents.remove_queue_item, rows[0]['row_id'], session_id='default')
    assert response.status == 200
    assert json.loads(response.body)['item']['row_id'] == rows[0]['row_id']
    assert 'claim_token' not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel', [False, True])
async def test_persisted_steering_route_transfers_or_releases_same_row(db, monkeypatch, cancel):
    import asyncio
    import json
    from aiohttp.test_utils import make_mocked_request
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda _: 'pi' if cancel else 'acp')
    monkeypatch.setattr(agents, '_is_agent_busy', lambda _: True)
    monkeypatch.setattr(agents, '_get_active_turn_for_agent', AsyncMock(return_value=None))
    monkeypatch.setattr(agents, 'send_pi_rpc_fire_and_forget', AsyncMock(side_effect=asyncio.CancelledError()))
    broadcast = AsyncMock()
    monkeypatch.setattr(agents, 'broadcast_event', broadcast)
    root = await db.create_interaction({'type': 'user', 'content': 'root'})
    store = FollowupStore(db)
    rows = [await store.enqueue(thread_id=root, agent_id='default', message_id=root, content=str(i)) for i in range(3)]
    request = make_mocked_request('POST', '/agent/queue-steer')
    request.json = AsyncMock(return_value={'row_id': rows[1]['row_id'], 'session_id': 'default'})
    if cancel:
        with pytest.raises(asyncio.CancelledError):
            await agents.steer_queue_item(request)
        listed = await store.list(thread_id=root, agent_id='default')
        assert [row['row_id'] for row in listed] == [row['row_id'] for row in rows]
        assert [row['state'] for row in listed] == ['pending', 'uncertain', 'pending']
        assert all(row['mode'] == 'queue' for row in listed)
        assert (await store.claim(root, 'default'))['row_id'] == rows[0]['row_id']
        assert (await store.claim(root, 'default'))['row_id'] == rows[2]['row_id']
        assert await store.claim(root, 'default') is None
        broadcast.assert_not_awaited()
    else:
        response = await agents.steer_queue_item(request)
        assert response.status == 200
        assert json.loads(response.body)['item']['row_id'] == rows[1]['row_id']
        assert 'claim_token' not in response.text
        assert (await store.claim(root, 'default'))['row_id'] == rows[1]['row_id']


@pytest.mark.asyncio
async def test_startup_recovers_claims_before_workers_without_replay(db, monkeypatch):
    from types import SimpleNamespace
    from vibes import app
    store = FollowupStore(db)
    await store.enqueue(thread_id=1, agent_id='pi', message_id=1, content='ambiguous')
    await store.claim(1, 'pi')
    await store.enqueue(thread_id=1, agent_id='pi', message_id=2, content='pending')
    monkeypatch.setattr(app, 'get_config', lambda: SimpleNamespace(db_path='test', default_agent='pi', pi_enabled=True, pi_agent='test'))
    monkeypatch.setattr(app, 'init_db', AsyncMock())
    monkeypatch.setattr(app, 'get_db', AsyncMock(return_value=db))
    async def start_workers(**kwargs):
        rows = await store.list(thread_id=1, agent_id='pi')
        assert [row['state'] for row in rows] == ['uncertain', 'pending']
    monkeypatch.setattr(app, 'start_task_queue', start_workers)
    monkeypatch.setattr(app.agents, 'start_ffi_dispatch', lambda: None)
    monkeypatch.setattr(app, 'start_pi_agent', AsyncMock(return_value=False))
    monkeypatch.setattr(app, 'reconcile_missing_previews', AsyncMock())
    await app.on_startup(None)
    assert [row['state'] for row in await store.list(thread_id=1, agent_id='pi')] == ['uncertain', 'pending']


@pytest.mark.asyncio
async def test_uncertain_discard_route_requires_explicit_chat_and_never_requeues(db, monkeypatch):
    from aiohttp.test_utils import make_mocked_request
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    broadcast = AsyncMock()
    monkeypatch.setattr(agents, 'broadcast_event', broadcast)
    root = await db.create_interaction({'type': 'user', 'content': 'root'})
    store = FollowupStore(db)
    uncertain = await store.enqueue(thread_id=root, agent_id='default', message_id=root, content='ambiguous')
    await store.claim(root, 'default')
    await store.recover()
    pending = await store.enqueue(thread_id=root, agent_id='default', message_id=root, content='pending')
    async def discard(data):
        request = make_mocked_request('POST', '/agent/queue-discard-uncertain')
        request.json = AsyncMock(return_value=data)
        return await agents.discard_uncertain_followup(request)
    for data in [None, [], {'row_id': True}, {'row_id': uncertain['row_id']},
                 {'row_id': uncertain['row_id'], 'session_id': ''}]:
        assert (await discard(data)).status == 400
    assert (await discard({'row_id': uncertain['row_id'], 'session_id': 'foreign'})).status == 404
    assert (await discard({'row_id': pending['row_id'], 'session_id': 'default'})).status == 404
    broadcast.assert_not_awaited()
    response = await discard({'row_id': uncertain['row_id'], 'session_id': 'default'})
    assert response.status == 200
    assert 'claim_token' not in response.text
    assert (await discard({'row_id': uncertain['row_id'], 'session_id': 'default'})).status == 404
    broadcast.assert_awaited_once()
    rows = await store.list(thread_id=root, agent_id='default')
    assert [(row['row_id'], row['state']) for row in rows] == [(pending['row_id'], 'pending')]


@pytest.mark.asyncio
async def test_cancelled_admitted_dispatch_becomes_reviewable_without_replay(db, monkeypatch):
    import asyncio
    store = FollowupStore(db)
    await store.enqueue(thread_id=1, agent_id='pi', message_id=1, content='ambiguous')
    owner = await store.claim(1, 'pi')
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    started = asyncio.Event()
    async def process(*args, **kwargs):
        assert (await store.list(thread_id=1, agent_id='pi'))[0]['state'] == 'admitted'
        started.set()
        await asyncio.Future()
    monkeypatch.setattr(agents, 'process_agent_response', process)
    task = asyncio.create_task(agents._run_claimed_followup(owner))
    await asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    rows = await store.list(thread_id=1, agent_id='pi')
    assert rows[0]['state'] == 'uncertain'
    assert 'claim_token' not in rows[0]
    assert await store.claim(1, 'pi') is None
    with pytest.raises(ValueError, match='Admission no longer owned'):
        await store.complete(owner)
    with pytest.raises(ValueError, match='Claim no longer owned'):
        await store.transition_claim(owner)
    # Cancellation cleanup released the shared transaction lock.
    pending = await store.enqueue(thread_id=1, agent_id='pi', message_id=2, content='new')
    assert (await store.claim(1, 'pi'))['row_id'] == pending['row_id']


@pytest.mark.asyncio
async def test_admission_journal_failure_never_executes_or_releases_claim(db, monkeypatch):
    store = FollowupStore(db)
    await store.enqueue(thread_id=1, agent_id='pi', message_id=1, content='next')
    owner = await store.claim(1, 'pi')
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    process = AsyncMock(return_value=True)
    monkeypatch.setattr(agents, 'process_agent_response', process)
    with monkeypatch.context() as patch:
        patch.setattr(FollowupStore, 'transition_claim', AsyncMock(side_effect=RuntimeError('journal unavailable')))
        with pytest.raises(RuntimeError, match='journal unavailable'):
            await agents._run_claimed_followup(owner)
    process.assert_not_awaited()
    assert (await store.list(thread_id=1, agent_id='pi'))[0]['state'] == 'claimed'
    assert await store.claim(1, 'pi') is None
    await store.recover()
    assert (await store.list(thread_id=1, agent_id='pi'))[0]['state'] == 'uncertain'
    assert await store.claim(1, 'pi') is None


@pytest.mark.asyncio
async def test_fire_and_forget_native_steer_is_reviewable_without_completion_inference(db, monkeypatch):
    from aiohttp.test_utils import make_mocked_request
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda _: 'pi')
    monkeypatch.setattr(agents, '_is_agent_busy', lambda _: True)
    monkeypatch.setattr(agents, '_get_active_turn_for_agent', AsyncMock(return_value=None))
    rpc = AsyncMock(return_value=True)
    monkeypatch.setattr(agents, 'send_pi_rpc_fire_and_forget', rpc)
    monkeypatch.setattr(agents, 'broadcast_event', AsyncMock())
    root = await db.create_interaction({'type': 'user', 'content': 'root'})
    store = FollowupStore(db)
    queued = await store.enqueue(thread_id=root, agent_id='default', message_id=root, content='steer')
    request = make_mocked_request('POST', '/agent/queue-steer')
    request.json = AsyncMock(return_value={'row_id': queued['row_id'], 'session_id': 'default'})
    response = await agents.steer_queue_item(request)
    assert response.status == 200
    assert 'claim_token' not in response.text
    rpc.assert_awaited_once_with({'type': 'steer', 'message': 'steer'}, raise_on_send_error=True)
    rows = await store.list(thread_id=root, agent_id='default')
    assert [(row['row_id'], row['state']) for row in rows] == [(queued['row_id'], 'uncertain')]
    assert await store.claim(root, 'default') is None
    await store.recover()
    assert (await store.list(thread_id=root, agent_id='default'))[0]['state'] == 'uncertain'


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['accepted', 'error', 'cancelled'])
async def test_busy_native_steer_has_persisted_review_identity(db, monkeypatch, outcome):
    from unittest.mock import Mock
    from aiohttp.test_utils import make_mocked_request
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    from types import SimpleNamespace
    monkeypatch.setattr(agents, 'get_config', lambda: SimpleNamespace(default_agent='pi', db_path=database.db_path, pi_enabled=False, acp_agent='offline'))
    monkeypatch.setattr(agents, '_resolve_agent_mode', Mock(return_value='pi'))
    monkeypatch.setattr(agents, '_is_agent_busy', Mock(return_value=True))
    root = await db.create_interaction({'type': 'user', 'content': 'active'})
    monkeypatch.setattr(agents, '_get_active_turn_for_agent', AsyncMock(return_value={'thread_id': root, 'turn_id': 'active'}))
    monkeypatch.setattr(agents, 'broadcast_event', AsyncMock())
    import asyncio
    failure = RuntimeError('RPC interrupted') if outcome == 'error' else asyncio.CancelledError()
    rpc = AsyncMock(return_value=True, side_effect=failure if outcome != 'accepted' else None)
    monkeypatch.setattr(agents, 'send_pi_rpc_fire_and_forget', rpc)
    request = make_mocked_request('POST', '/agent/default/message', match_info={'agent_id': 'default'})
    request.json = AsyncMock(return_value={'content': 'native steer', 'mode': 'steer'})
    if outcome == 'accepted':
        response = await agents.send_message(request)
        import json
        payload = json.loads(response.body)
        assert response.status == 201
        assert 'claim_token' not in response.text
    else:
        with pytest.raises(type(failure)):
            await agents.send_message(request)
    rows = await FollowupStore(db).list()
    assert len(rows) == 1 and rows[0]['state'] == 'uncertain'
    if outcome == 'accepted':
        assert payload['item']['row_id'] == rows[0]['row_id']
    rpc.assert_awaited_once()
    assert await FollowupStore(db).claim(rows[0]['thread_id'], 'default') is None
    await FollowupStore(db).recover()
    assert (await FollowupStore(db).list())[0]['state'] == 'uncertain'

@pytest.mark.asyncio
async def test_status_reads_persisted_pending_queues_with_chat_isolation(tmp_path, monkeypatch):
    import json
    from unittest.mock import MagicMock
    from vibes.db import Database
    from vibes.sessions import SessionStore
    database = Database(str(tmp_path / 'status-queue.db'))
    await database.connect()
    try:
        selected = await SessionStore(database).create('Selected')
        other = await SessionStore(database).create('Other')
        roots = [await database.create_interaction({'type': 'user', 'content': 'root', 'session_id': s['id']}) for s in [selected, other]]
        store = FollowupStore(database)
        queued = await store.enqueue(thread_id=roots[0], agent_id='pi', message_id=roots[0], content='queue')
        steer = await store.enqueue(thread_id=roots[0], agent_id='pi', message_id=roots[0], content='steer', steer=True)
        await store.enqueue(thread_id=roots[1], agent_id='pi', message_id=roots[1], content='foreign')
        claimed = await store.claim(roots[0], 'pi')
        assert claimed['row_id'] == steer['row_id']
        await store.transition_claim(claimed, admitted=True)
        await store.mark_uncertain(claimed)
        await database.close()
        await database.connect()
        monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=database))
        request = MagicMock()
        request.query = {'session_id': selected['id']}
        payload = json.loads((await agents.get_agent_status(request)).text)
        assert [row['row_id'] for row in payload['queued_followups']] == [queued['row_id']]
        assert payload['pending_steers'] == []
        assert 'claim_token' not in json.dumps(payload)
        assert 'foreign' not in json.dumps(payload)
    finally:
        await database.close()

@pytest.mark.asyncio
async def test_reopened_queue_dispatches_pending_not_recovered_uncertain(tmp_path, monkeypatch):
    import asyncio
    from vibes.db import Database
    database = Database(str(tmp_path / 'restart-dispatch.db'))
    await database.connect()
    store = FollowupStore(database)
    root = await database.create_interaction({'type': 'user', 'content': 'root', 'session_id': 'default'})
    ambiguous = await store.enqueue(thread_id=root, agent_id='default', message_id=root, content='never replay')
    owner = await store.claim(root, 'default')
    pending = await store.enqueue(thread_id=root, agent_id='default', message_id=root, content='pending after restart')
    await database.close()
    await database.connect()
    await store.recover()
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=database))
    monkeypatch.setattr(agents, 'broadcast_event', AsyncMock())
    calls = []
    async def process(thread, prompt, agent, **kwargs):
        calls.append(prompt)
        if prompt == pending['content']:
            rows = await store.list()
            assert next(row for row in rows if row['row_id'] == pending['row_id'])['state'] == 'admitted'
        return True
    monkeypatch.setattr(agents, 'process_agent_response', process)
    agents.start_ffi_dispatch()
    try:
        agents._enqueue_ffi('default', root, 'new turn', 'default', [])
        await asyncio.wait_for(agents._ffi_tasks['default'], 2)
        assert calls == ['new turn', pending['content']]
        rows = await store.list()
        assert len(rows) == 1
        assert rows[0]['row_id'] == ambiguous['row_id']
        assert rows[0]['state'] == 'uncertain'
        assert 'claim_token' not in rows[0]
        with pytest.raises(ValueError):
            await store.transition_claim(owner)
        assert await store.claim(root, 'default') is None
    finally:
        await agents.stop_ffi_dispatch()
        await database.close()

@pytest.mark.asyncio
async def test_production_startup_http_uncertain_review_after_reopen(tmp_path, monkeypatch, aiohttp_client):
    from types import SimpleNamespace
    from vibes import app as app_module
    from vibes.db import Database
    from vibes.sessions import SessionStore
    database = Database(str(tmp_path / 'startup-http.db'))
    await database.connect()
    selected = await SessionStore(database).create('Selected')
    foreign = await SessionStore(database).create('Foreign')
    root = await database.create_interaction({'type': 'user', 'content': 'root', 'session_id': selected['id']})
    store = FollowupStore(database)
    ambiguous = await store.enqueue(thread_id=root, agent_id='pi', message_id=root, content='review after restart')
    await store.claim(root, 'pi')
    pending = await store.enqueue(thread_id=root, agent_id='pi', message_id=root, content='keep pending')
    await database.close()
    monkeypatch.setattr(app_module, 'init_db', lambda path: database.connect())
    monkeypatch.setattr(app_module, 'get_db', AsyncMock(return_value=database))
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=database))
    monkeypatch.setattr(app_module, 'get_config', lambda: SimpleNamespace(default_agent='pi', db_path=database.db_path, pi_enabled=False, acp_agent='offline'))
    monkeypatch.setattr(app_module, 'start_task_queue', AsyncMock())
    monkeypatch.setattr(app_module, 'start_acp_agent', AsyncMock(return_value=False))
    monkeypatch.setattr(app_module, 'reconcile_missing_previews', AsyncMock())
    monkeypatch.setattr(agents, 'broadcast_event', AsyncMock())
    application = app_module.create_app()
    # Avoid external shutdown services; database ownership belongs to this test.
    application.on_cleanup.clear()
    client = await aiohttp_client(application)
    try:
        response = await client.get('/agent/queue', params={'session_id': selected['id']})
        assert response.status == 200
        payload = await response.json()
        assert [row['row_id'] for row in payload['uncertain']] == [ambiguous['row_id']]
        assert [row['row_id'] for row in payload['items']] == [pending['row_id']]
        assert 'claim_token' not in str(payload)
        response = await client.get('/agent/queue', params={'session_id': foreign['id']})
        assert (await response.json())['uncertain'] == []
        response = await client.post('/agent/queue-discard-uncertain', json={'row_id': ambiguous['row_id'], 'session_id': foreign['id']})
        assert response.status == 404
        response = await client.post('/agent/queue-discard-uncertain', json={'row_id': ambiguous['row_id'], 'session_id': selected['id']})
        assert response.status == 200
        rows = await store.list()
        assert [(row['row_id'], row['state']) for row in rows] == [(pending['row_id'], 'pending')]
    finally:
        await client.close()
        await database.close()
