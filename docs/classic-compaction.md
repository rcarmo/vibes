# Canonical FFI compaction lifecycle

Canonical compaction now calls native `session.rpc.history.compact` on an existing
idle FFI session, with durable admission, polling activity and exact-owner abort.
Pi/ACP canonical compaction remains unavailable. No normal prompt, reset or
transcript replay substitutes for the native operation.

## Capability and admission

GET `/api/sessions/{s}/compaction` returns `available`, `token` and the most recent
`operation` when present. A token is offered only for an already acquired ready
FFI lane with native compact/abort methods, no active conversation turn and no
pending/running/cancelling/uncertain compaction. Inspection never creates a lane,
starts a runtime or contacts a provider. Archived/unsupported sessions report
unavailable; missing sessions return 404. Unknown queries return 400.

An offer lasts 30 seconds; at most 128 are retained. It captures exact local lane,
session and client references plus transcript row count/latest ID and session
metadata. These are local observations, not a native monotonic history revision.
A new transcript row, observed deletion, session change or owner replacement
invalidates admission. Unobserved direct native/external mutations cannot be
excluded without a native revision mechanism.

POST accepts exactly `{token}` and returns 202 with `turn_id`, `state` and
`recovered`. The shared FFI admission lock, native lane lock and immediate SQLite
transaction exclude competing admission and revalidate the offer. Schema 15's
`compaction_operations` stores a unique token and turn ID before a retained worker
can call native code. A duplicate token returns its original operation and never
redispatches. The HTTP waiter is shielded through admission/task registration;
a disconnected request cannot authorise another attempt. Process loss after the
commit leaves durable pending state, which startup converts to uncertain.

## Activity, completion and cancellation

GET `/api/sessions/{s}/activity` returns the operation's stable `compact-...` turn
ID, `intent_key: compaction`, and running/cancelling status while active. Session
registry running state includes active compactions. GET compaction exposes the
last durable state and only bounded numeric result counts; native summaries,
provider errors and credentials are not returned.

The native lane lock stays reserved from admission through final settlement.
SDK 1.0.14 `history.compact(timeout=120)` returns a completed operation result;
the adapter adds a 125-second outer bound. A successful response from the same
native owner permits completed state. Malformed results, failure responses,
timeout or interrupted native work become uncertain and poison the local lane.
Failed native work does not prove that no mutation occurred. Pre-native ownership
failure becomes failed without pretending that compaction ran.

POST activity with the captured compaction turn ID sends
`abort_manual_compaction(timeout=10)` to that exact session. SDK's `aborted:true`
means the abort signal was applied, not that compaction has stopped. Activity
stays cancelling until the original compact call and any captured abort RPC
settle. Cancellation tracking remains sticky until finalisation; delayed abort
cannot reach a promoted operation. Any abort-touched operation ends uncertain,
including a later success response from the original call, because the combined
mutation outcome needs reconciliation. Abort failure/timeout also poisons the
lane. A foreign or stale turn cannot cancel it.

Active or uncertain operations block new FFI prompt admission, stored transcript
creation/deletion/thread movement and session archival/deletion. Canonical message
delete returns 409. Uncertain records remain durable after restart and prevent
another compaction or transcript mutation; there is deliberately no automatic
replay, discard or invented successful recovery endpoint. Operator reconciliation
requires a separate contract before clearing uncertainty. This conservative policy
can leave a session blocked; it preserves uncertain native state.

Shutdown stops new offers/admissions, joins admission registration, requests abort,
waits for settlement and cancels outstanding operation tasks. Ambiguous work is
persisted uncertain before native shutdown/database closure. A stopped manager
cannot issue new capabilities. Dedicated lifecycle tests preserve cleanup ordering.
Polling supplies current state; new compaction SSE event handling is not claimed.

## Verification

The focused lifecycle/unsupported-compaction/activity/session gate passed 44 tests
in 3.05 seconds. The final full Python regression passed 1,107 tests with 13
existing skips in 49.82 seconds using the pinned optional SDK and unchanged shared
assets. Changed backend modules, lifecycle tests and cleanup-order tests pass Ruff;
diff checks pass. No provider or native SDK runtime was started.

Tests use actual database, manager and native lane locks with deterministic RPC
seams: duplicate admission, exact operation identity, native completion, stale
session/client/transcript/lock, abort signal versus completion, delayed abort,
unsuccessful native result, abort false, timeout/poisoning, request cancellation
at commit, shutdown, schema-14 migration/reopen, restart uncertainty and
transcript/registry/archive/delete guards. The SDK generated request/result
source was inspected for compact completion fields and abort's `aborted` meaning.

Review identified unsafe failed-result replay, premature terminal publication
while abort was outstanding, and cancellation tracking removed before original
completion. Tests and state transitions now cover those races. Initial full runs
also exposed old startup/cleanup fixtures passing `None` and a test-level asyncio
lock crossing event loops; those fixtures were updated without weakening runtime
checks. Two preliminary read-only audits timed out and supplied no review result;
subsequent bounded reviews found the concrete races above.

Live native/provider execution, process-kill injection specifically during native
compaction, compiled Classic UI controls, realistic latency/allocation profiling,
Pi/ACP compaction and whole-application release acceptance remain open. Scratch SDK,
logs, temporary shared asset link and disposable test output are removed after
analysis; only source tests and these concise conclusions remain. No shared UI,
fixture pin, Go work, push or deployment changed.
