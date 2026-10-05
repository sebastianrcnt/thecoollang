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
