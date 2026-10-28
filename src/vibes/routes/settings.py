"""Settings APIs for the keychain and the shell environment (Classic API.md contract)."""

from aiohttp import web

from ..db import get_db
from ..secure import keychain as keychain_module
from ..secure.keychain import InvalidMasterPassword, MasterPasswordRequired


def _stores(db):
    return keychain_module.stores(db)


def _response(payload, *, status=200, headers=None):
    return web.json_response(payload, status=status, headers={
        **(headers or {}), 'Cache-Control': 'no-store',
    })


async def keychain_entries(request):
    db = await get_db()
    keychain, _ = _stores(db)
    try:
        if request.method == 'GET':
            return _response({'entries': await keychain.list()},
                                     headers={'Cache-Control': 'no-store'})
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError('Expected keychain entry object')
        name = payload.get('name')
        if request.method == 'DELETE':
            if not isinstance(name, str) or not name:
                raise ValueError('Keychain entry name is required')
            if not await keychain.delete(name):
                return _response({'error': 'Keychain entry not found', 'code': 'entry_not_found'}, status=404)
            return _response({'deleted': name})
        if not isinstance(name, str) or not name:
            raise ValueError('Keychain entry name is required')
        entry = await keychain.save(
            name,
            payload.get('secret', ''),
            payload.get('username'),
            payload.get('type', 'secret'),
        )
        return _response({'entry': entry}, status=201)
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
        return _response({'entry': entry}, headers={'Cache-Control': 'no-store'})
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
            return _response({'variables': await environment.list()},
                                     headers={'Cache-Control': 'no-store'})
        payload = await request.json()
        if not isinstance(payload, dict) or not {'name', 'value'} <= payload.keys():
            raise ValueError('Expected environment variable name and value')
        name = payload['name']
        if payload.get('value') is None:
            if not await environment.clear(name):
                return _response({'error': 'No stored override', 'code': 'override_not_found'}, status=404)
            return _response({'cleared': name})
        if not isinstance(payload['value'], str):
            raise ValueError('Environment value must be a string or null')
        row = await environment.set(name, payload['value'])
        return _response({'variable': row}, status=201)
    except ValueError as exc:
        return _response({'error': str(exc), 'code': 'invalid_environment_request'}, status=400)


def setup_routes(app):
    app.router.add_get('/api/settings/keychain', keychain_entries)
    app.router.add_post('/api/settings/keychain', keychain_entries)
    app.router.add_delete('/api/settings/keychain', keychain_entries)
    app.router.add_post('/api/settings/keychain/reveal', keychain_reveal)
    app.router.add_get('/api/settings/environment', environment_settings)
    app.router.add_post('/api/settings/environment', environment_settings)
