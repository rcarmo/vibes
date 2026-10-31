# Candidate Settings components against real Python routes

The Keychain and Environment components from fixtures-vibes `0259e9a` passed a
bounded headless Chromium probe against the Python Settings routes on 28 October
2026. Runtime base was `c7ec5c4` plus the Settings compatibility patch. Consumer
pin `4259e82` was not changed; nothing was deployed or published.

## Isolated host

A disposable loopback aiohttp service at `127.0.0.1:38508` registered the real
Settings handlers and SQLite store. Its home/workspace/database/key were owned
scratch; inherited environment was cleared and only synthetic credentials used.
The candidate's two components and exact `api.ts` Settings helper block were
bundled outside the shared repository with installed Preact/HTM. Mounting did not
change frontend source, selectors or capability claims.

The initial mount identified real response-contract mismatches: keychain expects
`ok`, top-level revealed secret/username, password-challenge boolean and camel-case
metadata; environment expects refreshed snapshots, `overridden`, counts and
`{name,clear:true}`. Backend compatibility fields preserve existing snake-case and
nested responses. User/agent note fields are now persisted in schema 12 rather
than silently dropped. Native note persistence, metadata aliases, clear variants
and invalid note/input handling have regression tests.

Harness-only errors (TypeScript helper extraction, old selector assumptions) were
fixed before the final two passing runs. A failed initial probe inherited server
environment names; subsequent hosts scrubbed their environment. The current
Environment API intentionally exposes inherited values to the trusted single
user, so isolated synthetic environment is mandatory for such diagnostics.

## Passing interactions

- Add a named secret; list responses and collapsed UI contain no secret value.
- Reveal gets 401 with `needs_master_password`; entering the synthetic password
  reveals only that entry. Hide removes its displayed secret.
- Add an environment override, reload, edit it and clear it through the actual
  shared API helper's `clear:true` request.
- Browser reload preserves the keychain entry and environment override while
  returning the secret to hidden state.
- Keychain variables and private keychain configuration do not appear in the
  Environment component.
- Confirmed deletion removes the keychain row. No page exceptions occurred.

These checks cover actual candidate UI handlers, API serialisation and Python
storage. They do not establish full application boot/authentication, the Settings
dialog shell, session changes, six viewport/browser projects, shell invocation by
a live model, clipboard permission, FFI integration or notes editing/reveal in
all UI states. Backend reconnect tests cover note persistence independently.

Host, database, keys, copied components, bundles, probe scripts and logs were
removed after analysis. Only this record is retained.
