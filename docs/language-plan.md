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

The production compiler is new-syntax Cool and compiles itself to LLVM IR and a
native executable. The bootstrap frontend remains in `language/`; C/assembly
supply platform/runtime services. No source-to-C transpilation is used.

Implemented and tested areas include methods, explicit generic specialization,
move-only owners, shared/exclusive loans, tracked slices and collection iteration,
core text/vector/map/JSON/file/path/process libraries, module resolution, persistent
REPL package imports, same-signature replacement and transactional reclamation.
The native LSP supplies diagnostics, definition lookup and scoped/member/declaration
completion, with protocol tests and a real Neovim-client integration suite.

This is a checkpoint, not a completion claim. Cool 1.0 is declared: the
mandatory gates in [the release contract](release-1.0.md) are closed with
recorded evidence, and that document's next-implementation checkpoints name the
remaining work (general nested borrowed storage, some temporary receivers,
broader editor recovery and further performance work).
[references](references.md) and [editor support](editor.md) state precise limits.
The [versioned specification draft](specification.md) and
[compatibility policy](compatibility.md) are frozen for the 1.0 language
contract.

`docs/release-1.0.md` records verification per milestone, including full regression,
both bootstrap chains, sanitizer and external installation results. Historical
pass reports do not certify later source changes or close unverified gates.
Broader ecosystem exclusions for the first release are explicitly listed there;
they do not remove the required end state above.
