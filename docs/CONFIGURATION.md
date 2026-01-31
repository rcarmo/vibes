# Configuration

Vibes reads configuration from environment variables (and a `.env` file if present).

| Variable | Default | Description |
|----------|---------|-------------|
| `VIBES_HOST` | `0.0.0.0` | Server bind address |
| `VIBES_PORT` | `8080` | Server port |
| `VIBES_DB_PATH` | `database/vibes.db` | SQLite database path |
| `VIBES_DEBUG` | `false` | Enable debug mode |
| `VIBES_ACP_AGENT` | `vibe-acp` | ACP agent command |
| `VIBES_AGENT_NAME` | `<hostname>` | Agent display name |
| `VIBES_PERMISSION_TIMEOUT` | `30` | Seconds before permission request times out |
| `VIBES_DISCONNECT_TIMEOUT` | `300` | Seconds to wait before restarting agent on disconnect |
| `VIBES_ACP_DEBUG` | `false` | Enable verbose ACP wire logging |
| `VIBES_CONFIG_PATH` | `config/endpoints.json` | Path to custom endpoints config |

Boolean values accept: `1`, `true`, `yes` (case-insensitive).
