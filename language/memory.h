#ifndef COOL_MEMORY_H
#define COOL_MEMORY_H
#include "numeric.h"
static inline int64_t cool_memory_read(int64_t address, int64_t type) {
    const void *p = (const void *)(uintptr_t)address;
    if (type == 12) { float n; memcpy(&n, p, 4); return cool_bits((double)n); }
    uint64_t bits = 0;
    int bytes = type == 2 ? 1 : type >= 100 || type == 11 ? 8 : cool_width(type) / 8;
    memcpy(&bits, p, bytes);
    if (type >= 100 || type == 11 || cool_unsigned(type) || bytes == 8) return (int64_t)bits;
    uint64_t sign = UINT64_C(1) << (bytes * 8 - 1);
    if (bits & sign) bits |= UINT64_MAX << (bytes * 8);
    return (int64_t)bits;
}
static inline void cool_memory_write(int64_t address, int64_t type, int64_t value) {
    void *p = (void *)(uintptr_t)address;
    if (type == 12) { float n = (float)cool_double(value); memcpy(p, &n, 4); return; }
    int bytes = type == 2 ? 1 : type >= 100 || type == 11 ? 8 : cool_width(type) / 8;
    memcpy(p, &value, bytes);
}
#endif
