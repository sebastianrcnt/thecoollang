#!/usr/bin/env python3
"""Build a deterministic development binary archive; does not declare Cool 1.0."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
ROOT=Path(__file__).resolve().parents[1]


def command(*args):
    return subprocess.check_output(args,cwd=ROOT,text=True).strip()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'build/dist')
    parser.add_argument('--allow-dirty',action='store_true',help='include uncommitted development changes, recorded in manifest')
    args=parser.parse_args()
    if platform.system()!='Darwin' or platform.machine()!='arm64':raise ValueError('binary packaging currently requires native Apple Silicon macOS')
    dirty=bool(command('git','status','--porcelain'))
    if dirty and not args.allow_dirty:raise ValueError('source tree is dirty; commit it or use --allow-dirty for a development artifact')
    version=(ROOT/'VERSION').read_text().strip()
    if not re.fullmatch(r'0\.[0-9]+\.[0-9]+-dev',version):raise ValueError('this development packager requires a 0.x.y-dev version; 1.0 release gates remain open')
    subprocess.run(['make','-s','build/cool-compiler','build/language-runtime.o','build/language-runtime.dylib'],cwd=ROOT,check=True)
    revision=command('git','rev-parse','HEAD');epoch=int(os.environ.get('SOURCE_DATE_EPOCH',command('git','show','-s','--format=%ct','HEAD')))
    with tempfile.TemporaryDirectory(prefix='cool-package-') as temporary:
        stage=Path(temporary)/'payload';stage.mkdir()
        files=['VERSION','LICENSE','THIRD_PARTY.md','SOURCE.md','tools/cool','tools/driver_common.py','tools/modules.py','tools/repl_driver.py','tools/release_support.py',
               'build/cool-compiler','build/language-runtime.o','build/language-runtime.dylib','language/runtime.c','language/numeric.h','language/memory.h','language/args.h']
        files += [str(path.relative_to(ROOT)) for path in sorted((ROOT/'stdlib').rglob('*')) if path.is_file() and path.suffix in ('.cool','.md')]
        files += [str(path.relative_to(ROOT)) for path in sorted((ROOT/'docs').glob('*.md'))]
        files += [str(path.relative_to(ROOT)) for path in sorted((ROOT/'examples/tally').rglob('*')) if path.is_file() and (path.suffix in ('.cool','.md') or path.name=='cool.mod')]
        for name in files:
            source=ROOT/name
            if source.is_symlink():raise ValueError('release input must not be a symlink: '+name)
            target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        shutil.copyfile(ROOT/'tools/install_release.py',stage/'install.py')
        (stage/'README.md').write_text('''# Cool development binary distribution

This is a development build, not Cool 1.0. The release gates in
`docs/release-1.0.md` remain open. It contains the new-syntax self-hosted compiler,
standard library and native runtimes; no legacy loader or compiler seed is used.

Python 3.10+ and native Apple Silicon macOS are required. Native linking also
requires clang/Xcode Command Line Tools; Git supports tagged modules. LLVM lli
is optional for `--backend llvm-jit`. The manifest records the tested host,
compiler toolchain, Mach-O deployment metadata and file checksums.

Run `python3 install.py --verify`, then
`python3 install.py --prefix "$HOME/.local"` and add that prefix's `bin` to PATH.
Use `cool --version`, `cool doctor`, and `cool run program.cool`.
Copy `examples/tally` to a writable directory for a complete multi-package CLI
example; its README covers command-line and REPL use.
`python3 install.py --uninstall --prefix "$HOME/.local"` removes this exact
installed version and its launcher only if it is still selected. Other installed
versions remain intact. `bin/cool` may replace only a managed Cool symlink.
Installation does not invoke make or write outside the selected prefix.
''')
        for path in stage.rglob('*'):
            if path.is_file():path.chmod(0o755 if path.relative_to(stage).as_posix() in ('tools/cool','build/cool-compiler') else 0o644)
        checksums={path.relative_to(stage).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(stage.rglob('*')) if path.is_file()}
        payload=hashlib.sha256(json.dumps(checksums,sort_keys=True).encode()).hexdigest()
        identity=f'{version}-{revision[:12]}-{payload[:12]}'
        deployment={}
        minimum=[]
        for artifact in ('cool-compiler','language-runtime.o','language-runtime.dylib'):
            details=command('xcrun','vtool','-show-build',str(ROOT/'build'/artifact))
            deployment[artifact]='\n'.join(details.splitlines()[1:])
            match=re.search(r'\bminos\s+([0-9.]+)',details)
            if not match:raise ValueError('could not read deployment target: '+artifact)
            minimum.append(tuple(int(part) for part in match[1].split('.')))
        minimum_macos='.'.join(str(part) for part in max(minimum))
        metadata={'schema':1,'id':identity,'version':version,'revision':revision,'dirty':dirty,'target':'darwin-arm64',
                  'source_date_epoch':epoch,'tested_host':platform.mac_ver()[0],'minimum_macos':minimum_macos,'deployment':deployment,
                  'dependencies':{'python_minimum':'3.10','clang':command('clang','--version'),'git':command('git','--version'),'python_build':platform.python_version(),'llvm_lli':'optional'},'files':checksums}
        (stage/'release.json').write_text(json.dumps(metadata,sort_keys=True,indent=2)+'\n')
        output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
        archive=output/(identity+'-darwin-arm64.tar.gz')
        # Fixed metadata/order/compression time make identical payloads reproducible.
        temporary_archive=output/(archive.name+'.tmp')
        try:
            with temporary_archive.open('wb') as raw,gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as zipped,tarfile.open(fileobj=zipped,mode='w') as tar:
                for path in sorted(stage.rglob('*')):
                    if not path.is_file():continue
                    relative=path.relative_to(stage).as_posix();info=tarfile.TarInfo(identity+'/'+relative)
                    contents=path.read_bytes();info.size=len(contents);info.mode=path.stat().st_mode & 0o777;info.mtime=epoch;info.uid=info.gid=0
                    tar.addfile(info,io.BytesIO(contents))
            os.replace(temporary_archive,archive)
        finally:temporary_archive.unlink(missing_ok=True)
        checksum=hashlib.sha256(archive.read_bytes()).hexdigest()
        archive.with_suffix(archive.suffix+'.sha256').write_text(checksum+'  '+archive.name+'\n')
        print(archive)


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,subprocess.CalledProcessError) as error:
        print('cool-package: '+str(error),file=sys.stderr);raise SystemExit(2)
