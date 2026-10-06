#!/usr/bin/env python3
"""Reproducible timing harness; excludes setup and reports process startup explicitly."""
import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--repeats', type=int, default=7)
parser.add_argument('--output', type=Path)
args = parser.parse_args()
if args.repeats < 1:
    parser.error('--repeats must be positive')
subprocess.run(['make', '-s', 'all'], cwd=ROOT, check=True)
results = {}
with tempfile.TemporaryDirectory(prefix='cool-benchmark-') as tmp:
    tmp = Path(tmp)
    env = dict(os.environ, COOL_CACHE=str(tmp/'cache'))
    source = tmp/'main.cool'
    source.write_text('''package main;
import "std/io";
fn sum(limit: i64) -> i64 {
    var total = 0;
    for (var i = 0; i < limit; i = i + 1) { total = total + i; }
    return total;
}
fn main() { io.println(sum(10000)); }
''')
    front = [str(ROOT/'build/cool-compiler')]
    cli = str(ROOT/'tools/cool')

    def measure(name, command, expected='', input=None, setup=None):
        samples = []
        for _ in range(args.repeats):
            if setup:
                setup()
            start = time.perf_counter_ns()
            p = subprocess.run(command, cwd=tmp, env=env, input=input, text=True,
                               capture_output=True, timeout=30)
            samples.append((time.perf_counter_ns() - start) / 1e6)
            assert p.returncode == 0 and p.stdout == expected and not p.stderr, (command, p)
        results[name] = {'median_ms': round(statistics.median(samples), 3),
                         'min_ms': round(min(samples), 3), 'samples_ms': samples}

    measure('frontend_check_with_process_startup', front + ['check', str(source)])
    for mode in ('run', 'bytecode', 'jit', 'auto'):
        measure(mode + '_cold_compile_and_execute_with_startup', front + [mode, str(source)], '49995000\n')
    measure('adaptive_run_including_driver', [cli, 'run', str(source)], '49995000\n')
    measure('llvm_ir_emission_with_startup', front + ['llvm', str(source), str(tmp/'main.ll')])
    measure('llvm_cold_build_including_driver', [cli, 'build', str(source), '-o', str(tmp/'app')],
            setup=lambda: shutil.rmtree(tmp/'cache/build', ignore_errors=True))
    measure('llvm_cached_build_including_driver', [cli, 'build', str(source), '-o', str(tmp/'app')])
    measure('llvm_executable_with_startup', [str(tmp/'app')], '49995000\n')
    # Compile a hot caller, replace its callee and prove only that callee recompiles.
    session = ('fn value() -> i64 { return 1; }\nfn caller() -> i64 { return value(); }\n'
               + 'caller()\n' * 4 + 'fn value() -> i64 { return 2; }\ncaller()\n:stats\n:quit\n')
    measure('repl_compile_hot_replace_and_call_with_startup', front + ['repl-quiet'],
            '1\n1\n1\n1\n2\nfunctions=2 compiled=2 bytecode_compilations=3 jit_compilations=2 tokens=27 aggregates=0 locals=0 literals=2 source_blocks=3 source_bytes=27\n', input=session)
report = {'platform': platform.platform(), 'machine': platform.machine(),
          'repeats': args.repeats, 'workload': 'sum integers [0, 10000)',
          'note': 'All measurements include process startup; setup excluded. No in-process latency claim.',
          'results': results}
text = json.dumps(report, indent=2) + '\n'
if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text)
print(text, end='')
