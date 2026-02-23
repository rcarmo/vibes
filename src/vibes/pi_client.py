"""Pi RPC client for communicating with pi in --mode rpc."""

from __future__ import annotations

import asyncio
import json
import logging
import shlex
import shutil
from typing import Any, Optional

from .config import get_config

logger = logging.getLogger(__name__)



class _PiState:
    """Encapsulated Pi RPC client state."""

    def __init__(self) -> None:
        self.agent_proc = None
        self.agent_reader = None
        self.agent_writer = None
        self.agent_lock = asyncio.Lock()
        self.request_lock = asyncio.Lock()
        self.pending_requests: dict[str, dict] = {}
        self.request_callback = None


_state = _PiState()


def set_request_callback(callback):
    """Set callback for pi extension UI requests."""
    _state.request_callback = callback


def respond_to_request(request_id: str, outcome: str) -> bool:
    """Respond to a pending pi extension UI request."""
    entry = _state.pending_requests.get(request_id)
    if entry and not entry["future"].done():
        entry["future"].set_result(outcome)
        return True
    return False


def reset_state() -> None:
    """Reset pi client state (primarily for tests)."""
    _state.agent_proc = None
    _state.agent_reader = None
    _state.agent_writer = None
    _state.agent_lock = asyncio.Lock()
    _state.request_lock = asyncio.Lock()
    _state.pending_requests = {}
    _state.request_callback = None


def is_pi_running() -> bool:
    """Check if the pi agent is currently running."""
    return _state.agent_proc is not None and _state.agent_proc.returncode is None


async def _read_event(reader) -> dict | None:
    """Read a JSON line from pi stdout."""
    line = await reader.readline()
    if not line:
        raise RuntimeError("Pi agent connection closed")
    try:
        return json.loads(line.decode("utf-8"))
    except json.JSONDecodeError:
        logger.warning("Pi RPC: invalid JSON line ignored")
        return None


async def _send_command(payload: dict) -> None:
    if _state.agent_writer is None:
        raise RuntimeError("Pi agent not connected")
    data = json.dumps(payload) + "\n"
    _state.agent_writer.write(data.encode())
    await _state.agent_writer.drain()


async def start_pi_agent() -> bool:
    """Start pi RPC agent if not already running."""
    async with _state.agent_lock:
        if is_pi_running():
            return True

        config = get_config()
        cmd = config.pi_agent
        cmd_parts = shlex.split(cmd)
        if not cmd_parts:
            raise RuntimeError("Pi agent command is empty")

        executable = cmd_parts[0]
        if not shutil.which(executable):
            raise RuntimeError(f"Pi agent executable '{executable}' not found in PATH")

        logger.info(f"Starting Pi agent: {cmd}")
        _state.agent_proc = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=4 * 1024 * 1024,
        )
        _state.agent_reader = _state.agent_proc.stdout
        _state.agent_writer = _state.agent_proc.stdin
        return True


async def stop_pi_agent() -> None:
    """Stop the pi agent process."""
    async with _state.agent_lock:
        if _state.agent_proc is None:
            return
        try:
            _state.agent_proc.terminate()
            await _state.agent_proc.wait()
        except Exception as e:
            logger.warning(f"Failed to terminate pi agent: {e}")
        finally:
            _state.agent_proc = None
            _state.agent_reader = None
            _state.agent_writer = None


def _extract_tool_status(result: dict | None) -> str | None:
    if not result:
        return None
    for block in result.get("content", []):
        if block.get("type") == "text" and block.get("text"):
            line = block["text"].splitlines()[0].strip()
            if line:
                return line[:120]
    return None


def _extract_tool_args(args: Any) -> dict | None:
    if not args:
        return None
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    if not isinstance(args, dict):
        return None

    nested = (
        args.get("arguments")
        or args.get("input")
        or args.get("params")
        or args.get("parameters")
        or args.get("args")
        or args.get("payload")
    )
    if isinstance(nested, dict):
        return nested
    return args


def _format_tool_title(tool_name: str, args: Any) -> str:
    record = _extract_tool_args(args)
    if not record:
        return tool_name

    detail = None
    command = record.get("command")
    if isinstance(command, str):
        detail = command

    if not detail and isinstance(record.get("commands"), list):
        commands = [item for item in record["commands"] if isinstance(item, str)]
        if commands:
            detail = " && ".join(commands)

    path = record.get("path") or record.get("filePath") or record.get("target")
    if not detail and isinstance(path, str):
        detail = path

    if not detail and isinstance(record.get("paths"), list):
        paths = [item for item in record["paths"] if isinstance(item, str)]
        if paths:
            detail = ", ".join(paths)

    filename = record.get("fileName") or record.get("filename") or record.get("file")
    if not detail and isinstance(filename, str):
        detail = filename

    url = record.get("url")
    if not detail and isinstance(url, str):
        detail = url

    query = record.get("query")
    if not detail and isinstance(query, str):
        detail = query

    if not detail:
        return tool_name

    normalized = " ".join(detail.split())
    clipped = f"{normalized[:120]}..." if len(normalized) > 120 else normalized
    return f"{tool_name}: {clipped}"


def _collect_text(blocks: list[dict]) -> str:
    parts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
    return "".join(parts)


def _blocks_from_pi_content(content, include_text: bool = True) -> list[dict]:
    blocks: list[dict] = []
    if isinstance(content, str):
        if content and include_text:
            blocks.append({"type": "text", "text": content})
        return blocks

    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "text":
                if include_text:
                    blocks.append({"type": "text", "text": item.get("text", "")})
            elif item_type == "image":
                data = item.get("data") or item.get("content")
                mime_type = item.get("mimeType") or item.get("mime_type") or item.get("content_type")
                block = {
                    "type": "image",
                    "mime_type": mime_type or "application/octet-stream",
                }
                if data:
                    block["data"] = data
                blocks.append(block)
            elif item_type == "file":
                data = item.get("data") or item.get("content")
                mime_type = item.get("mimeType") or item.get("mime_type") or item.get("content_type")
                name = item.get("name") or item.get("fileName")
                block = {
                    "type": "file",
                    "mime_type": mime_type or "application/octet-stream",
                }
                if data:
                    block["data"] = data
                if name:
                    block["name"] = name
                blocks.append(block)
            elif item_type in ("toolCall", "thinking"):
                continue
        return blocks

    return blocks


def _blocks_from_pi_attachments(attachments: list[dict] | None) -> list[dict]:
    blocks: list[dict] = []
    if not attachments:
        return blocks

    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        att_type = attachment.get("type")
        name = attachment.get("fileName") or attachment.get("name") or "attachment"
        mime_type = attachment.get("mimeType") or attachment.get("mime_type") or "application/octet-stream"
        content = attachment.get("content")
        if not content:
            continue
        if att_type == "image" or mime_type.startswith("image/"):
            blocks.append({
                "type": "image",
                "mime_type": mime_type,
                "data": content,
                "name": name,
            })
        else:
            blocks.append({
                "type": "file",
                "mime_type": mime_type,
                "data": content,
                "name": name,
            })

    return blocks


def _blocks_from_pi_result_details(details: dict | None) -> list[dict]:
    if not isinstance(details, dict):
        return []
    attachment = details.get("vibesAttachment")
    if not isinstance(attachment, dict):
        return []

    data = attachment.get("data")
    if not data:
        return []

    mime_type = attachment.get("mimeType") or "application/octet-stream"
    name = attachment.get("name")
    kind = attachment.get("kind")

    block = {
        "type": "image" if kind == "image" or mime_type.startswith("image/") else "file",
        "mime_type": mime_type,
        "data": data,
    }
    if name:
        block["name"] = name
    return [block]


def _has_binary_blocks(blocks: list[dict]) -> bool:
    return any(block.get("type") in ("image", "file") for block in blocks)


def _collect_tool_result_blocks(result: dict | None, tool_call_id: str | None, tool_blocks: list[dict], seen: set[str]) -> None:
    if not isinstance(result, dict):
        return
    if tool_call_id and tool_call_id in seen:
        return
    if tool_call_id:
        seen.add(tool_call_id)

    blocks = _blocks_from_pi_content(result.get("content"), include_text=False)
    if not _has_binary_blocks(blocks):
        blocks.extend(_blocks_from_pi_result_details(result.get("details")))

    tool_blocks.extend(blocks)


def _build_extension_request(event: dict) -> dict | None:
    method = event.get("method")
    request_id = event.get("id")
    if not method or not request_id:
        return None

    title = event.get("title") or "Pi Request"
    description = event.get("message") or ""
    tool_call = {
        "title": title,
        "description": description,
        "kind": method,
        "rawInput": event,
    }

    options: list[dict] = []
    if method == "confirm":
        options = [
            {"optionId": "confirm", "name": "Confirm", "kind": "allow_once"},
            {"optionId": "cancel", "name": "Cancel", "kind": "reject_once"},
        ]
    elif method == "select":
        raw_options = event.get("options", [])
        for opt in raw_options:
            if isinstance(opt, dict):
                value = opt.get("value") or opt.get("label") or opt.get("name")
                label = opt.get("label") or opt.get("name") or value
            else:
                value = str(opt)
                label = str(opt)
            if value is None:
                continue
            options.append({"optionId": value, "name": label})
    else:
        return None

    return {
        "request_id": request_id,
        "tool_call": tool_call,
        "options": options,
    }


async def _respond_extension_request(request_id: str, method: str, outcome: str | None) -> None:
    if outcome in (None, "cancel", "cancelled"):
        response = {"type": "extension_ui_response", "id": request_id, "cancelled": True}
    elif method == "confirm":
        response = {
            "type": "extension_ui_response",
            "id": request_id,
            "confirmed": outcome == "confirm",
        }
    else:
        response = {"type": "extension_ui_response", "id": request_id, "value": outcome}
    await _send_command(response)


async def send_message_multimodal(content: str, thread_id: Optional[int] = None, status_callback=None) -> dict:
    """Send a message to the pi agent and return multimodal response."""
    if _state.request_lock.locked():
        return {
            "text": "[Pi agent is busy, please try again]",
            "content": [{"type": "text", "text": "[Pi agent is busy, please try again]"}],
            "cancelled": False,
        }

    async with _state.request_lock:
        try:
            await start_pi_agent()
            if not is_pi_running():
                return {
                    "text": "[Error: Pi agent not running]",
                    "content": [{"type": "text", "text": "[Error: Pi agent not running]"}],
                    "cancelled": False,
                }

            await _send_command({"type": "prompt", "message": content})

            draft_text = ""
            thought_text = ""
            final_message = None
            tool_blocks: list[dict] = []
            tool_calls_seen: set[str] = set()
            tool_titles: dict[str, str] = {}

            def remember_tool_title(tool_call_id: str | None, tool_name: str, args: Any) -> str:
                title = _format_tool_title(tool_name, args)
                if tool_call_id:
                    tool_titles[tool_call_id] = title
                return title

            def lookup_tool_title(tool_call_id: str | None, tool_name: str, args: Any = None) -> str:
                if tool_call_id and tool_call_id in tool_titles:
                    return tool_titles[tool_call_id]
                return _format_tool_title(tool_name, args)

            while True:
                event = await _read_event(_state.agent_reader)
                if not event:
                    continue

                event_type = event.get("type")

                if event_type == "message_update":
                    delta = event.get("assistantMessageEvent", {})
                    delta_type = delta.get("type")
                    if delta_type == "text_delta":
                        chunk = delta.get("delta", "")
                        if chunk:
                            draft_text += chunk
                            if status_callback:
                                await status_callback({
                                    "type": "message_chunk",
                                    "text": chunk,
                                    "kind": "draft",
                                    "mode": "append",
                                })
                    elif delta_type == "thinking_delta":
                        chunk = delta.get("delta", "")
                        if chunk:
                            thought_text += chunk
                            if status_callback:
                                await status_callback({
                                    "type": "thought_chunk",
                                    "text": thought_text,
                                })
                    continue

                if event_type == "tool_execution_start":
                    if status_callback:
                        title = remember_tool_title(
                            event.get("toolCallId"),
                            event.get("toolName", "Tool"),
                            event.get("args") or event.get("arguments"),
                        )
                        await status_callback({
                            "type": "tool_call",
                            "title": title,
                        })
                    continue

                if event_type == "tool_execution_update":
                    if status_callback:
                        status_text = _extract_tool_status(event.get("partialResult")) or "Running"
                        title = lookup_tool_title(
                            event.get("toolCallId"),
                            event.get("toolName", "Tool"),
                            event.get("args") or event.get("arguments"),
                        )
                        await status_callback({
                            "type": "tool_status",
                            "title": title,
                            "status": status_text,
                        })
                    continue

                if event_type == "tool_execution_end":
                    if status_callback:
                        status_text = "Error" if event.get("isError") else "Done"
                        tool_call_id = event.get("toolCallId")
                        title = lookup_tool_title(
                            tool_call_id,
                            event.get("toolName", "Tool"),
                            event.get("args") or event.get("arguments"),
                        )
                        if tool_call_id:
                            tool_titles.pop(tool_call_id, None)
                        await status_callback({
                            "type": "tool_status",
                            "title": title,
                            "status": status_text,
                        })

                    _collect_tool_result_blocks(
                        event.get("result"),
                        event.get("toolCallId"),
                        tool_blocks,
                        tool_calls_seen,
                    )
                    continue

                if event_type == "extension_ui_request":
                    request_id = event.get("id")
                    method = event.get("method")
                    if not request_id or not method:
                        continue

                    request_payload = _build_extension_request(event)
                    if request_payload and _state.request_callback:
                        future = asyncio.get_event_loop().create_future()
                        _state.pending_requests[request_id] = {"future": future, "method": method}
                        await _state.request_callback(request_payload)

                        timeout_ms = event.get("timeout")
                        timeout = timeout_ms / 1000 if timeout_ms else get_config().permission_timeout
                        try:
                            outcome = await asyncio.wait_for(future, timeout=timeout)
                        except asyncio.TimeoutError:
                            outcome = "cancelled"
                        finally:
                            _state.pending_requests.pop(request_id, None)

                        await _respond_extension_request(request_id, method, outcome)
                    else:
                        await _respond_extension_request(request_id, method, "cancelled")
                    continue

                if event_type == "turn_end":
                    final_message = event.get("message")
                    continue

                if event_type == "agent_end":
                    messages = event.get("messages", [])
                    if not final_message:
                        for msg in reversed(messages):
                            if msg.get("role") == "assistant":
                                final_message = msg
                                break

                    for msg in messages:
                        if msg.get("role") == "toolResult":
                            _collect_tool_result_blocks(
                                msg,
                                msg.get("toolCallId"),
                                tool_blocks,
                                tool_calls_seen,
                            )
                    break

            if not final_message:
                return {
                    "text": "[No response from pi agent]",
                    "content": [{"type": "text", "text": "[No response from pi agent]"}],
                    "cancelled": False,
                }

            content_blocks = []
            content_blocks.extend(_blocks_from_pi_content(final_message.get("content")))
            content_blocks.extend(_blocks_from_pi_attachments(final_message.get("attachments")))
            if tool_blocks:
                content_blocks.extend(tool_blocks)

            text = _collect_text(content_blocks) or draft_text

            if not content_blocks and text:
                content_blocks = [{"type": "text", "text": text}]

            return {
                "text": text,
                "content": content_blocks,
                "cancelled": False,
            }

        except Exception as e:
            logger.error(f"Error communicating with pi agent: {e}", exc_info=True)
            return {
                "text": f"[Error: {e}]",
                "content": [{"type": "text", "text": f"[Error: {e}]"}],
                "cancelled": False,
            }
