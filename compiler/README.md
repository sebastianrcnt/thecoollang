# Self-hosted Cool compiler

`main.cool` is the new-syntax implementation of the full frontend, type checker,
ownership and borrow analysis, interpreter, bytecode compiler, ARM64 JIT, LLVM
emitter, formatter and persistent REPL. It was ported from the bootstrap sources
in `language/`. The initial mechanical migration is complete; this checked-in
Cool source is compiled directly. No migration tool, C parser, or generated C
source is part of the build or execution path.

Compiler state is explicit in `CompilerState`, obtained from the host allocation
adapter. Unsafe pointer manipulation is localized in compiler function bodies.
The port represents remaining non-structured bootstrap branches with a local
program-counter loop; those are ordinary Cool code and can be refactored without
adding goto or implicit conversions to the language.

`host.c` contains only allocation, OS files/arguments, C ABI, executable pages
and exception recovery around Cool callbacks. It performs no parsing, typing,
interpretation or code generation. Recovery keeps setjmp in an active C frame;
it does not longjmp into a returned LLVM wrapper.

## Build and verify

- `make all`: legacy seed → bootstrap frontend → new-syntax stage1 → self-built
  stage2 (`build/cool-compiler`, the frontend used by `tools/cool`).
- `make selfhost-check`: compare stage1/stage2/stage3 LLVM IR byte-for-byte,
  compare stage2/stage3 executables byte-for-byte, then run tree, bytecode and
  ARM64 JIT from a copied executable outside the repository with an invalid
  legacy seed path. The executable needs neither legacy loader nor seed.
- `make test`: language, ownership, modules, REPL and tools use stage2 by default;
  legacy compiler probes remain separate bootstrap regression coverage.
- `COOL_FRONTEND=/absolute/path/to/compiler tools/cool check path`: select a
  previously built standalone frontend without rebuilding a local frontend.

Native comparisons use identical output basenames because macOS embeds the
executable name in its ad-hoc code-signature identifier. No signature or code
bytes are stripped to obtain convergence. Supported build host: Apple Silicon
macOS with Clang and libffi; portability is a separate task.
