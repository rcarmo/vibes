"""Transaction-owned durable follow-up storage and explicit ambiguity review."""
from datetime import datetime, timezone
from uuid import uuid4
from contextlib import asynccontextmanager


class FollowupStore:
    def __init__(self, db):
        self.db = db

    @asynccontextmanager
    async def _write(self):
        # Database owns shared-connection locking and rollback. SQLite also
        # serializes independent connections before we read mutation state.
        async with self.db.transaction() as connection:
            await connection.execute('BEGIN IMMEDIATE')
            yield connection

    @staticmethod
    def _item(row):
        if row is None:
            return None
        item = dict(row)
        item['row_id'] = -item.pop('sequence')
        item['emulated'] = bool(item['emulated'])
        return item

    async def enqueue(self, *, thread_id, agent_id, message_id, content, steer=False):
        mode = 'steer' if steer else 'queue'
        async with self._write() as connection:
            cursor = await connection.execute(
                "INSERT INTO followup_queue(thread_id,agent_id,message_id,content,mode,created_at,emulated,ordinal) "
                "VALUES(?,?,?,?,?,?,?,(SELECT COALESCE(MAX(ordinal),0)+1 FROM followup_queue))",
                (thread_id, agent_id, message_id, content, mode, datetime.now(timezone.utc).isoformat(), int(steer)))
            async with connection.execute('SELECT * FROM followup_queue WHERE sequence=?', (cursor.lastrowid,)) as rows:
                return self._item(await rows.fetchone())

    async def claim(self, thread_id, agent_id):
        async with self._write() as connection:
            async with connection.execute(
                "SELECT * FROM followup_queue WHERE thread_id=? AND agent_id=? AND state='pending' "
                "ORDER BY CASE mode WHEN 'steer' THEN 0 ELSE 1 END, ordinal LIMIT 1",
                (thread_id, agent_id)) as cursor:
                row = await cursor.fetchone()
            if row is None:
                return None
            token = uuid4().hex
            cursor = await connection.execute(
                "UPDATE followup_queue SET state='claimed', claim_token=? WHERE sequence=? AND state='pending'",
                (token, row['sequence']))
            if cursor.rowcount != 1:
                return None
            item = self._item(row)
            item.update(state='claimed', claim_token=token)
            return item

    async def claim_for_steer(self, row_id, *, thread_id, agent_id):
        sequence = self._sequence(row_id)
        async with self._write() as connection:
            async with connection.execute(
                "SELECT * FROM followup_queue WHERE sequence=? AND thread_id=? AND agent_id=? "
                "AND state='pending' AND mode='queue'", (sequence, thread_id, agent_id)) as cursor:
                row = await cursor.fetchone()
            if row is None:
                return None
            token = uuid4().hex
            cursor = await connection.execute(
                "UPDATE followup_queue SET state='claimed', claim_token=? WHERE sequence=? AND state='pending' AND mode='queue'",
                (token, sequence))
            if cursor.rowcount != 1:
                return None
            item = self._item(row)
            item.update(state='claimed', claim_token=token)
            return item

    async def transition_claim(self, item, *, admitted=False, defer_steer=False):
        """Only the current opaque claim owner may release or admit a row."""
        if admitted and defer_steer:
            raise ValueError('Conflicting claim transition')
        row_id = item.get('row_id')
        token = item.get('claim_token')
        if type(row_id) is not int or row_id >= 0 or not isinstance(token, str) or not token:
            raise ValueError('Invalid claim identity')
        async with self._write() as connection:
            if defer_steer:
                async with connection.execute('SELECT COALESCE(MAX(ordinal),0)+1 FROM followup_queue') as cursor:
                    ordinal = (await cursor.fetchone())[0]
                cursor = await connection.execute(
                    "UPDATE followup_queue SET state='pending', mode='steer', emulated=1, ordinal=?, claim_token=NULL "
                    "WHERE sequence=? AND thread_id=? AND agent_id=? AND state='claimed' AND claim_token=?",
                    (ordinal, -row_id, item['thread_id'], item['agent_id'], token))
                if cursor.rowcount != 1:
                    raise ValueError('Claim no longer owned')
                return
            cursor = await connection.execute(
                "UPDATE followup_queue SET state=?, claim_token=? WHERE sequence=? "
                "AND thread_id=? AND agent_id=? AND state='claimed' AND claim_token=?",
                ('admitted' if admitted else 'pending', token if admitted else None,
                 -row_id, item['thread_id'], item['agent_id'], token))
            if cursor.rowcount != 1:
                raise ValueError('Claim no longer owned')

    async def complete(self, item):
        """Remove only work whose admitted owner confirms completion."""
        sequence = self._sequence(item.get('row_id'))
        token = item.get('claim_token')
        if not isinstance(token, str) or not token:
            raise ValueError('Invalid claim identity')
        async with self._write() as connection:
            cursor = await connection.execute(
                "DELETE FROM followup_queue WHERE sequence=? AND thread_id=? AND agent_id=? "
                "AND state='admitted' AND claim_token=?",
                (sequence, item['thread_id'], item['agent_id'], token))
            if cursor.rowcount != 1:
                raise ValueError('Admission no longer owned')

    async def mark_uncertain(self, item):
        """Revoke an admitted owner after an ambiguous execution outcome."""
        sequence = self._sequence(item.get('row_id'))
        token = item.get('claim_token')
        if not isinstance(token, str) or not token:
            raise ValueError('Invalid claim identity')
        async with self._write() as connection:
            cursor = await connection.execute(
                "UPDATE followup_queue SET state='uncertain', claim_token=NULL "
                "WHERE sequence=? AND thread_id=? AND agent_id=? "
                "AND state='admitted' AND claim_token=?",
                (sequence, item['thread_id'], item['agent_id'], token))
            if cursor.rowcount != 1:
                raise ValueError('Admission no longer owned')

    async def list(self, *, thread_id=None, agent_id=None):
        filters, params = [], []
        for column, value in [('thread_id', thread_id), ('agent_id', agent_id)]:
            if value is not None:
                filters.append(column + '=?')
                params.append(value)
        where = ' WHERE ' + ' AND '.join(filters) if filters else ''
        async with self.db.transaction() as connection:
            async with connection.execute(
                'SELECT * FROM followup_queue' + where + ' ORDER BY ordinal', params) as cursor:
                items = [self._item(row) for row in await cursor.fetchall()]
        for item in items:
            item.pop('claim_token', None)
        return items

    @staticmethod
    def _sequence(row_id):
        if type(row_id) is not int or row_id >= 0:
            raise ValueError('Invalid queue identity')
        return -row_id

    async def remove(self, row_id, *, thread_id, agent_id):
        sequence = self._sequence(row_id)
        async with self._write() as connection:
            async with connection.execute(
                "SELECT * FROM followup_queue WHERE sequence=? AND thread_id=? AND agent_id=? AND state='pending'",
                (sequence, thread_id, agent_id)) as cursor:
                row = await cursor.fetchone()
            if row is None:
                return None
            cursor = await connection.execute("DELETE FROM followup_queue WHERE sequence=? AND state='pending'", (sequence,))
            if cursor.rowcount != 1:
                return None
            item = self._item(row)
            item.pop('claim_token', None)
            return item

    async def discard_uncertain(self, row_id, *, thread_id, agent_id):
        """Explicit review action; never retries or changes pending work."""
        sequence = self._sequence(row_id)
        async with self._write() as connection:
            cursor = await connection.execute(
                "DELETE FROM followup_queue WHERE sequence=? AND thread_id=? AND agent_id=? AND state='uncertain'",
                (sequence, thread_id, agent_id))
            return cursor.rowcount == 1

    async def reorder(self, row_id, direction, *, thread_id, agent_id):
        sequence = self._sequence(row_id)
        if direction not in ('up', 'down'):
            raise ValueError('Invalid direction')
        async with self._write() as connection:
            async with connection.execute(
                "SELECT sequence,ordinal FROM followup_queue WHERE thread_id=? AND agent_id=? "
                "AND state='pending' AND mode='queue' ORDER BY ordinal",
                (thread_id, agent_id)) as cursor:
                rows = await cursor.fetchall()
            index = next((i for i, row in enumerate(rows) if row['sequence'] == sequence), None)
            if index is None:
                return False
            target = index + (-1 if direction == 'up' else 1)
            if 0 <= target < len(rows):
                first, second = rows[index], rows[target]
                await connection.executemany('UPDATE followup_queue SET ordinal=? WHERE sequence=?',
                                             [(second['ordinal'], first['sequence']), (first['ordinal'], second['sequence'])])
            return True

    async def recover(self):
        """Exclusive startup only; ambiguous ownership is never automatically replayed."""
        async with self._write() as connection:
            await connection.execute("UPDATE followup_queue SET state='uncertain', claim_token=NULL WHERE state IN ('claimed','admitted')")
