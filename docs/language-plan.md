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

## Current implementation checkpoint

The three follow-up areas have working, tested implementations:

1. Concrete enum payload layouts, exhaustive match, and explicit monomorphized
   function/struct/enum generics; imported Result and Option packages.
2. Move-only owners, managed allocation, nested deterministic destruction across
   all five engines, conservative branch/loop checks, modular borrowed-return
   contracts and REPL error recovery. Exclusive scoped loans and tracked slices
   (including owned arrays/elements) work in functions and persist across REPL
   inputs. REPL imports share normal module resolution and checksum policy.
   Bounded session resources and general nested borrowed storage remain
   explicit release work.
3. Source packages for slices, strings, checked arithmetic, owning chunked vectors,
   binary files and process arguments. The production compiler now uses new
   syntax and compiles itself: three generations of LLVM IR and two generations
   of native executables are byte-identical. The copied executable works without
   a legacy loader or seed. C is limited to platform/runtime services.

Validation: `make test`, `make bootstrap-check`, `make selfhost-check`, and
`make stdlib-test` pass. The legacy suite includes 1,703 ARM64/x86-64 executable
comparisons; the new-language suite includes 34 differential programs at LLVM
O0/O2 plus ownership, C ABI, standard-library, package and REPL coverage.

This does not close every item in the broader required end state above. Methods,
full scoped loan tracking, language-server services, Go-scale standard-library
coverage, module proxies/pseudo-versions, non-macOS new-language hosts and lower
CLI orchestration overhead remain separate outstanding work. There is no claim
that raw pointers or C interop are memory-safe.
