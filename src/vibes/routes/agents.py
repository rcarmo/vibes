"""ACP agent route handlers."""

import json
from aiohttp import web
from ..db import get_db
from .sse import broadcast_event


# Placeholder for agent sessions
_agent_sessions: dict[str, dict] = {}


async def list_agents(request: web.Request) -> web.Response:
    """List available agents and their capabilities."""
    # TODO: Integrate with actual ACP SDK to discover agents
    return web.json_response({
        "agents": [
            {
                "id": "default",
                "name": "Default Agent",
                "description": "Default coding assistant",
                "actions": []
            }
        ]
    })


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
    }
    if thread_id:
        user_msg["thread_id"] = thread_id
    
    msg_id = await db.create_interaction(user_msg)
    user_interaction = await db.get_interaction(msg_id)
    
    # Use the message ID as thread_id if this is a new thread
    if not thread_id:
        thread_id = msg_id
    
    # Broadcast user message
    await broadcast_event("new_post" if not data.get("thread_id") else "new_reply", user_interaction)
    
    # TODO: Integrate with actual ACP SDK
    # For now, create a placeholder agent response
    agent_response = {
        "type": "agent_response",
        "content": f"[Agent '{agent_id}' response placeholder]",
        "agent_id": agent_id,
        "thread_id": thread_id,
    }
    
    response_id = await db.create_interaction(agent_response)
    response_interaction = await db.get_interaction(response_id)
    
    # Broadcast agent response
    await broadcast_event("agent_response", response_interaction)
    
    return web.json_response({
        "user_message": user_interaction,
        "agent_response": response_interaction,
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

    # TODO: Integrate with actual ACP SDK for custom actions
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
