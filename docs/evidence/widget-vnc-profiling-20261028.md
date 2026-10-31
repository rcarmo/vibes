# Widget lookup and VNC transport profiling

An indexed widget lookup removes repeated parsing of historical HTML. VNC's
bounded echo workload showed no comparable application repeated-work hotspot.
This covers synthetic backend workloads; browser rendering, account inference
and slow-client soak still require separate acceptance.

## Workloads and tools

Python 3.12.3, Linux x64; baseline `3630e7e`, equivalent workload after SQLite
schema 11 expression index and first-block lookup. Widget publication always
creates exactly one generated-widget block; the index uses that contract. No
schema widening or additional HTML copy is required.

Widget workload: 120 durable widget messages, each containing approximately
200 kB of synthetic HTML, followed by 30 GETs of the newest artifact through
actual aiohttp routes. Every response is decoded and its content checked. This
includes the loopback HTTP client, not just SQL execution. Database setup is
outside the capture; the index adds one small entry per widget on writes.

VNC workload: actual loopback TCP echo server and browser-side WebSocket client,
100 sequential 32 KiB transfers (3.125 MiB each direction), asserting byte counts.
This tests transport buffers, not framebuffer quality, RFB parser state or auth.

CPU: cProfile plus process CPU time. Separate equivalent allocation runs used
Memray 1.20.0 with native stacks and Python allocator tracing. Totals count
allocation events; they are not RSS or live retained memory. Memray printed its
malloc/free symbol-correction warning; captures were nonempty and inspected.

## Widget comparison

| Metric | Baseline | Indexed lookup | Change |
| --- | ---: | ---: | ---: |
| CPU-capture wall time | 0.983 s | 0.0449 s | -95.4% |
| Process CPU time | 0.982 s | 0.0449 s | -95.4% |
| Allocation-capture wall time | 1.082 s | 0.105 s | -90.3% |
| Allocated bytes | 4,418,485,138 | 96,516,095 | -97.8% |
| Allocation events | 89,681 | 59,257 | -33.9% |
| Peak tracked bytes | 8,645,493 | 7,103,285 | -17.8% |
| SQLite worker allocated bytes | 4,334,021,630 | 12,041,374 | -99.7% |

The original query iterated `json_each` across historical candidate rows and
reparsed large JSON for every lookup. SQLite worker allocation dominated the
capture. A partial expression index on session plus first-block widget ID, with
the generated-widget predicate, selects the one durable row directly. The route
still uses session scoping, the database write lock, deletion-coupled storage and
JSON/nosniff delivery. No HTML cache or cross-session artifact sharing was added.
An `EXPLAIN QUERY PLAN` regression requires the intended index.

After the fix, costs move to HTTP socket buffers and JSON encode/decode of the
requested payload. Those are bounded by the existing artifact limit; they no
longer scale with all historical HTML for each read. These single-run results
show a large effect, not latency percentiles. Next validation: mixed publication/
lookup with concurrent sessions and a large migrated database, including index
creation time and write overhead.

## VNC result

CPU-capture wall/process CPU: 25.3/25.2 ms. cProfile recorded 36,732 calls, with
3 ms cumulative in the application forwarder. Allocation-capture wall/process
CPU: 87.5/86.6 ms. Total allocated bytes 154,709,671; 81,831 events; peak tracked
memory 453,123 bytes. Approximately 118 MB (76.3%) came from asyncio socket-read
buffer handling across the measured client/server/echo connections, not growing
application output history. The relay holds at most a bounded chunk while
detached. No speculative socket-buffer rewrite was attempted for this small
workload. Slow-client, parallel owner and long-running detach/handoff workloads
are the concrete next profiling steps before release.

Raw captures, profiler tooling, synthetic databases and disposable probe scripts
were removed after analysis. Only these measurements and limitations are kept.
