# Cool compatibility policy — 1.0 draft 1

Status: **frozen for the 1.0 contract**. Cool 1.0 is declared: the mandatory
gates in [release-1.0.md](release-1.0.md) are closed and `VERSION` is `1.0.0`.
`VERSION` remains the authoritative toolchain version; record a tested compiler
revision alongside reproducible builds.

## Source and behavior after the 1.0 freeze

Within the 1.x series, a program accepted by the published language specification
and using documented stable standard-library APIs must retain its specified
behavior on the same supported target. This includes evaluation order, numeric
behavior, ownership, borrowing, public names/signatures, and documented layouts.
An incompatible change requires a new major language version and migration
notes; a deprecation notice alone does not authorize breaking a 1.x program.

This guarantee does not turn a compiler bug into a language feature. Fixes for
memory unsafety, miscompilation, violated specified checks, and acceptance of
invalid source may reject or change affected programs. Such fixes require a
regression case and release notes explaining the affected behavior. An ambiguity
in the specification requires an explicit decision and documented transition;
it must not be silently reclassified as a bug to bypass compatibility.

Changes that introduce new keywords must account for previously valid identifiers.
Adding a builtin or library API must also consider name resolution and inference,
not merely whether an old declaration was deleted. Existing files do not opt into
new incompatible semantics just because the installed compiler was upgraded.

HolyC/bootstrap syntax and the `cool legacy` tool are separate implementations.
There is no promise that new Cool accepts HolyC or C/C++ source unchanged. The
production compiler is written in new Cool; the retained bootstrap frontend is
not the compatibility definition of the language.

## Tools, modules and artifacts

- Published CLI commands, documented options and successful exit conventions
  are stable within 1.x. Human diagnostic wording is not a machine interface.
  Machine-readable modes need a documented format before being promised stable;
  current `editor-*-bundle` modes are private frontend/driver interfaces.
- Module import identities, version selection, checksums and lockfile meaning
  form part of reproducibility. A tool must reject unsupported manifest/lockfile
  formats explicitly rather than reinterpret them. Go-like package organization
  does not imply compatibility with Go's checksum database or proxy protocols.
- Cache entries, bytecode, compiler ASTs, private frontend APIs, JIT code and
  emitted LLVM IR are implementation artifacts. Their formats and code bytes
  have no cross-version ABI promise. Rebuild caches and native outputs with the
  selected toolchain; bootstrap byte identity is a verification result, not a
  guarantee that later compiler releases emit identical files.
- The supported C boundary consists of documented `extern "C"`/`export "C"`
  scalar/pointer signatures and target calling conventions. There is no promised
  aggregate-by-value C ABI or general ABI for ordinary Cool functions. A dynamic
  library or executable must declare its actual target/dependency requirements.
- Package visibility uses `pub`; private symbols are not stable public APIs.
  Declaring an implementation stable requires documented contracts and tests.
  New experimental APIs must be explicitly identified before publication.

## Targets and release process

The first supported target is Apple Silicon macOS. Integer widths, pointer size,
layout and available C symbols must not be inferred for an unvalidated target.
Additional hosts need their own execution, ABI, installation and bootstrap gates.
A 1.x source guarantee does not promise bitwise-identical floating-point results
across different target toolchains unless the numerical specification requires it.

Before declaring 1.0, finish the versioned grammar and semantic specification,
resolve open language decisions, identify stable library/CLI/module formats,
validate the release matrix and publish limitations and release notes. A passing
self-hosting test alone does not freeze this draft or fulfill those requirements.
