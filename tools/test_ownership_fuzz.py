#!/usr/bin/env python3
"""Seeded ownership/evaluation-order oracle across engines and both frontends.

Generates programs that move, replace, mutate, swap and scope-drop owning
values, plus a fixed left-to-right argument-evaluation probe, and compares the
program output against an independent Python model of live owners and values.
Every operation asserts the exact live owner count; the scope must end at zero.
"""
import argparse
import os
import random
import shlex
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINES = ('tree', 'interp', 'jit', 'llvm', 'llvm-jit')

PREAMBLE = '''package main;
import "std/mem";import "std/io";
fn next(c: &mut i64) -> i64 { *c = *c + 1; return *c; }
fn pick(a: own[i64], b: own[i64]) -> i64 { return *a * 100 + *b; }
fn take(a: own[i64]) -> i64 { return *a; }
fn main(){
  var c1 = 0; var c2 = 100;
  io.println(pick(new[i64](next(&mut c1)), new[i64](next(&mut c2))));
  assert(c1 == 1); assert(c2 == 101);
'''


def generate(seed, slots, steps):
    rng = random.Random(seed)
    lines = [PREAMBLE]
    expected = ['201']  # left-to-right pick() probe
    model = [rng.randrange(-999, 1000) for _ in range(slots)]
    lines.append('  {')
    for index, value in enumerate(model):
        lines.append(f'  var s{index}: own[i64] = new[i64]({value});')
    lines.append(f'  assert(mem.owner_count() == {slots});')

    def live():
        return sum(1 for value in model if value is not None)

    def check():
        lines.append(f'  assert(mem.owner_count() == {live()});')

    operations = ['move'] * 3 + ['replace'] * 3 + ['mutate', 'read', 'swap', 'scope', 'branch', 'take']
    for number in range(steps):
        operation = rng.choice(operations)
        lines.append(f'  // seed {seed}, operation {number}: {operation}')
        if operation == 'replace':
            index = rng.randrange(slots)
            value = rng.randrange(-999, 1000)
            model[index] = value
            lines.append(f'  s{index} = new[i64]({value});')
        elif operation == 'move':
            source = rng.randrange(slots)
            target = rng.randrange(slots)
            if model[source] is None or source == target:
                continue
            model[target] = model[source]
            model[source] = None
            lines.append(f'  s{target} = move s{source};')
        elif operation == 'mutate' and model[rng.randrange(slots)] is not None:
            index = rng.randrange(slots)
            if model[index] is None:
                continue
            value = rng.randrange(-999, 1000)
            model[index] = value
            lines.append(f'  *s{index} = {value};')
        elif operation == 'read':
            index = rng.randrange(slots)
            if model[index] is None:
                continue
            lines.append(f'  io.println(*s{index});')
            expected.append(str(model[index]))
        elif operation == 'swap':
            left, right = rng.sample(range(slots), 2)
            if model[left] is None or model[right] is None:
                continue
            model[left], model[right] = model[right], model[left]
            lines.append(f'  {{ let t = move s{left}; s{left} = move s{right}; s{right} = move t; }}')
        elif operation == 'scope':
            index = rng.randrange(slots)
            if model[index] is None:
                continue
            model[index] = None
            lines.append(f'  {{ let t = move s{index}; }}')
        elif operation == 'branch':
            index = rng.randrange(slots)
            left = rng.randrange(-999, 1000)
            right = rng.randrange(-999, 1000)
            flag = rng.choice([True, False])
            model[index] = left if flag else right
            lines.append(f'  if ({str(flag).lower()}) {{ s{index} = new[i64]({left}); }} else {{ s{index} = new[i64]({right}); }}')
        elif operation == 'take':
            value = rng.randrange(-999, 1000)
            lines.append(f'  io.println(take(new[i64]({value})));')
            expected.append(str(value))
        check()
    lines.append(f'  assert(mem.owner_count() == {live()});')
    lines.append('  }')
    lines.append('  assert(mem.owner_count() == 0);')
    lines.append('  io.println(1234567);')
    lines.append('}')
    expected.append('1234567')
    return '\n'.join(lines) + '\n', expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', default='7,42,2026')
    parser.add_argument('--slots', type=int, default=6)
    parser.add_argument('--steps', type=int, default=60)
    parser.add_argument('--frontend', help='extra frontend executable')
    parser.add_argument('--sanitize-runtime', action='store_true')
    parser.add_argument('--output')
    args = parser.parse_args()

    frontends = []
    if args.frontend:
        frontends.append(Path(args.frontend))

    observations = []
    with tempfile.TemporaryDirectory(prefix='cool ownership fuzz ') as directory:
        work = Path(directory)
        legacy = work / 'legacy-frontend'
        legacy.write_text('#!/bin/sh\nexec %s --run %s "$@"\n' % (
            shlex.quote(str(ROOT / 'build/coolc')), shlex.quote(str(ROOT / 'build/language.BIN'))))
        legacy.chmod(0o755)
        frontends = [None, legacy] + frontends
        for seed in (int(value) for value in args.seeds.split(',')):
            program, expected = generate(seed, args.slots, args.steps)
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
                    observations.append({'seed': seed, 'frontend': 'legacy' if front == legacy else ('production' if front is None else str(front)),
                                         'engine': engine, 'exit': run.returncode})
                binary = work / f'seed-{seed}-{front}.bin'
                build = subprocess.run([str(ROOT / 'tools/cool'), 'build', '--release', source, '-o', binary],
                                       cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
                assert build.returncode == 0, (seed, front, build.stderr)
                run = subprocess.run([str(binary)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
                assert (run.returncode, run.stdout, run.stderr) == (0, want, ''), (seed, front, 'O2', run)
                observations.append({'seed': seed, 'frontend': 'legacy' if front == legacy else ('production' if front is None else str(front)),
                                     'engine': 'O2', 'exit': run.returncode})
                if args.sanitize_runtime:
                    ir = work / f'seed-{seed}-{front}.ll'
                    emit = subprocess.run([str(ROOT / 'tools/cool'), 'emit-ir', source, '-o', ir],
                                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
                    assert emit.returncode == 0, (seed, front, emit.stderr)
                    instrumented = work / f'seed-{seed}-{front}-asan.ll'
                    instrumented.write_text('\n'.join(
                        line.replace(' {', ' sanitize_address {') if line.startswith('define ') else line
                        for line in ir.read_text().splitlines()) + '\n')
                    checked = work / f'seed-{seed}-{front}-checked.ll'
                    check = subprocess.run(['clang', '-Wno-override-module', '-O1', '-fsanitize=address',
                                            '-S', '-emit-llvm', instrumented, '-o', checked],
                                           cwd=ROOT, capture_output=True, text=True, timeout=180)
                    assert check.returncode == 0, (seed, front, check.stderr)
                    assert '__asan_report_load' in checked.read_text(), (seed, front)
                    asan = work / f'seed-{seed}-{front}-asan.bin'
                    link = subprocess.run(['clang', '-Wno-override-module', '-O1', '-g',
                                           '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                                           instrumented, ROOT / 'language/runtime.c', '-o', asan],
                                          cwd=ROOT, capture_output=True, text=True, timeout=180)
                    assert link.returncode == 0, (seed, front, link.stderr)
                    run = subprocess.run([str(asan)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
                    assert (run.returncode, run.stdout, run.stderr) == (0, want, ''), (seed, front, 'ASan', run)
                    observations.append({'seed': seed, 'frontend': 'legacy' if front == legacy else ('production' if front is None else str(front)),
                                         'engine': 'ASan/UBSan', 'exit': run.returncode})
    if args.output:
        import json
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({'slots': args.slots, 'steps': args.steps,
                                      'seeds': args.seeds, 'observations': observations}, indent=2) + '\n')
    print(f'ownership fuzz: {args.steps}-step seeded move/replace/mutate/swap/scope/branch/take programs, '
          f'left-to-right argument evaluation and exact live-owner counts across five engines + O2 on '
          f'{len(frontends)} frontends PASS')


if __name__ == '__main__':
    main()
