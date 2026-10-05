#!/usr/bin/env python3
"""Primary expression grammar: calls, literals, projections, casts and borrowing."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);args=p.parse_args()
prelude='''import "std/io";import "std/mem";
struct Pair{first:i64;second:i64;}
enum E{Empty;Value(i64);}
struct Box[T]{value:T;}
fn identity[T](value:T)->T{return move value;}
fn Pair.sum(self:&Pair)->i64{return (*self).first+(*self).second;}
fn consume(owner:own[i64])->i64{return *owner;}
'''
program=prelude+'''fn test(){
 let zero=Pair{};assert(zero.first==0 && zero.second==0);
 var pair=Pair{second:2,first:1,};assert(pair.sum()==3);
 let box=Box[Pair]{value:identity[Pair](pair)};assert(box.value.first==1);
 let value=E.Value((3+4));match(value){E.Empty()=>{assert(false);}E.Value(n)=>{assert(n==7);}}
 let unit=E.Empty();match(unit){E.Empty=>{}E.Value(_)=>{assert(false);}}
 var array=[3]i64{1,2,3,};assert(array[1]==2);
 {let slice=array[1:];assert(len(slice)==2);slice[0]=9;}
 assert(array[1]==9);assert(len(array[:0])==0);assert(len(array[:])==3);
 let empty=[]i64{};assert(len(empty)==0);assert(sizeof([3]i64)==24);
 let owner=new[i64](5);assert(consume(move owner)==5);
 let default_owner=new[i64]();assert(*default_owner==0);
 var n=11;{let reference=&mut n;*reference=12;}{let reference=&n;assert(*reference==12);}
 unsafe {let pointer=&raw n;assert(pointer!=null);*pointer=13;assert(cast[u64](pointer)!=0);}
 {let anchor=&mut n;unsafe{let pointer=cast[*i64](anchor);let reference=borrow_raw[&mut i64](pointer,anchor);*reference=14;}}
 assert(n==14);assert(i8(255)==-1);assert(cast[i8](255)==-1);
 assert(-pair.first == -1);assert(!(pair.first==0));assert((~u8(0))==255);
}
fn main(){test();assert(mem.owner_count()==0);io.println(42);}
'''
invalid=[
 'let p=Pair{first:1};','let p=Pair{first:1,first:2};','let p=Pair{first:1;second:2};',
 'let a=[2]i64{1};','let a=[1]i64{1,2};','let s=[]i64{1};',
 'let e=E.Value;','let e=E.Value();','let e=E.Empty(1);','let e=E.Value(1,);',
 'identity[i64](1,);','let f=identity;','let n=(identity[i64])(1);',
 'var p=Pair{};p.sum(,);','var p=Pair{};p.sum(1,);',
 'let owner=new[i64](1,2);','let n=cast[i64]();','let n=cast[bool](1);',
 'let n=sizeof(1);','let n=len(1);','let n=&1;','let n=&raw 1;',
 'var a=[1]i64{};let n=a[true];','var a=[1]i64{};let s=a[0:1:1];',
 'let n=borrow_raw[i64](null,null);','var n=0;unsafe{let r=borrow_raw[&i64](&raw n,n);}',
]
recursive_types=[
 'struct Node{kids:[]Node;value:i64;}fn main(){var empty=[0]Node{};}',
 'struct Node{kids:[]Node;r:&i64;}fn main(){let node=new[Node]();}',
]
def run(command,env):return subprocess.run([str(x) for x in command],cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)
with tempfile.TemporaryDirectory(prefix='cool primary forms ') as temporary:
 directory=Path(temporary);source=directory/'main.cool';binary=directory/'program';wrapper=directory/'bootstrap'
 wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');wrapper.chmod(0o755)
 fronts=[ROOT/'build/cool-compiler',wrapper]
 if args.frontend:fronts.append(args.frontend.resolve())
 for frontend in fronts:
  env={**os.environ,'COOL_FRONTEND':str(frontend),'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
  for index,code in enumerate(recursive_types):
   source.write_text(code);r=run([frontend,'check',source],env)
   assert r.returncode==(0 if index==0 else 2),(code,r)
   if index:assert 'reference storage requires an explicit initializer' in r.stderr,(code,r)
  # Empty reference arrays may initialize, but cannot manufacture an element.
  for setup,value in [('let empty=[0]&i64{};','empty[0]'),
                      ('let empty=[0]&mut i64{};','empty[0]'),
                      ('let empty=new[[0]&mut i64]();','(*empty)[0]')]:
   source.write_text('fn main(){'+setup+'let value='+value+';}')
   r=run([frontend,'check',source],env);assert r.returncode==0,r
   for engine in ('tree','interp','jit','llvm','llvm-jit','O2'):
    if engine=='O2':
     r=run([ROOT/'tools/cool','build','--release',source,'-o',binary],env);assert r.returncode==0,r
     r=run([binary],env)
    else:r=run([ROOT/'tools/cool','run','--backend',engine,source],env)
    assert r.returncode==2 and 'index out of bounds' in r.stderr,(frontend,engine,r)
  source.write_text(program)
  for engine in ('tree','interp','jit','llvm','llvm-jit','O2'):
   if engine=='O2':
    result=run([ROOT/'tools/cool','build','--release',source,'-o',binary],env);assert result.returncode==0,result
    result=run([binary],env)
   else:result=run([ROOT/'tools/cool','run','--backend',engine,source],env)
   assert (result.returncode,result.stdout,result.stderr)==(0,'42\n',''),(frontend,engine,result)
  for body in invalid:
   source.write_text(prelude+'fn main(){'+body+'}')
   result=run([frontend,'check',source],env);assert result.returncode==2,(frontend,body,result)
 print(f'primary forms: aggregate/enum/array/slice/call/owner/reference/raw/cast grammar, zero surviving owners and {len(invalid)} rejections on {len(fronts)} frontends; five engines + O2 PASS')
