import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from vibes.copilot_host import CopilotHost


@pytest.mark.asyncio
async def test_catalogue_routes_to_requested_lane_not_another_busy_chat():
    host = CopilotHost()
    busy = SimpleNamespace(turn_lock=asyncio.Lock(), command_catalogue=AsyncMock())
    idle = SimpleNamespace(turn_lock=asyncio.Lock(), command_catalogue=AsyncMock(return_value={'available': True, 'commands': [], 'skills': []}))
    host.lanes = {'busy-chat': busy, 'idle-chat': idle}
    store = object()
    async with busy.turn_lock:
        result = await host.command_catalogue('idle-chat', store)
    assert result['available'] is True
    idle.command_catalogue.assert_awaited_once_with('idle-chat', store)
    busy.command_catalogue.assert_not_awaited()


@pytest.mark.asyncio
async def test_catalogue_keeps_busy_response_from_own_lane():
    host = CopilotHost()
    response = {'available': False, 'busy': True, 'commands': [], 'skills': []}
    lane = SimpleNamespace(command_catalogue=AsyncMock(return_value=response))
    host.lanes['chat'] = lane
    assert await host.command_catalogue('chat', object()) == response


def test_passive_diagnostics_never_creates_lane_or_exposes_other_chat():
    host = CopilotHost()
    assert host.diagnostics('absent') == {'state': 'not-started', 'session_bound': False, 'capabilities_verified': False}
    assert host.lanes == {}
    lane = host.lane('selected')
    lane.sessions['selected'] = SimpleNamespace(session_id='private-native-id')
    lane.poisoned = True
    host.runtime.error = 'private failure'
    host.lane('other').sessions['other'] = SimpleNamespace(session_id='foreign')
    result = host.diagnostics('selected')
    assert result == {'state': 'unavailable', 'session_bound': True, 'capabilities_verified': False}
    assert 'private' not in str(result)
    assert 'foreign' not in str(result)


def test_passive_diagnostics_does_not_report_stale_client_ready():
    host = CopilotHost()
    lane = host.lane('selected')
    lane.client = object()
    assert host.diagnostics('selected')['state'] == 'not-started'
    host.runtime.client = lane.client
    assert host.diagnostics('selected')['state'] == 'ready'
    host.runtime.poisoned = True
    assert host.diagnostics('selected')['state'] == 'unavailable'
    host.runtime.poisoned = False
    host.runtime.closing = True
    assert host.diagnostics('selected')['state'] == 'unavailable'


@pytest.mark.asyncio
async def test_passive_diagnostics_busy_state_is_lane_scoped():
    host = CopilotHost()
    host.runtime.client = object()
    selected = host.lane('selected')
    other = host.lane('other')
    selected.client = other.client = host.runtime.client
    await other.turn_lock.acquire()
    try:
        assert host.diagnostics('selected')['state'] == 'ready'
        assert host.diagnostics('other')['state'] == 'busy'
        await selected.turn_lock.acquire()
        try:
            assert host.diagnostics('selected')['state'] == 'busy'
            selected.closing = True
            assert host.diagnostics('selected')['state'] == 'unavailable'
        finally:
            selected.turn_lock.release()
        assert set(host.lanes) == {'selected', 'other'}
    finally:
        other.turn_lock.release()


def test_passive_diagnostics_rejects_replaced_runtime_client():
    host = CopilotHost()
    lane = host.lane('selected')
    lane.client = object()
    host.runtime.client = object()
    assert host.diagnostics('selected')['state'] == 'not-started'
    lane.client = host.runtime.client
    assert host.diagnostics('selected')['state'] == 'ready'


@pytest.mark.asyncio
async def test_tool_diagnostics_existing_session_only_and_safe_metadata():
    host = CopilotHost()
    assert (await host.tool_diagnostics('absent'))['state'] == 'unavailable'
    assert host.lanes == {}
    host.runtime.client = object()
    lane = host.lane('selected')
    lane.client = host.runtime.client
    read = AsyncMock(return_value=SimpleNamespace(to_dict=lambda: {'tools': [
        {'name': 'read', 'description': 'private', 'inputSchema': {'secret': 'private'}},
        {'name': 'searchable', 'deferLoading': True},
        {'name': 'bad\nname'},
    ]}))
    lane.sessions['selected'] = SimpleNamespace(rpc=SimpleNamespace(tools=SimpleNamespace(get_current_metadata=read)))
    result = await host.tool_diagnostics('selected')
    assert result['tools'] == [{'name': 'read', 'state': 'offered'}, {'name': 'searchable', 'state': 'deferred'}]
    assert 'private' not in str(result)
    read.assert_awaited_once_with(timeout=10)
    read.reset_mock()
    await lane.turn_lock.acquire()
    try:
        assert (await host.tool_diagnostics('selected'))['state'] == 'unavailable'
        read.assert_not_awaited()
    finally:
        lane.turn_lock.release()
    read.return_value = SimpleNamespace(to_dict=lambda: {'tools': None})
    assert (await host.tool_diagnostics('selected'))['state'] == 'uninitialised'
    read.side_effect = RuntimeError('private failure')
    assert await host.tool_diagnostics('selected') == {'state': 'unavailable', 'tools': []}
    assert not lane.turn_lock.locked()


@pytest.mark.asyncio
async def test_tool_diagnostics_cancellation_releases_lane():
    import asyncio
    host = CopilotHost()
    host.runtime.client = object()
    lane = host.lane('selected')
    lane.client = host.runtime.client
    read = AsyncMock(side_effect=asyncio.CancelledError)
    lane.sessions['selected'] = SimpleNamespace(rpc=SimpleNamespace(tools=SimpleNamespace(get_current_metadata=read)))
    with pytest.raises(asyncio.CancelledError):
        await host.tool_diagnostics('selected')
    assert not lane.turn_lock.locked()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['session', 'client', 'closing', 'lane'])
async def test_tool_diagnostics_discards_metadata_after_identity_change(change):
    host = CopilotHost()
    host.runtime.client = object()
    lane = host.lane('selected')
    lane.client = host.runtime.client
    async def read(**kwargs):
        if change == 'session':
            lane.sessions['selected'] = object()
        elif change == 'client':
            host.runtime.client = lane.client = object()
        elif change == 'closing':
            host.closing = True
        else:
            del host.lanes['selected']
        return SimpleNamespace(to_dict=lambda: {'tools': [{'name': 'stale'}]})
    lane.sessions['selected'] = SimpleNamespace(rpc=SimpleNamespace(tools=SimpleNamespace(get_current_metadata=read)))
    assert await host.tool_diagnostics('selected') == {'state': 'unavailable', 'tools': []}
    assert not lane.turn_lock.locked()


@pytest.mark.asyncio
@pytest.mark.parametrize('data', [{}, [], {'tools': 'invalid'}, {'tools': True}])
async def test_tool_diagnostics_malformed_is_not_uninitialised(data):
    host = CopilotHost()
    host.runtime.client = object()
    lane = host.lane('selected')
    lane.client = host.runtime.client
    lane.sessions['selected'] = SimpleNamespace(rpc=SimpleNamespace(tools=SimpleNamespace(
        get_current_metadata=AsyncMock(return_value=SimpleNamespace(to_dict=lambda: data)))))
    assert await host.tool_diagnostics('selected') == {'state': 'unavailable', 'tools': []}
    assert not lane.turn_lock.locked()


@pytest.mark.asyncio
async def test_tool_diagnostics_bounds_and_typed_deferred_flags():
    host = CopilotHost()
    host.runtime.client = object()
    lane = host.lane('selected')
    lane.client = host.runtime.client
    tools = [{'name': 'bad', 'deferLoading': 'false'}, {'name': 'x' * 513}, {'name': True}] + [
        {'name': f'tool-{index}', 'deferLoading': False} for index in range(70)]
    lane.sessions['selected'] = SimpleNamespace(rpc=SimpleNamespace(tools=SimpleNamespace(
        get_current_metadata=AsyncMock(return_value=SimpleNamespace(to_dict=lambda: {'tools': tools})))))
    result = await host.tool_diagnostics('selected')
    assert result['truncated'] is True
    assert len(result['tools']) == 61
    assert all(entry['state'] == 'offered' for entry in result['tools'])
    assert result['tools'][-1]['name'] == 'tool-60'


@pytest.mark.asyncio
async def test_tool_diagnostics_enforces_timeout_and_releases_lane():
    import asyncio
    from unittest.mock import patch
    host = CopilotHost()
    host.runtime.client = object()
    lane = host.lane('selected')
    lane.client = host.runtime.client
    cancelled = False
    async def stalled(**kwargs):
        nonlocal cancelled
        try:
            await asyncio.Event().wait()
        finally:
            cancelled = True
    lane.sessions['selected'] = SimpleNamespace(rpc=SimpleNamespace(tools=SimpleNamespace(get_current_metadata=stalled)))
    with patch('vibes.copilot_host._DIAGNOSTICS_TIMEOUT', 0.01):
        assert await host.tool_diagnostics('selected') == {'state': 'unavailable', 'tools': []}
    assert cancelled
    assert not lane.turn_lock.locked()


@pytest.mark.asyncio
async def test_mcp_diagnostics_safe_existing_connection_states():
    host = CopilotHost()
    assert await host.mcp_diagnostics('absent') == {'state': 'unavailable', 'servers': []}
    assert host.lanes == {}
    host.runtime.client = object()
    lane = host.lane('selected')
    lane.client = host.runtime.client
    read = AsyncMock(return_value=SimpleNamespace(to_dict=lambda: {'servers': [
        {'name': 'local', 'status': 'connected', 'error': 'private', 'serverMetadata': {'secret': 'private'}},
        {'name': 'broken', 'status': 'failed', 'error': 'private'},
        {'name': 'bad\nname', 'status': 'connected'},
        {'name': 'unknown', 'status': 'private-state'},
    ], 'host': {'private': 'secret'}}))
    lane.sessions['selected'] = SimpleNamespace(rpc=SimpleNamespace(mcp=SimpleNamespace(list=read)))
    result = await host.mcp_diagnostics('selected')
    assert result['servers'] == [{'name': 'local', 'state': 'connected'}, {'name': 'broken', 'state': 'failed'}]
    assert 'private' not in str(result)
    read.assert_awaited_once_with(timeout=10)
    read.reset_mock()
    await lane.turn_lock.acquire()
    try:
        assert (await host.mcp_diagnostics('selected'))['state'] == 'unavailable'
        read.assert_not_awaited()
    finally:
        lane.turn_lock.release()
    read.side_effect = RuntimeError('private failure')
    assert await host.mcp_diagnostics('selected') == {'state': 'unavailable', 'servers': []}
    assert not lane.turn_lock.locked()


@pytest.mark.asyncio
async def test_mcp_diagnostics_discards_stale_and_propagates_cancel():
    import asyncio
    host = CopilotHost()
    host.runtime.client = object()
    lane = host.lane('selected')
    lane.client = host.runtime.client
    async def stale(**kwargs):
        host.closing = True
        return SimpleNamespace(to_dict=lambda: {'servers': [{'name': 'stale', 'status': 'connected'}]})
    read = AsyncMock(side_effect=stale)
    lane.sessions['selected'] = SimpleNamespace(rpc=SimpleNamespace(mcp=SimpleNamespace(list=read)))
    assert await host.mcp_diagnostics('selected') == {'state': 'unavailable', 'servers': []}
    host.closing = False
    read.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await host.mcp_diagnostics('selected')
    assert not lane.turn_lock.locked()


@pytest.mark.asyncio
@pytest.mark.parametrize('data', [{}, [], {'servers': None}, {'servers': 'invalid'}])
async def test_mcp_diagnostics_rejects_malformed_metadata(data):
    host = CopilotHost()
    host.runtime.client = object()
    lane = host.lane('selected')
    lane.client = host.runtime.client
    lane.sessions['selected'] = SimpleNamespace(rpc=SimpleNamespace(mcp=SimpleNamespace(
        list=AsyncMock(return_value=SimpleNamespace(to_dict=lambda: data)))))
    assert await host.mcp_diagnostics('selected') == {'state': 'unavailable', 'servers': []}
    assert not lane.turn_lock.locked()


@pytest.mark.asyncio
async def test_mcp_diagnostics_bounds_and_timeout():
    import asyncio
    from unittest.mock import patch
    host = CopilotHost()
    host.runtime.client = object()
    lane = host.lane('selected')
    lane.client = host.runtime.client
    read = AsyncMock(return_value=SimpleNamespace(to_dict=lambda: {'servers': [
        {'name': f'server-{index}', 'status': 'connected', 'error': 'private'} for index in range(40)]}))
    lane.sessions['selected'] = SimpleNamespace(rpc=SimpleNamespace(mcp=SimpleNamespace(list=read)))
    result = await host.mcp_diagnostics('selected')
    assert len(result['servers']) == 32
    assert result['truncated'] is True
    assert 'private' not in str(result)
    cancelled = False
    async def stalled(**kwargs):
        nonlocal cancelled
        try:
            await asyncio.Event().wait()
        finally:
            cancelled = True
    read.side_effect = stalled
    with patch('vibes.copilot_host._DIAGNOSTICS_TIMEOUT', 0.01):
        assert await host.mcp_diagnostics('selected') == {'state': 'unavailable', 'servers': []}
    assert cancelled
    assert not lane.turn_lock.locked()
