"""Canonical FFI model observations stay inside an already-owned idle lane."""

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from vibes.copilot_host import CopilotHost
from vibes.routes import classic_model as routes
from vibes.sessions import SessionStore


@pytest.fixture
def native(monkeypatch):
    host = CopilotHost()
    host.runtime.client = SimpleNamespace(rpc=SimpleNamespace(sessions=SimpleNamespace(save=AsyncMock())))
    lane = host.lane('default')
    lane.client = host.runtime.client
    state = {'modelId': 'one', 'reasoningEffort': 'low'}
    calls = []

    async def current(**kwargs):
        assert lane.turn_lock.locked()
        return dict(state)

    async def listing(**kwargs):
        return {'list': [{'id': 'one', 'name': 'One', 'apiKey': 'private', 'supportedReasoningEfforts': ['low', 'high']},
                         {'id': 'two', 'supportedReasoningEfforts': ['low', 'high']}]}

    async def switch(argument, **kwargs):
        assert lane.turn_lock.locked()
        calls.append(('model', argument.model_id))
        state['modelId'] = argument.model_id

    async def thinking(argument, **kwargs):
        assert lane.turn_lock.locked()
        calls.append(('thinking', argument.reasoning_effort))
        state['reasoningEffort'] = argument.reasoning_effort

    rpc = SimpleNamespace(get_current=current, list=listing, switch_to=switch, set_reasoning_effort=thinking)
    session = SimpleNamespace(session_id='private-native-id', rpc=SimpleNamespace(model=rpc))
    lane.sessions['default'] = session
    # Deterministic generated-request types only; no SDK runtime import/start.
    fake = SimpleNamespace(ModelSwitchToRequest=lambda **kw: SimpleNamespace(**kw),
                           ModelSetReasoningEffortRequest=lambda **kw: SimpleNamespace(**kw),
                           SessionsSaveRequest=lambda **kw: SimpleNamespace(**kw))
    monkeypatch.setitem(sys.modules, 'copilot.generated.rpc', fake)
    return host, lane, session, state, calls


async def client_for(db, monkeypatch, host):
    monkeypatch.setattr(routes, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(routes.agents, '_resolve_agent_mode', lambda _: 'copilot-ffi')
    monkeypatch.setattr(routes.agents, 'copilot_backend', host)
    monkeypatch.setattr(routes, 'broadcast_session_event', AsyncMock())
    app = web.Application()
    routes.setup_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


@pytest.mark.asyncio
async def test_real_ffi_lane_choices_write_confirmation_and_stale_token(db, monkeypatch, native):
    host, lane, _, state, calls = native
    client = await client_for(db, monkeypatch, host)
    try:
        data = await (await client.get('/api/sessions/default/model')).json()
        assert data['current'] == 'copilot/one' and data['supports_thinking']
        assert 'private' not in str(data)
        body = {'model': data['current'], 'thinking_level': 'high', 'thinking_token': data['thinking_token']}
        response = await client.patch('/api/sessions/default/model', json=body)
        assert response.status == 200 and (await response.json())['thinking_level'] == 'high'
        response = await client.patch('/api/sessions/default/model', json=body)
        assert response.status == 409 and calls == [('thinking', 'high')]
        response = await client.patch('/api/sessions/default/model', json={'model': 'copilot/two'})
        assert response.status == 200 and state['modelId'] == 'two'
        response = await client.patch('/api/sessions/default/model', json={'model': 'copilot/foreign'})
        assert response.status == 400
        assert not lane.turn_lock.locked()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_passive_unbound_busy_and_other_lane_do_not_acquire_session(db, monkeypatch, native):
    host, lane, _, _, calls = native
    other = await SessionStore(db).create('Other')
    client = await client_for(db, monkeypatch, host)
    try:
        response = await client.get(f"/api/sessions/{other['id']}/model")
        assert not (await response.json())['available']
        assert other['id'] not in host.lanes
        await lane.turn_lock.acquire()
        response = await client.get('/api/sessions/default/model')
        assert not (await response.json())['available'] and not calls
        lane.turn_lock.release()
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['lane', 'session', 'client', 'closing'])
async def test_identity_change_during_read_rejects_stale_snapshot(native, change):
    host, lane, session, _, _ = native

    async def read(**kwargs):
        if change == 'lane':
            del host.lanes['default']
        elif change == 'session':
            lane.sessions['default'] = object()
        elif change == 'client':
            lane.client = host.runtime.client = object()
        else:
            lane.closing = True
        return {'modelId': 'one', 'reasoningEffort': 'low'}

    session.rpc.model.get_current = read
    with pytest.raises(RuntimeError):
        await host.classic_model('default')
    assert not lane.turn_lock.locked() and not lane.model_observations


@pytest.mark.asyncio
async def test_uncertain_setter_invalidates_token_and_releases_lane(native):
    host, lane, session, _, calls = native
    observed = await host.classic_model('default')
    token = observed['thinking_token']

    async def cancel(*args, **kwargs):
        assert 'default' not in lane.model_observations
        raise asyncio.CancelledError()

    session.rpc.model.set_reasoning_effort = cancel
    body = {'model': 'copilot/one', 'thinking_level': 'high', 'thinking_token': token}
    with pytest.raises(asyncio.CancelledError):
        await host.classic_model('default', body)
    assert not lane.turn_lock.locked()
    with pytest.raises(RuntimeError):
        await host.classic_model('default', body)
    assert not calls


@pytest.mark.asyncio
async def test_existing_binding_saved_only_after_confirmed_native_write(db, native):
    host, lane, _, _, _ = native
    store = SessionStore(db)
    await store.bind_backend('default', 'copilot-ffi', 'private-native-id')
    await host.classic_model('default', {'model': 'copilot/two'}, store)
    host.runtime.client.rpc.sessions.save.assert_awaited_once()
    assert (await store.backend_binding('default', 'copilot-ffi'))['model'] == 'two'
    assert not lane.turn_lock.locked()


@pytest.mark.asyncio
@pytest.mark.parametrize('malformed', [[], {'modelId': None}, {'modelId': 'one', 'reasoningEffort': []}])
async def test_malformed_native_state_fails_closed(native, malformed):
    host, lane, session, _, _ = native
    session.rpc.model.get_current = AsyncMock(return_value=malformed)
    with pytest.raises(RuntimeError):
        await host.classic_model('default')
    assert not lane.turn_lock.locked()


@pytest.mark.asyncio
async def test_bad_reasoning_revokes_old_observation(native):
    host, lane, session, state, _ = native
    token = (await host.classic_model('default'))['thinking_token']
    state['reasoningEffort'] = []
    with pytest.raises(RuntimeError):
        await host.classic_model('default')
    assert not lane.model_observations
    state['reasoningEffort'] = 'low'
    with pytest.raises(RuntimeError):
        await host.classic_model('default', {'model': 'copilot/one', 'thinking_level': 'high', 'thinking_token': token})


@pytest.mark.asyncio
async def test_rpc_timeouts_project_unavailable_or_unconfirmed_not_500(db, monkeypatch, native):
    host, lane, session, _, _ = native
    client = await client_for(db, monkeypatch, host)
    original = session.rpc.model.get_current
    try:
        session.rpc.model.get_current = AsyncMock(side_effect=TimeoutError('private read timeout'))
        response = await client.get('/api/sessions/default/model')
        assert response.status == 200 and not (await response.json())['available']
        session.rpc.model.get_current = original
        session.rpc.model.switch_to = AsyncMock(side_effect=TimeoutError('private setter timeout'))
        response = await client.patch('/api/sessions/default/model', json={'model': 'copilot/two'})
        assert response.status == 409 and 'private' not in await response.text()
        assert not lane.turn_lock.locked() and not lane.model_observations
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_failed_catalogue_read_revokes_existing_token(native):
    host, lane, session, _, _ = native
    token = (await host.classic_model('default'))['thinking_token']
    original = session.rpc.model.list
    session.rpc.model.list = AsyncMock(side_effect=TimeoutError())
    with pytest.raises(TimeoutError):
        await host.classic_model('default')
    assert not lane.model_observations
    session.rpc.model.list = original
    with pytest.raises(RuntimeError):
        await host.classic_model('default', {'model': 'copilot/one', 'thinking_level': 'high', 'thinking_token': token})
