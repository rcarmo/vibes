import importlib
import pytest

ModelPreferences = importlib.import_module('vibes.model_preferences').ModelPreferences


@pytest.mark.asyncio
async def test_model_pins_persist_after_database_reconnect(db):
    prefs = ModelPreferences(db)
    assert await prefs.get() == {'pins': []}
    assert await prefs.set_pins(['p/model', 'p/model', 'p/another']) == {'pins': ['p/model', 'p/another']}
    await db.close()
    await db.connect()
    assert await ModelPreferences(db).get() == {'pins': ['p/model', 'p/another']}


@pytest.mark.asyncio
@pytest.mark.parametrize('pins', [None, {}, [''], ['missing-provider'], ['/model'], ['p/'], ['p/\nmodel'], ['p/m'] * 101])
async def test_invalid_pins_do_not_change_preferences(db, pins):
    prefs = ModelPreferences(db)
    await prefs.set_pins(['p/keep'])
    with pytest.raises(ValueError):
        await prefs.set_pins(pins)
    assert await prefs.get() == {'pins': ['p/keep']}


@pytest.mark.asyncio
async def test_v6_upgrade_preserves_session_history_and_binding(db):
    from vibes.sessions import SessionStore
    store = SessionStore(db)
    session = await store.create('Before upgrade')
    await store.bind_backend(session['id'], 'pi', '/confirmed.jsonl', model='p/m', thinking_level='low')
    message = await db.create_interaction({'type': 'user', 'content': 'Keep history', 'session_id': session['id']})
    # Reconstruct the prior schema by removing only the v7 addition.
    async with db.transaction():
        await db._connection.execute('DROP TABLE model_preferences')
        await db._connection.execute('UPDATE schema_version SET version=6')
    await db.close()
    await db.connect()
    assert await ModelPreferences(db).get() == {'pins': []}
    assert (await store.get(session['id']))['name'] == 'Before upgrade'
    binding = await store.backend_binding(session['id'], 'pi')
    assert binding['conversation_id'] == '/confirmed.jsonl'
    assert binding['model'] == 'p/m'
    assert binding['thinking_level'] == 'low'
    assert await db.get_interaction(message) is not None
    await ModelPreferences(db).set_pins(['p/m'])
    await db.close()
    await db.connect()
    assert await ModelPreferences(db).get() == {'pins': ['p/m']}
