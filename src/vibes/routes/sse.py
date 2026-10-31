"""Server-Sent Events route handler."""

import asyncio
import json
from typing import Any
from aiohttp import web
from aiohttp.client_exceptions import ClientConnectionResetError

from ..acp_client import stop_agent as stop_acp_agent, start_agent as start_acp_agent
from ..pi_client import stop_pi_agent, start_pi_agent
from ..config import get_config
from ..db import get_db


async def stop_agent() -> None:
    """Backward-compatible alias for ACP stop."""
    await stop_acp_agent()


async def start_agent() -> None:
    """Backward-compatible alias for ACP start."""
    await start_acp_agent()

# Connected SSE clients
_clients: set[asyncio.Queue] = set()
_workspace_client_ids: dict[asyncio.Queue, str] = {}
_session_clients: dict[asyncio.Queue, str] = {}
_classic_clients: set[asyncio.Queue] = set()
_GLOBAL_EVENTS = {'workspace_update', 'ui_theme', 'sessions_changed', 'server_restart'}


def _requested_session(query):
    session_id, chat_jid = query.get('session_id'), query.get('chat_jid')
    if chat_jid is not None:
        if not chat_jid.startswith('gi:') or not chat_jid[3:]:
            raise ValueError('Expected chat_jid=gi:<session-id>')
        if session_id is not None and session_id != chat_jid[3:]:
            raise ValueError('Conflicting session selectors')
        session_id = chat_jid[3:]
    if session_id is not None and (not isinstance(session_id, str) or not session_id):
        raise ValueError('Invalid session selector')
    return session_id


async def _event_session(event_type, data):
    """Resolve persisted conversation ownership; ambiguous events fail closed."""
    if not isinstance(data, dict):
        return None
    payload = data.get('data') if isinstance(data.get('data'), dict) else data
    claimed = payload.get('session_id', data.get('session_id'))
    thread_id = payload.get('thread_id', data.get('thread_id'))
    message_id = data.get('id') if event_type in {'new_post', 'new_reply', 'agent_response'} else None
    items = data.get('items')
    if isinstance(items, list):
        owners = [await _event_session('agent_followup_queued', item) for item in items]
        return owners[0] if owners and None not in owners and len(set(owners)) == 1 else None
    try:
        db = await get_db()
        persisted_id = thread_id if type(thread_id) is int else message_id
        if type(persisted_id) is int:
            row = await db.get_interaction(persisted_id)
            if not row:
                return None
            owner = row['data'].get('session_id', 'default')
            return owner if claimed is None or claimed == owner else None
        if event_type in {'plan_updated', 'session_model_changed', 'model_changed'} and isinstance(claimed, str):
            from ..sessions import SessionStore
            return claimed if await SessionStore(db).get(claimed) else None
    except (RuntimeError, ValueError, TypeError):
        return None
    return None


def _without_hidden_nodes(value):
    if isinstance(value, list):
        return [_without_hidden_nodes(item) for item in value
                if not isinstance(item, dict) or (
                    (not str(item.get('name', '')).startswith('.') or item.get('name') == '.')
                    and not any(part.startswith('.') and part not in {'.', '..'} for part in str(item.get('path', '')).split('/')))]
    if isinstance(value, dict):
        return {key: _without_hidden_nodes(item) for key, item in value.items()}
    return value
_restart_task: asyncio.Task | None = None
_LOSSY_EVENT_TYPES = {"agent_status", "agent_draft", "agent_draft_delta", "agent_thought", "agent_thought_delta"}


async def broadcast_event(event_type: str, data: Any) -> None:
    """Deliver scoped conversations; preserve the legacy unscoped feed."""
    event_session = None
    if event_type not in _GLOBAL_EVENTS and any(q in _session_clients for q in _clients):
        event_session = await _event_session(event_type, data)
    classic_data = await _classic_event(event_type, data, event_session) if event_session is not None and _classic_clients else None
    _broadcast_resolved(event_type, data, event_session, classic_data)


async def _classic_event(event_type, data, session_id):
    if not isinstance(data, dict):
        return data
    result = {**data, 'chat_jid': 'gi:' + session_id, 'session_id': session_id}
    if event_type in {'new_post', 'new_reply', 'agent_response'} and isinstance(data.get('data'), dict):
        from .classic_messages import project
        database = await get_db()
        persisted = await database.get_interaction(data['id'])
        if not persisted or persisted['data'].get('session_id', 'default') != session_id:
            return None
        message = await project(database, {'id': persisted['id'], 'timestamp': persisted['timestamp'],
                                           'data': json.dumps(persisted['data'])})
        from .classic_messages import visible_sql
        # Both canonical and compatible post envelopes are consumed by shared
        # client variants. Never let a hidden record bypass conversation filters.
        async with database._connection.execute('SELECT 1 FROM interactions WHERE id=? AND ' + visible_sql(),
                                                  (data['id'],)) as cursor:
            if not await cursor.fetchone():
                return None
        legacy_data = {'type': 'agent_response' if message['role'] in {'assistant', 'system'} else 'user_message',
                       'content': message['content'], 'session_id': session_id,
                       'chat_jid': 'gi:' + session_id, **message['payload']}
        legacy_data['media_ids'] = [item['media_id'] for item in message['payload'].get('media', [])]
        if message['reply_to_id'] is not None:
            legacy_data['thread_id'] = message['reply_to_id']
        result = {**message, 'chat_jid': 'gi:' + session_id, 'timestamp': message['created_at'],
                  'data': legacy_data}
    elif event_type == 'agent_status':
        # Legacy type/title events lack Classic lifecycle status. Preserve type
        # detail while binding all UI control identity to the scoped envelope.
        kind = data.get('type')
        result['status'] = 'idle' if kind in {'done', 'error'} else 'cancelling' if kind == 'cancelled' else 'running'
    elif event_type in {'agent_draft', 'agent_thought'}:
        field = 'draft' if event_type == 'agent_draft' else 'thought'
        from . import agents
        preview = agents._turn_previews.get(data.get('turn_id'), {})
        # Classic consumes full snapshots; legacy draft events may be append
        # chunks. Use the already accumulated owner-bound preview when present.
        if preview.get('thread_id') != data.get('thread_id'):
            preview = {}
        text = preview.get(field, data.get('text', ''))
        result[field] = text if isinstance(text, str) else ''
    return result


async def broadcast_session_event(event_type: str, data: Any, session_id: str) -> None:
    """Publish after a mutation whose transaction already verified ownership.

    Callers must derive session_id from persisted rows, never a request claim.
    This supports deletion events after their source rows no longer exist.
    """
    classic_data = await _classic_event(event_type, data, session_id) if _classic_clients else None
    _broadcast_resolved(event_type, data, session_id, classic_data)


def _broadcast_resolved(event_type, data, event_session, classic_data=None):
    common_message = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    global_classic_messages = {}
    classic_message = f"event: {event_type}\ndata: {json.dumps(classic_data)}\n\n" if classic_data is not None else None
    lossy = event_type in _LOSSY_EVENT_TYPES
    for queue in list(_clients):
        session_id = _session_clients.get(queue)
        if session_id is not None and event_type not in _GLOBAL_EVENTS and event_session != session_id:
            continue
        message = common_message
        if queue in _classic_clients:
            if event_type in _GLOBAL_EVENTS and isinstance(data, dict):
                if session_id not in global_classic_messages:
                    envelope = {**data, 'chat_jid': 'gi:' + session_id, 'session_id': session_id}
                    global_classic_messages[session_id] = f"event: {event_type}\ndata: {json.dumps(envelope)}\n\n"
                message = global_classic_messages[session_id]
            elif classic_message is not None:
                message = classic_message
            elif event_type not in _GLOBAL_EVENTS:
                continue
        if event_type == 'workspace_update' and queue in _workspace_client_ids:
            from .workspace import _workspace_subscriptions
            if not _workspace_subscriptions.get(_workspace_client_ids[queue], False):
                message = f"event: {event_type}\ndata: {json.dumps(_without_hidden_nodes(data))}\n\n"
        if lossy and queue.qsize() >= queue.maxsize:
            # Drop low-priority stream noise first; keep critical timeline events.
            continue

        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            if lossy:
                continue

            # For critical events, evict stale queued entries until we can enqueue.
            enqueued = False
            for _ in range(max(queue.maxsize, 1)):
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                try:
                    queue.put_nowait(message)
                    enqueued = True
                    break
                except asyncio.QueueFull:
                    continue

            if not enqueued:
                # Last attempt: keep subscription alive even if this event is dropped.
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    pass


async def _restart_agent_after_disconnect(delay_s: int) -> None:
    try:
        await asyncio.sleep(delay_s)
        if _clients:
            return
        config = get_config()
        if config.pi_enabled:
            if config.pi_restart_on_disconnect:
                await stop_pi_agent()
                await start_pi_agent()
        else:
            await stop_acp_agent()
            await start_acp_agent()
    except asyncio.CancelledError:
        raise


def _schedule_restart_if_needed() -> None:
    global _restart_task
    if _clients:
        if _restart_task and not _restart_task.done():
            _restart_task.cancel()
        _restart_task = None
        return

    if _restart_task and not _restart_task.done():
        return

    config = get_config()
    if config.default_agent.lower() == 'copilot-ffi':
        # A browser subscription is not the owner of the native runtime.
        return
    delay_s = getattr(config, "disconnect_timeout", None)
    if delay_s is None:
        delay_s = getattr(config, "agent_restart_on_disconnect_s", 0)
    if delay_s <= 0:
        return

    _restart_task = asyncio.create_task(_restart_agent_after_disconnect(delay_s))


async def sse_stream(request: web.Request) -> web.StreamResponse:
    """SSE endpoint with optional explicit conversation isolation."""
    try:
        session_id = _requested_session(request.query)
    except ValueError as exc:
        return web.json_response({'error': str(exc)}, status=400)
    if session_id is not None:
        from ..sessions import SessionStore
        if not await SessionStore(await get_db()).get(session_id):
            return web.json_response({'error': 'Session not found'}, status=404)
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )
    await response.prepare(request)
    
    # Create client queue
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _clients.add(queue)
    if session_id is not None:
        _session_clients[queue] = session_id
        if request.query.get('chat_jid') is not None:
            _classic_clients.add(queue)
    if request.query.get('workspace_subscription'):
        _workspace_client_ids[queue] = request.query['workspace_subscription']
    _schedule_restart_if_needed()
    
    try:
        # Send initial connection event
        connected = {'chat_jid': 'gi:' + session_id, 'session_id': session_id} if queue in _classic_clients else {}
        await response.write(f"event: connected\ndata: {json.dumps(connected)}\n\n".encode())
        
        # Heartbeat and message loop
        while True:
            try:
                # Wait for message with timeout for heartbeat
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
                await response.write(message.encode())
            except asyncio.TimeoutError:
                # Send heartbeat
                await response.write(b": heartbeat\n\n")
            except asyncio.CancelledError:
                break
    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, ClientConnectionResetError):
        # Client disconnected, this is normal for SSE
        pass
    finally:
        _clients.discard(queue)
        _session_clients.pop(queue, None)
        _classic_clients.discard(queue)
        _workspace_client_ids.pop(queue, None)
        subscription = request.query.get('workspace_subscription')
        if subscription and subscription not in _workspace_client_ids.values():
            from .workspace import release_workspace_subscription
            await release_workspace_subscription(subscription)
        _schedule_restart_if_needed()
    
    return response


def setup_routes(app: web.Application) -> None:
    """Set up SSE routes."""
    app.router.add_get("/sse/stream", sse_stream)
