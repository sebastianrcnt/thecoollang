#!/usr/bin/env python3
"""Reproducible archive, isolated prefix install, read-only use and safe uninstall."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--nvim',type=Path)
args=parser.parse_args()


def run(args,*,cwd,env=None,code=0,input=None):
    p=subprocess.run([str(x) for x in args],cwd=cwd,env=env,capture_output=True,text=True,timeout=180,input=input)
    assert p.returncode==code,(args,p.returncode,p.stdout,p.stderr)
    return p


with tempfile.TemporaryDirectory(prefix='cool external distribution ') as temporary:
    root=Path(temporary).resolve();output=root/'archives'
    package=[sys.executable,ROOT/'tools/package_release.py','--allow-dirty','--output',output]
    archive=Path(run(package,cwd=root).stdout.strip().splitlines()[-1]);first=archive.read_bytes()
    run(package,cwd=root);assert archive.read_bytes()==first,'archive is not deterministic'
    assert archive.with_suffix('.gz.sha256').read_text().split()[0]==hashlib.sha256(first).hexdigest()
    unpack=root/'unpack';unpack.mkdir()
    with tarfile.open(archive) as tar:
        assert all(member.isfile() and '..' not in Path(member.name).parts and not member.name.startswith('/') for member in tar.getmembers())
        tar.extractall(unpack,filter='data')
    payload=next(unpack.iterdir());manifest=json.loads((payload/'release.json').read_text());install=payload/'install.py'
    assert not (payload/'coolc').exists() and not (payload/'Makefile').exists()
    run([sys.executable,install,'--verify'],cwd=root)
    prefix=root/'prefix with spaces';prefix.mkdir();(prefix/'unrelated.txt').write_text('keep')
    run([sys.executable,install,'--prefix',prefix],cwd=root)
    run([sys.executable,install,'--prefix',prefix],cwd=root) # idempotent
    cli=prefix/'bin/cool';installed=prefix/'lib/cool'/manifest['id']
    assert cli.is_symlink() and cli.resolve()==installed/'tools/cool'
    assert all((installed/name).read_bytes()==(payload/name).read_bytes() for name in manifest['files'])
    blocked=root/'blocked-tools';blocked.mkdir();stub=blocked/'make';stub.write_text('#!/bin/sh\necho UNEXPECTED-MAKE >&2\nexit 99\n');stub.chmod(0o755)
    env=dict(os.environ,PATH=str(blocked)+os.pathsep+os.environ['PATH'],COOL_CACHE=str(root/'cache'),COOLC_COMPILER_BIN='/missing/seed',PYTHONDONTWRITEBYTECODE='1')
    env.pop('COOL_FRONTEND',None)
    assert manifest['version'] in run([cli,'--version'],cwd=root,env=env).stdout
    assert 'Cool project driver' in run([cli,'--help'],cwd=root,env=env).stdout
    doctor=run([cli,'doctor'],cwd=root,env=env).stdout
    assert 'frontend' in doctor and 'gtimeout' not in doctor
    # A binary install must not write to its own prefix even for LLVM linking.
    for path in installed.rglob('*'):
        path.chmod(0o555 if path.is_dir() or path.stat().st_mode & 0o111 else 0o444)
    installed.chmod(0o555)
    if args.nvim:
        run([sys.executable,ROOT/'tools/test_neovim.py','--nvim',args.nvim.resolve(),'--cli',cli,
             '--config',installed/'editors/neovim/cool.lua','--report-name','neovim-installed'],cwd=root,env=env)
    project=root/'project';project.mkdir();run([cli,'mod','init','example.com/distribution'],cwd=project,env=env)
    library=project/'math';library.mkdir();(library/'math.cool').write_text('package math;pub fn value()->i64{return 42;}')
    source=project/'main.cool';source.write_text('''package main;import m "example.com/distribution/math";import "std/io";import "std/mem";import j "std/json";import t "std/text";import r "std/result";
fn main(){let input=r.value_or[t.Text,t.Utf8Error](t.from_literal("[42]"),t.create());let value=r.value_or[own[j.Value],j.ParseError](j.parse(&input),j.null_value());assert(j.array_len(&*value)==1);io.println(m.value());}
fn test_answer(){assert(m.value()==42);}
''')
    # Exercise the installed stdio server from a read-only prefix without seed/make.
    sys.path.insert(0,str(installed/'tools'))
    from lsp_server import read_message
    messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'capabilities':{}}},
        {'jsonrpc':'2.0','method':'initialized','params':{}},
        {'jsonrpc':'2.0','method':'textDocument/didOpen','params':{'textDocument':{
            'uri':source.as_uri(),'languageId':'cool','version':1,'text':'package main;fn main(){missing;}'}}},
        {'jsonrpc':'2.0','id':2,'method':'shutdown'}, {'jsonrpc':'2.0','method':'exit'}]
    editor_text='package main;import m "example.com/distribution/math";fn main(){let x=m.value();}'
    messages[-2:-2]=[
        {'jsonrpc':'2.0','method':'textDocument/didChange','params':{'textDocument':{'uri':source.as_uri(),'version':2},'contentChanges':[{'text':editor_text}]}},
        {'jsonrpc':'2.0','id':3,'method':'textDocument/definition','params':{'textDocument':{'uri':source.as_uri()},'position':{'line':0,'character':editor_text.index('value()')}}}]
    messages[-2:-2]=[{'jsonrpc':'2.0','id':4,'method':'textDocument/completion','params':{'textDocument':{'uri':source.as_uri()},'position':{'line':0,'character':editor_text.index('value()')+2}}}]
    broken_editor_text=editor_text.replace('fn main()', 'fn broken(){missing;}fn main()')
    messages[-2:-2]=[
        {'jsonrpc':'2.0','method':'textDocument/didChange','params':{'textDocument':{'uri':source.as_uri(),'version':3},'contentChanges':[{'text':broken_editor_text}]}},
        {'jsonrpc':'2.0','id':5,'method':'textDocument/completion','params':{'textDocument':{'uri':source.as_uri()},'position':{'line':0,'character':broken_editor_text.index('value()')+2}}}]
    frames=b''
    for message in messages:
        body=json.dumps(message).encode()
        frames+=f'Content-Length: {len(body)}\r\n\r\n'.encode()+body
    response=subprocess.run([cli,'lsp'],cwd=project,env=env,input=frames,capture_output=True,timeout=60)
    assert response.returncode==0,(response.stdout,response.stderr)
    stream=io.BytesIO(response.stdout);records=[]
    while (record:=read_message(stream)) is not None:records.append(record)
    assert records[0]['result']['capabilities']['positionEncoding']=='utf-16',records
    assert any(item.get('method')=='textDocument/publishDiagnostics' and
        item['params']['uri']==source.as_uri() and item['params']['diagnostics'] and 'unknown variable' in item['params']['diagnostics'][0]['message'] for item in records),records
    assert next(item for item in records if item.get('id')==3)['result'][0]['uri']==(library/'math.cool').as_uri(),records
    assert [item['label'] for item in next(item for item in records if item.get('id')==4)['result']['items']]==['value'],records
    assert [item['label'] for item in next(item for item in records if item.get('id')==5)['result']['items']]==['value'],records
    for backend in ('tree','interp','jit','llvm','llvm-jit'):
        assert run([cli,'run','--backend',backend,'.'],cwd=project,env=env).stdout=='42\n'
    session='import m "example.com/distribution/math";\nimport v "std/vector";\nvar values=v.create[i64]();\nvalues.append(m.value());\nlet r=values.at(0);\n*r\n:forget r\nvalues.append(7);\nvalues.len()\n:quit\n'
    assert run([cli,'repl','--offline'],cwd=project,env=env,input=session).stdout=='42\n2\n'
    run([cli,'fmt','.'],cwd=project,env=env);run([cli,'fmt','--check','.'],cwd=project,env=env)
    assert 'PASS test_answer' in run([cli,'test','.'],cwd=project,env=env).stdout
    assert 'pub fn value()' in run([cli,'doc',library],cwd=project,env=env).stdout
    executable=project/'native program';run([cli,'build','--release','-o',executable],cwd=project,env=env)
    assert run([executable],cwd=root,env=env).stdout=='42\n'
    tally=root/'tally';shutil.copytree(installed/'examples/tally',tally)
    report=root/'tally.json'
    for backend in ('auto','llvm'):
        assert run([cli,'run','--backend',backend,'.','--',report,'한글','apple','한글',''],cwd=tally,env=env).stdout=='4\n'
        assert json.loads(report.read_text())=={'한글':2,'apple':1,'':1}
    tally_binary=root/'tally-native';run([cli,'build','--release','-o',tally_binary],cwd=tally,env=env)
    assert run([tally_binary,report,'apple','apple'],cwd=root,env=env).stdout=='2\n'
    assert json.loads(report.read_text())=={'apple':2}
    session='import ledger "example.test/tally/ledger";\nimport "std/mem";\nvar book=ledger.create();\n'
    session+='{let count=ledger.add(&mut book,"한글",1);}\n'*256
    session+='ledger.total(&book)\n:forget book\nmem.owner_count()\n:quit\n'
    assert run([cli,'repl','--offline','--frozen'],cwd=tally,env=env,input=session).stdout=='256\n0\n'
    p=run([cli,'legacy'],cwd=root,env=env,code=2);assert 'source checkout' in p.stderr
    # Restore permissions for removal, preserving the installed launcher's mode.
    installed.chmod(0o755)
    for path in installed.rglob('*'):
        path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644)
    # Missing installed artifacts fail explicitly instead of falling back to make.
    runtime=installed/'build/language-runtime.o';saved_runtime=runtime.read_bytes();runtime.unlink()
    p=run([cli,'build','-o',executable],cwd=project,env=env,code=2);assert 'installed artifact missing' in p.stderr
    runtime.write_bytes(saved_runtime)
    # Install a second managed identity, then remove the older one without
    # disconnecting the selected launcher. Payload bytes are deliberately equal.
    next_payload=root/'next-payload';shutil.copytree(payload,next_payload)
    next_manifest=dict(manifest,id=manifest['id']+'-next')
    (next_payload/'release.json').write_text(json.dumps(next_manifest))
    run([sys.executable,next_payload/'install.py','--prefix',prefix],cwd=root)
    selected=cli.resolve();assert selected!=installed/'tools/cool'
    before=source.read_bytes();run([sys.executable,install,'--uninstall','--prefix',prefix],cwd=root)
    assert cli.resolve()==selected and not installed.exists()
    run([sys.executable,next_payload/'install.py','--uninstall','--prefix',prefix],cwd=root)
    assert not cli.exists() and not cli.is_symlink()
    assert (prefix/'unrelated.txt').read_text()=='keep' and source.read_bytes()==before
    # Existing unrelated programs must never be overwritten or removed.
    cli.write_text('unrelated');run([sys.executable,install,'--prefix',prefix],cwd=root,code=2);assert cli.read_text()=='unrelated'
    redirected=root/'redirected';redirected.mkdir();outside=root/'outside';outside.mkdir();(redirected/'lib').symlink_to(outside,target_is_directory=True)
    p=run([sys.executable,install,'--prefix',redirected],cwd=root,code=2);assert 'symlinked installation' in p.stderr and not list(outside.iterdir())
    bad_metadata=root/'bad-metadata';shutil.copytree(payload,bad_metadata)
    malicious=dict(manifest,id='..');(bad_metadata/'release.json').write_text(json.dumps(malicious))
    p=run([sys.executable,bad_metadata/'install.py','--prefix',prefix],cwd=root,code=2);assert 'invalid release manifest' in p.stderr
    # Integrity failures prevent installation and leave unrelated content intact.
    (payload/'stdlib/path/path.cool').write_text('tampered')
    p=run([sys.executable,install,'--verify'],cwd=root,code=2);assert 'checksum mismatch' in p.stderr
print('distribution: deterministic checksummed archive, seed/make-free external prefix, read-only five-engine use, project/test/doc/fmt/native build, idempotent install, safe uninstall/collision and tamper rejection PASS')
