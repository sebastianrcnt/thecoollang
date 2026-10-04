#!/usr/bin/env python3
"""Build manifest only: source parsing remains in Cool."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
files=sorted((ROOT/'compiler').glob('*.cool'))
if not files:raise SystemExit('compiler sources missing')
if any('\t' in str(p) or '\n' in str(p) for p in files):
    raise SystemExit('compiler source paths cannot contain tabs or newlines')
Path(sys.argv[1]).write_text(''.join(f'__main\t{p}\n' for p in files))
