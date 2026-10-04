#!/usr/bin/env python3
"""Source standard library across all engines, including binary IO and argv."""
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
def cool(*args,**kwargs):
    return subprocess.run([ROOT/'tools/cool',*args],capture_output=True,text=True,timeout=60,**kwargs)
PROGRAM = 'import "std/io";\nimport "std/os";\nimport "std/mem";\nimport v "std/vector";\nimport r "std/result";\nimport o "std/option";\nimport s "std/strings";\nimport m "std/math";\nimport fs "std/fs";\nfn main() {\n    assert(s.equal("한글", "한글"));\n    assert(!s.equal("a", "b"));\n    assert(s.starts_with("", "") && s.ends_with("abc", ""));\n    assert(!s.starts_with("a", "ab") && !s.ends_with("a", "ab"));\n    assert(r.value_or[i64,s.ParseError](s.parse_i64("+42"), 0) == 42);\n    assert(!r.is_ok[i64,s.ParseError](s.parse_i64("-9223372036854775809")));\n    assert(!r.is_ok[i64,s.ParseError](s.parse_i64("")));\n    assert(!r.is_ok[i64,s.ParseError](s.parse_i64("+")));\n    assert(!r.is_ok[i64,s.ParseError](s.parse_i64("1a")));\n    assert(!r.is_ok[i64,m.ArithmeticError](m.add_i64(-9223372036854775808, -1)));\n    assert(!r.is_ok[i64,m.ArithmeticError](m.divide_i64(1, 0)));\n    assert(!r.is_ok[i64,m.ArithmeticError](m.divide_i64(-9223372036854775808, -1)));\n    assert(r.value_or[i64,m.ArithmeticError](m.divide_i64(42, 2), 0) == 21);\n    assert(!r.is_ok[v.Vector[u8],i32](fs.read(os.arg(1))));\n    io.println(s.length("hello"));\n    io.println(s.starts_with("hello", "he"));\n    io.println(s.ends_with("hello", "lo"));\n    io.println(r.value_or[i64,s.ParseError](s.parse_i64("-9223372036854775808"), 0));\n    io.println(r.is_ok[i64,s.ParseError](s.parse_i64("9223372036854775808")));\n    io.println(m.clamp[i64](42, 1, 10));\n    io.println(r.is_ok[i64,m.ArithmeticError](m.add_i64(9223372036854775807, 1)));\n    { var values=v.create[own[i64]]();\n      unsafe {\n        for (var i=0; i<80; i=i+1) { v.append[own[i64]](&mut values, new[i64](i)); }\n        io.println(v.len[own[i64]](&values));\n        io.println(**v.at[own[i64]](&values, 40));\n        let last=o.value_or[own[i64]](v.pop[own[i64]](&mut values), new[i64](-1));\n        io.println(*last);\n        v.clear[own[i64]](&mut values);\n        io.println(v.len[own[i64]](&values));\n      }\n    }\n    io.println(mem.owner_count());\n    { var numbers = v.create[i64](); unsafe {\n      for (var i=0; i<1024; i=i+1) { v.append[i64](&mut numbers, i); }\n      var cursor=v.cursor[i64](&numbers);\n      for (var i=0; i<1024; i=i+1) { assert(*v.next[i64](&raw cursor) == i); }\n      assert(v.next[i64](&raw cursor) == null);\n      for (var i=1023; i>=0; i=i-1) { assert(o.value_or[i64](v.pop[i64](&mut numbers), -1) == i); }\n      assert(!o.is_some[i64](v.pop[i64](&mut numbers)));\n      v.append[i64](&mut numbers, 42); assert(*v.at[i64](&numbers, 0) == 42);\n    } }\n    assert(mem.owner_count() == 0);\n    var bytes=v.create[u8]();\n    unsafe { v.append[u8](&mut bytes, 65); v.append[u8](&mut bytes, 0); v.append[u8](&mut bytes, 255);\n      io.println(r.value_or[usize,i32](fs.write(os.arg(0), &bytes), 0)); }\n    var read=r.value_or[v.Vector[u8],i32](fs.read(os.arg(0)), v.create[u8]());\n    unsafe { io.println(v.len[u8](&read)); io.println(*v.at[u8](&read, 2)); }\n}\n'
EXPECTED='5\ntrue\ntrue\n-9223372036854775808\nfalse\n10\nfalse\n80\n40\n79\n0\n0\n3\n3\n255\n'
with tempfile.TemporaryDirectory(prefix='cool-stdlib-') as tmp:
    tmp=Path(tmp); source=tmp/'main.cool'; source.write_text(PROGRAM)
    output=tmp/'roundtrip.bin';missing=tmp/'missing'
    for mode in ('tree','interp','jit','llvm','llvm-jit'):
        p=cool('run','--backend',mode,str(source),'--',str(output),str(missing))
        assert (p.returncode,p.stdout,p.stderr)==(0,EXPECTED,''),(mode,p)
        assert output.read_bytes()==bytes([65,0,255]);output.unlink()
    binary=tmp/'standalone'
    p=cool('build','--release',str(source),'-o',str(binary));assert p.returncode==0,p
    p=subprocess.run([binary,output,missing],capture_output=True,text=True,timeout=20)
    assert (p.returncode,p.stdout,p.stderr)==(0,EXPECTED,''),p
    source.write_text('import "std/os"; import "std/io"; fn main() { io.println(os.arg_count()); for (var i:usize=0;i<os.arg_count();i=i+1) {io.println(os.arg(i));} }')
    for mode in ('tree','interp','jit','llvm','llvm-jit'):
        p=cool('run','--backend',mode,str(source),'--','한글','--flag','')
        assert (p.returncode,p.stdout,p.stderr)==(0,'3\n한글\n--flag\n\n',''),p
    source.write_text('import v "std/vector"; fn main() { var a=v.create[i64](); unsafe { v.at[i64](&a,0); } }')
    for mode in ('tree','interp','jit','llvm','llvm-jit'):
        p=cool('run','--backend',mode,str(source))
        assert p.returncode!=0 and 'assertion failed' in p.stderr,p
print('stdlib: strings/checked arithmetic, move-only vectors, boundaries, cursors, binary files/errors and argv across five engines plus standalone release PASS')
