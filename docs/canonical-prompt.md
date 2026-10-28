# Canonical prompt admission and send recovery

POST `/api/sessions/{s}/prompt` enters the real Vibes dispatcher. GET
`/api/sessions/{s}/send-receipt?client_request_id=...` recovers the original
admission result without sending another prompt. Legacy routes remain available.
No Classic static tree or consumer pin is switched by these routes.

## Request and result

Accepted fields: required nonempty `prompt` (at most 512 KiB), optional
`intent: prompt|queue|steer`, `client_request_id`, `media`, `parent_turn_id`, and
`target_agent_id`. Only the configured single `web`/`default` target is supported.
Media is a list of at most eight `{media_id,session_id?}` entries; both supplied
scope and persisted media metadata must match the path session. Parent turn IDs
must resolve to a currently active persisted turn in that session. An unknown,
foreign or expired parent is 409 before new admission.

Clients should always supply a stable, opaque `client_request_id`, at most 200
characters. Callers without one get a generated ID in the response but cannot
recover it if that response is lost. Invalid/unknown fields are 400; nonexistent
or archived sessions reject new work. Existing confirmed/rejected receipts can
still be recovered after later archival, media deletion or parent expiry.

The result preserves existing `user_message`, `thread_id`, queue/command status
and error fields, adding `session_id`, `source_session_id`, `client_request_id`
and `user_message_id`. A newly admitted worker gets a reserved `turn_id` which
is passed to the actual worker and `begin_turn`. A queued follow-up exposes its
`queue_item_id` and does not invent a native turn ID. A successful response is
an admission acknowledgement, not completion of inference. Dispatch-unavailable
responses remain 503 with `admitted:false`; a stored user message alone never
becomes a successful worker acknowledgement.

## Durable receipt state

Schema 13 adds `prompt_receipts`, keyed uniquely by session plus request ID.
Normalised request content is fingerprinted for identity checking; the hash is
not a generated-output correctness gate. Duplicate IDs with different content
return 409. Same-content terminal receipts return the original status/JSON.

A unique pending claim precedes admission. Message creation links its ID to that
claim in the same SQLite transaction as the user interaction. Receipt finalisation
occurs only after the actual dispatch/queue helper reports its outcome:

| State | Meaning |
| --- | --- |
| `pending` | Claimed, with no confirmed final admission response; may survive a process interruption |
| `confirmed` | Actual dispatcher/queue/command returned success; result is durable |
| `rejected` | Actual admission returned an HTTP error; retry returns that error |
| `uncertain` | Interrupted admission may have performed side effects; no replay is permitted |

A pending or uncertain ID always returns 409/no replay on POST. Receipt GET
returns `{receipt:{status,source_session_id,client_request_id,result}}`; an absent
receipt is 404. The client must inspect/reconcile uncertainty deliberately, never
create a new ID merely to replay unconfirmed work. There is no automatic pending
recovery or background redispatch after restart.

The process admission lock shares FFI's existing session lock; SQLite uniqueness
also prevents two processes claiming the same request. The claim is shielded so
cancellation can settle whether it was acquired. Finalisation transitions only
from pending: cancellation cannot downgrade an already committed terminal result.
If a claim is interrupted after a message or worker side effect, cleanup marks it
uncertain. A hard process exit can leave pending, which has the same no-replay
policy. This is at-most-once admission/recovery, not a transaction spanning model
execution or a claim that every admitted response completes.

## Verification

Focused prompt/receipt/agent/cancellation/database/model gate: 193 passed in
3.78s. Tests cover duplicate concurrent POST, different-payload conflict,
restart/reconnect receipt lookup, stored-message linkage, dispatch rejection,
foreign media/parent/session exclusion, cancelled admission, claim/finalisation
cancellation, completed-parent retry and actual reserved worker identity.
The full Python suite with the pinned optional SDK and unchanged shared assets
passed 988 tests with 13 existing skips in 39.08s. Ruff and diff checks passed.

A bounded headless Chromium Plan probe used the candidate `0259e9a` add-on with
its revision patch and a thin URL/field mapping to real file/Plan/prompt routes.
Submit created exactly one user message, entered the real task queue, stored one
synthetic agent reply and ended its active turn. Receipt GET returned the same
confirmed turn ID. No page exceptions occurred. The deterministic dispatch seam
provided test output; no live provider was called and no fake prompt handler was
used. Initial probe assertions used an obsolete prompt marker/status string;
a corrected fresh-database run passed.

Full compiled consumer boot, authentication deployment, broad media routes,
canonical activity/queue/model controls, six viewport/browser acceptance,
live-provider admission, independent-process crash injection and CPU/allocation
profiling of repeated concurrent admission remain open. Shared UI adoption and
release acceptance are separate tasks. Nothing was pushed or deployed.

Probe host, synthetic database, copied add-on assets, temporary optional SDK,
asset link and disposable logs are removed after analysis; concise conclusions
remain here.
