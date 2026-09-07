## Vibes

Vibes puts a coding agent, a workspace editor and a terminal in a browser, with a layout that also works on a phone or tablet. I built it for personal use over Tailscale, inspired by [Toad][toad]. The interface follows [`piclaw`][piclaw]'s classic web UI, but Vibes is a separate Python application with its own agent adapters and storage.

`main` contains the Python version. The Go implementation is preserved on the [`go` branch][go]; its build instructions and releases are separate.

![Vibes interface (earlier recording)](docs/demo.gif)

## Running it

Use Python 3.12 and Git for the installation below. Agent executables and their provider credentials are installed separately; Vibes does not include a model or an agent subscription. The package includes built browser assets, so running it does not require Bun or a Go compiler.

```bash
python3 -m venv ~/.venvs/vibes
~/.venvs/vibes/bin/python -m pip install --upgrade "git+https://github.com/rcarmo/vibes.git@main"

cd /path/to/your/project
VIBES_ACP_AGENT="copilot --acp" ~/.venvs/vibes/bin/vibes
```

Open <http://127.0.0.1:8080>. Run the server from the directory you want to expose as its workspace. The default database is `database/vibes.db` beneath that directory.

The example explicitly selects Copilot. Without an override, the configured ACP command is `vibe-acp`; another ACP agent can be selected with `VIBES_ACP_AGENT`, for example `opencode acp`. Install and authenticate the chosen agent using its own instructions before starting Vibes.

For [Pi][pi], use its RPC adapter instead:

```bash
VIBES_DEFAULT_AGENT=pi ~/.venvs/vibes/bin/vibes
```

See the [installation guide][install] for source installs, upgrades, service operation and troubleshooting, and [Pi mode][pimode] for adapter settings.

## Working in the browser

Chat streams over SSE and supports Markdown, maths, diagrams and attachments. The workspace tree opens files in a tabbed CodeMirror editor, with search, Vim mode and editor pop-outs. The optional terminal has a separate pop-out and reconnect support; enable it with `VIBES_ENABLE_TERMINAL=1` on a POSIX host.

The pill inside the composer selects a conversation and opens session management. Drag the grip above the input to make room for a longer draft; the chosen height survives a reload. Follow-ups can be queued and reordered, and Pi supports steering an active turn. File, folder and message references travel with the draft.

Model and thinking controls depend on the selected adapter. Context occupancy and cost appear only when the agent reports usable values. For ACP, the context gauge offers compaction only when the agent advertises a no-argument `compact` command. Missing telemetry is not treated as zero.

Conversations have separate stored timelines and agent-session bindings, but they share a server account and workspace. They are not security sandboxes. ACP text attachments can be read through the optional scoped messages tool; image and binary attachments have metadata-only retrieval through that tool, not guaranteed native model input. See the [agent file-access contract][files] for the exact boundary.

## Keep it private

Vibes binds to `127.0.0.1` by default and has **no built-in login**. Anyone who can reach its API can read or modify workspace files and operate the agent; enabling the terminal also gives them a shell as the server user. Put authentication and HTTPS in front of it before enabling remote access, including on a tailnet shared with other people.

Browser cross-origin checks are an additional restriction, not authentication. Agent permission prompts do not protect the file editor or terminal. Run Vibes as an unprivileged account and expose only a workspace you intend that account to use.

## Development

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
bun x playwright install --with-deps chromium webkit
xvfb-run -a -s "-screen 0 1920x1080x24" bun x playwright test --headed --workers=1 --trace retain-on-failure
```

The last command is the Linux browser test path; on a desktop with a display, omit the `xvfb-run` prefix and its display arguments. `make check` runs Python lint and tests, not the browser suite. Commit rebuilt assets under `src/vibes/static/dist/` when changing the frontend.

[Configuration][config] and the [API reference][api] cover the server controls. The [parity notes][parity] record UI differences and verification limits, including mocked rather than live speech testing. They are not installation prerequisites.

MIT licensed; see [LICENSE](LICENSE).

[toad]: https://github.com/batrachianai/toad
[piclaw]: https://github.com/rcarmo/piclaw
[go]: https://github.com/rcarmo/vibes/tree/go
[pi]: https://pi.dev
[install]: docs/INSTALLATION.md
[pimode]: docs/PI_MODE.md
[config]: docs/CONFIGURATION.md
[api]: docs/API.md
[files]: docs/INSTALLATION.md#agent-access-to-messages-and-files
[parity]: docs/PICLAW_PARITY_PLAN.md
