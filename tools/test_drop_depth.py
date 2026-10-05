#!/usr/bin/env python3
"""Bounded native-stack destruction for deep and wide owned structures.

A 32,768-node owning chain used to overflow the native stack on scope exit in
every engine under a 1 MiB stack limit. Destruction is now an explicit DFS
(interpreter) or a typed LIFO callback worklist (LLVM + runtime), so native
stack use stays bounded while children are still dropped before their owning
storage is freed. This test pins that behaviour, the worklist growth
boundaries, mixed struct/enum/array ownership, moved/null owner slots and
persistent-REPL release.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import resource
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ENGINES = ('tree', 'interp', 'jit', 'llvm', 'llvm-jit')
STACK_BYTES = 1024 * 1024

CHAIN = '''import "std/mem";import "std/io";
struct Node { next: own[Node]; value: i64; }
fn prepend(root: &mut own[Node], value: i64) {
  let node = new[Node](Node { next: move *root, value: value });
  *root = move node;
}
fn main() {
  { var empty = Node {}; var root = move empty.next;
    for (var i = 0; i < __DEPTH__; i = i + 1) { prepend(&mut root, i); }
    assert(mem.owner_count() == __DEPTH__); }
  assert(mem.owner_count() == 0);
  io.println(123);
}
'''

WIDE = '''import "std/mem";import "std/io";
struct Wide { items: [__COUNT__]own[i64]; }
fn main() {
  { var w = Wide {};
    for (var i = 0; i < __COUNT__; i = i + 1) { w.items[i] = new[i64](i); }
    assert(mem.owner_count() == __COUNT__); }
  assert(mem.owner_count() == 0);
  io.println(456);
}
'''

MIXED = '''import "std/mem";import "std/io";
struct Pair { left: own[i64]; right: own[i64]; }
struct Box { pair: Pair; tag: i64; }
enum Choice { Num(i64); Owned(own[i64]); Deep(own[Pair]); }
fn main() {
  { var b = Box { pair: Pair { left: new[i64](1), right: new[i64](2) }, tag: 3 };
    assert(mem.owner_count() == 2); }
  assert(mem.owner_count() == 0);
  { var c = Choice.Num(7); assert(mem.owner_count() == 0); }
  { var c = Choice.Owned(new[i64](8)); assert(mem.owner_count() == 1); }
  assert(mem.owner_count() == 0);
  { var c = Choice.Deep(new[Pair](Pair { left: new[i64](9), right: new[i64](10) }));
    assert(mem.owner_count() == 3); }
  assert(mem.owner_count() == 0);
  { var empty = Pair {}; assert(mem.owner_count() == 0); }
  io.println(789);
}
'''

MOVED = '''import "std/mem";import "std/io";
struct Pair { left: own[i64]; right: own[i64]; }
fn main() {
  { var p = Pair { left: new[i64](1), right: new[i64](2) };
    let taken = move p.left;
    assert(mem.owner_count() == 2);
    io.println(*taken); }
  assert(mem.owner_count() == 0);
  { var empty = Pair {}; }
  assert(mem.owner_count() == 0);
  io.println(321);
}
'''

REPL = '''import "std/mem";
struct Node { next: own[Node]; value: i64; }
fn prepend(root: &mut own[Node], value: i64) {
  let node = new[Node](Node { next: move *root, value: value });
  *root = move node;
}
var empty = Node {};
var root = move empty.next;
for (var i = 0; i < 32768; i = i + 1) { prepend(&mut root, i); }
mem.owner_count()
:forget root
mem.owner_count()
:quit
'''


def bounded():
    resource.setrlimit(resource.RLIMIT_STACK,
                       (STACK_BYTES, resource.getrlimit(resource.RLIMIT_STACK)[1]))


def limited_wrapper(directory, real, *prefix):
    """A frontend wrapper that drops the native stack to 1 MiB before exec."""
    path = directory / ('limited-' + real.name)
    command = ' '.join(shlex.quote(str(part)) for part in (*prefix, real))
    path.write_text(f'#!/bin/sh\nulimit -s {STACK_BYTES // 1024} 2>/dev/null\nexec {command} "$@"\n')
    path.chmod(0o755)
    return path


def frontends(directory, extra):
    """Production frontend, then the legacy frontend, then any requested extra."""
    production = limited_wrapper(directory, ROOT / 'build/cool-compiler')
    legacy = limited_wrapper(directory, ROOT / 'build/language.BIN',
                             ROOT / 'build/coolc', '--run')
    result = [production, legacy]
    if extra:
        extra_path = Path(extra)
        result.append(extra_path if extra_path.is_absolute() else (ROOT / extra_path))
    return result


def run(command, front, env_extra=None, preexec=None, timeout=180):
    env = dict(os.environ)
    if front is not None:
        env['COOL_FRONTEND'] = str(front)
    env.setdefault('ASAN_OPTIONS', 'halt_on_error=1')
    env.setdefault('UBSAN_OPTIONS', 'halt_on_error=1:print_stacktrace=1')
    if env_extra:
        env.update(env_extra)
    return subprocess.run([str(part) for part in command], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=timeout, preexec_fn=preexec)


def source_hash(paths):
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend', help='extra frontend executable to audit')
    parser.add_argument('--sanitize-runtime', action='store_true',
                        help='also build each case with ASan/UBSan and the C runtime')
    parser.add_argument('--output')
    args = parser.parse_args()

    sources = [ROOT / 'compiler' / name for name in sorted(os.listdir(ROOT / 'compiler')) if name.endswith('.cool')]
    sources += [ROOT / 'language' / name for name in sorted(os.listdir(ROOT / 'language')) if name.endswith('.cool')]
    sources += [ROOT / 'language/runtime.c']
    before = source_hash(sources)

    observations = []
    with tempfile.TemporaryDirectory(prefix='cool drop depth ') as directory:
        work = Path(directory)
        fronts = frontends(work, args.frontend)
        cases = [
            ('chain-32768', CHAIN.replace('__DEPTH__', '32768'), '123\n', ENGINES, True),
            ('chain-boundary', CHAIN.replace('__DEPTH__', '33'), '123\n', ENGINES, True),
            ('wide-100', WIDE.replace('__COUNT__', '100'), '456\n', ENGINES, False),
            ('wide-300', WIDE.replace('__COUNT__', '300'), '456\n', ENGINES, True),
            ('mixed', MIXED, '789\n', ENGINES, False),
            ('moved-null', MOVED, '1\n321\n', ENGINES, False),
        ]
        for name, program, expected, engines, deep in cases:
            source = work / (name + '.cool')
            source.write_text(program)
            for front in fronts:
                for engine in engines:
                    result = run([ROOT / 'tools/cool', 'run', '--backend', engine, source], front)
                    assert (result.returncode, result.stdout) == (0, expected), (name, front, engine, result)
                    observations.append({'case': name, 'frontend': front.name, 'engine': engine,
                                         'exit': result.returncode, 'stdout': result.stdout})
            # Release O2 is a separate compiled artifact for every case.
            for front in fronts:
                binary = work / (name + '-O2-' + front.name + '.bin')
                build = run([ROOT / 'tools/cool', 'build', '--release', source, '-o', binary], front)
                assert build.returncode == 0, (name, front, build.stderr)
                result = run([binary], front, preexec=bounded if deep else None)
                assert (result.returncode, result.stdout) == (0, expected), (name, front, 'O2', result)
                observations.append({'case': name, 'frontend': front.name, 'engine': 'O2',
                                     'exit': result.returncode, 'stdout': result.stdout})

        # Persistent REPL: forgetting a deep owner releases the whole chain.
        for front in fronts:
            result = subprocess.run([str(front), 'repl-quiet'], cwd=ROOT, input=REPL, text=True,
                                    capture_output=True, timeout=180,
                                    env={**os.environ, 'COOL_FRONTEND': str(front)})
            assert (result.returncode, result.stdout) == (0, '32768\n0\n'), (front, result)
            observations.append({'case': 'repl-forget', 'frontend': front.name, 'engine': 'repl',
                                 'exit': result.returncode, 'stdout': result.stdout})

        if args.sanitize_runtime:
            for name, program, expected, _, _ in cases:
                source = work / (name + '.cool')
                for front in fronts:
                    ir = work / (name + '-' + front.name + '.ll')
                    emit = run([ROOT / 'tools/cool', 'emit-ir', source, '-o', ir], front)
                    assert emit.returncode == 0, (name, front, emit.stderr)
                    instrumented = work / (name + '-' + front.name + '-asan.ll')
                    instrumented.write_text('\n'.join(
                        line.replace(' {', ' sanitize_address {') if line.startswith('define ') else line
                        for line in ir.read_text().splitlines()) + '\n')
                    checked = work / (name + '-' + front.name + '-checked.ll')
                    check = run(['clang', '-Wno-override-module', '-O1', '-fsanitize=address',
                                 '-S', '-emit-llvm', instrumented, '-o', checked], front)
                    assert check.returncode == 0, (name, front, check.stderr)
                    assert '__asan_report_load' in checked.read_text(), (name, front)
                    binary = work / (name + '-' + front.name + '-asan.bin')
                    link = run(['clang', '-Wno-override-module', '-O1', '-g',
                                '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                                instrumented, ROOT / 'language/runtime.c', '-o', binary], front)
                    assert link.returncode == 0, (name, front, link.stderr)
                    result = run([binary], front)
                    assert (result.returncode, result.stdout) == (0, expected), (name, front, 'asan', result)
                    observations.append({'case': name, 'frontend': front.name, 'engine': 'ASan/UBSan',
                                         'exit': result.returncode, 'stdout': result.stdout})

    after = source_hash(sources)
    assert before == after, 'audited sources changed during the drop-depth audit'
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({'source_sha256': before, 'observations': observations}, indent=2) + '\n')
    print(f'drop depth: deep chain, worklist growth, mixed/moved ownership and REPL release '
          f'{len(observations)} executions across five engines + O2 on {len(fronts)} frontends PASS')


if __name__ == '__main__':
    main()
