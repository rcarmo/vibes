# How Vibes uses the Copilot SDK in-process

Vibes calls the official Python Copilot SDK directly. `RuntimeConnection.for_inprocess()` loads the SDK-compatible native Rust runtime into the Python server process. Vibes supplies application sessions, approvals, tools and browser events; the SDK owns the native transport.

## Boundaries

```text
Browser
  HTTP messages / model controls / permission replies / cancellation
  SSE drafts / tool status / permission requests / timeline updates
    │
Vibes aiohttp routes + SQLite
    │
CopilotHost — one native host, lifecycle and lane registry
    ├─ ConversationLane A — lock, SDK session, active owner, pending decisions
    ├─ ConversationLane B — lock, SDK session, active owner, pending decisions
    └─ ConversationLane … — no fixed chat-count cap
    │
Official github-copilot-sdk (Python)
  CopilotClient(connection=RuntimeConnection.for_inprocess())
  generated RPC APIs + session event/tool/permission callbacks
    │ ctypes / native C ABI; framed JSON-RPC bytes
Native Copilot Rust runtime (same OS process)
    ├─ provider inference requests (when a prompt is submitted)
    └─ explicitly enabled builtins / custom tools / MCP servers
```

There is no custom Rust bridge, Node.js host or Copilot CLI/ACP subprocess in this agent transport. The SDK still uses JSON-RPC internally. FFI removes the external agent-process/stdio transport; it does not remove protocol serialisation or model network latency. Enabled shell/MCP tools may create their own subprocesses.

## Versions and provisioning

The optional `vibes[copilot]` extra pins `github-copilot-sdk==1.0.14` for Python 3.11+. Vibes checks native runtime `1.0.85` at startup. These pins describe tested compatibility, not a promise that arbitrary SDK/runtime versions interoperate.

Provision with the official SDK before starting Vibes:

```text
python -m pip install '.[copilot]'
python -m copilot download-runtime --in-process
```

Then set `COPILOT_SKIP_CLI_DOWNLOAD=1`. Vibes refuses startup without that opt-out, and never downloads a runtime implicitly. `COPILOT_CLI_PATH`, when supplied, identifies the provisioned runtime entrypoint from which the SDK resolves the adjacent native library; its name does not imply that Vibes executes a CLI. The SDK supports the natural library names (`copilot_runtime.dll`, `libcopilot_runtime.so`, `libcopilot_runtime.dylib`) and its packaged `runtime.node` layout. Native binaries are not vendored in this repository.

The Python SDK's `_ffi_runtime_host.py` uses `ctypes.WinDLL`/`ctypes.CDLL`, binds `copilot_runtime_host_start`, `connection_open`, `connection_write`, `connection_close` and `host_shutdown`, and pumps Content-Length-framed JSON-RPC bytes. Its process-like adapter reuses the SDK RPC framing layer. These are SDK implementation details: Vibes calls the public `RuntimeConnection`/`CopilotClient` interface rather than binding the C symbols itself. Loading a different native library in the same process is unsupported; restart for upgrades.

A minimal direct SDK lifecycle, omitting Vibes-specific routing:

```python
from copilot import CopilotClient, RuntimeConnection

client = CopilotClient(
    connection=RuntimeConnection.for_inprocess(),
    base_directory=".vibes/copilot",
    mode="empty",
    use_logged_in_user=False,
    enable_remote_sessions=False,
)
await client.start()
try:
    await client.ping("ready")
    # create_session/resume_session only with explicit tools and permission handler
finally:
    await client.stop()
```

## Implementation map

| Module | Responsibility |
|---|---|
| `copilot_client.py` | SDK preflight, native start/stop, lane send loop, event conversion, public generated model APIs, approvals and custom tools |
| `copilot_host.py` | Shared native host and independent `ConversationLane` registry; exact-chat cancellation and aggregate status |
| `routes/agents.py` | Per-chat admission/dispatch tasks, durable user/reply rows, scoped SSE, queued follow-ups and cancellation checks |
| `routes/sessions.py` | Existing session model/catalogue endpoints delegated to the selected backend |
| `sessions.py` | Existing SQLite backend bindings from Vibes chat ID to native session ID |
| `copilot_media.py` | Scoped input-media validation, verified images, bounded UTF-8/OOXML text and temporary selections |
| `agent_attachments.py`, `confined_files.py` | Captured-owner output delivery, idempotent receipts and no-follow bounded workspace reads |
| `db.py`, `plans.py` | Serialised SQLite write transactions and revision-checked plan changes |
| `static/js/components/agent-request-details.js` | Display conversion for native permission shapes; no approval policy |

## Host and chat lifecycle

Application startup starts one `CopilotHost`. Its runtime `CopilotClient` uses `mode="empty"`, explicit tool settings, disabled remote sessions and operator-selected authentication. Failure leaves `/health` HTTP liveness separate from backend readiness. No fallback transport is attempted.

A conversation lane owns a distinct SDK session, one turn lock, its current owner object, pending request futures, cached model selection and failure state. Different chats run independently without a global turn semaphore or the legacy three-worker queue. The dispatcher serialises admission and queue promotion within a chat. Model reads/changes lock only that chat. Legacy ACP/Pi locking is unchanged.

On stop, the host closes admission, denies outstanding requests, asks each lane to abort and drains lanes concurrently before stopping the shared client. A lane never closes the shared runtime by itself. Ordinary uncertain turn endings quarantine that lane until server restart; native startup/cleanup failures and native crashes can affect the whole process.

All chats share the server working directory and OS privileges. Lane isolation prevents conversation/permission routing mistakes; it is not a filesystem sandbox. Simultaneous edits to a shared file can conflict. SQLite writes use a short connection-level lock to prevent interleaved commit/rollback; this does not serialise inference.

## Prompt admission and persistence

1. The HTTP route validates the chat and upload ownership, persists the user message and captures an explicit turn context.
2. The lane loads its cached SDK session, resumes a stored native ID, or creates a fresh ID. Resume always uses `continue_pending_work=False`.
3. Immediately before prompt admission, Vibes binds the native ID in SQLite. A lost send response therefore cannot silently create a replacement conversation after restart.
4. The SDK sends the prompt and explicit attachments. Native events are consumed in order through a bounded queue.
5. On `session.idle`, Vibes calls the SDK's `sessions.save` RPC. The route persists the final response and releases the turn.

Runtime 1.0.85 does not reliably resume an empty session with no prompt journal. Controls-only sessions therefore remain unbound until admission. An ambiguous failed admission may leave an unresumable binding; the adapter fails closed instead of replacing it. Nonempty journal resume is tested both after host restart and in a separate Python process. Vibes does not edit native journal files.

## Streaming to the browser

SDK callbacks enqueue events onto the asyncio loop with `call_soon_threadsafe`. Each turn owns its bounded queue and event subscription. Late events are ignored when the owner is no longer current; overflow stops the turn without claiming completion.

`assistant.message_delta` updates a cumulative draft. The adapter publishes a bounded **replacement preview snapshot** plus the individual delta. Collapsed browser previews consume snapshots, which tolerate lossy SSE preview delivery. Expanded panels consume the separate delta stream after loading the full turn preview. Tool completions are matched to their start IDs and display success/failure accurately. Final messages are stored independently from previews.

Browser disconnect does not restart or dispose the native host. Status polling recovers active-turn and pending-request metadata. Permission close events name the exact request, so resolving an old request cannot dismiss a newer prompt.

## Permission and tool calls

The SDK session receives `on_permission_request` and `on_user_input_request` callbacks. Vibes checks the native session identity against the captured active owner before publishing a browser request. A random single-use request ID maps to that owner's future. Responses must match the allowed options; free-form answers are bounded.

Allow maps to SDK `PermissionDecisionApproveOnce(approved_interactively=True)`; deny/timeout/cancellation map to rejection. Vibes does not use global title whitelists or automatic blanket approval for FFI. Ownership is checked again after asynchronous UI-close notification. Runtime permission requests are an approval boundary, not proof that every builtin operation prompts.

Custom SDK tools are registered as `vibes_attach_file` and `vibes_plan`. Their handlers receive a native invocation/session ID and recheck their lane owner before each side effect. Output paths are confined to the workspace, never chosen by browser session override. Plan mutations require an expected revision from a read. Native builtins/MCP tools are operator-selected with exact source-qualified selectors; browser requests cannot expand this list.

## Inputs, models and authentication

Images use validated SDK blob attachments. Text and supported OOXML files become bounded text selections with explicit ranges; passing a bare native file reference alone did not reliably include text in the synthetic provider request. Temporary material is removed after the turn. The native journal may retain input content.

Model/catalogue changes use `session.rpc.model.list`, `switch_to`, `set_reasoning_effort` and `get_current`. Reasoning must be advertised by the chosen model, changes are disallowed during that chat's active turn, and read-back must confirm the result before success is returned. Account policy controls availability; the adapter does not manufacture catalogue entries.

Authentication uses the SDK's supported mechanisms. Vibes does not read Scout/WorkIQ caches, implement login, persist tokens in its settings, or include tokens in health/model payloads. Operator-managed environment credentials or an explicitly enabled signed-in account are distinct from native runtime readiness. The development LAN proxy and machine-specific credential-launch wrapper are outside the upstream package.

## Safety, observability and limits

- Loopback is enforced by the preview config/middleware. There is no built-in user login. Remote deployment requires a separate reviewed access-control design.
- FFI shares process environment, memory, privileges and native crash boundary. It provides no process isolation from the library.
- Event/input/output limits and permission timeouts remain enforced. No chat-count cap means provider/OS/memory limits can still be reached.
- Health reports native readiness, active-chat count and failed-chat count, without provider exception bodies. Host resource meters are OS metrics, not inference usage.
- Context/cost telemetry, durable approval replay, automatic interrupted-work retry, slash commands and PDF input are not supplied by this adapter.
- API generation and FFI are experimental. Upgrade SDK/runtime together, rerun synthetic/native regressions and review generated type changes.

## Verification

Offline tests mock the SDK and exercise lifecycle, queue/ownership races, input validation and concurrent HTTP admission. Opt-in native scripts use an explicit provisioned runtime, scrub inherited credentials, create disposable profiles and route inference to a loopback fake provider.

- `ffi_smoke.py`: native startup/ping/shutdown and optional unbound empty-session creation.
- `ffi_persistence_smoke.py --vibes`: native tools, input, permission, cancellation and history; `ffi_resume_child.py` proves fresh-process resume.
- `ffi-stream-web-smoke.mjs`: real native events through HTTP/SSE into Edge, with controlled multi-chunk output, polling and expansion.
- `ffi_concurrency_smoke.py`: six simultaneous native HTTP conversations, scoped cancel/permission timeout, plan reads and separate file outputs. Six is a test workload, not a configured cap.

See [configuration and operation](COPILOT_FFI.md) and [security review](COPILOT_FFI_SECURITY.md). Hosted Linux/Windows CI and independent review remain merge gates; local Windows evidence alone does not close them.
