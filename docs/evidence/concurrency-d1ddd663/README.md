# Python concurrent sessions

`@ux-chat-lifecycle-007` and `@ux-chat-lifecycle-009` passed in all six Chromium/WebKit phone, tablet and desktop projects on 2026-10-04. The run used fixture revision `d1ddd663b432b3a6bc4876df12084c1c86797028`, production Vibes Pi and the fixture model: 12 passed, zero skips, zero retries, 1.7 minutes.

The runtime changes give each chat its own Pi/ACP process, session selector, locks, current request, pending input requests and callback execution context. Dispatch locks, abort ownership, queued steering, status/model/context reads and loopback tool capabilities use the owning chat. Shutdown visits every process. ACP throttling is per process.

`playwright.json` contains the structured results; `run.txt` contains the per-project outcome list. The profile's historical runtime version predates this working-tree change; these results were generated from the concurrency draft atop `e171229`, not from that profile version or published main.

Focused Python verification passed 349 tests across registry, Pi/ACP clients and protocol/usage, agent routes, aborts, durable dispatch, cleanup, loopback messages, sessions, attachments and plan transport (19.74 seconds). Real subprocess tests verify distinct PIDs and independent shutdown. ACP protocol setup in those subprocess tests is synthetic. Live-provider acceptance and Go concurrency have not been tested.

Run the browser checks from `references/fixtures-vibes`:

```sh
FIXTURES_PROFILE="$PWD/../../tests/fixtures-vibes/profile.json" \
VIBES_PYTHON=/workspace/projects/vibes/.venv/bin/python \
bun x playwright test -c suite/playwright.config.ts \
  suite/specs/chat-lifecycle.spec.ts --grep 'ux-chat-lifecycle-(007|009)'
```

## Abort and queue checks

The focused suite includes exact-task Pi abort and exact-request ACP abort checks: a foreign chat or stale owner cannot cancel the selected runtime. Agent routes use the persisted root to scope active turns and queued steering. Durable dispatch tests retain pending work on pre-admission failure, preserve attachments and FIFO identity, and exclude uncertain work from replay. The combined 349-test result includes the complete abort and durable-dispatch modules.

The browser lifecycle run exercises the Pi runtime. ACP's offline checks cover owner-local state and dispatcher overlap; an ACP provider browser run has not been performed.

## Baseline cluster totals

`baseline-clusters.json` extracts all outcomes in the five target specs from the preserved `ccbd1fd` / `053ad57` full run. These are whole-spec totals, distinct from the narrower gate-not-reached counts 45/12/27/8/37 reported during triage.

| Spec | Passed | Failed | Skipped |
|---|---:|---:|---:|
| shared-queue | 7 | 47 | 0 |
| queue-steer | 0 | 12 | 0 |
| thoughts-panel | 0 | 30 | 0 |
| shared-reconnect | 0 | 12 | 0 |
| compaction | 1 | 53 | 0 |

The published-commit rerun has not run. These counts do not attribute every failure to the former concurrency guard.
