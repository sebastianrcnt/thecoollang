#!/usr/bin/env python3
"""Batch scan counts and content-addressed invalidation, including unchanged mtimes."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='cool-driver-cache-') as tmp:
 tmp=Path(tmp);project=tmp/'project space 한글';project.mkdir();log=tmp/'calls.jsonl';wrapper=tmp/'frontend'
 wrapper.write_text(f'''#!{sys.executable}
import json,sys,os
from pathlib import Path
with Path({str(log)!r}).open('a') as f:
 f.write(json.dumps([sys.argv[1], Path(sys.argv[2]).read_text() if sys.argv[1]=='scan-bundle' else ''])+'\\n')
os.execv({str(ROOT/'build/cool-compiler')!r},[{str(ROOT/'build/cool-compiler')!r},*sys.argv[1:]])
''');wrapper.chmod(0o755)
 env={**os.environ,'COOL_FRONTEND':str(wrapper),'COOL_CACHE':str(tmp/'cache')}
 (project/'a.cool').write_text('package main;fn main(){}')
 b=project/'b.cool';b.write_text('package main;fn value()->i64{return 0;}')
 def calls():return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
 def check(code=0):
  before=len(calls());p=subprocess.run([ROOT/'tools/cool','check',project],env=env,capture_output=True,text=True,timeout=60)
  assert p.returncode==code,p
  return [row for row in calls()[before:] if row[0]=='scan-bundle'],p
 rows,_=check();assert len(rows)==1 and len(rows[0][1].splitlines())==2,rows
 rows,_=check();assert rows==[],rows
 # Missing snapshots must recover from old per-file records without rescanning.
 snapshots=list((tmp/'cache/scan').glob('directory-*'));assert len(snapshots)==1,snapshots
 snapshot=snapshots[0];snapshot.unlink()
 rows,_=check();assert rows==[] and snapshot.is_file(),rows
 def current_keys():
  digest=hashlib.sha256(wrapper.read_bytes()).digest()
  return {hashlib.sha256(b'cool-scan-v2\0'+digest+source.read_bytes()).hexdigest()
          for source in project.glob('*.cool')}
 assert set(json.loads(snapshot.read_text()))==current_keys()
 # Two paths can share a content record; membership must still be rediscovered.
 duplicate=project/'duplicate.cool';twin=project/'twin.cool'
 duplicate.write_text('package main;');twin.write_text(duplicate.read_text())
 rows,_=check();assert len(rows)==1 and len(rows[0][1].splitlines())==2,rows
 assert set(json.loads(snapshot.read_text()))==current_keys()
 duplicate.unlink();rows,_=check();assert rows==[],rows
 assert set(json.loads(snapshot.read_text()))==current_keys()
 twin.unlink();rows,_=check();assert rows==[],rows
 assert set(json.loads(snapshot.read_text()))==current_keys()
 # Cache corruption is an explicit error, never silently a cache miss/hit.
 valid=snapshot.read_text()
 for corrupt in ('{', '[]', 'null', '{"key": 1}', '{"key": {}}',
                 json.dumps({next(iter(current_keys())):'package\tmain\npackage\tmain\n'})):
  snapshot.write_text(corrupt)
  before=len(calls());rows,p=check(2)
  assert rows==[] and len(calls())==before and 'cool:' in p.stderr,(corrupt,p,rows)
  assert snapshot.read_text()==corrupt
  snapshot.write_text(valid)
 rows,_=check();assert rows==[],rows
 # Only current records remain in the snapshot despite repeated edits; older
 # content-addressed per-file entries remain available for reverted sources.
 original=b.read_text()
 for index in range(8):
  b.write_text(original+f'\n// bounded history {index}\n')
  rows,_=check();assert len(rows)==1 and len(rows[0][1].splitlines())==1,rows
  records=json.loads(snapshot.read_text())
  assert set(records)==current_keys() and len(records)==2,records
 b.write_text(original);rows,_=check();assert rows==[],rows
 assert set(json.loads(snapshot.read_text()))==current_keys()
 old=b.stat();b.write_text(b.read_text().replace('return 0','return 1'));os.utime(b,ns=(old.st_atime_ns,old.st_mtime_ns))
 rows,_=check();assert len(rows)==1 and len(rows[0][1].splitlines())==1,rows
 c=project/'c.cool';c.write_text('package main;fn added(){}');rows,_=check();assert len(rows)==1 and len(rows[0][1].splitlines())==1,rows
 c.unlink();rows,_=check();assert rows==[],rows
 b.write_text('package main;import "missing/package";fn value()->i64{return 1;}')
 rows,p=check(2);assert rows and 'requires cool.mod' in p.stderr,p
 b.write_text('package main;fn value()->i64{return 1;}')
 rows,_=check();assert rows==[],rows
 old=wrapper.stat();wrapper.write_text(wrapper.read_text()+'# new frontend identity\n');wrapper.chmod(0o755);os.utime(wrapper,ns=(old.st_atime_ns,old.st_mtime_ns))
 rows,_=check();assert len(rows)==1 and len(rows[0][1].splitlines())==2,rows
 b.write_text('package main;fn value()->i64{return 2;}')
 def parallel_check(_):
  p=subprocess.run([ROOT/'tools/cool','check',project],env=env,capture_output=True,text=True,timeout=60);assert p.returncode==0 and not p.stderr,p
 with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(parallel_check,range(4)))
 rows,_=check();assert rows==[],rows
 empty=project/'empty.cool';empty.write_text('')
 rows,p=check(2);assert len(rows)==1 and 'package declaration' in p.stderr,p
 rows,p=check(2);assert rows==[] and 'package declaration' in p.stderr,p
 # Batch scanning must agree with individual scans in both frontend generations.
 manifest=tmp/'batch.list';sources=sorted(project.glob('*.cool'));manifest.write_text(''.join(f'__scan\t{p}\n' for p in sources))
 for front in ([ROOT/'build/cool-compiler'],[ROOT/'build/coolc','--run',ROOT/'build/language.BIN']):
  expected=''
  for source in sources:
   p=subprocess.run([*front,'scan',source],capture_output=True,text=True,check=True)
   expected+=''.join(str(source)+'\t'+line+'\n' for line in p.stdout.splitlines())
  p=subprocess.run([*front,'scan-bundle',manifest],capture_output=True,text=True,check=True)
  assert p.stdout==expected and not p.stderr,p
 # A rebuilt runtime object must invalidate native output even if source and
 # object mtimes are unchanged. Use an isolated toolchain tree, never the repo.
 isolated=tmp/'toolchain';(isolated/'tools').mkdir(parents=True);(isolated/'build').mkdir();(isolated/'language').mkdir()
 for name in ('cool','driver_common.py','release_support.py'):shutil.copy2(ROOT/'tools'/name,isolated/'tools'/name)
 shutil.copy2(ROOT/'VERSION',isolated/'VERSION')
 for name in ('runtime.c','numeric.h','memory.h','args.h'):(isolated/'language'/name).symlink_to(ROOT/'language'/name)
 obj=isolated/'build/language-runtime.o';shutil.copy2(ROOT/'build/language-runtime.o',obj)
 (isolated/'Makefile').write_text('build/language-runtime.o:\n\t@test -f $@\n')
 program=tmp/'print.cool';program.write_text('import "std/io";fn main(){io.println(1);}')
 binary=tmp/'print';native_env={**env,'COOL_CACHE':str(tmp/'native-cache')}
 command=[isolated/'tools/cool','build',program,'-o',binary]
 subprocess.run(command,env=native_env,check=True,capture_output=True)
 assert subprocess.check_output([binary],text=True)=='1\n'
 alternate=tmp/'runtime-alternate.c'
 alternate.write_text('#define putchar cool_test_putchar\n#include "'+str(ROOT/'language/runtime.c')+'"\n#undef putchar\nint cool_test_putchar(int c){fputc(33,stdout);return fputc(c,stdout); }\n')
 old=obj.stat();subprocess.run(['clang','-O2','-c',alternate,'-o',obj],check=True,capture_output=True);os.utime(obj,ns=(old.st_atime_ns,old.st_mtime_ns))
 subprocess.run(command,env=native_env,check=True,capture_output=True)
 assert subprocess.check_output([binary],text=True)=='1!\n'
 # Default native commands must check both real dependency targets in one lock,
 # while external frontends still require only the runtime target. Forward real
 # make through a recorder; the recipes actually refresh prerequisite artifacts.
 shutil.copy2(ROOT/'tools/cool',isolated/'tools/cool')
 shutil.copy2(ROOT/'build/cool-compiler',isolated/'build/cool-compiler')
 trigger=isolated/'frontend.trigger';trigger.write_text('changed compiler input')
 replacement=tmp/'runtime-replacement.o';shutil.copy2(obj,replacement)
 (isolated/'Makefile').write_text(
  'build/cool-compiler: frontend.trigger\n\t@touch $@\n'
  'build/language-runtime.o: '+str(replacement)+'\n\t@cp $< $@\n')
 make_calls=tmp/'make-calls.jsonl';commands=tmp/'commands';commands.mkdir()
 real_make=shutil.which('make');make_wrapper=commands/'make'
 make_wrapper.write_text('#!'+sys.executable+'\nimport json,os,sys\nfrom pathlib import Path\n'
  +'with Path('+repr(str(make_calls))+').open("a") as output:output.write(json.dumps(sys.argv[1:])+"\\n")\n'
  +'os.execv('+repr(real_make)+',['+repr(real_make)+',*sys.argv[1:]])\n')
 make_wrapper.chmod(0o755)
 default_env={**native_env,'PATH':str(commands)+os.pathsep+os.environ['PATH']}
 default_env.pop('COOL_FRONTEND',None)
 def requested_targets():
  return [json.loads(line)[3:] for line in make_calls.read_text().splitlines()]
 subprocess.run(command,env=default_env,check=True,capture_output=True)
 assert requested_targets()==[['build/cool-compiler','build/language-runtime.o']],requested_targets()
 assert (isolated/'build/cool-compiler').stat().st_mtime_ns>=trigger.stat().st_mtime_ns
 assert subprocess.check_output([binary],text=True)=='1!\n'
 # A changed runtime prerequisite must still rebuild and invalidate native cache.
 alternate.write_text(alternate.read_text().replace('fputc(33,stdout)','fputc(63,stdout)'))
 subprocess.run(['clang','-O2','-c',alternate,'-o',replacement],check=True,capture_output=True)
 subprocess.run(command,env=default_env,check=True,capture_output=True)
 assert requested_targets()[-1]==['build/cool-compiler','build/language-runtime.o']
 assert subprocess.check_output([binary],text=True)=='1?\n'
 subprocess.run([isolated/'tools/cool','check',program],env=default_env,check=True,capture_output=True)
 assert requested_targets()[-1]==['build/cool-compiler']
 # Override validation must not create/rebuild a checkout frontend.
 (isolated/'build/cool-compiler').unlink()
 external_env={**default_env,'COOL_FRONTEND':str(wrapper)}
 subprocess.run(command,env=external_env,check=True,capture_output=True)
 assert requested_targets()[-1]==['build/language-runtime.o']
 assert not (isolated/'build/cool-compiler').exists()
 assert subprocess.check_output([binary],text=True)=='1?\n'
print('driver cache: snapshot legacy fallback, duplicate-content membership, corruption rejection, bounded snapshot history, one scan per cold package, warm hits, same-mtime content changes, add/remove/import/frontend invalidation, concurrent readers, batch equivalence, rebuilt runtime objects and batched default/override dependency checks PASS')
