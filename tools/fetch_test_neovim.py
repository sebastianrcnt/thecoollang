#!/usr/bin/env python3
"""Fetch the pinned real-editor test client into build/, never user config."""
import hashlib
from pathlib import Path
import platform
import sys
import tarfile
import urllib.request

VERSION = 'v0.12.5'
SHA256 = '65fb000099e47ca1b762584c484cc833f40e30851a0ec450d4174e16317c1f9b'
ROOT = Path(__file__).resolve().parents[1]
if sys.platform != 'darwin' or platform.machine() != 'arm64':
    raise SystemExit('The pinned editor client supports the first release host: Apple Silicon macOS.')
root = ROOT/'build/editor-client'
root.mkdir(parents=True,exist_ok=True)
archive = root/f'nvim-macos-arm64-{VERSION}.tar.gz'
if not archive.exists():
    url = f'https://github.com/neovim/neovim/releases/download/{VERSION}/nvim-macos-arm64.tar.gz'
    with urllib.request.urlopen(url,timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise SystemExit('Neovim archive checksum mismatch')
    archive.write_bytes(data)
if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
    raise SystemExit('Cached Neovim archive checksum mismatch')
with tarfile.open(archive) as bundle:
    bundle.extractall(root,filter='data')
print(root/'nvim-macos-arm64/bin/nvim')
