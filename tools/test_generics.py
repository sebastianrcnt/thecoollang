#!/usr/bin/env python3
from pathlib import Path
import subprocess
import os
import shlex
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
    let value_or=17;let is_ok=false;let reverse=3;let tail=4;let fill=5;
    assert(value_or==17 && is_ok==false && reverse==3 && tail==4 && fill==5);
    io.println(r.value_or[i64,string](parse(true), 0));
    io.println(r.is_ok[i64,string](parse(false)));
    io.println(o.value_or[i32](o.Option[i32].None, 7));
    var a = [3]i32{1,2,3}; s.reverse[i32](a[:]);
    io.println(s.tail[i32](a[:])[1]); s.fill[i32](a[:], 9); io.println(a[2]);
}''')
    for mode in ('tree','interp','jit','llvm','llvm-jit'):
        p = subprocess.run([ROOT/'tools/cool','run','--backend',mode,source], text=True,capture_output=True,timeout=30)
        assert (p.returncode,p.stdout,p.stderr)==(0,'42\nfalse\n7\n1\n9\n',''),p
    bootstrap=Path(tmp)/'bootstrap';bootstrap.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');bootstrap.chmod(0o755)
    for front in (ROOT/'build/cool-compiler',bootstrap):
        env={**os.environ,'COOL_FRONTEND':str(front)}
        p=subprocess.run([ROOT/'tools/cool','check',source],text=True,capture_output=True,timeout=30,env=env);assert p.returncode==0,p
        negative=Path(tmp)/'bad.cool';negative.write_text('import r "std/result";fn main(){let value_or=7;let incorrect=r.value_or;}')
        p=subprocess.run([ROOT/'tools/cool','check',negative],text=True,capture_output=True,timeout=30,env=env);assert p.returncode==2 and 'unknown variable' in p.stderr,p
    for command in (['fmt',str(source)],['fmt','--check',str(source)],['check',str(source)]):
        subprocess.run([ROOT/'tools/cool',*command],check=True)
print('generics: imported Result/Option, generic slices, all execution engines and tools PASS')
