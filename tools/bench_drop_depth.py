#!/usr/bin/env python3
"""Compare scope-exit destruction cost between two Cool compilers.

Builds the same standalone programs with two checkout drivers and times release
O2 native processes (warm-up, then alternating order). The programs isolate
destruction: shallow per-iteration owner drops, wide single-parent drops and
deep chain drops.
"""
import argparse
import hashlib
import json
import statistics
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROGRAMS = {
    'shallow': '''package main;
import "std/mem";import "std/io";
struct Pair { a: own[i64]; b: own[i64]; }
fn main() {
  var total: i64 = 0;
  for (var i = 0; i < 1000000; i = i + 1) {
    var p = Pair { a: new[i64](i), b: new[i64](i) };
    total = total + *p.a;
  }
  assert(mem.owner_count() == 0);
  io.println(total);
}
''',
    'wide': '''package main;
import "std/mem";import "std/io";
struct Wide { items: [300]own[i64]; }
fn main() {
  var total: i64 = 0;
  for (var round = 0; round < 2000; round = round + 1) {
    var w = Wide {};
    for (var i = 0; i < 300; i = i + 1) { w.items[i] = new[i64](i); }
    total = total + *w.items[0];
  }
  assert(mem.owner_count() == 0);
  io.println(total);
}
''',
    'deep': '''package main;
import "std/mem";import "std/io";
struct Node { next: own[Node]; value: i64; }
fn prepend(root: &mut own[Node], value: i64) {
  let node = new[Node](Node { next: move *root, value: value });
  *root = move node;
}
fn main() {
  var total: i64 = 0;
  for (var round = 0; round < 200; round = round + 1) {
    { var empty = Node {}; var root = move empty.next;
      for (var i = 0; i < 8192; i = i + 1) { prepend(&mut root, i); }
      total = total + (*root).value; }
  }
  assert(mem.owner_count() == 0);
  io.println(total);
}
''',
    'vector': '''package main;
import v "std/vector";import "std/io";
fn main() {
  var bytes = v.create[u8]();
  for (var i = 0; i < 500000; i = i + 1) { bytes.append(u8(i % 251)); }
  var sum: i64 = 0;
  unsafe { var it = v.cursor[u8](&bytes); for (var i = 0; i < 500000; i = i + 1) { sum = sum + i64(*v.next[u8](&raw it)); } }
  assert(sum == 62499028);
  bytes.clear();
  io.println(sum);
}
''',
}


def build(driver_root, name, source, out):
    project = ROOT / 'build/drop-depth-benchmark' / name
    app = project / Path(driver_root).name
    app.mkdir(parents=True, exist_ok=True)
    (project / 'cool.mod').write_text('module example.test/dropcost\n')
    (app / 'main.cool').write_text(source)
    binary = project / (Path(driver_root).name + '-program')
    result = subprocess.run([str(Path(driver_root) / 'tools/cool'), 'build', '--release', app, '-o', binary],
                            cwd=driver_root, capture_output=True, text=True)
    assert result.returncode == 0, (name, driver_root, result.stderr)
    return binary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--before', required=True, help='baseline checkout root')
    parser.add_argument('--samples', type=int, default=7)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    rows = []
    for name, source in PROGRAMS.items():
        for label, root in (('before', args.before), ('after', str(ROOT))):
            binary = build(root, name, source, None)
            rows.append({'program': name, 'name': label, 'root': root,
                         'binary': str(binary),
                         'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
                         'source': source, 'samples_ms': []})

    def execute(row, record):
        start = time.perf_counter_ns()
        result = subprocess.run([row['binary']], capture_output=True, text=True)
        duration = (time.perf_counter_ns() - start) / 1e6
        assert result.returncode == 0 and not result.stderr, (row['program'], row['name'], result.stderr)
        row['stdout'] = result.stdout.strip()
        if record:
            row['samples_ms'].append(duration)

    for row in rows:
        execute(row, False)
    for sample in range(args.samples):
        order = rows if sample % 2 == 0 else list(reversed(rows))
        for row in order:
            execute(row, True)
    for row in rows:
        row['median_ms'] = statistics.median(row['samples_ms'])
    report = {'before': args.before, 'after': str(ROOT), 'samples': args.samples,
              'compiler_sha256': hashlib.sha256((ROOT / 'build/cool-compiler').read_bytes()).hexdigest(),
              'rows': rows,
              'method': 'LLVM release O2 standalone native processes; one warm-up each, then alternating '
                        'order. Duration includes process launch and scope-exit destruction.'}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2) + '\n')
    for program in PROGRAMS:
        pair = {row['name']: row['median_ms'] for row in rows if row['program'] == program}
        print(f'{program}: before {pair["before"]:.3f} ms, after {pair["after"]:.3f} ms')


if __name__ == '__main__':
    main()
