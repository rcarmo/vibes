# Same-state visual comparison

This fixture boots the real built Vibes UI and the deployed Piclaw classic UI in
isolated browser contexts. `state.mjs` defines shared semantic data;
`adapters.mjs` translates it into each application's API/SSE formats. It does not
rewrite application markup, import private component setters or adjust layout
CSS to improve a diff.

## Run

From the project root, after `bun install --frozen-lockfile`:

```bash
xvfb-run -a -s '-screen 0 1920x1080x24' \
  bun tests/visual-parity/capture.mjs \
  --reference /opt/piclaw/releases/piclaw-3.1.2-linux-x64-baseline/app/runtime/web/static \
  --out /workspace/tmp/vibes-visual-new-run
```

Add `--themes light,dark` for the complete two-theme matrix. The default remains
`dark` so historical commands and baselines stay reproducible.

The reference is an **installed release** containing `classic`, `common`, and the
sibling `../../extensions/viewers/editor/vendor` assets. Vibes uses the checked-in
`src/vibes/static/dist` build. Run `make build-frontend` first if testing source
changes, but not when comparing an exact already-deployed bundle. The harness
hashes JS, CSS, fixture files and the reference editor vendor.

Optional filters:

```bash
xvfb-run -a bun tests/visual-parity/capture.mjs \
  --browsers webkit --viewports tablet --scenarios working,models \
  --repeat 2 --out /workspace/tmp/vibes-visual-tablet
```

The output directory must be empty: failed and previous runs are never overwritten.
A run exits nonzero on a missing semantic assertion, browser error, unhandled
request, missing asset or differing repeat capture. Piclaw/Vibes differences are
reported, not thresholded into a false parity pass.

## Matrix and controls

* Chromium and WebKit, headed, serial execution, no retries.
* Desktop 1440×900, tablet 1024×768, mobile 390×844; DPR 1.
* Dark theme by default, or explicit `--themes light,dark`; en-GB locale, UTC, frozen time and deterministic avatars/image bytes.
* Idle messages, active draft/thought/status/queue, session picker, model picker,
  quick actions, and an assistant image attachment.
* The workspace is closed via the normal control; composer text and popup state
  are set by actual input/click/keyboard interactions. Vibes' lazy session registry
  is warmed through its picker, which is then closed before capture.
* Animation, transitions and carets are disabled on **both** sides. Mouse and focus
  are moved away from inactive controls. No colours, dimensions, spacing, fonts,
  positions or capability-specific controls are masked.
* Every request is intercepted at `fixture.invalid`; no production API, database,
  credentials, service worker or agent process is used. Unknown requests are logged
  and fail the scenario rather than falling through to a real server.
* Both APIs receive equivalent model/context, messages, session names, meter
  histories, command descriptions and queue text. Native session IDs and labels
  remain native. Unsupported product-specific commands are not invented.
* Semantic assertions verify messages, model, composer draft, metrics, and each
  scenario's important state before capturing. Images decode and fonts load first.

## Evidence

Open `index.html` in the result directory. Each comparison includes:

* original Piclaw/Vibes PNGs and repeat captures;
* side-by-side (Piclaw left), pixel diff and 50% alpha overlay;
* same-coordinate union crops for composer, status, meters and popup surfaces;
* DOM bounding boxes/computed styles, rendered text, focus, API request diagnostics;
* a manifest with asset/fixture hashes, browser versions and repeat stability.

Pixelmatch uses threshold 0.1 and excludes antialiasing. Percentages are the share
of changed screenshot pixels, **not** a usability or parity score. Region crops
use the union of actual positions; they are not translated to conceal offsets.
Blank space can dilute full-screen percentages, so inspect the region diffs too.

This is a focused baseline, not exhaustive parity coverage: expanded status
panels, workspace/editor/terminal panes, permission dialogs, real runtime
execution and OS-specific fonts are not covered yet. Add states to the shared
fixture and explicit adapters before expanding the matrix.

## Corrections found during the first UI fix pass

The original baseline accidentally set `vibes_compose_height` on Vibes instead of
its actual `piclaw_compose_height` preference. Both now receive an 80px textarea
height. This means the initial reported 27.8px mobile height gap was partly a
fixture error, not a production layout defect. Keep the original report as
historical evidence; do not use its height percentages as the corrected baseline.

The reference model catalogue now receives the same per-model thinking levels
as Vibes. Geometry capture includes the textarea, footer, gauge, model hint and
status title/body to separate missing fixture state from product styling.
