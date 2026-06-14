# AGENTS.md

Guidance for coding agents working in this repository.

## Project shape

Vibes is a Go backend with an embedded Bun-built frontend:

- Backend: `cmd/`, `internal/`
- Frontend source: `static/js/`, `static/css/`
- Generated frontend bundle: `static/dist/`
- Frontend build script: `build.js`
- E2E tests: `tests/`

Always treat `static/dist/*` as generated output. Change source files first, then rebuild with:

```bash
bun run build:frontend
```

## Frontend development principles

The frontend should move steadily away from large monolithic files and toward small, typed, capability-oriented modules.

### Modularity

Prefer small files with clear responsibilities over expanding existing large modules.

Recommended structure as the frontend grows:

```text
static/js/
  app.js                 # app wiring only; avoid adding feature logic here
  api/                   # API clients grouped by backend area
  components/            # reusable Preact components
  components/compose/    # compose box subcomponents
  components/timeline/   # timeline subcomponents
  features/              # feature-level modules, e.g. backends, workspace, settings
  hooks/                 # reusable Preact hooks
  lib/                   # pure utilities with no DOM assumptions
  types/                 # shared TS types once TypeScript is introduced
  ui/                    # low-level UI helpers
```

Avoid adding more unrelated logic to:

- `static/js/app.js`
- `static/js/components/compose-box.js`
- `static/js/components/timeline.js`

When modifying those files, prefer extracting cohesive pieces into nearby subfolders.

### CSS organization

`static/css/styles.css` should not keep growing indefinitely. New styles should be grouped by component or feature and progressively split into imports once the build pipeline supports it.

Recommended future structure:

```text
static/css/
  styles.css             # imports/tokens/base shell
  tokens.css             # variables, colour/theme tokens
  base.css               # reset/body/global typography
  layout.css             # app shell/layout primitives
  components/
    compose.css
    timeline.css
    status.css
    settings.css
    workspace.css
  features/
    backends.css
    editor.css
```

Until CSS imports are wired into `build.js`, keep changes in `styles.css` clearly sectioned and avoid scattering component rules across the file.

### Progressive TypeScript conversion

Start converting frontend code to TypeScript incrementally rather than as a flag day.

Preferred order:

1. Pure utilities in `static/js/lib/` → `.ts`
2. API clients and payload shapes → `.ts`
3. Backend/provider capability types → `.ts`
4. Small presentational components → `.tsx` or `.ts` depending on the chosen JSX/htm setup
5. Larger stateful components last

Do not convert a large component and mix unrelated refactors in the same change. Keep conversion PRs/commits small and reviewable.

When TypeScript is introduced:

- add a `tsconfig.json`
- enable `checkJs` only if useful during transition
- keep `strict` on for new `.ts` files where practical
- type API responses at module boundaries
- prefer discriminated unions for SSE/backend events
- avoid `any`; use `unknown` and narrow
- keep generated bundle output in `static/dist/`

### API and event typing

Backend/provider work should expose stable JSON shapes and corresponding frontend types.

In particular, keep these typed once TypeScript is available:

- provider descriptors
- provider capabilities
- timeline interactions
- backend provenance metadata
- SSE events
- slash command responses
- queue/follow-up items
- workspace file responses

Capability-driven UI should be represented as data, not scattered boolean guesses.

### Preact component practices

- Keep components focused and shallow.
- Extract derived state into pure helpers.
- Extract repeated effects into hooks.
- Avoid inline logic in large template blocks when it can be named.
- Prefer explicit props over implicit global state.
- Keep DOM-specific code out of pure modules.
- For event handlers, avoid capturing huge dependency sets where a small helper will do.

### Backend capability UI

The UI should hide unsupported backend controls rather than showing broken/disabled controls everywhere.

For provider-specific features:

- read capabilities from the backend descriptor
- show supported controls only
- keep common controls visually consistent
- avoid hard-coding assumptions like “Pi supports this” in components unless the capability map also says so

### Bundling

`build.js` is intentionally simple today. As TypeScript and CSS modules are introduced, update the build in small steps:

- support `.ts` entry/imports first
- then support CSS splitting/imports
- keep sourcemaps enabled
- preserve embedded output paths under `static/dist/`
- make `bun run lint:frontend` and `bun run build:frontend` the minimum validation for frontend changes

## Testing expectations

For frontend changes, run at least:

```bash
bun run lint:frontend
bun run build:frontend
```

For backend/API changes, run:

```bash
go test ./...
go build -o /tmp/vibes-check ./cmd/vibes
```

For changes affecting user flows, update or add Playwright tests under `tests/steps/` and `tests/features/`.

## Repository hygiene

- Do not edit `static/dist/*` directly.
- Do not mix generated bundle diffs with unrelated source changes unless a rebuild is required.
- Keep commits focused: dependency updates, backend API changes, frontend refactors and generated rebuilds should be easy to review.
- Avoid formatting-only churn in unrelated Go files.
- Preserve existing behavior while extracting modules; refactor first, then change behavior in a separate step when possible.
