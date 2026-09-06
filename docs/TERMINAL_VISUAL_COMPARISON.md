# Terminal visual comparison

Reviewed 2026-09-06 against deployed Piclaw 2.15.3 classic. Local implementation:
06d28df, integrated verification recorded in 890b62f. This is a comparison,
not approval of visual equivalence.

## Evidence

Reference captures (existing workspace evidence):
- `/workspace/tmp/piclaw-classic-terminal-desktop.png`
- `/workspace/tmp/piclaw-classic-terminal-mobile.png`

Local captures from the passing 284-test integrated run:
- `test-results/terminal-terminal-unavailable-reference-state-capture-chromium/terminal-unavailable-reference.png`
- `test-results/terminal-mobile-unavailabl-d30d9-ves-full-width-stacked-chat-chromium/terminal-mobile-unavailable.png`

Both pairs show the unavailable terminal state, at 1280×844 and 390×844.
Chat content is not identical, so whole-page pixel differences cannot be used as
a terminal-only parity score. Captures are ephemeral; a review bundle is delivered
with this report.

## Desktop findings

- Terminal occupies the left workspace pane, with chat to its right in both.
- Header position, title, terminal controls and unavailable-state treatment are
  broadly aligned. Existing assertions verify local header y=4, height=27 and
  padding=4px 16px; this is not a pixel-perfect equivalence assertion.
- Local workspace bottom strip is visibly taller than the deployed strip.
- Surrounding chat typography, empty-state content, footer and composer differ.
  These remain part of the wider UI parity backlog, not terminal protocol defects.
- Main-window splitter nesting remains structurally different from deployed.

## Mobile findings

- Deployed capture keeps terminal and chat side by side: the terminal occupies
  about 200px and chat receives the remaining narrow column.
- Local capture deliberately stacks a full-width terminal above full-width chat.
  The existing mobile test verifies both widths are 390px, chat begins below the
  terminal, and the composer remains in the viewport.
- Consequently neither terminal height nor chat position is visually equivalent.
  This is an intentional usability deviation, not a passing parity comparison.
- Live terminal output and ownership correctness are covered separately by the
  functional suite; unavailable-state images do not establish those properties.

## Remaining acceptance

The screenshot comparison and responsive-deviation review are complete. Maximum
UI equivalence is still open: resolve or explicitly accept workspace strip,
shared host structure, typography/composer differences and mobile stacking.
No live microphone, external ACP or attachment-consumption acceptance follows
from this review.
