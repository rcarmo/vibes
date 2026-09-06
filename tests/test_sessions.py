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
    assert rows[0]['version'] == 6


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
