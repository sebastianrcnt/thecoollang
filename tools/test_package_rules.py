#!/usr/bin/env python3
"""Multi-file package identities, file-scoped aliases and test-source isolation."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);args=p.parse_args()
with tempfile.TemporaryDirectory(prefix='cool package rules ') as temporary:
 root=Path(temporary);app=root/'app';app.mkdir();(app/'cool.mod').write_text('module example.com/app\n')
 for name in ('a','b'):(app/name).mkdir()
 (app/'a/value.cool').write_text('package deliberately_different;pub fn value()->i64{return hidden();}')
 (app/'a/private.cool').write_text('package deliberately_different;fn hidden()->i64{return 20;}')
 (app/'b/value.cool').write_text('package b;pub fn value()->i64{return 22;}')
 # A dependency's tests are not part of its production package, even when the
 # importing root is being tested. Missing test-only imports must stay isolated.
 (app/'a/invalid_test.cool').write_text('package deliberately_different;import "example.invalid/testonly";fn test_bad(){missing();}')
 (app/'first.cool').write_text('package main;import dep "example.com/app/a";fn first()->i64{return dep.value();}')
 (app/'second.cool').write_text('package main;import dep "example.com/app/b";fn second()->i64{return dep.value();}')
 main=app/'main.cool';main_text='package main;import "std/io";fn main(){io.println(first()+second());}'
 tests=app/'local_test.cool';test_text='package main;fn test_sum(){assert(first()+second()==42);}'
 wrapper=root/'bootstrap';wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');wrapper.chmod(0o755)
 fronts=[ROOT/'build/cool-compiler',wrapper]
 if args.frontend:fronts.append(args.frontend.resolve())
 for frontend in fronts:
  env={**os.environ,'COOL_FRONTEND':str(frontend),'COOL_CACHE':str(root/'cache'),'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
  def run(*command,code=0,contains=None):
   result=subprocess.run([str(ROOT/'tools/cool'),*map(str,command)],cwd=app,env=env,capture_output=True,text=True,timeout=180)
   assert result.returncode==code,(frontend,command,result)
   if contains:assert contains in result.stderr,(contains,result)
   return result
  main.write_text(main_text);tests.write_text(test_text)
  for engine in ('interp','jit'):
   result=run('test','--backend',engine,app)
   assert result.stdout=='PASS test_sum\n1 tests passed\n',result
  run('test',app/'a',code=2,contains='no module supplies') # Selected dependency is now the test root.
  for engine in ('tree','interp','jit','llvm','llvm-jit'):
   assert run('run','--backend',engine,app).stdout=='42\n'
  run('check',main,code=2,contains='unknown function') # A file entry includes only that root file.
  cases=[
   ('package main;fn main(){dep.value();}','unknown imported package alias'),
   ('package main;import "example.com/app/a";fn main(){a.hidden();}','private'),
   ('package main;import a "example.com/app/a";import a "example.com/app/b";fn main(){}','duplicate import alias'),
   ('package main;package main;fn main(){}','duplicate package declaration'),
   ('package other;fn main(){}','mixed package'),
   ('fn main(){}','require a package declaration'),
  ]
  for text,message in cases:
   main.write_text(text);run('check',app,code=2,contains=message)
  main.write_text(main_text)
  tests.write_text('package main;fn test_bad(){missing();}')
  run('check',app)
  run('test',app,code=2,contains='unknown function')
  tests.write_text(test_text)
  # Self-consistency applies to dependency files as well.
  private=app/'a/private.cool';original=private.read_text()
  private.write_text('package mismatched;fn hidden()->i64{return 20;}')
  run('check',app,code=2,contains='mixed package');private.write_text(original)
  standalone=root/'standalone.cool';standalone.write_text('fn main(){}')
  run('check',standalone)
 print(f'package rules: directory/file selection, alias isolation, visibility, package headers and root-only test inclusion on {len(fronts)} frontends PASS')
