"""One native FFI runtime, independent conversation lanes; no cross-chat turn cap.

A lane owns its lock, pending decisions, active turn, journal and poison state.
Runtime start/stop remains host-owned. Native crashes still share a process.
"""

import asyncio
from uuid import uuid4

from .copilot_client import CopilotBackend, _dict, _model_rows, _safe_label

_DIAGNOSTICS_TIMEOUT = 10


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
        for chat_id in list(self.compacting_sessions):
            try:
                await self.cancel_compaction(chat_id)
            except Exception:
                self.poisoned = True
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

    def diagnostic_identity(self, chat_id):
        """Opaque local references for snapshot freshness, never exported."""
        lane = self.lanes.get(chat_id)
        return (lane, lane.sessions.get(chat_id) if lane else None,
                lane.client if lane else None, self.runtime.client)

    def diagnostics(self, chat_id):
        """Passive lane lifecycle inspection; never acquire/create a session."""
        lane = self.lanes.get(chat_id)
        if lane is None:
            return {'state': 'not-started', 'session_bound': False, 'capabilities_verified': False}
        state = ('unavailable' if self.closing or self.runtime.closing or self.runtime.poisoned
                 or lane.closing or lane.poisoned
                 else 'busy' if lane.turn_lock.locked()
                 else 'ready' if lane.client is not None and lane.client is self.runtime.client
                 else 'not-started')
        return {'state': state, 'session_bound': chat_id in lane.sessions,
                'capabilities_verified': False}

    async def tool_diagnostics(self, chat_id):
        """Read metadata only from an already acquired, idle native session."""
        lane = self.lanes.get(chat_id)
        if lane is None or self.diagnostics(chat_id)['state'] != 'ready':
            return {'state': 'unavailable', 'tools': []}
        if chat_id not in lane.sessions:
            return {'state': 'unavailable', 'tools': []}
        async with lane.turn_lock:
            if self.diagnostics(chat_id)['state'] == 'unavailable':
                return {'state': 'unavailable', 'tools': []}
            session = lane.sessions.get(chat_id)
            if session is None or lane.client is not self.runtime.client:
                return {'state': 'unavailable', 'tools': []}
            client = lane.client
            try:
                async with asyncio.timeout(_DIAGNOSTICS_TIMEOUT):
                    metadata = await session.rpc.tools.get_current_metadata(timeout=_DIAGNOSTICS_TIMEOUT)
                if (self.lanes.get(chat_id) is not lane or lane.sessions.get(chat_id) is not session
                        or lane.client is not client or self.runtime.client is not client
                        or self.diagnostics(chat_id)['state'] == 'unavailable'):
                    return {'state': 'unavailable', 'tools': []}
                data = metadata.to_dict()
                if not isinstance(data, dict) or 'tools' not in data:
                    raise ValueError('Missing tool metadata')
                tools = data['tools']
                if tools is None:
                    return {'state': 'uninitialised', 'tools': []}
                if not isinstance(tools, list):
                    raise ValueError('Invalid tool metadata')
                from .diagnostics import _labels
                entries = []
                for tool in tools[:64]:
                    if not isinstance(tool, dict):
                        continue
                    names = _labels([tool.get('name')], 1)
                    deferred = tool.get('deferLoading', False)
                    if names and type(deferred) is bool:
                        entries.append({'name': names[0], 'state': 'deferred' if deferred else 'offered'})
                return {'state': 'reported', 'tools': entries,
                        'truncated': len(tools) > 64}
            except Exception:
                return {'state': 'unavailable', 'tools': []}

    async def mcp_diagnostics(self, chat_id):
        """Inspect existing MCP connection state, never connect or list tools."""
        lane = self.lanes.get(chat_id)
        if lane is None or self.diagnostics(chat_id)['state'] != 'ready':
            return {'state': 'unavailable', 'servers': []}
        async with lane.turn_lock:
            session = lane.sessions.get(chat_id)
            client = lane.client
            if session is None or client is not self.runtime.client or self.diagnostics(chat_id)['state'] == 'unavailable':
                return {'state': 'unavailable', 'servers': []}
            try:
                async with asyncio.timeout(_DIAGNOSTICS_TIMEOUT):
                    metadata = await session.rpc.mcp.list(timeout=_DIAGNOSTICS_TIMEOUT)
                if (self.lanes.get(chat_id) is not lane or lane.sessions.get(chat_id) is not session
                        or lane.client is not client or self.runtime.client is not client
                        or self.diagnostics(chat_id)['state'] == 'unavailable'):
                    return {'state': 'unavailable', 'servers': []}
                data = metadata.to_dict()
                if not isinstance(data, dict) or not isinstance(data.get('servers'), list):
                    raise ValueError('Invalid MCP metadata')
                from .diagnostics import _labels
                servers = []
                states = {'connected', 'failed', 'needs-auth', 'pending', 'disabled', 'stopped', 'not_configured'}
                for server in data['servers'][:32]:
                    if not isinstance(server, dict):
                        continue
                    names = _labels([server.get('name')], 1)
                    state = server.get('status')
                    if names and isinstance(state, str) and state in states:
                        servers.append({'name': names[0], 'state': state})
                return {'state': 'reported', 'servers': servers, 'truncated': len(data['servers']) > 32}
            except Exception:
                return {'state': 'unavailable', 'servers': []}

    async def skill_diagnostics(self, chat_id):
        """Inspect reported skill flags without loading contents or invoking skills."""
        lane = self.lanes.get(chat_id)
        if lane is None or self.diagnostics(chat_id)['state'] != 'ready':
            return {'state': 'unavailable', 'skills': []}
        async with lane.turn_lock:
            session = lane.sessions.get(chat_id)
            client = lane.client
            if session is None or client is not self.runtime.client or self.diagnostics(chat_id)['state'] == 'unavailable':
                return {'state': 'unavailable', 'skills': []}
            try:
                async with asyncio.timeout(_DIAGNOSTICS_TIMEOUT):
                    metadata = await session.rpc.skills.list(timeout=_DIAGNOSTICS_TIMEOUT)
                if (self.lanes.get(chat_id) is not lane or lane.sessions.get(chat_id) is not session
                        or lane.client is not client or self.runtime.client is not client
                        or self.diagnostics(chat_id)['state'] == 'unavailable'):
                    return {'state': 'unavailable', 'skills': []}
                data = metadata.to_dict()
                if not isinstance(data, dict) or not isinstance(data.get('skills'), list):
                    raise ValueError('Invalid skill metadata')
                from .diagnostics import _labels
                skills = []
                for server in data['skills'][:32]:
                    if not isinstance(server, dict):
                        continue
                    names = _labels([server.get('name')], 1)
                    enabled = server.get('enabled')
                    invocable = server.get('userInvocable')
                    if names and type(enabled) is bool and type(invocable) is bool:
                        skills.append({'name': names[0], 'state': 'enabled' if enabled else 'disabled',
                                       'user_invocable': invocable})
                return {'state': 'reported', 'skills': skills, 'truncated': len(data['skills']) > 32}
            except Exception:
                return {'state': 'unavailable', 'skills': []}

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

    async def command_catalogue(self, chat_id, store):
        return await self.lane(chat_id).command_catalogue(chat_id, store)

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

    async def classic_model(self, chat_id, changes=None, store=None):
        lane = self.lanes.get(chat_id)
        try:
            return await self._classic_model(chat_id, changes, store)
        except BaseException:
            # Failed reads, native timeouts and cancellation revoke observations
            # as well as setters. Never reuse a token across uncertain state.
            if lane is not None:
                lane.model_observations.pop(chat_id, None)
            raise

    async def _classic_model(self, chat_id, changes=None, store=None):
        """Existing idle lane only; observe and mutate under one native owner."""
        lane = self.lanes.get(chat_id)
        if lane is None or chat_id not in lane.sessions or self.diagnostics(chat_id)['state'] != 'ready':
            raise RuntimeError('Native model lane unavailable')
        captured = self.diagnostic_identity(chat_id)

        def check():
            if (any(current is not original for current, original in zip(self.diagnostic_identity(chat_id), captured))
                    or self.closing or self.runtime.closing
                    or self.runtime.poisoned or lane.closing or lane.poisoned):
                lane.model_observations.pop(chat_id, None)
                raise RuntimeError('Native model owner changed')

        async with lane.turn_lock:
            check()
            session = lane.sessions[chat_id]

            async def current():
                state = _dict(await session.rpc.model.get_current(timeout=10))
                check()
                if not isinstance(state, dict) or not _safe_label(state.get('modelId')):
                    lane.model_observations.pop(chat_id, None)
                    raise RuntimeError('Native model state unavailable')
                effort = state.get('reasoningEffort')
                if effort is not None and not _safe_label(effort):
                    lane.model_observations.pop(chat_id, None)
                    raise RuntimeError('Native reasoning state unavailable')
                observed = (session, lane.client, state['modelId'], effort)
                previous = lane.model_observations.get(chat_id)
                if previous is None or previous[:4] != observed:
                    lane.model_observations[chat_id] = (*observed, uuid4().hex)
                return state, lane.model_observations[chat_id][4]

            state, token = await current()
            raw = _dict(await session.rpc.model.list(timeout=10))
            check()
            if not isinstance(raw, dict) or not isinstance(raw.get('list'), list):
                raise RuntimeError('Native model catalogue unavailable')
            models = _model_rows(raw['list'])
            selected = next((row for row in models if row['id'] == state['modelId']), None)
            if changes is not None:
                if set(changes) == {'model'}:
                    if not any('copilot/' + row['id'] == changes['model'] for row in models):
                        raise ValueError('Model is not offered')
                    from copilot.generated.rpc import ModelSwitchToRequest
                    call = session.rpc.model.switch_to
                    argument = ModelSwitchToRequest(model_id=changes['model'].removeprefix('copilot/'), require_available=True)
                elif set(changes) == {'model', 'thinking_level', 'thinking_token'}:
                    if changes['model'] != 'copilot/' + state['modelId'] or changes['thinking_token'] != token:
                        raise RuntimeError('Native model observation is stale')
                    if selected is None or changes['thinking_level'] not in selected['efforts']:
                        raise ValueError('Thinking level is not offered')
                    from copilot.generated.rpc import ModelSetReasoningEffortRequest
                    call = session.rpc.model.set_reasoning_effort
                    argument = ModelSetReasoningEffortRequest(reasoning_effort=changes['thinking_level'])
                else:
                    raise ValueError('Unsupported native model fields')
                check()
                lane.model_observations.pop(chat_id, None)  # Before possibly committed native I/O.
                await call(argument, timeout=10)
                check()
                state, token = await current()
                if ('copilot/' + state['modelId'] != changes['model'] or
                        ('thinking_level' in changes and state.get('reasoningEffort') != changes['thinking_level'])):
                    raise RuntimeError('Native model change was not confirmed')
                lane.model_state[chat_id] = {'model_id': state['modelId'], 'thinking_level': state.get('reasoningEffort')}
                if store is not None and await store.backend_binding(chat_id, 'copilot-ffi'):
                    check()
                    from copilot.generated.rpc import SessionsSaveRequest
                    await lane.client.rpc.sessions.save(SessionsSaveRequest(session_id=session.session_id), timeout=5)
                    check()
                    await store.bind_backend(chat_id, 'copilot-ffi', session.session_id,
                                             model=state['modelId'], thinking_level=state.get('reasoningEffort'))
                    check()
                selected = next((row for row in models if row['id'] == state['modelId']), None)
            levels = selected['efforts'] if selected else []
            return {'state': {'model': {'provider': 'copilot', 'id': state['modelId'], 'reasoning': bool(levels)},
                              'thinkingLevel': state.get('reasoningEffort')},
                    'models': [{key: value for key, value in row.items() if key != 'efforts'} for row in models],
                    'thinking_levels': levels, 'thinking_token': token}

    async def abort(self, chat_id, expected):
        lane = self.lanes.get(chat_id)
        return await lane.abort(chat_id, expected) if lane else False


backend = CopilotHost()
