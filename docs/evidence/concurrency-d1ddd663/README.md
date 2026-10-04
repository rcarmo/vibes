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
