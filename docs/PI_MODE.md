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
