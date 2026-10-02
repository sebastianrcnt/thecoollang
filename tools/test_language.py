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
good('struct Point { x: i32; y: f32; } fn swap(p: Point) -> Point { return Point { x: 9, y: p.y }; } fn main() { var p = Point { y: f32(2.5), x: 1 }; var q = p; q.x = 7; io.println(p.x); io.println(q.x); io.println(swap(p).x); io.println(swap(p).y); }', '1\n7\n9\n2.5\n')
good('struct Outer { tag: u8; inner: Inner; } struct Inner { x: i32; y: f64; } fn main() { var p = Outer { tag: 3, inner: Inner { x: 7, y: 1.5 } }; var q = p; q.inner.x = 9; io.println(p.inner.x); io.println(q.inner.x); io.println(sizeof(Inner)); io.println(sizeof(Outer)); unsafe { let ptr = &p; ptr.inner.y = 2.25; } io.println(p.inner.y); }', '7\n9\n16\n24\n2.25\n')
good('fn identity(a: [3]i32, n: i64) -> [3]i32 { var b = a; b[1] = i32(n); return b; } fn main() { var a = [3]i32{1,2,3}; var b = identity(a, 7); b[0] = 8; io.println(a[1]); io.println(b[1]); io.println(len(b)); var nested = [2][2]i16{[2]i16{1,2},[2]i16{3,4}}; nested[1][0] = -5; io.println(nested[1][0]); }', '2\n7\n3\n-5\n')
good('fn fill(s: []i32) { s[0] = 42; } fn main() { var a = [3]i32{1,2,3}; let s = a[1:]; fill(s); io.println(a[1]); io.println(len(s)); a = [3]i32{4,5,6}; io.println(s[0]); let t = s[:1]; t[0] = 9; io.println(a[1]); io.println(len(a[3:3])); let empty = []i32{}; io.println(len(empty)); }', '42\n2\n5\n9\n0\n0\n')
good('struct Pair { a: [2]i64; } fn change(p: *Pair) -> i64 { unsafe { p.a[0] = 9; } return 0; } fn observe(p: Pair, ignored: i64) { io.println(p.a[0]); } fn main() { var p = Pair { a: [2]i64{1,2} }; unsafe { observe(p, change(&p)); } io.println(p.a[0]); var total = 0; for(var i=0;i<10000;i=i+1) { let a = [2]i64{i,1}; total = total+a[0]; } io.println(total); }', '1\n9\n49995000\n')
good('extern "C" fn memset(p: *void, c: i32, n: usize) -> *void; struct Pair { a: i32; b: i32; } fn main() { var a = [2]Pair{Pair{a:1,b:2},Pair{a:3,b:4}}; unsafe { memset(&a[1], 0, sizeof(Pair)); } io.println(a[0].a); io.println(a[1].b); }', '1\n0\n')
good('struct Empty {} struct Pair { a: Empty; b: Empty; } fn main() { let p = Pair {a: Empty{}, b: Empty{}}; io.println(sizeof(Pair)); let a = [0]i32{}; io.println(len(a)); }', '0\n0\n')
bad('struct Cycle { x: Cycle; } fn main() {}', 'recursive aggregate')
bad('struct Cycle { x: [1]Cycle; } fn main() {}', 'recursive aggregate')
bad('struct P { x: i64; y: i64; } fn main() { let p = P{x:1}; }', 'every element')
bad('struct P { x: i64; y: i64; } fn main() { let p = P{x:1,x:2}; }', 'duplicate initializer')
bad('fn main() { let a = [2]i32{1,2}; a[0]=3; }', 'immutable')
bad('fn main() { let a = [2]i32{1,2}; let s=a[:]; }', 'var array')
bad('fn f(a: [2]i32) { a[0]=3; } fn main() {}', 'immutable')
bad('fn f() -> []i32 { var a = [2]i32{}; return a[:]; } fn main() {}', 'returning borrowed slices')
bad('struct View { s: []i32; } fn f() -> View { return View{}; } fn main() {}', 'returning borrowed slices')
bad('extern "C" fn f(a: [2]i32); fn main() {}', 'aggregate values')
bad('fn main() { let a = [3]i32{1,2}; }', 'every element')
bad('fn main() { let a = [2]void{}; }', 'invalid element')
good('struct Link { value: i64; next: *Link; } fn change(p: *Link) { unsafe { p.value = 99; } } fn get() -> Link { var p = Link{value:7, next:null}; unsafe { defer change(&p); return p; } } fn main() { var a = get(); var b = Link{value:8,next:null}; unsafe { a.next = &b; io.println(a.value); io.println(a.next.value); } io.println(sizeof(Link)); }', '7\n8\n16\n')
good('extern "C" fn memset(p: *void, c: i32, n: usize) -> *void; struct Pair { a: i32; b: i32; } fn main() { var a = [2]Pair{Pair{a:1,b:2},Pair{a:3,b:4}}; unsafe { memset(&a[0]+1, 0, sizeof(Pair)); } io.println(a[0].a); io.println(a[1].a); }', '1\n0\n')
bad('struct i64 {} fn main() {}', 'builtin type')
bad('struct P {} fn P() {} fn main() {}', 'conflicts with a type')
bad('fn escape(out: [][]i32) { var a = [1]i32{7}; out[0] = a[:]; } fn main() {}', 'slice elements cannot contain')
bad('struct View { data: []i32; } fn escape(out: []View) { var a = [1]i32{7}; out[0].data = a[:]; } fn main() {}', 'slice elements cannot contain')
good('struct Box[T] { value: T; } fn identity[T](x: T) -> T { return x; } fn sum[T](n: T) -> T { if (n == 0) { return 0; } return n + sum[T](n-1); } fn main() { let b = identity[Box[i32]](Box[i32]{value:42}); io.println(b.value); io.println(sum[i64](10)); io.println(identity[f32](f32(2.5))); }', '42\n55\n2.5\n')
good('enum Result[T,E] { Ok(T); Err(E); } fn choose[T](x: T, good: bool) -> Result[T,string] { if (good) { return Result[T,string].Ok(x); } return Result[T,string].Err("bad"); } fn value[T](r: Result[T,string], fallback: T) -> T { match(r) { Result[T,string].Ok(x) => { return x; } Result[T,string].Err(_) => { return fallback; } } } fn main() { io.println(value[i32](choose[i32](7,true),0)); io.println(value[i32](choose[i32](7,false),0)); }', '7\n0\n')
good('enum Color { Red; Green; Blue; } fn describe(c: Color) -> i64 { match(c) { Color.Red => { return 1; } _ => { return 2; } } } fn main() { io.println(describe(Color.Red)); io.println(describe(Color.Blue())); }', '1\n2\n')
good('struct Link[T] { value: T; next: *Link[T]; } fn main() { var b=Link[i32]{value:2,next:null}; var a=Link[i32]{value:1,next:null}; unsafe { a.next=&b; io.println(a.next.value); } }', '2\n')
bad('enum E { A; B; } fn main() { match(E.A) { E.A => {} } }', 'non-exhaustive')
bad('enum E { A; B; } fn main() { match(E.A) { E.A => {} E.A => {} } }', 'duplicate match arm')
bad('enum E { A(i64); B; } fn main() { let x=E.A(true); }', 'incompatible types')
bad('enum E { A(i64); B; } fn main() { let x=E.A(1); io.println(x.A); }', 'field access requires a struct')
bad('fn identity[T](x:T)->T{return x;} fn main(){identity(1);}', 'generic argument count')
bad('fn add[T](x:T)->T{return x+1;} fn main(){add[bool](true);}', 'incompatible types')
bad('struct Box[T]{x:T;} fn main(){let x:Box=Box[i64]{x:1};}', 'generic arguments')
good('fn tail[T](values: []T) -> []T borrows(values) { return values[1:]; } fn empty() -> []i32 borrows() { return []i32{}; } fn main() { var a=[3]i32{1,2,3}; let s=tail[i32](a[:]); io.println(s[0]); io.println(len(empty())); }', '2\n0\n')
good('struct View { data: []i32; } fn view(s: []i32) -> View borrows(s) { return View{data:s}; } fn extract(v: View) -> []i32 borrows(v) { return v.data; } fn main(){var a=[2]i32{7,8}; io.println(extract(view(a[:]))[1]);}', '8\n')
bad('fn bad(s: []i32) -> []i32 borrows(s) { var a=[1]i32{3}; return a[:]; } fn main() {}', 'outlive local storage')
bad('fn bad(s: []i32) -> []i32 borrows(s) { var a=[1]i32{3}; var x=s; if(true){x=a[:];}else{x=s;} return x; } fn main() {}', 'outlive local storage')
bad('struct V {s: []i32;} fn bad(s: []i32)->V borrows(s){var v=V{s:s};var a=[1]i32{3};v.s=a[:];return v;} fn main(){}', 'outlive local storage')
bad('fn bad(a: []i32,b: []i32)->[]i32 borrows(a){return b;} fn main(){}', 'borrows contract')
bad('fn bad(a: [1]i32)->[]i32 borrows(a){return a[:];} fn main(){}', 'borrowed references')
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
