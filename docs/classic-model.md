# Classic native model adapters

GET/PATCH `/api/sessions/{s}/model` expose offered Pi/FFI model choices and
confirmed changes on the path session's runtime. Archived, stopped, busy or
unsupported ACP lanes return unavailable state on GET and reject canonical
writes. Legacy model endpoints retain their request/response contract.

GET holds Pi's per-session request lock across session selection, current-state,
model-catalogue and thinking-level reads. The result includes `model_options`,
`provider_options`, `current` (`provider/model`), `thinking_level`, `thinking_token`
and `thinking:{levels,configurable}`. Offered choices are bounded/sanitised and
exclude provider URLs/keys. Thinking is configurable only when the current model
advertises reasoning support and the native level catalogue offers choices.

PATCH accepts either `{model}` or `{model,thinking_level,thinking_token}`. A model
change must match a native offered provider/model choice. A thinking change must
match the captured model and opaque observed token under the same request lock,
then pass the current model's reasoning flag and native offered-level checks.
Unknown fields or malformed values return 400; busy/stale/unconfirmed writes
return 409. Successful responses use native post-write readback and verify the
requested identity/level; no requested value is echoed as confirmation.

Tokens represent process-local observations, not native monotonically increasing
revisions. A model/thinking/session change observed by these helpers rotates the
token; mutation invalidates it before setter I/O, including cancellation/timeout
following a possibly committed write. A subsequent write requires fresh state.
Tokens do not survive restart. An unobserved external A -> B -> A transition
cannot be detected without a native revision mechanism. Native transport
uncertainty requires refresh/reconciliation; clients must not blindly replay a
write whose response was lost.

Malformed native state/catalogue containers fail closed. Cancellation is not
caught as an ordinary HTTP error. The route emits a scoped model-change event
only after confirmed readback. It never starts a model provider solely to fill
an unavailable catalogue.

## FFI lane observations

Canonical FFI reads use only an already acquired session on an existing ready,
idle lane; inspection never starts the runtime or acquires a session. The lane
lock covers current state, offered catalogue, token validation, setter and native
readback. Opaque tokens include local session/client ownership and observed
model/reasoning state. The host checks exact lane/session/client identities after
RPC awaits and before mutation. Replacement, shutdown, malformed state, failed
reads, timeout and cancellation revoke observations. The setter also invalidates
the token before I/O, so uncertain writes require fresh inspection.

FFI choices and reasoning efforts use the existing bounded native catalogue
projection. A model change must be offered; a thinking change must match the
observed model/token and its offered effort list. Confirmed changes save an
already persisted backend binding using the existing native sessions-save flow.
No binding is invented for an unbound chat. GET timeout returns unavailable;
unconfirmed PATCH timeout returns 409. Cancellation continues to propagate.
Native model changes confirmed at runtime but interrupted during save/readback
remain uncertain to the caller; clients must inspect instead of blindly replaying.

## Verification

Focused canonical model/Pi/session tests: 65 passed in 1.33 seconds. The full
Python suite passed 1,047 tests with 13 existing skips in 42.02 seconds using the
pinned optional SDK and unchanged shared assets. New route/tests pass Ruff;
diff checks pass. Tests exercise the actual Pi request lock with deterministic
RPC replies, offered selection, sanitised metadata, native readback mismatch,
stale/replayed tokens, busy/unsupported lanes, invalid/missing/archived sessions,
malformed containers, unadvertised thinking and cancellation before setter
acknowledgement. No model provider or complete browser application was started.

The FFI follow-up gate passed 65 tests in 1.16 seconds before additional failure
invalidation tests. The final full Python regression passed 1,076 tests with 13
existing skips in 43.59 seconds. Tests use actual host/lane locks and deterministic
native-RPC seams for offered changes, stale/replayed tokens, unavailable/busy or
unbound lanes, lane/session/client replacement, malformed state, setter/read
cancellation and timeout, failed catalogue reads and binding persistence. No
SDK runtime or provider was started. Changed host/route/new tests pass Ruff and
diff checks pass.

Temporary SDK, asset link and disposable test output are removed after analysis.
Live native provider verification, canonical ACP model revision contracts,
complete consumer model UI and whole-application pre-release profiling still
need work.
