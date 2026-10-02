// Platform runtime for LLVM output. Language semantics live in the Cool compiler.
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
void cool_print(int64_t value, int64_t type, int64_t newline) {
    if (type == 3) fputs((const char *)(uintptr_t)value, stdout);
    else if (type == 2) fputs(value ? "true" : "false", stdout);
    else printf("%" PRId64, value);
    if (newline) putchar('\n');
}
static void fail(const char *message) {
    fprintf(stderr, "cool runtime: %s\n", message);
    exit(2);
}
void cool_assert(int64_t condition) { if (!condition) fail("assertion failed"); }
int64_t cool_div(int64_t a, int64_t b, int64_t remainder) {
    if (!b || (a == INT64_MIN && b == -1)) fail("invalid integer division");
    return remainder ? a % b : a / b;
}
int64_t cool_shift(int64_t a, int64_t b, int64_t right) {
    if (b < 0 || b >= 64) fail("shift count outside 0..63");
    return right ? (a >> b) : (int64_t)((uint64_t)a << b);
}
