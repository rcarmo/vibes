"""Loopback-only tools for the Vibes-owned Pi extension."""
from aiohttp import web
from ..db import get_db
from ..message_tools import MessageTools


def _loopback(request):
    peer = request.transport.get_extra_info('peername') if request.transport else None
    return bool(peer and peer[0] in {'127.0.0.1', '::1'})


async def messages(request):
    if not _loopback(request):
        raise web.HTTPForbidden(text='Loopback only')
    from ..pi_client import _state
    session_id = _state.session_selector.active
    if _state.session_selector.uncertain or not session_id:
        raise web.HTTPConflict(text='Active Pi session is uncertain')
    try:
        payload = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text='Invalid JSON')
    if not isinstance(payload, dict):
        raise web.HTTPBadRequest(text='Expected object')
    allowed = {'action', 'row_ids', 'query', 'limit', 'before_row', 'after_row', 'context_before', 'context_after'}
    if set(payload) - allowed:
        raise web.HTTPBadRequest(text='Unsupported field')
    try:
        result = await MessageTools((await get_db())._connection, session_id=session_id).query(
            payload.get('action'), row_ids=payload.get('row_ids'), query=payload.get('query', ''),
            limit=payload.get('limit', 10), before_row=payload.get('before_row'), after_row=payload.get('after_row'),
            context_before=payload.get('context_before', 0), context_after=payload.get('context_after', 0))
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))
    return web.json_response(result)


async def attach_file(request):
    from .. import agent_attachments
    if not _loopback(request) or request.headers.get('Origin'):
        return web.json_response({'error': 'Agent attachments require a local tool connection'}, status=403)
    try:
        token = request.headers.get('Authorization', '').removeprefix('Bearer ')
        mode, session_id = agent_attachments.resolve_token(token)
        context = agent_attachments.active
        if context is None:
            raise PermissionError('No active agent turn')
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError('Invalid attachment request')
        result = await agent_attachments.publish_file(payload, mode, session_id, expected=context)
        return web.json_response(result, status=201)
    except PermissionError as exc:
        return web.json_response({'error': str(exc)}, status=403)
    except (ValueError, TypeError, OSError) as exc:
        return web.json_response({'error': str(exc)}, status=400)


def setup_routes(app):
    app.router.add_post('/internal/pi-tools/messages', messages)
    app.router.add_post('/internal/agent-tools/attach-file', attach_file)
