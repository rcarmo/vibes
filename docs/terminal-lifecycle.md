# Local PTY shutdown and handoff ownership

The opt-in POSIX terminal now denies new acquisition after shutdown starts,
tracks opening WebSocket tasks and joins their acquisition before closing the
service. Its JSON wire protocol and shared frontend remain unchanged.

## Process and descriptor lifetime

`TerminalService.open` serialises acquisition under its service lock and rejects
opens once closing. A retained shielded spawn task owns process acquisition.
Cancellation waits for that task to settle, terminates/reaps any acquired process
and closes PTY descriptors only after spawn no longer uses them. Repeated waiter
cancellation cannot bypass that cleanup. Session close retains a shielded close
task; a cancelled caller still joins its process-group SIGHUP/wait/SIGKILL fallback
and removes the service entry. Shutdown serialises against outstanding opens.

Adapter shutdown sets a closing gate before yielding, cancels and joins tracked
opening handlers, closes acquired WebSockets and shuts down all remaining PTYs.
Late-acquired sessions are closed rather than registered. A socket upgraded before
its opening task is cancelled is explicitly closed before its mapping is dropped.
Close-handshake waiting uses the existing aiohttp one-second timeout.

Handoff is rejected while a connection is still opening. Opening-task removal
checks task identity. A failed replacement before the old attachment closes restores
the live old mapping instead of expiring its PTY. Shutdown during an in-progress
handoff closes both acquired sockets, including the old attachment whose mapping
was replaced. Timers and handoff tokens are cleared after cleanup.

## Verification

Deterministic tests first reproduced pending-open shutdown and post-shutdown-open
failures. Review expanded coverage to spawn cancellation, repeated cancellation,
close cancellation, handoff while opening, failed replacement before old close,
and shutdown while old close is suspended. Tests use actual isolated POSIX PTYs
and gated acquisition/close seams; all acquired test processes are reaped. The
terminal service/routes/race gate passed 19 tests in 3.56 seconds. The full Python
suite passed 1,092 tests with 13 existing skips in 46.82 seconds using the pinned
optional SDK and unchanged shared assets. Changed modules/new tests pass Ruff;
diff checks pass.

These are local lifecycle/transport checks. Complete compiled terminal pane,
browser emulator rendering, sustained slow-consumer behaviour, descendants that
escape the process group, Windows service support and release profiling/acceptance
are not established. Windows terminal remains explicitly disabled. Existing shell
selection, workspace cwd, private-variable filtering, bounded history, resize,
controlling-terminal and foreground-interrupt behaviour stay covered by prior
real-PTY tests.

Temporary SDK, asset link and disposable test output are removed after analysis.
No provider, shared UI/pin change, deployment, push or other-agent contact occurred.
