"""Durable chat metadata. Does not launch or switch agent processes."""
import re
import uuid


class SessionStore:
    def __init__(self, database):
        self.db = database

    async def list(self, include_archived=False):
        async with self.db._connection.execute(
            '''SELECT s.*, COALESCE(activity.message_count, 0) AS message_count,
                      activity.last_message_at, activity.last_message_id,
                      EXISTS (SELECT 1 FROM active_turns t JOIN interactions i ON i.id=t.thread_id
                        WHERE COALESCE(json_extract(i.data, '$.session_id'), 'default')=s.id) AS is_running
               FROM chat_sessions s LEFT JOIN (
                   SELECT COALESCE(json_extract(data, '$.session_id'), 'default') AS session_id,
                          COUNT(*) AS message_count, MAX(timestamp) AS last_message_at,
                          MAX(id) AS last_message_id
                   FROM interactions GROUP BY COALESCE(json_extract(data, '$.session_id'), 'default')
               ) activity ON activity.session_id=s.id
               WHERE (? OR s.archived=0)
               ORDER BY s.pinned DESC, COALESCE(activity.last_message_at, s.updated_at) DESC, s.id''',
            (int(include_archived),),
        ) as cursor:
            sessions = [{**dict(row), 'is_running': bool(row['is_running']), 'queued_count': 0} for row in await cursor.fetchall()]
        from .followups import list_followups, list_pending_steers
        pending = list_followups() + list_pending_steers()
        counts = {}
        for item in pending:
            thread_id = item['thread_id']
            counts[thread_id] = counts.get(thread_id, 0) + 1
        by_id = {session['id']: session for session in sessions}
        # Chunk lookups to stay below SQLite parameter limits. Ownership never
        # comes from queued content or caller-supplied session metadata.
        threads = list(counts)
        for start in range(0, len(threads), 500):
            batch = threads[start:start + 500]
            async with self.db._connection.execute(
                "SELECT id, COALESCE(json_extract(data, '$.session_id'), 'default') FROM interactions WHERE id IN (" + ','.join('?' for _ in batch) + ')', batch,
            ) as cursor:
                for row in await cursor.fetchall():
                    if row[1] in by_id:
                        by_id[row[1]]['queued_count'] += counts[row[0]]
        return sessions

    async def family_ids(self, session_id):
        session = await self.get(session_id)
        if not session:
            raise ValueError('Session not found')
        visited = set()
        while session['parent_id']:
            if session['id'] in visited:
                raise ValueError('Invalid cyclic session tree')
            visited.add(session['id'])
            parent = await self.get(session['parent_id'])
            if not parent:
                break
            session = parent
        async with self.db._connection.execute('''
            WITH RECURSIVE family(id) AS (
                SELECT ? UNION SELECT s.id FROM chat_sessions s JOIN family f ON s.parent_id=f.id
            ) SELECT id FROM family LIMIT 501
        ''', (session['id'],)) as cursor:
            ids = [row['id'] for row in await cursor.fetchall()]
        if len(ids) > 500:
            raise ValueError('Session family exceeds search limit')
        return ids

    async def backend_binding(self, session_id, backend):
        async with self.db._connection.execute('SELECT * FROM chat_session_backends WHERE session_id=? AND backend=?', (session_id, backend)) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def bind_backend(self, session_id, backend, conversation_id, *, model=None, thinking_level=None):
        if not await self.get(session_id):
            raise ValueError('Session not found')
        for value in (backend, conversation_id):
            if not isinstance(value, str) or not value or len(value) > 512 or re.search(r'[\x00-\x1f\x7f]', value):
                raise ValueError('Invalid backend identity')
        for value in (model, thinking_level):
            if value is not None and (not isinstance(value, str) or len(value) > 512):
                raise ValueError('Invalid backend metadata')
        async with self.db.transaction():
            await self.db._connection.execute('''
                INSERT INTO chat_session_backends(session_id,backend,conversation_id,model,thinking_level)
                VALUES (?,?,?,?,?) ON CONFLICT(session_id,backend) DO UPDATE SET
                conversation_id=excluded.conversation_id,
                model=COALESCE(excluded.model, chat_session_backends.model),
                thinking_level=COALESCE(excluded.thinking_level, chat_session_backends.thinking_level), updated_at=CURRENT_TIMESTAMP
            ''', (session_id, backend, conversation_id, model, thinking_level))
        return await self.backend_binding(session_id, backend)

    async def timeline(self, session_id, *, limit=50, before_id=None):
        if not await self.get(session_id):
            raise ValueError('Session not found')
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Invalid limit')
        if before_id is not None and (type(before_id) is not int or before_id < 1):
            raise ValueError('Invalid before ID')
        params = [session_id]
        where = "COALESCE(json_extract(data, '$.session_id'), 'default')=?"
        if before_id is not None:
            where += ' AND id < ?'
            params.append(before_id)
        async with self.db._connection.execute('SELECT id,timestamp,data FROM interactions WHERE ' + where + ' ORDER BY id DESC LIMIT ?', (*params, limit + 1)) as cursor:
            rows = await cursor.fetchall()
        import json
        posts = [{'id': row['id'], 'timestamp': row['timestamp'], 'data': json.loads(row['data'])} for row in rows[:limit]]
        return {'posts': list(reversed(posts)), 'has_more': len(rows) > limit}

    async def delete_empty(self, session_id):
        if session_id == 'default':
            raise ValueError('Default session cannot be deleted')
        async with self.db.transaction():
            cursor = await self.db._connection.execute('''
                DELETE FROM chat_sessions WHERE id=?
                AND NOT EXISTS (SELECT 1 FROM interactions WHERE json_extract(data, '$.session_id')=?)
                AND NOT EXISTS (SELECT 1 FROM chat_sessions WHERE parent_id=?)
            ''', (session_id, session_id, session_id))
            if not cursor.rowcount:
                raise ValueError('Session missing, nonempty, or has children')
        return True

    async def get(self, session_id):
        async with self.db._connection.execute('SELECT * FROM chat_sessions WHERE id=?', (session_id,)) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    def name(value):
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 80 or re.search(r'[\x00-\x1f\x7f]', value):
            raise ValueError('Session name must be 1–80 characters without control characters')
        return value.strip()

    async def create(self, name, parent_id=None):
        name = self.name(name)
        if parent_id is not None and not await self.get(parent_id):
            raise ValueError('Parent session not found')
        session_id = uuid.uuid4().hex
        async with self.db.transaction():
            await self.db._connection.execute('INSERT INTO chat_sessions (id,name,parent_id) VALUES (?,?,?)', (session_id, name, parent_id))
        return await self.get(session_id)

    async def update(self, session_id, *, name=None, pinned=None, archived=None):
        if not await self.get(session_id):
            raise ValueError('Session not found')
        fields, values = [], []
        if name is not None:
            fields.append('name=?')
            values.append(self.name(name))
        for key, value in [('pinned', pinned), ('archived', archived)]:
            if value is not None:
                if type(value) is not bool:
                    raise ValueError(f'{key} must be boolean')
                if key == 'archived' and value and session_id == 'default':
                    raise ValueError('Default session cannot be archived')
                fields.append(key + '=?')
                values.append(int(value))
        if fields:
            async with self.db.transaction():
                if archived:
                    async with self.db._connection.execute("SELECT 1 FROM active_turns t JOIN interactions i ON i.id=t.thread_id WHERE COALESCE(json_extract(i.data, '$.session_id'), 'default')=? LIMIT 1", (session_id,)) as cursor:
                        if await cursor.fetchone():
                            raise ValueError('Cannot archive a running session')
                await self.db._connection.execute('UPDATE chat_sessions SET ' + ','.join(fields) + ', updated_at=CURRENT_TIMESTAMP WHERE id=?', (*values, session_id))
        return await self.get(session_id)
