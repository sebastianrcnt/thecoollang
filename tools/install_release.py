#!/usr/bin/env python3
"""Verify/install/remove this Cool binary distribution within an explicit prefix."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_manifest(root):
    data = json.loads((root/'release.json').read_text())
    if not isinstance(data,dict):
        raise ValueError('invalid release manifest')
    identity = data.get('id','')
    if data.get('schema') != 1 or not isinstance(identity,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+-]*',identity):
        raise ValueError('invalid release manifest')
    if not isinstance(data.get('files'),dict) or not data['files']:
        raise ValueError('invalid payload file manifest')
    return data


def verify(root):
    data = read_manifest(root)
    for name, expected in data['files'].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name:
            raise ValueError('invalid manifest path')
        path = root.joinpath(*relative.parts)
        if any(p.is_symlink() for p in (path,*path.parents) if p != root and root in p.parents):
            raise ValueError('symlink in release payload: '+name)
        if not path.is_file() or digest(path) != expected:
            raise ValueError('release checksum mismatch: '+name)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix',type=Path,default=Path.home()/'.local')
    parser.add_argument('--verify',action='store_true')
    parser.add_argument('--uninstall',action='store_true')
    args = parser.parse_args()
    data = read_manifest(ROOT)
    if args.verify:
        verify(ROOT);print('verified '+data['id']);return
    prefix = args.prefix.expanduser().resolve()
    parent = prefix/'lib/cool';destination = parent/data['id'];binary = prefix/'bin/cool'
    for directory in (prefix/'bin', prefix/'lib', parent):
        if directory.is_symlink():
            raise ValueError('refusing a symlinked installation directory: '+str(directory))
    receipt_digest = digest(ROOT/'release.json')
    if args.uninstall:
        if not destination.is_dir() or destination.is_symlink():
            raise ValueError('this release is not installed at the selected prefix')
        receipt = json.loads((destination/'.installed.json').read_text())
        if receipt.get('manifest_sha256') != receipt_digest or digest(destination/'release.json') != receipt_digest:
            raise ValueError('installed release identity does not match')
        if binary.is_symlink() and binary.resolve() == destination/'tools/cool':
            binary.unlink()
        shutil.rmtree(destination)
        print('removed '+str(destination));return
    verify(ROOT)
    if binary.exists() or binary.is_symlink():
        target = binary.resolve()
        # Only replace the launcher of a previously installed Cool release.
        if not binary.is_symlink() or target.parent.name != 'tools' or target.name != 'cool' or target.parent.parent.parent != parent or not (target.parent.parent/'.installed.json').is_file():
            raise ValueError('refusing to replace an unrelated bin/cool')
    parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():
        if destination.is_symlink() or not (destination/'.installed.json').is_file() or digest(destination/'release.json') != receipt_digest:
            raise ValueError('release directory already exists with different contents')
        verify(destination)
    else:
        with tempfile.TemporaryDirectory(prefix='.cool-stage-',dir=parent) as temporary:
            staged = Path(temporary)/'payload';staged.mkdir()
            for name in [*data['files'],'release.json']:
                target=staged/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
            (staged/'.installed.json').write_text(json.dumps({'manifest_sha256':receipt_digest})+'\n')
            verify(staged)
            staged.rename(destination)
    binary.parent.mkdir(parents=True,exist_ok=True)
    # Replace the link atomically without ever copying over an unrelated file.
    descriptor, temporary = tempfile.mkstemp(prefix='.cool-link-',dir=binary.parent)
    os.close(descriptor);os.unlink(temporary)
    try:
        os.symlink(os.path.relpath(destination/'tools/cool',binary.parent),temporary)
        os.replace(temporary,binary)
    finally:
        if os.path.lexists(temporary):os.unlink(temporary)
    print('installed '+str(binary))


if __name__ == '__main__':
    try:main()
    except (OSError,ValueError,KeyError) as error:
        print('cool-install: '+str(error),file=sys.stderr);raise SystemExit(2)
