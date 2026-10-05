#!/usr/bin/env python3
"""Reference replacement retains all possible roots at the original binding lifetime."""
import argparse, os, shlex, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);p.add_argument('--sanitize-runtime',action='store_true');args=p.parse_args()
prelude='''import "std/io";import "std/mem";
struct View{r:&i64;}
struct Mut{r:&mut i64;}
struct Mixed{r:&i64;p:own[i64];}
struct Box[T]{value:T;}
enum Choice{None;Some(&i64);}
fn read(r:&i64)->i64{return *r;}
fn same(r:&i64)->&i64 borrows(r){return r;}
fn make(r:&i64)->View borrows(r){return View{r:r};}
fn later(r:&i64){assert(*r==8);}
'''
program=prelude+'''fn tests(){var x=7;var y=8;
 {var r=&x;r=&y;assert(read(r)==8);r=same(r);assert(*r==8);}
 {var r=&mut x;r=r;r=&mut y;*r=9;}assert(y==9);y=8;
 {var v=make(&x);v=make(&y);assert(*v.r==8);v.r=&x;assert(*v.r==7);}
 {var a=[2]&i64{&x,&x};a[0]=&y;assert(*a[0]==8);assert(*a[1]==7);}
 {var b=Box[View]{value:make(&x)};b.value.r=&y;assert(*b.value.r==8);}
 {var c=Choice.Some(&x);c=Choice.Some(&y);match(c){Choice.None=>{assert(false);}Choice.Some(r)=>{assert(*r==8);}}}
 {var p=new[View](make(&x));(*p).r=&y;assert(*(*p).r==8);}
 {var p=new[&i64](&x);*p=&y;assert(**p==8);}
 {var v=Mixed{r:&x,p:new[i64](10)};v=Mixed{r:&y,p:new[i64](11)};assert(mem.owner_count()==1);assert(*v.r==8);assert(*v.p==11);}
 {var v=Mut{r:&mut x};v.r=&mut y;*v.r=12;}assert(y==12);y=8;
 {var r=&x;if(true){r=&y;}else{r=&x;}assert(*r==8);}
 {var r=&x;for(var i=0;i<3;i=i+1){r=&y;}assert(*r==8);}
 {var r=&x;{r=&y;defer later(r);}assert(*r==8);}
 assert(mem.owner_count()==0);x=17;y=8;io.println(x+y);}
fn main(){tests();assert(mem.owner_count()==0);}
'''
invalid=[
 'fn main(){var x=1;var r=&x;{var y=2;r=&y;}}',
 'fn main(){var x=1;var v=make(&x);{var y=2;v.r=&y;}}',
 'fn main(){var x=1;var a=[1]&i64{&x};{var y=2;a[0]=&y;}}',
 'fn main(){var x=1;var p=new[View](make(&x));{var y=2;(*p).r=&y;}}',
 'fn bad(r:&i64)->&i64 borrows(r){var q=r;{var x=1;q=&x;}return q;}fn main(){}',
 'fn bad(a:&i64,b:&i64)->View borrows(a){var v=make(a);v.r=b;return v;}fn main(){}',
 'fn main(){var x=1;var y=2;var r=&x;r=&y;x=3;}',
 'fn main(){var x=1;var y=2;var r=&x;{r=&y;}y=3;}',
 'fn main(){var x=1;var y=2;var v=make(&x);v.r=&y;y=3;}',
 'fn main(){var x=1;var y=2;var r=&x;let a=&r;r=&y;}',
 'fn main(){var x=1;var y=2;var v=make(&x);let a=&v;v.r=&y;}',
 'fn main(){var x=1;var y=2;var r=&mut x;let c=&mut r;r=&mut y;**c=3;}',
 'fn main(){var x=1;var y=2;let r=&x;r=&y;}',
 'fn main(){var x=1;var y=2;var r=&y;defer later(r);r=&x;y=3;}',
 'fn replace(p:&mut View,r:&i64){(*p).r=r;}fn main(){}',
 'fn main(){var x=1;var y=2;var v=make(&x);let p=&mut v;{var z=3;(*p).r=&z;}}',
]
def run(command,env,input=None):return subprocess.run(list(map(str,command)),cwd=ROOT,env=env,input=input,capture_output=True,text=True,timeout=180)
with tempfile.TemporaryDirectory(prefix='cool borrowed heaps ') as temporary:
 root=Path(temporary);source=root/'main.cool';binary=root/'program';wrapper=root/'bootstrap'
 wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');wrapper.chmod(0o755)
 fronts=[ROOT/'build/cool-compiler',wrapper]
 if args.frontend:fronts.append(args.frontend.resolve())
 for front in fronts:
  env={**os.environ,'COOL_FRONTEND':str(front),'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
  source.write_text(program)
  engines=('tree','interp','jit','llvm','llvm-jit','O2')
  if args.sanitize_runtime and front==fronts[0]:engines+=('ASan/UBSan',)
  for engine in engines:
   if engine=='ASan/UBSan':
    ir=root/'program.ll';r=run([ROOT/'tools/cool','emit-ir',source,'-o',ir],env);assert r.returncode==0,r
    ir.write_text('\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in ir.read_text().splitlines())+'\n')
    checked=root/'instrumented.ll';r=run(['clang','-Wno-override-module','-O1','-fsanitize=address','-S','-emit-llvm',ir,'-o',checked],env);assert r.returncode==0,r
    assert '__asan_report_load' in checked.read_text() and '__asan_report_store' in checked.read_text()
    r=run(['clang','-Wno-override-module','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',ir,ROOT/'language/runtime.c','-o',binary],env);assert r.returncode==0,r
    r=run([binary],env)
   elif engine=='O2':
    r=run([ROOT/'tools/cool','build','--release',source,'-o',binary],env);assert r.returncode==0,r
    r=run([binary],env)
   else:r=run([ROOT/'tools/cool','run','--backend',engine,source],env)
   assert (r.returncode,r.stdout,r.stderr)==(0,'25\n',''),(front,engine,r)
  diagnostics=['outlive']*6+['conflicts']*6+['cannot assign','conflicts','replaced through a reference','outlive']
  for body,diagnostic in zip(invalid,diagnostics):
   code=prelude+body;source.write_text(code);r=run([front,'check',source],env)
   assert r.returncode==2 and diagnostic in r.stderr,(front,diagnostic,code,r)
  for exclusive in (False,True):
   reference='&mut ' if exclusive else '&'
   for container,bind,assign in (
    ('binding',f'var v={reference}x;',f'v={reference}y;'),
    ('field','var v='+('Mut' if exclusive else 'View')+'{r:'+reference+'x};',f'v.r={reference}y;'),
    ('array','var v=[1]'+('&mut i64' if exclusive else '&i64')+'{'+reference+'x};',f'v[0]={reference}y;'),
    ('heap','var v=new['+('Mut' if exclusive else 'View')+']('+('Mut' if exclusive else 'View')+'{r:'+reference+'x});',f'(*v).r={reference}y;')):
    for rootname in ('x','y'):
     for write in (False,True):
      # Independent root set model: replacement retains old and new roots.
      expected=2 if write or exclusive else 0
      action=f'{rootname}=3;' if write else f'let value={rootname};'
      source.write_text(prelude+'fn main(){var x=1;var y=2;'+bind+assign+action+'}')
      r=run([front,'check',source],env);assert r.returncode==expected,(front,container,exclusive,rootname,write,r)
      if expected:assert 'conflicts' in r.stderr,r
  r=run([front,'repl-quiet'],env,'var x=7;\nvar y=8;\nvar r=&x;\nr=&y;\nx=2;\ny=2;\n*r\n:forget r\nx=2;\ny=2;\ny\n:quit\n')
  assert r.returncode==0 and r.stdout=='8\n2\n' and r.stderr.count('error:')==2,r
  r=run([front,'repl-quiet'],env,'var x=7;\nvar y=8;\nvar r=&x;\nfn fail(p:&i64)->&i64 borrows(p){assert(false);return p;}\nr=fail(&y);\n*r\ny=9;\nx=2;\n:forget r\nx=2;\nx\n:quit\n')
  assert r.returncode==0 and r.stdout=='7\n2\n' and r.stderr.count('error:')==3,r
  r=run([front,'repl-quiet'],env,'var x=7;\nvar y=8;\nvar r=&x;\nr=missing(&y);\ny=9;\n*r\nx=2;\n:forget r\nx=2;\nx\n:quit\n')
  assert r.returncode==0 and r.stdout=='7\n2\n' and r.stderr.count('error:')==2,r
print(f'reference replacement: local/field/array/enum/generic/heap/mixed owning assignments, branch/loop/defer and scope roots; {len(invalid)} negative cases and 32 independent root/mode queries; five engines + O2 and REPL on {len(fronts)} frontends PASS')
