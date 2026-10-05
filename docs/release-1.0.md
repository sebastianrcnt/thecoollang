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
| G1: language contract | Versioned grammar, types, layouts, evaluation order, errors, unsafe obligations, examples and compatibility policy | Open (versioned lexical/declaration/expression/statement forms drafted and tested; whole-language conformance and semantic audit pending) |
| G2: ownership and borrows | Audit safe evaluation ordering, move/branch/loop/defer rules; scoped safe borrowing for ordinary collection use; negative and adversarial tests across engines | **Closed** (evaluation-order, loop-ownership and move-state audits; scoped shared/exclusive references, stored loans, slices, tracked iteration and vector/map APIs; 44+35 reference/storage rejection cases, 320 nested-reference classifications and seeded ownership/borrow/aggregate/slice fuzzers — see the audit log) |
| G3: maintainable compiler | Modular new-syntax source, documented compiler invariants, deterministic bootstrap with no migration-tool dependency | **Closed** (17-file directory-package source, `docs/compiler-invariants.md`, three-generation bootstrap fixed point, no migration tool; every port-generated dispatch section is now descriptive Cool — see the audit log) |
| G4: language ergonomics | Methods and a coherent borrowing/collection API; useful source diagnostics; no silently accepted unsupported semantics | Open |
| G5: core libraries | Owned text/bytes, vector, map, file/path/process utilities, useful serialization; documented errors and resource lifetimes; realistic projects | **Closed** (owned UTF-8 `Text` and `Vector[u8]` bytes; owning `Vector`/`Map`; `fs`/`path`/`process`; JSON serialization; ownership/error/lifetime contract in `stdlib/README.md`; the two-package `examples/tally` project — see the audit log) |
| G6: incremental development | Predictable function replacement and invalidation, external package use in REPL, bounded/reclaimable session resources, explicit unsupported redefinitions | Open (persistent state and transactional reclamation verified; final lifetime audit pending) |
| G7: developer tools | Formatter/test/doc integration; LSP diagnostics, definition lookup and completion; editor/protocol tests | **Closed** (`cool fmt`/`test`/`doc` token-preserving integration; `cool lsp` diagnostics, definitions and scoped/package/type/member/generic completion; a real Neovim client and the external-distribution editor test — see the audit log) |
| G8: performance | Separate compiler and CLI measurements, reduced hot CLI overhead, representative larger builds and incremental workloads; published methodology and samples | Open |
| G9: validation | Cross-engine differential and negative tests, deterministic seeded fuzzing, sanitizer-backed runtime checks, multi-package real applications, old and new bootstrap convergence | **Closed** (34 O0/O2 interpreter differential cases plus per-suite rejection cases; ownership/borrow/aggregate/slice/collection seeded fuzzers; runtime ASan/UBSan and instrumented-frontend sanitizer targets; the two-package `examples/tally` project on five engines and standalone O2; `make bootstrap-check` old/new convergence — see the audit log) |
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

- Compiler maintenance: split the new-syntax implementation into 17 ordinary
  directory-package files (state/platform declarations, core, lexer, layouts,
  borrows, owners, parser, tree interpreter, LLVM/C ABI/destructors, bytecode,
  JIT, REPL, formatter, driver and main initialization). Bootstrap uses a path
  manifest generated by a build-only helper. No source translation is required.
  Existing evaluation regressions, 34 O0/O2 differential cases, ownership and
  library suites, native self-host convergence, REPL, C exports and developer
  tools pass. G3 remains open for invariant documentation and further cleanup.

- Loop ownership audit: preserve the zero-iteration path when joining `while`
  and `for` move states, and prevent the syntactically earlier `for` update
  expression from reviving an owner on the first body iteration. Rejection
  cases pass on both frontends; valid branch and initializer reinitialization
  pass on five engines. Ownership, libraries and exact three-generation
  self-host convergence also pass. G2 remains open.

- Collection property testing: `make collection-fuzz-test` compares generated
  owning-vector programs against an independent Python list model on tree,
  bytecode, native JIT, LLVM O0, LLVM JIT and LLVM O2. Seeds 7, 42 and 2026 each
  exercise 230 operations, including chunk boundaries, replacement, pointee
  mutation, ownership transfer, empty pops and clear. Every operation checks
  live allocation count, length and selected elements; final traversal checks
  all remaining values and scope exit must leave zero owners. Generated inputs
  and expected output remain in `build/collection-fuzz/` for reproduction.
  `make collection-sanitize-test` additionally instruments generated LLVM
  loads/stores with ASan and the C runtime with ASan/UBSan; it verifies that the
  LLVM sanitizer pass actually inserted checks. All three seeds pass. UBSan
  does not validate Cool language semantics, and this bounded corpus is not a
  proof of memory safety; G2/G9 remain open. Expand with
  `python3 tools/test_collection_fuzz.py --seeds 1,2,3 --steps 500 --sanitize`.

- Reference preparation: added explicit `&raw place` for unsafe raw-pointer
  construction in both frontends and migrated compiler and library internals.
  It retains existing mutability and unsafe checks; it does not establish a
  loan or lifetime guarantee. The subsequent scoped-reference implementation
  replaces the transitional `&place` alias with shared-reference construction.
  Five-engine behavior, formatter preservation, negative cases and exact
  self-host convergence pass. G2/G4 remain open.

- Scoped-reference foundation: both frontends now implement `&T`/`&mut T`,
  `&place`/`&mut place`, lexical shared/exclusive loans, reborrowing, argument
  evaluation conflicts, borrowed-return provenance and deferred-call retention.
  Safe shared references cannot mutate or move pointees; live loans protect
  owning roots. References use pointer-sized values with no runtime allocation.
  Existing raw address expressions in tests were migrated to `&raw place`.
  Tests cover five engines, O2, both frontends, formatter, 27 rejection cases
  and REPL rejection rollback. Full `make test` and the legacy three-generation
  `make bootstrap-check` pass. Ownership/library/REPL/model suites and exact self-host convergence
  pass. See `docs/references.md` for explicit remaining restrictions. G2/G4 are
  still open: aggregate-stored references, shared slice/loan analysis, persistent
  REPL loans and complete collection APIs are not implemented.

- Safe collection APIs: vector length/indexing now take shared references;
  append/pop/clear and mutable indexing take exclusive references. Indexed
  elements retain a loan of their vector. File writing takes a shared byte
  vector and retains linear raw-cursor traversal internally. Added explicit
  unsafe, anchor-based raw-storage borrowing and exact-type reference-to-pointer
  casts for library implementation; provenance and exclusivity remain checked
  at safe call sites. A no-unsafe owning-vector/binary-file program passes all
  five engines; conflicting live element use is rejected. Both frontend suites
  (37 rejection cases), self-host convergence and all three owning-vector model
  seeds under ASan/UBSan pass. An additional regression closes a pending-address
  hole for temporary/returned references: their loans must be registered before
  a later assignment RHS or index expression can invalidate storage. Raw cursors
  still require manual lifetime care;
  stored references and tracked iterators remain mandatory work for G2/G4/G5.

- Owned text: added `std/text.Text` with strict UTF-8 validation, Unicode scalar
  counts/access, NUL-preserving byte ownership, append/clone/clear and bytewise
  comparisons/prefix/suffix operations. No lifetime-free string view of owned
  storage is exposed. An independent Python strict-decoder oracle covers 127
  fixed and seeded inputs, including invalid continuation bytes, overlong forms,
  surrogates, truncation and maximum scalars. All five engines and O2 pass with
  12 KiB growth, file round trips and zero remaining owners; instrumented Cool
  ASan and C-runtime ASan/UBSan also pass. G5 remains open for maps, serialization,
  additional path/process utilities and real applications; G2 remains open for
  stored references and tracked iteration.

- Move-state control flow: terminal `return` branches in `if` and exhaustive
  `match` no longer contribute moved flags to following reachable statements.
  This permits ordinary early-return ownership transfer without rejecting the
  surviving path. Negative coverage still rejects a move on a continuing path;
  both frontends, five engines and self-host convergence pass. This was exposed
  by implementing owning map insertion and does not relax live-path checks.

- Ordered map: added owning text-key `std/map.Map[V]` with AVL-balanced
  insert/replace/remove, borrowed read/mutation, clear and independent sorted
  key snapshots. Two deterministic Python-dictionary models cover rotation
  patterns, two-child deletion, sorted and random inputs; a test-only companion
  independently verifies ordering bounds, AVL balance, heights and counts after
  every operation. Exact allocation counts, five engines, O2 and instrumented
  ASan/UBSan pass for seeds 7 and 2026. Public API tests also cover narrow/float
  and owning text values, empty/NUL keys, missing-key traps and loan conflicts.
  This supplies an ordered text-key map, not arbitrary-key hashing. G5 still
  requires serialization, path/process utilities and real applications; stored
  references and tracked iterators remain required by G2/G4/G5.

- Driver performance: defer module/archive imports, hash the frontend once per
  invocation, and batch cold metadata scans per directory through a new Cool
  `scan-bundle` mode in both frontends. Content-addressed source/frontend keys
  and normal build checks remain intact; native cache keys now also include
  the linked runtime object. Cache/concurrency/mtime-preservation tests, project
  and CLI/tooling suites, and exact self-host convergence pass. Five-sample
  medians improve the synthetic 257-file cold check from 591.542 to 119.467 ms,
  warm check from 125.147 to 89.163 ms, and small full-driver execution from
  97.661 to 83.991 ms. `docs/performance.md` documents raw samples and boundaries.
  G8 remains open for real applications, additional overhead reduction and
  incremental workloads; these changes cache metadata, not typechecking/codegen.

- JSON serialization: `std/json` now owns parsed trees and exposes safe borrowed
  inspection, nested mutation, key snapshots and deletion. Strict UTF-8 parsing
  preserves arbitrary JSON number lexemes and NUL/Unicode text, reports byte
  offsets, replaces duplicate keys safely and bounds nesting. Compact encoding
  orders keys deterministically and retains number precision. An independent
  Python/Decimal oracle covers 105 fixed/seeded inputs across all five engines
  and O2; leak counts, malformed inputs, loan rejection and ASan/UBSan pass.
  G5 remains open for path/process utilities, tracked collection iteration and
  real applications; this is JSON support, not general serialization derivation.


- Nested reference-returning calls now propagate the selected argument's actual
  loan root and reborrow parent, rather than requiring a syntactically named
  argument. Later arguments cannot invalidate that loan, and pending assignment
  addresses remain protected. Both frontends pass 44 rejection cases plus five
  engines/O2, safe vector and JSON sanitizer suites; both bootstrap paths
  converge. Single-source contracts remain required; stored-reference and slice
  integration work is still open.

- Package qualification audit: generic calls such as `vector.cursor[T](...)`
  are no longer misparsed when a local has the same member name. A qualified
  bare name also cannot resolve to an unrelated local. Both frontends reject
  that ambiguity, generic runtime cases pass all five engines, and exact
  self-host convergence passes. This defect was exposed by the process library.

- Process execution: `std/process.run` now passes exact text arguments directly
  to macOS `posix_spawnp` and waits for exit/signal status, with structured
  start/wait errors and NUL rejection. PATH/cwd/environment/stdio are inherited;
  no shell parses the supplied arguments. All five engines, O2 and ASan/UBSan
  pass literal/Unicode/empty/300-argument cases, signal/nonzero exit and error
  paths. The sanitizer harness also counts raw-buffer allocations/frees and
  injects an interrupted wait to verify retry. This is a synchronous API; pipe capture and per-child overrides are
  not implemented. G5 remains open for path utilities and realistic projects.

- Lexical POSIX paths: `std/path` adds owned-text normalization, rooted joining,
  name/parent/extension and absolute-path queries with explicit Unicode/NUL,
  trailing separator and dot rules. 126 fixed/seeded oracle cases, idempotence,
  owner cleanup, five engines, O2 and ASan/UBSan pass. These operations do not
  resolve symlinks or provide filesystem containment. The complete `make test`
  suite also passes after the JSON/reference/namespace/process changes; the
  subsequent path suite passes separately. G5 still requires realistic project
  validation and coherent borrowed iteration; G1–G10 remain open.

- Compiler maintenance: named expression/call resolution is now a direct,
  descriptive `compiler/17-calls.cool` module rather than hundreds of temporary
  assignments inside Atom. The bootstrap frontend retains its independent
  equivalent implementation. `docs/compiler-invariants.md` records build/host
  boundaries, type/frame layout, AST tags, pass order, ownership/loan invariants,
  backend/recovery obligations and known resource limits. This is implementation
  documentation, not a substitute for the versioned language specification.
  The full `make test` suite and both bootstrap fixed-point checks pass after
  the refactor (new-compiler IR SHA256 begins `24c3b09c2d9ee851`).

- Nominal methods: structs/enums now declare `fn Type.member(self: &Type, ...)`
  (value, exclusive-reference and owning receivers also work). The defining
  package owns the method set; visibility, field/variant collisions, receiver
  types and explicit ownership are checked. Generic receiver arguments are
  supplied from the instance; additional method type arguments remain explicit.
  Calls lower to ordinary typed/borrow-checked calls across all backends.
  Vector/Text/Map now provide corresponding safe methods alongside free APIs.
  Focused tests cover both frontends, five engines/O2, imported same-named types,
  docs/formatting, REPL body replacement and 19 negative cases. Full regression
  and both bootstrap paths pass; final receiver-copy adjustments pass the
  method suite and new-syntax convergence again (IR SHA256 begins
  `e2d997b1e66690d4`). G4 remains open
  for complete borrowing/iteration ergonomics and diagnostics; reference
  temporary/storage/REPL restrictions have not been silently removed.

- Development distribution: added `VERSION`, lazy `--version`, `doctor`, a
  reproducible checksummed binary archive, verified versioned prefix install
  and identity-checked uninstall. Installed drivers use bundled artifacts and
  never invoke make; actual Mach-O minimum OS metadata is retained. External
  tests cover a read-only prefix with spaces, absent seed/failing make, five
  engines, a directory project with JSON, fmt/test/doc, native output, managed
  upgrades, collision/symlink/tamper rejection and missing-artifact errors.
  Project/tooling/cache regressions also pass. A pinned-action ARM64 CI workflow
  is prepared but not remotely run. This is explicitly `0.1.0-dev`; G10 remains
  open for remote CI evidence and the final 1.0 release process/notes.

- Reference provenance sets: calls with multiple `borrows` sources now preserve
  all possible roots with root-specific reborrow ancestry. Expression markers
  distinguish returned loans from index/argument temporaries; equivalent records
  are deduplicated. Computed exclusive references can be safely reborrowed as
  shared, enabling chains such as `map.at_mut(&key).scalar_len()`. Five engines,
  O2, 28 negative cases and 216 deterministic finite-set oracle queries pass on
  both frontends, alongside existing reference/method/evaluation regressions and
  self-host convergence (IR SHA256 begins `5342aa758b3f62f1`). The complete
  `make test bootstrap-check` run also passes, including legacy generation
  convergence. This is a foundation for stored loans and slice integration,
  which remain required and unimplemented.

- Stored shared references: non-owning, slice-free structs/arrays/enums now
  retain shared loans across literals, generic copies, field/index projections,
  calls, returns and by-value methods. Match scrutinees have anonymous holders,
  preserving single evaluation and loans through all arms. Empty enum results
  support `borrows()`. Missing initializers, borrowed-storage reassignment,
  lifetime escapes and conflicting source operations are rejected. Five engines,
  O2, 40 rejection cases and 144 source-set oracle queries cover this extension.
  Imported `std/option` reference payloads also pass all five engines. The full
  `make test bootstrap-check` run and new-syntax self-host convergence pass
  (IR SHA256 begins `e4eb69ff346b88b5`); instrumented Cool ASan plus C runtime
  ASan/UBSan fixtures pass. The documented example also executes successfully.
  Exclusive storage, nested borrowing, ownership/slice integration and tracked
  mutable iteration remain required; this does not close G2/G4.

- Nested shared storage and tracked iteration: shared-reference-only containers
  now accept shared/exclusive receiver borrows, preserving all underlying roots.
  `Vector.iter` returns a private anchored `Iterator`; `remaining` is O(1), and
  `next` advances in O(1) with `Option[&T]`, no allocation and no user `unsafe`.
  Source mutation/movement and advancement with a retained result are rejected.
  Tests cover nested receiver/array/owner/escape cases, 12 chunk-boundary sizes,
  owning elements, repeated exhaustion, early break and exact allocation counts.
  Both frontends, five engines/O2 and instrumented Cool ASan/C ASan+UBSan pass.
  UTF-8 validation now uses the tracked iterator without an unsafe block; the
  strict text oracle/sanitizer suite verifies this real library integration.
  The full regression/legacy bootstrap run passes; new-syntax self-host IR and
  native binaries converge (IR SHA256 begins `3131095f1f225302`). The subsequent
  UTF-8 migration passes all five engines/O2 plus ASan/UBSan independently.
  The documented iterator example executes successfully.
  Whole-root propagation remains conservative across independent containers
  sharing a referent; separating container storage from referent provenance,
  exclusive stored loans, slices and lifetime-aware replacement remain required.
  G2/G4/G5 are not closed by this step.

- Container/referent provenance: nested loans now distinguish physical container
  storage from shared payload roots. Direct, copied and independently created
  iterators can advance over one vector alongside shared element references.
  A retained result still freezes its own iterator; source mutation remains
  rejected. Direct/computed payload copies shed physical-container provenance,
  scalar projections keep it, and nested reference returns preserve the layers.
  Source acquisitions check both physical access and selected referent loans.
  A 120-query independent model, 14 explicit rejections and expanded iterator
  cases validate these rules on both frontends and five engines/O2. The final
  `make test bootstrap-check` run passes, including both fixed-point checks
  (new-syntax IR SHA256 begins `815666213c263b4d`). Expanded independent/copy
  iterator cases pass instrumented Cool ASan plus C ASan/UBSan. The documented
  container example executes successfully. Exclusive stored references, slices
  and lifetime-aware reassignment remain required.

- Exclusive stored loans and mutable iteration: non-owning structs/arrays/enums
  can now retain exclusive references alongside shared ones. Copies reborrow;
  each root preserves its mode, shared receivers only expose reads, and child
  exclusivity suspends the parent. `IteratorMut` provides checked in-place
  traversal, including owning-element moves and replacement. A 192-query
  permission model, 27 storage rejections and 26 iterator rejection cases cover
  both frontends; valid programs pass five engines/O2 and iterator ASan/UBSan.
  An additional audit found reference-mediated owner moves during a pending
  pointee address; shared pins now prevent invalidation through named, stored
  and returned references. Six new rejection cases and valid owner updates
  exercise the fix. Computed shared receivers cannot extract exclusive handles
  or modify owning pointees; plain reads remain valid. Full `make test
  bootstrap-check`, stored-reference and iterator ASan/UBSan, and executable
  documentation checks pass. Self-hosted stage 1/2/3 IR and stage 2/3 native
  binaries converge (IR SHA256
  `22ff0f9c1a8de58834b7a3bca7e10d43c12ff54e1f9e675f3cddb7d7e17a9bf4`).
  Owned/nested stored lifetimes, borrowed slices and reassignment remain
  required; this does not close G2/G4/G5.

- Slice/reference integration: function-body `[]T` values now retain exclusive
  lexical source loans through copies, reslicing, aggregate storage, calls and
  owned moves. Element references can reborrow slices; arrays can be used again
  after the view's scope ends. The whole-function slice/reference exclusion and
  guards against owned-array/owning-element views are replaced by tracked loans.
  Slice assignment preserves possible roots at the destination's declaration
  scope, checks deeper local escapes and avoids cyclic self-reslicing ancestry.
  This intentionally tightens pre-1.0 plain-array aliasing rules inside functions.
  All 96 independent source-set queries and 29 rejection cases pass on both
  frontends. Five engines/O2, instrumented Cool ASan plus C ASan/UBSan, imported
  `std/slice` integration and executable documentation pass. Full `make test
  bootstrap-check` passes; self-host IR and native binaries converge (IR SHA256
  `95c309ecf2e3fc997edf96b1931b6235f4a10208e7cf2219fb238cb96a3bb0a8`).
  Legacy REPL views of persistent plain arrays are preserved; owned views are
  explicitly rejected with verified rollback until persistent loans are added.
  References to slice descriptors, borrowed slice elements, general stored
  reference lifetimes and REPL integration remain release work; G2/G6 stay open.

- Persistent REPL loans: reference/slice provenance now survives submissions,
  including owned views and stored references, under the same rules as checked
  functions. Per-input clones roll back checking failures; runtime failures
  conservatively retain possible roots for old surviving bindings. `:forget`
  validates dependencies before dropping owners, releasing held loans and
  removing the name. Failed new bindings do not retain loans. Ten focused
  sessions and 288 independent permission queries pass on both frontends,
  including JIT/body replacement, borrow-contract rejection and partial-write
  recovery. The self-hosted compiler itself passes these tests with verified
  LLVM ASan load/store instrumentation and C host/runtime ASan/UBSan. Full
  `make test bootstrap-check` passes; self-host IR/native binaries converge
  (IR SHA256
  `ec515445abe36c33c9ceb6ecda3080a7cc034198eaa2051065ff0c4112c31cbb`).
  CI now includes slice and persistent-loan sanitizer targets; remote execution
  is still unverified. `:forget` does not reclaim value slots, tokens or all
  compiler metadata. External REPL package loading and bounded long-session
  resource reclamation remain mandatory; G6 stays open.

- Package-aware REPL: ordinary imports now request the same module graph,
  MVS/checksum/workspace/vendor resolution as builds through a private framed
  driver channel. Cool parses all imports and declarations. Packages are staged
  transactionally, pinned by content fingerprints and restored on failure with
  the session namespace and existing loans intact. The driver retains only the
  current request's source snapshots on disk. Both frontends pass standard/local
  and transitive package use, methods/generics, aliases/visibility, offline and
  frozen checksums, cache tampering, closed-channel recovery, failed-load retry
  and changed-loaded-package rejection. These sessions also pass on the
  ASan-instrumented self-hosted compiler with C host/runtime ASan/UBSan. Full
  regression and both bootstraps pass; the fixed-point IR SHA256 is
  `a54f66e912cd220330494065a2281769e1b16b56193b5fe565e4636fb2cd08dd`.
  Read-only external installation tests exercise dynamic project/standard REPL
  imports without a seed or working make. CI includes the new sanitizer target;
  remote CI is not yet verified. In-memory tokens, code and value slots still
  need bounded reclamation, so G6 remains open.

- REPL storage lifetime audit: redefining the synthetic `__session` function
  reset live slot metadata and changed an existing variable from 7 to 9 when
  a new variable reused its slot. Both frontends now reject redefinition and
  calls of that internal function in REPL mode; ordinary source identifiers
  remain unaffected. Dead trailing storage is reclaimed after statements and
  `:forget`, without relocating live bindings. Compile rollback removes new
  drop metadata without touching uninitialized values; runtime rollback drops
  initialized new owners and restores the old storage boundary. Dead owner
  descriptors are removed before slots can hold another type. Repeated large
  temporary/forgotten arrays exceed the former cumulative slot limit while
  preserving live references, mixed owner/scalar reuse and error recovery.
  Both frontends and the ASan-instrumented compiler pass these regressions.
  `make test bootstrap-check` and external read-only installation pass; the
  self-host fixed-point IR SHA256 is
  `0e3c643ab04bde18bc3825b579f4b1870b5d76ba68ddb7d6c7a8f6be51ea255d`.
  CI includes the storage sanitizer target; remote CI is still unverified.
  Interior holes and in-memory AST/token/code reclamation remain open, so this
  does not close G6 or declare bounded total session memory.

- REPL bytecode ownership: submission instruction buffers, argument vectors
  and scope/defer records now have explicit compilation ownership and are
  released after execution or failed code generation/runtime recovery. A
  single allocation contains each list header and its aligned payload;
  shared defer arguments are released once even when several cleanup paths
  reference them. Ordinary cached functions keep their compilation storage.
  Both frontends and compiler ASan pass repeated break/continue/defer, partial
  execution and generated-register-limit recovery, alongside existing REPL
  loan/package/JIT tests. Full regression, both bootstraps and the read-only
  external installation test pass with IR
  SHA256 `d20c741de2a8a09b73e80db03bdf565d38d224a135a16e924a14e6d02f1334c9`.
  This does not reclaim AST/tokens, replaced-function caches or all invocation
  scratch memory; G6 remains open.

  A macOS 27 ARM64 microbenchmark compares the prior `a38fb83` compiler with
  this change using identical `var total=0;`, N separate `total=total+1;`
  submissions, then printing `total`. `tools/bench_repl_memory.py --baseline
  <prior-compiler> --candidate build/cool-compiler` runs three fresh processes
  per version/count and verifies output. `/usr/bin/time -l` median peak RSS
  fell from 19,791,872 to 11,616,256 bytes at 2,000 submissions, and from
  94,896,128 to 29,163,520 bytes at 16,000 submissions (90.5 to 27.8 MiB).
  Baseline Cool sources were extracted from `a38fb83` and compiled with the
  current compiler and unchanged C adapters at `-O2`. Raw measurements are in
  `build/release-audit/repl-bytecode-memory-reproduce.json`. Full regression
  ran concurrently, so elapsed-time medians (0.74 vs 0.66 seconds at 16,000)
  are not an isolated speed claim. Remaining RSS growth demonstrates that
  total session memory is still not bounded; G8 also remains open.

- Disposable REPL syntax: all node allocation, including coercion clones, now
  goes through one allocator. Synthetic-session nodes have wrapper-owned
  allocation links outside the copied Node payload and are freed after each
  submission or recovery. Persistent loan expression pointers are cleared
  before disposal, preserving Local identities, permissions and ancestry without
  allowing allocator address reuse to match stale expressions. Ordinary and
  specialized function bodies remain cached. Bytecode invocation argument
  vectors now use bounded native stack scratch (32 accepted arguments), so
  nonlocal runtime recovery cannot skip a heap-vector free.
  Regression sessions cover all coercion clone paths, persistent strings and
  generic bodies, zero/32 owning arguments, deep recursive error recovery,
  shared defer cleanup and prior persistent-loan/package behavior. Both
  frontends and compiler ASan pass. Full regression, both bootstraps and the
  read-only external installation test pass; fixed-point IR SHA256 is
  `133f313eaf0e12aae00daf293c0322a365fab581668031859428d07588d0c128`.
  The same three-trial fresh-process scalar-update benchmark against `9f5ae8b`
  lowers median peak RSS at 16,000 submissions from 29,179,904 to 18,857,984
  bytes (27.8 to 18.0 MiB); at 2,000, from 11,632,640 to 10,354,688 bytes.
  Raw measurements are `build/release-audit/repl-nodes-memory.json`; build and
  measurement methodology matches the preceding entry. Concurrent regression
  means elapsed times are not an isolated performance claim. Tokens/lexical
  strings, Local metadata and replaced or rolled-back function caches still
  require reclamation. G6/G8 remain open and this is not a bounded-total-memory
  claim.

- REPL local metadata: named locals and anonymous match holders now enter an
  allocation registry independent of lexical chains and function snapshots.
  After node/move cleanup, a linear mark/sweep retains visible bindings and
  surviving loans' root/holder/parent identities, reclaims other locals and
  rebuilds the session's all-locals chain. This also recovers partially
  constructed locals rejected by the storage limit. Out-of-scope parent
  identities survive both successful assignments and assignments made before
  runtime failure; cached function locals and lexical strings stay separate.
  Both frontends and compiler ASan pass repeated allocation/release, hidden
  parents, anonymous match holders, incomplete declarations and the existing
  ownership/loan/package cases. Full regression, both bootstraps and external
  read-only installation pass. Fixed-point IR SHA256:
  `b493fb69fb3068e135938839c19cb8d7aa49c9cbe901be512268a589658d8be7`.
  `tools/bench_repl_memory.py --workload bindings` adds a repeated temporary-local
  workload, `{var scratch=total;total=scratch+1;}`. Against `f8c2f27`, the same
  fresh-process three-trial methodology gives median peak RSS 31,965,184 to
  30,425,088 bytes at 16,000 submissions, and 12,025,856 to 11,829,248 at 2,000.
  Raw data: `build/release-audit/repl-locals-memory.json`. This differs from the
  preceding scalar-update workload and is not a direct comparison to its RSS;
  concurrent regression again prevents an isolated timing claim.
  G6 remains open. A separate 50,000 scalar-update session still exits with
  code 70 and no diagnostic/output when the fixed token table is exhausted
  (`build/release-audit/repl-token-limit-baseline.json`). Reusing/reclaiming
  tokens while preserving literals, types and cached/generic function source
  is the next mandatory resource fix; increasing the limit alone is insufficient.

- REPL token reuse: completed/rejected statements and session commands now
  release lexical text/raw buffers and reuse the token-table tail after retained
  declarations. Session locals own copied names; types own diagnostic coordinates;
  statement literals are interned into stable session storage. Synthetic
  semicolons do not duplicate buffer ownership, and recovery records the lexical
  allocation range before restoring counters. Lexer string-construction headers,
  unfinished buffers and floating-parser substrings have explicit cleanup.
  A genuinely oversized input now reports a recoverable token-limit diagnostic.
  The former 50,000-input exit is fixed: 100,000 updates pass on both frontends
  and compiler ASan with strings, owning storage, functions and deferred generic
  specialization intact. Partial lexing, rejected declarations, implicit
  semicolons and oversized-input recovery also pass. Full regression, both
  bootstraps and external read-only installation pass. Fixed-point IR SHA256:
  `d3ca068cac35eb5063765ba5718c20425af7a002c89c9a54090a39cabe0e78a3`.
  CI includes the token sanitizer target; remote execution remains unverified.

  Against `acb7b7d`, three fresh-process trials reduce the 16,000-update median
  peak RSS from 18,857,984 to 9,142,272 bytes, and the temporary-binding workload
  from 30,425,088 to 9,175,040 bytes. The candidate's 2,000 and 100,000 update
  medians are both 9,142,272 bytes (8.7 MiB). Reproduce the latter with
  `python3 tools/bench_repl_memory.py --counts 2000 100000`; a baseline is now
  optional. Raw files are `build/release-audit/repl-tokens-memory.json`,
  `repl-tokens-bindings-memory.json` and `repl-tokens-stability.json`. The same
  macOS ARM64 methodology applies; these are workload-specific memory results,
  not an isolated speed or universal bounded-memory claim. Successful
  declarations/imports still retain source, replaced-function caches need
  reclamation, and distinct immutable literal contents have session lifetime.
  G6 stays open for these remaining lifecycle requirements.

- Transactional function artifact lifetime: successful REPL replacement now frees
  superseded node/local/borrow-source/drop records, bytecode pools and JIT mappings;
  failed submissions dispose staged artifacts before restoring prior functions.
  Cleanup runs after user frames unwind and does not repeat value destruction.
  Existing JIT callers continue dispatching by stable function ID. JIT builder
  scratch is released on success and recovery. Parser signature snapshots use
  stack storage, and foreign/exported C ABI mode changes require a new session.
  Active-prefix function snapshots replace full-capacity copies on every input;
  rollback clears newly discarded entries before their IDs are reused.
  `make repl-functions-test` covers warmed replacement, failed specialization/ID
  reuse, compile/runtime recovery, owner accounting, escaped literals, batch
  rollback and C ABI rejection on both frontends. The compiler-instrumented
  ASan suite passes, alongside persistent loan/storage/token/package sanitizers.
  Full `make test bootstrap-check` and `make distribution-test` pass. Self-host
  IR SHA256: `811d85f600fa604a63310f4523a30c282d3a7726ceca15ebbb12670da4d1e467`.
  Against `b480eea`, 2,048 replacements reduce peak RSS from 56,377,344 to
  4,571,136 bytes (three fresh-process trials, medians, concurrent regression
  activity). After our test jobs finished, five fresh-process trials of 100,000
  scalar updates measured median wall time 4.632 → 0.467 seconds and peak RSS
  9,142,272 → 2,211,840 bytes on macOS ARM64. Timing includes process launch;
  no system-wide idle guarantee or general compiler speed claim is implied.
  Reproduce with `tools/bench_repl_memory.py --baseline <old-compiler>
  --counts 100000 --trials 5`; replacement measurements use `--workload
  replacements --counts 256 2048`. Raw reports are
  `build/release-audit/repl-functions-memory.json` and
  `build/release-audit/repl-functions-snapshot-isolated.json`.
  Successful declaration source, distinct literals, storage holes and auxiliary
  allocation lifetimes still need work. G6 remains open.

- REPL symbol and literal lifetime: function-body literals and declared function
  names now use immutable session storage independent of declaration token
  buffers. Method call nodes refer to the declared symbol. Method lookup compares
  package/owner/member directly and creates no temporary composed name, including
  rejected lookups; declaration construction and method-owner lookup free their
  temporary buffers. This fixes a per-call leak whose Text capacity amplified
  even short method names. Both frontends pass 100,000 repeated method calls,
  unknown-name recovery, prefix-collision checks and cached caller replacement.
  The existing method suite covers package visibility, generic specialization,
  ownership and five engines plus optimized native output. Compiler ASan runs
  pass the extended function and token lifetime suites. Full `make test
  bootstrap-check` passes, with self-host IR SHA256
  `0e8bf3cb64fabad1b9615ce74bdadf934e65b5b246af7acbc8a78bf389865e7f`.
  `make distribution-test` also passes. Source reclamation itself
  is still pending; this makes escaped strings and canonical names independent
  of the source that will eventually be discarded.
  Three fresh-process trials against `109aab8` measured peak RSS medians for
  2,000 method calls of 12,894,208 → 2,310,144 bytes and for 100,000 calls of
  531,857,408 → 2,310,144 bytes. The candidate is flat for this workload; other
  session allocation classes remain open. Reproduce with
  `python3 tools/bench_repl_memory.py --workload methods --counts 2000 100000
  --baseline <old-compiler> --trials 3`. Raw data:
  `build/release-audit/repl-names-memory.json`. Measurements ran on macOS ARM64
  concurrently with focused tests; no isolated speed claim is made.

- Reclaimable declaration source: successful REPL declarations now form source
  blocks, marked by current function and AST token references. Blocks introducing
  nominal types or aliases stay pinned for lazy layout/generic parsing and
  source-backed names; a mixed batch remains intact while any root survives.
  After transaction cleanup, dead blocks free their token text/raw buffers and
  the live tokens compact in place. Function signatures/body ranges, node tokens
  and nominal type ranges are relocated together. Inline diagnostic tokens and
  interned function symbols/literals have independent lifetimes. Failed
  submissions never publish a block, and no source moves during execution or
  rollback. The existing capacity now bounds live retained source and single
  submissions instead of all past replaced definitions.
  Both frontends and compiler ASan pass 40,000 replacements, warm caller reuse,
  failed redefinition, moved generic/type bodies, JIT error recovery, escaped
  strings, mixed declaration batches, C declarations and package alias/lazy-
  specialization relocation. Full `make test bootstrap-check` and
  `make distribution-test` pass. Self-host
  IR SHA256: `764a7cfe761450f5b6c27e9bf32b874438131947cbf51c834d6f3a3dda2f1011`.
  A retained pre-fix
  `109aab8` executable stopped accepting the same replacements after 23,829,
  reporting 16,171 token-limit errors; raw result:
  `build/release-audit/repl-source-old-limit.json`.
  Three fresh-process trials of `tools/bench_repl_memory.py --workload replacements
  --counts 2048 40000` (each definition followed by four calls) measured peak RSS
  medians of 2,293,760 bytes at both sizes. Raw data:
  `build/release-audit/repl-source-memory.json`. Measurements ran on macOS ARM64
  alongside regression jobs; this is a workload-specific memory result, not a
  general speed or complete bounded-memory claim. Pinned mixed batches, distinct
  immutable text, storage holes and auxiliary parser/package allocations keep
  G6 open pending the complete lifecycle audit.

- Input-lifetime compiler scratch: parser branch/loop move snapshots, temporary
  generic bindings and match coverage arrays now enter an independent allocation
  registry in REPL mode. Both success and nonlocal recovery release that registry
  after restoring move/loan state and unwinding frames. Manifest buffers, loaded
  source buffers and temporary manifest fields use the same registry. Package
  names and original diagnostic paths are interned, while fingerprints have
  explicit package ownership. Rollback frees new fingerprints, package records
  and alias records. Error diagnostics are freed after the synchronous write
  and before the nonlocal jump; `:stats` frees its formatting buffer too.
  Both frontends and the compiler-instrumented ASan suite pass 100,000 branch
  submissions, 512 rejected matches preserving a preexisting owner, 512 stats
  commands, and 32 failed package loads (512 KiB comment per file) followed by
  successful repair/retry. Existing function, source, loan and package tests pass.
  Full `make test bootstrap-check` and `make distribution-test` pass. Self-host
  IR SHA256: `1174b9a36a56855ac27b7e90c5a918942beebc0bdc4daaae5b035de9c28ad463`.
  Against `ef1b3b7`, three fresh-process trials of 100,000 branch submissions
  reduce median peak RSS from 5,406,720 to 2,211,840 bytes; the candidate uses the
  same RSS at 2,000 inputs. Raw data: `build/release-audit/repl-scratch-memory.json`.
  `tools/bench_repl_packages_memory.py` times the frontend itself, excluding the
  Python resolver driver: at 128 failed imports, median peak RSS drops from
  72,499,200 to 2,834,432 bytes (three fresh processes). At eight imports the
  candidate uses 2,801,664 bytes. The package-source fixture is 524,341 bytes.
  Raw data: `build/release-audit/repl-scratch-packages-final-memory.json`. A longer
  1,024-failure run measures 2,867,200 bytes (three-process median), recorded in
  `build/release-audit/repl-scratch-packages-stability.json`.
  Measurements ran on macOS ARM64 alongside regression jobs; no isolated speed
  or universal memory-bound claim is made. G6 remains open for the full lifetime
  audit, including rejected nominal-layout metadata and newly interned text.

- Type and immutable-text rollback: reproduced a semantic error where a retained
  lazy generic instance remained in layout state 1 after failure, producing a
  false recursive-type diagnostic on retry. A completed layout could also retain
  field type IDs subsequently reused for unrelated types after another error.
  Layout now journals only touched preexisting descriptors. Rollback restores
  those descriptors, frees newly computed field lists and clears new type slots;
  runtime frames/owners are destroyed before layout restoration. Commit retains
  completed layouts and releases the journal. The original missing-type case
  now retries consistently and succeeds after the missing type is declared.
  Raw baseline/candidate reproduction: `build/release-audit/repl-types-reproduction.json`.
  Interned text gains a per-input insertion list. Checking failures discard only
  new entries after metadata/source cleanup. Once execution starts, new text
  survives runtime errors because prior writes, owning storage or foreign code
  may retain it. Previously committed text is untouched.
  `make repl-types-test` covers lazy retry/repair, completed-layout rollback,
  type ID reuse, failed nominal fields, runtime owner unwinding, 2,048 distinct
  rejected names/literals, and scalar/owner string writes before runtime failure
  on both frontends. `make repl-types-sanitize-test` passes with compiler LLVM
  loads/stores ASan-instrumented; package/function/token/loan sanitizer suites
  also pass. Full `make test bootstrap-check` and `make distribution-test` pass.
  Self-host IR SHA256: `29a9dab7e9caa2bafa430e263fca7c3343bcba9f107d4414b2af9f9e350504a6`.
  CI includes the new target; remote CI is still unverified.
  Three fresh-process trials against `9691ef9` at 16,000 rejected declarations
  measure peak RSS medians of 24,985,600 → 2,277,376 bytes for distinct 1 KiB
  literals/names, and 26,918,912 → 2,228,224 bytes for 32-field nominal layouts
  ending in an unknown type. Candidate RSS is identical at 2,000 and 16,000
  inputs for each workload. Reproduce with `tools/bench_repl_memory.py --baseline
  <old-compiler> --counts 2000 16000 --workload rejected-literals` or
  `--workload rejected-types`. Raw reports are
  `build/release-audit/repl-types-literals-memory.json` and
  `build/release-audit/repl-types-fields-memory.json`. These macOS ARM64 runs
  overlapped regression jobs and support workload-specific memory results.
  G6 stays open pending the complete session-lifetime audit and sustained
  real-project validation; accepted immutable text still has session lifetime.

- Sustained project integration: added the checked-in `examples/tally` directory
  module. Its separate ledger package composes owned UTF-8 text, a sorted map,
  bounded recent-update vector and JSON snapshots; the CLI accepts argv labels
  and writes a JSON count report. It rejects invalid UTF-8 and failed writes.
  Python Counter/JSON results match both frontend checks, all five engines and
  an optimized standalone executable outside the checkout. Formatter and public
  API documentation checks pass. The example ships in the checksummed archive;
  distribution tests copy it from a read-only installation and verify normal
  execution, LLVM native output and REPL use without a seed or working make.
  `make repl-project-test` adds 4,096 deterministic modeled updates, 128 function
  replacements, rejected replacement bodies, runtime errors after committed
  writes, persistent-loan conflicts, explicit binding release and JSON checkpoints.
  A longer 32,768-update / 1,024-replacement session passes both frontends and the
  compiler-instrumented ASan frontend; after forgetting the book every frontend
  reports zero live user owners. Cached callers remain valid and JIT compilation
  counters prove the workload exercises hot functions. `make distribution-test`
  passes with the example included. The new sanitizer target is wired into CI;
  remote CI has not been observed.
  Frontend-only macOS `time -l` observations with the final example measure
  production peak RSS of 9,142,272 bytes at 4,096 updates and 9,125,888 bytes at
  32,768 updates (about 8.7 MiB in both). These are one fresh process per workload,
  including cold package compilation, run alongside other verification jobs;
  they are neither medians nor isolated timing measurements. Bootstrap and ASan
  samples are recorded separately, not mixed into production results. Reproduce
  with `tools/test_repl_project.py --rounds 128 --rss-output <report.json>` and
  `--rounds 1024`; `--frontend build/repl-loans-asan/cool-compiler` adds ASan.
  Raw reports: `build/release-audit/repl-project-final-rss-128.json` and
  `build/release-audit/repl-project-final-rss-1024.json`.
  This strengthens G5/G6/G9/G10 evidence; it does not close the remaining language,
  resource-lifetime, tooling or release gates.

- Editor diagnostics foundation: `cool lsp` serves native compiler diagnostics
  through framed JSON-RPC. Both frontend implementations emit JSON with UTF-8
  byte ranges, including correct EOF offsets. The transport maps these into
  UTF-16 positions and supports unsaved dependency buffers, newly opened files,
  ordered incremental edits, stale-version rejection, save/watch and close/reset.
  Source and module files remain unchanged; analysis is offline/frozen. Tests
  cover quoted Unicode paths, emoji, CRLF, lexer/type errors and fragmented
  framing on both frontends and the compiler-instrumented ASan frontend.
  Full `make test bootstrap-check`, self-host IR/native convergence and installed
  read-only distribution tests pass. IR SHA256 is
  `8f4c7d371b083ec7a5af7841af40db461d89af8b56a7001805a2d625092437fd`.
  Logs: `build/release-audit/lsp-regression.log`, `lsp-sanitize.log`,
  `lsp-final-focused.log` and `lsp-distribution.log`. CI includes the new target;
  remote CI has not been observed. Analysis is synchronous, with a 20-second
  timeout per native process, and reports the compiler's first error per package.
  Definition lookup and completion remain unimplemented; G7 stays open. See
  [editor integration](editor.md) for the exact supported scope.

- Semantic definition lookup: `editor-index-bundle` emits native binding
  references for checked AST locals/assignments/parameters and function calls,
  plus semantic type/field resolution. Token-pointer identity distinguishes
  shadowed variables; methods and generic instances navigate to their source
  declarations. The LSP maps snapshot paths back to editor documents and discards
  failed-package indexes instead of returning stale locations. Both frontends
  and the compiler-instrumented ASan frontend pass shadowing, assignment,
  parameter, imported function/type/field/method/generic and invalidation tests.
  The read-only installed distribution passes cross-package definition lookup.
  Full `make test bootstrap-check` and self-host IR/native convergence pass;
  IR SHA256 is
  `fa83a5e4d7f216a99f5a53c1b6658568b5ebb6795a444b8d8a3fa81cf7aebb56`.
  A native compiler-source index produces 36,868 reference records successfully.
  An end-to-end LSP sample copies all 31 compiler sources into a temporary normal
  module, adds its package declarations and opens an unsaved buffer; it reports
  no diagnostics and exits cleanly. Observed times (0.443 seconds native index,
  1.091 seconds whole server sample) are single local runs alongside other work,
  not benchmark medians. Token lookup uses a pointer-keyed table; transport caches
  file position maps and deduplicates references with sets. Logs/reports are in
  `build/release-audit/editor-definition-{regression,sanitize,final,distribution}.log`
  and `editor-definition-{compiler,lsp-compiler}-sample.json`.
  G7 remains open for completion, import/builtin and uninstantiated-template
  navigation, analysis of incomplete code and broader editor integration.

- Native parser-context completion: `editor-complete-bundle` prepares a cursor
  token and temporary closing braces before declaration collection. The ordinary
  parser emits candidates when it reaches that position with live locals,
  imported package visibility and checked receiver types. `cool lsp` advertises
  completion with a dot trigger and UTF-16 identifier replacement edits. Tests
  cover prefix/mid-word completion, parameters, scoped and moved bindings,
  qualified type/value contexts, public/private fields and methods, enum variants,
  generic receivers, statement/loop keywords, std/io builtins, unfinished nested
  blocks, Unicode before the cursor, and comment/string exclusion. Source/module
  files remain unchanged. Both frontends and the compiler-instrumented ASan
  frontend pass; the read-only installed distribution supports completion too.
  Full `make test bootstrap-check` passes after correcting one new test oracle:
  types imported under alias `l` belong in `l.` completion, not bare type scope.
  Self-host IR/native convergence passes with IR SHA256
  `dc0f6941551808e47965ce2953b74336c0c96dddc341de37e981ddc2707016c8`.
  A temporary normal module containing all 32 compiler source files opens without
  diagnostics and completes CompilerState members through the LSP. One whole
  server run took 1.282 seconds with the existing configured scan cache while
  other checks ran; this is an observation, not a benchmark median or latency
  guarantee. Evidence: `build/release-audit/completion-verified.log`,
  `completion-final.log`, `completion-sanitize.log`, `completion-distribution.log`
  and `completion-lsp-compiler-sample.json`.
  G7 remains open: earlier unrelated errors can prevent reaching the cursor,
  uninstantiated generic bodies/top-level/import paths need support, and wider
  error recovery, cancellation and editor integration still need validation.

- Completion isolation from unrelated body errors: after collecting declarations
  and validating signatures, the completion process checks the requested
  non-generic function body first. Errors in earlier functions or dependency
  bodies no longer block its candidates. Normal diagnostics still report those
  errors; ordinary checking and REPL body order are unchanged. Tests on both
  frontends and the compiler-instrumented ASan frontend cover unknown names and
  type mismatches in other bodies, broken dependencies with valid signatures,
  and continued rejection when a type error precedes the cursor in the requested
  body. The installed read-only distribution also completes through an unrelated
  body error. Full `make test bootstrap-check`, self-host IR/native convergence,
  ASan checks and distribution tests pass. IR SHA256 is
  `9f02e62820c6c9c524327a60340c1be1c164de09dc7654596951f2b6df039dda`.
  Evidence: `build/release-audit/completion-order-{focused,regression,sanitize,distribution}.log`.
  This is a checking-order improvement, not general syntax or statement recovery;
  G7 remains open for the documented unsupported contexts and editor validation.

- Real editor integration: `editors/neovim/cool.lua` configures Neovim's native
  LSP client, filetype detection, cool.mod workspace selection and completion.
  The config ships in the checksummed distribution. An explicit fetch target
  downloads Neovim v0.12.5 for Apple Silicon macOS into build/ and verifies SHA256
  `65fb000099e47ca1b762584c484cc833f40e30851a0ec450d4174e16317c1f9b`;
  normal `make test` never downloads an editor. The headless client test uses
  actual Neovim document synchronization, UTF-16 conversions, diagnostics,
  requests and edit application. It passes CRLF/emoji locations, cross-package
  definitions, applying a completion edit, shared-client unsaved dependencies,
  close/reset, standalone files without a module and graceful shutdown.
  Source/module bytes are unchanged; editor config/data/state/cache are isolated.
  Checkout, compiler-instrumented ASan (halt-on-error) and read-only installed
  configurations all pass. The installed run uses an unavailable compiler seed
  and blocked make. Existing `make lsp-test` also passes on both frontends, and
  the full distribution suite passes with the editor configuration included.
  CI explicitly fetches and tests the pinned client, including sanitizer and
  installed runs; remote CI has not been observed. This validates the real
  headless client, not visual popup/UI behavior. Compiler sources are unchanged
  in this milestone. Evidence: `build/release-audit/neovim-{checkout,sanitize,distribution,lsp-regression}.log`
  and `neovim-{client,sanitize,installed}-report.json`.
  G7 remains open for the documented analysis/recovery gaps, rather than absence
  of an actual editor client test. See [editor setup](editor.md#neovim-setup).

- Empty-file and declaration completion: the native collector recognizes
  declaration boundaries and `pub` qualifiers, filters typed prefixes, and does
  not offer declaration keywords in declared-name positions. Empty/whitespace
  files receive keyword candidates without needing an existing token. Completion
  alone tolerates a missing package header in its target buffer; other sources
  and ordinary checking/diagnostics keep the language's package rules. Both
  frontends pass empty/header-comment files, partial keywords, pub-qualified
  types, post-function declarations and name-position exclusions. The actual
  Neovim client opens a new unsaved module file, receives candidates before its
  package header, observes the ordinary package diagnostic, closes/reset it and
  verifies no file was written. Full `make test bootstrap-check`, exact self-host
  convergence, instrumented LSP/Neovim checks and read-only installed editor plus
  distribution tests pass. IR SHA256 is
  `40abf0a30d2e0df1651a461beed5085a6f19f2ee13c8d53f3346886ad8ad0a84`.
  Evidence: `build/release-audit/completion-declarations-{focused,editor,regression,sanitize,distribution}.log`.
  Broader statement recovery and uninstantiated generic/import-path contexts
  remain documented limitations; this does not close the full release audit.

- Versioned language-contract audit: added `specification.md` (1.0 draft 1)
  with the audited integer-token rules and explicit remaining grammar/semantic
  work, plus `compatibility.md` covering source behavior, bug fixes, tool/module
  interfaces, internal artifacts, C ABI and target boundaries. Neither document
  claims that 1.0 is released or the full specification is complete. Corrected
  stale implementation summaries that described methods, scoped loans, REPL
  imports/source reclamation and LSP services as absent, and corrected raw
  address spelling to `&raw`. The original required end state is preserved.
  The lexical audit reproduced both frontends accepting digitless `0x___` and
  `0b_` tokens as zero. Both lexers now count actual base digits and reject
  such tokens. Existing nonempty separator spellings retain their behavior.
  `make integer-tokens-test` compares 101 values with a Python integer oracle
  under tree/bytecode/native JIT and rejects 40 malformed tokens on both
  frontends; the instrumented ASan frontend also passes. Full `make test
  bootstrap-check`, exact self-host convergence and installed Neovim/distribution
  validation pass. IR SHA256 is
  `8d3f0d56f9b8c93f81b16f719d7d6731069dd0c734aeb04171bb4dbcd836ce29`.
  Evidence: `build/release-audit/integer-tokens-{focused,regression,sanitize,distribution}.log`.
  G1 remains open for the complete versioned grammar, numeric/encoding/layout/
  evaluation contract and its conformance mapping; a partial draft is not a
  substitute for that gate.

- External input-length audit: reproduced both frontends silently accepting a
  valid program followed by NUL and invalid trailing source. Both now validate
  actual byte lengths before source/format/bundle/REPL package parsing and REPL
  execution. Embedded NUL inside comments or literals is also rejected. Raw
  REPL command matching cannot treat a truncated `:quit` prefix as a command;
  recovery preserves existing state without executing a submission prefix.
  Seven placements pass rejection across check/scan/tree/bytecode/JIT, formatter
  source/destination preservation, native JSON byte ranges, bundle rejection,
  and REPL recovery on both frontends and the compiler-instrumented ASan build.
  LSP tests verify the offending UTF-16 range after emoji and CRLF handling.
  Full `make test bootstrap-check`, exact self-host convergence, instrumented
  input/LSP checks, and installed Neovim/distribution validation pass.
  IR SHA256 is
  `723fd207fd318b78c2c0ec2fa56539513e3baf20af11f3dd7d14fe2ca0b9e63e`.
  Evidence: `build/release-audit/input-bytes-{focused,regression,sanitize,distribution}.log`.
  This closes the demonstrated truncation defect, not the full encoding audit
  or G1/G2/G4/G9 release gates; remote CI remains unobserved.

- Expression-contract audit: specification draft 2 records the ten binary
  precedence levels, left associativity, binary EBNF and left-to-right expression
  sequencing. Added independent expected-value cases and an observable event
  trace rather than relying on equivalent compiler outputs alone. Tests cover
  arithmetic/logical grouping, short circuiting, function arguments, initializer
  source order, destination-before-value stores, array-base/index ordering,
  slice bounds and a once-evaluated method receiver. Rejection cases include
  non-bool logic, chained numeric comparisons, unsupported operators and unknown
  calls even in runtime-skipped logical operands. The suite executes each of
  both frontends plus the compiler-instrumented ASan frontend across five engines
  and optimized standalone builds: 19 valid cases, 25 ordered events and 12
  rejected forms pass. `make expressions-test` is part of the normal test suite;
  `expressions-sanitize-test` is included in CI. Local full regression and
  bootstrap results are recorded in `build/release-audit/expressions-regression.log`;
  focused/instrumented evidence is in `expressions-{focused,sanitize,final}.log`.
  Compiler source is unchanged. G1 remains open for complete primary/declaration/
  statement/type grammar and numeric/layout/cleanup/compatibility contracts;
  this audited expression core is not the complete language specification.

- Fixed-width integer audit: added a Python unbounded-integer oracle for all
  eight signed/unsigned widths, boundary and deterministic random operands,
  wrapping arithmetic, bitwise/shift/comparison/unary operations and integer
  casts. It exposed a real bootstrap discrepancy: large unsigned remainders
  were truncated to 32 bits by the retained seed's ARM64 lowering. Both language
  interpreters now compute unsigned remainder from quotient/product/subtraction,
  preserving the original seed while avoiding its faulty instruction sequence.
  This does not repair or promise compatibility for the legacy compiler itself.
  Signed division/remainder overflow is now checked for every operand width;
  earlier development builds only rejected i64 minimum / -1 and wrapped narrower
  quotients. LLVM runtime shift diagnostics also now refer to the operand width.
  Specification draft 3 records these decisions and wrapping/conversion rules.
  Both frontends pass 2,840 independent results and 19 runtime rejection cases
  across five engines and optimized binaries. Full regression, exact self-host
  convergence and installed Neovim/distribution validation pass. IR SHA256 is
  `0bcc61fc4c98a63e2e5b358f78a9be27b5e538b9c641b23f13d1f1d1453f5c74`.
  Compiler-instrumented ASan evidence is in
  `build/release-audit/integer-semantics-sanitize.log`; focused/full/installed logs
  are `integer-semantics-{focused,regression,distribution}.log` in that directory.
  The sanitizer target additionally instruments emitted LLVM and the C runtime;
  `integer-semantics-final-sanitize.log` records all oracle and failure cases
  passing with those runtime checks enabled. G1/G2/G9 remain open:
  this audit does not cover all floating conversion/encoding/inference contracts
  or replace ownership, full grammar and final release acceptance work.

- Floating conversion/literal audit: both hosts rejected representable subnormal
  source literals such as `1e-310` because strtod may set ERANGE for nonzero
  subnormals. A shared numeric adapter now accepts these finite values while
  rejecting literal overflow to infinity and nonzero underflow to zero. The
  seed is unchanged. Specification draft 4 records half-open float-to-integer
  range checks before truncation, non-finite rejection and subnormal source
  acceptance. A Python/IEEE boundary suite checks 105 expected values, 21 runtime
  failures and two literal range rejections on both frontends under five engines
  and optimized builds. Sanitizer coverage adds the ASan frontend and emitted
  LLVM, plus ASan/UBSan/float-cast-overflow on the C numeric runtime. Evidence is
  in `build/release-audit/float-conversions-{regression,sanitize,distribution}.log`.
  Full regression, self-host/bootstrap convergence and read-only installed
  Neovim/distribution checks pass; remote CI has not been observed.
  Compiler Cool sources are unchanged; the IR SHA256 remains
  `0bcc61fc4c98a63e2e5b358f78a9be27b5e538b9c641b23f13d1f1d1453f5c74`.
  The audit also reproduced integer-to-f32 double rounding for
  `9223372586610589697`: the current binary64 intermediary rounds down to
  `9223372036854775808`, while direct nearest binary32 is `9223373136366403584`.
  That issue, complete floating-token grammar and the arithmetic contract remain
  mandatory pre-freeze work. G1/G9 stay open; this is not a completed numeric audit.

- Direct integer-to-f32 rounding: resolved the double-rounding issue recorded in
  the preceding conversion audit. The shared numeric boundary converts signed
  and unsigned integers directly to binary32, widening only the already-rounded
  value into the compiler's internal representation. Specification draft 5 now
  requires direct rounding. Expanded conversion coverage from 105 to 269 oracle
  values: exact integer quotient/remainder and even-significand tie handling
  determine expected f32 results independently of Python's float conversion.
  Midpoint neighbors cover exponents 24, 31, 53, 54, 62 and 63, both signs,
  odd/even significands and 64 deterministic random integers. The expanded suite
  demonstrably failed before the fix (`float-rounding-before.log`). All existing
  21 checked conversion failures and two literal range rejections remain in the
  suite. Evidence is recorded under `build/release-audit/float-rounding-` with
  `regression.log`, `sanitize.log` and `distribution.log`; the sanitizer run
  includes the instrumented compiler and emitted LLVM plus runtime float-cast-
  overflow checks. All cases pass, along with full regression, self-host/bootstrap
  convergence and installed Neovim/distribution checks. Remote CI is unobserved.
  No Cool compiler IR changed; the self-host IR SHA256 remains
  `0bcc61fc4c98a63e2e5b358f78a9be27b5e538b9c641b23f13d1f1d1453f5c74`.
  Full floating-token grammar and arithmetic, inference and release-wide audits
  remain open. Resolving this concrete rounding defect does not close G1/G9.

- Decimal floating-token grammar: reproduced valid finite decimal spellings
  such as `18446744073709551616.0` being rejected as overflowing integers by
  both lexers. Scanning now records overflow, stops integer accumulation and
  continues classifying the full token; only a remaining integer token reports
  integer overflow. Float conversion uses the complete source spelling. Draft 6
  publishes decimal fraction/exponent EBNF, digit/sign/separator/suffix rules and
  range behavior. The new suite checks 28 Python-oracle values, including
  2,000-digit significands with compensating exponents, 19 malformed/range cases,
  and formatting followed by execution. Both frontends and the ASan frontend
  pass five engines and optimized native builds. Full regression, self-host/
  bootstrap convergence and installed Neovim/distribution checks pass. Remote
  CI is unobserved. Logs are
  `build/release-audit/float-literals-{focused,regression,sanitize,distribution}.log`.
  The new test is in the ordinary test target and sanitizer CI configuration.
  Self-host IR SHA256 is
  `bea50524842a2150db96ec7a07dada92f8b027fabaa74a3219c8de515b99699c`.
  This completes the audited decimal floating-token grammar; it does not close
  the complete language grammar, encoding, floating arithmetic or release audit.

- Declaration/type contract: draft 7 adds EBNF for package/import, nominal types,
  fields/variants, functions/methods, C declarations/exports, parameters, generic
  lists, borrow contracts and type forms. It states duplicate-name rules, unit
  variants (including explicit void payload spelling), private fields, nominal
  forward references, required type arguments, resource limits and remaining
  lazy-template validation. The audit reproduced both frontends accepting
  duplicate parameter names on extern C functions: body-local checks never ran
  for them. Parameter uniqueness is now checked in FunctionSignature, including
  ordinary/exported functions and instantiated generic signatures. The new
  declaration suite passes 11 positive cases, five duplicate signatures and
  30 other malformed/invalid declarations on both frontends and the ASan build.
  Full regression, self-host/bootstrap convergence and installed Neovim/distribution
  checks pass. Remote CI remains unobserved.
  Evidence is in `build/release-audit/declarations-{focused,final,regression,sanitize,distribution}.log`.
  Self-host IR SHA256 is
  `a63be7e6fbca71b821c1f140b0475cad299787daee07d5c6e4815f6efc4d3cad`.
  G1 remains open for complete statement/primary grammar, full package/source
  rules and semantic contracts; G4/G9 are not closed by a declaration-only audit.

- Statement/control-flow contract: draft 8 defines blocks, bindings, assignments,
  if/while/for, loop exits, return, enum match, defer and unsafe forms. An exact
  observable trace checks immediate defer argument capture, reverse scope exit,
  result-before-cleanup ordering, continue/update/break behavior, once-evaluated
  matching and owner drops interleaved with explicit deferred observers. The
  audit also reproduced for initializers rejecting projected assignments while
  allowing them elsewhere. Both parsers now accept N_STORE through their normal
  statement and loan/ownership analysis. Array elements, struct fields and
  reference dereferences work; immutable destinations and active shared loans
  still reject writes. The suite passes 31 ordered events and 23 negative cases
  on both frontends and the ASan compiler across five engines and optimized
  binaries. Full regression, self-host/bootstrap convergence and installed
  Neovim/distribution checks pass; remote CI is unobserved. Evidence is in
  `build/release-audit/control-flow-{final,regression,sanitize,distribution}.log`.
  Self-host IR SHA256 is
  `b868ab248bfcd9813a427f2321292aac247266ddb04ec2a3e9a94a99a792c93f`.
  Runtime-failure unwinding, complete primary grammar, package rules and other
  remaining release-wide contracts remain open; structured-exit evidence is not
  a claim that every runtime failure performs full stack cleanup.

- Primary expression contract: specification draft 9 supplies the remaining
  core primary productions: prefix/postfix forms, named/method calls, aggregate/
  enum/array/slice construction, sizeof/len, owners, references, raw borrowing and
  explicit casts. It records initializer completeness and trailing-comma rules,
  name-resolution restrictions, slicing bounds, required places and unsafe
  obligations. A combined executable grammar test verifies successful forms and
  zero surviving owners, with 26 rejection cases covering malformed initializers,
  calls, enum payloads, casts, indexing and raw anchors. Both frontends plus the
  instrumented compiler pass five engines and optimized builds. The new ordinary
  and sanitizer targets are wired into test/CI. Evidence:
  `build/release-audit/primary-forms-{focused,sanitize}.log`.
  Compiler/runtime sources are unchanged in this milestone. The remaining-spec
  list now distinguishes published core productions from their release-wide
  conformance audit and unfinished source-file/package grammar. No release gate
  is closed by these grammar examples; remote CI has not been observed.

- Source/package assembly contract: specification draft 10 records file versus
  directory selection, package declaration consistency, import-path identity,
  file-local aliases, visibility and root-only test files. A real multi-file
  fixture reproduced `cool test` reading a dependency's `_test.cool` sources and
  failing on that dependency's test-only import. The driver now selects test
  files only for the requested package before scanning metadata or resolving
  edges. The same dependency's tests are included when it is explicitly selected
  as the test root. Production imports, standalone files and normal directory
  compilation preserve their selection rules. Fixtures verify two aliases with
  the same spelling in different files, private cross-file helpers, rejection of
  leaked/private/duplicate aliases and inconsistent/duplicate/missing headers,
  and root test failure visibility. Both frontends and the ASan frontend pass
  five run engines and both test backends. Full regression, self-host/bootstrap
  convergence and installed Neovim/distribution checks pass. Remote CI remains
  unobserved. Evidence is in
  `build/release-audit/package-rules-{before,focused,final,regression,sanitize,distribution}.log`.
  Compiler/runtime sources are unchanged; this change is in source selection and
  its language contract. Module-format/version/checksum policy, complete encoding
  and semantic conformance remain open release requirements.

- Supported-target layout contract: specification draft 11 defines scalar and
  handle sizes/alignments, field order/padding, array stride and zero-sized cases,
  enum tags/payloads, slice descriptors and representation validity obligations.
  A ctypes oracle independently models 24 nested/random structures and alignment
  wrappers; explicit byte probes verify enum declaration tags, payload offset and
  little-endian storage. The suite compares 191 values and rejects four oversized/
  recursive cases on both frontends and the instrumented compiler, with five
  engines and optimized binaries. Generated LLVM and the C runtime are also
  checked with ASan/UBSan. Evidence:
  `build/release-audit/layout-contract-{focused,sanitize}.log`.
  Compiler/runtime sources are unchanged. The new suite is wired into ordinary
  tests and sanitizer CI; remote CI has not been observed. Layout tests do not
  discharge ownership/aliasing validity, full cross-language ABI, encoding or
  whole-spec conformance gates, which remain under audit.

- Source encoding contract: draft 12 requires well-formed UTF-8 throughout
  external source/submission/manifest input, with ASCII identifiers, no implicit
  normalization/BOM stripping, and existing NUL rejection. Both frontends had
  accepted invalid UTF-8 inside comments/literals; ValidateInput now rejects
  isolated/truncated continuation sequences, overlong encodings, surrogates and
  values beyond U+10FFFF before parsing or executing a prefix. A Python decoder
  oracle covers 143 invalid sequences and 14 valid scalar/control boundaries,
  exact native byte positions, preserved formatter files, manifest rejection and
  REPL state recovery. LSP diagnostics for a closed malformed dependency retain
  its URI and UTF-16 replacement-character range instead of falling back to the
  open file; restoring the dependency clears the diagnostic without source edits.
  Both frontends and the compiler-instrumented ASan build pass the input and LSP
  suites. Full regression, self-host/bootstrap convergence and installed
  Neovim/distribution checks pass; IR SHA256 is
  `44a53172f2a2b66644170e2e66d88037d7f58f869f746dace42dbad198a4b00d`.
  Evidence: `build/release-audit/source-utf8-{focused,regression,sanitize,lsp-final,distribution-final}.log`.
  The encoding decision is explicit pre-freeze behavior; it does not close the
  remaining whole-spec conformance, generics, ownership and release gates.

- Unused generic function signatures: draft 13 makes declaration-time grammar
  validation explicit. Previously the parser skipped every token between the
  generic parameter list and the opening body brace, accepting duplicate value
  parameters, malformed type/parameter/result syntax and unknown names in borrow
  contracts until a specialization was requested. Both frontends now use a
  bounded syntax-only type walk and a stack-local parameter-name table without
  creating concrete type bindings or mutating layouts. The declaration suite
  covers 15 valid cases and 64 rejections, including unused templates and the
  nesting/argument limits. A REPL regression rejects an invalid template, then
  declares and calls a corrected template with the same name while preserving
  an existing variable. Both frontends and the ASan compiler pass. Full regression,
  self-host/bootstrap convergence and installed distribution/Neovim checks pass.
  Evidence:
  `build/release-audit/template-signature-{build,focused,final,regression,sanitize,distribution}.log`.
  IR SHA256: `877765896b066ed32b8aa991099fdde9ccceb5219bfa553f5c352a365a3c3b16`.
  This preflight does not discharge concrete type resolution, unused template
  body/layout validation or the remaining G1/G4 requirements.

- Non-dependent template signature types: draft 14 extends declaration-time
  checking to unknown nominal names, imported type visibility and exact nominal
  type argument counts. Type parameters take precedence over builtin spellings,
  consistent with specialization; forward nominal declarations remain available.
  Both frontend implementations reuse collected names/imports and record editor
  references without allocating instantiated types or forcing layouts. The
  declaration suite now covers 17 valid cases and 75 rejections, plus four
  bundled-package visibility/arity cases and transactional REPL recovery. Both
  normal frontends and the ASan compiler pass. Full regression, self-host/bootstrap
  convergence and installed distribution/Neovim checks pass. Evidence:
  `build/release-audit/template-names-{build,focused,final,regression,sanitize,distribution}.log`.
  IR SHA256: `1d7ca81f519e371f86f2bcab37c016b04cf525b04a92f3cde550dcb4be38cfda`.
  Further probes still accept unused templates with void parameters/elements,
  oversized arrays and malformed body expressions (recorded in
  `build/release-audit/template-names-remaining.log`). These are follow-up defects,
  alongside concrete layout/borrow semantics and unused generic bodies; this
  change does not close G1/G4 or the other mandatory release gates.

- Template signature value/element validity: draft 15 extends preflight to
  reject builtin void parameters, void sequence/reference elements, void generic
  arguments and literal array lengths outside 0..65,536, even when unused. A
  syntax-result flag distinguishes bare builtin void from raw pointers and type
  parameters (including a parameter named void), preserving existing substitution
  behavior without allocating layouts. Boundary regressions include zero and
  65,536-element arrays, unsigned lengths above signed-i64 range, nested invalid
  elements, legal void results/raw pointers and a called shadowing template.
  Twenty valid declarations, 87 rejections, four bundle cases and REPL recovery
  pass on both frontends and the ASan compiler. Full regression, self-host/bootstrap
  convergence and installed distribution/Neovim checks pass. Evidence:
  `build/release-audit/template-types-{build,focused,regression,sanitize,distribution}.log`.
  IR SHA256: `75ccae88a89675684d6021fd10ee62188b8bb84d9b7db5f6812acec19dafa91b`.
  Unused body syntax and dependent layout/ownership/borrow semantics remain open;
  this change resolves the previous void/array probes, not the remaining gates.

- Unused generic body grammar: draft 16 replaces unchecked body skipping with
  allocation-free statement/expression syntax parsing after declaration collection.
  Both frontends reject malformed initializers, operands, calls/type lists,
  constructors, indexes/slices, conditions, for headers, match arms, return/defer
  and loop control before any specialization. A stack-local table tracks parameters,
  block bindings, loop initializers and match payloads so locals can shadow import
  aliases; a positive regression covers scope exit and restored qualified enum
  construction. Fifty invalid unused bodies and REPL rejection/redeclaration pass.
  Generic versions of the existing primary-expression and control-flow programs
  preserve their exact output across five engines and optimized native binaries.
  Full regression, self-host/bootstrap convergence, compiler-instrumented ASan
  and installed Neovim/distribution checks pass.
  Evidence: `build/release-audit/template-body-{final-build,final-focused,final-regression,final-sanitize,distribution}.log`.
  IR SHA256: `a98a176f87ccb2bd911a880d4f73bef9f295dd899389d6d49a41e47d40ccf528`.
  Concrete expression typing, return coverage, moves/loans and unused nominal
  template layouts still need audit; mandatory gates remain open.

- Project performance and directory scan snapshots: seven repetitions on the
  same pinned frontend separate direct check/LLVM emission, native O2 link,
  cold/warm/edited CLI graphs and acknowledged REPL updates. The expanded Tally
  has 526 sources in 11 packages. Warm CLI checks improve from 133.253 to
  121.029 ms median; one-file edits from 135.125 to 124.052 ms. An atomic
  per-directory snapshot reduces metadata opens while content hashing,
  membership rediscovery and old per-file fallback preserve invalidation. The
  snapshot retains only current records. Permanent cache regressions cover
  fallback without scanning, identical-content paths and membership changes,
  malformed JSON/shape/record failures and bounded edit histories, plus existing
  same-mtime/frontend/runtime/concurrent checks. Native project JSON agrees with
  Python Counter; seven REPL sessions verify 448 replacements and zero owners.
  Raw reports and methodology: `docs/benchmarks/project-{before,after}-arm64.json`,
  `tools/bench_project.py`, `docs/performance.md`. These comparisons use the
  pre-coercion-audit frontend; compiler startup, frontend work and driver work
  are not conflated. External downloads, ordinary CLI make overhead and broader
  application workloads remain outside these samples; G8 stays open.

- Implicit typing and operand-order audit: draft 17 records local/literal
  inference, permitted scalar conversions and binary operand selection. Earlier
  checking rejects i8+i64 and f32+f64 with the narrow value first, while accepting
  the reverse order; `CoerceBinary` now adopts permitted literals and chooses a
  lossless widening direction symmetrically. Shift counts stay independently
  typed so a wide count cannot silently widen the left operand or evade its
  width check. A separate probe found u64 literals above i64 maximum being
  mistaken for small negative bits by the implicit float range test; both
  frontends now reject that in assignments and both operand orders. Explicit
  conversions remain the intentional rounding path. The oracle covers 541
  numeric outputs over all integer pairs, floating/literal behavior and pointer
  symmetry, 36 rejection cases, return narrowing and separately run invalid
  mixed-width shift counts across five engines and optimized binaries. Full
  regression, self-host/bootstrap convergence, compiler-instrumented ASan and
  installed Neovim/distribution checks pass.
  Evidence: `build/release-audit/coercion-{before,unsigned-before,final-build,final-focused,final-regression,final-sanitize,final-distribution}.log`.
  IR SHA256: `f5f4bc94b8b7c5641c84bb3b3d8f23e9cb44a7684ff1cbb9dd8b6fcf77d7eaa4`.
  This is an explicit pre-freeze numeric behavior decision; floating arithmetic,
  whole-spec conformance, dependent templates and other release gates remain open.

- Coercion maintenance: replaced the 236-line port-generated application path
  with readable `Coerce` in `33-implicit-types.cool`. Both binary selection and
  conversion application now consult `CanImplicitCoerce`; literal adoption,
  clone allocation/provenance and sibling-list topology remain intact. Expanded
  the independent numeric regression to 544 outputs with multiargument and
  named-field initialization ordering. Focused checks, compiler-instrumented
  ASan, full regression, bootstrap convergence and installed editor/distribution
  checks pass.
  Evidence: `build/release-audit/coercion-refactor-{build,focused,regression,sanitize}.log`.
  IR SHA256: `566dc496751ff2afb17b0ca1f1ad0ec92e124d16179973f415f8ace25d05e3c0`.
  This structural cleanup does not freeze the language or close G3.

- Module format/resolution audit: malformed/future workspace selectors and
  block structures, unused unsupported checksum rows and wrong cached/vendor
  identities previously passed unchecked; normal `/v10` paths were rejected.
  These now fail or resolve according to the documented contract in
  `modules.md`. Quoted paths preserve `//`, including manifest write/read;
  canonical SHA-256 h1 records and vendor map shape/duplicate keys are checked.
  Temporary real tagged Git repositories exercise fetch/archive, transitive MVS
  prerelease selection, offline/frozen CLI execution, tamper and identity
  rejection. `module-contract-test` is part of the full test target and CI.
  Installed editor/distribution validation passes. Evidence:
  `build/release-audit/module-contract-distribution.log` and the module-contract
  and project results in `coercion-refactor-regression.log`.
  Checksums are verification records, not an exact graph lock; local workspaces
  remain mutable, and there is no public proxy/checksum service or cool.lock
  protocol. No 1.0 gate is closed by this local module audit.

- Generic nominal declaration audit: draft 18 checks unused struct/enum member
  syntax, duplicate names, nominal type names/privacy/arity, void field types,
  literal array limits and nonempty enums before layout specialization. Earlier
  frontends accepted each demonstrated invalid declaration until it was used.
  The preflight reuses template type syntax without fake concrete arguments or
  layout materialization; scratch duplicate-name records are recovery-owned.
  Regression covers 34 malformed unused declarations, three imported type checks,
  forward/concrete layout execution on five engines plus O2, and rejected REPL
  declaration/name rollback. Updated the older unknown-type lazy-layout fixture
  to retain dependent oversized-layout retry checks and separately exercise 128
  declaration rejections followed by name reuse. Both frontends, compiler ASan,
  full regression/bootstrap convergence and installed editor/distribution pass.
  Evidence: `build/release-audit/template-aggregate-{build,focused,repl,regression,final-regression,sanitize,distribution}.log`.
  The initial full regression failure was the obsolete delayed-error fixture;
  the final regression is the completed passing run. IR SHA256:
  `670a1b5804d7c9ef84f372e5ee43fd28f79195529ab4bc61645215b1b1abeecd`.
  Dependent layouts, expression semantics and other release-wide gates remain open.

- Floating arithmetic/unordered comparison audit: draft 19 records binary64
  primitive evaluation, per-operation f32 normalization, signed zero/subnormal/
  infinity/NaN results and unordered comparisons. An exact rational oracle for
  386 finite operand pairs reproduced the retained bootstrap seed returning
  true for NaN equality. Both frontend Arithmetic paths now inspect carrier
  magnitude bits before comparisons and return true only for != when either
  operand is NaN; this avoids using the seed's faulty floating comparison to
  detect the condition. LLVM already uses ordered/une predicates. Regression
  compares 1,711 exact bit/classification/comparison outputs and seven invalid
  operators on five engines plus O2 in both frontends. Full regression and
  bootstrap convergence, compiler ASan and generated LLVM/runtime ASan/UBSan,
  and installed editor/distribution validation pass. NaN payloads are unspecified;
  the finite oracle cases are deterministic evidence, not exhaustive arithmetic
  equivalence. Evidence:
  `build/release-audit/float-arithmetic-{focused,build,final-focused,regression,sanitize,distribution}.log`.
  IR SHA256: `23bfb606877c2cdcc29784bbde7b725184a0c11705e2d67ec2855da3d8d7490d`.
  Remaining whole-spec, template semantics and release-wide gates stay open.

- Default development CLI performance: the benchmark now captures a separate
  source/artifact checkout, preserves dependency mtimes, verifies make -q
  readiness and keeps actual driver lock/make checks inside default invocation
  timers. Seven repetitions measure Tally and its synthetic 512-function
  extension separately; source/artifact inventory and all raw samples are in
  `docs/benchmarks/default-cli-arm64.json`. Warm default checking is 106.381 ms
  and 147.630 ms respectively. Alternating same-snapshot default/explicit pairs
  observe 14.575/13.296 ms additional default-path cost; this is not a predicted
  speedup. Check/run/cold-cached-edited O2 and cached LLVM costs are separately
  reported in `performance.md`, and every run/native output matches the JSON
  Counter oracle. The snapshot pins the pre-NaN-fix frontend by digest; later
  source changes cannot affect these observations. Source rebuild, public
  dependency transport and a wider real application corpus remain outside this
  measurement; G8 stays open.

- Batched native dependency checking: default native build/LLVM execution now
  acquires one driver lock and invokes make once for frontend plus runtime.o.
  Explicit COOL_FRONTEND still validates its executable and checks only the
  runtime; ordinary checking retains frontend-only dependencies. The actual
  dependency recipes and all content/artifact cache identities remain active.
  The cache regression forwards real make, refreshes a changed runtime object,
  verifies changed standalone output/cache invalidation, and ensures an external
  frontend does not create a checkout frontend. Project/cache and installed
  editor/distribution validation pass. Evidence:
  `build/release-audit/batched-ensure-{focused,project,distribution}.log`.
  Identical frontend/runtime seven-sample before/after snapshots are published in
  `docs/benchmarks/default-cli-batched-{before,after}-arm64.json`: cached O2 build
  medians decrease 103.063 to 95.269 ms for Tally and 121.760 to 113.160 ms for the
  expanded corpus. Cached-command observations support a local 7.6%/7.1%
  improvement; cold/edit variability and unchanged-path control measurements
  are documented without claiming all differences as dependency-check savings.
  G8 remains open for broader real projects and incremental compilation scope.

- Arithmetic evaluator maintenance: replaced the production evaluator's
  253-line generated dispatch with 58 lines of direct branches and descriptive
  values. Width-specific division/shift validation, unsigned comparisons and the
  seed-safe full-width remainder formula remain unchanged; floating carriers,
  f32 normalization, NaN predicates and final integer normalization are retained.
  The separate bootstrap evaluator provides a compact semantic counterpart.
  Full regression/self-host/bootstrap convergence passes, as do the independent
  integer, exact-rational floating and coercion suites with compiler ASan and
  generated LLVM/runtime instrumentation. Installed editor/distribution checks
  also pass. Evidence:
  `build/release-audit/arithmetic-refactor-{build,final-build,regression,sanitize}.log`
  and `module-roots-distribution.log`. IR SHA256:
  `3b4e481008aaedb274b3a65bab85a11c6ba7492d2d32316ed8ad18061c271685`.
  This removes one generated numeric section; remaining compiler maintenance and
  mandatory release-wide gates are not closed.

- Local/workspace module graph audit: main plus every addressable local root now
  seeds outgoing requirements into MVS. Previously an empty main requirement
  list left an imported local library's cached transitive dependency unresolved.
  Unversioned local roots receive no fake selection/checksum; explicitly required
  local roots retain mutable source semantics. A transitive tagged-main request
  validates its version but cannot fetch/checksum/select or overwrite the invoking
  checkout. Conflicting main replacements/workspace roots and two different
  workspace directories for one identity fail explicitly; same-directory repeats
  are deduplicated. `modules.md` records these eager-root and identity rules.
  Replace/workspace regression fixtures execute actual imported transitive CLI
  programs, include an unused peer raising a dependency's selected version, and
  verify frozen/offline failure, sum preservation, tampering and main shadow
  prevention. Final module-contract/project and installed editor/distribution
  checks pass; the preceding full regression also covers the graph-root changes.
  Evidence: `build/release-audit/module-roots-{focused,final-focused,final-project,distribution,final-distribution}.log`
  and `arithmetic-refactor-regression.log`. Local source contents remain mutable;
  fixed source identity is not a frozen-content guarantee or exact graph lock.
  Whole-language and remaining distribution gates stay open.

- Slice descriptor references (specification draft 20): both frontends accept
  direct shared/exclusive references to slices and non-owning aggregates mixing
  slices with reference fields. Descriptor length reads and element capability
  loans are distinct; owner-element moves/replacement retain their backing roots.
  Store address evaluation pins storage for RHS reads, while a separate enclosing
  capability check preserves rejection through computed shared receivers. The
  existing exclusive-storage suite caught and verified this capability regression
  during development. Obsolete rejection fixtures now cover still-unsupported
  nested descriptor storage. Thirty-one negative programs, thirty independent
  permission-model queries, five engines/O2 and persistent REPL tests pass on
  both frontends. Full regression and native/legacy bootstrap convergence pass,
  as do instrumented compiler and generated LLVM/runtime checks and installed
  editor/distribution verification. Evidence:
  `build/release-audit/slice-descriptors-capability-focused.log`,
  `slice-descriptors-verified-regression.log`,
  `slice-descriptors-verified-sanitize.log` and
  `slice-descriptors-verified-distribution.log`. Replacement through borrowed
  descriptors, stored descriptor references, reference-containing owners and
  projection-specific return anchors remain mandatory lifetime work; G2/G4 are
  not closed by this extension.

- REPL allocation lifecycle audit: a private copy of emitted compiler IR wraps
  compiler calls to CAlloc/StrNew/FileRead/Free without modifying production
  allocator behavior. Fourteen fixed-history rollback, source-compaction,
  replacement, scratch and framed package-load failure workloads finish with
  identical tracked live bytes/count after 64 and 1,024 submissions. Distinct
  executed literals intentionally retain session text (146 to 2,066 allocations
  in the control workload). `repl-lifecycle-test` is part of ordinary regression
  and CI. `docs/repl-memory.md` inventories roots and transaction cleanup, cache
  limits, escaped literal policy and excluded host/JIT allocation paths. Equal
  totals do not prove leak freedom or constant RSS; no missing release was
  reproduced, so no production reclamation fix was invented. The final full
  suite passes and `build/repl-lifecycle-audit.json` pins measured artifacts.
  G6 remains open for host/JIT accounting and complete resource acceptance.

- Borrowed-type maintenance: replaced 161 lines of port-generated provenance
  and storage-boundary dispatch in production `03-types.cool` with 42 lines of
  direct branches and named layout/field values. Value-level borrowing and
  owning/slice allocation boundaries retain the compact bootstrap semantics;
  storage restrictions were not loosened. `compiler-invariants.md` explains why
  owner contents are not recursively treated as value-level borrow roots and why
  extending owned borrowed storage requires separate lifetime analysis. Full
  regression, native/legacy bootstrap convergence, instrumented compiler and
  generated LLVM/runtime descriptor/reference checks, REPL allocation accounting
  and installed editor/distribution verification pass. Evidence:
  `build/release-audit/borrow-predicates-{build,regression,sanitize,distribution}.log`.
  Current compiler IR SHA256:
  `82ca7a0dd7ee1b507a61c4d41e8a8d2bd9be1aa1fb5b400893e94c60eeecf47c`.
  Remaining generated compiler sections and the complete G3 audit stay open.

- Template expression-root audit (specification draft 21): unused generic
  functions previously accepted undefined expression names. Both frontends now
  resolve independent lexical/type/function/import roots after declaration
  collection, reject unknown or out-of-scope locals and private imported symbols,
  and preserve forward declarations and import shadowing. Nineteen rejection
  cases, successful dependent-member specialization and failed concrete member
  checks pass on both frontends and five engines/O2; REPL rejected-declaration
  retries pass. The older failed-specialization fixture now uses a genuinely
  type-dependent missing field, preserving artifact cleanup coverage after names
  are rejected earlier. Full regression/bootstrap convergence, compiler ASan,
  REPL function ASan/UBSan and installed editor/distribution checks pass.
  Evidence: `build/release-audit/template-names-{build,final-build,focused,final-focused,repl,final-regression,sanitize,repl-sanitize,distribution}.log`.
  Current compiler IR SHA256:
  `c1296e446a6f165e468cb76f9e6756a8e78e2931127b3957d53fa8e5a6b6286d`.
  Type-dependent members and full unused-body typing/arity/ownership remain
  separate semantic work; the language conformance gate remains open.

- REPL host/JIT lifecycle audit: host context is a process singleton, resolver
  response storage is static, and the FFI adapter owns stack argument/cif values
  rather than a dynamic closure or dlopen cache. Private emitted-IR wrappers now
  account for NativeJitAlloc/Free mapping address, exact size and page-rounded
  bytes, rejecting duplicate mappings, unknown/double frees and mismatched sizes.
  At 64/1,024 histories, warm replacements retain exactly two current mappings
  and release every replaced mapping; cold/new JIT runtime rollback releases all
  new mappings; existing JIT rollback retains exactly its one committed mapping.
  Output, assertion diagnostic and owner-count checks are independent of mapping
  totals. `repl-jit-lifecycle-test` is part of normal regression/CI, and both heap
  and JIT lifecycle targets pass against the current pinned IR. Evidence:
  `build/release-audit/repl-jit-lifecycle-focused.log` and
  `build/repl-jit-lifecycle-audit.json`. `repl-memory.md` records current-code
  process lifetime, external library/Python allocations and non-RSS boundaries.
  No production mapping leak was reproduced; full resource-policy acceptance
  and broader unsupported session operations remain G6 work.

- Fragmented REPL storage (specification draft 22): deleting a large interior
  array previously left unusable space below a live scalar and rejected a new
  array despite sufficient available slots. Both frontends now share first-fit
  reservation for named/anonymous session allocations, pin visible bindings and
  every current-input temporary, and keep ordinary function allocation unchanged.
  Live addresses never move; executing inputs zero every reserved range before
  owner initialization can fail. Reservation records use transaction scratch and
  are reclaimed after success/error; old DropSlot records remain protected by
  snapshot-prefix cleanup. Eight sessions cover large/multiple array reuse,
  returned aggregates, owner/type changes, parser/runtime rollback over stale
  scalar slots, live root rejection, descriptor references and anonymous matches.
  Both frontends and the instrumented compiler pass. Two 64/1,024 history models
  have identical final tracked live bytes/count, bringing the heap lifecycle
  corpus to sixteen bounded-history workloads. Full regression, native/legacy
  bootstrap convergence, sanitizer and installed editor/distribution verification
  pass. Evidence: `build/release-audit/repl-holes-{build,focused,storage,regression,sanitize,lifecycle,distribution}.log`.
  Current IR SHA256:
  `d7a32a6b2a846b3966c2ed0eecc7b5fd32f8fc008ce496690011a15e3f659f0d`.
  Contiguous-gap fragmentation and live declaration/cache policy remain explicit;
  this improves reclamation without declaring every G6 requirement complete.


- Mixed owning/borrowed aggregate audit (specification draft 23): allow structs,
  arrays and enums to combine stored scoped references/slices with owning fields
  whose heap payloads are borrow-free. Reproduced and fixed a move accepted under
  a shared physical loan, and a safe move-return rejected because its value
  provenance was lost. Move nodes now retain their source value separately from
  their address; return regions and nested receiver payload loans follow it.
  Owned pointee getters through receivers retain physical storage, while pointers
  into a by-value parameter's owned allocation remain rejected. A further audit
  found that clearing a moved mixed aggregate completely could invalidate its
  retained receiver's reference fields. Interpreter/bytecode/native JIT and typed
  LLVM clearing now preserve borrowed fields and enum tags while clearing owning
  subobjects. Direct moved bindings retain whole-root checking; this does not
  implement granular partial moves or borrowed owned heap allocations. Tests
  cover nested/generic aggregates, exclusive retained receivers, repeated enum
  matches, anonymous payload cleanup, move/return contracts, checked empty-owner
  faults, seventeen rejected programs, fourteen independent permission queries
  and persistent REPL roots on both frontends, five engines and O2. ASan compiler,
  generated LLVM load/store checks and ASan/UBSan runtime pass. Full regression,
  native/legacy bootstrap convergence and installed editor/distribution pass.
  Evidence: `build/release-audit/mixed-owned-{build,regression,sanitize,distribution}.log`.
  Current IR SHA256:
  `32139c192d87d8f71abb158c1bf06084284c3e773b945653fc6de9946eb0fb42`.
  This extends ordinary borrowed aggregate use; G2 and the overall release gates
  remain open for the documented heap/nested/replacement lifetime work.


- Borrowed owning heap implementation (specification draft 24): owners now carry
  the external borrowed provenance/capabilities of their payloads. A recursion
  path terminates nominal-own cycles in borrowed/mutability property queries and
  storage validation. New expressions promote initializer regions and loans;
  owner dereference loads retain the owning value as their source. A consumed
  owner may return an external shared/exclusive reference under its contract,
  while references into its own heap remain tied to physical ownership and
  cannot escape a by-value owner. Fixed a consumed exclusive getter's temporary
  self-loan conflict by reading the owner handle without prematurely acquiring
  its payload capability. Owner handles always clear on transfer, irrespective
  of borrowed payloads, preventing dropped/double-owned transferred allocations.
  Tests cover recursive and generic heaps, nested owners, arrays, enum/anonymous
  cleanup, slices, local lifetime-aware owner replacement and persistent REPL
  roots. Twenty rejected programs and twelve independent capability queries pass
  on both frontends, five engines and O2; a 64-link recursive enum chain has
  exactly 65 live owners and returns to zero after transfer/destruction. The
  instrumented compiler and LLVM/C runtime ASan/UBSan pass, as do full regression,
  native/legacy bootstrap convergence and clean external editor/distribution.
  Earlier fixtures rejecting all borrowed owning heaps were replaced by actual
  nested-storage/lifetime violations, including shorter-scope slice installation.
  Evidence: `build/release-audit/heap-borrows-{build,focused,final-focused,regression,sanitize,distribution}.log`.
  Current IR SHA256:
  `6547cf8399019ff45eb8beef008ee94498b926dea23af261fdaac3bf6fe88817`.
  Cross-call replacement lifetimes, stored references to already-borrowed pointees
  and borrowed slice elements remain mandatory unfinished work. G2 and 1.0 remain
  open; this implementation does not replace those requirements with unsafe code.

- Borrowed type graph complexity audit: replaced active-path recursion guards
  with independent per-query/per-validation visited bitmaps. Shared owning DAGs
  no longer repeat the same reachable subgraph exponentially. Reference storage
  checks resolve lazy nominal layouts before reading fields. Thirty cyclic,
  shared-diamond and seeded graphs produce 524 borrowed/mutability queries checked
  against a separate worklist oracle. Private LLVM instrumentation bounds both
  property and storage-validation visits by types/edges, including depth-40
  `new` expressions. A late invalid storage branch, generic concrete layouts and
  REPL type-ID rollback are covered on native/legacy and ASan compiler frontends.
  Full regression, native/legacy bootstrap convergence, heap ASan/UBSan and clean
  external editor/distribution checks pass. Local direct-check timing observations
  and their limits are documented in `docs/performance.md`; total compilation
  still performs multiple independent queries and is not certified linear.
  Evidence: `build/release-audit/borrow-graphs-{regression,sanitize,distribution,final-focused,final-sanitize}.log`;
  raw local measurements: `build/release-audit/borrow-graphs-timing.json`.
  Current IR SHA256:
  `497007cf5690d20ef1bdf5862efe2ba70f9c4359000440e5df1526482ef1aeb6`.
  This improves G2/G3/G8 evidence; all ten release gates remain open with the
  mandatory nested storage, replacement lifetime and other listed work unfinished.

- Mutable local reference replacement (specification draft 25): mutable
  reference bindings and struct/array/enum/generic values can be replaced,
  including reference fields in locally owned heaps and mixed owning values.
  Existing physical mutability/conflict checks and original-marker depth checks
  reject shorter-lived sources. Return contracts include every possible source.
  Rebinding a shared reference changes its binding, without granting write access
  to its referent. Possible old/new roots remain conservatively protected.
  Identical retained holder/root/parent/mode/layer edges are merged rather than
  retaining one record per assignment. Thirty-two independently modeled root/mode
  queries and sixteen negative programs check lifetimes, physical aliases,
  deferred captures and unsupported reference receivers with specific diagnostics.
  Five engines, both frontend O2 builds and compiler/runtime ASan/UBSan pass.
  REPL tests distinguish compile-only rollback from conservative runtime-failure
  retention; failed RHS values remain unchanged before their store executes.
  Sixty-four and 1,024 repeated replacements have identical final tracked bytes/
  count and identical peak tracked bytes (30,001,152 locally). The broader
  allocation corpus now has seventeen bounded histories plus distinct-literal
  policy retention. Full regression, native/legacy bootstrap convergence and
  clean external editor/distribution verification pass. Prior blanket rejection
  fixtures now test real shorter-scope installation or live-loan conflicts.
  Evidence: `build/release-audit/reference-replacement-{final-build,final-focused,final-regression,final-sanitize,final-distribution,final-lifecycle}.log`.
  Current IR SHA256:
  `b8c350621af06ba0fb29373961a80c27f864e8722fea18d2e4c07d54550035ba`.
  Cross-call borrowed replacement, nested stored borrowed pointees and borrowed
  slice elements remain mandatory work; this implementation does not close G2
  or declare 1.0 complete.

- Borrow destination provenance foundation: rewrote the return-region module
  from generated control flow into 128 lines of direct Cool, with aligned legacy
  semantics. Separate binding-origin and value regions distinguish possible
  destinations from sources installed into their payloads. Binding edges are
  collected before stores; stored destinations follow every possible alias,
  reborrow and contracted call source without treating stored payloads as aliases.
  Query marks terminate cycles/shared alias DAGs, and source-edge deduplication
  plus parameter-time origin seeding makes propagation idempotent. A private
  instrumented compiler checks 330 independently modeled value/origin channels
  across fifteen seeded/branch/cycle/computed cases and direct replacement;
  destination visit bounds include a depth-32 diamond and repeated propagation.
  Source/IR/host/runtime identities are recorded in `build/borrow-origins-audit.json`
  and `build/borrow-origins-asan-audit.json`. Normal native/legacy and instrumented
  frontends enforce existing receiver-write/conflict and return-contract errors.
  Full regression, native/legacy bootstrap convergence, compiler/runtime ASan/UBSan
  replacement checks and clean external editor/distribution validation pass.
  Evidence: `build/release-audit/borrow-origins-{final-build,final-focused,final-regression,final-sanitize,final-distribution,final-audit}.log`.
  Current IR SHA256:
  `5114b6fcf3649fbb8f563faf22079f04e28c377b9fa44c804f9c41c6f7c93a78`.
  This is a tested provenance component and compiler-maintenance change, not
  acceptance of cross-call borrowed mutation. Destination lifetime contracts,
  caller/receiver loan updates and nested stored provenance remain mandatory;
  all release gates stay open.

- Checked borrowed mutation: specification draft 26 adds repeatable
  `stores(destination,source)` relations to function signatures. Destinations
  require exclusive references to borrowed storage; source names/types and body
  effects are checked. Unused templates check non-dependent parameter types;
  dependent constraints remain specialization checks. Local frame roots cannot
  escape into caller storage. Forwarded/recursive setters, multiple destinations,
  computed receiver unions, slices, references, enums, generic aggregates and
  borrowed owning handles retain installed source roots at every original caller
  marker. Live receiver payload loans gain the new roots without granting shared
  sources exclusive permission. Return-contract checking includes call effects.
  REPL body replacement compares the effect matrix independent of clause order;
  compilation failures discard staged roots and runtime failures retain candidate
  roots, including partial setters with a live receiver.

  Parameter checking separates physical binding storage from borrowed payload
  roots using compiler-only synthetic Locals, retained under existing function
  cleanup ownership. This avoids self-store conflicts while preserving frame
  address escape rejection. Retained capability edges merge identically rather
  than growing with repeated calls. Private copied-IR allocation histories for
  64/1,024 identical setter calls and compatible setter redefinitions have equal
  final allocation bytes/counts and equal peak bytes. The report records emitted
  artifact identities in `build/repl-stores-lifecycle-audit.json`; it measures
  compiler-owned allocation calls, not process RSS or host-internal memory.

  A first sanitizer run found a function-table underflow on builtin `assert`
  calls: these use negative IDs. Both borrow-region and loan effect dispatch now
  reject negative IDs before table access. Final full regression and exact
  three-generation bootstrap convergence pass. The stores suite passes on native,
  legacy and ASan compilers across five engines/O2, with generated LLVM load/store
  ASan and runtime ASan/UBSan instrumentation, 26 rejection cases and 28 independent
  root/mode queries per frontend. Related nested/reference/slice/loan-layer suites
  now test short-lived installations in place of obsolete blanket-rejection cases.
  Clean external editor/distribution installation also passes.
  Evidence: `build/release-audit/stores-final-{build,focused,regression,sanitize,distribution,lifecycle}.log`.
  Emitted compiler IR SHA-256:
  `b3a703f2dc02229e0e94b083cbe2705a9308bd2cb379511537949f533b0efba5`.
  Cross-call replacement is now supported within the current two-layer model.
  Arbitrary nested stored borrowed pointees, borrowed slice elements, whole-language
  conformance and other mandatory checkpoints remain unfinished. All release
  gates remain Open; this is not a 1.0 declaration.

- Multi-parent scoped ancestry: a holder/root can have several parents after
  unioned call results. `ReferenceAncestor` now follows all matching parents
  rather than one `ReferenceHolder` record. An intrusive query-local queue visits
  each Local once, terminates on cycles and clears all visited flags/links on
  every return, without allocations or persistent query state. Legacy and
  production implementations remain aligned. The current scan-based adjacency
  lookup is bounded by V node visits and V*E loan inspections per query; this is
  not a claim about total compilation complexity.

  A private production-source LLVM audit compares 52 root-filtered graph/order
  variants and 57,716 queries with an independent Python reachability oracle.
  Null endpoints/parents/roots, cycles, second-parent-only reachability, shared
  diamonds through depth 128, reversed edges and repeated queries on the same
  objects pass. Every query checks that its visited flags and queue links were
  cleared. Native and sanitizer reports record source/IR/platform identities in
  `build/reference-ancestry{,-asan}-audit.json`; sanitizer mode verifies generated
  LLVM load/store instrumentation and builds host/runtime with ASan/UBSan.
  Full regression, exact three-generation bootstrap convergence, REPL allocation
  histories and clean external editor/distribution use pass. Source-level
  diamonds and live exclusive ancestor/sibling conflicts were also probed on
  native/legacy compilers; no unsafe acceptance was reproduced in those probes.
  Permanent source regressions now execute shared diamonds, mutual replacement,
  common exclusive ancestors and scope release on five engines/O2 for both
  frontends and the ASan compiler; four live-loan conflicts and REPL dependency
  release cases pass. Repeated shared ancestry diamonds also have equal final
  allocation counts/bytes and peak bytes at 64/1,024 submissions.
  Evidence: `build/release-audit/ancestry-{build,focused,adjacent,regression,sanitize,distribution,lifecycle,final-native,final-focused,final-lifecycle}.log`.
  Emitted compiler IR SHA-256:
  `5bb1047591ebbb649a7d9b795a76d5950bf04d6e3df3e0d00bfb58b9a4327942`.

  This is a graph prerequisite for nested borrowed storage, not acceptance of
  that feature. [The nested provenance design](borrow-provenance-design.md)
  specifies typed field/element/referent/owned-payload cursors, per-root capability
  preservation, contract substitution, recursive graphs and transaction ownership.
  Stored borrowed pointees and borrowed slice elements remain mandatory; all
  release gates remain Open.

- Typed AST projections and parser maintenance: field addresses, struct
  initializer children, enum constructors and match guards/payloads retain
  resolved declaration identities in `Node.field_key`. Equal byte offsets no
  longer make those identities ambiguous to future provenance analysis. Typed
  field/element/referent/owned-payload helpers expose existing AST edges. Two
  existing reference guards now walk those edges iteratively while preserving
  their permission rules and raw pointer boundaries. `Primary` and `EnumLiteral`
  move from generated parser control flow into readable ordinary Cool. Legacy
  producers remain aligned. No borrowed-storage restriction is removed.

  Private production LLVM checks 49 records against actual declaration
  membership, concrete generic layouts, source/result types, tags and offsets.
  Zero-sized fields and enum variants with equal offsets retain different keys.
  Compatible REPL function replacement and failed lazy-layout construction
  followed by valid projection access pass under ASan. Focused native/legacy
  and sanitizer execution passes on five engines and O2. Full regression and
  exact three-generation bootstrap convergence, clean external editor/distribution
  installation and 64/1,024-submission compiler allocation histories pass.
  Reports: `build/place-projections{,-asan}-audit.json` and
  `build/repl-projections-lifecycle-audit.json`. Evidence:
  `build/release-audit/projections-{focused,adjacent,final-build,final-regression,final-sanitize,final-distribution,final-lifecycle}.log`.
  Emitted compiler IR SHA-256:
  `368ef3ca0691c1ecba3f33cf8549e9938d12cf172f1605bf2e07a43a24f6f0b2`.

  This preserves inputs for a typed provenance graph. Persistent cursor
  ownership, arbitrary nested stored borrowed pointees and borrowed slice
  elements remain required implementation work. All release gates remain Open.

- Typed payload graph query foundation: `compiler/38-provenance-graph.cool`
  implements arena-owned nodes/edges, declaration/type-aware fields, conservative
  element unions, referent/owned-payload edges and actual root capability
  selection. Edge barriers intersect permissions; shared/exclusive versions of
  one edge remain distinct. Insertion rejects invalid kinds, null sources and
  cross-arena targets. Substitution must copy nodes into the destination arena
  and check insertion results. Destruction follows owned allocation lists, so
  cycles/shared targets do not cause recursive or duplicate freeing.

  An independent Python product-graph model agrees with private production LLVM
  on 34 graph/order variants and 201,624 queries. Coverage includes declaration
  keys, wrong concrete source types, element unions, mixed permissions, nulls,
  graph/cursor cycles, duplicate edges and depth-64 shared paths. Query allocation
  balance returns to its starting value after every positive/negative result;
  graph destruction returns arena balance to zero and repeated destruction is
  safe. Production and legacy frontends agree; compiler/generated LLVM ASan
  plus host/runtime ASan/UBSan pass. Full regression, exact three-generation
  bootstrap convergence and clean external editor/distribution installation pass. Reports record source/platform/object/private-IR identities in
  `build/provenance-graph{,-legacy,-asan}-audit.json`. Evidence:
  `build/release-audit/provenance-graph-{final-build,final-focused,final-regression,final-sanitize,distribution}.log`.
  Emitted compiler IR SHA-256:
  `e86adf52b410e0d31abf5cb65115e7f20d6c61aa52618fc6d748915e520daf23`.
  Maximum measured state visits are
  129 and state-list membership comparisons 16,698; the initial linear-list
  deduplication can be quadratic and this is not a compiler speed claim.

  This is payload selection, not physical ancestor overlap. The graph is not
  yet installed in `ReferenceLoan`; descriptor pinning, transaction ownership,
  contract substitution, live stored-receiver updates and arbitrary nested
  borrowed-storage acceptance remain mandatory. All release gates remain Open.

- Provenance arena copy and rollback: `ProvenanceGraphCopyRoots` copies a
  complete root batch through one source-node identity map. Shared nodes, cycles
  and duplicate/null roots survive cross-arena and same-arena copying. Copies
  own every new node/edge and borrow Local/type/declaration identities. Failed
  insertion frees scratch mappings and newly allocated destination nodes/edges,
  restores the previous arena head and clears outputs. Invalid counts or null/
  overlapping buffers are rejected before mutation. The single-root wrapper
  diagnoses failure only after cleanup.

  The independent graph audit performs two joint copies, destroys the original
  arena and compares 201,624 payload queries across 34 graph/order variants per
  frontend. Exact copied node/edge counts verify preservation of sharing; checks
  include duplicate/null roots, partial buffer overlap, malformed edge insertion
  rollback and allocation balance after every query/destruction. Production,
  legacy and sanitizer frontends pass, with generated LLVM ASan loads/stores and
  host/runtime ASan/UBSan. Full regression, self-hosted IR/native convergence and
  external editor/distribution installation pass. Reports:
  `build/provenance-copy{,-legacy,-asan}-audit.json`. Evidence:
  `build/release-audit/provenance-copy-{final-build,final-focused,regression,final-sanitize,selfhost,final-distribution}.log`.
  Emitted compiler IR SHA-256:
  `c97110dff7e6ff30e9ac8049ff5c7c2f4ce97f417b565ac71634943fb099b6c1`.

  This provides arena transfer required for REPL staging; it has not yet
  replaced the existing shallow loan transaction or connected field graphs to
  scoped loans. Descriptor pinning, physical protection, contract substitution
  and arbitrary nested borrowed-storage acceptance remain required. Source-map
  lookup is currently linear and no whole-compiler speed claim is made. All
  release gates remain Open.

- Production loan graph ownership: `ReferenceLoan.provenance` now points into
  a check-owned arena. Struct/enum initializer declarations, conservative
  elements and owned payloads retain typed edges. Known same-type copies and
  whole-binding assignment preserve/union value graphs; opaque calls do not
  infer field identity from equal types. Reused terminals and single-edge nodes
  avoid duplicate equivalent subtree history. `ReferenceLoanQuery` intersects
  the loan entry mode with graph permissions. Joining a shared opaque root with
  a structural parent uses the actual root permission, not the parent's neutral
  mode; private probes also verify shared loans cannot regain stronger source
  graph permissions.

  REPL candidate loans jointly clone into independent arenas. Commit compacts
  reachable live roots before freeing old arenas; rejection discards candidates,
  runtime failure retains potentially executed effects, `:forget` compacts and
  session cleanup frees persistent graphs. Graph root Locals participate in
  reclamation. Function checks use a heap registry so failed reference analysis
  releases both loans and graphs before function metadata rollback.

  Private production-source LLVM checks 30 actual field/root/mode records across
  initialization, copy, whole assignment, same-root fields and mixed shared/
  exclusive fields. Compiler/generated private LLVM ASan and host/runtime
  ASan/UBSan, five engines/O2 and partial-runtime/failed-function REPL recovery
  pass. Repeated retained field assignments and rejected function loan analysis
  have equal final allocation bytes/counts and equal peak bytes at 64/1,024
  submissions. Full regression, exact self-hosted IR/native convergence and
  external editor/distribution installation pass. Reports:
  `build/loan-provenance{,-asan}-audit.json`, `build/repl-lifecycle-audit.json`.
  Evidence: `build/release-audit/loan-provenance-{final-build,final-focused,final-regression,final-sanitize,final-lifecycle,distribution}.log`.
  Emitted compiler IR SHA-256:
  `4e3ca4bdbaa71fc78dfa56763c453ce0c7ea30b240c71639584d770b4d8cf92e`.

  Metadata/lifetime checks concern the production compiler; the legacy seed
  checker keeps its old internal records and unchanged permission behavior.
  Existing two-layer checks remain authoritative on both frontends. Field load
  selection, physical protection, opaque call/partial-store substitution,
  parameter summaries and descriptor-lifetime audit must be completed before
  arbitrary nested borrowed storage is accepted. All release gates remain Open.

- Typed loan value selection: production loans now distinguish a precise absent
  root from unknown provenance and record the graph's declared value type.
  Address cursors select nominal fields, conservative element unions, referents
  and owned payloads. A named `&Pair` keeps physical storage protection separate
  from its referent's field graph. Computed aggregate LOADs use their stripped
  address as the origin boundary, avoiding duplicate payload traversal. Unknown
  raw/computed boundaries and opaque call results retain explicit opaque roots;
  coarsening intersects actual source capabilities. Unknown/null and mismatched
  typed alternatives cannot disappear during graph union. Shared selection
  barriers apply to outgoing edges and terminal roots. Shallow node interning
  bounds repeated identical selected-value assignment history. Arena copying
  preserves the opaque flag.

  Private actual binding/copy checks verify 34 field/root/mode records and 14
  value-selection records: named references, nested structs, array element
  unions, named and computed owners, precise absent roots and opaque swapped
  call results. Five engines/O2 and REPL failure recovery pass. An independent
  Python finite-state oracle verifies 1,620 typed selection/query combinations,
  including cyclic graphs/cursors, shared barriers, absent/unknown roots and
  mismatched types. Helper probes cover unknown/precise union in both orders,
  precise absence, mismatch and repeated identical union. Compiler-generated
  private LLVM ASan and host/runtime ASan/UBSan pass. Selected nested-value REPL
  replacement at 64/1,024 submissions has equal final bytes/counts (32,154,836/60)
  and equal peak bytes (32,167,949). Full regression, production and legacy seed
  convergence, and external editor/distribution installation pass. Reports:
  `build/provenance-selection{,-asan}-audit.json`,
  `build/loan-provenance{,-asan}-audit.json`, `build/repl-lifecycle-audit.json`.
  Evidence: `build/release-audit/provenance-selection-{build,focused,regression,sanitize,lifecycle,distribution}.log`.
  Emitted compiler IR SHA-256:
  `bf45d3723467d583c1d815b0beb8282c3d9942981a52d86fe58e27de9806fc06`.

  This certifies metadata selection, not authorization of additional language
  programs. Existing coarse roots, ancestry and two-layer permission decisions
  remain authoritative on both frontends. Computed reborrow retagging, partial
  stores, call substitution, descriptor lifetimes and physical overlap must be
  integrated and checked before arbitrary nested borrowed storage is accepted.
  All release gates remain Open.

- Typed installed-value metadata: direct partial stores wrap the incoming
  value graph in the destination's field/element/owned-payload cursor, producing
  the original holder's declared value type. Retention joins this graph with
  existing historical provenance instead of leaving only the old initializer
  graph or a mismatched field-value type. Live physical receivers gain a
  separate Referent payload wrapper; layer-zero protection is unchanged.
  Literal `stores` call addresses preserve the destination slot, with an opaque
  value graph at that slot because contracts do not describe callee field
  mappings. Named/computed receivers with unproven mappings use opaque holder
  anchors. Precise absent source roots stay absent through unknown mappings;
  unknown/null receiver sources become explicit opaque nodes before wrapping.
  Shared entry and terminal permissions are retained.

  Private production-source LLVM checks 18 post-store root/selection/known
  records across direct and nested fields, conservative array elements, owned
  payloads, live named receivers and opaque function stores. Existing historical
  siblings remain present and new roots occur only at proven direct-store paths.
  Helper probes cover nested cursor direction, sibling exclusion, all shared/
  exclusive entry and terminal combinations, precise absence, unknown fallback,
  repeated wrapper interning and unknown/absent receiver wrapping. All five
  engines/O2, compiler/private LLVM ASan, host/runtime ASan/UBSan and the full
  stores contract suite pass. Repeated partial stores at 64/1,024 submissions
  retain identical final bytes/counts (32,154,831/48) and peak bytes (32,168,528);
  repeated opaque named-receiver stores retain identical final bytes/counts
  (32,160,920/110) and peak bytes (32,174,539). Full regression, production and
  seed convergence, and external editor/distribution installation pass.
  Reports: `build/loan-provenance{,-asan}-audit.json`,
  `build/provenance-selection{,-asan}-audit.json`, `build/repl-lifecycle-audit.json`.
  Evidence: `build/release-audit/provenance-stores-{build,focused,regression,sanitize,contract-sanitize,lifecycle,distribution}.log`.
  Emitted compiler IR SHA-256:
  `86c4ded8446266adc07443232c5425fac8fe36cbb11873d3c8c5a6a9dd14e3ae`.

  Metadata installation is now connected to actual storage operations, but
  existing coarse roots/ancestry remain the authoritative permission checker
  on both frontends. Precise physical destination summaries, computed reborrow
  adaptation, graph-aware authorization, parameter/call substitution and
  descriptor lifetimes remain required before arbitrary nested borrowed
  storage is accepted. All release gates remain Open.

- Declared parameter type summaries and computed reborrow adaptation: parameter
  loans no longer infer a value type from anonymous payload Locals whose type
  is zero. By-value borrowed parameters use their declared aggregate shape;
  nested-reference parameters retain separate physical anchor loans and
  Referent payload summaries. Field/element/owned-payload edges enumerate all
  possible external origins represented by an abstract parameter root. Type
  memoization preserves recursive owned-layout cycles; borrow-free fields have
  no origin. Reference terminal/edge permissions use reference mutability;
  slice permissions use `ReferenceMode`, because slice count is not a permission
  field. Shared receivers intersect all internal mutable capabilities. These
  summaries describe possible structure, not observed argument/return field
  mappings. Unsupported future borrowed kinds stay opaque, and their borrow
  classification must be added with the kind. Summary scratch is freed after
  construction; insertion errors are internal invariant failures after types
  have passed parameter layout/borrow classification.

  Computed reborrow loans now adapt their graph before expression retagging.
  Scalar physical anchors remain conservative while known absent payload roots
  stay absent; borrowing a stored reference wraps the selected Referent payload
  without merging the physical and payload layers.

  Private production-source checks verify 22 parameter path/mode records across
  mixed shared/exclusive fields, a borrow-free sibling, shared and exclusive
  receivers, array/owner/slice wrappers, concrete generics and a recursive enum
  with the borrowed terminal following three owned links. Joint graph clones
  preserve these query results and cycles. Eight actual computed-reborrow
  records verify physical anchors, selected/absent payload roots, nested
  reference extraction and scalar projections. Existing 34 field/root/mode,
  14 selection and 18 store records, five engines/O2 and REPL recovery pass.
  Generated private LLVM ASan and host/runtime ASan/UBSan pass, including the
  full stores contract suite. Repeated typed/recursive parameter function
  replacement at 64/1,024 submissions retains equal final bytes/counts
  (32,156,971/161) and peak bytes (32,165,734); repeated computed reborrow
  assignment retains equal final bytes/counts (32,154,689/46) and peak bytes
  (32,166,586). Full regression, production and seed convergence, and external
  editor/distribution installation pass. Reports:
  `build/loan-provenance{,-asan}-audit.json`, `build/repl-lifecycle-audit.json`.
  Evidence: `build/release-audit/provenance-parameters-{build,focused,regression,sanitize,contract-sanitize,lifecycle,distribution}.log`.
  Emitted compiler IR SHA-256:
  `0f936bfece0c5e008f7b7eae18f466c31c839941622b2b3930d24c3d77c925c9`.

  Region/PlaceRegion, return/store contracts, caller-owned versus callee-owned
  storage and existing coarse scoped permissions remain authoritative on both
  frontends. Typed caller/callee graph substitution, physical protection,
  graph-aware authorization and descriptor-lifetime audit are still required
  before arbitrary nested borrowed storage is accepted. All release gates
  remain Open.

- Opaque call provenance now constructs declared output-type upper bounds for
  each contracted source root, bounded by that source's actual capability.
  Borrow-free siblings and known absent roots stay absent; nested physical
  anchors remain separate from Referent payloads. Equal input/output types do
  not imply field correspondence. Temporary store destinations use the same
  constructor when composing returns; persistent opaque stores still preserve
  conservative unknown mappings.

  Recursive skeleton and bounded overlay reuse survive graph clone/compaction.
  An auxiliary owned connection preserves canonical skeleton identity after
  observed/possible-origin unions; queries and mode propagation never follow
  that connection. Clone preserves auxiliary sharing/cycles, rejects foreign
  targets and rolls back; Local reclamation marks its summary keys. Private
  shared-bound probes confirm stronger cached skeletons cannot grant writes,
  including after clone and alternate bounds. Four actual mixed-capability
  call records pass alongside existing 34 field, 14 selection, 18 store,
  22 parameter and eight computed reborrow records, five engines/O2 and REPL
  recovery. Graph copy's 201,624 queries and 1,620 selection cases pass with
  generated LLVM ASan and host/runtime ASan/UBSan.

  REPL observed/opaque return, nested reference return and recursive owning
  return histories have equal final tracked bytes/counts at 64/1,024 submissions:
  respectively 32,159,904/107, 32,159,719/89 and 32,165,670/137. Their peak bytes
  are also equal: 32,173,255, 32,174,298 and 32,178,389. Final reports are measured
  after REPL cleanup; peak measurements cover session use. Recursive owning
  values preserve allocation counts and release to zero on forget. Full
  regression, production/seed bootstrap convergence, stores contracts under
  sanitizers and external editor/distribution installation pass.
  Reports: `build/loan-provenance{,-asan}-audit.json`,
  `build/provenance-copy{,-asan}-audit.json`, `build/repl-lifecycle-audit.json`.
  Evidence: `build/release-audit/provenance-calls-{build,focused,regression,sanitize,contract-sanitize,lifecycle,distribution}.log`.
  Emitted compiler IR SHA-256:
  `fef0fa0d77a3f2a7734f003ce1458282f00773bbf036592e5346c1498f7b7836`.
  Authoritative graph substitution/physical protection and arbitrary nested
  borrowed storage remain unfinished; all release gates remain Open.

- Production typed payload overlap now participates in actual conflict checks
  and reborrow acquisition. Exact absent layer-one roots can be excluded;
  layer-zero anchors, direct root protection and raw bridges retain existing
  coarse checks. Overlap ignores capability: a shared path still accesses its
  root. Physical terminal roots overlap remaining child projections, and
  unknown/opaque/mismatched/incomplete paths remain conservative. This enables
  independent access to distinct roots in known nested receiver fields while
  preserving same-root, array union and opaque return conflicts. Write
  authorization and arbitrary nested storage remain unfinished.

  Four explicit programs and 24 deterministic field/root/initializer
  permutations pass on production across five engines/O2, with 31 rejection
  cases and persistent REPL recovery. Private helper checks include cyclic
  cursors/recursive graphs, physical prefixes, shared overlap, absence and
  fallback. Eliminating proven absent payload loans changes audited records
  to 12 selection, 16 store and seven computed records; exact surviving root
  sets are asserted. Existing 34 field, 22 parameter and four call records
  pass. Generated LLVM ASan/host-runtime ASan/UBSan pass. A repeated disjoint
  payload access history has equal final tracked bytes/counts (32,154,838/52)
  and peak bytes (32,168,353) at 64/1,024 submissions. Final reports are after
  REPL cleanup; peaks cover session use. Production self-hosting converges,
  with compiler IR SHA-256:
  `d387dc147076df57a16d30beae9fd46576b35f3a77ae1969aafb0a57c2c55f36`.

  The full regression suite also passes against these frozen compiler/seed
  artifacts (`make -o build/cool-compiler -o build/language.BIN -j4 test`);
  this avoids rebuilding while legacy source integration is in progress.
  Evidence: `build/release-audit/provenance-access-regression-snapshot.log`.
  Final regression/bootstrap checks must be repeated after legacy integration.

  Legacy arena/query/clone foundations compile, but matching access acceptance
  and full legacy metadata/lifecycle integration are still in progress. Current
  production access evidence does not certify legacy parity or finish G2/G9.
  Reports: `build/provenance-access{,-asan}-audit.json`,
  `build/loan-provenance{,-asan}-audit.json`, `build/repl-lifecycle-audit.json`.
  Evidence: `build/release-audit/provenance-access-{build,cases,cases-sanitize,focused,helper-sanitize,sanitize,contracts,ancestry,lifecycle,selfhost,legacy-build}.log`.
  All release gates remain Open.

- Legacy payload-graph integration now matches production construction,
  selection, partial stores, declared parameter/call upper bounds and access
  overlap. HolyC struct-return helpers use explicit output pointers with
  initialized normal/early returns. Graph checks register for failure cleanup;
  persistent candidates jointly clone/compact reachable nodes and pin root and
  summary-key Locals. The missing initializer wrapper `provenance_known=1`
  assignment found in review was corrected before final validation. This
  resolves the legacy parity work left open in the preceding access entry.

  The mandatory access suite now checks both frontends, including persistent
  REPL rejection/recovery/forget, four explicit cases, 24 deterministic
  permutations and 31 rejected accesses; production execution passes five
  engines/O2. A separate mode-independent product-state overlap oracle is
  checked alongside all 1,620 selection cases, including physical prefixes,
  whole-value descendants, opaque/type/incomplete fallback, exact absence and
  cyclic paths/graphs. Generated LLVM ASan and host/runtime ASan/UBSan pass.

  Private copies of the actual seed-compiled legacy frontend track allocations
  originating in `Provenance.cool` (nodes, edges and query/copy scratch), including
  frees in its loan helpers. At 64/1,024 submissions, field access, opaque
  returns, recursive owning returns, failed analysis and stores all end with
  zero tracked bytes/counts and equal peaks: respectively 2,872, 4,016, 3,648,
  88 and 5,128 bytes. Arena allocations, loan records, other compiler metadata
  and JIT mappings are outside this instrumentation scope. Recursive owners
  release to zero on forget. Reports:
  `build/legacy-graph-lifecycle-audit.json`,
  `build/provenance-access{,-asan}-audit.json`,
  `build/provenance-selection{,-asan}-audit.json`.

  Final full regression and production/seed convergence pass after integration,
  as does external editor/distribution installation. Production compiler IR
  remains `d387dc147076df57a16d30beae9fd46576b35f3a77ae1969aafb0a57c2c55f36`.
  Evidence: `build/release-audit/provenance-parity-{build,focused,selection,sanitize,legacy-lifecycle,regression,distribution}.log`.
  This certifies matching payload absence decisions, not graph-based write
  authorization, arbitrary nested stored references, full physical projection
  overlap or descriptor lifetime completion. All release gates remain Open.

- Structured call upper bounds now exclude a shared source root from declared
  mutable-reference/slice physical terminals while retaining their Referent/
  Element children. A shared root may still occur inside a mutable receiver's
  shared payload; pruning the entire subtree would lose lifetime protection.
  A distinct shared-origin recursive skeleton (cache kind 4) survives clone and
  compaction without changing abstract parameter summaries. Opaque physical
  call anchors and conservative lifetime loans remain independently protected.

  Private actual mixed-call records verify shared x cannot supply the mutable
  output field, while exclusive y may occur in either field; no body field
  correspondence is inferred. Nested summary probes verify the shared root is
  absent at the outer mutable terminal but remains in the shared child, with
  writes unavailable. Both frontend access/REPL checks, recursive lifecycle
  histories, 1,620 selection/overlap cases, 201,624 graph-copy queries and
  compiler-generated LLVM ASan/host-runtime ASan/UBSan pass. Full regression,
  production/seed convergence and external editor/distribution checks pass.
  Compiler IR SHA-256:
  `ff6173b27a65f46787faadceb7498b0c19cabb42053047d001b4c6557bdaec0d`.
  Evidence: `build/release-audit/provenance-admissibility-{build,focused,regression,sanitize,distribution}.log`.
  Universal graph write-path authorization and arbitrary nested borrowed storage
  remain required; all release gates stay Open.

- Stored referent writes now reject any known shared payload path, even when
  another possible path is exclusive. Both frontends accumulate modes over
  finite (node,cursor,mode) states and preserve mode barriers. A cursor ending
  at a reference value slot contributes zero; replacing that slot is distinct
  from writing its external referent. Unknown/incomplete paths retain existing
  scoped permission checks, and all scratch is freed before diagnostics.

  Private actual production/seed frontend hooks inject shared and exclusive
  alternatives into one mutable-field loan: the old existential query succeeds,
  but actual referent writes are rejected. This validates rejection of malformed
  metadata; it does not claim ordinary source can create that mapping. The
  independent selection/overlap/write-mode oracle passes 1,624 cases, including
  reversed alternative order. Six legacy graph allocation workloads at
  64/1,024 submissions end at zero tracked allocations with equal peaks; the
  new rejection workload peaks at 2,704 bytes. Instrumentation scope excludes
  graph arenas, loans, other metadata and JIT mappings.

  Full regression, production/seed bootstrap convergence, generated LLVM ASan,
  host/runtime ASan/UBSan and external editor/distribution installation pass.
  Compiler IR SHA-256:
  `175ba5d63912fa3ff02ff08a4559bf0d434ce4ac17ca709e337bb1e7b2589fa3`.
  Evidence: `build/release-audit/provenance-write-final-{build,focused,regression,sanitize,distribution}.log`.
  This additional rejection check covers named layer-one stored-referent loans;
  complete physical projection and copy/move authority, arbitrary nested borrowed
  storage and remaining release gates still require implementation. All gates
  remain Open.

- Named borrowed-value copies/moves now reject any known shared path to an
  exclusive handle before graph selection can coarsen its capability. The finite
  authority query follows aggregate value edges after the place cursor ends,
  but stops at reference/slice handles. Shared handles require no exclusive copy
  authority; mutable handles use their declared mode, including slices. Their
  internal payloads keep lifetime protection and are not mistaken for copied
  handles. Both physical/payload loan layers participate for named receivers.

  Independent selection/overlap/write/copy-mode oracles pass 1,630 cases using
  actual private reference/slice descriptors, with shared/exclusive alternatives,
  cycles, missing paths and handle boundaries. Actual private production and seed
  hooks reject both a field copy and a whole aggregate copy when their metadata
  contains shared and exclusive alternatives. Seven legacy 64/1,024-submission
  histories end at zero tracked graph allocations and stable peaks; alternating
  copy rejection/recovery peaks at 2,704 bytes. These private graph allocations
  retain the instrumentation exclusions documented above.

  Full regression, production/seed bootstrap convergence, generated LLVM ASan,
  host/runtime ASan/UBSan and external editor/distribution installation pass.
  Compiler IR SHA-256:
  `6ff8e3a108fcec25424e4002ccd83340bcd277c3e64b4c47c53d9c1bdd2078d7`.
  Evidence: `build/release-audit/provenance-copy-authority-{build,focused,selection,regression,sanitize,distribution}.log`.
  Computed receivers, opaque permission fallback, complete physical projection
  protection and arbitrary nested borrowed storage remain required. This is
  additional rejection coverage, not full universal authorization or completion
  of any release gate. All gates remain Open.

- Computed receiver acquisition, borrowed-value projection and final writes now
  apply the universal shared-alternative rejection query before origin retagging
  or mode coarsening. Named projection paths redirect to original holder graphs.
  Unnamed LOAD projections query the highest still-live temporary source with
  the complete original place cursor. This avoids treating destination read-pin
  mode zero as an original shared capability while retaining intermediate shared
  barriers and all root alternatives. Explicit borrow constructors are not
  crossed. Unknown/incomplete/opaque origins keep existing scoped fallback.

  Actual private production/seed hooks inject mixed alternatives into a returned
  receiver payload; field/whole copies, writes and exclusive reborrows reject at
  the first failing operation. Nine legacy 64/1,024-submission workloads end at
  zero tracked graph allocations with equal peaks; computed writes/copies peak
  at 2,976/2,320 bytes respectively, under the existing instrumentation exclusions.
  Five ordinary source cases for read pins, field/whole copies, consecutive calls
  and stores followed by returned receiver use pass five engines/O2 and both
  frontends. Two shared receiver cases reject mutable field extraction/reborrow.

  Full regression, production/seed bootstrap convergence, 1,630 independent
  graph authority oracle cases, generated LLVM ASan, host/runtime ASan/UBSan and
  external editor/distribution installation pass. Compiler IR SHA-256:
  `1b159b7dfd109a77350ba316365351f3934497d8af65c1b66059865743845c9c`.
  Evidence: `build/release-audit/provenance-computed-authority-{build,focused,access,regression,sanitize,distribution}.log`.
  Full physical projection protection (including deeper authority after physical
  terminal prefixes), opaque permissions, descriptor lifetime and arbitrary
  nested stored borrowing remain required. All release gates remain Open.

- Universal write/copy mode queries no longer stop after recording a physical
  terminal prefix. They continue matching edges so an exclusive prefix cannot
  hide a deeper shared contribution from the same root. Node capability remains
  terminal-specific; child paths use edge barriers. Slot-write and handle-copy
  end boundaries remain unchanged, and existential overlap still stops when a
  physical prefix has proved overlap. Exclusive-plus-unknown remains fallback,
  not a universal authorization result. Both frontends mirror this behavior.

  Independent authority/selection/overlap oracles pass 1,642 cases, including
  prefix/descendant permission combinations, opaque children and a traversed
  graph/cursor cycle. Actual private production/seed metadata hooks place an
  exclusive physical prefix ahead of mixed payload alternatives and require
  named/computed writes and field/whole copies to reject. These injected states
  validate query/checker behavior, not ordinary-source construction of that
  mapping. Four added persistent rejection/recovery histories exercise candidate
  graph cloning: 64/1,024 repetitions end at zero tracked graph allocations with
  stable peaks of 2,792 bytes for named write/copy, 3,232 for computed write and
  2,320 for computed copy. All 13 legacy workloads pass under the previously
  documented instrumentation exclusions.

  Full regression, production/seed bootstrap convergence, generated LLVM ASan,
  host/runtime ASan/UBSan and external editor/distribution installation pass.
  Compiler IR SHA-256:
  `f4025b550cd8861959fbc1a0085b2fb7f76e84f39d825501f2949ed98a293e6b`.
  Evidence: `build/release-audit/provenance-prefix-authority-{build,focused,injection,selection,regression,sanitize,distribution}.log`.
  Physical address/projection alias protection, opaque permissions, descriptor
  lifetime and arbitrary nested borrowed storage still require completion. No
  release gate is closed by this additional rejection check; all remain Open.

- Physical address geometry is now separate from typed value provenance.
  Stable direct struct field addresses carry root-relative paths. Loan copies,
  unions and persistent candidate cloning preserve both arena roots. Unknown
  geometry dominates union; raw bridges and opaque call returns drop precision.
  Physical overlap uses visited node pairs, prefix protection, enum payload
  overlap and conservative array element unions. It only refines pre-existing
  root conflicts. Named references can access disjoint field regions; indirect
  projections use whole source regions and stored handles remain conservative.

  Actual fixtures pass 9 accepted and 16 rejected programs, five engines/O2 and
  persistent REPL recovery/forget on production and seed frontends. Cases cover
  field copies and call arguments, nested structs, whole-place conflicts, merged
  address sets, raw bridges, enum replacement, array unions and owner movement.
  Owned payload sibling access remains rejected; arbitrary nested borrowed
  storage and descriptor lifetime remain pending. The 1,642-case independent
  selection/authority suite also checks physical pair overlap. All 13 legacy
  graph lifecycle workloads end at zero tracked graph allocations with identical
  64/1,024 repetition peaks, under documented instrumentation exclusions.

  Full regression/bootstrap convergence, four existing provenance sanitizer
  targets plus physical-address sanitizer and external editor/distribution
  installation pass. Compiler IR SHA-256:
  `87fdb6ce125db886a2940ec634b9233620201e4e38f32dfdb8240e63f1529b8c`.
  Evidence: `build/release-audit/physical-address-{build,focused,regression,sanitize,distribution,extra-fixtures}.log`.
  All release gates remain Open.

- Direct owner payload field precision now distinguishes descriptor observation
  while forming an address from an ordinary whole value read. Only known
  physical geometry, matching direct root, complete cursor and owner endpoint
  qualify. Terminal/ancestor roots, opaque/type mismatch and unknown geometry
  remain conflicts; only endpoint OwnedPayload edges are excluded. Pending
  address pins keep their previous whole owner and source/lifetime protection.
  Moves, replacement and ordinary access use the existing whole-place query.
  Both frontend implementations mirror this behavior.

  Actual physical fixtures pass 14 accepted and 23 rejected programs across
  five engines/O2 and both frontends, including nested owned fields, simultaneous
  owned payload field borrows, same-field/owner-slot/whole-payload conflicts,
  RHS owner movement/replacement and containing aggregate replacement. Persistent
  REPL cases preserve loans across analysis rejection, partial runtime writes,
  graph cloning and forget/release. Aliased owners and external payload
  acquisition may still reject valid source; these cases remain pending.

  Independent selection/address/owner-slot/authority oracles pass 1,648 cases,
  including endpoint payload exclusions, opaque payload descendants,
  terminal/opaque/non-payload fallback and cyclic node/cursor termination.
  Two new seed lifecycle histories end at zero tracked graph allocations with
  equal 64/1,024 repetition peaks: 2,208 bytes for owned field pairs and 1,392
  for owner descriptor rejection/runtime recovery. All 15 legacy graph histories
  pass under documented instrumentation exclusions.

  Full regression and bootstrap convergence, four existing provenance sanitizer
  targets plus physical-address sanitizer, independent oracle sanitizer and
  external editor/distribution installation pass. Compiler IR SHA-256:
  `93ed7f30f65bd6d67b4b31ebcffdc0cc7b1db6ac9ba6d08472a55633bd9c7b81`.
  Evidence: `build/release-audit/owner-descriptor-{build,focused,fixtures,regression,sanitize,distribution,oracle,lifecycle}.log`.
  Arbitrary nested borrowed storage, descriptor lifetime and indirect address
  mapping remain required work. All release gates remain Open.

- Known named-reference physical addresses now compose stable typed place
  suffixes with every possible original address endpoint. Projection validates
  the whole reachable source set, independently clones it and substitutes all
  terminals; any opaque/root/type/unsupported suffix alternative falls back.
  New suffix terminals are fresh, original holder graphs remain unchanged and
  the fixed clone range prevents recursive resubstitution. Query candidates use
  freed scratch arenas; acquisition checks and resulting loans share one proof.
  Named reference handle observation checks descriptor storage separately from
  actual referent access. Ordinary reference copies still protect whole regions.

  Actual fixtures pass 22 accepted and 32 rejected programs on both frontends,
  five engines/O2 and persistent REPL recovery/forget. Cases include nested
  fields, same-root unioned receiver targets, disjoint call arguments and array
  field unions, descriptor aliases, shared receiver writes, whole reference/value
  copies and same-field conflicts. Added private metadata probes verify both
  union targets, source immutability, same-arena and equal source/target types,
  recursive source edges, identity and all-or-unknown/cyclic suffix fallback.
  The independent 1,648-case query suite still passes under sanitizers.

  Two new seed lifecycle histories end at zero tracked graph allocations with
  equal 64/1,024 repetition peaks: 1,992 bytes for repeated named field loans and
  1,560 for named physical analysis/runtime recovery. All 17 graph histories
  pass under the documented instrumentation exclusions. Full regression and
  bootstrap convergence, four existing provenance sanitizer targets, corrected
  physical-address sanitizer fixtures and external editor/distribution pass.
  An initial shared-write fixture expected a later borrow error, but the parser
  correctly rejected immutable assignment first; its exact diagnostic assertion
  was corrected and the full suite and physical sanitizer were rerun.

  Compiler IR SHA-256:
  `9a2375460d283adcc5b10249ca692406ae783f694d9e8b5db7fd6ceedf00a62f`.
  Evidence: `build/release-audit/reference-physical-project-{build,focused,fixtures,invariants,regression,sanitize,sanitize-fixtures,distribution}.log`.
  Parameter/aliased owner descriptor geometry, stored referents, borrowed slice
  elements, descriptor lifetime and arbitrary nested storage remain required.
  All release gates remain Open.

- REPL persistent ancestry now prunes dead leaves after candidate filtering and
  compact graph transfer on both successful commits and partially executed
  runtime failures. The caller's explicit visible list is authoritative. A Local
  remains protected whenever it is a visible binding, loan root/holder or graph
  root/summary root. Pruning neither changes its type nor invents a root ancestor;
  later existing reclamation frees unused Locals after cleanup/rollback.
  This fixes a concrete audit finding: failed generic assignments left an
  ancestry-only Local carrying a newly instantiated, subsequently rolled-back
  type ID. The old ancestor traversal did not read that type, so this was residual
  metadata rather than an observed invalid dereference.
  Persistent loans merge only with identical root/holder/parent/mode/layer/value
  type keys, excluding root-null markers and holder-null temporary records.
  Value and physical graphs join together, preserving all alternatives and
  unknown conservatism; a joint copy compacts the resulting graph.
  A new private-copy audit instruments Field frees and new type clears in both
  actual frontends, inspecting all live compact arena nodes/edges, node roots/
  summary roots and loan result/root/holder/parent types. Negative controls prove
  detection and role probes preserve all live metadata. Six histories
  per frontend pass normally; production LLVM/host/runtime additionally pass
  ASan/UBSan (seed parity remains unsanitized), including generic return/copy,
  physical field recovery, failed recursive layout and reuse of rolled-back type
  IDs with a different generic layout. Direct encoded IDs are checked; recursive
  descriptor dependency coverage is still incomplete.
  Both lifecycle suites add successful/failed generic-parent histories at 64
  and 1,024 submissions. Production final allocations stay at 32,154,387/45
  (success) and 32,154,291/43 (runtime failure); tracked peaks stay 32,165,100 and
  32,167,100 respectively. Both roots remain protected before forget, then their
  mutation succeeds. Legacy tracked graph allocations end at zero and peaks
  stay 1,280 bytes for both histories. Legacy excludes loans/Local metadata,
  whereas production instruments compiler allocation call sites; neither
  includes host-internal allocations, JIT mappings or production RSS.
  Full `make -j4 test bootstrap-check`, independent production lifecycle,
  provenance graph/copy/loan/selection and physical address sanitizer targets,
  descriptor rollback ASan/UBSan and external editor distribution validation
  pass. Generated compiler IR SHA-256 is
  `6a35a6f6c73e82911846faddf4a5306490b6671399557c76d42803a62470e509`.
  Evidence: `build/release-audit/descriptor-prune-{build,focused,lifecycle,regression,sanitize,distribution,reuse}.log`.
  Remaining recursive descriptor dependencies, parameter/aliased owner geometry,
  stored referents and borrowed slice elements are required work. All release
  gates remain Open.

- Descriptor rollback coverage now includes finite recursive dependency closure
  before any journal mutation, not only direct type IDs. The private audit follows
  normalized pointer bases, element types, nominal field types, origins and
  generic arguments through effective saved descriptors. It rejects reachable
  IDs scheduled for clear, retained graph Field keys scheduled for free (including
  intermediate journal snapshots), and graph-semantic header changes. Scratch
  lazy-layout state/size/alignment and unretained Field lists may be restored.
  Eleven synthetic controls on each actual frontend cover transitive failures,
  cycles, an exactly 4,096-type closure, reference-mode changes, repeated target
  snapshots and harmless scratch restoration. Ten actual source histories per
  frontend pass, adding recursive owners, generic owner/raw-pointer arguments
  and scalar-slice stores with runtime failure to the prior six histories.
  Normal `descriptor-rollback-test` and `descriptor-rollback-sanitize-test` pass.
  Sanitizers instrument production generated LLVM/host/runtime; seed execution
  is an unsanitized parity control. Earlier wording implying sanitized seed
  execution is corrected. These changes add validation only; compiler semantics
  and emitted stage-2 IR are unchanged from the preceding verified commit:
  `6a35a6f6c73e82911846faddf4a5306490b6671399557c76d42803a62470e509`.
  Evidence: `build/release-audit/descriptor-dependencies-{focused,sanitize}.log`
  and regenerated `build/descriptor-rollback{,-asan}-audit.json` with source and
  helper hashes. This validates the modeled descriptor dependencies in these
  histories, not all arbitrary nested storage or runtime/JIT lifetimes.
  Before lifting nested storage guards, remaining implementation must preserve
  external payload roots across arbitrary reference depth, connect borrowed
  slice-element provenance separately from backing storage, and update stored
  receiver aliases at arbitrary depth. All release gates remain Open.

- Private nested-reference design probes now provide concrete counterexamples
  before guards are removed. Twelve source fixtures are compiled using copied
  actual compiler sources and object artifacts. With only ReferenceStorage
  bypassed, and with typed layer-routing added, returning an external scalar
  reference through function-local Inner/Outer storage is overrejected in both
  copy and address forms. The coarse Region return gate combines the local
  descriptor's FRAME provenance with the external reference. Direct-holder
  routing alone also misses the computed stored-LOAD acquisition branch.
  A further private root-based return-validator hypothesis remains unsound:
  `fn bad(p:&i64)->& &i64 borrows(p){return &p;}` is accepted even though it returns
  the callee's parameter descriptor slot. The real frontend and Region-retaining
  private control correctly reject it. The unsafe accepted fixture is never run.
  Seven other negative probes remain rejected; two original positive probes
  execute successfully. These tree-mode experiments are not cross-engine safety
  evidence and intentionally do not pass readiness. The script's explicit
  `--assert-expectations` checks classification and diagnostics and rejects the
  three remaining gaps after saving the report.
  No production guards or compiler semantics were changed by these experiments;
  stage-2 IR remains
  `6a35a6f6c73e82911846faddf4a5306490b6671399557c76d42803a62470e509`.
  Evidence: `build/release-audit/nested-reference-{expanded-baseline,routing-expanded,graph-return-probe,root-lifetime-control,readiness-failed}.json`
  and `nested-reference-{root-lifetime-control,readiness-failed}.log`.
  The next root representation must distinguish parameter slot lifetime from
  caller referent lifetime, propagate that distinction through summaries and
  stored aliases, and select external payloads through computed origins before
  replacing Region checks. All release gates remain Open.

- Explicit caller-root identity: both frontends now distinguish callee
  parameter descriptor slots from synthetic caller storage. Reference returns
  validate actual loan roots against the borrows contract; other borrowed result
  forms retain their Region check. Typed nested paths and computed stored loads
  select payload lifetimes, while all existing nested-storage restrictions stay
  active. Public regressions cover reference-parameter descriptor slots,
  by-value aggregate reference slots and by-value owner scalar payloads.
  Caller-root store markers preserve checked replacement; the full regression
  first exposed a self-store ancestry cycle, fixed by retaining the original
  receiver's payload ancestry.
  The private readiness target checks 12 cases on each frontend with only
  ReferenceStorage bypassed. A separate failed type-predicate countermodel still
  accepts parameter-slot escape in both frontends; accepted negatives are never
  executed. This readiness evidence does not certify arbitrary nested stores.
  Validation: `make -j4 test bootstrap-check editor-distribution-test` PASS;
  bootstrap/stage2/stage3 IR and native binaries are identical. References now
  exercise 47 public rejections; stores retain 26 contract/lifetime negatives.
  Graph, copy, loan, selection, physical-address and descriptor-rollback sanitizer
  targets PASS; stores also pass with the sanitized third frontend and runtime.
  Stage-2 IR SHA256:
  `7a2af3e69f547fc36c7f1ef0c073e276851ff10b4243023f452f5a0639f78fe4`.
  Evidence: `build/release-audit/external-root-{regression-final,sanitize-final,stores-sanitize,references}.log`,
  `build/nested-reference-readiness-audit.json` and
  `build/release-audit/external-root-countermodel.json`.
  All release gates remain Open.

- Deeper nested lifetime audit: the existing 12-case-per-frontend readiness
  target still passes. The required `nested-reference-depth-readiness-test`
  expands to 27 fixtures per frontend: depth-two/three/four external-return
  copies and addresses plus frame scalar addresses at each level. All negative
  classifications and lifetime diagnostics pass; the eight depth-three/four
  external-return observations overreject in both frontends. The strict target
  correctly exits with failure after saving the complete evidence. These gaps
  are required unfinished 1.0 work, not an exclusion from the language goal.
  A private terminal-layer/physical-leaf correction also loses tracked roots
  during computed projections, so no experimental semantic changes were
  promoted. Production compiler sources and stage-2 IR are unchanged.
  Evidence: `build/nested-reference-depth-readiness-audit.json`,
  `build/release-audit/nested-depth-{required-readiness,supported-readiness}.log`
  and the private `nested-depth-terminal-layers.json` report.
  The next correction must preserve external payload roots through each
  intermediate copy without retaining callee frame addresses. All gates remain
  Open; nested-storage guards remain active.

- Deeper payload retention correction: both frontends now keep already-nested
  payload loans when taking the physical address of borrowed storage. Precise
  physical reference terminals are distinct from payload graphs; selected
  terminals become layer zero, nested projections preserve payload layers and
  computed copies select value paths rather than extra referent paths.
  The 54-case depth readiness audit now passes all classifications and
  diagnostics, including the previous eight overrejections. Accepted positives
  execute across five engines plus O2 on both frontends (120 executions);
  negatives never execute. The deeper audit is now part of the test target.
  This fixes the recorded depth-two/three/four return cases without claiming arbitrary alias/store or
  borrowed-slice completeness. Production restrictions remain active.
  Validation: `make -j4 test bootstrap-check editor-distribution-test` PASS;
  normal and deeper readiness targets PASS. Graph, copy, loan, selection,
  physical-address, descriptor-rollback and stores sanitizer targets PASS.
  Bootstrap/stage2/stage3 IR and native binaries remain identical.
  Stage-2 IR SHA256:
  `e32b177cc1fff9c429da26aac5cbbd6d3bf82847cdef6a943c4675c31c06a8aa`.
  Evidence: `build/release-audit/nested-depth-{regression,sanitize,engines,fixed-readiness}.log`
  and `build/nested-reference-depth-readiness-audit.json`.
  All release gates remain Open.

- Nested receiver contracts: added twelve private store fixtures per frontend.
  Depth-two/three local replacements and lifetime rejection already worked;
  valid `stores(p,src)` nested writes falsely mixed payload origins into
  destination authorization. Contracts now check actual physical caller roots.
  Retargeting `p.next=other` revealed that an incomplete trial accepted a write
  without `stores(other,src)`; this negative was never executed or promoted.
  Precise parameter terminals and referent-typed storage graphs now retain that
  new physical destination, so missing contracts reject and complete contracts
  execute with the expected stored value. Source modes are not upgraded.
  Combined depth/store audit: 78 classifications and 180 positive execution
  runs PASS across both frontends, five engines plus O2. Production nested
  guards remain; arbitrary alias/store and borrowed slice elements are still
  required unfinished work. Dedicated store-readiness joins the test target.
  Validation: `make -j4 test bootstrap-check editor-distribution-test` PASS;
  dedicated permanent store-readiness PASS (48 classifications/108 runs).
  Graph, copy, loan, selection, physical-address, descriptor-rollback and stores
  sanitizer targets PASS. Bootstrap/stage2/stage3 IR and binaries converge.
  Stage-2 IR SHA256:
  `18d5713cda60a00f56b5aef0b2191b5e5860a27474df811c3d484580d9233faa`.
  Evidence: `build/release-audit/nested-store-{regression,sanitize,fixed-readiness,permanent-readiness}.log`,
  `build/release-audit/nested-store-fixed-readiness.json`,
  `build/nested-reference-store-readiness-audit.json` and private trial
  `nested-store-retarget-{physical,precise,storage-type}.json` reports.
  All release gates remain Open.

- Pending owner addresses: separated temporary lifetime pins from borrowed
  values, using exact owned AST path identity for the current address operation.
  This removes the owned nested-store false rejection while preserving RHS
  move and aliasing replacement rejection. Computed reference results clone
  their existing roots into mode-zero pins without modifying ordinary value
  capability. Pins are excluded from value/authority/store/return selection;
  constructor deduplication distinguishes their role. Both frontends align.
  Expanded final private depth/store audit: 112 classifications, 40 positives
  and 240 execution runs across five engines plus O2, with no gaps.
  Legacy lifecycle adds repeated owner reborrows and rejects any holder carrying
  a pin; 64/1024 submissions retain equal graph peaks and clean up to zero.
  Graph/copy/loan/selection/access/physical-address/descriptor/stores ASan/UBSan
  targets PASS. The existing owner-evaluation and standard library checks PASS,
  including dereferencing a function's returned reference to an owner.
  Evidence: `build/release-audit/owner-pin-{regression,sanitize}.log`,
  `build/release-audit/nested-owned-pin-final-readiness.{json,log}` and
  `build/legacy-graph-lifecycle-audit.json`.
  Full `make -j4 test bootstrap-check editor-distribution-test` PASS; external
  installation/distribution and bootstrap/stage2/stage3 convergence PASS.
  Stage-2 IR SHA256:
  `e0801b26b44ab0cf4ba3e2d69ffded8080725fcbcc0676514028a7befa7d857e`.
  Production nested storage restrictions remain; all release gates remain Open.

- Borrowed slice backing and element roots: private type/parser guard bypass
  exposed two unsafe acceptances (local element-slot return and direct mutation
  of a sliced array); neither negative was executed. Formation now always
  retains backing storage and selects typed element payloads separately.
  Slice parameters, computed/call values and subslices preserve their layers;
  live receiver graphs acquire newly stored source roots. Local stored return
  escape rejects, while contracted external source stores/returns succeed.
  Added 26 private fixtures per frontend and permanent readiness/sanitizer
  targets; actual production storage/type/parser restrictions remain active.
  Combined depth/store/slice audit: 164 classifications and 384 positive
  execution runs across five engines plus O2 PASS with no gaps. The private
  frontend's instrumented slice audit passes 76 classifications and 32 tree
  runs, with ASan load/store instrumentation explicitly verified. Existing
  graph/copy/loan/selection/access/physical/descriptor/stores sanitizer targets
  PASS. Reports match current compiler/legacy source hashes.
  Evidence: `build/release-audit/slice-backing-{regression,sanitize,combined-readiness}.log`,
  `build/release-audit/slice-backing-combined-readiness.json`,
  `build/nested-reference-slice-asan-audit.json`, and the failing private
  `build/release-audit/borrowed-slice-lifetime-baseline.json` countermodel.
  Full `make -j4 test bootstrap-check editor-distribution-test` PASS, including
  the new permanent slice-readiness target, external distribution and identical
  bootstrap/stage2/stage3 IR/native binaries. Stage-2 IR SHA256:
  `863864f64fc672bf531257cf6754bf2c99e97e78da2f06a82ffa61afa59be49b`.
  Arbitrary nested/recursive/alias slice storage and persistent REPL lifetimes
  still require audit before enabling the feature. All release gates remain Open.

- Persistent borrowed slices: added six guard-bypass REPL scenarios on both
  frontends, covering backing forget/mutation, source release, compile/runtime
  recovery and warm identity calls followed by body replacement. Four allocation
  workloads exercise 64/1024 repetitions with reused session storage. For each
  workload, final tracked bytes/count and peak tracked bytes are equal at both
  history lengths. Partial stores, selected values and compile recovery finish
  at 32,154,167 tracked bytes / 18 allocations; identity declarations finish at
  32,159,385 / 63. These totals include fixed compiler tables/live declarations
  and establish bounded history retention; host internals, JIT mappings and RSS
  are not measured.
  The ordinary production allocation suite also passes with its default IR.
  Evidence: `build/release-audit/slice-repl-{lifecycle,validation,final-validation}.log`,
  `build/release-audit/slice-repl-lifecycle.json`,
  `build/nested-reference-slice-{readiness,asan}-audit.json` and
  `build/repl-lifecycle-audit.json`.
  Permanent private slice readiness and sanitizer targets include REPL and
  allocation checks. Production guards remain; all release gates remain Open.

- Cyclic borrowed type reachability: a private recursive `Node{kids:[]Node}`
  program exposed a stack-overflow/SIGSEGV in `ContainsReference`. Both frontend
  implementations now perform finite type reachability with a query-local
  visited bitmap, preserving the owner boundary and checking remaining fields
  after a cycle. Nine new private fixtures cover nested slices, external versus
  local element/slot returns, retained backing mutation, recursive reads and
  short replacements, and a cycle-first explicit-reference initializer. Two
  actual production diagnostic probes verify unsupported recursive declarations
  reject without a compiler crash.
  Full `make -j4 test bootstrap-check editor-distribution-test` PASS. Expanded
  combined depth/store/slice audit: 182 classifications, 70 accepted programs
  and 420 execution runs across both frontends/five engines plus O2, no gaps.
  Permanent private slice readiness and instrumented slice sanitizer audits
  each pass 94 classifications/38 positives plus 12 persistent scenarios and
  eight allocation observations; readiness runs 228 executions and sanitizer
  runs 38 tree executions. Primary-forms sanitizer also PASS.
  Evidence: `build/release-audit/recursive-slice-{regression,combined,sanitize}.log`,
  `build/release-audit/recursive-slice-combined.json`,
  `build/nested-reference-slice-{readiness,asan}-audit.json`. Baseline crash:
  `build/release-audit/nested-slice-baseline.log`. Stage-2 IR SHA256:
  `ba0be15aabe8ad8529cf157a7ea2d9bc9d820d0f5363369c9e787bbc5b14cc0d`.
  Production guards remain; mutual recursion, aliases and broader lifetime
  coverage remain required. All release gates remain Open.

- Slice return root selection: eight new private mutual-recursion/nested
  descriptor fixtures exposed two valid external inner-slice returns rejected
  by the coarse Region union, on both frontends. Slice returns with nonzero
  regions now use physical root authorization alongside reference returns;
  other aggregate returns keep the conservative region gate. Region-zero
  empty values preserve the existing root-free contract. An initial full test
  caught rejection of a valid empty literal; that regression is fixed rather
  than excluding the existing language case. Six further private fixtures
  distinguish literal/binding empties from local zero-length array views and
  separate `stores` installation from `borrows` return authorization.
  Scoped conflicts may now precede return diagnostics; the mixed-branch
  language case checks that first conflicting reborrow, and a separate
  one-branch case still requires local-return lifetime rejection.
  Combined depth/store/slice audit: 210 classifications and 82 positives,
  492 executions across both frontends/five engines plus O2, no gaps. Slice
  sanitizer: 122 classifications/50 tree runs plus 12 persistent scenarios and
  eight allocation observations PASS; primary-forms sanitizer also PASS.
  Evidence: `build/release-audit/mutual-slice-{baseline,precise-return}.{json,log}`,
  `build/release-audit/slice-return-{boundary,final-combined}.{json,log}`,
  `build/release-audit/slice-return-{language,sanitize}.log`.
  Initial regression logs document empty-value rejection and the changed first
  diagnostic; they are not passing acceptance evidence.
  Full `make -j4 test bootstrap-check editor-distribution-test` PASS, including
  external installation and bootstrap/stage2/stage3 convergence. Permanent
  slice readiness: 122 classifications/50 positives and 300 execution runs,
  plus persistent and allocation observations PASS. Final full regression:
  `build/release-audit/slice-return-verified-regression.log`. Stage-2 IR SHA256:
  `82b83e55bfb9aecc87bf76b120ea8f21987e22a0ed40af3beeb4b1f28273ab64`.
  Zero-region accumulation still needs permanent adversarial branch/alias/store
  and foreign/raw coverage; production nested guards and all release gates
  remain Open.

- Root-free slice replacement audit: promoted six local-return countercases
  into the permanent public slice-descriptor suite. Literal/helper-created empty
  bindings acquire local backing through assignment, a branch, a scoped mutable
  alias or a checked `stores` call. Zero-sized arrays and zero-length views also
  retain their installed backing roots. Every countercase requires the precise
  return-lifetime diagnostic, not merely any rejection. Five positive paths
  validate literal/helper empties, external stored/aliased backing, and both
  taken/untaken branches with expected values and zero surviving owners.
  Public production and seed frontends PASS on five engines plus O2. The
  slice-descriptor sanitizer target also PASS on its third, instrumented
  frontend and generated ASan/UBSan runtime; total suite now has 37 rejections
  and 30 independently modeled descriptor permission queries per frontend.
  Its REPL-loan sanitizer dependency passes persistence/recovery and the
  288-query read/write model. Compiler sources/IR are unchanged.
  Evidence: `build/release-audit/slice-empty-descriptor-{regression,sanitize}.log`.
  These tests cover root accumulation after an initially empty value; they do
  not complete foreign/raw, recursive alias or whole-language safety audits.
  Production nested-storage guards and all release gates remain Open.

- Nested slice value selection and stable simple call projections (specification
  draft 27): private generic recursion, enum payload, depth-three descriptor and
  alias fixtures exposed intermediate backing roots incorrectly retained by
  direct value selection. Selection now distinguishes slice value copies from
  storage/address selection. Precise intermediate terminals can be absent from
  an element value; its payload edges remain, with unchanged capability limits.
  Cursor endpoints, address selection, opaque/mismatched/incomplete paths and
  physical/authority checks remain conservative. Proven-absent selected roots
  do not recreate fallback loans or become computed result origins.
  A same-root intermediate/endpoint graph probe checks both shared/exclusive
  edge insertion orders, entry modes, absence and conservative fallbacks;
  the existing 1,648 independent selection/overlap/authority oracle also PASS
  with ASan/UBSan. Metadata selection does not itself authorize permissions.

  A bounded whole-body recognizer proves same-typed slice parameter returns,
  including literal/omitted reslicing bounds, without stores effects. These
  calls preserve actual argument value graphs rather than distributing every
  contracted root into every output slot. Unused overdeclared sources remain
  protected as arguments but do not enter the proven result. Forward and
  instantiated generic helper cases execute correctly. Other bodies keep
  conservative summaries. Established projections cannot become another source
  or opaque during live REPL replacement; same-source reslicing/renaming remains
  compatible. Existing-caller and multi-declaration rollback scenarios verify
  rejection preserves prior behavior. General body summaries and dependent
  caller revalidation remain required unfinished work.

  ASan found a new internal mistake: stored receiver effects reuse
  `ReferenceNewCall` with non-call destinations and slot -1. Projection lookup
  now requires a CALL and a valid function-table slot; receiver effects keep
  their old summary path. The failing setter was not excluded. Corrected private
  slice sanitizer: 164 classifications/70 tree runs, 22 persistent scenarios
  and eight allocation observations PASS. Permanent readiness has the same
  classifications/positives and 420 executions. Expanded combined depth/store/
  slice audit: 252 classifications/102 positives and 612 executions across both
  frontends/five engines plus O2, no gaps. Graph/copy/loan/selection/access/
  physical-address/descriptor/stores and public slice-descriptor sanitizer
  targets PASS. The four existing allocation workloads retain equal final and
  peak tracked bytes/counts at 64/1024 histories.

  Full `make -j4 test bootstrap-check editor-distribution-test` PASS on the
  corrected compiler, including external distribution and identical bootstrap/
  stage2/stage3 IR/native binaries. The later forward/generic fixtures and
  same-root graph probe pass their expanded permanent readiness/sanitizer/O2
  targets. Stage-2 IR SHA256:
  `6d5614be275227f0c3ea938b20f2151b33cc038b7f4056d3fa7f6d2ad2061ad0`.
  Evidence: `build/release-audit/slice-projection-final-{regression,sanitize}.log`,
  `build/release-audit/slice-projection-expanded-{validation,combined}.log`,
  `build/release-audit/slice-projection-expanded-combined.json`,
  `build/release-audit/slice-value-purpose-oracle.{json,log}` and
  `build/nested-reference-slice-{readiness,asan}-audit.json`.
  Counterexamples: `slice-aggregate-baseline.{json,log}`,
  `slice-value-selection-trial.{json,log}` and `slice-projection-sanitize.log`.
  Production nested-storage guards and all release gates remain Open.

- Straight-line slice alias projections (specification draft 28): result-origin
  inference now follows inferred `let`/`var` copies and literal reslicing while
  retaining the original parameter index. Unused aliases of other parameters
  do not contaminate the result. Assignments, calls, dynamic bounds, shadowing,
  duplicate names and unsupported statements keep the conservative summary;
  shared payload capabilities cannot become mutable through an alias. The
  recognizer uses bounded stack tables (32 names including arguments, 512 body
  tokens), checks token reads and falls back on exhaustion. Both frontends are
  aligned. Same-origin alias replacement preserves existing REPL callers;
  changed origins are rejected and roll back. General body summaries and
  dependent caller revalidation remain unfinished.

  Corrected permanent readiness: 194 classifications/80 positive programs,
  480 five-engine/O2 executions, 26 REPL scenarios and eight allocation
  observations PASS. Private sanitizer: the same 194 classifications and
  80 tree executions PASS. Shared mutation, duplicate declarations and malformed
  reslicing were rejected correctly on the first run, but their expected
  diagnostics initially assumed a later lifetime error; the test now asserts
  the actual earlier capability/declaration/grammar errors. No fixture was
  removed. Ordinary alias fixtures also pass 26 checks and eight executions on
  unmodified public production/seed frontends. Production nested-storage guards
  remain enabled.

  Full regression, three-generation bootstrap convergence and external editor/
  distribution validation passed on the unchanged compiler in the combined
  `slice-alias-final-validation.log` run; that command exited 2 solely for the
  three new diagnostic expectations above. After correcting only expectations,
  readiness/slice sanitizer plus graph/copy/loan/selection/access/physical/
  descriptor/stores/public slice sanitizer targets exit 0 in
  `build/release-audit/slice-alias-corrected-validation.log`.
  Production stage-2 IR SHA256:
  `7f368956c2b3fbcd679beeeefe9100cfd4cea9e53b63560dfcb3548fd6f59979`.
  Additional evidence: `build/release-audit/slice-alias-bootstrap.log`,
  `build/release-audit/slice-alias-public.json` and
  `build/nested-reference-slice-{readiness,asan}-audit.json`; both permanent
  reports' compiler/legacy source hashes match the committed sources.
  The four allocation workloads retain equal final/peak tracked allocations
  at histories 64 and 1024. All mandatory release gates remain Open.

- Transactional REPL projection revalidation (specification draft 29): changed
  established slice projections no longer unconditionally require a new session.
  After new bodies pass checking, the parser compares snapshot/final projections
  and rechecks every unchanged retained concrete body against the new callees.
  Safe caller contracts and same-submission caller rewrites are accepted;
  invalid lifetime contracts reject and roll back every replacement. Instantiated
  generic callers participate. Retained bodies with injected ownership/defer
  cleanup are also valid reanalysis inputs. Existing values retain historical
  provenance and continue to prevent forgetting borrowed backing bindings.

  Review exposed an implementation prerequisite: ReferenceParameters previously
  appended synthetic roots to function locals via AllocateLocal. Reanalysis
  could reseed those roots and register allocations under an unrelated current
  function. Roots now belong to ReferenceCheck and are freed after its loans and
  graph on success or abort. Function AST/local allocation lists are untouched.
  The legacy graph lifecycle instrument's exact structure marker was updated
  for the new field, retaining its graph allocation and barrier checks.

  Permanent readiness/sanitizer: 194 classifications, 80 positive programs,
  480 five-engine/O2 executions (80 tree runs under ASan), 36 persistent REPL
  scenarios, zero gaps and 12 allocation observations PASS. Multiple producer
  replacements followed by a later retained caller failure restore all prior
  behavior. Revalidation success and rollback workloads at 64/1024 histories
  have equal final/peak tracked allocation bytes; success ends at 32,164,649
  bytes/139 allocations and rollback at 32,164,643/136. The previous identity
  workload retains 288 fewer bytes/two fewer Local allocations (32,159,097/61).
  These include fixed compiler/live declaration resources, not host RSS or JIT
  mappings. Unmodified public production/seed frontends also pass 24 projection
  REPL scenarios in `build/release-audit/repl-projection-revalidation-public.json`.

  Full regression, bootstrap convergence, legacy graph lifecycle and external
  distribution passed on the current compiler in
  `build/release-audit/repl-projection-revalidation-complete.log`; that combined
  command exited 2 for the new cleanup fixture's invalid `defer { ... }` syntax.
  The fixture now uses supported `defer expression;`; no compiler change or
  exclusion was needed. Corrected permanent readiness/slice sanitizer plus
  graph/copy/loan/selection/access/physical/descriptor/stores/public slice
  sanitizer targets all exit 0 in
  `build/release-audit/repl-projection-revalidation-verified.log`.
  Production stage-2 IR SHA256:
  `ed0f3411e79a8a633f051fac25cef734633769c6d258d8418815899363b659b2`.
  Both final private reports' compiler/legacy source hashes match the sources.
  General body summaries, dependency-directed revalidation and the remaining
  production nested-storage acceptance stay mandatory; all gates remain Open.

- Dependency-directed projection revalidation (specification draft 30): changed
  established projections now seed a reverse graph from retained ReplNode CALL
  allocations, including value-copy clones. A bounded queue reaches transitive
  callers once across cycles, diamonds and multiple changed producers. New
  bodies were already checked against final headers. Missing node registries
  and positive slots outside the snapshot fall back to the full retained audit.
  Temporary adjacency/queue tables use submission scratch ownership, including
  nonlocal rollback cleanup. Inference and borrow permissions are unchanged.

  Added permanent `repl-dependencies-test` and sanitizer targets. Actual compiler
  analysis entry traces match an independent Python reachability model in 20
  cases on both production and legacy frontends (40 observations each at O2 and
  with the production frontend instrumented by ASan/UBSan). Cases cover indirect
  chains, cycles, diamonds, duplicated edges, multiple seeds and 12 deterministic
  random graphs. Missing/invalid/value-copy metadata probes preserve the AST and
  restore allocation ownership before checking. The rejected-caller case then
  executes the restored producer/caller, both yielding 7. A chain with 256
  unrelated bodies analyzes exactly three retained bodies; this is an analysis
  count result, not an elapsed-time speedup claim.

  Full `make -j4 test bootstrap-check editor-distribution-test
  repl-dependencies-sanitize-test nested-reference-slice-sanitize-test` exits 0
  in `build/release-audit/repl-dependency-regression.log`. After adding the two
  metadata boundary cases and rollback execution assertion, both expanded
  permanent dependency targets exit 0 in
  `build/release-audit/repl-dependency-expanded-validation.log`. Source/audit
  hashes in `build/repl-dependencies-{audit,asan-audit}.json` match current files.
  Existing slice readiness retains 194 classifications/80 positives/480 engine
  executions; slice sanitizer, 36 REPL scenarios and 12 allocation observations
  PASS. Revalidation success/failure allocations and peaks stay equal at 64/1024
  histories. Production stage-2 IR SHA256:
  `dbe6aa51997d7d98f77e0bdafdb965b3e07ed495ed48f25106095df6ce3e0fa6`.
  General body summaries, broader production nested-storage acceptance and all
  remaining mandatory release requirements are unfinished; all gates stay Open.


- Pure branch slice-origin unions (specification draft 31): the whole-body
  recognizer now returns a nonempty parameter-origin mask instead of one index.
  Pure boolean parameter/literal conditions (optionally negated), scoped aliases,
  nested blocks and early returns retain every possible returned source while
  excluding unused contracted arguments. Literal conditions still include both
  arms. Definite-return state is separate from the accumulated mask; continuing
  paths must reach a return. Blocks restore visible alias scope. Bounds remain
  conservative: 32 visible names, 512 body tokens and 16 block levels; overflow,
  assignments, calls and arbitrary condition expressions are opaque. Source
  permissions remain intersected, including shared/mutable branch unions.

  Permanent readiness/sanitizer: 232 classifications, 102 positive programs,
  612 five-engine/O2 executions (102 tree runs under ASan), 42 persistent REPL
  scenarios and 12 allocation observations PASS with zero gaps. New cases cover
  sibling alias names, continuing/nested branches, local-root countercases,
  literal-condition conservatism, bit 31, depth 16/17, branch-local scope and
  depth-three selection. REPL origin expansion rejects unsafe transitive callers
  and rolls back; narrowing and same-union branch swapping remain compatible.
  Success/failure revalidation retains equal tracked final/peak allocations at
  histories 64 and 1024. A separate public production/seed check covers 32
  ordinary branch classifications without removing production guards.

  Full test/editor/external-distribution/dependency sanitizer and private slice
  sanitizer command exits 0 in `build/release-audit/slice-branch-regression.log`.
  Graph/copy/loan/selection/access/physical-address/descriptor/stores/public slice
  sanitizer targets exit 0 in `build/release-audit/slice-branch-sanitize.log`.
  Bootstrap generations 1/2/3 and gen2==gen3 PASS in
  `build/release-audit/slice-branch-bootstrap.log`. Expanded testing initially
  rejected one intended positive because its fixture borrowed the same mutable
  descriptor into two live arrays. The fixture now uses an independent local
  backing source, preserving its lifetime countercase; no compiler workaround
  or exclusion was introduced. Corrected readiness and private sanitizer both
  exit 0 in `build/release-audit/slice-branch-corrected-validation.log`.
  Both permanent report source hashes match the current compiler/legacy files.
  Production stage-2 IR SHA256:
  `31e26395feef7e8df6de841e817ef31ba271561324cd074801128bc48a7e51e5`.
  General body inference, broader production nested storage and all mandatory
  release gates remain unfinished/Open.


- Production nested borrowed storage (specification draft 32): removed the
  blanket ReferenceStorage/ValidateReferenceStorage and borrowed slice-element
  restrictions from both frontends. Typed provenance, physical/payload roots,
  source permissions, lifetime/store contracts, raw anchor validation and
  owner-address pins remain authoritative. The nested regression tool now
  compiles byte-identical source copies without bypassing feature checks.
  Normal mode asserts copy identity; the unsafe-root countermodel remains an
  explicit experimental option rather than alternate production semantics.

  New loop receiver-retargeting cases require contracts for both possible
  destinations. Recursive slices preserve shared/exclusive payload authority.
  Valid raw anchors retain nested lifetime/capability checks. An owned recursive
  REPL payload replacement followed by assertion failure preserves the changed
  value and old/new protected roots; forgetting its owner releases both and
  leaves zero owners. A zero-length fixed array has no reference slots and can
  initialize empty, including in structs/owners. Other actual reference fields
  still require explicit initialization. Empty array element access traps with
  the normal bounds diagnostic across engines and both/instrumented frontends.

  Enabling the feature exposed an actual value-transport defect: moving
  `own[&Mixed]` into another aggregate omitted its layer-one external payload
  loans, despite retaining a field graph. Layer-zero owner/aggregate value
  copies now transport all payload layers. Reference-valued and deeper-layer
  selections retain existing filtering, preventing descriptor/backing roots
  from contaminating scalar reference and inner-slice results. Physical/raw
  paths remain distinct. Regression cases validate external payload returns
  after relocation, local descriptor/owned payload address rejection and shared
  permission barriers. Existing disjoint-field/layer models also pass.

  Permanent production slice readiness/sanitizer: 262 classifications and
  112 positive programs, 672 five-engine/O2 executions (112 tree ASan runs),
  44 persistent scenarios, zero gaps and 12 allocation observations PASS.
  Combined depth/store/slice audit: 350 classifications, 144 positives and
  864 executions; combined production-frontend ASan/UBSan audit runs the same
  classifications/144 tree positives and all 44 persistent scenarios PASS.
  Final source hashes match compiler/legacy files in both combined/permanent
  reports. REPL replacement success/failure workloads retain equal tracked
  final/peak allocations at histories 64 and 1024; this is not an RSS claim.
  Former support-limit rejection fixtures are promoted to positive checks or
  executable cases with assertions in the reference/heap/slice/mixed suites.
  Local storage escapes retain their precise lifetime errors. The late-DAG
  initializer test now distinguishes a real reference field from an empty
  nullable owner field; both semantics have permanent coverage.

  `make -k -j4 test bootstrap-check editor-distribution-test
  nested-reference-slice-sanitize-test heap-borrows-sanitize-test
  slice-descriptors-sanitize-test mixed-owned-references-sanitize-test
  primary-forms-sanitize-test` exits 0 in
  `build/release-audit/nested-production-all-regression.log`. Graph/copy/loan/
  selection/access/physical/descriptor/stores/dependency sanitizer targets exit
  0 in `build/release-audit/nested-production-verified-sanitize.log`.
  Combined evidence: `nested-production-verified-combined{,-asan}.{json,log}`.
  Earlier `nested-production-*-validation.log` and trial combined reports record
  initializer/obsolete-restriction expectations and the transport defect;
  they are not passing acceptance evidence. Bootstrap/stage2/stage3 converge.
  Production stage-2 IR SHA256:
  `baf859d61d182711ad55d00d65479e7cf249ca59b53bc3c8d68c5177d8c28872`.
  `examples/nested-views.cool` demonstrates a shared matrix view, descriptor
  reference returns and backing reuse after scope exit; five engines/O2 and
  seed tree produce 21 (`nested-views-example.json`, seven executions).
  Production availability is established for the audited cases. Broader safety
  fuzzing, relocation/alias combinations, collection APIs and every remaining
  mandatory release gate stay Open.

- Relocated borrowed endpoints and pure reference proofs (specification draft
  33): a borrowed owner moved through a slice previously lost its deeper
  external payload role. Selected non-reference tracked values now reconstruct
  physical/payload roles with a finite node/role walk. Same-root dual roles keep
  both records; opaque paths remain conservative. Computed retagging also keeps
  those roles instead of overwriting all nonlayered results with layer zero.
  Full-place authority and owner pins are checked before selection.

  Computed receiver coverage exposed a second defect: acquiring an address to
  a nested borrowed value could replace its payload graph with a type-mismatch
  fallback. Payload graphs are now wrapped under the new reference's Referent
  edge. Value copies consume intermediate slice/reference storage terminals
  while retaining endpoint and payload roots. Field/array/slice/enum relocation,
  call-produced slices and call-produced receivers all preserve valid external
  returns. Local payload/owner-slot escapes and shared receiver moves retain
  their required rejection diagnostics.

  The bounded pure parameter/alias/boolean-branch origin proof now supports
  exact-type reference returns as well as slices. Reference reslicing is not
  accepted by that proof. Same-type proven calls preserve value graphs; changed
  reference origin sets use the existing dependency-directed retained-caller
  revalidation. A producer replacement that invalidates an established caller
  rejects and restores its earlier execution (7 before and after rejection).
  Unsupported bodies, foreign/generic functions and stores remain conservative.

  Combined production/seed audit: 374 classifications, 158 positive programs,
  948 tree/five-engine/O2 executions, 46 REPL observations, zero gaps and 12
  allocation observations PASS. The combined production ASan/UBSan frontend
  audit covers the same classifications, 158 tree positives and 46 REPL
  observations PASS. Permanent slice reports cover 286 classifications, 126
  positives, 756 executions (126 ASan tree runs), 46 REPL observations and zero
  gaps. Final compiler/legacy hashes match all four reports. Allocation histories
  at 64/1024 retain equal final/peak tracked resources. New-syntax bootstrap
  stage2/stage3 and legacy generation 2/3 converge.

  Full `make -k -j4 test bootstrap-check editor-distribution-test
  nested-reference-slice-sanitize-test heap-borrows-sanitize-test
  slice-descriptors-sanitize-test mixed-owned-references-sanitize-test
  primary-forms-sanitize-test` exits 0 in
  `build/release-audit/nested-relocation-final-regression.log`. Graph/copy/loan/
  selection/access/physical/descriptor/stores/dependency sanitizer targets exit
  0 in `nested-relocation-final-sanitize.log`. Final combined reports/logs:
  `nested-relocation-final-combined{,-asan}.{json,log}`. Earlier baseline and
  intermediate logs record the overrejections and are not final acceptance
  evidence; the initial combined launch found a duplicate fixture name before
  running its audit, corrected without removing either test.
  Production stage-2 IR SHA256:
  `9456025a81c362280b86f23b07bbe649539c867493fedc786c6d688e8659c3cb`.
  Broader alias/relocation fuzzing, borrowed collection APIs, general body
  inference and every outstanding mandatory gate remain Open.

- Generic inactive storage effects (specification draft 34): a validated
  dependent template can specialize its `stores(dst,src)` relation to plain
  values without inventing a borrowed lifetime effect. The relation is inactive
  only for a concrete nonforeign specialization with an exclusive destination
  and no scoped borrows on either destination pointee or source. Other active
  pairs remain enforced. Parsed pair masks are separate from active effects,
  preserving duplicate detection. Unused known-invalid templates, shared
  receivers, nongeneric invalid declarations and foreign promises remain errors.

  Expanded permanent stores tests cover scalar/array/owning specialization,
  generic forwarding and a mixed inactive/active two-destination function. The
  active borrowed destination still prevents mutation of its installed source;
  the plain destination remains writable. 31 required rejection cases and
  existing lifetime/receiver/REPL models pass across production/legacy and the
  instrumented production frontend, five engines/O2 and runtime ASan/UBSan.
  Tracked store lifecycle histories 64/1024 finish at zero bytes/allocations
  with equal peak 6,168 bytes. Initial focused validation passes in
  `build/release-audit/generic-stores-validation.log`.

  Full `make -k -j4 test bootstrap-check editor-distribution-test
  stores-sanitize-test` exits 0 in
  `build/release-audit/generic-stores-final-regression.log`. Both bootstrap
  paths converge; production stage-2 IR SHA256:
  `abc17d2743be84f44635b86f1977539d16d67025e07187f9064d06e80d084ca7`.
  This is a prerequisite for one collection API across plain and borrowed T,
  not a completed borrowed-vector implementation. An isolated Option-slot
  Vector prototype exposed a production overrejection: installing direct
  `new[Maybe](Maybe.None)` into a borrowed owner slot succeeds, while passing
  the same reference-free value through a named local fails. A named unit
  variant similarly fails. Baseline fixtures/report are retained in
  `build/release-audit/empty-borrowed-{direct,named,unit}.cool` and
  `empty-borrowed-baseline.json`. Root-free value transport must be corrected
  before promoting the prototype; it is not release acceptance evidence.
  All mandatory gates remain Open.

- Root-free transport and borrowed vectors (specification draft 35): named
  unit variants and owners initialized without scoped roots no longer acquire
  fictitious local-storage loans when copied/moved. The exception requires a
  tracked holder marker and no root-bearing loan for that holder; it excludes
  references, physical addresses, owner_slot and pending_owner acquisitions.
  Actual and historically retained roots remain conservative. Explicit unit/
  owner stores and returns pass, while real local payload escape, owner-address
  escape, live-address moves and pending-index owner moves remain rejected.

  Vector now stores 32 initialized Option[T] slots per chunk. Free/method append
  APIs retain conditional stores effects; free/method pop returns carry source
  borrow contracts. Payload addressing asserts Some and uses the published enum
  offset. Pop moves through a typed scoped raw anchor, resets None, then updates
  and releases chunks through the trusted raw adapter without reusing freed slots.
  No per-element heap wrapper is introduced. Borrowed pop results conservatively
  retain the source lifetime; clear retains historical scoped roots until scope
  exit. Shared access/iteration preserve mutable-payload barriers.

  Permanent borrowed-vector tests cover 65 independent modeled values, chunk
  growth/deletion, shared/mutable iteration, aggregate/owned borrowed elements,
  exact live owner counts, fully empty reuse and live-chunk pop/reappend from a
  different source. Ten lifetime/capability negatives pass. Normal reports have
  32 engine/negative observations on production/legacy; instrumented frontend
  and runtime ASan/UBSan reports have 49. Compiler/legacy/stdlib hashes match.
  Existing owning-vector model seeds 7/42/2026 and runtime sanitizers also pass.
  REPL pop followed by assertion failure preserves the surviving vector and its
  protected roots; forgetting it releases storage and permits source reuse.

  Combined audit: 392 classifications, 168 positives, 1,008 engine executions,
  48 REPL scenarios, zero gaps and 12 allocation observations PASS. Combined
  production ASan/UBSan frontend audit has the same classifications, 168 tree
  positives and all REPL scenarios PASS. Permanent slice reports cover 304
  classifications, 136 positives, 816 executions (136 ASan tree runs), 48 REPL
  scenarios and zero gaps. All compiler/legacy/stdlib hashes match. Existing
  tracked resource histories at 64/1024 retain equal final/peak allocations.

  Full `make -k -j4 test bootstrap-check editor-distribution-test
  borrowed-vector-sanitize-test nested-reference-slice-sanitize-test
  stores-sanitize-test` exits 0 in
  `build/release-audit/borrowed-vector-final-regression.log`. Expanded/repaired
  permanent targets exit 0 in `borrowed-vector-verified-validation.log`.
  Final combined evidence: `empty-borrowed-verified-combined{,-asan}.{json,log}`.
  Earlier expanded reports failed only because the new package-import REPL
  fixture was run directly without the project driver. The fixture now runs
  the same private frontend through the driver, records that execution route,
  and includes stdlib hashes; no compiler guard or test was removed.
  Production stage-2 IR SHA256:
  `e0937220990e13a54c5abccf45f1811bb169215d52747d5e3ade77075aa4e755`.

  Measuring the new representation found a real performance regression:
  Chunk[u8] grows 48→528 bytes, and a controlled 500,000-byte standalone O2
  append/traverse/clear workload rises 58.350→91.655 ms median (seven alternating
  samples after warm-up). `tools/bench_vector_storage.py` and
  `docs/benchmarks/vector-storage-arm64.json` reproduce/retain the evidence.
  Reducing plain-value slot overhead while preserving safe borrowed storage is
  now required before G8 closure. All mandatory gates remain Open.

- Narrow Vector storage and chunk-wise clear (specification draft 36):
  sizeof(T)==1 selects 32 inline byte slots, which cannot hold actual scoped
  reference or ownership handles. Larger types retain explicitly initialized
  Option slots and ordinary payload destructors. Separate nullable small/big
  heads remove enum-head handling while keeping one chunk allocation per 32
  elements; only the size-selected family is active. Raw tail/cursor operations
  use that family. Vector itself grows 24→32 bytes; a byte chunk returns to
  48 bytes from 528. The large Option initializer is isolated in a construction
  helper instead of the hot append frame. Pop transfers its value before chunk
  release. Public APIs, stores effects and conservative borrowed pop lifetimes
  remain unchanged.

  Clear now detaches and drops complete tail chunks, avoiding an Option return
  for each discarded element. Each chunk's next owner is already null when
  dropped, bounding explicit clear's chunk recursion. All owned payloads are
  still dropped once. Ordinary scope-exit drop still follows the head chain
  recursively and needs separate resource-depth validation; this change does
  not claim to bound that path. Historical scoped roots remain protected after
  clear, now with a permanent required rejection case.

  Expanded Vector tests add u8/i8/bool, one-byte struct/fixed-array and a struct
  with zero-length reference/owner fields, with 65 values, exact chunk ownership,
  32/33 boundary reuse, ordered pops and live scope-exit cleanup. Zero-length
  fields may increase alignment; their storage selection follows actual sizeof.
  A 33-element owned borrowed-view scope checks both chunk and element cleanup.
  Normal production/legacy reports have 34 observations; instrumented frontend
  plus runtime ASan/UBSan reports have 52, including 11 required negatives.
  Existing owning collection seeds 7/42/2026 pass normal/runtime sanitizers.

  Full `make -k -j4 test bootstrap-check editor-distribution-test
  borrowed-vector-sanitize-test nested-reference-slice-sanitize-test
  stores-sanitize-test` exits 0 in
  `build/release-audit/vector-inline-final-regression.log`. Both bootstrap paths,
  external distribution and editor client validation pass. Permanent nested
  readiness reports retain 304 classifications, 136 positives, 816 engine
  executions, 48 REPL scenarios, zero gaps and equal tracked lifecycle resources
  at histories 64/1024; the ASan frontend report covers the same classifications,
  136 tree positives and 48 scenarios. All four Vector/nested normal/sanitizer
  reports match current compiler/legacy/stdlib hashes. Production stage-2 IR
  SHA256 remains `e0937220990e13a54c5abccf45f1811bb169215d52747d5e3ade77075aa4e755`.

  Final same-compiler standalone O2 byte workload (500,000 elements, independent
  checksum, warm-up and seven alternating samples, no competing validation)
  measures old plain storage at 23dbe7d: 58.367 ms median; current: 56.555 ms.
  Both byte chunks are 48 bytes. This restores the earlier workload range rather
  than proving a general speedup. Evidence and source/compiler/binary hashes:
  `docs/benchmarks/vector-inline-arm64.json` and
  `build/release-audit/vector-inline-final-benchmark.log`. Intermediate prototype
  rejection logs and slower enum-head measurements are not acceptance evidence.
  Broader element-size performance, scope-exit depth, safety fuzzing and every
  remaining mandatory release gate remain Open.

- Bounded-depth destruction (specification draft 36 continuation): scope-exit
  destruction of deep owned structures no longer grows the native stack with
  value depth. The interpreter walks explicit DFS frames (32 inline, then a
  heap buffer); generated LLVM destructors submit typed callbacks to a LIFO
  worklist in the C runtime, releasing owner storage after its children.
  Array/struct children are enqueued in reverse so the LIFO dispatcher keeps
  forward DFS order, and enums release only the active payload.

  Regression: a 32,768-node owning chain under a 1 MiB RLIMIT_STACK crashes
  every engine before the change (tree/interp/jit/llvm exit 139, llvm-jit exit
  132) and completes with stdout `123`, exit 0 and zero remaining owners after
  it, on both frontends and at release O2. `tools/test_drop_depth.py` covers
  the deep chain, worklist growth boundaries, mixed struct/enum/array
  ownership, moved/null owner slots and persistent-REPL release across five
  engines + O2; `make drop-depth-sanitize-test` adds runtime ASan/UBSan and an
  ASan-instrumented frontend (129 executions). The full `make -k -j4 test
  bootstrap-check editor-distribution-test borrowed-vector-sanitize-test
  nested-reference-slice-sanitize-test stores-sanitize-test` exits 0 in
  `build/drop-depth/full-regression.log`; both bootstrap paths converge
  (self-host IR SHA256 begins `21f9f88504284a28`).

  Ordinary destruction keeps direct-call cost. Types whose structural drop
  depth is bounded are emitted as direct recursive drops with no dispatcher,
  and owner wrappers skip the worklist entirely for moved/null slots. Release
  O2 destruction microbenchmarks (independent checksum, warm-up, seven
  alternating samples, three runs) measure shallow per-iteration owner drops
  and 300-wide arrays at parity with the previous recursive code, and recursive
  chains / 500k-byte vector teardown at ~1.16x / ~1.33x. The residual is the
  cost of the bounded worklist on recursive types and remains the G8 follow-up
  named below. Evidence and methodology: `tools/bench_drop_depth.py` and
  `docs/benchmarks/drop-depth-arm64.json`. Both interpreters also recurse
  natively for shallow destruction and only reach the explicit-frame DFS past a
  depth budget, so `tools/cool run` on the destruction-heavy shallow program
  moves from ~1.34x/1.24x (tree/interp) to ~1.18x/1.19x. Broader
  depth/store/slice audits, safety fuzzing and every remaining mandatory gate
  stay Open.

- Ownership/evaluation-order fuzzing: `tools/test_ownership_fuzz.py` generates
  seeded programs that move, replace, mutate, swap, scope-drop and branch on a
  set of owning slots, plus a fixed left-to-right argument-evaluation probe
  (`pick(new[i64](next(&mut c1)), new[i64](next(&mut c2)))`). An independent
  Python model of live owners and values drives exact `mem.owner_count()`
  assertions after every operation and a zero-owner scope exit. Seeds
  7/42/2026/1/99 at 80 steps pass on five engines + release O2 on both
  frontends; `ownership-fuzz-sanitize-test` adds runtime ASan/UBSan and an
  ASan-instrumented frontend. This extends G9's adversarial/deterministic
  coverage for evaluation order and ownership; borrowed-storage fuzzing and
  every remaining mandatory gate stay Open.

- Scoped-loan fuzzing: `tools/test_borrow_fuzz.py` generates seeded sequences of
  shared and exclusive loans over two locals, writes through the root or an
  exclusive binding, reads through live loans and opens/closes nested scopes.
  An independent model of live loans decides which operations are legal; the
  valid program must run and print the modeled values on five engines and both
  frontends, and one deliberately conflicting operation must be rejected with a
  scoped-reference diagnostic. Seven seeds at 120 steps pass. Together with
  `tools/test_ownership_fuzz.py` this supplies G9's deterministic fuzzing for
  evaluation order, ownership and borrowed storage; failure promotion, broader
  slice/aggregate loans and every remaining mandatory gate stay Open.

- Diagnostics: the coercion rejection no longer claims a "narrowing
  conversion" for values whose type is not convertible at all. Numeric
  narrowing keeps `incompatible types; narrowing conversion requires an
  explicit cast`, while non-numeric or unrelated mismatches report
  `incompatible types; value and target types do not convert`. Both frontends
  emit the same categories. `tools/test_diagnostics.py` pins 13 rejection
  categories (narrowing, non-convertible type/argument/pointer, unknown
  variable/function, missing return, wrong argument count, use-after-move,
  borrow conflict, duplicate function) on both frontends. This improves G4's
  "useful source diagnostics"; the broader ergonomics and diagnostics audit
  stays Open.

- Borrowed map iteration: `std/map` now exposes `iter`/`Map.iter` returning a
  private `Iterator[V]` that walks the AVL tree in key order. It holds a `&Map`
  loan, a raw left spine bounded by the AVL depth (asserted at 64) and a
  remaining count; `next` yields `Option[&V]` and the value reference borrows
  the iterator, so `next` cannot run while a result is retained and the map
  cannot change while the iterator lives, and `Iterator.key` returns the key of
  the most recently yielded value as a borrowed `&Text`. 
  `tools/test_map_iteration.py` checks 48-key sorted values and keys against a
  Python model, `remaining()` countdown, empty-map `None` and the
  mutation/retention rejections on five engines + O2 on both frontends. This
  extends G5's borrowed collection iteration; aggregate iteration and the
  broader G5 audit stay Open.

- Aggregate-destruction fuzzing: `tools/test_aggregate_fuzz.py` builds random
  values from structs with owned fields, fixed arrays of owners and enums with
  owned payloads, asserts the exact live owner count while each value is alive,
  checks modeled element reads and requires zero owners after the scope exits.
  Five seeds at 80 values pass on five engines + release O2 on both frontends;
  `aggregate-fuzz-sanitize-test` adds runtime ASan/UBSan and an instrumented
  frontend. This extends G9's deterministic fuzzing from scalar owners to
  aggregate owned payloads; slice/relocation fuzzing and every remaining
  mandatory gate stay Open.

- Import-path completion: the language server completes module paths inside an
  `import "..."` string from the stdlib package directories, the `std/io` and
  `std/mem` builtins and the workspace module graph (`cool.mod` module plus
  every directory containing `.cool` files), filtered by the typed prefix. It
  bypasses the token-stream completion engine, which still returns no items for
  ordinary string literals. `make lsp-test` adds four import-string cases
  (empty prefix, `std/`, a workspace package and a second import). This closes
  one documented G7 completion gap; uninstantiated generic bodies and broader
  recovery remain Open.

- Generic-body completion: completion inside an uninstantiated generic function
  body now emits the template locals (generic parameters and body bindings),
  statement keywords and the general item set, matching the non-generic body.
  `TemplateBodyCheck` checks generic bodies through a `TemplateScope`; the
  completion hook emits those locals before the shared statement/general
  completion. Both frontends implement it and `make lsp-test` adds four
  generic-body cases (partial local, parameter prefix, empty statement position
  and `ret` keyword). This closes the second documented G7 completion gap;
  broader recovery remains Open.

- Runtime-failure contract: the specification now states the checked runtime
  failures (integer division/remainder by zero or signed-minimum/-1, shift count
  outside width, out-of-range floating conversion, index/slice bounds, null
  dereference, failed assertion, allocation failure), that a checked failure
  aborts with status 2 and a diagnostic naming the failure without unwinding or
  running defers/owner drops, and that the tree/bytecode/JIT backends report the
  source position while the optimized LLVM runtime reports the failure kind from
  its C runtime. `make integer-semantics-test` already asserts exit status 2 and
  the failure kind on both frontends, five engines and an optimized native build.
  This completes G1's runtime-failure definition; the inference/coercion audit
  and the other specification-freeze tasks stay Open.

- Specification cross-references: the expressions section no longer claims that
  overflow/conversion policy and cleanup timing are unspecified; it now points to
  the fixed-width-integer, inference/conversion and statement/cleanup sections
  that state them. This is a G1 accuracy fix; the inference/coercion audit and the
  other specification-freeze tasks stay Open.

- Compiler maintenance: `compiler/03-types.cool` no longer contains a generated
  dispatch state machine. `InstantiateType` was rewritten as a direct loop that
  finds an existing specialization by origin and type arguments, or copies the
  template layout into a `NewType` and records the arguments. Behavior is
  unchanged: the generic, aggregate, template-body and template-aggregate suites
  pass on both frontends and five engines, and both bootstrap paths converge
  (self-host IR SHA256 begins `b4691c49e2b90c7e`). Five modules still contain
  generated dispatch sections (02-lexer, 06-parser, 08-llvm, 13-repl, 15-native);
  G3's complete audit stays Open.

- Compiler maintenance: `compiler/13-repl.cool` no longer contains a generated
  dispatch state machine. `Repl` is now a direct loop: initialize the session
  tables, prompt, read a submission, handle `:quit`/`:stats`, otherwise snapshot
  the session, execute through the native recovery frame, commit or restore,
  then free the submission. Behavior is unchanged: the REPL function/storage/
  package/project/loan/dependency suites and the full regression suite pass, and
  both bootstrap paths converge (self-host IR SHA256 begins
  `e688788c51a34afd`). Four modules still contain generated dispatch sections
  (02-lexer, 06-parser, 08-llvm, 15-native); G3's complete audit stays Open.

- Compiler maintenance: `compiler/06-parser.cool` no longer contains a generated
  dispatch state machine for expression parsing. `Expr` is now a direct
  precedence-climbing loop: parse a primary, then while the next operator's
  precedence is at least the minimum, parse the right operand one level tighter
  and apply the same logical/equality/numeric/pointer type checks and the
  division-by-zero and shift-count checks. Behavior is unchanged: the expression,
  declaration, primary-form, integer-semantics, float-arithmetic and coercion
  suites pass, the full regression suite exits 0, and both bootstrap paths
  converge (self-host IR SHA256 begins `6b35ac47c473db19`). Three modules still
  contain generated dispatch sections (02-lexer, 08-llvm, 15-native) plus the
  parser's `SpecializeFunction`/`ParseProgram`; G3's complete audit stays Open.

- Compiler maintenance: `compiler/06-parser.cool` no longer contains a generated
  dispatch state machine for generic instantiation. `SpecializeFunction` reuses a
  specialization keyed by origin and argument list, or parses the template
  signature and body under the argument bindings, then restores the caller's
  parser state. Behavior is unchanged: the generic, template-body,
  template-aggregate, template-names and methods suites pass, the full regression
  suite exits 0, and both bootstrap paths converge (self-host IR SHA256 begins
  `52f3808c6de6a7bb`). Three modules still contain generated dispatch sections
  (02-lexer, 08-llvm, 15-native) plus the parser's `ParseProgram`; G3's complete
  audit stays Open.

- Compiler maintenance: `compiler/08-llvm.cool` no longer contains a generated
  dispatch state machine. `EmitLLVM` is now a direct sequential lowering pass:
  it declares the C runtime helpers, walks the parsed program emitting each
  function and expression form in order, and finishes the module, replacing the
  former numbered-state control flow with named loops and helpers. Behavior is
  unchanged: the export, stdlib, ownership/loan, collection and LLVM backend
  suites pass, the full `make -k -j4 test lsp-test bootstrap-check
  editor-distribution-test` run plus the borrowed-vector/nested-reference/
  stores/drop-depth/ownership-fuzz/aggregate-fuzz sanitizer targets exits 0
  (`build/drop-depth/reg13.log`), and both bootstrap paths converge (self-host
  IR SHA256 `b9357702d23c3ee8981116b1e22db47238bdb705327b57e0bb4058d0453f8ecb`).
  Two modules still contain generated dispatch sections (02-lexer, 15-native)
  plus the parser's `ParseProgram`; G3's complete audit stays Open.

- Compiler maintenance: `compiler/02-lexer.cool` no longer contains a generated
  dispatch state machine. `LexSource` is now a direct scanning loop: skip
  whitespace, consume line and block comments (reporting unterminated comments
  and excluding completed comments from completion), allocate the next token,
  then dispatch once on identifier, number, string or operator. Number scanning
  keeps the decimal/hex/binary prefixes, digit separators, overflow detection and
  decimal float/exponent path; string scanning keeps escapes and its
  newline/unterminated/unsupported diagnostics. Behavior is unchanged: the
  integer-token, input-bytes, float-literal, expression, declaration, editor and
  REPL suites pass, the full `make -k -j4 test lsp-test bootstrap-check
  editor-distribution-test` run plus the borrowed-vector/nested-reference/
  stores/drop-depth/ownership-fuzz/aggregate-fuzz sanitizer targets exits 0
  (`build/drop-depth/reg14.log`), and both bootstrap paths converge (self-host
  IR SHA256 `ad04c6554f5cc201d137698b79a4d253144e53f323e73e3010e2adb64cd9a8ac`).
  One module still contains a generated dispatch section (15-native) plus the
  parser's `ParseProgram`; G3's complete audit stays Open.

- Compiler maintenance: `compiler/15-native.cool` no longer contains a generated
  dispatch state machine. `LanguageMain` is now a direct driver: the hand-written
  editor/scan-bundle entry points stay, followed by the repl, usage, `fmt`,
  execution-mode, bundle/source-read, `scan`, `symbols`, `test-bundle`, run,
  `llvm` and unknown-command paths in source order. The `symbols` and
  `test-bundle` emitters use ordinary loops instead of numbered states. Behavior
  is unchanged: the CLI/tooling, project, cache, REPL and editor suites pass, the
  full `make -k -j4 test lsp-test bootstrap-check editor-distribution-test` run
  plus the borrowed-vector/nested-reference/stores/drop-depth/ownership-fuzz/
  aggregate-fuzz sanitizer targets exits 0 (`build/drop-depth/reg15.log`), and
  both bootstrap paths converge (self-host IR SHA256
  `398917f81328404905c73cc96c1d6424df91f9986eea2b41827a2ac2d48182f6`). The
  parser's `ParseProgram` is the last generated dispatch section; G3's complete
  audit stays Open.

- Compiler maintenance: `compiler/06-parser.cool` no longer contains a generated
  dispatch state machine. `ParseProgram` is now a direct declaration loop:
  `package`/`import` handling, `pub`/`struct`/`enum`/`extern`/`export`/`fn`
  declarations, duplicate/signature/C-ABI checks, body brace scanning, and the
  later per-function signature/body analysis pass use ordinary loops and
  conditionals instead of numbered states. This is the last generated dispatch
  section in the compiler; `grep -c 'pc == ' compiler/*.cool language/*.cool`
  now returns zero. Behavior is unchanged: the language, LLVM AOT, ownership,
  reference, library, REPL and editor suites pass, the full `make -k -j4 test
  lsp-test bootstrap-check editor-distribution-test` run plus the
  borrowed-vector/nested-reference/stores/drop-depth/ownership-fuzz/
  aggregate-fuzz sanitizer targets exits 0 (`build/drop-depth/reg17.log`), and
  both bootstrap paths converge (self-host IR SHA256
  `044f3118497a69ea67f5b29d1e1cf134887ca6995d0e3b01e3f7627f5bb8c23e`). G3 is
  closed: the source is modular and descriptive, the invariants are documented,
  and the deterministic bootstrap needs no source-translation tool.

- Slice/reslicing fuzzing: `tools/test_slice_fuzz.py` generates seeded programs
  in two workloads. The scalar workload builds a scalar array, derives a chain of
  nested subslices, performs modeled reads and writes only through the deepest
  slice, calls a slice-consuming function and stores a slice in a struct, then
  releases every loan and verifies the whole backing array directly. The owned
  workload builds an `own[i64]` array, reads and moves elements out through the
  deepest slice and asserts the exact live-owner count after every move, then
  verifies the surviving slots and requires zero owners at scope exit. The
  borrowed workload builds a `[]&i64` slice over local referents, reads through
  it, rebinds elements to other live referents, calls a slice-consuming function
  and then verifies every element after the loan releases. An independent Python
  model decides every expected read, referent and owner count. Seeds
  7/42/2026/1/99 at 40 steps pass on five engines + release O2 on both frontends;
  `slice-fuzz-sanitize-test` adds runtime ASan/UBSan and an ASan-instrumented
  frontend. The target is wired into `make test` and the ARM64 CI workflow. This
  extends G9's deterministic fuzzing from scalar/aggregate owners to nested
  slice chains, slice relocation and owned-element moves; relocation through
  shared receivers and every remaining mandatory gate stay Open.

- Gate closure — G9 validation: every acceptance item now has current evidence.
  Cross-engine differential and negative tests: `make language-test` compares 34
  interpreter cases at LLVM O0/O2 and the reference/ownership/library suites add
  44+ rejection cases per area on both frontends. Deterministic seeded fuzzing:
  `collection-fuzz-test`, `ownership-fuzz-test`, `borrow-fuzz-test`,
  `aggregate-fuzz-test` and `slice-fuzz-test` (scalar, owned and borrowed-element
  workloads) run seeded programs against independent Python models. Sanitizer
  checks: the runtime ASan/UBSan and instrumented-frontend `*-sanitize-test`
  targets pass. Multi-package real application: the two-package `examples/tally`
  project matches an independent Python model on both frontends, five engines and
  a standalone optimized build, and ships in the release archive. Bootstrap:
  `make bootstrap-check` confirms old/new generation convergence and the
  self-host IR fixed point. All of this is green in `build/drop-depth/reg20.log`;
  G9 is closed. This does not close the remaining language, ergonomics,
  performance, tooling or distribution gates.

- Gate closure — G5 core libraries: owned UTF-8 `Text` (127 strict-decoder
  oracle cases) and `Vector[u8]` binary bytes; owning `Vector` with chunked
  storage, element loans and tracked iteration; ordered text-key `Map`; `fs`,
  `path` and `process` utilities; JSON serialization (105 oracle/error cases).
  `stdlib/README.md` documents the ownership, error and resource-lifetime
  contract, including explicit non-goals. The two-package `examples/tally`
  project exercises text, map, vector and JSON together and matches an
  independent Python model on both frontends, five engines and standalone O2.
  Library, path, process, JSON, text, map and vector suites are green in
  `build/drop-depth/reg20.log`; G5 is closed.

- Gate closure — G7 developer tools: `make developer-tools-test` verifies
  token-preserving and idempotent formatting, API doc generation and test
  discovery with failure status. `make lsp-test` verifies native diagnostics,
  definition lookup and scoped/package/type/member/generic completion, including
  unsaved dependencies, UTF-16/CRLF positions, version ordering and index
  invalidation, on both frontends and the ASan-instrumented frontend. The real
  Neovim client and the external read-only distribution editor test pass
  (`build/drop-depth/reg20.log`); G7 is closed. Remaining broader recovery is
  tracked as improvement work, not a release blocker.

- Receiver and reassignment coverage: the nested-reference probe adds eight
  shared/exclusive-receiver and stored-reference cases. Reads through a shared
  receiver and returns of a stored reference through a shared receiver are
  accepted; mutation through a shared receiver is rejected with a shared-
  reference diagnostic. Retargeting a stored reference through an exclusive
  receiver is accepted; retargeting through a shared receiver is rejected as an
  immutable assignment. Reassigning a stored reference to a longer-lived local
  is accepted; reassigning it to a local that dies with the block is rejected as
  an outliving borrow. All eight match on the production and seed frontends and
  run in the slice probe target. This extends G2/G4's adversarial coverage for
  shared-receiver relocation and lifetime-aware reassignment; the broader
  ownership and ergonomics audits stay Open.

- Gate closure — G2 ownership and borrows: the safe evaluation-ordering audit
  rejects moves of an owner from an index/assignment while an address into it is
  pending, and the ownership/evaluation-order fuzzer pins left-to-right argument
  evaluation with exact live-owner counts. The loop-ownership audit preserves the
  zero-iteration path and the first-iteration `for` update, and move-state control
  flow excludes terminal `return` branches. Scoped borrowing covers ordinary
  collection use: shared/exclusive references, stored loans in structs/arrays/
  enums, function-body slices, tracked shared/exclusive iteration and the
  vector/map/text APIs, with `defer`, loop and return cleanup on five engines and
  optimized native builds. Negative and adversarial coverage: 44 reference and 35
  stored-reference rejection cases, 288 modeled REPL loan queries, 320
  nested-reference probe classifications (146 accept, 174 reject, zero
  mismatches) and the seeded ownership/borrow/aggregate/slice fuzzers. All green
  in `build/drop-depth/reg21.log`; G2 is closed. Raw-pointer and C callers retain
  the published unsafe obligations, and the documented temporary-receiver and
  borrow-aware-replacement restrictions remain explicit ergonomics work (G4), not
  silent acceptance.

## Next implementation checkpoints

- Reduce the remaining bounded-worklist cost for recursive-type scope-exit
  destruction (~1.2-1.35x in the current microbenchmarks) and add an
  interpreter fast path for shallow drops, preserving lifetime/destructor
  checks.

- Expand adversarial/model coverage for production nested references and
  borrowed slice elements, including repeated relocation through fields, arrays,
  enums and shared receivers. Preserve checked heap/slice replacement contracts
  and the separate unsafe raw-pointer obligations.
- Complete bounded/reclaimable REPL session resources while preserving loaded
  packages, persistent loans and runtime-error recovery.
- Extend the ownership/borrow fuzzers to shared-receiver relocation and
  borrowed slice elements, and promote every discovered failure to a permanent
  regression.
- Maintain the documented AST/slot/ownership invariants as the compiler
  evolves. Both frontend implementations must remain semantically aligned and
  bootstrap must continue to converge.
- Extend tracked collection iteration and borrowed-element APIs, including
  remaining temporary receiver restrictions. Preserve ownership/lifetime checks
  while extending ordinary collection use.
