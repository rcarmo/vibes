"""Server-Sent Events route handler."""

import asyncio
import json
from typing import Any
from aiohttp import web
from aiohttp.client_exceptions import ClientConnectionResetError

from ..acp_client import stop_agent as stop_acp_agent, start_agent as start_acp_agent
from ..pi_client import stop_pi_agent, start_pi_agent
from ..config import get_config


async def stop_agent() -> None:
    """Backward-compatible alias for ACP stop."""
    await stop_acp_agent()


async def start_agent() -> None:
    """Backward-compatible alias for ACP start."""
    await start_acp_agent()

# Connected SSE clients
_clients: set[asyncio.Queue] = set()
_restart_task: asyncio.Task | None = None
_LOSSY_EVENT_TYPES = {"agent_status", "agent_draft", "agent_draft_delta", "agent_thought"}


async def broadcast_event(event_type: str, data: Any) -> None:
    """Broadcast an event to all connected SSE clients."""
    message = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    lossy = event_type in _LOSSY_EVENT_TYPES
    for queue in _clients:
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
    delay_s = getattr(config, "disconnect_timeout", None)
    if delay_s is None:
        delay_s = getattr(config, "agent_restart_on_disconnect_s", 0)
    if delay_s <= 0:
        return

    _restart_task = asyncio.create_task(_restart_agent_after_disconnect(delay_s))


async def sse_stream(request: web.Request) -> web.StreamResponse:
    """SSE endpoint for live updates."""
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
    _schedule_restart_if_needed()
    
    try:
        # Send initial connection event
        await response.write(b"event: connected\ndata: {}\n\n")
        
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
        _schedule_restart_if_needed()
    
    return response


def setup_routes(app: web.Application) -> None:
    """Set up SSE routes."""
    app.router.add_get("/sse/stream", sse_stream)
