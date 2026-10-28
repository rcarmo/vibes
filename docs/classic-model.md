# Classic Pi model adapter

GET/PATCH `/api/sessions/{s}/model` expose offered Pi model choices and confirmed
changes on the path session's runtime. Archived, stopped, busy or unsupported
ACP/FFI lanes return unavailable state on GET and reject canonical writes. Legacy
model endpoints are unchanged; canonical FFI support needs a separate revision
contract rather than an echoed request.

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

## Verification

Focused canonical model/Pi/session tests: 65 passed in 1.33 seconds. The full
Python suite passed 1,047 tests with 13 existing skips in 42.02 seconds using the
pinned optional SDK and unchanged shared assets. New route/tests pass Ruff;
diff checks pass. Tests exercise the actual Pi request lock with deterministic
RPC replies, offered selection, sanitised metadata, native readback mismatch,
stale/replayed tokens, busy/unsupported lanes, invalid/missing/archived sessions,
malformed containers, unadvertised thinking and cancellation before setter
acknowledgement. No model provider or complete browser application was started.

Temporary SDK, asset link and disposable test output are removed after analysis.
Live native provider verification, canonical ACP/FFI model revision contracts,
complete consumer model UI and pre-release CPU/allocation profiling still need
work.
