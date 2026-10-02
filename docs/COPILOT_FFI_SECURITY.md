# Copilot FFI security review — local preview

Decision: suitable for continued synthetic, single-user loopback testing. Production use and upstream merge require independent review and the external acceptance checks below. This review was performed by the implementation author.

## Assets and boundaries

- Assets: workspace files, uploaded inputs, conversation/plan records, native journals and inherited process environment.
- Browser entry points: message submission, upload, request response, model controls, cancellation and SSE/status recovery.
- Native boundary: official Python SDK 1.0.14 loads runtime 1.0.85 in-process. The native library has the same OS authority and crash boundary as Vibes. Version checks and explicit provisioning do not sandbox it.
- Runtime tools: only the two custom Vibes tools by default; additional builtin/MCP selectors are operator-owned and non-wildcard. MCP command execution and remote endpoints need their own trust review.
- Account use: off by default, enabled only by an operator setting. Tests use isolated profiles and a loopback synthetic provider. No token is returned in browser backend status.
- Rollback: stop the local preview and select the existing ACP/Pi backend deliberately. Never substitute transports or conversations automatically after failure. Native state is not deleted by rollback.

## Findings and controls

| Risk | Control and verification |
|---|---|
| DNS rebinding or accidental network bind exposes unauthenticated agent APIs | FFI-only configuration rejects non-loopback binds; middleware checks Host and network peer. `test_copilot_loopback.py`. A forwarding proxy is not authorised or secured by this check. |
| Approval becomes stale while UI closure yields | Recheck captured owner/cancellation immediately before returning SDK permission/input results. `test_copilot_audit.py` cancels/replaces the turn during notification. |
| Startup/shutdown lock inversion or uncertain session setup | Shutdown does not hold lifecycle lock while draining turn lock; all model/send setup paths fail closed after ambiguous create/resume. Deterministic audit tests; native stop/resume/cancel smoke. |
| Lost send response creates a replacement conversation after restart | Bind identity immediately before admission; save on native idle; resume with pending-work continuation off. Timeout test verifies binding survives. Fresh-process native smoke verifies nonempty journal history. Empty-session runtime behavior is documented. |
| Another conversation selects an unreferenced upload | Upload-time session metadata plus conservative legacy rules; tests reject wrong-session IDs and reference laundering. This is agent-context scoping, not authenticated per-user file access. |
| Traversal/reparse/rename during output read | Windows ancestor/final handles deny rename/write sharing; reject ambiguous DOS/UNC/ADS/reparse paths. POSIX descriptor-relative opens use no-follow. Tests cover junction rejection, traversal, size and deterministic rename/write attempts. |
| Cancellation publishes a slow output file | Attachment context is marked cancelled before abort and rechecked around read/store/delivery. Deterministic test holds the read and confirms no media creation after cancellation. Previously committed effects are not undone. |
| Malformed or oversized document input | Bounded ZIP member count and expansion, UTF-8/XML checks, no DOCTYPE/entities/NUL XML, text/image/total-size limits. No macros or external XML resources are executed. PDF and unsupported formats rejected. |
| Raw provider configuration reaches browser | Model catalogue/state exposes bounded scalar display fields only; nested names, invalid IDs, duplicate entries and malformed effort arrays are excluded. Provider exception bodies are replaced with a local error before timeline publication. SDK private diagnostics can still contain content. |
| Failed tool displayed as successful | Track tool names by call ID; only `success=true` maps to completed; false maps to failed. Unknown outcome maps to ended. Regression test covers native-shaped completion without a tool name. |
| Queue or late callback replays an interrupted action | One active turn per chat, independent FFI lanes without a chat-count cap, owner-scoped responses/tools, single-use request futures, cancellation retains same-chat follow-ups, lane-local poison on uncertain completion. Approvals are not durable and cannot be replayed after restart. Native session.idle remains the quiescence boundary supplied by the SDK. |

## Concurrent-session verification

The FFI host now separates conversation locks, active owners, pending permissions and failure state. FFI dispatch tasks are lifecycle-managed independently of the fixed legacy worker pool. Same-chat admission is locked against queue promotion. Global output attachment identity is no longer used by FFI tools; they carry an explicit captured context and a live lane-owner check. SQLite writes share a transaction lock to prevent a cancelled writer rolling back another chat's write. General file writes remain shared-workspace operations and can conflict.

`test_copilot_concurrency.py` verifies six-chat overlap, same-chat ordering, cross-chat cancellation rejection, permission ownership, lane-local failure, independent controls and database rollback safety. `ffi_concurrency_smoke.py` verifies six simultaneous native conversations via HTTP with fake loopback inference, cancel/timeout isolation, correct plan/file destinations and stale-response rejection. Host shutdown drains lanes concurrently; native faults still share the process.

## Earlier local verification

- Full Windows pytest collection runs without `--ignore`: 638 passed, 14 skips for explicit POSIX facilities. Disabled terminal and unsupported legacy MCP workspace configuration are tested; general workspace HTTP routes contribute 45 passing tests.
- Whole-repository Ruff, frontend lint and all 38 frontend tests pass.
- Real native fixture: image/document inputs reach fake inference, free-form input, custom/MCP permissions, plan read, file delivery, skill discovery, denied read, cancellation, model-state read and fresh-process journal resume.
- Clean Edge fixture: pending question survives page reload, free-form answer submitted, replay rejected and timeout dismissed; zero page errors.
- No authenticated model, external MCP write, production service, credential change or publication was used for these checks.

## Required external checks

1. Linux and hosted Windows CI against the actual pinned dependencies. Local Windows success does not establish Linux behavior.
2. Independent source/native-file-boundary review. An attempted delegated review was unavailable because no model was approved; this document is not independent approval.
3. Separately authorised account-backed model catalogue/switch/reasoning and inference tests. Local mocks validate shape and failure handling only.
4. Physical-device sleep/reconnect and soak/load testing. Desktop Edge mobile viewport emulation is limited evidence.
5. A separate authenticated deployment design before any remote access. Do not publish a forwarding proxy to this unauthenticated preview.

## Residual risks

Native faults can terminate the host. Enabled builtins/MCP programs run with host privileges; the runtime decides when to request permission. Native journals may retain uploaded content and require private ACLs/retention. Skills and operator-supplied servers remain trusted executable inputs. FFI and generated SDK contracts are experimental and pinned; upgrades require rerunning these gates. No blanket operating-system sandbox, multi-user isolation, side-effect rollback or independent review is claimed.
