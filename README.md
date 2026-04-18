# Vibes

A mobile-friendly web UI for coding agents, written in Go. Supports [ACP](https://agentclientprotocol.com/) agents (`copilot`, `codex-acp`, `claude-agent-acp`, `pi-acp`) and [Pi](https://pi.dev) via native RPC. Inspired by [Toad](https://github.com/batrachianai/toad), built for personal use over Tailscale.

![Demo](docs/demo.gif)

> Vibes and [piclaw](https://github.com/rcarmo/piclaw) share the same web UI design language. The extension system is inspired by piclaw's architecture.

## Features

- **Streaming chat** — real-time SSE with Markdown, KaTeX, and Mermaid rendering
- **Workspace explorer** — file tree with previews, drag-and-drop upload, and folder downloads
- **Code editor** — tabbed CodeMirror 6 editor (13 languages, Vim mode, search/replace, pop-out windows)
- **Agent controls** — approve/deny tool calls, queue follow-ups, mid-turn steering, slash commands
- **Rich media** — paste images, attach files, OpenGraph link previews
- **SQLite storage** — messages, media, and full-text search in a single file
- **PWA** — installable, dark/light themes, responsive from phone to desktop
- **Single binary** — no Python, no virtualenv, no runtime dependencies
- **Extension system** — backend routes, SSE events, and frontend UI panels (sidebar, toolbar, overlay)

## Verified ACP agents

All four ACP agents have been tested against our Go ACP client:

| Agent | Binary | ACP Version | Status |
|---|---|---|---|
| **GitHub Copilot** | `copilot-language-server --acp --stdio` | v1.472.0 | ✅ Responds to initialize |
| **OpenAI Codex** | `codex-acp` | v0.11.1 | ✅ Responds to initialize |
| **Claude Agent** | `claude-agent-acp` | v0.29.2 | ✅ Responds to initialize |
| **Pi** | `pi-acp` | v0.0.26 | ✅ Responds to initialize |

### Capability comparison

| Feature | Copilot | Codex | Claude | Pi |
|---|---|---|---|---|
| Image support | ✅ | ✅ | ✅ | ✅ |
| Embedded context | ✅ | ✅ | ✅ | — |
| MCP support | — | ✅ (HTTP) | ✅ (HTTP + SSE) | — |
| Session list/close | ✅ | ✅ | ✅ | ✅ |
| Session fork/resume | — | — | ✅ | — |
| Prompt queueing | — | — | ✅ (Claude-specific) | — |
| Auth | GitHub OAuth | ChatGPT / API key | Pre-configured | Terminal login |

All four implement ACP protocol v1 over stdio JSON-RPC and are driven by the same `internal/agent/acp/client.go` code — only the spawn command differs. Pi uses [`pi-acp`](https://github.com/svkozak/pi-acp) (★209), a community ACP adapter that wraps `pi --mode rpc`.

## Installation

### From source

```bash
git clone https://github.com/rcarmo/vibes.git
cd vibes
make build
```

This runs the full build pipeline:
1. `bun install` (frontend dependencies)
2. `bun run build.js` (bundles JS/CSS into `static/dist/`)
3. `go build` (compiles Go binary with all static assets embedded)

The resulting `vibes` binary is **fully self-contained** — no external static files, no Python, no Node.js runtime. Just deploy the binary anywhere.

### Cross-compile

```bash
make build-linux-arm64       # For Raspberry Pi, ARM Proxmox, etc.
make build-darwin-arm64      # For macOS Apple Silicon
make build-all               # Linux amd64 + arm64 + macOS arm64
```

The binary is ~23 MB with the embedded frontend bundle, with zero runtime dependencies (SQLite is pure Go via `modernc.org/sqlite`).

## Usage

```bash
# Run with GitHub Copilot (default)
./vibes

# Use Codex as the agent
VIBES_ACP_AGENT="codex-acp" ./vibes

# Use Claude
VIBES_ACP_AGENT="claude-agent-acp" ./vibes

# Use Pi via ACP adapter
VIBES_ACP_AGENT="pi-acp" ./vibes

# Use Pi's native RPC mode (richer features, not ACP)
VIBES_DEFAULT_AGENT=pi VIBES_PI_ENABLED=true ./vibes

# Custom host/port
VIBES_HOST=127.0.0.1 VIBES_PORT=3000 ./vibes
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

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for all environment variables. For Pi integration, see [docs/PI_MODE.md](docs/PI_MODE.md). For the full API, see [docs/API.md](docs/API.md).

## Architecture

See [GO_PORT.md](GO_PORT.md) for the full architecture document, including:
- Agent provider interface and registry
- ACP library choice (`keepmind9/acp-sdk-go`)
- Extension system design (inspired by piclaw)
- Module structure
- Migration plan

### Technology choices

| Concern | Choice | Rationale |
|---|---|---|
| Language | Go | Single binary, native concurrency, easy cross-compile |
| HTTP | `net/http` + `chi` | stdlib-based, minimal deps |
| SQLite | `modernc.org/sqlite` | Pure Go, no CGo, true single binary |
| ACP | `keepmind9/acp-sdk-go` | Typed schema, transport, contrib helpers |
| SSE | Custom | `http.Flusher` + goroutine per client |
| Config | `caarlos0/env` | Struct-tag env parsing |
| Logging | `log/slog` | stdlib structured logging |

## Project structure

```
vibes/
├── cmd/
│   ├── vibes/
│   │   └── main.go              # Entry point
│   └── acp-test/
│       └── main.go              # ACP agent integration test
├── internal/
│   ├── app/
│   │   └── app.go               # Application wiring (chi router)
│   ├── config/
│   │   └── config.go            # Configuration (env vars)
│   ├── agent/
│   │   ├── provider.go          # AgentProvider interface + Registry
│   │   ├── acp/
│   │   │   └── client.go        # ACP client (wraps acp-sdk-go)
│   │   └── pi/                  # Pi RPC client (planned)
│   ├── server/
│   │   └── sse/
│   │       └── broker.go        # SSE connection management + fanout
│   ├── extensions/
│   │   └── registry.go          # Extension discovery + lifecycle
│   ├── db/                      # SQLite database layer (planned)
│   ├── routes/                  # HTTP route handlers (planned)
│   └── media/                   # Image processing (planned)
├── static/                      # Frontend (Preact + HTM + CodeMirror 6)
│   ├── index.html
│   ├── css/
│   ├── js/
│   ├── dist/                    # Built bundles
│   └── fonts/
├── config/
│   └── endpoints.json           # Custom action definitions
├── docs/
│   ├── API.md                   # Full API endpoint reference
│   ├── CONFIGURATION.md         # Environment variable reference
│   ├── PI_MODE.md               # Pi RPC integration
│   ├── ACP_ROUTING.md           # ACP streaming/filtering
│   └── ACP_HARDENING.md         # ACP protocol hardening plan
├── build.js                     # Bun build script (frontend)
├── package.json                 # Frontend dependencies
├── go.mod
├── go.sum
├── Makefile
└── LICENSE
```

## Development

```bash
# Full build (frontend + Go binary, fully self-contained)
make build

# Run from source (skips frontend build, useful for backend iteration)
make dev

# Build and run with debug logging
make serve

# Test ACP agent handshakes (spawns copilot/codex/claude)
make test-acp

# Rebuild frontend bundles only
make frontend

# Lint, vet, and test
make check

# See all targets
make help
```

### Embedded assets

All static frontend assets (HTML, CSS, JS, fonts, icons) are embedded into the
Go binary at compile time via `//go:embed all:static`. This is the same pattern
used by [rcarmo/webterm](https://github.com/rcarmo/webterm) and produces a
truly self-contained binary that can be deployed anywhere without external files.

The `embed.go` file at the project root holds the directive; the `internal/app/`
package imports the root package to access `vibes.StaticFS()` for the HTTP
file server.

## License

MIT
