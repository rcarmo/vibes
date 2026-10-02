# Windows host support

Vibes can boot on Windows with its HTTP UI, workspace routes, file attachments and native host metrics. POSIX terminal and legacy descriptor-relative MCP workspace-reader facilities remain unavailable.

## Host metrics

`/system/metrics` uses documented Win32 APIs through Python `ctypes`, with no PowerShell/WMI subprocess or new dependency:

- `GetSystemTimes`: cumulative idle, kernel and user counters; CPU percentage requires two samples. Kernel time already includes idle time.
- `GlobalMemoryStatusEx`: physical RAM total/available, converted to used bytes and percentage.
- `K32GetProcessMemoryInfo`: the Vibes process working set. In-process native agent memory is included; child processes are not.

The server samples at most once every two seconds across clients and retains 30 history points. The browser shows CPU/RAM and process RSS when available. Missing counters are null, not zero. Windows commit/pagefile capacity is not reported as swap; GPU/VRAM and buffer-cache counters are not implemented on Windows. Linux `/proc` and optional DRM counters are unchanged.

## Files and terminal

Attachment reads reject UNC/device paths, drive-relative paths, alternate data streams, ambiguous DOS names, traversal and reparse points. Native handles keep ancestors open without write/delete sharing while opening and reading the final regular file. Tests cover junction rejection and concurrent rename/overwrite attempts. This is a bounded read path, not an OS sandbox.

Windows does not import `fcntl`, `termios` or the POSIX PTY implementation when starting the server. `/terminal/session` returns `enabled: false`. Legacy MCP workspace-read setup fails with an explicit POSIX requirement. The legacy `/shell` command still expects `/bin/bash`; native agent-provided Windows tools are a separate backend capability.

The vendored MCP stdio helper tolerates redirected streams that have no usable `fileno()`. Installed-package smoke cleanup retries transient Windows file locks within a bounded interval.

## Tests

```text
python -m pip install -e '.[dev]'
python -m ruff check src tests
python -m pytest tests -q -rs
```

POSIX-only tests are explicitly skipped on Windows. General HTTP workspace tests, disabled-terminal behavior, metrics and file-confinement tests run normally. `tests/test_windows_metrics.py` exercises injected API decoding and a real Win32 read on Windows. Run Linux CI as well; Windows success does not prove POSIX regression coverage.
