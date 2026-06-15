# ACP Routing & Streaming Notes (Go implementation)

This document describes how Vibes routes ACP session updates into SSE/UI channels and final stored responses.

## Scope

Relevant files:

- `internal/agent/acp/client.go` — ACP JSON-RPC client + `session/update` routing
- `internal/app/app.go` — provider event fanout to SSE (`agent_*`)
- `internal/server/sse/broker.go` — SSE transport
- `static/js/app.ts` — SSE consumption + timeline/draft/thought/session update UI state

## Current routing behavior

`session/update.sessionUpdate` is mapped as follows:

- `agent_message_chunk` → `agent.Event{Type:"draft"}`
- `agent_thought_chunk` → `agent.Event{Type:"thought"}`
- `tool_call`, `tool_call_update` → `agent.Event{Type:"status"}`
- `plan` → `agent.Event{Type:"plan"}`
- all recognized/unknown updates → safe `agent.Event{Type:"session_update"}` metadata event

These provider events are broadcast as SSE events prefixed with `agent_`.

## Final response aggregation

For ACP prompts, final persisted response text is derived from:

1. direct response payload text when available, and/or
2. accumulated draft chunks (`CollectedDraft()`) from `agent_message_chunk` events.

This ensures streamed assistant text is preserved even if the final RPC response has minimal body text.

## Content-block extraction note

ACP text content blocks are expected in the shape:

```json
{"type":"text","text":"hello"}
```

Extraction uses `cb["text"].(string)` (not nested `text.text`).

## Known limitations

- No deep semantic routing by ACP annotation metadata yet (current behavior routes by `sessionUpdate` kind).
- Tool call payloads are surfaced as typed status updates; full rich tool UI rendering is intentionally minimal.
- Session metadata updates are sanitized and bounded before they reach provider descriptors.
- SSE stream is long-lived and should be tested via headers/connectivity, not full-body completion.

## Operational guidance

- Enable ACP wire logging with `VIBES_ACP_DEBUG=true` for troubleshooting.
- Keep one consumer of provider events (`forwardAgentEvents`) to avoid event-channel contention.
