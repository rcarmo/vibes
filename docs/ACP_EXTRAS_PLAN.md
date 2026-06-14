# ACP extras implementation plan

This document tracks ACP features beyond the baseline text prompt/session flow. The guiding rule is to expose an ACP feature only after both sides support it and Vibes has a local safety/UX gate for it.

## Completed: Milestone A — capability negotiation and MCP injection

- Parse and persist `initialize` agent capabilities (`promptCapabilities`, `mcpCapabilities`, `sessionCapabilities`, `authMethods`, `agentInfo`).
- Reflect negotiated safe capabilities in provider descriptors.
- Configure ACP MCP servers with `VIBES_ACP_MCP_SERVERS_JSON`.
- Pass MCP servers to `session/new`, always allowing stdio and filtering HTTP/SSE unless the agent advertises support.
- Keep ACP client filesystem, terminal, and permission services disabled.

## Completed: Milestone B — prompt context blocks

Goal: enrich `session/prompt` without sending content block types the agent did not advertise.

### Delivered

- Added a provider-neutral prompt envelope while preserving legacy text-only `Provider.Prompt` compatibility.
- Added ACP rendering for `text` plus explicit `resource_link` prompt blocks.
- Added `POST /agent/{id}/message` request plumbing for optional explicit `context` resource links.
- Kept image/audio/embedded prompt blocks disabled until size/source policies and UI affordances exist.
- Added prompt rendering tests.

### Scope

1. Add an internal prompt envelope, for example:
   - required text body;
   - optional explicit resource links (`uri`, optional `name`, optional `mimeType`);
   - future media/embedded content fields kept private until gated.
2. Keep existing `Provider.Prompt(ctx, message, threadID)` behavior as text-only compatibility.
3. Let ACP providers render the envelope into ACP content blocks:
   - always allow `text`;
   - allow `resource_link` as baseline ACP prompt context;
   - allow `image`, `audio`, and `embedded_context` only when `promptCapabilities` advertise them and Vibes has a safe source/size policy.
4. Populate resource links only from explicit user/UI references, not by silently scanning the workspace.
5. Add tests for block rendering and capability filtering.

### Safety gates

- No implicit filesystem reads.
- No binary/media payloads until size/type limits and UI affordances exist.
- Unsupported prompt block types are dropped with debug logging, not sent.

## Milestone C — permission mediation and `fs/read_text_file`

Goal: support ACP-native permission requests and a read-only filesystem service behind user approval.

### Scope

1. Handle `session/request_permission` in the ACP receive loop.
2. Route permission prompts through the existing Vibes permission UX and timeout policy.
3. Advertise `clientCapabilities.fs.readTextFile` only when read service is enabled.
4. Implement `fs/read_text_file` with path normalization, workspace allowlisting, file size limits, and audit logging.
5. Add tests for path traversal, denied permissions, timeout, and successful approved reads.

### Safety gates

- Default disabled.
- Workspace-root allowlist only.
- No symlink escape.
- Explicit user approval unless an administrator enables a documented auto-approve policy.

## Milestone D — writes and terminal services

Goal: add mutating local services only behind stronger opt-in controls.

### Scope

1. Add `fs/write_text_file` only after read service hardening is complete.
2. Require explicit opt-in for write support and per-operation permission mediation.
3. Add terminal service support only when `/terminal/ws` is enabled and an ACP-specific terminal policy is configured.
4. Add tests for write confinement, overwrite behavior, terminal command denial, and session cleanup.

### Safety gates

- Default disabled.
- Workspace-root allowlist only.
- Per-operation approval by default.
- Terminal environment is minimal and audited.

## Milestone E — ACP-native UI controls

Goal: expose negotiated ACP controls in the frontend without leaking unsupported actions.

### Scope

1. Surface `session/new` result `modes` and `configOptions` in provider descriptors or a provider details endpoint.
2. Reflect usage/session updates from `session/update` events when present.
3. Add available command UI only after ACP command capabilities are detected.
4. Keep controls hidden/disabled unless the active provider advertises support.

### Safety gates

- UI controls are capability-driven.
- Unknown ACP update payloads are ignored safely and logged in debug mode.
- No frontend action assumes Copilot/Codex/Pi parity.
