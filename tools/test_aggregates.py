#!/usr/bin/env python3
"""Aggregate safety, directory visibility, tooling and persistent session regressions."""
from pathlib import Path
import subprocess
import os
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FRONT = [Path(os.environ.get('COOL_FRONTEND', ROOT/'build/cool-compiler'))]

def run(command, *, code=0, **kwargs):
    p = subprocess.run(command, text=True, capture_output=True, timeout=30, **kwargs)
    assert p.returncode == code, (command, p.returncode, p.stdout, p.stderr)
    return p

with tempfile.TemporaryDirectory(prefix='cool-aggregates-') as tmp:
    tmp = Path(tmp)
    source = tmp/'error.cool'
    for expression, diagnostic in [
        ('io.println(a[2]);', 'index out of bounds'),
        ('io.println(a[-1]);', 'index out of bounds'),
        ('io.println(a[18446744073709551615]);', 'index out of bounds'),
        ('let s = a[1:3];', 'slice bounds out of range'),
        ('let s = a[1:0];', 'slice bounds out of range'),
        ('let s = a[0:1]; io.println(s[1]);', 'index out of bounds'),
        ('let s = a[0:1]; let t = s[:2];', 'slice bounds out of range'),
    ]:
        source.write_text('import "std/io"; fn main() { var a = [2]i32{1,2}; '+expression+' }')
        for backend in ('run', 'bytecode', 'jit', 'auto'):
            assert diagnostic in run([*FRONT, backend, source], code=2).stderr
        run([*FRONT, 'llvm', source, tmp/'error.ll'])
        run(['clang', '-Wno-override-module', '-O2', tmp/'error.ll', ROOT/'language/runtime.c', '-o', tmp/'error'])
        assert diagnostic in run([tmp/'error'], code=2).stderr

    project = tmp/'project'; project.mkdir(); (project/'model').mkdir()
    cli = [ROOT/'tools/cool']
    run([*cli, 'mod', 'init', 'example.com/aggregate/app'], cwd=project)
    model = project/'model/model.cool'
    model.write_text('package model; pub struct Packet { pub values: [2]i32; } struct Hidden { value: i64; }')
    main = project/'main.cool'
    main.write_text('package main; import "std/io"; import m "example.com/aggregate/app/model"; pub fn copy(p: m.Packet) -> m.Packet { return p; } fn main() { var p = m.Packet { values: [2]i32{7,8} }; let q = copy(p); p.values[0]=9; io.println(q.values[0]); }')
    for backend in ('tree', 'interp', 'jit', 'llvm', 'llvm-jit'):
        assert run([*cli, 'run', '--backend', backend], cwd=project).stdout == '7\n'
    assert 'pub fn copy(p: Packet) -> Packet;' in run([*cli, 'doc'], cwd=project).stdout
    assert 'pub struct Packet { pub values: [2]i32; }' in run([*cli, 'doc', 'model'], cwd=project).stdout
    run([*cli, 'fmt', '.'], cwd=project)
    run([*cli, 'fmt', '--check', '.'], cwd=project)
    assert run([*cli, 'run'], cwd=project).stdout == '7\n'
    model.write_text('package model; pub struct Packet { values: [2]i32; }')
    assert 'private' in run([*cli, 'check'], cwd=project, code=2).stderr
    model.write_text('package model; struct Packet { pub values: [2]i32; }')
    assert 'private' in run([*cli, 'check'], cwd=project, code=2).stderr

session = '''struct Bad { recurse: Bad; }
struct Pair { value: i64; }
var a = [2]Pair{Pair{value:1},Pair{value:2}};
let s = a[:];
fn read(p: Pair) -> i64 { return p.value; }
read(a[0])
read(a[0])
read(a[0])
read(a[0])
fn read(p: Pair) -> i64 { return p.value+10; }
s[0].value = 9;
read(a[0])
struct Pair { value: i32; }
read(a[0])
:quit
'''
p = run([*FRONT, 'repl-quiet'], input=session)
assert p.stdout == '1\n1\n1\n1\n19\n19\n', (p.stdout, p.stderr)
assert 'recursive aggregate' in p.stderr and 'layout redefinition' in p.stderr, p.stderr
print('aggregates: runtime bounds across engines, public/private types and fields, LLVM JIT, formatter/docs, REPL rollback and replacement PASS')

session = 'var a = [1]i32{1};\nvar s = a[:];\n{ var b = [1]i32{7}; s = b[:]; assert(false); }\nvar c = [1]i32{99};\nio.println(s[0]);\n:quit\n'
p = run([*FRONT, 'repl-quiet'], input=session)
assert p.stdout == '7\n' and 'assertion failed' in p.stderr, (p.stdout, p.stderr)
print('aggregates: runtime-error recovery preserves storage borrowed by surviving REPL bindings PASS')
