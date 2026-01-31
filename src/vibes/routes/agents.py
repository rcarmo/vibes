"""ACP agent route handlers."""

import base64
import json
import logging
from aiohttp import web
from ..db import get_db
from ..config import get_config
from ..opengraph import queue_link_preview_fetch
from ..acp_client import (
    send_message_multimodal, is_agent_running,
    set_request_callback, set_whitelist_checker, respond_to_request,
    prompt_from_action
)
from ..tasks import enqueue
from .sse import broadcast_event

logger = logging.getLogger(__name__)


# Set up callback for agent requests
async def _handle_agent_request(request_data):
    """Broadcast agent requests to UI."""
    await broadcast_event("agent_request", request_data)

set_request_callback(_handle_agent_request)


# Set up whitelist checker
async def _check_whitelist(title: str) -> bool:
    """Check if a tool call title is whitelisted."""
    db = await get_db()
    return await db.is_whitelisted(title)

set_whitelist_checker(_check_whitelist)


async def list_agents(request: web.Request) -> web.Response:
    """List available agents and their capabilities."""
    config = get_config()
    return web.json_response({
        "agents": [
            {
                "id": "default",
                "name": config.agent_name,
                "description": f"ACP agent ({config.acp_agent})",
                "status": "running" if is_agent_running() else "stopped",
                "actions": []
            }
        ]
    })


async def process_agent_response(thread_id: int, content: str, agent_id: str):
    """Background task to get agent response and broadcast it."""
    try:
        # Status callback to broadcast agent activity
        async def status_callback(status):
            if status.get("type") == "message_chunk":
                await broadcast_event("agent_draft", {
                    "thread_id": thread_id,
                    "agent_id": agent_id,
                    "text": status.get("text", ""),
                    "kind": status.get("kind", "draft")
                })
                return
            await broadcast_event("agent_status", {
                "thread_id": thread_id,
                "agent_id": agent_id,
                **status
            })
        
        # Broadcast that agent is thinking
        await broadcast_event("agent_status", {
            "thread_id": thread_id,
            "agent_id": agent_id,
            "type": "thinking",
            "title": "Thinking..."
        })
        
        # Get multimodal response from ACP agent
        response = await send_message_multimodal(content, thread_id, status_callback)
        
        # Process content blocks - store images/files in media table
        db = await get_db()
        media_ids = []
        text_content = response.get("text", "")
        
        for block in response.get("content", []):
            block_type = block.get("type")
            
            if block_type == "image":
                # Store image in media table
                media_id = await _store_media_block(db, block)
                if media_id:
                    media_ids.append(media_id)
                    
            elif block_type == "file":
                # Store file in media table
                media_id = await _store_media_block(db, block)
                if media_id:
                    media_ids.append(media_id)
        
        # Store agent response
        agent_response = {
            "type": "agent_response",
            "content": text_content,
            "content_blocks": response.get("content", []),
            "agent_id": agent_id,
            "thread_id": thread_id,
            "media_ids": media_ids,
        }
        
        response_id = await db.create_interaction(agent_response)
        response_interaction = await db.get_interaction(response_id)
        
        # Don't fetch link previews for agent responses - they often contain
        # code snippets, documentation URLs, etc. that don't need previews
        
        # Broadcast agent response
        await broadcast_event("agent_response", response_interaction)

        # Broadcast that agent is done (after response is available)
        await broadcast_event("agent_status", {
            "thread_id": thread_id,
            "agent_id": agent_id,
            "type": "done"
        })
        
        logger.info(f"Agent response posted for thread {thread_id} with {len(media_ids)} media items")
        
    except Exception as e:
        logger.error(f"Error processing agent response: {e}", exc_info=True)
        
        # Broadcast error status
        await broadcast_event("agent_status", {
            "thread_id": thread_id,
            "agent_id": agent_id,
            "type": "error",
            "title": str(e)
        })
        
        # Post error message
        db = await get_db()
        error_response = {
            "type": "agent_response",
            "content": f"[Error: {e}]",
            "agent_id": agent_id,
            "thread_id": thread_id,
        }
        response_id = await db.create_interaction(error_response)
        response_interaction = await db.get_interaction(response_id)
        await broadcast_event("agent_response", response_interaction)


async def _store_media_block(db, block: dict) -> int | None:
    """Store an image or file block in the media table, return media_id."""
    try:
        block_type = block.get("type")
        mime_type = block.get("mime_type", "application/octet-stream")
        name = block.get("name", f"agent_{block_type}")
        
        # Get the data
        data = None
        if "data" in block:
            encoding = block.get("encoding", "base64")
            if encoding == "base64":
                data = base64.b64decode(block["data"])
            else:
                data = block["data"].encode() if isinstance(block["data"], str) else block["data"]
        elif "url" in block:
            from ..opengraph import download_and_cache_image
            logger.info(f"Media block has URL: {block['url']}")
            if mime_type.startswith("image/"):
                return await download_and_cache_image(block["url"])
            return None
        
        if not data:
            return None
        
        # Generate thumbnail for images
        thumbnail = None
        if mime_type.startswith("image/"):
            from .media import generate_thumbnail
            thumbnail = generate_thumbnail(data, mime_type)
        
        # Store in database
        media_id = await db.create_media(
            filename=name,
            content_type=mime_type,
            data=data,
            thumbnail=thumbnail,
            metadata={"source": "agent", "original_type": block_type}
        )
        
        logger.info(f"Stored agent media: {name} ({mime_type}) as media_id={media_id}")
        return media_id
        
    except Exception as e:
        logger.error(f"Failed to store media block: {e}", exc_info=True)
        return None


async def send_message(request: web.Request) -> web.Response:
    """Send a message to an agent."""
    agent_id = request.match_info["agent_id"]
    
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    if "content" not in data:
        return web.json_response({"error": "Missing 'content' field"}, status=400)

    thread_id = data.get("thread_id")
    
    # Store user message as interaction
    db = await get_db()
    user_msg = {
        "type": "user_message",
        "content": data["content"],
        "agent_id": agent_id,
        "media_ids": data.get("media_ids", []),
    }
    if thread_id:
        user_msg["thread_id"] = thread_id
    
    msg_id = await db.create_interaction(user_msg)
    user_interaction = await db.get_interaction(msg_id)
    
    # Queue background task to fetch link previews
    queue_link_preview_fetch(msg_id, data["content"])
    
    # Use the message ID as thread_id if this is a new thread
    if not thread_id:
        thread_id = msg_id
    
    # Broadcast user message
    await broadcast_event("new_post" if not data.get("thread_id") else "new_reply", user_interaction)
    
    # Queue agent response processing in background
    enqueue(process_agent_response, thread_id, data["content"], agent_id)
    
    return web.json_response({
        "user_message": user_interaction,
        "thread_id": thread_id
    }, status=201)


async def trigger_action(request: web.Request) -> web.Response:
    """Trigger a predefined agent action."""
    agent_id = request.match_info["agent_id"]
    action_id = request.match_info["action_id"]
    
    try:
        data = await request.json()
    except json.JSONDecodeError:
        data = {}

    prompt = prompt_from_action(action_id, data.get("params"))
    if not prompt:
        return web.json_response({"error": "Unknown action"}, status=404)
    thread_id = data.get("thread_id")
    if not thread_id:
        return web.json_response({"error": "Missing thread_id"}, status=400)
    enqueue(process_agent_response, thread_id, prompt, agent_id)
    return web.json_response({
        "status": "queued",
        "agent_id": agent_id,
        "action_id": action_id
    })


async def respond_to_agent_request(request: web.Request) -> web.Response:
    """Respond to a pending agent request (permission, choice, etc.)."""
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    
    request_id = data.get("request_id")
    outcome = data.get("outcome", "denied")
    
    if request_id is None:
        return web.json_response({"error": "Missing request_id"}, status=400)
    
    success = respond_to_request(request_id, outcome)
    
    if success:
        logger.info(f"Responded to agent request {request_id}: {outcome}")
        return web.json_response({"status": "ok", "request_id": request_id, "outcome": outcome})
    else:
        return web.json_response({"error": "Request not found or already responded"}, status=404)


async def get_whitelist(request: web.Request) -> web.Response:
    """Get the permission whitelist."""
    db = await get_db()
    whitelist = await db.get_whitelist()
    return web.json_response({"whitelist": whitelist})


async def add_to_whitelist(request: web.Request) -> web.Response:
    """Add a pattern to the permission whitelist."""
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    
    pattern = data.get("pattern")
    description = data.get("description")
    
    if not pattern:
        return web.json_response({"error": "Missing pattern"}, status=400)
    
    db = await get_db()
    entry_id = await db.add_to_whitelist(pattern, description)
    logger.info(f"Added to whitelist: {pattern}")
    
    return web.json_response({
        "status": "ok",
        "id": entry_id,
        "pattern": pattern,
        "description": description
    }, status=201)


async def remove_from_whitelist(request: web.Request) -> web.Response:
    """Remove a pattern from the permission whitelist."""
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    
    pattern = data.get("pattern")
    
    if not pattern:
        return web.json_response({"error": "Missing pattern"}, status=400)
    
    db = await get_db()
    success = await db.remove_from_whitelist(pattern)
    
    if success:
        logger.info(f"Removed from whitelist: {pattern}")
        return web.json_response({"status": "ok", "pattern": pattern})
    else:
        return web.json_response({"error": "Pattern not found"}, status=404)


def setup_routes(app: web.Application) -> None:
    """Set up agent routes."""
    app.router.add_get("/agents", list_agents)
    app.router.add_post("/agent/{agent_id}/message", send_message)
    app.router.add_post("/agent/{agent_id}/action/{action_id}", trigger_action)
    app.router.add_post("/agent/respond", respond_to_agent_request)
    app.router.add_get("/agent/whitelist", get_whitelist)
    app.router.add_post("/agent/whitelist", add_to_whitelist)
    app.router.add_delete("/agent/whitelist", remove_from_whitelist)
