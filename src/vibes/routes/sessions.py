"""Chat registry endpoints; runtime isolation is not implied by metadata creation."""
from aiohttp import web
from ..db import get_db
from ..sessions import SessionStore
from ..config import get_config
from .sse import broadcast_event


def valid_text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 512 and not any(ord(char) < 32 or ord(char) == 127 for char in value)


def sanitize_model(item):
    if not isinstance(item, dict) or not all(valid_text(item.get(key)) for key in ('id', 'provider')):
        return None
    model = {key: item[key] for key in ('id', 'provider')}
    if valid_text(item.get('name')):
        model['name'] = item['name']
    if type(item.get('reasoning')) is bool:
        model['reasoning'] = item['reasoning']
    if type(item.get('contextWindow')) is int and 0 < item['contextWindow'] <= 1_000_000_000:
        model['contextWindow'] = item['contextWindow']
    return model


def classic_session(session):
    """Keep legacy metadata while projecting the supported single-agent scope."""
    return {**session, 'running': bool(session.get('is_running')), 'title': session['name'],
            'parent_session_id': session['parent_id'], 'scope': {'agent_id': 'web'},
            'state': {'status': 'running' if session.get('is_running') else
                      'queued' if session.get('queued_count', 0) else 'idle',
                      'queue_count': session.get('queued_count', 0), 'pinned': bool(session['pinned']),
                      'archived_at': session.get('archived_at'),
                      'archived_at_source': session.get('archived_at_source')},
            'capabilities': {'fork': False}}


async def classic_sessions(request):
    if set(request.query) - {'include_archived'}:
        return web.json_response({'error': 'Unknown session query fields'}, status=400)
    include = request.query.get('include_archived', 'true')
    if include not in {'true', 'false'}:
        return web.json_response({'error': 'Invalid include_archived'}, status=400)
    rows = await SessionStore(await get_db()).list(include == 'true')
    return web.json_response({'sessions': [classic_session(row) for row in rows],
                              'runtime_isolation': False}, headers={'Cache-Control': 'no-store'})


async def classic_session_detail(request):
    if request.query:
        return web.json_response({'error': 'Unsupported session query'}, status=400)
    rows = await SessionStore(await get_db()).list(True, session_id=request.match_info['id'])
    if not rows:
        return web.json_response({'error': 'Session not found'}, status=404)
    return web.json_response({'session': classic_session(rows[0])}, headers={'Cache-Control': 'no-store'})


async def classic_mutate_session(request):
    store = SessionStore(await get_db())
    try:
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError('Expected an object')
        if request.method == 'POST':
            if set(data) - {'title', 'agent_id'} or data.get('agent_id', 'web') not in {'web', 'default'}:
                raise ValueError('Only a title and the configured web agent are supported')
            result = await store.create(data.get('title'))
        else:
            session_id = request.match_info['id']
            if not await store.get(session_id):
                return web.json_response({'error': 'Session not found'}, status=404)
            action = data.get('action')
            fields = {'rename': {'action', 'title'}, 'pin': {'action', 'pinned'},
                      'archive': {'action'}, 'restore': {'action'}}
            if not isinstance(action, str) or action not in fields or set(data) != fields[action]:
                raise ValueError('Unsupported session action or fields')
            if action == 'rename':
                changes = {'name': store.name(data['title'])}
            elif action == 'pin':
                if type(data['pinned']) is not bool:
                    raise ValueError('pinned must be boolean')
                changes = {'pinned': data['pinned']}
            else:
                changes = {'archived': action == 'archive'}
            result = await store.update(session_id, **changes)
    except (ValueError, TypeError) as exc:
        status = 404 if str(exc) == 'Session not found' else 400
        return web.json_response({'error': str(exc)}, status=status)
    await broadcast_event('sessions_changed', {})
    return web.json_response({'session': classic_session(result)}, status=201 if request.method == 'POST' else 200,
                              headers={'Cache-Control': 'no-store'})


async def classic_fork_unavailable(request):
    if not await SessionStore(await get_db()).get(request.match_info['id']):
        return web.json_response({'error': 'Session not found'}, status=404)
    return web.json_response({'error': 'Transcript and backend-state forking are not supported'}, status=501,
                              headers={'Cache-Control': 'no-store'})


async def list_sessions(request):
    include = request.query.get('include_archived', 'false')
    if include not in {'true', 'false'}:
        return web.json_response({'error': 'Invalid include_archived'}, status=400)
    store = SessionStore(await get_db())
    return web.json_response({'sessions': await store.list(include == 'true'), 'runtime_isolation': False})


async def session_model_state(request):
    from .. import pi_client
    with pi_client._runtimes.bind(request.match_info['id']):
        return await _session_model_state(request)


async def _session_model_state(request):
    from ..pi_client import inspect_model_state, is_busy
    store = SessionStore(await get_db())
    session_id = request.match_info['id']
    session = await store.get(session_id)
    if not session:
        return web.json_response({'error': 'Session not found'}, status=404)
    unavailable = {'session_id': session_id, 'available': False, 'model': None, 'thinking_level': None, 'compacting': None}
    if session['archived']:
        return web.json_response(unavailable)
    if get_config().default_agent.lower() == 'copilot-ffi':
        from ..copilot_host import backend
        try:
            return web.json_response(await backend.model(session_id, store))
        except Exception:
            return web.json_response({**unavailable, 'busy': backend.busy(session_id)})
    if is_busy():
        binding = await store.backend_binding(session_id, 'pi')
        label = (binding or {}).get('model')
        if isinstance(label, str) and '/' in label:
            provider, model_id = label.split('/', 1)
            model = sanitize_model({'provider': provider, 'id': model_id})
            if model:
                return web.json_response({'session_id': session_id, 'available': True, 'busy': True, 'model': model, 'thinking_level': (binding or {}).get('thinking_level'), 'source': 'confirmed-binding'})
        return web.json_response({**unavailable, 'busy': True})
    try:
        response = await inspect_model_state(session_id)
        if not response or not response.get('success'):
            return web.json_response({**unavailable, 'busy': is_busy()})
        state = response.get('data', {})
        model = state.get('model')
        # Exclude provider URLs and credentials from raw model configuration.
        model = sanitize_model(model)
        thinking = state.get('thinkingLevel')
        if not valid_text(thinking):
            thinking = None
        compacting = state.get('isCompacting')
        return web.json_response({'session_id': session_id, 'available': True,
            'model': model, 'thinking_level': thinking,
            'compacting': compacting if type(compacting) is bool else None})
    except Exception:
        return web.json_response(unavailable)


async def session_model_catalog(request):
    from ..pi_client import inspect_model_catalog
    session_id = request.match_info['id']
    session = await SessionStore(await get_db()).get(session_id)
    if not session:
        return web.json_response({'error': 'Session not found'}, status=404)
    unavailable = {'available': False, 'models': [], 'thinking_levels': []}
    if session['archived']:
        return web.json_response(unavailable)
    if get_config().default_agent.lower() == 'copilot-ffi':
        from ..copilot_host import backend
        try:
            return web.json_response(await backend.models(session_id, SessionStore(await get_db())))
        except Exception:
            return web.json_response(unavailable)
    try:
        catalog = await inspect_model_catalog(session_id)
        if not catalog:
            return web.json_response(unavailable)
        models = []
        identities = set()
        raw_models = catalog.get('models', [])
        for item in (raw_models[:500] if isinstance(raw_models, list) else []):
            model = sanitize_model(item)
            if model is not None:
                identity = (model['provider'], model['id'])
                if identity not in identities:
                    identities.add(identity)
                    models.append(model)
        raw_levels = catalog.get('thinking_levels', [])
        levels = list(dict.fromkeys(level for level in (raw_levels[:16] if isinstance(raw_levels, list) else []) if valid_text(level)))
        return web.json_response({'available': True, 'models': models, 'thinking_levels': levels})
    except Exception:
        return web.json_response(unavailable)


async def change_session_model(request):
    if get_config().default_agent.lower() == 'copilot-ffi':
        from ..copilot_host import backend
        store = SessionStore(await get_db())
        session_id = request.match_info['id']
        session = await store.get(session_id)
        if not session or session['archived']:
            return web.json_response({'error': 'Session unavailable'}, status=404)
        try:
            changes = await request.json()
            if not isinstance(changes, dict) or not changes:
                raise ValueError('Expected model changes')
            result = await backend.model(session_id, store, changes)
            await broadcast_event('session_model_changed', result)
            return web.json_response(result)
        except ValueError:
            return web.json_response({'error': 'Invalid model change'}, status=400)
        except Exception:
            return web.json_response({'error': 'Model change unavailable or unconfirmed; reread state'}, status=409)
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
        if any(not valid_text(value) for value in data.values()):
            raise ValueError('Invalid model change values')
        response = await change_chat_model(session_id, **data)
        if not response or not response.get('success'):
            raise RuntimeError('Unable to confirm model change')
        state = response.get('data', {})
        model = state.get('model')
        model = sanitize_model(model)
    except (ValueError, TypeError) as exc:
        return web.json_response({'error': str(exc)}, status=400)
    except RuntimeError as exc:
        return web.json_response({'error': str(exc)}, status=409)
    thinking = state.get('thinkingLevel') if valid_text(state.get('thinkingLevel')) else None
    session_file = state.get('sessionFile')
    if isinstance(session_file, str) and session_file:
        label = '/'.join(str(model[key]) for key in ('provider', 'id') if model and model.get(key)) or None
        await store.bind_backend(session_id, 'pi', session_file,
            model=label, thinking_level=thinking)
    result = {'session_id': session_id, 'available': True, 'model': model,
              'thinking_level': thinking}
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


async def model_preferences(request):
    from ..model_preferences import ModelPreferences, PreferenceConflict, preferences_etag
    store = ModelPreferences(await get_db())
    if request.method == 'GET':
        result = await store.get()
    else:
        try:
            data = await request.json()
            if not isinstance(data, dict) or set(data) != {'pins'}:
                raise ValueError('Expected only pins')
            result = await store.set_pins(data['pins'], request.headers.get('If-Match'))
        except PreferenceConflict as exc:
            return web.json_response({'error': str(exc)}, status=412)
        except (ValueError, TypeError) as exc:
            return web.json_response({'error': str(exc)}, status=400)
        await broadcast_event('model_preferences_changed', result)
    return web.json_response({**result, 'scope': 'instance'}, headers={'Cache-Control': 'no-store', 'ETag': preferences_etag(result['pins'])})


def setup_routes(app):
    app.router.add_get('/api/sessions', classic_sessions)
    app.router.add_post('/api/sessions', classic_mutate_session)
    app.router.add_get('/api/sessions/{id}', classic_session_detail)
    app.router.add_patch('/api/sessions/{id}', classic_mutate_session)
    app.router.add_post('/api/sessions/{id}/fork', classic_fork_unavailable)
    app.router.add_get('/model-preferences', model_preferences)
    app.router.add_put('/model-preferences', model_preferences)
    app.router.add_get('/sessions', list_sessions)
    app.router.add_get('/sessions/{id}/timeline', session_timeline)
    app.router.add_get('/sessions/{id}/model-state', session_model_state)
    app.router.add_post('/sessions/{id}/model', change_session_model)
    app.router.add_get('/sessions/{id}/models', session_model_catalog)
    app.router.add_post('/sessions', mutate_session)
    app.router.add_patch('/sessions/{id}', mutate_session)
    app.router.add_delete('/sessions/{id}', mutate_session)
