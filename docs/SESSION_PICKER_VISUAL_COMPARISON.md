# Session picker visual comparison

Reviewed 2026-09-06. Deployed reference: Piclaw 2.15.3 classic. Local captures
come from the 58-test headed Chromium/WebKit picker run recorded at 2329407;
subsequent backend changes do not modify this UI.

## Evidence

Reference: `/workspace/tmp/piclaw-classic-session-desktop.png` and
`/workspace/tmp/piclaw-classic-session-mobile.png`.
Local: `test-results/session-picker-capture-mounted-session-picker-at-1280px-chromium/session-picker-1280.png`
and `test-results/session-picker-capture-mounted-session-picker-at-390px-chromium/session-picker-390.png`.
Viewports: 1280×844 and 390×844. A delivered review archive preserves the images.
Different session contents prevent a meaningful whole-image pixel equality score.

## Findings

- Both use a searchable grouped picker with section headings, a close control,
  pin affordances and a scrollable results area.
- Mobile outer positioning is broadly aligned: near-full-screen popup, search
  at top and actions at bottom. Local tests assert 8px insets and 374×828 size.
- Local rows are substantially denser: canonical IDs, message counts and last
  persisted-message timestamps occupy space absent from the reference rows.
- Local explicit Rename/Archive/Delete text controls differ from the reference's
  compact icon treatment. Keeping accessible names does not require keeping
  visible text; reducing this width is a remaining markup/layout task.
- Local lifecycle pills say Running/Idle/Archived, while the reference also shows
  its own runtime labels. Local labels must stay tied to supported backend facts.
- Local New branch, New root and Rename current footer controls exceed the
  reference's simpler New root footer. They reflect local lifecycle capabilities,
  not proof of deployed markup equivalence.
- Desktop popup height/content density differ. No claim of identical geometry is
  made; the two captures contain different session populations.

## Acceptance boundaries

Grouping, keyboard navigation, accessible search, callback gating and backend
lifecycle protections have passing tests. Visual equivalence remains open:
compact row actions, metadata density and footer differences need resolution or
explicit acceptance. Runtime metrics must not be invented to mimic the reference.
This review neither verifies real third-party ACP execution nor persistent-thread
message-tool isolation.
