"""Post and reply route handlers."""

import json
from aiohttp import web
from ..db import get_db
from .sse import broadcast_event


async def create_post(request: web.Request) -> web.Response:
    """Create a new post (text, link, image, file)."""
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    if "content" not in data:
        return web.json_response({"error": "Missing 'content' field"}, status=400)

    post_data = {
        "type": "post",
        "content": data["content"],
        "media_ids": data.get("media_ids", []),
    }

    db = await get_db()
    post_id = await db.create_interaction(post_data)
    
    # Fetch the created post to return
    post = await db.get_interaction(post_id)
    
    # Broadcast to SSE clients
    await broadcast_event("new_post", post)
    
    return web.json_response(post, status=201)


async def create_reply(request: web.Request) -> web.Response:
    """Reply to an existing thread."""
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    if "content" not in data:
        return web.json_response({"error": "Missing 'content' field"}, status=400)
    if "thread_id" not in data:
        return web.json_response({"error": "Missing 'thread_id' field"}, status=400)

    db = await get_db()
    
    # Verify thread exists
    thread = await db.get_interaction(data["thread_id"])
    if not thread:
        return web.json_response({"error": "Thread not found"}, status=404)

    reply_data = {
        "type": "reply",
        "content": data["content"],
        "thread_id": data["thread_id"],
        "media_ids": data.get("media_ids", []),
    }

    reply_id = await db.create_interaction(reply_data)
    reply = await db.get_interaction(reply_id)
    
    # Broadcast to SSE clients
    await broadcast_event("new_reply", reply)
    
    return web.json_response(reply, status=201)


async def get_thread(request: web.Request) -> web.Response:
    """Get all interactions in a thread."""
    thread_id = int(request.match_info["thread_id"])
    
    db = await get_db()
    thread = await db.get_thread(thread_id)
    
    if not thread:
        return web.json_response({"error": "Thread not found"}, status=404)
    
    return web.json_response({"thread": thread})


async def get_timeline(request: web.Request) -> web.Response:
    """Get paginated timeline of posts."""
    limit = int(request.query.get("limit", 50))
    offset = int(request.query.get("offset", 0))
    
    # Clamp limit
    limit = max(1, min(100, limit))
    
    db = await get_db()
    posts = await db.get_timeline(limit=limit, offset=offset)
    
    return web.json_response({
        "posts": posts,
        "limit": limit,
        "offset": offset
    })


def setup_routes(app: web.Application) -> None:
    """Set up post routes."""
    app.router.add_post("/post", create_post)
    app.router.add_post("/reply", create_reply)
    app.router.add_get("/thread/{thread_id}", get_thread)
    app.router.add_get("/timeline", get_timeline)
