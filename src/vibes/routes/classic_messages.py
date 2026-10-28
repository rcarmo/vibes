"""Persisted conversation reads and transactional session-bound deletion."""

import json
import sqlite3

from aiohttp import web

from ..db import get_db
from ..sessions import SessionStore
from .sse import broadcast_session_event


# Hidden tool/runtime records do not consume visible conversation pagination.
_TYPES = "('user_message','user','post','reply','agent_response','assistant','system')"


def visible_sql(alias=''):
    column = alias + 'data'
    kind = "COALESCE(json_extract(" + column + ",'$.kind'),'')"
    return (alias + 'type IN ' + _TYPES + " AND NOT (" + alias + "type IN ('agent_response','assistant','system') AND " +
            kind + "='tool_result') AND NOT (" + alias + "type='system' AND " + kind + "='queue')")


def response(data, status=200):
    return web.json_response(data, status=status, headers={'Cache-Control': 'no-store'})


def parameters(request, allowed):
    if set(request.query) - allowed or any(len(request.query.getall(key)) != 1 for key in request.query):
        raise ValueError('Unknown or repeated query fields')
    if request.query.get('view', 'conversation') != 'conversation':
        raise ValueError('Only conversation view is supported')


def integer(value, *, minimum=1, maximum=2**63 - 1):
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        raise ValueError('Expected an integer')
    result = int(value)
    if not minimum <= result <= maximum:
        raise ValueError('Integer out of range')
    return result


def media_references(data):
    references = data.get('media_ids')
    return [value for value in references[:32] if type(value) is int and value > 0] if isinstance(references, list) else []


async def project_page(db, rows):
    # Request-local batching avoids repeated SQL/worker wakeups for attachments
    # shared by many messages. No cache outlives this response.
    parsed = [(row, json.loads(row['data'])) for row in rows]
    ids = list(dict.fromkeys(value for _, data in parsed for value in media_references(data)))
    saved = {}
    for start in range(0, len(ids), 500):
        batch = ids[start:start + 500]
        async with db._connection.execute('SELECT id,filename,content_type,metadata FROM media WHERE id IN (' +
                                          ','.join('?' for _ in batch) + ')', batch) as cursor:
            for item in await cursor.fetchall():
                saved[item['id']] = {**dict(item), 'metadata': json.loads(item['metadata']) if item['metadata'] else None}
    return [_project(row, data, saved) for row, data in parsed]


async def project(db, row):
    return (await project_page(db, [row]))[0]


def _project(row, data, saved_media):
    kind = data.get('type')
    role = 'assistant' if kind in {'agent_response', 'assistant'} else 'system' if kind == 'system' else 'user'
    session_id = data.get('session_id', 'default')
    payload = {key: data[key] for key in ('content_blocks', 'link_previews', 'agent_id', 'kind',
                                         'display_text', 'tokens_before', 'source', 'clipped') if key in data}
    blocks = payload.get('content_blocks')
    if isinstance(blocks, list):
        # Reconstruct attachments exclusively from validated persisted media;
        # stale/foreign references in legacy blocks must not bypass ownership.
        payload['content_blocks'] = [block for block in blocks if isinstance(block, dict)
                                     and block.get('type') not in {'image', 'file'}]
    media = []
    for media_id in media_references(data):
        saved = saved_media.get(media_id)
        metadata = saved.get('metadata') if saved else None
        if isinstance(metadata, dict) and metadata.get('session_id') == session_id:
            media.append({'media_id': media_id, 'session_id': session_id, 'name': saved['filename'],
                          'content_type': saved['content_type']})
    payload['media'] = media
    thread_id = data.get('thread_id')
    reply_to = str(thread_id) if type(thread_id) is int and thread_id != row['id'] else None
    return {'id': str(row['id']), 'display_row_id': row['id'], 'session_id': session_id,
            'role': role, 'content': data.get('content', ''), 'created_at': row['timestamp'],
            'reply_to_id': reply_to, 'payload': payload}


async def messages(request):
    try:
        parameters(request, {'view', 'limit', 'before', 'after'})
        limit = integer(request.query.get('limit', '50'), maximum=100)
        before = integer(request.query['before']) if 'before' in request.query else None
        after = integer(request.query['after']) if 'after' in request.query else None
        if before is not None and after is not None:
            raise ValueError('before and after are mutually exclusive')
    except ValueError as exc:
        return response({'error': str(exc)}, 400)
    db = await get_db()
    session_id = request.match_info['id']
    if not await SessionStore(db).get(session_id):
        return response({'error': 'Session not found'}, 404)
    filters = "COALESCE(json_extract(data,'$.session_id'),'default')=? AND " + visible_sql()
    args = [session_id]
    if before is not None or after is not None:
        filters += ' AND id ' + ('< ?' if before is not None else '> ?')
        args.append(before if before is not None else after)
    direction = 'ASC' if after is not None else 'DESC'
    async with db._connection.execute('SELECT id,timestamp,data FROM interactions WHERE ' + filters +
                                      ' ORDER BY id ' + direction + ' LIMIT ?', (*args, limit + 1)) as cursor:
        rows = await cursor.fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]
    if after is None:
        rows.reverse()
    return response({'messages': await project_page(db, rows), 'has_more': has_more,
                     'before': str(rows[0]['id']) if rows else None,
                     'after': str(rows[-1]['id']) if rows else None})


async def search(request):
    try:
        parameters(request, {'view', 'q', 'scope', 'limit', 'offset'})
        query = request.query.get('q', '').strip()
        if not query or len(query) > 4096:
            raise ValueError('A bounded nonempty q is required')
        limit = integer(request.query.get('limit', '50'), maximum=100)
        offset = integer(request.query.get('offset', '0'), minimum=0, maximum=10000)
        scope = request.query.get('scope', 'current')
        if scope not in {'current', 'root'}:
            raise ValueError('Unsupported search scope')
    except ValueError as exc:
        return response({'error': str(exc)}, 400)
    db = await get_db()
    session_id = request.match_info['id']
    store = SessionStore(db)
    if not await store.get(session_id):
        return response({'error': 'Session not found'}, 404)
    try:
        ids = await store.family_ids(session_id) if scope == 'root' else [session_id]
        placeholders = ','.join('?' for _ in ids)
        async with db._connection.execute('''
            SELECT i.id,i.timestamp,i.data FROM interactions_fts f JOIN interactions i ON i.id=f.rowid
            WHERE interactions_fts MATCH ? AND ''' + visible_sql('i.') +
            " AND COALESCE(json_extract(i.data,'$.session_id'),'default') IN (" + placeholders + ')'
            ' ORDER BY rank,i.id LIMIT ? OFFSET ?', (query, *ids, limit + 1, offset)) as cursor:
            rows = await cursor.fetchall()
    except (ValueError, sqlite3.OperationalError):
        return response({'error': 'Invalid search query or unavailable session family'}, 400)
    return response({'messages': await project_page(db, rows[:limit]), 'has_more': len(rows) > limit,
                     'limit': limit, 'offset': offset, 'scope': scope})


class DeleteConflict(ValueError):
    def __init__(self, message, status):
        super().__init__(message)
        self.status = status


async def delete_message(request):
    try:
        parameters(request, {'cascade'})
        target = integer(request.match_info['message_id'])
        cascade = request.query.get('cascade', 'false')
        if cascade not in {'true', 'false'}:
            raise ValueError('Invalid cascade')
    except ValueError as exc:
        return response({'error': str(exc)}, 400)
    db = await get_db()
    session_id = request.match_info['id']
    try:
        # Read/validate/delete in one SQLite write transaction, including other
        # processes. Never reinterpret a reply ID as permission to delete its root.
        async with db.transaction() as connection:
            await connection.execute('BEGIN IMMEDIATE')
            if not await SessionStore(db).get(session_id):
                raise DeleteConflict('Session not found', 404)
            post = await db.get_interaction(target)
            if not post or post['data'].get('session_id', 'default') != session_id:
                raise DeleteConflict('Message not found', 404)
            async with connection.execute('''
                WITH RECURSIVE descendants(id) AS (
                    SELECT id FROM interactions WHERE thread_id=? AND id!=?
                    UNION SELECT i.id FROM interactions i JOIN descendants d ON i.thread_id=d.id WHERE i.id!=d.id
                ) SELECT id,data FROM interactions WHERE id IN (SELECT id FROM descendants) AND id!=? LIMIT 1001
            ''', (target, target, target)) as cursor:
                children = await cursor.fetchall()
            if len(children) > 1000:
                raise DeleteConflict('Deletion batch exceeds supported limit', 409)
            if children and cascade != 'true':
                raise DeleteConflict('Replies exist; cascade confirmation required', 409)
            if any(json.loads(row['data']).get('session_id', 'default') != session_id for row in children):
                raise DeleteConflict('Thread ownership is inconsistent', 409)
            ids = [target, *(row['id'] for row in children)]
            placeholders = ','.join('?' for _ in ids)
            # Replies retain their own deletion identity, but active ownership
            # includes their ancestors. No in-flight transcript may be mutated.
            async with connection.execute('''
                WITH RECURSIVE ancestors(id) AS (
                    SELECT ? UNION SELECT i.thread_id FROM interactions i JOIN ancestors a ON i.id=a.id
                    WHERE i.thread_id IS NOT NULL AND i.thread_id!=i.id
                ) SELECT 1 FROM active_turns WHERE thread_id IN (SELECT id FROM ancestors)
            ''' + ' OR thread_id IN (' + placeholders + ') LIMIT 1', (target, *ids)) as cursor:
                if await cursor.fetchone():
                    raise DeleteConflict('Cannot delete an active turn', 409)
            async with connection.execute('''
                WITH RECURSIVE ancestors(id) AS (
                    SELECT ? UNION SELECT i.thread_id FROM interactions i JOIN ancestors a ON i.id=a.id
                    WHERE i.thread_id IS NOT NULL AND i.thread_id!=i.id
                ) SELECT 1 FROM followup_queue WHERE thread_id IN (SELECT id FROM ancestors)
            ''' + ' OR thread_id IN (' + placeholders + ') OR message_id IN (' + placeholders + ') LIMIT 1',
                                          (target, *ids, *ids)) as cursor:
                if await cursor.fetchone():
                    raise DeleteConflict('Cannot delete messages with durable queued work', 409)
            # Media is retained: receipt results and other native consumers may
            # still reference it. Canonical media lifecycle is a separate adapter.
            cursor = await connection.execute('DELETE FROM interactions WHERE id IN (' + placeholders + ')', ids)
            deleted = cursor.rowcount
    except DeleteConflict as exc:
        return response({'error': str(exc)}, exc.status)
    await broadcast_session_event('interaction_deleted', {'ids': ids, 'session_id': session_id, 'chat_jid': 'gi:' + session_id}, session_id)
    return response({'deleted': deleted, 'ids': [str(value) for value in ids]})


def setup_routes(app):
    app.router.add_get('/api/sessions/{id}/messages', messages)
    app.router.add_get('/api/sessions/{id}/search', search)
    app.router.add_delete('/api/sessions/{id}/messages/{message_id}', delete_message)
