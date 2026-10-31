"""Classic boot services run on main without inventing native capabilities."""

import asyncio
import hashlib
import json
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from vibes.routes import classic, sse, workspace
from vibes.routes.system_metrics import setup_routes as metrics_routes
from vibes.sessions import SessionStore


@pytest.mark.asyncio
async def test_workspace_aliases_and_truthful_index_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'hello.md').write_text('hello')
    app = web.Application()
    workspace.setup_routes(app)
    async with TestClient(TestServer(app)) as client:
        legacy = await (await client.get('/workspace/tree')).json()
        response = await client.get('/api/workspace/tree')
        tree = await response.json()
        assert response.status == 200 and tree['type'] == 'dir'
        assert tree['path'] == legacy['root']['path']
        assert any(child['name'] == 'hello.md' for child in tree['children'])
        assert 'root' not in tree
        response = await client.get('/api/workspace/stat?path=hello.md')
        stat = await response.json()
        assert response.status == 200 and stat['size'] == 5
        assert stat['revision'] == hashlib.sha256(b'hello').hexdigest()
        response = await client.get('/api/workspace/index')
        data = await response.json()
        assert response.status == 200 and data['state'] == 'failed' and not data['available']
        assert (await client.post('/api/workspace/index')).status == 501
        assert (await client.get('/api/workspace/stat?path=../outside')).status == 403
        assert (await client.get('/api/workspace/stat?path=missing')).status == 404
        assert await (await client.get('/api/workspace/raw?path=hello.md')).text() == 'hello'


@pytest.mark.asyncio
async def test_quick_actions_and_metrics_boot_without_agent(db, monkeypatch):
    from vibes.routes import system_metrics
    monkeypatch.setattr(system_metrics.SystemMetrics, 'get', AsyncMock(return_value={'available': False, 'metrics': {}}))
    no_agent = AsyncMock(side_effect=AssertionError('boot must not acquire an agent'))
    monkeypatch.setattr(classic.agents, '_ensure_agent', no_agent, raising=False)
    app = web.Application()
    classic.setup_routes(app)
    metrics_routes(app)
    async with TestClient(TestServer(app)) as client:
        response = await client.get('/api/quick-actions')
        assert response.status == 200
        assert await response.json() == {'workspaceCommands': [], 'slashCommands': [], 'commands': []}
        for path in ['/api/system-metrics', '/system/metrics']:
            response = await client.get(path)
            assert response.status == 200 and not (await response.json())['available']
        no_agent.assert_not_called()


@pytest.mark.asyncio
async def test_topic_stream_isolated_and_subscription_cleaned(db, monkeypatch):
    monkeypatch.setattr(sse, 'get_db', AsyncMock(return_value=db))
    store = SessionStore(db)
    assert await store.get('default')
    other = await store.create(name='other')
    app = web.Application()
    sse.setup_routes(app)
    async with TestClient(TestServer(app)) as client:
        assert (await client.get('/sse/topics?topic=unknown&session_id=default')).status == 400
        assert (await client.get('/sse/topics?topic=runtime.tool&session_id=missing')).status == 404
        response = await client.get('/sse/topics?topic=runtime.tool&session_id=default')
        assert response.status == 200
        assert await response.content.readuntil(b'\n\n') == b'event: connected\ndata: {}\n\n'
        topic_queue = next(iter(sse._topic_clients))
        await sse.broadcast_session_event('runtime.tool', {'tool': 'foreign'}, other['id'])
        await sse.broadcast_event('runtime.tool', {'session_id': 'default', 'tool': 'unverified-owner'})
        assert topic_queue.empty()
        await sse.broadcast_session_event('runtime.tool', {'tool': 'owned'}, 'default')
        frame = await asyncio.wait_for(response.content.readuntil(b'\n\n'), 1)
        envelope = json.loads(frame.split(b'data: ')[1])
        assert envelope == {'tool': 'owned', 'session_id': 'default'}
        response.close()
    assert not sse._topic_clients
