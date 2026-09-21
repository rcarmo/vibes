# Shared capture adapter contract (runner side)

Canonical state/cases are owned by @vibes; this document specifies only runner
callbacks, not an alternative state schema.

Factories return fresh adapter objects per host/repeat:

- `name`: stable host name.
- `assets`: nonempty map of logical names to actual files (HTML, app/CSS bundles,
  editor vendor, addon source). Capture pins bytes and resolved paths.
- `install({page,context,state})`: installs exact native request routes and state;
  returns `{url, dispose?}`. No persistent production writes. Native SSE servers
  may be owned here and must close through dispose.
- `ready({page,state})`: semantic assertions and documented state transitions.
  Must verify selected session, requested feature visibility and expected content.
  Do not modify product layout/styles to force matching pixels.
- `assertRequests()`: throw on unknown method/path/query, wrong session scope,
  unresolved request errors or unsupported capability. Called before/after shot.
- `dispose?()`: cleanup additional resources even when readiness/capture fails.

Screenshot cases must not mutate state after capture for unrelated safety tests.
Keep workflow/mutation tests separate. Unsupported Plan sidebar/tool fails its
capability case; it is not a renderer limitation.

Runner uses headed browser launcher, fresh contexts, en-US/UTC/DPR1, fixed wall
clock 2026-01-01T12:00Z, blocked service workers and explicit compositor settle.
Native engine versions/display configuration must be recorded by the CLI.

Comparison requires at least two repeats. Exact RGBA differences govern pass;
perceptual differences are supplementary. No masks/resizing/automatic AA waiver.
Originals, repeat diffs, cross-host diffs/overlays and reports are preserved.

Remaining runner work: canonical case CLI, cross-repeat asset equality checks,
real Piclaw/Tau adapters, shared state handoff, production UI headed validation.
