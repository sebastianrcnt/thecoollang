#!/usr/bin/env python3
"""Call exported Cool functions from C, checking actual platform scalar ABI."""
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='cool-exports-') as tmp:
    tmp=Path(tmp); src=tmp/'main.cool'; ir=tmp/'main.ll'; c=tmp/'probe.c'
    src.write_text('''export "C" fn negate(n: i8) -> i8 { return -n; }
export "C" fn widen(n: u8) -> u64 { return u64(n); }
export "C" fn add(a: f32, b: f64) -> f64 { return f64(a)+b; }
export "C" fn identity(p: *i32) -> *i32 { return p; }
export "C" fn invert(b: bool) -> bool { return !b; }
extern "C" fn probe() -> i32;
fn main() -> i32 { unsafe { return probe(); } }
''')
    c.write_text('''#include <stdint.h>
#include <stdbool.h>
extern int8_t negate(int8_t);
extern uint64_t widen(uint8_t);
extern double add(float,double);
extern int32_t *identity(int32_t *);
extern bool invert(bool);
int32_t probe(void) { int32_t n=7; return !(negate(-12)==12 && widen(255)==255 && add(1.25f,2.5)==3.75 && identity(&n)==&n && invert(false) && !invert(true)); }
''')
    subprocess.run([ROOT/'tools/cool','emit-ir',src,'-o',ir],check=True)
    for opt in ('-O0','-O2'):
        binary=tmp/('program'+opt)
        subprocess.run(['clang','-Wno-override-module',opt,ir,c,ROOT/'build/language-runtime.o','-o',binary],check=True)
        subprocess.run([binary],check=True)
print('exports: C callers, integer extension, float conversion, bool and pointer ABI at O0/O2 PASS')
