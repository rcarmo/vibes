"""ACP client for communicating with agents via stdio using the ACP protocol."""

import asyncio
import base64
import json
import logging
import mimetypes
import shlex
import sys
import shutil
from typing import Optional, AsyncIterator
from pathlib import Path

from .config import get_config
from .db import get_db
from .routes.media import generate_thumbnail
from .acp_protocol import (
    parse_frame,
    classify_frame,
    is_thinking_content,
    get_update_segment_kind,
    TurnState,
    THINKING_KINDS,
)

logger = logging.getLogger(__name__)

ACP_FILE_PREVIEW_TOOL_NAME = "vibes/preview_file"
ACP_STORE_MEDIA_TOOL_NAME = "vibes/store_media_file"
ACP_FILE_PREVIEW_INSTRUCTIONS = (
    "You can call Vibes tools via ACP JSON-RPC requests. Use these tools to attach files in chat.\n"
    "\n"
    "Tool: vibes/preview_file (preview + download attachment).\n"
    "Params: path (required, relative to server cwd), title/name (optional), "
    "mime_type/mimeType (optional), previewBytes (default 8192), "
    "maxBytes (default 5242880), mode: 'resource' (default, preview+download) "
    "or 'file' (attachment only).\n"
    "\n"
    "Tool: vibes/store_media_file (store binary in media table and return file/image block).\n"
    "Params: path (required), title/name (optional), mime_type/mimeType (optional), "
    "maxBytes (default 10485760).\n"
    "\n"
    "How to call a tool (ACP JSON-RPC request from agent to client):\n"
    "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"vibes/store_media_file\",\"params\":{\"path\":\"artifacts/report.pdf\"}}\n"
    "\n"
    "The tool response returns {text, content}. Include the returned content blocks in your final response so the UI renders the attachment."
)

DEFAULT_PREVIEW_BYTES = 8192
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_STORE_MAX_BYTES = 10 * 1024 * 1024
TEXT_MIME_TYPES = {
    "application/json",
    "application/xml",
    "application/x-yaml",
    "application/yaml",
    "application/javascript",
    "application/x-javascript",
    "application/markdown",
    "text/markdown",
}


class _ACPState:
    """Encapsulated ACP client state."""

    def __init__(self) -> None:
        self.agent_proc = None
        self.agent_reader = None
        self.agent_writer = None
        self.agent_lock = asyncio.Lock()
        self.request_lock = asyncio.Lock()  # Ensures only one request at a time
        self.cancel_event: asyncio.Event | None = None
        self.session_id = None
        self.chat_conversations = {}
        self.chat_id = 'default'
        self.request_id = 0
        self.pending_requests = {}  # request_id -> asyncio.Future
        self.request_callback = None  # Callback to notify UI of pending requests
        self.whitelist_checker = None  # Callback to check if request is whitelisted


_state = _ACPState()

_throttle_lock = asyncio.Lock()
_last_send_ts: float | None = None
_last_read_ts: float | None = None


async def _maybe_throttle(direction: str) -> None:
    """Throttle ACP traffic if configured."""
    rps = get_config().acp_throttle_rps
    if rps <= 0:
        return
    interval = 1.0 / rps
    global _last_send_ts, _last_read_ts
    async with _throttle_lock:
        now = asyncio.get_event_loop().time()
        last_ts = _last_send_ts if direction == "send" else _last_read_ts
        if last_ts is not None:
            sleep_for = interval - (now - last_ts)
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
        now = asyncio.get_event_loop().time()
        if direction == "send":
            _last_send_ts = now
        else:
            _last_read_ts = now


async def _wait_for_request_slot(timeout_s: float) -> bool:
    """Wait for the request lock to be released, returning True if acquired."""
    acquired = False
    try:
        await asyncio.wait_for(_state.request_lock.acquire(), timeout=timeout_s)
        acquired = True
        return True
    except asyncio.TimeoutError:
        return False
    finally:
        if acquired:
            _state.request_lock.release()


async def _interrupt_inflight_request() -> bool:
    """Cancel the active prompt and wait for the lock to release."""
    if _state.cancel_event:
        _state.cancel_event.set()
    await cancel_session()
    await stop_agent()
    _state.session_id = None
    _state.chat_conversations = {}
    _state.chat_id = 'default'
    return await _wait_for_request_slot(5.0)


def reset_state() -> None:
    """Reset ACP client state (primarily for tests)."""
    _state.agent_proc = None
    _state.agent_reader = None
    _state.agent_writer = None
    _state.agent_lock = asyncio.Lock()
    _state.request_lock = asyncio.Lock()
    _state.cancel_event = None
    _state.session_id = None
    _state.chat_conversations = {}
    _state.chat_id = 'default'
    _state.request_id = 0
    _state.pending_requests = {}
    _state.request_callback = None
    _state.whitelist_checker = None


def get_state() -> _ACPState:
    """Return the ACP state instance."""
    return _state


def prompt_from_action(action_id: str, params: dict | None) -> Optional[str]:
    """Build a prompt for a configured custom action."""
    config = get_config()
    action = config.custom_endpoints.get(action_id)
    if not action:
        return None
    description = action.get("description", action_id)
    prompt = action.get("prompt") or f"{description}"
    if params:
        prompt += f"\n\nParams: {json.dumps(params)}"
    return prompt


def set_request_callback(callback):
    """Set callback for agent requests that need user response."""
    _state.request_callback = callback


def set_whitelist_checker(checker):
    """Set callback to check if a request is whitelisted (auto-approve)."""
    _state.whitelist_checker = checker


def respond_to_request(request_id, outcome: str):
    """Respond to a pending agent request."""
    future = _state.pending_requests.get(request_id)
    if future and not future.done():
        future.set_result(outcome)
        return True
    return False


def _build_agent_prompt(content: str) -> str:
    """Build a prompt with ACP tool instructions appended."""
    from .config import get_config
    config = get_config()
    parts = [ACP_FILE_PREVIEW_INSTRUCTIONS]
    if config.prompt:
        parts.append(config.prompt)
    parts.append(f"User:\n{content}")
    return "\n\n".join(parts)


def _coerce_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_text_mime(mime_type: str) -> bool:
    return mime_type.startswith("text/") or mime_type in TEXT_MIME_TYPES


def _resolve_preview_path(path_str: str) -> Path:
    candidate = Path(path_str).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    resolved = candidate.resolve()
    root = Path.cwd().resolve()
    if root not in resolved.parents and resolved != root:
        raise ValueError("Path is outside the server working directory")
    if not resolved.is_file():
        raise ValueError("File not found")
    return resolved


def _read_preview_bytes(path: Path, preview_bytes: int) -> bytes:
    if preview_bytes <= 0:
        return b""
    with path.open("rb") as handle:
        return handle.read(preview_bytes)


async def _build_preview_file_result(params: dict) -> dict:
    path_value = params.get("path") or params.get("file") or params.get("filepath")
    if not path_value:
        raise ValueError("Missing required 'path' parameter")

    resolved = _resolve_preview_path(path_value)
    display_name = (
        params.get("title")
        or params.get("name")
        or params.get("filename")
        or resolved.name
    )
    preview_bytes = _coerce_int(
        params.get("previewBytes") or params.get("preview_bytes"),
        DEFAULT_PREVIEW_BYTES,
    )
    max_bytes = _coerce_int(
        params.get("maxBytes") or params.get("max_bytes"),
        DEFAULT_MAX_BYTES,
    )
    mode = (params.get("mode") or params.get("kind") or "resource").lower()
    include_blob = params.get("includeBlob")
    if include_blob is None:
        include_blob = params.get("include_blob", True)

    mime_type = (
        params.get("mimeType")
        or params.get("mime_type")
        or params.get("content_type")
        or mimetypes.guess_type(display_name)[0]
        or "application/octet-stream"
    )

    file_size = resolved.stat().st_size
    if mode == "file":
        include_blob = True
    if include_blob and file_size > max_bytes:
        raise ValueError(f"File too large to embed ({file_size} bytes > {max_bytes} bytes)")

    preview_data = await asyncio.to_thread(_read_preview_bytes, resolved, preview_bytes)
    preview_text = None
    if preview_data and _is_text_mime(mime_type):
        preview_text = preview_data.decode("utf-8", errors="replace")

    if include_blob:
        data = await asyncio.to_thread(resolved.read_bytes)
        encoded = base64.b64encode(data).decode("utf-8")
    else:
        encoded = None

    if mode == "resource":
        resource = {
            "uri": display_name,
            "mimeType": mime_type,
        }
        if preview_text:
            resource["text"] = preview_text
        if encoded:
            resource["blob"] = encoded
        block = {"type": "resource", "resource": resource}
    elif mode == "file":
        block = {
            "type": "file",
            "name": display_name,
            "content_type": mime_type,
            "content": encoded,
            "content_encoding": "base64",
        }
    else:
        raise ValueError("Invalid mode; expected 'resource' or 'file'")

    note = ""
    if preview_text and file_size > preview_bytes:
        note = " (preview truncated)"

    return {
        "text": f"Attached {display_name}{note}.",
        "content": [block],
    }


async def _build_store_media_result(params: dict) -> dict:
    path_value = params.get("path") or params.get("file") or params.get("filepath")
    if not path_value:
        raise ValueError("Missing required 'path' parameter")

    resolved = _resolve_preview_path(path_value)
    display_name = (
        params.get("title")
        or params.get("name")
        or params.get("filename")
        or resolved.name
    )
    max_bytes = _coerce_int(
        params.get("maxBytes") or params.get("max_bytes"),
        DEFAULT_STORE_MAX_BYTES,
    )

    mime_type = (
        params.get("mimeType")
        or params.get("mime_type")
        or params.get("content_type")
        or mimetypes.guess_type(display_name)[0]
        or "application/octet-stream"
    )

    data = await asyncio.to_thread(resolved.read_bytes)
    if len(data) > max_bytes:
        raise ValueError(f"File too large to store ({len(data)} bytes > {max_bytes} bytes)")

    thumbnail = generate_thumbnail(data, mime_type)
    metadata = {"size": len(data)}
    if mime_type.startswith("image/"):
        try:
            from PIL import Image
            import io

            img = Image.open(io.BytesIO(data))
            metadata["width"] = img.size[0]
            metadata["height"] = img.size[1]
        except Exception:
            pass

    db = await get_db()
    media_id = await db.create_media(
        filename=display_name,
        content_type=mime_type,
        data=data,
        thumbnail=thumbnail,
        metadata=metadata,
    )

    if mime_type.startswith("image/"):
        block = {
            "type": "image",
            "name": display_name,
            "content_type": mime_type,
            "media_id": media_id,
        }
    else:
        block = {
            "type": "file",
            "name": display_name,
            "content_type": mime_type,
            "media_id": media_id,
        }

    return {
        "text": f"Stored {display_name} in media.",
        "content": [block],
    }


def _next_request_id():
    _state.request_id += 1
    return _state.request_id


async def _read_frame(reader) -> list[dict]:
    """Read a JSON-RPC frame from the agent, returning a list of messages.

    - Returns empty list for blank lines
    - Returns [msg] for single JSON objects
    - Returns list of dicts for JSON-RPC batches
    - Raises RuntimeError if connection closed
    """
    await _maybe_throttle("receive")
    line = await reader.readline()
    if not line:
        raise RuntimeError("Agent connection closed")
    messages = parse_frame(line)
    # If line was non-empty but parse_frame returned [], it was invalid JSON
    # which is already logged by parse_frame; we continue reading
    return messages


async def _read_single_response(reader) -> dict:
    """Read frames until we get at least one message, return the first."""
    while True:
        messages = await _read_frame(reader)
        if messages:
            return messages[0]


async def _send_request(method: str, params: dict, collect_updates: bool = False, status_callback=None) -> dict:
    """Send a JSON-RPC request and wait for response."""
    if _state.agent_writer is None or _state.agent_reader is None:
        raise RuntimeError("Agent not connected")
    
    request = {
        "jsonrpc": "2.0",
        "id": _next_request_id(),
        "method": method,
        "params": params
    }
    
    data = json.dumps(request) + "\n"
    await _maybe_throttle("send")
    _state.agent_writer.write(data.encode())
    await _state.agent_writer.drain()
    
    # Per-turn state for aggregation (no cross-request bleed)
    turn = TurnState(turn_id=request["id"])
    current_tool_title = None
    permission_cancelled = False

    # Read responses until we get the one matching our request ID
    while True:
        # Read frame(s) - may return multiple messages for batches
        messages = await asyncio.wait_for(_read_frame(_state.agent_reader), timeout=300)
        if not messages:
            continue  # blank line or invalid JSON, already logged
        
        for response in messages:
            frame_kind = classify_frame(response)
            
            # Handle notifications (no id) - these are one-way updates
            if frame_kind == "notification":
                method_name = response.get("method", "")
                if collect_updates and method_name == "session/update":
                    update = response.get("params", {}).get("update", {})
                    session_update_type = update.get("sessionUpdate", "")
                    
                    # Track tool calls by toolCallId
                    if session_update_type == "tool_call":
                        tc = turn.record_tool_call(update)
                        if status_callback:
                            logger.info(f"Agent tool call: {tc.title}")
                            current_tool_title = tc.title
                            await status_callback({"type": "tool_call", "title": tc.title})
                    elif session_update_type == "tool_call_update":
                        tc = turn.record_tool_call_update(update)
                        if status_callback:
                            status = tc.status or ""
                            if status:
                                title = tc.title or current_tool_title
                                await status_callback({"type": "tool_status", "status": status, "title": title})

                    # Broadcast status updates via callback
                    if status_callback:
                        if session_update_type == "agent_message_chunk":
                            # Stream agent message chunks to UI
                            content = update.get("content", {})
                            chunk_content = content.get("content", content)
                            if chunk_content.get("type") == "text":
                                text = chunk_content.get("text", "")

                                # Use protocol module for segment classification
                                segment_kind = get_update_segment_kind(update, chunk_content)

                                if text:
                                    # If the agent is streaming a "thinking/segment" channel, keep it out of
                                    # Draft and send it to the thoughts pane.
                                    if segment_kind in THINKING_KINDS:
                                        await status_callback({"type": "thought_chunk", "text": text})
                                    else:
                                        mode = "replace"
                                        if turn.last_draft_text is not None and text and not text.startswith(turn.last_draft_text):
                                            mode = "append"

                                        await status_callback({
                                            "type": "message_chunk",
                                            "text": text,
                                            "kind": "draft",
                                            "mode": mode,
                                        })

                                        if mode == "replace":
                                            turn.last_draft_text = text
                                        else:
                                            turn.last_draft_text = (turn.last_draft_text or "") + text
                        elif session_update_type == "agent_thought_chunk":
                            # Stream agent thought chunks to UI
                            content = update.get("content", {})
                            chunk_content = content.get("content", content)
                            if chunk_content.get("type") == "text":
                                text = chunk_content.get("text", "")
                                if text:
                                    await status_callback({"type": "thought_chunk", "text": text})
                        elif session_update_type == "plan":
                            # Agent is sharing its plan
                            entries = update.get("entries", [])
                            if entries:
                                plan_text = "\n".join([e.get("content", "") for e in entries])
                                await status_callback({"type": "plan", "text": plan_text})
                                await status_callback({"type": "message_chunk", "text": plan_text, "kind": "plan"})
                    
                    # Collect content blocks for final response
                    content = update.get("content")
                    if content:
                        content_blocks = []
                        _collect_content_blocks(content, content_blocks)

                        for block in content_blocks:
                            # Only collect assistant final content; skip thoughts/plans/user echoes/tool-related content
                            if block.get("type") == "text":
                                if session_update_type in ("agent_thought_chunk", "user_message_chunk", "plan", "tool_call", "tool_call_update"):
                                    continue

                                if is_thinking_content(update, block):
                                    continue

                            # Skip non-text blocks from tool calls and plans as well
                            if session_update_type in ("tool_call", "tool_call_update", "plan"):
                                continue

                            # Avoid accumulating repeated snapshot chunks, but still support delta streams.
                            target_list = turn.post_tool_blocks if turn.saw_any_tool_call else turn.pre_tool_blocks
                            if session_update_type == "agent_message_chunk" and block.get("type") == "text":
                                if target_list and target_list[-1].get("type") == "text":
                                    prev = target_list[-1].get("text") or ""
                                    curr = block.get("text") or ""
                                    if curr and curr.startswith(prev):
                                        target_list[-1] = block
                                    else:
                                        target_list.append(block)
                                else:
                                    target_list.append(block)
                            else:
                                target_list.append(block)
                continue
            
            # Handle requests from agent (has id, has method) - agent asking client for something
            if frame_kind == "request":
                method_name = response.get("method", "")
                req_id = response.get("id")
                
                if method_name == "session/request_permission":
                    # Agent is asking for permission
                    params = response.get("params", {})
                    tool_call = params.get("toolCall", {})
                    options = params.get("options", [])
                    title = tool_call.get("title", "Unknown")
                    
                    logger.info(f"Agent requesting permission: {title}")
                    logger.info(f"Full params: {json.dumps(params, indent=2)}")
                    
                    # Check whitelist first
                    outcome = None
                    if _state.whitelist_checker:
                        try:
                            if await _state.whitelist_checker(title):
                                logger.info(f"Permission auto-approved (whitelisted): {title}")
                                outcome = "approved"
                        except Exception as e:
                            logger.error(f"Whitelist check failed: {e}")
                    
                    if outcome is None:
                        # Not whitelisted - wait for user response
                        future = asyncio.get_event_loop().create_future()
                        _state.pending_requests[req_id] = future
                        
                        # Notify UI via callback
                        if _state.request_callback:
                            await _state.request_callback({
                                "type": "permission_request",
                                "request_id": req_id,
                                "tool_call": tool_call,
                                "options": options
                            })
                        
                        # Wait for user response (with timeout)
                        try:
                            timeout_s = get_config().permission_timeout
                            outcome = await asyncio.wait_for(future, timeout=timeout_s)
                        except asyncio.TimeoutError:
                            outcome = "cancelled"
                            permission_cancelled = True
                            logger.warning("Permission request timed out, cancelling")
                        finally:
                            _state.pending_requests.pop(req_id, None)
                    
                    # Build ACP-compliant response
                    # Format: {"outcome": "cancelled"} or {"outcome": "selected", "optionId": "..."}
                    if outcome == "cancelled":
                        outcome_obj = {"outcome": "cancelled"}
                    elif outcome in ("approved", "denied", "rejected"):
                        # Map our simple responses to ACP format
                        # "approved" -> select first allow option, or use "allow-once"
                        # "denied"/"rejected" -> select first reject option, or use "reject-once"
                        if outcome == "approved":
                            # Find an allow option, or default to allow-once
                            option_id = "allow-once"
                            for opt in options:
                                if opt.get("kind") in ("allow_once", "allow_always"):
                                    option_id = opt.get("optionId", option_id)
                                    break
                        else:
                            # Find a reject option, or default to reject-once
                            option_id = "reject-once"
                            for opt in options:
                                if opt.get("kind") in ("reject_once", "reject_always"):
                                    option_id = opt.get("optionId", option_id)
                                    break
                        outcome_obj = {"outcome": "selected", "optionId": option_id}
                    else:
                        # User selected a specific optionId
                        outcome_obj = {"outcome": "selected", "optionId": outcome}
                    
                    logger.info(f"Sending permission response: {outcome_obj}")
                    
                    # Send response to agent
                    permission_response = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"outcome": outcome_obj}
                    }
                    data = json.dumps(permission_response) + "\n"
                    await _maybe_throttle("send")
                    _state.agent_writer.write(data.encode())
                    await _state.agent_writer.drain()

                    if permission_cancelled:
                        await stop_agent()
                        return {"_cancelled": True}

                    continue
                    
                elif method_name == ACP_FILE_PREVIEW_TOOL_NAME:
                    params = response.get("params", {})
                    try:
                        result = await _build_preview_file_result(params)
                        preview_response = {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": result,
                        }
                    except Exception as e:
                        preview_response = {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "error": {"code": -32602, "message": str(e)},
                        }
                    data = json.dumps(preview_response) + "\n"
                    await _maybe_throttle("send")
                    _state.agent_writer.write(data.encode())
                    await _state.agent_writer.drain()
                    continue
                elif method_name == ACP_STORE_MEDIA_TOOL_NAME:
                    params = response.get("params", {})
                    try:
                        result = await _build_store_media_result(params)
                        store_response = {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": result,
                        }
                    except Exception as e:
                        store_response = {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "error": {"code": -32602, "message": str(e)},
                        }
                    data = json.dumps(store_response) + "\n"
                    await _maybe_throttle("send")
                    _state.agent_writer.write(data.encode())
                    await _state.agent_writer.drain()
                    continue
                elif method_name in ("fs/read_text_file", "fs/write_text_file"):
                    # File system requests - we don't support these yet
                    logger.warning(f"Agent requested unsupported fs operation: {method_name}")
                    error_response = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": "Method not supported"}
                    }
                    data = json.dumps(error_response) + "\n"
                    await _maybe_throttle("send")
                    _state.agent_writer.write(data.encode())
                    await _state.agent_writer.drain()
                    continue
                elif method_name.startswith("terminal/"):
                    # Terminal requests - we don't support these yet
                    logger.warning(f"Agent requested unsupported terminal operation: {method_name}")
                    error_response = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": "Method not supported"}
                    }
                    data = json.dumps(error_response) + "\n"
                    await _maybe_throttle("send")
                    _state.agent_writer.write(data.encode())
                    await _state.agent_writer.drain()
                    continue
                else:
                    logger.warning(f"Unknown agent request: {method_name}")
                    continue
            
            # Handle response to our request (has id, matches our request)
            if frame_kind == "response" and response.get("id") == request["id"]:
                if "error" in response:
                    raise RuntimeError(f"Agent error: {response['error']}")
                result = response.get("result", {})
                if permission_cancelled:
                    result["_cancelled"] = True
                if collect_updates:
                    # Log the raw result for debugging
                    logger.debug(f"Final result keys: {list(result.keys())}")
                    logger.debug(f"Final result: {json.dumps(result, indent=2)[:500]}")
                    
                    result_blocks = []
                    
                    # Check for message field (ACP final response)
                    if "message" in result:
                        message = result["message"]
                        if isinstance(message, dict):
                            if "content" in message:
                                _collect_content_blocks(message["content"], result_blocks)
                            elif "text" in message:
                                result_blocks.append({"type": "text", "text": message["text"]})
                    
                    # Check for content field directly
                    if "content" in result:
                        _collect_content_blocks(result.get("content"), result_blocks)
                    
                    # Check for text field directly
                    if result.get("text"):
                        has_text_block = any(block.get("type") == "text" for block in result_blocks)
                        if not has_text_block:
                            result_blocks.append({"type": "text", "text": result["text"]})
                    
                    # Fall back to collected content from session updates
                    if not result_blocks:
                        result_blocks = turn.get_final_blocks()
                    
                    text_parts = [c.get("text", "") for c in result_blocks if c.get("type") == "text"]
                    result["_collected_text"] = _join_text_chunks(text_parts)
                    result["_collected_content"] = result_blocks
                    
                    # Log turn summary for observability
                    summary = turn.get_summary()
                    logger.info(f"Turn {summary['turn_id']} complete: {summary['final_blocks']} blocks, "
                                f"{summary['block_types']}, {summary['total_text_len']} chars, "
                                f"{summary['tool_calls']} tool calls")
                    logger.debug(f"Turn preview: {summary['text_preview']!r}...")
                return result


def _collect_content_blocks(content, collected: list):
    """Extract content blocks from ACP content (handles dict or list)."""
    if isinstance(content, dict):
        if content.get("type") == "content" and "content" in content:
            _collect_content_blocks(content.get("content"), collected)
            return
        if "type" in content:
            block = _parse_content_block(content)
            if block:
                collected.append(block)
            return
        if "content" in content:
            nested = content.get("content")
            if nested is not content:
                _collect_content_blocks(nested, collected)
        else:
            block = _parse_content_block(content)
            if block:
                collected.append(block)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "content" and "content" in item:
                    _collect_content_blocks(item.get("content"), collected)
                    continue
                if "type" in item:
                    block = _parse_content_block(item)
                    if block:
                        collected.append(block)
                    continue
                if "content" in item:
                    nested = item.get("content")
                    if nested is not item:
                        _collect_content_blocks(nested, collected)
                else:
                    block = _parse_content_block(item)
                    if block:
                        collected.append(block)
    else:
        block = _parse_content_block(content)
        if block:
            collected.append(block)


def _join_text_chunks(chunks: list[str]) -> str:
    """Join text chunks exactly as provided by the agent."""
    return "".join(chunk for chunk in chunks if chunk)


def _parse_content_block(block: dict) -> dict | None:
    """Parse a single ACP content block into our internal format."""
    if not isinstance(block, dict):
        return None
    content_type = block.get("type")
    annotations = block.get("annotations")
    
    if content_type == "text":
        result = {
            "type": "text",
            "text": block.get("text", "")
        }
        if annotations:
            result["annotations"] = annotations
        return result
    
    elif content_type == "image":
        # Image can be inline (base64) or by URL
        result = {"type": "image"}
        if "data" in block:
            result["data"] = block["data"]
            result["encoding"] = "base64"
        if "content" in block:
            result["data"] = block["content"]
            result["encoding"] = block.get("content_encoding", "base64")
        if "uri" in block:
            result["url"] = block["uri"]
        if "content_url" in block:
            result["url"] = block["content_url"]
        if "mimeType" in block:
            result["mime_type"] = block["mimeType"]
        elif "content_type" in block:
            result["mime_type"] = block["content_type"]
        elif "mime_type" in block:
            result["mime_type"] = block["mime_type"]
        else:
            result["mime_type"] = "image/png"  # Default
        if "name" in block:
            result["name"] = block["name"]
        if "media_id" in block or "mediaId" in block:
            result["media_id"] = block.get("media_id") or block.get("mediaId")
        if annotations:
            result["annotations"] = annotations
        return result
    
    elif content_type == "resource_link":
        # Resource link (MCP-compatible)
        result = {
            "type": "resource_link",
            "name": block.get("name", "resource"),
            "uri": block.get("uri"),
            "mime_type": block.get("mimeType", "application/octet-stream"),
            "description": block.get("description"),
            "title": block.get("title"),
            "size": block.get("size"),
        }
        if annotations:
            result["annotations"] = annotations
        return result
    
    elif content_type == "resource":
        # Embedded resource (text or blob)
        resource = block.get("resource", {})
        result = {
            "type": "resource",
            "uri": resource.get("uri"),
            "mime_type": resource.get("mimeType", "text/plain"),
        }
        if "text" in resource:
            result["text"] = resource["text"]
        if "blob" in resource:
            result["data"] = resource["blob"]
            result["encoding"] = "base64"
        if annotations:
            result["annotations"] = annotations
        return result
    
    elif content_type == "file" or content_type == "artifact":
        # File/artifact with content or URL
        result = {
            "type": "file",
            "name": block.get("name", "unnamed"),
            "mime_type": block.get(
                "content_type",
                block.get("mime_type", block.get("mimeType", "application/octet-stream"))
            )
        }
        if "content" in block:
            result["data"] = block["content"]
            result["encoding"] = block.get("content_encoding", "base64")
        if "content_url" in block:
            result["url"] = block["content_url"]
        if "media_id" in block or "mediaId" in block:
            result["media_id"] = block.get("media_id") or block.get("mediaId")
        if annotations:
            result["annotations"] = annotations
        return result
    
    # Unknown type - preserve as-is
    elif content_type:
        return block
    
    return None


def _messages_mcp_servers(chat_id=None):
    """Single ACP session currently implies explicitly enabled workspace scope."""
    config = get_config()
    if not getattr(config, 'acp_messages_enabled', False):
        return []
    if config.db_path == ':memory:':
        raise ValueError('ACP messages require a persistent database')
    database = Path(config.db_path).resolve()
    if not database.is_file():
        raise ValueError('ACP messages database does not exist')
    return [{
        'name': 'vibes-messages', 'command': sys.executable,
        'args': ['-m', 'vibes.messages_mcp', '--database', str(database), ] + (['--session-id', chat_id] if chat_id is not None else ['--workspace-access'])
                + (['--workspace-root', str(Path.cwd().resolve())] if getattr(config, 'acp_workspace_read_enabled', False) else []),
        'env': [{'name': 'PYTHONPATH', 'value': str(Path(__file__).resolve().parents[1])}],
    }]


async def select_chat_session(chat_id: str):
    """Select an in-process ACP conversation only while no prompt owns the stream."""
    if not isinstance(chat_id, str) or not chat_id:
        raise ValueError('Chat session ID required')
    if _state.request_lock.locked():
        raise RuntimeError('Cannot switch ACP session while agent is busy')
    async with _state.request_lock:
        await _ensure_agent()
        if _state.session_id:
            _state.chat_conversations[_state.chat_id] = _state.session_id
        conversation = _state.chat_conversations.get(chat_id)
        if conversation is None:
            result = await _send_request('session/new', {
                'cwd': str(Path.cwd()), 'mcpServers': _messages_mcp_servers(chat_id),
            })
            conversation = result.get('sessionId')
            if not isinstance(conversation, str) or not conversation:
                raise RuntimeError('Agent returned no conversation ID')
            _state.chat_conversations[chat_id] = conversation
        _state.chat_id = chat_id
        _state.session_id = conversation
        return conversation


async def _ensure_agent():
    """Ensure the agent is running and initialized."""
    async with _state.agent_lock:
        # Check if existing connection is still valid
        if _state.agent_proc is not None and _state.agent_proc.returncode is None:
            if _state.session_id is None:
                cwd = str(Path.cwd())
                result = await _send_request("session/new", {
                    "cwd": cwd,
                    "mcpServers": _messages_mcp_servers()
                })
                _state.session_id = result.get("sessionId")
                logger.info(f"Session created: {_state.session_id}")
            return
        
        # Clean up old state
        _state.agent_proc = None
        _state.agent_reader = None
        _state.agent_writer = None
        _state.session_id = None
        _state.chat_conversations = {}
        _state.chat_id = 'default'
        
        config = get_config()
        agent_cmd = config.acp_agent
        
        # Parse command with arguments (e.g., "copilot --acp")
        cmd_parts = shlex.split(agent_cmd)
        if not cmd_parts:
            raise RuntimeError("Agent command is empty")
        
        executable = cmd_parts[0]
        if not shutil.which(executable):
            raise RuntimeError(f"Agent executable '{executable}' not found in PATH")
        
        logger.info(f"Starting ACP agent: {agent_cmd}")
        
        # Start the agent process
        _state.agent_proc = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=4 * 1024 * 1024,
        )
        
        _state.agent_reader = _state.agent_proc.stdout
        _state.agent_writer = _state.agent_proc.stdin
        
        logger.info(f"ACP agent started (PID: {_state.agent_proc.pid})")
        
        # Initialize the connection with accurate capabilities
        # We don't support fs or terminal operations currently
        result = await _send_request("initialize", {
            "protocolVersion": 1,
            "clientCapabilities": {
                "fs": {
                    "readTextFile": False,
                    "writeTextFile": False,
                },
                "terminal": False,
            },
            "clientInfo": {
                "name": "vibes",
                "version": "0.1.0"
            }
        })
        logger.info(f"Agent initialized: {result}")
        
        # Create a new session
        cwd = str(Path.cwd())
        result = await _send_request("session/new", {
            "cwd": cwd,
            "mcpServers": _messages_mcp_servers()
        })
        _state.session_id = result.get("sessionId")
        logger.info(f"Session created: {_state.session_id}")


async def send_message_simple(content: str, thread_id: Optional[int] = None, status_callback=None) -> str:
    """Send a message to the agent and return the response."""
    # Check if lock is already held (agent busy)
    if _state.request_lock.locked():
        logger.info("Agent busy; sending session/cancel to interrupt.")
        interrupted = await _interrupt_inflight_request()
        if not interrupted:
            return "[Agent is busy, please try again]"
    
    # Only one request at a time to avoid read conflicts
    async with _state.request_lock:
        try:
            await _ensure_agent()
            
            if not _state.session_id:
                return "[Error: No active session]"
            
            logger.info(f"Sending message to agent: {content[:100]}...")
            prompt_text = _build_agent_prompt(content)
            
            # Send prompt and collect session updates
            result = await _send_request("session/prompt", {
                "sessionId": _state.session_id,
                "prompt": [{"type": "text", "text": prompt_text}]
            }, collect_updates=True, status_callback=status_callback)
            
            # Delay to let agent fully complete its loop
            await asyncio.sleep(0.5)
            
            # Get collected text from session updates
            response = result.get("_collected_text", "")
            
            logger.info(f"Agent response: {response[:100]}...")
            return response or "[No response from agent]"
            
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for agent response")
            await stop_agent()
            return "[Error: Agent timed out]"
        except RuntimeError as e:
            error_str = str(e)
            # If agent reports concurrent prompt error, restart it
            if "Concurrent prompts" in error_str:
                logger.warning("Agent stuck in concurrent state, restarting...")
                await stop_agent()
                await asyncio.sleep(1)
                return "[Agent was busy, please try again]"
            logger.warning("Agent internal error, restarting...")
            await stop_agent()
            await asyncio.sleep(1)
            logger.error(f"Error communicating with agent: {e}", exc_info=True)
            return f"[Error: {e}]"
        except Exception as e:
            logger.error(f"Error communicating with agent: {e}", exc_info=True)
            return f"[Error: {e}]"


async def send_message_multimodal(content: str, thread_id: Optional[int] = None, status_callback=None) -> dict:
    """Send a message to the agent and return multimodal response.
    
    Returns a dict with:
        - text: Combined text content (str)
        - content: List of content blocks (text, image, file, etc.)
    """
    # If another prompt is running, cancel it and wait to take the lock.
    if _state.request_lock.locked():
        logger.info("Agent busy; sending session/cancel to interrupt.")
        interrupted = await _interrupt_inflight_request()
        if not interrupted:
            return {
                "text": "[Agent is busy, please try again]",
                "content": [{"type": "text", "text": "[Agent is busy, please try again]"}],
                "cancelled": False
            }

    # Only one request at a time to avoid read conflicts
    async with _state.request_lock:
        _state.cancel_event = asyncio.Event()
        try:
            await _ensure_agent()
            
            if not _state.session_id:
                return {
                    "text": "[Error: No active session]",
                    "content": [{"type": "text", "text": "[Error: No active session]"}],
                    "cancelled": False
                }
            if _state.cancel_event.is_set():
                return {
                    "text": "[Agent was interrupted]",
                    "content": [{"type": "text", "text": "[Agent was interrupted]"}],
                    "cancelled": True
                }
            
            logger.info(f"Sending message to agent: {content[:100]}...")
            prompt_text = _build_agent_prompt(content)
            
            # Send prompt and collect session updates
            result = await _send_request("session/prompt", {
                "sessionId": _state.session_id,
                "prompt": [{"type": "text", "text": prompt_text}]
            }, collect_updates=True, status_callback=status_callback)
            
            # Delay to let agent fully complete its loop
            await asyncio.sleep(0.5)
            
            # Get collected content
            text = result.get("_collected_text", "")
            content_blocks = result.get("_collected_content", [])
            
            # Log the content blocks for debugging
            block_types = {}
            for b in content_blocks:
                t = b.get("type", "unknown")
                block_types[t] = block_types.get(t, 0) + 1
            logger.info(f"Agent response: {len(content_blocks)} blocks ({block_types}), text: {text[:100]}...")
            
            if not text and not content_blocks:
                return {
                    "text": "[No response from agent]",
                    "content": [{"type": "text", "text": "[No response from agent]"}],
                    "cancelled": bool(result.get("_cancelled"))
                }
            
            return {
                "text": text,
                "content": content_blocks,
                "cancelled": bool(result.get("_cancelled"))
            }
            
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for agent response")
            await stop_agent()
            return {
                "text": "[Error: Agent timed out]",
                "content": [{"type": "text", "text": "[Error: Agent timed out]"}],
                "cancelled": False
            }
        except RuntimeError as e:
            error_str = str(e)
            # If agent reports concurrent prompt error, restart it
            if "Concurrent prompts" in error_str:
                logger.warning("Agent stuck in concurrent state, restarting...")
                await stop_agent()
                await asyncio.sleep(1)
                return {
                    "text": "[Agent was busy, please try again]",
                    "content": [{"type": "text", "text": "[Agent was busy, please try again]"}]
                }
            logger.warning("Agent internal error, restarting...")
            await stop_agent()
            await asyncio.sleep(1)
            logger.error(f"Error communicating with agent: {e}", exc_info=True)
            return {
                "text": f"[Error: {e}]",
                "content": [{"type": "text", "text": f"[Error: {e}]"}]
            }
        except Exception as e:
            logger.error(f"Error communicating with agent: {e}", exc_info=True)
            return {
                "text": f"[Error: {e}]",
                "content": [{"type": "text", "text": f"[Error: {e}]"}]
            }
        finally:
            if _state.cancel_event:
                _state.cancel_event.set()


async def send_message(content: str, thread_id: Optional[int] = None) -> AsyncIterator[str]:
    """Send a message and yield the response (for streaming compatibility)."""
    response = await send_message_simple(content, thread_id)
    yield response


def is_agent_running() -> bool:
    """Check if the agent is currently running."""
    return _state.agent_proc is not None and _state.agent_proc.returncode is None


async def start_agent() -> bool:
    """Start the agent if not already running."""
    try:
        await _ensure_agent()
        return True
    except Exception as e:
        logger.error(f"Failed to start agent: {e}")
        return False


async def stop_agent():
    """Stop the agent process."""
    async with _state.agent_lock:
        # Send session/cancel notification if we have an active session
        if _state.session_id and _state.agent_writer:
            try:
                cancel_notification = {
                    "jsonrpc": "2.0",
                    "method": "session/cancel",
                    "params": {"sessionId": _state.session_id, "_meta": {}}
                }
                data = json.dumps(cancel_notification) + "\n"
                await _maybe_throttle("send")
                _state.agent_writer.write(data.encode())
                await _state.agent_writer.drain()
                logger.info(f"Sent session/cancel for session {_state.session_id}")
            except Exception as e:
                logger.warning(f"Failed to send session/cancel: {e}")

        if _state.agent_proc is not None:
            try:
                _state.agent_proc.terminate()
                await asyncio.wait_for(_state.agent_proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                _state.agent_proc.kill()
            except Exception:
                pass
            
            logger.info("ACP agent stopped")
        
        _state.agent_proc = None
        _state.agent_reader = None
        _state.agent_writer = None
        _state.session_id = None
        _state.chat_conversations = {}
        _state.chat_id = 'default'


async def cancel_session():
    """Send a session/cancel notification without stopping the agent."""
    if _state.session_id and _state.agent_writer:
        try:
            cancel_notification = {
                "jsonrpc": "2.0",
                "method": "session/cancel",
                "params": {"sessionId": _state.session_id, "_meta": {}}
            }
            data = json.dumps(cancel_notification) + "\n"
            await _maybe_throttle("send")
            _state.agent_writer.write(data.encode())
            await _state.agent_writer.drain()
            logger.info(f"Sent session/cancel for session {_state.session_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to send session/cancel: {e}")
            return False
    return False
