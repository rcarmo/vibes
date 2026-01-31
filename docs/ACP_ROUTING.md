# ACP filtering and streaming notes

This document captures the current understanding of how **Vibes** handles ACP session updates, and how we keep **"thinking/segment"** output out of the final assistant reply while still displaying it in the UI.

## Problem statement

Some ACP agents emit streaming updates where text is delivered as **snapshot-style chunks** (each new chunk repeats previous content). If the client/UI naïvely concatenates these chunks, the displayed "Draft" output can grow with repeated copies (e.g. the same sentence appearing multiple times).

Separately, ACP agents may emit **segments / thoughts / intents** that are meant for an intermediate UI pane, not for the final persisted assistant message.

## Design goals

1. **Use ACP context/metadata to classify output**, not text heuristics (no reliance on newlines, spacing, or regex-based content inspection).
2. **Do not persist** think/segment-like content into the stored `agent_response.content`.
3. Still **display** think/segment-like content live in an appropriate UI pane.
4. Be resilient to snapshot-style streaming to avoid apparent duplication.

## Where the logic lives

### Backend ACP parsing

File: `src/vibes/acp_client.py`

Key responsibilities:

- Reads ACP JSON-RPC responses.
- Handles `session/update` notifications.
- Streams intermediate UI updates via a `status_callback`.
- Collects final content blocks and derives a final `text` response.

### SSE bridging

File: `src/vibes/routes/agents.py`

Key responsibilities:

- Receives `status_callback` events from the ACP client.
- Broadcasts SSE events (`agent_draft`, `agent_thought`, `agent_status`) to the frontend.

### Frontend consumption

File: `src/vibes/static/js/app.js`

Key responsibilities:

- Listens to SSE events.
- Maintains local UI state for:
  - `agentDraft` (Draft pane)
  - `agentThought` (Thoughts pane)
  - `agentPlan` (Planning pane)
  - `agentStatus` (spinner/tool status)

## How we classify "thinking/segment" content

### Metadata sources (in priority order)

When receiving an ACP `session/update` of type `agent_message_chunk`, we prefer **explicit metadata fields** when present:

- `update.segment`
- `update.kind`
- `update.channel`
- `update.role`
- `chunk_content.segment`
- `chunk_content.channel`
- `chunk_content.role`

If none of the above exists, we fall back to **ACP annotations** on the content block:

- `chunk_content.annotations`

The helper `_segment_kind_from_annotations(annotations)` interprets annotation dictionaries/lists and extracts a best-effort "kind".

### Routing decisions

- If a chunk is tagged as one of: `think`, `thought`, `thinking`, `segment`, `intent` (via metadata/annotations), it is routed to the **Thoughts** stream (`thought_chunk`).
- Otherwise it is treated as **Draft** stream content (`message_chunk`).

### IMPORTANT: metadata-based only

The classification/routing above does **not** inspect the text content to infer meaning. It does not depend on:

- newline patterns
- repeated spaces
- regex matches
- marker strings like "Thought:" / "Plan:" embedded in text

## Preventing duplication from snapshot-style streaming

Some agents emit cumulative snapshots rather than incremental deltas.

To prevent duplication:

- Draft streaming is sent with `mode: "replace"` (SSE payload field).
- The frontend respects `mode === "replace"` by overwriting the draft buffer rather than concatenating.

This behavior is a **transport/display policy** and is **not determined by content heuristics**.

## Keeping thoughts/segments out of the final persisted reply

Even if a thought/segment chunk is streamed during the request, the backend also filters content during the "collect content blocks" phase:

- For `session/update` notifications, when collecting `content_blocks`, any text block that is marked as `think/thought/plan/intent/segment/thinking` (via update metadata or annotations) is excluded from the final `_collected_content`.

This ensures `agent_response.content` remains the final assistant response, not the agent's intermediate reasoning.

## Current UI panes

The `AgentStatus` component renders (when present):

- **Planning** (from `agentPlan`)
- **Thoughts** (from `agentThought`)
- **Draft** (from `agentDraft`)
- **Status** (spinner + tool/status text)

## Notes / open questions

- ACP may provide more structured semantics for segments (or snapshot vs delta) depending on the agent implementation. If we standardize on a specific field (e.g. `segment=plan`), we can route plan segments to the Planning pane consistently.
- If agents start emitting explicit delta/snapshot flags, we should use those instead of a fixed `mode: replace` policy.
