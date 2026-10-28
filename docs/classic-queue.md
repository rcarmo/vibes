# Classic durable queue adapter

The Python runtime exposes session-scoped queue snapshots, removal and atomic
compare-and-set reordering. Legacy queue routes keep their existing behaviour.

GET `/api/sessions/{s}/queue` returns `items`, `pending_steers`, `uncertain` and
`active_turn_id`. A turn ID is present only when exactly one persisted default
agent turn belongs to the session. Queue identities are canonical negative
integer strings derived from durable sequence IDs. Each item includes prompt,
mode/state, source message/thread IDs, session/chat identity, created time and a
minimal receipt-linked `metadata.client_request_id` when available. Claim tokens,
fingerprints and provider configuration are excluded.

The queue thread and original message must both belong to the path session, and
the message must belong to that thread. Missing/corrupt source records are hidden
and cannot be removed or reordered through this adapter. GET can inspect archived
sessions; mutations reject them. Unknown query options are rejected.

PATCH `/api/sessions/{s}/queue` accepts exactly `{expected,order}` arrays of
unique durable string IDs, at most 1,000 items. Both arrays must contain the same
set. An immediate SQLite transaction compares `expected` against the complete
current pending normal queue for that session. Concurrent enqueue, claim, removal
or reorder makes a stale request return 409. A successful permutation changes
only those items' existing ordinal slots; it preserves durable IDs and does not
alter steers, claimed/uncertain rows or another session. Duplicate ordinal slots
return 409 requiring recovery; the endpoint never acknowledges an order that a
tie would prevent it from persisting. Readback occurs in the same transaction.

DELETE `/api/sessions/{s}/queue/{id}` removes only a session-owned pending normal
item, preserving its user message and send receipt. Foreign/missing IDs return
404. Claimed/uncertain/steer items return 409; this route does not discard uncertain
work or permit automatic replay.

POST `/api/sessions/{s}/queue/{id}/steer` requires a bounded `{active_turn_id}`.
The canonical Pi text path verifies a uniquely active persisted session turn,
source ownership, runtime turn token, exact native task, selected session, busy
request lock, live process and writer. The final native check and synchronous
write contain no await. Idle promotion, stale/ambiguous targets and attachments
return 409 without sending; ACP/FFI return 501 with the item preserved.

An immediate SQLite transaction commits an uncertain item and opaque admission
owner before signal I/O. False from the native helper guarantees no write was
attempted and permits that same owner to restore pending state. Any attempted
write, including an exception, stays uncertain and cannot auto-dispatch. A hard
exit between commit and write also leaves uncertain state. The operation is
shielded from request cancellation through settlement. Success returns 202
`sent_unverified`, acknowledging a local write attempt without claiming native
processing, delivery or turn completion. Explicit queue inspection/reconciliation
is required afterward; retrying the same item cannot resend it.

These guarantees apply to this canonical endpoint. The compatibility
`/agent/queue-steer` route still permits legacy idle/emulated promotion and has
its older admission semantics. It has not been retired or given the canonical
captured-turn contract. This change establishes no app-wide steering guarantee.

Mutation events are scoped by transaction-verified ownership and carry `chat_jid`.
Candidate `0259e9a` omits `agent_queue_reordered` from its active refresh-event set,
so another tab can keep stale ordering until its periodic/explicit refresh. No
shared frontend source was changed.

## Verification

The initial queue/store/message gate passed 23 tests in 1.11 seconds. Added tests
cover source/root mismatch, minimal receipt metadata and tied-ordinal rejection.
The full Python suite passed 1,038 tests with 13 existing skips in 41.51 seconds,
using the pinned optional SDK and unchanged shared assets. New route/tests pass
Ruff and diff checks pass. Tests include concurrent same-revision reorder with
one winner, reopen persistence, cross-session isolation, claim/enqueue invalidation,
strict IDs/sets, transcript preservation and uncertain-item protection.

Captured-turn steering's focused queue/store/cancellation gate passed 66 tests
in 3.03 seconds. The follow-up full Python suite passed 1,061 tests with 13 existing
skips in 47.69 seconds. Tests check the actual synchronous Pi writer helper using
a mocked process/writer/task, concurrent duplicate requests, fresh-database reopen,
no-replay after write exceptions, request cancellation during settlement, runtime
promotion/task/selector/process/writer races, ambiguous persisted turns, foreign
items, attachments and unsupported backends. New/changed queue modules/tests pass
Ruff and diff checks. Read-only review found no additional canonical-path defect;
it identified the unchanged legacy steering contract described above.

No model provider, complete Classic app, browser drag/drop or cross-tab acceptance
was exercised. Temporary SDK, asset link and disposable test output are removed
after analysis. Native steering acknowledgement, compiled-consumer acceptance and
pre-release CPU/allocation profiling still require work.
