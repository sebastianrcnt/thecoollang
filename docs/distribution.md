# Development distribution and installation

Cool remains **0.1.0-dev**, not 1.0. The mandatory release gates are tracked in
[the release contract](release-1.0.md). Packaging a working development artifact
does not close language, safety, editor or incremental-session requirements.

## Build and identify an artifact

On the supported native Apple Silicon macOS build host:

```sh
make package-dev
# For an explicitly uncommitted development snapshot:
python3 tools/package_release.py --allow-dirty
```

The packager builds the new-syntax compiler and native runtimes, then writes
`build/dist/<id>-darwin-arm64.tar.gz` and its `.sha256` companion. It requires a
clean working tree unless `--allow-dirty` is given. The manifest records dirty
state, version, source revision, payload identity, per-file SHA-256 checksums,
build dependencies, tested host and actual Mach-O deployment metadata for the
compiler/runtime artifacts. The current packager deliberately accepts only
`0.x.y-dev` versions. A stable 1.0 publishing path must be added only after its
release gates pass.

Archive IDs include version, commit and payload digest. Tar entry order, owner,
permissions and timestamps are normalized; gzip's timestamp is fixed. The source
commit timestamp supplies `SOURCE_DATE_EPOCH` by default, and the environment can
override it. Identical payloads, metadata and epoch produce byte-identical
archives. This does not promise byte-identical compilation across different
Clang/SDK versions or a cryptographically signed release.

The archive also includes `examples/tally`, a complete directory-package CLI
using owned text, maps, vectors, JSON and files. Copy it to a writable directory
and follow its README with the installed `cool`. Distribution tests copy this
example from the read-only installed payload and run it through the interpreter,
LLVM native build and persistent REPL, with the seed and make unavailable.

## Requirements

- Native Apple Silicon macOS, at least the manifest's `minimum_macos`. This
  minimum comes from the actual binary/object load commands, not a guessed
  deployment target. The local validation host is macOS 27.0; an artifact built
  with a 27.0 deployment floor must not be advertised as supporting older macOS.
- Python 3.10+ for the project driver and installer.
- Clang and its macOS SDK for standalone native linking (`cool build` and
  `--backend llvm`). The interpreter and ARM64 JIT use the bundled frontend.
- Git for fetching tagged modules. Purely local/offline projects can use existing
  module sources without downloading them.
- LLVM `lli` only for `--backend llvm-jit`; set `COOL_LLI` to select it.

`cool --version` reports the distribution version/revision. `cool doctor` shows
host, Python, Clang, Git, installed frontend and optional lli availability. In a
source checkout it also checks make and gtimeout. It neither installs dependencies
nor treats missing optional lli as a failed base toolchain.

## Install, upgrade and remove

After checking the archive's SHA-256 against its companion and unpacking it:

```sh
cd <unpacked-distribution>
python3 install.py --verify
python3 install.py --prefix "$HOME/.local"
export PATH="$HOME/.local/bin:$PATH"
cool --version
cool doctor
```

The installer verifies every payload file, copies it into a versioned
`<prefix>/lib/cool/<id>` directory and atomically selects it using the relative
`<prefix>/bin/cool` symlink. It refuses to overwrite an unrelated launcher, reuse
a mismatched release directory or traverse symlinked bin/lib installation
subdirectories. Reinstalling the same verified identity is idempotent. Different
versions can coexist; installing another selects its launcher. No compiler seed,
legacy loader, source checkout or make invocation is needed after installation.
Installed operations work with a read-only release directory; build/module
caches live separately under `COOL_CACHE` or the normal user cache location.

To remove one exact version, use its unpacked or installed installer:

```sh
python3 install.py --uninstall --prefix "$HOME/.local"
```

Uninstall verifies the installed receipt/manifest identity and removes only that
version directory. It removes `bin/cool` only if the symlink still selects that
version. A newer selected release, user projects, other files in the prefix and
user caches remain intact. It does not automatically select an older version.
The version directory is reserved for installed package contents.

## Validation and CI

`make distribution-test` performs two independent package builds and compares
archive bytes/checksums. It installs to an external temporary prefix containing
spaces, disables the seed path, replaces make with a failing stub, and makes the
installed tree read-only. From a separate project directory it exercises five
engines, imports, owned JSON, fmt/test/doc and optimized standalone output. It
also tests idempotent installation, missing artifacts, multiple managed versions,
uninstall preserving a newer launcher, unrelated launcher collisions, symlinked
installation directories and corrupted payload rejection.

The prepared `.github/workflows/verify.yml` runs compiler/regression/bootstrap,
instrumented libraries, external installation and development packaging on the
`macos-15` ARM64 hosted runner, with checkout/upload actions pinned to commits.
The runner label follows the [official hosted-runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
Its setup explicitly checks native arm64 and availability of Rosetta for legacy
x86 probes. A remote workflow run has **not** been executed or certified by local
validation; G10 remains open until real CI/release evidence is recorded.

No stable release has been published, signed or uploaded by this work.

## Editor client configuration

The archive includes `editors/neovim/cool.lua` for Neovim's built-in LSP client.
See [editor integration](editor.md) for setup and the exact supported capabilities.
`make editor-distribution-test` exercises that installed configuration and server
from a read-only prefix, using the pinned or explicitly supplied Neovim client.
The client binary itself is downloaded only for explicit tests and is not shipped.
