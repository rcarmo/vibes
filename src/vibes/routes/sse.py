"""Server-Sent Events route handler."""

import asyncio
import json
from typing import Any
from aiohttp import web
from aiohttp.client_exceptions import ClientConnectionResetError

from ..acp_client import stop_agent, start_agent
from ..config import get_config

# Connected SSE clients
_clients: set[asyncio.Queue] = set()
_restart_task: asyncio.Task | None = None


async def broadcast_event(event_type: str, data: Any) -> None:
    """Broadcast an event to all connected SSE clients."""
    message = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    disconnected = set()
    
    for queue in _clients:
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            disconnected.add(queue)
    
    # Clean up disconnected clients
    _clients.difference_update(disconnected)


async def _restart_agent_after_disconnect(delay_s: int) -> None:
    try:
        await asyncio.sleep(delay_s)
        if _clients:
            return
        await stop_agent()
        await start_agent()
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

    delay_s = get_config().disconnect_timeout
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
