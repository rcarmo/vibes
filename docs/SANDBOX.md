# Native OS Sandbox Abstraction for Agent Subprocesses

## Status

This document describes a proposed sandbox abstraction for Vibes agent subprocesses. It is an implementation plan, not a guarantee that sandboxing is currently enforced.

The design is intentionally conservative: sandbox policies must be enforced by the selected platform backend or the run must fail closed.

## Goals

Provide an internal Go library that can spawn agent subprocesses with native OS sandboxing primitives, giving them:

- read access only to explicitly approved system, toolchain and project paths
- write access only to approved workspace/cache/output paths
- explicit environment variable allowlisting
- optional network denial
- optional process/resource limits
- clear per-platform capability reporting
- fail-closed behavior when a requested policy cannot be enforced

The primary initial target is sandboxing ACP-like agent subprocesses launched by Vibes.

## Non-goals

- Do not promise identical security semantics across Linux, macOS and Windows.
- Do not silently degrade to a weaker sandbox.
- Do not expose the user's whole home directory by default.
- Do not rely on containers or VMs for the first version.
- Do not attempt to sandbox in-process code.
- Do not make sandboxing mandatory until provider compatibility is understood.

Container, VM and remote-execution backends may be added later as separate sandbox backends.

## Threat model

AI agents can leak sensitive data if they can read it and then send it over the network, write it into project files, or include it in generated output.

Read-only access is therefore still sensitive. Risky locations include:

- `~/.ssh`
- `~/.gnupg`
- `~/.aws`
- `~/.azure`
- `~/.config/gh`
- `~/.config/gcloud`
- browser profiles
- password/keychain stores
- private notes
- `.env` files
- editor/session state
- shell history
- local database files

The preferred model is an allowlist:

- allow read access to required toolchain paths
- allow read/write access to the active workspace
- allow read/write access to explicit cache/temp/output directories
- deny or omit sensitive home paths
- optionally deny network access
- clear the inherited environment by default

## Design principle

The abstraction should not be "the same sandbox everywhere".

It should be:

```text
Express desired policy → ask native backend if it can enforce it → run only if yes.
```

A backend must fail closed when it cannot enforce a requested policy.

## Proposed package layout

Initial implementation should live under `internal/sandbox` until the API stabilizes:

```text
internal/sandbox/
  sandbox.go              # public package API
  policy.go               # policy and mount types
  capabilities.go         # backend capability model
  errors.go               # typed policy/capability errors

  run_linux.go            # bubblewrap backend
  run_darwin.go           # sandbox-exec backend or explicit unsupported behavior
  run_windows.go          # unsupported/experimental backend

  internal/
    bwrap/                # bubblewrap argv generation
    sbpl/                 # macOS Seatbelt profile generation
    shellquote/           # diagnostic rendering only; no shell execution
```

If the abstraction proves generally useful, it can later become a standalone module.

## Public API sketch

The API should support both short-lived commands and long-lived agent subprocesses. ACP providers in particular require streaming stdin/stdout/stderr and process lifecycle control, so a simple `Run(command, args)` API is not enough.

```go
package sandbox

import (
    "context"
    "io"
    "os"
)

type FSMode string

const (
    ReadOnly  FSMode = "ro"
    ReadWrite FSMode = "rw"
)

type NetworkMode string

const (
    NetworkDefault  NetworkMode = "default"  // backend default, normally host network
    NetworkDeny     NetworkMode = "deny"     // no network if backend can enforce it
    NetworkLoopback NetworkMode = "loopback" // future: loopback only
)

type EnvMode string

const (
    EnvClear     EnvMode = "clear"      // no inherited env except explicit Env
    EnvAllowlist EnvMode = "allowlist"  // inherit only EnvAllow entries plus Env overrides
    EnvInherit   EnvMode = "inherit"    // unsafe; for compatibility only
)

type ProcMode string

const (
    ProcNone ProcMode = "none"
    ProcRead ProcMode = "read"
)

type DevMode string

const (
    DevMinimal DevMode = "minimal" // null, zero, random, urandom, tty as appropriate
    DevNone    DevMode = "none"
    DevHost    DevMode = "host"    // unsafe; compatibility only
)

type Mount struct {
    HostPath  string
    GuestPath string
    Mode      FSMode

    // Required means policy validation fails if the host path is missing.
    Required bool

    // FollowSymlinks controls whether HostPath is canonicalized through symlinks
    // before being mounted. The safe default should be false or explicit
    // canonicalization with escape checks.
    FollowSymlinks bool
}

type Limits struct {
    MaxProcesses   int
    MaxOpenFiles   int
    MemoryBytes    int64
    CPUTimeSeconds int
    WallTimeSeconds int
}

type Policy struct {
    Mounts []Mount

    Workdir string

    EnvMode  EnvMode
    Env      map[string]string
    EnvAllow []string

    Network NetworkMode

    Proc ProcMode
    Dev  DevMode

    Tmpfs []string

    Limits Limits

    // DenyHomeSecrets is a helper mode for platforms that support explicit
    // deny rules. It must not be treated as sufficient isolation by itself.
    DenyHomeSecrets bool
}

type Capabilities struct {
    ReadOnlyRoot              bool
    ReadOnlyBindMounts        bool
    ReadWriteBindMounts       bool
    PathRemapping             bool
    Tmpfs                     bool
    DenyNetwork               bool
    LoopbackOnlyNetwork       bool
    PIDIsolation              bool
    IPCIsolation              bool
    ProcessLimits             bool
    MemoryLimits              bool
    CPUTimeLimits             bool
    StrongFilesystemIsolation bool
    Seccomp                   bool
    Landlock                  bool
    Seatbelt                  bool
    AppContainer              bool
    JobObject                 bool
}

type DiagnosticSeverity string

const (
    Info    DiagnosticSeverity = "info"
    Warning DiagnosticSeverity = "warning"
    Error   DiagnosticSeverity = "error"
)

type Diagnostic struct {
    Code     string
    Severity DiagnosticSeverity
    Message  string
}

type Command struct {
    Path string
    Args []string

    // Env is merged according to Policy.EnvMode and Policy.Env/EnvAllow.
    Env map[string]string

    // Dir is the command's requested working directory before sandbox remapping.
    // Policy.Workdir is authoritative inside the sandbox.
    Dir string

    Stdin  io.Reader
    Stdout io.Writer
    Stderr io.Writer
}

type Result struct {
    ExitCode int
    Signal   os.Signal
}

type Process interface {
    Wait() (Result, error)
    Kill() error
    Signal(os.Signal) error
}

type Runner interface {
    Name() string
    Capabilities() Capabilities
    Explain(policy Policy) []Diagnostic
    CanEnforce(policy Policy) error
    Start(ctx context.Context, command Command, policy Policy) (Process, error)
    Run(ctx context.Context, command Command, policy Policy) (Result, error)
}

func NativeRunner() Runner
func Run(ctx context.Context, command Command, policy Policy) (Result, error)
```

## Policy validation

`CanEnforce` must reject policies that the backend cannot enforce.

Examples:

- path remapping requested on a backend without path remapping
- network denial requested without network isolation support
- write allowlist requested without filesystem enforcement
- missing required host mount path
- workdir outside the sandbox-visible filesystem
- environment inheritance requested when runner configuration forbids it
- read/write mount nested inside a read-only mount in a way the backend cannot represent
- unsupported device/proc mode
- memory limits requested on a backend that only supports CPU limits

Validation should produce actionable diagnostics.

Example:

```go
runner := sandbox.NativeRunner()
if err := runner.CanEnforce(policy); err != nil {
    return fmt.Errorf("sandbox policy cannot be enforced: %w", err)
}
```

## Environment model

The inherited environment is a major credential leak source. Sensitive variables include:

- `GITHUB_TOKEN`
- `GH_TOKEN`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_SESSION_TOKEN`
- `AZURE_*`
- `GOOGLE_APPLICATION_CREDENTIALS`
- `SSH_AUTH_SOCK`
- `GIT_ASKPASS`
- `HTTP_PROXY`
- `HTTPS_PROXY`

Default behavior should be `EnvClear` or `EnvAllowlist`, not `EnvInherit`.

Recommended safe allowlist for many local commands:

```text
PATH
HOME                # points to a sandbox home, not the real home
TMPDIR
LANG
LC_ALL
TERM
```

Provider-specific credentials should be passed only when explicitly required and reflected in diagnostics.

## Filesystem semantics

The implementation must define the following clearly:

- host paths are absolute
- guest paths are absolute when path remapping is supported
- missing required mounts fail validation
- symlink handling is explicit
- workdir must be visible inside the sandbox
- writable paths must be explicit
- no implicit whole-home mount
- `/tmp` should be tmpfs or an explicit writable mount
- `/proc` and `/dev` exposure should be minimal and policy-driven

For Linux `bubblewrap`, the command generator should prefer explicit mounts only.

For macOS Seatbelt, path remapping is not available. Policies requiring remapping must be rejected.

## Linux backend

Linux is the strongest first target and should be the first fully implemented backend.

Recommended v1 backend: `bubblewrap`.

Linux v1 should support:

- explicit read-only bind mounts with `--ro-bind`
- explicit read/write bind mounts with `--bind`
- guest path remapping
- synthetic writable home via `--tmpfs` or explicit bind mount
- private `/tmp` via `--tmpfs /tmp`
- minimal `/proc` via `--proc /proc` when requested
- minimal `/dev` via `--dev /dev` when requested
- optional network denial via `--unshare-net`
- PID and IPC isolation via `--unshare-pid` and `--unshare-ipc`
- context cancellation and subprocess cleanup
- environment allowlisting before process launch

Example mapping:

```bash
bwrap \
  --unshare-user \
  --unshare-pid \
  --unshare-ipc \
  --unshare-net \
  --ro-bind /usr /usr \
  --ro-bind /bin /bin \
  --ro-bind /lib /lib \
  --ro-bind /lib64 /lib64 \
  --bind /home/me/project /workspace \
  --tmpfs /tmp \
  --proc /proc \
  --dev /dev \
  --chdir /workspace \
  -- go test ./...
```

Capabilities:

- read-only bind mounts: yes
- read/write bind mounts: yes
- path remapping: yes
- network denial: yes via network namespace
- process isolation: yes via PID namespace
- IPC isolation: yes
- filesystem isolation: strong when policy is explicit
- resource limits: possible via rlimits and/or cgroups
- seccomp: optional defense in depth
- Landlock: optional defense in depth

Useful packages/tools:

- `bubblewrap`
- `golang.org/x/sys/unix`
- `github.com/seccomp/libseccomp-golang`
- `github.com/landlock-lsm/go-landlock`
- cgroup v2 support for stronger memory/process limits

A later pure-Go backend can use user namespaces, mount namespaces, bind mounts, `pivot_root`, seccomp and Landlock directly. That should not be v1 unless there is a strong reason to avoid `bubblewrap`.

## macOS backend

macOS should be covered in v1 with conservative capability reporting, even if it cannot enforce the same policies as Linux.

The practical native mechanism is Seatbelt profiles through `/usr/bin/sandbox-exec`.

Important caveats:

- `sandbox-exec` exists and works but is not a modern public API Apple actively promotes.
- it denies operations but does not create a filesystem namespace
- path remapping is generally not supported
- many CLI tools need extra Mach/service permissions
- network-denial rules must be tested carefully
- filesystem isolation is medium, not Linux-style strong isolation

A strict profile should be allowlist-based, not broad read plus denylist.

Example direction:

```scheme
(version 1)

(deny default)

;; Basic process functionality. This will likely require iteration.
(allow process*)
(allow sysctl-read)
(allow mach-lookup)

;; Read allowlist.
(allow file-read*
  (subpath "/Users/me/project")
  (subpath "/usr/bin")
  (subpath "/bin")
  (subpath "/usr/lib")
  (subpath "/System/Library"))

;; Write allowlist.
(allow file-write*
  (subpath "/Users/me/project")
  (subpath "/Users/me/agent-tmp"))
```

Execution from Go:

```go
cmd := exec.CommandContext(
    ctx,
    "/usr/bin/sandbox-exec",
    "-p",
    profile,
    command.Path,
)
cmd.Args = append(cmd.Args, command.Args...)
```

Capabilities should be conservative:

- read allowlist: yes, policy-based
- write allowlist: yes
- read-only bind mounts: no, because there is no mount namespace
- read/write bind mounts: no, because there is no mount namespace
- path remapping: no
- synthetic sandbox home: only by choosing a real temporary directory and allowing it
- private `/tmp`: only by setting `TMPDIR` to an allowed temporary directory
- network denial: possible, but must be proven by integration tests before advertising `DenyNetwork`
- filesystem isolation: medium
- process/resource limits: limited, combine with rlimits where practical

Policies that rely on guest path remapping, bind mounts, private mount namespaces or Linux-style filesystem isolation must fail on macOS.

A macOS v1 backend is still useful because it can enforce deny-by-default file read/write profiles for commands that do not need path remapping. Its diagnostics must clearly say when it is enforcing a Seatbelt policy rather than a namespace sandbox.

## Windows backend

Windows is the hardest native target. There is no simple equivalent of Linux read-only and read/write bind mounts for arbitrary subprocesses.

Possible approaches:

### Restricted token + Job Object

Use:

- `CreateRestrictedToken`
- low integrity level
- disabled privileges
- Job Objects for process and resource limits
- process mitigation policies

This constrains process behavior but does not provide clean per-path filesystem policy by itself.

### Temporary local user

Run the agent as a dedicated low-privilege user:

- grant write ACLs only to approved directories
- rely on Windows ACLs for filesystem access
- deny access to sensitive profile paths

This is practical but operationally awkward.

### AppContainer

Use AppContainer profiles:

- create an AppContainer SID
- launch the subprocess inside the AppContainer
- ACL approved directories for that AppContainer SID

This is more sandbox-like but inconvenient for arbitrary CLI tools. The default model is closer to "almost no access unless granted".

### Windows Sandbox, containers or Hyper-V

These provide stronger isolation but are heavier and no longer simple native subprocess spawning.

Recommended v1 behavior:

- report Windows as unsupported for strict policies, or
- provide an experimental backend with explicit limited capabilities

Do not silently pretend Windows can enforce Linux-like policies.

## Vibes integration plan

The initial Vibes integration should be opt-in and diagnostic-first.

Potential environment/configuration:

```text
VIBES_AGENT_SANDBOX=off|strict
VIBES_AGENT_SANDBOX_NETWORK=allow|deny
VIBES_AGENT_SANDBOX_WORKSPACE=/path/to/workspace
```

Potential provider diagnostics:

```json
{
  "sandbox": {
    "enabled": true,
    "available": true,
    "backend": "bubblewrap",
    "network": "deny",
    "status": "ready"
  }
}
```

Sandbox state should appear in `/agent/providers` diagnostics rather than the compose box.

### Likely integration points

- ACP subprocess launch path under `internal/agent/acp/`
- provider registry diagnostics under `internal/agent/`
- provider route payloads under `internal/routes/agents.go`
- configuration under `internal/config/`

### Provider compatibility

Network denial cannot be universal:

- Copilot ACP may require network and authentication
- Codex-compatible ACP providers may require API access
- Pi RPC may connect to a local Pi service

Sandboxing should be represented as provider metadata and configuration, not as an assumed capability of all providers.

## Default Linux policy example

A conservative Linux policy for a workspace-oriented agent might look like:

```go
policy := sandbox.Policy{
    Mounts: []sandbox.Mount{
        {HostPath: "/usr", GuestPath: "/usr", Mode: sandbox.ReadOnly, Required: true},
        {HostPath: "/bin", GuestPath: "/bin", Mode: sandbox.ReadOnly, Required: true},
        {HostPath: "/lib", GuestPath: "/lib", Mode: sandbox.ReadOnly},
        {HostPath: "/lib64", GuestPath: "/lib64", Mode: sandbox.ReadOnly},
        {HostPath: projectRoot, GuestPath: "/workspace", Mode: sandbox.ReadWrite, Required: true},
        {HostPath: cacheDir, GuestPath: "/home/sandbox/.cache", Mode: sandbox.ReadWrite},
    },
    Workdir: "/workspace",
    EnvMode: sandbox.EnvAllowlist,
    Env: map[string]string{
        "HOME": "/home/sandbox",
        "TMPDIR": "/tmp",
    },
    EnvAllow: []string{"PATH", "LANG", "LC_ALL", "TERM"},
    Network: sandbox.NetworkDeny,
    Proc: sandbox.ProcRead,
    Dev: sandbox.DevMinimal,
    Tmpfs: []string{"/tmp", "/home/sandbox"},
}
```

The exact toolchain mounts should be built by explicit profile helpers and shown in diagnostics.

## Toolchain profile helpers

Toolchains often need more than `/usr` and `/bin`:

- `/nix/store` for Nix systems
- `/usr/local`
- `/opt`
- CA certificates
- timezone/locale files
- Go module/build cache
- npm/Bun cache
- Cargo registry/git cache
- Python/pip cache

The sandbox package can provide inspectable helpers:

```go
func BaseLinuxToolchainMounts() []Mount
func GoToolchainMounts(projectRoot string) []Mount
func NodeToolchainMounts(projectRoot string) []Mount
func RustToolchainMounts(projectRoot string) []Mount
```

These helpers must not silently mount broad home directories.

## Linux and macOS v1 acceptance criteria

A first implementation should be considered complete only when both Linux and macOS behavior is explicit and tested.

### Linux v1 acceptance

- `NativeRunner()` selects the `bubblewrap` runner when `bwrap` is available.
- `Capabilities()` reports bind mounts, path remapping, tmpfs, PID/IPC isolation and network denial accurately.
- `CanEnforce` accepts policies using read-only/read-write mounts, remapped guest paths, tmpfs and network denial.
- `CanEnforce` rejects missing required mounts and invalid workdirs.
- generated `bwrap` argv is covered by unit tests.
- integration tests verify allowed reads, denied omitted reads, allowed writes, denied outside writes and denied network when enabled.

### macOS v1 acceptance

- `NativeRunner()` selects the Seatbelt runner when `/usr/bin/sandbox-exec` is available.
- `Capabilities()` reports no bind mounts and no path remapping.
- `CanEnforce` accepts same-path file allowlist policies that can be represented as Seatbelt rules.
- `CanEnforce` rejects any policy requiring guest path remapping, bind mounts, private mount namespaces or Linux-style tmpfs behavior.
- generated Seatbelt profiles are covered by unit tests.
- integration tests verify allowed reads, denied omitted reads, allowed writes and denied outside writes.
- network denial is reported only after a dedicated integration test proves the profile blocks outbound network access.

## Testing strategy

Start with tests that do not require privileged sandbox execution.

### Unit tests

- policy validation
- capability matching
- path canonicalization
- missing required mount handling
- environment assembly
- `bubblewrap` argv generation
- macOS Seatbelt profile generation
- Windows strict-policy rejection

### Linux integration tests

Run only when `bubblewrap` is available:

- read allowed file succeeds
- read omitted sensitive path fails
- write allowed workspace file succeeds
- write outside allowed paths fails
- network denial blocks outbound access
- workdir is remapped correctly
- environment variables are cleared/allowlisted

### Vibes integration tests

- provider descriptor reports sandbox diagnostics
- unavailable sandbox marks provider diagnostics without crashing server
- strict sandbox policy failure prevents subprocess launch
- ACP subprocess stdio still works when sandboxed

## Implementation phases

### Phase 1: internal package and Linux argv generation

- add `internal/sandbox`
- implement policy and capabilities
- implement Linux `bubblewrap` command construction
- implement `CanEnforce`
- implement unsupported Darwin/Windows stubs or conservative capability reporters
- add unit tests

### Phase 2: Linux runner

- implement `Start` and `Run`
- wire stdio
- support context cancellation
- support basic rlimits
- add optional integration tests behind availability checks

### Phase 3: Vibes diagnostics

- add sandbox config
- expose sandbox status in provider descriptors
- do not sandbox providers by default yet

### Phase 4: opt-in ACP sandboxing

- apply sandbox runner to ACP subprocess launch when enabled
- validate provider-specific network needs
- add failure diagnostics

### Phase 5: macOS backend

- implement Seatbelt profile generation
- reject unsupported remapping policies
- test common CLI tools

### Phase 6: hardening

- seccomp/Landlock on Linux
- cgroup limits
- loopback-only networking
- richer toolchain profiles
- optional Windows AppContainer research

## Open questions

- Should sandboxing default to off or diagnostics-only for existing users?
- Should Vibes ship preset policies per backend family?
- How should provider auth tokens be passed when network is enabled?
- Should sandboxed agents use a synthetic home directory by default?
- How should local Unix sockets be modeled?
- Should Pi RPC be sandboxed, or only ACP child processes?
- Should path policy be configured via environment, JSON config, or UI?

## Recommendation

Implement Linux `bubblewrap` support first, as an internal package with strong tests and no automatic provider integration. Then surface sandbox capabilities in provider diagnostics. Only after that should Vibes add opt-in ACP subprocess sandboxing.

The key invariant is: if Vibes says a provider subprocess is sandboxed, the selected platform backend must actually enforce the requested policy.
