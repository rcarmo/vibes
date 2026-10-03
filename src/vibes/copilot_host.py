"""One native FFI runtime, independent conversation lanes; no cross-chat turn cap.

A lane owns its lock, pending decisions, active turn, journal and poison state.
Runtime start/stop remains host-owned. Native crashes still share a process.
"""

import asyncio

from .copilot_client import CopilotBackend


class ConversationLane(CopilotBackend):
    def __init__(self, host, chat_id):
        super().__init__()
        self.host = host
        self.chat_id = chat_id

    async def start(self):
        if self.closing or self.host.closing:
            raise RuntimeError("Native host is shutting down")
        if self.poisoned:
            raise RuntimeError(
                "This conversation requires a server restart after incomplete cleanup"
            )
        await self.host.start()
        if self.host.closing:
            raise RuntimeError("Native host is shutting down")
        self.client, self.sdk = self.host.client, self.host.runtime.sdk

    async def stop(self, *, permanent=False):
        # A lane must never stop the shared native client.
        self.closing = True
        if self.active:
            try:
                await self.abort(self.chat_id, self.active)
            except Exception:
                self.poisoned = True
        self._deny_pending()
        try:
            await asyncio.wait_for(self.turn_lock.acquire(), 6)
            self.turn_lock.release()
        except asyncio.TimeoutError:
            self.poisoned = True
            raise RuntimeError("Conversation did not quiesce during shutdown") from None
        self.sessions.clear()
        self.client = None
        self.closing = permanent


class CopilotHost:
    def __init__(self):
        self.runtime = CopilotBackend()
        self.lanes = {}
        self.closing = False
        self.stop_lock = asyncio.Lock()
        self.request_callback = None
        self.request_closed_callback = None

    @property
    def client(self):
        return self.runtime.client

    @client.setter
    def client(self, value):
        self.runtime.client = value

    def lane(self, chat_id):
        if not isinstance(chat_id, str) or not chat_id:
            raise ValueError("Conversation identity required")
        lane = self.lanes.get(chat_id)
        if lane is None:
            lane = self.lanes[chat_id] = ConversationLane(self, chat_id)
        lane.request_callback = self.request_callback
        lane.request_closed_callback = self.request_closed_callback
        return lane

    def busy(self, chat_id=None):
        if chat_id is not None:
            lane = self.lanes.get(chat_id)
            return bool(lane and lane.turn_lock.locked())
        return any(lane.turn_lock.locked() for lane in self.lanes.values())

    def active_for(self, chat_id):
        lane = self.lanes.get(chat_id)
        return lane.active if lane else None

    def status(self):
        return {
            **self.runtime.status(),
            "ready": self.runtime.status()["ready"] and not self.closing,
            "busy": self.busy(),
            "active_chats": sum(
                lane.turn_lock.locked() for lane in self.lanes.values()
            ),
            "failed_chats": sum(lane.poisoned for lane in self.lanes.values()),
        }

    async def start(self):
        if self.closing:
            raise RuntimeError("Native host is shutting down")
        await self.runtime.start()

    async def stop(self, *, permanent=False):
        self.closing = True
        async with self.stop_lock:
            lanes = list(self.lanes.values())
            # Deny every lane before yielding. Drain concurrently, not N * timeout.
            for lane in lanes:
                lane.closing = True
                lane._deny_pending()
            results = await asyncio.gather(
                *(lane.stop(permanent=True) for lane in lanes), return_exceptions=True
            )
            if any(isinstance(result, BaseException) for result in results):
                self.runtime.poisoned = True
            await self.runtime.stop(permanent=permanent)
            self.lanes.clear()
            self.closing = permanent

    def pending_requests(self, chat_id=None):
        lanes = (
            [self.lanes[chat_id]]
            if chat_id in self.lanes
            else []
            if chat_id is not None
            else list(self.lanes.values())
        )
        return [payload for lane in lanes for payload in lane.pending_requests(chat_id)]

    def respond(self, request_id, outcome, answer=None):
        if not isinstance(request_id, str):
            return False
        for lane in self.lanes.values():
            if request_id in lane.pending:
                return lane.respond(request_id, outcome, answer)
        return False

    async def send(
        self,
        content,
        thread_id,
        callback,
        *,
        chat_id,
        store,
        media_ids=None,
        attachment_context=None,
    ):
        if self.closing:
            raise RuntimeError("Native host is shutting down")
        if not attachment_context or attachment_context.get("session_id") != chat_id:
            raise RuntimeError("Explicit attachment ownership required")
        return await self.lane(chat_id).send(
            content,
            thread_id,
            callback,
            chat_id=chat_id,
            store=store,
            media_ids=media_ids,
            attachment_context=attachment_context,
        )

    async def compact(self, chat_id, store):
        return await self.lane(chat_id).compact(chat_id, store)

    async def cancel_compaction(self, chat_id):
        lane = self.lanes.get(chat_id)
        return await lane.cancel_compaction(chat_id) if lane else False

    async def models(self, chat_id, store):
        return await self.lane(chat_id).models(chat_id, store)

    async def model(self, chat_id, store, changes=None):
        return await self.lane(chat_id).model(chat_id, store, changes)

    async def abort(self, chat_id, expected):
        lane = self.lanes.get(chat_id)
        return await lane.abort(chat_id, expected) if lane else False


backend = CopilotHost()
