# Session picker visual comparison

Rechecked after eedd6a4. Deployed reference: Piclaw 2.15.3 classic. Local captures
come from the passing 60-test headed Chromium/WebKit picker run for eedd6a4.
This supersedes the pre-refinement local capture review at 2329407.

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
- Canonical IDs no longer occupy a separate metadata row; they remain searchable
  and available through accessible descriptions and tooltips. Message counts and
  persisted-message timestamps remain visible local extensions.
- Rename/Archive/Delete now use compact icons. Delete matches the deployed class
  and crossed-line SVG; Rename/Archive are documented local action extensions.
  Mobile retains touch-sized controls and the tested readable session-name width.
- Rechecked desktop/mobile captures show no visible overlap between row actions
  and labels. Footer actions remain visible; desktop labels fit on one line and
  mobile footer labels wrap within the available width.
- Local lifecycle pills say Running/Idle/Archived, while the reference also shows
  its own runtime labels. Local labels must stay tied to supported backend facts.
- The reference capture shows only New root, but source-map inspection confirms
  conditional New branch, New root session… and Rename current session actions.
  Local labels now match those entries. Unlike deployed, local actions remain
  available during search to preserve filtered rename-current behavior.
- Desktop popup height/content density differ. No claim of identical geometry is
  made; the two captures contain different session populations.

## Acceptance boundaries

Grouping, keyboard navigation, accessible search, callback gating and backend
lifecycle protections have passing tests. The scoped row-density/footer refinement
and screenshot recheck are complete, with retained metrics, local lifecycle icons
and search-time footer availability explicitly documented as deviations. This is
not full visual equivalence approval. The intermittent closed-picker failures
recorded in 8399b9d also remain unresolved despite subsequent passing runs.
Runtime metrics must not be invented to mimic the reference.
This review neither verifies real third-party ACP execution nor persistent-thread
message-tool isolation.
