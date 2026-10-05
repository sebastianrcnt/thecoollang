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
| `19-repl-loans.cool` | Persistent loan transactions, recovery filtering and explicit binding release | `ReplLoans.cool` |
| `20-repl-packages.cool` | Import discovery, immutable package staging and rollback | `ReplPackages.cool` |
| `21-bytecode-memory.cool` | Compilation-owned argument/scope allocation lists and disposal | `Bytecode.cool` |
| `22-repl-nodes.cool` | Disposable submission node allocation and cleanup | `Core.cool`, `Repl.cool` |
| `23-repl-locals.cool` | Session-local allocation registry and loan-rooted reclamation | `Core.cool`, `References.cool`, `Repl.cool` |
| `24-repl-tokens.cool` | Statement token disposal and session literal interning | `Core.cool`, `Repl.cool` |
| `25-repl-functions.cool` | Transactional disposal of replaced/rejected function artifacts | `ReplFunctions.cool` |
| `26-repl-source.cool` | Live declaration source marking, disposal and token relocation | `ReplSource.cool` |
| `27-repl-scratch.cool` | Input-lifetime parser/resolver allocations across nonlocal recovery | `ReplScratch.cool` |
| `28-repl-types.cool` | Lazy-layout journal, field rollback and staged immutable text | `ReplTypes.cool` |
| `29-editor.cool` | Native JSON diagnostics and semantic reference index | `Editor.cool` |
| `31-template-syntax.cool` | Generic signature/name/type syntax preflight | `Parser.cool` |
| `32-template-body.cool` | Unspecialized function body grammar and lexical scopes | `TemplateBody.cool` |
| `33-implicit-types.cool` | Implicit eligibility, binary selection and conversion application | `Core.cool` |
| `34-template-aggregate.cool` | Generic nominal member preflight | `TemplateAggregate.cool` |
| `30-completion.cool` | Cursor token preparation and parser-context completion | `Completion.cool` |

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
stored reference lifetimes and references to slice descriptors remain
unsupported. Do not remove
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

REPL checking clones the persistent loan list before analyzing a statement.
The clone preserves order, rootless lifetime markers and Local identities;
assignment may add roots below an old marker without mutating the saved list.
Compile failure frees the candidate. Success commits loans whose holders are
still visible. Runtime failure commits only loans held by previously visible
bindings because existing values may have changed before the trap; their root
union is conservative even for statements that did not execute. New failed
bindings cannot retain loans or hide original dependencies. Loan lists and
candidate check records are freed on replacement and exit.

`:forget` validates source/parent dependencies and syntax before any mutation.
It drops owning storage, removes the binding from name lookup, and frees its
held loans. `ReplTrimStorage` removes dead drop descriptors and reduces the
slot high-water mark to the maximum end of a visible binding; live bindings
never move. `ReserveStorage` reuses interior as well as trailing gaps while
protecting all visible bindings and current-input reservations. Never retain a
dead drop descriptor across reuse: its former owner type could interpret a new
scalar as an owned pointer. The focused heap/JIT audits complement broader
resource-policy acceptance.

`ReplDiscardNewDrops` traverses only records above the saved drop-list head.
Execution failure drops new initialized owners before restoring the old
function snapshot; compile failure frees descriptors without touching values
because the new slots were never initialized. Safe persistent references
require surviving tracked roots, so failed new local storage cannot escape
and does not need a permanent slot reservation. Unsafe pointers remain the
caller's lifetime responsibility. The synthetic function ID zero must never
be redefined or called by source in REPL mode; otherwise its slot/drop metadata
can be reset underneath live session values. This restriction does not apply
to ordinary compilation.

REPL imports use a private length-framed driver channel. The frontend recognizes
import tokens; the driver only reuses package graph resolution, metadata scans,
checksums and file snapshots. `ReplLoadImports` preserves an EOF separator after
the submitted declaration, appends imported source tokens, parses the new
packages, then restores the submission position and `__main` lexical namespace.
Never overwrite a package's first token with the submission separator: generic
bodies retain token indices. Original paths remain the alias/diagnostic file
identity, while file bytes come from immutable per-request snapshots.

Package fingerprints include length-framed filenames and contents. Already
loaded packages must match; newly staged records roll back with aliases,
function snapshots and aggregate counts after any import error. Several files
in a newly loaded package are all read, while a package loaded by an earlier
request is skipped. The driver may delete the previous request's snapshots
only after receiving the next request: the frontend has consumed them into
its own token storage by then. A malformed/closed channel reports an import
error rather than discarding existing session values or loan state.

Bytecode argument vectors and scope/defer records belong to a function's
`byte_allocations` list. `ByteAllocate` uses one allocation containing an aligned
list header followed by zeroed payload. Deferred calls may emit several
instructions sharing the same argument vector, so never free instruction `args`
independently. `FreeBytecode` walks the allocation list exactly once and clears
the instruction buffer and counts. It disposes completed/rejected submission
code and obsolete/staged function code after all user frames return or unwind.
Function zero is never JIT-compiled. Ordinary functions retain their current
caches; callers dispatch by stable function ID. Bytecode invocation argument values use native stack scratch with the
language's 32-argument bound; nonlocal runtime recovery cannot leak that vector.
Argument scratch contains borrowed value representations, never ownership of
the referenced aggregate storage.

All AST allocation and coercion clones go through `AllocateNode`. In REPL mode,
nodes created for synthetic function zero have an outer `ReplNode` allocation
link, separate from the copied Node payload. `ReplFreeNodes` runs after successful
submission execution or recovery, after bytecode disposal and move-state cleanup.
It first clears persistent loans' expression pointers: these identify expressions
only during checking, whereas Local identities, modes and ancestry persist. A
freed expression address must never match a later allocation. Generic specialization
switches `current_fun` before building its body. Nonzero functions own separate
node and local allocation lists, reclaimed when their artifacts are discarded.
Node cleanup does not free lexical strings or tokens; those have independent
lifetimes.

`AllocateLocal` tracks synthetic-session locals independently of the lexical
`next` chain and the snapshotted function `all_locals` head. Both named locals
and anonymous match holders use it, including allocations rejected before
`AddLocal` publishes a binding. After node and move-state disposal,
`ReplReclaimLocals` marks visible bindings and every surviving loan's root,
holder and parent, sweeps other session locals and rebuilds `all_locals` from
survivors. An out-of-scope parent can remain relevant after a slice assignment,
including an assignment executed before a runtime error; never infer liveness
only from name lookup. The independent registry survives snapshot restoration.
Marking and sweeping are linear in registered locals, visible bindings and loans.
Non-visible survivors have their obsolete lexical `next` cleared. Cached
function locals are outside this registry. Named session locals own separate
`StrNew` name copies, released with their Local records; they never own the
lexer's original identifier strings.

Before changing an existing lazy layout from state 0 to 1, `ReplSaveLayout`
journals its full descriptor. It records only touched preexisting types, avoiding
whole-table snapshots on every input. A failed submission restores these copies,
frees newly built field lists and clears newly allocated descriptors before their
IDs can be reused. Field lists belong to their nominal descriptor; generic
templates have no computed fields to share with an instance. Runtime frames and
new owned values must be dropped before restoring layouts, because destruction
still needs the just-computed type information. Commit releases journal records
without releasing the completed fields. Restoring only `naggregates` is incorrect:
a previously retained lazy instance can otherwise remain in state 1, or in state
2 with field type IDs that now refer to unrelated descriptors.

Parser move snapshots, temporary type bindings and match coverage arrays use
`ScratchAllocate`. In REPL mode an independent `CompilerScratch` list tracks
allocations even when parser locals disappear through nonlocal recovery.
`ScratchRelease` defers reclamation until input completion; outside REPL mode
it frees its argument normally. `ScratchOwn` enrolls externally allocated
manifest/file buffers and field substrings, each registered exactly once. Only
explicitly temporary objects
belong here: never enroll ASTs, Local identities, alias records or type fields.

`ReplFreeScratch` runs after frame unwinding, move restoration and loan recovery,
before function/local/source reclamation. It frees the complete list and clears
`repl_moves` and temporary type bindings. Do not separately free the top-level
move snapshot: it belongs to the same pool as nested parser snapshots.
Package identity and original diagnostic paths are interned before the resolver
scratch disappears; package fingerprints are separately owned and freed on
package rollback. New alias records are also freed when restoring the saved
alias head; their strings belong to token storage. Token package/file pointers
must never refer to scratch fields.
The native resolver response is a host-owned static buffer and is not enrolled.
`ErrorAt` frees its formatted message after the synchronous write and before
nonlocal recovery/exit. Session statistics similarly free their formatted text.

REPL statements and commands reuse the token-table tail after the last retained
declaration. `ReplFinishTokens` runs after nodes and locals are reconciled and
frees each discarded token's text/raw buffers. Synthetic semicolons copy source
coordinates but must clear text/raw pointers to avoid duplicate ownership.
Recovery records the pre-restore token end before resetting `ntok`; otherwise
partial lexing and rejected declarations would lose their allocation range.
Successful declarations/imports retain tokens for cached bodies and later
generic specialization. A token-table limit reports a recoverable diagnostic.

Type descriptors own an inline copy of diagnostic coordinates, with text/raw
cleared, so structural types can outlive their statement tokens. Session-local
names are copied as described above. `LiteralString` interns all REPL literals and declared function symbols
by bytes into stable session storage; lexical buffers can be discarded even if
a string value escaped from a function into owning storage or foreign code.
Function symbols also survive their declaration token storage. Equal literals may
share storage and literals remain immutable. New entries also enter an input-local
LIFO list with their bucket index. Checking failures remove only these new entries
in reverse insertion order, after function/type/local/token rollback. Existing
entries are never removed. Once execution begins, keep the new entries even on
runtime failure: prior writes or foreign code may retain their addresses. Startup
imports commit their entries before the first user transaction. Accepted distinct
literal contents persist until session exit; this pool is not a claim of bounded memory for an unbounded
set of new literals. Lexer string-construction headers are freed on success and
unfinished string buffers on recovery; numeric parsing substrings are temporary.
Method lookup compares package, owner and member directly against declared
symbols, skipping generic specializations like ordinary function lookup. It must
not allocate/intern a name for each call or failed lookup. Method call nodes use
the canonical declared symbol. Declaration-time composed-name buffers and
method-owner lookup substrings are temporary and freed. Outside REPL mode,
function declarations retain their composed-name data for compiler lifetime.
After a successful declaration, `ReplReclaimSource` records its token span and
marks source blocks referenced by live functions and every retained AST token.
Blocks introducing aliases or nominal types are pinned: their token strings,
field names and lazy generic bodies remain source-backed. The startup import
block is pinned too. A mixed declaration block stays live as a whole while any
of these roots survives. Rejected submissions never publish a source block.

After superseded function artifacts and statement nodes have been disposed,
source cleanup maps each old token index to its compacted index. It relocates
function signature/body indices and token pointers, every function node's token
pointer, and nominal type body indices. Inline type diagnostics remain independent
of the table. Bytecode/JIT retain node objects, so updating those objects preserves
runtime diagnostics without recompiling callers. Dead blocks free text/raw;
live tokens move toward the beginning of the stable table. Clear the vacated
tail without freeing its copied string pointers a second time. Then update block
boundaries and `ntok`/`pos`; the next transaction takes a fresh snapshot.
No compaction occurs while frames, parser state or rollback snapshots are live.
This removes replaced-only declaration history from the token limit. The limit
still applies to simultaneously retained source and to individual submissions.

REPL function IDs remain stable so callers observe body replacement. Unsupported
signature/generic changes, including foreign/exported C ABI mode changes, require
a new session. Each function owns its node/local lists, borrow-source records,
drop metadata, bytecode pool and JIT mapping. `FreeFunctionChanges` compares
current and snapshotted ownership pointers: commit disposes superseded artifacts,
rollback disposes staged artifacts before restoring the snapshot. Never drop
user values from this metadata cleanup; frame unwinding already handles them.
Function local names still refer to retained source tokens. JIT mappings record
their emitted byte length for `NativeJitFree`; successful generation and rollback
also free the builder's offsets, patches and temporary machine-code text.

Snapshots copy only the active function prefix. Rollback clears discarded tail
entries before reusing their IDs, including specialization origins and ownership
fields. Cached callers survive callee replacement and rejected submissions.
Pinned mixed declaration blocks, distinct immutable text and
other auxiliary allocations still require a complete lifetime audit; this
remains an open release gate.

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

## Editor boundary

Editor diagnostics use the native Token file/start/end fields (UTF-8 byte
positions, including EOF). JSON escaping must preserve valid source UTF-8 and
escape path/message quotes, backslashes and control bytes. ErrorAt keeps the
ordinary human diagnostic and failure status; structured output is enabled only
for editor modes. The transport converts positions and orchestrates unsaved
snapshots, never reimplements parsing or type/ownership decisions. Overlay files
must keep their original module-resolution identity and must not update source
files, module sums or the persistent source scan cache.

Editor reference lookup keys token text by pointer identity, never spelling:
separate declarations named `x` must remain separate. A per-analysis open-addressed
map resolves those identities to tokens without rescanning all tokens per name.
Local records and checked AST call slots supply binding identity; field/type
resolution emits references at native semantic resolution sites. Specialized
functions keep their template's declaration token. The editor mode is a fresh
process with no REPL token compaction or interned session identifiers. Never use
this index across source reloads without rebuilding it. Python may map paths and
positions and deduplicate records; it must not infer Cool name resolution.

Completion runs in its own native checking process. Insert synthetic tokens only
before CollectTypes/ParseProgram establish token pointers and declaration ranges.
Preserve the final EOF token and enforce the token capacity on every insertion.
Temporary closing braces only allow the declaration scan to locate incomplete
function bodies; ordinary parser state determines actual visible locals, type
names, package exports and receiver members. Never infer scope from spelling or
return moved/shadowed outer bindings as live locals. The lexer excludes comment
ranges; strings and other literal interiors cannot become completion markers.
Reaching the marker emits results and exits before executing user code. Failures
before the cursor can still prevent completion; this path does not certify a
whole incomplete program or replace the normal checker.

After declaration collection, completion may swap the requested non-generic
function to the front of the body-checking order. It must preserve the complete
function list and all signature/layout validation. Normal checking and REPL
parsing keep their original order because their completion token is null. This
allows a valid signature in a broken dependency to support candidate lookup;
it neither accepts the broken program nor suppresses ordinary diagnostics.
Errors before the cursor in the requested function still abort that request.

Top-level completion is allowed only at declaration boundaries (file start,
a semicolon or closing brace) or after `pub`. Do not offer declaration keywords
where the grammar expects a declared name. Empty files have no source token;
a temporary marker supplies only the completion edit range and is consumed
before exiting the isolated process. The driver may tolerate a missing package
header only for the requested completion source; other files and ordinary
checking/diagnostics retain normal package rules. This is not a change to the
language's package requirements.

## External input lengths

ValidateInput must run on the actual byte length before lexing external source,
formatting input, interpreting bundle/package manifests, or evaluating a REPL
submission. A zero byte inside that length is invalid; the allocated trailing
sentinel is outside the length. Do not replace length checks with StrLen.
Raw REPL commands must also check that their C-string length equals Text.len,
so they cannot bypass validation and recovery with a truncated command prefix.
Package loading keeps input buffers registered with the recovery scratch owner
before validation can raise an error. The diagnostic uses the offending byte's
file/range/line/column and consumes its temporary Token synchronously.

## Integer execution agreement

Arithmetic, bytecode/native-JIT helpers and LLVM runtime helpers must agree on
operand width and signedness. Division/remainder must reject zero divisors and
signed minimum divided by -1 using the actual operand width, not just i64's
minimum. Shift validation uses that width, and its diagnostic must not imply a
64-bit count range for narrow operands. Addition/subtraction/multiplication and
unary negation retain wrapping semantics; do not add LLVM overflow assumptions.

The retained HolyC seed truncates its native unsigned remainder result to 32
bits. The bootstrap interpreter therefore computes unsigned remainder as
`a - (a / b) * b`, after checking the divisor. Keep the production interpreter
formula aligned. This avoids relying on that seed instruction while leaving the
seed/provenance unchanged; it does not claim the legacy compiler is repaired.
Use an independent large-u64 oracle, not just cross-engine agreement, to guard
this boundary. The LLVM runtime's C unsigned remainder remains full-width.

## Floating host boundary

Both production and bootstrap hosts use cool_parse_float from numeric.h. strtod
may set ERANGE for a nonzero representable subnormal, so ERANGE alone must not
reject a literal. Reject non-finite results and ERANGE with a zero result, along
with incomplete/invalid parses. Do not let host wrappers diverge on this rule.
The lexer owns token grammar; this adapter only converts an already selected
numeric spelling. Float-to-integer casts must check finiteness and the half-open
destination range before executing the host cast; sanitizer tests explicitly
enable float-cast-overflow in addition to undefined/address checks.

Integer-to-f32 conversion must cast the integer directly to float, then widen
that rounded value only for the internal double-bit representation. Casting to
double before float loses which side of a binary32 midpoint a large integer
occupies. Signed and unsigned inputs require their respective integer casts.
Expected values for this boundary must be computed with exact integer quotient,
remainder and even-significand tie handling, not float(value) followed by f32,
which would duplicate the defect in the oracle.

Numeric token scanning records accumulator overflow without reporting it until
the token is classified. Once overflow is recorded, stop accumulating integer
bits but keep scanning the spelling. Decimal tokens with a fraction or exponent
are converted from the complete source spelling; their integer prefix need not
fit u64. Only a token that remains K_INT reports integer overflow. Reset the
flag for every number; it must not leak into later literals or REPL submissions.

## Signature name validation

Check uniqueness of function parameter names while collecting the signature,
before any body or ABI handling. Checking only AddLocal misses extern functions
because they have no body. Apply the same signature rule when a generic function
is instantiated and to exported functions and methods. The current lazy-template
validation limitation remains separate; this check must not imply that unused
generic bodies have been fully analyzed.

## For initializer stores

For initializers accept N_STORE alongside binding/local assignment/expression
nodes. Parse them with the ordinary statement parser so mutable-place checks,
coercion, transfer and live-place validation remain active. The initializer stays
before the loop node in its enclosing block, so it executes once and participates
in the same ownership/reference analysis as an ordinary store. Do not special-case
projected writes to bypass loans or introduce a separate unchecked evaluator.

## Package test-source selection

The driver's include_tests flag applies only to the requested root package, not
to every package visited through imports. Determine eligibility using the resolved
package identity, not the declared short name or directory basename. Dependencies
supply production files even during a root test build; their test-only imports
must never add edges to that graph. Explicit file entries remain explicit and
are not filtered by filename suffix. Source selection happens before metadata
scanning, so excluded dependency tests must not produce parse/resolution errors
or affect the artifact input set. Selecting that dependency itself as a test root
must include its own tests normally.

## UTF-8 input and invalid-file diagnostics

ValidateInput checks complete byte lengths for well-formed UTF-8 before lexing
or manifest interpretation. It must reject isolated/truncated continuations,
overlong encodings, surrogates and values beyond U+10FFFF without reading beyond
the supplied length. ASCII NUL keeps its separate diagnostic. Native positions
remain byte-based; successful multibyte sequences advance the column by their
byte width. Validation cannot execute a valid prefix of an invalid REPL input.

An invalid UTF-8 dependency can still receive an editor diagnostic. Preserve the
original file URI and raw bytes rather than redirecting its error to an open
buffer when decoding fails. Diagnostic position mapping uses replacement
characters only for malformed byte input. Valid source keeps the existing UTF-16
mapping. This recovery path must not write replacement bytes back into the file.

## Template signature preflight

`TemplateSignatureSyntax` consumes a generic function signature at declaration
time without binding type parameters or allocating concrete types. Its type
syntax walk checks delimiters recursively, with a 256-level bound; parameters
and type arguments retain the ordinary 32/8 limits. The parameter-name table
lives on the stack and is used for duplicate and borrow-contract name checks.
The cursor stops immediately before the required opening body brace. It must
not populate `Function.argc` or concrete argument types: specialization starts
with a cleared `Function` and runs the full `FunctionSignature` parser after
binding real type arguments. Keep both syntax implementations and the concrete
parser aligned when changing type grammar. `TemplateNamedArity` resolves type
parameters before builtins, then nominal types, using the same alias/privacy
rules as `ParseType`. `CollectTypes` has already gathered forward nominal names
and imports. It records nominal editor references, but does not instantiate a
type or compute a layout. Borrowed type semantics and generic bodies are not
certified by the preflight.

`TemplateNamedArity` returns -1 only for the actual builtin `void`, after checking
parameter names; ordinary zero-argument types and a parameter named `void` return
zero. `TemplateTypeSyntax` normalizes that sentinel for arity checking and returns
one only for a bare builtin void type. Raw pointer construction consumes the
flag and returns zero; references/owners/arrays/slices and generic argument lists
reject it. The signature rejects it in value parameter position, while permitting
a void result. Literal array counts are checked before constructing any layout,
including unsigned literals whose token bits appear negative as signed i64.

## Template body grammar

After collecting declarations, `TemplateBodyCheck` parses each unspecialized
function's body from `Function.begin`. This pass creates no AST, slots, concrete
types, move state or loan state. `TemplateScope` is a stack-local name table;
parameter names come from the already checked signature. Bindings enter after
their initializer. Blocks restore the entry count; for loops additionally restore
the initializer scope, and each match arm restores its payload binding. This is
needed to distinguish imported nominal constructors from ordinary projections
when a local shadows an import alias. The scope supports root-name resolution but does not certify inferred local
types or lifetimes. The cursor/recursive-depth limits bound grammar work and stack
usage; all state disappears on normal return or native error recovery.

Expressions use the ordinary `Prec` table. Type-list lookahead is limited to
balanced square brackets followed by a call or constructor; collected nominal
names also permit enum type arguments before a variant selection. Type syntax
uses the signature preflight. Concrete specialization still runs the normal
parser and every semantic/ownership/borrow pass. Keep `TemplateBody.cool` and
`32-template-body.cool` aligned and extend the positive cross-engine fixture and
unused rejection suite whenever grammar changes.

## Binary implicit typing

`CanImplicitCoerce` is the single side-effect-free eligibility predicate used by
both `CoerceBinary` and `Coerce`. `Coerce` applies only the AST transformation. `CoerceBinary` first adopts representable
literals, then chooses a lossless conversion direction. It does not create a
third inferred type or permit narrowing. Comparisons use the same normalized
operands before producing bool. Shift counts remain independently typed, with
integer checks and the left operand's original width; every backend checks the
actual count before shifting. Numeric typing changes must preserve runtime
canonical values and update both frontend implementations and the oracle suite.

Implicit float range tests inspect the mathematical integer value. A u64 literal
above i64 maximum has negative internal bits; it must not pass a small-signed
range test in either `CanImplicitCoerce` or `Coerce`. Explicit numeric casts use
the original unsigned type and retain the published rounding behavior.

`Coerce` is readable new-syntax code in `33-implicit-types.cool`, replacing the
old generated core implementation. Identity conversion leaves the node untouched;
permitted null/integer literal adoption changes its type in place. Other eligible
conversions clone the old node through `AllocateNode`, clear the clone's `next`,
and wrap it with N_CAST. The original node's `next` remains the surrounding
argument/initializer list link. Keep allocation tracking and source/provenance
metadata intact: conversion must not copy a sibling into its operand subtree.

## Nominal template preflight

`TemplateAggregateSyntax` walks collected generic nominal member tokens using a
stack-local Function solely as the generic-name environment for
`TemplateTypeSyntax`. It must not bind fake concrete type arguments, attach
fields to the descriptor, or mark its layout complete. Duplicate-name records
are recovery-owned scratch allocations, so a rejected REPL declaration retains
no fields or temporary names. The cursor is restored on success; nonlocal error
recovery restores the parser and declaration transaction. Concrete Layout still
constructs fields and validates recursion/size/storage after specialization.

Floating comparisons must handle NaN before the retained seed's native comparison
instructions: its unordered CPU flags otherwise make `NaN == NaN` true. For the
binary64 carrier, magnitude bits above `0x7ff0000000000000` denote NaN for either
sign. Return true only for K_NE in that case, before the scalar switch. LLVM
ordered comparisons/une already match this rule; VM and native JIT share
Arithmetic. Do not test NaN through `x != x` in bootstrap compiler code, because
that would rely on the defective seed operation itself.

`Arithmetic` in `07-interpreter.cool` now uses direct control flow rather than
port-generated temporaries and single-iteration dispatch loops. Preserve the
operand's width/signedness for division and shifts, the seed-safe full-width
unsigned remainder formula, binary64 carriers with f32 normalization, unordered
comparison handling and final integer normalization. The bootstrap's compact
switch implementation remains intentionally separate. Numeric refactors must
pass independent integer/rational oracles on both frontends and all engines;
bootstrap convergence alone cannot establish arithmetic correctness.

## Slice descriptor reference projections

`ReferenceSliceValue` reads a projected descriptor without treating that read as
an exclusive slice-value copy, and acquires the selected payload capability for
an element address. `ReferenceLength` observes only physical descriptor storage;
it must not bypass a live exclusive loan of the descriptor binding. Physical
and indirect roots of a nested receiver remain distinct. Direct element reborrows
may allow descriptor reads; ambiguous returned-reference contracts retain their
physical anchors conservatively.

A store pins its destination with read-mode address evaluation before evaluating
the RHS, then requires write access after the RHS. `ReferenceWriteCapability`
checks every enclosing reference in the destination projection before read-mode
pins are established, including computed shared receivers and stored references.
This allows ordinary scalar read/modify/write without weakening owner-address liveness or live child-loan
conflicts. Do not discard pending address pins before evaluating RHS/index calls.
Borrowed-storage writes through a reference are rejected until replacement
provenance can be attached to the actual destination lifetime across calls.

## Value provenance and borrowed storage boundaries

`Borrowed(type)` classifies value-level provenance: slices and references retain
external roots, arrays inherit their element provenance, and nominal aggregates
inherit their fields. Owning handles inherit their payload's external provenance;
the heap's physical storage lifetime is separately anchored to its owner. Keep `Layout` before
reading field lists, including lazy nominal and generic layouts.

`ValidateBorrowedElements` first enforces reference-storage restrictions, then
checks owner payloads for unsupported nested stored references and slice
elements for borrowed payloads, recursively validating owner/array/nominal fields. The predicate and storage validator have distinct
roles. `BorrowTypeProperty` creates an independent 4096-byte visited bitmap for
each query; `BorrowTypeWalk` visits each reachable aggregate once, bounding
work by reachable types and fields even in shared DAGs. Returning false for a
repeated type is valid for this single-root existential reachability query; do
not cache intermediate false results across queries. `ValidateBorrowedGraph`
uses a separate bitmap per validation. Neither bitmap survives lazy layouts,
generic specialization or REPL rollback. Both walks and `ReferenceStorage`
resolve `Layout` before reading fields. Heap
initializers propagate external loans, while addresses into an owned allocation
use physical owner roots; relaxing the validator alone would not establish this. The production implementations use direct control flow
and remain semantically aligned with the compact bootstrap `Types.cool` helpers.

## Template expression-root resolution

`TemplateValueName` resolves bare and import-qualified roots against lexical
scope, the template's generic parameter names and the already collected nominal
and function tables. It preserves forward functions and import-alias shadowing,
and checks public visibility when an alias qualifies a type/function. Intrinsic
names must match the ordinary parser's builtin categories. It never creates
layouts, nodes, slots, move state or loans. Member names after a local/dependent
root remain deferred to concrete specialization; rejecting every unknown-looking
member here would break valid generic code. Undefined root names are independent
of substitutions and must be rejected even when the template is unused.

## REPL interior storage reservations

`ReserveStorage` is shared by `AddLocal` and anonymous `Storage`. Ordinary
functions keep monotonic allocation. Session function zero searches for the first
contiguous range that does not overlap a visible binding or any reservation made
in the current input. It advances past colliding range ends, without moving live
values. `Function.slots` remains the highest allocated end, so bytecode virtual
registers start beyond physical local/temporary storage.

Every current-input allocation, including match scrutinees, aggregate call
results, literals and locals inside a block, enters `ReplStorageRange`. Checking
only lexical locals would lose anonymous or ended-block temporaries. Range records
use `ScratchAllocate` and survive nonlocal recovery; `ReplFreeScratch` releases
them and clears the head. A new statement starts with an empty reservation list.
No allocation-time mutation of the old drop list is allowed: rollback compares
new DropSlot records to the saved list head.

Before executing bytecode, `ReplStorageInitialize` zeroes each reserved range,
including holes below the previous high-water mark. A failure before storing an
owner must drop zero, not stale scalar bytes interpreted as an owner address.
Compile-only failure does not initialize/rewrite existing live values. After
execution/recovery, existing frame/drop/loan cleanup runs before metadata disposal.
`:forget` still rejects a root or parent with surviving dependent loans. Raw
pointers escaped through unsafe code must not outlive a forgotten binding.

## Moving aggregates that contain borrows

`N_MOVE.origin_source` preserves the original value expression separately from
its address operand. Region analysis follows that value, including enum payload
loads. Physical move access is checked as a write before external payload loans
are acquired. A move through a nested receiver selects payload layer one like
an ordinary load, while owned pointee loans use physical layer zero. Place
regions of an owned handle loaded from a receiver follow its address; by-value
owned handles still belong to the current frame.

`ClearMoved` and generated LLVM `__cool_clearTYPE` routines clear owning
subobjects recursively. Borrow-free owned subobjects keep the previous complete
zeroing behavior. Borrowed aggregate fields and enum tags remain initialized;
this prevents a retained exclusive receiver from exposing null scoped references
after a move. Destruction of emptied handles remains a no-op. Both interpreter
paths, native JIT's bytecode operation and LLVM AOT/JIT use this contract.

## Heap payload provenance

`N_NEW` carries its initializer's regions and loan expressions. An owner LOAD
retains its original owning value as `origin_source`; borrowed payload projections
follow that value. `ReferenceMode` includes owned payload capabilities, with the
same recursive type-cycle guard as `Borrowed`. Reading a named owner handle to
form an address uses physical access checking rather than prematurely acquiring
its payload's exclusive reborrow, avoiding a self-conflict in consumed exclusive
getters. Assignment keeps the original holder marker and checks source root depth.

`ClearMoved` and generated `__cool_clearTYPE` routines special-case owning
handles before classifying borrowed payloads. The handle is always zeroed, never
recursively cleared in its allocation. Typed destructor traversal still frees
only owned subobjects. Compiler and runtime checks preserve the distinction
between externally borrowed heap fields and references to the heap itself.


The graph audit uses a separate Python worklist oracle over generated nominal
owner/array graphs. A private compiler LLVM copy records property results and
property/validation walk calls; normal compiler artifacts contain no instrumentation. Cycles with
late shared/exclusive terminals, reversed field order, shared diamonds through
depth 40, lazy generic layouts and REPL rollback are checked. The per-query call
bound counts graph edges/types rather than relying on a wall-clock timeout as
proof of linear work. Overall compilation can still issue many separate queries;
this audit establishes the traversal bound, not linear total compiler complexity.


## Local borrowed replacement

`ReferenceStatement` routes local `N_ASSIGN` and locally rooted `N_STORE`
through `ReferenceAssign`, including reference-bearing values. `N_ASSIGN`
changes physical binding storage; it must not be treated as mutation through
that binding's shared referent. A live physical loan still blocks replacement.
Through-reference borrowed replacement remains explicitly rejected.

The original null-root holder marker anchors retained loans. Every incoming
root must outlive the target depth, and borrow-region analysis accumulates new
sources for return-contract validation. Keep old roots conservatively. Before
inserting, merge an existing identical holder/root/parent/mode/layer edge below
the marker; expression identity is irrelevant once a loan has a holder. This
bounds repeated identical REPL replacement without discarding distinct
capabilities or parent ancestry. Cross-engine replacement, independently modeled
root permissions, runtime rollback and 64/1,024-input allocation histories cover
this invariant.


## Value regions and binding origins

`04-borrow.cool` now expresses provenance directly, without generated temporary
variables or numbered control-flow states. `BorrowRegion`/`BorrowPlaceRegion`
share the AST cases for value and binding-origin queries. `Region` keeps all
possible payload roots for escape contracts; `OriginRegion` follows reference
binding sources independently of indirect storage writes. Parameter construction
seeds both `Local.region` and `Local.place_region` with the parameter bit. Do not
seed origins from an already-propagated value region on reanalysis: that would
turn installed payload sources into possible physical destinations.

`BorrowSource.storage` separates stores from binding initialization/replacement.
`PropagateBorrowRegions` first gathers all binding edges, then records stores.
Stores through a reference alias propagate to every reachable binding source,
including reborrows and calls selected by a `borrows` contract. Store edges are
excluded from destination traversal. Identical node/channel edges are recorded
once. The monotone fixed point propagates both channels; loaded payloads use
value regions because stored data may have changed. This is conservative root
information, not a field-sensitive multi-layer provenance graph.

`Local.destination_mark` uses the current RHS AST node as a query identity.
Bindings are complete before traversal, so visiting each local once per store
covers cycles and shared DAGs. Clear marks before/after propagation; they must
never be persistent AST roots. Repeating propagation on the same function keeps
origins/results stable and does not add duplicate source edges.

`tools/test_borrow_origins.py` inserts trace calls into a private source copy,
compiles it through the production frontend and compares 330 channel values with
an independent worklist oracle. It runs propagation twice and counts destination
visits, including a depth-32 alias diamond, cyclic aliases, multiple store
queries, late branches, stored aliases, computed reborrows and contracted results.
It copies host/runtime objects and records source/IR/object identities in
`build/borrow-origins-audit.json`. Normal native/legacy and ASan frontends still
reject unsupported receiver writes (or earlier live-alias conflicts). This audit
proves the component's modeled provenance results, not cross-call mutation safety.

The remaining cross-call implementation must validate destination/source
relations in function signatures, preserve per-root capabilities, retain source
loans at every actual destination's original marker, update live receiver
payload loans and caller return-region edges, compare effects on REPL replacement,
and preserve candidate roots after partially executed runtime failures. The
origin split is prerequisite evidence; it does not itself relax those checks.
