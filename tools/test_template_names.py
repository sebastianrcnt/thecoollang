#!/usr/bin/env python3
"""Pre-specialization name resolution, lexical scopes, privacy and recovery."""
import argparse, os, shlex, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);args=p.parse_args()
prelude='''import "std/io";import "std/mem";import lib "example.test/template-names/lib";
struct Box[T]{value:T;}enum Choice[T]{None;Value(T);}
fn known()->i64{return 7;}
'''
program=prelude+'''struct Member{value:i64;}struct Receiver{member:Member;}
fn Member.missing(self:&Member)->i64{return (*self).value;}
fn unused[T](value:T)->T{
 let b=Box[T]{value:move value};let p:*T=null;assert(p==null);
 let yes=true;assert(yes && !false);let n=i64(7);assert(n==known());
 let a=[2]i64{1,2};assert(len(a)==2);assert(sizeof(T)>0);
 assert(mem.owner_count()==0);io.print("");
 {let lib=Box[i64]{value:7};assert(lib.value==7);}
 let c=lib.Public[T]{value:move b.value};
 let e=Choice[i64].Value(known());
 match(e){Choice[i64].None=>{assert(false);}Choice[i64].Value(lib)=>{assert(lib==7);}}
 for(var lib=Box[i64]{value:0};false;){let x=lib.value;}
 return later[T](move c.value);
}
fn later[T](value:T)->T{return lib.identity[T](move value);}
fn dependent[T](value:T)->i64{return value.member.missing();}
fn main(){assert(dependent[Receiver](Receiver{member:Member{value:7}})==7);io.println(unused[i64](42));}
'''
invalid=[
 ('return missing;','unknown name'),('missing();','unknown name'),
 ('missing[T]();','unknown name'),('let x=Missing{value:1};','unknown name'),
 ('let x=missing.value;','unknown name'),('missing=1;','unknown name'),
 ('let x=x;','unknown name'),('let x=later_local;let later_local=7;','unknown name'),
 ('{let x=1;}let y=x;','unknown name'),
 ('for(var i=0;false;i=i+1){}let x=i;','unknown name'),
 ('match(Choice[i64].Value(1)){Choice[i64].None=>{}Choice[i64].Value(x)=>{}}let y=x;','unknown name'),
 ('let x=Choice[i64].None;match(x){Choice[i64].None=>{let only=1;}Choice[i64].Value(v)=>{assert(only==1);}}','unknown name'),
 ('lib.missing();','unknown name'),('lib.missing[T]();','unknown name'),
 ('let x=lib.Hidden[T]{value:1};','private'),('lib.secret();','private'),
 ('let x=mem.missing();','unknown name'),('let x=io.missing();','unknown name'),
 ('unknown.member();','unknown name'),
]
def run(command,env,input=None,cwd=ROOT):
 return subprocess.run(list(map(str,command)),cwd=cwd,env=env,input=input,capture_output=True,text=True,timeout=180)
with tempfile.TemporaryDirectory(prefix='cool template names ') as temporary:
 root=Path(temporary);source=root/'main.cool';binary=root/'program';wrapper=root/'bootstrap'
 (root/'cool.mod').write_text('module example.test/template-names\n');(root/'lib').mkdir()
 (root/'lib/lib.cool').write_text('package lib;pub struct Public[T]{pub value:T;}struct Hidden[T]{value:T;}fn secret()->i64{return 1;}pub fn identity[T](value:T)->T{return move value;}')
 wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');wrapper.chmod(0o755)
 fronts=[ROOT/'build/cool-compiler',wrapper]
 if args.frontend:fronts.append(args.frontend.resolve())
 for front in fronts:
  env={**os.environ,'COOL_FRONTEND':str(front),'COOL_CACHE':str(root/'cache'),'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
  source.write_text(program)
  for engine in ('tree','interp','jit','llvm','llvm-jit','O2'):
   if engine=='O2':
    r=run([ROOT/'tools/cool','build','--release',source,'-o',binary],env);assert r.returncode==0,r
    r=run([binary],env)
   else:r=run([ROOT/'tools/cool','run','--backend',engine,source],env)
   assert (r.returncode,r.stdout,r.stderr)==(0,'42\n',''),(front,engine,r)
  for body,error in invalid:
   source.write_text(prelude+'fn rejected[T](){'+body+'}fn main(){}')
   r=run([ROOT/'tools/cool','check',source],env);assert r.returncode==2 and error in r.stderr,(front,body,r)
  source.write_text(prelude+'fn dependent[T](value:T)->i64{return value.member.missing();}fn main(){dependent[i64](7);}')
  r=run([ROOT/'tools/cool','check',source],env);assert r.returncode==2 and ('field' in r.stderr or 'aggregate' in r.stderr),(front,r)
  r=run([front,'repl-quiet'],env,'var kept=7;\nfn retry[T](x:T)->T{return missing;}\nfn retry[T](x:T)->T{return move x;}\nretry[i64](kept)\n:quit\n')
  assert r.returncode==0 and r.stdout=='7\n' and r.stderr.count('error:')==1,r
print(f'template names: lexical/import/type/function resolution, forward declarations, dependent members and five engines/O2; {len(invalid)} unused-body rejections and REPL rollback on {len(fronts)} frontends PASS')
