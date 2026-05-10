# Pi Mode Integration

Vibes can use a Pi coding agent via Pi RPC events and commands.

## Enable Pi mode

```bash
VIBES_DEFAULT_AGENT=pi
VIBES_PI_ENABLED=true
```

Optional:

```bash
VIBES_PI_AGENT="pi"
```

Agent ids:

- `default` → uses `VIBES_DEFAULT_AGENT`
- `pi` → Pi provider
- `acp` → ACP provider

## Implementation locations

- `internal/agent/pi/client.go` — Pi provider (spawn, prompt, event routing)
- `internal/routes/commands.go` — slash command integration (`/model`, `/thinking`, `/abort`, `/steer`, `/restart`)
- `static/js/app.js` — draft/thought/status rendering via SSE

## Supported Pi event mapping

The provider reads NDJSON-style events from stdout using a buffered scanner and maps:

- `message_*` + `delta.type=text_delta` → `draft`
- `message_*` + `delta.type=thinking_delta` → `thought`
- `tool_execution_*`, `turn_*`, `agent_start` → `status`
- `extension_ui_request` → `permission`
- `agent_end` → `response`

## Supported Pi commands (current)

| Command | Purpose |
|---|---|
| `prompt` | send user prompt |
| `steer` | mid-turn guidance |
| `abort` | cancel active turn |
| `set_model` | switch model |
| `set_thinking_level` | change thinking level |
| `new_session` | reset session |
| `get_state` | fetch current state |
| `get_available_models` | list models |
| `extension_ui_response` | respond to confirm/select prompts |

## Behavior notes

- Pi provider is process-backed and streams incremental UI updates.
- `/restart` attempts a session reset (`new_session`) and falls back to restart logic if needed.
- Permission dialogs currently support confirm/select flows.

## Limitations

- Advanced extension dialog types beyond confirm/select are not rendered as rich UI yet.
- Tool execution output is shown as status updates, not full rich per-tool panes.
