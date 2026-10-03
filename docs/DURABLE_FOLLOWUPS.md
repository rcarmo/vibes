# Durable follow-ups

Schema version 9 stores queued follow-ups and emulated steers in SQLite. Public row IDs are negative values from a monotonic allocator and survive database reopen. Deleting a row does not reuse its ID.

## Ownership and ordering

`FollowupStore` writes use `Database.transaction` and `BEGIN IMMEDIATE`, serialising mutations across shared and independent connections. A claim carries an opaque token scoped to its row, thread and agent. HTTP responses and events exclude that token.

Steers dispatch before normal follow-ups. Each mode preserves FIFO order; promoting a normal follow-up appends it after existing steers while retaining its public ID. Reorder and ordinary removal accept only pending work. Source validation checks chat and root-thread ownership and retains stored attachments.

Before execution, the owner records admission. Confirmed successful execution deletes its admitted row. Errors, cancellation and unconfirmed outcomes mark it uncertain and revoke ownership. Pre-admission rejection releases the same pending row without changing its identity or order. A failed admission journal write prevents execution and leaves the claim for startup recovery.

## Restart and review

Startup recovery runs after database initialisation and before dispatchers or workers. Claimed and admitted rows become uncertain; pending rows stay pending. Startup does not automatically dispatch pending work. A subsequent successful turn can dispatch eligible pending rows.

Native Pi fire-and-forget steering has no per-item completion receipt. Accepted sends and interrupted sends become uncertain. Known no-send results transfer the same row to emulated steering. Completing the enclosing turn does not establish completion of that steer.

`GET /agent/queue?session_id=<chat>` exposes selected-chat pending and uncertain items. Claimed and admitted rows are excluded. The UI explains possible prior execution and offers confirmation-gated discard without retry. `POST /agent/queue-discard-uncertain` requires a negative integer `row_id` and nonblank `session_id`; wrong-chat or non-uncertain rows return 404. Discard never requeues work.

Recovery requires exclusive application startup. Running multiple application instances against the same database while one performs recovery is unsupported. Schema 8 queues were process-local; this migration cannot recover work lost before schema 9 persisted it.

## Verification

The bounded integration set passed 281 tests across database, workers, cleanup, storage, dispatch, agent routes, abort handling, Copilot routes, sessions and Pi transport. A subsequent import cleanup passed all 36 malformed queue mutation boundary cases.

`tests/test_followup_dispatch.py` exercises production startup and real HTTP after database reopen with external runtime services stubbed. It checks uncertain recovery, pending identity, chat isolation and scoped discard. Separate dispatcher tests execute persisted pending work once and exclude recovered uncertain work.

Chromium and WebKit probes cover the uncertain-review component, the full built application's delayed-response guards and session picker, and SSE reconnect. Browser servers use synthetic backend responses. Live-provider acceptance and native per-item steering completion receipts have not been established.
