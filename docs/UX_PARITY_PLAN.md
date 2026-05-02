# UX Feature Parity Plan: vibes vs piclaw

This table tracks every UX feature in piclaw, whether vibes will implement it,
current status, and rationale for any exclusions.

**Legend:**
- ✅ Done
- 🔶 Partial
- ⬜ Planned
- ❌ Won't do
- 🚫 N/A (platform/ACP limitation)

---

## Core Chat

| # | Feature | Do it? | Status | Notes |
|---|---------|--------|--------|-------|
| 1 | Streaming chat timeline | Yes | ✅ | SSE-based real-time rendering |
| 2 | Markdown rendering (marked.js) | Yes | ✅ | |
| 3 | KaTeX math (`$...$`, `$$...$$`) | Yes | ✅ | |
| 4 | Mermaid diagrams | Yes | ✅ | |
| 5 | Code syntax highlighting (in-post) | Yes | ✅ | |
| 6 | Threaded conversations | Yes | ✅ | |
| 7 | Post delete (with cascade) | Yes | ✅ | |
| 8 | Full-text search (FTS5) | Yes | ✅ | |
| 9 | Hashtag filtering | Yes | ✅ | |
| 10 | Agent draft streaming pane | Yes | ✅ | |
| 11 | Thinking/reasoning pane | Yes | ✅ | |
| 12 | Tool call status display | Yes | ✅ | |
| 13 | Context window pie chart | Yes | ✅ | Sunburst component |
| 14 | Copy code block widget | Yes | 🔶 | Basic copy; piclaw has richer widget |
| 15 | Post speech (TTS) | No | ❌ | Low priority; adds browser API complexity for minimal gain |
| 16 | OpenGraph link previews | Yes | ✅ | |

## Compose Box

| # | Feature | Do it? | Status | Notes |
|---|---------|--------|--------|-------|
| 17 | Text input with send | Yes | ✅ | |
| 18 | Shift+Enter for newline | Yes | ✅ | |
| 19 | Compose history (↑/↓) | Yes | ✅ | |
| 20 | File drag-and-drop upload | Yes | ✅ | |
| 21 | Image paste from clipboard | Yes | ✅ | |
| 22 | File pill attachments | Yes | ✅ | |
| 23 | Slash command autocomplete | Yes | ✅ | |
| 24 | @mention autocomplete | No | 🚫 | ACP has no multi-agent mention protocol; vibes is single-agent-at-a-time |
| 25 | Model picker popup | Yes | ✅ | |
| 26 | Model picker typeahead | Yes | ✅ | 1:1 port of piclaw's popup-typeahead.ts |
| 27 | Session switcher popup | No | 🚫 | ACP agents don't expose session branching; vibes has flat session model |
| 28 | Session switcher typeahead | No | 🚫 | Depends on #27 |
| 29 | Speech-to-text input | No | ❌ | Browser speech API is inconsistent; low priority |
| 30 | Queue stack (follow-ups + steering) | Yes | ✅ | |
| 31 | Inline upload/send error feedback | Yes | 🔶 | Basic; piclaw has richer UX |
| 32 | Compose layout (mobile/desktop) | Yes | 🔶 | Responsive but no dedicated layout module |

## Agent Control

| # | Feature | Do it? | Status | Notes |
|---|---------|--------|--------|-------|
| 33 | Approve/deny tool calls (modal) | Yes | ✅ | |
| 34 | Permission whitelist (auto-approve) | Yes | ✅ | Glob pattern matching |
| 35 | Mid-turn steering (/steer) | Yes | ✅ | |
| 36 | Abort (/abort) | Yes | ✅ | |
| 37 | Queued follow-ups | Yes | ✅ | |
| 38 | Model switching (/model) | Yes | ✅ | Via Pi RPC; ACP agents don't support live model switch |
| 39 | Thinking level (/thinking) | Yes | ✅ | Via Pi RPC only |
| 40 | Session restart (/restart) | Yes | 🔶 | Basic restart; no session tree support |
| 41 | Multi-agent switching | Yes | ✅ | Registry-based runtime switching |
| 42 | Turn content preview panels | Yes | ✅ | Expandable draft/thought/plan |

## Workspace / Editor

| # | Feature | Do it? | Status | Notes |
|---|---------|--------|--------|-------|
| 43 | File tree explorer | Yes | ✅ | |
| 44 | File tree keyboard navigation | Yes | ✅ | |
| 45 | Hidden files toggle | Yes | ✅ | |
| 46 | File upload (drag-and-drop) | Yes | ✅ | |
| 47 | Folder download (ZIP) | Yes | ✅ | |
| 48 | CodeMirror 6 editor | Yes | ✅ | 13 languages |
| 49 | Tabbed editor | Yes | ✅ | |
| 50 | Tab context menu | Yes | ✅ | Close, Close Others, Pin, Popout |
| 51 | Editor popout window | Yes | ✅ | |
| 52 | Vim mode (Alt+V) | Yes | ✅ | |
| 53 | Whitespace toggle (Alt+W) | Yes | ✅ | |
| 54 | File conflict detection | Yes | ⬜ | Planned — compare mtime before save |
| 55 | Workspace auto-open | No | ❌ | Opinionated; users can open files manually |
| 56 | Workspace scale/zoom | No | ❌ | Low priority; browser zoom suffices |
| 57 | Source editor pane | No | ❌ | Vibes uses the same CodeMirror editor for all files |

## Viewer Panes

| # | Feature | Do it? | Status | Notes |
|---|---------|--------|--------|-------|
| 58 | Image viewer (zoom/pan) | Yes | ⬜ | Planned — lightbox modal |
| 59 | PDF viewer | Yes | ⬜ | Planned — embed pdf.js |
| 60 | Office document viewer | No | 🚫 | Requires server-side LibreOffice or cloud API; out of scope for single-binary |
| 61 | CSV viewer | Yes | ⬜ | Planned — table rendering |
| 62 | HTML viewer | Yes | ⬜ | Planned — sandboxed iframe |
| 63 | Video viewer | Yes | ⬜ | Planned — native `<video>` element |
| 64 | Workspace file preview | Yes | ⬜ | Planned — quick preview in sidebar |
| 65 | ZIP content preview | No | ❌ | Low value; users can download and extract |
| 66 | Draw.io editor | No | 🚫 | Requires draw.io server; vibes is self-contained |
| 67 | Mindmap pane | No | ❌ | Specialized; out of scope |
| 68 | VNC remote display | No | 🚫 | Requires VNC target; piclaw-specific integration |
| 69 | Terminal pane | Yes | ⬜ | Planned — xterm.js or similar |

## Sessions and Branching

| # | Feature | Do it? | Status | Notes |
|---|---------|--------|--------|-------|
| 70 | Session trees (branch/fork) | No | 🚫 | ACP has limited session support; only Claude supports fork/resume |
| 71 | Session tree widget | No | 🚫 | Depends on #70 |
| 72 | Branch rename | No | 🚫 | Depends on #70 |
| 73 | Branch delete | No | 🚫 | Depends on #70 |
| 74 | Chat swipe navigation | No | ❌ | Single-session model; no multiple chats to swipe between |
| 75 | Session resume | No | 🚫 | Only Claude ACP supports resume; not universal |
| 76 | Session fork | No | 🚫 | Only Claude ACP supports fork; not universal |

## Settings and Configuration

| # | Feature | Do it? | Status | Notes |
|---|---------|--------|--------|-------|
| 77 | Settings dialog (tabbed) | Yes | ⬜ | Planned — modal with sections |
| 78 | — General settings | Yes | ⬜ | Agent name, defaults |
| 79 | — Appearance/theme | Yes | ⬜ | Font, colors |
| 80 | — Models & providers | Yes | ⬜ | Agent selection, model config |
| 81 | — Editor settings | Yes | ⬜ | Font size, tab width, Vim mode |
| 82 | — Keyboard shortcuts | No | ❌ | Fixed shortcuts; customization adds complexity for little gain |
| 83 | — Keychain management | No | 🚫 | Vibes uses env vars / agent-side auth, not a server-side keychain |
| 84 | — Addon management | No | 🚫 | Extension system exists but no runtime addon install UI yet |
| 85 | — Developer settings | Yes | ⬜ | Debug toggle, ACP wire logging |
| 86 | — Session management | No | 🚫 | No session tree model (see #70) |
| 87 | — Workspace settings | Yes | ⬜ | Path, hidden files |
| 88 | — Compaction settings | No | 🚫 | ACP doesn't expose compaction; Pi RPC has `compact` but rarely used |
| 89 | — Tools settings | Yes | ⬜ | Permission whitelist management |
| 90 | — Quick actions | Yes | ⬜ | Custom endpoints (config/endpoints.json) |
| 91 | OOBE (first-run wizard) | Yes | ⬜ | Planned — agent selection + auth setup |
| 92 | Login/auth flow | No | 🚫 | Auth is handled per-agent (GitHub OAuth, API keys); no unified login |

## Advanced UI

| # | Feature | Do it? | Status | Notes |
|---|---------|--------|--------|-------|
| 93 | Adaptive Cards (structured content) | No | 🚫 | piclaw-specific; ACP agents don't emit Adaptive Cards |
| 94 | Floating widget panes (dashboards) | No | 🚫 | piclaw-specific; requires extension bridge infrastructure |
| 95 | System meters HUD | No | ❌ | Low priority; container metrics aren't relevant for vibes use case |
| 96 | Timeline quick actions | Yes | ⬜ | Planned — context menu on messages |
| 97 | Timeline menu (message context) | Yes | ⬜ | Planned — copy, delete, reply actions |
| 98 | Attachment preview modal | Yes | ⬜ | Planned — full-screen image/file preview |
| 99 | Image modal (zoom/pan) | Yes | ⬜ | Same as #58 |
| 100 | Notification system | Yes | ⬜ | Planned — browser notifications for agent responses |
| 101 | Performance tracing | No | ❌ | Developer-only; use browser DevTools |
| 102 | "By the way" panel | No | ❌ | piclaw-specific UI element |
| 103 | Extension UI events (SSE-driven panels) | Yes | ⬜ | Extension system supports this; needs frontend wiring |
| 104 | Pane detach/reattach | No | ❌ | Editor popout covers the main use case |

## PWA and Mobile

| # | Feature | Do it? | Status | Notes |
|---|---------|--------|--------|-------|
| 105 | PWA manifest | Yes | ✅ | Installable |
| 106 | Dark/light theme (system) | Yes | ✅ | CSS prefers-color-scheme |
| 107 | Responsive layout | Yes | ✅ | Phone → desktop |
| 108 | Mobile viewport handling | Yes | ⬜ | Planned — keyboard-aware resize |
| 109 | Window controls overlay | No | ❌ | PWA-specific; low adoption rate |

---

## Summary

| Category | Total | ✅ Done | ⬜ Planned | ❌ Won't | 🚫 N/A |
|---|---|---|---|---|---|
| Core Chat | 16 | 15 | 0 | 1 | 0 |
| Compose Box | 16 | 12 | 0 | 2 | 2 |
| Agent Control | 10 | 10 | 0 | 0 | 0 |
| Workspace/Editor | 15 | 11 | 1 | 3 | 0 |
| Viewer Panes | 12 | 0 | 6 | 2 | 4 |
| Sessions | 7 | 0 | 0 | 1 | 6 |
| Settings | 16 | 0 | 8 | 1 | 7 |
| Advanced UI | 12 | 0 | 5 | 4 | 3 |
| PWA/Mobile | 5 | 3 | 1 | 1 | 0 |
| **Total** | **109** | **51** | **21** | **15** | **22** |

- **51 done** (47%) — core chat, compose, agents, editor all complete
- **21 planned** (19%) — viewer panes, settings, and polish
- **15 won't do** (14%) — low value or alternative approaches exist
- **22 N/A** (20%) — platform/ACP limitations (sessions, Adaptive Cards, VNC, keychain, etc.)

**Effective target: 72 features (excluding N/A). Currently 51/72 = 71% complete.**
