# Vibes — Go Port

This branch is a **work-in-progress** port of [Vibes](https://github.com/rcarmo/vibes) from Python (aiohttp) to Go.

> **Status: design phase** — scaffolding and ACP research, not yet functional.

## Why Go

- Single static binary — no Python, no virtualenv, no pip
- Lower memory footprint for always-on deployments (Tailscale, homelab)
- Native concurrency (goroutines) maps well to SSE fanout + stdio agent management
- Easy cross-compilation for ARM (Proxmox nodes, Raspberry Pi, etc.)
- CGo-free SQLite via `modernc.org/sqlite` for true single-binary builds

## Verified ACP agents

All four ACP agents have been tested against our Go ACP client (via `cmd/acp-test/main.go`):

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

## Architecture

### Agent backends

Vibes supports multiple agent backends via a common interface:

```
                    ┌──────────────────────┐
                    │   AgentProvider      │ (interface)
                    │   Initialize()       │
                    │   Prompt()           │
                    │   Cancel()           │
                    │   Events() <-chan     │
                    └────────┬─────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
     ┌─────────────┐ ┌────────────┐ ┌────────────┐
     │ ACP Provider │ │ Pi Provider│ │ Extension  │
     │ (stdio)      │ │ (RPC)     │ │ Provider   │
     └──────┬──────┘ └─────┬─────┘ └─────┬──────┘
            │               │              │
     ┌──────┴──────┐ ┌─────┴─────┐  ┌─────┴──────┐
     │copilot --acp│ │pi --rpc   │  │ custom     │
     │codex-acp    │ │           │  │ agents     │
     │claude-acp   │ │           │  │            │
     └─────────────┘ └───────────┘  └────────────┘
```

### ACP library choice

| Library | Stars | Notes |
|---|---|---|
| **`keepmind9/acp-sdk-go`** | 0 | Full ACP SDK: typed schema, stdio transport, contrib helpers (ToolCallTracker, PermissionBroker, SessionAccumulator). Recent (Apr 2026). Best fit. |
| `zhangweiii/acpnet` | 0 | TCP/HTTP bridge for ACP — networking layer, not a protocol SDK |
| Roll our own | — | ACP is JSON-RPC 2.0 over stdio; straightforward but ~2 weeks of schema work |

**Recommendation**: start with `keepmind9/acp-sdk-go` as the ACP layer. It provides:
- Typed Go structs for all ACP schema types
- `ClientSideConnection` for sending prompts and receiving streaming updates
- `transport.Spawn` for launching agent subprocesses
- `ToolCallTracker`, `PermissionBroker`, `SessionAccumulator` in contrib
- Agent binary switching is just changing the spawn command

If the SDK proves insufficient, we can fork or replace individual layers since ACP is a simple protocol.

### Switching between agents

```go
// Agent registry — switch at runtime
registry := agent.NewRegistry()
registry.Register("copilot", agent.ACPConfig{Command: "copilot-language-server", Args: []string{"--acp", "--stdio"}})
registry.Register("codex",   agent.ACPConfig{Command: "codex-acp"})
registry.Register("claude",  agent.ACPConfig{Command: "claude-agent-acp"})
registry.Register("pi-acp",  agent.ACPConfig{Command: "pi-acp"})
registry.Register("pi",      agent.PiConfig{Command: "pi", Args: []string{"--mode", "rpc"}})

// Select agent per request or globally
provider := registry.Get("copilot")
```

### Extension system

Inspired by piclaw's architecture, the Go port will support UI extensions:

```
vibes-go/
├── extensions/             # Extension mount point
│   ├── registry.go         # Extension discovery + lifecycle
│   ├── types.go            # Extension interface definitions
│   └── builtin/            # Built-in extensions
│       ├── workspace/      # Workspace file explorer
│       └── editor/         # Code editor
├── static/
│   └── extensions/         # Frontend extension assets
│       └── {ext}/
│           ├── manifest.json
│           ├── index.js
│           └── styles.css
```

Extension interface:

```go
// Extension is the interface all extensions implement
type Extension interface {
    // Metadata
    ID() string
    Name() string
    Version() string

    // Lifecycle
    Init(ctx context.Context, app *App) error
    Shutdown(ctx context.Context) error

    // HTTP routes (optional)
    Routes() []Route

    // SSE event types (optional)
    EventTypes() []string

    // Static assets directory (optional, served under /ext/{id}/)
    StaticDir() string

    // Frontend manifest (optional, for UI panel registration)
    Manifest() *ExtensionManifest
}

// ExtensionManifest describes frontend UI panels
type ExtensionManifest struct {
    Panels []PanelDef `json:"panels"`  // sidebar, main area, or overlay panels
    CSS    []string   `json:"css"`     // CSS files to inject
    JS     []string   `json:"js"`      // JS modules to load
}

// PanelDef describes a UI panel
type PanelDef struct {
    ID       string `json:"id"`
    Title    string `json:"title"`
    Position string `json:"position"` // "sidebar", "main", "overlay", "toolbar"
    Icon     string `json:"icon"`     // Font Awesome class or SVG path
    Default  bool   `json:"default"`  // visible by default
}
```

This allows:
- **Backend extensions**: register HTTP routes, SSE event types, background tasks
- **Frontend extensions**: inject CSS/JS, register UI panels (sidebar, toolbar, overlays)
- **piclaw-style viewers**: draw.io, office, image viewers as drop-in extensions
- **Custom agent tools**: extensions can expose tools to agents via the workspace

## Go module structure

```
vibes-go/
├── cmd/
│   └── vibes/
│       └── main.go              # Entry point
├── internal/
│   ├── app/
│   │   └── app.go               # Application wiring
│   ├── config/
│   │   └── config.go            # Configuration (env + file)
│   ├── db/
│   │   ├── db.go                # SQLite database layer
│   │   ├── migrations.go        # Schema migrations
│   │   └── queries.go           # Typed queries
│   ├── agent/
│   │   ├── provider.go          # AgentProvider interface
│   │   ├── registry.go          # Agent registry + switching
│   │   ├── acp/
│   │   │   ├── client.go        # ACP client (wraps acp-sdk-go)
│   │   │   ├── streaming.go     # Stream routing (draft/thought/plan)
│   │   │   └── permissions.go   # Permission broker
│   │   └── pi/
│   │       ├── client.go        # Pi RPC client
│   │       ├── parser.go        # NDJSON event parser
│   │       └── commands.go      # Pi slash commands
│   ├── server/
│   │   ├── server.go            # HTTP server setup
│   │   ├── routes.go            # Route registration
│   │   ├── middleware.go        # Logging, CORS, etc.
│   │   └── sse/
│   │       ├── broker.go        # SSE connection management
│   │       └── events.go        # Event types
│   ├── routes/
│   │   ├── timeline.go          # Timeline + posts
│   │   ├── media.go             # Media upload/serve
│   │   ├── workspace.go         # Workspace file tree + CRUD
│   │   ├── agents.go            # Agent messaging + queue
│   │   └── search.go            # Full-text search
│   ├── extensions/
│   │   ├── registry.go          # Extension discovery + lifecycle
│   │   ├── types.go             # Extension interfaces
│   │   └── builtin/             # Built-in extensions
│   └── media/
│       └── processing.go        # Image downscaling, thumbnails
├── static/                      # Frontend (reused from Python vibes)
│   ├── index.html
│   ├── css/
│   ├── js/
│   └── dist/
├── extensions/                  # User/third-party extensions
├── go.mod
├── go.sum
├── Makefile
└── Dockerfile
```

## Technology choices

| Concern | Choice | Rationale |
|---|---|---|
| HTTP framework | `net/http` + `chi` router | stdlib-based, minimal deps, middleware ecosystem |
| SQLite | `modernc.org/sqlite` | Pure Go, no CGo, single binary |
| ACP protocol | `keepmind9/acp-sdk-go` | Typed schema, transport, contrib helpers |
| SSE | Custom (trivial in Go) | `http.Flusher` + goroutine per client |
| JSON | `encoding/json` + `github.com/goccy/go-json` | stdlib compat, faster option available |
| Image processing | `golang.org/x/image` | Thumbnails, downscaling |
| Config | `github.com/caarlos0/env` | Struct-tag env parsing |
| Logging | `log/slog` | stdlib structured logging |
| Testing | `testing` + `testify` | stdlib + assertions |

## Migration plan

### Phase 1 — Core server + ACP
- [ ] Go module init + dependency setup
- [ ] Config loader (env vars, matching Python vibes)
- [ ] SQLite database layer with migrations
- [ ] HTTP server with health endpoint
- [ ] SSE broker
- [ ] ACP client using acp-sdk-go
- [ ] Agent registry with runtime switching
- [ ] Basic timeline routes (GET/POST)
- [ ] Media upload/serve

### Phase 2 — Full API parity
- [ ] All timeline/thread/search routes
- [ ] Workspace file tree + CRUD
- [ ] Agent messaging + queue + permissions
- [ ] Pi RPC client
- [ ] Slash command dispatch
- [ ] OpenGraph link previews

### Phase 3 — Frontend + extensions
- [ ] Serve existing frontend static files
- [ ] Extension registry + manifest loading
- [ ] Extension HTTP route mounting
- [ ] Extension static asset serving
- [ ] Built-in workspace extension
- [ ] Built-in editor extension

### Phase 4 — Production
- [ ] Dockerfile (scratch-based, ~15 MB)
- [ ] Makefile targets (build, test, lint, cross-compile)
- [ ] GitHub Actions CI
- [ ] systemd unit file
- [ ] PWA manifest + service worker

## Compatibility

The Go port aims to be **API-compatible** with the Python version:
- Same HTTP endpoints
- Same SSE event format
- Same SQLite schema
- Same frontend (shared static files)
- Same config env vars (with `VIBES_` prefix)

This means the existing frontend works unchanged with the Go backend.
