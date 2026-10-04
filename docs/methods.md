# Methods

Methods belong to a nominal struct or enum in the package that declares the
type. The receiver is an explicit first parameter; the call supplies it before
other arguments. Methods lower to ordinary typed calls and use the same
ownership, borrow, defer, execution and C-runtime rules.

```cool
struct Point { x: i64; y: i64; }
fn Point.sum(self: &Point) -> i64 {
    return (*self).x + (*self).y;
}
fn Point.add(self: &mut Point, delta: i64) {
    (*self).x = (*self).x + delta;
}
fn Point.xref(self: &mut Point) -> &mut i64 borrows(self) {
    return &mut (*self).x;
}
fn main() {
    var point = Point { x: 1, y: 2 };
    point.add(4);
    assert(point.sum() == 7);
    *point.xref() = 8;
    assert(point.sum() == 10);
}
```

The receiver name is ordinary (it need not be `self`). The declaration owner and
receiver nominal type must agree. A type's fields/enum variants cannot have the
same name as a method. There is no overloading: a type has one method with each
name, and duplicate declarations are rejected. Different types or packages can
use the same method name independently. Only `pub` methods are callable from
other packages. Methods can access their own package's private fields. Foreign
extension methods, C ABI method declarations and bound-method function values
are not supported. Calls currently use instance syntax, not `Type.method(...)`.

## Receiver modes

| First parameter | Instance call behavior |
| --- | --- |
| `self: Type` | Pass a value; ordinary non-owning values copy, owning values require explicit `move` |
| `self: &Type` | Borrow a stable receiver as shared, or pass a matching reference |
| `self: &mut Type` | Borrow a mutable stable receiver exclusively, or pass a matching exclusive reference |
| `self: own[Type]` | Consume an explicit owning receiver, such as `(move owner).take()` |

For borrowed receivers, `own[Type]` is dereferenced automatically, while keeping
the owner as the loan root. An existing named exclusive reference may be
reborrowed shared for a read-only method. A `let` value cannot satisfy a mutable
receiver; an owning pointee follows the same mutation rule as explicit owner
dereference. Non-owning value receivers also copy through references/owners. Auto-borrow
never implicitly moves an owning value. Raw pointer
receivers need an explicit dereference in `unsafe`.

The receiver is evaluated once, before explicit arguments. An implicit borrow
protects the receiver while those arguments are evaluated. A returned reference
keeps the original receiver root borrowed, preventing invalidating operations:

```cool
// Rejected: the element remains borrowed.
let element = values.at(0);
values.clear();
```

The current reference restrictions still apply. A shared/exclusive receiver
borrow requires a stable tracked place; borrowing a fresh by-value temporary is
not implemented. Reference-returning calls can chain directly, including shared reborrows of
computed exclusive receivers such as `map.at_mut(&key).scalar_len()`. Every
possible source in a multi-parameter return contract remains protected. Stored references,
slice-loan integration and top-level persistent REPL loans remain open work;
methods do not bypass these checks. Compiled functions containing methods can
be used and replaced in the REPL under its existing signature rules.

## Generic types and methods

Declare the type's parameters first, with the same names and order. Instance
calls obtain those arguments from the receiver; extra method parameters are
specified explicitly at the call:

```cool
struct Box[T] { value: T; }
fn Box.get[T](self: &Box[T]) -> &T borrows(self) {
    return &(*self).value;
}
fn Box.replace[T](self: &mut Box[T], value: T) {
    (*self).value = move value;
}
fn Box.choose[T, U](self: &Box[T], value: U) -> U {
    return move value;
}
fn main() {
    var box = Box[i64] { value: 42 };
    assert(*box.get() == 42);
    box.replace(19);
    assert(box.choose[u8](255) == 255);
}
```

Generic bodies/signatures are checked when specialized, as for ordinary generic
functions. The declaration's receiver-parameter prefix is checked immediately.
The total function argument limit includes the receiver. No new runtime
method table, virtual dispatch or allocation is introduced.

## Collections and tools

`Vector[T]` supplies `len`, `append`, `pop`, `clear`, `at`, `at_mut`.
`Map[V]` supplies `len`, `contains`, `insert`, `remove`, `at`, `at_mut`, `clear`,
`keys`. `Text` supplies `byte_len`, `scalar_len`, `scalar_at`, `as_bytes`, `clone`,
`append`, `append_literal`, `append_scalar`, `clear`, `equal`, `compare`,
`starts_with`, `ends_with`. Their free-function forms remain available with
identical borrow/ownership/error behavior. Factories remain package functions:

```cool
import vector "std/vector";
fn main() {
    var values = vector.create[i64]();
    values.append(42);
    assert(values.len() == 1);
    assert(*values.at(0) == 42);
}
```

Formatting preserves method declarations/calls. `cool doc` includes public
method signatures and excludes private methods. `make methods-test` checks both
frontends, five engines, optimized native output, imported same-named types,
visibility, single receiver evaluation, extra generic arguments, explicit
ownership, returned loans, collection chains, formatting, docs and REPL method
replacement. Negative cases cover receiver/type/arity/visibility/ownership and
loan conflicts. The full regression and self-hosting suites remain required for
shared parser changes.
