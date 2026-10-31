"""Canonical media scope never falls back to global numeric access."""

from unittest.mock import AsyncMock

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from vibes.routes import classic_media as routes, media
from vibes.sessions import SessionStore


async def client_for(db, monkeypatch):
    monkeypatch.setattr(routes, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(media, 'get_db', AsyncMock(return_value=db))
    app = web.Application(client_max_size=12 * 1024 * 1024)
    media.setup_routes(app)
    routes.setup_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


def upload_form(data=b'hello', content_type='text/plain'):
    form = aiohttp.FormData()
    form.add_field('file', data, filename='test.txt', content_type=content_type)
    return form


@pytest.mark.asyncio
async def test_upload_shape_ownership_and_safe_read_headers(db, monkeypatch):
    client = await client_for(db, monkeypatch)
    try:
        response = await client.post('/api/sessions/default/media', data=upload_form(b'<html>active</html>', 'text/html'))
        assert response.status == 201
        saved = (await response.json())['media']
        assert saved['session_id'] == 'default' and saved['id'] > 0
        key = saved['id']
        response = await client.get(f'/api/sessions/default/media/{key}')
        assert (await response.json())['session_id'] == 'default'
        for path in (f'/api/sessions/default/media/{key}/raw', f'/api/media/{key}/raw?session_id=default',
                     f'/api/sessions/default/media/{key}/thumbnail'):
            response = await client.get(path)
            assert response.status == 200 and await response.read() == b'<html>active</html>'
            assert response.headers['Content-Disposition'] == 'attachment'
            assert response.headers['Content-Security-Policy'] == "sandbox; default-src 'none'"
            assert response.headers['Cache-Control'] == 'no-store'
            assert response.headers['X-Content-Type-Options'] == 'nosniff'
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_numeric_id_never_grants_foreign_or_unowned_bytes(db, monkeypatch):
    other = await SessionStore(db).create('Other')
    own = await db.create_media('own', 'text/plain', b'private', metadata={'session_id': 'default'})
    unowned = await db.create_media('legacy', 'text/plain', b'legacy')
    client = await client_for(db, monkeypatch)
    try:
        for path, status in ((f'/api/media/{own}', 400), (f'/api/media/{own}/raw', 400),
                             (f'/api/media/{own}/raw?session_id={other["id"]}', 404),
                             (f'/api/sessions/{other["id"]}/media/{own}/raw', 404),
                             (f'/api/sessions/default/media/{unowned}/raw', 404),
                             (f'/api/media/{own}/raw?session_id=default&session_id={other["id"]}', 400),
                             (f'/api/sessions/default/media/{own}?session_id=default', 400),
                             ('/api/sessions/default/media/true/raw', 400),
                             (f'/api/sessions/missing/media/{own}/raw', 404)):
            response = await client.get(path)
            assert response.status == status
            assert 'private' not in await response.text()
        # Legacy feed remains compatible inside the trusted single-user app.
        response = await client.get(f'/media/{own}')
        assert response.status == 200 and await response.read() == b'private'
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_upload_validation_size_archive_and_metadata_redaction(db, monkeypatch):
    archived = await SessionStore(db).create('Archived')
    await SessionStore(db).update(archived['id'], archived=True)
    client = await client_for(db, monkeypatch)
    try:
        for path in ('/api/sessions/missing/media', f'/api/sessions/{archived["id"]}/media'):
            response = await client.post(path, data=upload_form())
            assert response.status == 404
        response = await client.post('/api/sessions/default/media?session_id=foreign', data=upload_form())
        assert response.status == 400
        response = await client.post('/api/sessions/default/media', data='not multipart')
        assert response.status == 400
        monkeypatch.setattr(media, 'MAX_UPLOAD_SIZE', 3)
        response = await client.post('/api/sessions/default/media', data=upload_form(b'oversized'))
        assert response.status == 413
        key = await db.create_media('owned', 'text/plain', b'owned', metadata={'session_id': 'default', 'secret': 'private-meta', 'original_url': 'https://private/'})
        response = await client.get(f'/api/media/{key}?session_id=default')
        result = await response.json()
        assert result['session_id'] == 'default' and 'private' not in str(result)
    finally:
        await client.close()
