#!/usr/bin/env python3
"""Borrowed heap payloads carry external loans separately from physical owners."""
import argparse, os, shlex, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);p.add_argument('--sanitize-runtime',action='store_true');args=p.parse_args()
prelude='''import "std/io";import "std/mem";
struct View{r:&i64;}
struct Mut{r:&mut i64;}
struct Mixed{r:&i64;p:own[i64];}
struct Box[T]{value:T;}
struct Holder{p:own[View];n:i64;}
struct Recursive{next:own[Recursive];r:&i64;}
struct Bare{next:own[Bare];value:i64;}
enum Chain{End;Link(Entry);}
struct Entry{r:&i64;next:own[Chain];}
enum Maybe{None;Some(View);}
fn make(r:&i64)->own[View] borrows(r){return new[View](View{r:r});}
fn same(p:own[View])->own[View] borrows(p){return move p;}
fn get(p:own[View])->&i64 borrows(p){return (*p).r;}
fn mut_get(p:own[Mut])->&mut i64 borrows(p){return (*p).r;}
fn receiver_get(p:&own[View])->&i64 borrows(p){return (**p).r;}
fn heap_get(p:&own[View])->&View borrows(p){return &**p;}
fn take(p:&mut own[View])->own[View] borrows(p){return move *p;}
fn generic[T](p:own[T])->own[T] borrows(p){return move p;}
fn chain(n:i64,r:&i64)->own[Chain] borrows(r){if(n==0){return new[Chain](Chain.End);}return new[Chain](Chain.Link(Entry{r:r,next:chain(n-1,r)}));}
fn recursive(p:own[Recursive])->own[Recursive] borrows(p){return move p;}
'''
program=prelude+'''fn tests(){
 var x=7;var y=8;
 {let p=make(&x);let q=new[&View](&*p);assert(*(**q).r==7);}
 {var a=[1]own[View]{make(&x)};let s=a[:];assert(*(*s[0]).r==7);}
 {let p=make(&x);let q=same(move p);assert(*(*q).r==7);let r=get(move q);assert(*r==7);}x=9;
 {var p=make(&x);{let r=&p;assert(*receiver_get(r)==9);let h=heap_get(r);assert(*(*h).r==9);}let q=take(&mut p);assert(*(*q).r==9);}
 {let p=new[Mut](Mut{r:&mut x});let r=mut_get(move p);*r=10;}assert(x==10);
 {let p=new[&mut i64](&mut x);**p=11;let q=move p;**q=12;}assert(x==12);
 {let p=new[&i64](&x);assert(**p==12);let q=move p;assert(**q==12);}
 {let p=new[Mixed](Mixed{r:&x,p:new[i64](13)});let q=generic[Mixed](move p);assert(*(*q).r==12);assert(*(*q).p==13);}
 {let p=new[Box[View]](Box[View]{value:View{r:&x}});let q=generic[Box[View]](move p);assert(*(*q).value.r==12);}
 {let p=new[own[View]](make(&x));assert(*(**p).r==12);let q=move p;assert(*(**q).r==12);}
 {let p=new[[2]View]([2]View{View{r:&x},View{r:&y}});assert(*(*p)[1].r==8);let q=move p;assert(*(*q)[0].r==12);}
 {let h=Holder{p:make(&x),n:1};let q=move h;assert(*(*q.p).r==12);let r=get(move q.p);assert(*r==12);}
 {let p=new[Maybe](Maybe.Some(View{r:&x}));match(*p){Maybe.None=>{assert(false);}Maybe.Some(v)=>{assert(*v.r==12);}}}
 {let p=new[Chain](Chain.Link(Entry{r:&x,next:new[Chain](Chain.End)}));let q=move p;match(move *q){Chain.End=>{assert(false);}Chain.Link(entry)=>{assert(*entry.r==12);match(move *entry.next){Chain.End=>{}Chain.Link(_)=>{assert(false);}}}}}
 {var p=new[own[View]](make(&x));*p=make(&y);assert(*(**p).r==8);}
 {let p=chain(64,&x);assert(mem.owner_count()==65);let q=move p;match(move *q){Chain.End=>{assert(false);}Chain.Link(entry)=>{assert(*entry.r==12);}}}assert(mem.owner_count()==0);
 {let p=new[Bare]();let q=move p;assert((*q).value==0);}
 {var a=[2]i64{14,15};let p=new[[]i64](a[:]);(*p)[0]=16;let q=move p;assert(len(*q)==2);(*q)[1]=17;} 
}
fn main(){tests();assert(mem.owner_count()==0);io.println(42);}
'''
invalid=[
 'fn bad()->own[View] borrows(){var x=1;return new[View](View{r:&x});}fn main(){}',
 'fn bad(p:own[View])->&View borrows(p){return &*p;}fn main(){}',
 'fn bad(r:&i64)->own[View] borrows(){return make(r);}fn main(){}',
 'fn bad()->own[own[View]] borrows(){var x=1;return new[own[View]](make(&x));}fn main(){}',
 'fn main(){var x=1;let p=make(&x);x=2;}',
 'fn main(){var x=1;let p=make(&x);let r=&*p;let q=move p;}',
 'fn main(){var x=1;let p=new[own[View]](make(&x));let r=&**p;let q=move p;}',
 'fn main(){var x=1;let p=new[Mut](Mut{r:&mut x});x=2;}',
 'fn main(){var x=1;let p=new[Mut](Mut{r:&mut x});let r=mut_get(move p);x=2;}',
 'fn main(){let p=new[View]();}',
 'fn main(){let p=new[&i64]();}',
 'fn main(){var x=1;var y=2;var p=make(&x);{var z=3;(*p).r=&z;}}',
 'fn main(){var x=1;var p=new[own[View]](make(&x));{var y=2;*p=make(&y);}}',
 'fn replace(p:&mut own[View],r:&i64){*p=make(r);}fn main(){}',
 'fn main(){var x=1;var p=make(&x);let r=&p;let q=take(&mut p);}',
 'fn main(){var x=1;var p=make(&x);let r=heap_get(&p);let q=move p;}',
 'fn main(){var x=1;let p=make(&x);let q=same(move p);x=2;}',
 'fn main(){var x=1;let p=new[&mut i64](&mut x);let r=&*p;let q=move p;}',
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
   assert (r.returncode,r.stdout,r.stderr)==(0,'42\n',''),(front,engine,r)
  for code in [prelude+body for body in invalid]:
   source.write_text(code);r=run([front,'check',source],env);assert r.returncode==2,(front,code,r)
  queries=0
  operations={'root_read':'let n=x;','root_write':'x=2;',
   'owner_read':'let n=*(*p).r;','owner_move':'let q=move p;',
   'receiver_read':'let n=*(**r).r;','receiver_move':'let q=move *r;'}
  for exclusive in (False,True):
   for operation,body in operations.items():
    allowed=operation in ('root_read','receiver_read') or (operation=='owner_read' and not exclusive) or (operation=='receiver_move' and exclusive)
    source.write_text(prelude+'fn main(){var x=1;var p=make(&x);let r=&'+('mut ' if exclusive else '')+'p;'+body+'}')
    r=run([front,'check',source],env);assert r.returncode==(0 if allowed else 2),(front,exclusive,operation,allowed,r)
    queries+=1
  r=run([front,'repl-quiet'],env,'struct View{r:&i64;}\nvar x=7;\nlet p=new[View](View{r:&x});\nlet q=move p;\nx=2;\n:forget x\n*(*q).r\n:forget q\n:forget p\nx=2;\nx\n:quit\n')
  assert r.returncode==0 and r.stdout=='7\n2\n' and r.stderr.count('error:')==2,r
print(f'borrowed owning heaps: shared/exclusive payloads, recursive/generic/nested owners, move/drop/returns; {len(invalid)} rejected programs, {queries} modeled queries, five engines + O2, persistent REPL on {len(fronts)} frontends PASS')
