"""Classic persistent identity and enforced upload settings."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from vibes.config import get_config
from vibes.db import Database
from vibes.routes import classic_media, instance_settings, workspace


@pytest.mark.asyncio
async def test_identity_revision_and_restart_activation(db, monkeypatch):
    monkeypatch.setattr(instance_settings, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(get_config(), 'agent_name', 'Before')
    monkeypatch.setattr(get_config(), 'user_name', 'User')
    app = web.Application()
    instance_settings.setup_routes(app)
    async with TestClient(TestServer(app)) as client:
        before = await (await client.get('/api/settings/identity')).json()
        body = {'assistant_name': 'After', 'user_name': 'Rui', 'revision': before['saved']['revision']}
        response = await client.patch('/api/settings/identity', json=body)
        data = await response.json()
        assert response.status == 200 and data['restart_required']
        assert data['active']['assistant_name'] == 'Before'
        assert (await client.patch('/api/settings/identity', json=body)).status == 409
        assert (await client.patch('/api/settings/identity', json={**body, 'assistant_name': '\n'})).status == 400
        await instance_settings.apply_saved_identity()
        current = await (await client.get('/api/settings/identity')).json()
        assert current['active']['assistant_name'] == 'After' and not current['restart_required']


@pytest.mark.asyncio
async def test_general_persists_and_enforces_upload_limit(db, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(instance_settings, 'get_db', AsyncMock(return_value=db))
    app = web.Application(client_max_size=3 * 1024 * 1024)
    instance_settings.setup_routes(app)
    workspace.setup_routes(app)
    async with TestClient(TestServer(app)) as client:
        for value in [0, 1025, True, 1.5]:
            assert (await client.post('/api/settings/general', json={'workspaceUploadLimitMb': value})).status == 400
        assert (await client.post('/api/settings/general', json={'maxIterations': 3})).status == 400
        response = await client.post('/api/settings/general', json={'workspaceUploadLimitMb': 1})
        assert response.status == 200
        assert 'maxIterations' not in (await response.json())['settings']
        from aiohttp import FormData
        form = FormData()
        form.add_field('file', b'x' * (1024 * 1024 + 1), filename='large.bin')
        assert (await client.post('/api/workspace/upload', data=form)).status == 413
        assert not (tmp_path / 'large.bin').exists()
        settings = await (await client.get('/api/settings/general')).json()
        assert settings['settings']['workspaceUploadLimitMb'] == 1
        reopened = Database(db.db_path)
        await reopened.connect()
        try:
            monkeypatch.setattr(instance_settings, 'get_db', AsyncMock(return_value=reopened))
            assert await instance_settings.upload_limit_mb() == 1
        finally:
            await reopened.close()


@pytest.mark.asyncio
async def test_unverified_native_policy_and_provider_mutations_stay_unavailable(db, monkeypatch):
    monkeypatch.setattr(instance_settings, 'get_db', AsyncMock(return_value=db))
    app = web.Application()
    instance_settings.setup_routes(app)
    async with TestClient(TestServer(app)) as client:
        for name in ['providers', 'compaction']:
            response = await client.get('/api/settings/' + name)
            assert response.status == 200 and not (await response.json())['available']
            assert (await client.patch('/api/settings/' + name, json={})).status == 501


@pytest.mark.asyncio
async def test_scoped_media_collection(db, monkeypatch):
    monkeypatch.setattr(classic_media, 'get_db', AsyncMock(return_value=db))
    own = await db.create_media('a.png', 'image/png', b'a', metadata={'session_id': 'default'})
    await db.create_media('other.png', 'image/png', b'b', metadata={'session_id': 'foreign'})
    app = web.Application()
    classic_media.setup_routes(app)
    async with TestClient(TestServer(app)) as client:
        data = await (await client.get('/api/sessions/default/media')).json()
        assert [item['id'] for item in data['media']] == [own]
        assert (await client.get('/api/sessions/missing/media')).status == 404
        assert (await client.get('/api/sessions/default/media?session_id=foreign')).status == 400


@pytest.mark.asyncio
async def test_identity_competing_writers_one_revision_wins(db, monkeypatch):
    monkeypatch.setattr(instance_settings, 'get_db', AsyncMock(return_value=db))
    app = web.Application()
    instance_settings.setup_routes(app)
    async with TestClient(TestServer(app)) as client:
        responses = await asyncio.gather(*[client.patch('/api/settings/identity', json={
            'revision': '0', 'assistant_name': f'Agent {i}', 'user_name': 'Rui'}) for i in range(2)])
        assert sorted(response.status for response in responses) == [200, 409]
