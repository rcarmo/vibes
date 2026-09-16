from unittest.mock import AsyncMock
import importlib
import pytest

PiSessionSelector = importlib.import_module('vibes.pi_sessions').PiSessionSelector


def state(path, **kwargs):
    return {'success': True, 'data': {'sessionFile': path, **kwargs}}


@pytest.mark.asyncio
async def test_pi_create_and_switch_back():
    selector = PiSessionSelector()
    rpc = AsyncMock(side_effect=[state('/default.jsonl'), {'success': True, 'data': {'cancelled': False}}, state('/other.jsonl')])
    assert await selector.select('other', rpc) == '/other.jsonl'
    assert rpc.call_args_list[1].args[0] == {'type': 'new_session'}
    rpc = AsyncMock(side_effect=[state('/other.jsonl'), {'success': True, 'data': {'cancelled': False}}, state('/default.jsonl')])
    assert await selector.select('default', rpc) == '/default.jsonl'
    assert rpc.call_args_list[1].args[0]['sessionPath'] == '/default.jsonl'


@pytest.mark.asyncio
async def test_fresh_unpersisted_process_can_bootstrap_named_session():
    selector = PiSessionSelector()
    rpc = AsyncMock(side_effect=[state(None), {'success': True, 'data': {'cancelled': False}}, state('/named.jsonl')])
    assert await selector.select('other', rpc) == '/named.jsonl'
    assert rpc.call_args_list[1].args[0] == {'type': 'new_session'}
    assert selector.active == 'other'
    assert selector.paths == {'other': '/named.jsonl'}


@pytest.mark.asyncio
async def test_known_unpersisted_busy_and_cancelled_states_do_not_switch():
    known_unpersisted = PiSessionSelector()
    known_unpersisted.paths['default'] = '/remembered.jsonl'
    with pytest.raises(RuntimeError, match='persistence'):
        await known_unpersisted.select('other', AsyncMock(return_value=state(None)))
    for responses in [[state('/default.jsonl', isStreaming=True)], [state('/default.jsonl'), {'success': True, 'data': {'cancelled': True}}]]:
        selector = PiSessionSelector()
        with pytest.raises(RuntimeError):
            await selector.select('other', AsyncMock(side_effect=responses))
        assert selector.active == 'default'


@pytest.mark.asyncio
async def test_unconfirmed_switch_blocks_further_selection_without_corrupting_map():
    selector = PiSessionSelector()
    rpc = AsyncMock(side_effect=[state('/default.jsonl'), {'success': True, 'data': {'cancelled': False}}, {'success': False}])
    with pytest.raises(RuntimeError):
        await selector.select('other', rpc)
    assert selector.uncertain
    assert selector.paths == {'default': '/default.jsonl'}
    next_rpc = AsyncMock(return_value=state('/other.jsonl'))
    with pytest.raises(RuntimeError, match='uncertain'):
        await selector.select('default', next_rpc)
    next_rpc.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_switch_keeps_selector_usable():
    selector = PiSessionSelector()
    rpc = AsyncMock(side_effect=[state('/default.jsonl'), {'success': True, 'data': {'cancelled': True}}])
    with pytest.raises(RuntimeError):
        await selector.select('other', rpc)
    assert not selector.uncertain
    assert await selector.select('default', AsyncMock(return_value=state('/default.jsonl'))) == '/default.jsonl'


@pytest.mark.asyncio
async def test_fresh_named_path_persists_and_is_reused_after_selector_restart(db):
    SessionStore = importlib.import_module('vibes.sessions').SessionStore
    store = SessionStore(db)
    named = await store.create('Named Pi bootstrap')
    selector = PiSessionSelector()
    first = AsyncMock(side_effect=[state(None), {'success': True, 'data': {'cancelled': False}}, state('/named.jsonl')])
    path = await selector.select(named['id'], first)
    await store.bind_backend(named['id'], 'pi', path)
    binding = await store.backend_binding(named['id'], 'pi')
    restarted = PiSessionSelector()
    second = AsyncMock(side_effect=[state('/startup.jsonl'), {'success': True, 'data': {'cancelled': False}}, state('/named.jsonl')])
    assert await restarted.select(named['id'], second, persisted_path=binding['conversation_id']) == '/named.jsonl'
    assert second.call_args_list[1].args[0] == {'type': 'switch_session', 'sessionPath': '/named.jsonl'}


@pytest.mark.asyncio
async def test_restart_loads_persisted_path_instead_of_new_conversation():
    selector = PiSessionSelector()
    rpc = AsyncMock(side_effect=[state('/startup.jsonl'), {'success': True, 'data': {'cancelled': False}}, state('/saved.jsonl')])
    assert await selector.select('other', rpc, persisted_path='/saved.jsonl') == '/saved.jsonl'
    assert rpc.call_args_list[1].args[0] == {'type': 'switch_session', 'sessionPath': '/saved.jsonl'}
