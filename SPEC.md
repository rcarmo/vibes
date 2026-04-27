# SPEC.md

## Overview

A single-user, mobile-friendly single-page application (SPA) that enables Slack-like interactions with coding agents via the ACP protocol and Pi RPC. The Go backend (`main` branch) is a port of the original Python implementation (preserved on the `python` branch). It ships as a single static binary (~24 MB) using a chi router, pure-Go SQLite (`modernc.org/sqlite`), and embedded frontend assets (`//go:embed`). All interactions are stored in a SQLite database using JSON columns with virtual indexing and FTS5 for full-text search.

---

## Architecture

| Layer | Technology |
|-------|------------|
| Frontend | Preact + HTM (vendored), CodeMirror 6, bundled via Bun |
| Backend | Go with chi router + ACP protocol + Pi RPC |
| Database | SQLite (pure Go via modernc.org/sqlite) with JSON columns |
| Live Updates | Server-Sent Events (SSE) |
| Authentication | Deferred to upstream proxy/IDP |
| CORS | Open |
| Extensions | Go interface + JSON manifests for frontend panels |

---

## Features

- Post text, links, images, and files
- Threaded conversations with ACP and Pi agents
- Rich media previews (downscaled and stored in database)
- Live updates via SSE with token-by-token streaming
- Workspace file explorer with file tree, upload, download, and previews
- Built-in code editor with tabbed editing, popout windows, and syntax highlighting
- Queued follow-ups and mid-turn steering
- Accept/deny agent tool usage with command previews
- Context window indicator (colour-coded pie chart)
- Compose history (up/down arrow keys cycle through last 200 messages)
- Full-text search via SQLite FTS
- Responsive design for mobile, tablet, and desktop
- Dark/light mode following system preference
- Markdown, KaTeX math, and Mermaid diagram rendering
- Installable PWA with window-controls-overlay support
- Extension system for backend routes, SSE events, and frontend UI panels

---

## Frontend

**Framework:** Preact + HTM (vendored), bundled with Bun

### Styling
- Cross-platform sans-serif font stack
- CSS media queries for responsive breakpoints (mobile, tablet, desktop)
- Dark/light mode using CSS variables (follows `prefers-color-scheme`)

### UI Layout
- **Three-pane layout** — workspace sidebar (left), editor stack (centre), chat timeline (right)
- Resizable panes via drag handles / splitters
- Workspace sidebar toggleable (auto-hides on narrow viewports)
- Chat compose box with file attachment pills, queue stack, and steering controls
- Agent status indicator with context-window pie chart

### Components

| Component | File | Description |
|-----------|------|-------------|
| `App` | `app.js` | Root SPA component; all state management |
| `Timeline` / `Post` | `timeline.js` | Message timeline with threading, media, and attachment previews |
| `ComposeBox` | `compose-box.js` | Text input with file pills, queue stack, history |
| `WorkspaceExplorer` | `workspace-explorer.js` | File tree sidebar with upload, preview, keyboard nav |
| `WorkspaceEditor` | `editor.js` | CodeMirror 6 editor with save, dirty tracking, status bar |
| `TabStrip` | `tab-strip.js` | Editor tab bar with context menu (close, pin, popout) |
| `AgentStatus` | `status.js` | Streaming panels (Draft, Thoughts, Planning) + spinner |
| `MarkdownPreview` | `markdown-preview.js` | Markdown/KaTeX/Mermaid rendering |
| `Sunburst` | `sunburst.js` | Context-window pie chart |

### Editor details

- **13 languages** — JS/TS, Python, Go, JSON, CSS, HTML, YAML, SQL, XML, Markdown, Shell, plus auto-detection
- **Tabbed editing** — multiple files open as tabs; dirty state shown as a dot indicator
- **Save** — Cmd/Ctrl+S; dirty state tracked per tab
- **Close** — Escape to close the active editor tab
- **Open in Window** — pop out any tab into a standalone editor-only popup window
- **Tab context menu** — Close, Close Others, Close All, Pin/Unpin, Open in Window
- **Vim mode** — Alt+V (persisted)
- **Whitespace visibility** — Alt+W (persisted)
- **Dark/Light theme** — switches automatically with system preference

### Popout (editor-only) mode

When a tab is popped out via "Open in Window", the new window:
- Opens as a popup window (820×620) centred on screen
- Runs in **editor-only mode** — no sidebar, no chat, no tab bar
- Receives editor content via localStorage transfer for instant hydration
- The original tab is removed from the parent window

---

## Backend

**Framework:** Go with chi router

### Agent Integration

Vibes supports multiple agent backends via a common `Provider` interface:
- **ACP** (Agent Client Protocol) — stdio-based JSON-RPC communication with agents like `copilot-language-server --acp`, `codex-acp`, and `claude-agent-acp`
- **Pi RPC** — Pi's `--mode rpc` protocol with streaming drafts, thinking traces, tool events, and live model/thinking control

Agent switching is done via an `agent.Registry` that maps agent IDs to providers. The active agent can be changed at runtime.

### Extension System

Extensions implement a Go interface and can provide:
- HTTP routes (mounted on the chi router)
- SSE event types (broadcast via the SSE broker)
- Static assets (served under `/ext/{id}/`)
- Frontend UI panel manifests (sidebar, toolbar, overlay, main area)

### Media Handling
- Accept image/file uploads
- Downscale images and store as BLOBs in the database
- Generate and serve rich previews from database

### Workspace
- Serve the agent's working directory as a browsable file tree
- Support file CRUD, rename, move, upload, and folder download (as ZIP)
- Detect binary vs text files for preview routing
- File editing via the built-in editor (PUT `/workspace/file`)

### Live Updates
- SSE endpoint for real-time updates to the frontend
- Per-client buffered channels with goroutine-per-connection fanout
- Event types: connection, posts, replies, agent responses, status, drafts, permissions

---

## Database Schema

**Engine:** SQLite (pure Go via `modernc.org/sqlite`)

### Design Principles
- Use JSON columns for flexible data storage
- Implement virtual columns for indexing and querying
- Store media as BLOBs for easy migration/backup

### Tables

#### `interactions`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PRIMARY KEY | Auto-increment |
| timestamp | DATETIME | Creation time |
| data | JSON | Flexible payload |

**Virtual columns (indexed):**
- `type` (from `data->>'type'`)
- `thread_id` (from `data->>'thread_id'`)
- `agent_id` (from `data->>'agent_id'`)

#### `media`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PRIMARY KEY | Auto-increment |
| filename | TEXT | Original filename |
| content_type | TEXT | MIME type |
| data | BLOB | Original file binary |
| thumbnail | BLOB | Downscaled preview binary |
| metadata | JSON | Additional metadata (dimensions, size, etc.) |

---

## API Endpoints

See [docs/API.md](docs/API.md) for the full endpoint reference.

### Summary

| Section | Endpoints |
|---------|-----------|
| Health | `GET /health` |
| Timeline & Posts | 7 endpoints — CRUD, search, hashtags, threads |
| Media | 4 endpoints — upload, serve, thumbnail, info |
| Workspace | 12 endpoints — tree, file CRUD, rename, move, upload, download, attach, visibility |
| Agents | 16 endpoints — list, status, context, models, commands, queue, messaging, actions, permissions, whitelist |
| Avatars | `GET /avatar/{kind}` |
| Extensions | `GET /extensions` — list manifests; `/ext/{id}/*` — static assets |
| Real-time | `GET /sse/stream` (11 event types) |

---

## Deployment

- Single static binary (~11 MB), cross-compilable for any Go-supported platform
- Minimal Dockerfile (scratch-based)
- Single-user mode
- CORS enabled
- Authentication handled externally
- Static frontend embedded or served from `static/` directory

---

## File Structure

```
vibes/
├── cmd/
│   ├── vibes/
│   │   └── main.go              # Entry point
│   └── acp-test/
│       └── main.go              # ACP agent integration test
├── internal/
│   ├── app/
│   │   └── app.go               # chi router + application wiring
│   ├── config/
│   │   └── config.go            # Configuration (env vars)
│   ├── db/
│   │   ├── db.go                # Database layer
│   │   ├── migrations.go        # Schema migrations
│   │   └── queries.go           # Typed queries
│   ├── agent/
│   │   ├── provider.go          # AgentProvider interface + Registry
│   │   ├── acp/
│   │   │   └── client.go        # ACP client (wraps acp-sdk-go)
│   │   └── pi/
│   │       └── client.go        # Pi RPC client
│   ├── server/
│   │   └── sse/
│   │       └── broker.go        # SSE connection management + fanout
│   ├── routes/
│   │   ├── timeline.go          # Timeline, threads, search
│   │   ├── media.go             # Media upload/serve
│   │   ├── workspace.go         # Workspace file tree + CRUD
│   │   └── agents.go            # Agent messaging, queue, permissions
│   ├── extensions/
│   │   └── registry.go          # Extension discovery + lifecycle
│   └── media/
│       └── processing.go        # Image downscaling, thumbnails
├── static/                      # Frontend (Preact + HTM + CodeMirror 6)
│   ├── index.html
│   ├── css/
│   ├── js/
│   ├── dist/
│   └── fonts/
├── config/
│   └── endpoints.json           # Custom action definitions
├── docs/
│   ├── API.md
│   ├── CONFIGURATION.md
│   ├── PI_MODE.md
│   ├── ACP_ROUTING.md
│   └── ACP_HARDENING.md
├── build.js                     # Bun build script (frontend)
├── package.json
├── go.mod
├── go.sum
├── Makefile
└── LICENSE
```
