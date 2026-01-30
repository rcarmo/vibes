"""Server-Sent Events route handler."""

import asyncio
import json
from typing import Any
from aiohttp import web

# Connected SSE clients
_clients: set[asyncio.Queue] = set()


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
    finally:
        _clients.discard(queue)
    
    return response


def setup_routes(app: web.Application) -> None:
    """Set up SSE routes."""
    app.router.add_get("/sse/stream", sse_stream)
