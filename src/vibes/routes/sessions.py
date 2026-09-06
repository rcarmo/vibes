"""Chat registry endpoints; runtime isolation is not implied by metadata creation."""
from aiohttp import web
from ..db import get_db
from ..sessions import SessionStore
from .sse import broadcast_event


async def list_sessions(request):
    include = request.query.get('include_archived', 'false')
    if include not in {'true', 'false'}:
        return web.json_response({'error': 'Invalid include_archived'}, status=400)
    store = SessionStore(await get_db())
    return web.json_response({'sessions': await store.list(include == 'true'), 'runtime_isolation': False})


async def mutate_session(request):
    store = SessionStore(await get_db())
    try:
        session_id = request.match_info.get('id')
        if request.method == 'DELETE':
            await store.delete_empty(session_id)
            result = {'deleted': True, 'id': session_id}
        else:
            data = await request.json()
            if not isinstance(data, dict):
                raise ValueError('Expected an object')
            allowed = {'name', 'parent_id'} if request.method == 'POST' else {'name', 'pinned', 'archived'}
            if set(data) - allowed:
                raise ValueError('Unknown session fields')
            if request.method == 'POST':
                result = {'session': await store.create(data.get('name'), data.get('parent_id'))}
            else:
                result = {'session': await store.update(session_id, **data)}
    except (ValueError, TypeError) as exc:
        return web.json_response({'error': str(exc)}, status=400)
    await broadcast_event('sessions_changed', {})
    return web.json_response(result, status=201 if request.method == 'POST' else 200)


def setup_routes(app):
    app.router.add_get('/sessions', list_sessions)
    app.router.add_post('/sessions', mutate_session)
    app.router.add_patch('/sessions/{id}', mutate_session)
    app.router.add_delete('/sessions/{id}', mutate_session)
