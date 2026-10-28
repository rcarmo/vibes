"""Canonical prompt admission and durable no-replay receipts.

This adapter uses the existing real dispatch path. A pending/uncertain receipt
is never interpreted as permission to dispatch the prompt again.
"""

import asyncio
import hashlib
import json
import uuid
from types import SimpleNamespace

from aiohttp import web

from ..db import get_db
from ..sessions import SessionStore
from . import agents


def _response(data, status=200):
    return web.json_response(data, status=status, headers={'Cache-Control': 'no-store'})


def _request_id(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 200 or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid client_request_id')
    return value


async def _receipt(db, session_id, request_id):
    async with db._write_lock:
        async with db._connection.execute(
            'SELECT * FROM prompt_receipts WHERE session_id = ? AND client_request_id = ?',
            (session_id, request_id),
        ) as cursor:
            row = await cursor.fetchone()
    return dict(row) if row else None


async def send_receipt(request):
    session_id = request.match_info['id']
    try:
        request_id = _request_id(request.query.get('client_request_id'))
    except ValueError as exc:
        return _response({'error': str(exc)}, 400)
    db = await get_db()
    if not await SessionStore(db).get(session_id):
        return _response({'error': 'Session not found'}, 404)
    row = await _receipt(db, session_id, request_id)
    if not row:
        return _response({'error': 'Send receipt not found'}, 404)
    result = json.loads(row['result']) if row['result'] else None
    return _response({'receipt': {'status': row['state'], 'source_session_id': session_id,
                                 'client_request_id': request_id, 'result': result}})


async def _finalize(db, session_id, request_id, state, status, result):
    async with db.transaction() as connection:
        await connection.execute(
            'UPDATE prompt_receipts SET state = ?, response_status = ?, result = ?, '
            "updated_at = CURRENT_TIMESTAMP WHERE session_id = ? AND client_request_id = ? AND state = 'pending'",
            (state, status, json.dumps(result), session_id, request_id),
        )


async def _claim(db, session_id, request_id, fingerprint):
    async with db.transaction() as connection:
        cursor = await connection.execute(
            'INSERT OR IGNORE INTO prompt_receipts '
            '(session_id, client_request_id, fingerprint, state) VALUES (?, ?, ?, ?)',
            (session_id, request_id, fingerprint, 'pending'),
        )
        return cursor.rowcount == 1


def _recover(row, fingerprint, request_id):
    if row['fingerprint'] != fingerprint:
        return _response({'error': 'Request ID already used with different content', 'code': 'receipt_conflict'}, 409)
    if row['state'] in {'confirmed', 'rejected'}:
        return _response(json.loads(row['result']), row['response_status'])
    return _response({'error': 'Prompt admission is pending or uncertain; inspect receipt, do not replay',
                      'code': 'admission_uncertain', 'client_request_id': request_id}, 409)


async def prompt(request):
    session_id = request.match_info['id']
    try:
        payload = await request.json()
        allowed = {'prompt', 'intent', 'client_request_id', 'media', 'parent_turn_id', 'target_agent_id'}
        if not isinstance(payload, dict) or set(payload) - allowed:
            raise ValueError('Invalid prompt fields')
        if not isinstance(payload.get('prompt'), str) or not payload['prompt'].strip():
            raise ValueError('Nonempty prompt required')
        if len(payload['prompt'].encode('utf-8')) > 512 * 1024:
            raise ValueError('Prompt exceeds 512 KiB')
        intent = payload.get('intent', 'prompt')
        if intent not in {'prompt', 'queue', 'steer'}:
            raise ValueError('Invalid prompt intent')
        if payload.get('target_agent_id') not in (None, '', 'web', 'default'):
            raise ValueError('Only the configured web agent is supported')
        request_id = _request_id(payload.get('client_request_id', uuid.uuid4().hex))
        media = payload.get('media', [])
        if not isinstance(media, list) or len(media) > 8:
            raise ValueError('Invalid prompt media')
        media_ids = []
        for item in media:
            if (not isinstance(item, dict) or set(item) - {'media_id', 'session_id'}
                    or type(item.get('media_id')) is not int or item['media_id'] < 1
                    or item.get('session_id', session_id) != session_id):
                raise ValueError('Invalid or foreign media')
            media_ids.append(item['media_id'])
        parent_turn = payload.get('parent_turn_id')
        if parent_turn is not None and (not isinstance(parent_turn, str) or not parent_turn):
            raise ValueError('Invalid parent turn')
    except (ValueError, TypeError) as exc:
        return _response({'error': str(exc)}, 400)

    normalized = {'prompt': payload['prompt'], 'intent': intent, 'media_ids': media_ids,
                  'parent_turn_id': parent_turn, 'agent_id': 'default'}
    fingerprint = hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()
    db = await get_db()
    # Share FFI admission ownership; other backends bind their session below.
    lock = agents._ffi_lock(agents._ffi_admission_locks, session_id)
    async with lock:
        session = await SessionStore(db).get(session_id)
        if not session:
            return _response({'error': 'Session unavailable'}, 404)
        # Terminal results survive later archival, media deletion and parent expiry.
        previous = await _receipt(db, session_id, request_id)
        if previous:
            return _recover(previous, fingerprint, request_id)
        if session['archived']:
            return _response({'error': 'Session unavailable'}, 404)
        if agents._resolve_agent_mode('default') == 'copilot-ffi' and agents._ffi_closing:
            return _response({'error': 'Server shutting down'}, 503)
        for media_id in media_ids:
            saved = await db.get_media(media_id)
            if not saved or saved.get('metadata', {}).get('session_id') != session_id:
                return _response({'error': 'Media does not belong to this session'}, 400)
        thread_id = None
        if parent_turn is not None:
            active = next((turn for turn in await db.get_active_turns() if turn['turn_id'] == parent_turn), None)
            root = await db.get_interaction(active['thread_id']) if active else None
            if not root or root['data'].get('session_id', 'default') != session_id:
                return _response({'error': 'Parent turn stale or foreign'}, 409)
            thread_id = active['thread_id']
        # Uniqueness is enforced by SQLite, not just this process lock. Shield
        # claim so cancellation at commit can settle whether this request owns it.
        claim = asyncio.create_task(_claim(db, session_id, request_id, fingerprint))
        inserted = False
        try:
            inserted = await asyncio.shield(claim)
            if not inserted:
                return _recover(await _receipt(db, session_id, request_id), fingerprint, request_id)
            data = {'content': payload['prompt'], 'session_id': session_id,
                    'mode': {'prompt': 'auto', 'queue': 'queue', 'steer': 'steer'}[intent], 'media_ids': media_ids}
            if thread_id is not None:
                data['thread_id'] = thread_id
            proxy = SimpleNamespace(match_info={'agent_id': 'default'})
            from .. import pi_client, acp_client
            mode = agents._resolve_agent_mode('default')
            runtimes = pi_client._runtimes if mode == 'pi' else acp_client._runtimes
            with runtimes.bind(session_id):
                response = await agents._send_message(proxy, data, send_receipt=(session_id, request_id))
            legacy = json.loads(response.body)
            result = {**legacy, 'session_id': session_id, 'source_session_id': session_id,
                      'client_request_id': request_id}
            # Queued follow-ups have no new turn yet; only real reserved IDs appear.
            if legacy.get('item'):
                result['queue_item_id'] = legacy['item']['row_id']
            message = legacy.get('user_message')
            if message:
                result['user_message_id'] = str(message['id'])
            state = 'confirmed' if response.status < 300 else 'rejected'
            await _finalize(db, session_id, request_id, state, response.status, result)
            return _response(result, response.status)
        except BaseException:
            inserted = await asyncio.shield(claim)
            if inserted:
                # Guarded transition preserves an already committed terminal result.
                cleanup = asyncio.create_task(_finalize(db, session_id, request_id, 'uncertain', 409, {
                    'session_id': session_id, 'client_request_id': request_id, 'code': 'admission_uncertain',
                }))
                await asyncio.shield(cleanup)
            raise


async def activity(request):
    """Project persisted activity without consulting a process-global selection."""
    session_id = request.match_info['id']
    db = await get_db()
    session = await SessionStore(db).get(session_id)
    if not session or session['archived']:
        return _response({'error': 'Session unavailable'}, 404)
    owned = []
    for turn in await db.get_active_turns():
        if turn['agent_id'] != 'default':
            continue
        root = await db.get_interaction(turn['thread_id'])
        if root and root['data'].get('session_id', 'default') == session_id:
            owned.append(turn)
    if len(owned) > 1:
        return _response({'error': 'Multiple active turns; activity ownership is ambiguous'}, 409)
    if not owned:
        return _response({'status': 'idle', 'session_id': session_id,
                          'source_session_id': session_id, 'turn_id': None})
    turn = owned[0]
    # last_status can contain arbitrary tool/runtime payloads. Project only the
    # UI status fields and bind identity to the persisted turn and its root.
    last = turn.get('last_status')
    if not isinstance(last, dict):
        last = {}
    status = 'cancelling' if last.get('status') == 'cancelling' else 'running'
    result = {'status': status, 'session_id': session_id, 'source_session_id': session_id,
              'turn_id': turn['turn_id'], 'thread_id': turn['thread_id'], 'agent_id': 'default',
              'started_at': turn['started_at']}
    if last.get('type') == 'retry_wait':
        result['type'] = 'retry_wait'
        # Retry counters/delays are numeric metadata, never arbitrary error text.
        for field in ('attempt', 'max_attempts', 'delay_ms'):
            value = last.get(field)
            if type(value) is int and value >= 0:
                result[field] = value
    return _response(result)


async def cancel_activity(request):
    session_id = request.match_info['id']
    try:
        payload = await request.json()
        if (not isinstance(payload, dict) or set(payload) != {'turn_id'}
                or not isinstance(payload['turn_id'], str) or not payload['turn_id'].strip()):
            raise ValueError('A turn_id is required; session scope comes from the path')
    except (ValueError, TypeError) as exc:
        return _response({'error': str(exc)}, 400)
    response = await agents._abort_turn('default', {'session_id': session_id, 'turn_id': payload['turn_id']})
    response.headers['Cache-Control'] = 'no-store'
    return response


def setup_routes(app):
    app.router.add_post('/api/sessions/{id}/prompt', prompt)
    app.router.add_get('/api/sessions/{id}/send-receipt', send_receipt)
    app.router.add_get('/api/sessions/{id}/activity', activity)
    app.router.add_post('/api/sessions/{id}/activity', cancel_activity)
