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
Python startup and dependency checks still dominate small workloads. Real
application workloads, external-module costs and in-session invalidation need
further measurement before the 1.0 performance gate can close.

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
