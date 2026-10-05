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
