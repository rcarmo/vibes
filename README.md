# Vibes

A single-user, mobile-friendly SPA for Slack-like interactions with coding agents via the ACP protocol, as well as direct integration with [`pi`](https://pi.dev). Heavily inspired by [Toad](https://github.com/batrachianai/toad)'s ACP implementation, (which is stellar), but aimed at providing my own mobile agent interface over Tailscale.

![Demo](docs/demo.gif)

> Vibes and [piclaw](https://github.com/rcarmo/piclaw) share the same web UI.

## Features

- Persistent, infinite scrolling conversations with ACP agents and `pi`
- Accept/Deny tool usage by agents, with command previews
- Live reasoning/intent updates via Server-Sent Events (SSE)
- Post text, links, images, and files
- Rich media previews (downscaled and stored in database)
- KaTeX maths and SVG image support
- API endpoints for predefined custom actions/prompts
- Full-text search using `sqlite` FTS
- Responsive design for mobile, tablet, and desktop
- Dark/light mode

## Non-Features

- Authentication (use `authelia` or an authenticating reverse proxy)
- Security (use `traefik` or Tailscale)
- Multiple users (should be trivial to add)

## Roadmap

- [ ] Better integration with multimodal models (ACP punts on that right now)
- [x] Slash commands
- [x] Switching agents/models

## Slash Commands

Type a `/` command in the message input to control the agent or run utilities without sending a prompt. Built-in commands are handled instantly; unknown commands are forwarded to the agent as regular prompts.

| Command | Description |
|---|---|
| `/commands` | List all available slash commands |
| `/model` | Show the current model (Pi) or agent binary (ACP) |
| `/model <provider/model>` | Switch the Pi agent to a different model (live, no restart) |
| `/thinking` | Show current thinking level and available levels |
| `/thinking <level>` | Set thinking level (`off`, `minimal`, `low`, `medium`, `high`, `xhigh`) live |
| `/steer <message>` | Inject mid-turn guidance while the agent is thinking/working |
| `/abort` | Cancel the current agent operation |
| `/restart` | Reset the agent session (or hard restart as fallback) |
| `/shell <command>` | Run a shell command and display the output |

> **Note:** `/model`, `/thinking`, `/steer`, and `/abort` use Pi's RPC protocol and apply to the Pi agent only. ACP agents do not expose these controls.

## Installation

```bash
# Install directly from GitHub
pip install -U git+https://github.com/rcarmo/vibes.git

# Install a specific tag
pip install -U "vibes @ git+https://github.com/rcarmo/vibes.git@v0.1.0"

# Or with uv (faster alternative, installs as isolated tool)
uv tool install git+https://github.com/rcarmo/vibes.git

# Install a specific tag with uv
uv tool install "vibes @ git+https://github.com/rcarmo/vibes.git@v0.1.0"
```

Or for development:

```bash
git clone https://github.com/rcarmo/vibes.git
cd vibes
pip install -e ".[dev]"
```

## Usage

```bash
# Run the server
vibes

# Or with custom options
VIBES_DEFAULT_AGENT=pi VIBES_HOST=127.0.0.1 VIBES_PORT=3000 vibes

# Manage agent permission whitelist
vibes whitelist add "Run command"
vibes whitelist remove "Run command"
vibes whitelist list
```

## Configuration

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md). For Pi RPC integration, see [docs/PI_MODE.md](docs/PI_MODE.md).

## API Endpoints

See [docs/API.md](docs/API.md).

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest

# Run frontend linting (requires bun)
make lint-frontend

# Run with make
make serve
```

## License

MIT
