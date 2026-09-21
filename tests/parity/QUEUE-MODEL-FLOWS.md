# Queue and model interaction acceptance (draft)

Owner: Tau. Input to the shared interaction contract; not evidence of passing coverage.

## Common rules

Run each native host independently with the same semantic state. Use real pointer clicks and keyboard focus/Enter/Space, never forced clicks. Capture before/after checkpoints with native assets and unmasked diffs. Record request IDs, selected session, stored revisions, queue order and drafts, as well as DOM state. A fixture-only mutation proves UI routing, not live backend behavior; repeat persistence/race cases against isolated native servers. No production mutations.

An unsupported operation is a capability failure, not permission to fabricate a control. Reference defects remain recorded; do not copy unsafe behavior to achieve visual equality.

## Queue flows

Preconditions: two distinct queued IDs in one session, a second session with unrelated items, a composer draft, explicit idle/running state. Exercise attachments and references separately from plain text.

- **Send while busy:** submit text once; show one queue row with its persisted ID. Preserve ordering, clear only the successfully accepted submitted draft, and retain later edits. Failure retains draft and shows an actionable error. Enter and pointer submission agree.
- **Idle Steer:** remains disabled, causes no request on click or keyboard activation. Piclaw currently differs; do not enable Tau's idle action to match it.
- **Active Steer:** consume the selected original queued ID exactly once; deliver to the active session/run only. Repeated activation is guarded. Completion races must not duplicate, lose or retarget the item to another session. Preserve other FIFO IDs.
- **Reorder:** first Up and last Down disabled. Move exactly one adjacent position within the same target group; persist order across reload. Errors retain reconciled authoritative ordering, never report success from optimistic DOM alone.
- **Remove:** remove only the selected ID after server success; failed/409 removal keeps the row or explicitly reconciles its actual consumed state. Do not affect composer text or another session.
- **Return to editor:** durably preserve the original content before deletion, append to the latest origin-session draft, and retain attachments/references. Storage failure prevents DELETE. Switching sessions during the request must not write into the new session's draft. Retrying a partial failure is idempotent. Test concurrent edits and already-consumed 409 separately.
- **Reconnect:** reload and SSE reconnect reproduce native queue IDs/order without duplicates. Focus returns to a surviving adjacent control or composer after row removal, never a detached node.

Existing Tau evidence: installed active-steer HTTP/SSE tests in both engines; return-to-editor storage/race tests. These do not establish all shared-host flows, especially attachment/reference retention.

## Model flows

Preconditions: registry supplies at least two real model entries with explicit capabilities; current session/model selected; unrelated session unchanged; composer contains text and attachment/reference variants.

- **Open/search/dismiss:** pointer and keyboard open the same picker, focus its search field, and preserve composer content. Search filters native registry results; no-match state is explicit. Escape/outside dismissal restores focus to trigger and does not change model.
- **Navigate/select:** arrows and Enter select the same model as pointer activation. Commit only after accepted native mutation; update label/context window from authoritative response. Reload persists selected model in that session only.
- **Failure/race:** rejected switch retains current model and draft and exposes error. Disable duplicate requests; changing sessions during a pending switch cannot overwrite the new session's label or configuration.
- **Capabilities:** thinking controls exist only for advertised support; configured policy is not proof of reasoning capability. Unknown context stays unavailable; local token estimates are labelled as estimates. Compaction is actionable only when genuinely supported. Do not fabricate token usage or silently reinterpret unknown as zero.
- **Active run:** define native support before testing model changes mid-run; do not let a UI label imply a running turn was changed if only subsequent turns use the new model.

## Evidence still required

Every flow needs per-host capability status, pointer/keyboard results, persistence and failure/race evidence, and screenshot checkpoint IDs. Exact screenshot equality alone cannot complete a flow.
