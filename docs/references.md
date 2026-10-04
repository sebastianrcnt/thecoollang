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
block ends, the parent can be used again. Reference bindings currently cannot
be reassigned. `move` of a reference is also a reborrow, not ownership transfer.
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

- Shared references can be stored in non-owning, slice-free structs, arrays and
  enums, as described below. Stored exclusive references, reference-containing
  owned allocations and aggregates mixing references with owners/slices are
  still rejected. Reassignment of borrowed bindings/fields and references to
  storage already containing references/slices require further tracking.
- Existing mutable slices cannot share a root with references within one
  function, even in disjoint scopes. References into aliasable slice storage are
  rejected. Slice and reference provenance must be integrated before relaxing
  these restrictions.
- REPL statement submissions containing references are rejected because loans
  are not yet retained across submissions. Compiled function bodies are checked.
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
anchor's loan. Merely naming an unrelated anchor does not make a pointer valid.
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
Vector `cursor`/`next` remain a raw, manually managed iteration API until stored
reference support permits a tracked iterator. Cursor advancement still needs
unsafe raw access and removal/clear/destruction invalidates raw cursors. File
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
union deduplication. Stored shared references extend this model below; borrowed
slice integration and persistent REPL loans remain separate work.


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
`PairView {}` cannot manufacture null references. Containers and reference
fields cannot be reassigned, even when declared `var`; ordinary scalar fields
can be changed when no conflicting loan exists. These restrictions prevent a
shorter-lived reference from being written into an older container. Nested
borrows such as `&PairView` and stored `&mut T` remain unsupported, so this is
not yet the tracked mutable iterator API or full stored-reference gate.

`make stored-references-test` checks nested structs/arrays/enums, generic
copies, methods, computed projections, match evaluation, empty results, owner
lifetimes and scope release on both frontends, all five engines and O2. It also
checks 40 rejection cases and 144 independently modeled source-set queries,
plus actual imported `std/option` reference payloads and fallback results.

`make stored-references-sanitize-test` additionally marks generated Cool LLVM
functions for ASan, verifies inserted load checks and links the instrumented
program against the ASan/UBSan C runtime. This checks the executable fixtures;
it is not a proof of all borrowing rules.
