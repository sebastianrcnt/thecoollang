# New-language compiler

The lexer, parser, type checker, interpreter and LLVM emitter are written in
bootstrap Cool (`*.cool`). `runtime.c` supplies only LLVM program IO and checked
integer division/shift operations. No source-to-C compilation is used.

```sh
make language-test
build/coolc --run build/language.BIN run examples/modern.cool
build/coolc --run build/language.BIN llvm examples/modern.cool build/modern.ll
clang -O2 build/modern.ll language/runtime.c -o build/modern
```

Current scalar core: `fn`, `let`/`var`, explicit parameter/result types, `i64`,
`i32`, `u8`, `bool`, `string`, explicit integer casts, forward calls, recursion,
lexical scope, immutable bindings/parameters, `if`/`else`, `while`, `break`,
`continue`, short-circuit boolean expressions and captured-argument `defer`.
Every local requires initialization. Non-void functions must return on every
statically reachable path. Ordinary integer arithmetic wraps to its type width;
division and shift errors are checked in both execution paths. String values
currently refer to immutable literals; no ownership claim is made.

`defer` evaluates call arguments at registration and runs calls in reverse order
on normal block exit, return, break and continue. Panic/runtime failure terminates
the process and does not promise cleanup.

This is an implementation stage, not the full language: aggregate types, generic
specialization, ownership checking and the complete runtime are still pending.
The interpreter currently executes typed trees, not bytecode. The new frontend is
written in existing Cool; new-syntax self-hosting is not yet achieved.

## Additional execution paths and projects

`cool run` now uses typed register bytecode, compiled lazily per function.
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
versions. Commit pseudo-versions, registry/proxy protocol, vendor and tidy commands
are pending. `cool.sum` protects pinned content; no transparency service exists.

`cool legacy ...` retains the original CLI for bootstrap-era source files.

## Persistent session

`cool repl` supports persistent scalar bindings, expressions, imports of std/io,
function definitions and same-signature body replacement. `:stats` reports actual
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
