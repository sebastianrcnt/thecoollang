#!/usr/bin/env python3
"""Measure frontend peak RSS during repeated failed package parsing on macOS."""
from pathlib import Path
import argparse
import json
import os
import platform
import re
import shlex
import statistics
import subprocess
import tempfile
from modules import Manifest

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline', type=Path)
parser.add_argument('--candidate', type=Path, default=ROOT/'build/cool-compiler')
parser.add_argument('--counts', type=int, nargs='+', default=[8, 128])
parser.add_argument('--trials', type=int, default=3)
parser.add_argument('--output', type=Path)
args = parser.parse_args()
if platform.system() != 'Darwin' or args.trials < 1 or any(n < 1 or n > 4096 for n in args.counts):
    parser.error('macOS, positive trials and counts from 1 to 4096 required')
versions = ([('baseline', args.baseline)] if args.baseline else []) + [('candidate', args.candidate)]
samples = []
with tempfile.TemporaryDirectory(prefix='cool-package-memory-') as tmp:
    project = Path(tmp)/'project'
    project.mkdir()
    Manifest(project, 'example.test/memory').write()
    package = project/'bad'
    package.mkdir()
    source = '/*' + 'padding '*65536 + '*/\npackage bad;pub fn value()->i64{return missing;}'
    (package/'lib.cool').write_text(source)
    for label, frontend in versions:
        wrapper = Path(tmp)/(label+'-frontend')
        # Time the compiler itself, excluding the Python package graph driver.
        wrapper.write_text('#!/bin/sh\nexec /usr/bin/time -l '+shlex.quote(str(frontend.resolve()))+' "$@"\n')
        wrapper.chmod(0o755)
        for count in args.counts:
            for trial in range(1, args.trials+1):
                result = subprocess.run([ROOT/'tools/cool', 'repl', '--offline'], cwd=project,
                    input='var kept=7;\n'+'import bad "example.test/memory/bad";\n'*count+'kept\n:quit\n',
                    text=True, capture_output=True, timeout=120,
                    env={**os.environ, 'COOL_FRONTEND':str(wrapper), 'COOL_CACHE':str(Path(tmp)/'cache')})
                assert result.returncode == 0 and result.stdout == '7\n', result
                assert result.stderr.count('error:') == count and result.stderr.count('unknown variable') == count, result
                rss = re.findall(r'(\d+)\s+maximum resident set size', result.stderr)
                assert len(rss) == 1, result.stderr
                samples.append(dict(implementation=label, failed_imports=count, trial=trial, peak_rss_bytes=int(rss[0])))
report = dict(platform=platform.platform(), source_bytes=len(source.encode()),
              method='macOS time -l around frontend only; fresh compiler/driver process per trial; record concurrent load separately',
              samples=samples, medians=[dict(implementation=label, failed_imports=count,
                peak_rss_bytes=statistics.median(s['peak_rss_bytes'] for s in samples if s['implementation']==label and s['failed_imports']==count))
                for label, _ in versions for count in args.counts])
text = json.dumps(report, indent=2)+'\n'
if args.output:
    args.output.write_text(text)
print(text, end='')
