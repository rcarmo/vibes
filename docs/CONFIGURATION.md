# Configuration

Vibes reads configuration from environment variables (and a `.env` file if present).

| Variable | Default | Description |
|----------|---------|-------------|
| `VIBES_HOST` | `0.0.0.0` | Server bind address |
| `VIBES_PORT` | `8080` | Server port |
| `VIBES_DB_PATH` | `database/vibes.db` | SQLite database path |
| `VIBES_DEBUG` | `false` | Enable debug mode (verbose logging) |
| `VIBES_ACP_AGENT` | `copilot-language-server --acp --stdio` | ACP agent command. Set to `codex-acp` or `claude-agent-acp` for other backends. |
| `VIBES_AGENT_NAME` | `<hostname>` | Agent display name |
| `VIBES_PERMISSION_TIMEOUT` | `30` | Seconds before permission request times out |
| `VIBES_PERMISSION_AUTO_APPROVE` | `false` | Auto-approve all agent permission requests |
| `VIBES_DISCONNECT_TIMEOUT` | `300` | Seconds to wait before restarting agent on disconnect |
| `VIBES_ACP_DEBUG` | `false` | Enable verbose ACP wire logging |
| `VIBES_ACP_THROTTLE_RPS` | `0` | Max ACP messages per second (0 = no throttling) |
| `VIBES_DEFAULT_AGENT` | `acp` | Default agent mode (`acp` or `pi`) for the `default` agent id |
| `VIBES_PI_AGENT` | *(auto)* | Pi RPC command to spawn when Pi mode is enabled |
| `VIBES_PI_ENABLED` | `false` | Enable Pi RPC agent (auto-enabled when `VIBES_DEFAULT_AGENT=pi`) |
| `VIBES_PI_RESTART_ON_DISCONNECT` | `false` | Restart Pi agent when all SSE clients disconnect |
| `VIBES_CONFIG_PATH` | `config/endpoints.json` | Path to custom endpoints config |
| `VIBES_EXTENSIONS_DIR` | `extensions` | Directory to scan for extensions |

Boolean values accept: `1`, `true`, `yes` (case-insensitive).

## Agent selection

Vibes supports three ACP agents out of the box:

```bash
# GitHub Copilot (default)
VIBES_ACP_AGENT="copilot-language-server --acp --stdio"

# OpenAI Codex
VIBES_ACP_AGENT="codex-acp"

# Claude
VIBES_ACP_AGENT="claude-agent-acp"
```

The agent binary must be in `$PATH`. Install via npm:

```bash
npm install -g @github/copilot-language-server    # GitHub Copilot
npm install -g @openai/codex                       # codex-acp is bundled
npm install -g @agentclientprotocol/claude-agent-acp  # Claude
```

## Permission whitelist

Whitelist entries are persisted in the SQLite database at `VIBES_DB_PATH`.
Manage entries via the API:

```bash
# List whitelist
curl http://localhost:8080/agent/whitelist

# Add pattern
curl -X POST http://localhost:8080/agent/whitelist \
  -H 'Content-Type: application/json' \
  -d '{"pattern": "Run command"}'

# Remove pattern
curl -X DELETE http://localhost:8080/agent/whitelist \
  -H 'Content-Type: application/json' \
  -d '{"pattern": "Run command"}'
```

## Custom endpoints (config/endpoints.json)

Vibes can map **custom action IDs** to prompts using `config/endpoints.json`.
These actions are triggered with `POST /agent/{agent_id}/action/{action_id}`.

### File format

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

See [docs/API.md](API.md) for the full custom endpoint triggering reference.
