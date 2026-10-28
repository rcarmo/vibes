"""Local, owner-scoped shell preparation for the Pi bash tool."""

import asyncio
from pathlib import Path

from aiohttp import web

from ..config import get_config
from ..db import get_db
from ..secure.keychain import stores
from ..secure.shell_exec import DEFAULT_TIMEOUT, prepare, run_prepared
from .pi_tools import _loopback


async def prepare_shell(request):
    from .. import agent_attachments

    headers = {'Cache-Control': 'no-store'}
    if not _loopback(request) or request.headers.get('Origin'):
        return web.json_response({'error': 'Local tool connection required'}, status=403, headers=headers)
    try:
        mode, session_id = agent_attachments.resolve_token(
            request.headers.get('Authorization', '').removeprefix('Bearer ')
        )
        owner = agent_attachments.active_for(session_id)

        def check_owner():
            if (not owner or agent_attachments.active_for(session_id) is not owner
                    or owner['mode'] != mode
                    or (session_id is not None and owner['session_id'] != session_id)):
                raise PermissionError('No matching active agent turn')

        check_owner()
        payload = await request.json()
        execute = request.path.endswith('/shell')
        allowed = {'command', 'timeout'} if execute else {'command'}
        if (not isinstance(payload, dict) or 'command' not in payload or set(payload) - allowed
                or not isinstance(payload['command'], str)):
            raise ValueError('Expected shell command string')
        timeout = payload.get('timeout', DEFAULT_TIMEOUT)
        if type(timeout) not in (int, float) or not 0 < timeout <= 3600:
            raise ValueError('Invalid shell timeout')
        keychain, environment = stores(await get_db())
        shell_path = get_config().shell_path or None
        plan = await prepare(payload['command'], keychain, environment, shell_path=shell_path)
        check_owner()
        if execute:
            operation = asyncio.create_task(run_prepared(
                plan, shell_path=shell_path, cwd=Path.cwd().resolve(), timeout=timeout,
            ))
            try:
                while not operation.done():
                    await asyncio.wait({operation}, timeout=0.1)
                    check_owner()
                    if request.transport is None or request.transport.is_closing():
                        raise PermissionError('Shell caller disconnected')
                return web.json_response(await operation, headers=headers)
            finally:
                if not operation.done():
                    operation.cancel()
                    await asyncio.gather(operation, return_exceptions=True)
        return web.json_response({
            'command': plan['text'], 'env': plan['env'], 'cwd': str(Path.cwd().resolve()),
            'shell_path': plan['shell']['path'], 'shell_kind': plan['shell']['kind'],
        }, headers=headers)
    except PermissionError as exc:
        return web.json_response({'error': str(exc)}, status=403, headers=headers)
    except (ValueError, LookupError, OSError):
        # Do not echo the substituted command or decrypted values on a preparation error.
        return web.json_response({'error': 'Shell preparation failed'}, status=400, headers=headers)


def setup_routes(app):
    app.router.add_post('/internal/agent-tools/shell-prepare', prepare_shell)
    app.router.add_post('/internal/agent-tools/shell', prepare_shell)
