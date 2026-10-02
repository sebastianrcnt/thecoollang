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
    CASES.append((source, output, status))
    p = invoke(source)
    assert (p.returncode, p.stdout, p.stderr) == (status, output, ''), (source, p.returncode, p.stdout, p.stderr)

def bad(source, diagnostic):
    p = invoke(source, 'check')
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
print('new language: 22 parser/type/interpreter cases PASS')

# The same typed program must produce identical observable behavior under LLVM AOT.
with tempfile.TemporaryDirectory(prefix='cool-llvm-') as tmp:
    tmp = Path(tmp)
    for index, (source, expected, status) in enumerate(CASES):
        path, ir, exe = tmp / 'case.cool', tmp / 'case.ll', tmp / 'case'
        path.write_text(source)
        subprocess.run([ROOT/'build/coolc', '--run', ROOT/'build/language.BIN', 'llvm', path, ir], check=True, capture_output=True)
        for optimization in ('-O0', '-O2'):
            subprocess.run(['clang', '-Wno-override-module', optimization, ir, ROOT/'language/runtime.c', '-o', exe], check=True, capture_output=True)
            result = subprocess.run([exe], capture_output=True, text=True, timeout=10)
            assert (result.returncode, result.stdout, result.stderr) == (status, expected, ''), (index, optimization, result)
print(f'LLVM AOT: {len(CASES)} interpreter differential cases at O0 and O2 PASS')
