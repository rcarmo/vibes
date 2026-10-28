# Keychain CPU and allocation comparison

Command preparation now derives one password key per operation and decrypts only
selected entries. It never caches a key across commands. This removes repeated
scrypt work while retaining the existing scrypt parameters, authentication checks,
configuration-change rejection and command-scoped secret selection.

## Workload

Python 3.12.3, Linux x64; baseline `49c5944`, compared with the `reveal_many`
change in the same checkout/toolchain. One protected keychain with 20 synthetic
entries and 10 stored environment overrides. After initial import/crypto warmup,
prepare 12 commands with eight distinct referenced secrets each; after each
command list the environment and assert selected values. No shell process or
external provider is part of this workload.

CPU capture: cProfile plus process CPU time. Native allocation capture: Memray
1.20.0 with native stacks and Python allocator tracing, in a separate equivalent
run. Allocation totals count allocation events, not live RSS or retained memory.

| Metric | Before | After | Change |
| --- | ---: | ---: | ---: |
| CPU-profile workload wall time | 2.783 s | 0.416 s | -85.1% |
| Process CPU time | 2.821 s | 0.425 s | -84.9% |
| scrypt calls | 96 | 12 | -87.5% |
| Total allocated bytes | 1,661,109,184 | 218,690,400 | -86.8% |
| Allocation events | 395,350 | 132,694 | -66.4% |
| Peak tracked allocation | 16,841,774 bytes | 16,828,895 bytes | -12,879 bytes |
| scrypt allocated bytes | 1,612,666,560 | 201,583,320 | -87.5% |
| Allocation-profile workload wall time | 3.081 s | 0.639 s | -79.3% |
| Maximum event-loop delay, CPU run | 1.54 ms | 2.40 ms | +0.86 ms |
| Maximum event-loop delay, allocation run | 11.11 ms | 10.76 ms | -0.35 ms |

## Analysis

Repeated key derivation accounted for 97.1% of baseline allocation bytes. Each
referenced entry previously called `_key`, repeated scrypt, rechecked key metadata
and made associated SQLite transactions. `reveal_many` deduplicates selected
names, returns immediately for an empty selection and derives/checks once before
reading those entries. Single-entry reveal delegates to the same implementation.

cProfile runs on the event-loop thread and attributes native worker time partly
to polling; its per-function scrypt time alone understates total CPU. Process CPU
time and Memray's worker-thread/native stacks identify the repeated work. Scrypt
still accounts for 92.2% of post-change allocated bytes; one derivation per
protected command is deliberate. Reducing the work factor or retaining a key
across commands was not attempted. The next measurement should cover a realistic
mixed single-/multi-secret shell workload and concurrent sessions.

These are single equivalent before/after captures, not latency percentiles or
cross-machine benchmarks. Scheduling noise affects short event-loop maxima; the
CPU-run increase of 0.86 ms is small relative to 2.37 s less overall wall time,
and the allocation-instrumented run improved its maximum. Peak memory stays near
one scrypt workspace, as expected. No inference-quality or browser claim follows
from these measurements.

Regression tests check no derivation/decryption for an empty command, one
derivation per command despite repeated references/placeholders, exactly selected
entry decryption, no retained key, unchanged password/configuration failures,
collisions and environment precedence. Existing backend tests also pass.

Raw captures, profiler tooling, synthetic databases and disposable probe scripts
are deleted after analysis. Only this comparison is retained.
