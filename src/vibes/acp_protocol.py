"""ACP protocol types, JSON-RPC frame parsing, and message classification.

This module provides schema-driven helpers for working with the Agent Client Protocol.
All routing decisions are metadata-based (no payload heuristics).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from .config import get_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON-RPC Message Classification
# ---------------------------------------------------------------------------

FrameKind = Literal["notification", "request", "response", "invalid"]


def classify_frame(msg: dict) -> FrameKind:
    """Classify a JSON-RPC message as notification, request, response, or invalid.

    - notification: has "method", no "id"
    - request: has "method" and "id"
    - response: has "id" and ("result" or "error"), no "method"
    - invalid: anything else
    """
    if not isinstance(msg, dict):
        return "invalid"

    has_id = "id" in msg
    has_method = "method" in msg
    has_result_or_error = "result" in msg or "error" in msg

    if has_method and not has_id:
        return "notification"
    if has_method and has_id:
        return "request"
    if has_id and has_result_or_error and not has_method:
        return "response"
    return "invalid"


def is_notification(msg: dict) -> bool:
    return classify_frame(msg) == "notification"


def is_request(msg: dict) -> bool:
    return classify_frame(msg) == "request"


def is_response(msg: dict) -> bool:
    return classify_frame(msg) == "response"


# ---------------------------------------------------------------------------
# Frame Parsing (line -> list of messages)
# ---------------------------------------------------------------------------


def parse_frame(line: bytes) -> list[dict]:
    """Parse a line from stdio into a list of JSON-RPC messages.

    - Blank lines are ignored (returns []).
    - Single JSON objects are returned as [obj].
    - JSON arrays (batch) are returned as-is, filtering out non-dicts.
    - Invalid JSON logs a warning and returns [].
    """
    stripped = line.strip()
    if not stripped:
        return []

    debug = get_config().acp_debug

    try:
        decoded = stripped.decode("utf-8")
    except UnicodeDecodeError as e:
        logger.warning(f"ACP: non-UTF8 line ignored: {e}")
        return []

    if debug:
        logger.debug(f"ACP < {decoded[:500]}")

    try:
        data = json.loads(decoded)
    except json.JSONDecodeError as e:
        logger.warning(f"ACP: invalid JSON ignored: {e}")
        return []

    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        valid = [item for item in data if isinstance(item, dict)]
        if len(valid) != len(data):
            logger.warning(f"ACP: batch contained {len(data) - len(valid)} non-dict items")
        return valid

    logger.warning(f"ACP: unexpected JSON type: {type(data).__name__}")
    return []


# ---------------------------------------------------------------------------
# Tool Call State Management
# ---------------------------------------------------------------------------


@dataclass
class ToolCallState:
    """State for a single tool call, keyed by toolCallId."""

    tool_call_id: str
    title: str = "Tool call"
    status: str | None = None
    kind: str | None = None
    raw_input: dict | None = None
    raw_output: dict | None = None
    content: list[dict] = field(default_factory=list)
    locations: list[dict] = field(default_factory=list)

    def merge_update(self, update: dict) -> None:
        """Merge fields from a tool_call_update, ignoring None values."""
        for key in ("title", "status", "kind"):
            val = update.get(key)
            if val is not None:
                setattr(self, key, val)
        if update.get("rawInput") is not None:
            self.raw_input = update["rawInput"]
        if update.get("rawOutput") is not None:
            self.raw_output = update["rawOutput"]
        if update.get("content") is not None:
            self.content = update["content"]
        if update.get("locations") is not None:
            self.locations = update["locations"]

    def to_dict(self) -> dict:
        return {
            "toolCallId": self.tool_call_id,
            "title": self.title,
            "status": self.status,
            "kind": self.kind,
            "rawInput": self.raw_input,
            "rawOutput": self.raw_output,
            "content": self.content,
            "locations": self.locations,
        }

    @classmethod
    def from_tool_call(cls, data: dict) -> "ToolCallState":
        return cls(
            tool_call_id=data.get("toolCallId", ""),
            title=data.get("title", "Tool call"),
            status=data.get("status"),
            kind=data.get("kind"),
            raw_input=data.get("rawInput"),
            raw_output=data.get("rawOutput"),
            content=data.get("content", []),
            locations=data.get("locations", []),
        )


# ---------------------------------------------------------------------------
# Per-Turn State (aggregation context for a single prompt request)
# ---------------------------------------------------------------------------


@dataclass
class TurnState:
    """Aggregation state for a single prompt turn."""

    turn_id: int
    pre_tool_blocks: list[dict] = field(default_factory=list)
    post_tool_blocks: list[dict] = field(default_factory=list)
    saw_any_tool_call: bool = False
    last_draft_text: str | None = None
    tool_calls: dict[str, ToolCallState] = field(default_factory=dict)

    def get_or_create_tool_call(self, tool_call_id: str) -> ToolCallState:
        """Get existing tool call state or create a placeholder."""
        if tool_call_id not in self.tool_calls:
            self.tool_calls[tool_call_id] = ToolCallState(tool_call_id=tool_call_id)
        return self.tool_calls[tool_call_id]

    def record_tool_call(self, data: dict) -> ToolCallState:
        """Record a new tool_call event."""
        tool_call_id = data.get("toolCallId", "")
        tc = self.get_or_create_tool_call(tool_call_id)
        tc.merge_update(data)
        self.saw_any_tool_call = True
        self.pre_tool_blocks.clear()
        return tc

    def record_tool_call_update(self, data: dict) -> ToolCallState:
        """Record a tool_call_update event (may arrive before tool_call)."""
        tool_call_id = data.get("toolCallId", "")
        tc = self.get_or_create_tool_call(tool_call_id)
        tc.merge_update(data)
        if not self.saw_any_tool_call:
            self.saw_any_tool_call = True
            self.pre_tool_blocks.clear()
        return tc

    def add_content_block(self, block: dict) -> None:
        """Add a content block to the appropriate list (pre/post tool)."""
        target = self.post_tool_blocks if self.saw_any_tool_call else self.pre_tool_blocks
        target.append(block)

    def get_final_blocks(self) -> list[dict]:
        """Return the content blocks to use for the final response."""
        if self.saw_any_tool_call:
            return self.post_tool_blocks
        return self.pre_tool_blocks

    def get_summary(self) -> dict:
        """Return a summary of this turn for logging."""
        final_blocks = self.get_final_blocks()
        block_types: dict[str, int] = {}
        total_text_len = 0
        for b in final_blocks:
            t = b.get("type", "unknown")
            block_types[t] = block_types.get(t, 0) + 1
            if t == "text":
                total_text_len += len(b.get("text", ""))

        return {
            "turn_id": self.turn_id,
            "tool_calls": len(self.tool_calls),
            "final_blocks": len(final_blocks),
            "block_types": block_types,
            "total_text_len": total_text_len,
            "text_preview": (final_blocks[0].get("text", "")[:80] if final_blocks and final_blocks[0].get("type") == "text" else ""),
        }


# ---------------------------------------------------------------------------
# Segment/Content Kind Classification (Metadata-Only)
# ---------------------------------------------------------------------------

THINKING_KINDS = frozenset({"think", "thought", "thinking", "segment", "intent", "plan"})


def segment_kind_from_annotations(annotations: Any) -> str | None:
    """Extract segment/thinking kind from ACP annotations (metadata-only)."""
    if not annotations:
        return None

    candidates: list[dict] = []
    if isinstance(annotations, dict):
        candidates = [annotations]
    elif isinstance(annotations, list):
        candidates = [a for a in annotations if isinstance(a, dict)]
    else:
        return None

    for a in candidates:
        a_type = (a.get("type") or a.get("annotation") or "").lower()
        kind = (
            a.get("kind")
            or a.get("segment")
            or a.get("role")
            or a.get("channel")
            or a.get("name")
            or a.get("value")
        )
        kind = kind.lower() if isinstance(kind, str) else None

        if a_type in ("segment", "thinking", "intent"):
            return kind or a_type
        if kind in THINKING_KINDS:
            return kind

    return None


def get_update_segment_kind(update: dict, block: dict | None = None) -> str | None:
    """Get segment kind from update metadata and/or block annotations."""
    hint = (
        update.get("segment")
        or update.get("kind")
        or update.get("channel")
        or update.get("role")
    )
    if isinstance(hint, str):
        hint = hint.lower()
        if hint in THINKING_KINDS:
            return hint

    if block:
        block_hint = (
            block.get("segment")
            or block.get("channel")
            or block.get("role")
        )
        if isinstance(block_hint, str) and block_hint.lower() in THINKING_KINDS:
            return block_hint.lower()

        ann_kind = segment_kind_from_annotations(block.get("annotations"))
        if ann_kind:
            return ann_kind

    return None


def is_thinking_content(update: dict, block: dict | None = None) -> bool:
    """Check if content should be routed to thinking pane (not final output)."""
    kind = get_update_segment_kind(update, block)
    return kind in THINKING_KINDS
