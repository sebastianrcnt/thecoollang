# Cool language specification — 1.0 draft 8

Status: **partial specification under implementation audit**. This document does
not declare the language complete or freeze the 1.0 contract. It starts a
versioned specification series; later draft revisions must record changed
language decisions. See [compatibility](compatibility.md) for the proposed freeze
policy and [release gates](release-1.0.md) for remaining acceptance work.

## Audited lexical core

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
The editor translates these ranges to UTF-16 positions. This rule does not imply
whole-input UTF-8 validation. `make input-bytes-test` covers rejection, formatter
file preservation, byte ranges and REPL recovery on both frontends.

A string literal is enclosed in double quotes. Supported escapes are `\n`, `\t`,
`\r`, `\\` and `\"`. A newline inside a string, an unknown escape, or a missing
closing quote is a compile-time error. Runtime `string` values denote immutable
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
meaning. `string_token` denotes a quoted string token. This section does not yet
specify the driver's complete multi-file package-header/resolution rules.
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
function_decl  = [ "pub" ], "fn", function_name, [ generic_names ],
                 parameters, [ result ], [ borrow_contract ], block ;
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
Generic signatures/bodies and generic type layouts are still validated lazily
when instantiated; complete validation of unused templates remains release work.

`make declarations-test` covers eleven valid declaration/type/boundary cases and
35 rejections, including duplicate extern/ordinary/export/instantiated-generic
parameters, duplicate nominal members, malformed lists, invalid C signatures,
method owners, borrow contracts and implementation limits, on both frontends.
The wider package/method/reference suites cover visibility and lifetime behavior.

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
prefix, literal, name, call, aggregate and postfix forms described above and in
the semantic contract map; this production does not yet claim their complete
grammar. Braces in the EBNF mean repetition, not source-language braces.

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
complete inference algorithm for mixed-type binary expressions.

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
This section does not yet specify the full floating arithmetic/rounding contract.

## Draft revisions

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

1. Complete the source-encoding/control-byte audit, then
   publish complete EBNF for declarations, statements, types, expressions and
   precedence, including explicit generic arguments, methods and borrow contracts.
2. Define inference/coercion, integer/float operations and every runtime failure
   consistently across tree, bytecode, native JIT and optimized LLVM.
3. State layout/alignment, copy/move/initialization, evaluation order, cleanup and
   unsafe/C obligations independently of compiler-internal representations.
4. Consolidate package visibility, module-format/versioning and REPL replacement
   contracts, with executable positive and rejection examples.
5. Resolve remaining ownership/storage restrictions and language decisions;
   connect each normative rule to conformance evidence, and audit compatibility.

These are unfinished mandatory specification tasks. Existing tests and links are
supporting evidence, not a substitute for a complete, reviewed language contract.
