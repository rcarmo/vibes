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
