#!/usr/bin/env python3
"""Source diagnostics: each rejected program names the actual problem.

Narrowing (numeric) and non-convertible type mismatches are reported
differently, and the other common rejection categories keep a stable, specific
message on both frontends.
"""
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ('narrowing-int', 'fn main(){ let x: u8 = 256; }',
     'narrowing conversion requires an explicit cast'),
    ('narrowing-literal', 'fn main(){ let x: i64 = 18446744073709551615; }',
     'narrowing conversion requires an explicit cast'),
    ('incompatible-string', 'fn main(){ var x: i64 = "hi"; }',
     'value and target types do not convert'),
    ('incompatible-bool', 'fn main(){ let x: bool = 3; }',
     'value and target types do not convert'),
    ('incompatible-pointer', 'fn main(){ let p: *i64 = 5; }',
     'value and target types do not convert'),
    ('incompatible-argument', 'fn a(x: i64) {} fn main(){ a(true); }',
     'value and target types do not convert'),
    ('unknown-variable', 'fn main(){ io.println(nope); }', 'unknown variable'),
    ('unknown-function', 'fn main(){ nope(); }', 'unknown function'),
    ('missing-return', 'fn f() -> i64 {} fn main(){}', 'not every path returns a value'),
    ('wrong-argument-count', 'fn f(a: i64) -> i64 { return a; } fn main(){ f(); }', 'wrong argument count'),
    ('use-after-move', 'fn main(){ var x = new[i64](1); let y = move x; let z = *x; }', 'use of moved value'),
    ('borrow-conflict', 'fn main(){ var x = 1; let r = &x; let m = &mut x; }',
     'access conflicts with a live scoped reference'),
    ('duplicate-function', 'fn f(){} fn f(){} fn main(){}', 'duplicate function declaration'),
]


def main():
    with tempfile.TemporaryDirectory(prefix='cool diagnostics ') as directory:
        work = Path(directory)
        legacy = work / 'legacy-frontend'
        legacy.write_text('#!/bin/sh\nexec %s --run %s "$@"\n' % (
            shlex.quote(str(ROOT / 'build/coolc')), shlex.quote(str(ROOT / 'build/language.BIN'))))
        legacy.chmod(0o755)
        source = work / 'case.cool'
        observations = []
        for frontend in (None, legacy):
            env = dict(os.environ)
            if frontend is not None:
                env['COOL_FRONTEND'] = str(frontend)
            for name, body, message in CASES:
                source.write_text('package main;\nimport "std/io";\n' + body + '\n')
                run = subprocess.run([str(ROOT / 'tools/cool'), 'check', source],
                                     cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
                assert run.returncode == 2 and message in run.stderr, (name, frontend, run)
                assert 'narrowing' not in run.stderr or 'narrowing' in message, (name, frontend, run)
                observations.append({'case': name, 'frontend': 'legacy' if frontend else 'production'})
    print(f'diagnostics: {len(CASES)} rejection categories name the actual problem on both frontends; '
          f'narrowing and non-convertible mismatches stay distinct PASS')


if __name__ == '__main__':
    main()
