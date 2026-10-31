"""Durable at-most-once admission for existing-lane native FFI compaction."""

import asyncio
import json
import time
from uuid import uuid4
from aiohttp import web

from .copilot_client import _dict


KEY = web.AppKey('vibes.classic_compaction', object)
_ACTIVE = ('pending', 'running', 'cancelling')


class CompactionError(RuntimeError):
    pass


class Compactions:
    def __init__(self):
        self.offers = {}
        self.tasks = {}
        self.owners = {}
        self.admissions = set()
        self.cancellations = {}
        self.closing = False

    @staticmethod
    def _identity(host, session_id):
        lane = host.lanes.get(session_id)
        if lane is None or host.diagnostics(session_id)['state'] != 'ready':
            return None
        session = lane.sessions.get(session_id)
        history = getattr(getattr(session, 'rpc', None), 'history', None)
        if session is None or not callable(getattr(history, 'compact', None)) or not callable(getattr(history, 'abort_manual_compaction', None)):
            return None
        return (lane, session, lane.client, host.client)

    @staticmethod
    def _same(host, session_id, captured):
        lane, session, client, shared = captured
        return (host.lanes.get(session_id) is lane and lane.sessions.get(session_id) is session
                and lane.client is client and host.client is shared and not host.closing
                and not host.runtime.closing and not host.runtime.poisoned and not lane.closing and not lane.poisoned)

    @staticmethod
    async def _version(db, session_id):
        async with db._connection.execute("SELECT COUNT(*),COALESCE(MAX(id),0) FROM interactions WHERE COALESCE(json_extract(data,'$.session_id'),'default')=?", (session_id,)) as cursor:
            message = tuple(await cursor.fetchone())
        async with db._connection.execute('SELECT updated_at,archived FROM chat_sessions WHERE id=?', (session_id,)) as cursor:
            row = await cursor.fetchone()
        return (message, tuple(row) if row else None)

    async def _blocked(self, db, session_id):
        async with db._connection.execute("SELECT 1 FROM compaction_operations WHERE session_id=? AND state IN ('pending','running','cancelling','uncertain') LIMIT 1", (session_id,)) as cursor:
            return await cursor.fetchone() is not None

    async def capability(self, db, host, session_id):
        async with db._connection.execute('SELECT turn_id,state,result FROM compaction_operations WHERE session_id=? ORDER BY rowid DESC LIMIT 1', (session_id,)) as cursor:
            last = await cursor.fetchone()
        operation = {'turn_id': last['turn_id'], 'state': last['state'],
                     'result': json.loads(last['result']) if last['result'] else None} if last else None
        unavailable = {'session_id': session_id, 'available': False, 'token': None,
                       'operation': operation, 'reason': 'native-operation-unavailable'}
        identity = self._identity(host, session_id)
        if self.closing or identity is None or await self._blocked(db, session_id):
            return unavailable
        lane = identity[0]
        version = await self._version(db, session_id)
        if not version[1] or version[1][1] or not self._same(host, session_id, identity) or lane.turn_lock.locked():
            return unavailable
        if await self.activity(db, session_id):
            return unavailable
        async with db._connection.execute("SELECT 1 FROM active_turns t JOIN interactions i ON i.id=t.thread_id WHERE COALESCE(json_extract(i.data,'$.session_id'),'default')=? LIMIT 1", (session_id,)) as cursor:
            if await cursor.fetchone():
                return unavailable
        now = time.monotonic()
        self.offers = {token: offer for token, offer in self.offers.items() if offer[0] > now}
        for token, offer in self.offers.items():
            if offer[1] == session_id and all(a is b for a, b in zip(offer[2], identity)) and offer[3] == version:
                return {'session_id': session_id, 'available': True, 'token': token, 'operation': operation}
        if len(self.offers) >= 128:
            return unavailable
        token = uuid4().hex
        self.offers[token] = (now + 30, session_id, identity, version)
        return {'session_id': session_id, 'available': True, 'token': token, 'operation': operation}

    async def activity(self, db, session_id):
        async with db._connection.execute("SELECT turn_id,state FROM compaction_operations WHERE session_id=? AND state IN ('pending','running','cancelling') ORDER BY created_at LIMIT 1", (session_id,)) as cursor:
            row = await cursor.fetchone()
        if row:
            return {'session_id': session_id, 'source_session_id': session_id, 'turn_id': row['turn_id'],
                    'status': 'cancelling' if row['state'] == 'cancelling' else 'running', 'intent_key': 'compaction'}
        return None

    async def admit(self, db, host, session_id, token):
        if self.closing:
            raise CompactionError('Compaction admission is closing')
        task = asyncio.current_task()
        self.admissions.add(task)
        try:
            return await self._admit(db, host, session_id, token)
        finally:
            self.admissions.discard(task)

    async def _admit(self, db, host, session_id, token):
        from .routes import agents
        async with agents._ffi_lock(agents._ffi_admission_locks, session_id):
            async with db._connection.execute('SELECT * FROM compaction_operations WHERE token=? AND session_id=?', (token, session_id)) as cursor:
                previous = await cursor.fetchone()
            if previous:
                return {'turn_id': previous['turn_id'], 'state': previous['state'], 'recovered': True}
            offer = self.offers.get(token)
            if self.closing or not offer or offer[0] <= time.monotonic() or offer[1] != session_id:
                raise CompactionError('Compaction capability expired; refresh')
            identity = offer[2]
            lane = identity[0]
            if not self._same(host, session_id, identity) or lane.turn_lock.locked() or session_id in agents._ffi_tasks:
                raise CompactionError('Native owner is no longer idle')
            await lane.turn_lock.acquire()
            try:
                async with db.transaction() as connection:
                    await connection.execute('BEGIN IMMEDIATE')
                    if (not self._same(host, session_id, identity) or offer[3] != await self._version(db, session_id)
                            or await self._blocked(db, session_id)):
                        raise CompactionError('Compaction state changed; refresh')
                    async with connection.execute("SELECT 1 FROM active_turns t JOIN interactions i ON i.id=t.thread_id WHERE COALESCE(json_extract(i.data,'$.session_id'),'default')=? LIMIT 1", (session_id,)) as cursor:
                        if await cursor.fetchone():
                            raise CompactionError('A conversation turn is active')
                    turn_id = 'compact-' + uuid4().hex
                    await connection.execute("INSERT INTO compaction_operations(token,session_id,turn_id,state) VALUES(?,?,?,'pending')", (token, session_id, turn_id))
                # No await from committed admission to retained task registration.
                self.offers.pop(token, None)
                self.owners[turn_id] = (session_id, identity)
                task = asyncio.create_task(self._run(db, host, session_id, token, turn_id, identity))
                self.tasks[turn_id] = task
                return {'turn_id': turn_id, 'state': 'pending', 'recovered': False}
            except BaseException:
                lane.turn_lock.release()
                raise

    async def _state(self, db, token, state, result=None):
        async with db.transaction() as connection:
            # Completion races cancellation's durable running->cancelling CAS.
            # Once cancellation wins, completion cannot drop protection even
            # if its task was registered after the worker's in-memory check.
            source = "state='running'" if state == 'completed' else "state IN ('pending','running','cancelling')"
            cursor = await connection.execute("UPDATE compaction_operations SET state=?,result=?,updated_at=CURRENT_TIMESTAMP WHERE token=? AND " + source, (state, json.dumps(result) if result is not None else None, token))
            return cursor.rowcount == 1

    async def _run(self, db, host, session_id, token, turn_id, identity):
        lane, session, _, _ = identity
        attempted = False
        try:
            await self._state(db, token, 'running')
            if self.closing or not self._same(host, session_id, identity):
                raise CompactionError('Native owner changed before compaction')
            lane.compacting_sessions.add(session_id)
            attempted = True
            async with asyncio.timeout(125):
                result = _dict(await session.rpc.history.compact(timeout=120))
            if not self._same(host, session_id, identity) or not isinstance(result, dict) or type(result.get('success')) is not bool:
                raise CompactionError('Native compaction completion unconfirmed')
            counts = {key: result[key] for key in ('messagesRemoved', 'tokensRemoved')
                      if type(result.get(key)) is int and result[key] >= 0}
            if not result['success']:
                raise CompactionError('Native failure does not prove absence of mutation')
            cancellation = self.cancellations.get(turn_id)
            if cancellation is not None:
                await asyncio.shield(cancellation)
                raise CompactionError('Abort applied; native mutation outcome requires reconciliation')
            # Even a failed/late abort may have reached native state. Only
            # publish terminal completion after both RPCs settle authoritatively.
            if not self._same(host, session_id, identity):
                raise CompactionError('Native owner uncertain after cancellation')
            if not await self._state(db, token, 'completed', counts):
                raise CompactionError('Cancellation won completion publication')
        except BaseException:
            # Native mutation may have completed. Never release this admission
            # to automatic replay; poison ambiguous native sessions until restart.
            if attempted:
                lane.poisoned = True
            settle = asyncio.create_task(self._state(db, token, 'uncertain' if attempted else 'failed'))
            await asyncio.shield(settle)
        finally:
            # Keep the lane reserved until any captured abort RPC settles. A
            # delayed abort must never reach a subsequently promoted operation.
            cancellation = self.cancellations.get(turn_id)
            if cancellation is not None:
                try:
                    await asyncio.shield(cancellation)
                except BaseException:
                    lane.poisoned = True
            lane.compacting_sessions.discard(session_id)
            self.cancellations.pop(turn_id, None)
            self.owners.pop(turn_id, None)
            self.tasks.pop(turn_id, None)
            lane.turn_lock.release()

    async def cancel(self, db, host, session_id, turn_id):
        owner = self.owners.get(turn_id)
        if owner is None or owner[0] != session_id or not self._same(host, session_id, owner[1]):
            raise CompactionError('Compaction owner is no longer active')
        if turn_id in self.cancellations:
            raise CompactionError('Cancellation already in progress')
        task = asyncio.create_task(self._cancel_owned(db, host, session_id, turn_id))
        self.cancellations[turn_id] = task
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await asyncio.shield(task)
            raise
        finally:
            if turn_id not in self.tasks and task.done():
                self.cancellations.pop(turn_id, None)

    async def _cancel_owned(self, db, host, session_id, turn_id):
        owner = self.owners.get(turn_id)
        if owner is None or owner[0] != session_id or not self._same(host, session_id, owner[1]):
            raise CompactionError('Compaction owner is no longer active')
        lane, session, _, _ = owner[1]
        if session_id not in lane.compacting_sessions:
            raise CompactionError('Compaction has not entered native execution')
        async with db.transaction() as connection:
            cursor = await connection.execute("UPDATE compaction_operations SET state='cancelling',updated_at=CURRENT_TIMESTAMP WHERE turn_id=? AND session_id=? AND state='running'", (turn_id, session_id))
            if cursor.rowcount != 1:
                raise CompactionError('Compaction is no longer cancellable')
        if self.owners.get(turn_id) is not owner or not self._same(host, session_id, owner[1]):
            raise CompactionError('Compaction owner changed')
        try:
            async with asyncio.timeout(11):
                result = _dict(await session.rpc.history.abort_manual_compaction(timeout=10))
            if not isinstance(result, dict) or result.get('aborted') is not True:
                raise CompactionError('Native cancellation unconfirmed; inspect activity')
        except BaseException:
            lane.poisoned = True
            raise
        return {'status': 'cancelling', 'session_id': session_id, 'turn_id': turn_id}

    async def recover(self, db):
        async with db.transaction() as connection:
            await connection.execute("UPDATE compaction_operations SET state='uncertain',updated_at=CURRENT_TIMESTAMP WHERE state IN ('pending','running','cancelling')")

    async def close(self, db, host):
        self.closing = True
        self.offers.clear()
        await asyncio.gather(*(task for task in self.admissions if task is not asyncio.current_task()), return_exceptions=True)
        for turn_id, (session_id, _) in list(self.owners.items()):
            try:
                await self.cancel(db, host, session_id, turn_id)
            except Exception:
                pass
        tasks = list(self.tasks.values())
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=1)
            for task in pending:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
