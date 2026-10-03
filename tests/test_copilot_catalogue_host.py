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
