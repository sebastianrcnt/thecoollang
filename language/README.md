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
