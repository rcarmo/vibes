# Vibes

A single-user, mobile-friendly SPA for Slack-like interactions with coding agents via the ACP protocol (including [`copilot --acp`](https://docs.github.com/en/copilot) and [`codex-acp`](https://github.com/openai/codex)), as well as direct integration with [`pi`](https://pi.dev). Heavily inspired by [Toad](https://github.com/batrachianai/toad)'s ACP implementation, (which is stellar), but aimed at providing my own mobile agent interface over Tailscale.

## Highlights

![Demo](docs/demo.gif)

> Vibes and [piclaw](https://github.com/rcarmo/piclaw) share the same web UI.

- **Streaming web UI** — real-time token-by-token updates over SSE, with Markdown, KaTeX, and Mermaid rendering
- **Workspace explorer** — file tree sidebar with previews, drag-and-drop upload, keyboard navigation, and downloads
- **Code editor** — built-in CodeMirror 6 with syntax highlighting for 13 languages, Vim mode, search/replace, and save
- **Persistent storage** — SQLite-backed messages, media, and full-text search
- **Rich media** — paste or drag images, attach workspace files, link previews with OpenGraph
- **Dark/Light themes** — follows system preference automatically
- **Installable PWA** — standalone webapp manifest with window-controls-overlay support

## Web UI

The UI is single-user, mobile-friendly, and streams updates over SSE:

- **Thought/Draft panels** — collapsible live reasoning and draft blocks, visible during streaming
- **Live steering** — inject follow-up guidance while the agent is still responding (`/steer`)
- **File attachments** — drag, paste, or pick images; attach workspace files as reference pills
- **Link previews** — server-side OpenGraph fetch with image thumbnails
- **Multi-turn threading** — subsequent turns are visually threaded under the first
- **Accept/Deny tool usage** — approve, deny, or always-allow agent operations with command previews
- **Context window indicator** — colour-coded pie chart showing token usage (green / amber / red)
- **Compose history** — up/down arrow keys cycle through last 200 messages
- **Full-text search** — search conversations using SQLite FTS
- **Mobile-first layout** — responsive design for phone, tablet, and desktop

### Workspace explorer

The sidebar shows a file tree with auto-refresh. Click a file to preview it or add a **file reference pill** to the next prompt. Drag and drop files onto the tree to upload them, with overwrite conflict detection.

- **Keyboard navigation** — arrow keys to browse, Enter to open/edit, Delete to remove, Escape to deselect
- **Per-folder upload** — hover a folder to reveal its upload button
- **Touch support** — long-press to delete files on mobile
- **Hidden files toggle** — show/hide dotfiles (persisted)
- **Download** — single files or entire folders as ZIP

### Code editor

Click the **pencil icon** on any text file preview (up to 256 KB) to open the built-in editor. It appears as a resizable centre pane between the sidebar and the chat.

- **13 languages** — JS/TS, Python, Go, JSON, CSS, HTML, YAML, SQL, XML, Markdown, Shell, plus auto-detection
- **Search and replace** — Cmd/Ctrl+F
- **Save** — Cmd/Ctrl+S or the Save button; dirty state is tracked
- **Vim mode** — toggle with Alt+V (persisted)
- **Whitespace visibility** — toggle with Alt+W (persisted)
- **Line wrapping**, line numbers, active line highlight, and indentation markers
- **Dark/Light theme** — switches automatically with system preference

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
| `/prompt` | Show or set the user system prompt |
| `/user-name` | Set or show your display name |
| `/user-avatar` | Set or show your avatar URL |
| `/user-github` | Set name and avatar from a GitHub profile |
| `/agent-name` | Set or show the agent display name |
| `/agent-avatar` | Set or show the agent avatar URL |
| `/queue <message>` | Queue a message for after the current turn |

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

## Configuration

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md). For Pi RPC integration, see [docs/PI_MODE.md](docs/PI_MODE.md).

## API Endpoints

See [docs/API.md](docs/API.md).

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
make check           # lint + tests (344 tests)

# Run frontend linting (requires bun)
make lint-frontend

# Rebuild frontend bundle
make build-frontend  # bundles JS + CSS via bun

# Run with make
make serve
```

## License

MIT
