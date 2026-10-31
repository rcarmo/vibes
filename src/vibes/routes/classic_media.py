"""Canonical media requires explicit persisted session ownership."""

import json
from aiohttp import web

from ..db import get_db
from ..sessions import SessionStore
from . import media
from .classic_messages import integer


def response(data, status=200):
    return web.json_response(data, status=status, headers={'Cache-Control': 'no-store'})


def project(saved, session_id):
    return {'id': saved['id'], 'session_id': session_id, 'filename': saved['filename'],
            'name': saved['filename'], 'content_type': saved['content_type'],
            'created_at': saved.get('created_at')}


def selector(request):
    path_session = request.match_info.get('session_id')
    if path_session is not None:
        if request.query:
            raise ValueError('Session scope comes from the path')
        return path_session
    if set(request.query) != {'session_id'} or len(request.query.getall('session_id')) != 1:
        raise ValueError('An explicit session_id is required')
    value = request.query['session_id']
    if not value:
        raise ValueError('An explicit session_id is required')
    return value


async def upload(request):
    session_id = request.match_info['session_id']
    if request.query:
        return response({'error': 'Session scope comes from the path'}, 400)
    try:
        result = await media._upload_media(request, session_id)
    except (ValueError, AssertionError):
        return response({'error': 'Invalid multipart upload'}, 400)
    if result.status >= 300:
        result.headers['Cache-Control'] = 'no-store'
        return result
    saved = json.loads(result.body)
    db = await get_db()
    row = await db.get_media(saved['id'])
    return response({'media': project(row, session_id)}, 201)


async def read(request):
    try:
        session_id = selector(request)
        media_id = integer(request.match_info['media_id'])
    except ValueError as exc:
        return response({'error': str(exc)}, 400)
    db = await get_db()
    if not await SessionStore(db).get(session_id):
        return response({'error': 'Session not found'}, 404)
    # Metadata and bytes share the write lock so a delete/replacement cannot
    # change ownership between validation and readback.
    async with db.transaction():
        saved = await db.get_media(media_id)
        metadata = saved.get('metadata') if saved else None
        if not isinstance(metadata, dict) or metadata.get('session_id') != session_id:
            return response({'error': 'Media not found'}, 404)
        kind = request.match_info.get('kind', 'info')
        if kind == 'info':
            return response(project(saved, session_id))
        data = await db.get_media_thumbnail(media_id) if kind == 'thumbnail' else None
        if not data:
            data = await db.get_media_data(media_id)
        if not data:
            return response({'error': 'Media not found'}, 404)
    result = media.media_response(data[1], data[0])
    result.headers['Cache-Control'] = 'no-store'
    return result


async def list_media(request):
    if request.query:
        return response({'error': 'Unexpected query parameters'}, 400)
    session_id = request.match_info['session_id']
    database = await get_db()
    if not await SessionStore(database).get(session_id):
        return response({'error': 'Session not found'}, 404)
    async with database._connection.execute(
        "SELECT id, filename, content_type, created_at, metadata FROM media "
        "WHERE json_extract(metadata, '$.session_id')=? ORDER BY id DESC LIMIT 100", (session_id,)
    ) as cursor:
        rows = await cursor.fetchall()
    return response({'media': [project({**dict(row), 'metadata': json.loads(row['metadata'] or '{}')}, session_id)
                                for row in rows]})


def setup_routes(app):
    app.router.add_get('/api/sessions/{session_id}/media', list_media)
    app.router.add_post('/api/sessions/{session_id}/media', upload)
    app.router.add_get('/api/sessions/{session_id}/media/{media_id}', read)
    app.router.add_get('/api/sessions/{session_id}/media/{media_id}/{kind:raw|thumbnail}', read)
    app.router.add_get('/api/media/{media_id}', read)
    app.router.add_get('/api/media/{media_id}/{kind:raw|thumbnail}', read)
