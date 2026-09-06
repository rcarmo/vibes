# Python revival audit — 2026-09-06

## Verdict

The original Python UI is viable as a revival base. Keep this work on
`revival/python-audit`, not on Go main. This is not a certification of production
security or live provider compatibility.

## Verified fixes

- Removed dead steering bookkeeping; no change to queue/steer semantics.
- Updated Python and frontend dependencies, committed Bun lockfile, and made
  Ruff's baseline lint policy local rather than inherited from the parent workspace.
- Blocked popups no longer discard the source editor tab.
- Popout transfers retain the saved baseline: unsaved text stays dirty and closing
  the transferred tab requires confirmation. Tested in Chromium and WebKit.
- Cross-origin API requests are rejected before route execution.
- Public health-path exemption is exact, not a `/health*` prefix.
- Default network bind is loopback (also in Makefile). There is no built-in login;
  explicit remote deployment requires an authenticated reverse proxy.
- Browser suite owns an isolated in-memory database/server and does not rely on
  a manually started service. Bundled frontend was rebuilt and committed.

## Verification

- Python 3.12: 390 tests passed after dependency upgrades and middleware fixes.
- Ruff and frontend ESLint passed; Bun frontend bundle builds.
- Chromium: 19 editor tests passed, including two new popup/data-loss regressions.
- Headed Chromium + WebKit under Xvfb: all 38 tests pass, including popup opening.
  Headless WebKit popup automation is unreliable on this host; no tests were skipped.
- Desktop (1440x1000) and mobile (390x844) screenshots use isolated test data.

## Remaining blockers / scope boundaries

1. Headless-only WebKit popup limitation (headed suite passes): reproduced under Bun and Node, with/without forced
   window features, software rendering, delayed source-tab teardown, and blank
   window navigation. None provided a repeatable fix; experiments were reverted.
   Native WebKit logs include automation-context warnings. Minimal blank-page
   popups work, so attributing this solely to the runtime is not justified.
2. Installed Pi subprocess and the Python Pi client both successfully returned
   `get_state`. Live ACP authentication and model responses were not exercised. Backend
   protocol/lifecycle coverage is from the existing mocked tests. No credentials
   or real user database were used. A live-provider smoke test remains required.
3. Authentication is still a callback seam, not a user login system. Loopback
   default and browser-origin rejection do not sandbox agents or block direct
   non-browser clients. Do not deploy without external access control.
4. Workspace path resolution checks resolved paths, but is not an OS sandbox or
   a race-proof filesystem capability boundary. Do not run untrusted local users
   against a writable workspace under this process.
5. Screenshots prove renderability, not comprehensive mobile or accessibility
   conformance. Editor suite is narrower than all chat/settings/media workflows.

## Reproduction

```
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e '.[dev]'
bun install --frozen-lockfile
PATH="$PWD/.venv/bin:$PATH" make check PYTHON=.venv/bin/python
make build-frontend lint-frontend
bun x playwright install chromium webkit
bun x playwright test
```

The original UI revival and bounded automated audit are verified. Paid model
responses and production deployment remain explicit acceptance checks, not claims
made by this report. Run `make test-browser` for the supported Linux browser
verification path. Slash-command tests now isolate persisted settings to avoid
writing fake models into developer configuration.
