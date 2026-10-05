# Cool language specification — 1.0 draft 33

Status: **partial specification under implementation audit**. This document does
not declare the language complete or freeze the 1.0 contract. It starts a
versioned specification series; later draft revisions must record changed
language decisions. See [compatibility](compatibility.md) for the proposed freeze
policy and [release gates](release-1.0.md) for remaining acceptance work.

## Audited lexical core

Source is well-formed UTF-8. Overlong encodings, isolated continuation bytes,
truncated sequences, surrogate code points and values above U+10FFFF are errors
anywhere in the input, including comments and string literals. Validation reports
the first invalid sequence at its leading byte before tokenization or execution.
Unicode scalar values in comments/literals are preserved without normalization.
Identifiers remain ASCII; valid Unicode encoding does not make every scalar a
valid token. A leading BOM is not ignored as whitespace. LF advances the source
line; CR is whitespace outside literals and does not independently advance it.

Source uses ASCII identifier characters: a letter or `_`, followed by letters,
digits or `_`. Keywords are recognized contextually by the parser; do not infer
that every keyword spelling is valid as a binding in every grammatical position.
Spaces, tabs, CR and LF separate tokens. `//` comments extend to the next newline;
`/* ... */` comments end at the first closing delimiter and do not nest.

External source and REPL submissions are interpreted using their actual byte
length. An embedded NUL byte is an error anywhere in the input, including inside
comments and string literals; it never terminates a source file early. Bundle
and REPL package manifests follow the same rule. REPL rejection happens before
executing any prefix, and command matching cannot treat `:quit` followed by a
NUL and extra bytes as a quit command. Native diagnostic offsets are zero-based
byte ranges; native line and column numbers are one-based, with byte columns.
The editor translates these ranges to UTF-16 positions. `make source-utf8-test`
checks whole-input UTF-8 validity, including byte ranges, formatter preservation
and REPL recovery. `make input-bytes-test` covers NUL rejection, formatter file
preservation, byte ranges and REPL recovery on both frontends.

A string literal is enclosed in double quotes. Supported escapes are `\n`, `\t`,
`\r`, `\\` and `\"`. An unescaped LF inside a string, an unknown escape, or a
missing closing quote is a compile-time error. Runtime `string` values denote immutable
literal text; owned/validated UTF-8 text is a separate `std/text` facility. This
lexical description does not claim Unicode identifier or normalization support.

Integer token forms use decimal digits, `0x` hexadecimal digits or `0b` binary
digits. Hexadecimal digit letters may be uppercase or lowercase; the prefixes
are lowercase. Every integer token must contain at least one digit in its base.
Underscores do not contribute a digit or value. In particular, `0x`, `0x_`,
`0x___`, `0b`, and `0b___` are errors, not zero. Invalid base digits and identifier
characters appended to a numeric token are errors. Values exceeding `u64` are
rejected before type checking. A leading minus is an expression operator,
including the special representable minimum signed-i64 case.

The current draft permits repeated, leading-after-prefix and trailing integer
underscores when at least one real digit exists: `0x_FF_`, `0b_10__01_`, and
`1__234_` have values 255, 9, and 1234. This permissive separator placement is an
explicit pre-freeze decision to review, not an undocumented assumption.

Decimal floating tokens use the following grammar. `digit` is an ASCII decimal
digit; brackets mean an optional production and braces mean repetition.

```ebnf
digits         = digit, { digit } ;
exponent       = ("e" | "E"), [ "+" | "-" ], digits ;
floating_token = digits, ".", digits, [ exponent ]
               | digits, exponent ;
```

Leading zeroes are allowed. Both sides of the decimal point require a digit;
`.5`, `1.` and `1.e2` are not floating tokens. An exponent requires digits after
its optional sign. Floating tokens do not permit underscores, type suffixes,
hexadecimal/binary significands or hexadecimal exponents. A leading minus is a
separate unary operator. Examples are `0.0`, `001.25`, `1e3`, and `1.5E-2`.
The complete token's finite binary64 value determines its range validity, not
the size of an integer prefix: `18446744073709551616.0` is valid even though
`18446744073709551616` is outside the integer literal range. The lexer must finish
classifying the token before reporting integer accumulator overflow. The
[floating range rules](#floating-conversions-and-literal-range) include subnormals
and rejection of nonzero underflow to zero or overflow to infinity.

`make float-literals-test` covers this grammar, integer/float classification,
long decimal significands with compensating exponents, integer overflow
rejection, all execution engines and formatter preservation on both frontends.

`make integer-tokens-test` checks independently computed integer values and
malformed tokens on both frontends, with tree, bytecode and native-JIT execution
for valid cases. The broader language suite covers LLVM and numerical behavior.

## Declaration and type forms

The following EBNF specifies individual top-level forms. `identifier` follows
the lexical identifier rule; contextual parser words still have their grammatical
meaning. `string_token` denotes a quoted string token. Source assembly constraints
are defined in the following section.
`block` is the braced statement sequence defined below.

```ebnf
package_decl   = "package", identifier, ";" ;
import_decl    = "import", [ identifier ], string_token, ";" ;
generic_names  = "[", identifier, { ",", identifier }, "]" ;
type_arguments = "[", type, { ",", type }, "]" ;
struct_decl    = [ "pub" ], "struct", identifier, [ generic_names ],
                 "{", { field }, "}", [ ";" ] ;
field          = [ "pub" ], identifier, ":", type, ";" ;
enum_decl      = [ "pub" ], "enum", identifier, [ generic_names ],
                 "{", variant, { variant }, "}", [ ";" ] ;
variant        = [ "pub" ], identifier, [ "(", type, ")" ], ";" ;
function_name  = identifier, [ ".", identifier ] ;
parameter      = identifier, ":", type ;
parameters     = "(", [ parameter, { ",", parameter } ], ")" ;
result         = "->", type ;
borrow_contract = "borrows", "(", [ identifier, { ",", identifier } ], ")" ;
store_contract = "stores", "(", identifier, ",", identifier, ")" ;
function_decl  = [ "pub" ], "fn", function_name, [ generic_names ],
                 parameters, [ result ], [ borrow_contract ], { store_contract }, block ;
extern_decl    = [ "pub" ], "extern", '"C"', "fn", identifier,
                 parameters, [ result ], [ borrow_contract ], ";" ;
export_decl    = [ "pub" ], "export", '"C"', "fn", identifier,
                 parameters, [ result ], [ borrow_contract ], block ;
type           = primitive | named_type | "*", type | "&", [ "mut" ], type
               | "own", "[", type, "]" | "[", integer_token, "]", type
               | "[", "]", type ;
named_type     = identifier, [ ".", identifier ], [ type_arguments ] ;
primitive      = "void" | "bool" | "string" | "i8" | "i16" | "i32" | "i64"
               | "u8" | "u16" | "u32" | "u64" | "isize" | "usize"
               | "f32" | "f64" ;
```

A named type can also be a bound generic parameter. Type arguments apply to a
generic nominal type and must match its parameter count; they are not optional
in use merely because the EBNF also covers non-generic names. Arrays use a
single nonnegative integer token as their length, not a constant expression.
An owner or reference wraps its following type; slices are written `[]T` and
fixed arrays `[N]T`. Nesting is grammatical, but the documented borrowed-storage
restrictions still apply. `void` denotes no value and is permitted as a function result or raw-pointer
element. An explicit enum variant payload `(void)` denotes a unit variant,
equivalent to omitting the payload. `void` is not a struct field, parameter,
array/slice/owner/reference element or generic type argument.

Struct fields and enum variants have distinct names within their declaration.
Enums require at least one variant; structs may be empty. A variant has zero or
one payload type. Struct fields are package-private unless marked `pub`; enum
variants are public within an accessible enum type. Declaring a type public
does not make its private struct fields public. Nominal types are collected
before layout, allowing forward references; recursive by-value layout is an
error and requires indirection. Type names cannot redefine primitive names.
Functions and nominal types cannot share a name in a package; function overloads
by signature are not supported.

Parameter names are unique in each signature, including extern declarations.
Every parameter has an explicit type. Omitting a result means `void`. Parameter,
generic-name, type-argument and borrow-contract lists do not allow trailing
commas. Generic parameter names are unique; ordinary generic function calls
require explicit type arguments. A method name is `Owner.member`, with a nominal
owner declared in the same package and an explicit first receiver parameter.
Method receiver adaptation and generic inference follow [methods](methods.md).
A borrowed result requires an explicit borrow contract naming permitted parameter
sources; actual lifetime/loan validation follows [references](references.md).

`extern "C"` declares an externally supplied function and ends with a semicolon;
`export "C"` defines a body with a C entry point. These forms cannot be generic
or methods. Their supported ABI uses scalar values and raw pointers, with no
by-value aggregates or language `string` values. `pub` controls package access
independently of C linkage. Ordinary Cool functions have a body; C-style separate
prototypes, default parameters, variadic parameters, type aliases and top-level
variable declarations are not supplied by these forms.

Current checked implementation limits include eight generic parameters/arguments,
32 function parameters, array lengths up to 65,536, and aggregate layouts up to
512 KiB. These are resource limits, not permission to accept malformed syntax.
Generic function signature syntax, unique parameter names, parameter/type-argument
counts and names in borrow contracts are checked when declared, including unused
templates. Signature type names resolve to a type parameter, builtin or declared
nominal type; qualified names respect per-file imports and public visibility.
Nominal type argument counts are checked without constructing concrete layouts.
Type names declared later in the package are available. The preflight rejects
actual `void` parameters, sequence/reference elements and generic arguments;
`*void` and a type parameter named `void` retain their ordinary meanings. Array
lengths must be in 0..65,536 even in unused signatures. Template signature type syntax is limited to 256 nested type operators
or argument lists. Concrete type substitution, layout, borrowed-result contracts
and body semantics are still checked on instantiation. Unused function bodies
are parsed for statement/expression grammar after declaration collection, without
inventing concrete types: missing initializers/operands, malformed calls, lists,
indexing, conditions, loop headers and match arms are errors before any call.
Loop control must be inside a loop. This syntax pass has a 256-level nesting
budget and room for 4,096 simultaneously tracked parameter/local names. It tracks
block, for and match scopes so locals may shadow file import aliases. Expression
root names resolve against lexical scope, generic parameters and collected
type/function names; qualified symbols must be public. Member resolution, operand
types, return coverage, moves and loans still require specialization; complete
semantic validation of unused templates remains work.

Generic nominal declarations also validate fields and variants before any
instantiation: names must be unique, delimiters must follow the declaration
production, field types cannot be bare builtin `void`, and enums require at
least one variant. Field/payload type syntax resolves nominal names, privacy,
generic arity and literal array limits using the template parameters in scope.
As with function signatures, a parameter named `void` shadows the builtin.
An explicit enum payload `(void)` continues to denote a payload-free variant,
matching concrete layout parsing. This preflight does not materialize field
layouts or certify dependent size, recursion, reference storage or lifetimes;
concrete instantiation still runs those checks.

`make template-aggregate-test` exercises forward types and concrete execution on
five engines plus optimized binaries, rejects 34 unused malformed declarations,
checks imported privacy/arity and verifies REPL rollback after rejection.

`make declarations-test` covers 20 valid declaration/type/boundary cases and
87 rejections, including duplicate extern/ordinary/export/unused-generic
parameters, duplicate nominal members, malformed template signatures, invalid C
signatures, method owners, borrow contracts and implementation limits. Four
additional bundle cases check qualified type visibility and argument counts. REPL
recovery also verifies that a rejected template does not reserve its name or
change existing values, on both frontends.
The wider package/method/reference suites cover visibility and lifetime behavior.
`make template-body-test` executes generic versions of the primary-expression and
control-flow suites on five engines plus optimized native binaries, rejects 50
unused malformed bodies, and checks import-alias shadowing and REPL recovery.

## Source files and package assembly

```ebnf
source_file = { package_decl | import_decl | struct_decl | enum_decl
              | function_decl | extern_decl | export_decl } ;
```

The public `cool` CLI assembles source files with these additional rules:

- A directory entry selects its immediate `.cool` files in sorted order; it does
  not recursively merge child directories. A file entry selects that root file
  alone, even inside a module. Imported package directories are still resolved
  normally. Use a directory entry to compile all sibling files of a package.
- Each selected file in a directory package requires exactly one `package name;`
  declaration. All selected files in that directory must declare the same name.
  A standalone file may omit the declaration. Duplicate package declarations are
  rejected. The current grammar permits a package declaration among top-level
  forms; placing it first is the conventional spelling, not an extra parser rule.
- Package identity is the resolved import path, not just the declared short
  name. Files in one package share top-level functions/types and package-private
  members. Different import paths remain distinct even when they declare the
  same short name. A directory basename need not equal its declared package name.
- Import aliases are scoped to the source file. An explicit alias follows
  `import`; otherwise the final path component is the alias. Aliases may be
  reused for different packages in different files, but cannot be duplicated in
  one file. A sibling file's import does not introduce its alias locally.
- Imported functions/types/methods must be public, and imported struct field
  access must respect field visibility. A public function does not expose its
  private helper as a callable imported name. Imports are collected before
  signatures/bodies, so their written position does not prescribe initialization
  execution. There is no top-level executable initialization statement syntax.
- Ordinary directory builds/checks/runs omit filenames ending `_test.cool`.
  `cool test` includes such files only in the requested root package; dependencies
  use their production files. Dependency test-only imports and invalid test code
  cannot contaminate the root test build. Explicit file entries select the named
  file regardless of its suffix. Root tests remain type-checked, and eligible
  root `test_` functions must take no parameters and return void.

Import edges must be acyclic. `std/io` and `std/mem` are compiler-supported
packages; other `std/` paths resolve from the shipped standard library. Nonstandard
imports require a `cool.mod` module context and a supplying module in its resolved
graph. `__main` and `__scan` are reserved internal identities and cannot be imported
as user packages. Module versions, replacements, checksum persistence, cache and
offline/frozen resolution are separate module-management contracts still under
release audit; they must not be inferred from this source assembly grammar.

`make package-rules-test` uses real multi-file packages to verify per-file alias
isolation, cross-file private helpers, public access, declared-name/path separation,
file-versus-directory selection, package-header consistency and root-only test
inclusion. Both frontends run five engines; the instrumented frontend is included
by the sanitizer target. Existing project tests cover cycles, version resolution,
checksums and build-cache behavior.

## Expressions: precedence and sequencing

Binary operators below are ordered from lowest to highest precedence. Operators
in the same row associate left to right. Parentheses override the grouping.
Grouping and evaluation order are separate rules: the tree implied by precedence
is evaluated with the left operand before the right operand.

| Level | Operators | Operand category |
| --- | --- | --- |
| 1 | `\|\|` | bool; short circuit |
| 2 | `&&` | bool; short circuit |
| 3 | `\|` | integer |
| 4 | `^` | integer |
| 5 | `&` | integer |
| 6 | `==`, `!=` | compatible scalar values; no string or aggregate equality |
| 7 | `<`, `>`, `<=`, `>=` | numeric |
| 8 | `<<`, `>>` | integer |
| 9 | `+`, `-` | numeric; permitted raw pointer arithmetic requires unsafe |
| 10 | `*`, `/`, `%` | numeric; `%` requires integer operands |

The bitwise-or symbol in row 3 is `|`. Unary `-`, `!`, `~`, dereference `*`,
borrow `&`/`&mut`, raw address `&raw` and `move` consume a primary expression,
including its member/index suffixes. They bind more tightly than binary
operators. `!` requires bool, `~` requires integer and unary `-` requires numeric
input. There is no unary plus, ternary conditional, comma expression, increment
operator or assignment expression. Assignment is a statement; `a = b = c` is
not chained assignment. Comparison chaining is not mathematical notation:
`a < b < c` groups as `(a < b) < c` and fails for integer `c` because the first
comparison produces bool. `true == false == false` is valid left association.

The following EBNF describes the binary expression core. `primary` includes the
prefix, literal, name, call, aggregate and postfix forms defined in
[primary expressions](#primary-expressions-calls-and-construction). Braces in the EBNF mean repetition, not source-language braces.

```ebnf
expression     = logical_or ;
logical_or     = logical_and, { "||", logical_and } ;
logical_and    = bitwise_or, { "&&", bitwise_or } ;
bitwise_or     = bitwise_xor, { "|", bitwise_xor } ;
bitwise_xor    = bitwise_and, { "^", bitwise_and } ;
bitwise_and    = equality, { "&", equality } ;
equality       = comparison, { ("==" | "!="), comparison } ;
comparison     = shift, { ("<" | ">" | "<=" | ">="), shift } ;
shift          = additive, { ("<<" | ">>"), additive } ;
additive       = multiplicative, { ("+" | "-"), multiplicative } ;
multiplicative = primary, { ("*" | "/" | "%"), primary } ;
```

Evaluation obeys these rules, including optimized LLVM builds:

- A binary expression evaluates its left operand first. `&&` skips the right
  operand when the left is false; `||` skips it when the left is true. All other
  binary operators evaluate both operands. Both sides must type-check even when
  runtime evaluation skips one side.
- Function arguments evaluate left to right. A method receiver evaluates once,
  before its explicit arguments.
- Aggregate initializer expressions evaluate in their written order. Named
  struct fields do not reorder effects into declaration order.
- Indexing evaluates the base before the index. Slicing evaluates the base,
  lower bound and explicit upper bound in that order.
- A store through an indexed/projected place computes its destination before
  evaluating the value to store. This is not a relaxation of loan/move checks:
  an invalidated destination must still be rejected statically.

`make expressions-test` checks 19 precedence/association examples, twelve
rejected forms, and an exact 25-event observable trace covering binary operands,
short circuiting, argument order, named fields, array elements, indexed stores,
slice bounds and a temporary method receiver. Each frontend executes all five
engines and an optimized standalone binary. Existing reference/ownership suites
cover the separate validity obligations around moves and live destinations.
This does not yet specify overflow/conversion policy or cleanup timing.

## Primary expressions, calls and construction

The binary grammar's `primary` production is defined below. Name resolution
selects among type names, locals, import aliases and callable names; this EBNF is
not a context-free replacement for that resolution. `named_type`, `type_arguments`,
`type`, `integer_token` and `floating_token` refer to the earlier productions.

```ebnf
primary        = atom, { suffix } ;
atom           = integer_token | floating_token | string_token
               | "true" | "false" | "null" | identifier
               | "(", expression, ")" | prefix, primary
               | named_call | struct_literal | array_literal | empty_slice
               | enum_value | "sizeof", "(", type, ")"
               | "len", "(", expression, ")"
               | "new", "[", type, "]", "(", [ expression ], ")"
               | "cast", "[", type, "]", "(", expression, ")"
               | "borrow_raw", "[", type, "]", "(", expression, ",",
                 expression, ")" ;
prefix         = "-" | "!" | "~" | "*" | "&", [ "mut" | "raw" ] | "move" ;
arguments      = "(", [ expression, { ",", expression } ], ")" ;
named_call     = identifier, [ ".", identifier ], [ type_arguments ], arguments ;
suffix         = "[", expression, "]"
               | "[", [ expression ], ":", [ expression ], "]"
               | ".", identifier
               | ".", identifier, [ type_arguments ], arguments ;
struct_literal = named_type, "{", [ field_value, { ",", field_value }, [ "," ] ], "}" ;
field_value    = identifier, ":", expression ;
array_literal  = "[", integer_token, "]", type, "{",
                 [ expression, { ",", expression }, [ "," ] ], "}" ;
empty_slice    = "[", "]", type, "{", "}" ;
enum_value     = named_type, ".", identifier, [ "(", [ expression ], ")" ] ;
```

Calls refer to a function or builtin by name, possibly qualified by an import
alias, or to a method via a receiver suffix. Function values and arbitrary
expression calls such as `(function_name)(value)` are not supported. A numeric
type name used as a one-argument call, such as `i32(value)`, performs an explicit
numeric conversion; `cast[T](value)` provides the explicit cast spelling. Neither
spelling makes nonnumeric conversions generally valid. Raw pointer/reference
casts follow their unsafe restrictions. Ordinary calls, method calls and enum
payload constructors do not allow trailing commas.

A nonempty struct literal must name every field exactly once; order is arbitrary
and expression evaluation follows written order. A nonempty fixed-array literal
must supply exactly its declared number of elements. These two initializer forms
permit a trailing comma. Empty braces request default zero initialization,
subject to the type's safety/validity rules and field access checks. Slice literals
must be empty; a nonempty slice is obtained from an existing array or slice.
An enum is constructed by naming its variant. Payload variants require one
expression in parentheses; unit variants permit either no parentheses or `()`.

Field/index/slice/method suffixes may chain where the intermediate types permit
it. Indexing accepts integer indices on arrays, slices or typed raw pointers;
raw-pointer indexing requires unsafe. Slicing accepts arrays or slices, uses a
half-open range, defaults the low bound to zero and the high bound to length,
and has no step expression. Checked sequence indexing rejects out-of-bounds
indices; slicing requires `0 <= low <= high <= length`. Loans and mutability
still restrict which slices and accesses are permitted. `len` takes an array or
slice and `sizeof` takes a type, not an expression.

Dereference `*` applies to owners/references or typed raw pointers; the latter
requires unsafe. `&place` creates a shared reference and `&mut place` an exclusive
reference, both requiring a tracked stable place and satisfying loan checks.
`&raw place` creates a raw address inside unsafe. `borrow_raw[R](pointer, anchor)`
also requires unsafe: `R` must be a reference type, the pointer element must match,
and the anchor must be a named reference with sufficient mutability. The caller
must satisfy the raw-memory validity obligations in [references](references.md).
This construct does not infer allocation validity from an arbitrary pointer.

`new[T](value)` allocates an owner initialized from the supplied value;
`new[T]()` requests default initialization. Stored scoped references require an
explicit initializer. Owners can retain external borrows from their payloads
under the heap lifetime rules in draft 24. Moving an owned binding or
projection requires `move` where ownership transfers; a fresh owned result can
transfer directly. Direct moved bindings follow whole-root checking and are
unusable until validly reinitialized. Moves through exclusive receivers preserve
non-owning fields of borrowed aggregates as described in draft 23. The full move/loan and cleanup rules remain in the ownership/reference contract.

`make primary-forms-test` runs combined construction/access/conversion/ownership
examples with zero surviving owners, plus 26 rejected grammar/type/place cases,
on both frontends under five engines and optimized binaries. The sanitizer target
adds the instrumented frontend. This complements the dedicated ownership,
reference, generic, method, numeric and package suites.

## Statements, control flow and deferred calls

```ebnf
block          = "{", { statement }, "}" ;
statement      = block | binding, ";" | assignment, ";" | expression, ";"
               | "return", [ expression ], ";"
               | "if", "(", expression, ")", block,
                 [ "else", (block | if_statement) ]
               | "while", "(", expression, ")", block
               | "for", "(", [ for_init ], ";", [ expression ], ";",
                 [ for_update ], ")", block
               | "break", ";" | "continue", ";"
               | "defer", expression, ";" | "unsafe", block | match_statement ;
binding        = ("let" | "var"), identifier, [ ":", type ], "=", expression ;
assignment     = expression, "=", expression ;
for_init       = binding | assignment | expression ;
for_update     = assignment | expression ;
if_statement   = "if", "(", expression, ")", block,
                 [ "else", (block | if_statement) ] ;
match_statement = "match", "(", expression, ")", "{", { match_arm }, "}" ;
match_arm      = pattern, "=>", block, [ "," ] ;
pattern        = "_" | type, ".", identifier, [ "(", [ identifier ], ")" ] ;
```

A binding always has an initializer; its type may be inferred. `let` makes the
binding immutable and `var` permits assignment. This is not a blanket claim of
deep constness for all owned/referenced values: pointee mutability follows the
reference and owner rules. An assignment requires a mutable place, such as a
local, field, indexed element or dereference. Assignment is not an expression.
Blocks introduce lexical scopes. A name cannot be redeclared at the same depth;
an inner scope may shadow it. A for-initializer binding is local to that loop.

Conditions must be bool. If/while/for bodies require braces; `else if` is the
specified exception to an else block. A for loop evaluates its initializer once,
checks the condition before each iteration, executes its body and then its update.
An omitted condition means true. The initializer accepts the same assignment
places as ordinary statements, including fields, array elements and dereferences.
`continue` exits the current body scopes and performs a for update before the
next condition check; a while loop instead proceeds to its condition. `break`
exits the innermost loop without its update. Neither is valid outside a loop.
`return` evaluates and captures its result, exits enclosing scopes, and returns
from the function. Its presence/type must agree with the function result.

Match is an enum statement, not a general expression or integer switch. Its
scrutinee is evaluated once. A named arm must refer to a variant of that enum;
payload variants require a binding name (or `_` to discard it). A unit variant
has no binding and may use empty parentheses. Payload bindings are scoped to the
arm. Arms require blocks, may each have a trailing comma, and do not fall through.
Duplicate named arms are invalid. All variants must be covered unless a wildcard
arm is present; a wildcard must be last. Moving/copying the scrutinee and payloads
obeys ordinary ownership and borrowing checks.

`defer` requires a call returning void, not a block or arbitrary non-call
expression. The call arguments are evaluated and captured when execution reaches
the defer statement. The deferred call runs on ordinary exit from its enclosing
block, including return, break and continue, in reverse registration order.
Capturing a reference captures that reference, not a snapshot of its pointee;
its loan remains subject to scope/lifetime checks. An owned local registers its
implicit drop when bound. Explicit defers and implicit drops follow their common
reverse registration order, so a later deferred observer runs before an earlier
owner's drop, and an earlier observer runs after that drop. These rules describe
normal structured exits; they do not promise stack unwinding through every
runtime failure or unsafe foreign failure. Failure recovery remains separately
audited.

`unsafe` introduces a lexical block in which the documented raw-pointer and
foreign-call operations are permitted. It does not disable type checks or grant
permission to violate an existing safe reference's rules. Empty statements,
labels/goto, do/while and C switch statements are not part of this grammar.

`make control-flow-test` verifies a 31-event trace covering immediate defer argument
capture, nested reverse cleanup, return evaluation, loop updates/continue/break,
once-evaluated enum matching, owner-drop ordering and projected for-initializer
assignments. It also checks 23 rejected forms, including immutable and live-loan
assignment destinations. Both frontends run all five engines and optimized
binaries; the sanitizer target adds the instrumented compiler.

## Inference and permitted implicit conversions

An unannotated local binding takes its initializer's checked type. A nonnegative
integer literal defaults to i64 when representable and u64 above i64's maximum;
its unary negative form follows the signed minimum rule in the lexical contract.
A float literal defaults to f64. Parentheses preserve the enclosed expression's
literal status; general arithmetic expressions are not folded into literal
nodes for implicit narrowing. For example, `let n:i8=1` works but
`let n:i8=1+2` requires an explicit conversion. Parameter/result/field types and
annotated bindings provide required destination types; they do not propagate
backward into the operands of a binary expression.

Permitted implicit conversions are:

| Source | Destination and requirement |
| --- | --- |
| Same type | Identity |
| Integer literal | Integer type that contains the value; a u64 literal above i64 maximum retains its unsigned meaning |
| Typed integer value | A wider type of the same signedness, or a signed type strictly wider than an unsigned source |
| Integer literal in -16,777,216..16,777,216 | f32 or f64; larger literals require an explicit conversion even when a particular value is exactly representable |
| f32 | f64 |
| null | A raw pointer type |
| Typed raw pointer | `*void` erasure |

Other implicit narrowing/sign changes, float-to-integer conversions and typed
integer-to-float conversions require explicit casts. Bool/string, nominal
aggregates, owners and references do not gain numeric conversions through these
rules. Raw-pointer erasure does not establish a safe reference or lifetime.

For arithmetic, comparisons and integer bitwise operations with different operand
types, adopt a permitted literal conversion first. If the left literal can adopt
the right type, it does so; otherwise try the right literal with the left type.
If neither applies, use a permitted lossless widening direction. Reject operands
when neither can convert to the other; there is no invented third common type.
Thus i8/i64 addition uses i64 in either order, and f32/f64 addition uses f64 in
either order. i32/u32 operands require an explicit conversion. A literal fitting
an i8 operand preserves i8 arithmetic (`i8(127)+1` wraps to -128); a literal 128
cannot narrow to i8, so that expression widens to i64 and produces 255.

Shifts preserve the left integer operand's type and width. Their count may have
any integer width or signedness; it is checked as its actual value against the
left width, without narrowing or widening either operand. Float counts/operands
are errors. This preserves the narrow left-width runtime checks even with an i64
or u64 count. Raw pointer +/- integer arithmetic follows its separate unsafe
rule and does not use numeric common-type inference.

`make coercion-test` compares both operand orders over all eight integer types,
using an independent fixed-width integer oracle, plus floating widening, literal
adoption, pointer/null symmetry, rejection cases and separately executed invalid
mixed-width shift counts on all five engines and optimized native builds.

## Fixed-width integer values and operations

Signed integer types `i8`, `i16`, `i32`, `i64` use two's-complement values from
`-2^(w-1)` through `2^(w-1)-1`. Unsigned `u8`, `u16`, `u32`, `u64` range from zero
through `2^w-1`. On the supported 64-bit target, `isize` aliases `i64` and `usize`
aliases `u64`; this does not promise another target's pointer width.

Addition, subtraction, multiplication, unary negation and left shift retain the
low `w` bits of their mathematical result. Signed results interpret those bits
as two's complement; overflow in these operations wraps and does not constitute
undefined behavior. Bitwise operators work on the fixed-width representation.
Signed right shift propagates the sign bit; unsigned right shift inserts zeroes.
The shift count must be at least zero and strictly below the left operand's width.
An invalid count is an error, never a masked count. These rules apply equally in
interpreted, JIT and optimized builds.

Integer division truncates the mathematical quotient toward zero. For a valid
division, the remainder satisfies `a = (a / b) * b + a % b` in mathematical
integers; a nonzero signed remainder has the dividend's sign. Division and
remainder reject zero divisors. Both also reject signed `MIN / -1` and `MIN % -1`
at every width, including `i8`, `i16` and `i32`. This checked division-overflow
rule is separate from the wrapping rules for addition and multiplication.
Compile-time literal checks may diagnose invalid divisors/counts earlier; inputs
that pass type checking still undergo the corresponding runtime checks.

An explicit integer-to-integer conversion retains the low destination-width bits
and interprets them according to the destination's signedness. This includes
signed-to-unsigned conversion and narrowing. Implicit conversions are narrower:
representable integer literals can adopt their required type, widening preserves
signedness, and unsigned-to-signed widening is permitted when the signed type has
strictly more bits. Other integer narrowing or sign-changing assignments require
an explicit cast. This paragraph does not specify floating conversions or the
binary inference algorithm documented above.

`make integer-semantics-test` compares fixed boundary and deterministic random
operands with Python unbounded arithmetic for all eight integer types. It covers
arithmetic, signed remainder, bitwise operations, comparisons, shifts, unary
operators and cross-width/sign casts, plus separately executed runtime failures.
Each frontend runs the same oracle under five engines and an optimized native
build; the sanitizer target adds a compiler-instrumented frontend and
ASan-instrumented LLVM linked with the ASan/UBSan C runtime.

## Floating conversions and literal range

Floating literals have type `f64`. A decimal literal may represent a finite
subnormal value, including the smallest nonzero binary64 value (`5e-324` rounds
to that value). A nonzero literal whose conversion underflows to zero is an
error, as is overflow to infinity. Zero itself is valid. These rules apply to
source conversion; runtime arithmetic and explicit float narrowing may produce
zero, infinity or NaN. The decimal token grammar is defined in the lexical core.

A floating-to-integer conversion requires a finite input in a half-open interval:
`[-2^(w-1), 2^(w-1))` for signed destinations and `[0, 2^w)` for unsigned
ones. The check applies to the original floating value, before truncation toward
zero. Thus `i8(127.75)` is 127, `i8(-128.75)` fails, and `u8(-0.75)` fails.
Negative zero converts to integer zero. NaN, either infinity, and values outside
the interval fail with a checked conversion error. There is no saturation or
unchecked host float-to-integer cast for such inputs. An input originating in
`f32` follows the same rules using its represented value.

Integer-to-`f64` conversion rounds to binary64. Integer-to-`f32` rounds directly
to binary32, without an intermediate binary64 rounding. For example, converting
integer `9223372586610589697` to `f32` produces `9223373136366403584`.
`f64` to `f32` rounds to binary32, and widening a finite `f32` to `f64`
preserves its value exactly. Signed zero is preserved across float conversions.
The supported default floating environment rounds halfway cases to even; unsafe
foreign changes to that environment are outside this audited contract.

`make float-conversions-test` checks adjacent representable binary64 values at
all integer-width boundaries, signed zero, fractional truncation, f32 precision
ties, exact-integer midpoint neighbors, widening/narrowing, representable
subnormals, and NaN/infinite/out-of-range
rejections across both frontends, five engines and optimized binaries. The
sanitizer target additionally checks the compiler with ASan and generated LLVM
with ASan, linking the runtime with UBSan and float-cast-overflow checks enabled.
## Floating operations

`f64` is IEEE binary64 and `f32` is IEEE binary32 in stored values. The default
supported floating environment rounds halfway values to even. Arithmetic `+`,
`-`, `*`, `/` evaluates each primitive operation separately: the implementation
uses binary64 carriers and normalizes an f32 operation's result back to binary32
before further use. It does not contract an expression into a fused operation.
Overflow yields signed infinity; underflow may yield a signed subnormal or zero.
Floating division by zero follows IEEE infinity/NaN behavior and does not use
the integer division error. Zero divided by zero, infinity minus itself and
zero times infinity produce NaN. NaN payload bits are not specified.

Comparisons involving either NaN are unordered: `!=` is true and `==`, `<`, `<=`,
`>`, `>=` are false. Signed positive/negative zero compare equal. Infinities are
ordered beyond finite values. Integer bitwise/remainder/shift operators and
logical negation do not accept floating operands. Unsafe foreign changes to
rounding mode or exception behavior remain outside the default environment
contract.

`make float-arithmetic-test` checks finite operand bit patterns with an exact
Python rational oracle, including independent tie-to-even rounding, subnormal,
overflow and signed-zero boundaries. It also checks NaN/ordered comparisons,
infinities and invalid operators on both frontends, five engines and optimized
binaries. The sanitizer target adds compiler instrumentation and generated LLVM
with the instrumented C runtime. These deterministic cases support this contract;
they are not an exhaustive numerical equivalence proof.

## Memory layout on the supported target

The first supported target is little-endian 64-bit Apple Silicon macOS. Sizes
and alignments below are in bytes. These are language value layouts on that
target, not the compiler's internal register/stack-slot representation. A value
occupying an eight-byte interpreter slot does not make an `i8` field eight bytes.

| Type | Size | Alignment |
| --- | --- | --- |
| bool, i8, u8 | 1 | 1 |
| i16, u16 | 2 | 2 |
| i32, u32, f32 | 4 | 4 |
| i64, u64, isize, usize, f64 | 8 | 8 |
| Raw pointer, reference, owner, literal string handle | 8 | 8 |
| Slice descriptor | 16 | 8 |
| Empty struct | 0 | 1 |

`sizeof(void)` is zero; void is not a storable element type. Bool values use zero
for false and one for true. Floating storage uses binary32/binary64 respectively;
internal widening during evaluation does not change an f32 field's storage size.
A literal string handle points to its immutable text; it is not an owned UTF-8
container or a C ABI string parameter. A reference and an owner each carry one
address, with lifetime/ownership obligations checked separately. Their size is
not a guarantee that arbitrary integers or null constitute valid safe references.

A struct preserves declaration order. Each field begins at the smallest offset
at least as large as the previous field's end and divisible by that field's
alignment. The struct alignment is the maximum of one and its field alignments.
Its size rounds the last field's end up to that alignment. Packing, explicit
alignment annotations, bitfields and field reordering are not supplied. Padding
bytes are not a stable value/serialization contract.

An array has its element's alignment, size `length * sizeof(element)`, and
contiguous element stride `sizeof(element)`. Nesting therefore follows row-major
storage. A zero-length array has size zero while retaining element alignment.
Zero-sized fields/elements may share an address; distinct object identity must
not be inferred merely from their numerical addresses. An instantiated generic
nominal type is laid out using its concrete substituted field types.

An enum begins with an eight-byte signed tag at offset zero. Tags are zero-based
variant declaration indices. Every payload begins at offset eight; the payload
area is large enough for the largest variant. The enum alignment is eight and
its total size is `round_up(8 + maximum_payload_size, 8)`. A unit-only enum still
occupies eight bytes. Only the active variant's payload is valid to inspect as
that type. Unsafe code must not manufacture invalid tags or interpret an inactive
payload as a valid owner/reference/value.

A slice consists of its data address followed by an eight-byte length. Ownership
and exclusive/shared access are not encoded as extra descriptor fields. Bounds
and loan rules still apply. Layout does not give a slice ownership of its data.
The owner allocation strategy and allocator metadata are not part of the value
layout contract.

By-value layout cycles are rejected. An indirection can break a size dependency,
but this does not lift separate borrowed-storage or ownership restrictions.
The current aggregate-size limit is 512 KiB and array-length limit is 65,536;
these checks apply before allocating source-language aggregate storage.
The C ABI currently accepts scalars and raw pointers, not by-value Cool
aggregates. Layout compatibility with a particular C struct is not permission
to pass that aggregate by value through an unsupported foreign signature.

`make layout-contract-test` compares 24 generated structures and alignment
wrappers to Python ctypes' native C ABI layout, including nested and zero-sized
members. It also checks primitive/sequence sizes, enum tag/payload positions,
little-endian bytes, size limits and by-value cycles: 191 expected values and
four rejection cases across both frontends, five engines and optimized binaries.
The sanitizer target adds the ASan compiler and ASan-instrumented emitted LLVM
linked with the ASan/UBSan runtime. Dedicated ownership/reference/ABI tests remain
necessary for validity and lifetime properties that a size/offset test cannot prove.

## Draft revisions

- Draft 26: add checked `stores(destination,source)` contracts, caller lifetime
  retention and compatible REPL replacement effects; keep nested stored work open.

- Draft 19: specify primitive floating operation normalization and unordered
  comparisons; correct bootstrap NaN comparison behavior with carrier-bit tests.
- Draft 18: validate unused generic nominal member grammar, uniqueness, type
  names/privacy/arity, void fields, literal array limits and nonempty enums.
- Draft 17: specify binding/literal inference and implicit conversions; remove
  mixed-width operand order bias and preserve the left width for shift counts.
- Draft 16: check unused generic body statement/expression grammar with lexical
  import-alias shadowing and bounded recursion; preserve specialization semantics.
- Draft 15: reject actual void values/elements and out-of-range array lengths in
  unused template signatures, while preserving raw void pointers and shadowing.
- Draft 14: resolve non-dependent nominal signature types, visibility and arity
  before specialization; preserve forward names and type-parameter precedence.
- Draft 13: check unused generic signature syntax, duplicate parameter names
  and names in borrow contracts at declaration time.
- Draft 12: require well-formed UTF-8 across external inputs, preserve byte-based
  native ranges, and retain invalid dependency diagnostics on their actual URI.
- Draft 11: specify supported-target sizes, alignments, structure/array/enum
  layout and representation obligations, with an independent native ABI oracle.
- Draft 10: specify source-file/package assembly, file-local import aliases and
  test selection; exclude dependency test files when testing a root package.
- Draft 9: complete the primary-expression productions and record call,
  construction, projection, owner/reference and explicit conversion syntax.
- Draft 8: specify statement/control-flow/defer grammar and normal-exit ordering;
  permit projected assignments in for initializers under normal safety checks.
- Draft 7: add declaration/type EBNF and signature rules; reject duplicate
  parameter names during signature checking, including extern declarations.
- Draft 6: define the decimal floating-token grammar; defer integer overflow
  diagnostics until token classification so long finite float spellings work.
- Draft 5: integer-to-f32 conversion rounds directly to binary32. Removed the
  binary64 intermediary that gave incorrect results near large-integer midpoints;
  exact integer tie-to-even oracle cases cover both signs and tie directions.
- Draft 4: specify float-to-integer checks and subnormal literal acceptance;
  record remaining float arithmetic and integer-to-f32 rounding work.
- Draft 3: specify fixed-width integer operations and conversions. Signed
  division/remainder overflow now fails at every width; earlier development
  builds wrapped the narrow-width quotient. Correct bootstrap `u64` remainder
  truncation and width-specific runtime shift diagnostics.
- Draft 2: specify embedded-NUL rejection and byte positions; add the audited
  binary grammar, precedence, associativity and expression sequencing contract.
- Draft 1: initial integer lexical contract and remaining semantic audit map.

## Semantic contract map

The following sources document implemented behavior while this central
specification is completed. Their implementation restrictions remain explicit;
a link is not proof that a release gate is closed.

| Area | Current contract and evidence |
| --- | --- |
| Declarations, expressions and control flow | `language/Parser.cool`, `compiler/06-parser.cool`, `compiler/17-calls.cool`; `make language-test` |
| Methods and receiver evaluation | [Methods](methods.md); `make methods-test` |
| Shared/exclusive references, slices, stored loans | [References](references.md); reference/storage/iteration and sanitizer targets |
| Aggregate layout and monomorphization | `language/Types.cool`, `compiler/03-types.cool`; aggregate/generic tests |
| Owner moves, destruction and deferred calls | Ownership/reference invariants in [compiler architecture](compiler-invariants.md); ownership/evaluation tests |
| REPL replacement, recovery and retained resources | [Compiler invariants](compiler-invariants.md), [performance evidence](performance.md); REPL test targets |
| Core libraries and error contracts | [Standard library](../stdlib/README.md) and package source/public documentation |
| Packages and module resolution | [Implementation contract](language-plan.md), driver/module tests; `tools/modules.py` orchestrates resolution |
| Diagnostics and editor protocol | [Editor integration](editor.md); native protocol and actual Neovim-client tests |
| Target/installation boundary | [Distribution](distribution.md); external-prefix and C ABI tests |

## Work required before freezing this specification

1. Verify completeness and conformance mapping of the published source-file/package,
   declaration, statement, type and expression productions, including generic
   arguments, methods and borrow contracts.
2. Audit the inference/coercion and integer contracts against all conformance
   cases; define remaining float operations and runtime failures consistently
   across tree, bytecode, native JIT and optimized LLVM.
3. State layout/alignment, copy/move/initialization, evaluation order, cleanup and
   unsafe/C obligations independently of compiler-internal representations.
4. Consolidate package visibility, module-format/versioning and REPL replacement
   contracts, with executable positive and rejection examples.
5. Resolve remaining ownership/storage restrictions and language decisions;
   connect each normative rule to conformance evidence, and audit compatibility.

These are unfinished mandatory specification tasks. Existing tests and links are
supporting evidence, not a substitute for a complete, reviewed language contract.

## Draft 20: slice descriptor references

Direct `&[]T` and `&mut []T` references protect descriptor storage and its element
roots. Shared references permit descriptor length and element reads; exclusive
references permit element mutation and reborrowing. Non-owning aggregates may
mix slices and scoped reference fields. Whole-root conflict checks and lexical
loan lifetimes remain unchanged. See [descriptor rules](references.md#references-to-slice-descriptors)
for copy/reslice restrictions and conservative return-contract anchors.
Borrowed storage replacement through a reference, stored descriptor references
and borrowed slice elements remain explicitly rejected pending lifetime tracking.
This revision extends accepted programs; it does not close the whole-language
conformance or ownership release gates.

## Draft 21: template body name preflight

Unused generic function bodies now resolve expression roots that are independent
of type arguments: lexical parameters/locals, generic parameters, nominal type
names, collected function names and import-qualified public symbols. Undefined
names, use before a local declaration, use after a lexical block/for/match arm,
and private imported type/function names are errors before specialization. Forward
function declarations remain available. Import aliases are resolved only when not
shadowed by a local; the alias resumes after that local scope ends. Boolean/null
literals, numeric casts and the intrinsic names follow the ordinary parser's
lookup categories. `make template-names-test` checks these rules on both frontends
and five engines/O2, with unused-body rejection and REPL retry coverage.

Type-dependent member/operator checks still occur during concrete specialization.
This preflight does not yet typecheck every nondependent subexpression, validate
all call/constructor arities or establish ownership/loan validity in an unused
body; those remain part of the complete semantic audit. It does not manufacture a
substitute type for a generic parameter or run placeholder specializations.

## Draft 22: session storage reuse

REPL `:forget` releases a binding only after checking its dependent loans and
cleaning owned values. Later input may reuse a contiguous interior or trailing
storage gap. Live binding addresses are stable; values are not compacted or moved.
All anonymous and named allocations made while checking one input stay reserved
through its execution/recovery. Newly reserved ranges are zero-initialized before
execution, including interior slots formerly used for another type. Compile-only
rejection preserves existing live values.

The 65,536-slot storage/register limits remain implementation bounds. A request
that fits no contiguous gap can fail even when total free space is larger. Unsafe
raw pointers may not access storage after its binding is forgotten. See
[REPL storage checks](references.md#reusing-fragmented-repl-storage) and
[allocation accounting](repl-memory.md) for reclamation evidence and its limits.

## Draft 23: owning aggregates with stored borrows

Structs, arrays and enums may combine scoped references/slices with owning
fields when every owned allocation's payload is borrow-free. Ownership transfer
of such an aggregate preserves its external borrow provenance; an explicit
`borrows` return contract is still required. An owned field does not establish
external provenance: returning a reference into a by-value parameter's owned
allocation remains rejected. A reference into an owner accessed through a
receiver is tied to the receiver's physical storage lifetime.

A move conflicts with live references to the source aggregate or its owned
pointees. Through an exclusive receiver, moving a borrowed owning aggregate
clears owning subobjects but preserves initialized references, slice descriptors
and enum tags. The destination retains its external loans; conflicting access
through the retained source stays rejected while those loans are live. Empty
owned handles fault on dereference. Direct moved bindings remain unusable under
existing whole-root move tracking; this revision does not introduce granular
partial-move tracking or permit reference-field replacement.

At this revision, borrowed owned heap allocations and nested stored references
remained rejected. Draft 24 below extends the owned heap boundary. See
[mixed aggregate rules](references.md#owning-aggregates-with-stored-borrows).

## Draft 24: borrowed owning heaps

`own[T]` carries the external borrow provenance of its payload `T`. An explicit
`new[T](value)` initializer transfers those external loans to the owning handle;
returning it requires a matching `borrows` contract. Pointers into a by-value
owner's heap cannot escape that owner, even when the owner contains an external
borrow. A by-value owner may return one of its external reference fields under
its declared contract. An address into the heap instead pins its physical owner.

Ownership transfer always clears the owning handle itself, including when the
payload is borrowed; it must not clear or drop the allocation being transferred.
Recursive nominal types linked through owners are supported. Shared/exclusive
reference fields, slices, fixed arrays, enum payloads, generic and nested owning
heaps retain their existing capability and escape checks. Default initialization
cannot create null scoped reference fields. Empty owning handles remain valid
and fault when dereferenced.

Replacement of a local borrowed owner or an owned subobject uses the binding's
original lifetime marker and accumulates possible external roots. References
from a shorter nested scope cannot be installed into longer-lived heap storage.
Cross-call replacement through reference receivers remains rejected until
mutation contracts carry destination lifetimes. Stored references whose pointees
also contain borrows, and slices whose elements contain borrows, remain separate
unfinished lifetime work; this revision does not declare the 1.0 gate complete.


## Draft 25: mutable local reference replacement

Mutable local reference bindings and borrowed struct/array/enum/generic values
may be replaced, including reference fields in locally owned heaps. The new
borrow roots must outlive the original binding. Physical mutability and live
loan checks apply before storing; rebinding `var r:&T` never grants mutable
access through its shared referent. Explicit full initialization remains required.

The binding retains the union of old/new possible roots at its original lifetime
marker. Nested blocks, branches and loops cannot release installed roots early.
Identical holder/root/parent/mode/layer edges are retained once rather than once
per assignment. This conservative rule may keep a replaced root borrowed longer
than runtime use requires. All possible roots also contribute to return contract
checking. A failed RHS preserves the old reference value before its store executes.
REPL checking failures restore prior loans; runtime failures conservatively
retain candidate roots because preceding stores may already have executed.

Borrowed storage replacement through reference receivers remains unfinished:
callee parameters do not yet express the destination's retained lifetime.
Nested stored borrowed pointees and borrowed slice elements remain mandatory
work. This revision does not change the 1.0 release status.


## Draft 26: checked borrowed storage mutation

An exclusive reference to borrowed storage can install borrowed values through
`stores(destination, source)` signature relations. Relations follow the optional
return `borrows` contract, can repeat for distinct pairs, and are part of the
function's REPL replacement signature. Destinations require `&mut T` with a
borrowed `T`; sources must contain borrows. Unknown names, duplicate pairs and
known incompatible types are errors even in unused templates. Dependent template
type constraints are checked on specialization. Foreign declarations cannot
promise checked storage effects; C/raw-pointer access retains its unsafe duties.

The body must declare every possible parameter source installed into every
possible parameter destination. Function-local roots cannot escape into caller
storage. Caller checking retains the union of old and incoming roots at each
actual destination's original lifetime marker. All actual roots of computed
receivers are checked. Shared/exclusive payload permissions are preserved and
live reborrow ancestry gains installed roots. Call arguments remain protected
while later arguments are evaluated; installation effects and return-contract
root selection are applied after argument checking. A setter that also returns
a borrow must include all possible return sources in `borrows`.

This supports local and cross-call replacement of reference fields, borrowed
aggregates, slices and borrowed owning handles. Repeated identical retained
edges are merged. Compilation rejection rolls back staged loans; REPL runtime
failure retains candidate roots because a store may already have executed.
Multi-layer stored borrowed pointees and borrowed slice elements remain required
work. All 1.0 release gates remain open.


## Draft 27: slice return roots and stable simple projections

A slice return with nonzero borrow provenance requires every retained backing
root to be caller storage authorized by the function's `borrows` contract.
Selecting an inner slice value does not return the physical storage of an
intermediate descriptor array. Taking the descriptor's address or returning
that intermediate slice still requires its backing lifetime. Other borrowed
aggregate returns retain the conservative region rule. Region-zero empty slice
values may be returned; a zero-length view of a local array is not root-free.
Direct assignments, branches, aliases and checked stores accumulate installed
backing roots even when the binding originally held an empty literal.

A checked function whose entire body returns one equal-typed slice parameter,
optionally resliced with omitted or nonnegative integer-literal bounds, preserves
that parameter's borrowed element graph in the caller. It must have no `stores`
effects, be nonforeign, and name that parameter in `borrows`. Additional declared
return sources do not become actual result origins for this proven simple
projection. Argument loans still protect all arguments during evaluation.
Calls with other bodies retain conservative contract summaries; an equal input
and output type alone does not prove a value-preserving projection.

In a live REPL, changing an established simple projection to another parameter
or an unproven body requires a new session. The diagnostic is `borrow projection
change requires a new session`. This prevents callers checked against the old
projection from becoming unsafe after body replacement. Parameter renaming and
literal reslicing of the same source remain compatible. Failed replacements
roll back without changing the prior body or its callers. This is an explicit
current limitation: general body summaries and dependent caller revalidation
remain unfinished incremental-compilation work.

Arbitrary nested borrowed storage and borrowed slice elements remain guarded in
production. Private readiness tests audit deeper cases without enabling those
features. This draft does not complete any 1.0 release gate.


## Draft 28: straight-line slice aliases

The proven slice projection from draft 27 also follows straight-line inferred
`let` and `var` bindings. Each initializer must be a previously available slice
parameter or alias, optionally resliced with literal/omitted bounds; the final
statement returns such a value. The result retains the original parameter's
origins, even when an unused alias refers to a different contracted parameter.
All call arguments remain protected during evaluation. A mutable descriptor
binding does not strengthen the borrowed element capabilities.

Assignments, calls, branches, explicit binding type annotations, shadowed names
and other unrecognized body forms retain conservative summaries. Live REPL
replacement accepts an alias chain with the same proven source and rejects a
changed or unproven source under the draft 27 compatibility rule. General body
summaries and dependent caller revalidation remain required work.


## Draft 29: transactional projection replacement

The draft 27 requirement for a new session on a changed established slice
projection is superseded. After checking every new declaration body, a live
session detects changed proven parameter origins (including a transition to an
opaque summary) and checks all retained concrete function bodies against the
new projections. A caller whose lifetime/permission contract no longer holds
rejects the entire submission with its ordinary borrow diagnostic. The previous
functions and callers survive unchanged. Replacing affected callers in the
same submission is supported when their signatures stay compatible and their
new bodies pass checking.

Already-created session values retain the provenance of their actual historical
storage. Replacing a producer does not rewrite those loans or release protected
bindings. Future calls are checked against the new body. Parameter storage
anchors are owned by one analysis and are released on successful checking or
aborted transactions; checking retained bodies does not append synthetic locals
to their AST or function allocation registries.

This implementation checks every retained concrete body when an established
projection changes. Dependency-directed invalidation and broader body summaries
remain required compiler/performance work. Arbitrary nested storage restrictions
and all remaining release gates still apply.


## Draft 30: dependency-directed projection revalidation

The draft 29 transaction and historical-value rules remain unchanged. When an
established projection changes, the compiler now rechecks its retained callers
and their transitive callers instead of every retained body. Dependency edges
come from retained function call allocations, including cloned and conservative
unreachable calls. Multiple changed producers share one traversal; recursion
and repeated edges do not cause repeated checks. New declaration bodies have
already been checked against the final headers in the submission.

Missing call allocation metadata or a positive callee ID outside the snapshot
triggers the full retained-body audit. This fallback preserves the same safety
contract. Temporary graph tables are owned by submission scratch storage and
are reclaimed after successful checking or transaction rollback. General body
summary inference and broader nested storage support remain unfinished.


## Draft 31: pure branch slice-origin unions

Proven slice returns may use scoped blocks and `if`/`else` with a boolean
parameter or boolean literal, optionally negated once. Inferred aliases and
literal/omitted reslicing bounds retain their source origins. The summary is the
union of all syntactically possible returned parameters, even for literal
conditions; it does not infer relationships between successive conditions.
Every path must return. An early return without `else` still requires analysis
of following statements on the continuing path. Branch-local aliases cease to
exist when their block ends. Unused contracted parameters do not enter the
proven result, while argument evaluation continues to protect them.

A proof requires at most 32 visible names including parameters, 512 body tokens
and 16 nested blocks including the function body. Exhaustion, arbitrary
condition expressions, calls, assignments, annotated aliases and unsupported
statements use the conservative contract. The proof never strengthens source
capabilities. Any change of the nonempty returned-origin set participates in
transactional dependency-directed REPL revalidation, including expansion and
narrowing. Existing returned values retain historical provenance. General body
inference and production nested-storage acceptance remain unfinished.


## Draft 32: nested borrowed storage

Prior draft restrictions on stored references to borrowed pointees, owned
nested reference payloads and slice elements containing borrowed storage are
superseded. The production language permits these forms with typed provenance
and physical/payload lifetime checking. Recursive slice type queries terminate
through query-local visitation. Shared selection preserves capability barriers;
unknown or incomplete paths remain conservative. A copied external value may
outlive its local enclosing descriptor when its roots satisfy the return
contract; an address into that descriptor may not. Branch/loop replacements and
retargeted nested receivers retain every possible root and require applicable
`stores` relations. REPL success/compile rollback/runtime failure keep the same
historical-root rules. Raw operations keep the published unsafe obligations.

Zero-length fixed arrays contain no scoped reference slots. They, including
owners and aggregate fields of such arrays, may be empty-initialized. Nonempty
reference arrays and other scoped-reference fields still require explicit
initialization. This rule changes reference-presence queries for zero arrays,
not their declared element types or ordinary borrow-mode queries.

This draft establishes production availability; broader adversarial audits,
tracked collection iteration and every outstanding release requirement remain
mandatory. It does not declare the safety gate or the 1.0 release complete.


## Draft 33: relocated value layers and pure reference projections

Moving or copying a borrowed owner/aggregate through a field, array element,
slice element or computed receiver retains the selected value's scoped roots.
Physical storage protection is checked before selecting the result. Relative to
that result, ordinary fields, fixed-array elements and owning payloads preserve
root roles; crossing a scoped referent or borrowed-slice element enters the
payload role. A root present in both roles retains both loans. Opaque paths keep
both possible roles. This does not authorize escaping a local slot or upgrading
a shared path's capability.

The bounded pure-origin proof from draft 31 also applies to reference results
whose returned parameters have exactly the result type. Bare parameters, inferred
aliases and the same pure boolean branches are supported; reference reslicing
is not part of this proof. Unsupported bodies retain the conservative contract.
Changed established reference-origin sets use the same dependency-directed REPL
revalidation and rollback as slice projections. Historical values keep their
original roots. General body inference and all outstanding release gates remain
required.
