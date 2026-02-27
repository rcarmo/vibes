# Pi Mode Integration

Vibes can run a **Pi RPC agent** alongside (or instead of) ACP. This lets you use pi’s streaming updates (drafts/thinking), tool execution events, and rich media attachments in the Vibes UI.

## Enable Pi Mode

```bash
# Use Pi as the default agent
VIBES_DEFAULT_AGENT=pi
VIBES_PI_ENABLED=true
VIBES_PI_AGENT="pi --mode rpc --no-session --append-system-prompt '<vibes prompt>' -e /path/to/site-packages/vibes/extensions/pi-vibes-tools.ts"
```

You can also keep ACP as default and expose Pi as a separate agent id:

```bash
VIBES_DEFAULT_AGENT=acp
VIBES_PI_ENABLED=true
```

Agent ids:
- `default` → uses `VIBES_DEFAULT_AGENT`
- `pi` → forces Pi mode
- `acp` → forces ACP mode

## What Pi Mode Supports

Pi mode automatically loads the packaged `vibes/extensions/pi-vibes-tools.ts` via the default `VIBES_PI_AGENT` command and injects a Vibes formatting prompt via `--append-system-prompt`. This adds a `vibes_attach_file` tool for attaching local files as base64 content blocks.

- **History & threading**: Pi responses are stored just like ACP responses in the timeline.
- **Draft streaming**: `message_update` text deltas are streamed to the Draft pane.
- **Thinking stream**: `thinking_delta` updates appear in the Thoughts pane.
- **Tool status**: `tool_execution_start/update/end` map to `agent_status` updates.
- **Permission/choice prompts**: Pi extension UI requests (`confirm`, `select`) surface in the existing modal.
- **Media**:
  - Base64 image blocks (recommended): `{type: "image", data, mimeType}`
  - File attachments: `{type: "file", fileName, mimeType, content}`
  - `vibes_attach_file` tool from the bundled Pi extension

Vibes stores received media in the media table and renders previews/downloads in the timeline.

## Output Formatting (Pi Guidance)

Pi receives a prompt prefix that describes Vibes’ supported formats:
- Markdown rendering via `marked` (tables, lists, fenced code)
- KaTeX math: `$...$` and `$$...$$`
- Mermaid: fenced blocks ` ```mermaid ... ``` `
- Base64 media blocks and file attachments

## Limitations (current)

- Only `confirm` and `select` extension dialogs are supported in the UI. Other dialog types are auto-cancelled.
- Tool output is summarized as status updates; full tool outputs are not rendered inline (yet).

## Restart behavior

Pi is kept warm by default even if all SSE clients disconnect. Set `VIBES_PI_RESTART_ON_DISCONNECT=true` to restart Pi when all clients disconnect.

## Troubleshooting

- Use `GET /agents` to verify agent status and mode.
- Ensure `VIBES_PI_AGENT` is in PATH and callable by the server process.
- Check server logs for Pi startup/shutdown messages.

## RPC Parsing Notes

Pi communicates via **newline-delimited JSON** on stdout when running with `--mode rpc`. In practice, JSON events frequently contain **raw control characters** (literal `\n`, `\t`, `\r` bytes — not `\\n` escapes) inside string values, particularly in:

- `thinking_delta` events — the `partial.thinking` field carries the **entire accumulated thinking text**, which grows to hundreds of lines during long reasoning sessions.
- `toolcall_delta` events — tool argument deltas can contain file contents with embedded newlines.
- `tool_execution_update` / `turn_end` events — base64 `toolCallId` fields can exceed 50 KB.

### Why `readline()` doesn't work

A naive `readline()` approach splits on every `\n` byte, including those *inside* JSON string values. A single `thinking_delta` event with 500 lines of thinking content would be split into 500+ readline segments. Any line-stitching approach either:

- Drops events when stitching exceeds a cap (causing hung responses — the UI waits for `agent_end` that was silently discarded), or
- Re-parses the growing buffer on every stitch (O(N²) per event).

### Current approach: `read()` + `raw_decode(strict=False)`

The parser uses `reader.read(524288)` to read raw byte chunks into a persistent string buffer (`_state.rpc_buffer`), then calls `json.JSONDecoder(strict=False).raw_decode()` to extract complete JSON objects:

- `strict=False` tells Python's JSON parser to **accept raw control characters** inside strings — no sanitization needed.
- `raw_decode()` stops at the exact end of the first JSON value, leaving remaining data in the buffer for the next call.
- No dependence on newline boundaries at all.
- Buffer is capped at 16 MB to prevent unbounded growth; on overflow the oldest half is discarded.

### Key event types

| Event | Description |
|-------|-------------|
| `agent_start` | Agent session begins |
| `turn_start` / `turn_end` | One reasoning turn |
| `message_start` / `message_update` / `message_end` | Text/thinking/tool-call deltas |
| `tool_execution_start` / `tool_execution_update` / `tool_execution_end` | Tool runs |
| `extension_ui_request` | Permission/choice dialogs |
| `agent_end` | **Terminal event** — loop must wait for this |

### Debugging

If responses hang (no reply until `/restart`), check logs for:

- `Pi RPC: buffer exceeded ... truncating` — a single event exceeded 16 MB (extremely rare; increase `_MAX_RPC_BUFFER`).
- `Pi RPC: read exceeded buffer limit` — the asyncio pipe limit (16 MB) was hit. Increase the `limit=` parameter in `create_subprocess_exec`.
- `Pi RPC: timed out waiting for agent_end` — Pi stopped sending events but didn't close. Check if Pi is alive (`/agents` endpoint).
