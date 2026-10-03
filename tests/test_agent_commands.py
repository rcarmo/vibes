"""Command discovery must not switch or consume another session's Pi stream."""
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from vibes import pi_client
from vibes.routes import agents
from vibes.sessions import SessionStore

@pytest_asyncio.fixture
async def client(aiohttp_client, db):
    from aiohttp import web
    routes = agents
    app = web.Application()
    routes.setup_routes(app)
    with patch.object(routes, 'get_db', AsyncMock(return_value=db)):
        yield await aiohttp_client(app)



@pytest.mark.asyncio
async def test_commands_default_and_missing_session(client):
    with patch.object(agents, 'get_config') as config:
        config.return_value.pi_enabled = False
        response = await client.get('/agent/commands')
        assert response.status == 200
        assert '/theme' in [cmd['name'] for cmd in (await response.json())['commands']]
        response = await client.get('/agent/commands?session_id=missing')
        assert response.status == 404


@pytest.mark.asyncio
async def test_commands_use_guarded_selected_inspection(client, db):
    session = {'id': 'default'}
    with patch.object(agents, 'get_config') as config, \
         patch('vibes.pi_client.inspect_model_state', AsyncMock(return_value={
             'success': True, 'data': {'commands': [{'name': '/private', 'description': 'Scoped'}]}
         })) as inspect, \
         patch.object(pi_client, 'send_rpc_command', AsyncMock()) as raw:
        config.return_value.pi_enabled = True
        config.return_value.default_agent = 'pi'
        response = await client.get('/agent/commands', params={'session_id': session['id']})
        assert response.status == 200
        assert '/private' in [cmd['name'] for cmd in (await response.json())['commands']]
        inspect.assert_awaited_once_with(session['id'])
        raw.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['busy', 'other', 'uncertain', 'offline'])
async def test_commands_never_read_busy_unconfirmed_or_other_pi_context(client, mode):
    from importlib import import_module
    pi_client = import_module('vibes.pi_client')
    state = pi_client._state
    previous_active = state.session_selector.active
    previous_uncertain = state.session_selector.uncertain
    state.session_selector.active = 'default' if mode != 'other' else 'other'
    state.session_selector.uncertain = mode == 'uncertain'
    if mode == 'busy':
        await state.request_lock.acquire()
    try:
        with patch.object(agents, 'get_config') as config, \
             patch.object(pi_client, 'is_pi_running', return_value=mode != 'offline'), \
             patch.object(pi_client, 'send_rpc_command', AsyncMock()) as raw:
            config.return_value.pi_enabled = True
            config.return_value.default_agent = 'pi'
            response = await client.get('/agent/commands?session_id=default')
            assert response.status == 200
            assert '/theme' in [cmd['name'] for cmd in (await response.json())['commands']]
            raw.assert_not_awaited()
    finally:
        if state.request_lock.locked():
            state.request_lock.release()
        state.session_selector.active = previous_active
        state.session_selector.uncertain = previous_uncertain


@pytest.mark.asyncio
async def test_acp_commands_do_not_inspect_pi(client):
    with patch.object(agents, 'get_config') as config, \
         patch('vibes.pi_client.inspect_model_state', AsyncMock()) as inspect:
        config.return_value.pi_enabled = True
        config.return_value.default_agent = 'acp'
        assert (await client.get('/agent/commands')).status == 200
        inspect.assert_not_awaited()


@pytest.mark.asyncio
async def test_nondefault_advertises_only_supported_appearance_commands(client, db):
    session = await SessionStore(db).create('Other')
    with patch('vibes.pi_client.inspect_model_state', AsyncMock()) as inspect:
        response = await client.get('/agent/commands', params={'session_id': session['id']})
        assert response.status == 200
        assert [command['name'] for command in (await response.json())['commands']] == ['/theme', '/tint']
        inspect.assert_not_awaited()


@pytest.mark.asyncio
async def test_ffi_catalogue_is_discovery_not_executable_commands(client, monkeypatch):
    from unittest.mock import AsyncMock
    from vibes.routes import agents
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda _: 'copilot-ffi')
    discovery = AsyncMock(return_value={'available': True, 'commands': [{'name': 'native'}], 'skills': []})
    monkeypatch.setattr(agents.copilot_backend, 'command_catalogue', discovery)
    response = await client.get('/agent/commands')
    assert response.status == 200
    body = await response.json()
    assert body['commands'] == []
    assert body['native_execution_supported'] is False
    assert body['native_catalogue']['commands'] == [{'name': 'native'}]
    assert discovery.await_args.args[0] == 'default'


@pytest.mark.asyncio
async def test_ffi_named_chat_busy_catalogue_is_scoped_and_missing_chat_is_not_queried(client, db, monkeypatch):
    from vibes.routes import agents
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda _: 'copilot-ffi')
    session = await SessionStore(db).create('Native chat')
    busy = {'available': False, 'busy': True, 'commands': [], 'skills': []}
    discovery = AsyncMock(return_value=busy)
    monkeypatch.setattr(agents.copilot_backend, 'command_catalogue', discovery)
    response = await client.get('/agent/commands', params={'session_id': session['id']})
    assert response.status == 200
    body = await response.json()
    assert body['native_catalogue'] == busy
    assert body['commands'] == [] and body['native_execution_supported'] is False
    discovery.assert_awaited_once()
    assert discovery.await_args.args[0] == session['id']
    response = await client.get('/agent/commands', params={'session_id': 'missing-chat'})
    assert response.status == 404
    discovery.assert_awaited_once()
