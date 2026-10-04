#!/usr/bin/env python3
from pathlib import Path
import subprocess
ROOT = Path(__file__).resolve().parents[1]
source = '''var x = 40;
x + 2
fn value() -> i64 { return 1; }
fn caller() -> i64 { return value(); }
caller()
caller()
caller()
caller()
:stats
fn value() -> i64 { return 9; }
caller()
:stats
fn value(n: i64) -> i64 { return n; }
caller()
x = x + 1;
x
let bad: bool = 123;
let good = 7;
good
fn failed() -> i64 { return missing; }
caller()
:quit
'''
p = subprocess.run([ROOT/'tools/cool', 'repl'], input=source, text=True, capture_output=True, timeout=20)
assert p.returncode == 0, p
assert p.stdout.splitlines() == [
    '42', '1', '1', '1', '1',
    'functions=2 compiled=2 bytecode_compilations=2 jit_compilations=2',
    '9', 'functions=2 compiled=2 bytecode_compilations=3 jit_compilations=2',
    '9', '41', '7', '9'], (p.stdout, p.stderr)
assert 'signature change requires a new session' in p.stderr
assert 'incompatible types' in p.stderr
assert 'unknown variable' in p.stderr
print('REPL: persistent locals, adaptive JIT, changed-function-only compilation, live caller dispatch, error rollback PASS')

source = '\n'.join(['unsafe { missing; }', 'let p: *i64 = null;', '*p', 'extern "C" fn abs(n: i32) -> i32;', 'unsafe { io.println(abs(-9)); }', ':quit', ''])
p = subprocess.run([ROOT/'tools/cool', 'repl'], input=source, text=True, capture_output=True, timeout=20)
assert p.returncode == 0 and p.stdout == '9\n', (p.stdout, p.stderr)
assert 'requires unsafe' in p.stderr, p.stderr
print('REPL: unsafe scope cannot escape a rejected submission; C declarations PASS')

source = 'var n: f32 = f32(1.25);\nvar p: *f32 = null;\nunsafe { p = &raw n; }\n' + ''.join(f'var x{i} = {i};\n' for i in range(100)) + 'unsafe { *p = f32(2.5); }\nn\n:quit\n'
p = subprocess.run([ROOT/'tools/cool', 'repl'], input=source, text=True, capture_output=True, timeout=20)
assert (p.returncode, p.stdout, p.stderr) == (0, '2.5\n', ''), p
print('REPL: local addresses remain stable as the session grows PASS')
