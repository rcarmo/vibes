## Shared session Plan

The Plan drawer and agent tools use the same SQLite record. A browser edit is visible to the next tool read; a tool write broadcasts `plan_updated` and updates the drawer without reloading the chat. This is separate from the transient Planning preview shown during a turn.

Open the right-hand Plan tab to edit the Markdown checklist. Save persists it; Refresh asks before discarding unsaved edits; Reset clears the checklist after confirmation. Closing the drawer saves dirty text, and a failed save leaves the drawer open. Submit to model saves first, then submits the saved checklist to the captured session using the normal `auto` send/queue policy. It does not replace the composer draft.

Unsaved text is retained in memory per session while switching chats. A newer server revision does not overwrite it. Reloading a dirty page triggers the browser's leave-page warning; drafts are not persisted across a forced reload. The drawer is not installed in editor/terminal pop-out windows.

## Model tools

Pi exposes `vibes_plan`. ACP exposes `plan` through the same local MCP descriptor that supplies `attach_file`, including when history-read access is disabled. Both support `read`, `write`, `update`, `patch` and `edit`.

```json
{"action":"read"}
```

The result includes `session_id`, `markdown`, `revision` and `updated_at`. Mutations require `expected_revision` from a previous read:

```json
{"action":"update","expected_revision":2,"plan":[
  {"step":"Inspect reference","status":"completed"},
  {"step":"Implement changes","status":"in_progress"},
  {"step":"Verify both browsers","status":"pending"}
]}
```

`patch` accepts `add`, `update` and `remove`. Select an existing item with a 1-based `index` or a unique text `match`, not both; `add` accepts `position: start|end`. `edit` accepts exact `oldText`/`newText` replacements, deletion, insertion before/after an `anchorText`, and append/prepend. Ambiguous matches fail without saving. Updates preserve unrelated prose; fenced Markdown examples do not count as checklist items. Normalisation keeps the first in-progress item and marks additional ones pending.

The limit is 128 KiB of UTF-8 Markdown. A stale revision fails rather than overwriting another editor. No tool argument selects a destination: the server resolves it from the authenticated Pi/ACP capability and current turn. Browser-origin calls to the internal tool endpoint are rejected, even on loopback. Provider-generated empty optional fields are removed by the tool adapter before sending the action-specific payload.

## HTTP and persistence

`GET /sessions/{id}/plan` returns the saved snapshot, or an empty revision-zero Plan for an existing session without a record. `PUT` requires exactly `markdown` and `expected_revision`. Success advances the revision and broadcasts `plan_updated`; conflicts return 409 with `code: plan_revision_conflict`. Unknown sessions return 404. Archived sessions are readable but cannot be changed.

`POST /internal/agent-tools/plan` is the loopback bearer-capability transport for model tools. It uses the same store as the browser API. Mutations are conditional SQLite statements, so two connections cannot both overwrite the same revision. Schema migration 8 adds `session_plans`; deleting a session cascades to its Plan.

## Verification boundary

Storage tests cover persistence, independent-connection conflicts, session isolation and bounded edits. Browser tests exercise real SSE updates, dirty-text conflicts, saved revisions, draft restoration across session switches, late responses, submission and 390/820/1440px drawers. The registered ACP MCP tool has a bidirectional store/API test; no external ACP model execution is claimed.

An isolated Pi model run used only `vibes_plan`: it wrote a random checklist marker, which appeared in the mounted drawer via SSE. A browser edit replaced that marker with another random value; a second model read returned the new value without receiving it in the prompt. Reload preserved the second revision. This verifies the default Pi session, not named Pi-session persistence or complete visual parity.

The drawer uses Piclaw's MIT-licensed Plan sidebar markup, styles and CodeMirror configuration, adapted to Vibes' native session API and revision handling. The original notice is retained in `src/vibes/static/js/vendor/licenses/PICLAW-MIT.txt`.
