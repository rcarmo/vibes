"""Bounded read-only message queries for the forthcoming MCP adapter.

Scope is supplied by trusted adapter construction, never tool arguments.
No database connection is opened or schema migrated by this module.
"""
import json


class MessageTools:
    def __init__(self, connection, *, thread_id=None, session_id=None, workspace_access=False):
        if sum([thread_id is not None, session_id is not None, bool(workspace_access)]) != 1:
            raise ValueError('Exactly one explicit message scope required')
        if session_id is not None and (not isinstance(session_id, str) or not session_id):
            raise ValueError('Invalid session scope')
        self.connection = connection
        self.thread_id = thread_id
        self.session_id = session_id
        self.workspace_access = bool(workspace_access)

    def scope(self):
        if self.session_id is not None:
            return "COALESCE(json_extract(i.data, '$.session_id'), 'default') = ?", [self.session_id]
        if self.thread_id is None:
            return '1=1', []
        return '(i.id = ? OR i.thread_id = ?)', [self.thread_id, self.thread_id]

    async def attachment(self, media_id):
        if type(media_id) is not int or media_id < 1:
            raise ValueError('media_id must be a positive integer')
        scope, params = self.scope()
        # Authorization is through a referencing message, never the attachment ID alone.
        sql = '''SELECT m.id, m.filename, m.content_type, length(m.data) AS size,
                 substr(m.data, 1, 24001) AS preview
                 FROM media m WHERE m.id = ? AND EXISTS (
                   SELECT 1 FROM interactions i, json_each(i.data, '$.media_ids') ref
                   WHERE ''' + scope + ''' AND ref.type = 'integer' AND ref.value = m.id)'''
        async with self.connection.execute(sql, [media_id, *params]) as cursor:
            row = await cursor.fetchone()
        if not row:
            raise ValueError('Attachment unavailable in current scope')
        mime = row['content_type'].split(';', 1)[0].lower()
        result = {'media_id': row['id'], 'filename': row['filename'], 'content_type': mime, 'size': row['size']}
        if mime.startswith('text/') or mime in {'application/json', 'application/xml', 'application/yaml'}:
            raw = bytes(row['preview'])
            result.update({'text': raw[:24000].decode('utf-8', errors='replace'),
                'truncated': row['size'] > 24000})
        else:
            result['notice'] = 'Binary attachment: text preview unavailable.'
        return result

    async def resolve_session(self, reference):
        """Resolve identity only; a reference never expands the trusted scope."""
        if not isinstance(reference, str) or not reference.startswith('@session:'):
            raise ValueError('Expected @session:ID reference')
        session_id = reference[len('@session:'):]
        if not session_id or len(session_id) > 512 or any(char.isspace() or ord(char) < 32 for char in session_id):
            raise ValueError('Invalid session reference')
        allowed = self.workspace_access or self.session_id == session_id
        if self.thread_id is not None:
            async with self.connection.execute(
                "SELECT COALESCE(json_extract(data, '$.session_id'), 'default') FROM interactions WHERE id=?",
                (self.thread_id,),
            ) as cursor:
                owner = await cursor.fetchone()
            allowed = owner is not None and owner[0] == session_id
        if not allowed:
            return {'session': None}
        async with self.connection.execute(
            'SELECT id, name, archived FROM chat_sessions WHERE id=?', (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return {'session': {'id': row[0], 'name': row[1], 'archived': bool(row[2])} if row else None}

    async def query(self, action, *, row_ids=None, query='', limit=10, before_row=None, after_row=None,
                    context_before=0, context_after=0, media_id=None, reference=None):
        if action == 'resolve_session':
            return await self.resolve_session(reference)
        if action == 'attachment':
            return await self.attachment(media_id)
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError('limit must be between 1 and 50')
        for name, value in [('before_row', before_row), ('after_row', after_row)]:
            if value is not None and (type(value) is not int or value < 1):
                raise ValueError(f'{name} must be a positive integer')
        if before_row is not None and after_row is not None and after_row >= before_row:
            raise ValueError('after_row must be less than before_row')
        if any(type(value) is not int or not 0 <= value <= 20 for value in (context_before, context_after)):
            raise ValueError('context_before and context_after must be between 0 and 20')
        if action != 'get' and (context_before or context_after):
            raise ValueError('context windows are only supported for get')
        where, scope_params = self.scope()
        params = list(scope_params)
        clauses = [where]
        requested = []
        if action == 'get':
            if not isinstance(row_ids, list) or not 1 <= len(row_ids) <= 50 or any(type(i) is not int or i < 1 for i in row_ids):
                raise ValueError('row_ids must contain 1 to 50 positive integers')
            requested = list(dict.fromkeys(row_ids))
            authorized_requested = set()
            for row_id in requested:
                async with self.connection.execute('SELECT i.id FROM interactions i WHERE ' + where + ' AND i.id=?', [*scope_params, row_id]) as cursor:
                    if await cursor.fetchone(): authorized_requested.add(row_id)
            if context_before or context_after:
                selected = set(authorized_requested)
                for row_id in authorized_requested:
                    for op, count, order in [('<', context_before, 'DESC'), ('>', context_after, 'ASC')]:
                        if not count: continue
                        async with self.connection.execute('SELECT i.id FROM interactions i WHERE ' + where + f' AND i.id {op} ? ORDER BY i.id {order} LIMIT ?', [*scope_params, row_id, count]) as cursor:
                            selected.update(row[0] for row in await cursor.fetchall())
                clauses.append('i.id IN (' + ','.join('?' for _ in selected or [0]) + ')')
                params.extend(selected or [0])
            else:
                clauses.append('i.id IN (' + ','.join('?' for _ in requested) + ')')
                params.extend(requested)
        elif action == 'search':
            if not isinstance(query, str) or not query.strip() or len(query) > 500:
                raise ValueError('query must contain 1 to 500 characters')
            # Literal phrase search: tool callers cannot inject FTS operators.
            phrase = '"' + query.strip().replace('"', '""') + '"'
            clauses.append('i.id IN (SELECT rowid FROM interactions_fts WHERE interactions_fts MATCH ?)')
            params.append(phrase)
        else:
            raise ValueError('Unsupported messages action')
        if before_row is not None:
            clauses.append('i.id < ?'); params.append(before_row)
        if after_row is not None:
            clauses.append('i.id > ?'); params.append(after_row)
        sql = 'SELECT i.id, i.timestamp, i.data FROM interactions i WHERE ' + ' AND '.join(clauses) + ' ORDER BY i.id DESC LIMIT ?'
        params.append(limit + 1)
        async with self.connection.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
        messages = []
        remaining = 24000
        for row in rows[:limit]:
            data = json.loads(row['data'])
            raw_media_ids = data.get('media_ids', [])
            if not isinstance(raw_media_ids, list):
                raw_media_ids = []
            media_ids = list(dict.fromkeys(i for i in raw_media_ids if type(i) is int and i > 0))[:50]
            content = str(data.get('content', ''))
            bounded = content[:min(4000, remaining)]
            messages.append({'row_id': row['id'], 'timestamp': row['timestamp'],
                'type': data.get('type'), 'thread_id': data.get('thread_id'),
                'content': bounded, 'content_truncated': len(bounded) < len(content),
                'media_ids': media_ids,
                'attachment_references': [f'attachment:{i}' for i in media_ids]})
            remaining -= len(bounded)
            if remaining <= 0:
                break
        more = len(rows) > len(messages)
        result = {'messages': messages, 'has_more': more,
            'next_before_row': messages[-1]['row_id'] if more and messages else None}
        if action == 'get':
            result['missing_row_ids'] = [row_id for row_id in requested if row_id not in authorized_requested]
        return result
