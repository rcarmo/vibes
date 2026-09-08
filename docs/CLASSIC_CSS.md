## Classic stylesheets

Vibes now loads the complete classic stylesheet set from Piclaw 2.15.3 rather
than maintaining copies of individual rules in one large file. Shared surfaces
use the same declarations, including responsive and interaction states. The
snapshot lives in `src/vibes/static/css/classic/`, with its MIT licence.

The source is the deployed `piclaw-2.15.3-linux-x64-baseline` release's
`runtime/web/static/classic/css/` directory. `build.js` preserves its manifest
order: base, shell, workspace, editor, chat, content, agent, overlays, responsive,
settings. KaTeX precedes these layers; Vibes compatibility rules follow them.
The build adjusts the two font URLs for Vibes' `/static/dist/app.css` location.
No files or network access from a Piclaw installation are needed at build time.

## Where the rules apply

Base tokens, fonts, colours, reset and viewport sizing are shared. Workspace
navigation, editor tabs and docks use their classic layers. Composer controls,
model/session pickers, search, queue previews, message content, thinking/status
panes, request dialogs and responsive states use the remaining applicable rules.

The snapshot also contains selectors for Piclaw-only features (including settings
pages, system meters and additional agent panels). Without their markup these
rules are dormant; importing CSS does not implement those features. Markup and
agent behaviour have not been replaced as part of this change.

`src/vibes/static/css/styles.css` holds the remaining Vibes selectors and the
following compatibility rules:

* The session picker is mounted beside the composer, rather than inside its
  positioned input wrapper. It keeps its viewport host on desktop and mobile;
  otherwise classic's absolute positioning places it outside the viewport.
* Backend-gated session actions stay discoverable before hover, including their
  disabled reasons. Inactive editor tabs retain directly clickable close buttons.
* The editor/terminal stack, terminal pop-out and mobile terminal stacking retain
  Vibes' host layout. Workspace drawer controls keep their existing positioning.
* Local theme palettes, capability notices, pin-settings dialog, queue controls
  and extra accessibility/focus states remain local. The anchored model catalogue
  retains a parent-width limit so opening the editor cannot make it overflow.

These exceptions preserve behaviour, not an alternative visual theme for shared
controls. Refresh shared rules from a named reference release rather than editing
the snapshot piecemeal, and explain new host exceptions alongside their rules.

## Checks

Build/lint, 537 backend tests, 23 frontend tests (114 assertions), and all 326
headed Chromium/WebKit tests pass with one worker and zero retries. The browser
suite covers session switching, picker keyboard actions, drafts, editor/terminal
lifecycle, attachments, queues and responsive surfaces. Screenshots use test
fixtures, not new live-agent sessions.

The first broad run timed out after layout-related failures; its results were
retained under `/workspace/tmp/vibes-css-parity/first-results`. Targeted failures
are in `targeted-results`; the final passing run is `browser-second.log` in the
same directory. Exhaustive rendered pixel-identity verification is deferred;
behavioural regression checks take priority. The `v0.8.0` tag is unchanged.
