# Configuration

Vibes reads configuration from environment variables (and a `.env` file if present).

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `VIBES_HOST` | `0.0.0.0` | Server bind address |
| `VIBES_PORT` | `8080` | Server port |
| `VIBES_DB_PATH` | `database/vibes.db` | SQLite database path |
| `VIBES_DEBUG` | `false` | Enable debug mode (verbose structured logging) |
| `VIBES_ACP_AGENT` | `copilot-language-server --acp --stdio` | ACP agent command to spawn |
| `VIBES_AGENT_NAME` | `<hostname>` | Agent display name |
| `VIBES_PERMISSION_TIMEOUT` | `30` | Seconds before permission request auto-cancels |
| `VIBES_PERMISSION_AUTO_APPROVE` | `false` | Auto-approve all agent permission requests |
| `VIBES_DISCONNECT_TIMEOUT` | `300` | Seconds to keep agent alive after last SSE client disconnects |
| `VIBES_ACP_DEBUG` | `false` | Enable verbose ACP wire logging |
| `VIBES_ACP_THROTTLE_RPS` | `0` | Max ACP messages per second (0 = unlimited) |
| `VIBES_DEFAULT_AGENT` | `acp` | Default agent mode (`acp` or `pi`) |
| `VIBES_PI_AGENT` | `pi` | Pi binary path for native RPC mode |
| `VIBES_PI_ENABLED` | `false` | Enable Pi native RPC provider (auto-enabled when `DEFAULT_AGENT=pi`) |
| `VIBES_PI_RESTART_ON_DISCONNECT` | `false` | Restart Pi when all SSE clients disconnect |
| `VIBES_CONFIG_PATH` | `config/endpoints.json` | Custom action definitions |
| `VIBES_EXTENSIONS_DIR` | `extensions` | Extension scan directory |
| `VIBES_WORKSPACE` | `<cwd>` | Workspace root for file explorer |

Boolean values accept: `1`, `true`, `yes` (case-insensitive).

## Agent selection

Vibes supports four ACP agents plus Pi native RPC:

```bash
# GitHub Copilot (default)
VIBES_ACP_AGENT="copilot-language-server --acp --stdio"

# OpenAI Codex
VIBES_ACP_AGENT="codex-acp"

# Claude
VIBES_ACP_AGENT="claude-agent-acp"

# Pi via ACP adapter
VIBES_ACP_AGENT="pi-acp"

# OpenCode (free models — ideal for CI/testing)
VIBES_ACP_AGENT="opencode acp"

# Pi native RPC (richer: streaming drafts, thinking, live model control)
VIBES_DEFAULT_AGENT=pi VIBES_PI_ENABLED=true
```

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
| `/commands` | List all slash commands |
| `/clear` | Clear the timeline display |
| `/shell <command>` | Run a shell command (30s timeout) |

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
