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
    allowed = {'action', 'row_ids', 'query', 'limit', 'before_row'}
    if set(payload) - allowed:
        raise web.HTTPBadRequest(text='Unsupported field')
    try:
        result = await MessageTools((await get_db())._connection, session_id=session_id).query(
            payload.get('action'), row_ids=payload.get('row_ids'), query=payload.get('query', ''),
            limit=payload.get('limit', 10), before_row=payload.get('before_row'))
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))
    return web.json_response(result)


def setup_routes(app):
    app.router.add_post('/internal/pi-tools/messages', messages)
