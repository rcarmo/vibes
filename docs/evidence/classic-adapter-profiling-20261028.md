# Classic response projection profiling

Request-local batching removes repeated media metadata lookups from Classic
history/search projection. Ownership, reference order/duplicates, first-32 bounds
and output fields are unchanged; no cache survives a response.

## Workload and measurements

Baseline `0081cb8`, CPython 3.12.3, aiosqlite, local SQLite/WAL, 200 visible
messages with eight shared owned attachments each. Every loop reads 50 history
messages, 50 FTS results and one empty queue snapshot; 60 warmed loops per sample.
No model provider or browser is involved. CPU uses process time and cProfile;
allocation totals/counts and high-water memory use Memray 1.19.1 with the same
workload, separately from unprofiled timing.

| Metric | Before | After | Change |
| --- | ---: | ---: | ---: |
| SQL executions | 48,360 | 480 | -99.01% |
| Process CPU | 3.8660 s | 0.1550 s | -95.99% |
| Wall time | 4.0187 s | 0.1569 s | -96.10% |
| Allocated bytes | 1,479,069,864 | 147,006,152 | -90.06% |
| Allocation count | 1,131,253 | 128,305 | -88.66% |
| Peak tracked bytes | 1,426,375 | 1,428,231 | +1,856 (+0.13%) |

cProfile ranked repeated `get_media` calls and SQLite worker/event-loop wakeups
as the material baseline outlier. The allocation history attributed 105,120,000
bytes/192,000 allocation events to `get_media` and 1,317,571,020 bytes/912,247 events
to SQLite/asyncio/runtime stacks. After batching, metadata decoding accounts for
2,102,400 bytes/3,840 events; SQLite/asyncio/runtime falls to 87,476,332 bytes/97,458
events. Remaining costs are bounded message JSON decoding, projection and final
response serialization. The small peak increase pays for a response-local lookup
map and is acceptable beside the verified CPU/total-allocation reduction.

An additional same-database comparison loaded the baseline projection module
without modifying source and compared decoded history/search responses directly;
they were equal. Three independent 60-loop history+search timing repeats (without
the queue snapshot) gave median process CPU 3.7537 -> 0.1142 seconds (-96.96%) and
wall time 3.9202 -> 0.1153 seconds (-97.06%). CPU sample ranges were 3.7243–3.8217
and 0.1134–0.1237 seconds. This repeat is a separate workload, not mixed into the
CPU/allocation table above. Gains are material beyond observed timing noise.

## Change and correctness

`project_page` parses each interaction once, gathers distinct bounded attachment
IDs, fetches metadata in chunks of at most 500 SQL parameters and projects each
message with its own persisted-session ownership check. Single-message SSE uses
the same path. Missing/foreign metadata remains excluded; each message retains
its original attachment order and duplicates. Deletion or ownership changes
appear on the next response because nothing is cached across requests.

The 24-test message/SSE/media gate passed in 1.42 seconds. Added coverage crosses
500 distinct IDs, checks two batch queries, preserves message/reference ordering
and duplicates, then changes ownership/deletes media and verifies fresh readback.
Full Python regression: 1,062 passed, 13 existing skips in 43.12 seconds, using the
pinned optional SDK and unchanged shared assets. Changed route/tests pass Ruff;
diff checks pass. Read-only review found no concrete projection regression.

The first profiling script shadowed Python's standard `profile` module, causing
a failed capture; it was renamed and its failed database/logs removed before the
comparison. Captures, matching scripts, synthetic databases, copied baseline source,
profiling dependencies, SDK, asset link and disposable test output are removed
immediately after analysis. Only these concise measurements remain.

This targets the measured attachment-rich response outlier. It does not complete
whole-application pre-release profiling, live-provider, high-rate SSE/slow-client
or six-project browser acceptance. The next validation is a compiled-client
workload after protected UI/pin adoption, including latency and allocation checks
with realistic attachment distributions and concurrent sessions.
