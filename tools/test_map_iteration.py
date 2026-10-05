#!/usr/bin/env python3
"""Borrowed in-order map iteration: sorted values, remaining counts, conflicts.

An independent Python model sorts the inserted keys; the generated program must
print values in that key order on five engines and both frontends, count down
through remaining(), yield None on an empty map, and reject mutation while an
iterator (or a retained value result) is live.
"""
import argparse
import json
import os
import random
import shlex
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINES = ('tree', 'interp', 'jit', 'llvm', 'llvm-jit')
PRELUDE = '''package main;
import m "std/map";import t "std/text";import o "std/option";import r "std/result";import "std/io";
fn key(value:string)->t.Text{return r.value_or[t.Text,t.Utf8Error](t.from_literal(value),t.create());}
'''


def literal(value):
    return json.dumps(value, ensure_ascii=False)


def generate(seed, count):
    rng = random.Random(seed)
    model = {}
    lines = [PRELUDE, 'fn main(){', '  var map = m.create[i64]();']
    for index in range(count):
        name = f'k{index:03d}-{rng.randrange(100000)}'
        model[name] = rng.randrange(-1000, 1000)
    for name, value in model.items():
        lines.append(f'  m.insert[i64](&mut map, key({literal(name)}), {value});')
    lines.append(f'  assert(m.len[i64](&map) == {len(model)});')
    lines.append('  var it = m.iter[i64](&map);')
    lines.append(f'  assert(it.remaining() == {len(model)});')
    lines.append('  while (it.remaining() > 0) {')
    lines.append('    match (it.next()) {')
    lines.append('      o.Option[&i64].None => { assert(false); }')
    lines.append('      o.Option[&i64].Some(value) => { io.println(*value); }')
    lines.append('    }')
    lines.append('  }')
    lines.append('  match (it.next()) { o.Option[&i64].None => {}, o.Option[&i64].Some(value) => { assert(false); } }')
    lines.append('  io.println(1234567);')
    lines.append('}')
    expected = [str(model[name]) for name in sorted(model)]
    expected.append('1234567')
    return '\n'.join(lines) + '\n', expected


NEGATIVE = [
    ('mutate-while-iterating',
     '  m.insert[i64](&mut map, key("b"), 2);', 'conflicts'),
    ('retained-value-blocks-next',
     '  let first = it.next(); let second = it.next();', 'conflicts'),
]
POSITIVE_EXTRA = '''
fn empty(){ var map = m.create[i64](); var it = m.iter[i64](&map); assert(it.remaining() == 0);
  match (it.next()) { o.Option[&i64].None => { io.println(7); } o.Option[&i64].Some(value) => { assert(false); } } }
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', default='7,42,2026')
    parser.add_argument('--count', type=int, default=40)
    parser.add_argument('--output')
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix='cool map iteration ') as directory:
        work = Path(directory)
        legacy = work / 'legacy-frontend'
        legacy.write_text('#!/bin/sh\nexec %s --run %s "$@"\n' % (
            shlex.quote(str(ROOT / 'build/coolc')), shlex.quote(str(ROOT / 'build/language.BIN'))))
        legacy.chmod(0o755)
        frontends = [None, legacy]
        observations = []
        for seed in (int(value) for value in args.seeds.split(',')):
            program, expected = generate(seed, args.count)
            source = work / f'seed-{seed}.cool'
            source.write_text(program)
            want = '\n'.join(expected) + '\n'
            for front in frontends:
                env = dict(os.environ)
                if front is not None:
                    env['COOL_FRONTEND'] = str(front)
                for engine in ENGINES:
                    run = subprocess.run([str(ROOT / 'tools/cool'), 'run', '--backend', engine, source],
                                         cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
                    assert (run.returncode, run.stdout, run.stderr) == (0, want, ''), (seed, front, engine, run)
                    observations.append({'seed': seed, 'engine': engine, 'exit': run.returncode})
                binary = work / f'seed-{seed}-{front}.bin'
                build = subprocess.run([str(ROOT / 'tools/cool'), 'build', '--release', source, '-o', binary],
                                       cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
                assert build.returncode == 0, (seed, front, build.stderr)
                run = subprocess.run([str(binary)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
                assert (run.returncode, run.stdout, run.stderr) == (0, want, ''), (seed, front, 'O2', run)
                observations.append({'seed': seed, 'engine': 'O2', 'exit': run.returncode})
                for name, tail, diagnostic in NEGATIVE:
                    bad = work / f'seed-{seed}-{name}.cool'
                    bad.write_text(PRELUDE + 'fn main(){ var map = m.create[i64](); m.insert[i64](&mut map, key("a"), 1);\n'
                                   '  var it = m.iter[i64](&map);\n' + tail + '\n}\n')
                    check = subprocess.run([str(ROOT / 'tools/cool'), 'check', bad],
                                           cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
                    assert check.returncode == 2 and diagnostic in check.stderr, (seed, front, name, check)
                empty = work / f'seed-{seed}-empty.cool'
                empty.write_text(PRELUDE + POSITIVE_EXTRA + 'fn main(){ empty(); }\n')
                run = subprocess.run([str(ROOT / 'tools/cool'), 'run', '--backend', 'tree', empty],
                                     cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
                assert (run.returncode, run.stdout, run.stderr) == (0, '7\n', ''), (seed, front, run)
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({'seeds': args.seeds, 'count': args.count,
                                      'observations': observations}, indent=2) + '\n')
    print(f'map iteration: {args.count}-key sorted borrowed in-order values, remaining counts, empty-map '
          f'None and mutation/retention conflicts across five engines + O2 on {len(frontends)} frontends PASS')


if __name__ == '__main__':
    main()
