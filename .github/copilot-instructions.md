
If `AGENTBOX_ENVIRONMENT` is set and you are in `/workspace`, then you are running in a sandbox container where you can use `uv`, `brew` and `apt` to install additional tooling. For Python you should prefer `pip3 install --user --break-system-packages` over a `venv`.

## Build, lint, and test

- Prefer Makefile targets for common workflows (e.g., `make lint`, `make lint-frontend`, `make test`, `make check`).
- Run existing linters/tests before and after changes when feasible.

## Avoid duplication

- Do not duplicate logic across files: extract helpers or reuse existing utilities.
- Keep tests DRY by parameterizing cases and using fixtures instead of copy/paste.
