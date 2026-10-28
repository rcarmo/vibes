"""Owner-scoped widget publication and inert JSON artifact lookup.

HTML is data in these routes. Only the shared UI may execute it inside its
sandboxed iframe; serving executable HTML at a same-origin URL is prohibited.
"""

import asyncio
import hashlib
import json
import uuid

from aiohttp import web

from ..db import get_db
from .pi_tools import _loopback
from .sse import broadcast_event

MAX_HTML_BYTES = 512 * 1024


def _widget(params):
    if not isinstance(params, dict) or set(params) - {'html', 'title', 'description', 'interactive', 'request_id'}:
        raise ValueError('Unsupported widget fields')
    html = params.get('html')
    if not isinstance(html, str) or not html.strip() or len(html.encode('utf-8')) > MAX_HTML_BYTES:
        raise ValueError('Widget HTML must be nonempty and at most 512 KiB')
    for key in ['title', 'description']:
        value = params.get(key, '')
        if not isinstance(value, str) or len(value) > (200 if key == 'title' else 2000):
            raise ValueError('Invalid widget label')
    if type(params.get('interactive', True)) is not bool:
        raise ValueError('Interactive must be a boolean')
    request_id = params.get('request_id')
    if not isinstance(request_id, str) or not request_id or len(request_id) > 200:
        raise ValueError('A stable request_id is required')
    return {'type': 'generated_widget', 'widget_id': uuid.uuid4().hex,
            'title': params.get('title', 'Dashboard'), 'description': params.get('description', ''),
            'artifact': {'kind': 'html', 'html': html}, 'source': 'timeline', 'status': 'final',
            'capabilities': ['interactive'] if params.get('interactive', True) else [], 'auto_open': True}


async def publish_widget(mode, session_id, params, *, expected):
    from .. import agent_attachments

    def check_owner():
        if (not expected or agent_attachments.active_for(session_id) is not expected
                or expected.get('cancelled') or expected.get('mode') != mode
                or (session_id is not None and expected.get('session_id') != session_id)):
            raise PermissionError('No matching active agent turn')

    check_owner()
    block = _widget(params)
    request_id = params['request_id']
    fingerprint = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
    lock = expected.setdefault('widget_lock', asyncio.Lock())
    async with lock:
        check_owner()
        receipts = expected.setdefault('widget_receipts', {})
        if request_id in receipts:
            old_fingerprint, result = receipts[request_id]
            if old_fingerprint != fingerprint:
                raise ValueError('request_id already used for a different widget')
            return result
        if len(receipts) >= 100:
            raise ValueError('Widget limit reached for this turn')
        db = await get_db()
        check_owner()
        # Hold database admission through commit and the final ownership check.
        # Widget lookup uses this same lock, so rolled-back/compensated rows are
        # never returned by the artifact endpoint.
        async with db._write_lock:
            connection = db._connection
            try:
                return await _store_widget(connection, db, expected, block, request_id,
                                           fingerprint, receipts, check_owner)
            except BaseException:
                await connection.rollback()
                raise


async def _store_widget(connection, db, expected, block, request_id, fingerprint, receipts, check_owner):
    row_id = None
    try:
        check_owner()
        async with connection.execute("SELECT COALESCE(json_extract(data, '$.session_id'), 'default') AS session_id FROM interactions WHERE id = ?",
                                      (expected['thread_id'],)) as cursor:
            parent = await cursor.fetchone()
        if not parent or parent['session_id'] != expected['session_id']:
            raise PermissionError('Widget parent does not belong to this session')
        check_owner()
        block['origin_chat_jid'] = 'gi:' + expected['session_id']
        row = {'type': 'agent_response', 'agent_id': expected['agent_id'], 'content': '',
               'thread_id': expected['thread_id'], 'session_id': expected['session_id'],
               'turn_id': expected['turn_id'], 'intermediate': True, 'content_blocks': [block]}
        cursor = await connection.execute(
            'INSERT INTO interactions (data) VALUES (?)', (json.dumps(row),),
        )
        row_id = cursor.lastrowid
        check_owner()
        commit = asyncio.create_task(connection.commit())
        try:
            await asyncio.shield(commit)
            check_owner()
        except (PermissionError, asyncio.CancelledError):
            # Settle the submitted commit before compensating a cancellation.
            # Do not let task cancellation leave an unacknowledged durable row.
            await asyncio.shield(commit)
            cleanup = asyncio.create_task(_remove_widget(connection, row_id))
            await asyncio.shield(cleanup)
            raise
    except BaseException:
        await connection.rollback()
        raise
    result = {'widget_id': block['widget_id'], 'message_id': row_id,
              'session_id': expected['session_id'],
              'url': f"/api/sessions/{expected['session_id']}/widgets/{block['widget_id']}"}
    receipts[request_id] = (fingerprint, result)
    await broadcast_event('new_post', await db.get_interaction(row_id))
    await broadcast_event('sessions_changed', {'session_id': expected['session_id']})
    return result


async def _remove_widget(connection, row_id):
    await connection.execute('DELETE FROM interactions WHERE id = ?', (row_id,))
    await connection.commit()


async def send_widget(request):
    from .. import agent_attachments
    if not _loopback(request) or request.headers.get('Origin'):
        return web.json_response({'error': 'Local tool connection required'}, status=403)
    try:
        mode, session_id = agent_attachments.resolve_token(
            request.headers.get('Authorization', '').removeprefix('Bearer '))
        owner = agent_attachments.active_for(session_id)
        result = await publish_widget(mode, session_id, await request.json(), expected=owner)
        return web.json_response(result, status=201, headers={'Cache-Control': 'no-store'})
    except PermissionError as exc:
        return web.json_response({'error': str(exc)}, status=403)
    except (ValueError, TypeError) as exc:
        return web.json_response({'error': str(exc)}, status=400)


async def get_widget(request):
    session_id, widget_id = request.match_info['session_id'], request.match_info['widget_id']
    if len(widget_id) != 32 or any(ch not in '0123456789abcdef' for ch in widget_id):
        raise web.HTTPNotFound()
    db = await get_db()
    # The durable message is the artifact source; deletion removes lookup as well.
    async with db._write_lock:
        async with db._connection.execute(
            "SELECT data FROM interactions WHERE COALESCE(json_extract(data, '$.session_id'), 'default') = ? "
            "AND type = 'agent_response' "
            "AND EXISTS (SELECT 1 FROM json_each(interactions.data, '$.content_blocks') AS block "
            "WHERE json_extract(block.value, '$.type') = 'generated_widget' "
            "AND json_extract(block.value, '$.widget_id') = ?) LIMIT 1", (session_id, widget_id),
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        raise web.HTTPNotFound()
    blocks = json.loads(row['data'])['content_blocks']
    block = next(block for block in blocks if block.get('widget_id') == widget_id)
    return web.json_response(block, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


def setup_routes(app):
    app.router.add_post('/internal/agent-tools/dashboard-widget', send_widget)
    app.router.add_get('/api/sessions/{session_id}/widgets/{widget_id}', get_widget)
