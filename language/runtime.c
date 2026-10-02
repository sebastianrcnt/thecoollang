// Platform runtime for LLVM output. Language semantics live in the Cool compiler.
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "memory.h"
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

int64_t cool_alloc(int64_t size) {
    if (size < 0) fail("allocation size exceeds host range");
    void *p = calloc(1, size ? (size_t)size : 1);
    if (!p) fail("out of memory");
    return (int64_t)(uintptr_t)p;
}
void cool_free(int64_t p) { free((void *)(uintptr_t)p); }
void cool_copy(int64_t to, int64_t from, int64_t size) {
    if (size < 0) fail("copy size exceeds host range");
    memcpy((void *)(uintptr_t)to, (void *)(uintptr_t)from, (size_t)size);
}
int64_t cool_load(int64_t address, int64_t type) {
    if (!address) fail("null pointer dereference");
    return cool_memory_read(address, type);
}
void cool_store(int64_t address, int64_t type, int64_t value) {
    if (!address) fail("null pointer dereference");
    cool_memory_write(address, type, value);
}

void cool_zero(int64_t address, int64_t size) { memset((void *)(uintptr_t)address, 0, (size_t)size); }
int64_t cool_length(int64_t source, int64_t count, int64_t slice) {
    return slice ? ((const int64_t *)(uintptr_t)source)[1] : count;
}
int64_t cool_index(int64_t source, int64_t index, int64_t count, int64_t size, int64_t slice) {
    count = cool_length(source, count, slice);
    if (index < 0 || index >= count) fail("index out of bounds");
    if (slice) source = ((const int64_t *)(uintptr_t)source)[0];
    return (int64_t)((uint64_t)source + (uint64_t)index * (uint64_t)size);
}
void cool_slice(int64_t destination, int64_t source, int64_t low, int64_t high, int64_t count, int64_t size, int64_t slice) {
    count = cool_length(source, count, slice);
    if (low < 0 || high < low || high > count) fail("slice bounds out of range");
    if (slice) source = ((const int64_t *)(uintptr_t)source)[0];
    int64_t *result = (int64_t *)(uintptr_t)destination;
    result[0] = (int64_t)((uint64_t)source + (uint64_t)low * (uint64_t)size);
    result[1] = high-low;
}
