#!/usr/bin/env python3
"""
aioumcp.py - Async MCP (Model Context Protocol) server implementation
Handles JSON-RPC 2.0 messaging and MCP protocol infrastructure with asyncio support.

Transports:
  stdio  (default)       – reads newline-delimited JSON-RPC from stdin, writes to stdout.
  sse   (--port N)       – HTTP server on 127.0.0.1:N implementing the MCP SSE
                            transport (GET /sse for the event stream, POST /message
                            for JSON-RPC requests).  Compatible with VS Code and
                            other MCP clients that use the "sse" transport type.
  socket (--port N --tcp) – raw TCP with newline-delimited JSON-RPC.
                            Legacy mode; use --tcp flag to opt in.
"""

# ruff: noqa: E402

import os as _os
import sys as _sys

# Force unbuffered stdio before any other I/O occurs.  Setting the env var
# only helps child processes; it does NOT fix already-opened streams.
_os.environ.setdefault("PYTHONUNBUFFERED", "1")

# On Windows the default stdio streams are buffered text-mode with CRLF
# translation.  Switch stdout (and stderr) to binary / unbuffered so
# JSON-RPC newline-delimited output is flushed immediately and is not
# corrupted by \r\n translation.  stdin is switched to binary so that
# readline() returns raw bytes without encoding surprises.
if _os.name == "nt":
    import msvcrt as _msvcrt  # Windows-only
    _msvcrt.setmode(_sys.stdin.fileno(), _os.O_BINARY)
    _msvcrt.setmode(_sys.stdout.fileno(), _os.O_BINARY)
    _msvcrt.setmode(_sys.stderr.fileno(), _os.O_BINARY)

# Regardless of platform, grab the raw binary buffers for stdio.
# Using .buffer bypasses Python's text-mode buffering layer entirely.
_stdin_bin  = _sys.stdin.buffer
_stdout_bin = _sys.stdout.buffer

import math
import re
from asyncio import (
    CancelledError,
    Event,
    IncompleteReadError,
    Lock,
    Queue,
    QueueEmpty,
    QueueFull,
    StreamReader,
    StreamWriter,
    current_task,
    get_event_loop,
    run,
    sleep,
    start_server,
    wait_for,
)
from base64 import b64encode, urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Mapping
from contextvars import copy_context
from dataclasses import MISSING, asdict, dataclass, fields, is_dataclass
from enum import Enum
from inspect import (
    Parameter,
    Signature,
    getdoc,
    getmembers,
    isawaitable,
    iscoroutinefunction,
    ismethod,
    signature,
)
from json import JSONDecodeError, dumps
from json import loads as _json_loads
from logging import INFO, FileHandler, basicConfig, getLogger
from pathlib import Path
from sys import argv, exit
from time import monotonic
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints, is_typeddict

_STRUCTURED_UNSET = object()
from urllib.parse import parse_qs
from uuid import uuid4

from .umcp_shared import (
    SUPPORTED_PROTOCOL_VERSIONS,
    MCPCancellationState,
    MCPHTTPResponse,
    MCPPrincipal,
    MCPRequestCancelled,
    MCPRequestContext,
    MCPRequestRuntime,
    content_type_is_json,
    exact_or_fallback,
    get_request_context,
    get_request_runtime,
    has_ambiguous_singleton_values,
    has_singleton_header_violations,
    http_status_line,
    is_jsonrpc_object,
    is_valid_jsonrpc_id,
    is_valid_jsonrpc_response,
    media_accepts_event_stream,
    media_accepts_json,
    origin_is_allowed,
    protocol_version_error,
    request_target_path,
    reset_request_context,
    reset_request_runtime,
    set_request_context,
    set_request_runtime,
    validate_http_response,
)
from .umcp_shared import (
    get_progress_token as _get_progress_token,
)
from .umcp_shared import (
    is_request_cancelled as _is_request_cancelled,
)
from .umcp_shared import (
    raise_if_cancelled as _raise_if_cancelled,
)


def _reject_json_constant(value: str) -> None:
    raise JSONDecodeError(f"Invalid JSON constant: {value}", value, 0)


def loads(value: str | bytes) -> Any:
    return _json_loads(value, parse_constant=_reject_json_constant)


def get_progress_token() -> str | int | None:
    return _get_progress_token()


def is_request_cancelled() -> bool:
    return _is_request_cancelled()


def raise_if_cancelled() -> None:
    _raise_if_cancelled()


async def notify_progress(progress: float | int, total: float | int | None = None, message: str | None = None) -> None:
    runtime = get_request_runtime()
    if runtime is None or runtime.progress_callback is None:
        return
    result = runtime.progress_callback(progress, total, message)
    if isawaitable(result):
        await result


@dataclass(slots=True)
class _AsyncStreamableHTTPSession:
    principal: str
    protocol_version: str
    created_at: float
    last_seen: float
    disconnect_event: Event
    queue: Queue[bytes]
    writer: StreamWriter | None = None


class AsyncMCPServer:
    """Async MCP server implementation using JSON-RPC 2.0 protocol with asyncio."""

    def __init__(self):
        # Get the directory where the script is located
        self.script_dir = Path(__file__).parent.absolute()
        self.log_file = self.script_dir / "mcpserver.log"

        # Set up logging
        self._setup_logging()

        # Resource state.
        self._resource_subscriptions: set[str] = set()
        self._resource_session_subscriptions: dict[str, set[str]] = {}
        self._dynamic_tools: dict[str, tuple[dict[str, Any], Any]] = {}
        self._dynamic_prompts: dict[str, tuple[dict[str, Any], Any]] = {}
        self._dynamic_resources: dict[str, tuple[dict[str, Any], Any]] = {}
        self._dynamic_resource_templates: list[tuple[dict[str, Any], Any]] = []
        self._completion_providers: dict[tuple[str, str, str], Any] = {}
        self.default_list_page_size: int | None = None
        self.max_completion_values: int = 100
        self.logging_level: str = "info"
        self._request_registry_lock = Lock()
        self._active_requests_by_id: dict[str | int, dict[str, Any]] = {}
        self._active_requests_by_progress_token: dict[str | int, set[str | int]] = {}
        # SSE session map -- populated by run_sse_async; declared here so
        # notification helpers can introspect it from any context.
        # session_id -> (writer, disconnect_event, write_lock, principal name)
        self._sse_sessions: dict[str, tuple[StreamWriter, Event, Lock, str]] = {}
        self._streamable_http_sessions: dict[str, _AsyncStreamableHTTPSession] = {}
        self.streamable_http_session_ttl_seconds = 30 * 60
        self.streamable_http_keepalive_seconds = 15.0
        self.streamable_http_request_timeout_seconds = 30.0
        self.streamable_http_max_sessions = 1024
        self.streamable_http_max_requests_per_connection = 1000
        self._streamable_http_active = False

    def _setup_logging(self) -> None:
        """Set up logging configuration."""
        # Create logs directory if it doesn't exist
        self.log_file.parent.mkdir(exist_ok=True)

        # Configure logging
        basicConfig(
            level=INFO,
            format='[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[
                FileHandler(self.log_file),
            ]
        )
        self.logger = getLogger(__name__)

    def get_config(self) -> dict[str, Any]:
        """Generate server configuration dynamically.

        Ports newer functionality from the synchronous server, including:
          * Updated protocolVersion
          * Prompt capabilities
          * Dynamic instructions string
        """
        capabilities: dict[str, Any] = {
            "tools": {"listChanged": True},
            "prompts": {
                "get": True,
                "listChanged": True,
            },
            "resources": {
                "subscribe": True,
                "listChanged": True,
            },
            "logging": {},
        }
        if self._has_completion_support():
            capabilities["completions"] = {}
        return {
            "protocolVersion": SUPPORTED_PROTOCOL_VERSIONS[0],
            "serverInfo": {
                "name": self.__class__.__name__,
                "version": "0.2.2"
            },
            "capabilities": capabilities,
            "instructions": self.get_instructions()
        }

    def get_instructions(self) -> str:
        """Get server-specific instructions. Override in subclasses."""
        return "This server provides tool functionality via the Model Context Protocol."

    def _empty_object_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    def _sort_discovery_items(self, items: list[dict[str, Any]], *keys: str) -> list[dict[str, Any]]:
        return sorted(items, key=lambda item: tuple(str(item.get(key, "")) for key in keys))

    def _cursor_fingerprint(self, label: str, items: list[dict[str, Any]], identity_keys: tuple[str, ...]) -> str:
        principal = get_request_context().principal or ""
        basis = [principal, label]
        for item in items:
            basis.append("\x1f".join(str(item.get(key, "")) for key in identity_keys))
        return urlsafe_b64encode("\n".join(basis).encode("utf-8")).decode("ascii").rstrip("=")

    def _encode_cursor(self, label: str, offset: int, fingerprint: str) -> str:
        payload = dumps({"v": 1, "l": label, "o": offset, "f": fingerprint}, separators=(",", ":"))
        return urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")

    def _decode_cursor(self, cursor: str, *, label: str, fingerprint: str) -> int:
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            payload = _json_loads(urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise ValueError("Invalid cursor") from exc
        if not isinstance(payload, dict) or payload.get("v") != 1 or payload.get("l") != label:
            raise ValueError("Invalid cursor")
        offset = payload.get("o")
        if not isinstance(offset, int) or offset < 0 or payload.get("f") != fingerprint:
            raise ValueError("Invalid cursor")
        return offset

    def _page_list(
        self,
        *,
        label: str,
        items: list[dict[str, Any]],
        result_key: str,
        identity_keys: tuple[str, ...],
        params: dict[str, Any],
    ) -> dict[str, Any]:
        cursor = params.get("cursor")
        page_size = params.get("pageSize")
        if page_size is not None and (not isinstance(page_size, int) or isinstance(page_size, bool) or page_size <= 0):
            raise ValueError("Invalid params: 'pageSize' must be a positive integer")
        if cursor is not None and not isinstance(cursor, str):
            raise ValueError("Invalid params: 'cursor' must be a string")
        if cursor is None and page_size is None:
            return {result_key: items}

        page_size = page_size or self.default_list_page_size or 50
        fingerprint = self._cursor_fingerprint(label, items, identity_keys)
        start = 0 if cursor is None else self._decode_cursor(cursor, label=label, fingerprint=fingerprint)
        page = items[start:start + page_size]
        result: dict[str, Any] = {result_key: page}
        next_offset = start + len(page)
        if next_offset < len(items):
            result["nextCursor"] = self._encode_cursor(label, next_offset, fingerprint)
        return result

    def discover_tools(self) -> dict[str, Any]:
        """Discover tools via naming convention and runtime registration."""
        tools_by_name: dict[str, dict[str, Any]] = {}
        for name, method in getmembers(self, predicate=ismethod):
            if not name.startswith('tool_'):
                continue
            tool_name = name[5:]
            sig = signature(method)
            doc = getdoc(method) or f"Execute {tool_name} tool"
            parameters = self._extract_parameters_from_signature(sig, method)
            tool_def = {
                "name": tool_name,
                "description": doc,
                "inputSchema": parameters if parameters else self._empty_object_schema(),
            }
            output_schema = self._tool_output_schema(method)
            if output_schema is not None:
                tool_def["outputSchema"] = output_schema
            annotations = self._infer_tool_annotations(tool_name, method)
            if annotations:
                tool_def["annotations"] = annotations
            tools_by_name[tool_name] = tool_def
        for tool_name, (meta, _callable) in self._dynamic_tools.items():
            tools_by_name[tool_name] = dict(meta)
        return {"tools": self._sort_discovery_items(list(tools_by_name.values()), "name")}

    def register_tool(
        self,
        name: str,
        callable_: Any,
        *,
        description: str | None = None,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        annotations: dict[str, Any] | None = None,
    ) -> None:
        meta: dict[str, Any] = {
            "name": name,
            "description": description or (getdoc(callable_) or f"Execute {name} tool"),
            "inputSchema": dict(input_schema) if input_schema else self._extract_parameters_from_signature(signature(callable_), callable_) or self._empty_object_schema(),
        }
        inferred_output_schema = output_schema if output_schema is not None else self._tool_output_schema(callable_)
        if inferred_output_schema is not None:
            meta["outputSchema"] = dict(inferred_output_schema)
        tool_annotations = annotations if annotations is not None else self._infer_tool_annotations(name, callable_)
        if tool_annotations:
            meta["annotations"] = dict(tool_annotations)
        self._dynamic_tools[name] = (meta, callable_)

    async def register_tool_and_notify(self, name: str, callable_: Any, **kwargs: Any) -> None:
        """Register a tool and immediately emit ``tools/list_changed``."""
        self.register_tool(name, callable_, **kwargs)
        await self.notify_tool_list_changed()

    def unregister_tool(self, name: str) -> bool:
        return self._dynamic_tools.pop(name, None) is not None

    async def unregister_tool_and_notify(self, name: str) -> bool:
        """Unregister a tool and emit ``tools/list_changed`` only on success."""
        removed = self.unregister_tool(name)
        if removed:
            await self.notify_tool_list_changed()
        return removed

    @staticmethod
    def _infer_tool_annotations(tool_name: str, method: Any) -> dict[str, bool]:
        """Infer MCP tool annotations from naming conventions and metadata.

        If the method has a ``_mcp_annotations`` dict attribute it is returned
        directly, allowing individual tools to override the heuristics.

        Otherwise, the tool name is matched against known patterns:
        - Read-only tools: list, get, read, inspect, extract, query, search,
          check, audit, fetch, calculate, recommend
        - Destructive tools: delete, clear, cleanup, restart
        - Open-world (external I/O): web_*, azure_*, fetch
        """
        # Explicit override on the method itself
        explicit = getattr(method, "_mcp_annotations", None)
        if explicit is not None:
            return dict(explicit)

        READ_PREFIXES = (
            "list_", "get_", "read_", "inspect_", "extract_",
            "query_", "search_", "check_", "audit_", "fetch_",
            "calculate_", "recommend_",
        )
        READ_EXACT = {
            "list_supported_formats", "office_read", "office_inspect",
            "office_audit",
        }
        DESTRUCTIVE_PREFIXES = ("delete_", "clear_", "cleanup_", "restart_")
        OPEN_WORLD_PREFIXES = ("web_", "azure_")

        is_read_only = (
            any(tool_name.startswith(p) or f"_{p[:-1]}" in tool_name for p in READ_PREFIXES)
            or tool_name in READ_EXACT
        )
        is_destructive = any(tool_name.startswith(p) or f"_{p[:-1]}" in tool_name for p in DESTRUCTIVE_PREFIXES)
        is_open_world = any(tool_name.startswith(p) for p in OPEN_WORLD_PREFIXES)

        annotations: dict[str, bool] = {}
        if is_read_only:
            annotations["readOnlyHint"] = True
            annotations["destructiveHint"] = False
        elif is_destructive:
            annotations["readOnlyHint"] = False
            annotations["destructiveHint"] = True
        else:
            # Mutating but not destructive (patch, add, create, set, etc.)
            annotations["readOnlyHint"] = False
            annotations["destructiveHint"] = False
        if is_open_world:
            annotations["openWorldHint"] = True
        return annotations

    # --- Prompt discovery & handling (ported from synchronous server) ---
    def discover_prompts(self) -> dict[str, Any]:
        """Discover prompts via naming convention and runtime registration."""
        prompts_by_name: dict[str, dict[str, Any]] = {}
        for name, method in getmembers(self, predicate=ismethod):
            if not name.startswith('prompt_'):
                continue
            prompt_name = name[7:]
            sig = signature(method)
            doc = getdoc(method) or f"Prompt template {prompt_name}"
            parameters = self._extract_parameters_from_signature(sig, method)
            categories = self._extract_prompt_categories(doc)
            prompts_by_name[prompt_name] = {
                "name": prompt_name,
                "description": doc,
                "inputSchema": parameters or self._empty_object_schema(),
                "categories": categories,
            }
        for prompt_name, (meta, _callable) in self._dynamic_prompts.items():
            prompts_by_name[prompt_name] = dict(meta)
        return {"prompts": self._sort_discovery_items(list(prompts_by_name.values()), "name")}

    def register_prompt(
        self,
        name: str,
        callable_: Any,
        *,
        description: str | None = None,
        input_schema: dict[str, Any] | None = None,
        categories: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        doc = description or (getdoc(callable_) or f"Prompt template {name}")
        meta: dict[str, Any] = {
            "name": name,
            "description": doc,
            "inputSchema": dict(input_schema) if input_schema else self._extract_parameters_from_signature(signature(callable_), callable_) or self._empty_object_schema(),
            "categories": list(categories) if categories is not None else self._extract_prompt_categories(doc),
        }
        self._dynamic_prompts[name] = (meta, callable_)

    async def register_prompt_and_notify(self, name: str, callable_: Any, **kwargs: Any) -> None:
        """Register a prompt and immediately emit ``prompts/list_changed``."""
        self.register_prompt(name, callable_, **kwargs)
        await self.notify_prompt_list_changed()

    def unregister_prompt(self, name: str) -> bool:
        return self._dynamic_prompts.pop(name, None) is not None

    async def unregister_prompt_and_notify(self, name: str) -> bool:
        """Unregister a prompt and emit ``prompts/list_changed`` only on success."""
        removed = self.unregister_prompt(name)
        if removed:
            await self.notify_prompt_list_changed()
        return removed

    def _extract_prompt_categories(self, doc: str) -> list[str]:
        """Extract categories from a docstring.

        Supports patterns:
          Category: foo
          Categories: foo, bar
          [categories: foo, bar]
          [category: foo]
        Returns a list of lowercase trimmed category tokens.
        """
        if not doc:
            return []
        import re
        lines = doc.splitlines()
        cats = []
        pattern_line = re.compile(r'^\s*Categor(?:y|ies):\s*(.+)$', re.IGNORECASE)
        bracket_pattern = re.compile(r'\[(?:categor(?:y|ies)):\s*([^\]]+)\]', re.IGNORECASE)
        for ln in lines:
            m = pattern_line.match(ln)
            if m:
                cats.extend([c.strip().lower() for c in m.group(1).split(',') if c.strip()])
            for b in bracket_pattern.findall(ln):
                cats.extend([c.strip().lower() for c in b.split(',') if c.strip()])
        seen = set()
        out = []
        for c in cats:
            if c not in seen:
                seen.add(c)
                out.append(c)
        return out

    def _has_completion_support(self) -> bool:
        return bool(
            self._completion_providers
            or self.discover_prompts()["prompts"]
            or self.discover_resource_templates()["resourceTemplates"]
        )

    def register_completion_provider(self, ref_type: str, ref_name: str, argument_name: str, callable_: Any) -> None:
        self._completion_providers[(ref_type, ref_name, argument_name)] = callable_

    def _completion_parameter_schema(self, method: Any, argument_name: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        if isinstance(meta, dict):
            input_schema = meta.get("inputSchema")
            if isinstance(input_schema, dict):
                properties = input_schema.get("properties")
                if isinstance(properties, dict):
                    schema = properties.get(argument_name)
                    if isinstance(schema, dict):
                        return schema
        override = getattr(method, "_mcp_resource_template", None) or getattr(method, "_mcp_prompt", None) or {}
        input_schema = override.get("input_schema")
        if isinstance(input_schema, dict):
            properties = input_schema.get("properties")
            if isinstance(properties, dict):
                schema = properties.get(argument_name)
                if isinstance(schema, dict):
                    return schema
        return self._extract_parameters_from_signature(signature(method), method).get("properties", {}).get(argument_name, {})

    def _resolve_completion_target(self, ref: dict[str, Any]) -> tuple[str, str, Any, dict[str, Any]]:
        ref_type = ref.get("type")
        if ref_type == "ref/prompt":
            name = ref.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError("Invalid completion ref: prompt name is required")
            if name in self._dynamic_prompts:
                meta, method = self._dynamic_prompts[name]
                return ref_type, name, method, dict(meta)
            method_name = f"prompt_{name}"
            if hasattr(self, method_name):
                method = getattr(self, method_name)
                return ref_type, name, method, {"name": name}
            raise ValueError(f"Unknown prompt ref: {name}")
        if ref_type == "ref/resource":
            ref_name = ref.get("uri") or ref.get("uriTemplate") or ref.get("name")
            if not isinstance(ref_name, str) or not ref_name:
                raise ValueError("Invalid completion ref: resource template identifier is required")
            for name, method, params in self._iter_resource_template_methods():
                meta = self._resource_metadata(name, method, params=params)
                if ref_name in {meta.get("name"), meta.get("uriTemplate")}:
                    return ref_type, str(meta.get("uriTemplate")), method, meta
            for meta, method in self._dynamic_resource_templates:
                if ref_name in {meta.get("name"), meta.get("uriTemplate")}:
                    return ref_type, str(meta.get("uriTemplate")), method, dict(meta)
            raise ValueError(f"Unknown resource template ref: {ref_name}")
        raise ValueError("Invalid completion ref: unsupported ref type")

    def _enum_completion_values(self, method: Any, argument_name: str) -> list[str]:
        try:
            type_hints = get_type_hints(method)
        except (NameError, AttributeError, TypeError):
            type_hints = {}
        annotation = type_hints.get(argument_name, signature(method).parameters.get(argument_name, Parameter("x", Parameter.POSITIONAL_OR_KEYWORD)).annotation)
        schema = self._type_to_json_schema(annotation)
        if not isinstance(schema, dict):
            return []
        values = schema.get("enum") if isinstance(schema.get("enum"), list) else []
        return [str(value) for value in values]

    def _schema_enum_completion_values(self, schema: dict[str, Any]) -> list[str]:
        values = schema.get("enum") if isinstance(schema.get("enum"), list) else []
        return [str(value) for value in values]

    def _normalise_completion_result(self, raw: Any) -> tuple[list[str], int | None, bool | None]:
        if isinstance(raw, dict):
            values = raw.get("values", [])
            total = raw.get("total")
            has_more = raw.get("hasMore")
        else:
            values = raw
            total = None
            has_more = None
        if not isinstance(values, list):
            raise ValueError("Completion provider must return a list or {'values': [...]} result")
        out: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = str(value)
            if text not in seen:
                seen.add(text)
                out.append(text)
        if total is not None and (not isinstance(total, int) or isinstance(total, bool) or total < 0):
            raise ValueError("Completion provider returned invalid total")
        if has_more is not None and not isinstance(has_more, bool):
            raise ValueError("Completion provider returned invalid hasMore")
        return out, total, has_more

    async def handle_completion_complete_async(self, request_id: str | int | None, params: dict[str, Any]) -> dict[str, Any]:
        ref = params.get("ref")
        argument = params.get("argument")
        context = params.get("context") or {}
        requested = params.get("maxValues", self.max_completion_values)
        if not isinstance(ref, dict):
            return self.create_response(request_id, None, self.create_error(-32602, "Invalid params: 'ref' must be an object"))
        if not isinstance(argument, dict):
            return self.create_response(request_id, None, self.create_error(-32602, "Invalid params: 'argument' must be an object"))
        if not isinstance(context, dict):
            return self.create_response(request_id, None, self.create_error(-32602, "Invalid params: 'context' must be an object"))
        if not isinstance(requested, int) or isinstance(requested, bool) or requested <= 0:
            return self.create_response(request_id, None, self.create_error(-32602, "Invalid params: 'maxValues' must be a positive integer"))
        argument_name = argument.get("name")
        if not isinstance(argument_name, str) or not argument_name:
            return self.create_response(request_id, None, self.create_error(-32602, "Invalid params: 'argument.name' must be a non-empty string"))
        prefix = argument.get("value", "")
        if prefix is None:
            prefix = ""
        if not isinstance(prefix, str):
            prefix = str(prefix)
        context_arguments = context.get("arguments", {}) or {}
        if not isinstance(context_arguments, dict):
            return self.create_response(request_id, None, self.create_error(-32602, "Invalid params: 'context.arguments' must be an object"))
        try:
            ref_type, ref_name, method, meta = self._resolve_completion_target(ref)
        except ValueError as exc:
            return self.create_response(request_id, None, self.create_error(-32602, str(exc)))
        if argument_name not in signature(method).parameters:
            return self.create_response(request_id, None, self.create_error(-32602, f"Unknown completion argument: {argument_name}"))

        values = self._schema_enum_completion_values(self._completion_parameter_schema(method, argument_name, meta))
        if not values:
            values = self._enum_completion_values(method, argument_name)
        provider = self._completion_providers.get((ref_type, ref_name, argument_name))
        if provider is not None:
            try:
                raw = provider(prefix=prefix, arguments=dict(context_arguments), ref=dict(ref), argument=dict(argument))
                if isawaitable(raw):
                    raw = await raw
                provided_values, provided_total, provided_has_more = self._normalise_completion_result(raw)
            except ValueError as exc:
                return self.create_response(request_id, None, self.create_error(-32602, str(exc)))
            except Exception:  # noqa: BLE001
                return self.create_response(request_id, None, self.create_error(-32603, "Completion provider failed"))
            values.extend(provided_values)
        else:
            provided_total = None
            provided_has_more = None

        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            if prefix and not value.startswith(prefix):
                continue
            if value not in seen:
                seen.add(value)
                deduped.append(value)
        limit = min(requested, self.max_completion_values)
        total = max(provided_total or 0, len(deduped)) if provided_total is not None else len(deduped)
        has_more = provided_has_more if provided_has_more is not None else total > len(deduped[:limit])
        result: dict[str, Any] = {"completion": {"values": deduped[:limit], "hasMore": has_more}}
        if total != len(result["completion"]["values"]) or has_more:
            result["completion"]["total"] = total
        return self.create_response(request_id, result)

    async def handle_prompt_get_async(self, request_id: str | int | None, params: dict[str, Any]) -> dict[str, Any]:
        """Async handler for ``prompts/get`` supporting sync or async methods."""
        prompt_name = params.get('name')
        if not prompt_name:
            error = self.create_error(-32602, "Missing required parameter 'name'")
            return self.create_response(request_id, None, error)
        method_name = f"prompt_{prompt_name}"
        if prompt_name in self._dynamic_prompts:
            _meta, method = self._dynamic_prompts[prompt_name]
        elif hasattr(self, method_name):
            method = getattr(self, method_name)
        else:
            error = self.create_error(-32601, f"Prompt not found: {prompt_name}")
            return self.create_response(request_id, None, error)

        sig = signature(method)
        doc = getdoc(method) or f"Prompt template {prompt_name}"
        arguments = params.get('arguments', {}) or {}
        categories = self._extract_prompt_categories(doc)
        result_body: dict[str, Any] = {'description': doc}
        if categories:
            result_body['categories'] = categories

        allowed_params = {p_name for p_name in sig.parameters if p_name != 'self'}
        unknown_params = sorted(key for key in arguments if key not in allowed_params)
        if unknown_params:
            error = self.create_error(
                -32602, "Unrecognized parameter(s): " + ", ".join(unknown_params)
            )
            return self.create_response(request_id, None, error)

        try:
            type_hints = get_type_hints(method)
        except (NameError, AttributeError, TypeError):
            type_hints = {}

        try:
            kwargs = {}
            for p_name, p in sig.parameters.items():
                if p_name == 'self':
                    continue
                if p_name in arguments:
                    value = arguments[p_name]
                    if p_name in type_hints:
                        value = self._coerce_value(value, type_hints[p_name])
                    kwargs[p_name] = value
                elif p.default != Parameter.empty:
                    kwargs[p_name] = p.default
                else:
                    raise ValueError(f"Missing required argument '{p_name}' for prompt {prompt_name}")
        except ValueError as e:
            error = self.create_error(-32602, str(e))
            return self.create_response(request_id, None, error)

        try:
            if iscoroutinefunction(method):
                ret = await method(**kwargs)
            else:
                ctx = copy_context()
                ret = await get_event_loop().run_in_executor(None, lambda: ctx.run(method, **kwargs))
        except (MCPRequestCancelled, CancelledError):
            raise
        except Exception as e:  # noqa: BLE001
            message = self._remote_safe_failure("Prompt execution failed", f"Prompt execution error: {e}")
            error = self.create_error(-32603, message)
            return self.create_response(request_id, None, error)

        if isinstance(ret, str):
            result_body['messages'] = [{'role': 'user', 'content': {'type': 'text', 'text': ret}}]
        elif isinstance(ret, list) and all(isinstance(m, dict) and 'role' in m and 'content' in m for m in ret):
            result_body['messages'] = ret
        elif isinstance(ret, dict):
            if 'messages' in ret and isinstance(ret['messages'], list):
                merged = dict(ret)
                merged.setdefault('description', doc)
                if categories and 'categories' not in merged:
                    merged['categories'] = categories
                result_body = merged
            else:
                result_body['messages'] = [{
                    'role': 'user',
                    'content': {'type': 'text', 'text': dumps(ret, ensure_ascii=False)}
                }]
        else:
            result_body['messages'] = [{
                'role': 'user',
                'content': {'type': 'text', 'text': dumps(ret, ensure_ascii=False)}
            }]
        return self.create_response(request_id, result_body, None)

    @staticmethod
    def _parse_args_descriptions(doc: str | None) -> dict[str, str]:
        """Parse the Args: section of a docstring to extract parameter descriptions.

        Returns a dict mapping parameter name to its one-line description.
        Multi-line continuations (indented deeper) are folded into the
        preceding parameter's description.
        """
        if not doc:
            return {}
        lines = doc.splitlines()
        in_args = False
        descs: dict[str, str] = {}
        current_name: str | None = None
        # Detect the indentation of the first param line to distinguish
        # param lines from continuation/sub-list lines.
        param_indent: int | None = None
        for line in lines:
            stripped = line.strip()
            if stripped in ("Args:", "Arguments:"):
                in_args = True
                continue
            if not in_args:
                continue
            # Blank line inside Args is OK (may separate groups)
            if not stripped:
                continue
            indent = len(line) - len(line.lstrip())
            # Section headers like "Returns:" are at indent 0
            if indent == 0 and stripped.endswith(":"):
                break
            # Once we know the param indent, lines indented deeper are continuations
            if param_indent is not None and indent > param_indent:
                # Sub-list / continuation — fold into current param description
                if current_name and not stripped.startswith("-"):
                    descs[current_name] += " " + stripped
                continue
            # Try to parse as "param_name: description"
            if ":" in stripped and not stripped.startswith("-"):
                colon_pos = stripped.index(":")
                candidate = stripped[:colon_pos].strip()
                if candidate.isidentifier():
                    if param_indent is None:
                        param_indent = indent
                    desc = stripped[colon_pos + 1:].strip()
                    # Remove trailing colon that introduces a sub-list
                    if desc.endswith(":"):
                        desc = desc[:-1].strip()
                    descs[candidate] = desc
                    current_name = candidate
                    continue
            # Unknown line at param indent level — stop parsing
            if param_indent is not None and indent <= param_indent:
                break
        return descs

    def _extract_parameters_from_signature(self, sig: Signature, method) -> dict[str, Any]:
        """Extract parameter schema from method signature and type hints (parity with sync server)."""
        try:
            type_hints = get_type_hints(method)
        except (NameError, AttributeError, TypeError):
            type_hints = {}
        params = [param for name, param in sig.parameters.items() if name != 'self']
        if not params:
            return {}
        # Parse Args: descriptions from docstring
        doc = getdoc(method)
        arg_descs = self._parse_args_descriptions(doc)
        properties = {}
        required = []
        for param in params:
            # Fall back to the raw annotation when get_type_hints() failed (e.g.
            # forward refs that don't resolve at import time).
            param_type = type_hints.get(param.name, param.annotation)
            prop_schema = self._type_to_json_schema(param_type)
            # Add description from docstring if available
            desc = arg_descs.get(param.name)
            if desc:
                prop_schema["description"] = desc
            properties[param.name] = prop_schema

            # Required by signature
            if param.default == Parameter.empty and param.name not in required:
                required.append(param.name)

            # Required by documentation hint (e.g. "(REQUIRED)")
            if desc and re.search(r"\brequired\b", desc, flags=re.IGNORECASE):
                if param.name not in required:
                    required.append(param.name)

        schema = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }

        if required:
            schema["required"] = required

        # Markdown input helper: require at least one of inline markdown or markdown_file.
        if "markdown" in properties and "markdown_file" in properties:
            schema["oneOf"] = [
                {"required": ["markdown"]},
                {"required": ["markdown_file"]},
            ]

        return schema

    def _tool_output_schema(self, method: Any) -> dict[str, Any] | None:
        explicit = getattr(method, "_mcp_output_schema", None)
        if explicit is not None:
            return dict(explicit)
        try:
            type_hints = get_type_hints(method)
        except (NameError, AttributeError, TypeError):
            type_hints = {}
        return_type = type_hints.get("return", signature(method).return_annotation)
        if return_type in (Parameter.empty, Signature.empty, Any):
            return None
        return self._type_to_json_schema(return_type)

    def _type_to_json_schema(self, param_type: Any) -> dict[str, Any]:
        """Convert Python type annotation to JSON schema property."""
        # Untyped parameter (no annotation) -> default to string for MCP clients.
        if param_type is Parameter.empty:
            return {"type": "string"}
        if param_type is Any:
            return {}
        if param_type is None or param_type is type(None):
            return {"type": "null"}
        elif param_type is str:
            return {"type": "string"}
        elif param_type is int:
            return {"type": "integer"}
        elif param_type is float:
            return {"type": "number"}
        elif param_type is bool:
            return {"type": "boolean"}
        elif param_type is list:
            return {"type": "array"}
        elif param_type is dict:
            return {"type": "object"}

        origin = get_origin(param_type)
        args = get_args(param_type)

        # Handle Literal types → JSON Schema enum
        if origin is Literal:
            values = list(args)
            # Infer type from the literal values
            if all(isinstance(v, str) for v in values):
                return {"type": "string", "enum": values}
            elif all(isinstance(v, int) for v in values):
                return {"type": "integer", "enum": values}
            return {"enum": values}

        if isinstance(param_type, type) and issubclass(param_type, Enum):
            values = [member.value for member in param_type]
            if all(isinstance(v, str) for v in values):
                return {"type": "string", "enum": values}
            if all(isinstance(v, int) for v in values):
                return {"type": "integer", "enum": values}
            return {"enum": values}

        # Handle Union types (e.g., Optional[str], str | None, str | int | None)
        is_union = isinstance(param_type, UnionType) or origin is Union
        if is_union:
            # Strip None from the union to find the real types
            non_none_args = [a for a in args if a is not type(None)]
            if len(non_none_args) == 1:
                # Optional[T] — just return T's schema
                return self._type_to_json_schema(non_none_args[0])
            elif len(non_none_args) > 1:
                # Multi-type union (e.g., str | int) — use oneOf
                return {"oneOf": [self._type_to_json_schema(a) for a in non_none_args]}

        # Handle generic types like List[str], Dict[str, Any]
        if origin is list:
            schema: dict[str, Any] = {"type": "array"}
            if args:
                schema["items"] = self._type_to_json_schema(args[0])
            return schema
        elif origin is dict:
            schema = {"type": "object"}
            if len(args) == 2:
                schema["additionalProperties"] = self._type_to_json_schema(args[1])
            return schema

        # Handle TypedDict classes → JSON Schema with typed properties
        try:
            if is_typeddict(param_type):
                td_hints = get_type_hints(param_type)
                td_props = {}
                for field_name, field_type in td_hints.items():
                    td_props[field_name] = self._type_to_json_schema(field_type)
                td_schema: dict[str, Any] = {"type": "object", "properties": td_props}
                td_required = list(getattr(param_type, "__required_keys__", td_hints.keys()))
                if td_required:
                    td_schema["required"] = td_required
                return td_schema
        except TypeError:
            pass

        if isinstance(param_type, type) and is_dataclass(param_type):
            dc_props = {}
            dc_required = []
            dc_hints = get_type_hints(param_type)
            for field in fields(param_type):
                dc_props[field.name] = self._type_to_json_schema(dc_hints.get(field.name, field.type))
                if field.default is MISSING and field.default_factory is MISSING:
                    dc_required.append(field.name)
            dc_schema: dict[str, Any] = {"type": "object", "properties": dc_props, "additionalProperties": False}
            if dc_required:
                dc_schema["required"] = dc_required
            return dc_schema

        # Default to string for unknown types
        return {"type": "string"}

    def _normalise_structured_tool_value(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if is_dataclass(value):
            return {k: self._normalise_structured_tool_value(v) for k, v in asdict(value).items()}
        if isinstance(value, Mapping):
            return {str(k): self._normalise_structured_tool_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._normalise_structured_tool_value(item) for item in value]
        return _STRUCTURED_UNSET

    def _validate_schema_subset(self, value: Any, schema: dict[str, Any], path: str = "$") -> None:
        if not schema:
            return
        if "enum" in schema and value not in schema["enum"]:
            raise ValueError(f"{path} must be one of {schema['enum']}")
        for branch_key in ("oneOf", "anyOf"):
            branches = schema.get(branch_key)
            if isinstance(branches, list) and branches:
                errors = []
                for branch in branches:
                    try:
                        self._validate_schema_subset(value, branch, path)
                        return
                    except ValueError as exc:
                        errors.append(str(exc))
                raise ValueError(errors[0])
        expected_type = schema.get("type")
        if isinstance(expected_type, list):
            errors = []
            for item_type in expected_type:
                try:
                    self._validate_schema_subset(value, {**schema, "type": item_type}, path)
                    return
                except ValueError as exc:
                    errors.append(str(exc))
            raise ValueError(errors[0])
        if expected_type == "null":
            if value is not None:
                raise ValueError(f"{path} must be null")
            return
        if expected_type == "string":
            if not isinstance(value, str):
                raise ValueError(f"{path} must be a string")
            return
        if expected_type == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{path} must be an integer")
            return
        if expected_type == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{path} must be a number")
            return
        if expected_type == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"{path} must be a boolean")
            return
        if expected_type == "array":
            if not isinstance(value, list):
                raise ValueError(f"{path} must be an array")
            item_schema = schema.get("items")
            if isinstance(item_schema, dict):
                for index, item in enumerate(value):
                    self._validate_schema_subset(item, item_schema, f"{path}[{index}]")
            return
        if expected_type == "object" or "properties" in schema or "required" in schema:
            if not isinstance(value, dict):
                raise ValueError(f"{path} must be an object")
            properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
            required = schema.get("required") if isinstance(schema.get("required"), list) else []
            for key in required:
                if key not in value:
                    raise ValueError(f"{path}.{key} is required")
            additional = schema.get("additionalProperties", True)
            for key, item in value.items():
                if key in properties:
                    self._validate_schema_subset(item, properties[key], f"{path}.{key}")
                elif additional is False:
                    raise ValueError(f"{path}.{key} is not allowed")
                elif isinstance(additional, dict):
                    self._validate_schema_subset(item, additional, f"{path}.{key}")
            return

    def _format_tool_result(self, method: Any, content: Any, output_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        output_schema = dict(output_schema) if output_schema is not None else self._tool_output_schema(method)
        structured = self._normalise_structured_tool_value(content)
        if output_schema is not None:
            candidate = structured if structured is not _STRUCTURED_UNSET else content
            self._validate_schema_subset(candidate, output_schema)
        if isinstance(content, str):
            stringified_content = content
        else:
            try:
                stringified_content = dumps(structured if structured is not _STRUCTURED_UNSET else content, ensure_ascii=False)
            except TypeError:
                stringified_content = str(content)
        result = {
            "content": [{
                "type": "text",
                "text": stringified_content
            }]
        }
        if structured is not _STRUCTURED_UNSET and (isinstance(structured, dict) or (output_schema is not None and not isinstance(content, str))):
            result["structuredContent"] = structured
        return result

    def _coerce_value(self, value: Any, param_type: Any) -> Any:
        """Coerce a value to the expected type if needed.

        MCP clients may send numeric values as strings. This method converts
        them to the expected Python types based on type hints.
        """
        if value is None:
            return None

        # Get the actual type for Optional/Union types
        actual_type = param_type
        origin = get_origin(param_type)
        is_union = isinstance(param_type, UnionType) or origin is Union

        if is_union:
            args = get_args(param_type)
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                actual_type = non_none[0]
            elif len(non_none) > 1:
                # Multi-type union (e.g., str | int) — try each non-None type
                for candidate in non_none:
                    if isinstance(value, candidate):
                        return value
                # If value is a string, try coercing to the first numeric type
                if isinstance(value, str):
                    for candidate in non_none:
                        if candidate is int:
                            try:
                                return int(value)
                            except ValueError:
                                continue
                        elif candidate is float:
                            try:
                                return float(value)
                            except ValueError:
                                continue
                return value

        # Coerce string to numeric types
        if isinstance(value, str):
            if actual_type is float:
                try:
                    return float(value)
                except ValueError:
                    return value
            elif actual_type is int:
                try:
                    return int(value)
                except ValueError:
                    return value
            elif actual_type is bool:
                return value.lower() in ('true', '1', 'yes')

        return value

    # ==== Resource discovery & handling ====
    #
    # Mirrors the synchronous implementation in umcp.py.  Resource methods
    # may be ``def`` or ``async def``; the read handler awaits coroutine
    # results.  See umcp.py for the full doc on naming, return-type
    # normalisation, URI templates, and the optional ``_mcp_resource``
    # override attribute.

    _DEFAULT_TEXT_MIME = "text/plain"
    _DEFAULT_BINARY_MIME = "application/octet-stream"

    @staticmethod
    def _resource_uri_template_to_regex(template: str) -> tuple[Any, list[str]]:
        names: list[str] = []
        pattern_parts: list[str] = []
        cursor = 0
        for m in re.finditer(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", template):
            pattern_parts.append(re.escape(template[cursor:m.start()]))
            names.append(m.group(1))
            pattern_parts.append(f"(?P<{m.group(1)}>[^/]+)")
            cursor = m.end()
        pattern_parts.append(re.escape(template[cursor:]))
        return re.compile("^" + "".join(pattern_parts) + "$"), names

    def _default_resource_uri(self, name: str) -> str:
        return f"umcp://{self.__class__.__name__}/{name}"

    def _default_resource_template_uri(self, name: str, params: list[str]) -> str:
        slots = "/".join("{" + p + "}" for p in params)
        base = f"umcp://{self.__class__.__name__}/{name}"
        return f"{base}/{slots}" if slots else base

    def _resource_metadata(self, name: str, method: Any, params: list[str]) -> dict[str, Any]:
        override = (
            getattr(method, "_mcp_resource", None)
            or getattr(method, "_mcp_resource_template", None)
            or {}
        )
        doc = (getdoc(method) or "").strip()
        description = override.get("description") or (doc.splitlines()[0] if doc else None)
        meta: dict[str, Any] = {"name": override.get("name", name)}
        if params:
            meta["uriTemplate"] = override.get("uri_template") or self._default_resource_template_uri(name, params)
        else:
            meta["uri"] = override.get("uri") or self._default_resource_uri(name)
        if override.get("title"):
            meta["title"] = override["title"]
        if description:
            meta["description"] = description
        if override.get("mime_type"):
            meta["mimeType"] = override["mime_type"]
        if override.get("size") is not None:
            meta["size"] = override["size"]
        if override.get("annotations"):
            meta["annotations"] = dict(override["annotations"])
        return meta

    def _iter_resource_methods(self) -> list[tuple[str, Any]]:
        out: list[tuple[str, Any]] = []
        for member_name, method in getmembers(self, predicate=ismethod):
            if member_name.startswith("resource_template_"):
                continue
            if not member_name.startswith("resource_"):
                continue
            out.append((member_name[len("resource_"):], method))
        return out

    def _iter_resource_template_methods(self) -> list[tuple[str, Any, list[str]]]:
        out: list[tuple[str, Any, list[str]]] = []
        for member_name, method in getmembers(self, predicate=ismethod):
            if not member_name.startswith("resource_template_"):
                continue
            sig = signature(method)
            params = [
                p.name for p in sig.parameters.values()
                if p.kind in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY)
            ]
            out.append((member_name[len("resource_template_"):], method, params))
        return out

    def discover_resources(self) -> dict[str, Any]:
        """Return the ``resources/list`` payload for static resources."""
        resources: list[dict[str, Any]] = []
        for name, method in self._iter_resource_methods():
            resources.append(self._resource_metadata(name, method, params=[]))
        for meta, _callable in self._dynamic_resources.values():
            resources.append(dict(meta))
        return {"resources": self._sort_discovery_items(resources, "name", "uri")}

    def discover_resource_templates(self) -> dict[str, Any]:
        """Return the ``resources/templates/list`` payload."""
        templates: list[dict[str, Any]] = []
        for name, method, params in self._iter_resource_template_methods():
            templates.append(self._resource_metadata(name, method, params=params))
        for meta, _callable in self._dynamic_resource_templates:
            templates.append(dict(meta))
        return {"resourceTemplates": self._sort_discovery_items(templates, "name", "uriTemplate")}

    def register_resource(
        self,
        uri: str,
        callable_: Any,
        *,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        mime_type: str | None = None,
        size: int | None = None,
        annotations: dict[str, Any] | None = None,
    ) -> None:
        meta: dict[str, Any] = {"uri": uri, "name": name or uri}
        if title:
            meta["title"] = title
        if description:
            meta["description"] = description
        if mime_type:
            meta["mimeType"] = mime_type
        if size is not None:
            meta["size"] = size
        if annotations:
            meta["annotations"] = dict(annotations)
        self._dynamic_resources[uri] = (meta, callable_)

    def register_resource_template(
        self,
        uri_template: str,
        callable_: Any,
        *,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        mime_type: str | None = None,
        annotations: dict[str, Any] | None = None,
    ) -> None:
        meta: dict[str, Any] = {"uriTemplate": uri_template, "name": name or uri_template}
        if title:
            meta["title"] = title
        if description:
            meta["description"] = description
        if mime_type:
            meta["mimeType"] = mime_type
        if annotations:
            meta["annotations"] = dict(annotations)
        self._dynamic_resource_templates.append((meta, callable_))

    def _normalise_resource_content(
        self, uri: str, default_mime: str | None, value: Any
    ) -> list[dict[str, Any]]:
        if isinstance(value, (bytes, bytearray, memoryview)):
            data = bytes(value)
            return [{
                "uri": uri,
                "mimeType": default_mime or self._DEFAULT_BINARY_MIME,
                "blob": b64encode(data).decode("ascii"),
            }]
        if isinstance(value, str):
            return [{
                "uri": uri,
                "mimeType": default_mime or self._DEFAULT_TEXT_MIME,
                "text": value,
            }]
        if isinstance(value, dict):
            entry = dict(value)
            entry.setdefault("uri", uri)
            if default_mime and "mimeType" not in entry:
                entry["mimeType"] = default_mime
            return [entry]
        if isinstance(value, list):
            out = []
            for item in value:
                if isinstance(item, dict):
                    entry = dict(item)
                    entry.setdefault("uri", uri)
                    if default_mime and "mimeType" not in entry:
                        entry["mimeType"] = default_mime
                    out.append(entry)
                else:
                    out.extend(self._normalise_resource_content(uri, default_mime, item))
            return out
        return [{
            "uri": uri,
            "mimeType": default_mime or self._DEFAULT_TEXT_MIME,
            "text": str(value),
        }]

    def handle_resources_list(
        self, request_id: int | str | None, params: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            result = self._page_list(
                label="resources",
                items=self.discover_resources()["resources"],
                result_key="resources",
                identity_keys=("uri", "name"),
                params=params,
            )
        except ValueError as exc:
            return self.create_response(request_id, None, self.create_error(-32602, str(exc)))
        return self.create_response(request_id, result)

    def handle_resources_templates_list(
        self, request_id: int | str | None, params: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            result = self._page_list(
                label="resourceTemplates",
                items=self.discover_resource_templates()["resourceTemplates"],
                result_key="resourceTemplates",
                identity_keys=("uriTemplate", "name"),
                params=params,
            )
        except ValueError as exc:
            return self.create_response(request_id, None, self.create_error(-32602, str(exc)))
        return self.create_response(request_id, result)

    async def _maybe_await(self, value: Any) -> Any:
        if iscoroutinefunction(value):
            value = value()
        if hasattr(value, "__await__"):
            return await value
        return value

    async def handle_resources_read_async(
        self, request_id: int | str | None, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle ``resources/read`` -- supports both sync and async resource methods."""
        uri = params.get("uri")
        if not uri:
            error = self.create_error(-32602, "Missing 'uri' parameter")
            return self.create_response(request_id, None, error)

        async def call(method: Any, **kwargs: Any) -> Any:
            result = method(**kwargs)
            if hasattr(result, "__await__"):
                result = await result
            return result

        for name, method in self._iter_resource_methods():
            meta = self._resource_metadata(name, method, params=[])
            if meta["uri"] == uri:
                try:
                    value = await call(method)
                except (MCPRequestCancelled, CancelledError):
                    raise
                except Exception as exc:  # noqa: BLE001
                    self.logger.exception("Resource %s raised", uri)
                    return self.create_response(
                        request_id, None,
                        self.create_error(
                            -32603,
                            self._remote_safe_failure("Resource read failed", f"Resource read failed: {exc}"),
                        ),
                    )
                contents = self._normalise_resource_content(uri, meta.get("mimeType"), value)
                return self.create_response(request_id, {"contents": contents})

        if uri in self._dynamic_resources:
            meta, fn = self._dynamic_resources[uri]
            try:
                value = await call(fn)
            except (MCPRequestCancelled, CancelledError):
                raise
            except Exception as exc:  # noqa: BLE001
                self.logger.exception("Resource %s raised", uri)
                return self.create_response(
                    request_id, None,
                    self.create_error(
                        -32603,
                        self._remote_safe_failure("Resource read failed", f"Resource read failed: {exc}"),
                    ),
                )
            contents = self._normalise_resource_content(uri, meta.get("mimeType"), value)
            return self.create_response(request_id, {"contents": contents})

        for name, method, params_list in self._iter_resource_template_methods():
            meta = self._resource_metadata(name, method, params=params_list)
            regex, _ = self._resource_uri_template_to_regex(meta["uriTemplate"])
            m = regex.match(uri)
            if m:
                try:
                    value = await call(method, **m.groupdict())
                except (MCPRequestCancelled, CancelledError):
                    raise
                except Exception as exc:  # noqa: BLE001
                    self.logger.exception("Resource template %s raised", uri)
                    return self.create_response(
                        request_id, None,
                        self.create_error(
                            -32603,
                            self._remote_safe_failure("Resource read failed", f"Resource read failed: {exc}"),
                        ),
                    )
                contents = self._normalise_resource_content(uri, meta.get("mimeType"), value)
                return self.create_response(request_id, {"contents": contents})

        for meta, fn in self._dynamic_resource_templates:
            regex, _ = self._resource_uri_template_to_regex(meta["uriTemplate"])
            m = regex.match(uri)
            if m:
                try:
                    value = await call(fn, **m.groupdict())
                except (MCPRequestCancelled, CancelledError):
                    raise
                except Exception as exc:  # noqa: BLE001
                    self.logger.exception("Resource template %s raised", uri)
                    return self.create_response(
                        request_id, None,
                        self.create_error(
                            -32603,
                            self._remote_safe_failure("Resource read failed", f"Resource read failed: {exc}"),
                        ),
                    )
                contents = self._normalise_resource_content(uri, meta.get("mimeType"), value)
                return self.create_response(request_id, {"contents": contents})

        return self.create_response(
            request_id, None,
            self.create_error(-32002, "Resource not found", data={"uri": uri}),
        )

    def handle_resources_subscribe(
        self, request_id: int | str | None, params: dict[str, Any]
    ) -> dict[str, Any]:
        uri = params.get("uri")
        if not uri:
            return self.create_response(
                request_id, None,
                self.create_error(-32602, "Missing 'uri' parameter"),
            )
        session_id = params.get("_session_id")
        if isinstance(session_id, str) and session_id:
            self._resource_session_subscriptions.setdefault(session_id, set()).add(uri)
        else:
            self._resource_subscriptions.add(uri)
        return self.create_response(request_id, {})

    def handle_resources_unsubscribe(
        self, request_id: int | str | None, params: dict[str, Any]
    ) -> dict[str, Any]:
        uri = params.get("uri")
        if not uri:
            return self.create_response(
                request_id, None,
                self.create_error(-32602, "Missing 'uri' parameter"),
            )
        session_id = params.get("_session_id")
        if isinstance(session_id, str) and session_id:
            if session_id in self._resource_session_subscriptions:
                self._resource_session_subscriptions[session_id].discard(uri)
                if not self._resource_session_subscriptions[session_id]:
                    self._resource_session_subscriptions.pop(session_id, None)
        else:
            self._resource_subscriptions.discard(uri)
        return self.create_response(request_id, {})

    @staticmethod
    def _disconnect_streamable_http_session(session: _AsyncStreamableHTTPSession) -> None:
        session.disconnect_event.set()
        try:
            session.queue.put_nowait(b"")
        except QueueFull:
            try:
                session.queue.get_nowait()
            except QueueEmpty:
                pass
            session.queue.put_nowait(b"")

    def _expire_streamable_http_sessions(self, now: float) -> None:
        expired = [
            session_id
            for session_id, session in self._streamable_http_sessions.items()
            if now - session.last_seen >= self.streamable_http_session_ttl_seconds
        ]
        for session_id in expired:
            session = self._streamable_http_sessions.pop(session_id)
            self._disconnect_streamable_http_session(session)
            self._resource_session_subscriptions.pop(session_id, None)
            self.logger.info("Streamable HTTP session %s expired", session_id)

    async def _send_notification_async(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        session_ids: set[str] | None = None,
    ) -> None:
        """Emit a JSON-RPC notification on the active transport.

        SSE: write to every connected session's StreamWriter, or a targeted
        subset for per-session resource subscriptions. Stdio / TCP / file mode:
        write one newline-delimited message to stdout.
        """
        notification: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            notification["params"] = params
        payload_text = dumps(notification)

        sse_blob = f"event: message\ndata: {payload_text}\n\n".encode()
        delivered_to_http = False
        if self._sse_sessions:
            target_items = list(self._sse_sessions.items())
            if session_ids is not None:
                target_items = [item for item in target_items if item[0] in session_ids]
            for sid, (writer, _evt, write_lock, _owner) in target_items:
                try:
                    async with write_lock:
                        writer.write(sse_blob)
                        await writer.drain()
                    delivered_to_http = True
                except Exception:  # noqa: BLE001
                    self.logger.debug("Dropping notification for stale SSE session %s", sid)

        if self._streamable_http_active:
            self._expire_streamable_http_sessions(monotonic())
            target_items = list(self._streamable_http_sessions.items())
            if session_ids is not None:
                target_items = [item for item in target_items if item[0] in session_ids]
            for sid, session in target_items:
                if session.writer is None:
                    continue
                try:
                    session.queue.put_nowait(sse_blob)
                    delivered_to_http = True
                except QueueFull:
                    self.logger.warning(
                        "Dropping Streamable HTTP notification because session %s queue is full",
                        sid,
                    )
            return

        if delivered_to_http:
            return

        try:
            _stdout_bin.write((payload_text + "\n").encode("utf-8"))
            _stdout_bin.flush()
        except Exception:  # noqa: BLE001
            self.logger.exception("Failed to emit notification %s", method)

    async def notify_tool_list_changed(self) -> None:
        """Tell connected clients the tool list has changed."""
        await self._send_notification_async("notifications/tools/list_changed")

    async def notify_prompt_list_changed(self) -> None:
        """Tell connected clients the prompt list has changed."""
        await self._send_notification_async("notifications/prompts/list_changed")

    async def notify_resource_list_changed(self) -> None:
        """Tell connected clients the resource list has changed."""
        await self._send_notification_async("notifications/resources/list_changed")

    async def notify_resource_updated(self, uri: str) -> None:
        """Tell subscribed clients that *uri* has changed."""
        target_sessions = {
            session_id
            for session_id, uris in self._resource_session_subscriptions.items()
            if uri in uris
        }
        if target_sessions:
            await self._send_notification_async(
                "notifications/resources/updated", {"uri": uri}, session_ids=target_sessions,
            )
        elif uri in self._resource_subscriptions:
            await self._send_notification_async(
                "notifications/resources/updated", {"uri": uri},
            )

    _LOG_LEVELS = ("debug", "info", "notice", "warning", "error", "critical", "alert", "emergency")
    _SECRET_KEY_PATTERN = re.compile(r"(?:pass(word)?|secret|token|api[_-]?key|auth(orization)?|cookie|session|credential)", re.IGNORECASE)
    _SECRET_VALUE_PATTERN = re.compile(r"(?i)(bearer\s+[A-Za-z0-9._~+/=-]+|sk-[A-Za-z0-9]+|api[_-]?key\s*[:=]\s*\S+|token\s*[:=]\s*\S+)")

    def _should_emit_log_message(self, level: str) -> bool:
        return self._LOG_LEVELS.index(level) >= self._LOG_LEVELS.index(self.logging_level)

    def _sanitize_log_data(self, data: Any) -> Any:
        if isinstance(data, dict):
            return {
                str(key): ("[redacted]" if self._SECRET_KEY_PATTERN.search(str(key)) else self._sanitize_log_data(value))
                for key, value in data.items()
            }
        if isinstance(data, list):
            return [self._sanitize_log_data(item) for item in data]
        if isinstance(data, tuple):
            return [self._sanitize_log_data(item) for item in data]
        if isinstance(data, str):
            return self._SECRET_VALUE_PATTERN.sub("[redacted]", data)
        return data

    def handle_logging_set_level(self, request_id: str | int | None, params: dict[str, Any]) -> dict[str, Any]:
        level = params.get("level")
        if not isinstance(level, str) or level not in self._LOG_LEVELS:
            return self.create_response(request_id, None, self.create_error(-32602, "Invalid params: 'level' must be one of debug, info, notice, warning, error, critical, alert, emergency"))
        self.logging_level = level
        return self.create_response(request_id, {})

    async def notify_log_message(self, level: str, data: Any, *, logger: str | None = None, sanitize: bool = True) -> None:
        if level not in self._LOG_LEVELS or not self._should_emit_log_message(level):
            return
        params: dict[str, Any] = {"level": level, "data": self._sanitize_log_data(data) if sanitize else data}
        if logger:
            params["logger"] = logger
        await self._send_notification_async("notifications/message", params)

    async def log_message(self, level: str, data: Any, *, logger: str | None = None, sanitize: bool = True) -> None:
        await self.notify_log_message(level, data, logger=logger, sanitize=sanitize)

    # ==== Protocol handlers ====

    def handle_initialize(self, request_id: str | int | None, params: dict[str, Any]) -> dict[str, Any]:
        """Handle initialize request."""
        config = self.get_config()
        config["protocolVersion"] = exact_or_fallback(
            params.get("protocolVersion"), SUPPORTED_PROTOCOL_VERSIONS[0]
        )
        return self.create_response(request_id, config)

    def handle_tools_list(self, request_id: str | int | None, params: dict[str, Any]) -> dict[str, Any]:
        """Handle tools/list request with optional cursor pagination."""
        try:
            result = self._page_list(
                label="tools",
                items=self.discover_tools()["tools"],
                result_key="tools",
                identity_keys=("name",),
                params=params,
            )
        except ValueError as exc:
            return self.create_response(request_id, None, self.create_error(-32602, str(exc)))
        return self.create_response(request_id, result)

    async def handle_tools_call_async(self, request_id: int, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``tools/call`` asynchronously."""
        import traceback

        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        self.logger.info("TOOL CALL: %s with args: %s", tool_name, list(arguments.keys()) if arguments else [])

        if not tool_name:
            error = self.create_error(-32602, "Missing 'name' parameter")
            return self.create_response(request_id, None, error)

        method_name = f"tool_{tool_name}"
        output_schema: dict[str, Any] | None = None
        if tool_name in self._dynamic_tools:
            meta, method = self._dynamic_tools[tool_name]
            raw_output_schema = meta.get("outputSchema")
            if isinstance(raw_output_schema, dict):
                output_schema = raw_output_schema
        else:
            method = getattr(self, method_name, None)
        if not method or not callable(method):
            error = self.create_error(-32601, f"Tool not found: {tool_name}")
            return self.create_response(request_id, None, error)

        sig = signature(method)
        self.logger.info("TOOL DISPATCH: %s signature: %s", tool_name, sig)

        params_list = [p for name, p in sig.parameters.items() if name != 'self']
        allowed_params = {
            param_name for param_name in sig.parameters
            if param_name != 'self'
        }
        unknown_params = sorted(
            key for key in arguments
            if key not in allowed_params
        )
        if unknown_params:
            error = self.create_error(
                -32602, "Unrecognized parameter(s): " + ", ".join(unknown_params)
            )
            return self.create_response(request_id, None, error)

        try:
            type_hints = get_type_hints(method)
        except (NameError, AttributeError, TypeError):
            type_hints = {}

        try:
            if len(params_list) == 0:
                self.logger.info("TOOL EXEC: %s (no params, async=%s)", tool_name, iscoroutinefunction(method))
                if iscoroutinefunction(method):
                    content = await method()
                else:
                    ctx = copy_context()
                    content = await get_event_loop().run_in_executor(None, lambda: ctx.run(method))
            else:
                kwargs = {}
                for param_name, param in sig.parameters.items():
                    if param_name == 'self':
                        continue

                    if param_name in arguments:
                        value = arguments[param_name]
                        if param_name in type_hints:
                            value = self._coerce_value(value, type_hints[param_name])
                        kwargs[param_name] = value
                    elif param.default != Parameter.empty:
                        kwargs[param_name] = param.default
                    else:
                        raise ValueError(f"Required parameter '{param_name}' is missing")

                self.logger.info("TOOL EXEC: %s with kwargs: %s (async=%s)", tool_name, list(kwargs.keys()), iscoroutinefunction(method))
                if iscoroutinefunction(method):
                    content = await method(**kwargs)
                else:
                    ctx = copy_context()
                    content = await get_event_loop().run_in_executor(
                        None, lambda: ctx.run(method, **kwargs)
                    )
        except ValueError as e:
            return self.create_response(request_id, None, self.create_error(-32602, str(e)))
        except (MCPRequestCancelled, CancelledError):
            raise
        except Exception as e:
            tb = traceback.format_exc()
            self.logger.error("TOOL ERROR: %s failed with %s: %s\n%s", tool_name, type(e).__name__, e, tb)
            message = self._remote_safe_failure(
                "Tool execution failed",
                f"Tool execution error for {tool_name}: {type(e).__name__}: {str(e)}",
            )
            error = self.create_error(-32603, message)
            return self.create_response(request_id, None, error)

        self.logger.info("TOOL SUCCESS: %s returned type: %s", tool_name, type(content).__name__)

        try:
            result = self._format_tool_result(method, content, output_schema=output_schema)
        except ValueError as exc:
            message = self._remote_safe_failure(
                "Tool output validation failed",
                f"Tool output validation failed for {tool_name}: {exc}",
            )
            return self.create_response(request_id, None, self.create_error(-32603, message))

        return self.create_response(request_id, result)

    # ==== JSON-RPC utilities ====

    def create_response(self, request_id: int | str | None, result: dict[str, Any] | None = None,
                        error: dict[str, Any] | None = None) -> dict[str, Any]:
        """Create a JSON-RPC 2.0 response."""
        response = {
            "jsonrpc": "2.0",
            "id": request_id
        }

        if error is not None:
            response["error"] = error
        else:
            response["result"] = result

        return response

    def create_error(self, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
        """Create a JSON-RPC 2.0 error object."""
        error = {
            "code": code,
            "message": message
        }
        if data is not None:
            error["data"] = data
        return error

    @staticmethod
    def _remote_safe_failure(public_message: str, detailed_message: str) -> str:
        transport = get_request_context().transport
        if transport in {"streamable-http", "sse", "tcp"}:
            return public_message
        return detailed_message

    def authenticate_request(self, *, method: str, path: str, headers: Mapping[str, str], peer: str | None) -> MCPPrincipal | None:
        legacy = type(self).authenticate
        if legacy is not AsyncMCPServer.authenticate:
            return legacy(self, headers, peer)
        return MCPPrincipal(name="anonymous")

    def authorize_request(self, principal: MCPPrincipal | None, *, rpc_method: str | None, tool_name: str | None) -> bool:
        legacy = type(self).authorize
        if legacy is not AsyncMCPServer.authorize:
            params: Mapping[str, Any] = {"name": tool_name} if tool_name is not None else {}
            return legacy(self, principal, rpc_method, params)
        return True

    def handle_http_request(self, *, method: str, path: str, headers: Mapping[str, str], body: bytes, peer: str | None) -> MCPHTTPResponse | None:
        return None

    # Back-compat aliases.
    def authenticate(self, headers: Mapping[str, str], peer: Any) -> MCPPrincipal | None:
        request_hook = type(self).authenticate_request
        if request_hook is not AsyncMCPServer.authenticate_request:
            result = request_hook(self, method="", path="", headers=headers, peer=str(peer) if peer is not None else None)
            if isawaitable(result):
                close = getattr(result, "close", None)
                if close:
                    close()
                raise TypeError("async authentication hook requires authenticate_async()")
            return result
        return MCPPrincipal(name="anonymous")

    def authorize(self, principal: MCPPrincipal | None, method: str | None, params: Mapping[str, Any]) -> bool:
        request_hook = type(self).authorize_request
        if request_hook is not AsyncMCPServer.authorize_request:
            result = request_hook(self, principal, rpc_method=method, tool_name=(params.get("name") if isinstance(params, Mapping) else None))
            if isawaitable(result):
                close = getattr(result, "close", None)
                if close:
                    close()
                raise TypeError("async authorization hook requires authorize_async()")
            return result
        return True

    async def authenticate_request_async(self, *, method: str, path: str, headers: Mapping[str, str], peer: str | None) -> MCPPrincipal | None:
        result = self.authenticate_request(method=method, path=path, headers=headers, peer=peer)
        return await result if isawaitable(result) else result

    async def authorize_request_async(self, principal: MCPPrincipal | None, *, rpc_method: str | None, tool_name: str | None) -> bool:
        result = self.authorize_request(principal, rpc_method=rpc_method, tool_name=tool_name)
        return await result if isawaitable(result) else result

    async def handle_http_request_async(self, *, method: str, path: str, headers: Mapping[str, str], body: bytes, peer: str | None) -> MCPHTTPResponse | None:
        result = self.handle_http_request(method=method, path=path, headers=headers, body=body, peer=peer)
        return await result if isawaitable(result) else result

    async def authenticate_async(self, headers: Mapping[str, str], peer: Any) -> MCPPrincipal | None:
        result = self.authenticate_request(
            method="", path="", headers=headers,
            peer=str(peer) if peer is not None else None,
        )
        return await result if isawaitable(result) else result

    async def authorize_async(self, principal: MCPPrincipal | None, method: str | None, params: Mapping[str, Any]) -> bool:
        result = self.authorize_request(
            principal, rpc_method=method,
            tool_name=params.get("name") if isinstance(params, Mapping) else None,
        )
        return await result if isawaitable(result) else result

    def _with_request_context(self, *, transport: str | None, request_id: str | int | None, principal: str | None, peer: str | None, headers: dict[str, str], version: str | None, session_id: str | None = None, progress_token: str | int | None = None):
        return set_request_context(MCPRequestContext(transport=transport, request_id=request_id, progress_token=progress_token, protocol_version=version, session_id=session_id, principal=principal, peer=peer, headers=headers))

    @staticmethod
    def _validate_progress_token(value: Any) -> str | int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ValueError("Invalid params: '_meta.progressToken' must be a string or integer")
        return value

    @staticmethod
    def _validate_progress_value(name: str, value: float | int) -> float | int:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"Invalid progress notification: '{name}' must be a finite non-negative number")
        return value

    @staticmethod
    def _sanitize_progress_message(message: str | None) -> str | None:
        if message is None:
            return None
        text = str(message).replace("\x00", "")
        return text[:4096]

    async def _register_request_cancellation(self, request_id: str | int | None, progress_token: str | int | None) -> tuple[MCPCancellationState, dict[str, Any]]:
        state = MCPCancellationState()
        entry = {"state": state, "task": current_task(), "progress_token": progress_token}
        async with self._request_registry_lock:
            if request_id is not None:
                self._active_requests_by_id[request_id] = entry
            if progress_token is not None and request_id is not None:
                self._active_requests_by_progress_token.setdefault(progress_token, set()).add(request_id)
        return state, entry

    async def _cleanup_request_cancellation(self, request_id: str | int | None, progress_token: str | int | None, entry: dict[str, Any]) -> None:
        async with self._request_registry_lock:
            if request_id is not None and self._active_requests_by_id.get(request_id) is entry:
                self._active_requests_by_id.pop(request_id, None)
            if progress_token is not None and request_id is not None:
                request_ids = self._active_requests_by_progress_token.get(progress_token)
                if request_ids is not None:
                    request_ids.discard(request_id)
                    if not request_ids:
                        self._active_requests_by_progress_token.pop(progress_token, None)

    async def _mark_request_cancelled(self, cancel_key: str | int | None) -> None:
        if cancel_key is None or isinstance(cancel_key, bool) or not isinstance(cancel_key, (str, int)):
            return
        async with self._request_registry_lock:
            entries: list[dict[str, Any]] = []
            direct = self._active_requests_by_id.get(cancel_key)
            if direct is not None:
                entries.append(direct)
            for request_id in self._active_requests_by_progress_token.get(cancel_key, ()):
                entry = self._active_requests_by_id.get(request_id)
                if entry is not None and entry not in entries:
                    entries.append(entry)
        for entry in entries:
            state = entry["state"]
            state.mark_cancelled()
            task = entry.get("task")
            if task is not None and not task.done():
                task.cancel()

    def get_progress_token(self) -> str | int | None:
        return _get_progress_token()

    def is_request_cancelled(self) -> bool:
        return _is_request_cancelled()

    def raise_if_cancelled(self) -> None:
        _raise_if_cancelled()

    async def notify_progress(self, progress: float | int, total: float | int | None = None, message: str | None = None) -> None:
        token = self.get_progress_token()
        if token is None:
            return
        progress = self._validate_progress_value("progress", progress)
        params: dict[str, Any] = {"progressToken": token, "progress": progress}
        if total is not None:
            total = self._validate_progress_value("total", total)
            if total < progress:
                raise ValueError("Invalid progress notification: 'total' must be greater than or equal to 'progress'")
            params["total"] = total
        sanitized = self._sanitize_progress_message(message)
        if sanitized:
            params["message"] = sanitized
        await self._send_notification_async("notifications/progress", params)

    def _validate_http_principal(self, principal: MCPPrincipal | None) -> bool:
        return principal is None or isinstance(principal, MCPPrincipal)

    def _validate_http_authorization_result(self, authorized: Any) -> bool:
        return isinstance(authorized, bool)

    def _validate_http_route_response(self, response: Any, *, max_request_bytes: int) -> MCPHTTPResponse | None:
        return validate_http_response(response, max_bytes=max_request_bytes)

    async def process_request_async(
        self, request_data: str, *, context: MCPRequestContext | None = None
    ) -> dict[str, Any] | None:
        """Process a JSON-RPC 2.0 request asynchronously in an isolated context."""
        try:
            request = loads(request_data)
        except JSONDecodeError as e:
            self.logger.error("JSON decode error: %s", e)
            error = self.create_error(-32700, "Parse error")
            return self.create_response(None, None, error)

        if not is_jsonrpc_object(request):
            error = self.create_error(-32600, "Invalid Request: top-level JSON value must be an object")
            return self.create_response(None, None, error)

        # Extract request components
        jsonrpc = request.get("jsonrpc")
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        if params is None:
            params = {}
        elif not isinstance(params, dict):
            return self.create_response(
                request_id, None, self.create_error(-32602, "Invalid params: expected an object")
            )

        self.logger.info("Processing method: %s (id: %s)", method, request_id)

        meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else None
        try:
            progress_token = self._validate_progress_token(meta.get("progressToken") if meta else None)
        except ValueError as exc:
            return self.create_response(request_id, None, self.create_error(-32602, str(exc)))

        # Validate JSON-RPC 2.0 version
        if jsonrpc != "2.0":
            error = self.create_error(-32600, "Invalid Request: Not a JSON-RPC 2.0 request")
            return self.create_response(request_id, None, error)
        if "id" in request and not is_valid_jsonrpc_id(request_id):
            error = self.create_error(-32600, "Invalid Request: invalid id")
            return self.create_response(None, None, error)

        if method is None and ("result" in request or "error" in request):
            valid_response = is_valid_jsonrpc_response(request)
            if valid_response:
                return None  # A client response is acknowledged by the transport.
            error = self.create_error(-32600, "Invalid Request: malformed response")
            return self.create_response(request_id, None, error)
        if not isinstance(method, str):
            error = self.create_error(-32600, "Invalid Request: method must be a string")
            return self.create_response(request_id, None, error)

        if context is None:
            context = MCPRequestContext(request_id=request_id, progress_token=progress_token)
        else:
            context = MCPRequestContext(
                transport=context.transport,
                request_id=request_id,
                progress_token=progress_token,
                protocol_version=context.protocol_version,
                session_id=context.session_id,
                principal=context.principal,
                peer=context.peer,
                headers=context.headers,
            )
        cancellation_state = None
        registry_entry = None
        if request_id is not None:
            cancellation_state, registry_entry = await self._register_request_cancellation(request_id, progress_token)
        runtime_token = set_request_runtime(MCPRequestRuntime(progress_token=progress_token, cancellation=cancellation_state, progress_callback=self.notify_progress))
        token = set_request_context(context)
        try:
            # Process the method
            if method == "notifications/cancelled":
                cancel_id = params.get("requestId")
                if cancel_id is not None and not is_valid_jsonrpc_id(cancel_id):
                    if request_id is None:
                        return None
                    return self.create_response(request_id, None, self.create_error(-32602, "Invalid params: 'requestId' must be a string, integer, or null"))
                await self._mark_request_cancelled(cancel_id)
                return None
            if method == "initialize":
                return self.handle_initialize(request_id, params)
            elif method == "tools/list":
                return self.handle_tools_list(request_id, params)
            elif method == "tools/call":
                return await self.handle_tools_call_async(request_id, params)
            elif method == "prompts/list":
                try:
                    result = self._page_list(
                        label="prompts",
                        items=self.discover_prompts()["prompts"],
                        result_key="prompts",
                        identity_keys=("name",),
                        params=params,
                    )
                except ValueError as exc:
                    return self.create_response(request_id, None, self.create_error(-32602, str(exc)))
                return self.create_response(request_id, result)
            elif method == "prompts/get":
                return await self.handle_prompt_get_async(request_id, params)
            elif method == "resources/list":
                return self.handle_resources_list(request_id, params)
            elif method == "resources/templates/list":
                return self.handle_resources_templates_list(request_id, params)
            elif method == "resources/read":
                return await self.handle_resources_read_async(request_id, params)
            elif method == "resources/subscribe":
                return self.handle_resources_subscribe(request_id, params)
            elif method == "resources/unsubscribe":
                return self.handle_resources_unsubscribe(request_id, params)
            elif method == "completion/complete":
                return await self.handle_completion_complete_async(request_id, params)
            elif method == "logging/setLevel":
                return self.handle_logging_set_level(request_id, params)
            elif method == "notifications/initialized":
                self.logger.info("Host confirmed toolContract reception with 'notifications/initialized'")
                return None
            else:
                error = self.create_error(-32601, f"Method not found: {method}")
                return self.create_response(request_id, None, error)
        except MCPRequestCancelled:
            if request_id is None:
                return None
            return self.create_response(request_id, None, self.create_error(-32800, "Request cancelled"))
        except CancelledError:
            if request_id is None:
                raise
            return self.create_response(request_id, None, self.create_error(-32800, "Request cancelled"))
        finally:
            reset_request_context(token)
            reset_request_runtime(runtime_token)
            if registry_entry is not None:
                await self._cleanup_request_cancellation(request_id, progress_token, registry_entry)

    # ==== Main execution ====

    async def _handle_socket_client(self, reader: StreamReader, writer: StreamWriter) -> None:
        """Handle a single TCP client connection with newline-delimited JSON-RPC."""
        peer = writer.get_extra_info("peername")
        self.logger.info("Socket client connected: %s", peer)
        try:
            while True:
                line = await reader.readline()
                if not line:  # EOF / disconnect
                    break

                line = line.decode().strip()
                if not line:
                    continue

                self.logger.info("SOCKET REQUEST (%s): %s", peer, line)
                peer_name = f"{peer[0]}:{peer[1]}" if isinstance(peer, tuple) and len(peer) >= 2 else str(peer)
                response = await self.process_request_async(
                    line,
                    context=MCPRequestContext(transport="tcp", peer=peer_name),
                )

                if response is not None:
                    payload = dumps(response) + "\n"
                    writer.write(payload.encode())
                    await writer.drain()
        except CancelledError:
            pass
        except Exception as e:  # noqa: BLE001 broad for runtime resilience
            self.logger.error("Socket client %s error: %s", peer, e)
        finally:
            self.logger.info("Socket client disconnected: %s", peer)
            writer.close()
            wait_closed = getattr(writer, "wait_closed", None)
            if wait_closed is not None:
                try:
                    await wait_closed()
                except Exception:
                    pass

    async def run_socket_async(self, host: str = "127.0.0.1", port: int = 0) -> None:
        """Run the MCP server over TCP sockets.

        Listens on *host*:*port* for newline-delimited JSON-RPC connections.
        Each accepted connection is handled concurrently.  When *port* is 0
        the OS assigns an ephemeral port, which is printed to stdout so the
        caller can discover it.
        """
        server = await start_server(self._handle_socket_client, host, port)
        addrs = [s.getsockname() for s in server.sockets]
        for addr in addrs:
            self.logger.info("MCP Socket Server listening on %s:%s", addr[0], addr[1])
            # Print the address to stdout so the parent process can discover it.
            print(f"Listening on {addr[0]}:{addr[1]}", flush=True)

        async with server:
            await server.serve_forever()

    # ---- SSE (Server-Sent Events) HTTP transport ----

    async def _sse_read_http_request(self, reader: StreamReader, *, max_request_bytes: int) -> tuple[str, str, str, dict[str, str], dict[str, int], bytes]:
        request_line = await wait_for(reader.readline(), timeout=30.0)
        if not request_line:
            raise ConnectionError("Client disconnected")
        if len(request_line) > 8192:
            raise ValueError("Request line too long")
        parts = request_line.decode("ascii", errors="strict").strip().split(" ")
        if len(parts) != 3:
            raise ValueError("Malformed request line")
        method, path, http_version = parts
        if http_version not in {"HTTP/1.0", "HTTP/1.1"}:
            raise ValueError("Unsupported HTTP version")
        headers: dict[str, str] = {}
        header_counts: dict[str, int] = {}
        header_bytes = 0
        for _ in range(100):
            line = await wait_for(reader.readline(), timeout=30.0)
            header_bytes += len(line)
            if header_bytes > 65536:
                raise ValueError("headers too large")
            if line in (b"\r\n", b"\n"):
                break
            if not line or b":" not in line:
                raise ValueError("invalid header")
            key, value = line.decode("iso-8859-1").split(":", 1)
            normalized = key.strip().lower()
            headers[normalized] = value.strip()
            header_counts[normalized] = header_counts.get(normalized, 0) + 1
        else:
            raise ValueError("too many headers")
        if (
            has_singleton_header_violations(header_counts, http_version=http_version)
            or has_ambiguous_singleton_values(headers)
        ):
            raise ValueError("invalid singleton header")
        try:
            content_length = int(headers.get("content-length", "0") or "0")
        except ValueError as exc:
            raise ValueError("invalid content-length") from exc
        if content_length < 0:
            raise ValueError("invalid content-length")
        if content_length > max_request_bytes:
            raise OverflowError("request too large")
        body = await wait_for(reader.readexactly(content_length), timeout=30.0) if content_length else b""
        return method, path, http_version, headers, header_counts, body

    async def _sse_handle_client(self, reader: StreamReader, writer: StreamWriter, allowed_origins: list[str], max_request_bytes: int, host: str = "127.0.0.1") -> None:
        peer = writer.get_extra_info("peername")

        async def send_response(status: str, *, body: bytes = b"", content_type: str | None = None, origin: str | None = None, extra_headers: tuple[tuple[str, str], ...] = ()) -> None:
            response = [f"HTTP/1.1 {status}\r\n".encode()]
            if content_type:
                response.append(f"Content-Type: {content_type}\r\n".encode())
            if origin:
                response.append(f"Access-Control-Allow-Origin: {origin}\r\nVary: Origin\r\n".encode())
            for key, value in extra_headers:
                response.append(f"{key}: {value}\r\n".encode())
            response.append(f"Content-Length: {len(body)}\r\n\r\n".encode())
            if body:
                response.append(body)
            writer.write(b"".join(response))
            await writer.drain()

        try:
            try:
                method, path, _http_version, headers, _header_counts, body = await self._sse_read_http_request(reader, max_request_bytes=max_request_bytes)
            except OverflowError:
                await send_response("413 Payload Too Large")
                return
            except (ConnectionError, ValueError, UnicodeError, TimeoutError, IncompleteReadError) as exc:
                self.logger.warning("SSE: bad request from %s: %s", peer, exc)
                await send_response("400 Bad Request")
                return

            origin = headers.get("origin")
            allowed_origin = origin if origin and origin_is_allowed(origin, allowed_origins, local_bind=host in ("127.0.0.1", "localhost", "::1"), request_authority=headers.get("host")) else None
            if origin and not allowed_origin:
                await send_response("403 Forbidden")
                return
            self.logger.info("SSE HTTP %s %s from %s", method, path, peer)

            if method == "OPTIONS":
                if request_target_path(path) not in {"/sse", "/message"}:
                    await send_response("404 Not Found", origin=allowed_origin)
                    return
                if not origin:
                    await send_response("405 Method Not Allowed", origin=allowed_origin, extra_headers=(("Allow", "GET, POST, OPTIONS"),))
                    return
                await send_response("204 No Content", origin=allowed_origin, extra_headers=(("Access-Control-Allow-Methods", "GET, POST, OPTIONS"), ("Access-Control-Allow-Headers", "Content-Type, Accept, Authorization")))
                return

            if method == "GET" and request_target_path(path) == "/sse":
                if not media_accepts_event_stream(headers.get("accept")):
                    await send_response("406 Not Acceptable", origin=allowed_origin)
                    return
                try:
                    principal = await self.authenticate_request_async(method="GET", path=path, headers=headers, peer=peer[0] if peer else None)
                except Exception:
                    self.logger.exception("SSE authentication hook failed for GET %s", path)
                    await send_response("500 Internal Server Error", origin=allowed_origin)
                    return
                if not self._validate_http_principal(principal):
                    self.logger.error("SSE authentication hook returned invalid principal type: %r", type(principal))
                    await send_response("500 Internal Server Error", origin=allowed_origin)
                    return
                if principal is None:
                    await send_response("401 Unauthorized", origin=allowed_origin, extra_headers=(("WWW-Authenticate", "Bearer"),))
                    return
                try:
                    authorized = await self.authorize_request_async(principal, rpc_method=None, tool_name=None)
                except Exception:
                    self.logger.exception("SSE authorization hook failed for GET %s", path)
                    await send_response("500 Internal Server Error", origin=allowed_origin)
                    return
                if not self._validate_http_authorization_result(authorized):
                    self.logger.error("SSE authorization hook returned invalid result type: %r", type(authorized))
                    await send_response("500 Internal Server Error", origin=allowed_origin)
                    return
                if not authorized:
                    await send_response("403 Forbidden", origin=allowed_origin)
                    return
                session_id = str(uuid4())
                self.logger.info("SSE: new session %s from %s", session_id, peer)
                disconnect_event = Event()
                write_lock = Lock()
                self._sse_sessions[session_id] = (writer, disconnect_event, write_lock, principal.name)
                response = [b"HTTP/1.1 200 OK\r\n", b"Content-Type: text/event-stream\r\n", b"Cache-Control: no-cache\r\n", b"Connection: keep-alive\r\n"]
                if allowed_origin:
                    response.append(f"Access-Control-Allow-Origin: {allowed_origin}\r\nVary: Origin\r\n".encode())
                response.append(b"\r\n")
                writer.write(b"".join(response))
                writer.write(f"event: endpoint\ndata: /message?sessionId={session_id}\n\n".encode())
                await writer.drain()
                try:
                    while not disconnect_event.is_set():
                        await sleep(15)
                        if writer.is_closing():
                            break
                        async with write_lock:
                            writer.write(b": keepalive\n\n")
                            await writer.drain()
                except (CancelledError, ConnectionError, OSError):
                    pass
                finally:
                    self._sse_sessions.pop(session_id, None)
                    self._resource_session_subscriptions.pop(session_id, None)
                    self.logger.info("SSE: session %s closed", session_id)
                return

            if method == "POST" and request_target_path(path) == "/message":
                if headers.get("transfer-encoding"):
                    await send_response("400 Bad Request", origin=allowed_origin)
                    return
                if not content_type_is_json(headers.get("content-type")):
                    await send_response("415 Unsupported Media Type", origin=allowed_origin)
                    return
                if not media_accepts_json(headers.get("accept")):
                    await send_response("406 Not Acceptable", origin=allowed_origin)
                    return
                qs = parse_qs(path.split("?", 1)[1] if "?" in path else "")
                session_id = (qs.get("sessionId") or [None])[0]
                try:
                    principal = await self.authenticate_request_async(method="POST", path=path, headers=headers, peer=peer[0] if peer else None)
                except Exception:
                    self.logger.exception("SSE authentication hook failed for POST %s", path)
                    await send_response("500 Internal Server Error", origin=allowed_origin)
                    return
                if not self._validate_http_principal(principal):
                    self.logger.error("SSE authentication hook returned invalid principal type: %r", type(principal))
                    await send_response("500 Internal Server Error", origin=allowed_origin)
                    return
                if principal is None:
                    await send_response("401 Unauthorized", origin=allowed_origin, extra_headers=(("WWW-Authenticate", "Bearer"),))
                    return
                session = self._sse_sessions.get(session_id) if session_id else None
                if session is None:
                    self.logger.warning("SSE: unknown session %s from %s", session_id, peer)
                    await send_response("404 Not Found", origin=allowed_origin)
                    return
                if session[3] != principal.name:
                    await send_response("403 Forbidden", origin=allowed_origin)
                    return
                try:
                    request_data = body.decode("utf-8")
                except UnicodeDecodeError:
                    await send_response("400 Bad Request", origin=allowed_origin)
                    return
                self.logger.info("SSE REQUEST (session %s): %s", session_id, request_data[:200])
                try:
                    request_obj = loads(request_data)
                except JSONDecodeError:
                    request_obj = None
                rpc_method = request_obj.get("method") if isinstance(request_obj, dict) else None
                params = request_obj.get("params") if isinstance(request_obj, dict) and isinstance(request_obj.get("params"), dict) else {}
                tool_name = params.get("name") if rpc_method == "tools/call" else None
                try:
                    authorized = await self.authorize_request_async(principal, rpc_method=rpc_method, tool_name=tool_name)
                except Exception:
                    self.logger.exception("SSE authorization hook failed for rpc_method=%r tool_name=%r", rpc_method, tool_name)
                    await send_response("500 Internal Server Error", origin=allowed_origin)
                    return
                if not self._validate_http_authorization_result(authorized):
                    self.logger.error("SSE authorization hook returned invalid result type: %r", type(authorized))
                    await send_response("500 Internal Server Error", origin=allowed_origin)
                    return
                if not authorized:
                    await send_response("403 Forbidden", origin=allowed_origin)
                    return
                if isinstance(request_obj, dict) and request_obj.get("method") in ("resources/subscribe", "resources/unsubscribe"):
                    request_obj["params"] = dict(params)
                    request_obj["params"]["_session_id"] = session_id
                    request_data = dumps(request_obj)
                if self._sse_sessions.get(session_id) is not session:
                    await send_response("404 Not Found", origin=allowed_origin)
                    return
                sse_writer, _disconnect_event, write_lock, _owner = session
                response = await self.process_request_async(request_data, context=MCPRequestContext(transport="sse", request_id=request_obj.get("id") if isinstance(request_obj, dict) else None, session_id=session_id, principal=principal.name if principal else None, peer=peer[0] if peer else None, headers=headers))
                if response is not None:
                    response_json = dumps(response)
                    try:
                        async with write_lock:
                            sse_writer.write(f"event: message\ndata: {response_json}\n\n".encode())
                            await sse_writer.drain()
                    except (ConnectionError, OSError):
                        self._sse_sessions.pop(session_id, None)
                        await send_response("404 Not Found", origin=allowed_origin)
                        return
                await send_response("202 Accepted", origin=allowed_origin)
                return

            await send_response("404 Not Found", origin=allowed_origin)
        finally:
            if not writer.is_closing():
                writer.close()
            wait_closed = getattr(writer, "wait_closed", None)
            if wait_closed is not None:
                try:
                    await wait_closed()
                except Exception:
                    pass

    async def run_streamable_http_async(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        endpoint: str = "/mcp",
        allowed_origins: list[str] | None = None,
        max_request_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        allowed_origins = allowed_origins or []
        if host not in ("127.0.0.1", "localhost", "::1") and type(self).authenticate_request is AsyncMCPServer.authenticate_request and type(self).authenticate is AsyncMCPServer.authenticate:
            self.logger.warning("Streamable HTTP is bound beyond loopback without an authentication hook")
        server = await start_server(lambda r, w: self._handle_streamable_http_client(r, w, endpoint, allowed_origins, max_request_bytes, host), host, port)
        addrs = [s.getsockname() for s in server.sockets]
        for addr in addrs:
            print(f"MCP Streamable HTTP Server listening on http://{addr[0]}:{addr[1]}{endpoint}", flush=True)
        self._streamable_http_active = True
        try:
            async with server:
                await server.serve_forever()
        finally:
            self._streamable_http_active = False
            for session in self._streamable_http_sessions.values():
                self._disconnect_streamable_http_session(session)
            self._streamable_http_sessions.clear()

    async def _handle_streamable_http_client(self, reader: StreamReader, writer: StreamWriter, endpoint: str, allowed_origins: list[str], max_request_bytes: int, host: str = "127.0.0.1") -> None:
        peer = writer.get_extra_info("peername")

        async def handle_one_request(request_number: int) -> bool:
            keep_alive = False
            request_version = "HTTP/1.1"

            async def send_response(
                status: str,
                *,
                body: bytes = b"",
                content_type: str | None = None,
                allow: str | None = None,
                www_authenticate: str | None = None,
                origin: str | None = None,
                extra_headers: tuple[tuple[str, str], ...] = (),
                force_close: bool = False,
                streaming: bool = False,
            ) -> None:
                nonlocal keep_alive
                if force_close or request_number >= self.streamable_http_max_requests_per_connection:
                    keep_alive = False
                response = [f"HTTP/1.1 {status}\r\n".encode()]
                if content_type:
                    response.append(f"Content-Type: {content_type}\r\n".encode())
                if allow:
                    response.append(f"Allow: {allow}\r\n".encode())
                if www_authenticate:
                    response.append(f"WWW-Authenticate: {www_authenticate}\r\n".encode())
                if origin:
                    response.append(f"Access-Control-Allow-Origin: {origin}\r\n".encode())
                    response.append(b"Access-Control-Expose-Headers: Mcp-Session-Id\r\n")
                    response.append(b"Vary: Origin\r\n")
                for key, value in extra_headers:
                    response.append(f"{key}: {value}\r\n".encode())
                if not keep_alive:
                    response.append(b"Connection: close\r\n")
                elif request_version == "HTTP/1.0":
                    response.append(b"Connection: keep-alive\r\n")
                if not streaming:
                    response.append(f"Content-Length: {len(body)}\r\n".encode())
                response.append(b"\r\n")
                if body:
                    response.append(body)
                writer.write(b"".join(response))
                await writer.drain()

            async def send_json(
                payload: dict[str, Any],
                status: str = "200 OK",
                *,
                origin: str | None = None,
                extra_headers: tuple[tuple[str, str], ...] = (),
            ) -> None:
                await send_response(
                    status,
                    body=dumps(payload).encode(),
                    content_type="application/json",
                    origin=origin,
                    extra_headers=extra_headers,
                )

            try:
                request_line = await wait_for(
                    reader.readline(),
                    timeout=self.streamable_http_request_timeout_seconds,
                )
            except (TimeoutError, ConnectionError, OSError):
                return False
            if not request_line:
                return False
            if len(request_line) > 8192:
                await send_response("414 URI Too Long", force_close=True)
                return False
            try:
                method, target, request_version = request_line.decode("ascii").strip().split()
            except (UnicodeDecodeError, ValueError):
                await send_response("400 Bad Request", force_close=True)
                return False
            if request_version not in ("HTTP/1.0", "HTTP/1.1"):
                await send_response("400 Bad Request", force_close=True)
                return False

            header_lines: list[bytes] = []
            total_header_bytes = 0
            while True:
                try:
                    line = await wait_for(
                        reader.readline(),
                        timeout=self.streamable_http_request_timeout_seconds,
                    )
                except (TimeoutError, ConnectionError, OSError):
                    await send_response("400 Bad Request", force_close=True)
                    return False
                total_header_bytes += len(line)
                if not line or total_header_bytes > 65536 or len(header_lines) > 100:
                    await send_response("400 Bad Request", force_close=True)
                    return False
                if line in (b"\r\n", b"\n"):
                    break
                if line[:1] in (b" ", b"\t"):
                    await send_response("400 Bad Request", force_close=True)
                    return False
                header_lines.append(line)

            headers: dict[str, str] = {}
            header_counts: dict[str, int] = {}
            try:
                for line in header_lines:
                    name_raw, value_raw = line.split(b":", 1)
                    name = name_raw.decode("ascii").strip().lower()
                    if not name:
                        raise ValueError
                    value = value_raw.decode("iso-8859-1").strip()
                    header_counts[name] = header_counts.get(name, 0) + 1
                    headers[name] = f"{headers[name]}, {value}" if name in headers else value
            except (UnicodeDecodeError, ValueError):
                await send_response("400 Bad Request", force_close=True)
                return False

            connection_tokens = {
                token.strip().lower()
                for token in headers.get("connection", "").split(",")
                if token.strip()
            }
            keep_alive = (
                request_version == "HTTP/1.1" and "close" not in connection_tokens
            ) or (
                request_version == "HTTP/1.0"
                and "keep-alive" in connection_tokens
                and "close" not in connection_tokens
            )
            origin = headers.get("origin")
            allowed_origin = None
            if origin and header_counts.get("origin") == 1:
                if origin_is_allowed(
                    origin,
                    allowed_origins,
                    local_bind=host in ("127.0.0.1", "localhost", "::1"),
                    request_authority=headers.get("host"),
                ):
                    allowed_origin = origin
            if (
                has_singleton_header_violations(header_counts, http_version=request_version)
                or has_ambiguous_singleton_values(headers)
                or "transfer-encoding" in headers
            ):
                await send_response("400 Bad Request", origin=allowed_origin, force_close=True)
                return False
            if origin and not allowed_origin:
                await send_response("403 Forbidden", force_close=True)
                return False

            try:
                content_length = int(headers.get("content-length", "0"))
            except ValueError:
                await send_response("400 Bad Request", origin=allowed_origin, force_close=True)
                return False
            if content_length < 0:
                await send_response("400 Bad Request", origin=allowed_origin, force_close=True)
                return False
            if content_length > max_request_bytes:
                await send_response("413 Payload Too Large", origin=allowed_origin, force_close=True)
                return False
            try:
                body = (
                    await wait_for(
                        reader.readexactly(content_length),
                        timeout=self.streamable_http_request_timeout_seconds,
                    )
                    if content_length
                    else b""
                )
            except (IncompleteReadError, TimeoutError, ConnectionError, OSError):
                await send_response("400 Bad Request", origin=allowed_origin, force_close=True)
                return False

            path = request_target_path(target)
            if path != endpoint:
                try:
                    response = await self.handle_http_request_async(
                        method=method,
                        path=path,
                        headers=headers,
                        body=body,
                        peer=peer[0] if peer else None,
                    )
                except Exception:
                    self.logger.exception("HTTP auxiliary route hook failed for %s %s", method, path)
                    await send_response("500 Internal Server Error", origin=allowed_origin)
                    return keep_alive
                if response is None:
                    await send_response(
                        "405 Method Not Allowed",
                        allow="GET, POST, DELETE, OPTIONS",
                        origin=allowed_origin,
                    )
                    return keep_alive
                validated = self._validate_http_route_response(response, max_request_bytes=max_request_bytes)
                if validated is None:
                    self.logger.error("HTTP auxiliary route hook returned invalid response: %r", response)
                    await send_response("500 Internal Server Error", origin=allowed_origin)
                    return keep_alive
                await send_response(
                    http_status_line(validated.status),
                    body=validated.body,
                    content_type=validated.content_type,
                    origin=allowed_origin,
                    extra_headers=validated.headers,
                )
                return keep_alive

            if method == "OPTIONS":
                if not origin:
                    await send_response(
                        "405 Method Not Allowed",
                        allow="GET, POST, DELETE, OPTIONS",
                        origin=allowed_origin,
                    )
                    return keep_alive
                await send_response(
                    "204 No Content",
                    origin=allowed_origin,
                    extra_headers=(
                        ("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS"),
                        ("Access-Control-Allow-Headers", "Content-Type, Accept, MCP-Protocol-Version, Mcp-Session-Id, Last-Event-ID, Authorization"),
                    ),
                )
                return keep_alive

            if method not in ("GET", "POST", "DELETE"):
                await send_response(
                    "405 Method Not Allowed",
                    allow="GET, POST, DELETE, OPTIONS",
                    origin=allowed_origin,
                )
                return keep_alive

            try:
                principal = await self.authenticate_request_async(
                    method=method,
                    path=target,
                    headers=headers,
                    peer=peer[0] if peer else None,
                )
            except Exception:
                self.logger.exception("HTTP authentication hook failed for %s %s", method, target)
                await send_response("500 Internal Server Error", origin=allowed_origin)
                return keep_alive
            if not self._validate_http_principal(principal):
                self.logger.error("HTTP authentication hook returned invalid principal type: %r", type(principal))
                await send_response("500 Internal Server Error", origin=allowed_origin)
                return keep_alive
            if principal is None:
                await send_response(
                    "401 Unauthorized",
                    www_authenticate="Bearer",
                    origin=allowed_origin,
                )
                return keep_alive

            async def validated_session(
                protocol_version: str,
                *,
                required: bool,
            ) -> tuple[str, _AsyncStreamableHTTPSession] | None:
                session_id = headers.get("mcp-session-id")
                if not session_id:
                    if required:
                        await send_response("400 Bad Request", origin=allowed_origin)
                    return None
                self._expire_streamable_http_sessions(monotonic())
                session = self._streamable_http_sessions.get(session_id)
                if session is None:
                    await send_response("404 Not Found", origin=allowed_origin)
                    return None
                if session.principal != principal.name:
                    await send_response("403 Forbidden", origin=allowed_origin)
                    return None
                if session.protocol_version != protocol_version:
                    await send_json(protocol_version_error(protocol_version), "400 Bad Request", origin=allowed_origin)
                    return None
                session.last_seen = monotonic()
                return session_id, session

            if method == "GET":
                if not media_accepts_event_stream(headers.get("accept")):
                    await send_response("406 Not Acceptable", origin=allowed_origin)
                    return keep_alive
                version = headers.get("mcp-protocol-version")
                if version not in SUPPORTED_PROTOCOL_VERSIONS:
                    await send_json(protocol_version_error(version), "400 Bad Request", origin=allowed_origin)
                    return keep_alive
                session_id = headers.get("mcp-session-id")
                validated = await validated_session(version, required=True)
                if validated is None:
                    return keep_alive
                _validated_id, session = validated
                if session.writer is not None:
                    await send_response("409 Conflict", origin=allowed_origin)
                    return keep_alive
                while True:
                    try:
                        session.queue.get_nowait()
                    except QueueEmpty:
                        break
                session.disconnect_event.clear()
                session.writer = writer
                await send_response(
                    "200 OK",
                    content_type="text/event-stream",
                    origin=allowed_origin,
                    extra_headers=(("Cache-Control", "no-cache"),),
                    streaming=True,
                )
                writer.write(b": connected\n\n")
                await writer.drain()
                try:
                    while not session.disconnect_event.is_set():
                        try:
                            payload = await wait_for(
                                session.queue.get(),
                                timeout=self.streamable_http_keepalive_seconds,
                            )
                        except TimeoutError:
                            payload = b": keepalive\n\n"
                        if session.disconnect_event.is_set() or session.writer is not writer:
                            break
                        writer.write(payload)
                        await writer.drain()
                        session.last_seen = monotonic()
                except (CancelledError, ConnectionError, OSError):
                    pass
                finally:
                    if session.writer is writer:
                        session.writer = None
                        session.last_seen = monotonic()
                    self.logger.info("Streamable HTTP event stream %s disconnected", session_id)
                return False

            if method == "DELETE":
                version = headers.get("mcp-protocol-version")
                if version not in SUPPORTED_PROTOCOL_VERSIONS:
                    await send_json(protocol_version_error(version), "400 Bad Request", origin=allowed_origin)
                    return keep_alive
                validated = await validated_session(version, required=True)
                if validated is None:
                    return keep_alive
                session_id, session = validated
                if self._streamable_http_sessions.get(session_id) is not session:
                    await send_response("404 Not Found", origin=allowed_origin)
                    return keep_alive
                self._streamable_http_sessions.pop(session_id, None)
                self._disconnect_streamable_http_session(session)
                self._resource_session_subscriptions.pop(session_id, None)
                self.logger.info("Streamable HTTP session %s deleted", session_id)
                await send_response("200 OK", origin=allowed_origin)
                return keep_alive

            if not content_type_is_json(headers.get("content-type")):
                await send_response("415 Unsupported Media Type", origin=allowed_origin)
                return keep_alive
            if not media_accepts_json(headers.get("accept")):
                await send_response("406 Not Acceptable", origin=allowed_origin)
                return keep_alive
            try:
                request_obj = loads(body.decode())
            except (UnicodeDecodeError, JSONDecodeError):
                await send_json(
                    {"jsonrpc": "2.0", "error": self.create_error(-32700, "Parse error"), "id": None},
                    origin=allowed_origin,
                )
                return keep_alive
            if not isinstance(request_obj, dict):
                await send_json(
                    self.create_response(None, None, self.create_error(-32600, "Invalid Request")),
                    origin=allowed_origin,
                )
                return keep_alive

            rpc_method = request_obj.get("method")
            version = headers.get("mcp-protocol-version")
            if rpc_method != "initialize" and version not in SUPPORTED_PROTOCOL_VERSIONS:
                await send_json(protocol_version_error(version), "400 Bad Request", origin=allowed_origin)
                return keep_alive
            validated: tuple[str, _AsyncStreamableHTTPSession] | None = None
            if rpc_method == "initialize":
                if headers.get("mcp-session-id"):
                    await send_response("400 Bad Request", origin=allowed_origin)
                    return keep_alive
            else:
                validated = await validated_session(version, required=False)
                if headers.get("mcp-session-id") and validated is None:
                    return keep_alive

            session_id = validated[0] if rpc_method != "initialize" and validated is not None else None
            is_response = rpc_method is None and "id" in request_obj and is_valid_jsonrpc_response(request_obj)
            is_notification = rpc_method is not None and "id" not in request_obj
            if is_response:
                await send_response("202 Accepted", origin=allowed_origin)
                return keep_alive
            params = request_obj.get("params") if isinstance(request_obj.get("params"), dict) else {}
            tool_name = params.get("name") if rpc_method == "tools/call" else None
            try:
                authorized = await self.authorize_request_async(
                    principal,
                    rpc_method=rpc_method,
                    tool_name=tool_name,
                )
            except Exception:
                self.logger.exception("HTTP authorization hook failed for rpc_method=%r tool_name=%r", rpc_method, tool_name)
                await send_response("500 Internal Server Error", origin=allowed_origin)
                return keep_alive
            if not self._validate_http_authorization_result(authorized):
                self.logger.error("HTTP authorization hook returned invalid result type: %r", type(authorized))
                await send_response("500 Internal Server Error", origin=allowed_origin)
                return keep_alive
            if not authorized:
                await send_response("403 Forbidden", origin=allowed_origin)
                return keep_alive
            if session_id and rpc_method in ("resources/subscribe", "resources/unsubscribe"):
                request_obj["params"] = dict(params)
                request_obj["params"]["_session_id"] = session_id

            context = MCPRequestContext(
                transport="streamable-http",
                request_id=request_obj.get("id"),
                protocol_version=version,
                session_id=session_id,
                principal=principal.name,
                peer=peer[0] if peer else None,
                headers=headers,
            )
            response = await self.process_request_async(dumps(request_obj), context=context)
            if is_notification:
                response = None
            if response is None:
                await send_response("202 Accepted", origin=allowed_origin)
                return keep_alive

            extra_headers: tuple[tuple[str, str], ...] = ()
            if rpc_method == "initialize" and "result" in response:
                result = response.get("result")
                negotiated = result.get("protocolVersion") if isinstance(result, dict) else None
                if negotiated in SUPPORTED_PROTOCOL_VERSIONS:
                    now = monotonic()
                    self._expire_streamable_http_sessions(now)
                    if len(self._streamable_http_sessions) >= self.streamable_http_max_sessions:
                        await send_response("503 Service Unavailable", origin=allowed_origin)
                        return keep_alive
                    created_id = str(uuid4())
                    self._streamable_http_sessions[created_id] = _AsyncStreamableHTTPSession(
                        principal=principal.name,
                        protocol_version=negotiated,
                        created_at=now,
                        last_seen=now,
                        disconnect_event=Event(),
                        queue=Queue(maxsize=100),
                    )
                    self.logger.info("Streamable HTTP session %s created for %s", created_id, principal.name)
                    extra_headers = (("Mcp-Session-Id", created_id),)
            await send_json(response, origin=allowed_origin, extra_headers=extra_headers)
            return keep_alive

        try:
            for request_number in range(1, self.streamable_http_max_requests_per_connection + 1):
                if not await handle_one_request(request_number):
                    break
        except (CancelledError, ConnectionError, OSError):
            pass
        except Exception:
            self.logger.exception("Streamable HTTP connection failed for %s", peer)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def run_sse_async(self, host: str = "127.0.0.1", port: int = 0, allowed_origins: list[str] | None = None, max_request_bytes: int = 4 * 1024 * 1024) -> None:
        allowed_origins = allowed_origins or []
        self._sse_sessions: dict[str, tuple[StreamWriter, Event, Lock, str]] = {}
        server = await start_server(lambda r, w: self._sse_handle_client(r, w, allowed_origins, max_request_bytes, host), host, port)
        addrs = [s.getsockname() for s in server.sockets]
        for addr in addrs:
            self.logger.info("MCP SSE Server listening on http://%s:%s/sse", addr[0], addr[1])
            print(f"MCP SSE Server listening on http://{addr[0]}:{addr[1]}/sse", flush=True)
        async with server:
            await server.serve_forever()

    async def run_async(self, args: list[str] | None = None) -> None:
        if args is None:
            args = argv[1:]
        port: int | None = None
        host: str = "127.0.0.1"
        use_tcp: bool = False
        transport: str | None = None
        endpoint = "/mcp"
        max_request_bytes = 4 * 1024 * 1024
        allowed_origins: list[str] = []
        remaining: list[str] = []
        i = 0
        while i < len(args):
            if args[i] in ("--port", "-p") and i + 1 < len(args):
                port = int(args[i + 1])
                i += 2
            elif args[i] == "--host" and i + 1 < len(args):
                host = args[i + 1]
                i += 2
            elif args[i] == "--endpoint" and i + 1 < len(args):
                endpoint = args[i + 1]
                i += 2
            elif args[i] == "--max-request-bytes" and i + 1 < len(args):
                max_request_bytes = int(args[i + 1])
                i += 2
            elif args[i] == "--allowed-origin" and i + 1 < len(args):
                allowed_origins.append(args[i + 1])
                i += 2
            elif args[i] == "--transport" and i + 1 < len(args):
                selected = args[i + 1]
                if transport is not None and transport != selected:
                    raise ValueError("conflicting transport options")
                transport = selected
                i += 2
            elif args[i] in ("--tcp", "--http", "--sse"):
                selected = {"--tcp": "tcp", "--http": "streamable-http", "--sse": "sse"}[args[i]]
                if transport is not None and transport != selected:
                    raise ValueError("conflicting transport options")
                use_tcp = selected == "tcp"
                transport = selected
                i += 1
            else:
                remaining.append(args[i])
                i += 1
        valid_transports = {"stdio", "streamable-http", "sse", "tcp"}
        if transport not in valid_transports | {None}:
            raise ValueError(f"unsupported transport: {transport}")
        if transport not in (None, "stdio") and port is None:
            raise ValueError("network transports require --port")
        if transport == "stdio" and port is not None:
            raise ValueError("stdio transport cannot use --port")
        if port is not None:
            mode = transport or ("tcp" if use_tcp else "sse")
            if mode == "tcp":
                await self.run_socket_async(host=host, port=port)
            elif mode == "streamable-http":
                await self.run_streamable_http_async(host=host, port=port, endpoint=endpoint, allowed_origins=allowed_origins, max_request_bytes=max_request_bytes)
            else:
                await self.run_sse_async(host=host, port=port, allowed_origins=allowed_origins, max_request_bytes=max_request_bytes)
            return
        args = remaining
        if args:
            try:
                with open(args[0], encoding='utf-8') as f:
                    input_data = f.read()
                response = await self.process_request_async(input_data, context=MCPRequestContext(transport="file"))
                if response is not None:
                    payload = (dumps(response) + "\n").encode("utf-8")
                    _stdout_bin.write(payload)
                    _stdout_bin.flush()
            except OSError as e:
                self.logger.error("Error reading file %s: %s", args[0], e)
                exit(1)
        else:
            while True:
                raw = await get_event_loop().run_in_executor(None, _stdin_bin.readline)
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                response = await self.process_request_async(line, context=MCPRequestContext(transport="stdio"))
                if response is not None:
                    payload = (dumps(response) + "\n").encode("utf-8")
                    _stdout_bin.write(payload)
                    _stdout_bin.flush()

    def run(self, args: list[str] | None = None) -> None:
        """Synchronous wrapper to run the async MCP server."""
        try:
            run(self.run_async(args))
        except KeyboardInterrupt:
            self.logger.info("Async MCP Server stopped by user.")
            exit(0)


if __name__ == "__main__":
    # This will be overridden by subclasses
    server = AsyncMCPServer()
    server.run()
