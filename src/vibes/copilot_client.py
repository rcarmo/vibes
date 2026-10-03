"""Optional Copilot backend. Native FFI only; never falls back to another transport.

The SDK owns the C ABI, native callbacks and shutdown. This module owns the
Vibes session/turn binding and ordered event translation. No credentials are
stored here. Each instance owns one conversation lane; copilot_host shares its runtime.
"""
import asyncio
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import sys
import uuid

from .config import get_config

log = logging.getLogger(__name__)
SDK_VERSION = '1.0.14'
RUNTIME_VERSION = '1.0.85'
BACKEND = 'copilot-ffi'


def _sdk():
    if sys.version_info < (3, 11):
        raise RuntimeError('Copilot FFI requires Python 3.11 or later')
    try:
        import copilot
    except ImportError:
        raise RuntimeError("Install the optional backend with pip install 'vibes[copilot]'") from None
    if importlib.metadata.version('github-copilot-sdk') != SDK_VERSION:
        raise RuntimeError(f'Copilot FFI requires tested SDK {SDK_VERSION}; reprovision its matching runtime')
    # Fail before SDK construction: it otherwise downloads implicitly.
    if os.environ.get('COPILOT_SKIP_CLI_DOWNLOAD', '').lower() not in {'1', 'true', 'yes'}:
        raise RuntimeError('Provision the native runtime, then set COPILOT_SKIP_CLI_DOWNLOAD=1 before starting Vibes')
    return copilot


def _draft_preview(text):
    """Bounded cumulative snapshot; collapsed SSE is lossy, individual deltas are not snapshots."""
    value = text.replace('\r\n', '\n')
    lines = value.split('\n')
    return {'text': '\n'.join(lines[-9:])[-16000:],
            'total_lines': sum(max(1, (len(line) + 159) // 160) for line in lines) if value else 0}


def _safe_label(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 512 and not any(ord(c) < 32 or ord(c) == 127 for c in value)


def _model_rows(value):
    """Expose bounded display metadata only; never serialize raw provider config."""
    if not isinstance(value, list):
        return []
    result, seen = [], set()
    for raw in value[:500]:
        row = _dict(raw)
        identity = row.get('id', row.get('modelId'))
        if not _safe_label(identity) or identity in seen:
            continue
        seen.add(identity)
        efforts = row.get('supportedReasoningEfforts', [])
        efforts = list(dict.fromkeys(e for e in efforts[:16] if _safe_label(e))) if isinstance(efforts, list) else []
        result.append({'id': identity, 'provider': 'copilot',
                       'name': row['name'] if _safe_label(row.get('name')) else identity,
                       'reasoning': bool(efforts), 'efforts': efforts})
    return result


def _dict(value):
    if isinstance(value, dict):
        return value
    if hasattr(value, 'to_dict'):
        return value.to_dict()
    return vars(value) if hasattr(value, '__dict__') else {}


class CopilotBackend:
    def __init__(self):
        self.client = None
        self.sdk = None
        self.runtime_version = None
        self.error = None
        self.lifecycle_lock = asyncio.Lock()
        self.stop_lock = asyncio.Lock()
        self.turn_lock = asyncio.Lock()
        self.sessions = {}
        self.model_state = {}
        self.active = None
        self.pending = {}
        self.request_callback = None
        self.request_closed_callback = None
        self.poisoned = False
        self.closing = False

    def status(self):
        return {'backend': BACKEND, 'transport': 'ffi', 'ready': self.client is not None and not self.poisoned and not self.closing,
                'sdk_version': SDK_VERSION, 'runtime_version': self.runtime_version,
                'error': self.error, 'busy': self.turn_lock.locked()}

    async def start(self):
        if self.closing:
            raise RuntimeError('Native host is shutting down')
        async with self.lifecycle_lock:
            if self.closing:
                raise RuntimeError('Native host is shutting down')
            if self.poisoned:
                raise RuntimeError('Native host requires a server restart after incomplete cleanup')
            if self.client is not None:
                return
            try:
                self.sdk = _sdk()
            except RuntimeError as exc:
                self.error = str(exc)  # Locally authored preflight messages only.
                raise
            client = None
            try:
                config = get_config()
                state_dir = Path(config.copilot_state_dir).absolute()
                state_dir.mkdir(parents=True, exist_ok=True)
                client = self.sdk.CopilotClient(
                    connection=self.sdk.RuntimeConnection.for_inprocess(),
                    base_directory=str(state_dir), mode='empty',
                    use_logged_in_user=config.copilot_use_logged_in_user,
                    enable_remote_sessions=False, log_level='error')
                await asyncio.wait_for(client.start(), config.copilot_start_timeout)
                status = _dict(await asyncio.wait_for(client.get_status(), 5))
                self.runtime_version = status.get('version')
                if self.runtime_version != RUNTIME_VERSION:
                    raise RuntimeError('Unexpected native runtime version; provision the SDK-pinned runtime')
                self.client, self.error = client, None
            except BaseException as exc:
                self.error = f'Copilot FFI unavailable ({type(exc).__name__}); check the optional SDK and provisioned native runtime'
                if client is not None:
                    try:
                        await asyncio.wait_for(client.stop(), 10)
                    except BaseException:
                        self.poisoned = True
                if isinstance(exc, asyncio.CancelledError):
                    raise
                # No tokens, arguments or raw provider error bodies in status/logs.
                raise RuntimeError(self.error) from None

    async def stop(self, *, permanent=False):
        # Reject new work before waiting for native lifecycle ownership.
        self.closing = True
        async with self.stop_lock:
            if self.active:
                try:
                    await self.abort(self.active['chat_id'], self.active)
                except Exception:
                    self.poisoned = True
            self._deny_pending()
            if self.turn_lock.locked():
                try:
                    await asyncio.wait_for(self.turn_lock.acquire(), 6)
                    self.turn_lock.release()
                except asyncio.TimeoutError:
                    self.poisoned = True
            # Never hold lifecycle_lock while waiting for turn_lock: send/model
            # acquire them in the opposite order while starting the native host.
            async with self.lifecycle_lock:
                client, self.client = self.client, None
                self.sessions.clear()
                if client:
                    try:
                        await asyncio.wait_for(client.stop(), 10)
                    except BaseException:
                        self.poisoned = True
                        self.error = 'Native cleanup incomplete; restart the Vibes process'
                        raise
            self.closing = permanent

    def _deny_pending(self):
        for item in list(self.pending.values()):
            if not item['future'].done():
                item['future'].set_result('deny')

    def pending_requests(self, chat_id=None):
        return [item['payload'] for item in self.pending.values()
                if not item['future'].done() and item['owner'] is self.active
                and not item['owner']['cancelled']
                and (chat_id is None or item['owner']['chat_id'] == chat_id)]

    def respond(self, request_id, outcome, answer=None):
        if not isinstance(request_id, str):
            return False
        item = self.pending.get(request_id)
        if (not isinstance(outcome, str) or not item or item['owner'] is not self.active or item['owner']['cancelled']
                or item['future'].done() or outcome not in item['allowed']):
            return False
        if outcome == 'freeform':
            if not isinstance(answer, str) or not answer.strip() or len(answer) > 8000:
                return False
            item['future'].set_result({'answer': answer, 'wasFreeform': True})
        else:
            item['future'].set_result(outcome)
        return True

    async def _decision(self, title, detail, options):
        owner = self.active
        if not owner or owner['cancelled'] or not self.request_callback:
            return 'deny'
        request_id = 'ffi-' + uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        payload = {'request_id': request_id, 'session_id': owner['chat_id'],
                   'thread_id': owner['thread_id'], 'turn_id': owner['turn_id'],
                   'tool_call': {'title': title, 'rawInput': detail,
                                 'description': json.dumps(detail, ensure_ascii=False, indent=2) if detail else title},
                   'options': [x for x in options if x['optionId'] != 'freeform'],
                   'allow_freeform': any(x['optionId'] == 'freeform' for x in options)}
        self.pending[request_id] = {'owner': owner, 'future': future, 'payload': payload,
                                    'allowed': {x['optionId'] for x in options}}
        reason = 'resolved'
        try:
            async def await_response():
                await self.request_callback(payload)
                return await future
            answer = await asyncio.wait_for(await_response(), get_config().permission_timeout)
            return answer if owner is self.active and not owner['cancelled'] else 'deny'
        except asyncio.TimeoutError:
            reason = 'timeout'
            return 'deny'
        finally:
            self.pending.pop(request_id, None)
            if not future.done():
                future.cancel()
            if self.request_closed_callback:
                try:
                    await asyncio.wait_for(self.request_closed_callback({
                        'request_id': request_id, 'session_id': owner['chat_id'],
                        'thread_id': owner['thread_id'], 'turn_id': owner['turn_id'], 'reason': reason}), 2)
                except Exception:
                    # A UI notification failure is not authority to retry a decision.
                    log.warning('Copilot request closure notification failed')

    async def _permission(self, request, _invocation):
        from copilot.generated.rpc import PermissionDecisionApproveOnce, PermissionDecisionReject
        detail = _dict(request)
        identity = _dict(_invocation)
        active = self.active
        if not active or identity.get('session_id', identity.get('sessionId')) != active['session'].session_id:
            return PermissionDecisionReject()
        # Deliberately ignore title-based global whitelists and auto-approve.
        answer = await self._decision('Copilot tool permission', detail, [
            {'optionId': 'allow', 'name': 'Allow once', 'kind': 'allow_once'},
            {'optionId': 'deny', 'name': 'Deny', 'kind': 'reject_once'}])
        # _decision publishes closure in its finally block, which can yield.
        # Cancellation or ownership can change during that final notification.
        return (PermissionDecisionApproveOnce(approved_interactively=True)
                if answer == 'allow' and self.active is active and not active['cancelled']
                else PermissionDecisionReject())

    async def _question(self, request, _invocation):
        identity = _dict(_invocation)
        if not self.active or identity.get('session_id', identity.get('sessionId')) != self.active['session'].session_id:
            raise PermissionError('Question does not belong to the active turn')
        owner = self.active
        detail = _dict(request)
        choices = detail.get('choices') or []
        if not isinstance(choices, list) or len(choices) > 20 or any(not isinstance(c, str) or len(c) > 8000 for c in choices):
            raise ValueError('Unsupported question choices')
        options = [{'optionId': f'choice-{i}', 'name': str(c), 'kind': 'allow_once'}
                   for i, c in enumerate(choices[:20])]
        if detail.get('allowFreeform', detail.get('allow_freeform', False)):
            options.append({'optionId': 'freeform'})
        options.append({'optionId': 'deny', 'name': 'Cancel', 'kind': 'reject_once'})
        answer = await self._decision(str(detail.get('question', 'Input requested')), {}, options)
        if self.active is not owner or owner['cancelled']:
            raise PermissionError('Question turn ended before response')
        if isinstance(answer, dict):
            return answer
        if not answer.startswith('choice-'):
            raise RuntimeError('Question cancelled or unsupported freeform input')
        return {'answer': str(choices[int(answer.split('-')[1])]), 'wasFreeform': False}

    def _owner(self, chat_id, sdk_id):
        owner = self.active
        if not owner or owner['chat_id'] != chat_id or owner['session'].session_id != sdk_id or owner['cancelled']:
            raise PermissionError('No matching active Copilot turn')
        return owner

    def _tools(self, chat_id):
        async def attach(invocation):
            from . import agent_attachments
            owner = self._owner(chat_id, invocation.session_id)
            args = dict(invocation.arguments or {})
            args['request_id'] = invocation.tool_call_id
            result = await agent_attachments.publish_file(args, BACKEND, chat_id, expected=owner['attachments'],
                owner_check=lambda: self._owner(chat_id, invocation.session_id) is owner)
            return self.sdk.ToolResult(text_result_for_llm=json.dumps(result))

        async def plan(invocation):
            from .db import get_db
            from .plans import PlanStore
            from .routes.sse import broadcast_event
            owner = self._owner(chat_id, invocation.session_id)
            def still_owned():
                if self._owner(chat_id, invocation.session_id) is not owner:
                    raise PermissionError('Plan turn changed')
            args = dict(invocation.arguments or {})
            if args.get('action') != 'read' and type(args.get('expected_revision')) is not int:
                raise ValueError('Read the plan and pass expected_revision before editing')
            result = await PlanStore(await get_db()).apply(chat_id, args,
                owner_check=still_owned)
            await broadcast_event('plan_updated', result)
            return self.sdk.ToolResult(text_result_for_llm=json.dumps(result))

        async def messages(invocation):
            owner = self._owner(chat_id, invocation.session_id)
            def still_owned():
                if self._owner(chat_id, invocation.session_id) is not owner:
                    raise PermissionError('Turn ownership changed')
            still_owned()
            from .db import get_db
            from .message_tools import MessageTools
            args = invocation.arguments
            allowed = {'action', 'row_ids', 'query', 'limit', 'before_row', 'after_row', 'context_before', 'context_after', 'media_id'}
            if not isinstance(args, dict) or set(args) - allowed or args.get('action') not in {'get', 'search', 'attachment'}:
                raise ValueError('Expected bounded read-only message query')
            result = await MessageTools((await get_db())._connection, session_id=chat_id).query(**args)
            still_owned()
            return self.sdk.ToolResult(text_result_for_llm=json.dumps(result))

        async def open_file(invocation):
            owner = self._owner(chat_id, invocation.session_id)
            def still_owned():
                if self._owner(chat_id, invocation.session_id) is not owner:
                    raise PermissionError('Turn ownership changed')
            still_owned()
            from .routes.workspace import _resolve_workspace_path, _to_workspace_relative, _file_views
            from .routes.sse import broadcast_event
            target = _resolve_workspace_path(invocation.arguments.get('path', ''))
            if not target.is_file():
                raise ValueError('Workspace file does not exist')
            result = await _file_views.request(chat_id, _to_workspace_relative(target), still_owned, broadcast_event)
            return self.sdk.ToolResult(text_result_for_llm=json.dumps(result), result_type='success' if result['status'] == 'opened' else 'failure')

        return [self.sdk.Tool(name='messages', handler=messages, description='Bounded read-only retrieval/search of current-chat messages and referenced attachments. IDs do not grant access to other chats.', parameters={'type': 'object', 'additionalProperties': False, 'required': ['action'], 'properties': {'action': {'type': 'string', 'enum': ['get', 'search', 'attachment']}, 'row_ids': {'type': 'array', 'maxItems': 50, 'items': {'type': 'integer', 'minimum': 1}}, 'query': {'type': 'string', 'maxLength': 500}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 50}, 'before_row': {'type': 'integer', 'minimum': 1}, 'after_row': {'type': 'integer', 'minimum': 1}, 'context_before': {'type': 'integer', 'minimum': 0, 'maximum': 20}, 'context_after': {'type': 'integer', 'minimum': 0, 'maximum': 20}, 'media_id': {'type': 'integer', 'minimum': 1}}}), self.sdk.Tool(name='open_file', handler=open_file, description='Request browser-acknowledged workspace text-file viewing.', parameters={'type': 'object', 'required': ['path'], 'additionalProperties': False, 'properties': {'path': {'type': 'string'}}}), self.sdk.Tool(name='vibes_attach_file', description='Attach a regular workspace file to the current conversation. No destination override.', handler=attach,
                    parameters={'type': 'object', 'properties': {'path': {'type': 'string'}, 'name': {'type': 'string'}, 'kind': {'type': 'string', 'enum': ['image', 'file']}}, 'required': ['path'], 'additionalProperties': False}),
                self.sdk.Tool(name='plan', description='Read/write the current conversation plan. Writes require expected_revision from a read.', handler=plan,
                    parameters={'type': 'object', 'properties': {'action': {'type': 'string', 'enum': ['read', 'write']}, 'markdown': {'type': 'string'}, 'expected_revision': {'type': 'integer'}}, 'required': ['action'], 'additionalProperties': False})]

    async def _session(self, chat_id, store):
        if chat_id in self.sessions:
            return self.sessions[chat_id]
        config = get_config()
        tools = self._tools(chat_id)
        options = dict(on_permission_request=self._permission, on_user_input_request=self._question,
                       enable_skills=bool(config.copilot_skill_directories),
                       mcp_servers=getattr(config, 'copilot_mcp_servers', {}),
                       tools=tools, available_tools=['custom:vibes_attach_file', 'custom:plan', 'custom:open_file', 'custom:messages', *config.copilot_available_tools],
                       working_directory=str(Path.cwd()), streaming=True,
                       include_sub_agent_streaming_events=False,
                       skill_directories=config.copilot_skill_directories,
                       system_message={'mode': 'append', 'content': 'You are running in Vibes. Use vibes_attach_file to deliver generated files and plan for the shared plan. Use messages for msg:ID references, ordered row ranges, earlier current-chat text and referenced attachments; preserve returned row/session/sender provenance. Missing IDs are not permission to access another chat, and truncated results are not complete history. Use open_file only to request browser-acknowledged viewing; unacknowledged is not opened. Do not invent successful tool results. ' + getattr(config, 'prompt', '')},
                       remote_session=self.sdk.RemoteSessionMode.OFF)
        binding = await store.backend_binding(chat_id, BACKEND)
        if not binding:
            preferred = self.model_state.get(chat_id, {})
            if preferred.get('model_id') or config.copilot_model:
                options['model'] = preferred.get('model_id') or config.copilot_model
            if preferred.get('thinking_level'):
                options['reasoning_effort'] = preferred['thinking_level']
        if binding:
            # Never replay an interrupted write automatically after a cold resume.
            session = await self.client.resume_session(binding['conversation_id'], continue_pending_work=False, **options)
        else:
            session = await self.client.create_session(session_id=str(uuid.uuid4()), **options)
            # The runtime does not journal a session until its first prompt.
            # Do not persist an unresumable empty session as a durable binding.
        self.sessions[chat_id] = session
        return session

    async def _ready_session(self, chat_id, store):
        await self.start()
        if self.closing:
            raise RuntimeError('Native host is shutting down')
        try:
            session = await asyncio.wait_for(self._session(chat_id, store), get_config().copilot_start_timeout)
        except BaseException as exc:
            # A timed-out create/resume may still complete inside the native host.
            # Never allow another creation after ambiguous setup from any API.
            self.poisoned = True
            self.error = 'Copilot session setup failed; restart Vibes before continuing'
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise RuntimeError(self.error) from None
        if self.closing:
            raise RuntimeError('Native host is shutting down')
        return session

    async def send(self, content, thread_id, callback, *, chat_id, store, media_ids=None, attachment_context=None):
        async with self.turn_lock:
            session = await self._ready_session(chat_id, store)
            from . import agent_attachments
            context = attachment_context if attachment_context is not None else agent_attachments.active
            if not context or context['session_id'] != chat_id or context['mode'] != BACKEND:
                raise RuntimeError('Missing turn ownership')
            owner = {'chat_id': chat_id, 'thread_id': thread_id, 'turn_id': context['turn_id'],
                     'session': session, 'cancelled': False, 'attachments': context}
            self.active = owner
            events = asyncio.Queue(maxsize=256)
            overflow = asyncio.Event()
            loop = asyncio.get_running_loop()

            def accept(event):
                if self.active is not owner:
                    return
                try:
                    events.put_nowait(event)
                except asyncio.QueueFull:
                    overflow.set()

            def receive(event):
                loop.call_soon_threadsafe(accept, event)

            unsubscribe = session.on(receive)
            draft, finals = '', []
            tool_names = {}
            from .copilot_media import ModelInputs, validate_media
            from .db import get_db
            inputs = None
            try:
                attachments = []
                if media_ids:
                    inputs = ModelInputs(await validate_media(await get_db(), media_ids, chat_id))
                    attachments = await inputs.prepare()
                # Persist identity immediately before admission: a lost send response
                # must not let a restart silently replace the conversation. Empty
                # sessions opened only for controls remain deliberately unbound.
                if owner['cancelled'] or self.closing:
                    raise RuntimeError('Turn cancelled before admission')
                await store.bind_backend(chat_id, BACKEND, session.session_id, model=configured_model(chat_id, self))
                if owner['cancelled'] or self.closing:
                    raise RuntimeError('Turn cancelled before admission')
                await asyncio.wait_for(session.send(content, **({'attachments': attachments} if attachments else {})),
                                       get_config().copilot_start_timeout)
                while True:
                    if overflow.is_set():
                        raise RuntimeError('Stream consumer overloaded; turn stopped without claiming completion')
                    event = await asyncio.wait_for(events.get(), get_config().copilot_event_timeout)
                    kind = getattr(event.type, 'value', event.type)
                    data = _dict(event.data)
                    if kind == 'assistant.usage':
                        usage = {}
                        for source, destination in [('inputTokens', 'input_tokens'), ('outputTokens', 'output_tokens'), ('cacheReadTokens', 'cache_read_tokens'), ('cacheWriteTokens', 'cache_write_tokens')]:
                            value = data.get(source, data.get(destination))
                            if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 10**12:
                                usage[destination] = value
                        await callback({'type': 'usage', 'usage': usage, 'context_occupancy': None, 'context_source': 'unavailable'})
                    elif kind == 'assistant.intent':
                        intent = data.get('intent')
                        if _safe_label(intent):
                            await callback({'type': 'thinking', 'title': intent})
                    elif kind == 'assistant.message_delta':
                        if not draft:
                            await callback({'type': 'writing', 'title': 'Writing response'})
                        delta = data.get('deltaContent', data.get('delta_content', ''))
                        delta_reset = not draft
                        draft += delta
                        if len(draft) > 2_000_000:
                            raise RuntimeError('Response exceeded display limit')
                        await callback({'type': 'message_chunk', **_draft_preview(draft),
                                        'delta': delta, 'delta_reset': delta_reset, 'kind': 'draft', 'mode': 'replace'})
                    elif kind == 'assistant.message':
                        if data.get('content'):
                            if not isinstance(data['content'], str) or sum(map(len, finals)) + len(data['content']) > 2_000_000:
                                raise RuntimeError('Response exceeded display limit')
                            finals.append(data['content'])
                    elif kind in {'tool.execution_start', 'tool.execution_complete'}:
                        call_id = data.get('toolCallId', data.get('tool_call_id'))
                        if kind.endswith('start'):
                            title = data.get('toolName', data.get('tool_name', 'Tool'))
                            title = title if _safe_label(title) else 'Tool'
                            if isinstance(call_id, str):
                                if len(tool_names) >= 256:
                                    raise RuntimeError('Too many in-flight tools')
                                tool_names[call_id] = title
                            await callback({'type': 'tool_call', 'tool_call_id': call_id, 'title': title, 'status': 'running'})
                        else:
                            title = tool_names.pop(call_id, 'Tool') if isinstance(call_id, str) else 'Tool'
                            outcome = 'completed' if data.get('success') is True else 'failed' if data.get('success') is False else 'ended'
                            await callback({'type': 'tool_status', 'tool_call_id': call_id, 'title': title, 'status': outcome})
                    elif kind in {'tool.execution_partial_result', 'tool.execution_progress'}:
                        call_id = data.get('toolCallId', data.get('tool_call_id', ''))
                        output = data.get('partialOutput', data.get('partial_output')) if kind == 'tool.execution_partial_result' else data.get('progressMessage', data.get('progress_message'))
                        if isinstance(output, str):
                            await callback({'type': 'tool_output', 'tool_call_id': call_id, 'title': tool_names.get(call_id, 'Tool'), 'content': output[:16000], 'content_truncated': len(output) > 16000, 'progress': kind == 'tool.execution_progress'})
                    elif kind == 'session.error':
                        raise RuntimeError('Copilot reported a session error; inspect private diagnostics')
                    elif kind == 'session.idle':
                        from copilot.generated.rpc import SessionsSaveRequest
                        await self.client.rpc.sessions.save(SessionsSaveRequest(session_id=session.session_id), timeout=5)
                        break
                text = '\n\n'.join(finals) or draft
                if not text and not owner['cancelled']:
                    text = 'Turn ended without a text response. Check tool results and denied requests before continuing.'
                return {'text': text, 'content': [{'type': 'text', 'text': text}] if text else [],
                        'cancelled': owner['cancelled'], 'cancel_reason': 'abort' if owner['cancelled'] else None}
            except BaseException:
                owner['cancelled'] = True
                context['cancelled'] = True
                # An abort acknowledgement is not proof of quiescence. Refuse further
                # turns after an uncertain ending rather than accept late events/tools.
                self.poisoned = True
                self.error = 'Previous turn ended without confirmed idle; restart Vibes before continuing'
                try:
                    await asyncio.wait_for(session.abort(), 5)
                except Exception:
                    pass
                raise
            finally:
                unsubscribe()
                self._deny_pending()
                self.active = None
                if inputs:
                    inputs.close()

    async def compact(self, chat_id, store):
        """Native idle-session compaction; never substitute session reset/replay."""
        if self.turn_lock.locked():
            raise RuntimeError('Wait for the active turn before compacting')
        async with self.turn_lock:
            session = await self._session(chat_id, store)
            result = await session.rpc.history.compact(timeout=120)
            return {'success': result.success is True, 'messages_removed': result.messages_removed,
                    'tokens_removed': result.tokens_removed, 'context_window': result.context_window.to_dict() if result.context_window else None}

    async def command_catalogue(self, chat_id, store):
        """Native discovery only; this does not imply bridge execution support."""
        from copilot.generated.rpc import SessionCommandsListRequest
        session = await self._session(chat_id, store)
        try:
            listing = await session.rpc.commands.list(SessionCommandsListRequest(include_builtins=True, include_client_commands=False, include_skills=True), timeout=10)
            skills = await session.rpc.skills.list(timeout=10)
        except Exception:
            return {'available': False, 'commands': [], 'skills': []}
        return {'available': True, 'commands': [item.to_dict() for item in listing.commands],
                'skills': [item.to_dict() for item in skills.skills]}

    async def models(self, chat_id, store):
        if self.turn_lock.locked():
            return {'available': False, 'models': [], 'thinking_levels': [], 'busy': True}
        async with self.turn_lock:
            session = await self._ready_session(chat_id, store)
            rows = _dict(await session.rpc.model.list(timeout=10)).get('list', [])
            current = _dict(await session.rpc.model.get_current(timeout=10)).get('modelId')
            models = _model_rows(rows)
            levels = next((m['efforts'] for m in models if m['id'] == current), [])
            return {'available': True, 'models': [{k: v for k, v in m.items() if k != 'efforts'} for m in models],
                    'thinking_levels': levels}

    async def model(self, chat_id, store, changes=None):
        if self.turn_lock.locked():
            raise RuntimeError('Wait for the active turn before changing models')
        async with self.turn_lock:
            session = await self._ready_session(chat_id, store)
            if changes:
                if set(changes) - {'provider', 'model_id', 'thinking_level'} or changes.get('provider', 'copilot') != 'copilot':
                    raise ValueError('Invalid Copilot model fields')
                if not (changes.get('model_id') or changes.get('thinking_level')):
                    raise ValueError('Expected a model or reasoning change')
                if any(not isinstance(v, str) or not v.strip() or len(v) > 512 or any(ord(c) < 32 for c in v) for v in changes.values()):
                    raise ValueError('Invalid Copilot model value')
                from copilot.generated.rpc import ModelSwitchToRequest, ModelSetReasoningEffortRequest
                if changes.get('thinking_level'):
                    target = changes.get('model_id') or _dict(await session.rpc.model.get_current(timeout=10)).get('modelId')
                    catalog = _dict(await session.rpc.model.list(timeout=10)).get('list', [])
                    supported = next((row['efforts'] for row in _model_rows(catalog) if row['id'] == target), [])
                    if changes['thinking_level'] not in supported:
                        raise ValueError('Reasoning level is not advertised by this model')
                if changes.get('model_id'):
                    await session.rpc.model.switch_to(ModelSwitchToRequest(model_id=changes['model_id'],
                        reasoning_effort=changes.get('thinking_level'), require_available=True), timeout=10)
                elif changes.get('thinking_level'):
                    await session.rpc.model.set_reasoning_effort(ModelSetReasoningEffortRequest(reasoning_effort=changes['thinking_level']), timeout=10)
            state = _dict(await session.rpc.model.get_current(timeout=10))
            identity, effort = state.get('modelId'), state.get('reasoningEffort')
            identity = identity if _safe_label(identity) else None
            effort = effort if _safe_label(effort) else None
            if changes and (changes.get('model_id', identity) != identity or changes.get('thinking_level', effort) != effort):
                raise RuntimeError('Model change was not confirmed')
            self.model_state[chat_id] = {'model_id': identity, 'thinking_level': effort}
            if changes and await store.backend_binding(chat_id, BACKEND):
                from copilot.generated.rpc import SessionsSaveRequest
                await self.client.rpc.sessions.save(SessionsSaveRequest(session_id=session.session_id), timeout=5)
                await store.bind_backend(chat_id, BACKEND, session.session_id, model=identity, thinking_level=effort)
            return {'session_id': chat_id, 'available': bool(identity), 'model': {'provider':'copilot','id':identity,'reasoning':bool(effort)} if identity else None,
                    'thinking_level': effort, 'compacting': None}

    async def abort(self, chat_id, expected):
        owner = self.active
        if owner is None or expected is not owner or owner['chat_id'] != chat_id:
            return False
        owner['cancelled'] = True
        if owner.get('attachments'):
            owner['attachments']['cancelled'] = True
        self._deny_pending()
        await asyncio.wait_for(owner['session'].abort(), 5)
        return True


def configured_model(chat_id, backend):
    return backend.model_state.get(chat_id, {}).get('model_id') or get_config().copilot_model
