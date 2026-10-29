"""Canonical model readback and optimistic thinking tokens use real Pi locking."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from vibes.routes import classic_model as routes
from vibes.sessions import SessionStore


async def client_for(db, monkeypatch):
    monkeypatch.setattr(routes, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(routes.agents, '_resolve_agent_mode', lambda _: 'pi')
    monkeypatch.setattr(routes, 'broadcast_session_event', AsyncMock())
    app = web.Application()
    routes.setup_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


def native(monkeypatch, chat='default'):
    module = routes.pi_client
    runtime = module._runtimes.get(chat)
    monkeypatch.setattr(runtime, 'request_lock', asyncio.Lock())
    monkeypatch.setattr(runtime, 'model_observation', None)
    monkeypatch.setattr(runtime, 'model_token', None)
    monkeypatch.setattr(module, 'is_pi_running', lambda: True)
    monkeypatch.setattr(module, '_select_idle_chat', AsyncMock())
    state = {'model': {'provider': 'p', 'id': 'one', 'name': 'One', 'reasoning': True,
                       'apiKey': 'private-secret', 'contextWindow': 4096}, 'thinkingLevel': 'low'}
    calls = []

    async def rpc(payload, timeout):
        assert runtime.request_lock.locked()
        calls.append(payload['type'])
        if payload['type'] == 'get_state':
            return {'success': True, 'data': {**state, 'model': dict(state['model'])}}
        if payload['type'] == 'get_available_models':
            return {'success': True, 'data': {'models': [state['model'], {'provider': 'p', 'id': 'two', 'apiKey': 'private'}]}}
        if payload['type'] == 'get_available_thinking_levels':
            return {'success': True, 'data': {'levels': ['low', 'high']}}
        if payload['type'] == 'set_thinking_level':
            state['thinkingLevel'] = payload['level']
        if payload['type'] == 'set_model':
            state['model'] = {'provider': payload['provider'], 'id': payload['modelId'], 'reasoning': True}
        return {'success': True}

    monkeypatch.setattr(module, 'send_rpc_command', rpc)
    return runtime, state, calls


@pytest.mark.asyncio
async def test_offered_choices_safe_projection_and_confirmed_model_readback(db, monkeypatch):
    client = await client_for(db, monkeypatch)
    runtime, state, calls = native(monkeypatch)
    try:
        response = await client.get('/api/sessions/default/model')
        data = await response.json()
        assert data['current'] == 'p/one' and data['available']
        assert data['model_options'][0]['id'] == 'p/one' and data['supports_thinking']
        assert data['thinking_token'] and 'private' not in str(data)
        response = await client.patch('/api/sessions/default/model', json={'model': 'p/two'})
        assert response.status == 200 and (await response.json())['current'] == 'p/two'
        assert 'set_model' in calls and not runtime.request_lock.locked()
        response = await client.patch('/api/sessions/default/model', json={'model': 'p/unknown'})
        assert response.status == 400
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_stale_thinking_and_replayed_tokens_rejected_under_native_lock(db, monkeypatch):
    client = await client_for(db, monkeypatch)
    runtime, state, calls = native(monkeypatch)
    try:
        data = await (await client.get('/api/sessions/default/model')).json()
        body = {'model': data['current'], 'thinking_level': 'high', 'thinking_token': data['thinking_token']}
        response = await client.patch('/api/sessions/default/model', json=body)
        assert response.status == 200 and (await response.json())['thinking_level'] == 'high'
        count = calls.count('set_thinking_level')
        response = await client.patch('/api/sessions/default/model', json=body)
        assert response.status == 409 and calls.count('set_thinking_level') == count
        data = await (await client.get('/api/sessions/default/model')).json()
        state['model']['id'] = 'two'  # Native/external state changed after observation.
        response = await client.patch('/api/sessions/default/model', json={**body, 'thinking_token': data['thinking_token']})
        assert response.status == 409 and calls.count('set_thinking_level') == count
        assert not runtime.request_lock.locked()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_busy_or_unsupported_lane_unavailable_without_dispatch(db, monkeypatch):
    client = await client_for(db, monkeypatch)
    runtime, _, calls = native(monkeypatch)
    try:
        await runtime.request_lock.acquire()
        response = await client.get('/api/sessions/default/model')
        assert (await response.json())['available'] is False
        response = await client.patch('/api/sessions/default/model', json={'model': 'p/two'})
        assert response.status == 409 and not calls
        runtime.request_lock.release()
        monkeypatch.setattr(routes.agents, '_resolve_agent_mode', lambda _: 'acp')
        response = await client.get('/api/sessions/default/model')
        assert (await response.json())['model_options'] == []
        response = await client.patch('/api/sessions/default/model', json={'model': 'p/two'})
        assert response.status == 409 and not calls
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_invalid_queries_fields_missing_archived_and_wrong_confirmation(db, monkeypatch):
    client = await client_for(db, monkeypatch)
    archived = await SessionStore(db).create('Archived')
    await SessionStore(db).update(archived['id'], archived=True)
    native(monkeypatch)
    try:
        for body in ([], {}, {'model': 'bad'}, {'model': 'p/one', 'thinking_level': 'high'},
                     {'model': 'p/one', 'thinking_level': 'high', 'thinking_token': None}):
            response = await client.patch('/api/sessions/default/model', json=body)
            assert response.status == 400
        response = await client.get('/api/sessions/default/model?provider=foreign')
        assert response.status == 400
        response = await client.get('/api/sessions/missing/model')
        assert response.status == 404
        response = await client.get(f"/api/sessions/{archived['id']}/model")
        assert (await response.json())['available'] is False
        monkeypatch.setattr(routes.pi_client, 'change_chat_model', AsyncMock(return_value={'success': True, 'data': {'model': {'provider': 'p', 'id': 'wrong'}}}))
        response = await client.patch('/api/sessions/default/model', json={'model': 'p/two'})
        assert response.status == 409
        routes.broadcast_session_event.assert_not_awaited()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_uncertain_setter_invalidates_token_before_dispatch(db, monkeypatch):
    client = await client_for(db, monkeypatch)
    runtime, _, _ = native(monkeypatch)
    original = routes.pi_client.send_rpc_command
    try:
        data = await (await client.get('/api/sessions/default/model')).json()
        token = data['thinking_token']

        async def cancel_setter(payload, timeout):
            if payload['type'] == 'set_thinking_level':
                assert runtime.model_token is None
                raise asyncio.CancelledError()
            return await original(payload, timeout)

        monkeypatch.setattr(routes.pi_client, 'send_rpc_command', cancel_setter)
        with pytest.raises(asyncio.CancelledError):
            await routes.pi_client.change_chat_model('default', thinking_level='high',
                                                      expected_model='p/one', expected_thinking_token=token)
        assert runtime.model_token is None and not runtime.request_lock.locked()
        with pytest.raises(RuntimeError):
            await routes.pi_client.change_chat_model('default', thinking_level='high',
                                                      expected_model='p/one', expected_thinking_token=token)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_native_malformed_payloads_fail_closed_and_no_unadvertised_thinking(db, monkeypatch):
    client = await client_for(db, monkeypatch)
    _, state, calls = native(monkeypatch)
    original = routes.pi_client.send_rpc_command
    try:
        for malformed in ([], {'success': True, 'data': []}, {'success': True, 'data': {'model': None}}):
            monkeypatch.setattr(routes.pi_client, 'send_rpc_command', AsyncMock(return_value=malformed))
            response = await client.get('/api/sessions/default/model')
            assert response.status == 200 and not (await response.json())['available']
        monkeypatch.setattr(routes.pi_client, 'send_rpc_command', original)
        state['model']['reasoning'] = False
        data = await (await client.get('/api/sessions/default/model')).json()
        assert not data['supports_thinking']
        response = await client.patch('/api/sessions/default/model', json={'model': data['current'],
                                     'thinking_level': 'high', 'thinking_token': data['thinking_token']})
        assert response.status == 400 and 'set_thinking_level' not in calls
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_acp_unverified_metadata_never_enables_speculative_model_rpc(db, monkeypatch):
    client = await client_for(db, monkeypatch)
    monkeypatch.setattr(routes.agents, '_resolve_agent_mode', lambda _: 'acp')
    module = routes.agents.acp_client
    runtime = module._runtimes.get('default')
    monkeypatch.setattr(runtime, 'reported_capabilities', {'models': {'currentModelId': 'private/model'}})
    monkeypatch.setattr(runtime, 'session_usage', {'default': {'models': ['unverified'], 'configOptions': [{'id': 'model'}]}})
    speculative = AsyncMock(side_effect=AssertionError('No verified ACP model RPC contract'))
    monkeypatch.setattr(module, '_send_request', speculative)
    monkeypatch.setattr(routes.pi_client, 'inspect_classic_model', speculative)
    try:
        response = await client.get('/api/sessions/default/model')
        data = await response.json()
        assert response.status == 200 and not data['available']
        assert data['reason'] == 'acp-model-contract-unverified' and not data['model_options']
        assert 'private' not in str(data) and data['thinking_token'] is None
        response = await client.patch('/api/sessions/default/model', json={'model': 'acp/unverified'})
        assert response.status == 409 and (await response.json())['code'] == 'acp-model-contract-unverified'
        speculative.assert_not_awaited()
    finally:
        await client.close()
