# Cool 1.0 release contract

Status: **in development; no 1.0 release has been declared**.

The user has authorized autonomous implementation, prioritization, validation and
intermediate commits. A passing old test suite or self-hosting alone does not
satisfy this contract. `docs/language-plan.md` remains the broader design record.

## Supported release

The first supported host is Apple Silicon macOS. Installation, package use,
interpretation, ARM64 JIT, LLVM AOT/JIT and standalone CLI deployment must work
outside this checkout. Linux, Windows and native x86-64 support require their
own tested release gates; existing legacy x86 probes do not certify them.
The release must publish exact dependencies and reproducible artifact manifests.

The language stays C-like and explicit: no GC, implicit reference counting,
implicit narrowing or elaborate metaprogramming. Directory packages and tagged
Git modules follow Go-like organization. C/assembly provide platform adapters;
Cool implements all compiler semantics. Python may orchestrate tools, never
implement parsing, type analysis, interpretation or code generation.

## Mandatory gates

| Gate | Acceptance evidence | Status |
| --- | --- | --- |
| G1: language contract | Versioned grammar, types, layouts, evaluation order, errors, unsafe obligations, examples and compatibility policy | Open |
| G2: ownership and borrows | Audit safe evaluation ordering, move/branch/loop/defer rules; scoped safe borrowing for ordinary collection use; negative and adversarial tests across engines | Open |
| G3: maintainable compiler | Modular new-syntax source, documented compiler invariants, deterministic bootstrap with no migration-tool dependency | Open (self-hosting already verified) |
| G4: language ergonomics | Methods and a coherent borrowing/collection API; useful source diagnostics; no silently accepted unsupported semantics | Open |
| G5: core libraries | Owned text/bytes, vector, map, file/path/process utilities, useful serialization; documented errors and resource lifetimes; realistic projects | Open (initial packages exist) |
| G6: incremental development | Predictable function replacement and invalidation, external package use in REPL, bounded/reclaimable session resources, explicit unsupported redefinitions | Open |
| G7: developer tools | Formatter/test/doc integration; LSP diagnostics, definition lookup and completion; editor/protocol tests | Open |
| G8: performance | Separate compiler and CLI measurements, reduced hot CLI overhead, representative larger builds and incremental workloads; published methodology and samples | Open |
| G9: validation | Cross-engine differential and negative tests, deterministic seeded fuzzing, sanitizer-backed runtime checks, multi-package real applications, old and new bootstrap convergence | Open |
| G10: distribution | Install/uninstall and release archive tested from clean external directories; version/help, dependency checks, checksums, CI and release notes | Open |

Release completion requires evidence for every mandatory gate and zero known
release-blocking defects. Merely disabling a required feature, reducing the
claimed scope after a failure, or labeling a development build 1.0 is not a fix.
Broader ecosystem parity (networking frameworks, async runtimes, Unicode
normalization, a public package proxy) is not required for this first release;
unsupported features must be explicit. Raw-pointer and C callers retain the
published unsafe obligations; safe source must not acquire dangling storage
through ordinary evaluation or library use.

## Execution order

1. Audit safety and compiler invariants; add regressions before fixes.
2. Make the self-hosted compiler maintainable and specify semantics.
3. Implement safe borrowing, methods and practical standard-library APIs.
4. Complete incremental tooling, LSP and real project examples.
5. Optimize measured bottlenecks; harden using fuzzing/sanitizers.
6. Validate clean installation, run release gates and only then declare 1.0.

## Audit log

- Evaluation-order audit: the previous frontend accepts a move of an owner from
  an index expression or assignment RHS while an address into that owner is
  pending. Fixed in both frontends with pending-place liveness checks. Four
  rejection regressions and positive cases across five engines pass; ownership,
  standard-library and three-generation self-hosting checks pass. This closes
  this defect, not the full ownership/borrowing gate (G2).
