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
