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
async def test_pi_cancel_busy_and_no_persistence_do_not_switch():
    for responses in [[state(None)], [state('/default.jsonl', isStreaming=True)], [state('/default.jsonl'), {'success': True, 'data': {'cancelled': True}}]]:
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
