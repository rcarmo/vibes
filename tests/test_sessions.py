import importlib
import pytest

SessionStore = importlib.import_module('vibes.sessions').SessionStore


@pytest.mark.asyncio
async def test_registry_metadata_and_default_protection(db):
    store = SessionStore(db)
    assert (await store.get('default'))['name'] == 'Default'
    session = await store.create(' Research ', parent_id='default')
    assert session['name'] == 'Research'
    await store.update(session['id'], name='Renamed', pinned=True)
    assert (await store.list())[0]['id'] == session['id']
    await store.update(session['id'], archived=True)
    assert len(await store.list()) == 1
    assert len(await store.list(include_archived=True)) == 2
    with pytest.raises(ValueError):
        await store.update('default', archived=True)
    with pytest.raises(ValueError):
        await store.create('bad\nname')
    with pytest.raises(ValueError):
        await store.create('Child', parent_id='missing')
    with pytest.raises(ValueError):
        await store.update(session['id'], pinned='true')


@pytest.mark.asyncio
async def test_registry_survives_reopen_without_duplicate_migration(db):
    store = SessionStore(db)
    session = await store.create('Persistent')
    await db.close()
    await db.connect()
    assert (await store.get(session['id']))['name'] == 'Persistent'
    async with db._connection.execute('SELECT version FROM schema_version') as cursor:
        rows = await cursor.fetchall()
    assert len(rows) == 1
    assert rows[0]['version'] == 7


@pytest.mark.asyncio
async def test_messages_inherit_session_and_timeline_isolates(db):
    store = SessionStore(db)
    session = await store.create('Other')
    root = await db.create_interaction({'type': 'user', 'content': 'root', 'session_id': session['id']})
    reply = await db.create_interaction({'type': 'agent', 'content': 'reply', 'thread_id': root})
    default = await db.create_interaction({'type': 'user', 'content': 'default'})
    assert (await db.get_interaction(reply))['data']['session_id'] == session['id']
    assert [p['id'] for p in (await store.timeline(session['id']))['posts']] == [root, reply]
    assert [p['id'] for p in (await store.timeline('default'))['posts']] == [default]
    with pytest.raises(ValueError):
        await db.create_interaction({'type': 'agent', 'content': 'wrong', 'thread_id': root, 'session_id': 'default'})
    with pytest.raises(ValueError):
        await db.create_interaction({'type': 'user', 'content': 'wrong', 'session_id': 'missing'})


@pytest.mark.asyncio
async def test_backend_bindings_isolate_conversations_and_persist(db):
    store = SessionStore(db)
    other = await store.create('Other')
    await store.bind_backend('default', 'acp:agent', 'conversation-a', model='model-a')
    await store.bind_backend(other['id'], 'acp:agent', 'conversation-b', model='model-b')
    await store.bind_backend('default', 'pi', 'pi-conversation')
    assert (await store.backend_binding('default', 'acp:agent'))['conversation_id'] == 'conversation-a'
    assert (await store.backend_binding(other['id'], 'acp:agent'))['model'] == 'model-b'
    await db.close()
    await db.connect()
    assert (await store.backend_binding('default', 'pi'))['conversation_id'] == 'pi-conversation'
    with pytest.raises(ValueError):
        await store.bind_backend('missing', 'pi', 'anything')
    with pytest.raises(ValueError):
        await store.bind_backend('default', '', 'anything')


@pytest.mark.asyncio
async def test_thread_reassignment_cannot_cross_session_boundary(db):
    store = SessionStore(db)
    other = await store.create('Other')
    a = await db.create_interaction({'type': 'user', 'content': 'a'})
    b = await db.create_interaction({'type': 'user', 'content': 'b'})
    foreign = await db.create_interaction({'type': 'user', 'content': 'foreign', 'session_id': other['id']})
    assert await db.set_interaction_thread_id(a, b)
    with pytest.raises(ValueError):
        await db.set_interaction_thread_id(a, foreign)
    assert (await db.get_interaction(a))['data']['thread_id'] == b
    with pytest.raises(ValueError):
        await db.set_interaction_thread_id(a, 999999)
    assert await db.set_interaction_thread_id(b, b)


@pytest.mark.asyncio
async def test_session_listing_reports_stored_activity_not_runtime(db):
    store = SessionStore(db)
    other = await store.create('Other')
    first = await db.create_interaction({'type': 'user', 'content': 'one'})
    last = await db.create_interaction({'type': 'user', 'content': 'two'})
    sessions = {item['id']: item for item in await store.list()}
    assert sessions['default']['message_count'] == 2
    assert sessions['default']['last_message_id'] == last
    assert sessions['default']['last_message_at']
    assert sessions[other['id']]['message_count'] == 0
    assert sessions[other['id']]['last_message_id'] is None
    assert sessions['default']['is_running'] is False
    assert first < last


@pytest.mark.asyncio
async def test_running_session_cannot_be_archived(db):
    store = SessionStore(db)
    session = await store.create('Running')
    root = await db.create_interaction({'type': 'user', 'content': 'work', 'session_id': session['id']})
    await db.begin_turn('archive-test', root, 'default')
    with pytest.raises(ValueError, match='running'):
        await store.update(session['id'], archived=True)
    await db.end_turn('archive-test')
    assert (await store.update(session['id'], archived=True))['archived'] == 1


@pytest.mark.asyncio
async def test_listing_running_flag_tracks_active_turn_not_history(db):
    store = SessionStore(db)
    session = await store.create('Active')
    root = await db.create_interaction({'type': 'user', 'content': 'work', 'session_id': session['id']})
    await db.begin_turn('running-list', root, 'default')
    rows = {row['id']: row for row in await store.list()}
    assert rows[session['id']]['is_running'] is True
    assert rows['default']['is_running'] is False
    await db.end_turn('running-list')
    rows = {row['id']: row for row in await store.list()}
    assert rows[session['id']]['is_running'] is False


@pytest.mark.asyncio
async def test_rebinding_preserves_confirmed_model_metadata(db):
    store = SessionStore(db)
    await store.bind_backend('default', 'pi', '/session.jsonl', model='provider/model', thinking_level='low')
    await store.bind_backend('default', 'pi', '/session.jsonl')
    binding = await store.backend_binding('default', 'pi')
    assert binding['model'] == 'provider/model'
    assert binding['thinking_level'] == 'low'
    await store.bind_backend('default', 'pi', '/session.jsonl', thinking_level='high')
    binding = await store.backend_binding('default', 'pi')
    assert binding['model'] == 'provider/model'
    assert binding['thinking_level'] == 'high'


@pytest.mark.asyncio
async def test_registry_queue_counts_follow_persisted_thread_ownership(db):
    from vibes.followups import queue_followup, defer_steer, reset_state
    reset_state()
    try:
        store = SessionStore(db)
        other = await store.create('Queue owner')
        root = await db.create_interaction({'type': 'user', 'content': 'root', 'session_id': other['id']})
        legacy = await db.create_interaction({'type': 'user', 'content': 'legacy'})
        queue_followup(thread_id=root, agent_id='default', message_id=None, content='one')
        defer_steer(thread_id=root, agent_id='default', message_id=None, content='two')
        queue_followup(thread_id=legacy, agent_id='default', message_id=None, content='legacy')
        queue_followup(thread_id=999999, agent_id='default', message_id=None, content='orphan')
        rows = {row['id']: row for row in await store.list()}
        assert rows[other['id']]['queued_count'] == 2
        assert rows['default']['queued_count'] == 1
        assert not rows[other['id']]['is_running']
        reset_state()
        assert all(row['queued_count'] == 0 for row in await store.list())
    finally:
        reset_state()


@pytest.mark.asyncio
async def test_child_creation_requires_unarchived_parent(db):
    store = SessionStore(db)
    parent = await store.create('Parent')
    await store.update(parent['id'], archived=True)
    with pytest.raises(ValueError, match='Restore parent'):
        await store.create('Child', parent['id'])
    assert len(await store.list(include_archived=True)) == 2
    await store.update(parent['id'], archived=False)
    child = await store.create('Child', parent['id'])
    assert child['parent_id'] == parent['id']


@pytest.mark.asyncio
async def test_running_session_deletion_preserves_session_and_history(db):
    store = SessionStore(db)
    session = await store.create('Running deletion')
    root = await db.create_interaction({'type': 'user', 'content': 'work', 'session_id': session['id']})
    await db.begin_turn('delete-test', root, 'default')
    with pytest.raises(ValueError, match='nonempty'):
        await store.delete_empty(session['id'])
    rows = {row['id']: row for row in await store.list()}
    assert rows[session['id']]['is_running'] is True
    assert rows[session['id']]['message_count'] == 1
    await db.end_turn('delete-test')
    with pytest.raises(ValueError, match='nonempty'):
        await store.delete_empty(session['id'])
    assert await store.get(session['id']) is not None


@pytest.mark.asyncio
async def test_archived_session_pin_requires_restore(db):
    store = SessionStore(db)
    session = await store.create('Archived pin')
    await store.update(session['id'], archived=True)
    with pytest.raises(ValueError, match='Restore session before pinning'):
        await store.update(session['id'], pinned=True, name='Must roll back')
    unchanged = await store.get(session['id'])
    assert unchanged['name'] == 'Archived pin'
    assert not unchanged['pinned']
    restored = await store.update(session['id'], archived=False, pinned=True)
    assert restored['pinned'] and not restored['archived']
    with pytest.raises(ValueError, match='Restore session before pinning'):
        await store.update(session['id'], archived=True, pinned=True)
    assert not (await store.get(session['id']))['archived']
    await store.update(session['id'], archived=True)
    assert not (await store.update(session['id'], pinned=False))['pinned']
