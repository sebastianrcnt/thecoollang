#!/usr/bin/env python3
"""Owning aggregates retain external borrows separately from owned storage."""
import argparse, os, shlex, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);p.add_argument('--sanitize-runtime',action='store_true');args=p.parse_args()
prelude='''import "std/io";import "std/mem";
struct Mixed{r:&i64;p:own[i64];}
struct Exclusive{r:&mut i64;p:own[i64];}
struct View{r:&i64;data:[]i64;p:own[i64];}
struct Wrap{value:Mixed;}
struct Box[T]{value:T;}
fn generic[T](value:T)->T borrows(value){return move value;}
enum Choice{None;Some(Mixed);Owned(own[i64]);}
fn extract(value:Wrap)->Mixed borrows(value){return move value.value;}
fn external(value:Mixed)->&i64 borrows(value){return value.r;}
fn identity(value:Mixed)->Mixed borrows(value){return move value;}
fn take(value:&mut Mixed)->Mixed borrows(value){return move *value;}
fn label(value:&Mixed)->&i64 borrows(value){return (*value).r;}
fn payload(value:&Mixed)->&i64 borrows(value){return &*(*value).p;}
fn exclusive(value:Exclusive)->Exclusive borrows(value){return move value;}
fn array(value:[2]Mixed)->[2]Mixed borrows(value){return move value;}
fn choice(value:Choice)->Choice borrows(value){return move value;}
'''
program=prelude+'''fn tests(){
 var x=7;var y=8;
 {let a=Mixed{r:&x,p:new[i64](9)};let b=identity(move a);assert(*b.r==7);assert(*b.p==9);{let r=&b;assert(*label(r)==7);assert(*payload(r)==9);}}
 {var a=Mixed{r:&x,p:new[i64](10)};let receiver=&mut a;{let b=take(receiver);assert(*b.r==7);assert(*b.p==10);}assert(*(*receiver).r==7);}
 {let a=Exclusive{r:&mut x,p:new[i64](11)};let b=exclusive(move a);*b.r=17;assert(*b.p==11);}assert(x==17);
 {var a=Exclusive{r:&mut x,p:new[i64](12)};let receiver=&mut a;{let b=move *receiver;*b.r=18;assert(*b.p==12);}*(*receiver).r=19;}assert(x==19);
 {let a=[2]Mixed{Mixed{r:&x,p:new[i64](20)},Mixed{r:&y,p:new[i64](21)}};let b=array(move a);assert(*b[0].r==19);assert(*b[1].p==21);}
 {var a=[2]Mixed{Mixed{r:&x,p:new[i64](22)},Mixed{r:&y,p:new[i64](23)}};let receiver=&mut a;{let b=move *receiver;assert(*b[0].p==22);}assert(*(*receiver)[1].r==8);}
 {let w=Wrap{value:Mixed{r:&x,p:new[i64](24)}};let moved=move w;assert(*moved.value.r==19);assert(*moved.value.p==24);}
 {let a=Choice.Some(Mixed{r:&x,p:new[i64](25)});let b=choice(move a);match(move b){Choice.None=>{assert(false);}Choice.Some(v)=>{assert(*v.r==19);assert(*v.p==25);}Choice.Owned(p)=>{assert(false);}}}
 {match(Choice.Some(Mixed{r:&x,p:new[i64](26)})){Choice.None=>{assert(false);}Choice.Some(_)=>{}Choice.Owned(_)=>{assert(false);}}}
 {var a=Choice.Some(Mixed{r:&x,p:new[i64](27)});let receiver=&mut a;{let b=move *receiver;match(move b){Choice.None=>{assert(false);}Choice.Some(v)=>{assert(*v.r==19);}Choice.Owned(_)=>{assert(false);}}}match(move *receiver){Choice.None=>{assert(false);}Choice.Some(v)=>{assert(*v.r==19);}Choice.Owned(_)=>{assert(false);}}}
 {let box=Box[Mixed]{value:Mixed{r:&x,p:new[i64](28)}};let moved=generic[Box[Mixed]](move box);assert(*moved.value.p==28);assert(*moved.value.r==19);}
 {let w=Wrap{value:Mixed{r:&x,p:new[i64](28)}};let moved=extract(move w);assert(*moved.r==19);assert(*moved.p==28);}
 {let r=external(Mixed{r:&x,p:new[i64](29)});assert(*r==19);}
 {var a=Choice.Owned(new[i64](30));let receiver=&mut a;let b=move *receiver;match(move b){Choice.None=>{assert(false);}Choice.Some(_)=>{assert(false);}Choice.Owned(p)=>{assert(*p==30);}}}
 {var a=[2]i64{30,31};let view=View{r:&x,data:a[:],p:new[i64](32)};let moved=move view;assert(*moved.r==19);moved.data[0]=33;assert(*moved.p==32);}
 {var a=[2]i64{34,35};var view=View{r:&x,data:a[:],p:new[i64](36)};let receiver=&mut view;{let moved=move *receiver;moved.data[0]=37;assert(*moved.p==36);}assert(len((*receiver).data)==2);(*receiver).data[1]=38;assert(*(*receiver).r==19);}
}
fn main(){tests();assert(mem.owner_count()==0);io.println(42);}
'''
invalid=[
 'fn bad(v:Mixed)->&i64 borrows(v){return &*v.p;}fn main(){}',
 'fn bad(v:Mixed)->Mixed borrows(){return move v;}fn main(){}',
 'fn bad()->Mixed borrows(){var x=1;return Mixed{r:&x,p:new[i64](7)};}fn main(){}',
 'fn bad(v:[2]Mixed)->&i64 borrows(v){return &*v[0].p;}fn main(){}',
 'fn main(){var x=1;let v=Mixed{r:&x,p:new[i64](7)};let r=&v;let gone=move v;}',
 'fn main(){var x=1;var v=Mixed{r:&x,p:new[i64](7)};let r=&mut v;let gone=move v;}',
 'fn main(){var x=1;var v=Mixed{r:&x,p:new[i64](7)};let r=&*v.p;let gone=move v;}',
 'fn main(){var x=1;var v=Mixed{r:&x,p:new[i64](7)};let r=payload(&v);let gone=move v;}',
 'fn main(){var x=1;var v=Mixed{r:&x,p:new[i64](7)};let r=&v;let gone=move *r;}',
 'fn main(){var x=1;var v=Mixed{r:&x,p:new[i64](7)};let r=label(&v);x=2;}',
 'fn main(){var x=1;let v=Mixed{r:&x,p:new[i64](7)};let gone=identity(move v);x=2;}',
 'fn main(){var x=1;var v=Exclusive{r:&mut x,p:new[i64](7)};let r=&mut v;let gone=move *r;*(*r).r=2;}',
 'fn main(){var x=1;var v=Mixed{r:&x,p:new[i64](7)};let r=&mut v;let gone=take(r);x=2;}',
 'fn main(){var x=1;var v=Mixed{r:&x,p:new[i64](7)};let r=&mut v;let p=&*(*r).p;let gone=take(r);}',
 'fn main(){var x=1;let p=new[Mixed](Mixed{r:&x,p:new[i64](7)});}',
 'struct Bad{r:&i64;p:own[&i64];}fn main(){}',
 'fn main(){var x=1;var a=[2]Mixed{Mixed{r:&x,p:new[i64](7)},Mixed{r:&x,p:new[i64](8)}};let r=&a;let gone=move a;}',
]
def run(command,env,input=None):return subprocess.run(list(map(str,command)),cwd=ROOT,env=env,input=input,capture_output=True,text=True,timeout=180)
with tempfile.TemporaryDirectory(prefix='cool mixed owning references ') as temporary:
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
  # Owned handles left by a receiver move are empty, with checked faults.
  source.write_text(prelude+'fn main(){var x=7;var v=Mixed{r:&x,p:new[i64](9)};let r=&mut v;{let taken=take(r);}let p=&*(*r).p;}')
  for engine in ('tree','interp','jit','llvm','llvm-jit','O2'):
   if engine=='O2':
    r=run([ROOT/'tools/cool','build','--release',source,'-o',binary],env);assert r.returncode==0,r
    r=run([binary],env)
   else:r=run([ROOT/'tools/cool','run','--backend',engine,source],env)
   assert r.returncode==2 and 'empty or moved owner' in r.stderr,(front,engine,r)
  for code in [prelude+body for body in invalid]:
   source.write_text(code);r=run([front,'check',source],env);assert r.returncode==2,(front,code,r)
  # Independent physical/external-root permission model: shared receiver
  # permits reads, exclusive receiver blocks aliases; any receiver pins moves.
  queries=0
  operations={'root_read':'let n=x;','root_write':'x=2;',
   'owner_read':'let n=*v.p;','owner_write':'*v.p=2;',
   'whole_move':'let gone=move v;','receiver_read':'let n=*(*r).p;',
   'receiver_write':'*(*r).p=2;'}
  for exclusive in (False,True):
   for operation,body in operations.items():
    allowed=operation=='root_read' or operation=='receiver_read' or (operation=='owner_read' and not exclusive) or (operation=='receiver_write' and exclusive)
    source.write_text(prelude+'fn main(){var x=1;var v=Mixed{r:&x,p:new[i64](7)};let r=&'+('mut ' if exclusive else '')+'v;'+body+'}')
    r=run([front,'check',source],env);assert r.returncode==(0 if allowed else 2),(front,exclusive,operation,allowed,r)
    queries+=1
  r=run([front,'repl-quiet'],env,'struct Mixed{r:&i64;p:own[i64];}\nvar x=7;\nlet v=Mixed{r:&x,p:new[i64](9)};\nlet moved=move v;\nx=2;\n:forget x\n*moved.r\n*moved.p\n:forget moved\n:forget v\nx=2;\nx\n:quit\n')
  assert r.returncode==0 and r.stdout=='7\n9\n2\n' and r.stderr.count('error:')==2,r
print(f'mixed owning references: structs/arrays/enums, shared/exclusive receivers, move contracts and cleanup; {len(invalid)} rejections, {queries} modeled queries, five engines + O2, persistent REPL on {len(fronts)} frontends PASS')
