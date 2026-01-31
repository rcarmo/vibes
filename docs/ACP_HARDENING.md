# PROTOCOL_HARDENING.md

This document is a detailed implementation plan to harden Vibes’ ACP (Agent Client Protocol) and JSON-RPC handling for correctness, resilience, and debuggability.

It is intentionally **schema-/metadata-driven**: no routing decisions should depend on payload content heuristics (whitespace/newlines, partial characters, etc.).

---

## Goals

1. **Protocol correctness**: Implement ACP + JSON-RPC behaviors in a way that matches the protocol schema and tolerates real-world agent quirks.
2. **Robust streaming**: Correctly handle both **snapshot** and **delta** message chunk streams without losing final output.
3. **Stable tool-call lifecycle**: Track tool calls by **toolCallId**, merge updates, and keep state coherent even with out-of-order events.
4. **Clean cancellation + timeouts**: Ensure prompt turns and permission requests can be cancelled reliably.
5. **Better observability**: Improve logging so failures are diagnosable without reading raw stdout.

Non-goals:
- Rewriting the UI or switching transport away from stdio.
- Implementing every ACP tool surface unless required; focus on correctness and safety.

---

## Current State (Vibes)

- Reads stdio JSON-RPC line-delimited (`readline()`), expects one JSON object per line.
- Handles:
  - `session/update` notifications (draft/thought/plan/tool_call/tool_call_update)
  - `session/request_permission` requests with a timeout + cancellation pathway
  - hard-rejects `fs/*` and `terminal/*` methods
- Aggregates final output via collected content blocks from session updates and/or final RPC response fields.
- Has explicit **delta vs snapshot** logic for draft display and final collection.

---

## Reference: What to Learn from toad

Toad’s ACP implementation suggests several improvements:

1. **Schema-first / typed protocol layer**: define request/notification/response structures to avoid ad-hoc parsing.
2. **Tool call state keyed by `toolCallId`**: merge tool updates into a stable record (including “update before tool_call” quirks).
3. **Clear JSON-RPC separation**: robustly distinguish notifications vs requests vs responses; support batch responses.

---

## Work Plan

### Phase 0 — Safety + Baselines

#### Implementation
- [ ] Add a dedicated module for protocol concerns (recommended): `src/vibes/acp_protocol.py` (or `src/vibes/acp/schema.py`).
- [ ] Centralize parsing of incoming JSON-RPC frames into a small set of dataclasses/types.
- [ ] Add a `VIBES_ACP_DEBUG=1` option to enable verbose wire logging without spamming production logs.

#### Testing
- [ ] Add a fast unit test suite that feeds canned JSON-RPC frames into the parser and asserts classification (notification/request/response/batch).

---

### Phase 1 — JSON-RPC Framing & Message Classification

**Objective:** Make stdio parsing resilient and protocol-correct.

#### Implementation
- [ ] Update `_read_response()` (or rename to `_read_frame()`) to:
  - [ ] tolerate blank lines (ignore)
  - [ ] log and skip non-JSON lines with rate limiting (optional)
  - [ ] accept JSON-RPC **batch** frames (a JSON list) and return as a list of messages
  - [ ] enforce that each element of a batch is a dict
- [ ] Update `_send_request()` loop to consume frames that may contain:
  - [ ] a single dict
  - [ ] a list[dict]
  and process each message in order.
- [ ] Add a helper:
  - [ ] `is_notification(msg)` (no `id`, has `method`)
  - [ ] `is_request(msg)` (has `id` and `method`)
  - [ ] `is_response(msg)` (has `id` and (`result` or `error`))

#### Testing checklist
- [ ] Notification parsing: `{"method":"session/update",...}` is detected as notification.
- [ ] Request parsing: `{"id":1,"method":"session/request_permission",...}` is detected as request.
- [ ] Response parsing: `{"id":1,"result":{...}}` is detected as response.
- [ ] Batch parsing: `[ {response}, {notification}, ... ]` returns N items and all are processed.
- [ ] Invalid batch: list contains non-dicts → safely ignored/logged (no crash).

---

### Phase 2 — Tool Call Lifecycle: Track by `toolCallId` and Merge Updates

**Objective:** Replace the current “saw_tool_call” boolean with stable per-tool state.

#### Implementation
- [ ] Add to ACP state:
  - [ ] `tool_calls: dict[str, dict]` keyed by `toolCallId`.
- [ ] In `session/update` handling:
  - [ ] on `tool_call`:
    - [ ] read `toolCallId`
    - [ ] store the tool call object in `tool_calls[toolCallId]`
    - [ ] broadcast status update using the stored tool call
  - [ ] on `tool_call_update`:
    - [ ] read `toolCallId`
    - [ ] if toolCallId exists: merge fields where update values are not None
    - [ ] else: create placeholder tool call record and then merge (toad’s “rolls eyes” case)
    - [ ] broadcast updated tool state
- [ ] Redefine “pre-tool vs post-tool” collection using tool state:
  - [ ] Decide what constitutes “tool has started” using `tool_call.status` and/or first `tool_call` event.
  - [ ] Keep a per-prompt-turn timeline (see Phase 3) rather than global boolean.

#### Testing checklist
- [ ] `tool_call_update` before `tool_call` does not crash and results in a stored tool call.
- [ ] `tool_call_update` merges fields without clobbering existing values with `None`.
- [ ] Multiple concurrent tool calls (different toolCallId) maintain independent state.

---

### Phase 3 — Prompt-Turn Model: Explicit “Turn State” Object

**Objective:** Make aggregation deterministic and avoid cross-request bleed.

#### Implementation
- [ ] Introduce a per-request object (e.g. `TurnState`) created inside `_send_request()` that tracks:
  - [ ] `turn_id` (request id)
  - [ ] `pre_tool_blocks`, `post_tool_blocks`
  - [ ] `saw_any_tool_call`
  - [ ] `last_draft_text` (for snapshot vs delta)
  - [ ] `tool_calls_seen: set[toolCallId]`
- [ ] Ensure all aggregation decisions are made using `TurnState`, not global state.

#### Testing checklist
- [ ] Two back-to-back prompts do not share tool state or accumulated blocks.
- [ ] Tool calls in prompt A do not affect aggregation in prompt B.

---

### Phase 4 — Content Aggregation Policy (Final Answer vs Draft/Thought/Plan)

**Objective:** Keep final stored output clean and consistent.

#### Implementation
- [ ] Formalize a single function to classify blocks using only metadata:
  - [ ] `segment/kind/channel/role` and/or `annotations`.
- [ ] For each `session/update` block:
  - [ ] route “thought/segment/intent/plan” to non-final channels
  - [ ] route assistant-visible content to the final collector
  - [ ] do not use text content (e.g., `>`, `|`, whitespace) for classification
- [ ] Ensure non-text blocks are also filtered consistently:
  - [ ] images/files/resources should only be collected when they are assistant final output (not tool-call echoes)

#### Testing checklist
- [ ] Regression: delta stream “Hello ” + “World” → final “Hello World”.
- [ ] Regression: snapshot stream “H”, “He”, “Hel” → final “Hel” (or full last snapshot).
- [ ] Regression: “thought” stream never appears in final response.
- [ ] Images in content blocks remain in final output.

---

### Phase 5 — Permission Request Handling Hardening

**Objective:** Improve correctness and reduce deadlock risk.

#### Implementation
- [x] Keep current timeout behavior, but add:
  - [x] per-request cancellation token so a user disconnect (or prompt cancel) can cancel an in-flight permission wait
  - [x] guarantee `_state.pending_requests.pop(req_id)` is always executed
  - [x] ensure the response is ACP-correct: `{"result": {"outcome": {"outcome":"cancelled"}}}` etc.
- [x] Consider implementing ACP `session/cancel` (client -> agent) if the agent supports it:
  - [x] send notification `session/cancel` when user cancels a prompt or disconnect triggers cleanup

#### Testing checklist
- [x] Permission timeout returns `_cancelled` and agent is stopped.
- [x] Permission approve/reject maps to the correct `optionId` from options.
- [x] Cancelling a prompt while a permission dialog is open cancels cleanly (no stuck futures).

---

### Phase 6 — Capability Negotiation & Method Dispatch

**Objective:** Behave like a well-formed ACP client.

#### Implementation
- [x] Implement a typed `clientCapabilities` model like toad's `protocol.ClientCapabilities`.
- [x] Ensure we pass accurate capabilities to `initialize`:
  - [x] if we don't support terminal/fs, declare them false/absent
- [ ] If we want to support these later:
  - [ ] implement `fs/read_text_file` and `fs/write_text_file` behind an allowlist rooted at cwd/project
  - [ ] implement minimal `terminal/*` only if needed

#### Testing checklist
- [x] Initialize includes capabilities that match implemented handlers.
- [ ] If fs support is enabled, path traversal is prevented.

---

### Phase 7 — Observability: Wire Logging + Structured Summaries

**Objective:** Make diagnosing stream issues easy.

#### Implementation
- [x] Add structured log events for:
  - [x] each JSON-RPC frame type (notification/request/response)
  - [x] `sessionUpdate` type counts per prompt
  - [x] toolCall lifecycle transitions per toolCallId
  - [x] final aggregation summary: block types + text prefix
- [ ] Add an option to write raw ACP logs to a rotating file.

#### Testing checklist
- [x] Unit tests validate summary fields exist (at least smoke tests).

---

## Complete Implementation Checklist (One-Pager)

- [ ] JSON-RPC: accept batch frames and ignore blank lines
- [ ] JSON-RPC: classify notification/request/response explicitly
- [ ] Per-turn state object (no cross-prompt bleed)
- [ ] Tool calls keyed by `toolCallId`
- [ ] Merge `tool_call_update` into stored tool calls; handle out-of-order updates
- [ ] Content routing is metadata-only; no payload heuristics
- [ ] Snapshot vs delta detection applied consistently
- [ ] Implement/confirm `session/cancel` behavior if supported
- [ ] Permission waits are cancellable and always clean up futures
- [ ] Capability negotiation reflects reality
- [ ] Harden any enabled fs/terminal methods with safety checks
- [ ] Add structured logs for prompt-turn summaries

---

## Complete Testing Checklist (One-Pager)

### Unit tests (fast)
- [ ] JSON-RPC: notification/request/response classification
- [ ] JSON-RPC: batch frame processing
- [ ] ToolCall: update-before-call supported
- [ ] ToolCall: merge semantics (no clobber with None)
- [ ] Streaming: delta vs snapshot aggregation correctness
- [ ] Routing: thought/plan never enters final output
- [ ] Permission: timeout cancels + stops agent
- [ ] Permission: approve/reject selects correct optionId

### Integration tests
- [ ] SSE pipeline: draft/thought/plan/response end-to-end handling
- [ ] Restart on disconnect does not interrupt active clients

### Regression tests
- [ ] Large markdown tables / single-char chunk failures stay fixed
- [ ] Base64 data URI images rewritten to /media/<id> (no broken markup)

---

## Rollout / Risk Notes

- Implement phases 1–3 first; they reduce the chance of subtle protocol bugs.
- ToolCallId tracking (phase 2) is the most behaviorally impactful change; gate it behind tests.
- If enabling fs/terminal, treat as security-sensitive and add path and resource limits.
