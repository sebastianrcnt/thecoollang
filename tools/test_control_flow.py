#!/usr/bin/env python3
"""Observable control-flow, defer capture/ordering and lexical owner cleanup."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);args=p.parse_args()
program='''import "std/io";import "std/mem";
enum E{Empty;Value(i64);}
struct Counter{value:i64;}
fn mark(n:i64)->i64{io.println(n);return n;}
fn emit(n:i64){io.println(n);}
fn observe(n:i64){io.println(n);io.println(mem.owner_count());}
fn returning()->i64{defer emit(mark(1));{defer emit(mark(2));return mark(3);}}
fn post(n:i64)->i64{io.println(200+n);return n+1;}
fn select()->E{io.println(600);return E.Value(7);}
fn matched(e:E)->i64{match(e){E.Empty=>{return 0;}E.Value(value)=>{defer emit(610);return value;}}}
fn main(){
 io.println(returning());
 for(var i=0;i<3;i=post(i)){defer emit(100+i);if(i==0){continue;}if(i==1){break;}emit(999);}
 emit(300);
 while(true){defer emit(400);{defer emit(401);break;}}
 for(;;){defer emit(500);break;}
 match(select()){E.Empty=>{emit(999);}E.Value(value)=>{defer emit(601);io.println(value);}}
 match(E.Empty){E.Value(_)=>{emit(999);},_=>{emit(602);},}
 io.println(matched(E.Value(8)));
 {var value=700;defer emit(value);value=701;io.println(value);}
 {defer observe(800);let owner=new[i64](1);defer observe(801);}
 assert(mem.owner_count()==0);
 var array=[1]i64{};for(array[0]=2;array[0]<4;array[0]=array[0]+1){io.println(array[0]);}
 var counter=Counter{};for(counter.value=10;counter.value<12;counter.value=counter.value+1){io.println(counter.value);}
 var value=0;{let reference=&mut value;for(*reference=4;*reference<6;*reference=*reference+1){io.println(*reference);}}

}
'''
expected=''.join(str(n)+'\n' for n in [1,2,3,2,1,3,100,200,101,300,401,400,500,600,7,601,602,610,8,701,700,801,1,800,0,2,3,10,11,4,5])
invalid=[
 'let a=[1]i64{};for(a[0]=1;false;){}',
 'var a=[1]i64{};let borrowed=&a[0];for(a[0]=1;false;){}',
 'break;','continue;','if(1){}','while(1){}','for(;1;){}',
 'if(true) return;','while(true) break;','var x:i64;','let x=1;x=2;',
 'return 1;','defer mark(1);','defer {emit(1);}',';',
 'match(1){_=>{}}','match(E.Empty){E.Value(x)=>{}}',
 'match(E.Empty){E.Empty=>{}E.Empty=>{}E.Value(x)=>{}}',
 'match(E.Empty){_=>{}E.Empty=>{}}',
 'match(E.Value(1)){E.Empty=>{}E.Value=>{}}',
 'match(E.Empty){E.Empty(x)=>{}E.Value(x)=>{}}',
 'match(E.Value(1)){E.Empty=>{}E.Value(x)=>{}}emit(x);',
 'for(var i=0;i<1;i=i+1){}emit(i);',
]
def run(command,env):return subprocess.run([str(x) for x in command],cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)
with tempfile.TemporaryDirectory(prefix='cool control flow ') as temporary:
 directory=Path(temporary);source=directory/'main.cool';binary=directory/'program';wrapper=directory/'bootstrap'
 wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');wrapper.chmod(0o755)
 fronts=[ROOT/'build/cool-compiler',wrapper]
 if args.frontend:fronts.append(args.frontend.resolve())
 for frontend in fronts:
  env={**os.environ,'COOL_FRONTEND':str(frontend),'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
  source.write_text(program)
  for engine in ('tree','interp','jit','llvm','llvm-jit','O2'):
   if engine=='O2':
    result=run([ROOT/'tools/cool','build','--release',source,'-o',binary],env);assert result.returncode==0,result
    result=run([binary],env)
   else:result=run([ROOT/'tools/cool','run','--backend',engine,source],env)
   assert (result.returncode,result.stdout,result.stderr)==(0,expected,''),(frontend,engine,result)
  for body in invalid:
   source.write_text('enum E{Empty;Value(i64);}fn mark(n:i64)->i64{return n;}fn emit(n:i64){}fn main(){'+body+'}')
   result=run([frontend,'check',source],env);assert result.returncode==2,(frontend,body,result)
 print(f'control flow: 31 ordered events, defer capture/return/break/continue/match/owner cleanup and {len(invalid)} rejections on {len(fronts)} frontends; five engines + O2 PASS')
