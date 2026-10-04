#!/usr/bin/env python3
"""The REPL uses normal package graphs while retaining existing state on failure."""
from pathlib import Path
import os
import argparse
import selectors
import socket
import shlex
import subprocess
import tempfile
from modules import Graph, Manifest
ROOT=Path(__file__).resolve().parents[1]
CLI=ROOT/'tools/cool'
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--frontend',type=Path);args=parser.parse_args()
def run(cwd,front,source,*flags):
 return subprocess.run([CLI,'repl',*flags],cwd=cwd,input=source,text=True,capture_output=True,timeout=120,env={**os.environ,'COOL_FRONTEND':str(front)})
def line(process):
 with selectors.DefaultSelector() as selector:
  selector.register(process.stdout,selectors.EVENT_READ)
  assert selector.select(20),'REPL output timeout'
 return process.stdout.readline()
with tempfile.TemporaryDirectory(prefix='cool REPL 한글 ') as tmp:
 root=Path(tmp);project=root/'app';project.mkdir();cache=root/'cache';os.environ['COOL_CACHE']=str(cache)
 Manifest(project,'example.test/app').write()
 local=project/'math';local.mkdir()
 (local/'a.cool').write_text('package math;pub fn answer()->i64{return hidden();}pub struct Number{pub value:i64;}pub fn Number.read(self:&Number)->i64{return (*self).value;}')
 (local/'b.cool').write_text('package math;fn hidden()->i64{return 42;}')
 bootstrap=root/'bootstrap';bootstrap.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');bootstrap.chmod(0o755)
 fronts=[ROOT/'build/cool-compiler',bootstrap]
 if args.frontend:fronts.append(args.frontend.resolve())
 for front in fronts:
  relocation = 'fn before()->i64{return 0;}\nimport vector "std/vector";\nimport m "example.test/app/math";\n'
  relocation += 'm.answer()\n'*4
  relocation += 'fn before()->i64{return 1;}\n'*128
  relocation += 'var bytes=vector.create[u8]();\nbytes.append(42);\n*bytes.at(0)\nlet number=m.Number{value:9};\nnumber.read()\nm.answer()\n:quit\n'
  p=run(project,front,relocation,'--offline');assert (p.returncode,p.stdout,p.stderr)==(0,'42\n'*5+'9\n42\n',''),p
  source='''import vector "std/vector";
var values=vector.create[i64]();
values.append(42);
let item=values.at(0);
import missing "std/not-here";
import reserved "__main";
values.append(3);
*item
:forget item
values.append(7);
values.len()
import m "example.test/app/math";
m.answer()
let number=m.Number{value:9};
number.read()
m.hidden()
import again "example.test/app/math"; import third "example.test/app/math";
again.answer()+third.answer()
import text "std/text";import result "std/result";
let word=result.value_or[text.Text,text.Utf8Error](text.from_literal("hello"),text.create());
text.byte_len(&word)
:quit
'''
  p=run(project,front,source,'--offline');assert p.returncode==0 and p.stdout=='42\n2\n42\n9\n84\n5\n' and p.stderr.count('error:')==4 and all(s in p.stderr for s in ('unknown standard package','reserved package identity','conflicts','private')),p
 print('REPL packages: standard/local packages, methods/generics, multiple aliases and persistent-loan recovery on both frontends PASS')
 for front in fronts:
  peer,channel=socket.socketpair();peer.close();descriptor=channel.fileno()
  p=subprocess.run([front,'repl-quiet'],input='var x=7;\nimport broken "example.test/closed";\nx\n:quit\n',cwd=project,text=True,capture_output=True,timeout=20,pass_fds=(descriptor,),env={**os.environ,'COOL_REPL_REQUEST_FD':str(descriptor),'COOL_REPL_RESPONSE_FD':str(descriptor)})
  channel.close()
  assert p.returncode==0 and p.stdout=='7\n' and 'package resolver channel' in p.stderr,p
 print('REPL packages: closed resolver channel is recoverable on both frontends PASS')
 # A cached immutable module graph exercises MVS and frozen checksum policy.
 def dependency(name,version,requires=None,value=1):
  folder=cache/'mod'/(name+'@'+version);folder.mkdir(parents=True)
  Manifest(folder,name,requires=requires or {}).write()
  (folder/'lib.cool').write_text(f'package lib;pub fn value()->i64{{return {value};}}')
  return folder
 dependency('example.test/shared','v1.0.0',value=1)
 chosen=dependency('example.test/shared','v1.2.0',value=12)
 dependency('example.test/a','v1.0.0',{'example.test/shared':'v1.0.0'})
 dependency('example.test/b','v1.0.0',{'example.test/shared':'v1.2.0'})
 manifest=Manifest.read(project);manifest.requires={'example.test/a':'v1.0.0','example.test/b':'v1.0.0'};manifest.write()
 for front in fronts:
  p=run(project,front,'var x=8;\nimport dep "example.test/shared";\nx\n:quit\n','--offline','--frozen')
  assert p.returncode==0 and p.stdout=='8\n' and 'missing checksum' in p.stderr,p
 Graph(Manifest.read(project),offline=True).resolve().save_sums()
 for front in fronts:
  p=run(project,front,'import dep "example.test/shared";\ndep.value()\n:quit\n','--offline','--frozen')
  assert (p.returncode,p.stdout,p.stderr)==(0,'12\n',''),p
 (chosen/'lib.cool').write_text('package lib;pub fn value()->i64{return 99;}')
 for front in fronts:
  p=run(project,front,'var x=7;\nimport dep "example.test/shared";\nx\n:quit\n','--offline')
  assert p.returncode==0 and p.stdout=='7\n' and 'checksum mismatch' in p.stderr,p
 (chosen/'lib.cool').write_text('package lib;pub fn value()->i64{return 12;}')
 print('REPL packages: MVS, offline/frozen checksums, tamper rejection and surviving session values on both frontends PASS')
 # Live source changes: failed declarations can be fixed; loaded packages stay
 # frozen, and dependency changes cannot silently replace callable definitions.
 broken=project/'broken';broken.mkdir()
 for front in fronts:
  (broken/'lib.cool').write_text('/*'+'padding '*65536+'*/\npackage broken;pub struct State{pub value:i64;}pub fn value()->i64{return missing;}')
  (local/'b.cool').write_text('package math;fn hidden()->i64{return 42;}')
  temporary=root/'session-temp';temporary.mkdir(exist_ok=True)
  process=subprocess.Popen([CLI,'repl','--offline'],cwd=project,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1,env={**os.environ,'COOL_FRONTEND':str(front),'TMPDIR':str(temporary)})
  process.stdin.write('import broken "example.test/app/broken";\n'*32+'var guard=7;\nguard\n');process.stdin.flush();assert line(process)=='7\n'
  (broken/'lib.cool').write_text('package broken;pub struct State{pub value:i64;}pub fn value()->i64{return 11;}')
  process.stdin.write('import broken "example.test/app/broken";\nbroken.value()\n');process.stdin.flush();assert line(process)=='11\n'
  process.stdin.write('import m "example.test/app/math";\nm.answer()\n');process.stdin.flush();assert line(process)=='42\n'
  for _ in range(3):
   process.stdin.write('m.answer()\n');process.stdin.flush();assert line(process)=='42\n'
  snapshots=list(temporary.glob('cool-repl-*/snapshots'))
  assert len(snapshots)==1 and len(list(snapshots[0].iterdir()))==1,snapshots
  (local/'b.cool').write_text('package math;fn hidden()->i64{return 99;}')
  process.stdin.write('import changed "example.test/app/math";\nm.answer()\nfn local_value()->i64{return 5;}\nlocal_value()\n:quit\n');process.stdin.flush()
  output,error=process.communicate(timeout=30)
  assert process.returncode==0 and output=='42\n5\n' and error.count('error:')==33 and 'unknown variable' in error and 'loaded package changed' in error,(output,error)
 print('REPL packages: failed-load retry, type/alias rollback, immutable loaded sources and restored session namespace on both frontends PASS')
