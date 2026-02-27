# Pi Mode Integration

Vibes can use a **Pi coding agent** as its backend via Pi's `--mode rpc` protocol. This provides streaming drafts, thinking traces, tool execution events, and rich media attachments in the Vibes timeline.

When Pi mode is enabled, **only Pi is launched** — the ACP agent subprocess is not started.

## Enable Pi Mode

```bash
# Use Pi as the default agent
VIBES_DEFAULT_AGENT=pi
VIBES_PI_ENABLED=true
```

The default `VIBES_PI_AGENT` command is auto-generated and includes the bundled extension (`pi-vibes-tools.ts`) and formatting prompt. Override it only if you need custom flags:

```bash
VIBES_PI_AGENT="pi --mode rpc --no-session --append-system-prompt '<vibes prompt>' -e /path/to/pi-vibes-tools.ts"
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

- **Draft streaming**: `text_delta` events stream to the Draft pane in real time.
- **Thinking stream**: `thinking_delta` events appear in the Thoughts pane.
- **Tool status**: `tool_execution_start/update/end` map to `agent_status` updates.
- **Permission/choice prompts**: Pi `extension_ui_request` events (`confirm`, `select`) surface in the existing approval modal.
- **Media**: base64 image blocks, file attachments, and the `vibes_attach_file` tool from the bundled extension.
- **Live model/thinking changes**: `/model` and `/thinking` slash commands use RPC (no restart needed).
- **Mid-turn steering**: `/steer` sends guidance while the agent is working.
- **Abort**: `/abort` cancels the current request immediately.

## Slash Commands

| Command | Description |
|---------|-------------|
| `/model [provider/model]` | Show or change the active model via RPC |
| `/model list` | List available models |
| `/thinking [level]` | Show or change thinking level via RPC |
| `/restart` | Reset session (or hard restart as fallback) |
| `/abort` | Cancel current request + in-flight task |
| `/steer <message>` | Send mid-turn steering guidance |
| `/shell <command>` | Run a shell command (30s timeout) |
| `/commands` | List all slash commands |

## Output Formatting

Pi receives a prompt prefix describing Vibes' supported formats:
- Markdown rendering via `marked` (tables, lists, fenced code)
- KaTeX math: `$...$` and `$$...$$`
- Mermaid diagrams: ` ```mermaid ... ``` `
- Base64 media blocks and file attachments

## Restart & Disconnect Behavior

Pi is kept warm by default even if all SSE clients disconnect. Set `VIBES_PI_RESTART_ON_DISCONNECT=true` to restart Pi when all clients disconnect.

`/restart` first tries `new_session` RPC (resets session without killing the process). If that fails, it falls back to a hard process restart.

## Limitations

- Only `confirm` and `select` extension dialogs are supported. Other dialog types are auto-cancelled.
- Tool output is summarized as status updates; full tool outputs are not rendered inline (yet).

---

## RPC Protocol Details

### Event stream format

Pi emits **newline-delimited JSON** on stdout. Each line is a complete JSON object produced by `JSON.stringify()`, which always escapes control characters properly (`\n`, `\t`, etc.).

**Key finding from live testing**: Pi's JSON output is always valid. `json.loads()` with `strict=True` parses every line correctly across multiple models and 13+ MB of captured output. There are no raw control characters in Pi's stdout. Early parser issues were caused by `readline()` returning partial lines when pipe reads split across event boundaries, not by malformed JSON.

### Event types

| Event | Description |
|-------|-------------|
| `response` | Acknowledgement after sending a command |
| `agent_start` | Agent session begins (emitted after first `prompt`) |
| `turn_start` / `turn_end` | One reasoning turn (may include thinking, tool calls, and text) |
| `message_start` / `message_update` / `message_end` | Deltas: `thinking_delta`, `text_delta`, `toolcall_delta`, etc. |
| `tool_execution_start` / `tool_execution_update` / `tool_execution_end` | Tool runs with progress |
| `extension_ui_request` | Permission/choice dialogs |
| `agent_end` | **Terminal event** — the event loop exits here |

A typical flow: `response` → `agent_start` → (`turn_start` → `message_*` → `tool_*` → `turn_end`)+ → `agent_end`.

### Parser implementation

The parser (`_read_event` in `pi_client.py`) uses `reader.read(512KB)` + `json.JSONDecoder(strict=False).raw_decode()`:

- **Why not `readline()`?** Although Pi's JSON is valid, `readline()` returns partial lines when a pipe read boundary falls mid-event. Stitching partial lines is fragile and was the original source of "invalid JSON" errors.
- **Why `raw_decode()`?** It extracts the first complete JSON object from a byte buffer regardless of newline positions. No line-splitting, no stitching.
- **Why `strict=False`?** Pi's output is valid, so this is not strictly needed. It is kept as a safety margin at zero cost.
- **Buffer cap**: 16 MB. On overflow, the oldest half is discarded.
- **Error recovery**: `Unterminated string` → wait for more data. Any other `JSONDecodeError` → skip to next `{`.
- **Stuck detection**: 30s per-read timeout. After 3 consecutive timeouts with buffered data, force-skip past the stuck prefix.

### Hang prevention: activity timeouts

The most common cause of hangs is **the model API stalling mid-stream**. When the upstream model provider hits a rate limit, has an infrastructure hiccup, or simply pauses token generation, Pi has no new tokens to forward and stdout goes silent. This is not a parser bug or a pipe issue — Pi is faithfully waiting for the model.

Pi streams `thinking_delta` events continuously while models think, so any gap longer than the timeout indicates a genuine API stall rather than slow reasoning.

| Variable | Default | Description |
|----------|---------|-------------|
| `VIBES_PI_RESPONSE_TIMEOUT_S` | 120 | Max silence between any two events. Resets on every event received. |
| `VIBES_PI_AGENT_END_TIMEOUT_S` | 30 | Max wait for `agent_end` after `turn_end`. |

When a timeout fires:
- If we already have content (draft text, thinking, or tool results), the response is finalized from collected content.
- If no content has been received, a "timed out" error is returned.
- The user can also `/abort` at any time to cancel immediately.

Set either to `0` to disable (not recommended — hangs become unrecoverable without `/abort`).

### Busy-state prevention

The `request_lock` is held for the entire duration of a response. To prevent permanent "agent is busy" lockouts:

1. **Lock acquire timeout (5s)**: instead of instant-fail, waits briefly. After `/abort` cancels the in-flight task, the lock releases within this window.
2. **Task cancellation**: `/abort` and `/restart` call `cancel_current_request()` which cancels the asyncio task. `CancelledError` is caught, the lock is released via `finally`, and a `[Request cancelled]` response is returned.

---

## RPC Commands Reference

Pi's `--mode rpc` protocol accepts JSON commands on **stdin** and emits events on **stdout**. Below is the full set of supported commands (discovered from Pi v0.55.1 type definitions).

### Currently implemented

| Command | Payload | Notes |
|---------|---------|-------|
| `prompt` | `{"type":"prompt","message":"..."}` | Send a user message. Supports optional `images` and `streamingBehavior`. |
| `extension_ui_response` | `{"type":"extension_ui_response","id":"...","confirmed":true}` | Respond to permission/choice dialogs. |
| `set_model` | `{"type":"set_model","provider":"...","modelId":"..."}` | Change model live (no restart). |
| `set_thinking_level` | `{"type":"set_thinking_level","level":"high"}` | Change thinking level live. |
| `get_state` | `{"type":"get_state"}` | Query current session state. |
| `get_available_models` | `{"type":"get_available_models"}` | List available models. |
| `new_session` | `{"type":"new_session"}` | Reset session (keeps process alive). |
| `steer` | `{"type":"steer","message":"..."}` | Mid-turn steering. |
| `abort` | `{"type":"abort"}` | Cancel current execution. |

### Not yet implemented

| Command | Payload | Description |
|---------|---------|-------------|
| `follow_up` | `{"type":"follow_up","message":"..."}` | Queue a follow-up after the current turn. |
| `compact` | `{"type":"compact"}` | Trigger context window compaction. |
| `get_commands` | `{"type":"get_commands"}` | List slash commands from extensions. |
| `cycle_model` | `{"type":"cycle_model"}` | Cycle to the next model. |
| `cycle_thinking_level` | `{"type":"cycle_thinking_level"}` | Cycle thinking level. |
| `bash` / `abort_bash` | `{"type":"bash","command":"..."}` | Direct bash execution via RPC. |
| `set_steering_mode` | `{"type":"set_steering_mode","mode":"all"}` | Steering message batching. |
| `set_follow_up_mode` | `{"type":"set_follow_up_mode","mode":"all"}` | Follow-up message batching. |

### Prompt streaming behavior

The `prompt` command accepts an optional `streamingBehavior` field:
- `"steer"` — if the agent is already streaming, treat as a steering message
- `"followUp"` — if already streaming, queue as a follow-up

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| No response, agent appears hung | Model API stall; activity timeout will finalize | Wait for 120s timeout, or `/abort` |
| "Pi agent is busy, please try again" | Previous request lock still held | `/abort` to cancel, then retry |
| Response appears after `/restart` | Previous request timed out or was cancelled | Expected — check logs for timeout warnings |
| `timed out waiting for agent_end` | Pi stopped sending events after `turn_end` | Normal — response is finalized from collected content |
| `read timeout with N bytes buffered` | Parser stuck on incomplete buffer prefix | Auto-recovers by skipping; check if Pi version changed |
| Pi not starting | Executable not in PATH | Verify `which pi` works from the server process |
