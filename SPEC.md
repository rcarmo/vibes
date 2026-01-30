# SPEC.md

## Overview

A single-user, mobile-friendly single-page application (SPA) that enables Twitter-like interactions with coding agents via the ACP protocol. The app supports text, links, images/files, threaded conversations, and rich media previews. It uses an asyncio-based Python backend (aiohttp) and stores all interactions in a SQLite database using JSON columns with virtual indexing for efficient querying.

---

## Architecture

| Layer | Technology |
|-------|------------|
| Frontend | Preact + HTM (vendored) |
| Backend | Python with aiohttp + python-sdk for ACP |
| Database | SQLite with JSON columns and virtual columns for indexing |
| Live Updates | Server-Sent Events (SSE) |
| Authentication | Deferred to upstream proxy/IDP |
| CORS | Open |

---

## Features

- Post text, links, images, and files
- Threaded conversations with ACP agents
- Rich media previews (downscaled and stored in database)
- Live updates via SSE
- Configurable custom endpoints for predefined agent tasks
- Responsive design for mobile, tablet, and desktop
- Dark/light mode toggle

---

## Frontend

**Framework:** Preact + HTM (vendored)

### Styling
- Cross-platform sans-serif font stack
- CSS media queries for responsive breakpoints (mobile, tablet, desktop)
- Dark/light mode using CSS variables

### UI Layout
- Timeline view similar to old Twitter
- Compose box for new posts
- Threaded replies
- Media preview components

---

## Backend

**Framework:** aiohttp

### ACP Integration
- Use python-sdk from `agentclientprotocol/python-sdk`
- Maintain persistent sessions with agents
- Support custom endpoints for predefined tasks (e.g., summarizing a web page)

### Media Handling
- Accept image/file uploads
- Downscale images and store as BLOBs in the database
- Generate and serve rich previews from database

### Live Updates
- Implement SSE endpoints for real-time updates to the frontend

---

## Database Schema

**Engine:** SQLite

### Design Principles
- Use JSON columns for flexible data storage
- Implement virtual columns for indexing and querying
- Store media as BLOBs for easy migration/backup
- Follow guidance from SQLite JSON Virtual Columns & Indexing

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

### Public
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sse/stream` | SSE endpoint for live updates |
| GET | `/media/{id}` | Serve media files from database |
| GET | `/media/{id}/thumbnail` | Serve downscaled previews from database |

### Authenticated (via upstream proxy)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/post` | Submit new post (text/link/image/file) |
| POST | `/reply` | Reply to a thread |
| POST | `/agent/{agent_id}/action/{action_id}` | Trigger custom agent action |
| GET | `/thread/{thread_id}` | Retrieve full thread context |

---

## Deployment

- Installable via pip from https://github.com/rcarmo/vibes 
- Minimal Dockerfile and CI/CD workflows similar to https://github.com/rcarmo/webterm
- Single-user mode
- CORS enabled
- Authentication handled externally
- Static frontend served by aiohttp but bundled into the pip package

---

## Notes

- All user-agent interactions are stored and indexed for context reconstruction
- Custom endpoints can be configured via a JSON file or environment variables
- Media processing uses PIL or similar for image downscaling
- All media stored in database for single-file backup/migration

---

## Future Enhancements

- Multi-user support
- Plugin system for custom agent actions

---

# Implementation Plan

## Phase 1: Project Setup & Foundation

- [ ] **1.1 Initialize project structure**
  - Create directory layout: `src/`, `static/`
  - Create `requirements.txt` with dependencies: `aiohttp`, `aiosqlite`, `pillow`
  - Create `pyproject.toml` for packaging

- [ ] **1.2 Set up database layer**
  - Create `src/db.py` with async SQLite connection management
  - Implement schema initialization with migrations support
  - Create `interactions` table with JSON columns and virtual column indexes
  - Create `media` table with BLOB columns for file storage
  - Write unit tests for database operations

- [ ] **1.3 Create base aiohttp application**
  - Create `src/app.py` with aiohttp application factory
  - Configure CORS middleware (open policy)
  - Set up static file serving for `/static/`
  - Add health check endpoint (`GET /health`)

## Phase 2: Core Backend API

- [ ] **2.1 Implement interactions API**
  - `POST /post` – Create new post (text, link, image, file)
  - `POST /reply` – Reply to existing thread
  - `GET /thread/{thread_id}` – Fetch full thread with all interactions
  - `GET /timeline` – Fetch paginated timeline (newest first)
  - Add request validation and error handling

- [ ] **2.2 Implement media handling (database storage)**
  - `POST /media/upload` – Accept multipart file uploads, store as BLOB
  - `GET /media/{id}` – Serve media from database BLOB
  - `GET /media/{id}/thumbnail` – Serve thumbnail from database BLOB
  - Implement image downscaling with PIL (max 800px, JPEG 80%)
  - Store both original and thumbnail as BLOBs in `media` table

- [ ] **2.3 Implement SSE for live updates**
  - `GET /sse/stream` – SSE endpoint with event types:
    - `new_post` – New post created
    - `new_reply` – Reply added to thread
    - `agent_response` – Agent responded
  - Implement connection management and heartbeat (30s keepalive)
  - Add reconnection support with `Last-Event-ID`

## Phase 3: ACP Agent Integration

- [ ] **3.1 Set up ACP client**
  - Install and configure `python-sdk` from agentclientprotocol
  - Create `src/acp_client.py` wrapper for agent communication
  - Implement session management (persistent sessions per agent)

- [ ] **3.2 Implement agent endpoints**
  - `POST /agent/{agent_id}/message` – Send message to agent
  - `POST /agent/{agent_id}/action/{action_id}` – Trigger predefined action
  - `GET /agents` – List available agents and their capabilities
  - Handle async agent responses and push via SSE

- [ ] **3.3 Custom endpoint configuration**
  - Create `config/endpoints.json` schema for custom actions
  - Implement config loader with environment variable overrides
  - Add validation for custom endpoint definitions

## Phase 4: Frontend Implementation

- [ ] **4.1 Set up frontend foundation**
  - Vendor Preact + HTM (no build step required)
  - Create `static/index.html` as SPA entry point
  - Create `static/js/app.js` with Preact application
  - Create `static/css/styles.css` with CSS variables for theming

- [ ] **4.2 Implement CSS framework**
  - Define CSS variables for colors, spacing, typography
  - Implement dark/light mode toggle with `prefers-color-scheme` support
  - Create responsive breakpoints: mobile (<640px), tablet (640-1024px), desktop (>1024px)
  - Style timeline, compose box, thread view components

- [ ] **4.3 Build UI components**
  - `<App>` – Root component with routing
  - `<Timeline>` – Scrollable list of posts
  - `<Post>` – Individual post with media previews
  - `<ComposeBox>` – Text input with file attachment
  - `<ThreadView>` – Expanded thread with replies
  - `<MediaPreview>` – Image/file preview component
  - `<ThemeToggle>` – Dark/light mode switch

- [ ] **4.4 Implement API integration**
  - Create `static/js/api.js` with fetch wrappers
  - Implement SSE client with auto-reconnect
  - Add optimistic UI updates for posts
  - Handle error states and loading indicators

## Phase 5: Polish & Testing

- [ ] **5.1 End-to-end testing**
  - Test full post → agent response → SSE update flow
  - Test media upload and retrieval from database
  - Test responsive layout on different viewports
  - Test dark/light mode persistence

- [ ] **5.2 Error handling & edge cases**
  - Handle network failures gracefully
  - Add retry logic for failed API calls
  - Implement offline indicator
  - Validate file types and sizes on upload

- [ ] **5.3 Documentation**
  - Create `README.md` with setup instructions
  - Document API endpoints with examples
  - Add configuration reference for custom endpoints

## Phase 6: Deployment Preparation

- [ ] **6.1 Production configuration**
  - Create `Dockerfile` for containerized deployment
  - Add environment variable configuration
  - Set up logging with structured JSON output
  - Add graceful shutdown handling

- [ ] **6.2 Final verification**
  - Run full test suite
  - Verify all endpoints work correctly
  - Test with actual ACP agent
  - Performance check on timeline loading

---

## File Structure

```
/
├── src/
│   ├── __init__.py
│   ├── app.py          # aiohttp application factory
│   ├── db.py           # Database layer (SQLite with BLOBs)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── posts.py    # Post/reply endpoints
│   │   ├── media.py    # Media upload/serve from DB
│   │   ├── sse.py      # Server-Sent Events
│   │   └── agents.py   # ACP agent integration
│   ├── acp_client.py   # ACP SDK wrapper
│   └── config.py       # Configuration loader
├── static/
│   ├── index.html
│   ├── css/
│   │   └── styles.css
│   └── js/
│       ├── app.js      # Main Preact app
│       ├── api.js      # API client
│       └── vendor/     # Vendored Preact + HTM
├── config/
│   └── endpoints.json  # Custom endpoint definitions
├── data/
│   └── app.db          # SQLite database (contains all data + media)
├── requirements.txt
├── Dockerfile
└── README.md
```
