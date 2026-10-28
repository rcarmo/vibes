# Historical Python suite classification

The `ccbd1fd` / fixtures `053ad57` run contains 1,554 outcomes across 41 specs:
337 passed, 923 failed and 294 skipped, with zero flaky outcomes. Its reported
duration was 18,869.643 seconds (5.24 hours). This classification uses the
historical JSON, not a new suite execution or the current source's behaviour.

The companion [compact JSON](baseline-ccbd1fd-classification.json) records all
spec and scenario-tag counts, primary failure-point groups, three bounded
examples per group and skip annotations. Raw traces/screenshots are not retained
with this classification. The original report is still being used by the active
published-SHA comparison and must not be deleted until that analysis finishes.

## Observed failure points

Each failed test is assigned exactly one primary group in this order: missing
profile command, JavaScript exception, timeout, missing UI target, expected one
result but observed zero, other state/value assertion, transport signature, other.
Timeout matching precedes missing selectors, so groups are failure-message
buckets rather than independent root causes.

| Primary failure point | Outcomes |
| --- | ---: |
| Test or operation timeout | 432 |
| Expected one result, observed zero | 246 |
| Other value/state assertion | 151 |
| Missing UI target | 79 |
| Missing profile command | 6 |
| Fixture JavaScript exception | 3 |
| Other explicit helper error | 6 |
| **Total failed** | **923** |

No primary transport/HTTP bucket was populated by this rule. That does not prove
that the backend or provider was healthy; a missing reply or later UI timeout can
hide an earlier backend problem.

There are 233 distinct scenario tags: 125 have failures and no passes, 41 have
both passes and failures, 22 pass only, and 45 skip only. Some tags cover multiple
cases, so these are tag groups, not a count of individual test titles.

## Five-spec baseline

| Spec | Passed | Failed | Skipped | Total |
| --- | ---: | ---: | ---: | ---: |
| shared-queue | 7 | 47 | 0 | 54 |
| queue-steer | 0 | 12 | 0 | 12 |
| thoughts-panel | 0 | 30 | 0 | 30 |
| shared-reconnect | 0 | 12 | 0 | 12 |
| compaction | 1 | 53 | 0 | 54 |
| **Cluster** | **8** | **154** | **0** | **162** |
| All other specs | 329 | 769 | 294 | 1,392 |

A read-only inspection of these failures found 146 ending at common held-turn or
agent-post observations, two queue error-feedback targets absent after a
simulated failed write, and six explicit `commands.selectModel` configuration
errors. These are observed stopping points; no new known-defect skip follows.
The broader message buckets above deliberately do not infer provider or UI root
causes from a timeout alone.

Earlier narrow gate counts (45/12/27/8/37) refer to separately selected outcomes;
they must not replace the five whole-spec totals above. The compact JSON retains
per-tag results so future comparisons can state their exact selection.

## Concrete triage

The six missing-profile-command failures are `@ux-compaction-008` and explicitly
report `@cap-compaction requires commands.selectModel`. Correct the consumer
profile/runtime command contract before treating these as compaction execution
failures. The three JavaScript exceptions are WebKit `@ux-compose-008`, failing
in fixture workspace handling with an undefined `unicode` value. The six other
helper errors are `@ux-workspace-001`, `newFile: nothing created after 4 enabled
clicks`; this identifies the operation that failed, not which layer caused it.

The highest failing whole specs are terminal (98), editor (74), compaction (53)
and theme/tint (51). Test these through bounded backend/real-route probes before
another broad suite. Editor-open-file passed all 18 cases, so its successful
open/view path must not be conflated with editor write/conflict acceptance.

The 294 skip annotations include capability absence (notably 96 Settings-dialog
outcomes), viewport/app-mode constraints and documented browser limitations.
They describe the historical profile, not current product scope. Retirement
changes and added APIs still need a separately reviewed profile/fixture repin;
classification does not add or relax skips.

## Complete spec totals

| Spec | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| `adaptive-cards.spec.ts` | 0 | 0 | 12 |
| `btw.spec.ts` | 0 | 6 | 0 |
| `chat-lifecycle.spec.ts` | 0 | 48 | 0 |
| `classic-core.spec.ts` | 0 | 12 | 0 |
| `compaction.spec.ts` | 1 | 53 | 0 |
| `compose-stability.spec.ts` | 14 | 34 | 0 |
| `compose-submit.spec.ts` | 6 | 24 | 0 |
| `context-meter.spec.ts` | 0 | 12 | 0 |
| `editor-open-file.spec.ts` | 18 | 0 | 0 |
| `editor.spec.ts` | 0 | 74 | 4 |
| `highlights.spec.ts` | 0 | 0 | 30 |
| `image-annotator.spec.ts` | 0 | 0 | 42 |
| `lightbox.spec.ts` | 14 | 8 | 2 |
| `message-deletion.spec.ts` | 0 | 30 | 0 |
| `mobile-swipe.spec.ts` | 0 | 1 | 35 |
| `plan.spec.ts` | 24 | 24 | 0 |
| `pwa-manifest.spec.ts` | 6 | 36 | 12 |
| `queue-steer.spec.ts` | 0 | 12 | 0 |
| `quick-actions.spec.ts` | 0 | 18 | 0 |
| `reconnect.spec.ts` | 0 | 18 | 0 |
| `rendering.spec.ts` | 4 | 32 | 0 |
| `session-picker.spec.ts` | 6 | 12 | 6 |
| `settings.spec.ts` | 0 | 0 | 96 |
| `shared-copy.spec.ts` | 0 | 48 | 0 |
| `shared-messages-tool.spec.ts` | 0 | 12 | 0 |
| `shared-model-picker.spec.ts` | 21 | 15 | 0 |
| `shared-pickers.spec.ts` | 0 | 24 | 0 |
| `shared-queue.spec.ts` | 7 | 47 | 0 |
| `shared-quick-actions.spec.ts` | 92 | 16 | 0 |
| `shared-reconnect.spec.ts` | 0 | 12 | 0 |
| `shared-session-picker.spec.ts` | 0 | 30 | 0 |
| `shared-shell.spec.ts` | 56 | 4 | 0 |
| `shared-svg.spec.ts` | 12 | 6 | 0 |
| `shell-menu.spec.ts` | 12 | 30 | 12 |
| `terminal.spec.ts` | 0 | 98 | 10 |
| `theme-tint.spec.ts` | 39 | 51 | 0 |
| `thoughts-panel.spec.ts` | 0 | 30 | 0 |
| `timeline-time.spec.ts` | 2 | 4 | 0 |
| `vnc.spec.ts` | 0 | 0 | 6 |
| `widgets.spec.ts` | 0 | 0 | 12 |
| `workspace-flows.spec.ts` | 3 | 42 | 15 |
