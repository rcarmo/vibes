# Classic boot and session adapters

The Python runtime exposes auth-free boot policy, a small runtime configuration
projection and session registry routes for the candidate Classic client. The
legacy `/sessions` routes retain their field names and default archive filter.
These routes do not switch static assets or the consumer fixture pin.

## Authentication and configuration

GET `/api/auth/status` and `/api/auth/policy` return the candidate single-user,
auth-free policy only when the installed auth middleware uses its default
allow-all callback. Browser login, TOTP, passkeys and setup are unavailable.
A custom auth callback still gates every protected route. If that callback
allows a request, these policy routes return 501 because the adapter cannot
represent its external authentication policy. An absent middleware marker also
fails closed. No token, login, enrolment or logout handler is fabricated.

GET `/api/runtime/config` publishes `assistant_name`, the supported `web` agent
and its allowlisted backend (`pi`, `acp`, `copilot-ffi`, or null for unknown
configuration). Models, provider and thinking are unavailable until the separate
session model adapter supplies authoritative state. The endpoint does not expose
raw configuration, launch commands, avatar URLs, environment values or secrets.
All successful boot responses have `Cache-Control: no-store`; existing origin,
security and FFI loopback middleware still apply.

## Session registry

GET `/api/sessions` includes archived sessions by default so the picker can
restore them. `include_archived=true|false` is its only supported query option.
GET `/api/sessions/{s}` returns one session with persisted activity counts.
Unknown sessions return 404. Unsupported query fields return 400.

Each projection preserves legacy metadata and adds:

- `title` from durable `name`, and `parent_session_id` from durable `parent_id`;
- `scope.agent_id: web`, with no arbitrary agent or branch semantics;
- `state.status: idle|queued|running`, `state.queue_count`, `state.pinned`,
  `state.archived_at` and `state.archived_at_source`;
- `capabilities.fork: false`.

POST `/api/sessions` accepts `{title,agent_id?}` for a new empty root session.
Only `web` and the compatibility spelling `default` are accepted agent IDs.
PATCH `/api/sessions/{s}` accepts one exact action shape:

| Action | Body |
| --- | --- |
| Rename | `{action: rename, title}` |
| Pin/unpin | `{action: pin, pinned: boolean}` |
| Archive | `{action: archive}` |
| Restore | `{action: restore}` |

Unknown fields, null names/booleans and unsupported actions return 400. Mutations
use the existing store and emit `sessions_changed` only after a successful write.
Readback occurs under the write lock; a target deleted before mutation returns
404 instead of false success. The default session cannot be archived. Archive
rejects active turns and live descendants; restore requires unarchived ancestors.
Child creation and archive validation use the same write lock. These controls
preserve hierarchy without implicitly archiving or restoring a subtree.

POST `/api/sessions/{s}/fork` returns 501 for an existing session, or 404 for a
missing session. Metadata-only child creation does not copy a transcript or
branch provider state. No successful fork acknowledgement is returned.

## Archive migration

Schema 14 adds `chat_sessions.archived_at` and `archived_at_source`. New archive
actions persist their time with source `mutation`; repeat archive keeps the same
time and restore clears it. For legacy archived rows, migration records the
observation time with source `migration-observed`. The original archive time is
unknown. DDL, data initialisation and schema-version publication share an explicit
SQLite transaction. Column checks recover partially applied upgrades without
overwriting an already recorded observation time.

## Verification

The full Python suite passed 1,023 tests with 13 existing skips in 40.94 seconds,
using the pinned optional SDK and unchanged shared assets. Changed backend modules
and new tests pass Ruff; `git diff --check` passes. Tests cover default/external
auth, origin rejection, configuration allowlists, legacy response preservation,
real persisted activity, strict mutations, missing/fork errors, archive ancestry,
new/reopened/partially migrated databases and deletion during mutation.

The candidate `0259e9a` `parseAuthPolicy` and `sessionPickerAgents` functions also
passed against the real HTTP routes with a disposable SQLite database. The picker
recognised pinned, archived/restorable and active child sessions. The first probe
assertion used incorrect picker output field names; a corrected fresh-database
run passed. No provider, browser application, shared asset adoption or release
acceptance was exercised. Copied candidate helper modules, host, synthetic DB,
optional SDK, temporary asset link, test scratch and logs are removed after use.

Session timeline/search/delete, queue and model controls, canonical media,
compiled client boot, reconnect, six-project acceptance and pre-release profiling
still require work. Authentication deployment needs a separate policy contract
if authentication is introduced.
