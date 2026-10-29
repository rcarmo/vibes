# Bounded local PTY browser transport

Headless Chromium exchanged real shell input/output over the Python terminal
WebSocket adapter, resized the PTY, isolated two browser owners, reattached to
the same shell process and verified expiry cleanup. Runtime `da1abfb`; this
probe did not mount the shared terminal pane or a browser terminal emulator.

## Workload

The host used the real `TerminalAdapter` and POSIX `TerminalService`, explicitly
enabled for `/bin/sh` in an isolated project-owned workspace. Its environment was
created with an allowlist of PATH, owned HOME/temp directories and source/cache
configuration; dotenv discovery was disabled before importing Vibes. No provider
or keychain credential was supplied. The actual shell reported the synthetic
provider variable unset and its working directory inside the fixture workspace.

Browser pages used same-origin owner cookies and WebSocket JSON frames. Output
was accumulated into a plain DOM `pre`, not an emulator. The first page executed
a harmless printf and pwd, then sent resize 101 columns by 31 rows. The real
shell's `stty size` reported `31 101`. A second browser context acquired a distinct
session ID and process PID; its output marker never appeared on the first page.
Closing and reopening the first socket before grace expiry returned the same
session ID and PID. After both pages closed and grace expired, service inspection
reported zero sessions, sockets and opening tasks.

The final fresh-host probe passed without source changes. The preceding full
Python regression passed 1,092 tests with 13 existing skips in 46.82 seconds;
terminal lifecycle/routes tests passed 19 cases. This browser check exercises the
wire contract separately from those deterministic cancellation/race regressions.

## Limits and cleanup

No shared terminal pane, xterm/Ghostty rendering, keyboard shortcut UI, clipboard,
popout interaction, sustained slow-consumer soak, six-project suite or Windows
support was tested. Separate owner processes share the intentionally configured
workspace and OS user; this is transport/process ownership, not filesystem or
multi-user isolation. The terminal remains opt-in and disabled on Windows.

The browser and host were stopped after all fixture sessions expired. Probe
scripts, synthetic workspace, output and logs are removed after analysis. Only
these concise conclusions remain. No shared frontend/pin, provider, Go, push,
deployment or other-agent contact occurred.
