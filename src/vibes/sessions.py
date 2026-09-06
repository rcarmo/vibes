"""Durable chat metadata. Does not launch or switch agent processes."""
import re
import uuid


class SessionStore:
    def __init__(self, database):
        self.db = database

    async def list(self, include_archived=False):
        async with self.db._connection.execute(
            'SELECT * FROM chat_sessions WHERE (? OR archived=0) ORDER BY pinned DESC, updated_at DESC, id',
            (int(include_archived),),
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

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
                await self.db._connection.execute('UPDATE chat_sessions SET ' + ','.join(fields) + ', updated_at=CURRENT_TIMESTAMP WHERE id=?', (*values, session_id))
        return await self.get(session_id)
