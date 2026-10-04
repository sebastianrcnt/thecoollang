#!/usr/bin/env python3
"""Union provenance: every possible returned root must remain protected."""
from pathlib import Path
import subprocess
import random
import tempfile
ROOT=Path(__file__).resolve().parents[1]
FRONTS=[[ROOT/'build/cool-compiler'],[ROOT/'build/coolc','--run',ROOT/'build/language.BIN']]
PRELUDE='''import "std/io";import "std/mem";
fn choose(flag:bool,a:&i64,b:&i64)->&i64 borrows(a,b){if(flag){return a;}return b;}
fn choose_mut(flag:bool,a:&mut i64,b:&mut i64)->&mut i64 borrows(a,b){if(flag){return a;}return b;}
fn project(a:&i64)->&i64 borrows(a){return a;}
fn project_mut(a:&mut i64)->&mut i64 borrows(a){return a;}
fn add(a:&mut i64){*a=*a+1;}
fn index(other:&mut i64)->usize{*other=*other+1;return 0;}
fn consume(value:own[i64])->i64{return *value;}
fn observe(a:&i64,value:i64){}
struct Item{value:i64;}
fn Item.select(self:&Item,other:&Item,first:bool)->&i64 borrows(self,other){if(first){return &(*self).value;}return &(*other).value;}
'''
POSITIVE=PRELUDE+'''fn tests(){
 var a=1;var b=2;var c=3;
 {let r=choose(true,&a,&b);assert(*r==1);let s=&*r;assert(*s==1);}
 {let r=choose(false,&a,&b);assert(*r==2);let s=project(r);assert(*s==2);}
 {let r=choose(false,choose(true,&a,&b),&c);assert(*r==3);let s=&*r;assert(*s==3);}
 {let r=choose_mut(false,&mut a,&mut b);*r=7;{let s=&mut *r;*s=8;}*r=9;}
 assert(a==1 && b==9);
 {let r=&*choose_mut(false,&mut a,&mut b);assert(*r==9);let s=&*r;assert(*s==9);}
 {let r=&mut *choose_mut(false,&mut a,&mut b);*r=9;}
 {let r=&*(&mut a);assert(*r==1);}

 {let ra=&mut a;let rb=&mut b;{let r=choose_mut(true,ra,rb);let s=project_mut(r);*s=11;}*ra=12;*rb=13;}
 assert(a==12 && b==13);
 {let r=choose(true,&a,&a);let s=choose(false,r,r);assert(*s==12);}
 {var array=[2]i64{4,5};var other=0;let r=&array[index(&mut other)];other=7;assert(*r==4 && other==7);}
 {var array=[2]i64{4,5};var other=0;let r=&mut array[index(&mut other)];other=7;*r=8;assert(other==7);}
 {let left=Item{value:17};let right=Item{value:19};let r=left.select(&right,false);assert(*r==19);}
 let one=new[i64](21);let two=new[i64](22);{let r=choose(false,&*one,&*two);assert(*r==22);}let moved=move one;assert(*moved==21);
}
fn main(){tests();assert(mem.owner_count()==0);io.println(42);}
'''
NEGATIVE=[]
for root in ('a','b','c'):
 NEGATIVE.append((f'var a=1;var b=2;var c=3;let r=choose(true,choose(false,&a,&b),&c);{root}=9;', 'conflicts'))
 NEGATIVE.append((f'var a=1;var b=2;var c=3;let r=choose_mut(true,choose_mut(false,&mut a,&mut b),&mut c);let s=project_mut(r);{root}=9;', 'conflicts'))
for root in ('a','b'):
 NEGATIVE += [
  (f'let a=new[i64](1);let b=new[i64](2);let r=choose(true,&*a,&*b);let moved=move {root};','conflicts'),
  (f'let a=new[i64](1);let b=new[i64](2);observe(choose(true,&*a,&*b),consume(move {root}));','conflicts'),
  (f'let a=new[i64](1);let b=new[i64](2);*choose_mut(true,&mut *a,&mut *b)=consume(move {root});','conflicts'),
  (f'var a=1;var b=2;defer add(choose_mut(true,&mut a,&mut b));{root}=9;','conflicts'),
 ]
NEGATIVE += [
 ('var a=1;var b=2;let ra=&mut a;let rb=&mut b;let r=choose_mut(true,ra,rb);*ra=3;','conflicts'),
 ('var a=1;var b=2;let ra=&mut a;let rb=&mut b;let r=choose_mut(true,ra,rb);*rb=3;','conflicts'),
 ('var a=1;var b=2;let r=choose_mut(true,&mut a,&mut b);let s=&*r;*r=4;','conflicts'),
 ('var a=1;var b=2;let r=choose_mut(true,&mut a,&mut b);let s=&mut *r;let n=*r;','conflicts'),
 ('var a=1;var b=2;let r=choose(true,&a,&b);*r=4;','immutable'),
 ('var a=1;choose_mut(true,&mut a,&mut a);','conflicts'),
 ('var a=Item{};var b=Item{};let r=a.select(&b,true);b.value=2;','conflicts'),
 ('var a=1;var b=2;let r=&*choose_mut(true,&mut a,&mut b);b=3;','conflicts'),
 ('var a=1;var b=2;let r=&*choose_mut(true,&mut a,&mut b);a=3;','conflicts'),
 ('var a=1;var b=2;let r=&mut *choose(true,&a,&b);','mutable place'),
 ('var a=1;let r=&*(&mut a);a=3;','conflicts'),
 ('let a=new[i64](1);let b=new[i64](2);*(&mut *choose_mut(true,&mut *a,&mut *b))=consume(move b);','conflicts'),
]
WHOLE=[
 ('fn bad(a:&i64,b:&i64)->&i64 borrows(a){return choose(true,a,b);}fn main(){}','outlive'),
 ('fn bad(a:&i64,b:&i64)->&i64 borrows(a,b){let local=1;return choose(true,a,&local);}fn main(){}','outlive'),
]
def run(command):return subprocess.run([str(x) for x in command],cwd=ROOT,text=True,capture_output=True,timeout=120)
with tempfile.TemporaryDirectory(prefix='cool-reference-sets-') as tmp:
 source=Path(tmp)/'main.cool';source.write_text(POSITIVE)
 for front in FRONTS:
  p=run([*front,'check',source]);assert p.returncode==0,(p.stdout,p.stderr)
 for engine in ('tree','interp','jit','llvm','llvm-jit'):
  p=run([ROOT/'tools/cool','run','--backend',engine,source]);assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),(engine,p)
 binary=Path(tmp)/'native';p=run([ROOT/'tools/cool','build','--release',source,'-o',binary]);assert p.returncode==0,p
 p=run([binary]);assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),p
 for body,error in [(PRELUDE+'fn main(){'+body+'}',error) for body,error in NEGATIVE]+[(PRELUDE+body,error) for body,error in WHOLE]:
  source.write_text(body)
  for front in FRONTS:
   p=run([*front,'check',source]);assert p.returncode==2 and error in p.stderr,(body,error,p)
 # Repeated unioning of the same source is a set, not exponential duplicated loans.
 body='var x=42;let r0=&x;'+''.join(f'let r{i}=choose(true,r{i-1},r{i-1});' for i in range(1,65))+'assert(*r64==42);'
 source.write_text(PRELUDE+'fn main(){'+body+'}')
 for front in FRONTS:
  p=run([*front,'check',source]);assert p.returncode==0,p
 # Independent finite-set model of every possible source in seeded selector
 # trees. Constant flags affect runtime choice, not the declared borrow union.
 model_cases=0
 for seed in (7,42,2026):
  rng=random.Random(seed)
  def expression(depth):
   if depth==0 or rng.randrange(3)==0:
    index=rng.randrange(5);return '&v'+str(index),{index}
   left,roots_left=expression(depth-1);right,roots_right=expression(depth-1)
   return 'choose('+rng.choice(['true','false'])+','+left+','+right+')',roots_left|roots_right
  for _ in range(12):
   expr,roots=expression(3)
   for target in range(6):
    source.write_text(PRELUDE+'fn main(){'+''.join(f'var v{i}={i};' for i in range(6))+'let result='+expr+';let child=project(result);'+f'v{target}=99;'+'}')
    for front in FRONTS:
     p=run([*front,'check',source]);expected=2 if target in roots else 0
     assert p.returncode==expected and (expected==0 or 'conflicts' in p.stderr),(seed,expr,roots,target,p)
    model_cases+=1
 print(f'reference root-set model: {model_cases} deterministic mutation queries on both frontends PASS')
print(f'reference sets: shared/exclusive union, nested reborrow, methods, duplicate collapse and temporary cleanup; five engines/O2; {len(NEGATIVE)+len(WHOLE)} rejections on both frontends PASS')
