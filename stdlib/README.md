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
| `std/map` | ordered text-key `Map[V]`, `create`, `len`, `contains`, `insert`, `remove`, `at`, `at_mut`, `clear`, independent sorted `keys` |
| `std/json` | owned JSON trees, strict parsing, deterministic encoding, exact number text, borrowed access and mutation |
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
Additional mandatory core APIs remain in development under
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


## Ordered maps

`std/map.Map[V]` owns UTF-8 `Text` keys and generic values. It uses an AVL tree:
lookup, insertion and removal perform O(log n) key comparisons regardless of
insertion order. Comparisons use `text.compare` bytewise ordering and cost up to
the common key length. This is a text-key ordered map, not a hash map or an
arbitrary-key map. Empty and embedded-NUL keys are distinct and supported.

```cool
import map "std/map";
import text "std/text";
import result "std/result";
import option "std/option";
fn key(value: string) -> text.Text {
    return result.value_or[text.Text, text.Utf8Error](
        text.from_literal(value), text.create());
}
fn main() {
    var counts = map.create[i64]();
    map.insert[i64](&mut counts, key("hello"), 1);
    let search = key("hello");
    *map.at_mut[i64](&mut counts, &search) = 2;
    assert(*map.at[i64](&counts, &search) == 2);
    assert(option.value_or[i64](map.remove[i64](&mut counts, &search), 0) == 2);
}
```

`insert` consumes its key/value and returns `Option[V]` containing the previous
value on replacement. Replacing a value retains the existing equal key and
releases the incoming key. `remove` returns ownership of the removed value;
missing keys return `None`. Ignored owning results are automatically released.
`len` is O(1). `clear` and normal destruction release every node, key and value.

`at`/`at_mut` return shared/exclusive value references with `borrows(map)`.
Missing keys trap; call `contains` when absence is expected. A live value loan
prevents structural changes or incompatible access to the map. Like vectors,
map values cannot yet contain borrowed references. `keys` returns an independent
owned `Vector[Text]` in sorted order; it remains valid after changing or dropping
the map and takes O(n + total key bytes) time and memory. It is a copied snapshot,
not a replacement for the still-planned tracked iterator API.

`make map-test` checks public APIs and two deterministic Python-dictionary
models. A test-only companion module independently checks all ordering bounds,
AVL balance, stored heights and node counts after every operation. Tests cover
all four rotation patterns, two-child deletion, sorted insertion, random
replacement/removal/clear/moves, exact live-owner counts, narrow integers,
floats, owned values and loan conflicts on five engines plus O2.
`make map-sanitize-test` also instruments Cool memory accesses with ASan and the
C runtime with ASan/UBSan. Generated projects remain in `build/map-tests/` for
reproduction; additional seeds/steps can be supplied to `tools/test_map.py`.

## JSON

`std/json` parses strict UTF-8 JSON into an owning `Value` tree. `parse(&Text)`
returns `Result[own[Value], ParseError]`; `parse_bytes(Vector[u8])` consumes and
validates raw bytes first. Parsed strings, numbers and object keys own their
storage independently of the input. Both success and failure release temporary
buffers and discarded subtrees. Errors contain a UTF-8 **byte offset** at which
failure was detected and a `Syntax`, `InvalidUtf8` or `DepthLimit` kind.

```cool
import json "std/json";
import text "std/text";
import result "std/result";
fn main() {
    let input = result.value_or[text.Text, text.Utf8Error](
        text.from_literal("[true,42]"), text.create());
    let value = result.value_or[own[json.Value], json.ParseError](
        json.parse(&input), json.null_value());
    assert(json.array_len(&*value) == 2);
    {
        let number = json.array_at(&*value, 1);
        assert(text.byte_len(json.number_text(number)) == 2);
    }
    json.array_push(&mut *value, json.integer_value(99));
    let encoded = result.value_or[text.Text, json.ErrorKind](
        json.encode(&*value), text.create());
    assert(text.byte_len(&encoded) == 12);
}
```

`kind` distinguishes Null, Boolean, Number, String, Array and Object. Use
`as_bool`, `as_text`, `number_text`, `array_len`/`array_at` and
`object_len`/`object_contains`/`object_at` to inspect matching kinds. Access with
an incorrect kind, absent key or invalid array index traps. Borrowed child/text
access prevents mutation or movement of the parent for the loan's scope.
Reference-returning calls may be nested directly, for example
`text.byte_len(json.number_text(json.array_at(&*value, 1)))`; the original tree
remains borrowed throughout the expression.

Construct trees with `null_value`, `boolean_value`, `integer_value`,
`number_value(Text)`, `string_value(Text)`, `array_value` and `object_value`.
`number_value` validates JSON number syntax and returns a parsing result; it
accepts surrounding JSON whitespace and rejects a non-number with
`ExpectedNumber`. JSON number lexemes retain all digits, exponent spelling and
negative zero; there is no implicit floating-point conversion or rounding.

`array_push` and `object_insert` consume a child owner (empty owners trap).
`array_pop` and `object_remove` return `Option[own[Value]]`; replacing an existing
object key returns the previous child. `array_at_mut` and `object_at_mut` lend
exclusive access to a child, allowing nested array/object edits. `object_keys`
returns an independent sorted `Vector[Text]` snapshot. Object keys may contain
NUL, and duplicate keys during parsing use the last value.

`encode` produces compact UTF-8 `Text`, sorting object keys by UTF-8 bytes. It
escapes quotes, backslashes and control characters; supplementary Unicode and
escaped surrogate pairs round-trip, while unpaired surrogates are rejected.
This deterministic encoding is not a canonical JSON signing format: number
lexemes are deliberately preserved. Nesting is limited to 128 edges from the
root by both parser and encoder. Encoding an excessively deep constructed tree
returns `DepthLimit` and frees partial output. Array traversal is linear;
ordered-object encoding takes O(n log n) key comparisons plus output work.

`make json-test` uses Python's independent JSON decoder with exact Decimal
numbers on 105 fixed/seeded cases, all five engines and optimized native output.
It checks malformed syntax/UTF-8, byte offsets, depth limits, NUL/Unicode,
duplicate-key destruction, tree mutation, safe loan rejection and zero leaked
owners. `make json-sanitize-test` additionally instruments generated Cool memory
accesses with ASan and the C runtime with ASan/UBSan.
