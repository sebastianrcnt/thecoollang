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
| G2: ownership and borrows | Audit safe evaluation ordering, move/branch/loop/defer rules; scoped safe borrowing for ordinary collection use; negative and adversarial tests across engines | Open |
| G3: maintainable compiler | Modular new-syntax source, documented compiler invariants, deterministic bootstrap with no migration-tool dependency | Open (self-hosting already verified) |
| G4: language ergonomics | Methods and a coherent borrowing/collection API; useful source diagnostics; no silently accepted unsupported semantics | Open |
| G5: core libraries | Owned text/bytes, vector, map, file/path/process utilities, useful serialization; documented errors and resource lifetimes; realistic projects | Open (text, vector, ordered map and JSON validated) |
| G6: incremental development | Predictable function replacement and invalidation, external package use in REPL, bounded/reclaimable session resources, explicit unsupported redefinitions | Open (persistent state and transactional reclamation verified; final lifetime audit pending) |
| G7: developer tools | Formatter/test/doc integration; LSP diagnostics, definition lookup and completion; editor/protocol tests | Open (native tooling and real Neovim client verified; broader recovery/unsupported contexts pending) |
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

## Next implementation checkpoints

- Extend reference-containing owned/nested storage and references to slice
  descriptors; keep unsafe raw pointers separate and add rejection regressions
  before removing restrictions.
- Complete bounded/reclaimable REPL session resources while preserving loaded
  packages, persistent loans and runtime-error recovery.
- Add adversarial/deterministic fuzz cases for evaluation order, ownership and
  borrowed storage. Promote every discovered failure to a permanent regression.
- Maintain the documented AST/slot/ownership invariants while simplifying
  remaining port-generated compiler sections. Both frontend implementations
  must remain semantically aligned and bootstrap must continue to converge.
- Complete stored loans and tracked iteration, including the remaining
  temporary receiver restrictions. Preserve existing ownership checks while
  extending ordinary collection use.
