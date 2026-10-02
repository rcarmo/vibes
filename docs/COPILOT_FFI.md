# Copilot FFI backend (local preview)

The optional `copilot-ffi` backend embeds the native Copilot runtime through the official Python SDK. Existing ACP and Pi backends remain selectable. Selecting FFI never launches a Copilot CLI/ACP process or falls back to another agent transport. Explicit MCP/tool subprocesses are separate.

For the direct SDK/native call path, lifecycle and source map, see [How Vibes uses the Copilot SDK in-process](COPILOT_FFI_ARCHITECTURE.md). The [security review](COPILOT_FFI_SECURITY.md) records trust boundaries and remaining acceptance gates.

## Install and provision

Requires Python 3.11+; tested on Windows with Python 3.12, SDK 1.0.14 and native runtime 1.0.85. The base package still permits older interpreters for existing backends.

```text
python -m pip install '.[copilot]'
python -m copilot download-runtime --in-process
```

Provision once using the official SDK downloader, which checks the release checksum. Set `COPILOT_SKIP_CLI_DOWNLOAD=1` before starting Vibes. Do not point it at an incompatible CLI installation or vendor runtime binaries in this repository.

Example PowerShell configuration from a dedicated workspace:

```powershell
$env:VIBES_DEFAULT_AGENT = 'copilot-ffi'
$env:COPILOT_SKIP_CLI_DOWNLOAD = '1'
$env:VIBES_COPILOT_STATE_DIR = '.vibes/copilot'
$env:VIBES_COPILOT_MODEL = '<available-model-id>'
# Enable a previously approved/signed-in account only deliberately:
$env:VIBES_COPILOT_USE_LOGGED_IN_USER = 'true'
vibes
```

Vibes does not implement sign-in. `/health` reports native readiness separately from HTTP liveness; readiness does not prove authentication or model availability. Tests scrub inherited credentials and use an isolated local fake model. Remote-session export is disabled.

The FFI preview rejects non-loopback configured binds, network peers and non-loopback Host headers (including DNS rebinding). Use a literal loopback address or `localhost`. Vibes has no user login and its browser/file APIs are not a multi-user security boundary. Proxies can still forward trusted loopback requests, so do not expose a forwarding proxy; remote access requires separately reviewed authentication and deployment changes. FFI is experimental and shares Vibes' environment, native-crash and OS-privilege boundaries. Configure working directory and environment before startup, never per request.

## Sessions and cancellation

Different FFI chats run concurrently with **no application-level chat-count cap**. One turn runs at a time within each chat; same-chat follow-ups remain ordered. Each chat owns its turn lock, pending decisions, cancellation and failure state. One shared native host supplies separate SDK sessions, without the legacy three-worker queue limiting active chats. ACP/Pi keep their existing single-runtime behaviour.

Chats share the working directory and OS privileges: concurrent edits to the same file can conflict. Provider rate limits, native/runtime capacity, memory and OS limits still apply. SQLite writes are briefly serialised for transaction safety; model execution is not. Vibes stores the SDK conversation ID immediately before prompt admission and explicitly saves the native journal on idle. Cold resume uses `continue_pending_work=False`; interrupted work is never automatically replayed. Failed resume does not silently create a replacement conversation.

The pinned runtime does not persist an empty session created only for controls. Such sessions remain unbound until the first prompt. A completed synthetic conversation has been stopped and resumed through the real adapter with history preserved. A failed or ambiguous admission may leave a binding which cannot resume; recover deliberately rather than silently discard it.

Browser disconnect/reload leaves the native host running. Pending requests can be recovered from session-scoped status. Cancel checks the exact active owner, rejects pending approvals and waits for native idle; it does not consume queued follow-ups. Unconfirmed completion, timeout or overflow makes the affected chat unavailable until a deliberate server restart; other chats continue. Native startup/shutdown failure or a native crash is still host-wide. Shutdown closes admission, denies each chat's outstanding requests and drains all lanes concurrently before stopping the host. Ambiguous session creation/resume from model-control APIs also fails closed for that chat.

## Permissions, questions and controls

Permissions offer **Allow once** and **Deny**. Vibes ignores blanket auto-approval and title whitelists for FFI. This is a host permission handler, not an OS sandbox: the runtime decides which operations request permission.

Multiple-choice and explicit free-form questions are supported, with answers limited to 8,000 characters. Responses are single-use and scoped to the requesting owner. Timeouts deny requests and dismiss their browser prompt. Closing one prompt cannot dismiss a newer one. Permission/answer callbacks recheck ownership after asynchronous close notifications; cancellation during notification cannot deliver an approval. Pending approvals are not persisted across server restarts.

The existing per-session model picker uses native model APIs. Model/reasoning changes are blocked during a turn in that same chat, reasoning must be advertised for the selected model, and changes require authoritative read-back. Bound sessions are saved after confirmed changes. Model reads and account-backed catalogue/model switching were manually checked in the authorised preview. Automated catalogue/switch/reasoning contracts use mocked SDK responses and no inherited credentials; account policy and supported reasoning levels still require operator validation.

## Input and output files

Composer uploads are bound to the selected conversation when uploaded. FFI only accepts their explicit media IDs. Legacy unscoped files must already be referenced exclusively in that conversation; unreferenced legacy IDs fail closed.

Limits: eight files, 10 MiB per file, 20 MiB total, 40 million pixels per image, and 200,000 extracted characters per document.

- PNG, JPEG, GIF and WebP images are verified and passed as SDK blobs.
- UTF-8 TXT, Markdown, CSV, JSON and VTT are passed as explicit text selections.
- DOCX, PPTX and XLSX contribute bounded text/value XML content. Extraction does not preserve layout, evaluate formulae or macros, resolve spreadsheet shared-string indices into a formatted table, or perform OCR. Treat it as a text-only view, not a faithful Office renderer.
- PDF, legacy Office formats, encrypted documents, macro-enabled extensions, malformed ZIP/XML and oversized inputs are rejected. Convert unsupported input to reviewed text first.

The native file-reference input alone did not supply document contents to the synthetic model. Vibes therefore supplies extracted text and an explicit selection range. Temporary files have generated names and are removed after the turn. Native journals can retain supplied input content; apply retention and access controls to the state directory.

`vibes_attach_file` publishes output to the active conversation; it cannot choose another destination. Windows reads retain ancestor and final-file handles, reject links/reparse points, UNC/device paths, ADS and ambiguous names, and deny concurrent rename/write sharing. Cancellation is rechecked before delivery. `vibes_plan` writes require a revision from a prior read.

## Practical native coding tools

Defaults intentionally offer only `vibes_plan` and `vibes_attach_file`; they do not grant a shell or general filesystem tools. For an operator-approved Windows coding workspace, explicitly add:

```json
{
  "copilot_available_tools": [
    "builtin:ask_user", "builtin:view", "builtin:glob",
    "builtin:grep", "builtin:rg", "builtin:create", "builtin:edit", "builtin:apply_patch",
    "builtin:powershell", "builtin:read_powershell", "builtin:stop_powershell", "builtin:list_powershell",
    "builtin:web_fetch"
  ]
}
```

The effective tool names depend on the model/runtime. Some models use `rg` and `apply_patch` instead of `grep`, `create` and `edit`; unsupported selectors do not create tools. On POSIX inspect the SDK's tool descriptors for that platform's shell names. Native shell/file tools run with the server account's authority and can reach outside the workspace; permission prompts are not confinement.

`web_fetch` reads a known URL. No dedicated web-search provider is configured by Vibes. Shell networking and enabled MCP servers are separate capabilities, not a search feature. Restart the server while chats are idle after changing operator settings, so cached native sessions are resumed with the new allowlist.

## Explicit MCP and skills

Operator-owned `.vibes/settings.json` accepts `copilot_skill_directories`, `copilot_available_tools` and `copilot_mcp_servers`. Browser requests cannot set these. Defaults expose only `vibes_attach_file` and `vibes_plan`. No production MCP or skill configuration is imported.

```json
{
  "copilot_skill_directories": ["./skills"],
  "copilot_available_tools": ["builtin:ask_user", "builtin:skill", "mcp:example-lookup"],
  "copilot_mcp_servers": {
    "example": {
      "type": "local",
      "command": "python",
      "args": ["example_mcp.py"],
      "tools": ["lookup"]
    }
  }
}
```

Both the server tool list and the source-qualified `mcp:server-tool` selector must allow a tool. Wildcards are rejected. Enabling a skill does not grant its tools; add the required selectors deliberately. The native fixture verified custom skill discovery and an explicit local MCP call. Remote MCP/OAuth and account-backed integrations have not been tested. Review local skills, MCP command paths, environment and tool effects before enabling them.

## Windows limits and release gates

The POSIX terminal stays disabled on Windows. Legacy MCP workspace-read configuration fails explicitly on Windows; `/shell` still requires `/bin/bash`. These facilities have not been ported. Their POSIX tests have explicit Windows skips, while terminal-disabled and workspace-rejection behavior are tested. General workspace HTTP routes work on Windows and are included in the full suite. Slash commands, context/cost telemetry and durable approval replay are not provided by this backend.

Local tests cover native streaming, image/text input, free-form input, permissions, plan read, file output, MCP, skill discovery, cold resume, model-state read and cancellation. Browser tests use clean headless Edge desktop/mobile viewports and synthetic pending requests. They do not measure authenticated inference, physical-device sleep/reconnect or end-to-end model performance.

Before upstream merge or daily use: run Linux/hosted CI, independently review the native/file boundary, and authorise account-backed and physical-device testing separately. Nothing in the local preview installs a service or changes another agent host.

## Tests

```text
python -m ruff check src tests
python -m pytest tests -q -rs
```

Install the optional SDK for these offline contracts, with `COPILOT_SKIP_CLI_DOWNLOAD=1`. They do not start the runtime. Other tests purge `vibes.*` during collection; run a failing module alone to distinguish package-reload contamination.

Opt-in native tests require explicit `COPILOT_CLI_PATH` pointing to the provisioned runtime:

- `python tests/ffi_smoke.py`: startup/ping/shutdown. Also requires an empty owned `VIBES_FFI_SMOKE_ROOT`.
- `python tests/ffi_smoke.py --session --resume`: retained diagnostic reproducer for unpersisted empty sessions; expected to fail with this runtime.
- `python tests/ffi_concurrency_smoke.py`: six overlapping real native sessions through HTTP and loopback fake inference, with scoped cancellation, permission timeout, plan reads, attachment ownership and stale-response rejection. No external model calls.
- `python tests/ffi_persistence_smoke.py --vibes`: real FFI and Vibes adapter with local fake inference/MCP, isolated state and no inherited credentials. Includes journal resume in a separate OS process via `ffi_resume_child.py`.
- `bun tests/ffi-stream-web-smoke.mjs`: native multi-chunk fake inference through actual HTTP routes and SSE into Edge, with cumulative previews, polling, expansion and a final stored reply. Requires `VIBES_TEST_PYTHON` and `COPILOT_CLI_PATH`.
- `bun tests/ffi-web-smoke.mjs`: isolated native host plus Edge browser. Requires `VIBES_TEST_PYTHON` and `VIBES_TEST_OUTPUT`. Exercises reload recovery, free-form submission, stale-response rejection and timeout dismissal without model calls.
