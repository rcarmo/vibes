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

## Quick actions and turn cancellation

Typing with focus on the timeline opens the classic quick-actions palette. The
composer's lightning button also opens it on touch devices. Sessions, workspace
visibility, an enabled terminal and supported slash commands are searchable;
arrows select, Enter activates and Escape restores focus. Inserting a command
preserves existing draft text, attachments and references, and never sends it.
Generic slash commands remain unavailable in non-default sessions, so their
catalogue is empty. VNC, chat pop-outs and full Settings actions are not offered.

The composer stop control follows turn activity, including restored turns and
SSE interruptions, rather than the status caption. It stays accessible in search
mode. Cancellation uses a separate endpoint with session/turn/runtime ownership
checks, reports rejected requests, and leaves composition and queued items alone.
The connection notice no longer intercepts pointer input over the stop control.

Validation: 557 backend tests, 26 frontend tests (140 assertions), and 220 focused
headed Chromium/WebKit cases passed with one worker and no retries. The full
browser run timed out after a terminal-load failure and an over-specific default
session label assertion; those artifacts were retained. The corrected session
assertion and terminal suite passed separately, not as a full-suite checkpoint.

Live check: the default Pi session started a real turn, retained its stop control
and draft after a page reload, accepted cancellation with HTTP 202, and returned
to an idle backend with no active turns. The named-session attempt failed before
generation because Pi reported no persisted session file; live non-default
cancellation remains unverified. Automated tests cover its ownership checks.

## Server resource meters

The collapsible top-right panel shows CPU/RAM history, Vibes process RSS,
buffer/cache memory, swap when configured, and VRAM when Linux DRM exposes usable
counters. It uses the vendored classic meter styles, with a compact mobile summary
and a quick action to collapse or restore it. The host label identifies the source:
the Vibes server's OS view, not browser usage, container limits or a separate model
server. RSS excludes child agent processes.

`GET /system/metrics` uses the normal API middleware and a shared sampler, limited
to one collection every two seconds and thirty history points. Reads run outside
the event loop; no subprocesses or Pi RPC calls are involved. The first CPU sample
(and the first after a long pause) is unavailable until a delta can be calculated.
Missing metrics are not presented as zero, unsupported platforms report unavailable,
and failed/stale responses clear displayed readings. Browser polling pauses when
the page is hidden. Optional VRAM currently covers Linux DRM counters, not NVIDIA
management tools or Apple unified memory.

Validation: build/lint, 564 backend tests, 28 frontend tests (161 assertions), and
46 focused headed Chromium/WebKit tests passed, one worker and no retries. The
browser checks include meter refresh/failure recovery, mobile layout, keyboard
collapse/restore, quick actions, cancellation and composer sizing.

## Controlled visual parity, first fix pass

The shared fixture exposed a wrong composer-height storage key on its Vibes side.
With the same 80px preference applied to both UIs, the remaining footer difference
came from Vibes' bordered thinking control and an unstyled context-gauge button.
Those now use classic geometry while preserving thinking changes and guarded
compaction. Short Draft/Thought previews no longer show an overflow toggle;
expanded long previews retain it. Overflow measurement runs outside the
ResizeObserver callback to avoid WebKit notification loops.

The model picker now uses classic option/section markup, mobile sizing and footer
thinking controls. Refresh/cycle remain in Models settings, pinning and keyboard
focus remain available. Meters retain their source description in the tooltip
rather than an extra visible heading, and their compact summary follows classic
ordering. Disclosure triangles and message Copy icons use matching SVG geometry.

This is not final parity. The corrected 36-comparison matrix has zero browser
errors, unhandled requests or changed pixels between repeats. Meter regions match
in all captures, while session/quick-action presentation and smaller browser-specific
differences remain. Regression validation: 570 backend tests, 30 frontend tests
(220 assertions), 152 headed Chromium/WebKit cases, plus eight status cases after
the ResizeObserver correction. Earlier failures were retained and resolved before
this checkpoint; they were not retries of a failing acceptance run.
