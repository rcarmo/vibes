# Configuration

Vibes reads configuration from environment variables (and a `.env` file if present).

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `VIBES_HOST` | `0.0.0.0` | Server bind address |
| `VIBES_PORT` | `8080` | Server port |
| `VIBES_DB_PATH` | `database/vibes.db` | SQLite database path |
| `VIBES_DEBUG` | `false` | Enable debug mode (verbose structured logging) |
| `VIBES_COPILOT_AGENT` | `copilot-language-server --acp --stdio` | GitHub Copilot ACP command to probe/spawn |
| `VIBES_COPILOT_ENABLED` | `true` | Enable Copilot backend discovery |
| `VIBES_CODEX_AGENT` | `codex-acp` | Codex ACP command to probe/spawn |
| `VIBES_CODEX_ENABLED` | `true` | Enable Codex backend discovery |
| `VIBES_AGENT_NAME` | `<hostname>` | Agent display name |
| `VIBES_PERMISSION_TIMEOUT` | `30` | Seconds before permission request auto-cancels |
| `VIBES_PERMISSION_AUTO_APPROVE` | `false` | Auto-approve all agent permission requests |
| `VIBES_DISCONNECT_TIMEOUT` | `300` | Seconds to keep agent alive after last SSE client disconnects |
| `VIBES_ACP_DEBUG` | `false` | Enable verbose ACP wire logging |
| `VIBES_ACP_THROTTLE_RPS` | `0` | Max ACP messages per second (0 = unlimited) |
| `VIBES_ACP_MCP_SERVERS_JSON` | _(unset)_ | JSON array of MCP servers to pass to ACP sessions |
| `VIBES_DEFAULT_AGENT` | `acp` | Default backend (`acp` is treated as `copilot` for compatibility) |
| `VIBES_PI_AGENT` | `pi` | Pi binary path for native RPC mode |
| `VIBES_PI_ENABLED` | `true` | Enable Pi native RPC provider discovery/probing (set `false` to hide/disable Pi) |
| `VIBES_PI_RESTART_ON_DISCONNECT` | `false` | Restart Pi when all SSE clients disconnect |
| `VIBES_CONFIG_PATH` | `config/endpoints.json` | Custom action definitions |
| `VIBES_EXTENSIONS_DIR` | `extensions` | Extension scan directory |
| `VIBES_WORKSPACE` | `<cwd>` | Workspace root for file explorer |
| `VIBES_CORS_ALLOW_ORIGIN` | _(unset)_ | Enable CORS for a specific origin (or `*`); also used as terminal WS origin allowlist override |
| `VIBES_API_TOKEN` | _(unset)_ | Optional token required for sensitive/mutating routes |
| `VIBES_ENABLE_TERMINAL` | `false` | Enable `/terminal/ws` PTY WebSocket endpoint (same-origin by default) |
| `VIBES_ENABLE_PPROF` | `false` | Enable `/debug/pprof/*` profiling endpoints |

Boolean values accept: `1`, `true`, `yes` (case-insensitive).

## API token auth (optional)

If `VIBES_API_TOKEN` is set, sensitive/mutating routes require a token via one of:

- `X-API-Token: <token>`
- `Authorization: Bearer <token>`
- `?token=<token>` (fallback)

This includes all mutating routes (`POST`/`PUT`/`PATCH`/`DELETE`) plus sensitive read routes like `/workspace*`, optional `/terminal/ws`, and optional `/debug/pprof*`.


## Agent selection

Vibes uses product-level backend identities (`pi`, `copilot`, `codex`) with transport metadata (`pi-rpc`, `acp`). Backend discovery is hybrid: defaults are probed on launch, and environment variables can override or disable each backend.

Vibes supports ACP backends plus Pi native RPC:

```bash
# GitHub Copilot (default ACP backend)
VIBES_COPILOT_AGENT="copilot-language-server --acp --stdio"

# OpenAI Codex
VIBES_CODEX_AGENT="codex-acp"

# Pi native RPC (richer: streaming drafts, thinking, live model control)
VIBES_DEFAULT_AGENT=pi
```

### ACP MCP servers

ACP sessions can receive MCP server definitions through `VIBES_ACP_MCP_SERVERS_JSON`. This is the recommended portable way to provide extra tools/context to ACP agents.

Stdio MCP servers are always eligible because ACP requires agents to support stdio MCP. HTTP and SSE MCP servers are passed only when the agent advertises the corresponding `mcpCapabilities.http` or `mcpCapabilities.sse` flag during `initialize`.

```bash
export VIBES_ACP_MCP_SERVERS_JSON='[
  {
    "name": "workspace-tools",
    "command": "workspace-mcp-server",
    "args": ["--root", "/path/to/workspace"],
    "env": {"LOG_LEVEL": "info"}
  },
  {
    "type": "http",
    "name": "remote-tools",
    "url": "https://example.test/mcp",
    "headers": {"Authorization": "Bearer ${TOKEN_FROM_ENV_OR_WRAPPER}"}
  }
]'
```

Keep secrets out of committed files. Prefer wrapper commands or inherited process environment for secret material; if headers/env are included in the JSON, treat the environment variable as sensitive.

Current ACP client-service limitations:

- Vibes negotiates and stores ACP prompt/MCP/session/auth capabilities.
- Vibes passes configured MCP servers to `session/new`, filtering unsupported HTTP/SSE transports.
- Vibes still advertises no ACP client filesystem or terminal capabilities; `fs/*`, `terminal/*`, and ACP permission request handling are planned but disabled until explicit safety gates are implemented.
- Prompt payloads are still text-only; resource links, embedded resources, image, and audio blocks are planned follow-up work.

### Installing agent binaries

```bash
npm install -g @github/copilot-language-server       # Copilot
npm install -g @openai/codex                          # Codex (includes codex-acp)
npm install -g @agentclientprotocol/claude-agent-acp  # Claude
npm install -g pi-acp                                 # Pi ACP adapter
npm install -g opencode-ai                            # OpenCode (free models)
npm install -g @mariozechner/pi-coding-agent          # Pi (native RPC)
```

## Slash commands

Available via the compose box (type `/` to see autocomplete):

| Command | Description |
|---|---|
| `/model [provider/model]` | Show or change the active model |
| `/model list` | List available models |
| `/thinking [level]` | Show or change thinking level |
| `/restart` | Reset agent session |
| `/abort` | Cancel current request |
| `/steer <message>` | Send mid-turn steering guidance |
| `/user-name [name]` | Show or set your display name |
| `/user-avatar [url]` | Show or set your avatar URL |
| `/user-github <username>` | Set your name/avatar from a GitHub profile |
| `/commands` | List all slash commands |
| `/clear` | Clear the timeline display |
| `/shell <command>` | Run a shell command (30s timeout) |
| `/bash <command>` | Alias for `/shell` |

## Permission whitelist

Whitelist entries auto-approve matching tool calls. Managed via API:

```bash
# List
curl http://localhost:8080/agent/whitelist

# Add (supports glob: "Run *" matches "Run command", "Run script", etc.)
curl -X POST http://localhost:8080/agent/whitelist \
  -H 'Content-Type: application/json' \
  -d '{"pattern": "Run *", "description": "Auto-approve all run commands"}'

# Remove
curl -X DELETE http://localhost:8080/agent/whitelist \
  -H 'Content-Type: application/json' \
  -d '{"pattern": "Run *"}'
```

## Custom endpoints (config/endpoints.json)

Map custom action IDs to prompts:

```json
{
  "endpoints": {
    "summarize": {
      "description": "Summarize a web page",
      "prompt": "Summarize the following URL",
      "params": ["url"],
      "agent_id": "default"
    }
  }
}
```

Trigger with `POST /agent/{agent_id}/action/{action_id}`.

## Database

SQLite with WAL mode. Location controlled by `VIBES_DB_PATH`.

Schema:
- `interactions` — JSON column with virtual columns (type, thread_id, agent_id) + FTS5
- `media` — BLOBs for files and thumbnails
- `whitelist` — permission patterns

The database is the single source of truth. Back up `vibes.db` to preserve all messages, media, and settings.
