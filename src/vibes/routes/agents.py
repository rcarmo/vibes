"""ACP agent route handlers."""

import asyncio
import json
import logging
from aiohttp import web
from ..db import get_db
from ..config import get_config
from ..opengraph import queue_link_preview_fetch
from ..acp_client import send_message_simple, is_agent_running, start_agent
from ..tasks import enqueue
from .sse import broadcast_event

logger = logging.getLogger(__name__)


async def list_agents(request: web.Request) -> web.Response:
    """List available agents and their capabilities."""
    config = get_config()
    return web.json_response({
        "agents": [
            {
                "id": "default",
                "name": config.acp_agent,
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
        
        # Get response from ACP agent
        response_content = await send_message_simple(content, thread_id, status_callback)
        
        # Broadcast that agent is done
        await broadcast_event("agent_status", {
            "thread_id": thread_id,
            "agent_id": agent_id,
            "type": "done"
        })
        
        # Store agent response
        db = await get_db()
        agent_response = {
            "type": "agent_response",
            "content": response_content,
            "agent_id": agent_id,
            "thread_id": thread_id,
        }
        
        response_id = await db.create_interaction(agent_response)
        response_interaction = await db.get_interaction(response_id)
        
        # Queue link preview fetch for agent response too
        queue_link_preview_fetch(response_id, response_content)
        
        # Broadcast agent response
        await broadcast_event("agent_response", response_interaction)
        
        logger.info(f"Agent response posted for thread {thread_id}")
        
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

    # TODO: Implement custom actions via ACP
    return web.json_response({
        "status": "triggered",
        "agent_id": agent_id,
        "action_id": action_id,
        "params": data
    })


def setup_routes(app: web.Application) -> None:
    """Set up agent routes."""
    app.router.add_get("/agents", list_agents)
    app.router.add_post("/agent/{agent_id}/message", send_message)
    app.router.add_post("/agent/{agent_id}/action/{action_id}", trigger_action)
