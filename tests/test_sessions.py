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
    assert rows[0]['version'] == 5
