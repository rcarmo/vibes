# Developer tools

## UI screenshots

Install frontend dependencies (`bun install --frozen-lockfile`) and the browser
(`bun x playwright install chromium`), build with `make build-frontend`, and
start Vibes with a test workspace/database. Then run:

```sh
bun tools/capture-ui.mjs --url http://127.0.0.1:8765/ --file README.md --output screenshots
```

Captures desktop (1440×1000) and mobile (390×844) timeline/editor PNGs. The file
must exist in the running server's workspace. Options: `--browser chromium`,
`--browser webkit`, `--browser firefox`, `--headed`, `--help`. Firefox uses a
narrow touch viewport rather than mobile emulation. For headed Linux runs use
`xvfb-run -a bun tools/capture-ui.mjs --browser webkit --headed`.

The script does not start a server, send chat messages, or save editor changes.
It fails if navigation or editor loading fails. Existing screenshot files with
the same names are overwritten. Use test data: screenshots can contain private
chat or file contents. Fresh browser contexts do not reuse logged-in sessions.

## Pi conversation isolation smoke

`PYTHONPATH=src .venv/bin/python tools/smoke-pi-sessions.py` starts installed Pi
with extensions disabled in a temporary directory, creates another session, and
switches back. It sends no model prompts and deletes temporary session files.
Requires Python 3.11+ for asyncio.timeout and a `pi` executable on PATH.
