#!/usr/bin/env python3
"""Unused-template grammar rejection and executed cross-engine body coverage."""
import argparse, ast, os, shlex, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);args=p.parse_args()
# Reuse audited positive programs as data, without executing another test runner.
def fixture(name):
 values={}
 def literal(node):
  if isinstance(node,ast.Name):return values[node.id]
  if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add):return literal(node.left)+literal(node.right)
  return ast.literal_eval(node)
 for node in ast.parse((ROOT/'tools'/name).read_text()).body:
  if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('prelude','program'):
   values[node.targets[0].id]=literal(node.value)
 return values['program']
primary=fixture('test_primary_forms.py').replace('fn test(){','fn test[T](){').replace('test();','test[i64]();')
control=fixture('test_control_flow.py').replace('fn main(){','fn scenario[T](){')+'fn main(){scenario[i64]();}'
trace=''.join(str(n)+'\n' for n in [1,2,3,2,1,3,100,200,101,300,401,400,500,600,7,601,602,610,8,701,700,801,1,800,0,2,3,10,11,4,5])
invalid=[
 'let x=;','var x:i64;','let =1;','let x:Missing=1;','let x:void=1;',
 'let x=1','let x=1+;','let x=+1;','let x=(1+2;','let x=1 2;',
 'foo(,);','foo(1,);','foo(1;','foo[i64,](1);','foo[i64](;','foo[void](1);',
 'let x=new[T](1,2);','let x=cast[T]();','let x=borrow_raw[&T](x);',
 'let x=sizeof();','let x=[2]T{1,,2};','let x=G[T]{value:};','let x=G[T]{value 1};',
 'let x=a[];','let x=a[0:1:2];','let x=a[1+];','let x=a.;','let x=!;',
 'if(){}','if(true) return;','if(true){}else return;','while(true) break;',
 'for(var i=0 i<1;i=i+1){}','for(;true;let x=1){}','for(;;)return;',
 'return 1+;','return 1','defer;','defer {foo();}','break;','continue;',
 'match(x){_ {}}','match(x){G[T].Value(,)=>{}}','match(x){G[T].Value(a,b)=>{}}',
 'match(x){_=>return;}','unsafe return;',';','{let x=;}','let x=1=2;',
 '{'*130+'}'*130,
]
def run(command,env,input=None):return subprocess.run(list(map(str,command)),cwd=ROOT,env=env,input=input,capture_output=True,text=True,timeout=180)
with tempfile.TemporaryDirectory(prefix='cool template body ') as temporary:
 root=Path(temporary);source=root/'main.cool';binary=root/'program';wrapper=root/'bootstrap'
 wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');wrapper.chmod(0o755)
 fronts=[ROOT/'build/cool-compiler',wrapper]
 if args.frontend:fronts.append(args.frontend.resolve())
 for front in fronts:
  env={**os.environ,'COOL_FRONTEND':str(front),'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
  for program,expected in ((primary,'42\n'),(control,trace)):
   source.write_text(program)
   for engine in ('tree','interp','jit','llvm','llvm-jit','O2'):
    if engine=='O2':
     r=run([ROOT/'tools/cool','build','--release',source,'-o',binary],env);assert r.returncode==0,r
     r=run([binary],env)
    else:r=run([ROOT/'tools/cool','run','--backend',engine,source],env)
    assert (r.returncode,r.stdout,r.stderr)==(0,expected,''),(front,engine,r)
  for body in invalid:
   source.write_text('struct G[T]{value:T;}fn unused[T](){'+body+'}fn main(){}')
   r=run([front,'check',source],env);assert r.returncode==2,(front,body,r)
  library=root/'library.cool';manifest=root/'bundle'
  library.write_text('package a;pub struct B[T]{pub value:T;}pub enum E[T]{None;Value(T);}')
  source.write_text('package main;import "a";\nstruct S{B:[1]i64;}enum Local{Value(S);}\nfn parameter[T](a:S){assert(a.B[0]==0);}\nfn shadow[T](){\n {let a=S{};assert(a.B[0]==0);}\n let e=a.E[[1]i64].None;\n match(e){a.E[[1]i64].None=>{} a.E[[1]i64].Value(x)=>{assert(x[0]==0);}}\n for(var a=S{};false;){let x=a.B[0];}\n let after_for=a.E[[1]i64].None;\n match(Local.Value(S{})){Local.Value(a)=>{assert(a.B[0]==0);}}\n let after_match=a.E[[1]i64].None;\n parameter[i64](S{});\n}\nfn main(){shadow[i64]();}\n')
  manifest.write_text('__main\t'+str(source)+'\na\t'+str(library)+'\n')
  for mode in ('check-bundle','run-bundle','bytecode-bundle','jit-bundle'):
   r=run([front,mode,manifest],env);assert (r.returncode,r.stdout,r.stderr)==(0,'',''),(front,mode,r)
  r=run([front,'repl-quiet'],env,'var kept=7;\nfn retry[T](){let x=;}\nfn retry[T](x:T)->T{return move x;}\nretry[i64](kept)\n:quit\n')
  assert r.returncode==0 and r.stdout=='7\n' and r.stderr.count('error:')==1,r
print(f'template body: two executed grammar/control programs on five engines + O2, {len(invalid)} unused-body rejections and REPL recovery on {len(fronts)} frontends PASS')
