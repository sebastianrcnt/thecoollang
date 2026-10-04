"""Lightweight driver filesystem helpers; no package graph or archive imports."""
import os
from pathlib import Path
import tempfile


def cache_home():
    return Path(os.environ.get('COOL_CACHE', Path.home() / '.cache/cool'))


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as out:
        temp = Path(out.name)
        out.write(data)
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def find_root(start):
    start = Path(start).resolve()
    if start.is_file():
        start = start.parent
    for parent in (start, *start.parents):
        if (parent / 'cool.mod').is_file():
            return parent
    return None


