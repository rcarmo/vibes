"""Session Plan API; model transport resolves destination from its owned turn."""
from aiohttp import web
from ..db import get_db
from ..plans import PlanStore, PlanConflict
from .sse import broadcast_event


async def classic_plan(request):
    """Classic writes keep the native integer precondition and transaction."""
    try:
        if request.method == 'GET':
            snapshot = await PlanStore(await get_db()).get(request.match_info['id'])
        else:
            data = await request.json()
            if isinstance(data, dict) and 'expected_revision' not in data:
                return web.json_response({'error': 'expected_revision required', 'code': 'revision_required'}, status=428)
            if not isinstance(data, dict):
                raise ValueError('JSON object required')
            if set(data) == {'markdown', 'expected_revision'}:
                mutation = {'action': 'write', 'markdown': data['markdown'],
                            'expected_revision': data['expected_revision']}
            elif set(data) == {'action', 'expected_revision'} and data['action'] == 'reset':
                mutation = {'action': 'write', 'markdown': '',
                            'expected_revision': data['expected_revision']}
            else:
                raise ValueError('Expected markdown or reset with expected_revision')
            snapshot = await PlanStore(await get_db()).apply(request.match_info['id'], mutation)
            await broadcast_event('plan_updated', snapshot)
        return web.json_response({'plan': snapshot}, headers={'Cache-Control': 'no-store'})
    except (ValueError, PlanConflict) as exc:
        status = 409 if isinstance(exc, PlanConflict) else 400
        return web.json_response({'error': str(exc), 'code': 'plan_revision_conflict' if status == 409 else 'invalid_plan_request'}, status=status)
    except LookupError:
        return web.json_response({'error': 'Session unavailable', 'code': 'session_not_found'}, status=404)


async def session_plan(request):
    store = PlanStore(await get_db())
    session_id = request.match_info['id']
    try:
        if request.method == 'GET':
            result = await store.get(session_id)
        else:
            payload = await request.json()
            if not isinstance(payload, dict) or set(payload) != {'markdown', 'expected_revision'}:
                raise ValueError('Expected markdown and expected_revision')
            result = await store.apply(session_id, {'action': 'write', **payload})
            await broadcast_event('plan_updated', result)
        return web.json_response(result, headers={'Cache-Control': 'no-store'})
    except LookupError as exc:
        return web.json_response({'error': str(exc)}, status=404)
    except PlanConflict as exc:
        return web.json_response({'error': str(exc), 'code': 'plan_revision_conflict'}, status=409)
    except (ValueError, TypeError) as exc:
        return web.json_response({'error': str(exc)}, status=400)


async def agent_plan(request):
    from .. import agent_attachments
    from .pi_tools import _loopback
    if not _loopback(request) or request.headers.get('Origin'):
        return web.json_response({'error': 'Plan tools require a local tool connection'}, status=403)
    try:
        mode, session_id = agent_attachments.resolve_token(request.headers.get('Authorization', '').removeprefix('Bearer '))
        owner = agent_attachments.active_for(session_id)

        def check_owner():
            if not owner or agent_attachments.active_for(session_id) is not owner or owner['mode'] != mode or (session_id is not None and session_id != owner['session_id']):
                raise PermissionError('No matching active agent turn')

        check_owner()
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError('Expected plan object')
        if payload.get('action') != 'read' and 'expected_revision' not in payload:
            raise ValueError('Read the Plan first and provide expected_revision to mutate it')
        result = await PlanStore(await get_db()).apply(owner['session_id'], payload, owner_check=check_owner)
        if payload['action'] != 'read':
            await broadcast_event('plan_updated', result)
        return web.json_response(result, headers={'Cache-Control': 'no-store'})
    except PermissionError as exc:
        return web.json_response({'error': str(exc)}, status=403)
    except LookupError as exc:
        return web.json_response({'error': str(exc)}, status=404)
    except PlanConflict as exc:
        return web.json_response({'error': str(exc), 'code': 'plan_revision_conflict'}, status=409)
    except (ValueError, TypeError) as exc:
        return web.json_response({'error': str(exc)}, status=400)


def setup_routes(app):
    app.router.add_get('/sessions/{id}/plan', session_plan)
    app.router.add_put('/sessions/{id}/plan', session_plan)
    app.router.add_get('/api/sessions/{id}/plan', classic_plan)
    app.router.add_post('/api/sessions/{id}/plan', classic_plan)
    app.router.add_post('/internal/agent-tools/plan', agent_plan)
