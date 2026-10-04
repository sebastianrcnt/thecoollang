# Compiler architecture and maintenance invariants

This describes the implementation, not a frozen 1.0 language/ABI specification.
The release contract remains [open](release-1.0.md). Production compiler source
is `compiler/*.cool`, written in the same new syntax accepted for user programs.
The compact `language/*.cool` frontend is maintained as a bootstrap and a second
semantic implementation. Neither directory is generated from the other.

## Build and host boundary

`tools/compiler_sources.py` writes a sorted `package<TAB>absolute-path` manifest;
it does not parse Cool. `tools/cool` and `tools/modules.py` resolve packages,
manage caches and invoke tools. Parsing, typing, ownership/borrow analysis,
interpretation and code generation belong in Cool.

`compiler/host.c` supplies allocation, file/console access, numeric/C ABI
adapters, executable pages and the C recovery frame. `language/runtime.c` is the
runtime linked to generated native user programs. The host adapter is not a C
implementation of the frontend. libffi implements dynamic foreign calls; it
does not define language type checking. Numeric and memory adapters are shared
through `language/numeric.h`, `language/memory.h` and `language/ffi.h`.

The normal `make build/cool-compiler` dependency chain is:

1. The preserved legacy seed builds `build/language.BIN` from `language/*.cool`.
2. That bootstrap frontend compiles all new-syntax `compiler/*.cool` to
   `compiler-stage1.ll`; clang links stage 1 with the host/runtime adapters.
3. Stage 1 recompiles the same source to `compiler-stage2.ll`; clang links
   `build/cool-compiler`.

`make selfhost-check` copies the final compiler outside the checkout, disables
the seed path, produces stage 3, and requires stage 1/2/3 LLVM IR equality plus
stage 2/3 native binary equality. It also executes a program using the copied
compiler's tree, VM and JIT engines. Equal native binaries use the same basename
(`cool-compiler`) to avoid macOS signing metadata differences. The separate
`make bootstrap-check` checks the older seed compiler's generation 2/3 fixed
point. Neither test overwrites the checked-in seed. A fixed point proves
bootstrap consistency, not correctness of every language feature.

Do not restore an obsolete migration script to regenerate production source.
A semantic change shared by the two frontends needs an intentional edit and
regression coverage on both. A production-only structural refactor can leave
the bootstrap representation intact if both remain behaviorally equivalent.

## Source map

The modules currently share one `__main` package. Numbered filenames make source
order deterministic; they are not independently linked compiler libraries.

| Production source | Responsibility | Bootstrap counterpart |
| --- | --- | --- |
| `00-state.cool`, `main.cool` | Shared structures, compiler context and entrypoint | `Core.cool`, `Native.cool` |
| `01-core.cool` | Tokens/nodes/locals, scalar types and coercion | `Core.cool` |
| `02-lexer.cool` | Source tokenization and locations | `Lexer.cool` |
| `03-types.cool` | Aggregate layouts, generics, type collection | `Types.cool` |
| `04-borrow.cool` | Return-region propagation and escape contracts | `Borrow.cool` |
| `05-ownership.cool` | Explicit transfers, moved-state joins and drop injection | `Ownership.cool` |
| `06-parser.cool` | Expressions/statements/declarations and specialization | `Parser.cool` |
| `07-interpreter.cool` | Typed AST evaluation, frames and value operations | `Interpreter.cool` |
| `08-llvm.cool` | LLVM lowering and native entrypoint | `LLVM.cool` |
| `09-foreignllvm.cool` | C imports/exports and scalar ABI conversion | `ForeignLLVM.cool` |
| `10-ownershipllvm.cool` | Native ownership helpers and recursive destruction | `OwnershipLLVM.cool` |
| `11-bytecode.cool` | Typed bytecode generation and execution | `Bytecode.cool` |
| `12-jit.cool` | ARM64 machine-code lowering and dispatch | `JIT.cool` |
| `13-repl.cool` | Persistent submissions, replacement and recovery | `Repl.cool` |
| `14-format.cool` | Token-based formatting | `Format.cool` |
| `15-native.cool` | Frontend CLI, bundles, metadata and tools | `Native.cool` |
| `16-references.cool` | Scoped loans and unsafe storage bridges | `References.cool` |
| `17-calls.cool` | Named expressions, builtins and function-call resolution | `Parser.cool: Atom` |
| `18-methods.cool` | Nominal method declaration, receiver adaptation and call lowering | `Methods.cool` |

Much of the initial port still has explicit temporary variables and program
counter loops. New modules and edited sections should use direct control flow
and descriptive names. Do not combine a large structural rewrite with an
unrelated semantic change: keeping the differential test meaningful matters.

## Type identity, layout and storage

Type IDs are shared implementation tags, not serialized public identifiers.
The bootstrap names live in `language/Core.cool`; production lowering currently
uses the same numeric tags. Updating a tag requires auditing every consumer,
including the C numeric/FFI boundary and bytecode/runtime helpers.

| Representation | Meaning |
| --- | --- |
| 0–13 | `void`, `i64`, `bool`, `string`, `i32`, `u8`, `i8`, `i16`, `u16`, `u32`, `u64`/`usize`, `f64`, `f32`, null literal |
| 1000 + aggregate index | Nominal or structural aggregate descriptor |
| 100000 + pointee type | Raw pointer; repeated addition represents pointer depth |
| Aggregate kinds 1–6 | Struct, array, slice, enum, owner, scoped reference |

Arrays/slices/owners/references are interned by `(kind, element, count)`;
reference `count` is 0 for shared and 1 for exclusive. Nominal structs/enums
are package-qualified; generic instances retain origin and concrete arguments.
A descriptor's layout state is 0 (uncomputed), 1 (in progress) or 2 (complete).
Seeing state 1 again rejects a by-value recursive aggregate. Owners/pointers can
break recursion because their layout does not recursively inline the pointee.

On the supported 64-bit host, owners/references occupy one 8-byte word and slices
two words (data, length). Arrays are contiguous element storage. Struct fields
are aligned in declaration order with final tail padding. Enums have an 8-byte
tag and payload at offset 8, sized for the largest variant and aligned to 8.
An empty struct can have byte size zero. `TypeSlots` still reserves at least one
8-byte frame slot; otherwise it rounds byte size up to whole slots.

Do not equate frame slots with byte offsets: `Local.slot` and `Node.storage` are
8-byte slot indices; aggregate `Field.offset`/projection offsets are byte
positions. Runtime scalar memory reads/writes use the actual scalar width.
Tree/VM scalar floats use a double-bit carrier, with explicit f32 normalization;
LLVM storage/foreign calls must perform the equivalent f32/f64 conversions.

Current hard limits include 4096 types/functions, 8 generic parameters, 32
function arguments, 65536 array elements, 512 KiB per aggregate and 65536 local
storage slots per function. These are implementation limits, not evidence of
bounded allocation in long REPL sessions.

## Typed AST and pass ordering

`Node.kind` selects an interpretation of the remaining fields. It is not valid
to read every field generically as an expression edge. `a/b/c` are kind-specific
children; `next` links argument, initializer or statement lists. `token` carries
source identity/location. `local_ref` ties reads/places back to lexical locals;
`origin_source` preserves provenance through projection and borrow creation.

Relevant kinds are declared in `language/Core.cool`: locals/calls are 3/4,
bind/assign/return are 7/8/9, load/store are 18/19, local/field/index addresses are
22/24/25, aggregate construction is 23, slice/length are 26/27, and new/move/owner
address are 28/29/30. A reference literal also uses 23, and reference dereference
uses 30; type and `op` discriminate those cases. `borrow_raw` uses construction
`op=1`; reference-to-pointer conversion uses address `op=1`. Never assume kind
30 always means an owning allocation.

Named expressions resolve a file-local import alias before looking up package
members. Once qualified, a member must not fall back to a same-named local.
Generic type arguments are explicit. Calls keep arguments in source order,
record arity in `value`, specialize their function, coerce each argument and
validate ownership transfer before code generation. Nonnegative `slot` is a
stable function ID. Negative builtin slots are:

| Slot | Operation |
| --- | --- |
| -1 / -2 | print or println / assert |
| -3 / -4 / -5 | raw allocation / free / copy |
| -6 / -7 | owner count / compiler-injected drop |

Methods use package-qualified `Type.member` function names. Their first
parameter is explicit; receiver generic arguments precede extra call-site type
arguments. The parser inserts the receiver as the first ordinary call argument,
using `ReferenceForPlace` for auto-borrows. Field indexing must not be mistaken
for generic method syntax: lookahead requires a call after closing brackets.
Declaration/template/signature checks reject foreign owners, C ABI methods,
receiver mismatches and field/variant collisions. Backends do not get a separate
method opcode.

A function body is parsed and typed before `AnalyzeBorrows`, then
`AnalyzeReferences`, then `InjectDrops`. Return-path validation follows.
Generic specializations must run the same checks as ordinary functions. Do not
bypass these checks in a new execution backend or tool mode that accepts code.

## Ownership, loans and evaluation

Owning values require explicit transfer unless the expression is a fresh call,
new allocation, aggregate construction or already an explicit move. Runtime
transfer drops the previous destination, copies the representation and zeros
the source. Self-transfer is a no-op. Zero owner slots are empty and safe to
drop; dereferencing an empty/moved owner traps. Aggregate destruction visits
owning fields/array elements and only the active enum payload.

Lexical owner bindings insert a deferred drop at their scope. Function-level
registered drops also cover owning temporaries and recovery cleanup. Repeated
drops are safe because transferred/dropped owner words are zero. Return values
must be transferred to the destination before cleanup can destroy their source.
Explicit deferred calls capture evaluated arguments and run in reverse order
when their scope is exited, including return/break/continue paths.

Moved-state joins include every continuing control-flow path. Returning branches
are excluded, but a loop must include the zero-iteration path. For-post parsing
must not make body parsing assume a move/reinitialization has already happened.
Moving an outer owner inside a loop is currently rejected. Pending projection
addresses cannot outlive a move during index or assignment-RHS evaluation;
`CheckLivePlace` and reference address analysis protect that boundary.

Borrow regions propagate parameter bits plus a frame bit through source edges.
A returned borrow must be a subset of the declared `borrows(...)` contract.
Scoped references additionally maintain loans with root, holder, reborrow parent
and exclusivity, plus an `indirect` layer and the AST expression that produced
the loan. A binding may
hold several root/parent records. Direct and nested reference-returning calls
keep the union of all declared source arguments, deduplicating equivalent
records rather than guessing a single root from syntax. Parent ancestry must
be resolved for the specific root being checked.
Argument loans remain active while later arguments are evaluated. Temporary
loans normally end at the statement; named/deferred loans remain through scope.
A child loan can restrict its parent until that child's scope ends. Binding a
reference retains only the resulting expression's loans; index-computation
temporaries expire at that statement. Reborrowing a computed reference transforms
its temporary result loans after address evaluation, preserving the root set
and preventing an exclusive upgrade from a shared source.

Reference-containing aggregate values use the same provenance sets. Literal
members relabel their result loans to the container expression; copies and
projections retain the entire set. Anonymous match storage receives a Local in
`all_locals` (not the name lookup chain), so payloads reborrow an already
evaluated scrutinee rather than analyzing its calls again. Borrow-region edges
include this binding. Empty enum results may have no loans and `borrows()`.
Reference-containing arrays/structs cannot be zero initialized or reassigned.

The checker currently treats an entire root as conflicting, not individual
fields. Layer zero is the addressed storage of a reference, or the contained
reference roots of a by-value aggregate. Layer one retains the payload
referents of a reference to borrowed storage. Taking a container address adds a
physical local root at layer zero and retains payloads at layer one. A shared
outer borrow downgrades payloads; an exclusive outer borrow preserves each
source mode. `ReferenceMode` computes the capability a typed copy requires,
never an instruction to promote every source. Reborrows/calls intersect the
requested mode with each source's existing mode. Read-only lifetime anchors
are not treated as writable roots when accessing an exclusive result. Access
through a stored reference selects the payload layer; scalar field
access and receiver mutation select the physical layer. Named/temporary payload
loads flatten selected payload loans back to layer zero, leaving evaluation
loans temporary until the statement ends. Source acquisition checks conflicts
against the pre-acquisition list as well as the physical place.
Nested-reference returns preserve nested argument layers; other anchors are
conservative in both layers. Ordinary borrowed returns combine selected roots.
This avoids inventing an exclusive source-vector loan when mutating an iterator,
while keeping physical receiver aliases and all referent invalidations checked.
Aggregates mixing scoped references with owner/slice fields, arbitrary nested
stored reference lifetimes, references to slice descriptors and persistent REPL
loans remain unsupported. Do not remove
their rejections merely because a happy-path example works. Unsafe `borrow_raw` anchors
provide lifetime provenance but cannot prove arbitrary pointer validity or
storage association. See [the reference contract](references.md).

Address analysis distinguishes reads from writes when loading a stored
reference, so a shared receiver may read an exclusive reference's pointee
without extracting exclusive access. Computed projections propagate the
requested permission through intermediate aggregate loads and reject exclusive
extraction from a shared receiver before deriving the result loans.
Temporary result loans are exempt only
for the exact reference expression currently being dereferenced. Owner-pointer
projections retain a shared pending-access pin (or reuse an existing evaluated
reference loan) before later indices/RHS expressions execute. This prevents
moving/replacing an owner through another use of the same reference while a
pointee address is pending. Plain loads release address-evaluation loans after
access; owner loads keep them for surrounding projections. Never exempt another
argument or a merely similar expression from these pins.

Slice values participate through `TrackedBorrow`, while `ContainsReference`
continues to enforce reference-specific storage and reassignment restrictions.
Slices request exclusive mode; constructing an array view acquires its source
before evaluating bounds. Slice index addresses observe a named descriptor
without creating a spurious exclusive copy, and element references reborrow
its source loans. Slice call results, projections, aggregates and owned moves
retain the same source sets. `len` of a named slice reads only its descriptor.

Each tracked binding has a rootless lifetime marker. Markers are not source
loans and acquisition must skip them. Slice reassignment inserts retained source
loans below the destination's marker, so an inner block's ordinary temporary
release cannot free them prematurely. Sources accumulate conservatively across
branches and loops; deeper local roots cannot escape into an outer binding.
Reassignment through a descendant normalizes ancestry to the destination's
previous parent, preventing self-reslicing cycles. Original loans are not
removed during this analysis, which keeps saved list boundaries stable.

## Backends, replacement and recovery

Tree evaluation is the executable semantic baseline. The bytecode compiler
preserves evaluation order, checked operations, aggregate destinations and
scope cleanup; `Instruction.node` retains type/source context. Bytecode registers
include local storage slots plus expression temporaries. The ARM64 JIT lowers
bytecode and shares checked/runtime operations rather than inventing another
type system. Adaptive execution compiles a function to native code after four
calls. LLVM AOT/JIT must agree on errors and values even where it uses different
runtime helpers.

REPL function IDs remain stable so callers observe body replacement. Unsupported
signature/generic changes require a new session. Compilation-product pointers
are invalidated on replacement; that does **not** currently prove old AST,
bytecode or JIT-page memory is fully reclaimed. This is an open release gate.

`NativeRecover` keeps `setjmp` in a live C frame while calling `CoolSubmission`;
`NativeRaise` can only jump to that active frame. Never move `setjmp` into a
wrapper that returns before executing the submission. Runtime-error rollback
cleans active frames/new owned values and restores metadata; it does not undo
external effects or arbitrary writes already performed by executed code.

## Evidence required for changes

Use a focused regression that would fail before a semantic fix, then the
relevant existing suites. Parser/type/call/ownership refactors justify the full
`make test`; `make selfhost-check` checks the new compiler fixed point, and
`make bootstrap-check` checks the seed path. Keep rejected programs in the
negative suites and test both frontend implementations where applicable.

For raw-storage libraries, compare to an independent model and check owner/raw
resource accounting where applicable. `*-sanitize-test` targets instrument
LLVM definitions with `sanitize_address` and verify that the sanitizer pass
actually emitted memory checks. Merely passing `-fsanitize=address` while
linking arbitrary LLVM IR is insufficient. UBSan on the C runtime does not prove
Cool language arithmetic semantics. Large compiler changes still require the
cross-engine, C ABI, package/tooling and bootstrap tests, not only library tests.
