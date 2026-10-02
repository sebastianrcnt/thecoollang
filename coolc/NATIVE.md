# Native Cool compiler

`make` builds the macOS ARM64 BIN loader, the Cool CLI and the formatter.
The checked-in `seed/Compiler.BIN` contains the compiler written in Cool.
No external compiler source or OS checkout is needed.

```sh
make
build/cool run examples/hello.cool
make -j4 test
make bootstrap-check
```

`tools/native/prepare.sh` stages compiler frontend, runtime and backend sources
in `build/native-src`, enabling the owned frontend fixes and native backend.
The bootstrap check compiles three generations under `build/bootstrap` and
compares gen2 with gen3. It never overwrites the committed seed.

For low-level compilation from another working directory, set the seed path:

```sh
COOLC_COMPILER_BIN=/path/to/coollang/coolc/seed/Compiler.BIN \
  /path/to/coollang/build/coolc Entry.cool Output.BIN
/path/to/coollang/build/coolc --run Output.BIN
```

The public `cool` command resolves the seed and build paths automatically.
ARM64 and x86-64 code generation use the same ARM64 compiler seed; the x86 runner
is not a self-hosted compiler. See [X86.md](Host/X86.md) for its limits.
