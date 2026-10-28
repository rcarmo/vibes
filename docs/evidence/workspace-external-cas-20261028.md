# External-writer revision boundary

The workspace conditional-save endpoint detects changes read before validation,
but cannot provide atomic filesystem compare-and-swap against an uncooperative
external writer. This is an unresolved acceptance limit; no save behaviour or
frontend contract was weakened.

## Reproduction

`tests/test_workspace_revision_boundary.py` injects an independent Python process
after the backend reads the current content revision and before its separate
pathname write. Two cases change the same inode and replace the pathname with a
new inode. Both external writes complete, then the backend returns 200 and writes
the local draft. These tests intentionally pass by recording today's limitation;
they do not pass an external-writer CAS acceptance gate. The 59-test workspace
boundary/routes gate passed in 2.07 seconds. The follow-up full Python regression
passed 1,083 tests with 13 existing skips in 44.69 seconds using the pinned SDK
and unchanged shared assets. The new test passes Ruff and diff checks pass. No
provider, real workspace file or shared UI was involved.

The current synchronous comparison/write tail has no await, so requests in one
application event loop cannot interleave there. There is no process-local file
write lock. This does not serialise threads, multiple workers or external tools.

## Why a rename or lock is insufficient

Portable filesystem overwrite APIs have no expected-content/inode/generation
predicate. An advisory lock only serialises participating writers. Atomic rename
or `os.replace` provides complete-file name replacement, but can overwrite a
new external edit just before commit. Linux exchange/no-replace variants provide
unconditional swap or create-if-absent, not replacement conditional on revision.
A second content check only moves the race. Safe descriptor opening and fsync
address other safety/durability concerns, not conditional commit.

Scratch staging can also cross filesystems (`EXDEV`); copying as fallback is not
atomic. Staging in the source directory conflicts with this project's temp policy.
Inode replacement would change hardlink semantics compared with today's in-place
write. Symlink/path-component race hardening is a separate policy-sensitive task;
pathname containment alone does not establish hostile-local-writer isolation.

## Decision needed

True CAS requires a versioned authoritative store whose write API accepts the
observed revision, and all writers must use that authority. A narrower cooperative
writer protocol could serialise compliant writers, but requires an explicit
contract, portable coordination authority and scope. Neither prevents an external
writer that ignores it. Refusing every save would fail closed but would remove
working save behaviour and needs explicit approval.

The backend owner can implement an approved storage/cooperative protocol after
Rui selects the required guarantee. Until then, retain current revision conflict
detection and disclose the external-writer limitation. Do not mark revision-safe
full-app acceptance complete based on these boundary tests. Compiled-client,
shared pin/profile adoption and frontend ownership decisions are independent.
Disposable subprocess files and test scratch are removed after the gate; concise
results and regression source remain.
