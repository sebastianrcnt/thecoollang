#!/usr/bin/env python3
"""Verify that every backtick-quoted `make <target>` named in the specification
and the release contract is a real Makefile target, so the conformance map
cannot silently go stale."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def make_targets():
    targets = set()
    for path in (ROOT / 'Makefile', ROOT / 'tools/toolchain.mk'):
        for line in path.read_text().splitlines():
            match = re.match(r'^([A-Za-z0-9_./-]+):', line)
            if match:
                targets.add(match.group(1))
    return targets

def referenced(path):
    names = set()
    for match in re.finditer(r'`make\s+([^`]+)`', path.read_text()):
        for token in match.group(1).split():
            token = token.strip('.,;:')
            if token and not token.startswith('-'):
                names.add(token)
    return names

targets = make_targets()
documents = [ROOT / 'docs/specification.md', ROOT / 'docs/release-1.0.md']
missing = {}
for document in documents:
    for target in sorted(referenced(document)):
        if target not in targets:
            missing.setdefault(str(document.relative_to(ROOT)), []).append(target)

if missing:
    for document, names in missing.items():
        print(f'{document}: unknown make targets: {", ".join(names)}', file=sys.stderr)
    raise SystemExit(1)

checked = sum(len(referenced(document)) for document in documents)
print(f'spec map: {checked} make-target references in the specification and release '
      f'contract all resolve to real targets PASS')
