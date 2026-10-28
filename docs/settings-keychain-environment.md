# Keychain and shell environment

Python stores keychain entries and environment overrides in SQLite schema 10.
Settings routes use the application's existing authentication and same-origin
middleware. They return `Cache-Control: no-store`, including errors. No frontend
files or fixture pins change in this implementation.

## Settings API

| Method and path | Request | Response |
| --- | --- | --- |
| GET `/api/settings/keychain` | — | `{entries: [{name, type, username, created_at, updated_at}]}`; no secrets |
| POST `/api/settings/keychain` | `{name, secret, username?, type?}` | 201 `{entry: {name, type, username}}`; upserts by name |
| DELETE `/api/settings/keychain` | `{name}` | 200 `{deleted: name}`; missing entry 404 |
| POST `/api/settings/keychain/reveal` | `{name, master_password?}` | `{entry: {name, type, username, secret}}`; missing entry 404 |
| GET `/api/settings/environment` | — | `{variables: [{name, value, override}]}` |
| POST `/api/settings/environment` | `{name, value}` | String value: 201 `{variable: {name, value, override: true}}`; null: 200 `{cleared: name}`; missing override 404 |

Types are `secret` (default), `token`, `password` and `basic`. Invalid input is
400. Protected reveal requires the configured master password; missing or wrong
password returns 401 `needs_master_password`. List operations never decrypt an
entry. UI confirmation and per-entry reveal state belong to the shared frontend.

## Storage and configuration

`cryptography` supplies ChaCha20-Poly1305 authenticated encryption with fresh
12-byte nonces. Without a configured master password, a random 32-byte installation
key lives beside the selected settings file as `keychain.key` (POSIX mode 0600).
`VIBES_KEYCHAIN_KEY_PATH` selects another path. Creation publishes a complete key
atomically; existing keys are never truncated. POSIX reads reject symlinks,
non-regular files, foreign ownership and group/world permissions.

Set `VIBES_KEYCHAIN_MASTER_PASSWORD` or the server setting
`keychain_master_password` before first use to select password mode. Scrypt derives
the encryption key using a database salt. The database contains no master
password. A stored encrypted key check rejects changed key configuration before
writing entries. Password/key rotation is not implemented: changing mode or
password requires an explicit future migration, not an ordinary settings edit.
Back up the database and its key together. Losing either key or password loses
access to the encrypted secrets.

The Environment API lists inherited values and saved overrides, excluding
keychain variables and the two private keychain configuration variables. This is
a trusted-user interface: inherited process values can contain deployment
credentials. Do not expose it to untrusted users or run the server with unrelated
secrets. Overrides are non-secret strings; use the keychain for credentials.

## Shell rules

`/shell`, `/bash` and the Pi `bash` adapter read overrides for every command.
Overrides survive database reconnects and apply without restarting Pi. Clearing
an override restores the inherited value. Keychain-derived variable names cannot
be added as environment overrides. Existing inherited values take precedence over
keychain injection.

Reference scanning is textual and case-sensitive for `$NAME`, `${NAME}`,
`$env:NAME` and `%NAME%`, including quoted text and comments. Only referenced
entries are decrypted. Existing identifier names retain case; other names replace
runs of `/`, `-` and `.` with `_`, remove invalid characters and uppercase the
result. Empty/digit-leading results are ignored. Collisions select the first
entry name in byte order.

`keychain:name` and the `:secret`, `:password`, `:token`, `:username` and `:user`
forms follow the shared Classic contract: literal substitution into shell source
before execution. Missing entries, missing usernames and unknown fields fail
before execution. **Prefer quoted variable expansion for credentials containing
shell syntax.** Literal placeholders can change shell syntax; they are not an
escaping mechanism. Prepared commands and injected values are never included in
adapter details or error responses. Commands that explicitly print credentials
will still return those credentials in their output.

`VIBES_SHELL_PATH` or server setting `shell_path` selects a configured POSIX shell.
Otherwise detection tries inherited `$SHELL`, `/bin/bash`, then bash on PATH.
Commands start in the workspace root. Python shell timeout/cancellation kills the
POSIX process group and reaps the shell; Pi uses its SDK's process lifecycle.
The private keychain configuration variables are removed from prepared shell
environments.

## Pi adapter boundary

The adapter POSTs `{command}` to `/internal/agent-tools/shell-prepare`. This route
requires loopback access, no browser Origin, an attachment bearer token and a
matching active session turn. It rechecks ownership after secret preparation.
The response contains the prepared command, environment, cwd and detected shell;
it is secret-bearing and must never be logged or persisted in tool results.
The adapter delegates execution and cancellation to Pi's `createBashTool`.

ACP's capability-scoped MCP server also advertises `bash`. It POSTs to
`/internal/agent-tools/shell`, which applies the same preparation and executes the
command server-side. The endpoint monitors ownership and caller disconnection,
cancels the process group on loss of either, and returns only stdout/exit code.
A real independent MCP subprocess roundtrip is tested; provider selection of this
tool over a provider's own shell requires live acceptance.

Pi and ACP subprocess environments omit the master-password and key-path
configuration variables, preventing bypass through child environment enumeration.

## Verification and limits

Development checks on base `86392e6`, Python 3.12.3:

- Storage, malformed-input, concurrent-key creation, wrong-password, environment,
  shell, ownership, database, Plan and workspace routes: 99 passed in 4.23s.
- Pi client, tool routes and session runtime: 42 passed in 0.25s.
- Shell/bash slash-command subset: 9 passed; configuration tests: 33 passed.
- Entire slash-command module: 86 passed, four theme/tint failures reproduced
  unchanged at base `86392e6` (expected partial UI events, actual complete events).
- Installed Pi SDK loaded all five adapter tools; controlled shell execution
  returned the expected environment value; abort cancelled a sleeping command.
  Existing Plan serialization regression: one Bun test passed.
- Ruff on changed Python backend/tests and `git diff --check` passed.

Follow-up checks: the expanded backend gate passed 107 tests in 5.98s, including
startup fallback and a real MCP subprocess shell roundtrip. Pi/ACP clients,
protocol, runtime, tool routes and MCP tests passed 134 tests in 17.26s. Python
shell execution retries candidates only for pre-start ENOENT/ENOEXEC failures;
configured shells, running commands and missing working directories never trigger
replay. Pi candidate startup fallback still belongs to the SDK execution path.

Browser Settings acceptance and live-provider execution are not established.
Windows detection branches exist but execution remains unaccepted; the Pi
adapter rejects non-POSIX shells. A combined
Python run including module-purging tests also exposed workspace test-isolation
failures; the 99-test gate and configuration/Pi/slash modules were run separately.
This was development verification, not pre-release profiling. Nothing was deployed.
