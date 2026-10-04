"""Installed artifact checks and host dependency diagnostics (no language logic)."""
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys


def manifest(root):
    path = root/'release.json'
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if not isinstance(data,dict) or data.get('schema') != 1 or data.get('target') != 'darwin-arm64':
        raise ValueError('unsupported installed release manifest')
    if not all(isinstance(data.get(key),str) and data[key] for key in ('id','version','revision','minimum_macos')) or not isinstance(data.get('files'),dict):
        raise ValueError('invalid installed release manifest')
    if not re.fullmatch(r'[0-9]+(?:[.][0-9]+){0,2}',data['minimum_macos']):
        raise ValueError('invalid macOS deployment target')
    return data


def version(root):
    data = manifest(root)
    if data:
        return f"Cool {data['version']} ({data['revision'][:12]}, {data['target']})"
    return 'Cool '+(root/'VERSION').read_text().strip()+' (source checkout)'


def ensure_installed(root, targets):
    data = manifest(root)
    if data is None:
        return False
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('this installed Cool build requires native Apple Silicon macOS')
    minimum=tuple(int(part) for part in data['minimum_macos'].split('.'))
    current=tuple(int(part) for part in platform.mac_ver()[0].split('.'))
    if (current+(0,0,0))[:3] < (minimum+(0,0,0))[:3]:
        raise ValueError('this build requires macOS '+data['minimum_macos']+' or later')
    for target in targets:
        if target not in data['files'] or not (root/target).is_file():
            raise ValueError(f'installed artifact missing: {target}; reinstall this release')
    return True


def doctor(root):
    data = manifest(root)
    checks = []
    checks.append(('host', platform.system() == 'Darwin' and platform.machine() == 'arm64', platform.platform()))
    checks.append(('Python >= 3.10', sys.version_info >= (3,10), sys.version.split()[0]))
    for tool, required in (('clang', True), ('git', True), ('make', data is None)):
        if not required:
            continue
        path = shutil.which(tool)
        if path:
            p = subprocess.run([path,'--version'],capture_output=True,text=True)
            checks.append((tool, p.returncode == 0, p.stdout.splitlines()[0] if p.stdout else path))
        elif required:
            checks.append((tool, False, 'not found'))
    if data:
        current=tuple(int(part) for part in (platform.mac_ver()[0] or '0').split('.'))
        minimum=tuple(int(part) for part in data['minimum_macos'].split('.'))
        checks.append(('macOS >= '+data['minimum_macos'], (current+(0,0,0))[:3] >= (minimum+(0,0,0))[:3], platform.mac_ver()[0] or 'not macOS'))
        checks.append(('frontend', (root/'build/cool-compiler').is_file(), data['id']))
    else:
        path = shutil.which('gtimeout')
        checks.append(('gtimeout (source bootstrap)', bool(path), path or 'not found'))
    lli = os.environ.get('COOL_LLI') or shutil.which('lli')
    if not lli and Path('/opt/homebrew/opt/llvm/bin/lli').is_file():
        lli = '/opt/homebrew/opt/llvm/bin/lli'
    print(version(root))
    for name, ok, detail in checks:
        print(f"{'OK' if ok else 'MISSING'} {name}: {detail}")
    print('OPTIONAL LLVM lli: '+(lli or 'not found; needed only for --backend llvm-jit'))
    return all(ok for _,ok,_ in checks)
