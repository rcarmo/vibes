# fixtures-vibes v0.3.0 alignment — 2026-10-31

Python `main` targets annotated fixtures-vibes tag `v0.3.0`, whose commit is
`8f76048862febf91c26f84a293a9761e5f3cca68`. Relative to `2fc49ef`, the release
removes the legacy Vibes/Tau trees and updates release/layout documentation and
checks. `ui/classic`, `ui/API.md`, schemas, features and suite code are unchanged.
The existing Classic symlink and frontend Make targets remain correct.

The compliance profile now creates sessions through `POST /api/sessions` with
`title` and `agent_id:web`, and opens `/?chat_jid=gi:{id}`. The old `session_id`
URL is not consumed by the Classic session bootstrap. The profile records its
starting runtime revision `ec62eb2`. Skip metadata now identifies `v0.3.0`:
all existing entries were reviewed for catalogue IDs, duplicates, declared
capabilities and capability-absent consistency. Their historical behavioural
reasons were not re-certified as current passing/failing browser outcomes.
The root adapter-gap document now identifies the current Classic binding instead
of the retired Vibes tree; historical candidate evidence retains its revisions.

## Verification

- 54 focused consumer pin/layout/session/boot/settings/cache tests passed.
- Profile and skips validate against release schemas. All 57 skip IDs resolve
  in the 310-scenario catalogue; all 26 capability names are known. None of the
  retired settings IDs or Add-ons/Recordings capability references are present.
- 20 fixture contract/Gherkin tests passed with 204 assertions.
- Classic hook check, 209 shared UI unit tests and one local Plan-tool test pass.
- Main regression: 1,125 passed, 13 skipped in 56.05 seconds, with optional
  Copilot SDK 1.0.14. Targeted Ruff and diff checks pass.
- Chromium loaded the pinned compiled bundle on an isolated real Python HTTP
  host with agent startup disabled. The updated profile created/opened the
  correct session; its message route was requested and title displayed. Composer
  mounted and the opened workspace listed the test folder. No page errors or
  failed HTTP requests occurred.
- GET API probe passed boot and all listed routes except `/pdf-viewer/source`.

## Unfinished acceptance

The profile still lacks `commands.selectModel`, required by the claimed
compaction scenarios. Native command selection/compaction support and full
browser compliance remain unfinished; a schema-valid profile is insufficient.
Existing provider/policy/indexing unavailable responses remain implementation
gaps. PDF attachment source, provider/native tests, filesystem external-writer
CAS and whole-application pre-release profiling also remain open.

No provider calls, push, deployment, shared frontend source edits or Go changes.
Only main was modified. User test edits/probe files were preserved. Disposable
SDK, host/browser scripts, database/workspace, logs and pytest scratch were removed
after analysis. No full-suite browser or release acceptance is established.
