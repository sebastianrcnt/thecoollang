#!/usr/bin/env python3
"""New-language compiler/interpreter conformance, implemented in Cool."""
from pathlib import Path
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[1]
CASES = []

def invoke(source, mode='run'):
    with tempfile.TemporaryDirectory(prefix='cool-language-') as tmp:
        path = Path(tmp) / 'test.cool'
        path.write_text(source)
        return subprocess.run([ROOT / 'build/coolc', '--run', ROOT / 'build/language.BIN', mode, path],
                              text=True, capture_output=True, timeout=10)

def good(source, output, status=0):
    source = 'import "std/io";\n' + source
    CASES.append((source, output, status))
    for mode in ('run', 'bytecode', 'jit'):
        p = invoke(source, mode)
        assert (p.returncode, p.stdout, p.stderr) == (status, output, ''), (mode, source, p.returncode, p.stdout, p.stderr)

def bad(source, diagnostic):
    p = invoke('import "std/io";\n' + source, 'check')
    assert p.returncode == 2 and diagnostic in p.stderr, (source, p.returncode, p.stdout, p.stderr)

good('fn main() -> i32 { return 7; }', '', 7)
good('fn main() { io.println(add(20, 22)); } fn add(a: i64, b: i64) -> i64 { return a + b; }', '42\n')
good('fn fib(n: i64) -> i64 { if (n < 2) { return n; } return fib(n-1)+fib(n-2); } fn main() { io.println(fib(12)); }', '144\n')
good('fn main() { var n = 0; while (n < 5) { n = n + 1; if (n == 2) { continue; } if (n == 4) { break; } io.println(n); } }', '1\n3\n')
good('fn side() -> bool { io.println("unexpected"); return true; } fn main() { assert(true || side()); assert(!(false && side())); }', '')
good('fn main() { var n = 1; defer io.println(n); n = 2; { defer io.println("inner"); } defer io.println("last"); io.println(n); }', 'inner\n2\nlast\n1\n')
good('fn main() { var n = 0; while (n < 2) { defer io.println(n); n = n + 1; continue; } }', '0\n1\n')
good('fn main() { let x: u8 = 255; io.println(i64(x)); io.println(u8(256)); io.println(1 + 2 << 3); io.println("한글"); }', '255\n0\n24\n한글\n')
bad('fn main() { let x = 1; x = 2; }', 'cannot assign')
bad('fn main() { var x: i64; }', 'initializer')
bad('fn main() { if (1) {} }', 'bool')
bad('fn main() { let x: u8 = 256; }', 'incompatible types')
bad('fn main() { let x = 1 / 0; }', 'division by zero')
bad('fn main() { let x = 1 << 64; }', 'shift count')
bad('fn a(x: i64) {} fn main() { a(true); }', 'incompatible types')
bad('fn a(x: i64) {} fn main() { a(); }', 'argument count')
bad('fn main() -> i64 { if (true) { return 1; } }', 'not every path')
bad('fn main() { break; }', 'outside a loop')
bad('fn main() {} fn main() {}', 'duplicate function')
bad('fn main() { let x = missing; }', 'unknown variable')
bad('fn main() { let x = "unfinished; }', 'unterminated string')
bad('fn main() {} /*', 'unterminated comment')
good('fn main() { var x = 0; while (x < 10000) { if ((x > 3 && x < 7) || x == 9) { io.print(x); } x = x + 1; } io.println(true); }', '4569true\n')
good('fn main() { var x: i32 = 2147483647; let y: i64 = x + 1; io.println(y); }', '-2147483648\n')
good('fn main() { var a = 0; while (a < 3) { var b = 0; while (b < 3) { b = b + 1; if (b == 2) { break; } io.print(a); } a = a + 1; } }', '012')
good('fn main() { let n = 18446744073709551615; io.println(n); io.println(n / 2); io.println(n > u64(1)); io.println(n >> 63); io.println(i8(255)); io.println(u16(65536)); io.println(i16(65535)); io.println(u32(-1)); io.println(-9223372036854775808); }', '18446744073709551615\n9223372036854775807\ntrue\n1\n-1\n0\n-1\n4294967295\n-9223372036854775808\n')
bad('fn main() { let x: i64 = 18446744073709551615; }', 'incompatible types')
bad('fn main() { let x: u8 = 1; io.println(x << 8); }', 'shift count')
good('fn main() { let x = 1.5; let y: f64 = 2; io.println(x + y); io.println(x * y); io.println(-x); io.println(i32(3.9)); io.println(f64(u64(42))); io.println(f32(1.25) + f32(2.5)); io.println(1e-3 < 0.01); let nan = 0.0 / 0.0; io.println(nan != nan); }', '3.5\n3\n-1.5\n3\n42\n3.75\ntrue\ntrue\n')
bad('fn main() { let x = 1.0 & 2.0; }', 'integer operands')
bad('fn main() { let x = 1e; }', 'exponent digits')
good('import "std/mem"; fn main() { unsafe { let p = cast[*i16](mem.alloc(4)); defer mem.free(p); p[0] = 42; let q = p + 1; *q = -2; io.println(p[0]); io.println(p[1]); io.println(p != null); let f = cast[*f32](mem.alloc(4)); defer mem.free(f); f[0] = f32(1.25); io.println(f[0]); } }', '42\n-2\ntrue\n1.25\n')
bad('fn main() { let p: *i64 = null; io.println(*p); }', 'requires unsafe')
bad('fn main() { unsafe { let p: *void = null; io.println(*p); } }', 'typed pointer')
good('extern "C" fn strlen(s: *u8) -> usize; extern "C" fn abs(n: i32) -> i32; extern "C" fn sqrt(n: f64) -> f64; fn main() { unsafe { io.println(strlen(cast[*u8]("hello"))); io.println(abs(-7)); io.println(sqrt(9.0)); } }', '5\n7\n3\n')
bad('extern "C" fn abs(n: i32) -> i32; fn main() { abs(-7); }', 'require unsafe')
good('fn main() { var total = 0; for (var i = 0; i < 5; i = i + 1) { defer io.print(i); if (i == 1) { continue; } if (i == 4) { break; } total = total + i; } io.println(total); }', '012345\n')
bad('fn main() { for (var i = 0; i < 1; i = i + 1) {} io.println(i); }', 'unknown variable')
good('fn bump(p: *i16) { unsafe { *p = -2; } } fn main() { var small: i16 = 32767; var f: f32 = f32(1.5); unsafe { bump(&small); io.println(small); let p = &f; *p = f32(2.25); io.println(f); f = f32(3.5); io.println(*p); } }', '-2\n2.25\n3.5\n')
good('extern "C" fn frexp(n: f64, exponent: *i32) -> f64; extern "C" fn modff(n: f32, integer: *f32) -> f32; fn main() { var exponent: i32 = 0; var integer: f32 = 0; unsafe { io.println(frexp(8.0, &exponent)); io.println(exponent); io.println(modff(f32(3.25), &integer)); io.println(integer); } }', '0.5\n4\n0.25\n3\n')
good('fn identity(x: f32) -> f32 { return x; } fn main() { io.println(identity(f32(2.5))); var n: u8 = 255; unsafe { let p = &n; *p = 1; io.println(n); n = 2; io.println(*p); } }', '2.5\n1\n2\n')
bad('fn main() { var x = 1; let p = &x; }', 'requires unsafe')
bad('fn main() { let x = 1; unsafe { let p = &x; } }', 'mutable address')
bad('fn f(x: i64) { unsafe { let p = &x; } } fn main() {}', 'mutable address')
print('new language: parser/type checks + tree/bytecode/native-JIT differential cases PASS')

# The same typed program must produce identical observable behavior under LLVM AOT.
with tempfile.TemporaryDirectory(prefix='cool-llvm-') as tmp:
    tmp = Path(tmp)
    for index, (source, expected, status) in enumerate(CASES):
        path, ir, exe = tmp / 'case.cool', tmp / 'case.ll', tmp / 'case'
        path.write_text(source)
        subprocess.run([ROOT/'build/coolc', '--run', ROOT/'build/language.BIN', 'llvm', path, ir], check=True, capture_output=True)
        for optimization in ('-O0', '-O2'):
            compilation = subprocess.run(['clang', '-Wno-override-module', optimization, ir, ROOT/'language/runtime.c', '-o', exe], capture_output=True, text=True)
            assert compilation.returncode == 0, (index, optimization, compilation.stderr, ir.read_text())
            result = subprocess.run([exe], capture_output=True, text=True, timeout=10)
            assert (result.returncode, result.stdout, result.stderr) == (status, expected, ''), (index, optimization, result)
print(f'LLVM AOT: {len(CASES)} interpreter differential cases at O0 and O2 PASS')
