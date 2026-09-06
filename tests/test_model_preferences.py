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
