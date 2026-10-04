# Standard library

These directory packages use ordinary Cool source and the same frontend as user
programs. `std/io` and `std/mem` are compiler/runtime primitives; the other
packages are bundled sources and need no module download.

| Package | API |
| --- | --- |
| `std/io` | `print`, `println` for scalar values and strings |
| `std/mem` | unsafe `alloc`, `free`, `copy`; diagnostic `owner_count` |
| `std/result` | `Result[T,E]`, `is_ok`, `value_or` |
| `std/option` | `Option[T]`, `is_some`, `value_or` |
| `std/slice` | generic `fill`, `reverse`, `tail`, `take`; checked return borrow contracts |
| `std/strings` | UTF-8 byte `length`, `byte_at`, `equal`, `starts_with`, `ends_with`; checked decimal `parse_i64` |
| `std/math` | numeric `min`, `max`, `clamp`; `add_i64`, `divide_i64` returning arithmetic errors |
| `std/vector` | move-only `Vector[T]`, `create`, `len`, `append`, `pop`, `at`, `clear`; raw `cursor`/`next` |
| `std/fs` | binary `read`/`write` with `Result`, supporting embedded NUL bytes; errors are Darwin errno values |
| `std/os` | `arg_count`, `arg`; executable/runner flags excluded |

## Ownership and low-level interfaces

```cool
import vector "std/vector";
import option "std/option";
fn main() {
    var values = vector.create[own[i64]]();
    unsafe {
        vector.append[own[i64]](&values, new[i64](42));
        let value = option.value_or[own[i64]](
            vector.pop[own[i64]](&values), new[i64](0));
        assert(*value == 42);
    }
}
```

Vectors own fixed-size chunks and all owning elements. Append is amortized O(1)
and does not relocate existing elements; pop is O(1). `at` checks the index and
walks to its chunk; the cursor visits all elements in O(n). `clear` removes chunks
iteratively. Moving a vector transfers the entire owned chain. Automatic scope
cleanup also releases the chain and elements.

Mutating collection APIs accept explicit raw pointers, so taking an address and
reading a cursor result require `unsafe`. Pointer/cursor lifetime remains the
caller's obligation: removal, clear and destruction can invalidate pointers.
These interfaces do not pretend to provide scoped exclusive loans. Chunks
cannot contain borrowed slices, matching the language's owner restrictions.

`Result`/`Option` helpers take values by value. An owning argument requires
`move`; an unused fallback or consumed payload is released. Generic arithmetic
is checked at specialization. Ordinary language arithmetic still wraps;
`std/math` is an opt-in checked alternative.

Strings are immutable NUL-terminated text. String indexing/counting here uses
UTF-8 bytes, not Unicode graphemes. `parse_i64` accepts an optional sign and
ASCII decimal digits, rejects empty/invalid input and detects both signed range
boundaries. Binary data belongs in `Vector[u8]`. Raw `cast[string](pointer)` is
unsafe and requires a live, NUL-terminated allocation.

```sh
cool run program.cool -- first "한글" --flag
cool build program.cool -o program
./program first "한글" --flag
make stdlib-test
```

The same argument values reach tree, bytecode, native JIT, LLVM AOT/JIT and
standalone output. Filesystem read errors release intermediate owned buffers;
write errors and close/flush errors are returned. Paths use the current working
directory. This is a core library, not a claim of Go standard-library parity:
networking, async IO, Unicode normalization, hash maps and serialization remain
future extensions.
