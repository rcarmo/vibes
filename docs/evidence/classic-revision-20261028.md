# Bounded Classic editor and Plan browser probe

Revision-aware shared editor and Plan persistence passed a test-only loopback
probe on 28 October 2026. Runtime `ad7b6f3` includes the published `86392e6`
file/Plan routes; the tested shared candidate was fixtures-vibes
`0259e9a4816d3d643159538095fdffc884104598`. The actual consumer pin remains
`4259e825964d2b60dd6c6f7242e2b1daf4280a7d`; no fixture repin or deployment occurred.

## Host and UI

An isolated aiohttp host bound to `127.0.0.1:38507`, with an owned temporary
workspace and SQLite database. It registered the production workspace and Plan
routes directly, without application boot/auth/SSE changes or a prompt stub.
Python 3.12.3, Bun 1.4.2 and headless Chromium 1243 on Linux x64.

The editor mounted the candidate's existing built `StandaloneEditorInstance`
from `/dist/editor.bundle.js` with `{path:'editor.txt'}`, the shared stylesheet
and CodeMirror vendor asset. It rendered `.cm-content`, loaded the actual file
and produced no page exceptions. The older failure to mount an editor was a
probe limitation; this explicit component mount resolves that narrow blocker.

The Plan probe used the candidate's vendored add-on and its own
`patchPlanRevision`, bundled only in disposable scratch. A test shim performed
URL/response mapping equivalent to `giPlanSidebarRequest`: remove `chat_jid`,
call `/api/sessions/default/plan`, unwrap `{plan}` and preserve HTTP errors.
No store, conditional-write result or revision was simulated. This tests the
add-on and backend route but not the complete compiled application's adapter or
session-switch lifecycle.

## Results

Editor:

- Visible CodeMirror editor; read snapshot had a string revision and
  `truncated:false`.
- Conditional save returned 200 and wrote the draft.
- An external file change caused 409; the local draft and external content both
  survived.
- Save copy used POST create-only and retained the source draft/baseline.
- Cancelling the review left the external version untouched.
- Explicit confirmation of the reviewed version produced a conditional 200
  overwrite. A separate stale save before that confirmation still returned 409.

Plan:

- Save succeeded with the loaded revision.
- An independently updated Plan caused 409; the unsaved local draft survived.
- A stale reset caused 409 and preserved the newer saved Plan.
- Refresh followed by confirmed reset used the current revision and cleared it.
- No page exceptions occurred. The final clean run exited successfully for both
  probes.

Initial probe assertions incorrectly expected HTTP 201 from file creation
(the existing backend returns 200), read the asynchronous response log too early,
and expected a native confirm instead of the editor's review dialog. These
harness errors were corrected. A Plan response logger initially outlived browser
shutdown; its teardown was fixed and both probes reran successfully.

## Open acceptance

The pinned consumer cannot be accepted for revision-safe Classic writes:
`4259e82`'s `updateWorkspaceFile` omits `expected_revision`, while the backend
correctly requires it. Candidate `0259e9a` supplies it. A reviewed repin still
needs schema/profile/retirement checks and full consumer acceptance.

Submit was not tested: this host intentionally has no canonical prompt route.
No issue was closed. This does not establish full-app boot, authentication, SSE,
browser reconnect, Settings UI, live-provider execution, other browsers or six
viewport acceptance. File revision checking's current synchronous comparison/
write tail does not yield within one event loop; there is no process-local file
write lock. It does not guarantee atomic compare-and-swap against an external
writer changing a file between check and write. Independent-process race
reproductions and the concrete storage-contract blocker are recorded in
[workspace-external-cas-20261028.md](workspace-external-cas-20261028.md).

The host was stopped and all disposable copied UI assets, probe scripts,
databases, fixtures and logs were removed after analysis. Only this record is
retained.
