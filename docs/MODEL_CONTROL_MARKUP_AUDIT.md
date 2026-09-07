# Model/thinking markup audit

Reference: installed Piclaw 2.15.3 classic `dist/app.bundle.js.map`, embedded
`../../../src/components/compose-box.ts`, lines 3819–3842. Local source:
`src/vibes/static/js/components/compose-box.js`, model hint/thinking controls.
Source inspection only; not visual approval or authenticated execution evidence.

## Confirmed matches

The model trigger is an explicit button with classes `compose-model-hint
compose-model-hint-btn`, accessible Open model picker label, switching-state
presentation and disabled mutation state. Local session-specific catalog and
thinking capability gating have existing browser coverage.

## Concrete remaining structure gap

Deployed structure:

- `compose-meta-row`
  - `compose-model-meta`
    - model trigger
    - `compose-model-meta-subline`
      - `compose-model-usage-hint` span, when information is available
  - context gauge

Deployed thinking level is part of the usage subline, joined with supported usage
and routing information. It is not a `compose-thinking-pill` button. Local code
currently places a cycle-thinking button adjacent to the model trigger instead.

Next implementation: adopt the deployed model-meta/subline structure and its CSS,
retain the capability-gated local cycle action as an explicitly documented
interactive extension, and compare desktop/mobile captures. Do not add fabricated
pricing, routing or provider usage to fill the reference subline. Preserve explicit
button types, accessible labels, selection callbacks and context-gauge behavior.

The local thinking selector inside the catalog also remains a local extension;
this audit does not authorize removing working per-session controls merely to
obtain screenshot similarity. Full picker and status visual acceptance remain open.

## Implemented metadata wrappers

Local model trigger and thinking action now sit inside compose-model-meta, with
thinking inside compose-model-meta-subline. Copied deployed column layout, 2px
gaps and min-width rules, with max-width containment on the local model trigger.
The pill remains an explicitly interactive local extension rather than a copied
usage-hint span. No provider usage/pricing data was invented.

Ten targeted headed Chromium/WebKit tests pass, including desktop/mobile structural
and bounding-box assertions plus thinking/context behavior. 20 frontend tests and
build/lint pass. Rechecked 1280px/390px Chromium captures: model and thinking stack
without overlap; controls fit the viewport. This is scoped structure verification,
not full footer/picker visual equivalence or approval of the local pill treatment.

## Full browser regression after layout change

All 304 headed Chromium/WebKit tests pass with one worker, zero retries and
retain-on-failure tracing (6.0m); log /workspace/tmp/model-meta-integrated-browser.log.
This includes picker, thinking, context, session switching, queue and terminal
workflows after 55f02bf. Historical intermittent opening failures were not
reproduced and remain unresolved; passing is not evidence of their root cause.

## Metadata row alignment

Copied deployed compose-meta-row flex-start alignment, 12px minimum height,
0 2px padding, flex:1 and min-width:0. Model/thinking and context now form one
left-aligned group rather than being spread across the composer. Expanded
1280px/390px captures include real-shaped mocked context data; tests assert the
gauge follows the metadata group with a nonnegative gap no larger than 8px and
fits the viewport. Eight targeted Chromium/WebKit cases and build/lint pass.
Mobile Chromium capture inspected with gauge present; no control overlap observed.

## Long canonical identity containment

A new mobile regression reproduced horizontal overflow in both browsers with a
long canonical model ID: the gauge right edge exceeded 1500px in a 390px viewport.
The flex composer wrapper retained its intrinsic automatic minimum width. Added
min-width:0 to that wrapper and flex-shrink:0 to the gauge. The label now truncates
visually while its complete text and title retain canonical identity; gauge remains
visible within the viewport. Eight targeted browser tests and build/lint pass.

## Picker capture recheck after containment fix

Six headed Chromium/WebKit capture cases pass after 30b710a: a single-model fixture
at 1280px and model/thinking catalogs at 1280px/390px. Reviewed the current Chromium
single-model capture alongside /workspace/tmp/piclaw-classic-model-desktop.png,
and the current 390px model/thinking capture. Local model population is fixture
data, not authenticated provider discovery. The single-model fixture uses
`test/review-model`; it is not identical reference content.

The base compose-model-popup rule matches the installed classic rule (absolute
position, bottom:calc(100% + 6px), column flex, z-index:120). Matching that rule does
not establish the same surrounding composer geometry. Local catalog loading/count
status, scoped thinking selector and Models settings for pin transfers remain
application-specific behavior. Local full-page chrome and composer structure still
differ from deployed; this comparison does not close full footer visual acceptance.
No additional production styling changed during this recheck.

## Shared composer footer implemented

Metadata and actions now share a compose-footer below compose-input-main instead
of placing actions alongside the input. Composer wrapper is a stretched column;
footer uses deployed flex alignment/gap/position, with actions aligned to the end.
Model popup remains anchored to its existing input-main host; all handlers and
control labels are preserved. The local thinking pill remains an extension.

Full headed Chromium/WebKit suite: 306 pass without retries (5.9m); 20 frontend
tests/95 assertions and build/lint pass. Then four strengthened desktop/mobile
cases pass, asserting footer children and placement below the textarea. Inspected
390px Chromium capture with model/thinking/context and actions present. Full visual
identity is still not claimed: local controls and surrounding application chrome
remain different. Historical intermittent picker failures are not declared fixed.

## Footer accessibility attributes

Footer buttons now declare type="button" consistently; decorative action SVGs
are aria-hidden="true". The meaningful context gauge retains its accessible usage
label. Existing button labels and callbacks are unchanged. Four desktop/mobile
Chromium/WebKit footer cases verify explicit types and decorative icon attributes;
build/lint pass. Evidence: /workspace/tmp/footer-a11y-browser.log and
/workspace/tmp/footer-a11y-build.log. These checks do not establish live speech
acceptance or close the broader visual-parity gate.
