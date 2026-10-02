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
