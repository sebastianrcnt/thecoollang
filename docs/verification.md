# Extraction verification

Verified on Apple silicon macOS, 2026-10-02.

- Clean `make -j4 all test bootstrap-check`: passed.
- ARM64/x86-64 code generation: 1,703 executable probes matched.
- Large-function liveness, inlining, AOT redefinition, architecture guards and target validation: passed.
- Compiler diagnostics and compatibility checks: passed.
- Native behavior regressions B05–B10 and host loader probe: passed.
- Formatter golden cases, fixed points and idempotence: passed.
- CLI from an unrelated directory: run, standalone ARM64 Mach-O build, spaces in paths,
  arguments, exit status, relative includes, BIN execution, formatting and errors: passed.
- Failed compilation preserves prior output; source/output collision is rejected: passed.
- Bootstrap: seed → gen1 → gen2 → gen3; gen2 and gen3 are byte-identical.
  The checked-in seed was not overwritten.
- Source-only copy to a temporary path containing spaces, with no build directory,
  OS, Warm, vendor tree or external symlinks: clean build and CLI suite passed.

Local logs: `build/validation.log`, `build/isolation.log`, `build/bootstrap/*.log`,
`build/codegen/`, `build/checks/`, `build/native-behavior/`.

These tests verify the supported host paths; they do not establish Linux/Windows support,
full x86-64 feature parity, or exhaustive language correctness. See `coolc/Host/X86.md`
for the untested aggregate ABI cases and current runner restrictions.
