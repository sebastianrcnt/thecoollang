// Platform runtime for LLVM output. Language semantics live in the Cool compiler.
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "numeric.h"
void cool_print(int64_t value, int64_t type, int64_t newline) {
    if (type == 3) fputs((const char *)(uintptr_t)value, stdout);
    else if (type == 11 || type == 12) printf("%.17g", cool_double(value));
    else if (type == 2) fputs(value ? "true" : "false", stdout);
    else if (type == 5 || type == 8 || type == 9 || type == 10) printf("%" PRIu64, (uint64_t)value);
    else printf("%" PRId64, value);
    if (newline) putchar('\n');
}
static void fail(const char *message) {
    fprintf(stderr, "cool runtime: %s\n", message);
    exit(2);
}
void cool_assert(int64_t condition) { if (!condition) fail("assertion failed"); }
int64_t cool_div(int64_t a, int64_t b, int64_t remainder, int64_t is_unsigned, int64_t width) {
    (void)width;
    if (!b || (!is_unsigned && a == INT64_MIN && b == -1)) fail("invalid integer division");
    if (is_unsigned) return remainder ? (uint64_t)a % (uint64_t)b : (uint64_t)a / (uint64_t)b;
    return remainder ? a % b : a / b;
}
int64_t cool_shift(int64_t a, int64_t b, int64_t right, int64_t is_unsigned, int64_t width) {
    if (b < 0 || b >= width) fail("shift count outside 0..63");
    if (right && is_unsigned) return (uint64_t)a >> b;
    return right ? (a >> b) : (int64_t)((uint64_t)a << b);
}

int64_t cool_cast(int64_t value, int64_t from, int64_t to) {
    int64_t ok, result = cool_numeric_cast(value, from, to, &ok);
    if (!ok) fail("floating conversion out of range");
    return result;
}
