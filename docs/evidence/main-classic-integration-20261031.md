# Python main integration — 2026-10-31

All Python work from `feat/python-keychain-environment` was merged into `main`
in `379fa61`. Active development now uses `/workspace/projects/vibes` on main.
The existing local `tests/test_config.py` change and three untracked probe files
were preserved; Go worktrees were untouched. The fixture pin stays at `2fc49ef`
and the consumer serves `ui/classic/static`.

## Implemented on main

- `/api/system-metrics` uses the existing bounded OS metrics reader.
- `/api/quick-actions` returns empty configured action/command lists without
  starting an agent or inventing a native command catalogue.
- Workspace tree, raw, stat, delete, rename, move and upload have Classic aliases.
  Tree replies return the node directly as required by the current adapter.
  Stat validates workspace containment and returns bounded text revisions.
- `/sse/topics` accepts `runtime.tool` with an existing session selector. Bounded
  subscriptions receive only owner-verified events, and disconnect removes them.
  Actual live native codemode event production was not verified.
- Schema 16 adds persistent instance settings. Identity mutations use revision
  CAS under the database transaction lock and activate at startup. General's
  1–1024 MiB upload limit persists and is captured/enforced for each upload.
  No maxIterations property is exposed: native loop control is not implemented.
- Session media collection GET returns only the latest 100 media records with
  matching persisted ownership; unexpected selectors are rejected.

Provider credential management and native compaction policy remain unavailable:
GET describes unavailable state, mutation returns 501. Workspace full-text index
GET describes unavailable/failed state and reindex returns 501. These are explicit
implementation gaps, not completed native features.

## Verification

Focused boot/workspace/SSE tests passed 85 tests. Settings/media/database gate
passed 96 tests; startup/settings follow-up gate passed 43 tests. Final main
regression passed 1,123 tests with 13 skips in 54.32 seconds using optional SDK
1.0.14. Changed modules and new tests passed Ruff; diff checks passed.

Compiled Chromium boot used an isolated database/workspace and disabled agent
startup. Composer and Plan mounted; OS metrics displayed; opening the workspace
panel loaded its tree and the test folder. No JavaScript errors or failed HTTP
requests occurred. The earlier five-second loading observation was from a closed
workspace panel, so it was not evidence of a backend loading failure.

The current GET contract probe passed boot and all listed GET routes except
`/pdf-viewer/source`. Empty/unavailable API responses do not establish complete
Settings or native capability acceptance. Full consumer/browser compliance,
provider/native verification, filesystem external-writer CAS, remaining adapter
features and pre-release performance verification remain open.

No provider calls, push, deployment, shared UI source edits or Go changes. Raw
probe scripts, SDK, logs, database and test scratch were deleted after analysis.
