"""ACP client for communicating with agents via stdio using the ACP protocol."""

import asyncio
import json
import logging
import shlex
import shutil
from typing import Optional, AsyncIterator
from pathlib import Path

from .config import get_config

logger = logging.getLogger(__name__)

class _ACPState:
    """Encapsulated ACP client state."""

    def __init__(self) -> None:
        self.agent_proc = None
        self.agent_reader = None
        self.agent_writer = None
        self.agent_lock = asyncio.Lock()
        self.request_lock = asyncio.Lock()  # Ensures only one request at a time
        self.session_id = None
        self.request_id = 0
        self.pending_requests = {}  # request_id -> asyncio.Future
        self.request_callback = None  # Callback to notify UI of pending requests
        self.whitelist_checker = None  # Callback to check if request is whitelisted


_state = _ACPState()


def reset_state() -> None:
    """Reset ACP client state (primarily for tests)."""
    _state.agent_proc = None
    _state.agent_reader = None
    _state.agent_writer = None
    _state.agent_lock = asyncio.Lock()
    _state.request_lock = asyncio.Lock()
    _state.session_id = None
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


def _next_request_id():
    _state.request_id += 1
    return _state.request_id


async def _read_response(reader) -> dict:
    """Read a JSON-RPC response from the agent."""
    line = await reader.readline()
    if not line:
        raise RuntimeError("Agent connection closed")
    try:
        return json.loads(line.decode())
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse agent response: {line}")
        raise RuntimeError(f"Invalid JSON from agent: {e}")


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
    _state.agent_writer.write(data.encode())
    await _state.agent_writer.drain()
    
    # Collect session updates if requested
    collected_content = []  # List of content blocks (text, images, files, etc.)
    current_tool_title = None
    
    # Read responses until we get the one matching our request ID
    while True:
        response = await asyncio.wait_for(_read_response(_state.agent_reader), timeout=300)
        
        # Handle notifications (no id) - these are one-way updates
        if "id" not in response:
            method_name = response.get("method", "")
            if collect_updates and method_name == "session/update":
                update = response.get("params", {}).get("update", {})
                session_update_type = update.get("sessionUpdate", "")
                
                # Broadcast status updates via callback
                if status_callback:
                    if session_update_type == "tool_call":
                        title = update.get("title", "Working...")
                        logger.info(f"Agent tool call: {title}")
                        current_tool_title = title
                        await status_callback({"type": "tool_call", "title": title})
                    elif session_update_type == "tool_call_update":
                        status = update.get("status", "")
                        if status:
                            title = update.get("title") or current_tool_title
                            await status_callback({"type": "tool_status", "status": status, "title": title})
                    elif session_update_type == "agent_message_chunk":
                        # Stream agent message chunks to UI
                        content = update.get("content", {})
                        chunk_content = content.get("content", content)
                        if chunk_content.get("type") == "text":
                            text = chunk_content.get("text", "")
                            if text:
                                if status_callback:
                                    await status_callback({"type": "message_chunk", "text": text, "kind": "draft"})
                    elif session_update_type == "agent_thought_chunk":
                        # Stream agent thought chunks to UI
                        content = update.get("content", {})
                        chunk_content = content.get("content", content)
                        if chunk_content.get("type") == "text":
                            text = chunk_content.get("text", "")
                            if text:
                                if status_callback:
                                    await status_callback({"type": "thought_chunk", "text": text})
                    elif session_update_type == "plan":
                        # Agent is sharing its plan
                        entries = update.get("entries", [])
                        if entries:
                            plan_text = "\n".join([e.get("content", "") for e in entries])
                            await status_callback({"type": "plan", "text": plan_text})
                            await status_callback({"type": "message_chunk", "text": plan_text, "kind": "plan"})
                
                content = update.get("content")
                if content:
                    content_blocks = []
                    _collect_content_blocks(content, content_blocks)
                    for block in content_blocks:
                        # Only collect agent_message_chunk content for the final response
                        # Skip thoughts, plans, user echoes, and tool-related content
                        if block.get("type") == "text" and session_update_type in ("agent_thought_chunk", "user_message_chunk", "plan", "tool_call", "tool_call_update"):
                            continue
                        # Skip non-text blocks from tool calls and plans as well
                        if session_update_type in ("tool_call", "tool_call_update", "plan"):
                            continue
                        collected_content.append(block)
            continue
        
        # Handle requests from agent (has id, has method) - agent asking client for something
        if "method" in response:
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
                        outcome = await asyncio.wait_for(future, timeout=300)
                    except asyncio.TimeoutError:
                        outcome = "rejected"
                        logger.warning("Permission request timed out, rejecting")
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
                _state.agent_writer.write(data.encode())
                await _state.agent_writer.drain()
                continue
            else:
                logger.warning(f"Unknown agent request: {method_name}")
                continue
        
        # Handle response to our request (has id, matches our request)
        if response.get("id") == request["id"]:
            if "error" in response:
                raise RuntimeError(f"Agent error: {response['error']}")
            result = response.get("result", {})
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
                    result_blocks = collected_content
                
                text_parts = [c.get("text", "") for c in result_blocks if c.get("type") == "text"]
                result["_collected_text"] = _join_text_chunks(text_parts)
                result["_collected_content"] = result_blocks
                
                logger.debug(f"Extracted {len(result_blocks)} content blocks, text length: {len(result['_collected_text'])}")
            return result


def _collect_content_blocks(content, collected: list):
    """Extract content blocks from ACP content (handles dict or list)."""
    if isinstance(content, dict):
        _collect_content_blocks(content.get("content", content), collected)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                _collect_content_blocks(item.get("content", item), collected)
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
    
    if content_type == "text":
        return {
            "type": "text",
            "text": block.get("text", "")
        }
    
    elif content_type == "image":
        # Image can be inline (base64) or by URL
        result = {"type": "image"}
        if "data" in block:
            result["data"] = block["data"]
            result["encoding"] = "base64"
        if "uri" in block:
            result["url"] = block["uri"]
        if "mimeType" in block:
            result["mime_type"] = block["mimeType"]
        else:
            result["mime_type"] = "image/png"  # Default
        if "name" in block:
            result["name"] = block["name"]
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
        return result
    
    elif content_type == "file" or content_type == "artifact":
        # File/artifact with content or URL
        result = {
            "type": "file",
            "name": block.get("name", "unnamed"),
            "mime_type": block.get("content_type", "application/octet-stream")
        }
        if "content" in block:
            result["data"] = block["content"]
            result["encoding"] = block.get("content_encoding", "base64")
        if "content_url" in block:
            result["url"] = block["content_url"]
        return result
    
    # Unknown type - preserve as-is
    elif content_type:
        return block
    
    return None


async def _ensure_agent():
    """Ensure the agent is running and initialized."""
    async with _state.agent_lock:
        # Check if existing connection is still valid
        if _state.agent_proc is not None and _state.agent_proc.returncode is None:
            return
        
        # Clean up old state
        _state.agent_proc = None
        _state.agent_reader = None
        _state.agent_writer = None
        _state.session_id = None
        
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
        )
        
        _state.agent_reader = _state.agent_proc.stdout
        _state.agent_writer = _state.agent_proc.stdin
        
        logger.info(f"ACP agent started (PID: {_state.agent_proc.pid})")
        
        # Initialize the connection
        result = await _send_request("initialize", {
            "protocolVersion": 1,
            "clientCapabilities": {},
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
            "mcpServers": []
        })
        _state.session_id = result.get("sessionId")
        logger.info(f"Session created: {_state.session_id}")


async def send_message_simple(content: str, thread_id: Optional[int] = None, status_callback=None) -> str:
    """Send a message to the agent and return the response."""
    # Check if lock is already held (agent busy)
    if _state.request_lock.locked():
        logger.warning("Agent is busy processing another request")
        return "[Agent is busy, please wait...]"
    
    # Only one request at a time to avoid read conflicts
    async with _state.request_lock:
        try:
            await _ensure_agent()
            
            if not _state.session_id:
                return "[Error: No active session]"
            
            logger.info(f"Sending message to agent: {content[:100]}...")
            
            # Send prompt and collect session updates
            result = await _send_request("session/prompt", {
                "sessionId": _state.session_id,
                "prompt": [{"type": "text", "text": content}]
            }, collect_updates=True, status_callback=status_callback)
            
            # Delay to let agent fully complete its loop
            await asyncio.sleep(0.5)
            
            # Get collected text from session updates
            response = result.get("_collected_text", "")
            
            logger.info(f"Agent response: {response[:100]}...")
            return response or "[No response from agent]"
            
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for agent response")
            return "[Error: Agent timed out]"
        except RuntimeError as e:
            error_str = str(e)
            # If agent reports concurrent prompt error, restart it
            if "Concurrent prompts" in error_str:
                logger.warning("Agent stuck in concurrent state, restarting...")
                await stop_agent()
                await asyncio.sleep(1)
                return "[Agent was busy, please try again]"
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
    # Check if lock is already held (agent busy)
    if _state.request_lock.locked():
        logger.warning("Agent is busy processing another request")
        return {
            "text": "[Agent is busy, please wait...]",
            "content": [{"type": "text", "text": "[Agent is busy, please wait...]"}]
        }
    
    # Only one request at a time to avoid read conflicts
    async with _state.request_lock:
        try:
            await _ensure_agent()
            
            if not _state.session_id:
                return {
                    "text": "[Error: No active session]",
                    "content": [{"type": "text", "text": "[Error: No active session]"}]
                }
            
            logger.info(f"Sending message to agent: {content[:100]}...")
            
            # Send prompt and collect session updates
            result = await _send_request("session/prompt", {
                "sessionId": _state.session_id,
                "prompt": [{"type": "text", "text": content}]
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
                    "content": [{"type": "text", "text": "[No response from agent]"}]
                }
            
            return {
                "text": text,
                "content": content_blocks
            }
            
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for agent response")
            return {
                "text": "[Error: Agent timed out]",
                "content": [{"type": "text", "text": "[Error: Agent timed out]"}]
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
