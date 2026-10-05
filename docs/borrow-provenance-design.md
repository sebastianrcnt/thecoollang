# Nested borrowed provenance implementation design

Status: **required implementation work, not implemented acceptance**. The current
compiler still rejects stored references to borrowed pointees and borrowed slice
elements. This document defines the next implementation boundary without reducing
the 1.0 release requirements. See [release gates](release-1.0.md).

## Current foundation

Value regions and binding origins are independent. Checked `stores(dst,src)`
effects retain installed sources at original caller lifetime markers and update
live receivers before selecting returned loans. Scoped loan ancestry now follows
all parents for a physical root with a cleared, query-local visited queue. The
current `ReferenceLoan.indirect` still describes only physical/payload layers;
it cannot encode arbitrary nested projections.

A holder/root may have multiple parents after a unioned call result. Parent
selection must not depend on list order. `ReferenceHolder` still returns one
record for existing replacement normalization; it is not a general graph query.
The ancestry walker must remain allocation-free, terminate on cycles and clear
its temporary Local fields before returning or persistent metadata reclamation.

## Typed cursors

Replace the two-layer projection selector with a cursor into a typed provenance
graph. Each loan keeps its physical root, actual per-root permission, holder and
reborrow ancestry, plus its value-relative cursor. Separate lifetime protection
from the provenance of values stored in that protected space.

| Edge | Meaning |
| --- | --- |
| Field(nominal type, declaration key) | Struct field or enum variant payload |
| Element(sequence type) | Conservative union of possible array/slice elements |
| Referent(reference type) | Storage addressed by a scoped reference |
| OwnedPayload(owner type) | Storage inside the owning allocation |

Offsets alone are insufficient: enum payloads can occupy the same offset, and
zero-sized fields can share offsets. `Node.field_key` retains resolved declaration identity in struct initializer
children, field addresses, enum tags/payloads and match guards/payloads.
`PlaceProjectionKind`, `PlaceProjectionParent` and `PlaceProjectionType` expose
typed AST edges; existing stored-reference and write-capability guards use the
parent walk without changing their permission rules. This is compiler metadata,
not emitted runtime representation. Private AST checks cover compatible REPL
function replacement and failed lazy-layout construction under sanitizers.
Future persistent cursor graphs still need explicit descriptor ownership across
layout rollback and source reclamation; these AST checks do not implement it.

Dynamic indexing selects every possible element cursor. Constant indexing may
refine the selection only when all writes, moves and opaque calls use a compatible
model. Shared/exclusive fields at the same nesting depth must remain distinct.
Do not replace field identity with nesting depth or the maximum mode of a type.

Recursive nominal references use shared graph nodes, not infinitely expanded
path strings. Walk keys include cursor/projection state, root and actual mode.
Type-only visited sets are insufficient when one type appears with different
capabilities or provenance. Borrow-free ownership/layout traversal remains a
separate operation.

## Implemented graph query foundation

`compiler/38-provenance-graph.cool` now implements an owned node/edge arena and
typed value-relative payload selection. Each node has a terminal physical root
and its actual capability; intermediate shared barriers belong to edges. Field
selection compares declaration keys and concrete source types, element selection
unions possible elements, and referent/owned-payload edges retain their kinds.
Capabilities intersect along edges and at the selected root. Distinct shared and
exclusive source edges remain distinct; another path cannot upgrade a shared
path. Edge insertion rejects cross-arena targets and invalid edge kinds. Callers
must check its boolean result and copy substitutions into the destination arena.

Queries retain no AST/layout pointers or cursor ownership, mutate no graph
marks, and free every query state even after early success. Visits are keyed by
(node,cursor,actual mode), so both recursive graph edges and cyclic query cursors
terminate. Arena destruction visits owned allocation lists rather than target
edges, safely handling cycles/shared targets and repeated destruction.

`ProvenanceGraphCopyRoots` copies all supplied reachable roots with one
source-node identity map, preserving cycles, shared targets and duplicate/null
roots. Input and output buffers must not overlap. Single-root copying is a
wrapper over this batch operation. Cross-arena and same-arena copying both
create independent nodes. Failed edge insertion frees the scratch map, removes
only newly allocated destination nodes/edges, restores the previous arena head
and clears output roots. Local/type/declaration metadata remains borrowed.
Independent tests destroy the source arena before querying copied graphs,
compare copied node/edge counts and check malformed-copy rollback.

Production `ReferenceLoan.provenance` now carries a node in a check-owned
arena. Initializers preserve Field/Element/OwnedPayload edges; known same-type
value copies and whole-binding assignment retain/union graphs. REPL begin copies
all surviving loan roots jointly into an independent arena; commit compacts
reachable roots, rejection frees candidates, and runtime failure keeps candidate
roots. `:forget` compacts again and session cleanup frees the arena. Failed
function analysis is registered under a heap check list for exception cleanup.
Graph roots participate in Local reclamation. Loan queries intersect the loan's
entry capability before following graph barriers.

The existing two-layer checker still protects physical anchors and supplies
opaque permission fallback. Universal typed payload mode queries additionally
reject shared alternatives for named and computed stored-referent writes and
exclusive-handle value copies/moves. Computed projection read pins query their
original live source with the full place cursor, preserving shared barriers. Handle copies stop at reference/slice nodes; their internal
payload graphs retain lifetime protection without requiring exclusive copy
authority. Universal mode queries record physical prefix contributions and
continue matching edges; existential overlap may stop at the prefix. This retains
deeper shared capabilities of the same root. Full physical protection and opaque
authority remain required. Typed graph paths now exclude proven absent layer-one payload roots
from production conflict matching and reborrow acquisition. Overlap ignores
shared/exclusive mode; terminal physical roots overlap remaining projections.
Unknown/opaque/incomplete paths remain conservative. This first access step
does not remove nested storage restrictions. Legacy metadata/arena integration
and both-frontend access/REPL acceptance now pass. Field loads and partial stores now select/update
metadata; parameter and opaque return summaries describe declared possible
structure. Opaque return bounds are per source root/capability, with recursive
skeleton reuse preserved through owned auxiliary clone edges. These are upper
bounds, not callee-body field correspondences. Auxiliary ownership is never
followed for access authorization. Precise typed caller/callee substitution
and physical protection remain required. Legacy graph construction, selection, call/store upper bounds, access absence
and these additional universal authority checks now mirror production; both
actual frontends are exercised by private metadata/REPL regressions. Physical prefix overlap, descriptor-lifetime audit
and arbitrary nested acceptance remain required. The initial state deduplication scans a list:
state visits are bounded but membership search can be quadratic. The independent
product-graph audit counts both visits and membership comparisons; no linear
compiler performance claim follows from its state bound.

## Operations

Address acquisition creates physical protection for the selected place and
links the borrowed payload graph beneath its cursor. A load/copy selects the
value provenance at that cursor; a move also checks live physical children and
transfers the graph while preserving the existing initialized-reference rules.
`N_FIELD_ADDRESS`, `N_INDEX_ADDRESS` and `N_OWN_ADDRESS` retain their distinct
field/element/reference-or-owner projections. `N_LOAD.origin_source` identifies
the source value; resolving an origin must not discard the selected projection.

A store resolves every possible destination cursor, checks physical write
permission and source lifetime, and substitutes the incoming graph beneath the
original destination holder marker. Keep conservative old roots and update all
live receivers which reach that cursor. A shared barrier can reduce capability;
no path operation may upgrade a shared root because another field is mutable.

Function signatures keep the existing parameter masks for `borrows` and `stores`.
At a call, evaluate and protect all arguments first. Substitute selected source
graphs into every possible actual destination, then collect the return graph.
When parameter-only contracts do not express a precise field correspondence,
union every compatible mapping conservatively, preserving source capabilities.
Callee body checking uses abstract parameter graphs and rejects frame roots in
caller storage. Recursive calls require a terminating summary/fixed-point model.
A call must not guess one physical destination from its syntactic root.

Temporary and named receivers use the same original holder lifetime. Physical
owner anchors must remain separate from references to external data stored in
that owner's payload. Returning an external field is different from returning
an address into a callee-local owning allocation.

## Transactions and validation

Temporary query graphs use bounded/reclaimable scratch ownership. Persistent
binding graphs belong to session/function metadata with explicit commit/rollback
ownership. Checking failure discards staged graphs; runtime failure retains
candidate roots after potentially executed stores. Function replacement, type
layout rollback, source compaction, `:forget`, owner destruction and session
cleanup must account for graph edges without double-freeing shared nodes.

Required acceptance cases include stored `&&i64`, `&View` and `&mut View`, mixed
shared/mutable fields at equal depth, arrays/slices of borrowed values, recursive
nominal references, enums/generic/owning wrappers, computed multi-root receivers,
forwarded/recursive contracts and moved aggregates. Check read/write/copy/move
permissions independently from lifetime escape behavior. Include shorter-scope
installations, live child conflicts, shared barriers, lazy type rollback and
partial REPL execution. Positive cases must execute on all five engines and O2;
negative and independently modeled graph cases must run on both frontends and
under compiler/generated-code sanitizers. Repeated graph installations and
compatible function replacements need allocation/JIT lifecycle measurements.

This work closes no release gate until the implementation and this full scope of
acceptance evidence exist.
