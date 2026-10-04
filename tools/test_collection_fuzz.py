#!/usr/bin/env python3
"""Seeded list-model oracle for owning vectors; retain all inputs for reproduction."""
import argparse
import os
from pathlib import Path
import random
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def generate(seed, steps):
    rng = random.Random(seed)
    model = []
    lines = ['import v "std/vector"; import o "std/option";',
             'import "std/mem"; import "std/io";',
             'fn main(){ { var xs=v.create[own[i64]](); unsafe {']
    expected = []

    def check():
        lines.append(f'assert(v.len[own[i64]](&xs)=={len(model)});')
        lines.append(f'assert(mem.owner_count()=={len(model)+(len(model)+31)//32});')
        for index in sorted(set([0, len(model)//2, len(model)-1])):
            if index >= 0 and model:
                lines.append(f'assert(**v.at[own[i64]](&xs,{index})=={model[index]});')

    # Repeatedly cross chunk boundaries before the random state-machine walk.
    operations = ['append'] * 70 + ['pop'] * 40
    operations += [rng.choice(['append'] * 7 + ['pop'] * 3 + ['replace', 'mutate', 'move', 'clear'])
                   for _ in range(steps)]
    for number, operation in enumerate(operations):
        value = rng.randrange(-1000000, 1000001)
        lines.append(f'// seed {seed}, operation {number}: {operation}')
        if operation == 'append':
            model.append(value)
            lines.append(f'v.append[own[i64]](&xs,new[i64]({value}));')
        elif operation == 'pop':
            result = model.pop() if model else -2000000
            lines.append('{let result=o.value_or[own[i64]](v.pop[own[i64]](&xs),new[i64](-2000000));'
                         f'assert(*result=={result});' + '}')
        elif operation in ('replace', 'mutate') and model:
            index = rng.randrange(len(model))
            model[index] = value
            if operation == 'replace':
                lines.append(f'*v.at[own[i64]](&xs,{index})=new[i64]({value});')
            else:
                lines.append(f'**v.at[own[i64]](&xs,{index})={value};')
        elif operation == 'move':
            lines.append('{let transfer=move xs;xs=move transfer;}')
        elif operation == 'clear':
            model.clear()
            lines.append('v.clear[own[i64]](&xs);')
        check()
    # Check every element with an independent traversal API too.
    lines.append('var cursor=v.cursor[own[i64]](&xs);')
    for value in model:
        lines.append('io.println(**v.next[own[i64]](&cursor));')
        expected.append(str(value))
    lines += ['assert(v.next[own[i64]](&cursor)==null);', '} } assert(mem.owner_count()==0);io.println(1234567);}']
    expected.append('1234567')
    return '\n'.join(lines)+'\n', '\n'.join(expected)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', default='7,42,2026')
    parser.add_argument('--steps', type=int, default=120)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    directory = ROOT/'build/collection-fuzz'
    directory.mkdir(parents=True, exist_ok=True)

    def run(command, output=None):
        result = subprocess.run([str(x) for x in command], cwd=ROOT, capture_output=True,
                                text=True, timeout=120, env={**os.environ, 'ASAN_OPTIONS': 'halt_on_error=1',
                                                           'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'})
        if result.returncode or result.stderr or (output is not None and result.stdout != output):
            raise AssertionError(f'{command}\nreturn={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}')

    for seed in map(int, args.seeds.split(',')):
        source, expected = generate(seed, args.steps)
        path = directory/f'seed-{seed}.cool'
        path.write_text(source)
        path.with_suffix('.expected').write_text(expected)
        for engine in ('tree', 'interp', 'jit', 'llvm', 'llvm-jit'):
            run([ROOT/'tools/cool', 'run', '--backend', engine, path], expected)
        binary = directory/f'seed-{seed}'
        run([ROOT/'tools/cool', 'build', '--release', path, '-o', binary])
        run([binary], expected)
        if args.sanitize:
            ir = path.with_suffix('.ll')
            run([ROOT/'tools/cool', 'emit-ir', path, '-o', ir])
            # Clang does not infer sanitizer attributes on input LLVM functions.
            # Explicitly instrument generated Cool loads/stores as well as C.
            ir.write_text('\n'.join(line.replace(' {', ' sanitize_address {')
                                      if line.startswith('define ') else line
                                      for line in ir.read_text().splitlines())+'\n')
            instrumented = directory/f'seed-{seed}-asan.ll'
            run(['clang', '-Wno-override-module', '-O1', '-fsanitize=address',
                 '-S', '-emit-llvm', ir, '-o', instrumented])
            assert '__asan_report_load' in instrumented.read_text(), 'Cool IR was not instrumented'
            run(['clang', '-Wno-override-module', '-O1', '-g', '-fsanitize=address,undefined',
                 '-fno-omit-frame-pointer', ir, ROOT/'language/runtime.c', '-o', binary])
            run([binary], expected)
        print(f'collection model seed {seed}: five engines, O2' + (' and ASan Cool/runtime + UBSan C runtime' if args.sanitize else '') + ' PASS', flush=True)


if __name__ == '__main__':
    main()
