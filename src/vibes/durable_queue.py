"""Durable queue admission journal; ambiguous claims never replay automatically."""
import json
from uuid import uuid4


class DurableQueue:
    def __init__(self, connection):
        self.connection = connection

    async def initialise(self):
        await self.connection.execute('CREATE TABLE IF NOT EXISTS queued_work (id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL, ordinal INTEGER NOT NULL)')
        await self.connection.execute("UPDATE queued_work SET state='uncertain' WHERE state='claimed'")
        await self.connection.commit()

    async def enqueue(self, chat_id, payload):
        encoded = json.dumps(payload)
        if not isinstance(chat_id, str) or not chat_id or len(encoded) > 128 * 1024:
            raise ValueError('Invalid queued work')
        item_id = uuid4().hex
        await self.connection.execute("INSERT INTO queued_work VALUES(?,?,?,'pending',(SELECT COALESCE(MAX(ordinal),0)+1 FROM queued_work))", (item_id, chat_id, encoded))
        await self.connection.commit()
        return item_id

    async def claim(self, chat_id):
        async with self.connection.execute("SELECT id,payload FROM queued_work WHERE chat_id=? AND state='pending' ORDER BY ordinal LIMIT 1", (chat_id,)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        cursor = await self.connection.execute("UPDATE queued_work SET state='claimed' WHERE id=? AND state='pending'", (row[0],))
        await self.connection.commit()
        return {'id': row[0], 'payload': json.loads(row[1])} if cursor.rowcount == 1 else None

    async def admitted(self, item_id, chat_id):
        cursor = await self.connection.execute("UPDATE queued_work SET state='admitted' WHERE id=? AND chat_id=? AND state='claimed'", (item_id, chat_id))
        await self.connection.commit()
        if cursor.rowcount != 1:
            raise ValueError('No matching claimed work')

    async def list(self, chat_id):
        async with self.connection.execute('SELECT id,state,payload FROM queued_work WHERE chat_id=? ORDER BY ordinal', (chat_id,)) as cursor:
            rows = await cursor.fetchall()
        return [{'id': row[0], 'state': row[1], 'payload': json.loads(row[2])} for row in rows]
