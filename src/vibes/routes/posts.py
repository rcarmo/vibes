"""Post and reply route handlers."""

import json
from aiohttp import web
from ..db import get_db
from ..opengraph import queue_link_preview_fetch
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
    
    # Queue background task to fetch link previews
    queue_link_preview_fetch(post_id, data["content"])
    
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
    
    # Queue background task to fetch link previews
    queue_link_preview_fetch(reply_id, data["content"])
    
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
    """Get paginated timeline of posts (chat style - oldest first, load older with before_id)."""
    limit = int(request.query.get("limit", 10))
    before_id = request.query.get("before")
    
    # Clamp limit
    limit = max(1, min(100, limit))
    
    if before_id:
        before_id = int(before_id)
    
    db = await get_db()
    session_id = request.query.get('session_id')
    if session_id is not None:
        from ..sessions import SessionStore
        try:
            result = await SessionStore(db).timeline(session_id, limit=limit, before_id=before_id)
        except ValueError as exc:
            return web.json_response({'error': str(exc)}, status=400)
        return web.json_response({**result, 'limit': limit})
    posts = await db.get_timeline(limit=limit, before_id=before_id)
    
    # Check if there are older posts
    has_more = len(posts) == limit and posts[0]["id"] > 1
    
    return web.json_response({
        "posts": posts,
        "limit": limit,
        "has_more": has_more
    })


async def get_hashtag(request: web.Request) -> web.Response:
    """Get posts containing a specific hashtag."""
    hashtag = request.match_info["hashtag"]
    limit = int(request.query.get("limit", 50))
    offset = int(request.query.get("offset", 0))
    
    # Clamp limit
    limit = max(1, min(100, limit))
    
    db = await get_db()
    posts = await db.get_posts_by_hashtag(hashtag, limit=limit, offset=offset)
    
    return web.json_response({
        "hashtag": hashtag,
        "posts": posts,
        "limit": limit,
        "offset": offset
    })


async def search(request: web.Request) -> web.Response:
    """Full-text search across posts and replies."""
    query = request.query.get("q", "").strip()
    if not query:
        return web.json_response({"error": "Missing 'q' parameter"}, status=400)
    
    limit = int(request.query.get("limit", 50))
    offset = int(request.query.get("offset", 0))
    
    # Clamp limit
    limit = max(1, min(100, limit))
    
    db = await get_db()
    try:
        thread_id = int(request.query['thread_id']) if 'thread_id' in request.query else None
        if thread_id is not None and thread_id < 1:
            raise ValueError()
        if any(request.query.get(key, 'false') not in {'true', 'false'} for key in ('has_images', 'has_attachments')):
            raise ValueError()
    except ValueError:
        return web.json_response({'error': 'Invalid search filters'}, status=400)
    filters = {}
    session_id = request.query.get('session_id')
    if session_id is not None:
        from ..sessions import SessionStore
        if not await SessionStore(db).get(session_id):
            return web.json_response({'error': 'Session not found'}, status=404)
        if request.query.get('scope') == 'root':
            try:
                filters['session_ids'] = await SessionStore(db).family_ids(session_id)
            except ValueError as exc:
                return web.json_response({'error': str(exc)}, status=400)
        else:
            filters['session_id'] = session_id
    if thread_id is not None:
        filters['thread_id'] = thread_id
    for key in ('has_images', 'has_attachments'):
        if request.query.get(key) == 'true':
            filters[key] = True
    results = await db.search(query, limit=limit, offset=offset, **filters)
    
    return web.json_response({
        "query": query,
        "results": results,
        "limit": limit,
        "offset": offset
    })

async def delete_post(request: web.Request) -> web.Response:
    """Delete an interaction, optionally cascading replies."""
    post_id = int(request.match_info["post_id"])
    cascade = request.query.get("cascade", "false").lower() == "true"
    
    db = await get_db()
    post = await db.get_interaction(post_id)
    if not post:
        return web.json_response({"error": "Post not found"}, status=404)

    root_id = post["data"].get("thread_id") or post_id
    reply_ids = await db.get_reply_ids(root_id)
    if reply_ids and not cascade:
        return web.json_response({"error": "Replies exist", "reply_count": len(reply_ids)}, status=409)

    delete_ids = [root_id]
    if cascade and reply_ids:
        delete_ids.extend(reply_ids)
    
    media_ids = await db.get_media_ids_for_interactions(delete_ids)
    deleted = await db.delete_interactions(delete_ids)

    if media_ids:
        refs = await db.get_media_reference_counts(media_ids)
        to_delete = [mid for mid in media_ids if refs.get(mid, 0) == 0]
        if to_delete:
            await db.delete_media(to_delete)

    await broadcast_event("interaction_deleted", {"ids": delete_ids})
    
    return web.json_response({"deleted": deleted, "ids": delete_ids})


def setup_routes(app: web.Application) -> None:
    """Set up post routes."""
    app.router.add_post("/post", create_post)
    app.router.add_post("/reply", create_reply)
    app.router.add_get("/thread/{thread_id}", get_thread)
    app.router.add_get("/timeline", get_timeline)
    app.router.add_get("/hashtag/{hashtag}", get_hashtag)
    app.router.add_get("/search", search)
    app.router.add_delete("/post/{post_id}", delete_post)
