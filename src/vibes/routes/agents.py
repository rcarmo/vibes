"""ACP agent route handlers."""

import base64
import json
import logging
import re
from aiohttp import web
import asyncio
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
from ..followups import (
    consume_next_followup,
    defer_steer,
    list_followups,
    list_pending_steers,
    queue_followup,
    remove_followup,
    restore_followup,
    reorder_followup,
)
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
_PREVIEW_MAX_CHARS_PER_LINE = 160
_MAX_TURN_PREVIEWS = 128
_turn_previews: dict[str, dict] = {}


def _serialize_followup_event(item: dict) -> dict:
    return {
        "row_id": item["row_id"],
        "thread_id": item["thread_id"],
        "agent_id": item["agent_id"],
        "message_id": item["message_id"],
        "content": item["content"],
        "mode": item.get("mode", "queue"),
        "created_at": item.get("created_at"),
        "emulated": bool(item.get("emulated")),
    }


def _estimate_total_lines(text: str, max_chars_per_line: int = _PREVIEW_MAX_CHARS_PER_LINE) -> int:
    value = (text or "").replace("\r\n", "\n")
    if not value:
        return 0
    return sum(max(1, (len(line) + max_chars_per_line - 1) // max_chars_per_line) for line in value.split("\n"))


def _register_turn_preview(turn_id: str, thread_id: int, agent_id: str) -> None:
    _turn_previews[turn_id] = {
        "thread_id": thread_id,
        "agent_id": agent_id,
        "draft": "",
        "thought": "",
        "expanded": {"draft": False, "thought": False},
    }
    while len(_turn_previews) > _MAX_TURN_PREVIEWS:
        oldest = next(iter(_turn_previews))
        _turn_previews.pop(oldest, None)


def _update_turn_preview(turn_id: str, *, draft: str | None = None, thought: str | None = None) -> None:
    preview = _turn_previews.get(turn_id)
    if preview is None:
        return
    if draft is not None:
        preview["draft"] = draft
    if thought is not None:
        preview["thought"] = thought


def _is_panel_expanded(turn_id: str, panel: str) -> bool:
    preview = _turn_previews.get(turn_id)
    if preview is None:
        return False
    expanded = preview.get("expanded")
    if not isinstance(expanded, dict):
        return False
    return bool(expanded.get(panel))


def _set_panel_expanded(turn_id: str, panel: str, expanded: bool) -> bool:
    preview = _turn_previews.get(turn_id)
    if preview is None:
        return False
    state = preview.get("expanded")
    if not isinstance(state, dict):
        state = {"draft": False, "thought": False}
        preview["expanded"] = state
    state[panel] = bool(expanded)
    return True


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
    from ..avatar import resolve_avatar_url

    config = get_config()
    payload = dict(request_data or {})
    payload["agent_name"] = config.agent_name
    payload["agent_avatar"] = resolve_avatar_url("agent", config.agent_avatar)
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
    from ..avatar import resolve_avatar_url

    config = get_config()
    default_mode = config.default_agent.lower()
    agents = []
    pi_model = await _resolve_pi_model(config)
    agent_avatar = resolve_avatar_url("agent", config.agent_avatar)

    if default_mode == "pi":
        agents.append({
            "id": "default",
            "name": config.agent_name,
            "avatar_url": agent_avatar,
            "description": f"Pi agent ({config.pi_agent})",
            "model": pi_model,
            "status": "running" if is_pi_running() else "stopped",
            "actions": []
        })
    else:
        agents.append({
            "id": "default",
            "name": config.agent_name,
            "avatar_url": agent_avatar,
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

    user = {}
    if config.user_name:
        user["name"] = config.user_name
    if config.user_avatar:
        user["avatar_url"] = resolve_avatar_url("user", config.user_avatar)
    if config.user_avatar_background:
        user["avatar_background"] = config.user_avatar_background

    return web.json_response({"agents": agents, "user": user or None})


async def get_agent_status(request: web.Request) -> web.Response:
    """Return current agent busy state and active turns for polling."""
    from ..pi_client import is_busy as is_pi_busy

    pi_busy = is_pi_busy()
    acp_busy = False
    try:
        from ..acp_client import _state as acp_state
        acp_busy = acp_state.request_lock.locked()
    except Exception:
        pass

    # Get active turns from DB (persisted) + in-memory previews
    active_turns = []
    try:
        db = await get_db()
        active_turns = await db.get_active_turns()
    except Exception:
        pass

    # Enrich with in-memory draft/thought state
    for turn in active_turns:
        preview = _turn_previews.get(turn["turn_id"])
        if preview:
            turn["has_draft"] = bool(preview.get("draft"))
            turn["has_thought"] = bool(preview.get("thought"))

    return web.json_response({
        "busy": pi_busy or acp_busy,
        "pi_busy": pi_busy,
        "acp_busy": acp_busy,
        "active_turns": active_turns,
        "queued_followups": list_followups(),
        "pending_steers": list_pending_steers(),
    })


async def get_turn_preview(request: web.Request) -> web.Response:
    """Return full draft/thought text captured for a live agent turn."""
    turn_id = request.match_info.get("turn_id", "")
    preview = _turn_previews.get(turn_id)
    if not preview:
        return web.json_response({"error": "Turn not found"}, status=404)

    draft = str(preview.get("draft", "") or "")
    thought = str(preview.get("thought", "") or "")
    return web.json_response({
        "turn_id": turn_id,
        "draft": draft,
        "thought": thought,
        "draft_total_lines": _estimate_total_lines(draft),
        "thought_total_lines": _estimate_total_lines(thought),
    })


async def get_agent_queue(request: web.Request) -> web.Response:
    """Return queued follow-ups and pending steering items."""
    agent_id = request.query.get("agent_id") or None
    thread_id_raw = request.query.get("thread_id")
    try:
        thread_id = int(thread_id_raw) if thread_id_raw is not None else None
    except (TypeError, ValueError):
        return web.json_response({"error": "Invalid thread_id"}, status=400)

    items = list_followups(agent_id=agent_id, thread_id=thread_id)
    steers = list_pending_steers(agent_id=agent_id, thread_id=thread_id)
    session_id = request.query.get('session_id')
    if session_id is not None:
        from ..sessions import SessionStore
        database = await get_db()
        if not await SessionStore(database).get(session_id):
            return web.json_response({'error': 'Session not found'}, status=404)
        owners = {}
        for item in items + steers:
            root_id = item.get('thread_id')
            if root_id not in owners:
                root = await database.get_interaction(root_id)
                owners[root_id] = root['data'].get('session_id', 'default') if root else None
        items = [item for item in items if owners[item.get('thread_id')] == session_id]
        steers = [item for item in steers if owners[item.get('thread_id')] == session_id]
    return web.json_response({"items": items, "pending_steers": steers})


async def reorder_queue_item(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        row_id = data.get('row_id')
        if type(row_id) is not int:
            raise ValueError('Invalid row_id')
        found = reorder_followup(row_id, data.get('direction'))
    except (ValueError, TypeError, AttributeError):
        return web.json_response({'error': 'Invalid reorder request'}, status=400)
    if not found:
        return web.json_response({'error': 'Queue item not found'}, status=404)
    items = list_followups()
    await broadcast_event('agent_queue_reordered', {'items': items})
    return web.json_response({'items': items})


async def remove_queue_item(request: web.Request) -> web.Response:
    """Remove a queued follow-up item."""
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    try:
        row_id = int(data.get("row_id"))
    except (TypeError, ValueError):
        return web.json_response({"error": "Missing row_id"}, status=400)

    removed = remove_followup(row_id)
    if not removed:
        return web.json_response({"error": "Queue item not found"}, status=404)

    payload = _serialize_followup_event(removed)
    await broadcast_event("agent_followup_removed", payload)
    return web.json_response({"removed": True, "item": payload})


async def steer_queue_item(request: web.Request) -> web.Response:
    """Promote a queued item into steering for the active turn."""
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    try:
        row_id = int(data.get("row_id"))
    except (TypeError, ValueError):
        return web.json_response({"error": "Missing row_id"}, status=400)

    queued = None
    for item in list_followups():
        if item["row_id"] == row_id:
            queued = item
            break
    if not queued:
        return web.json_response({"error": "Queue item not found"}, status=404)

    agent_mode = _resolve_agent_mode(queued["agent_id"])
    active_turn = await _get_active_turn_for_agent(queued["agent_id"])
    target_turn_id = active_turn.get("turn_id") if active_turn else None
    actual_steer = False
    emulated = agent_mode != "pi"

    removed = remove_followup(row_id)
    if not removed:
        return web.json_response({"error": "Queue item not found"}, status=404)

    if agent_mode == "pi" and _is_agent_busy(agent_mode):
        try:
            actual_steer = bool(await send_pi_rpc_fire_and_forget({"type": "steer", "message": removed["content"]}))
        except asyncio.CancelledError:
            restore_followup(removed)
            raise
        except Exception:
            actual_steer = False
        emulated = not actual_steer

    if not actual_steer:
        emulated = True
        steered = restore_followup(removed, steer=True)
    else:
        steered = {
            **removed,
            "mode": "steer",
            "emulated": False,
        }

    removed_payload = _serialize_followup_event(removed)
    steer_payload = {
        **_serialize_followup_event(steered),
        "turn_id": target_turn_id,
        "actual": actual_steer,
        "emulated": emulated,
    }
    await broadcast_event("agent_followup_removed", removed_payload)
    await broadcast_event("agent_steer_queued", steer_payload)
    return web.json_response({"queued": "steer", "item": steer_payload})


async def set_turn_panel_state(request: web.Request) -> web.Response:
    """Set expanded/collapsed state for draft/thought panel of a turn."""
    turn_id = request.match_info.get("turn_id", "")
    if turn_id not in _turn_previews:
        return web.json_response({"error": "Turn not found"}, status=404)
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    panel = str(data.get("panel", "")).strip().lower()
    if panel not in {"draft", "thought"}:
        return web.json_response({"error": "Invalid panel"}, status=400)
    expanded = bool(data.get("expanded"))
    _set_panel_expanded(turn_id, panel, expanded)
    return web.json_response({"turn_id": turn_id, "panel": panel, "expanded": expanded})


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


async def _get_active_turn_for_agent(agent_id: str) -> dict | None:
    """Return the most recently started active turn for an agent."""
    try:
        db = await get_db()
        turns = await db.get_active_turns()
    except Exception:
        return None

    matching = [turn for turn in turns if turn.get("agent_id") == agent_id]
    if not matching:
        return None
    matching.sort(key=lambda turn: str(turn.get("started_at") or ""), reverse=True)
    return matching[0]


def _is_agent_busy(agent_mode: str) -> bool:
    if agent_mode == "pi":
        return is_pi_busy()
    try:
        from ..acp_client import _state as acp_state
        return acp_state.request_lock.locked()
    except Exception:
        return False


async def _dispatch_acp_thread(content, thread_id, status_callback):
    """Resolve chat identity from persisted history, not global UI selection."""
    database = await get_db()
    root = await database.get_interaction(thread_id)
    chat_id = root['data'].get('session_id', 'default') if root else 'default'
    if chat_id == 'default':
        return await send_acp_message_multimodal(content, thread_id, status_callback)
    from ..sessions import SessionStore
    store = SessionStore(database)
    session = await store.get(chat_id)
    if not session or session['archived']:
        raise ValueError('Chat session unavailable')
    return await send_acp_message_multimodal(content, thread_id, status_callback, chat_id=chat_id, session_store=store)


async def _dispatch_pi_thread(content, thread_id, status_callback):
    """Resolve Pi chat identity from stored history before lock-held selection."""
    database = await get_db()
    root = await database.get_interaction(thread_id)
    chat_id = root['data'].get('session_id', 'default') if root else 'default'
    if chat_id == 'default':
        return await send_pi_message_multimodal(content, thread_id, status_callback)
    from ..sessions import SessionStore
    session = await SessionStore(database).get(chat_id)
    if not session or session['archived']:
        raise ValueError('Chat session unavailable')
    return await send_pi_message_multimodal(content, thread_id, status_callback, chat_id=chat_id,
        session_store=SessionStore(database))


_agent_dispatch_lock = asyncio.Lock()


async def process_agent_response(thread_id: int, content: str, agent_id: str):
    """The process owns one shared ACP/Pi runtime: never overlap worker turns."""
    async with _agent_dispatch_lock:
        return await _process_agent_response_locked(thread_id, content, agent_id)


async def _process_agent_response_locked(thread_id: int, content: str, agent_id: str):
    """Background task to get agent response and broadcast it."""
    import random
    import string
    import time

    from ..avatar import resolve_avatar_url

    turn_id = f"turn-{int(time.time() * 1000)}-{''.join(random.choices(string.ascii_lowercase + string.digits, k=6))}"
    database = await get_db()
    root = await database.get_interaction(thread_id)
    chat_session_id = root["data"].get("session_id", "default") if root else "default"
    config = get_config()
    agent_profile = {"agent_name": config.agent_name, "agent_avatar": resolve_avatar_url("agent", config.agent_avatar)}
    latest_draft_text = ""
    latest_thought_text = ""
    turn_completed = False
    _register_turn_preview(turn_id, thread_id, agent_id)

    # Persist turn start in DB for crash recovery
    try:
        db = await get_db()
        await db.begin_turn(turn_id, thread_id, agent_id)
    except Exception:
        logger.warning("Failed to persist turn start for %s", turn_id, exc_info=True)

    async def _persist_and_broadcast_status(status_data: dict) -> None:
        """Broadcast an agent_status event and persist it for polling."""
        await broadcast_event("agent_status", {
            "thread_id": thread_id,
                "session_id": chat_session_id,
            "agent_id": agent_id,
            "turn_id": turn_id,
            **status_data,
            **agent_profile,
        })
        try:
            db = await get_db()
            await db.update_turn_status(turn_id, status_data)
        except Exception:
            pass

    try:
        # Status callback to broadcast agent activity
        async def status_callback(status):
            nonlocal latest_draft_text, latest_thought_text
            if status.get("type") == "message_chunk":
                text = status.get("text", "")
                kind = status.get("kind", "draft")
                mode = status.get("mode", "append")
                if kind == "draft":
                    delta = status.get("delta")
                    delta_reset = bool(status.get("delta_reset"))
                    if isinstance(delta, str) and delta:
                        latest_draft_text = delta if delta_reset else f"{latest_draft_text}{delta}"
                    elif text:
                        latest_draft_text = text if mode == "replace" else f"{latest_draft_text}{text}"
                    _update_turn_preview(turn_id, draft=latest_draft_text)
                await broadcast_event("agent_draft", {
                    "thread_id": thread_id,
                "session_id": chat_session_id,
                    "agent_id": agent_id,
                    "turn_id": turn_id,
                    "text": text,
                    "total_lines": status.get("total_lines"),
                    "kind": kind,
                    "mode": mode,
                    **agent_profile,
                })
                if kind != "plan":
                    delta = status.get("delta")
                    if isinstance(delta, str):
                        delta_text = delta
                        delta_reset = bool(status.get("delta_reset"))
                    else:
                        delta_text = text
                        delta_reset = mode == "replace"
                    delta_payload = {
                        "thread_id": thread_id,
                "session_id": chat_session_id,
                        "agent_id": agent_id,
                        "turn_id": turn_id,
                        "delta": delta_text,
                        "reset": delta_reset,
                        **agent_profile,
                    }
                    if _is_panel_expanded(turn_id, "draft") and delta_text:
                        await broadcast_event("agent_draft_delta", delta_payload)
                return
            if status.get("type") == "thought_chunk":
                text = status.get("text", "")
                mode = status.get("mode", "append")
                delta = status.get("delta")
                delta_reset = bool(status.get("delta_reset"))
                if isinstance(delta, str) and delta:
                    latest_thought_text = delta if delta_reset else f"{latest_thought_text}{delta}"
                elif text:
                    latest_thought_text = text if mode == "replace" else f"{latest_thought_text}{text}"
                _update_turn_preview(turn_id, thought=latest_thought_text)
                await broadcast_event("agent_thought", {
                    "thread_id": thread_id,
                "session_id": chat_session_id,
                    "agent_id": agent_id,
                    "turn_id": turn_id,
                    "text": text,
                    "total_lines": status.get("total_lines"),
                    **agent_profile,
                })
                if isinstance(delta, str):
                    delta_text = delta
                else:
                    delta_text = text
                    delta_reset = mode == "replace"
                if _is_panel_expanded(turn_id, "thought") and (delta_text or delta_reset):
                    await broadcast_event("agent_thought_delta", {
                        "thread_id": thread_id,
                "session_id": chat_session_id,
                        "agent_id": agent_id,
                        "turn_id": turn_id,
                        "delta": delta_text,
                        "reset": delta_reset,
                        **agent_profile,
                    })
                return
            await _persist_and_broadcast_status(status)
        
        # Broadcast that agent is thinking
        await _persist_and_broadcast_status({
            "type": "thinking",
            "title": "Thinking...",
        })
        
        agent_mode = _resolve_agent_mode(agent_id)
        if agent_mode == "pi":
            response = await _dispatch_pi_thread(content, thread_id, status_callback)
        else:
            response = await _dispatch_acp_thread(content, thread_id, status_callback)

        # If a permission request timed out, stop and explain what happened.
        if response.get("cancelled") and response.get("cancel_reason") != "abort":
            await broadcast_event("agent_request_timeout", {
                "thread_id": thread_id,
                "session_id": chat_session_id,
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
            await _persist_and_broadcast_status({
                "type": "cancelled",
                "title": "Cancelled",
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
                "session_id": chat_session_id,
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
        await _persist_and_broadcast_status({"type": "done"})
        turn_completed = True
        
        next_followup = consume_next_followup(thread_id, agent_id)
        if next_followup:
            logger.info(
                "Dispatching queued follow-up %s for thread %s (%s)",
                next_followup["row_id"],
                thread_id,
                next_followup.get("mode", "queue"),
            )
            await broadcast_event("agent_followup_consumed", _serialize_followup_event(next_followup))
            enqueue(process_agent_response, thread_id, next_followup["content"], agent_id)
        
    except Exception as e:
        logger.error(f"Error processing agent response: {e}", exc_info=True)
        turn_completed = True
        
        # Broadcast error status
        await _persist_and_broadcast_status({
            "type": "error",
            "title": str(e),
        })
        
        # Post error message
        db = await get_db()
        error_response = {
            "type": "agent_response",
            "content": f"[Error: {e}]",
            "agent_id": agent_id,
            "thread_id": thread_id,
                "session_id": chat_session_id,
        }
        response_id = await db.create_interaction(error_response)
        response_interaction = await db.get_interaction(response_id)
        await broadcast_event("agent_response", response_interaction)
    finally:
        # Always clean up turn state
        _turn_previews.pop(turn_id, None)

        # Remove turn from DB
        try:
            db = await get_db()
            await db.end_turn(turn_id)
        except Exception:
            logger.warning("Failed to clean up turn %s from DB", turn_id, exc_info=True)

        # If neither success nor error handler ran, broadcast an error so the
        # frontend never gets stuck in a "thinking" state.
        if not turn_completed:
            try:
                await _persist_and_broadcast_status({
                    "type": "error",
                    "title": "Turn ended unexpectedly",
                })
            except Exception:
                pass


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


async def get_agent_context(request: web.Request) -> web.Response:
    """GET /agent/context — return context window usage for the compose box indicator."""
    null_resp = {"tokens": None, "contextWindow": None, "percent": None}
    if not is_pi_running():
        return web.json_response(null_resp)
    try:
        resp = await send_rpc_command({"type": "get_state"}, timeout=2.0)
        if not resp or not resp.get("success"):
            return web.json_response(null_resp)
        data = resp.get("data", {})
        # Try extracting context usage from state — Pi may include it.
        context = data.get("context") or data.get("context_usage") or {}
        tokens = context.get("tokens")
        context_window = context.get("contextWindow") or context.get("context_window")
        # Also try model-level contextWindow
        if not context_window:
            model = data.get("model")
            if isinstance(model, dict):
                context_window = model.get("contextWindow") or model.get("context_window")
        percent = None
        if tokens is not None and context_window:
            try:
                percent = round(100.0 * tokens / context_window, 1)
            except (TypeError, ZeroDivisionError):
                pass
        return web.json_response({
            "tokens": tokens,
            "contextWindow": context_window,
            "percent": percent,
        })
    except Exception:
        logger.debug("Failed to get agent context usage", exc_info=True)
        return web.json_response(null_resp)


def _format_model_label(model) -> str | None:
    """Format a model dict or string into a 'provider/id' label."""
    if isinstance(model, str):
        return model if model.strip() else None
    if isinstance(model, dict):
        provider = str(model.get("provider", "") or "").strip()
        model_id = str(model.get("modelId") or model.get("id") or model.get("name") or "").strip()
        if provider and model_id:
            return f"{provider}/{model_id}"
        return model_id or None
    return None


async def get_agent_models(request: web.Request) -> web.Response:
    """GET /agent/models — return available models and current selection."""
    empty = {"current": None, "models": []}
    if not is_pi_running():
        return web.json_response(empty)
    try:
        # Get current model from get_state
        current = None
        state_resp = await send_rpc_command({"type": "get_state"}, timeout=2.0)
        if state_resp and state_resp.get("success"):
            current = _format_model_label(state_resp.get("data", {}).get("model"))

        # Get available models via dedicated RPC command
        models = []
        models_resp = await send_rpc_command({"type": "get_available_models"}, timeout=2.0)
        if models_resp and models_resp.get("success"):
            raw_models = models_resp.get("data", {}).get("models", [])
            if isinstance(raw_models, list):
                for m in raw_models:
                    label = _format_model_label(m)
                    if label:
                        models.append(label)
                models.sort()

        return web.json_response({"current": current, "models": models})
    except Exception:
        logger.debug("Failed to get agent models", exc_info=True)
        return web.json_response(empty)


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
    requested_mode = str(data.get("mode") or "").strip().lower() or None
    if requested_mode not in {None, "auto", "queue", "steer"}:
        return web.json_response({"error": "Invalid mode"}, status=400)
    
    # Store user message as interaction
    db = await get_db()
    session_id = data.get('session_id', 'default')
    if not isinstance(session_id, str) or not session_id:
        return web.json_response({'error': 'Invalid session_id'}, status=400)
    if session_id != 'default':
        from ..sessions import SessionStore
        session = await SessionStore(db).get(session_id)
        if not session or session['archived']:
            return web.json_response({'error': 'Session unavailable'}, status=404)
        if data['content'].lstrip().startswith('/'):
            return web.json_response({'error': 'Session-specific commands are not enabled yet'}, status=409)
    if _agent_dispatch_lock.locked() or _is_agent_busy(_resolve_agent_mode(agent_id)):
        active = await _get_active_turn_for_agent(agent_id)
        active_root = await db.get_interaction(active['thread_id']) if active else None
        active_session = active_root['data'].get('session_id', 'default') if active_root else None
        if active_session != session_id:
            return web.json_response({'error': 'Another session is active; retry after its turn completes'}, status=409)
    if thread_id:
        parent = await db.get_interaction(thread_id)
        if parent and parent['data'].get('session_id', 'default') != session_id:
            return web.json_response({'error': 'Thread belongs to another session'}, status=409)
    user_msg = {
        "type": "user_message",
        "content": data["content"],
        "agent_id": agent_id,
        "media_ids": data.get("media_ids", []),
    }
    if session_id != 'default':
        user_msg['session_id'] = session_id
    if thread_id:
        user_msg["thread_id"] = thread_id
    
    msg_id = await db.create_interaction(user_msg)

    # Default new user messages to be their own thread root
    if not thread_id:
        thread_id = msg_id
        await db.set_interaction_thread_id(msg_id, msg_id)

    user_interaction = await db.get_interaction(msg_id)
    
    # Queue background task to fetch link previews
    queue_link_preview_fetch(msg_id, data["content"])
    
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
            # Broadcast model state changes to all clients
            if result.model_label is not None or result.thinking_level is not None:
                model_event = {}
                if result.model_label is not None:
                    model_event["model"] = result.model_label
                if result.thinking_level is not None:
                    model_event["thinking_level"] = result.thinking_level
                if result.supports_thinking is not None:
                    model_event["supports_thinking"] = result.supports_thinking
                await broadcast_event("model_changed", model_event)
            cmd_response = {"status": result.status, "message": result.message}
            if result.model_label is not None:
                cmd_response["model_label"] = result.model_label
            if result.thinking_level is not None:
                cmd_response["thinking_level"] = result.thinking_level
            if result.supports_thinking is not None:
                cmd_response["supports_thinking"] = result.supports_thinking
            return web.json_response({
                "user_message": user_interaction,
                "thread_id": thread_id,
                "command": cmd_response,
            }, status=201)
        # Not a built-in command — fall through to forward to agent

    agent_mode = _resolve_agent_mode(agent_id)
    busy = _is_agent_busy(agent_mode)
    submit_mode = requested_mode or "auto"
    active_turn = await _get_active_turn_for_agent(agent_id) if busy else None
    inflight_thread = active_turn.get("thread_id") if active_turn else None

    if busy and inflight_thread:
        await db.set_interaction_thread_id(msg_id, inflight_thread)
        updated = await db.get_interaction(msg_id)
        await broadcast_event("interaction_updated", updated)
        thread_id = inflight_thread
        user_interaction = updated

    if busy:
        effective_mode = submit_mode if submit_mode != "auto" else "queue"

        if effective_mode == "steer":
            actual_steer = False
            if agent_mode == "pi":
                actual_steer = bool(await send_pi_rpc_fire_and_forget({"type": "steer", "message": data["content"]}))

            if actual_steer:
                steer_payload = {
                    "thread_id": thread_id,
                    "agent_id": agent_id,
                    "message_id": msg_id,
                    "turn_id": active_turn.get("turn_id") if active_turn else None,
                    "actual": True,
                    "emulated": False,
                }
                await broadcast_event("agent_steer_queued", steer_payload)
                return web.json_response({
                    "user_message": user_interaction,
                    "thread_id": thread_id,
                    "queued": "steer",
                    "steered": True,
                    "emulated": False,
                    "status": "Sent as steering to active turn",
                }, status=201)

            queued_item = defer_steer(
                thread_id=thread_id,
                agent_id=agent_id,
                message_id=msg_id,
                content=data["content"],
                emulated=True,
            )
            steer_payload = {
                **_serialize_followup_event(queued_item),
                "turn_id": active_turn.get("turn_id") if active_turn else None,
                "actual": False,
                "emulated": True,
            }
            await broadcast_event("agent_steer_queued", steer_payload)
            return web.json_response({
                "user_message": user_interaction,
                "thread_id": thread_id,
                "queued": "steer",
                "steered": False,
                "emulated": True,
                "item": steer_payload,
                "status": "Steering queued for the next turn",
            }, status=201)

        queued_item = queue_followup(
            thread_id=thread_id,
            agent_id=agent_id,
            message_id=msg_id,
            content=data["content"],
            mode="queue",
        )
        queued_payload = _serialize_followup_event(queued_item)
        await broadcast_event("agent_followup_queued", queued_payload)
        return web.json_response({
            "user_message": user_interaction,
            "thread_id": thread_id,
            "queued": "followup",
            "item": queued_payload,
            "status": "Queued for after the current turn",
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


async def get_agent_commands(request: web.Request) -> web.Response:
    """GET /agent/commands — return slash commands for autocomplete."""
    from ..slash_commands import AVAILABLE_THEMES

    # Base commands that are always available
    commands = [
        {"name": "/model", "description": "Show or set the model"},
        {"name": "/models", "description": "Alias for /model"},
        {"name": "/cycle-model", "description": "Cycle to the next available model"},
        {"name": "/thinking", "description": "Show or set thinking level"},
        {"name": "/cycle-thinking", "description": "Cycle to the next thinking level"},
        {"name": "/context", "description": "Show context window usage"},
        {"name": "/ctx", "description": "Alias for /context"},
        {"name": "/state", "description": "Show current agent/session state"},
        {"name": "/prompt", "description": "Show or set the user system prompt"},
        {"name": "/theme", "description": "Show or set the UI theme", "options": AVAILABLE_THEMES},
        {"name": "/tint", "description": "Set or clear a UI colour tint"},
        {"name": "/name", "description": "Show or set the agent display name"},
        {"name": "/agent-name", "description": "Show or set the agent display name"},
        {"name": "/agent-avatar", "description": "Set or show the agent avatar URL"},
        {"name": "/user-name", "description": "Set or show your display name"},
        {"name": "/user-avatar", "description": "Set or show your avatar URL"},
        {"name": "/user-github", "description": "Set name/avatar from GitHub profile"},
        {"name": "/queue", "description": "Queue a message for after the current turn"},
        {"name": "/abort", "description": "Cancel the current agent operation"},
        {"name": "/restart", "description": "Restart the active agent"},
        {"name": "/shell", "description": "Run a shell command"},
        {"name": "/bash", "description": "Run a shell command and return output inline"},
        {"name": "/commands", "description": "List available commands"},
    ]

    # Try to query agent-specific commands from the running agent
    config = get_config()
    if config.pi_enabled and is_pi_running():
        try:
            resp = await send_rpc_command({"type": "get_state"}, timeout=2.0)
            if resp and resp.get("success"):
                data = resp.get("data", {})
                agent_cmds = data.get("commands") or data.get("available_commands") or []
                existing = {c["name"] for c in commands}
                for cmd in agent_cmds:
                    if isinstance(cmd, dict):
                        name = cmd.get("name", "")
                        if name and name not in existing:
                            commands.append({"name": name, "description": cmd.get("description", "")})
                    elif isinstance(cmd, str) and cmd not in existing:
                        commands.append({"name": cmd, "description": ""})
        except Exception:
            logger.debug("Failed to query agent commands", exc_info=True)

    return web.json_response({"commands": commands})


def setup_routes(app: web.Application) -> None:
    """Set up agent routes."""
    app.router.add_get("/agents", list_agents)
    app.router.add_get("/agents/status", get_agent_status)
    app.router.add_get("/agent/context", get_agent_context)
    app.router.add_get("/agent/models", get_agent_models)
    app.router.add_get("/agent/commands", get_agent_commands)
    app.router.add_get("/agent/queue", get_agent_queue)
    app.router.add_get("/agent/turn/{turn_id}", get_turn_preview)
    app.router.add_post("/agent/turn/{turn_id}/panel", set_turn_panel_state)
    app.router.add_post("/agent/{agent_id}/message", send_message)
    app.router.add_post("/agent/{agent_id}/action/{action_id}", trigger_action)
    app.router.add_post("/agent/queue-remove", remove_queue_item)
    app.router.add_post("/agent/queue-reorder", reorder_queue_item)
    app.router.add_post("/agent/queue-steer", steer_queue_item)
    app.router.add_post("/agent/respond", respond_to_agent_request)
    app.router.add_get("/agent/whitelist", get_whitelist)
    app.router.add_post("/agent/whitelist", add_to_whitelist)
    app.router.add_delete("/agent/whitelist", remove_from_whitelist)
