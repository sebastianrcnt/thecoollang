# New-language compiler

The lexer, parser, type checker, interpreter and LLVM emitter are written in
bootstrap Cool (`*.cool`). `runtime.c` supplies LLVM program IO, numeric checks and raw memory services;
`ffi.h` adapts scalar/pointer C calls through libffi. No source-to-C compilation is used.

```sh
make language-test
build/coolc --run build/language.BIN run examples/modern.cool
build/coolc --run build/language.BIN llvm examples/modern.cool build/modern.ll
clang -O2 build/modern.ll language/runtime.c -o build/modern
```

Current scalar core: `fn`, `let`/`var`, explicit parameter/result types, `i64`,
`i32`, `u8`, `bool`, `string`, explicit integer casts, forward calls, recursion,
lexical scope, immutable bindings/parameters, `if`/`else`, `while`, `for`, `break`,
`continue`, short-circuit boolean expressions and captured-argument `defer`.
Every local requires initialization. Non-void functions must return on every
statically reachable path. Ordinary integer arithmetic wraps to its type width;
division and shift errors are checked in both execution paths. String values
currently refer to immutable literals; no ownership claim is made.

`defer` evaluates call arguments at registration and runs calls in reverse order
on normal block exit, return, break and continue. Panic/runtime failure terminates
the process and does not promise cleanup.

This is an implementation stage, not the full language: generic specialization,
ownership checking and the complete runtime are still pending.
The new frontend is
written in existing Cool; new-syntax self-hosting is not yet achieved.

## Additional execution paths and projects

`cool run` uses adaptive bytecode/native execution, compiled lazily per function.
`cool run --backend jit` compiles that bytecode to ARM64 native arithmetic and
branches; checked operations and calls use shared runtime helpers. Functions
with register files too large for baseline encodings fall back to bytecode.
`--backend tree` retains the tree evaluator for differential testing;
`--backend llvm` runs a cached native executable, and `--backend llvm-jit` uses
LLVM's lli with the runtime library (set COOL_LLI if it is not on PATH).

The driver delegates source metadata discovery to the Cool lexer. Directory
packages support aliases, public/private functions, forward declarations across
files and cycle rejection. `cool.mod` supports semantic-version requirements and
local replacement; the module graph uses MVS and records verified tree hashes in
`cool.sum`. Local workspaces and offline/frozen resolution are supported.
Direct fetching currently supports host/owner/repo Git repositories and tagged
versions. `mod tidy` records selected module versions; `mod vendor` includes the source
graph and version manifests needed for offline MVS. Commit pseudo-versions and
registry/proxy protocol are pending. `cool.sum` protects pinned content; no transparency service exists.

`cool legacy ...` retains the original CLI for bootstrap-era source files.

## Persistent session

`cool repl` supports persistent scalar bindings, expressions, imports of std/io,
function/struct definitions and same-signature function body replacement. `:stats` reports actual
bytecode/native compilation counters; `:quit` exits. Functions start in bytecode
and become baseline native code on the fourth call (`run --backend auto`, default).
Call sites dispatch through stable function IDs, so a changed callee is replaced
without recompiling callers. No inlining is done by this baseline tier.

Invalid declarations roll back the symbol table and token cursor. Runtime side
effects are not transactional. Signature changes require a new session. External
package loading inside REPL, aggregate layout changes, concurrent redefinition,
completion and source-history memory reclamation are not implemented yet. The
session currently has explicit token/function/depth limits.

## Numeric and developer tools coverage

The scalar core now supports signed/unsigned 8/16/32/64-bit integers, 64-bit
isize/usize on supported execution hosts, f32/f64 and explicit numeric casts.
Floating-point operations preserve IEEE comparisons (including NaN); conversion
to an out-of-range integer is a runtime error. f32 values are rounded at casts
and arithmetic operations. Wide unsigned literals and signed minimum i64 are
accepted. Integer arithmetic wraps; constant/runtime shift counts are checked
against the operand width.

`cool fmt [--check|--diff] paths...` preserves comments and literal token spelling,
relexes its output before writing, and is idempotence-tested. `cool test` discovers
`test_` functions in directory packages including `_test.cool` files; `--backend
jit` runs them under native JIT. `cool doc` prints public typed function signatures.
Documentation comments, a full documentation site and language-server services
remain outstanding.

## Raw memory and C interoperability

Typed `*T` pointers, `null`, `cast[*T](value)`, `&variable`, dereference and pointer indexing
are implemented across all execution paths. Pointer arithmetic scales by element
size. Raw loads/stores check null, but do not promise allocation bounds or lifetime
safety. `std/mem` exposes alloc/free/copy. Unsafe operations require a lexical
`unsafe { ... }` block, including casts and C calls.

`extern "C" fn strlen(s: *u8) -> usize;` declares a C function. Interpreter and
baseline JIT use a libffi host adapter; LLVM emits native C ABI calls with proper
scalar conversions. Only scalar/pointer arguments and results are supported;
variadic C functions, aggregate ABI and user-specified library linking are pending.
The C symbols must be available to the selected execution engine.

Addresses of mutable locals use their native scalar representation, including
f32 and narrow integers, so C output-pointer parameters work. Immutable bindings
and parameters cannot yield mutable addresses. Local addresses must not escape
their function lifetime; this is an unsafe obligation, not an ownership proof.
REPL local storage is stable and capped at 65,536 registers.

## Timing measurements

`make benchmark` measures checking, each execution path, LLVM cold/cached builds
and a persistent-session replacement workload. Setup is excluded; every reported
measurement includes process startup. JSON samples go to
`build/language-benchmark.json`; no hardware-dependent pass threshold is imposed.

On the development Apple Silicon Mac, five-sample medians for summing integers
from 0 through 9,999 were approximately 3.4 ms for direct frontend checking,
3.0 ms for cold baseline JIT plus execution, and 88 ms for `cool run` including
the Python driver. LLVM build medians were 128 ms cold and 99 ms cached; the built
executable including startup took 2.7 ms. These are small-workload measurements,
not large-project throughput or in-process incremental compilation latency.
The driver overhead remains a performance task.

## Structs, arrays and borrowed slices

```cool
struct Point { x: i32; y: f32; }
fn offset(p: Point) -> Point {
    var copy = p;
    copy.x = copy.x + 1;
    return copy;
}
fn fill(values: []i32) { values[0] = 42; }
fn main() {
    var points = [2]Point{Point{x: 1, y: f32(2.5)}, Point{x: 2, y: f32(3.5)}};
    let snapshot = points;
    points[0] = offset(points[0]);
    var numbers = [3]i32{1, 2, 3};
    fill(numbers[1:]);
}
```

- Structs and fixed arrays have value semantics for bindings, assignment,
  arguments, returns and captured defer arguments. Evaluation snapshots values
  before later arguments or deferred calls can mutate the source. Nested arrays
  and structs are supported. All initializer elements are required; an explicit
  empty initializer (`Point{}` or `[3]i32{}`) zero-initializes the entire value.
- Array types are `[N]T`; slice types are `[]T`. `len(value)` works on either.
  `sizeof(T)` reports the byte layout. Scalar field alignment follows native
  widths, with padding between fields and at the end of structs. Empty structs
  have size zero; do not assume their layout is a standard C struct.
- `array[low:high]` and `slice[low:high]` create views with an exclusive upper bound;
  omitted bounds use zero and length. Indexing and slicing check bounds in every
  execution engine, including optimized LLVM. Slice writes update the source;
  array/struct assignment copies into existing storage, preserving live views.
- Safe mutable slices require a `var` array. `let` aggregate values and aggregate
  parameters cannot be mutated directly. A `let` slice freezes the descriptor,
  while its referenced array remains writable, as with a pointer's pointee.
- Values and temporary copies occupy fixed function-frame storage; repeated
  loop execution does not allocate an ever-growing list of aggregate temporaries.
  Aggregate returns copy into caller-owned storage before the callee frame ends.
  Current limits are 512 KiB per aggregate and 65,536 storage slots per function;
  baseline JIT falls back to bytecode for large register files.
- Slices borrow storage; no GC or reference counting was introduced. Function
  parameters may accept slices, but returning a slice or a value containing one
  is rejected until lifetime analysis exists. Mutable slice elements cannot contain
  further slices, which prevents storing a local borrow into caller-owned storage.
  Slice growth/append, dynamic arrays
  and owning containers are not implemented. Unsafe pointers retain manual
  lifetime obligations.
- `pub struct` and `pub` fields expose package APIs. Nominal types and layouts are
  collected before function signatures, permitting forward declarations and
  recursive pointers. By-value layout cycles are rejected. REPL layouts cannot
  be redefined, and failed declarations roll back new type registrations. Runtime
  failure retains storage that surviving REPL views may still reference.
- Raw pointers to aggregates work with C ABI calls. Aggregate arguments/results
  by value at the C boundary remain explicitly unsupported.

`examples/aggregates.cool` demonstrates independent array copies and shared slice
views. `make aggregate-test` checks bounds, package visibility, LLVM JIT, tools
and REPL behavior in addition to the differential cases in `language-test`.
