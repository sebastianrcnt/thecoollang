#!/usr/bin/env python3
"""Measure fresh-process REPL peak RSS for identical scalar-update workloads (macOS)."""
from pathlib import Path
import argparse
import json
import platform
import re
import statistics
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline', type=Path, required=True)
parser.add_argument('--candidate', type=Path, default=Path(__file__).resolve().parents[1] / 'build/cool-compiler')
parser.add_argument('--counts', type=int, nargs='+', default=[2000, 16000])
parser.add_argument('--trials', type=int, default=3)
parser.add_argument('--output', type=Path)
args = parser.parse_args()
if platform.system() != 'Darwin':
    parser.error('this measurement uses macOS /usr/bin/time -l byte-valued peak RSS')
if args.trials < 1 or any(count < 1 or count > 30000 for count in args.counts):
    parser.error('use positive trials and counts from 1 to 30000 (within the current token limit)')
samples = []
for count in args.counts:
    source = 'var total=0;\n' + 'total=total+1;\n' * count + 'total\n:quit\n'
    for label, compiler in [('baseline', args.baseline), ('candidate', args.candidate)]:
        for trial in range(args.trials):
            start = time.monotonic()
            result = subprocess.run(['/usr/bin/time', '-l', compiler.resolve(), 'repl-quiet'],
                                    input=source, text=True, capture_output=True, timeout=120)
            elapsed = time.monotonic() - start
            if result.returncode or result.stdout != str(count) + '\n' or 'error:' in result.stderr:
                raise RuntimeError(f'{label} failed workload: {result}')
            match = re.search(r'(\d+)\s+maximum resident set size', result.stderr)
            if match is None:
                raise RuntimeError(f'peak RSS missing: {result.stderr}')
            samples.append(dict(implementation=label, submissions=count, trial=trial + 1,
                                wall_seconds=round(elapsed, 3), peak_rss_bytes=int(match[1])))
medians = []
for count in args.counts:
    for label in ('baseline', 'candidate'):
        selected = [sample for sample in samples if sample['implementation'] == label and sample['submissions'] == count]
        medians.append(dict(implementation=label, submissions=count,
                            peak_rss_bytes=statistics.median(sample['peak_rss_bytes'] for sample in selected),
                            wall_seconds=statistics.median(sample['wall_seconds'] for sample in selected)))
report = dict(platform=platform.platform(), baseline=str(args.baseline.resolve()), candidate=str(args.candidate.resolve()),
              method='macOS time -l; fresh process per trial, no warmup; wall time includes launch; record concurrent machine load separately',
              samples=samples, medians=medians)
text = json.dumps(report, indent=2) + '\n'
if args.output:
    args.output.write_text(text)
print(text, end='')
