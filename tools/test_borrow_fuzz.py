#!/usr/bin/env python3
"""Seeded scoped-loan oracle: valid programs run, conflicting programs reject.

Generates random sequences of shared/exclusive loans over two locals, writes
through the root or an exclusive binding, and reads through a live loan. An
independent model of live loans decides which operations are legal; the emitted
valid program must run and print the modeled values, and one deliberately
conflicting operation must be rejected by both frontends.
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
ROOTS = ('a', 'b')


def generate(seed, steps):
    rng = random.Random(seed)
    lines = ['package main;', 'import "std/io";', 'fn main(){', '  var a = 0; var b = 0;']
    expected = []
    values = {'a': 0, 'b': 0}
    shared = {'a': [], 'b': []}
    exclusive = {'a': None, 'b': None}
    scopes = [[]]
    counter = 0

    def close_scope():
        if len(scopes) <= 1:
            return False
        lines.append('  }')
        for root, kind, name in scopes.pop():
            if kind == 'shared':
                shared[root].remove(name)
            else:
                exclusive[root] = None
        return True

    operations = ['shared'] * 3 + ['exclusive'] * 2 + ['write_root'] * 2 + ['read_shared'] + ['read_excl'] + ['open', 'close']
    for _ in range(steps):
        operation = rng.choice(operations)
        root = rng.choice(ROOTS)
        if operation == 'open':
            lines.append('  {')
            scopes.append([])
        elif operation == 'close':
            close_scope()
        elif operation == 'shared' and exclusive[root] is None:
            name = f'r{counter}'; counter += 1
            lines.append(f'  let {name} = &{root};')
            shared[root].append(name); scopes[-1].append((root, 'shared', name))
        elif operation == 'exclusive' and exclusive[root] is None and not shared[root]:
            name = f'm{counter}'; counter += 1
            lines.append(f'  let {name} = &mut {root};')
            exclusive[root] = name; scopes[-1].append((root, 'exclusive', name))
        elif operation == 'write_root' and exclusive[root] is None and not shared[root]:
            value = rng.randrange(-99, 100)
            values[root] = value
            lines.append(f'  {root} = {value};')
        elif operation == 'write_excl' and exclusive[root] is not None:
            value = rng.randrange(-99, 100)
            values[root] = value
            lines.append(f'  *{exclusive[root]} = {value};')
        elif operation == 'read_shared' and shared[root]:
            name = rng.choice(shared[root])
            lines.append(f'  io.println(*{name});')
            expected.append(str(values[root]))
        elif operation == 'read_excl' and exclusive[root] is not None:
            lines.append(f'  io.println(*{exclusive[root]});')
            expected.append(str(values[root]))
        if rng.random() < 0.2 and exclusive[root] is not None:
            value = rng.randrange(-99, 100)
            values[root] = value
            lines.append(f'  *{exclusive[root]} = {value};')
    while close_scope():
        pass
    for root in ROOTS:
        if exclusive[root] is not None:
            lines.append(f'  io.println(*{exclusive[root]});')
        elif shared[root]:
            lines.append(f'  io.println(*{shared[root][0]});')
        else:
            lines.append(f'  io.println({root});')
        expected.append(str(values[root]))
    lines.append('  io.println(7654321);')
    expected.append('7654321')
    lines.append('}')
    program = '\n'.join(lines) + '\n'
    return program, expected, (shared, exclusive)


def conflicting_tail(seed, program, state):
    """Append one operation that the current live loans must reject."""
    shared, exclusive = state
    for root in ROOTS:
        if exclusive[root] is not None:
            return program.replace('\n}\n', f'\n  {root} = 1;\n}}\n'), 'conflicts'
        if shared[root]:
            return program.replace('\n}\n', f'\n  {root} = 1;\n}}\n'), 'conflicts'
    return program.replace('\n}\n', f'\n  let bad = &mut a; let other = &a;\n}}\n'), 'conflicts'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', default='7,42,2026,1,99')
    parser.add_argument('--steps', type=int, default=80)
    parser.add_argument('--output')
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix='cool borrow fuzz ') as directory:
        work = Path(directory)
        legacy = work / 'legacy-frontend'
        legacy.write_text('#!/bin/sh\nexec %s --run %s "$@"\n' % (
            shlex.quote(str(ROOT / 'build/coolc')), shlex.quote(str(ROOT / 'build/language.BIN'))))
        legacy.chmod(0o755)
        frontends = [None, legacy]
        observations = []
        for seed in (int(value) for value in args.seeds.split(',')):
            program, expected, state = generate(seed, args.steps)
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
                bad, diagnostic = conflicting_tail(seed, program, state)
                bad_source = work / f'seed-{seed}-bad.cool'
                bad_source.write_text(bad)
                check = subprocess.run([str(ROOT / 'tools/cool'), 'check', bad_source],
                                       cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
                assert check.returncode == 2 and diagnostic in check.stderr, (seed, front, check)
                observations.append({'seed': seed, 'engine': 'reject', 'exit': check.returncode})
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({'seeds': args.seeds, 'steps': args.steps,
                                      'observations': observations}, indent=2) + '\n')
    print(f'borrow fuzz: {args.steps}-step seeded shared/exclusive loan programs run on five engines '
          f'and each modeled conflicting operation is rejected by both frontends PASS')


if __name__ == '__main__':
    main()
