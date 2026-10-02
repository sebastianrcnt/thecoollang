#!/usr/bin/env python3
"""Real projects: directory imports, visibility, cycles, cache and module integrity."""
import os
from pathlib import Path
import subprocess
import tempfile
from modules import Graph, Manifest, tree_hash, version_key
ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT/'tools/cool'

def cli(cwd, *args, code=0):
    p = subprocess.run([CLI, *args], cwd=cwd, text=True, capture_output=True, timeout=30)
    assert p.returncode == code, (args, p.returncode, p.stdout, p.stderr)
    return p

with tempfile.TemporaryDirectory(prefix='cool project ') as tmp:
    root = Path(tmp); os.environ['COOL_CACHE'] = str(root/'cache')
    project = root/'app'; project.mkdir()
    cli(project, 'mod', 'init', 'example.com/me/app')
    (project/'math').mkdir()
    (project/'math/a.cool').write_text('package math; pub fn answer() -> i64 { return hidden(); }')
    (project/'math/b.cool').write_text('package math; fn hidden() -> i64 { return 42; }')
    main = project/'main.cool'
    main.write_text('package main; import "std/io"; import m "example.com/me/app/math"; fn main() { io.println(m.answer()); }')
    for backend in ('interp', 'jit', 'llvm', 'llvm-jit'):
        assert cli(project, 'run', '--backend', backend).stdout == '42\n'
    cli(project, 'build', '-o', 'program')
    assert subprocess.check_output([project/'program'], text=True) == '42\n'
    cached = [p for p in (root/'cache/build').glob('*') if p.suffix != '.lock']
    times = {p: p.stat().st_mtime_ns for p in cached}
    cli(project, 'build', '-o', 'program2')
    assert all(p.stat().st_mtime_ns == t for p, t in times.items())
    (project/'math/b.cool').write_text('package math; fn hidden() -> i64 { return 43; }')
    assert cli(project, 'run', '--backend', 'llvm').stdout == '43\n'
    main.write_text(main.read_text().replace('m.answer()', 'm.hidden()'))
    assert 'private' in cli(project, 'check', code=2).stderr
    main.write_text(main.read_text().replace('m.hidden()', 'm.answer()'))
    (project/'math/b.cool').write_text('package math; import "example.com/me/app"; fn hidden() -> i64 { return 43; }')
    assert 'cycle' in cli(project, 'check', code=2).stderr
    (project/'math/b.cool').write_text('package different; fn hidden() -> i64 { return 43; }')
    assert 'mixed package' in cli(project, 'check', code=2).stderr
    (project/'math/b.cool').write_text('package math; fn hidden() -> i64 { return 43; }')
    # Real immutable cache trees: two graph paths require different versions of a shared module.
    def cached_module(path, version, requires=None):
        folder = root/'cache/mod'/(path+'@'+version); folder.mkdir(parents=True)
        m = Manifest(folder, path, requires=requires or {}); m.write()
        (folder/'lib.cool').write_text('package lib; pub fn value() -> i64 { return 1; }')
        return folder
    shared1 = cached_module('example.com/me/shared', 'v1.0.0')
    shared2 = cached_module('example.com/me/shared', 'v1.2.0')
    cached_module('example.com/me/a', 'v1.0.0', {'example.com/me/shared': 'v1.0.0'})
    cached_module('example.com/me/b', 'v1.0.0', {'example.com/me/shared': 'v1.2.0'})
    manifest = Manifest.read(project)
    manifest.requires = {'example.com/me/a': 'v1.0.0', 'example.com/me/b': 'v1.0.0'}
    manifest.write()
    graph = Graph(manifest, offline=True).resolve()
    assert graph.selected['example.com/me/shared'] == 'v1.2.0'
    graph.save_sums()
    Graph(manifest, offline=True, frozen=True).resolve()
    assert 'v1.2.0' in cli(project, 'mod', 'graph', '--offline').stdout
    (shared2/'lib.cool').write_text('tampered')
    try:
        Graph(manifest, offline=True).resolve()
    except ValueError as error:
        assert 'checksum mismatch' in str(error)
    else:
        raise AssertionError('cache tampering was not detected')
    (shared2/'lib.cool').write_text('package lib; pub fn value() -> i64 { return 1; }')
    cli(project, 'mod', 'vendor', '--offline')
    # Dependency updates regenerate stale vendor trees from the module cache.
    cached_module('example.com/me/shared', 'v1.3.0')
    manifest.requires['example.com/me/shared'] = 'v1.3.0'
    manifest.write()
    assert 'stale' in cli(project, 'mod', 'verify', '--offline', code=2).stderr
    cli(project, 'mod', 'vendor', '--offline')
    (root/'cache/mod').rename(root/'saved-cache')
    Graph(manifest, offline=True, frozen=True).resolve()
    cli(project, 'mod', 'verify', '--offline')
    (project/'vendor/example.com/me/shared/lib.cool').write_text('tampered')
    assert 'checksum mismatch' in cli(project, 'mod', 'verify', '--offline', code=2).stderr
    assert version_key('v1.0.0-alpha.2') < version_key('v1.0.0-alpha.10') < version_key('v1.0.0')
print('projects: package graph, private symbols, cycles, cache invalidation, LLVM JIT, MVS, offline checksums PASS')
