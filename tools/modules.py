"""Module graph, immutable source cache and MVS. No language parsing lives here."""
from __future__ import annotations
import base64
from dataclasses import dataclass, field
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile


def cache_home():
    return Path(os.environ.get('COOL_CACHE', Path.home() / '.cache/cool'))


def version_key(version):
    match = re.fullmatch(r'v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z.-]+))?', version)
    if not match:
        raise ValueError(f'invalid semantic version: {version}')
    major, minor, patch = map(int, match.group(1, 2, 3))
    pre = match[4]
    parts = []
    if pre:
        for part in pre.split('.'):
            if not part or (part.isdigit() and len(part) > 1 and part[0] == '0'):
                raise ValueError(f'invalid prerelease: {version}')
            parts.append((0, int(part)) if part.isdigit() else (1, part))
    return major, minor, patch, pre is None, tuple(parts)


def validate_path(path):
    if not path or path.startswith('/') or '\\' in path or any(p in ('', '.', '..') for p in path.split('/')):
        raise ValueError(f'invalid module path: {path}')
    if not re.fullmatch(r'[A-Za-z0-9._~+/-]+', path):
        raise ValueError(f'invalid module path: {path}')


def validate_version(path, version):
    major = version_key(version)[0]
    suffix = re.search(r'/v([2-9][0-9]*)$', path)
    if major >= 2 and (not suffix or int(suffix[1]) != major):
        raise ValueError(f'{path}@{version}: major versions >= 2 require /v{major}')
    if suffix and int(suffix[1]) != major:
        raise ValueError(f'{path}@{version}: major version mismatch')


@dataclass
class Manifest:
    root: Path
    module: str = ''
    language: str = '1.0'
    requires: dict[str, str] = field(default_factory=dict)
    replaces: dict[str, str] = field(default_factory=dict)

    @classmethod
    def read(cls, root):
        root = Path(root).resolve()
        result = cls(root)
        block = None
        for number, raw in enumerate((root / 'cool.mod').read_text().splitlines(), 1):
            line = raw.split('//', 1)[0].strip()
            if not line:
                continue
            if line == ')':
                if block is None:
                    raise ValueError(f'cool.mod:{number}: unexpected )')
                block = None
                continue
            words = shlex.split(line)
            if len(words) == 2 and words[1] == '(':
                if block or words[0] not in ('require', 'replace'):
                    raise ValueError(f'cool.mod:{number}: invalid block')
                block = words[0]
                continue
            if block:
                words.insert(0, block)
            kind, *args = words
            if kind == 'module' and len(args) == 1 and not result.module:
                validate_path(args[0]); result.module = args[0]
            elif kind == 'cool' and len(args) == 1:
                if args[0] != '1.0':
                    raise ValueError(f'unsupported language version: {args[0]}')
                result.language = args[0]
            elif kind == 'require' and len(args) == 2:
                validate_path(args[0]); validate_version(*args)
                if args[0] in result.requires:
                    raise ValueError(f'duplicate requirement: {args[0]}')
                result.requires[args[0]] = args[1]
            elif kind == 'replace' and len(args) == 3 and args[1] == '=>':
                validate_path(args[0])
                if args[0] in result.replaces:
                    raise ValueError(f'duplicate replacement: {args[0]}')
                result.replaces[args[0]] = args[2]
            else:
                raise ValueError(f'cool.mod:{number}: invalid directive')
        if block or not result.module:
            raise ValueError('cool.mod: missing module or unclosed block')
        return result

    def write(self):
        lines = [f'module {self.module}', '', f'cool {self.language}', '']
        if self.requires:
            lines += ['require (', *(f'    {p} {v}' for p, v in sorted(self.requires.items())), ')', '']
        if self.replaces:
            lines += ['replace (', *(f'    {p} => {shlex.quote(v)}' for p, v in sorted(self.replaces.items())), ')', '']
        atomic_write(self.root / 'cool.mod', '\n'.join(lines).encode())


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


def tree_hash(root):
    h = hashlib.sha256()
    for base, dirs, files in os.walk(root):
        for name in dirs:
            if (Path(base) / name).is_symlink():
                raise ValueError(f'symlink in module content: {Path(base) / name}')
        dirs[:] = sorted(d for d in dirs if d != '.git')
        for name in sorted(files):
            path = Path(base) / name
            if path.is_symlink():
                raise ValueError(f'symlinks are not allowed in module archives: {path}')
            rel = path.relative_to(root).as_posix()
            data = path.read_bytes()
            h.update(rel.encode() + b'\0' + str(len(data)).encode() + b'\0' + data)
    return 'h1:' + base64.b64encode(h.digest()).decode()


class Graph:
    def __init__(self, manifest, offline=False, frozen=False):
        self.manifest = manifest
        self.offline = offline or os.environ.get('COOL_OFFLINE') == '1'
        self.frozen = frozen
        self.selected = {}
        self.visited_roots = {}
        self.roots = {manifest.module: manifest.root}
        self.sums = {}
        self.pending_sums = {}
        self.local = dict(manifest.replaces)
        self._workspace()
        sums = manifest.root / 'cool.sum'
        if sums.exists():
            for line in sums.read_text().splitlines():
                if line.strip():
                    path, version, digest = line.split()
                    if (path, version) in self.sums and self.sums[path, version] != digest:
                        raise ValueError(f'conflicting checksums for {path}@{version}')
                    self.sums[path, version] = digest

    def _workspace(self):
        for parent in (self.manifest.root, *self.manifest.root.parents):
            work = parent / 'cool.work'
            if work.exists():
                block = False
                for raw in work.read_text().splitlines():
                    words = shlex.split(raw.split('//', 1)[0])
                    if not words or words[0] == 'cool':
                        continue
                    if words == ['use', '(']:
                        block = True; continue
                    if words == [')']:
                        block = False; continue
                    if not block:
                        if words[0] != 'use':
                            raise ValueError('cool.work: expected use directive')
                        words = words[1:]
                    if len(words) != 1:
                        raise ValueError('cool.work: expected one path')
                    root = (parent / words[0]).resolve()
                    module = Manifest.read(root)
                    self.local[module.module] = str(root)
                return

    def source(self, path, version):
        if path in self.local:
            root = (self.manifest.root / self.local[path]).resolve()
            if Manifest.read(root).module != path:
                raise ValueError(f'replacement module path mismatch: {path}')
            return root
        vendor_index = self.manifest.root / 'vendor/cool.vendor.json'
        if vendor_index.exists():
            index = json.loads(vendor_index.read_text())
            root = self.manifest.root / 'vendor' / path if index.get(path) == version else self.manifest.root / 'vendor/.versions' / (path + '@' + version)
            if not root.is_dir():
                raise ValueError(f'vendor contents are stale for {path}@{version}; regenerate vendor')
            self.verify_sum(path, version, tree_hash(root))
            return root
        root = cache_home() / 'mod' / (path + '@' + version)
        if not root.exists():
            if self.offline:
                raise ValueError(f'offline: missing cached module {path}@{version}')
            repository = re.sub(r'/v[2-9][0-9]*$', '', path)
            if len(repository.split('/')) != 3 or '.' not in repository.split('/')[0]:
                raise ValueError('direct fetching currently requires host/owner/repo module paths')
            root.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=root.parent, prefix='.fetch-') as tmp:
                temp = Path(tmp)
                subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', 'clone', '--bare', '--quiet',
                                (('git@' + repository.split('/', 1)[0] + ':' + repository.split('/', 1)[1]) if os.environ.get('COOL_GIT_SSH') == '1' else 'https://' + repository) + '.git', str(temp / 'repo')], check=True)
                archive = subprocess.check_output(['git', '-C', str(temp/'repo'), 'archive', '--format=tar', 'refs/tags/' + version])
                unpack = temp / 'source'; unpack.mkdir()
                with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                    for member in tar:
                        name = Path(member.name)
                        if name.is_absolute() or '..' in name.parts or not (member.isdir() or member.isfile()):
                            raise ValueError(f'unsafe archive entry: {member.name}')
                        target = unpack / name
                        if member.isdir():
                            target.mkdir(parents=True, exist_ok=True)
                        else:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_bytes(tar.extractfile(member).read())
                if Manifest.read(unpack).module != path:
                    raise ValueError('downloaded module declares a different module path')
                digest = tree_hash(unpack)
                self.verify_sum(path, version, digest)
                try:
                    unpack.rename(root)
                except FileExistsError:
                    pass
        self.verify_sum(path, version, tree_hash(root))
        return root

    def verify_sum(self, path, version, digest):
        expected = self.sums.get((path, version))
        if expected is not None and expected != digest:
            raise ValueError(f'checksum mismatch: {path}@{version}')
        if expected is None and self.frozen:
            raise ValueError(f'frozen: missing checksum for {path}@{version}')
        self.pending_sums[path, version] = digest

    def resolve(self):
        pending = list(self.manifest.requires.items())
        for path in self.local:
            if path != self.manifest.module and path not in self.manifest.requires:
                # Workspaces/replacements are addressable without fetching, not version requirements.
                self.roots[path] = (self.manifest.root / self.local[path]).resolve()
        seen = set()
        while pending:
            path, version = pending.pop()
            validate_version(path, version)
            if (path, version) in seen:
                continue
            seen.add((path, version))
            root = self.source(path, version)
            self.visited_roots[path, version] = root
            if path not in self.selected or version_key(version) > version_key(self.selected[path]):
                self.selected[path] = version
                self.roots[path] = root
            pending.extend(Manifest.read(root).requires.items())
        return self

    def save_sums(self):
        sums = self.sums | self.pending_sums
        if sums and sums != self.sums:
            atomic_write(self.manifest.root / 'cool.sum', ''.join(f'{p} {v} {h}\n' for (p, v), h in sorted(sums.items())).encode())

    def package(self, path):
        validate_path(path)
        candidates = [m for m in self.roots if path == m or path.startswith(m + '/')]
        if not candidates:
            raise ValueError(f'no module supplies {path}; add it with cool get or replace')
        module = max(candidates, key=len)
        return self.roots[module] / path[len(module):].lstrip('/')
