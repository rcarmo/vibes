# Full Python development regression

The full Python test suite passed **969 tests, with 13 existing skips**, in
40.28 seconds on Python 3.12.3/Linux x64. No test was newly skipped or disabled.
This was a development regression run, not the browser compliance suite or a
release-performance workload.

## Setup

Source base `84a992c` plus VNC race fixes and test-fixture updates. Installed
optional `github-copilot-sdk==1.0.14` into owned scratch and set
`COPILOT_SKIP_CLI_DOWNLOAD=1`; no runtime was downloaded/started for these tests.
The checkout's absent submodule assets were supplied through a temporary `ui`
link to unchanged fixture pin `4259e82`. Neither optional SDK nor UI setup changed
a tracked dependency or fixture pin.

Make sets `PYTHONPATH=src` in its test recipe; preserving a scratch SDK required
an explicit Python invocation via `/usr/bin/env PYTHONPATH=<scratch-sdk>:src`.
The initial ordinary run reported 939 passed/28 failed/13 skipped; after correct
optional dependency/asset setup, four durable-queue test mismatches remained.
These setup failures were not counted as passing runs.

## Corrections

VNC review identified two real lifecycle bugs: simultaneous upgrades could act
on a stale no-tunnel snapshot, and shutdown did not own pending TCP connections.
Connection/attachment admission now stays reserved across awaits. Shutdown
rejects new work, cancels and joins pending opens, and closes late sockets.
Close-handshake waiting is bounded. Forced tests verify no duplicate upstream,
no post-shutdown tunnel and closure of a connect completing during cancellation.

The v8 migration fixture's expected schema number was hard-coded to 9; it now
checks the current schema constant while preserving history and idempotence
assertions. The v6 fixture relabelled a modern database without removing newer
note columns; it now removes those additions before exercising the real upgrade.
No duplicate-column exception is ignored in production migrations.

Four tests still targeted retired in-memory queue APIs. They now use the durable
FollowupStore and retain their original safety contracts: cancellation/errors
keep queued items, unsupported FFI steering preserves pending state, listing
excludes foreign-session items, and steering cannot target another session.
Ruff caught unused imports left by those updates; they were removed. A repeat
run exposed procfs reaping races in cancellation assertions (`FileNotFoundError`
or `ProcessLookupError` during reads); both now treat disappearance as stopped,
while still rejecting a live process. The final complete rerun passed.

## Limits and cleanup

Thirteen platform-specific/optional skips are unchanged. This does not establish
Windows runtime operation, account-backed inference, browser reconnect or live
provider selection. The published 162-test browser comparison runs separately
against `86392e6`; this branch's test result cannot replace that comparison.

Disposable SDK, temporary asset link, test databases, caches owned by this run
and logs are removed after the final verification. The concurrently active
browser comparison and shared installed dependencies are not removed.
