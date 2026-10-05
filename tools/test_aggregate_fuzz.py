#!/usr/bin/env python3
"""Seeded aggregate-destruction oracle: exact owner counts for nested owners.

Generates random values built from structs with owned fields, fixed arrays of
owners and enums with owned payloads, asserts the exact live owner count while
each value is alive, reads a modeled element, and requires zero owners after the
scope exits. Runs on five engines and both frontends.
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
import "std/mem";import "std/io";
struct Leaf { value: own[i64]; }
struct Pair { left: own[i64]; right: own[i64]; }
struct Box { leaf: Leaf; pair: Pair; }
enum Choice { None; One(own[i64]); Two(own[Pair]); }
'''


def gen_value(rng, depth):
    """Return (cool expression, owner count, [(access expression, value)])."""
    kinds = ['leaf', 'pair', 'array', 'choice-none', 'choice-one', 'choice-two', 'box', 'deep']
    if depth <= 0:
        kinds = ['leaf', 'pair', 'array', 'choice-none', 'choice-one']
    kind = rng.choice(kinds)
    if kind == 'leaf':
        v = rng.randrange(-999, 1000)
        return f'Leaf {{ value: new[i64]({v}) }}', 1, [('*g.value', v)]
    if kind == 'pair':
        a, b = rng.randrange(-999, 1000), rng.randrange(-999, 1000)
        return (f'Pair {{ left: new[i64]({a}), right: new[i64]({b}) }}', 2,
                [('*g.left', a), ('*g.right', b)])
    if kind == 'array':
        n = rng.randrange(1, 5)
        values = [rng.randrange(-999, 1000) for _ in range(n)]
        literal = ', '.join(f'new[i64]({value})' for value in values)
        return (f'[N]own[i64] {{ {literal} }}', n, [(f'*g[{i}]', value) for i, value in enumerate(values)])
    if kind == 'choice-none':
        return 'Choice.None', 0, []
    if kind == 'choice-one':
        v = rng.randrange(-999, 1000)
        return f'Choice.One(new[i64]({v}))', 1, [('*one', v)]
    if kind == 'choice-two':
        a, b = rng.randrange(-999, 1000), rng.randrange(-999, 1000)
        return (f'Choice.Two(new[Pair](Pair {{ left: new[i64]({a}), right: new[i64]({b}) }}))', 3,
                [('*two.left', a), ('*two.right', b)])
    if kind == 'box':
        a, b, c = (rng.randrange(-999, 1000) for _ in range(3))
        return (f'Box {{ leaf: Leaf {{ value: new[i64]({a}) }}, pair: Pair {{ left: new[i64]({b}), right: new[i64]({c}) }} }}',
                3, [('*g.leaf.value', a), ('*g.pair.left', b), ('*g.pair.right', c)])
    # deep: two nested aggregates
    a, b, c = (rng.randrange(-999, 1000) for _ in range(3))
    return (f'Box {{ leaf: Leaf {{ value: new[i64]({a}) }}, pair: Pair {{ left: new[i64]({b}), right: new[i64]({c}) }} }}',
            3, [('*g.leaf.value', a), ('*g.pair.right', c)])


def generate(seed, steps):
    rng = random.Random(seed)
    lines = [PRELUDE, 'fn main(){']
    for _ in range(steps):
        expr, count, reads = gen_value(rng, rng.randrange(0, 3))
        if '[N]own[i64]' in expr:
            expr = expr.replace('[N]', f'[{count}]')
        lines.append('  {')
        lines.append(f'    var g = {expr};')
        lines.append(f'    assert(mem.owner_count() == {count});')
        one = [(a, v) for a, v in reads if a.startswith('*one')]
        two = [(a, v) for a, v in reads if a.startswith('*two')]
        plain = [(a, v) for a, v in reads if not a.startswith('*one') and not a.startswith('*two')]
        if one:
            lines.append('    match (move g) { Choice.One(v) => { assert(*v == ' + str(one[0][1]) +
                         '); } Choice.None => { assert(false); } Choice.Two(p) => { assert(false); } }')
        if two:
            asserts = ' '.join('assert(*(*p).' + ('left' if a.endswith('left') else 'right') + ' == ' + str(v) + ');'
                               for a, v in two)
            lines.append('    match (move g) { Choice.Two(p) => { ' + asserts +
                         ' } Choice.None => { assert(false); } Choice.One(v) => { assert(false); } }')
        for access, value in plain:
            lines.append(f'    assert({access} == {value});')
        lines.append('  }')
        lines.append('  assert(mem.owner_count() == 0);')
    lines.append('  io.println(1234567);')
    lines.append('}')
    return '\n'.join(lines) + '\n', ['1234567']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', default='7,42,2026,1,99')
    parser.add_argument('--steps', type=int, default=60)
    parser.add_argument('--frontend', help='extra frontend executable')
    parser.add_argument('--sanitize-runtime', action='store_true')
    parser.add_argument('--output')
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix='cool aggregate fuzz ') as directory:
        work = Path(directory)
        legacy = work / 'legacy-frontend'
        legacy.write_text('#!/bin/sh\nexec %s --run %s "$@"\n' % (
            shlex.quote(str(ROOT / 'build/coolc')), shlex.quote(str(ROOT / 'build/language.BIN'))))
        legacy.chmod(0o755)
        frontends = [None, legacy]
        if args.frontend:
            frontends.append(Path(args.frontend))
        observations = []
        for seed in (int(value) for value in args.seeds.split(',')):
            program, expected = generate(seed, args.steps)
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
                if args.sanitize_runtime:
                    ir = work / f'seed-{seed}-{front}.ll'
                    emit = subprocess.run([str(ROOT / 'tools/cool'), 'emit-ir', source, '-o', ir],
                                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
                    assert emit.returncode == 0, (seed, front, emit.stderr)
                    instrumented = work / f'seed-{seed}-{front}-asan.ll'
                    instrumented.write_text('\n'.join(
                        line.replace(' {', ' sanitize_address {') if line.startswith('define ') else line
                        for line in ir.read_text().splitlines()) + '\n')
                    asan = work / f'seed-{seed}-{front}-asan.bin'
                    link = subprocess.run(['clang', '-Wno-override-module', '-O1', '-g',
                                           '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                                           instrumented, ROOT / 'language/runtime.c', '-o', asan],
                                          cwd=ROOT, capture_output=True, text=True, timeout=180)
                    assert link.returncode == 0, (seed, front, link.stderr)
                    run = subprocess.run([str(asan)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
                    assert (run.returncode, run.stdout, run.stderr) == (0, want, ''), (seed, front, 'ASan', run)
                    observations.append({'seed': seed, 'engine': 'ASan/UBSan', 'exit': run.returncode})
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({'seeds': args.seeds, 'steps': args.steps,
                                      'observations': observations}, indent=2) + '\n')
    print(f'aggregate fuzz: {args.steps}-value seeded struct/array/enum owned-payload programs with exact '
          f'live-owner counts across five engines + O2 on {len(frontends)} frontends PASS')


if __name__ == '__main__':
    main()
