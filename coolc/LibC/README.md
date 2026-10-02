# Cool C compatibility library

`LibC.cool` provides C-style names for memory, strings, formatting, file IO, math,
time and nonlocal jumps. Include it once per program using a path relative to
your source. The host primitives are supplied by `coolc/Host/native.c`.
The `include/` headers describe the compatibility API.

This is not a complete system libc: streams use whole-file buffering, locale is
C, time is UTC, and process/environment/dynamic-loader/signal facilities are
not implemented. Check return values for unsupported operations. Use malloc/free
as a pair; its private allocation headers are incompatible with MAlloc/Free.

The retained COOLCOM_KERNEL branches are historical platform adapters; the host
build does not require kernel sources. The upstream c2hc translator and its
library/font integration tests are outside this standalone compiler distribution.
