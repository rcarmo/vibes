# Shared interaction parity contract (draft)

Visual checkpoints are meaningful only when both hosts reach them through the same user flow. Each flow runs against native product APIs and components with isolated data. Adapters translate identifiers and wire shapes; they do not click hidden controls, inject product DOM, suppress errors, or turn unsupported actions into successful ones.

## Case shape

An interaction case defines:

- `id`, initial canonical state and required capabilities;
- pointer and keyboard variants where both are applicable;
- stable semantic selectors/accessible names rather than coordinates, except explicit hit-testing cases;
- checkpoints with focus owner, open/closed surfaces, stored draft/media/reference/queue state, current session and server revision;
- failure injection and the input that must remain recoverable;
- scope assertions (session, turn/run and queue item identity);
- optional screenshots after semantic assertions and compositor settling.

A host passes only if each action produces the canonical observable outcome. A missing capability is a failed case. A real backend or browser limitation is reported by the adapter, never hidden with markup or a CSS mask.

## Cross-cutting rules

- Escape dismisses the topmost dismissible surface and restores a usable focus target. It does not abort an agent unless the focused control and flow explicitly request cancellation.
- Pointer targets cannot move between pointer-down and pointer-up because of lazy content or late layout. Keyboard activation must produce the same mutation exactly once.
- Async responses carry the captured session/turn/item identity. Switching A -> B -> A does not make an old A response current, and no response may overwrite B.
- Failed, cancelled or conflicting mutations retain typed text, media and references. Retrying the same action does not duplicate delivery.
- Destructive actions require an explicit confirmation or an unambiguous affordance. Unknown server state disables them rather than assuming safety.
- Unsupported controls are absent or disabled with a reason. They are not renamed into an unrelated action to match a screenshot.
- Screenshot fixtures use deterministic data, but mutation/race tests run separately and retain failure artifacts.

## Initial shared flows

### `shell.workspace`

1. With workspace closed, activate the hamburger by pointer and keyboard. The menu opens once and focus can move through enabled items.
2. Escape and outside pointer-down close it without activating content underneath; `aria-expanded` becomes false.
3. Show workspace through the menu. The file tree becomes reachable and the menu closes. On narrow layouts, the drawer backdrop closes only the workspace and does not trigger the Plan tab or composer.
4. Reopen and hide workspace. Composer text and current session are unchanged.
5. Open terminal/editor only when advertised. A disabled action cannot create a blank pane. Pop-outs transfer only their own pane state and do not install the chat Plan drawer.

### `quick-actions.typeahead`

1. Typing one printable non-whitespace character on noninteractive timeline content opens the palette once, focuses search and preserves that character as the initial query.
2. Editable fields, buttons, links, workspace/editor surfaces, open dialogs/pickers, consumed/repeated/composing keys and Control/Meta/Alt combinations never trigger it.
3. Results contain only current supported sessions, workspace actions and slash commands in native group order. Exact-title and prefix matches determine the initial highlight; arrows wrap and Enter activates once.
4. Escape, close control and outside pointer dismissal preserve session, draft, media and references. Focus returns to the connected opener when applicable.
5. Session/catalog requests are scoped and generation-guarded. Failed activation remains recoverable; command insertion never submits the composer.

### `plan.roundtrip`

1. Open the Plan tab by pointer and keyboard; editor focus is available and progress reflects real checklist items.
2. Edit and save with the loaded revision. Tool read returns the saved text/revision.
3. Tool write with that revision emits the scoped update and refreshes a clean open sidebar. A dirty sidebar keeps its text and reports the remote change.
4. A stale save fails without replacing either editor. Refresh asks before discarding dirty text.
5. Switching sessions preserves separate unsaved drafts in memory; returning restores the correct draft. No draft or update crosses session scope.
6. Submit saves first, then sends the saved checklist to the captured session using normal send/queue policy; composer text/media/references remain unchanged.
7. Escape/close autosaves. A failed autosave leaves the drawer open. Forced reload warns when unsaved state exists.

### `session.picker`

1. Open by pointer and keyboard; search receives focus without shifting the popup after pointer-down.
2. Arrow keys wrap, Home/End and eight-row paging are bounded, and Enter selects. Search Tab selection, IME input and non-search typeahead retain their defined behavior.
3. Switching commits timeline, queue, model/context and composer state as one scoped view. Late responses cannot partially replace it.
4. Pin/archive/restore/rename/delete are exposed only when supported. Running or unknown-count sessions cannot be deleted; failed mutations keep the picker and selection recoverable.

### `queue.lifecycle`

1. Sending while active follows the advertised queue/steer policy and stores text, media and references once.
2. Two items retain FIFO order. Reorder is session-scoped and changes only the selected item order.
3. Remove keeps input when the server rejects an identity/revision conflict.
4. Return-to-editor persists the merged draft before deleting the queue item, does not overwrite text typed while the request is in flight, and is idempotent on repeated activation.
5. Steer requires a matching active run and existing queue item. Idle or unknown activity disables it. A failed steer leaves the item queued.

### `turn.cancel-reconnect`

1. Busy status exposes a stop control distinct from queue-send. Cancellation includes captured session, turn and runtime owner.
2. A disconnected SSE stream does not erase the busy state or redirect cancellation. Reconnect refreshes scoped status.
3. Successful cancellation preserves the composer draft and queue. A stale terminal event cannot end a newer turn.

### `attachments.copy-speech`

1. Upload/paste shows one progress control. Cancellation keeps the draft and prevents send; retry reuses the selected file without duplication.
2. Agent attachment delivery resolves destination from the active turn capability, renders durable media, and survives reload/source removal.
3. Copy returns original stored Markdown/code text, not highlighted HTML.
4. Read aloud appears only for supported browsers and assistant text; starting another post transfers ownership, stale completion callbacks do nothing, and unmount stops only its own playback.

## Ownership

Initial proposal: @vibes owns this contract plus `plan.roundtrip`, `session.picker` and `shell.workspace` executable cases. @tau owns `queue.lifecycle` and model-picker cases. Cancellation and attachment flows are reviewed jointly because their native transports differ. Changes to canonical outcomes require agreement; adapters remain host-owned.
