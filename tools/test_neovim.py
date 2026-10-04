#!/usr/bin/env python3
"""Run the real Neovim LSP client with isolated configuration and project files."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--nvim',type=Path,default=ROOT/'build/editor-client/nvim-macos-arm64/bin/nvim')
parser.add_argument('--cli',type=Path,default=ROOT/'tools/cool')
parser.add_argument('--config',type=Path,default=ROOT/'editors/neovim/cool.lua')
parser.add_argument('--frontend',type=Path)
parser.add_argument('--report-name',default='neovim-client')
args=parser.parse_args()
if not args.nvim.is_file():
    raise SystemExit('Neovim test client missing: run make editor-client-fetch, or pass --nvim /path/to/nvim.')
with tempfile.TemporaryDirectory(prefix='cool editor 실제 ') as directory:
    root=Path(directory).resolve();project=root/'project';project.mkdir()
    (project/'cool.mod').write_text('module example.test/editor\n')
    library=project/'lib';library.mkdir();lib=library/'lib.cool'
    lib.write_text('package lib;pub fn answer()->i64{return 7;}\n')
    source=project/'main.cool';source.write_bytes('package main;\r\nimport l "example.test/editor/lib";\r\nfn main(){let emoji="🙂";missing;}\r\n'.encode())
    standalone=root/'standalone.cool';standalone.write_text('fn main(){let value=1;assert(value==1); }\n')
    saved={path:path.read_bytes() for path in (source,lib,standalone,project/'cool.mod')}
    report=root/'report.json'
    env=dict(os.environ,COOL_EDITOR_SOURCE=str(source),COOL_EDITOR_LIBRARY=str(lib),
        COOL_EDITOR_STANDALONE=str(standalone),COOL_EDITOR_CLI=str(args.cli.resolve()),COOL_EDITOR_CONFIG=str(args.config.resolve()),
        COOL_EDITOR_REPORT=str(report),COOL_CACHE=str(root/'cool-cache'),PYTHONDONTWRITEBYTECODE='1')
    for name in ('COOL_FRONTEND','VIMINIT','EXINIT','VIMRUNTIME','NVIM','NVIM_APPNAME','NVIM_LOG_FILE'):
        env.pop(name,None)
    if args.frontend:
        env['COOL_FRONTEND']=str(args.frontend.resolve())
        env['ASAN_OPTIONS']='halt_on_error=1'
        env['UBSAN_OPTIONS']='halt_on_error=1:print_stacktrace=1'
    for name in ('XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_STATE_HOME','XDG_CACHE_HOME'):
        env[name]=str(root/name.lower())
    result=subprocess.run([str(args.nvim.resolve()),'--headless','--clean','-l',str(ROOT/'tools/test_neovim.lua')],
        cwd=project,env=env,capture_output=True,text=True,timeout=120)
    audit=ROOT/'build/release-audit';audit.mkdir(parents=True,exist_ok=True)
    (audit/(args.report_name+'-output.log')).write_text(result.stdout+result.stderr)
    assert result.returncode==0,(result.returncode,result.stdout,result.stderr)
    actual=json.loads(report.read_text())
    actual['cli']=str(args.cli.resolve())
    actual['config']=str(args.config.resolve())
    actual['frontend']=str(args.frontend.resolve()) if args.frontend else 'default'
    assert all(path.read_bytes()==contents for path,contents in saved.items())
    assert not (project/'cool.sum').exists()
    assert not (project/'new.cool').exists()
    (audit/(args.report_name+'-report.json')).write_text(json.dumps(actual,indent=2)+'\n')
    print('Neovim client: automatic attach, UTF-16/CRLF diagnostics, unsaved edits, cross-package definition, native completion edit, dependency buffers, close/reset, graceful shutdown and unchanged source files PASS')
