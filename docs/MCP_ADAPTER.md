# Bundled Vibes MCP adapter plan

Vibes should ship a first-party MCP adapter, comparable in spirit to Piclaw's bundled tools, so ACP agents can discover Vibes-native workspace, provider, session, UI and audit capabilities through a standard MCP surface.

This document plus `internal/mcpadapter/` is the durable plan. Future passes should update code and this file together rather than relying on external planning notes.

## Goals

- Provide a `vibes mcp --stdio` entrypoint from the same static binary.
- Auto-inject the bundled stdio MCP server into ACP `session/new` only when explicitly configured.
- Use dynamic tool discovery based on Vibes runtime capabilities and safety gates.
- Prefer context-efficient tools: metadata first, bounded slices, stable mtimes/hashes, compact summaries.
- Expose Vibes workbench capabilities without inventing non-standard ACP JSON-RPC methods.

## Non-goals for the first implementation

- No arbitrary shell/terminal control.
- No arbitrary frontend JavaScript execution.
- No cross-session messaging until a real Vibes work-session registry exists.
- No broad file dumps by default.
- No mutating UI/editor actions until an SSE `ui_command` bridge and safety rules exist.
- Do not duplicate ACP `fs/write_text_file` unless MCP-only providers require a high-level write tool later.

## Current scaffold

Implemented now:

- `internal/mcpadapter.Registry` with a durable list of planned tools.
- Dynamic discovery via `mcpadapter.Environment`.
- Context budgets on tool descriptors.
- Stub handlers returning `ErrToolNotImplemented`.
- `mcpadapter.Server` with capabilities metadata.
- `vibes mcp --list-tools` CLI for inspecting the mapped surface.
- `vibes mcp --stdio` CLI stub that clearly reports MCP protocol serving is not implemented yet.
- Config placeholders:
  - `VIBES_MCP_ENABLED=false`
  - `VIBES_MCP_AUTO_INJECT_ACP=false`
  - `VIBES_MCP_COMMAND=`
- Disabled-by-default ACP auto-injection placeholder for the bundled stdio MCP server.

Not implemented yet:

- JSON-RPC/MCP protocol loop.
- Actual tool handlers.
- Frontend `ui_command` bridge.
- MCP resource templates.
- HTTP/SSE MCP serving.

## Dynamic discovery model

Tool discovery must be derived from runtime state:

```text
Vibes build capabilities
+ configuration flags
+ provider descriptors/session metadata
+ workspace availability
+ database/audit availability
+ frontend UI bridge availability
+ future work-session registry
= MCP tools/list response
```

Read-only metadata tools can be available by default. UI, write, terminal and cross-session tools must remain hidden until their safety gates exist.

## Context optimization rules

All MCP handlers must be designed to avoid wasting model context.

1. **Metadata first**: return paths, sizes, mtimes, hashes and suggested follow-up tools before content.
2. **Bounded content**: content tools require explicit range/limit arguments.
3. **Compact lists**: provider lists, audit lists and timeline search return summaries by default.
4. **Stable identifiers**: include ids, mtimes, hashes or rowids so agents can avoid rereading unchanged data.
5. **No secret payloads**: never return full local-service content, terminal output, raw environment, tokens or secrets.
6. **Tool suggestions**: where useful, include `suggested_next_tool` or equivalent metadata instead of embedding large data.

## Tool surface

The canonical tool list lives in `internal/mcpadapter/defaultTools()`.

### Phase 1: read-only introspection/context tools

These should be implemented first.

| Tool | Purpose | Source |
|---|---|---|
| `vibes.adapter_capabilities` | Describe adapter version, dynamic discovery and unavailable tool reasons. | `mcpadapter.Server.Capabilities` |
| `vibes.list_providers` | Compact provider list, active backend, status, model, capabilities. | `agent.Registry.Descriptors` |
| `vibes.get_provider` | One provider descriptor and session metadata. | `agent.Registry.Descriptor` |
| `vibes.get_session_metadata` | ACP modes/config/commands/current mode. | `ProviderDescriptor.SessionMetadata` |
| `vibes.get_context_usage` | Current context percent/status. | `ProviderStatus.ContextPct` |
| `vibes.get_recent_local_service_audit` | Sanitized audit rows. | `db.GetLocalServiceAudits` |
| `vibes.get_workspace_tree` | Bounded workspace tree. | workspace route/path helpers |
| `vibes.get_workspace_file_info` | File stat/hash/mtime/type info. | workspace root-confined stat helper |
| `vibes.read_workspace_file_slice` | Explicit bounded text slice. | ACP read confinement logic/workspace file helpers |
| `vibes.search_timeline` | Compact timeline search snippets. | `db.SearchInteractions` |

### Phase 2: UI command bridge

Requires an SSE `ui_command` event and frontend handler.

| Tool | Purpose | Safety gate |
|---|---|---|
| `vibes.open_workspace_file` | Open a workspace file in editor tab/popout. | workspace path validation + UI bridge |
| `vibes.show_workspace` | Focus/show workspace explorer. | UI bridge |

Rules:

- only workspace-confined paths;
- no arbitrary URL opens;
- no arbitrary JS;
- no dirty-tab close;
- audit/log UI commands.

### Phase 3: mutating/workflow tools

Only after clear semantics and permission/audit paths exist.

| Tool | Purpose | Notes |
|---|---|---|
| `vibes.request_write_file` | High-level MCP write request. | Prefer ACP `fs/write_text_file` unless MCP-only agents need it. |

### Phase 4: terminal tools

Only after ACP terminal policy/config/lifecycle scaffolding is complete.

| Tool | Purpose |
|---|---|
| `vibes.terminal_create` | Future guarded terminal creation. |

### Phase 5: cross-session coordination

Only after Vibes has an explicit work-session registry.

| Tool | Purpose |
|---|---|
| `vibes.list_work_sessions` | List named work sessions. |
| `vibes.send_work_session_message` | Queue/steer/message a target work session. |

## MCP protocol implementation checklist

1. Choose/implement a minimal Go MCP stdio protocol layer.
2. Support `initialize` with adapter metadata.
3. Support `tools/list` using `Registry.Discover(env)`.
4. Support `tools/call` dispatching through `Registry.HandlerFor`.
5. Add argument schemas to `ToolDescriptor` or a sibling descriptor type.
6. Implement Phase 1 handlers with app dependency injection:
   - DB;
   - provider registry;
   - workspace root;
   - config;
   - optional SSE broker later.
7. Add integration tests using stdin/stdout JSON-RPC frames.
8. Enable `VIBES_MCP_AUTO_INJECT_ACP=true` only after stdio serving is functional.

## ACP auto-injection

When `VIBES_MCP_ENABLED=true` and `VIBES_MCP_AUTO_INJECT_ACP=true`, Vibes appends a stdio MCP server to ACP `session/new`:

```json
{
  "name": "vibes",
  "command": "/path/to/vibes",
  "args": ["mcp", "--stdio"]
}
```

This remains disabled by default and should stay disabled until the stdio MCP protocol loop is implemented and tested.

## Relationship to ACP local services

- ACP `fs/read_text_file` and `fs/write_text_file` remain the low-level filesystem services.
- The Vibes MCP adapter is for higher-level workbench/context/session/UI tools.
- Do not use MCP as a shortcut around ACP local-service safety gates.

## Relationship to sandboxing

The adapter should integrate with `docs/SANDBOX.md` as terminal/process tooling matures. MCP tools that launch processes, terminals or writes must reflect sandbox capabilities in dynamic discovery and must fail closed when sandbox policies cannot be enforced.
