"""Classic model choices and Pi changes with authoritative lane readback."""

from aiohttp import web

from .. import pi_client
from ..db import get_db
from ..sessions import SessionStore
from . import agents
from .sessions import sanitize_model, valid_text
from .sse import broadcast_session_event


def response(data, status=200):
    return web.json_response(data, status=status, headers={'Cache-Control': 'no-store'})


def unavailable(session_id):
    return {'session_id': session_id, 'available': False, 'models': [], 'model_options': [],
            'provider_options': [], 'current': None, 'thinking_level': None,
            'supports_thinking': False, 'thinking_token': None,
            'thinking': {'levels': [], 'configurable': False}}


async def inspect(session_id, observed=None):
    if observed is None:
        if agents._resolve_agent_mode('default') == 'copilot-ffi':
            observed = await agents.copilot_backend.classic_model(session_id)
        else:
            observed = await pi_client.inspect_classic_model(session_id)
    if not isinstance(observed, dict):
        return unavailable(session_id)
    state = observed.get('state', {})
    current = sanitize_model(state.get('model'))
    if not current:
        return unavailable(session_id)
    choices, seen = [], set()
    raw = observed.get('models', [])
    if isinstance(raw, list):
        for entry in raw[:500]:
            model = sanitize_model(entry)
            if not model:
                continue
            identity = (model['provider'], model['id'])
            if identity in seen:
                continue
            seen.add(identity)
            choices.append({'id': '/'.join(identity), 'provider': model['provider'],
                            'label': model.get('name', model['id']), 'context_window': model.get('contextWindow')})
    levels = observed.get('thinking_levels', [])
    levels = list(dict.fromkeys(value for value in levels[:16] if valid_text(value))) if isinstance(levels, list) else []
    thinking = state.get('thinkingLevel')
    thinking = thinking if valid_text(thinking) else None
    configurable = bool(current.get('reasoning') and levels)
    return {'session_id': session_id, 'available': True, 'models': choices, 'model_options': choices,
            'provider_options': sorted({entry['provider'] for entry in choices}),
            'current': current['provider'] + '/' + current['id'], 'thinking_level': thinking,
            'supports_thinking': configurable, 'thinking_token': observed.get('thinking_token'),
            'thinking': {'levels': levels, 'configurable': configurable}}


async def model(request):
    session_id = request.match_info['id']
    if request.query:
        return response({'error': 'Unsupported model query'}, 400)
    store = SessionStore(await get_db())
    session = await store.get(session_id)
    if not session:
        return response({'error': 'Session not found'}, 404)
    mode = agents._resolve_agent_mode('default')
    if session['archived'] or mode not in {'pi', 'copilot-ffi'}:
        if request.method == 'GET':
            return response(unavailable(session_id))
        return response({'error': 'Canonical model changes are unavailable for this lane'}, 409)
    if request.method == 'GET':
        try:
            return response(await inspect(session_id))
        except (ValueError, RuntimeError, TimeoutError):
            return response(unavailable(session_id))
    try:
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError('Expected an object')
        if set(data) == {'model'}:
            if not valid_text(data['model']) or '/' not in data['model']:
                raise ValueError('A provider/model identifier is required')
            provider, model_id = data['model'].split('/', 1)
            if not valid_text(provider) or not valid_text(model_id):
                raise ValueError('Invalid model identifier')
            options = {'provider': provider, 'model_id': model_id}
        elif set(data) == {'model', 'thinking_level', 'thinking_token'}:
            if not all(valid_text(data[key]) for key in data):
                raise ValueError('A model, thinking level and observed token are required')
            options = {'thinking_level': data['thinking_level'], 'expected_model': data['model'],
                       'expected_thinking_token': data['thinking_token']}
        else:
            raise ValueError('Unsupported model change fields')
        if mode == 'copilot-ffi':
            observed = await agents.copilot_backend.classic_model(session_id, data, store)
            result = {'success': True, 'data': observed.get('state')} if isinstance(observed, dict) else None
        else:
            result = await pi_client.change_chat_model(session_id, **options)
        state = pi_client._model_rpc_data(result)
        selected = sanitize_model(state.get('model'))
        if not selected:
            raise RuntimeError('Model change readback unavailable; refresh before retrying')
        if 'thinking_level' in options:
            if state.get('thinkingLevel') != options['thinking_level'] or selected['provider'] + '/' + selected['id'] != data['model']:
                raise RuntimeError('Thinking change was not confirmed')
        elif (selected['provider'], selected['id']) != (options['provider'], options['model_id']):
            raise RuntimeError('Model change was not confirmed')
        # Return the confirmed write projection. A later GET independently
        # refreshes offered choices; never echo a requested model as readback.
        acknowledged = {'session_id': session_id, 'current': selected['provider'] + '/' + selected['id'],
                        'thinking_level': state.get('thinkingLevel') if valid_text(state.get('thinkingLevel')) else None,
                        'confirmed': True}
    except (ValueError, TypeError) as exc:
        return response({'error': str(exc)}, 400)
    except (RuntimeError, TimeoutError):
        return response({'error': 'Model state changed or is unconfirmed; refresh before retrying'}, 409)
    await broadcast_session_event('session_model_changed', {**acknowledged, 'chat_jid': 'gi:' + session_id}, session_id)
    return response(acknowledged)


def setup_routes(app):
    app.router.add_get('/api/sessions/{id}/model', model)
    app.router.add_patch('/api/sessions/{id}/model', model)
