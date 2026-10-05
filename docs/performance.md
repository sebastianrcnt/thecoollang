# Compiler and driver measurements

The Cool frontend and the Python project driver have different costs. The driver
resolves packages, scans imports, checks build dependencies and manages caches;
the Cool frontend performs all language parsing, checking and code generation.
Do not describe cached import metadata as incremental compilation.

The driver now loads module/archive machinery only when needed, hashes the
frontend once per invocation, and scans all uncached files in one directory
package with one `scan-bundle` frontend process. Metadata remains keyed by source
and frontend contents. Directory membership is rediscovered on every invocation.
Native artifact identities also include the linked runtime object's contents,
so rebuilding that object invalidates previously linked output. Existing `make`
checks remain in place; no timestamp-only shortcut was introduced.

## Measured change

Apple Silicon macOS, five repetitions; values are median wall-clock milliseconds.
The complete samples, platform and workload details are in
[driver-optimization-arm64.json](benchmarks/driver-optimization-arm64.json).
Baseline driver revision: `c04efde`.

| Workload | Before | After |
| --- | ---: | ---: |
| Single-file adaptive run, including driver/build checks | 97.661 | 83.991 |
| Single-file cold LLVM build | 132.428 | 112.819 |
| Single-file cached LLVM build | 98.435 | 87.132 |
| 257-file package check, cold metadata cache | 591.542 | 119.467 |
| Same package, warm metadata cache | 125.147 | 89.163 |
| Same package, one source file changed | 124.956 | 90.026 |

Single-file measurements use the existing integer-sum workload and include
process startup and normal build checks. Package measurements use a synthetic
directory of integer-loop functions and include Python startup, metadata and a
full frontend check. Both package drivers use the same explicit `COOL_FRONTEND`,
so these rows exclude `make`. Cold runs clear only metadata before each sample;
one-file-change runs use new contents each time. Setup time is excluded.

These samples are local observations, not cross-platform latency guarantees.
Python startup and dependency checks still dominate small workloads. The application and in-session measurements below extend this evidence.
External tagged-module download costs and release-wide acceptance remain
separate from these local timings.

## Reproduction and correctness

```sh
python3 tools/bench_language.py --repeats 5 --output build/small.json
python3 tools/bench_driver.py --files 256 --repeats 5 --output build/package.json
make driver-cache-test project-test developer-tools-test selfhost-check
```

For a comparison, `bench_driver.py --driver PATH` accepts a prior driver snapshot
with its matching `modules.py`. It uses the current frontend for both drivers.
The committed report compares those controlled package runs.

`driver-cache-test` checks one scan per cold package, warm cache hits, content
changes with preserved mtimes, file creation/removal, changed imports, frontend
replacement and concurrent cache readers. It compares batch and individual scan
records on both frontend generations, including empty and Unicode-named paths.
An isolated runtime rebuild changes native program behavior while preserving
object mtime and verifies that the cached binary is invalidated. Project tests
also exercise package visibility, import cycles, dependency changes, MVS,
offline checksums and LLVM execution.


## Stateful project workload

`tools/test_repl_project.py` uses the shipped Tally directory module and compares
its map updates and JSON files to an independent seeded Python model. It keeps
user state while replacing a called function, warming JIT callers, rejecting
invalid definitions/borrow conflicts and recovering from runtime errors after
writes. Every frontend must release all user owners when the state is forgotten.

On macOS, `--rss-output report.json` measures the frontend process with `time -l`,
excluding the Python package resolver. `--rounds 128` performs 4,096 updates;
`--rounds 1024` performs 32,768. Each report contains a single fresh-process
observation per frontend, including cold compilation. Repeat whole runs to obtain
a distribution; do not describe one report as a median or an isolated speed test.
The optional `--frontend` adds an instrumented compiler; its memory must be
reported separately from the production and bootstrap frontends.

## Application, larger build and acknowledged edit measurements

`tools/bench_project.py` measures the shipped Tally application, with its actual
map/text/vector/JSON/filesystem dependencies, and a larger variant that adds 512
ordinary loop functions to the application's directory. This variant increases
compiler/build size; it does not represent 512 independent real application
features. Both O2 executables process 40 Unicode, empty and repeated labels and
must write exactly the JSON counts computed by Python's `Counter`.

Seven fresh-process repetitions on Apple Silicon macOS, after concurrent release
regression tests finished, use the same frontend binary SHA256
`432ed782037dad8fe66345297cb76496cd86bed6f9b0ccff7a581680fcfcd913`.
The raw distributions and environment are published in
[project-before-arm64.json](benchmarks/project-before-arm64.json) and
[project-after-arm64.json](benchmarks/project-after-arm64.json).
These sequential local observations do not establish a statistical confidence
interval or guarantee performance on other hosts.

| Workload (median ms) | Tally | Tally + 512 functions |
| --- | ---: | ---: |
| Sources / packages / source bytes | 14 / 11 / 57,790 | 526 / 11 / 110,928 |
| Direct frontend check, prepared manifest | 15.754 | 40.228 |
| Direct frontend LLVM emission | 24.037 | 53.956 |
| Clang O2 optimization and linking of emitted IR | 238.240 | 302.638 |
| CLI check, cold scan metadata | 109.848 | 214.920 |
| CLI check, warm scan metadata | 83.219 | 121.029 |
| CLI check after one file content edit | 85.622 | 124.052 |
| Direct frontend check after one file content edit | 15.887 | 42.537 |

Direct frontend and clang rows include their respective process startup and are
separate stages, not full-build end-to-end totals. Preparation and oracle checks
are outside their timers. CLI rows include Python startup, module resolution,
directory discovery, reading and hashing source contents, metadata handling and
a full frontend check. An explicit `COOL_FRONTEND` excludes automatic toolchain
`make` checks; ordinary CLI invocations without that override still pay them.
One-file edits append a unique comment before each sample. They invalidate scan
metadata but do not change semantics; the entire graph is parsed and checked.
The clang rows use the existing runtime object, whose digest is in the report;
they exclude runtime-object rebuild time and driver artifact caching.

The warm larger-project cost exposed repeated metadata-file opens. The driver
now keeps one atomic JSON snapshot per directory/frontend identity, containing
only that directory's current content-keyed records. Every invocation still
rediscovers membership and reads/hashes source contents. Missing records fall
back to the original per-file cache and then Cool scanning; previous cache
formats remain usable, edits need only scan changed files, and reverted contents
can reuse old per-file records. Snapshot metadata is parsed with the same package
validation as individual records; malformed JSON or record types fail explicitly.
The snapshot does not cache typechecking or machine code.

| CLI check median ms | Before | After |
| --- | ---: | ---: |
| Tally warm | 84.313 | 83.219 |
| Expanded Tally warm | 133.253 | 121.029 |
| Expanded Tally one-file edit | 135.125 | 124.052 |
| Expanded Tally cold metadata | 219.132 | 214.920 |

The useful measured change is the approximately 9% warm and 8% one-file-edit
reduction in this larger workload. Cold performance remains dominated by source
scanning, individual cache writes and process orchestration. Python startup and
module handling still dominate small-project CLI checks; frontend checking grows
with total graph size. This is a bounded overhead improvement, not evidence of
incremental typechecking.

### Stateful editing without restarting the process

Each of seven sessions launches the project CLI and waits for a checked numeric
acknowledgment. It then separately times importing Tally's `ledger`, initial
compilation/calling of an updater with a persistent owning `Book`, and 64 valid
callee replacements followed by a call through an already warmed caller. These
448 replacement samples have median 1.221 ms (the raw values remain grouped by
session in the report). Median launch-to-first-acknowledgment is 67.927 ms,
package import acknowledgment 15.401 ms, and initial function compilation/call
1.390 ms. The import resolves and loads the real dependency graph; the first
call instantiates the used generic library paths.

Each acknowledgment includes pipe transport, frontend parsing/dispatch and the
called expression; it is not an isolated JIT compiler timer. Session samples are
correlated, so 448 observations should not be described as 448 independent
fresh processes. After replacement, an independent arithmetic model checks every
returned count and the final map lookup. Forgetting the book must leave zero
owners, and the session must have no diagnostics and valid compiler statistics.
The existing `test_repl_project.py` additionally supplies rejection, borrower,
runtime-error and JSON-checkpoint recovery coverage; this timing harness isolates
the successful edit path rather than timing that entire adversarial test.

```sh
# Build beforehand, outside measurement; the benchmark itself never runs make.
python3 tools/bench_project.py --repeats 7 --files 512 --replacements 64 \
  --output build/project-performance.json
python3 tools/test_driver_cache.py
```

Use `--frontend PATH` to pin a copied stable executable while other development
continues. The harness rejects a frontend content change during a run. The
existing cache test passes after this optimization, including same-mtime edits,
creation/removal, imports, frontend replacement, concurrent readers, both
frontend scan formats and an isolated runtime rebuild that invalidates native
artifacts. G8's remaining release assessment must consider these boundaries and
the broader representative-workload scope; these numbers alone do not certify
the whole 1.0 release.

## Default development CLI with real dependency checks

The separate `--default-cli` mode measures normal development CLI invocation
without `COOL_FRONTEND`. It captures an independent source checkout containing
actual Makefile/toolchain dependencies, standard libraries and already built
frontend/runtime artifacts. Source/artifact SHA256 and mtimes must match the
original checkout across capture. `make -q` must confirm that the copied frontend
and runtime are up to date before any sample is taken. This prevents an accidental
compiler rebuild from being reported as normal invocation overhead.

Timed default CLI calls use the actual driver lock and `make` dependency checks.
The original checkout may change after capture without affecting this fixture;
artifact hashes are checked after every sample. Source inventory, captured
revision, artifact identities and raw values are recorded in the JSON report.
Snapshot preparation, correctness checks and artifact hashing are outside timers.
The snapshot preserves dependency timestamps rather than setting artificial
future timestamps or substituting a trivial Makefile.

The mode measures cold/warm metadata and one-file-edit checking/default execution,
cold/cached/one-file-edit optimized native builds, and cached LLVM execution.
Native cold samples clear only the artifact cache; metadata remains warm. Edits
append unique comments, so they change content identities while preserving the
expected program output. They still perform a full frontend compile, including
unused functions in the expanded workload. Native build samples include output
copying; their execution oracle is outside the timer. Run samples include program
execution and JSON file output. All 40-label outputs must match Python Counter.

Alternating paired warm checks compare the default invocation and an explicit
frontend invocation in the same snapshot, with identical source/cache contents.
Their observed difference includes dependency checks and the driver's override
branch; it is not a compiler speedup or an isolated `make` microbenchmark.
Separate real `make -s` frontend/runtime up-to-date samples give additional context.
The real Tally application and its synthetic 512-function size extension remain
separate workloads; the extension is not evidence of broader application coverage.

```sh
python3 tools/bench_project.py --default-cli --repeats 7 --files 512 \
  --output build/default-cli-performance.json
```

The host must have completed its build beforehand. If snapshot files change
during capture, or real dependencies are stale, the harness fails and requires a
fresh capture after the build completes. Default invocation costs during an
actual compiler-source edit/rebuild are intentionally outside these observations.

Seven repetitions of this mode on Apple Silicon macOS are published in
[default-cli-arm64.json](benchmarks/default-cli-arm64.json). The captured frontend
SHA256 is `0f72540478d9af1a93593ad5a003cd4f7a0f1d2800a6746886f9f6a9d36026e4`;
the report records 371 source/artifact content and timestamp entries. This is a
later compiler revision than the earlier isolated frontend measurements above.
Compare the paired checks within this report when assessing dependency-check
cost, rather than attributing differences between revisions to `make` alone.

| Default CLI workload (median ms) | Tally | Tally + 512 functions |
| --- | ---: | ---: |
| Check, cold metadata | 136.373 | 249.496 |
| Check, warm metadata | 106.381 | 147.630 |
| Check, one-file edit | 109.233 | 147.487 |
| Default adaptive run, cold metadata | 162.670 | 277.834 |
| Default adaptive run, warm metadata | 133.488 | 172.254 |
| Default adaptive run, one-file edit | 137.642 | 175.656 |
| O2 build, cold native artifact | 414.439 | 511.995 |
| O2 build, cached native artifact | 105.067 | 121.149 |
| O2 build, one-file edit | 389.601 | 511.109 |
| LLVM run, cached native artifact | 104.807 | 124.468 |

The 14-source real app and 526-source expanded corpus each use 11 packages. The
LLVM run uses the driver's default O0 artifact, primed separately outside the
timer; the O2 build uses its distinct optimization-keyed artifact. A native cache
hit still performs source/metadata discovery, runtime/frontend dependency checks,
artifact hashing and a `clang --version` process. A comment-only edit invalidates
the native artifact even though output semantics remain the same.

Within-snapshot alternating pairs observe a median default-minus-explicit warm
check difference of 14.575 ms for Tally and 13.296 ms for the expanded corpus.
Direct frontend up-to-date `make` observations have median 11.414 ms; runtime
up-to-date checks 6.936 ms; `clang --version` processes 7.503 ms. These observations
identify concrete remaining orchestration costs. They are not additive predicted
speedups: paired invocation differences include driver locking and branch costs,
and microbenchmark timings occur in different call contexts.

Those observations motivated combining the native command's frontend/runtime
up-to-date checks into one locked `make` invocation, measured below. Avoiding
repeated toolchain-version queries would require a correctly invalidated Clang
identity cache; that remains an unimplemented proposal with no predicted speedup
claim. Cold native optimization/linking and full-graph checking still remain
outside true incremental compilation.

### Batched native dependency checks: measured change

The default native build and LLVM execution paths now check the frontend and
runtime object together in one locked `make` invocation. An explicit
`COOL_FRONTEND` still checks only the runtime object; ordinary check/adaptive
execution keeps its frontend-only check. The underlying Makefile rules and
native artifact content identities continue to decide rebuilds and cache hits.

Seven repetitions with the same `--default-cli --files 512` options are in
[default-cli-batched-before-arm64.json](benchmarks/default-cli-batched-before-arm64.json)
and
[default-cli-batched-after-arm64.json](benchmarks/default-cli-batched-after-arm64.json).
Both captures use frontend SHA256
`5a338e3e1ae8d524b2e8bad93ee4b7aaa9a1367ab8838c57822001744dc3d742`,
the same runtime digest and identical workload sizes. Comparing full captured
inventories shows only `tools/cool` and its cache regression test changed;
compiler, libraries, build artifacts and benchmark implementation are identical.
Each capture independently verifies real up-to-date dependencies and every
program output/artifact digest. No compiler/runtime rebuild or concurrent heavy
release check is included in these observations.

| Default native workload (median ms) | Tally before | Tally after | Expanded before | Expanded after |
| --- | ---: | ---: | ---: | ---: |
| O2 build, cold native artifact | 387.139 | 381.335 | 515.879 | 503.863 |
| O2 build, cached native artifact | 103.063 | 95.269 | 121.760 | 113.160 |
| O2 build, one-file edit | 408.398 | 385.205 | 512.630 | 502.208 |
| LLVM run, cached native artifact | 111.878 | 97.377 | 124.750 | 115.235 |
| Warm check (unchanged dependency path) | 104.710 | 103.681 | 147.303 | 145.434 |

The cached O2 build medians decrease by 7.794 ms (7.6%) for Tally and 8.600 ms
(7.1%) for the expanded corpus. Their seven-sample before/after ranges do not
overlap in this local observation. Cached LLVM execution medians also decrease,
by 14.501 and 9.516 ms respectively; those end-to-end measurements include program
execution/file output, so their whole difference is not an isolated dependency
checker speedup. Warm-check control medians differ by 1.029 and 1.869 ms.

Cold and edited native builds include Clang optimization/linking and show wider
variation. In particular the Tally edit baseline includes a 466.348 ms sample
and has a 23.192 ms median difference; that larger difference should not be
attributed entirely to eliminating one make invocation. Cold-build sample ranges
overlap. These sequential seven-sample measurements establish a useful local
cached-command improvement, not a general latency guarantee or a confidence
interval across hosts and workloads.

The driver-cache regression passes with checks that native commands issue one
make call for both targets, check retains its frontend-only target, and an
explicit frontend does not generate a checkout frontend. It also changes an
actual runtime prerequisite and verifies that make rebuilds the object and that
native output/cache invalidation reflect the change. This optimization reduces
orchestration overhead without certifying incremental typechecking or closing
the wider 1.0 release gates.


### Borrowed type graph traversal

An active recursion path terminated owning cycles but repeatedly explored shared
DAG subgraphs. A borrow-free diamond consisting of two owning fields pointing
at the previous level reproduced exponential work: direct native `check` took
0.527 seconds at depth 16 and exceeded a three-second timeout at depth 20.
These baseline figures are single reproduction observations.

Query-local visited bitmaps now bound each borrowed/mutability traversal by
reachable types and fields. Validation uses an independent bitmap, and storage
checks resolve lazy layouts before inspecting fields. Five fresh-process samples
on the local Apple Silicon host gave median direct `check` times of 3.921 ms at
depth 16, 3.177 ms at depth 24 and 2.999 ms at depth 40. Measurements include
process launch and parsing; the first depth-8 sample was 328.661 ms, so this is
not a general latency guarantee or a controlled statistical speedup estimate.
The raw local capture is `build/release-audit/borrow-graphs-timing.json`.

`make borrow-graphs-test` checks results against independent worklist reachability
and counts property/validation calls in a private instrumented compiler. Each query must satisfy a
structural bound based on graph edges/types; cycles, field permutations and DAGs
are covered. Compiler checks may still make multiple traversals of the same
types across separate queries. This removes exponential work within a query,
without claiming linear overall compilation or closing G8.


## Borrowed-vector storage cost (draft-35 regression)

The draft-35 Vector implementation uses initialized Option[T] slots for both
plain and borrowed T. This removes unsafe zero initialization of reference
slots without per-element heap wrappers, but it increases tag/padding bytes and
adds slot handling. The draft-36 measurements below supersede this implementation.

`python3 tools/bench_vector_storage.py --before-ref 23dbe7d --output
build/vector-storage-benchmark/report.json` builds old/current package copies
with the same compiler at LLVM release O2. Each standalone executable appends
500,000 bytes, traverses them with the raw cursor, checks the independent sum
62,499,028 and explicitly clears the vector. One warm-up precedes seven
alternating samples; durations include process launch. No unrelated validation
was running during the retained sample run.

| Measurement | Before | Option slots |
| --- | ---: | ---: |
| `sizeof(Chunk[u8])` | 48 bytes | 528 bytes |
| Whole-process median | 58.350 ms | 91.655 ms |

Chunk size excludes owner/runtime overhead and is not an RSS measurement.
The approximately 1.57x elapsed-time ratio describes this byte workload only;
it is not a general compiler or collection performance claim. Raw samples,
programs and source/compiler/binary hashes are retained in
[vector-storage-arm64.json](benchmarks/vector-storage-arm64.json). The larger
slot representation especially affects narrow element types. Preserve borrowed
slot initialization and destructor safety while reducing plain-value overhead;
do not revert to uninitialized scoped references to recover performance.


## Narrow Vector storage (draft 36)

One-byte elements now use 48-byte inline chunks. Other T retains the initialized
Option slots required for borrowed values. Separate nullable head owners keep
one allocation per chunk; Vector itself is 32 rather than 24 bytes. The larger
Option initializer is isolated in a chunk-construction helper. Clear detaches
whole chunks from the tail rather than constructing a popped Option for each
removed element, while still dropping every owned payload once with bounded
chunk recursion during explicit clear. Ordinary scope-exit drop still traverses
the owner chain recursively. These changes preserve the public lifetime contracts.

The same 500,000-byte append/raw-cursor/checksum/clear workload, compiler,
release-O2 flags, warm-up and seven alternating samples compare the old plain
storage at 23dbe7d against current storage. The retained run has no unrelated
validation running. Current byte chunk size matches the old 48 bytes; raw
samples and source/compiler/binary hashes are in
[vector-inline-arm64.json](benchmarks/vector-inline-arm64.json).

The final whole-process medians are 58.367 ms for old plain storage and
56.555 ms for current storage. This restores
this workload's earlier elapsed-time range; small differences within that range
are not evidence of a general speedup. It does not close G8 or certify the
performance of larger/borrowed element types. Earlier 528-byte/91.655ms samples
remain above as evidence of the actual regression and its cause.
