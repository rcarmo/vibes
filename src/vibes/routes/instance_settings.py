"""Persistent Classic instance settings with transaction-bound revisions."""

import json

from aiohttp import web

from ..config import get_config
from ..db import get_db


def response(data, status=200):
    return web.json_response(data, status=status, headers={'Cache-Control': 'no-store'})


async def _read(connection, name, default):
    async with connection.execute('SELECT value, revision FROM instance_settings WHERE name=?', (name,)) as cursor:
        row = await cursor.fetchone()
    return (json.loads(row['value']), row['revision']) if row else (default, 0)


async def _write(connection, name, value, revision):
    await connection.execute('INSERT INTO instance_settings(name,value,revision) VALUES(?,?,?) '
        'ON CONFLICT(name) DO UPDATE SET value=excluded.value, revision=excluded.revision',
        (name, json.dumps(value), revision))


def _identity_default():
    config = get_config()
    return {'assistant_name': config.agent_name or 'Agent', 'user_name': config.user_name or 'You'}


async def identity(request):
    database = await get_db()
    active = _identity_default()
    async with database.transaction() as connection:
        saved, revision = await _read(connection, 'identity', active)
        if request.method == 'PATCH':
            try:
                body = await request.json()
            except (ValueError, TypeError):
                return response({'error': 'Invalid JSON'}, 400)
            if not isinstance(body, dict) or set(body) != {'assistant_name', 'user_name', 'revision'}:
                return response({'error': 'Names and revision are required'}, 400)
            for key in ('assistant_name', 'user_name'):
                value = body[key]
                if not isinstance(value, str) or not value.strip() or len(value) > 128 or any(ord(c) < 32 for c in value):
                    return response({'error': 'Names require 1–128 characters without control characters'}, 400)
            if body['revision'] != str(revision):
                return response({'error': 'Identity changed', 'code': 'revision_conflict'}, 409)
            saved = {key: body[key].strip() for key in ('assistant_name', 'user_name')}
            revision += 1
            await _write(connection, 'identity', saved, revision)
    return response({'active': active, 'saved': {**saved, 'revision': str(revision)},
                     'restart_required': saved != active})


async def apply_saved_identity(database=None):
    if database is None:
        database = await get_db()
    async with database.transaction() as connection:
        saved, _ = await _read(connection, 'identity', _identity_default())
    get_config().agent_name = saved['assistant_name']
    get_config().user_name = saved['user_name']


async def upload_limit_mb():
    database = await get_db()
    async with database.transaction() as connection:
        settings, _ = await _read(connection, 'general', {'workspaceUploadLimitMb': 5})
    return settings['workspaceUploadLimitMb']


async def general(request):
    database = await get_db()
    async with database.transaction() as connection:
        settings, revision = await _read(connection, 'general', {'workspaceUploadLimitMb': 5})
        if request.method == 'POST':
            try:
                body = await request.json()
            except (ValueError, TypeError):
                return response({'error': 'Invalid JSON'}, 400)
            if not isinstance(body, dict) or set(body) != {'workspaceUploadLimitMb'}:
                return response({'error': 'Only workspaceUploadLimitMb is supported'}, 400)
            limit = body['workspaceUploadLimitMb']
            if type(limit) is not int or not 1 <= limit <= 1024:
                return response({'error': 'Upload limit must be an integer from 1 to 1024 MiB'}, 400)
            settings = {'workspaceUploadLimitMb': limit}
            await _write(connection, 'general', settings, revision + 1)
    # No maxIterations field: this adapter cannot control native model/tool loops.
    return response({'ok': True, 'settings': settings})


async def unavailable_settings(request):
    if request.method != 'GET':
        return response({'error': 'Native settings mutation is unavailable', 'code': 'settings_unavailable'}, 501)
    if request.path.endswith('/providers'):
        return response({'available': False, 'providers': [], 'revision': 'unavailable'})
    return response({'available': False, 'saved': None, 'active': None, 'restart_required': False,
                     'reason': 'native-compaction-policy-unverified'})


def setup_routes(app):
    app.router.add_get('/api/settings/identity', identity)
    app.router.add_patch('/api/settings/identity', identity)
    app.router.add_get('/api/settings/general', general)
    app.router.add_post('/api/settings/general', general)
    for path in ('providers', 'compaction'):
        for method in ('GET', 'PATCH', 'DELETE') if path == 'providers' else ('GET', 'PATCH'):
            app.router.add_route(method, '/api/settings/' + path, unavailable_settings)
