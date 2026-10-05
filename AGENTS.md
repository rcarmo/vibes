# Vibes Python

## Cache and scratch paths

The canonical disposable root is `/workspace/tmp/vibes/`:

- `cache/<tool>/` for Python bytecode, pytest, pip, uv, Bun, npm and XDG caches.
- `build/` for disposable build output.
- `runs/<purpose>/<run-id>/` for isolated scratch and test filesystem roots.

The Makefile exports `TMPDIR`, `TMP`, `TEMP`, `XDG_CACHE_HOME`,
`PIP_CACHE_DIR`, `UV_CACHE_DIR`, `BUN_INSTALL_CACHE_DIR`, `npm_config_cache`,
`PYTHONPYCACHEPREFIX` and pytest basetemp/cache options. Set `VIBES_RUN_ID`
explicitly for reproducible run receipts. Direct commands must use the same
paths. Never use bare `/tmp`, home caches or ad-hoc top-level temporary paths.

Retained profiles, logs, receipts and datasets are evidence, not disposable
scratch. Keep publication evidence under `docs/evidence/`; preserve external
historical evidence until explicitly migrated. Cleanup may remove only confirmed
inactive disposable paths beneath `/workspace/tmp/vibes/`. Never delete another
project's root, retained evidence or files used by active jobs. The existing
`clean` target removes local Python bytecode/test cache only and does not delete
the project scratch root or evidence.

## Ownership

Backend APIs, adapters and runtime profile lifecycle belong to the Vibes agent.
Frontend source, builds, tests, selectors and frontend capability claims belong
to the fixtures-vibes owner. `src/vibes/static` links into the pinned shared UI;
do not edit it locally. Coordinate cache routing in shared UI/fixture helpers
with that owner. Go work is cancelled; preserve its branch and worktree.

Use git merge, never rebase. Publish only with the shared workspace Makefile
helper and an explicit keychain environment reference. Preserve unrelated work.
