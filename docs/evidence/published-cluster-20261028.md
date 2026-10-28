# Published five-spec browser comparison

Published runtime `86392e62bfe12ef32abbeca81820f1f15974a127` with fixtures
`4259e825964d2b60dd6c6f7242e2b1daf4280a7d` finished with **48 passed,
114 failed, zero skipped and zero flaky** outcomes. Exit status was 1.
The six-project run took 5,721.976 seconds (95.37 minutes), with one worker,
zero retries and local deterministic model output. It started on
2026-10-28 at 20:48:43 UTC. The final Playwright JSON and shell exit marker
agree; the launcher and its browser jobs have ended.

Each Chromium/WebKit phone, tablet and desktop project recorded 8 passes and
19 failures. This run covers five specs and 162 outcomes. It predates the
local keychain/environment, scoped SSE, prompt receipt and activity work.
No external model provider was contacted.

## Historical counts

| Spec | Historical pass/fail | Published pass/fail |
| --- | ---: | ---: |
| shared-queue | 7 / 47 | 24 / 30 |
| queue-steer | 0 / 12 | 0 / 12 |
| thoughts-panel | 0 / 30 | 18 / 12 |
| shared-reconnect | 0 / 12 | 0 / 12 |
| compaction | 1 / 53 | 6 / 48 |
| Total | 8 / 154 | 48 / 114 |

The historical cluster used runtime `ccbd1fd` and fixtures `053ad57`.
The published counts have 40 more passes; the pass rate changes from 4.94%
to 29.63%, a 24.69 percentage-point increase. Both clusters have 162 outcomes,
but their runtime and fixture revisions differ. These counts do not establish
matched test identities, a causal performance improvement or 40 verified fixes.

## Failure observations

All locations below refer to the pinned fixture source. Each failure was
inspected in the completed JSON; counts reconcile to 114.

| Observation | Count | Fixture location |
| --- | ---: | --- |
| Context meter click does not complete within 120s; locator reports disabled | 36 | `compaction.spec.ts:36` |
| Compaction disabled-state attribute expected `true`, observed empty string | 6 | `compaction.spec.ts:113` |
| Profile contract error: `@cap-compaction requires commands.selectModel` | 6 | `compaction.spec.ts:137` |
| Expected steered agent reply absent | 6 | `queue-steer.spec.ts:29` |
| Expected failed-steer warning absent | 6 | `queue-steer.spec.ts:42` |
| Expected reorder/remove error feedback absent | 6 | `shared-queue.spec.ts:106` |
| Expected active-run steer reply absent | 6 | `shared-queue.spec.ts:134` |
| Expected rejected-action recovery feedback absent | 18 | `shared-queue.spec.ts:150` |
| Expected reconnect stop-control state absent | 12 | `shared-reconnect.spec.ts:42` |
| Collapsed thought visibility differs from assertion | 6 | `thoughts-panel.spec.ts:47` |
| Escape-collapse visibility differs from assertion | 6 | `thoughts-panel.spec.ts:92` |

These are observed failure points. The report does not assign application,
fixture, adapter, environment or backend root causes without further diagnosis.
The six `commands.selectModel` failures are explicit profile contract errors;
no scenario was skipped or silently reclassified.

## Data and limits

[Compact results](published-cluster-20261028.json) retain totals, per-project,
per-spec and per-tag counts, assertion locations and historical comparison.
The historical aggregate remains in
[baseline-clusters.json](concurrency-d1ddd663/baseline-clusters.json).

The completed snapshot, copied fixtures, browser artefacts, synthetic model
state, raw JSON and run logs are disposable and removed after this analysis.
No current-candidate rerun, full-suite, live-provider, release or full Classic
application acceptance is established by this comparison. The consumer pin,
shared frontend, Go work, remote refs and deployment are unchanged.
