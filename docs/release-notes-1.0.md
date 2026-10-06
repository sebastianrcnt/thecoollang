# Cool 1.0 release notes

Status: **declared**. Every mandatory gate G1-G10 in
[the release contract](release-1.0.md) is closed and its evidence is recorded in
that document's audit log, including the remote workflow run that validates the
release commit. The language specification is
[1.0 draft 39](specification.md), frozen for the 1.0 contract.

## What Cool 1.0 is

Cool is an explicit, C-like systems language with no garbage collector and no
implicit reference counting. Values are copied, owners are moved, and borrowing
is scoped and checked before a program runs. The compiler is self-hosted: Cool
implements lexing, parsing, type checking, ownership/borrow analysis and code
generation, while the C and assembly hosts only provide platform adapters.
`make bootstrap-check` compiles the compiler with itself for three generations
and requires the IR and native binaries to be identical.

The same source runs on five engines - `tree`, `interp`, `jit`, `llvm` and
`llvm-jit` - and the release validates them with cross-engine differential,
negative and seeded fuzzing tests rather than a single happy path.

## Supported host

The first supported release host is native Apple Silicon macOS.

- Python 3.10 or later for the CLI tooling.
- `clang`/Xcode Command Line Tools for native linking.
- `git` for tagged directory modules.
- LLVM `lli` is optional and only needed for `--backend llvm-jit`.

Linux, Windows and native x86-64 are **not** certified by this release; the
legacy x86 probes are diagnostics, not a supported target.

## Included

- Frozen 1.0 language contract: grammar, types and layouts, evaluation order,
  error behavior, value copy/move/initialization/cleanup and the explicit
  obligations of `unsafe` and foreign calls.
- Ownership and borrowing: move-only owners, block-scoped `&T`/`&mut T`
  references, stored loans, checked slice projections, tracked iteration and
  collection methods that borrow instead of copying.
- Standard library: owned UTF-8 `Text` and `Vector[u8]`, owning `Vector` and
  sorted `Map`, `option`/`result`, `slice`, `strings`, `math`, `fs`, `path`,
  `process`, `os` and JSON serialization.
- Tooling: `cool run/build/test/fmt/doc`, the incremental REPL with function
  replacement, package loading and bounded session resources, `cool lsp`
  (diagnostics, definitions, completion) with a Neovim client, and
  `cool mod`/`cool get` for directory packages and tagged Git modules.
- Distribution: a deterministic, checksummed `tar.gz` with a manifest of the
  tested host, toolchain and file checksums; `install.py` installs, verifies and
  uninstalls from an external prefix without invoking `make`; `cool doctor`
  reports host dependencies.
- A complete two-package example application, `examples/tally`, covering a CLI,
  JSON output and REPL use.

## Explicitly not in 1.0

These are deliberate omissions, not regressions: closures, `async`/`await`,
traits and bounds, lifetime syntax, auto-deref, operator overloading, macros,
exceptions and GC. The language extensions that are still missing - function
pointers, C ABI by-value aggregates, `repr(C)`/packed/union layouts, variadic
`extern`, primitive threads and temporary receivers - are tracked publicly as
[issue #1](https://github.com/sebastianrcnt/thecoollang/issues/1) with the
anti-pattern list. Networking is available today through `extern "C"` POSIX
calls.

## Install and verify

```sh
python3 install.py --verify
python3 install.py --prefix "$HOME/.local"
export PATH="$HOME/.local/bin:$PATH"
cool --version
cool doctor
cool run program.cool
python3 install.py --uninstall --prefix "$HOME/.local"
```

Copy `examples/tally` to a writable directory for a complete multi-package CLI
example; its README covers command-line and REPL use.

## Verification evidence

- `make test`, `make bootstrap-check` and `make distribution-test` pass locally
  and in the remote workflow.
- Runtime ASan/UBSan suites and instrumented-frontend sanitizer targets cover
  collections, text, JSON, process/path, REPL storage and tokens, LSP, editor
  integration and the ownership/borrow/aggregate/slice fuzzers.
- `make drop-depth-sanitize-test` reproduces the bounded-depth destruction
  checkpoint: a 32,768-node owning chain under a 1 MiB stack limit completes
  with stdout `123`, exit 0 and zero remaining owners on every engine and both
  frontends.
- The remote `Verify Cool release build` workflow runs the compiler, runtime and
  bootstrap regressions, the instrumented and sanitizer suites, the external
  distribution validation and the release packaging on the `macos-15` arm64
  hosted runner. The run id and result for the release commit are recorded in
  [the release contract](release-1.0.md).
