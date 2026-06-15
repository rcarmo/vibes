# ACP local services safety policy

This document defines the safety model for ACP local client services. Vibes now supports `fs/write_text_file` only behind explicit configuration, root confinement, per-operation permission mediation, atomic writes, and durable audit persistence. ACP `terminal/*` remains disabled and must continue to advertise `clientCapabilities.terminal=false`.

## Current state

- `fs/read_text_file` is the only ACP filesystem service with implementation scaffolding.
- `fs/read_text_file` is default-off and only advertised when `VIBES_ACP_FS_READ_TEXT_ENABLED=true`.
- `fs/write_text_file` is implemented only when `VIBES_ACP_FS_WRITE_TEXT_ENABLED=true`; otherwise it returns a JSON-RPC method-not-implemented error and is not advertised.
- Write execution uses configuration, confinement planning, permission request shaping, broker-mediated decision handling, durable audit persistence, structured SSE audit emission, and atomic same-directory temp-file rename.
- ACP terminal methods are not implemented and must return JSON-RPC method-not-implemented errors.
- `/terminal/ws` is a separate browser PTY endpoint, gated by `VIBES_ENABLE_TERMINAL`; that flag does not enable ACP terminal services.
- Provider descriptors expose `fs_write_text_file=true` only when write support is explicitly enabled; `terminal_services=false` remains unconditional.

## Non-goals for the current implementation

- Do not advertise ACP write capability unless `VIBES_ACP_FS_WRITE_TEXT_ENABLED=true` and the write policy implementation is active; do not advertise ACP terminal capability.
- Do not reuse `/terminal/ws` directly as an ACP terminal implementation.
- Do not auto-approve ACP write or terminal operations based only on broad whitelist patterns.
- Do not let ACP agents bypass Vibes workspace/root confinement, permission mediation, API-token protection, or audit logs.

## Required opt-in configuration

Write and terminal services require separate, explicit configuration. A future implementation should use names equivalent to:

| Variable | Default | Required meaning |
|---|---:|---|
| `VIBES_ACP_FS_WRITE_TEXT_ENABLED` | `false` | Advertise and handle `fs/write_text_file` only with all write policy checks active. |
| `VIBES_ACP_FS_WRITE_ROOT` | `VIBES_WORKSPACE` | Root directory for ACP writes; must resolve to an existing directory. |
| `VIBES_ACP_FS_WRITE_TEXT_MAX_BYTES` | policy-defined | Maximum accepted write payload size. |
| `VIBES_ACP_FS_WRITE_ALLOW_OVERWRITE` | `false` | Whether approved writes may replace existing regular files. |
| `VIBES_ACP_TERMINAL_ENABLED` | `false` | Advertise and handle ACP `terminal/*`; independent from `VIBES_ENABLE_TERMINAL`. |
| `VIBES_ACP_TERMINAL_ROOT` | `VIBES_WORKSPACE` | Working directory root for ACP terminal sessions. |
| `VIBES_ACP_TERMINAL_SHELL` | allowlisted shell | Shell/command used to start ACP terminals; must not inherit arbitrary agent-provided commands. |
| `VIBES_ACP_TERMINAL_MAX_SESSIONS` | small bounded value | Maximum concurrent ACP terminal sessions per provider/session. |
| `VIBES_ACP_TERMINAL_IDLE_TIMEOUT` | policy-defined | Idle timeout before terminal cleanup. |

A future implementation may choose different exact names, but it must preserve these properties:

1. write and terminal are independently configurable;
2. both default to disabled;
3. enabling `/terminal/ws` does not imply ACP terminal enablement;
4. invalid roots or unsafe policy values fail closed and do not advertise capabilities.

## Workspace/root confinement

### Shared rules

- Resolve the configured root with `filepath.EvalSymlinks` before use.
- Resolve every requested path or working directory through `filepath.Abs`, `filepath.Clean`, and symlink evaluation where applicable.
- Reject paths whose resolved form is outside the configured root.
- Reject paths with empty names, NUL bytes, platform-invalid names, or paths that become roots after cleaning.
- Treat symlink escape attempts as denials, not as prompts for user approval.
- Emit an audit event for every allow/deny/error decision.

### `fs/write_text_file`

The write implementation must:

1. require an absolute ACP path or normalize a relative path against the configured write root;
2. reject directory targets;
3. reject writes above `VIBES_ACP_FS_WRITE_MAX_BYTES` before touching the filesystem;
4. create parent directories only if an explicit policy allows it;
5. use atomic write semantics for new/replacement files (`tempfile` in same directory, fsync where practical, rename);
6. support overwrite only when `VIBES_ACP_FS_WRITE_ALLOW_OVERWRITE=true` and the user approves the concrete operation;
7. avoid following final-path symlinks for write targets unless a future policy explicitly permits safe in-root symlink writes;
8. preserve file permissions according to a documented rule (for example `0600` for new files, preserve mode for approved overwrites).

### `terminal/*`

A future ACP terminal implementation must:

1. create terminals only inside `VIBES_ACP_TERMINAL_ROOT`;
2. start from a server-side allowlisted shell/command, not arbitrary agent-provided command text;
3. use a minimal environment (for example `TERM`, `HOME` if safe, `PATH` from policy, no secrets by default);
4. enforce per-session and global terminal limits;
5. close PTYs on provider shutdown, session cancellation, idle timeout, or explicit `terminal/kill`;
6. avoid streaming terminal output to persistent logs by default, but audit lifecycle and command-intent metadata;
7. treat binary/control output carefully in UI and logs to avoid terminal escape injection.

## Per-operation permission mediation

Write and terminal operations are mutating/high-risk and require per-operation mediation through the Vibes permission broker. Vibes turns a validated write plan into a per-operation permission request with target path, byte count, overwrite flag, escaped content preview, and content hash. The write mediation path is wired to the existing Vibes permission broker for approve/deny/timeout decisions and bypasses broad whitelist auto-approval for high-risk local-service prompts. Denial, timeout, validation error, revalidation error, and write error outcomes do not mutate files.

### Required prompts

| Operation | Prompt contents |
|---|---|
| `fs/write_text_file` new file | provider, session ID, normalized path, byte count, whether parent directories are created, preview/hash of content. |
| `fs/write_text_file` overwrite | all new-file fields plus existing file size/mtime and a clear overwrite warning. |
| `terminal/create` | provider, session ID, root, shell, environment summary, timeout/limits. |
| `terminal/output` input from agent | terminal ID, byte count, printable preview with control characters escaped. |
| `terminal/kill` | terminal ID, process/session summary. |

### Required behavior

- Timeout returns an ACP cancellation/denial outcome and must not perform the operation.
- Denial must be returned to the ACP agent as a structured error/outcome and audited.
- Approval applies only to the exact normalized operation that was shown to the user.
- If the request changes between prompt and execution, re-check policy and deny on mismatch.
- Broad whitelist/auto-approve mechanisms must not approve terminal or write operations unless a future policy adds explicit high-risk scopes; the current future write mediation path uses the broker's manual/no-whitelist request mode.

## Audit events

Every ACP local-service request should emit a structured audit event. Vibes now has a local-service audit recorder interface and helpers that map future write approval, denial, timeout, and error outcomes into the structured event shape below. The app-level route adapter persists sanitized rows to `local_service_audit` and then emits `agent_audit` SSE events for future local-service mediation.

At minimum:

```json
{
  "type": "acp_local_service",
  "provider_id": "copilot",
  "session_id": "...",
  "method": "fs/write_text_file",
  "request_id": "...",
  "target": "/workspace/path.txt",
  "decision": "approved|denied|timeout|error",
  "reason": "user_denied|path_escape|too_large|not_enabled|...",
  "bytes": 1234,
  "timestamp": "RFC3339"
}
```

Audit data must not include full file contents, terminal output, secrets, or raw environment variables. Durable rows store structured fields (`provider_id`, `session_id`, `method`, `request_id`, `target`, `decision`, `reason`, `bytes`, small safe metadata) and intentionally omit content previews.

## UI gating

- Provider descriptors remain the source of truth for UI affordances.
- The UI must hide write controls unless `capabilities.fs_write_text_file=true`.
- The UI must hide terminal controls unless `capabilities.terminal_services=true`.
- Display-only metadata such as `session_metadata.modes` or `config_options` must not imply action support.
- Permission prompts must distinguish read, write, overwrite, terminal create, terminal input, and terminal kill.
- The UI must render terminal previews with control characters escaped.

## Test plan before enablement

### Capability and default-off tests

- Default client capabilities advertise `fs.writeTextFile=false` and `terminal=false`.
- Setting read flags cannot enable write or terminal capabilities.
- Write capability is advertised only when `VIBES_ACP_FS_WRITE_TEXT_ENABLED=true`.
- Invalid write/terminal config fails closed.
- Provider descriptors keep `terminal_services=false`; `fs_write_text_file` follows explicit write configuration.

### Write tests

- path traversal and symlink escapes are denied;
- directory targets are denied;
- oversized payloads are denied before filesystem mutation;
- new-file write succeeds only after approval;
- overwrite is denied by default;
- overwrite succeeds only with explicit overwrite config and approval;
- denied/timeout permission requests do not create or modify files;
- audit events are emitted for approve/deny/timeout/error.

### Terminal tests

- terminal capability remains false unless ACP terminal config is explicitly enabled;
- `/terminal/ws` enablement alone does not enable ACP terminal capability;
- terminal roots are confined to workspace/root policy;
- agent-provided arbitrary shell commands are ignored/rejected;
- environment is minimal and excludes known secret variables;
- session limits and idle cleanup kill PTYs;
- terminal input requires approval and escapes previews;
- output/control sequences are not persisted unsafely;
- audit events are emitted for create/input/kill/cleanup.

## Rollout order

1. Keep current design-only policy and default-false tests in place.
2. Implement write config parsing without advertising write capability. ✅
3. Implement non-mutating write path validation and audit event shape scaffolding. ✅
4. Add write permission request shaping and no-op-by-default audit recorder plumbing without filesystem mutation. ✅
5. Wire future write mediation through the Vibes permission broker and SSE audit event flow without filesystem mutation. ✅
6. Add database audit persistence integration without filesystem mutation. ✅
7. Enable `fs/write_text_file` behind config and per-operation approval. ✅
8. Reassess terminal separately; do not couple terminal enablement to write support.
9. Implement terminal lifecycle/limits/audit behind config.
10. Only then advertise `clientCapabilities.terminal=true`.
