# ACP Hardening Status (Go implementation)

This document summarizes hardening work completed in the Go port and the remaining risk areas.

## Implemented hardening

### Transport / lifecycle

- Uses dedicated ACP client with request/response correlation and async notification handling.
- Non-fatal agent initialization: server boots even if ACP agent binary/auth is unavailable.
- Single event-consumer model from provider to SSE (`forwardAgentEvents`) avoids channel races.

### Streaming correctness

- Handles `session/update` notifications for draft/thought/status/plan streams.
- Accumulates draft text per prompt turn (`CollectedDraft`) for persisted response fallback.
- Fixed content-block parsing to support ACP text shape `{type:"text", text:"..."}`.

### Permission + command safety

- Permission timeout flow implemented with explicit timeout/cancel handling.
- Sensitive routes can be guarded by `VIBES_API_TOKEN` (header/bearer/query token).
- Terminal endpoint is disabled by default (`VIBES_ENABLE_TERMINAL=false`).

### Surface hardening

- CORS is opt-in via `VIBES_CORS_ALLOW_ORIGIN` (not wildcard by default).
- Optional pprof endpoints behind explicit opt-in (`VIBES_ENABLE_PPROF`) and token middleware.

## Operational toggles

| Variable | Purpose |
|---|---|
| `VIBES_ACP_DEBUG` | Wire-level ACP logs |
| `VIBES_API_TOKEN` | Protect sensitive/mutating endpoints |
| `VIBES_CORS_ALLOW_ORIGIN` | Restrict browser origin access |
| `VIBES_ENABLE_TERMINAL` | Opt-in PTY WebSocket |
| `VIBES_ENABLE_PPROF` | Opt-in profiling endpoints |

## Remaining improvement backlog

1. Deeper typed ACP schema handling for all optional update variants.
2. Richer tool-call lifecycle state (per-toolCallId merge semantics).
3. Additional ACP conformance tests against more agents/providers.
4. Rotating wire-log sink option for long-running production diagnostics.

## Notes

This file supersedes older Python-era ACP hardening checklists. Current implementation references are in `internal/agent/acp/`.
