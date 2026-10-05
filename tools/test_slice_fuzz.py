#!/usr/bin/env python3
"""Seeded slice/reslicing oracle: modeled element values through slice chains.

Builds an owning scalar array, derives a chain of nested subslices, performs
modeled reads and writes only through the deepest slice, calls a function that
consumes a slice, stores a slice in a struct, then verifies the backing array
after every slice scope has closed and requires zero owners. Runs on five
engines and both frontends.
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
struct View { items: []i64; }
fn total(values: []i64) -> i64 { var sum: i64 = 0; for (var i: usize = 0; i < len(values); i = i + 1) { sum = sum + values[i]; } return sum; }
fn deref_total(values: []&i64) -> i64 borrows(values) { var sum: i64 = 0; for (var i: usize = 0; i < len(values); i = i + 1) { sum = sum + *values[i]; } return sum; }
'''


def generate(seed, steps):
    rng = random.Random(seed)
    lines = [PRELUDE, 'fn main(){']
    for _ in range(steps):
        size = rng.randrange(2, 7)
        values = [rng.randrange(-999, 1000) for _ in range(size)]
        model = list(values)
        literal = ', '.join(str(value) for value in values)
        lines.append('  {')
        lines.append(f'    var a = [{size}]i64{{{literal}}};')
        # Build a chain of nested subslices; track each level's base offset.
        levels = []
        base, length = 0, size
        depth = rng.randrange(1, 4)
        for level in range(depth):
            if length < 2:
                break
            lo = rng.randrange(0, length - 1)
            hi = rng.randrange(lo + 1, length + 1)
            base = base + lo
            length = hi - lo
            levels.append((base, length))
            lines.append('  ' * (level + 1) + f'{{')
            source = 'a' if level == 0 else f's{level - 1}'
            lines.append('  ' * (level + 2) + f'let s{level} = {source}[{lo}:{hi}];')
            lines.append('  ' * (level + 2) + f'assert(len(s{level}) == {length});')
        deepest = len(levels) - 1
        indent = '  ' * (deepest + 2)
        for _ in range(rng.randrange(2, 6)):
            index = rng.randrange(0, length)
            if rng.random() < 0.5:
                lines.append(indent + f'assert(s{deepest}[{index}] == {model[base + index]});')
            else:
                value = rng.randrange(-999, 1000)
                model[base + index] = value
                lines.append(indent + f's{deepest}[{index}] = {value};')
                lines.append(indent + f'assert(s{deepest}[{index}] == {value});')
        if rng.random() < 0.5:
            expected = sum(model[base:base + length])
            lines.append(indent + f'assert(total(s{deepest}) == {expected});')
        if rng.random() < 0.4:
            index = rng.randrange(0, length)
            lines.append(indent + f'var view = View{{items: s{deepest}}};')
            lines.append(indent + f'assert(view.items[{index}] == {model[base + index]});')
        # Close every slice scope.
        for level in range(deepest, -1, -1):
            lines.append('  ' * (level + 1) + '}')
        # After all loans are released the backing array is readable directly.
        for index in range(size):
            lines.append(f'    assert(a[{index}] == {model[index]});')
        lines.append('    assert(mem.owner_count() == 0);')
        lines.append('  }')
    lines.append('  io.println(7654321);')
    lines.append('}')
    return '\n'.join(lines) + '\n', ['7654321']


def generate_owned(seed, steps):
    """Owned backing array: model live owners across slice reads and element moves."""
    rng = random.Random(seed)
    lines = [PRELUDE, 'fn main(){']
    for _ in range(steps):
        size = rng.randrange(2, 7)
        values = [rng.randrange(-999, 1000) for _ in range(size)]
        alive = [True] * size
        owners = size
        literal = ', '.join(f'new[i64]({value})' for value in values)
        lines.append('  {')
        lines.append(f'    var a = [{size}]own[i64]{{{literal}}};')
        lines.append(f'    assert(mem.owner_count() == {size});')
        levels = []
        base, length = 0, size
        depth = rng.randrange(1, 4)
        for level in range(depth):
            if length < 2:
                break
            lo = rng.randrange(0, length - 1)
            hi = rng.randrange(lo + 1, length + 1)
            base = base + lo
            length = hi - lo
            levels.append((base, length))
            lines.append('  ' * (level + 1) + '{')
            source = 'a' if level == 0 else f's{level - 1}'
            lines.append('  ' * (level + 2) + f'let s{level} = {source}[{lo}:{hi}];')
            lines.append('  ' * (level + 2) + f'assert(len(s{level}) == {length});')
        deepest = len(levels) - 1
        indent = '  ' * (deepest + 2)
        for _ in range(rng.randrange(2, 6)):
            live = [index for index in range(length) if alive[base + index]]
            if not live:
                break
            index = rng.choice(live)
            if rng.random() < 0.5:
                lines.append(indent + f'assert(*s{deepest}[{index}] == {values[base + index]});')
            else:
                lines.append(indent + '{')
                lines.append(indent + f'  let moved = move s{deepest}[{index}];')
                lines.append(indent + f'  assert(*moved == {values[base + index]});')
                lines.append(indent + '}')
                alive[base + index] = False
                owners = owners - 1
                lines.append(indent + f'assert(mem.owner_count() == {owners});')
        for level in range(deepest, -1, -1):
            lines.append('  ' * (level + 1) + '}')
        lines.append(f'    assert(mem.owner_count() == {owners});')
        for index in range(size):
            if alive[index]:
                lines.append(f'    assert(*a[{index}] == {values[index]});')
        lines.append('  }')
        lines.append('  assert(mem.owner_count() == 0);')
    lines.append('  io.println(2468135);')
    lines.append('}')
    return '\n'.join(lines) + '\n', ['2468135']


def generate_borrowed(seed, steps):
    """Borrowed-element slices: model referents across reads, rebinding and calls."""
    rng = random.Random(seed)
    lines = [PRELUDE, 'fn main(){']
    for _ in range(steps):
        size = rng.randrange(2, 6)
        values = [rng.randrange(-999, 1000) for _ in range(size)]
        chosen = list(range(size))
        lines.append('  {')
        for index, value in enumerate(values):
            lines.append(f'    var x{index} = {value};')
        pointers = ', '.join(f'&x{index}' for index in range(size))
        lines.append(f'    var refs = [{size}]&i64{{{pointers}}};')
        lines.append('    {')
        lines.append('      let s = refs[:];')
        lines.append(f'      assert(len(s) == {size});')
        for _ in range(rng.randrange(2, 6)):
            index = rng.randrange(0, size)
            if rng.random() < 0.5:
                lines.append(f'      assert(*s[{index}] == {values[chosen[index]]});')
            else:
                target = rng.randrange(0, size)
                chosen[index] = target
                lines.append(f'      s[{index}] = &x{target};')
                lines.append(f'      assert(*s[{index}] == {values[chosen[index]]});')
        if rng.random() < 0.5:
            expected = sum(values[chosen[index]] for index in range(size))
            lines.append(f'      assert(deref_total(s) == {expected});')
        lines.append('    }')
        for index in range(size):
            lines.append(f'    assert(*refs[{index}] == {values[chosen[index]]});')
        lines.append('  }')
    lines.append('  io.println(1357246);')
    lines.append('}')
    return '\n'.join(lines) + '\n', ['1357246']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', default='7,42,2026,1,99')
    parser.add_argument('--steps', type=int, default=40)
    parser.add_argument('--frontend', help='extra frontend executable')
    parser.add_argument('--sanitize-runtime', action='store_true')
    parser.add_argument('--output')
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix='cool slice fuzz ') as directory:
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
          for workload, generator, marker in (('scalar', generate, 7654321), ('owned', generate_owned, 2468135), ('borrowed', generate_borrowed, 1357246)):
            program, expected = generator(seed, args.steps)
            source = work / f'seed-{seed}-{workload}.cool'
            source.write_text(program)
            want = '\n'.join(expected) + '\n'
            for front in frontends:
                env = dict(os.environ)
                if front is not None:
                    env['COOL_FRONTEND'] = str(front)
                for engine in ENGINES:
                    run = subprocess.run([str(ROOT / 'tools/cool'), 'run', '--backend', engine, source],
                                         cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
                    assert (run.returncode, run.stdout, run.stderr) == (0, want, ''), (seed, workload, front, engine, run)
                    observations.append({'seed': seed, 'workload': workload, 'engine': engine, 'exit': run.returncode})
                binary = work / f'seed-{seed}-{workload}-{front}.bin'
                build = subprocess.run([str(ROOT / 'tools/cool'), 'build', '--release', source, '-o', binary],
                                       cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
                assert build.returncode == 0, (seed, front, build.stderr)
                run = subprocess.run([str(binary)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
                assert (run.returncode, run.stdout, run.stderr) == (0, want, ''), (seed, workload, front, 'O2', run)
                observations.append({'seed': seed, 'workload': workload, 'engine': 'O2', 'exit': run.returncode})
                if args.sanitize_runtime:
                    ir = work / f'seed-{seed}-{workload}-{front}.ll'
                    emit = subprocess.run([str(ROOT / 'tools/cool'), 'emit-ir', source, '-o', ir],
                                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
                    assert emit.returncode == 0, (seed, front, emit.stderr)
                    instrumented = work / f'seed-{seed}-{workload}-{front}-asan.ll'
                    instrumented.write_text('\n'.join(
                        line.replace(' {', ' sanitize_address {') if line.startswith('define ') else line
                        for line in ir.read_text().splitlines()) + '\n')
                    asan = work / f'seed-{seed}-{workload}-{front}-asan.bin'
                    link = subprocess.run(['clang', '-Wno-override-module', '-O1', '-g',
                                           '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                                           instrumented, ROOT / 'language/runtime.c', '-o', asan],
                                          cwd=ROOT, capture_output=True, text=True, timeout=180)
                    assert link.returncode == 0, (seed, front, link.stderr)
                    run = subprocess.run([str(asan)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
                    assert (run.returncode, run.stdout, run.stderr) == (0, want, ''), (seed, workload, front, 'ASan', run)
                    observations.append({'seed': seed, 'workload': workload, 'engine': 'ASan/UBSan', 'exit': run.returncode})
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({'seeds': args.seeds, 'steps': args.steps,
                                      'observations': observations}, indent=2) + '\n')
    print(f'slice fuzz: {args.steps}-step seeded nested-slice read/write/call/store programs with a '
          f'modeled backing array across five engines + O2 on {len(frontends)} frontends PASS')


if __name__ == '__main__':
    main()
