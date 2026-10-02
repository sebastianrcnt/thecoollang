#ifndef COOL_NUMERIC_H
#define COOL_NUMERIC_H
#include <stdint.h>
#include <string.h>
#include <math.h>
static inline double cool_double(int64_t bits) { double n; memcpy(&n, &bits, 8); return n; }
static inline int64_t cool_bits(double n) { int64_t bits; memcpy(&bits, &n, 8); return bits; }
static inline int cool_unsigned(int64_t type) { return type == 5 || type == 8 || type == 9 || type == 10; }
static inline int cool_width(int64_t type) {
    if (type == 5 || type == 6) return 8;
    if (type == 7 || type == 8) return 16;
    if (type == 4 || type == 9) return 32;
    return 64;
}
static inline int64_t cool_numeric_cast(int64_t bits, int64_t from, int64_t to, int64_t *ok) {
    *ok = 1;
    if (to == 11 || to == 12) {
        double n = from >= 11 ? cool_double(bits) : cool_unsigned(from) ? (double)(uint64_t)bits : (double)bits;
        if (to == 12) n = (double)(float)n;
        return cool_bits(n);
    }
    double n = cool_double(bits);
    int width = cool_width(to), u = cool_unsigned(to);
    double edge = ldexp(1.0, u ? width : width - 1);
    if (!isfinite(n) || n >= edge || n < (u ? 0 : -edge)) { *ok = 0; return 0; }
    return u ? (int64_t)(uint64_t)n : (int64_t)n;
}
#endif
