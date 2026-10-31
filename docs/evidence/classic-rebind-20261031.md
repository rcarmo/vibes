# Classic consumer rebind — 2026-10-31

Vibes now binds `src/vibes/static` to
`../../references/fixtures-vibes/ui/classic/static` at fixtures-vibes
`2fc49eff0f0025cd542ce17853b5db63f7925359`. The consumer Makefile uses Classic
`check`, `build` and `test` targets; npm commands delegate to that Makefile.
Shared frontend source and committed bundles are unchanged.

Root bundle paths (`/dist/`, `/css/`, `/fonts/`, `/js/`, `/editor-vendor/`,
`/common/`) and `/static/` aliases serve the pinned assets. Unknown API and
missing asset paths retain 404 responses; extensionless app paths serve the
index. Index caching stays disabled; assets revalidate, including 304 replies.
Viewer pages use the pinned Piclaw CSP and page-specific SAMEORIGIN framing;
other pages retain DENY. Opaque widget origins may GET/HEAD static modules;
API requests and writes from those origins remain denied.

The runtime-owned diagnostics page and script moved out of the old UI tree
into `diagnostic_assets`, included in Python package data. No shared frontend
files were edited. The fixture pin and Go worktree are unchanged.

## Checks

- Active Python branch: 46 focused binding/boot/routes/middleware tests passed.
- Primary checkout: 66 focused binding/routes/config/middleware tests passed.
- Diagnostics and updated asset-cache gate: 30 tests passed in each checkout.
- Shared Classic hook check passed; 209 UI unit tests and the local Plan-tool
  test passed using the consumer targets. The build target's command mapping
  was checked with `make -n`; committed bundles were served without rebuilding.
- Final active Python regression: 1,115 passed, 13 skipped in 64.59 seconds,
  with the pinned optional Copilot SDK 1.0.14. Targeted Ruff and diff checks pass.
- Installed wheel: isolated-import smoke passed for health, index, root JS/CSS,
  diagnostics, messages-MCP entry point and extension presence.

## Compiled browser boot and limits

Chromium loaded the pinned bundle against the active Python checkout's real
HTTP routes with an isolated database/workspace and agent startup disabled.
One composer mounted, Plan loaded, and no JavaScript page errors or static
asset failures occurred. No external provider calls were made.

`/api/system-metrics`, `/api/quick-actions` and `/sse/topics` returned 404;
the workspace still displayed loading after five seconds. This bounded boot
check did not test provider submission, workspace editing, complete session
behaviour, browser compliance or release performance. The primary checkout
has fewer Classic backend adapters; its HTTP binding tests do not establish
compiled application compatibility. Existing full-application and external
writer CAS limitations remain open.

The first regression found old cache-test URLs and a missing diagnostics page;
both were corrected before the passing final run. Build-environment probes
needed isolated build dependencies and installed runtime dependencies; the final
installed-wheel smoke passed. Probe scripts, logs, SDK, wheel, isolated install,
database/workspace and generated setuptools output were removed after analysis.
