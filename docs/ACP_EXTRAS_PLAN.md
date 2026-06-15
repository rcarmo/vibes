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

## Completed: Milestone C — permission mediation and `fs/read_text_file`

Goal: support ACP-native permission requests and a read-only filesystem service behind explicit local safety gates.

### Delivered

1. Handle incoming ACP client-side requests in the provider receive loop and return JSON-RPC responses instead of dropping them.
2. Route `session/request_permission` through the existing Vibes permission dialog, whitelist, and timeout policy.
3. Return ACP `selected` outcomes for approved option IDs and ACP `cancelled` outcomes for broker timeouts/errors.
4. Advertise `clientCapabilities.fs.readTextFile` only when `VIBES_ACP_FS_READ_TEXT_ENABLED=true`.
5. Keep `clientCapabilities.fs.writeTextFile=false` and `clientCapabilities.terminal=false` unconditionally.
6. Implement `fs/read_text_file` with path normalization, workspace-root confinement, symlink escape prevention, directory rejection, file size limits, and ACP line/limit slicing.
7. Surface provider descriptor booleans for read/write filesystem and terminal services so UI controls can stay capability-driven.
8. Return explicit `method not found`/disabled errors for unimplemented ACP client methods rather than silently allowing them.

### Follow-up hardening

1. Add richer audit UI entries for approved/denied ACP client-service calls.
2. Add operation-specific permission policy before enabling write filesystem or terminal services.

### Safety gates

- Read service is disabled by default.
- Reads are confined to the active workspace root.
- Symlinks must not escape the allowlisted root.
- Files larger than `VIBES_ACP_FS_READ_TEXT_MAX_BYTES` are rejected.
- Write and terminal services are not advertised or implemented.

## Design complete: Milestone D — writes and terminal services

Goal: add mutating local services only behind stronger opt-in controls.

### Delivered design-only slice

1. Added [ACP_LOCAL_SERVICES_POLICY.md](ACP_LOCAL_SERVICES_POLICY.md) for `fs/write_text_file` and `terminal/*`.
2. Defined separate default-off opt-in configuration for ACP write and ACP terminal services.
3. Defined workspace/root confinement, symlink handling, overwrite policy, terminal root/environment/session constraints, per-operation permission mediation, audit event shape, UI gating, and test coverage requirements.
4. Kept `clientCapabilities.fs.writeTextFile=false` and `clientCapabilities.terminal=false`; no write or terminal implementation is enabled by this milestone.

### Implementation rollout

1. Add write config parsing without advertising write capability. ✅
2. Add non-mutating write path validation/audit shape scaffolding and tests. ✅
3. Add permission-broker/audit persistence plumbing without filesystem mutation.
4. Enable `fs/write_text_file` only behind config and per-operation approval.
5. Reassess and implement terminal separately with lifecycle limits, minimal env, audit, and explicit ACP-specific config.
6. Advertise `clientCapabilities.terminal=true` only after terminal policy enforcement is complete.

### Safety gates

- Default disabled.
- Workspace-root allowlist only.
- Per-operation approval by default.
- Terminal environment is minimal and audited.
- `/terminal/ws` enablement never implies ACP terminal enablement.

## In progress: Milestone E — ACP-native UI controls

Goal: expose negotiated ACP controls in the frontend without leaking unsupported actions.

### Delivered safe UI metadata slice

1. Provider descriptors expose explicit filesystem and terminal service booleans.
2. Frontend provider utilities understand `permission_requests`, `fs_read_text_file`, `fs_write_text_file`, and `terminal_services` capability flags.
3. Provider summaries can display read-only filesystem and permission support while write filesystem and terminal affordances remain hidden/disabled unless a provider explicitly advertises them.
4. ACP providers store bounded display-only `session/new` metadata (`modes`, sanitized `configOptions`) and expose it as `session_metadata` in provider descriptors.
5. Frontend summaries can show session `modes`/`config` availability without enabling session-mode or config mutation controls.

### Remaining scope

1. Reflect usage/session updates from `session/update` events when present.
2. Add available command UI only after ACP command capabilities are detected.
3. Keep controls hidden/disabled unless the active provider advertises support.

### Safety gates

- UI controls are capability-driven.
- Unknown ACP update payloads are ignored safely and logged in debug mode.
- No frontend action assumes Copilot/Codex/Pi parity.
- Write filesystem and terminal controls stay unavailable until Milestone D implements explicit policies.
