#!/usr/bin/env python3
"""A pending address must not outlive its owner during index/RHS evaluation."""
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
FRONTS=[[ROOT/'build/cool-compiler'],[ROOT/'build/coolc','--run',ROOT/'build/language.BIN']]
NEGATIVE=[
 'fn consume(p: own[[2]i64]) -> i64 { return 0; } fn main(){let p=new[[2]i64]([2]i64{1,2}); let x=(*p)[consume(move p)];}',
 'fn consume(p: own[i64]) -> i64 { return 9; } fn main(){let p=new[i64](1); *p=consume(move p);}',
 'struct S { items:[2]i64; } fn consume(p:own[S])->i64{return 0;} fn main(){let p=new[S](); let x=(*p).items[consume(move p)];}',
 'struct S { item:i64; } fn consume(p:own[S])->i64{return 9;} fn main(){let p=new[S](); (*p).item=consume(move p);}',
]
NEGATIVE += [
 'fn consume(p:own[i64])->i64{return *p;}fn main(){var p=new[i64](1);let r=&mut p;**r=consume(move *r);}',
 'fn consume(p:own[[2]i64])->usize{return 0;}fn main(){var p=new[[2]i64]([2]i64{1,2});let r=&mut p;let x=(**r)[consume(move *r)];}',
 'fn replace(p:&mut own[i64])->i64{*p=new[i64](3);return 4;}fn main(){var p=new[i64](1);let r=&mut p;**r=replace(r);}',
 'struct S{value:i64;}fn consume(p:own[S])->i64{return 2;}fn main(){var p=new[S]();let r=&mut p;(**r).value=consume(move *r);}',
 'struct Slot{value:&mut own[i64];}fn consume(p:own[i64])->i64{return *p;}fn main(){var p=new[i64](1);let s=Slot{value:&mut p};**s.value=consume(move *s.value);}',
]
NEGATIVE += [
 'fn id(p:&mut own[i64])->&mut own[i64] borrows(p){return p;}fn consume(p:own[i64])->i64{return *p;}fn main(){var p=new[i64](1);let r=&mut p;**id(r)=consume(move *r);}',
]
NEGATIVE.append('fn consume(p:own[i64])->i64{return 1;}fn f(p:own[i64],flag:bool)->i64{if(flag){return 0;}else{consume(move p);}return *p;}fn main(){}')
LOOP_NEGATIVE=[
 'while(false){p=new[i64](2);}',
 'for(var i=0;i<0;i=i+1){p=new[i64](2);}',
 'for(var i=0;i<1;p=new[i64](2)){let invalid=*p;break;}',
]
POSITIVE='''import "std/io";
fn consume(p:own[i64])->i64{return *p;}
fn id(p:&mut own[i64])->&mut own[i64] borrows(p){return p;}
enum Choice { First; Second; }
fn early(p:own[i64],first:bool)->own[i64]{if(first){return move p;}return move p;}
fn selected(p:own[i64],choice:Choice)->own[i64]{
 match(choice){Choice.First=>{return move p;}Choice.Second=>{}}
 return move p;
}
fn main(){
  assert(consume(early(new[i64](8),true))==8);
  assert(consume(early(new[i64](9),false))==9);
  assert(consume(selected(new[i64](10),Choice.First))==10);
  assert(consume(selected(new[i64](11),Choice.Second))==11);
  let a=new[[2]i64]([2]i64{10,20}); let b=new[i64](1);
  io.println((*a)[consume(move b)]);
  let p=new[i64](2); let q=new[i64](3); *p=consume(move q); io.println(*p);
  var r=new[i64](4); r=move r; io.println(*r);
  var restored=new[i64](0); let previous=move restored;
  if (true) {restored=new[i64](5);} else {restored=new[i64](6);}
  assert(*restored==5);
  let previous_again=move restored;
  for(restored=new[i64](7);false;) {}
  assert(*restored==7);
  {var owner=new[i64](1);{let slot=&mut owner;**id(slot)=2;}assert(*owner==2);}
  {var owner=new[i64](1);{let slot=&mut owner;**slot=**slot+1;assert(**slot==2);let part=&mut **slot;*part=3;}assert(*owner==3);}
  {var owner=new[[2]i64]([2]i64{5,6});let slot=&mut owner;let item=&mut (**slot)[1];*item=7;assert(*item==7);}
}
'''
with tempfile.TemporaryDirectory(prefix='cool-owner-evaluation-') as tmp:
 p=Path(tmp)/'main.cool'
 for source in NEGATIVE:
  p.write_text(source)
  for front in FRONTS:
   run=subprocess.run([*front,'check',p],capture_output=True,text=True,timeout=10)
   assert run.returncode==2 and ('owner moved while an access' in run.stderr or 'moved value' in run.stderr or 'conflicts' in run.stderr),(source,front,run)
 for loop in LOOP_NEGATIVE:
  p.write_text('fn main(){var p=new[i64](1);let q=move p;'+loop+'let invalid=*p;}')
  for front in FRONTS:
   run=subprocess.run([*front,'check',p],capture_output=True,text=True,timeout=10)
   assert run.returncode==2 and 'moved value' in run.stderr,(loop,front,run)
 p.write_text(POSITIVE)
 for mode in ('tree','interp','jit','llvm','llvm-jit'):
  run=subprocess.run([ROOT/'tools/cool','run','--backend',mode,p],capture_output=True,text=True,timeout=30)
  assert (run.returncode,run.stdout,run.stderr)==(0,'20\n3\n4\n',''),(mode,run)
print('owner evaluation: pending index/store moves and zero-iteration/for-update liveness rejected by both frontends; unrelated moves, reinitialization and terminal-branch transfers across five engines PASS')
