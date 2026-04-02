# SPEC.md

## Overview

A single-user, mobile-friendly single-page application (SPA) that enables Slack-like interactions with coding agents via the ACP protocol and Pi RPC. The app supports text, links, images/files, threaded conversations, rich media previews, a workspace file explorer, and a built-in code editor. It uses an asyncio-based Python backend (aiohttp) and stores all interactions in a SQLite database using JSON columns with virtual indexing for efficient querying.

---

## Architecture

| Layer | Technology |
|-------|------------|
| Frontend | Preact + HTM (vendored), CodeMirror 6, bundled via Bun |
| Backend | Python with aiohttp + ACP protocol + Pi RPC |
| Database | SQLite with JSON columns and virtual columns for indexing |
| Live Updates | Server-Sent Events (SSE) |
| Authentication | Deferred to upstream proxy/IDP |
| CORS | Open |

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

**Framework:** aiohttp

### Agent Integration

Vibes supports two agent backends:
- **ACP** (Agent Client Protocol) — stdio-based JSON-RPC communication with agents like `copilot --acp` and `codex-acp`
- **Pi RPC** — Pi's `--mode rpc` protocol with streaming drafts, thinking traces, tool events, and live model/thinking control

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
- Event types: connection, posts, replies, agent responses, status, drafts, permissions

---

## Database Schema

**Engine:** SQLite

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
| Real-time | `GET /sse/stream` (11 event types) |

---

## Deployment

- Installable via pip from https://github.com/rcarmo/vibes
- Minimal Dockerfile and CI/CD workflows
- Single-user mode
- CORS enabled
- Authentication handled externally
- Static frontend bundled into the pip package

---

## File Structure

```
/
├── src/vibes/
│   ├── __init__.py
│   ├── app.py              # aiohttp application factory + routes
│   ├── db.py               # Database layer (SQLite with BLOBs)
│   ├── config.py           # Configuration loader
│   ├── middleware.py        # HTTP middleware
│   ├── acp_client.py       # ACP agent subprocess + JSON-RPC
│   ├── acp_protocol.py     # ACP protocol types + helpers
│   ├── pi_client.py        # Pi RPC agent subprocess
│   ├── pi_prompt.py        # Pi system prompt generation
│   ├── slash_commands.py   # Slash command dispatch
│   ├── followups.py        # Queue/steering logic
│   ├── tasks.py            # Background task management
│   ├── opengraph.py        # OpenGraph link preview fetcher
│   ├── avatar.py           # Avatar serving
│   ├── routes/
│   │   ├── posts.py        # Timeline, threads, search
│   │   ├── media.py        # Media upload/serve from DB
│   │   ├── workspace.py    # Workspace file tree + CRUD
│   │   ├── agents.py       # Agent messaging, queue, permissions
│   │   ├── avatar.py       # Avatar endpoint
│   │   └── sse.py          # Server-Sent Events
│   ├── extensions/
│   │   └── pi-vibes-tools.ts  # Pi extension for file attachments
│   └── static/
│       ├── index.html
│       ├── css/styles.css
│       ├── js/
│       │   ├── app.js               # Main Preact SPA
│       │   ├── api.js               # API client
│       │   ├── components/
│       │   │   ├── compose-box.js   # Message compose
│       │   │   ├── editor.js        # CodeMirror 6 editor
│       │   │   ├── tab-strip.js     # Editor tab bar
│       │   │   ├── timeline.js      # Message timeline
│       │   │   ├── workspace-explorer.js  # File tree sidebar
│       │   │   ├── status.js        # Agent status panels
│       │   │   ├── markdown-preview.js    # Markdown rendering
│       │   │   └── sunburst.js      # Context pie chart
│       │   ├── panes/
│       │   │   └── editor-popout-transfer.js  # Popout state transfer
│       │   └── vendor/              # Vendored Preact + HTM
│       └── dist/                    # Built bundles (bun)
├── config/
│   └── endpoints.json       # Custom action definitions
├── data/                    # Runtime data (DB, workspace)
├── tests/
│   ├── e2e/
│   │   └── editor-tabs.spec.mjs  # Playwright E2E tests (34 tests)
│   └── test_*.py            # pytest unit tests (388 tests)
├── docs/
│   ├── API.md               # Full API endpoint reference
│   ├── CONFIGURATION.md     # Environment variable reference
│   ├── PI_MODE.md           # Pi RPC integration details
│   ├── ACP_HARDENING.md     # ACP protocol hardening plan
│   └── ACP_ROUTING.md       # ACP streaming/filtering notes
├── build.js                 # Bun build script
├── playwright.config.mjs    # Playwright config (Chromium + WebKit)
├── Makefile                 # Build, lint, test, serve targets
├── package.json             # Frontend dependencies
└── pyproject.toml           # Python packaging
```
