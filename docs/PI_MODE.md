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

The parser uses `reader.read(512KB)` to read raw byte chunks into a persistent string buffer (`_state.rpc_buffer`), then calls `json.JSONDecoder(strict=False).raw_decode()` to extract complete JSON objects:

- `strict=False` tells Python's JSON parser to **accept raw control characters** inside strings — no sanitization needed.
- `raw_decode()` stops at the exact end of the first JSON value, leaving remaining data in the buffer for the next call.
- No dependence on newline boundaries at all.
- Buffer is capped at 16 MB to prevent unbounded growth; on overflow the oldest half is discarded.

### Why not use a streaming JSON parser?

We evaluated **ijson** (yajl2 backend), **json-stream** (Rust tokenizer), and **jsonslicer** — all reject raw control characters inside strings per the JSON spec. Only Python's built-in `json.JSONDecoder(strict=False)` accepts raw `0x0a` bytes in string values without sanitization. Since Pi emits these routinely in thinking/tool payloads, off-the-shelf streaming parsers are not viable.

### Error recovery

The parser distinguishes two failure modes:

1. **Incomplete event** (`Unterminated string`): the buffer ends mid-event because `read()` returned a partial chunk. The parser waits for more data.
2. **Malformed event** (any other `JSONDecodeError`): the buffer starts with garbage. The parser skips forward to the next `{` and retries.

Two safety mechanisms prevent the parser from blocking forever:

- **Per-read timeout (30s)**: each `reader.read()` call has a timeout. If Pi stops writing (e.g. it already sent `agent_end` but the buffer has a malformed prefix), the timeout fires instead of blocking indefinitely.
- **Stuck detection**: after 3 consecutive read timeouts with no events extracted, the parser force-skips past the current `{` to the next one, discarding the stuck prefix.

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
- `Pi RPC: stuck for N reads` — the parser detected a malformed event blocking the buffer and skipped past it.

## RPC Commands Reference

Pi's `--mode rpc` protocol accepts JSON commands on **stdin** and emits events on **stdout**. Below is the full set of supported commands (discovered from Pi v0.55.1 type definitions).

### Currently implemented

| Command | Payload | Notes |
|---------|---------|-------|
| `prompt` | `{"type":"prompt","message":"..."}` | Send a user message. Supports optional `images` and `streamingBehavior` (`"steer"` or `"followUp"`). |
| `extension_ui_response` | `{"type":"extension_ui_response","id":"...","confirmed":true}` | Respond to permission/choice dialogs. |
| `set_model` | `{"type":"set_model","provider":"...","modelId":"..."}` | Change model live via `/model` command (no restart). |
| `set_thinking_level` | `{"type":"set_thinking_level","level":"high"}` | Change thinking level live via `/thinking` command. |
| `get_state` | `{"type":"get_state"}` | Query current session state (used by `/model` to show active model). |
| `get_available_models` | `{"type":"get_available_models"}` | List models via RPC (used by `/model` listing). |
| `new_session` | `{"type":"new_session"}` | Reset session via `/restart` (keeps process alive). |
| `steer` | `{"type":"steer","message":"..."}` | Mid-turn steering via `/steer` command. |
| `abort` | `{"type":"abort"}` | Cancel current execution via `/abort` command. |

### Not yet implemented

These commands are available in Pi's RPC protocol but not yet wired up:

| Command | Payload | Description |
|---------|---------|-------------|
| `follow_up` | `{"type":"follow_up","message":"..."}` | Queue a follow-up message to be processed after the current turn completes. |
| `compact` | `{"type":"compact"}` | Trigger context window compaction. |
| `get_commands` | `{"type":"get_commands"}` | List slash commands registered by extensions/skills. |
| `cycle_model` | `{"type":"cycle_model"}` | Cycle to the next model in the `--models` list. |
| `cycle_thinking_level` | `{"type":"cycle_thinking_level"}` | Cycle to the next thinking level. |
| `bash` / `abort_bash` | `{"type":"bash","command":"..."}` | Run a bash command / abort running bash. |
| `set_steering_mode` | `{"type":"set_steering_mode","mode":"all"}` | Controls how steering messages are batched (`"all"` or `"one-at-a-time"`). |
| `set_follow_up_mode` | `{"type":"set_follow_up_mode","mode":"all"}` | Controls how follow-up messages are batched. |

### Prompt streaming behavior

The `prompt` command accepts an optional `streamingBehavior` field:
- `"steer"` — if the agent is already streaming, treat this prompt as a steering message
- `"followUp"` — if the agent is already streaming, queue this prompt as a follow-up
