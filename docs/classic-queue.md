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

POST `/api/sessions/{s}/queue/{id}/steer` requires `{active_turn_id}` but returns
501 for an existing owned item and preserves it. The legacy steering helper also
allows idle promotion and does not enforce the candidate's captured-turn contract.
Canonical turn-bound steering needs a separate implementation and native-owner
validation; it is not silently mapped to that helper.

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

No model provider, complete Classic app, browser drag/drop or cross-tab acceptance
was exercised. Temporary SDK, asset link and disposable test output are removed
after analysis. Turn-bound steering, compiled-consumer acceptance and pre-release
CPU/allocation profiling still require work.
