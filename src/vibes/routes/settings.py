"""Settings APIs for the keychain and the shell environment (Classic API.md contract)."""

from aiohttp import web

from ..db import get_db
from ..secure import keychain as keychain_module
from ..secure.keychain import InvalidMasterPassword, MasterPasswordRequired
from ..secure.shell_secrets import env_name


def _stores(db):
    return keychain_module.stores(db)


async def _environment_snapshot(environment):
    variables = await environment.list()
    return {'variables': [{**row, 'overridden': row['override']} for row in variables],
            'count': len(variables), 'overrideCount': sum(row['override'] for row in variables)}


async def _entry_snapshot(keychain):
    return [{**row, 'envVar': env_name(row['name']), 'updatedAt': row['updated_at'],
             'createdAt': row['created_at'], 'userNote': row['user_note'],
             'agentNote': row['agent_note']} for row in await keychain.list()]


def _response(payload, *, status=200, headers=None):
    payload = {'ok': status < 400, **payload}
    if payload.get('code') == 'needs_master_password':
        payload['needs_master_password'] = True
    return web.json_response(payload, status=status, headers={
        **(headers or {}), 'Cache-Control': 'no-store',
    })


async def keychain_entries(request):
    db = await get_db()
    keychain, _ = _stores(db)
    try:
        if request.method == 'GET':
            return _response({'entries': await _entry_snapshot(keychain), 'enabled': True})
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError('Expected keychain entry object')
        name = payload.get('name')
        if request.method == 'DELETE':
            if not isinstance(name, str) or not name:
                raise ValueError('Keychain entry name is required')
            if not await keychain.delete(name):
                return _response({'error': 'Keychain entry not found', 'code': 'entry_not_found'}, status=404)
            return _response({'deleted': name, 'entries': await _entry_snapshot(keychain), 'enabled': True})
        if not isinstance(name, str) or not name:
            raise ValueError('Keychain entry name is required')
        entry = await keychain.save(
            name,
            payload.get('secret', ''),
            payload.get('username'),
            payload.get('type', 'secret'),
            user_note=payload.get('userNote', ''), agent_note=payload.get('agentNote', ''),
        )
        return _response({'entry': entry, 'entries': await _entry_snapshot(keychain), 'enabled': True}, status=201)
    except ValueError as exc:
        return _response({'error': str(exc), 'code': 'invalid_keychain_request'}, status=400)


async def keychain_reveal(request):
    db = await get_db()
    keychain, _ = _stores(db)
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError('Expected reveal request object')
        name = payload.get('name')
        if not isinstance(name, str) or not name:
            raise ValueError('Keychain entry name is required')
        supplied = payload.get('master_password')
        if supplied is not None and not isinstance(supplied, str):
            raise ValueError('Master password must be a string')
        if keychain.master_password and not supplied:
            return _response({'error': 'Master password required', 'code': 'needs_master_password'}, status=401)
        entry = await keychain.reveal(name, master_password=supplied or None)
        return _response({'entry': entry, 'secret': entry['secret'], 'username': entry['username']})
    except (MasterPasswordRequired, InvalidMasterPassword) as exc:
        return _response({'error': str(exc), 'code': 'needs_master_password'}, status=401)
    except LookupError as exc:
        return _response({'error': str(exc), 'code': 'entry_not_found'}, status=404)
    except ValueError as exc:
        return _response({'error': str(exc), 'code': 'invalid_keychain_request'}, status=400)


async def environment_settings(request):
    db = await get_db()
    _, environment = _stores(db)
    try:
        if request.method == 'GET':
            return _response(await _environment_snapshot(environment))
        payload = await request.json()
        if not isinstance(payload, dict) or 'name' not in payload:
            raise ValueError('Expected environment variable name and value or clear')
        if 'clear' in payload and type(payload['clear']) is not bool:
            raise ValueError('Clear must be a boolean')
        clear = payload.get('clear') is True
        if clear and 'value' in payload:
            raise ValueError('Clear and value cannot be combined')
        if not clear and 'value' not in payload:
            raise ValueError('Expected environment variable value')
        name = payload['name']
        if clear or payload.get('value') is None:
            if not await environment.clear(name):
                return _response({'error': 'No stored override', 'code': 'override_not_found'}, status=404)
            return _response({'cleared': name, **await _environment_snapshot(environment)})
        if not isinstance(payload['value'], str):
            raise ValueError('Environment value must be a string or null')
        row = await environment.set(name, payload['value'])
        return _response({'variable': row, **await _environment_snapshot(environment)}, status=201)
    except ValueError as exc:
        return _response({'error': str(exc), 'code': 'invalid_environment_request'}, status=400)


def setup_routes(app):
    app.router.add_get('/api/settings/keychain', keychain_entries)
    app.router.add_post('/api/settings/keychain', keychain_entries)
    app.router.add_delete('/api/settings/keychain', keychain_entries)
    app.router.add_post('/api/settings/keychain/reveal', keychain_reveal)
    app.router.add_get('/api/settings/environment', environment_settings)
    app.router.add_post('/api/settings/environment', environment_settings)
