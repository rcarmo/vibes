# Vibes

A mobile-friendly web UI for coding agents, supporting [ACP](https://docs.github.com/en/copilot) (`copilot --acp`, [`codex-acp`](https://github.com/openai/codex)) and [Pi](https://pi.dev) via RPC. Inspired by [Toad](https://github.com/batrachianai/toad), built for personal use over Tailscale.

![Demo](docs/demo.gif)

> Vibes and [piclaw](https://github.com/rcarmo/piclaw) share the same web UI.

## Features

- **Streaming chat** — real-time SSE with Markdown, KaTeX, and Mermaid rendering
- **Workspace explorer** — file tree with previews, drag-and-drop upload, and folder downloads
- **Code editor** — tabbed CodeMirror 6 editor (13 languages, Vim mode, search/replace, pop-out windows)
- **Agent controls** — approve/deny tool calls, queue follow-ups, mid-turn steering (Pi), slash commands
- **Rich media** — paste images, attach files, OpenGraph link previews
- **SQLite storage** — messages, media, and full-text search in a single file
- **PWA** — installable, dark/light themes, responsive from phone to desktop

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
# Run the server (defaults to copilot --acp)
vibes

# Or with custom options
VIBES_DEFAULT_AGENT=pi VIBES_HOST=127.0.0.1 VIBES_PORT=3000 vibes

# Use codex-acp as the agent
VIBES_ACP_AGENT="codex-acp" vibes

# Manage agent permission whitelist
vibes whitelist add "Run command"
vibes whitelist remove "Run command"
vibes whitelist list
```

## Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| `Cmd/Ctrl+S` | Save current editor tab |
| `Cmd/Ctrl+F` | Search/replace in editor |
| `Escape` | Close active editor tab |
| `Alt+V` | Toggle Vim mode |
| `Alt+W` | Toggle whitespace visibility |
| `↑` / `↓` | Cycle compose history |

Type `/commands` in the chat input to list all slash commands.

## Configuration

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md). For Pi integration, see [docs/PI_MODE.md](docs/PI_MODE.md). For the full API, see [docs/API.md](docs/API.md).

## Development

```bash
pip install -e ".[dev]"        # dev dependencies
make check                     # lint + 388 unit tests + 34 E2E tests
make build-frontend            # rebuild JS/CSS bundles (requires bun)
bunx playwright test           # E2E tests (Chromium + WebKit)
make serve                     # run dev server
```

## License

MIT
