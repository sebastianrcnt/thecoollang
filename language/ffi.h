#ifndef COOL_FFI_H
#define COOL_FFI_H
#include <ffi/ffi.h>
#include <dlfcn.h>
#include "numeric.h"
static ffi_type *cool_ffi_type(int64_t type) {
    switch (type) {
        case 0: return &ffi_type_void;
        case 1: return &ffi_type_sint64;
        case 2: case 5: return &ffi_type_uint8;
        case 4: return &ffi_type_sint32;
        case 6: return &ffi_type_sint8;
        case 7: return &ffi_type_sint16;
        case 8: return &ffi_type_uint16;
        case 9: return &ffi_type_uint32;
        case 10: return &ffi_type_uint64;
        case 11: return &ffi_type_double;
        case 12: return &ffi_type_float;
        default: return type >= 100 ? &ffi_type_pointer : NULL;
    }
}
static int64_t cool_foreign_call(const char *name, int64_t result_type, const int64_t *types,
                                const int64_t *values, int64_t count, int64_t *ok) {
    *ok = 0;
    if (count < 0 || count > 32) return 0;
    void *function = dlsym(RTLD_DEFAULT, name);
    if (!function) return 0;
    union Value { uint64_t bits; double real; float single; void *pointer; } args[32], result = {0};
    ffi_type *arguments[32], *returns = cool_ffi_type(result_type);
    void *addresses[32];
    if (!returns) return 0;
    for (int64_t i = 0; i < count; i++) {
        arguments[i] = cool_ffi_type(types[i]);
        if (!arguments[i] || types[i] == 0) return 0;
        args[i].bits = (uint64_t)values[i];
        if (types[i] == 12) args[i].single = (float)cool_double(values[i]);
        addresses[i] = &args[i];
    }
    ffi_cif cif;
    if (ffi_prep_cif(&cif, FFI_DEFAULT_ABI, (unsigned)count, returns, arguments) != FFI_OK) return 0;
    ffi_call(&cif, FFI_FN(function), &result, addresses);
    *ok = 1;
    if (result_type == 0) return 0;
    if (result_type == 12) return cool_bits((double)result.single);
    int width = cool_width(result_type);
    uint64_t bits = result.bits;
    if (result_type < 11 && width < 64) {
        bits &= (UINT64_C(1) << width) - 1;
        if (!cool_unsigned(result_type) && result_type != 2 && (bits & (UINT64_C(1) << (width - 1))))
            bits |= UINT64_MAX << width;
    }
    return (int64_t)bits;
}
#endif
