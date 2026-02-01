# Configuration

Vibes reads configuration from environment variables (and a `.env` file if present).

| Variable | Default | Description |
|----------|---------|-------------|
| `VIBES_HOST` | `0.0.0.0` | Server bind address |
| `VIBES_PORT` | `8080` | Server port |
| `VIBES_DB_PATH` | `database/vibes.db` | SQLite database path |
| `VIBES_DEBUG` | `false` | Enable debug mode |
| `VIBES_ACP_AGENT` | `vibe-acp` | ACP agent command (recommended: `copilot --acp --model gpt-5-mini` |
| `VIBES_AGENT_NAME` | `<hostname>` | Agent display name |
| `VIBES_PERMISSION_TIMEOUT` | `30` | Seconds before permission request times out |
| `VIBES_DISCONNECT_TIMEOUT` | `300` | Seconds to wait before restarting agent on disconnect |
| `VIBES_ACP_DEBUG` | `false` | Enable verbose ACP wire logging |
| `VIBES_CONFIG_PATH` | `config/endpoints.json` | Path to custom endpoints config |

Boolean values accept: `1`, `true`, `yes` (case-insensitive).

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
