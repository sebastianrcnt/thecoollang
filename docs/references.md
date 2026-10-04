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
rejected. Callers currently require one declared source and a named reference
or direct borrow as that argument. A returned field reference keeps the entire
source root borrowed.

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

- References stored in structs, arrays, enums or owning storage are rejected.
  References to storage already containing borrowed slices/references are also
  rejected. These require a complete graph of stored loans and escape checks.
- Existing mutable slices cannot share a root with references within one
  function, even in disjoint scopes. References into aliasable slice storage are
  rejected. Slice and reference provenance must be integrated before relaxing
  these restrictions.
- REPL statement submissions containing references are rejected because loans
  are not yet retained across submissions. Compiled function bodies are checked.
- Reference calls with multiple return sources or nested computed return-source
  arguments are rejected. References need richer provenance sets for these.
- There is no automatic field dereference, reference coercion, lifetime syntax,
  method receiver syntax or borrow-aware replacement for every collection API.

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
