## Installing the Python version

These instructions are for `main`. The [Go branch][go] has its own build and deployment instructions; an old Go binary, container image or release tag is not a Python installation.

Python 3.12 on Linux is the tested installation path. Package metadata permits Python 3.10 and later, but that is not a claim that every interpreter/platform combination has been tested. The PTY terminal and descriptor-confined workspace reader require POSIX facilities; native Windows is not the verified server path. A browser on Windows, macOS, iOS or Android can connect to a server running elsewhere.

You need Git to install from this repository. Install and authenticate an ACP agent or Pi separately, under the account that will run Vibes. Check that its executable is on that account's `PATH`. Vibes does not install agents, choose their provider credentials or grant API access.

## Install without a checkout

```bash
python3 -m venv ~/.venvs/vibes
~/.venvs/vibes/bin/python -m pip install --upgrade "git+https://github.com/rcarmo/vibes.git@main"
~/.venvs/vibes/bin/vibes --help
```

On Debian/Ubuntu, install `python3-venv` and `git` with `sudo apt install python3-venv git` if needed. Do not install into the system Python with `sudo pip`.

An isolated tool installation with uv is an alternative:

```bash
uv tool install "git+https://github.com/rcarmo/vibes.git@main"
```

Use `uv tool update-shell` if the resulting `vibes` command is not on your `PATH`. Choose one installation method rather than keeping two different copies on the same path. The Python package contains browser bundles, fonts, vendored browser libraries, the messages MCP implementation and the Pi extension; Bun is only needed to rebuild the frontend.

## Choose the workspace and agent

The server's current directory is its workspace. Relative database and configuration paths resolve there too.

```bash
cd /path/to/your/project
VIBES_ACP_AGENT="copilot --acp" ~/.venvs/vibes/bin/vibes serve
```

Open <http://127.0.0.1:8080>. `vibes` and `vibes serve` start the same server. Bind address and port are environment settings, not `--host`/`--port` CLI options.

Other examples, after installing and authenticating the corresponding agent:

```bash
VIBES_ACP_AGENT="opencode acp" ~/.venvs/vibes/bin/vibes
VIBES_ACP_AGENT="codex-acp" ~/.venvs/vibes/bin/vibes
VIBES_DEFAULT_AGENT=pi ~/.venvs/vibes/bin/vibes
```

Commands are examples, not interchangeable protocol implementations: model selection, compaction and session restoration depend on what each agent advertises. The live ACP checks used OpenCode 1.18.29. Plain `vibes` without configuration tries `vibe-acp`, not Copilot. Pi mode generates its RPC command with the bundled extension and does not need an ACP executable for normal Pi startup.

For repeatable local settings, create `.vibes/settings.json` in the workspace:

```json
{
  "host": "127.0.0.1",
  "port": 8080,
  "acp_agent": "opencode acp",
  "db_path": "database/vibes.db"
}
```

Environment variables take precedence. See [configuration][config] for `.env`, XDG fallback settings, permission controls and Pi options. Keep credentials out of version control; use the agent's credential store or your service environment.

## Remote access and service operation

There is no built-in login. Keep the default loopback bind and put an authenticated HTTPS reverse proxy in front of it for remote access. Allow long-lived SSE and WebSocket connections, and disable response buffering for SSE. Configure both the public page and API under the same origin. Cross-origin checks do not stop non-browser clients.

A private tailnet restricts reachability, but every permitted client can operate the server. The file editor can write workspace files; agents and the optional terminal run as the service account. Do not run as root or treat conversation selection as a sandbox.

A service manager must set a stable working directory, use the installed executable's absolute path, and provide the same agent `PATH` and credentials used during interactive setup. For example, a systemd service's relevant settings are:

```ini
[Service]
Type=simple
User=vibes
WorkingDirectory=/srv/vibes/workspace
Environment=VIBES_HOST=127.0.0.1
Environment=VIBES_PORT=8080
Environment="VIBES_ACP_AGENT=opencode acp"
Environment=PATH=/srv/vibes/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/srv/vibes/venv/bin/vibes serve
Restart=on-failure
```

This is a template, not an installer: create the account and directories, install Vibes into `/srv/vibes/venv`, and install/authenticate the agent for that account before enabling a service. Adjust paths to the actual installation. No Python Docker image is provided by this branch.

To enable the terminal on a POSIX host, set `VIBES_ENABLE_TERMINAL=1` in the server environment. It is disabled by default and grants shell access, not an agent-approved command queue.

## Agent access to messages and files

ACP messages retrieval is opt-in. To expose the read-only messages MCP tool and bounded workspace reads/listing to a supporting ACP agent:

```bash
VIBES_ACP_AGENT="opencode acp" \
VIBES_ACP_MESSAGES_ENABLED=true \
VIBES_ACP_WORKSPACE_READ_ENABLED=true \
~/.venvs/vibes/bin/vibes
```

The messages tool is scoped to the selected conversation. Text attachments can be read through it; image and binary retrieval returns metadata and an unavailability notice, not native model input. A file or folder reference in a prompt is a reference, not an automatic recursive upload.

`workspace_read` resolves relative paths beneath the server working directory, rejects symlinks and traversal, and returns at most 24,000 bytes per read. `workspace_list` returns at most 200 entries without recursion. These optional tools do not constrain an agent's independent filesystem or shell tools. They are not an operating-system sandbox.

## Upgrade and back up

Stop the server before making a consistent backup of its SQLite database. The default is `database/vibes.db`; preserve any SQLite sidecars if present, workspace files, `.vibes/settings.json`, custom endpoint configuration and separately managed agent credentials. Do not assume a database backup includes files on disk or the agent's own session store. Do not feed a Go-version database to Python without a separately verified migration.

Upgrade the virtual environment using the same command as installation:

```bash
~/.venvs/vibes/bin/python -m pip install --upgrade "git+https://github.com/rcarmo/vibes.git@main"
```

For uv tool installs, use `uv tool upgrade vibes`. For a reproducible deployment, replace `main` in the Git URL with a reviewed Python commit ID. Historical version tags may name the Go implementation; do not select one merely because its version number is higher. Keep a pre-upgrade database backup for rollback and restart from the same workspace directory.

## Build and test from source

```bash
git clone https://github.com/rcarmo/vibes.git
cd vibes
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
bun install --frozen-lockfile
make check PYTHON=.venv/bin/python
make build-frontend lint-frontend
bun test tests/frontend
```

For the headed Chromium/WebKit suite on Linux:

```bash
bun x playwright install --with-deps chromium webkit
xvfb-run -a -s "-screen 0 1920x1080x24" bun x playwright test --headed --workers=1 --trace retain-on-failure
```

Install `xvfb` if your distribution does not already provide it. The explicit display size leaves room for the 1280px viewport and browser chrome. On a graphical desktop, omit the `xvfb-run` prefix and its display arguments. The browser suite owns port 8765 and deliberately uses an unavailable agent executable; do not run a second server on that port. These tests exercise the browser and local server, not a live model subscription.

`make serve` runs the source tree. `make check` covers Python lint/tests only; frontend lint, unit tests and browser tests are separate commands. Browser source changes require rebuilding and committing `src/vibes/static/dist/` because installed packages serve those bundles.

## When startup fails

| Symptom | Check |
| --- | --- |
| `vibes` not found | Use the virtual environment's absolute path or activate it. For uv, check the tool bin directory. |
| Agent executable not found | Set `VIBES_ACP_AGENT` explicitly; test that executable under the service account's `PATH`. |
| Agent connects but cannot answer | Authenticate with the agent's own CLI and check provider/model access. Server startup does not prove model access. |
| Unexpected workspace or empty history | Check the working directory and `VIBES_DB_PATH`; a different directory means different relative paths. |
| Permission or database errors | Check ownership and write access for the service account, not just your login account. |
| Browser updates stall behind a proxy | Check SSE buffering/timeouts and WebSocket forwarding; compare a local loopback connection. |
| Missing context or cost | The agent may not report it. Do not substitute billing token totals for context occupancy. |
| Terminal unavailable | It is opt-in and needs POSIX PTY support. |

[go]: https://github.com/rcarmo/vibes/tree/go
[config]: CONFIGURATION.md
