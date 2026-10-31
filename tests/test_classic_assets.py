"""The consumer binding serves pinned Classic assets without hiding API failures."""

import json
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from vibes.app import STATIC_PATH, create_app
from vibes.middleware import is_public_route


@pytest.mark.asyncio
async def test_classic_assets_and_viewers():
    app = create_app()
    # This binding test must never start an agent, queue, or real database.
    app.on_startup.clear()
    app.on_cleanup.clear()
    async with TestClient(TestServer(app)) as client:
        for path, mime in [('/', 'text/html'), ('/dist/app.bundle.js', 'javascript'),
                           ('/dist/app.bundle.css', 'text/css'), ('/css/gi-settings.css', 'text/css')]:
            response = await client.get(path)
            assert response.status == 200, path
            assert mime in response.headers['Content-Type']
            assert response.headers['X-Content-Type-Options'] == 'nosniff'
            assert response.headers['X-Frame-Options'] == 'DENY'
            assert response.headers['Cache-Control'] == ('no-store' if path == '/' else 'no-cache, must-revalidate')
            assert len(await response.read()) > 100
        policy_file = STATIC_PATH.resolve().parents[0] / 'piclaw/viewers-3.3.4/csp.json'
        policies = json.loads(policy_file.read_text())
        for path, policy in policies.items():
            response = await client.get(path + '?path=notes/a.md')
            assert response.status == 200
            assert response.headers['Content-Security-Policy'] == policy
            assert response.headers['X-Frame-Options'] == 'SAMEORIGIN'
            assert response.headers['Cache-Control'] == 'no-cache'
            assert await response.read() == (STATIC_PATH / path.strip('/') / 'index.html').read_bytes()
        response = await client.get('/chat/example')
        assert response.status == 200 and response.headers['Cache-Control'] == 'no-store'
        for path in ['/api/not-a-route', '/agent/not-a-route', '/workspace/not-a-route',
                     '/dist/missing.js', '/missing.js']:
            assert (await client.get(path)).status == 404, path
        assert (await client.post('/unknown')).status in (404, 405)


@pytest.mark.asyncio
async def test_opaque_widget_modules_do_not_open_cross_origin_apis():
    app = create_app()
    app.on_startup.clear()
    app.on_cleanup.clear()
    async with TestClient(TestServer(app)) as client:
        response = await client.get('/dist/app.bundle.js', headers={'Origin': 'null'})
        assert response.status == 200
        assert response.headers['Access-Control-Allow-Origin'] == '*'
        assert (await client.get('/health', headers={'Origin': 'null'})).status == 403
        assert (await client.post('/dist/app.bundle.js', headers={'Origin': 'null'})).status == 403
        assert (await client.get('/dist/app.bundle.js', headers={'Origin': 'https://foreign.test'})).status == 403


def test_classic_binding_and_public_asset_classification():
    assert Path(STATIC_PATH).is_symlink()
    assert Path(STATIC_PATH).readlink() == Path('../../references/fixtures-vibes/ui/classic/static')
    for path in ['/dist/app.bundle.js', '/css/gi-settings.css', '/js/vendor/preact.js', '/static/icon-192.png']:
        assert is_public_route(path)
    for path in ['/api/sessions', '/workspace/file', '/distinction', '/image-viewer/']:
        assert not is_public_route(path)
