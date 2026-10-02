#!/usr/bin/env python3
from pathlib import Path
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='cool-generics-') as tmp:
    source = Path(tmp)/'main.cool'
    source.write_text('''package main;
import "std/io";
import r "std/result";
import o "std/option";
import s "std/slice";
fn parse(good: bool) -> r.Result[i64,string] {
    if (good) { return r.Result[i64,string].Ok(42); }
    return r.Result[i64,string].Err("bad");
}
fn main() {
    io.println(r.value_or[i64,string](parse(true), 0));
    io.println(r.is_ok[i64,string](parse(false)));
    io.println(o.value_or[i32](o.Option[i32].None, 7));
    var a = [3]i32{1,2,3}; s.reverse[i32](a[:]);
    io.println(s.tail[i32](a[:])[1]); s.fill[i32](a[:], 9); io.println(a[2]);
}''')
    for mode in ('tree','interp','jit','llvm','llvm-jit'):
        p = subprocess.run([ROOT/'tools/cool','run','--backend',mode,source], text=True,capture_output=True,timeout=30)
        assert (p.returncode,p.stdout,p.stderr)==(0,'42\nfalse\n7\n1\n9\n',''),p
    for command in (['fmt',str(source)],['fmt','--check',str(source)],['check',str(source)]):
        subprocess.run([ROOT/'tools/cool',*command],check=True)
print('generics: imported Result/Option, generic slices, all execution engines and tools PASS')
