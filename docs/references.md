# Scoped references (development)

A shared `&T` provides read access. An exclusive `&mut T` permits mutation.
`&value` and `&mut value` borrow a stable local, field, array element or owned
pointee. The exclusive form requires a mutable place. Neither allocates memory
or takes ownership. Both occupy eight bytes on the supported 64-bit host.

```cool
fn increment(value: &mut i64) { *value = *value + 1; }
fn read(value: &i64) -> i64 { return *value; }
fn main() {
    var number = 40;
    {
        let writable = &mut number;
        increment(writable);
    }
    let readable = &number;
    assert(read(readable) == 41);
}
```

A reference binding holds its loan through the enclosing lexical block.
Several shared loans may coexist. A live exclusive loan rejects other access
through its root; any live loan rejects incompatible writes, moves or owner
replacement. Conflict checks conservatively treat all projections of one local
as the same root, so two different fields are not yet independently borrowable.
Calls retain argument loans while later arguments are evaluated. Temporary
loans ordinarily end with the statement; `defer` retains captured loans through
its enclosing block. Owner destruction still follows normal scope cleanup.

Passing or binding an existing reference reborrows it. A child exclusive loan
suspends parent access; a shared child prevents parent writes. After the child
block ends, the parent can be used again. Mutable local reference bindings can
be reassigned under the lifetime rules below. `move` of a reference is also a reborrow, not ownership transfer.
Moving an owning pointee requires an exclusive reference and leaves its owner
slot empty, just as a direct owner move does.

Generic code can exchange owning values without raw pointers:

```cool
fn swap[T](left: &mut T, right: &mut T) {
    let old = move *left;
    *left = move *right;
    *right = move old;
}
```

A function returning a reference declares `borrows(parameter)` and may only
return storage rooted in that parameter. Returning a local or local owner is
rejected. A contract can name multiple reference parameters, such as
`borrows(left, right)`. The caller conservatively protects the union of possible
roots, even when a literal selector appears to choose only one branch. Arguments
may be named references, direct borrows or reference-returning calls; nested
calls and reborrows retain every root and its corresponding parent. Argument
loans protect evaluation of later arguments, and result loans remain live through
their enclosing binding or expression. A returned field reference keeps the
entire source root borrowed.

```cool
struct Pair { value: i64; }
fn field(pair: &mut Pair) -> &mut i64 borrows(pair) {
    return &mut (*pair).value;
}
```

Raw pointers remain `*T`, constructed with `unsafe { &raw place }`. Bare `&`
now always constructs a shared reference, including inside `unsafe`; it is no
longer a raw-address alias. The usual raw-pointer lifetime obligations remain
with unsafe code. There is no implicit reference-to-pointer conversion.

## Remaining implementation work

This is a development foundation, not completion of the 1.0 borrowing gate.

- Shared and exclusive references can be stored in structs, arrays and enums,
  including aggregates that also contain slices and owning fields. Owning
  payloads retain their own external loans. A stored reference's pointee must not itself contain borrowed storage.
  Stored references to borrowed pointees still need nested lifetime tracking. Reassignment of reference
  bindings/fields and general nested stored lifetimes need further tracking.
- Function-body slices use the same lexical provenance as references. A slice
  exclusively borrows its elements; element references reborrow it, and disjoint
  lexical scopes can reuse the source. Direct references to slice descriptors
  are supported; stored references to descriptors and slice elements containing
  borrowed storage remain unsupported.
- REPL submissions retain reference and slice loans across inputs under the
  same checking rules as functions. Top-level bindings stay live until
  `:forget name` or session exit. See the persistent-loan and recovery rules
  below; bounded session-resource reclamation remains work.
- There is no automatic field dereference, reference coercion, lifetime syntax,
  or borrow-aware replacement for every collection API.
  [Methods](methods.md) use the same scoped loans.

`make references-test` exercises both frontends, all five execution engines,
optimized native output, generic owner exchange, diagnostics, formatting and
REPL rollback. `make selfhost-check` separately proves bootstrap convergence.

## Unsafe library bridges

Low-level containers sometimes keep storage behind raw links. Inside `unsafe`,
`cast[*T](reference)` exposes the pointee address with an exactly matching
pointee type. The resulting raw pointer has no tracked lifetime. A pointer
derived from a shared reference must not be used to mutate its shared storage.

`borrow_raw[&T](pointer, anchor)` and `borrow_raw[&mut T](pointer, anchor)`
construct references whose lifetime is rooted in a named reference `anchor`.
They require `unsafe`, exact pointer element types, and an exclusive anchor for
an exclusive result. The implementer must prove that the pointer is valid,
properly aligned, initialized, and remains within storage protected by the
anchor's loan. An exclusive result also requires that the pointed-to storage
itself is exclusively protected: an exclusive container anchor does not upgrade
its contained shared references. Merely naming an unrelated anchor does not
make a pointer valid.
The compiler retains the anchor's provenance and checks caller-side conflicts,
but cannot verify arbitrary raw-pointer data structures.

The vector implementation uses these bridges internally. Its public `len` and
`at` accept `&Vector[T]`; `append`, `pop`, `clear` and `at_mut` accept
`&mut Vector[T]`. `at` returns `&T`, and `at_mut` returns `&mut T`, both with
`borrows(vector)`. A live element reference therefore prevents invalidating
operations on the vector. Indices are checked; invalid indices trap.

```cool
import vector "std/vector";
fn main() {
    var values = vector.create[i64]();
    vector.append[i64](&mut values, 40);
    {
        let value = vector.at_mut[i64](&mut values, 0);
        *value = 42;
    }
    assert(*vector.at[i64](&values, 0) == 42);
    vector.clear[i64](&mut values);
}
```

`fs.write(path, &bytes)` similarly accepts a shared byte-vector reference.
Vector `iter`/`Iterator.next` provide tracked read-only iteration, as described
below. The older `cursor`/`next` free functions remain raw, manually managed
iteration APIs. Their advancement needs unsafe raw access and
removal/clear/destruction invalidates raw cursors. File
writing uses that internal linear traversal; it does not repeatedly index the
chunk chain. Indexed access is O(index / 32); append and pop are O(1).

`make safe-vector-test` executes an owning-vector and binary-file program with
no `unsafe` blocks on five engines and rejects conflicting element-loan use.
The seeded collection model also exercises the reference APIs under ASan.


## Multiple sources and computed reborrows

```cool
fn choose(first: bool, left: &i64, right: &i64)
    -> &i64 borrows(left, right) {
    if (first) { return left; }
    return right;
}
fn main() {
    var left = 1;
    var right = 2;
    {
        let selected = choose(false, &left, &right);
        assert(*selected == 2);
        // Neither left nor right can be changed while selected remains live.
    }
    left = 3;
    right = 4;
}
```

The same rule applies to exclusive results. A reborrow through a union-valued
binding carries the whole root set; changing or moving any candidate root is
rejected. Root-specific parent relationships allow a parent to resume use after
its child scope ends. Repeated occurrences of the same root/parent combination
are deduplicated rather than expanding exponentially.

An address projection through a computed reference also retains the actual
result loans. `&*choose_mut(...)` may reborrow an exclusive result as shared;
it cannot upgrade a shared result to exclusive. This enables chains such as
`map.at_mut(&key).scalar_len()` without an intermediate reference variable.
Indices and later arguments still execute while the original storage is
protected. Temporary loans used only to compute an index end after the statement;
they do not become unrelated roots of the reference being bound.

`make reference-sets-test` validates these cases on both frontends, five engines
and optimized native output. It includes 28 explicit rejection cases and an
independent finite-set oracle with 216 seeded mutation queries, plus repeated
union deduplication. Stored shared references, slices and persistent REPL
loans extend this model below.


## Stored shared references

Non-owning structs, fixed arrays and enums may contain shared references,
including through generic and nested aggregate fields. These are ordinary
pointer-sized fields; storing a reference never allocates or owns its pointee.
Every copied container retains shared loans to every possible source root.
Projection is conservative: selecting one field continues to protect the
container's whole source set, not just the field selected at runtime.

```cool
struct PairView { first: &i64; second: &i64; }
fn view(first: &i64, second: &i64) -> PairView borrows(first, second) {
    return PairView { first: first, second: second };
}
fn main() {
    var first = 10;
    var second = 20;
    {
        let pair = view(&first, &second);
        let copy = pair;
        assert(*copy.second == 20);
        // Neither source can be mutated or moved until these loans end.
    }
    first = 30;
    second = 40;
}
```

A function returning a borrowed container must declare `borrows(...)`; the
region checker rejects local-storage escapes and undeclared parameter sources.
An empty enum variant can be returned under `borrows()` with no source. Match
scrutinees have anonymous loan holders: the expression is evaluated once and
its loans remain live while any arm executes. Payload bindings reborrow that
holder. By-value methods on borrowed containers obey the same rules.

A reference-containing struct/array requires an explicit full initializer;
`PairView {}` cannot manufacture null references. Mutable local containers, reference fields and array elements can be replaced
when the new roots outlive the original binding and no live loan protects its
storage. This also applies to locally owned heap fields. Replacement through a
reference receiver remains unsupported until destination lifetime contracts
exist. Shared or
exclusive borrows such as `&PairView` and `&mut PairView` retain its possible
source roots as shared loans while separately borrowing the container's storage.
An exclusive container receiver can update ordinary fields, but
cannot replace reference fields or mutate through a contained shared reference.
Stored `&mut T` uses the reborrow rules below. Mixed ownership/slice storage,
general nested stored lifetimes and lifetime-aware replacement remain required
work for the full stored-reference gate.

`make stored-references-test` checks nested structs/arrays/enums, generic
copies, methods, computed projections, match evaluation, empty results, owner
lifetimes and scope release on both frontends, all five engines and O2. It also
checks 40 rejection cases and 144 independently modeled source-set queries,
plus actual imported `std/option` reference payloads and fallback results.

`make stored-references-sanitize-test` additionally marks generated Cool LLVM
functions for ASan, verifies inserted load checks and links the instrumented
program against the ASan/UBSan C runtime. This checks the executable fixtures;
it is not a proof of all borrowing rules.


## Tracked vector iteration

`values.iter()` (also `vector.iter(&values)`) returns `Iterator[T]`, a non-owning
value containing a shared source reference and a private raw chunk cursor.
`remaining()` is O(1). `next()` advances in O(1) and returns `Option[&T]`;
empty/exhausted iterators return `None` repeatedly. Total traversal is O(n)
and allocates no storage. An owning element is observed through `&own[T]`,
without copying or taking ownership of it.

```cool
import vector "std/vector";
import option "std/option";
fn main() {
    var values = vector.create[i64]();
    values.append(10);
    values.append(20);
    var sum = 0;
    {
        var iterator = values.iter();
        while (iterator.remaining() > 0) {
            match (iterator.next()) {
                option.Option[&i64].None => { assert(false); }
                option.Option[&i64].Some(value) => { sum = sum + *value; }
            }
        }
    }
    assert(sum == 30);
    values.clear();
}
```

The source remains borrowed through the iterator binding's lexical scope,
including after exhaustion or an early break. `clear`, `pop`, `append`, `at_mut`
and moving the source are rejected while the iterator lives. Each result also
borrows the iterator: storing the `Option` or payload outside the match arm
prevents the next exclusive call until that result's scope ends. Iterator fields
are private; safe code cannot forge an anchor or alter the chunk pointers.

Container storage and referent storage are separate loan layers. Two iterators
created from the same vector can advance independently; an ordinary shared
reference to an element may coexist with their advancement. Copying an iterator
copies its position and retains shared source loans. Keeping an element result
from the first iterator freezes that iterator, but permits the second iterator
to advance. The source vector remains immutable until all its loans end.

Fields within one container still share a conservative physical root. References
returned from a locally bound iterator cannot escape its scope, even if the
source outlives it: `next` explicitly borrows `self`. General stored lifetimes
and lifetime-aware reference replacement remain necessary for
the complete borrowing design; this API does not close that release gate.

`make nested-references-test` covers container receiver mutation, reborrows,
borrowed arrays, owner lifetimes and escape/conflict rejections on both
frontends and five engines/O2. `make tracked-iteration-test` additionally covers
12 vector sizes around chunk boundaries, owning elements, repeated exhaustion,
early breaks, unchanged allocation counts and API rejection cases.
`make tracked-iteration-sanitize-test` instruments generated LLVM with ASan and
the C runtime with ASan/UBSan and verifies inserted Cool load checks.

The standard UTF-8 validator now consumes the tracked iterator through safe
Cool code; raw chunk traversal is confined to the vector implementation. Its
existing strict UTF-8 oracle corpus and sanitizer checks cover this integration.


## Container and referent provenance

A reference to shared-reference storage carries a physical-storage loan and
shared payload loans. Reborrowing `&mut container` does not upgrade its shared
payloads. A container storing exclusive references retains their exclusive
payload loans when borrowed exclusively; a shared outer borrow downgrades its
payload reborrows to shared. Copying a reference field or copying the referenced container value
retains the payload loans without retaining its former physical address. Taking
`&container.scalar_field`, however, protects the container's physical root.
Computed projections obey the same rules as named values.

```cool
struct View { source: &i64; position: i64; }
fn main() {
    var value = 10;
    var left = View { source: &value, position: 0 };
    var right = View { source: &value, position: 0 };
    let first = &mut left;
    let second = &mut right;
    (*first).position = 1;
    (*second).position = 2;
    let item = (*first).source;
    (*first).position = 3;
    assert(*item == 10);
    // value remains shared; neither receiver permits changing it.
}
```

For a function returning an ordinary reference or borrowed container,
`borrows(...)` still conservatively combines all selected argument roots. A
returned reference to borrowed storage preserves the selected nested arguments'
physical/payload layers. An opaque non-nested anchor conservatively protects
both layers. These contracts describe possible lifetimes, not precise field
paths; this does not add field-disjoint borrowing or arbitrary nested mutable
reference storage.

`make loan-layers-test` covers receiver aliases, container copies, direct and
computed payload extraction, scalar projections, nested reference returns and
reference-slot borrowing. Fourteen negative cases and 120 seeded queries
compare container mutations and referent mutations against an independent
storage/source-set model on both frontends; valid programs run on five engines
and optimized native output. The tracked-iteration sanitizer test also covers
independent/copied iterators and retained shared element references.


## Stored exclusive references and mutable iteration

A non-owning struct, array or enum may store `&mut T`, including alongside
shared references. Each source retains its own mode: a shared source is never
promoted just because another field is exclusive. Copying or passing the value
reborrows its references. An exclusive child suspends conflicting use of the
parent's borrowed fields until the child scope ends; `move` of a non-owning
borrowed container has the same reborrow meaning. No owner allocation or
implicit reference count is added.

```cool
struct View { input: &i64; output: &mut i64; }
fn main() {
    var input = 10;
    var output = 0;
    {
        let view = View { input: &input, output: &mut output };
        {
            let child = view;
            let input_value = *child.input;
            let target = child.output;
            *target = *target + input_value;
        }
        *view.output = 20;
        assert(input == 10);
    }
    assert(output == 20);
}
```

Mutable local reference fields and whole borrowed containers follow the
replacement rules below; reference receiver replacement remains unsupported.
Shared outer receivers may read through contained exclusive references or
reborrow them as shared, but cannot copy an exclusive handle or mutate through
it. This also applies to computed receivers such as `(*share(&view)).output`;
reading its pointee is permitted, extracting its exclusive handle is rejected.
A `borrows(...)` return preserves each selected source's mode. Field/root
sets remain conservative: name an element reference before updating its
pointee when a compound expression would otherwise create competing temporary
reborrows of a stored handle.

`values.iter_mut()` returns `IteratorMut[T]`, which exclusively borrows the
source. Its `next()` returns `Option[&mut T]`; `remaining()` observes the cursor.
A retained result prevents further advancement. Copying the iterator reborrows
its source and suspends the original iterator until that copy's scope ends;
copying its position does not advance the original. An ordinary shared iterator
or element loan cannot coexist with this exclusive source loan.

```cool
import vector "std/vector";
import option "std/option";
fn main() {
    var values = vector.create[i64]();
    values.append(10);
    values.append(20);
    {
        var iterator = values.iter_mut();
        while (iterator.remaining() > 0) {
            match (iterator.next()) {
                option.Option[&mut i64].None => { assert(false); }
                option.Option[&mut i64].Some(value) => { *value = *value + 1; }
            }
        }
    }
    assert(*values.at(0) == 11);
    assert(*values.at(1) == 21);
}
```

Owning elements may be modified, moved out or replaced through the returned
exclusive reference. Moving an owner leaves its slot empty. A pointer into an
owner remains protected while an index or assignment RHS is evaluated, even
when the owner is reached through a named, stored or returned reference. Moving
or replacing that owner during this pending access is rejected. Non-owning
loaded values release their address-evaluation loans after the load; loaded
owner handles retain them until the surrounding projection is finished.

`make exclusive-storage-test` checks 192 modeled read/write queries, 27 negative
cases and valid mixed/generic/array/enum reborrows on both frontends, five engines
and O2. The tracked-iteration suite covers shared and exclusive traversal at
12 chunk-boundary sizes, parent resumption, owner mutation/movement/replacement,
empty/exhausted iterators and 26 rejection cases. Its sanitizer mode instruments
Cool memory accesses and C runtime operations. `make owner-evaluation-test`
includes six further reference-mediated pending-owner rejection cases and valid
reads/updates through named and returned owner references.


## Tracked slices

Inside checked function bodies, `[]T` is an exclusive lexical view of contiguous
array storage. Its representation remains a pointer and length (16 bytes on
the supported host); borrowing does not allocate or copy elements. This is a
pre-1.0 change: code that reads or replaces the original array while its slice
is live now receives a conflict diagnostic. Use the slice during its scope,
then use the original after the scope ends.

```cool
fn tail(values: []i64) -> []i64 borrows(values) {
    return values[1:];
}
fn main() {
    var values = [3]i64{10, 20, 30};
    {
        let view = values[:];
        {
            let item = &mut view[1];
            assert(len(view) == 3);
            *item = 21;
        }
        {
            let rest = tail(view);
            rest[0] = 22;
        }
        view[2] = 31;
    }
    assert(values[1] == 22 && values[2] == 31);
}
```

Copying, passing and reslicing reborrow all possible source roots. Shared
`&view[index]` and exclusive `&mut view[index]` references retain those roots;
the parent resumes when their scopes end. `len` of a named slice observes only
its descriptor and is allowed while an element loan lives. A returned slice
requires a `borrows(...)` contract; multiple declared sources are conservatively
retained. Structs/enums/arrays containing slices follow the same rules, and
moving a value with owning fields must retain its contained slice provenance.
Slice elements still cannot contain borrowed storage.

Slices may borrow owned arrays and arrays of owners. The source cannot be moved
or freed while the slice lives. Elements may be moved out and replaced through
the slice with explicit `move`, just as through an exclusive element reference.
A pending pointer into an owning element prevents moving/replacing that owner
while evaluating an index or assignment RHS. A slice of a shared array reference
cannot grant write permission and is rejected; there is no separate read-only
slice type yet.

Slice variables and slice-containing local fields can be reassigned. The checker
conservatively retains both previous and new possible roots through the target
binding's lexical scope, including assignments inside a branch or loop. Assigning
a source whose local storage is nested more deeply than the destination is
rejected. Self-reslicing (`view = view[1:]`) preserves its original ancestry;
it does not introduce a cyclic parent loan. Replacing a slice with an empty
value does not end earlier loans. Lifetime-aware release of individual replaced
sources and mutable reference-field replacement remain future work.

`make slice-loans-test` checks 96 independently modeled source-set queries,
29 rejection cases, owned arrays/elements, computed element references,
self-reslicing, nested/branch/loop assignment, moved owning containers and
scope resumption. Both frontends and all five engines plus optimized native
output are exercised. `make slice-loans-sanitize-test` additionally instruments
Cool LLVM accesses with ASan and the C runtime with ASan/UBSan. The REPL test
checks that owned views protect their sources across inputs and release them
when explicitly forgotten.


## Persistent REPL loans

References, stored references and slices (including owned-array/owner-element
views) can live across REPL submissions. The checking rules are the same as in
function bodies. Top-level bindings live for the session; an explicit block
ends its local loans when the block ends. Reads and writes through a parent
remain restricted while a conflicting child loan lives.

```text
cool> var value = 10;
cool> let item = &mut value;
cool> *item = 20;
cool> value = 30;
error: access conflicts with a live scoped reference
cool> :forget item
cool> value = 30;
cool> value
30
```

`:forget name` removes a session binding and its held loans. Owning bindings
are destroyed immediately and exactly once. A binding with live source or
parent dependencies cannot be forgotten: forget dependent views first. Unknown
names and malformed commands leave bindings intact. The removed name can then
be declared again. Dead storage after the last surviving binding is reused,
including statement temporaries and failed new bindings. Surviving bindings
keep stable addresses. Dead session-local metadata is reclaimed, while surviving
loan roots and parent identities remain live even after their lexical blocks
end. Ordinary statement tokens are recycled after execution or rejection.
Interior storage holes are not yet reclaimed;
the existing register limit still applies to each
submission and its live storage. Raw pointers remain subject to explicit
unsafe lifetime obligations and must not access forgotten/reused storage.
The REPL reserves its internal `__session` function: user code cannot redefine
or call it. Ordinary source files may still use that identifier.

Input checking uses a copy of the live loan list. Syntax/type/checking failure
discards that copy and preserves existing bindings and loans. Successful
execution commits loans for surviving bindings. Runtime errors can occur after
an existing value has changed; they do **not** roll back those writes. Recovery
therefore preserves the candidate's possible roots for old surviving bindings,
including assignments that might not have executed yet, and discards loans
held only by failed new bindings. This conservative union can keep a source
borrowed until the holder is forgotten. A failing block still cannot store a
reference to its shorter-lived local storage into an outer binding.

`make repl-loans-test` exercises persistent exclusive/shared references, nested
reborrows, owned views, compile/runtime failures, `:forget` ordering, owner
cleanup and JIT/body replacement. Ten focused sessions and 288 independent
read/write permission queries run on both frontends. With
`make repl-loans-sanitize-test`, the self-hosted compiler's own LLVM loads/stores
are ASan-instrumented and its C host/runtime use ASan/UBSan, then the same tests
run against that compiler. These checks do not prove bounded metadata use in
long sessions, which remains release work. `make repl-storage-test` additionally
checks repeated large temporary/forgotten arrays beyond the former cumulative
slot limit, stable references, mixed owning/non-owning slot reuse and compile/
runtime rollback on both frontends. Completed and rejected submission bytecode
and its argument/scope allocations are reclaimed, including shared deferred
argument vectors. Submission AST nodes and coercion clones are reclaimed after
checking/execution; cached function/generic bodies and literal strings survive.
Bytecode call argument scratch uses the native stack, including error recovery.
Current function caches remain live; obsolete or rejected artifacts are reclaimed. `make repl-storage-sanitize-test` repeats
these checks on the ASan-instrumented compiler. Package loading is described
below.


`make repl-tokens-test` runs 100,000 submissions with surviving string values,
owning storage, functions and generic source, then checks partial lexing and
rejected-declaration recovery on both frontends. `make repl-tokens-sanitize-test`
adds the ASan-instrumented compiler. A single oversized input or too many retained
declarations can still exceed the token-table limit; it reports an error and
preserves the session. Normal statement history no longer consumes that limit.

String literals are immutable and remain valid throughout the session, including
when stored inside owners. Equal literals, including literals in function bodies,
share a stable allocation. Newly interned contents are discarded when checking
fails before execution. After execution begins, distinct contents remain valid
until session exit, including writes performed before a runtime failure. Live functions, types and import aliases keep the source needed for subsequent
compilation. Replaced-only declaration blocks are reclaimed and the remaining
tokens are compacted. A batch containing multiple declarations remains intact
while any function, type or alias still needs it. Distinct literals and other
auxiliary state still require a complete lifetime audit before the full
long-session release gate can close.


Function body replacement keeps stable function IDs, including callers already
compiled by the JIT. Successful replacement releases the old AST, local metadata,
bytecode and JIT mapping after user frames finish. Failed parsing/compilation or
execution releases newly staged artifacts and preserves previous function code.
Signature, borrow-contract, generic and foreign/exported C ABI mode changes
require a new session. Escaped string literals remain valid after replacement.
`make repl-functions-test` exercises repeated warm/cold replacement, failed generic
specialization and ID reuse, batch rollback, owner cleanup and C ABI rejection
on both frontends. It also exercises 100,000 method calls, unknown methods and
owner/member prefix collisions. `make repl-functions-sanitize-test` repeats these checks with
the ASan-instrumented compiler. `make repl-tokens-test` additionally replaces a
function 40,000 times beyond the former cumulative token limit, then checks
failed-replacement recovery, moved generic/type source, runtime diagnostics and
escaped strings. Package tests load aliases and generic library bodies after a
soon-to-be-discarded definition, compact that source and execute the imports
again, including a new specialization.


Temporary parser state (branch/loop move snapshots, generic bindings and match
coverage arrays) is discarded after each input, including rejected inputs.
Package manifest/source buffers and temporary fields have the same lifetime;
package names and diagnostic paths remain stable. Regressions include 100,000
branch submissions, 512 failed matches preserving an existing owner, and repeated
failed package loads with a large source comment followed by a successful retry.


Lazy type layouts participate in the same transaction. A failed layout can be
retried with a valid specialization. Unknown member type names are rejected
at declaration time even in unused generic aggregates. Rejected declarations
also restore completed layouts that were first computed while checking that input,
so their field types cannot accidentally refer to reused descriptor IDs. The
`repl-types-test` and `repl-types-sanitize-test` targets verify specialization retries, rejected-name reuse,
field reclamation, type ID reuse, owner destruction and staged text lifetime.


## Packages in the REPL

Run `cool repl` from the project directory and use ordinary imports. The driver
uses the same package graph, MVS selection, workspaces/local replacements,
checksums and vendoring rules as `cool run`/`cool check`. `cool repl --offline`
forbids fetching missing modules; `--frozen` also requires existing checksums.
Standard packages work without `cool.mod`. Directory packages still require a
consistent package declaration, and only public symbols can cross packages.

```text
cool> import vector "std/vector";
cool> var values = vector.create[i64]();
cool> values.append(42);
cool> let item = values.at(0);
cool> *item
42
cool> :forget item
cool> values.append(7);
cool> values.len()
2
```

Imports load on demand. The Cool frontend recognizes imports and parses/checks
all declarations; the Python driver resolves paths and supplies verified source
snapshots. Loading a package does not call its `main` or other functions.
Imported methods, generic types/functions and transitive dependencies work in
the persistent session. A second alias can refer to the same package without
loading its declarations twice.

A loaded package's content fingerprint is fixed for the session. Importing a
changed loaded package or dependency is rejected with a request to start a new
session; existing callables keep their previous definitions. Session-defined
function bodies retain their ordinary compatible-replacement rules. Failed
imports roll back newly staged packages, aliases, types and functions while
preserving existing variables and loans. Fixing a package that never loaded
successfully allows a later retry. Module resolution may still update
`cool.sum`, just as for an ordinary build/check; that verification record is
independent of whether source type checking succeeds.

Compiler binaries invoked directly support builtin `std/io` and `std/mem`
imports. Other packages require the `cool` driver and its private resolver
channel. Channel errors produce a recoverable import diagnostic. Source
snapshots retain original file paths for diagnostics and only one resolver
request's files remain on disk; the frontend owns the token storage needed for
later generic specialization. Loaded compiler metadata still occupies memory
until session end; this feature does not close the long-session resource gate.

`make repl-packages-test` covers standard/local packages, multiple files and
aliases, public/private visibility, methods/generics, MVS, offline/frozen and
tampered caches, closed-channel recovery, failed-load retry, changed source
rejection, JIT calls and restoration of the session namespace on both frontends.
`make repl-packages-sanitize-test` repeats the package sessions with an
ASan-instrumented self-hosted compiler and sanitized C host/runtime. Distribution
tests exercise project and standard imports from a read-only installed prefix
with no seed or working `make` command.

## References to slice descriptors

A named slice may be borrowed as `&[]T` or `&mut []T`. The reference protects
both its descriptor binding and the underlying elements. Shared descriptor
references allow `len(*ref)` and element reads, including shared element
references. Exclusive descriptor references allow element updates and exclusive
reborrows. Taking a shared descriptor reference does not permit copying the
exclusive slice value out of it or creating an exclusive reslice.

```cool
fn count(values: &[]i64) -> usize { return len(*values); }
fn increment(values: &mut []i64) {
    for (var i: usize = 0; i < len(*values); i = i + 1) {
        (*values)[i] = (*values)[i] + 1;
    }
}
```

`len(*ref)` reads the descriptor and may coexist with a direct element reborrow.
`len(slice)` requires access to the original descriptor, so it conflicts with a
live exclusive descriptor reference. Element loans still protect the entire
underlying root. Return contracts retain all selected roots conservatively:
`fn first(s: &mut []i64) -> &mut i64 borrows(s)` may retain an exclusive descriptor
anchor as well, so `len(*s)` can conflict while its returned element reference is
live. Projection-specific return contracts are not implemented.

Aggregates may combine slice fields, reference fields and owning fields;
borrowed heap payloads retain their external roots. Direct
references to these aggregates preserve physical and payload loans separately.
Slices of owning elements support reading, explicit moves and replacement through
an exclusive descriptor reference; moving their backing owner remains rejected.
Replacing a slice or slice-containing field through a reference is currently
rejected, because cross-call replacement lifetimes are not tracked. Ordinary
local descriptor reassignment retains the existing lifetime checks. Stored
`&[]T` fields, references to references, borrowed slice elements and
general replacement contracts still require further implementation.

`make slice-descriptors-test` verifies both frontends, five engines and O2,
31 negative programs, 30 independent permission-model queries and persistent
REPL loans. `make slice-descriptors-sanitize-test` adds an ASan compiler and
instrumented generated LLVM/C runtime checks.

## Reusing fragmented REPL storage

Forgetting a binding releases its storage even when newer bindings remain above
it. A later declaration may use that interior gap; live references and slices
continue to point to the same values. Contiguous allocation is still required,
and a single input's anonymous temporaries remain reserved until it completes.
Live data is not compacted or moved. The existing 65,536-slot limit still applies
to actual simultaneous storage plus bytecode registers; fragmentation without a
large enough contiguous gap can still reach that limit.

`make repl-holes-test` covers large interior array gaps, simultaneous arrays and
returned aggregates, repeated owner/type changes, compile/runtime rollback,
initialization failure over stale scalar bytes, live root rejection, persistent
slice descriptor references and anonymous match storage. Both frontends run the
eight focused sessions; `make repl-holes-sanitize-test` adds the ASan compiler.
The heap lifecycle regression compares 64/1,024 interior reuse and runtime-failure
histories while checking stable referenced values and zero user owners.

## Owning aggregates with stored borrows

```cool
struct Mixed { label: &i64; payload: own[i64]; }
fn identity(value: Mixed) -> Mixed borrows(value) { return move value; }
fn take(value: &mut Mixed) -> Mixed borrows(value) { return move *value; }
fn payload(value: &Mixed) -> &i64 borrows(value) { return &*(*value).payload; }
```

The outer struct, fixed array or enum stores borrowed handles; each owned
allocation may contain borrowed fields under the heap rules below. Moving it preserves the borrowed
handles' root sets and return regions. Loans into its own physical storage or
owned pointees prevent a move, including shared physical loans. The owned
payload getter above retains the receiver's physical root; a getter for `label`
retains the external referent. A by-value `Mixed` parameter cannot return a
reference into its owned payload, because that allocation is dropped on return.

Moving through `&mut` clears only owning subobjects of a borrowed aggregate.
References, slices, scalar fields and enum tags remain initialized in the source;
owned handles become empty and dereferencing them produces a checked fault.
The moved destination keeps its external loans. A retained exclusive reference
field cannot be used incompatibly with the destination's loan. Once the
latter's scope ends, the receiver's preserved borrowed fields can be used again.
Direct moved bindings still follow whole-root move checking, and reference fields
cannot be replaced. REPL dependents must be forgotten before their parent loan
holders; moving a value does not remove its lexical or persistent root record.

This supports nested ordinary aggregates and generic layouts, shared/exclusive
fields, arrays, named/anonymous enum matches and aggregates combining slices and
owners. Borrowed owning heaps are supported as described below; stored references
to borrowed pointees and general cross-call replacement lifetimes remain incomplete. `make mixed-owned-references-test` checks both
frontends, five engines and O2, zero leaked owners, checked empty-owner faults,
17 rejected programs, 14 independent permission queries and persistent REPL
roots. `make mixed-owned-references-sanitize-test` adds an ASan compiler and
instrumented LLVM runtime verification.

## Borrowed owning heaps

```cool
struct View { value: &i64; }
fn box(value: &i64) -> own[View] borrows(value) {
    return new[View](View { value: value });
}
fn unbox(box: own[View]) -> &i64 borrows(box) { return (*box).value; }
```

The owning handle protects the allocation; its payload's external references
protect their own roots. A move transports those external roots and clears the
old handle. It never drops the allocation being transported. A consumed owner
can yield an external reference, including an exclusive reference, under its
return contract. It cannot yield its own heap address. `&*owner` keeps the owning
root alive and prevents moving or replacing that root while the loan is live.
References through receivers retain conservative physical/payload root sets.

Recursive owned nominal layouts, nested owners, owning enum payloads, fixed
arrays and generic wrappers use the same rules. `new[&i64](&value)` is supported;
`new[View]()` is rejected because zero initialization cannot create a valid
scoped reference. Empty owner handles and empty slice descriptors can still be
initialized where the ordinary type rules permit them.

Local owner replacement may retain new external roots at the original binding's
lifetime marker. Earlier possible roots remain pinned conservatively until that
binding ends. A borrow from a shorter block cannot be installed into a longer
lived heap. Reference-field assignment and cross-call borrowed storage
replacement through a receiver remain rejected. Heap storage containing a
reference to an already-borrowed pointee is also still rejected; arbitrary nested
stored lifetimes require further work.

`make heap-borrows-test` exercises both frontends, five engines and O2, recursive
and generic owners, consumed exclusive getters, nested moves and enum cleanup, a 64-link chain with exactly 65 live owners and
zero after scope exit, twenty rejected programs, twelve independent capability
queries and persistent REPL roots. `make heap-borrows-sanitize-test` adds an ASan
compiler and LLVM load/store plus C runtime ASan/UBSan instrumentation.


## Mutable local reference replacement

A `var` reference binding, reference field or fixed-array element can receive a
new initialized reference. This includes generic/enum containers and fields in
locally owned heaps. Physical storage must be mutable and unborrowed, and every
new root must live at least as long as the original binding. Return contracts
include all possible roots acquired by replacement.

```cool
var x=7;
var y=8;
{
    var view=&x;
    view=&y;
    assert(*view==8);
}
x=9;
y=10;
```

Possible old/new roots remain protected until the binding's scope ends (or the
REPL binding is forgotten). Replacement does not yet shorten the old root's
loan. Branches, loops and nested blocks retain the union at the original binding
marker. Installing a reference to a shorter-lived nested local is rejected.
Replacing a binding is distinct from mutating its referent: a mutable binding
of type `&T` can be replaced, while writes through its shared referent remain
forbidden. Live references to the binding/container itself prevent replacement.

Identical retained root/parent/mode/layer records are merged, so repeating the
same replacement does not retain one loan record per input. A failed RHS leaves the old reference value when the store was not executed.
REPL checking failures discard staged loans; runtime failures retain candidate
roots conservatively because earlier stores in the input may have executed.
Replacing borrowed storage through `&mut` receivers, multi-layer stored borrowed
pointees and borrowed slice elements still require further lifetime work.
