"""ACP agent route handlers."""

import base64
import json
import logging
import re
from aiohttp import web
from ..db import get_db
from ..config import get_config
from ..opengraph import queue_link_preview_fetch
from ..acp_client import (
    send_message_multimodal as send_acp_message_multimodal,
    is_agent_running as is_acp_running,
    set_request_callback as set_acp_request_callback,
    set_whitelist_checker,
    respond_to_request as respond_to_acp_request,
    prompt_from_action,
)
from ..pi_client import (
    send_message_multimodal as send_pi_message_multimodal,
    is_pi_running,
    is_busy as is_pi_busy,
    send_rpc_command,
    send_rpc_fire_and_forget as send_pi_rpc_fire_and_forget,
    set_request_callback as set_pi_request_callback,
    respond_to_request as respond_to_pi_request,
)
from ..slash_commands import parse_command, execute_command
from ..tasks import enqueue
from .sse import broadcast_event

_DATA_URI_MARKDOWN_IMAGE_RE = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<uri>data:(?P<mime>image/[^;\)]+);base64,(?P<b64>[A-Za-z0-9+/=\s]+))\)"
)


async def _extract_and_store_data_uri_images(db, text: str) -> str:
    """Replace markdown data: image URIs with /media/<id> URLs.

    Some browsers/DOM paths can become unhappy with very large data URIs.
    Converting them to first-class media keeps final rendering stable.
    """
    if not text or "data:image/" not in text:
        return text

    async def _replace(match: re.Match) -> str:
        alt = match.group("alt")
        mime = match.group("mime")
        b64 = (match.group("b64") or "").strip()
        # data URIs sometimes include newlines; remove whitespace for decode.
        b64 = "".join(b64.split())
        try:
            data = base64.b64decode(b64)
        except Exception:
            return match.group(0)

        ext = mime.split("/", 1)[-1] if mime else "png"
        media_id = await db.create_media(
            filename=f"inline.{ext}",
            content_type=mime or "image/png",
            data=data,
            thumbnail=None,
            metadata={"source": "agent", "inline": True},
        )
        return f"![{alt}](/media/{media_id})"

    # Python's re.sub doesn't support async replacement; do a manual scan.
    out = []
    last = 0
    for m in _DATA_URI_MARKDOWN_IMAGE_RE.finditer(text):
        out.append(text[last:m.start()])
        out.append(await _replace(m))
        last = m.end()
    out.append(text[last:])
    return "".join(out)

logger = logging.getLogger(__name__)


def _extract_text_from_blocks(blocks) -> str:
    parts: list[str] = []

    def _walk(node) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text" and isinstance(node.get("text"), str):
                parts.append(node["text"])
            if "content" in node:
                _walk(node.get("content"))
            return
        if isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(blocks)
    return "".join(parts)


def _has_meaningful_response(text_content: str, content_blocks, media_ids) -> bool:
    if str(text_content or "").strip():
        return True
    if media_ids:
        return True

    def _walk(node) -> bool:
        if isinstance(node, dict):
            block_type = node.get("type")
            if block_type in {"image", "file"}:
                return True
            if block_type == "text":
                return bool(str(node.get("text", "")).strip())
            if "content" in node:
                return _walk(node.get("content"))
            return False
        if isinstance(node, list):
            return any(_walk(item) for item in node)
        return False

    return _walk(content_blocks)


# Set up callback for agent requests
async def _handle_agent_request(request_data):
    """Broadcast agent requests to UI."""
    config = get_config()
    payload = dict(request_data or {})
    payload["agent_name"] = config.agent_name
    payload["agent_avatar"] = None
    await broadcast_event("agent_request", payload)

set_acp_request_callback(_handle_agent_request)
set_pi_request_callback(_handle_agent_request)


# Set up whitelist checker
async def _check_whitelist(title: str) -> bool:
    """Check if a tool call title is whitelisted."""
    if get_config().permission_auto_approve:
        return True
    db = await get_db()
    return await db.is_whitelisted(title)

set_whitelist_checker(_check_whitelist)


async def list_agents(request: web.Request) -> web.Response:
    """List available agents and their capabilities."""
    config = get_config()
    default_mode = config.default_agent.lower()
    agents = []
    pi_model = await _resolve_pi_model(config)

    if default_mode == "pi":
        agents.append({
            "id": "default",
            "name": config.agent_name,
            "description": f"Pi agent ({config.pi_agent})",
            "model": pi_model,
            "status": "running" if is_pi_running() else "stopped",
            "actions": []
        })
    else:
        agents.append({
            "id": "default",
            "name": config.agent_name,
            "description": f"ACP agent ({config.acp_agent})",
            "model": config.acp_agent,
            "status": "running" if is_acp_running() else "stopped",
            "actions": []
        })

    if config.pi_enabled and default_mode != "pi":
        agents.append({
            "id": "pi",
            "name": "Pi",
            "description": f"Pi agent ({config.pi_agent})",
            "model": pi_model,
            "status": "running" if is_pi_running() else "stopped",
            "actions": []
        })

    if default_mode != "acp":
        agents.append({
            "id": "acp",
            "name": config.agent_name,
            "description": f"ACP agent ({config.acp_agent})",
            "model": config.acp_agent,
            "status": "running" if is_acp_running() else "stopped",
            "actions": []
        })

    return web.json_response({"agents": agents})


def _format_model_identifier(model: dict) -> str:
    provider = str(model.get("provider", "") or "").strip()
    model_id = str(model.get("modelId") or model.get("id") or model.get("name") or "").strip()
    if provider and model_id:
        return f"{provider}/{model_id}"
    return model_id


def _get_configured_pi_model(config) -> str | None:
    model = getattr(config, "pi_model", None)
    if isinstance(model, str):
        model = model.strip()
        return model or None
    return None


async def _resolve_pi_model(config) -> str | None:
    configured = _get_configured_pi_model(config)
    if not is_pi_running():
        return configured
    try:
        resp = await send_rpc_command({"type": "get_state"}, timeout=1.0)
        if resp and resp.get("success"):
            data = resp.get("data", {})
            model = data.get("model")
            if isinstance(model, dict):
                resolved = _format_model_identifier(model)
                if resolved:
                    return resolved
            elif isinstance(model, str):
                model = model.strip()
                if model:
                    return model
    except Exception:
        logger.debug("Failed to query Pi model state for /agents", exc_info=True)
    return configured


def _resolve_agent_mode(agent_id: str) -> str:
    config = get_config()
    default_mode = config.default_agent.lower()
    if agent_id == "default":
        return default_mode
    if agent_id in ("pi", "acp"):
        return agent_id
    return default_mode


async def process_agent_response(thread_id: int, content: str, agent_id: str):
    """Background task to get agent response and broadcast it."""
    import random
    import string
    import time

    turn_id = f"turn-{int(time.time() * 1000)}-{''.join(random.choices(string.ascii_lowercase + string.digits, k=6))}"
    config = get_config()
    agent_profile = {"agent_name": config.agent_name, "agent_avatar": None}
    latest_draft_text = ""

    try:
        # Status callback to broadcast agent activity
        async def status_callback(status):
            nonlocal latest_draft_text
            if status.get("type") == "message_chunk":
                text = status.get("text", "")
                kind = status.get("kind", "draft")
                mode = status.get("mode", "append")
                if kind == "draft" and text:
                    latest_draft_text = text if mode == "replace" else f"{latest_draft_text}{text}"
                await broadcast_event("agent_draft", {
                    "thread_id": thread_id,
                    "agent_id": agent_id,
                    "turn_id": turn_id,
                    "text": text,
                    "total_lines": status.get("total_lines"),
                    "kind": kind,
                    "mode": mode,
                    **agent_profile,
                })
                if kind != "plan":
                    delta_payload = {
                        "thread_id": thread_id,
                        "agent_id": agent_id,
                        "turn_id": turn_id,
                        "delta": text if mode == "replace" else text,
                        "reset": mode == "replace",
                        **agent_profile,
                    }
                    await broadcast_event("agent_draft_delta", delta_payload)
                return
            if status.get("type") == "thought_chunk":
                await broadcast_event("agent_thought", {
                    "thread_id": thread_id,
                    "agent_id": agent_id,
                    "turn_id": turn_id,
                    "text": status.get("text", ""),
                    "total_lines": status.get("total_lines"),
                    **agent_profile,
                })
                return
            await broadcast_event("agent_status", {
                "thread_id": thread_id,
                "agent_id": agent_id,
                "turn_id": turn_id,
                **status,
                **agent_profile,
            })
        
        # Broadcast that agent is thinking
        await broadcast_event("agent_status", {
            "thread_id": thread_id,
            "agent_id": agent_id,
            "turn_id": turn_id,
            "type": "thinking",
            "title": "Thinking...",
            **agent_profile,
        })
        
        agent_mode = _resolve_agent_mode(agent_id)
        if agent_mode == "pi":
            response = await send_pi_message_multimodal(content, thread_id, status_callback)
        else:
            response = await send_acp_message_multimodal(content, thread_id, status_callback)

        # If a permission request timed out, stop and explain what happened.
        if response.get("cancelled") and response.get("cancel_reason") != "abort":
            await broadcast_event("agent_request_timeout", {
                "thread_id": thread_id,
                "agent_id": agent_id,
                "turn_id": turn_id,
                **agent_profile,
            })
            response = {
                "text": "[Cancelled: permission request timed out]",
                "content": [{"type": "text", "text": "[Cancelled: permission request timed out]"}],
                "cancelled": True,
            }
        
        if response.get("cancelled"):
            await broadcast_event("agent_status", {
                "thread_id": thread_id,
                "agent_id": agent_id,
                "turn_id": turn_id,
                "type": "cancelled",
                "title": "Cancelled",
                **agent_profile,
            })
            # Don't overwrite with generic message — keep the specific one from the client.

        # Process content blocks - store images/files in media table
        db = await get_db()
        media_ids = []
        content_blocks = response.get("content", [])
        text_content = response.get("text", "") or _extract_text_from_blocks(content_blocks)

        # If the agent injected data-uri base64 images into markdown, convert them
        # to stored media and rewrite the markdown to /media/<id>.
        text_content = await _extract_and_store_data_uri_images(db, text_content)
        if not str(text_content or "").strip() and latest_draft_text.strip():
            text_content = latest_draft_text
        
        for block in content_blocks:
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

        if _has_meaningful_response(text_content, content_blocks, media_ids):
            # Store agent response
            agent_response = {
                "type": "agent_response",
                "content": text_content,
                "content_blocks": content_blocks,
                "agent_id": agent_id,
                "thread_id": thread_id,
                "media_ids": media_ids,
            }

            response_id = await db.create_interaction(agent_response)
            response_interaction = await db.get_interaction(response_id)

            # Don't fetch link previews for agent responses - they often contain
            # code snippets, documentation URLs, etc. that don't need previews

            # Broadcast agent response
            await broadcast_event("agent_response", {
                **response_interaction,
                **agent_profile,
            })
            logger.info(
                "Agent response posted for thread %s with %d media items",
                thread_id,
                len(media_ids),
            )
        else:
            logger.info("Skipping empty agent response for thread %s", thread_id)

        # Broadcast that agent is done (after response is available)
        await broadcast_event("agent_status", {
            "thread_id": thread_id,
            "agent_id": agent_id,
            "turn_id": turn_id,
            "type": "done",
            **agent_profile,
        })
        
        # Check for queued messages and send the next one
        if agent_mode == "pi":
            from ..pi_client import pop_queued_message
            queued = pop_queued_message()
            if queued:
                logger.info("Sending queued message after turn completion")
                enqueue(process_agent_response, thread_id, queued, agent_id)
        
    except Exception as e:
        logger.error(f"Error processing agent response: {e}", exc_info=True)
        
        # Broadcast error status
        await broadcast_event("agent_status", {
            "thread_id": thread_id,
            "agent_id": agent_id,
            "turn_id": turn_id,
            "type": "error",
            "title": str(e),
            **agent_profile,
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
        existing_media_id = block.get("media_id") or block.get("mediaId")
        if existing_media_id:
            return int(existing_media_id)

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

    # Intercept slash commands before sending to agent
    command = parse_command(data["content"])
    if command:
        agent_mode = _resolve_agent_mode(agent_id)
        result = await execute_command(command, agent_mode)
        if result.handled:
            # Built-in command — post result as agent response
            agent_response = {
                "type": "agent_response",
                "content": result.message,
                "agent_id": agent_id,
                "thread_id": thread_id,
            }
            response_id = await db.create_interaction(agent_response)
            response_interaction = await db.get_interaction(response_id)
            await broadcast_event("agent_response", response_interaction)
            if result.refresh_agents:
                await broadcast_event("agents_changed", {})
            return web.json_response({
                "user_message": user_interaction,
                "thread_id": thread_id,
                "command": {"status": result.status, "message": result.message},
            }, status=201)
        # Not a built-in command — fall through to forward to agent

    # If agent is busy, send as steering instead of queueing a new turn
    agent_mode = _resolve_agent_mode(agent_id)
    if agent_mode == "pi" and is_pi_busy():
        ok = await send_pi_rpc_fire_and_forget({"type": "steer", "message": data["content"]})
        status_msg = "Sent as steering to active turn" if ok else "Agent is busy (steering failed)"
        return web.json_response({
            "user_message": user_interaction,
            "thread_id": thread_id,
            "steered": ok,
            "status": status_msg,
        }, status=201)

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
    
    success = respond_to_acp_request(request_id, outcome)
    if not success:
        success = respond_to_pi_request(request_id, outcome)
    
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
