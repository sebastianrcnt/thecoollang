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
import tempfile


from driver_common import cache_home, atomic_write, find_root


MAJOR_SUFFIX = r'/v([2-9]|[1-9][0-9]+)$'


def directive_words(raw, filename, number):
    # // comments begin only outside shell-style quoted local filesystem paths.
    quote = None
    escaped = False
    for index, char in enumerate(raw):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote != "'":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif raw[index:index+2] == '//':
            raw = raw[:index]
            break
    try:
        return shlex.split(raw)
    except ValueError as error:
        raise ValueError(f'{filename}:{number}: {error}') from error


def quote_local_path(path):
    # shlex.quote leaves // unquoted, but our manifest treats it as a comment.
    if '//' in path:
        return "'" + path.replace("'", "'\"'\"'") + "'"
    return shlex.quote(path)


def vendor_records(pairs):
    records = {}
    for key, value in pairs:
        if key in records:
            raise ValueError(f'duplicate vendor index module: {key}')
        records[key] = value
    return records


def validate_digest(digest):
    if not isinstance(digest, str) or not digest.startswith('h1:'):
        raise ValueError(f'unsupported checksum format: {digest}')
    try:
        decoded = base64.b64decode(digest[3:], validate=True)
    except ValueError as error:
        raise ValueError(f'invalid h1 checksum: {digest}') from error
    if len(decoded) != 32 or base64.b64encode(decoded).decode() != digest[3:]:
        raise ValueError(f'invalid h1 checksum: {digest}')


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
    suffix = re.search(MAJOR_SUFFIX, path)
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
        language_seen = False
        for number, raw in enumerate((root / 'cool.mod').read_text().splitlines(), 1):
            words = directive_words(raw, 'cool.mod', number)
            if not words:
                continue
            if words == [')']:
                if block is None:
                    raise ValueError(f'cool.mod:{number}: unexpected )')
                block = None
                continue
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
                if language_seen:
                    raise ValueError(f'cool.mod:{number}: duplicate cool directive')
                language_seen = True
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
            lines += ['replace (', *(f'    {p} => {quote_local_path(v)}' for p, v in sorted(self.replaces.items())), ')', '']
        atomic_write(self.root / 'cool.mod', '\n'.join(lines).encode())


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
    def __init__(self, manifest, offline=False, frozen=False, use_vendor=True):
        self.manifest = manifest
        self.use_vendor = use_vendor
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
            for number, line in enumerate(sums.read_text().splitlines(), 1):
                if line.strip():
                    words = line.split()
                    if len(words) != 3:
                        raise ValueError(f'cool.sum:{number}: expected module version h1-checksum')
                    path, version, digest = words
                    validate_path(path); validate_version(path, version); validate_digest(digest)
                    if (path, version) in self.sums and self.sums[path, version] != digest:
                        raise ValueError(f'conflicting checksums for {path}@{version}')
                    self.sums[path, version] = digest

    def _workspace(self):
        for parent in (self.manifest.root, *self.manifest.root.parents):
            work = parent / 'cool.work'
            if work.exists():
                block = False
                language_seen = False
                workspace_roots = {}
                for number, raw in enumerate(work.read_text().splitlines(), 1):
                    words = directive_words(raw, 'cool.work', number)
                    if not words:
                        continue
                    if words[0] == 'cool':
                        if block or language_seen or len(words) != 2:
                            raise ValueError(f'cool.work:{number}: invalid or duplicate cool directive')
                        if words[1] != '1.0':
                            raise ValueError(f'unsupported workspace language version: {words[1]}')
                        language_seen = True
                        continue
                    if words == ['use', '(']:
                        if block:
                            raise ValueError(f'cool.work:{number}: nested use block')
                        block = True
                        continue
                    if words == [')']:
                        if not block:
                            raise ValueError(f'cool.work:{number}: unexpected )')
                        block = False
                        continue
                    if not block:
                        if words[0] != 'use':
                            raise ValueError(f'cool.work:{number}: expected use directive')
                        words = words[1:]
                    if len(words) != 1:
                        raise ValueError(f'cool.work:{number}: expected one path')
                    root = (parent / words[0]).resolve()
                    module = Manifest.read(root)
                    if module.module == self.manifest.module and root != self.manifest.root:
                        raise ValueError(f'conflicting workspace main module identity: {module.module}')
                    if module.module in workspace_roots and workspace_roots[module.module] != root:
                        raise ValueError(f'conflicting workspace module identity: {module.module}')
                    workspace_roots[module.module] = root
                    self.local[module.module] = str(root)
                if block:
                    raise ValueError('cool.work: unclosed use block')
                return

    def source(self, path, version):
        if path in self.local:
            root = (self.manifest.root / self.local[path]).resolve()
            if Manifest.read(root).module != path:
                raise ValueError(f'replacement module path mismatch: {path}')
            return root
        vendor_index = self.manifest.root / 'vendor/cool.vendor.json'
        if self.use_vendor and vendor_index.exists():
            index = json.loads(vendor_index.read_text(), object_pairs_hook=vendor_records)
            if not isinstance(index, dict):
                raise ValueError('unsupported vendor index format: expected module/version object')
            for module, selected in index.items():
                if not isinstance(selected, str):
                    raise ValueError('unsupported vendor index format: expected version strings')
                validate_path(module); validate_version(module, selected)
            root = self.manifest.root / 'vendor' / path if index.get(path) == version else self.manifest.root / 'vendor/.versions' / (path + '@' + version)
            if not root.is_dir():
                raise ValueError(f'vendor contents are stale for {path}@{version}; regenerate vendor')
            if Manifest.read(root).module != path:
                raise ValueError(f'vendored module path mismatch: {path}')
            self.verify_sum(path, version, tree_hash(root))
            return root
        root = cache_home() / 'mod' / (path + '@' + version)
        if not root.exists():
            if self.offline:
                raise ValueError(f'offline: missing cached module {path}@{version}')
            repository = re.sub(MAJOR_SUFFIX, '', path)
            if len(repository.split('/')) != 3 or '.' not in repository.split('/')[0]:
                raise ValueError('direct fetching currently requires host/owner/repo module paths')
            root.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=root.parent, prefix='.fetch-') as tmp:
                temp = Path(tmp)
                subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', 'clone', '--bare', '--quiet',
                                (('git@' + repository.split('/', 1)[0] + ':' + repository.split('/', 1)[1]) if os.environ.get('COOL_GIT_SSH') == '1' else 'https://' + repository) + '.git', str(temp / 'repo')], check=True)
                archive = subprocess.check_output(['git', '-C', str(temp/'repo'), 'archive', '--format=tar', 'refs/tags/' + version])
                unpack = temp / 'source'; unpack.mkdir()
                import tarfile
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
        if Manifest.read(root).module != path:
            raise ValueError(f'cached module path mismatch: {path}')
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
        # Addressable local modules are unversioned graph roots. Their outgoing
        # requirements participate in MVS even without a require on the root.
        for path, location in self.local.items():
            if path == self.manifest.module:
                if (self.manifest.root / location).resolve() != self.manifest.root:
                    raise ValueError(f'conflicting local main module identity: {path}')
                continue
            root = (self.manifest.root / location).resolve()
            local_manifest = Manifest.read(root)
            if local_manifest.module != path:
                raise ValueError(f'replacement module path mismatch: {path}')
            self.roots[path] = root
            pending.extend(local_manifest.requires.items())
        seen = set()
        while pending:
            path, version = pending.pop()
            validate_version(path, version)
            # The main source identity is fixed to the invoking checkout. A
            # dependency's requirement on a tagged main version cannot fetch or
            # replace it; its outgoing requirements were already seeded above.
            if path == self.manifest.module:
                continue
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
        if module in self.local and module != self.manifest.module:
            if Manifest.read(self.roots[module]).module != module:
                raise ValueError(f'replacement module path mismatch: {module}')
        return self.roots[module] / path[len(module):].lstrip('/')
