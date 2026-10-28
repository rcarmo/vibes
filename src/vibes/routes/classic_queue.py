"""Classic queue snapshots and atomic session-owned compare-and-set reorder."""

from aiohttp import web

from ..db import get_db
from ..sessions import SessionStore
from .sse import broadcast_session_event


class QueueError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def response(data, status=200):
    return web.json_response(data, status=status, headers={'Cache-Control': 'no-store'})


def identity(value):
    if not isinstance(value, str) or not value.startswith('-') or not value[1:].isascii() or not value[1:].isdecimal():
        raise QueueError('Expected a durable queue ID')
    number = int(value)
    if not -(2**63 - 1) <= number < 0 or str(number) != value:
        raise QueueError('Invalid durable queue ID')
    return number


async def rows_for(connection, session_id):
    # The thread and original message must agree about ownership. Imported or
    # corrupt records never become authorised from queued content alone.
    async with connection.execute('''
        SELECT q.*, -q.sequence AS queue_id,
            (SELECT r.client_request_id FROM prompt_receipts r WHERE r.session_id=? AND r.message_id=q.message_id
             ORDER BY r.created_at,r.client_request_id LIMIT 1) AS client_request_id
        FROM followup_queue q
        JOIN interactions root ON root.id=q.thread_id
        JOIN interactions message ON message.id=q.message_id
        WHERE COALESCE(json_extract(root.data,'$.session_id'),'default')=?
          AND COALESCE(json_extract(message.data,'$.session_id'),'default')=?
          AND COALESCE(json_extract(message.data,'$.thread_id'),message.id)=q.thread_id
          AND q.agent_id='default'
        ORDER BY q.ordinal,q.sequence
    ''', (session_id, session_id, session_id)) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


def project(row, session_id):
    return {'id': str(row['queue_id']), 'prompt': row['content'], 'state': row['state'],
            'mode': row['mode'], 'session_id': session_id, 'chat_jid': 'gi:' + session_id,
            'message_id': str(row['message_id']), 'thread_id': str(row['thread_id']),
            'created_at': row['created_at'],
            'metadata': {'client_request_id': row['client_request_id']} if row.get('client_request_id') else {}}


async def snapshot(connection, session_id):
    rows = await rows_for(connection, session_id)
    async with connection.execute('''
        SELECT t.turn_id FROM active_turns t JOIN interactions root ON root.id=t.thread_id
        WHERE t.agent_id='default' AND COALESCE(json_extract(root.data,'$.session_id'),'default')=?
    ''', (session_id,)) as cursor:
        active = await cursor.fetchall()
    return {'active_turn_id': active[0]['turn_id'] if len(active) == 1 else None,
            'items': [project(row, session_id) for row in rows if row['state'] == 'pending' and row['mode'] == 'queue'],
            'pending_steers': [project(row, session_id) for row in rows if row['state'] == 'pending' and row['mode'] == 'steer'],
            'uncertain': [project(row, session_id) for row in rows if row['state'] == 'uncertain']}


async def queue_state(request):
    if request.query:
        return response({'error': 'Unsupported queue query'}, 400)
    db = await get_db()
    session_id = request.match_info['id']
    async with db.transaction() as connection:
        if not await SessionStore(db).get(session_id):
            return response({'error': 'Session not found'}, 404)
        result = await snapshot(connection, session_id)
    return response(result)


async def reorder(request):
    try:
        if request.query:
            raise QueueError('Unsupported queue query')
        data = await request.json()
        if not isinstance(data, dict) or set(data) != {'expected', 'order'}:
            raise QueueError('Expected only expected and order')
        for field in ('expected', 'order'):
            values = data[field]
            if not isinstance(values, list) or len(values) > 1000:
                raise QueueError('Invalid queue order')
            for value in values:
                identity(value)
            if len(set(values)) != len(values):
                raise QueueError('Queue order contains duplicate IDs')
        if set(data['expected']) != set(data['order']):
            raise QueueError('Reorder must preserve the expected item set')
        db = await get_db()
        session_id = request.match_info['id']
        async with db.transaction() as connection:
            await connection.execute('BEGIN IMMEDIATE')
            session = await SessionStore(db).get(session_id)
            if not session:
                raise QueueError('Session not found', 404)
            if session['archived']:
                raise QueueError('Session is archived', 409)
            rows = [row for row in await rows_for(connection, session_id)
                    if row['state'] == 'pending' and row['mode'] == 'queue']
            if [str(row['queue_id']) for row in rows] != data['expected']:
                raise QueueError('Queue changed; refresh before reordering', 409)
            # Permute only this session's existing ordinal slots. Never alter
            # another session, claimed/uncertain rows, steers or item identity.
            slots = [row['ordinal'] for row in rows]
            if len(set(slots)) != len(slots):
                raise QueueError('Queue ordinal collision; refresh/recovery required', 409)
            for item_id, ordinal in zip(data['order'], slots):
                await connection.execute("UPDATE followup_queue SET ordinal=? WHERE sequence=? AND state='pending' AND mode='queue'",
                                         (ordinal, -identity(item_id)))
            result = await snapshot(connection, session_id)
    except QueueError as exc:
        return response({'error': str(exc)}, exc.status)
    except (ValueError, TypeError):
        return response({'error': 'Invalid queue request'}, 400)
    await broadcast_session_event('agent_queue_reordered', {**result, 'session_id': session_id,
                                                           'chat_jid': 'gi:' + session_id}, session_id)
    return response(result)


async def remove(request):
    try:
        if request.query:
            raise QueueError('Unsupported queue query')
        row_id = identity(request.match_info['item_id'])
        db = await get_db()
        session_id = request.match_info['id']
        async with db.transaction() as connection:
            await connection.execute('BEGIN IMMEDIATE')
            session = await SessionStore(db).get(session_id)
            if not session:
                raise QueueError('Session not found', 404)
            if session['archived']:
                raise QueueError('Session is archived', 409)
            row = next((row for row in await rows_for(connection, session_id) if row['queue_id'] == row_id), None)
            if row is None:
                raise QueueError('Queue item not found', 404)
            if row['state'] != 'pending' or row['mode'] != 'queue':
                raise QueueError('Queue item is not removable pending work', 409)
            await connection.execute("DELETE FROM followup_queue WHERE sequence=? AND state='pending' AND mode='queue'", (-row_id,))
            item = project(row, session_id)
    except QueueError as exc:
        return response({'error': str(exc)}, exc.status)
    await broadcast_session_event('agent_followup_removed', item, session_id)
    return response({'removed': True, 'item': item})


async def steer_unavailable(request):
    # Legacy steering permits idle promotion and cannot enforce the candidate's
    # captured active-turn contract. Preserve work rather than silently emulate it.
    try:
        identity(request.match_info['item_id'])
        data = await request.json()
        if (request.query or not isinstance(data, dict) or set(data) != {'active_turn_id'}
                or not isinstance(data['active_turn_id'], str) or not data['active_turn_id'].strip()):
            raise QueueError('A captured active_turn_id is required')
    except (ValueError, TypeError):
        return response({'error': 'Invalid steering request'}, 400)
    db = await get_db()
    session_id = request.match_info['id']
    if not await SessionStore(db).get(session_id):
        return response({'error': 'Session not found'}, 404)
    async with db.transaction() as connection:
        row = next((row for row in await rows_for(connection, session_id)
                    if str(row['queue_id']) == request.match_info['item_id']), None)
    if row is None:
        return response({'error': 'Queue item not found'}, 404)
    return response({'error': 'Turn-bound canonical steering is not implemented; queued item preserved'}, 501)


def setup_routes(app):
    app.router.add_get('/api/sessions/{id}/queue', queue_state)
    app.router.add_patch('/api/sessions/{id}/queue', reorder)
    app.router.add_delete('/api/sessions/{id}/queue/{item_id}', remove)
    app.router.add_post('/api/sessions/{id}/queue/{item_id}/steer', steer_unavailable)
