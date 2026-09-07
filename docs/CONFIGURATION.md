# Configuration

Run Vibes from the workspace directory you want the browser and agent to use. Relative paths below resolve from that directory.

Settings resolve in this order: environment variables (including `.env` values loaded without replacing existing environment entries), a settings JSON file, then defaults. Vibes looks for `.vibes/settings.json` in the current directory first, then `$XDG_CONFIG_HOME/vibes/settings.json` (or `~/.config/vibes/settings.json`). It selects one settings file, rather than merging both. JSON keys use the lower-case names without the `VIBES_` prefix, such as `acp_agent`.

See [installation](INSTALLATION.md) for setup, upgrades and network protection. There is no built-in login; the default loopback bind is deliberate.

| Variable | Default | Description |
|----------|---------|-------------|
| `VIBES_HOST` | `127.0.0.1` | Server bind address; protect remote access with authentication |
| `VIBES_PORT` | `8080` | Server port |
| `VIBES_DB_PATH` | `database/vibes.db` | SQLite database path |
| `VIBES_DEBUG` | `false` | Enable debug mode |
| `VIBES_ACP_AGENT` | `vibe-acp` | Installed ACP command, e.g. `copilot --acp` or `opencode acp`; agent authentication is separate |
| `VIBES_AGENT_NAME` | `<hostname>` | Agent display name |
| `VIBES_PERMISSION_TIMEOUT` | `30` | Seconds before permission request times out |
| `VIBES_PERMISSION_AUTO_APPROVE` | `false` | Auto-approve all agent permission requests |
| `VIBES_DISCONNECT_TIMEOUT` | `300` | Seconds to wait before restarting agent on disconnect |
| `VIBES_ACP_DEBUG` | `false` | Enable verbose ACP wire logging |
| `VIBES_ACP_THROTTLE_RPS` | `0` | Max ACP messages per second (0 = no throttling) |
| `VIBES_DEFAULT_AGENT` | `acp` | Default agent mode (`acp` or `pi`) for the `default` agent id |
| `VIBES_PI_AGENT` | `pi --mode rpc --no-session --append-system-prompt <vibes prompt> -e <package>/extensions/pi-vibes-tools.ts` | Pi RPC command to spawn when Pi mode is enabled (default resolves to the packaged extension path and includes the Vibes prompt) |
| `VIBES_PI_ENABLED` | `false` | Enable Pi RPC agent (auto-enabled when `VIBES_DEFAULT_AGENT=pi`) |
| `VIBES_PI_RESTART_ON_DISCONNECT` | `false` | Restart Pi agent when all SSE clients disconnect |
| `VIBES_CONFIG_PATH` | `config/endpoints.json` | Path to custom endpoints config; inline `endpoints` in settings JSON override matching entries |
| `VIBES_ACP_MESSAGES_ENABLED` | `false` | Inject the read-only, conversation-scoped messages MCP server into supporting ACP sessions |
| `VIBES_ACP_WORKSPACE_READ_ENABLED` | `false` | Add bounded workspace read/list tools; also requires messages enabled; POSIX only |
| `VIBES_PI_MODEL` | unset | Initial Pi model override |
| `VIBES_PI_THINKING` | unset | Initial Pi thinking-level override |
| `VIBES_PI_RESPONSE_TIMEOUT_S` | `120` | Pi idle event timeout; `0` disables it |
| `VIBES_PI_AGENT_END_TIMEOUT_S` | `30` | Wait for Pi agent-end after turn-end; `0` disables it |
| `VIBES_PROMPT` | empty | User prompt appended to the adapter's system prompt |
| `VIBES_AGENT_AVATAR` | empty | Agent avatar URL |
| `VIBES_USER_NAME` | empty | User display name |
| `VIBES_USER_AVATAR` | empty | User avatar URL |
| `VIBES_USER_AVATAR_BACKGROUND` | empty | User avatar background |

`VIBES_ENABLE_TERMINAL` is a separate, environment-only switch: `1` or `true` enables the POSIX terminal; it is disabled otherwise. It is not a settings JSON field, and unlike the settings booleans below, it does not accept `yes`. Enabling it grants shell access as the server account.

For Pi mode details, see [docs/PI_MODE.md](PI_MODE.md).

Boolean values accept: `1`, `true`, `yes` (case-insensitive).

## Permission whitelist

Whitelist entries are persisted in the SQLite database at `VIBES_DB_PATH`. They match agent permission requests, not browser file operations or terminal commands. Broad patterns and `VIBES_PERMISSION_AUTO_APPROVE=true` bypass approval checks; leave them off unless you intend that access.

Manage entries with the CLI, from the same working directory/environment as the server:

```bash
vibes whitelist add "Run command" --description "Auto-approved: Run command"
vibes whitelist remove "Run command"
vibes whitelist list
```

## Custom endpoints (config/endpoints.json)

Vibes can map **custom action IDs** to prompts using `config/endpoints.json` (path configurable via `VIBES_CONFIG_PATH`).
These actions are triggered with `POST /agent/{agent_id}/action/{action_id}` and enqueue an agent response.

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

### Field meanings

- `endpoints` (object, required): map of `action_id` → action definition.
- `description` (string, optional): used as a default prompt if `prompt` is not provided.
- `prompt` (string, optional): explicit prompt template used when action is triggered.
- `params` (array of strings, optional): parameter names expected by the action. These are **not** enforced server‑side, but are appended to the prompt when provided.
- `agent_id` (string, optional): informational only; the **request path** (`/agent/{agent_id}/...`) selects the actual agent.

### How prompts are built

When you trigger an action:

1. `prompt` is used if present; otherwise `description` is used (or `action_id` as a fallback).
2. If `params` are supplied in the request body, they are appended as JSON:

```
<prompt text>

Params: {"url": "https://example.com"}
```

### Triggering a custom action

**Request**

```
POST /agent/{agent_id}/action/{action_id}
Content-Type: application/json

{
  "thread_id": 123,
  "params": {
    "url": "https://example.com"
  }
}
```

**Response (immediate)**

```json
{
  "status": "queued",
  "agent_id": "default",
  "action_id": "summarize"
}
```

**Actual result**

The agent response is **async**:
- Stored as a new interaction in the thread.
- Broadcast over SSE as `agent_response`.
There is no synchronous response payload beyond the `queued` acknowledgment.
