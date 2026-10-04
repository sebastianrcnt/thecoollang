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
| `std/text` | owning UTF-8 `Text`, strict validation, byte/scalar lengths, scalar access, append/clone/clear, byte conversion, ordering/prefix/suffix |
| `std/math` | numeric `min`, `max`, `clamp`; `add_i64`, `divide_i64` returning arithmetic errors |
| `std/vector` | move-only `Vector[T]`, `create`, `len`, `append`, `pop`, `at`, `at_mut`, `clear`; raw `cursor`/`next` |
| `std/fs` | binary `read`/`write` with `Result`, supporting embedded NUL bytes; errors are Darwin errno values |
| `std/os` | `arg_count`, `arg`; executable/runner flags excluded |

## Ownership and low-level interfaces

```cool
import vector "std/vector";
import option "std/option";
fn main() {
    var values = vector.create[own[i64]]();
    vector.append[own[i64]](&mut values, new[i64](42));
    let value = option.value_or[own[i64]](
        vector.pop[own[i64]](&mut values), new[i64](0));
    assert(*value == 42);
}
```

Vectors own fixed-size chunks and all owning elements. Append is amortized O(1)
and does not relocate existing elements; pop is O(1). `at` checks the index and
walks to its chunk; the cursor visits all elements in O(n). `clear` removes chunks
iteratively. Moving a vector transfers the entire owned chain. Automatic scope
cleanup also releases the chain and elements.

Mutating collection APIs accept exclusive references; length and read-only
indexing accept shared references. `at`/`at_mut` return checked element loans
that prevent incompatible access, vector movement, removal or clear. These
ordinary operations require no `unsafe`. Raw `cursor`/`next` still require
manual lifetime care and unsafe pointer access. Chunks cannot contain borrowed
references until stored-loan support is implemented.

`Result`/`Option` helpers take values by value. An owning argument requires
`move`; an unused fallback or consumed payload is released. Generic arithmetic
is checked at specialization. Ordinary language arithmetic still wraps;
`std/math` is an opt-in checked alternative.

Legacy `string` values are immutable NUL-terminated byte strings. String indexing/counting here uses
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
networking, async IO and Unicode normalization are outside the first release.
Maps, serialization and other mandatory core APIs remain in development under
[the 1.0 release contract](../docs/release-1.0.md).


## Owning UTF-8 text

`std/text.Text` owns its bytes and validates UTF-8 strictly. `from_bytes` consumes
`Vector[u8]` without copying its storage and returns `Result[Text, Utf8Error]`;
rejected buffers are released. `Utf8Error.Invalid(offset)` identifies the first
invalid byte, while `Truncated(offset)` identifies the end of incomplete input.
Overlong encodings, surrogate scalars and values above U+10FFFF are rejected.
`from_literal` copies a legacy NUL-terminated string and validates it; use
`from_bytes` to preserve embedded NULs.

```cool
import text "std/text";
import result "std/result";
fn main() {
    var message = result.value_or[text.Text, text.Utf8Error](
        text.from_literal("안녕"), text.create());
    assert(text.append_scalar(&mut message, 128578));
    assert(text.scalar_len(&message) == 3);
    assert(text.byte_len(&message) == 10);
    let copy = text.clone(&message);
    assert(text.equal(&copy, &message));
}
```

`byte_len` and `scalar_len` are O(1). Scalar counts are Unicode code points,
not grapheme clusters; normalization is not performed. `scalar_at` scans to the
requested scalar and checks bounds. `validate`, `append`, `clone`, `equal`,
`compare`, `starts_with` and `ends_with` traverse bytes linearly. `compare`
returns -1, 0 or 1 using bytewise ordering. `append_literal` validates before
changing the destination; an invalid `append_scalar` returns false without
changing it. Self-append requires an explicit clone because shared and exclusive
loans of the same text conflict.

`as_bytes(&text)` returns a shared vector reference protected by the text's loan;
`into_bytes(move text)` transfers ownership. `fs.write(path, text.as_bytes(&text))`
preserves every byte, including NULs. There is no conversion to a lifetime-free
`string` pointing into owned text. `clear` releases chunks and restores empty
text. Text falls under normal move-only ownership and automatic destruction.

`make text-test` compares 127 fixed/seeded inputs with Python's strict UTF-8
decoder across five engines and O2, including every decoded scalar, 12 KiB growth,
file round trips and allocation counts. `make text-sanitize-test` also instruments
Cool output with ASan and the C runtime with ASan/UBSan.
