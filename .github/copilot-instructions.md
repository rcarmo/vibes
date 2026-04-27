# Vibes — Copilot Instructions

This is the Go implementation of Vibes (main branch). The Python version lives on the `python` branch.

## Key files

- `cmd/vibes/main.go` — entry point
- `internal/app/app.go` — application wiring
- `internal/config/config.go` — environment-based configuration
- `internal/agent/provider.go` — agent provider interface and registry
- `internal/agent/acp/client.go` — ACP client wrapping keepmind9/acp-sdk-go
- `internal/extensions/registry.go` — extension system
- `internal/server/sse/broker.go` — SSE fanout broker
- `static/` — frontend (Preact + HTM, bundled with Bun)

## Conventions

- Use `log/slog` for structured logging
- Use `context.Context` for cancellation and timeouts
- Use interfaces for testability (agent.Provider, extensions.Extension)
- Config is loaded from `VIBES_*` environment variables
- The frontend is shared with the Python version — do not modify frontend files without checking compatibility
- ACP protocol handling must be metadata-only (no content heuristics) per docs/ACP_ROUTING.md
