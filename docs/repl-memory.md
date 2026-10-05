# REPL lifecycle audit and memory accounting

This inventory describes the current implementation and a focused development
regression. It does not declare the complete G6 release gate closed or prove the
absence of memory leaks, dangling storage or other lifetime defects.

## Resource inventory

| Resource | Retained roots / lifetime | Commit and rollback behavior |
| --- | --- | --- |
| Compiler state and fixed token/function/type/session tables | One frontend process; implementation capacity limits | Not allocated once per submission; released by process termination |
| Token spelling/raw buffers and partial lexer text | Live declaration source blocks, import aliases and nominal templates/types | Disposable statement tokens and failed declarations are freed; partial lexer text is freed on recovery |
| Source block records | Functions and their AST token references; blocks with aliases or nominal declarations are pinned | Replacement history is reclaimed after commit/frame cleanup; retained token coordinates are relocated before compaction |
| Function AST/local/drop/bytecode pools and JIT mappings | Current function definitions, generic specializations and live callers dispatching by function ID | Replaced products are freed after user frames finish; rejected replacement products are freed before restoring the function snapshot |
| Parser/resolver/move/type-binding scratch | Current submission, including nonlocal recovery | Registered buffers are released after checking/execution/recovery; scratch-list records are released too |
| Lazy layout field lists and transaction journal | Current type descriptors; journal entries only for previously existing layouts changed during a submission | Rollback frees new field lists and restores old descriptors; newly allocated descriptors' fields are freed before type-ID reuse; commit releases journal records |
| Alias and package registration nodes | Accepted imports and loaded packages | Failed loads/definitions free registrations before restoring previous heads; accepted aliases/packs retain their source dependencies |
| Session locals and borrowed identities | Visible bindings plus live loan roots/holders/parents | Forgotten/dead interior and tail storage can be reused; provenance identities required by surviving loans remain live |
| Owning user values | Live session bindings and active frames | Runtime recovery unwinds user frames before layout rollback; forgetting bindings and session exit drop owners |
| Interned literal text and declared symbols | Stable immutable text for the whole session; equal bytes share storage | Failed compile-only submissions discard newly interned text; executed submissions keep it because values or unsafe pointers may have escaped before a runtime failure |

Fixing source identity or retaining literal bytes does not freeze mutable user
contents. A runtime error may occur after a write to a surviving value. Freeing
all literals introduced by that executed submission would create dangling
storage. Conversely a compile-only rejected definition has not executed and its
new literal/symbol entries can be discarded.

Type descriptors and successful generic specializations remain session caches,
with explicit implementation limits. This audit does not establish garbage
collection of unused structural type identities or cached specializations. New
nominal declarations, accepted aliases, distinct literals and distinct successful
specializations can increase session retention; a fixed-history workload with
stable identities is a different claim from constant memory for arbitrary new
program definitions. No unsafe reclamation of potentially escaped literal text
was introduced by this audit.

## Focused allocation regression

```sh
python3 tools/test_repl_lifecycle.py --counts 64 1024 \
  --output build/repl-lifecycle-audit.json
```

The test copies already emitted `compiler-stage2.ll`, `compiler-host.o` and the
runtime object into a private directory. Their SHA256 identities must match the
originals during capture. It replaces only emitted IR call targets for `CAlloc`,
`StrNew`, `FileRead` and `Free` with diagnostic C wrappers and links a private
frontend. It never regenerates compiler source/IR, invokes make or changes shared
build artifacts. The shim's own bookkeeping uses separate host `malloc` storage.
This is instrumented diagnostic execution, not a production RSS measurement or
compiler-speed benchmark.

A fresh process executes each workload/count pair. The report includes final
tracked live bytes/count, peak tracked bytes and live allocation-size histograms,
after the REPL exits and drops user values. Fixed tables and surviving compiler
metadata are still counted: the compiler context intentionally lasts until
process termination. Input checking, expected values, diagnostic counts and
owner cleanup are verified independently of allocation counts.

The 16 bounded-history cases cover unique cancelled literals/function names,
invalid nominal declarations, repeated dependent layout failures, partial lexing,
function replacements, generic-call scratch, runtime owner unwinding, cancelled
import aliases, mixed declaration batches, completed existing layout rollback,
source compaction with lazy generic bodies, duplicate declaration rejection,
incomplete local storage allocation, real framed CLI package-import failure,
interior owning-array reuse and poisoned interior-slot runtime failure.
For each case, 64 and 1,024 repetitions must finish with exactly equal tracked
live bytes and allocation count. The distinct-literal runtime-error workload is
an explicit policy control: its retention grows and is not asserted constant.

This comparison detects obsolete-history growth in these particular programs.
Equal totals are not a leak proof: untracked allocation paths can leak, a leak
could be balanced by an incorrect free elsewhere, and a dangling access might not
change totals. Functional outputs and the existing sanitizer/runtime suites
remain necessary. The test does not replace those suites or verify every legal
REPL input.

Coverage includes compiler IR calls to the listed allocators and `FileRead`
returns with a size-output pointer. Other host-internal allocations (including
the host compiler-state singleton, resolver and FFI machinery), JIT executable
mappings, Python resolver memory/disk caches and allocations reached through
foreign symbol lookup are outside this accounting. Peak tracked bytes are not
peak resident memory and include large fixed tables. Concurrent machine load
can affect execution time but is not used to infer allocation counts.

## Audit result

The focused observations found no accumulating tracked allocations in the 16
bounded-history cases, including rejected package loads with source-file buffers.
The executed distinct-literal control grows according to the documented session
lifetime policy. No production reclamation change was made because these
observations did not reproduce a missing release or an incorrect free. The raw
local report records the exact instrumented artifact identities; broader host/JIT
accounting, successful specialization-cache retention and the full G6 acceptance
assessment remain separate work.

## Host and JIT mapping audit

The Apple Silicon host's `NativeCompilerState` allocates its context once and
retains that singleton for the process. The resolver adapter in `repl_io.h`
reuses a static 65,536-byte response buffer. The FFI adapter in `ffi.h` uses
stack argument arrays and a stack `ffi_cif`, resolves foreign symbols through
`dlsym(RTLD_DEFAULT)` and has no adapter-owned `dlopen` handles or closure cache.
These observations do not account for allocations inside libffi, dyld, foreign
functions or the Python module resolver.

Each executable JIT mapping belongs to a `Function.machine/machine_size` pair.
After user frames return/unwind, `FreeFunctionChanges` frees mappings replaced
by a committed definition or created in a rejected transaction. Recoverable
branch-range errors in `CompileNative` occur before allocating executable memory.
Existing JIT mappings survive failed calls so their previously committed code
remains usable. The CLI returns from Main after Repl; surviving current code and
compiler metadata have process lifetime. There is no reusable embedded-session
teardown contract yet.

```sh
make repl-jit-lifecycle-test
# Larger/alternative counts and a separate report:
python3 tools/test_repl_jit_lifecycle.py --counts 64 1024 \
  --output build/repl-jit-lifecycle-audit.json
```

This independent diagnostic frontend copies the same emitted IR/host/runtime
snapshot and wraps `NativeJitAlloc/Free`. It records mapping addresses, requested
sizes and host-page-rounded live bytes. Unknown/double frees, duplicate live
addresses, nonpositive requests and mismatched release sizes fail immediately.
Expected user output, assertion diagnostics and zero user owners are checked
separately. The four workloads have exact allocation/release expectations:

| History | Allocations after n repetitions | Releases | Current mappings |
| --- | ---: | ---: | ---: |
| Warm callee replacement with a live JIT caller | n + 2 | n | 2 |
| Cold/new JIT rolled back on runtime failure | n | n | 0 |
| New JIT rollback retaining earlier bytecode | n | n | 0 |
| Runtime failure retaining existing JIT | 1 | 0 | 1 |

At 64 and 1,024 repetitions, final mapping counts, requested sizes and rounded
live bytes must agree for each history. Addresses naturally vary across fresh
processes; the JSON report records them as diagnostic data, with artifact SHA256
identities. Current mappings are intentionally counted at exit; asserting zero
would confuse retained live code with obsolete replacement history.

This measures executable mapping ownership on these paths. It does not measure
RSS, all compiler/host heap allocations, every legal session or dangling accesses.
The heap lifecycle audit and sanitizer suites remain separate complementary
checks. No production change was needed: these workloads reproduced neither
obsolete mapping growth nor an invalid release. Whole G6 acceptance still needs
an assessment of all resource policies and unsupported session operations.

## Fragmented local storage

The session allocator now excludes persistent binding ranges and all named or
anonymous reservations in the current input, then reuses the earliest fitting
gap. Range metadata is transaction scratch and is reclaimed after success/error.
Execution zeroes new ranges before any initializer can fail. Live values never
move; `:forget` checks dependent loans before releasing a binding. The hole tests
and two additional fixed-history heap-accounting workloads exercise reuse,
rollback and drop-descriptor cleanup. This is contiguous slot reuse, not moving
compaction: a request larger than every free contiguous gap can still fail even
when the sum of free slots would suffice. Lifetime-free raw pointers must not be
used after their source binding is forgotten.
