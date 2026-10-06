#!/usr/bin/env python3
"""Fast REPL session-resource audit: read the compiler's own counters.

Runs one REPL process per size and parses the `:stats` counters (tokens,
aggregates, locals, literals, live source blocks/bytes, functions). Because it
reads internal counters instead of OS RSS, it needs only a small geometric size
sweep and one process per size, so it is far faster and deterministic.
"""
import argparse
import os
import re
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COUNTERS = ('tokens', 'aggregates', 'locals', 'literals', 'source_blocks', 'source_bytes', 'functions')

WORKLOADS = {
    'updates': lambda n: ''.join('total=total+1;\n' for i in range(n)),
    'bindings': lambda n: ''.join('{var scratch=total;total=scratch+1;}\n' for i in range(n)),
    'methods': lambda n: ''.join(f'io.println(total+{i % 7});\n' for i in range(n)),
    'branches': lambda n: ''.join(f'if(total>=0){{total=total+{i % 3};}}\n' for i in range(n)),
    'replacements': lambda n: ''.join(f'fn f(x:i64)->i64{{return x+{i % 5};}}\nf(total);\n' for i in range(n)),
    'literals': lambda n: ''.join(f'io.println("literal-{i}");\n' for i in range(n)),
    'rejected-literals': lambda n: ''.join(f'var q{i}:i64="s{i}";\n' for i in range(n)),
    'rejected-types': lambda n: ''.join(f'struct R{i}{{a:Unknown{i};}}\n' for i in range(n)),
    'forget-churn': lambda n: ''.join(f'var v{i}=i64({i});\n:forget v{i}\n' for i in range(n)),
    'structs': lambda n: ''.join(f'struct T{i}{{a:i64;}}\n' for i in range(n)),
    'functions': lambda n: ''.join(f'fn g{i}(x:i64)->i64{{return x+{i};}}\n' for i in range(n)),
}


def stats(workload, count, compiler, timeout):
    program = 'total=0;\n' + WORKLOADS[workload](count) + ':stats\n:quit\n'
    env = {**os.environ, 'COOL_FRONTEND': str(compiler.resolve())}
    run = subprocess.run([str(compiler), 'repl-quiet'], input=program, capture_output=True,
                         text=True, env=env, timeout=timeout)
    assert run.returncode == 0, (workload, count, run.stderr[-400:])
    match = re.search(r'functions=.*', run.stdout)
    assert match, run.stdout[-400:]
    return {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', match.group(0))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workloads', default=','.join(WORKLOADS))
    parser.add_argument('--counts', default='200,800')
    parser.add_argument('--compiler', default=str(ROOT / 'build/cool-compiler'))
    parser.add_argument('--timeout', type=int, default=300)
    parser.add_argument('--output')
    parser.add_argument('--bounded', default='updates,bindings,methods,branches,replacements,forget-churn,rejected-literals,rejected-types',
                        help='workloads whose per-input counter growth must be zero')
    args = parser.parse_args()
    low, high = (int(value) for value in args.counts.split(','))
    compiler = Path(args.compiler)
    rows = []
    for workload in args.workloads.split(','):
        first = stats(workload, low, compiler, args.timeout)
        second = stats(workload, high, compiler, args.timeout)
        row = {'workload': workload, 'low': low, 'high': high,
               'counters_low': first, 'counters_high': second,
               'delta_per_input': {key: (second[key] - first[key]) / (high - low) for key in COUNTERS}}
        rows.append(row)
        growing = {key: round(value, 4) for key, value in row['delta_per_input'].items() if abs(value) > 1e-9}
        print(f'{workload:18s} n={low}->{high}  per-input growth: {growing or "none"}')
        row['growing'] = growing
    if args.output:
        import json
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps({'counts': args.counts, 'rows': rows}, indent=2) + '\n')
    bounded = set(args.bounded.split(','))
    violations = [row for row in rows if row['workload'] in bounded and row['growing']]
    if violations:
        for row in violations:
            print(f"{row['workload']}: unbounded per-input growth {row['growing']}", file=sys.stderr)
        raise SystemExit(1)
    print(f'repl resources: {len(rows)} workloads at {low}->{high} inputs on internal counters PASS')


if __name__ == '__main__':
    main()
