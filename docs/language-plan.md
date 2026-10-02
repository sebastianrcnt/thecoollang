# Cool language implementation contract

This work implements the design agreed in the conversation. The legacy compiler
is the bootstrap tool, not an implementation of the new language specification.
Compiler language: Cool. Host/platform adapters may use C/assembly. Python may
orchestrate builds, dependency fetching and tests; it must not implement the parser,
type checker, interpreter or code generator.

## Required end state

- `fn`, `let`, `var`, name/type declarations; explicit calls and conversions.
- Static typing, inference inside functions, numeric types, structs, enums,
  arrays/slices/pointers, generics, methods and controlled unsafe operations.
- Explicit allocation, defer, move-only owners, Result handling.
- Directory packages, visibility, cycle checks, no import initialization effects.
- Go-like modules/MVS/checksums, local replacement, workspaces and offline builds.
- Shared typed representation for interpretation, native JIT and LLVM AOT/JIT.
- Incremental function compilation, dependency invalidation, consistent redefinition.
- Native C ABI, runtime/standard library, standalone output.
- Formatter, diagnostics, REPL, tests, docs and language server.
- New-language self-hosting, reproducible bootstrap, conformance and timing tests.

Every implementation commit must describe its tested coverage. Missing features
must produce diagnostics rather than silently selecting different semantics.
This file records the full requested scope; implementing a subset does not mean
the end state is complete.
