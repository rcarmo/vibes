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


async def session_model_state(request):
    from ..pi_client import inspect_model_state
    store = SessionStore(await get_db())
    session_id = request.match_info['id']
    if not await store.get(session_id):
        return web.json_response({'error': 'Session not found'}, status=404)
    unavailable = {'session_id': session_id, 'available': False, 'model': None, 'thinking_level': None, 'compacting': None}
    try:
        response = await inspect_model_state(session_id)
        if not response or not response.get('success'):
            return web.json_response(unavailable)
        state = response.get('data', {})
        model = state.get('model')
        # Exclude provider URLs and credentials from raw model configuration.
        model = {key: model[key] for key in ('id', 'name', 'provider', 'reasoning', 'contextWindow') if key in model} if isinstance(model, dict) else None
        return web.json_response({'session_id': session_id, 'available': True,
            'model': model, 'thinking_level': state.get('thinkingLevel'),
            'compacting': state.get('isCompacting')})
    except Exception:
        return web.json_response(unavailable)


async def session_model_catalog(request):
    from ..pi_client import inspect_model_catalog
    session_id = request.match_info['id']
    if not await SessionStore(await get_db()).get(session_id):
        return web.json_response({'error': 'Session not found'}, status=404)
    unavailable = {'available': False, 'models': [], 'thinking_levels': []}
    try:
        catalog = await inspect_model_catalog(session_id)
        if not catalog:
            return web.json_response(unavailable)
        models = [{key: item[key] for key in ('id', 'name', 'provider', 'reasoning', 'contextWindow') if key in item}
                  for item in catalog['models'][:500] if isinstance(item, dict)]
        levels = [level for level in catalog['thinking_levels'][:16] if isinstance(level, str)]
        return web.json_response({'available': True, 'models': models, 'thinking_levels': levels})
    except Exception:
        return web.json_response(unavailable)


async def change_session_model(request):
    from ..pi_client import change_chat_model
    session_id = request.match_info['id']
    store = SessionStore(await get_db())
    session = await store.get(session_id)
    if not session or session['archived']:
        return web.json_response({'error': 'Session unavailable'}, status=404)
    try:
        data = await request.json()
        if not isinstance(data, dict) or not data or set(data) - {'provider', 'model_id', 'thinking_level'}:
            raise ValueError('Invalid model change fields')
        if any(not isinstance(value, str) or not value or len(value) > 512 for value in data.values()):
            raise ValueError('Invalid model change values')
        response = await change_chat_model(session_id, **data)
        if not response or not response.get('success'):
            raise RuntimeError('Unable to confirm model change')
        state = response.get('data', {})
        model = state.get('model')
        model = {key: model[key] for key in ('id', 'name', 'provider', 'reasoning', 'contextWindow') if key in model} if isinstance(model, dict) else None
    except (ValueError, TypeError) as exc:
        return web.json_response({'error': str(exc)}, status=400)
    except RuntimeError as exc:
        return web.json_response({'error': str(exc)}, status=409)
    result = {'session_id': session_id, 'available': True, 'model': model,
              'thinking_level': state.get('thinkingLevel')}
    await broadcast_event('session_model_changed', result)
    return web.json_response(result)


async def session_timeline(request):
    try:
        store = SessionStore(await get_db())
        result = await store.timeline(request.match_info['id'],
            limit=int(request.query.get('limit', '50')),
            before_id=int(request.query['before']) if 'before' in request.query else None)
        return web.json_response(result)
    except ValueError as exc:
        return web.json_response({'error': str(exc)}, status=400)


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
    app.router.add_get('/sessions/{id}/timeline', session_timeline)
    app.router.add_get('/sessions/{id}/model-state', session_model_state)
    app.router.add_post('/sessions/{id}/model', change_session_model)
    app.router.add_get('/sessions/{id}/models', session_model_catalog)
    app.router.add_post('/sessions', mutate_session)
    app.router.add_patch('/sessions/{id}', mutate_session)
    app.router.add_delete('/sessions/{id}', mutate_session)
