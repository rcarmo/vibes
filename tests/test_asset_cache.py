"""Verify cache policy on the real SPA/static routes, including 304 responses."""
import importlib

import pytest

@pytest.mark.asyncio
async def test_spa_and_mutable_assets_revalidate(aiohttp_client):
    app_module = importlib.import_module('vibes.app')
    app = app_module.create_app()
    # Keep production routes and response hooks, but do not launch agents/watchers.
    app.on_startup.clear()
    app.on_cleanup.clear()
    client = await aiohttp_client(app)
    response = await client.get('/')
    assert response.headers['Cache-Control'] == 'no-store'
    html = await response.text()
    assert '/static/dist/app.js?v=' in html
    assert '?v=1"' not in html
    for path in ('/static/dist/app.js?v=1', '/static/dist/app.css?v=1',
                 '/static/js/components/session-picker.js'):
        response = await client.get(path)
        await response.read()
        assert response.status == 200
        assert response.headers['Cache-Control'] == 'no-cache, must-revalidate'
        etag = response.headers['Etag']
        response = await client.get(path, headers={'If-None-Match': etag})
        assert response.status == 304
        assert response.headers['Cache-Control'] == 'no-cache, must-revalidate'
    response = await client.get('/static/index.html')
    assert response.headers['Cache-Control'] == 'no-store'
