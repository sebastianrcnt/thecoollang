#!/usr/bin/env python3
"""Exclusive stored references reborrow without upgrading shared source roots."""
from pathlib import Path
import subprocess
import tempfile
import random
ROOT=Path(__file__).resolve().parents[1]
FRONTS=[[ROOT/'build/cool-compiler'],[ROOT/'build/coolc','--run',ROOT/'build/language.BIN']]
PRELUDE='''import "std/io";import "std/mem";
struct Mixed{read:&i64;write:&mut i64;index:i64;}
struct Box[T]{value:T;}
enum Maybe{None;Some(&mut i64);}
fn create(a:&i64,b:&mut i64)->Mixed borrows(a,b){return Mixed{read:a,write:b,index:0};}
fn field(v:Mixed)->&mut i64 borrows(v){return v.write;}
fn optional(v:&mut i64)->Maybe borrows(v){return Maybe.Some(v);}
fn identity[T](v:T)->T borrows(v){return v;}
fn Mixed.sum(self:&Mixed)->i64{return *(*self).read+*(*self).write;}
fn Mixed.bump(self:&mut Mixed){let target=(*self).write;*target=*target+1;}
fn consume(p:own[i64])->i64{return *p;}
fn share(v:&Mixed)->&Mixed borrows(v){return v;}
fn exclusive(v:&mut Mixed)->&mut Mixed borrows(v){return v;}
fn owner_shared(v:&own[i64])->&own[i64] borrows(v){return v;}
fn box_shared(v:&Box[&mut own[i64]])->&Box[&mut own[i64]] borrows(v){return v;}
'''
POSITIVE=PRELUDE+'''fn tests(){
 var a=1;var b=2;
 {var v=create(&a,&mut b);*v.write=3;assert(*v.read==1);assert(v.sum()==4);
  {let copy=v;*copy.write=4;}*v.write=5;
  {let r=field(v);*r=6;assert(a==1);}*v.write=7;
  {let r=&v;assert(*(*r).read==1);assert(*(*r).write==7);let shared=&*(*r).write;assert(*shared==7);}
  assert(*(*share(&v)).write==7);
  {let r=(*exclusive(&mut v)).write;*r=7;}
  v.bump();assert(v.sum()==9);
  {var box=Box[Mixed]{value:v};{let copy=identity[Box[Mixed]](box);*copy.value.write=9;}*box.value.write=10;}
  *v.write=11;
 }
 assert(b==11);
 {let values=[2]&mut i64{&mut a,&mut b};{let selected=values[1];*selected=12;}*values[0]=3;}
 assert(a==3 && b==12);
 {let option=optional(&mut a);match(option){Maybe.None=>{assert(false);}Maybe.Some(value)=>{*value=*value+1;}}}
 assert(a==4);
 {var owner=new[i64](10);assert(**owner_shared(&owner)==10);{let holders=Box[&mut own[i64]]{value:&mut owner};
  {let ref=holders.value;**ref=**ref+1;let old=move *ref;*ref=new[i64](*old+1);}
  assert(**holders.value==12);assert(**(*box_shared(&holders)).value==12);
 }assert(*owner==12);}
 {var x=1;var pointer=&mut x;{let ref=&mut pointer;**ref=2;}*pointer=3;}
}
fn main(){tests();assert(mem.owner_count()==0);io.println(42);}
'''
NEGATIVE=[
 ('let r=(*share(&v)).write;*r=3;','shared reference'),
 ('*(*share(&v)).write=3;','shared reference|immutable'),
 ('let copy=*share(&v);','shared reference'),
 ('let child=v;*v.write=3;','conflicts'),
 ('let child=v;let read=*v.write;','conflicts'),
 ('let child=v;let again=v;','conflicts'),
 ('let r=&v;*(*r).write=3;','immutable|shared reference|exclusive borrow'),
 ('let r=&v;let copy=(*r).write;','shared reference'),
 ('let r=&v;*v.write=3;','conflicts'),
 ('let r=&mut v;let child=(*r).write;(*r).write=&mut b;','conflicts'),
 ('let copy=identity[Mixed](v);*v.write=3;','conflicts'),
 ('let result=field(v);b=3;','conflicts'),
 ('let result=field(v);let n=b;','conflicts'),
 ('let result=field(v);a=3;','conflicts'),
 ('let result=field(v);let shared=&*result;*result=3;','conflicts'),
 ('let source=v.write;let sibling=v.write;','conflicts'),
 ('let shared=&*v.write;*v.write=3;','conflicts'),
 ('let exclusive=&mut *v.read;','mutable place'),
 ('let moved=move v;*v.write=3;','conflicts'),
]
WHOLE=[
 ('fn main(){var p=new[i64](1);**owner_shared(&p)=2;}','shared reference|immutable'),
 ('fn main(){var p=new[i64](1);let h=Box[&mut own[i64]]{value:&mut p};**(*box_shared(&h)).value=2;}','shared reference|immutable'),
 ('fn bad(a:&mut i64)->Maybe borrows(a){var b=1;return optional(&mut b);}fn main(){}','outlive'),
 ('fn bad(a:&i64,b:&mut i64)->Mixed borrows(a){return create(a,b);}fn main(){}','outlive'),
 ('fn main(){let v=[2]&mut i64{};}','explicit initializer'),
 ('fn main(){var x=1;let a=[2]&mut i64{&mut x,&mut x};}','conflicts'),
 ('fn main(){var a=1;let o=optional(&mut a);let c=o;match(o){Maybe.None=>{}Maybe.Some(r)=>{*r=2;}}}','conflicts'),
]
def run(command):return subprocess.run([str(x) for x in command],cwd=ROOT,text=True,capture_output=True,timeout=120)
SUPPORTED_NESTED = [
 'fn main(){var a=1;var b=2;let v=create(&a,&mut b);let h=new[&Mixed](&v);}',
]
with tempfile.TemporaryDirectory(prefix='cool-exclusive-storage-') as tmp:
 source=Path(tmp)/'main.cool';source.write_text(POSITIVE)
 for front in FRONTS:
  p=run([*front,'check',source]);assert p.returncode==0,p
 for engine in ('tree','interp','jit','llvm','llvm-jit'):
  p=run([ROOT/'tools/cool','run','--backend',engine,source]);assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),(engine,p)
 binary=Path(tmp)/'program';p=run([ROOT/'tools/cool','build','--release',source,'-o',binary]);assert p.returncode==0,p
 p=run([binary]);assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),p
 for body,error in [(PRELUDE+'fn main(){var a=1;var b=2;var v=create(&a,&mut b);'+body+'}',error) for body,error in NEGATIVE]+[(PRELUDE+body,error) for body,error in WHOLE]:
  source.write_text(body)
  for front in FRONTS:
   p=run([*front,'check',source]);assert p.returncode==2 and any(word in p.stderr for word in error.split('|')),(body,error,p)
 queries=0
 # A mixed container permits unrelated reads of its shared source, rejects reads
 # of its exclusive source, and forbids writes to both. Copying/returning it
 # must retain these distinct permissions instead of promoting every root.
 for seed in (7,42,2026):
  rng=random.Random(seed)
  for _ in range(8):
   read,write=rng.sample(range(4),2)
   wrapper=rng.choice(['{v}','identity[Mixed]({v})','Box[Mixed]{{value:{v}}}'])
   expr=wrapper.format(v=f'create(&x{read},&mut x{write})')
   for target in range(4):
    for writing in (False,True):
     mutation=f'x{target}=99;' if writing else f'let n=x{target};'
     source.write_text(PRELUDE+'fn main(){'+''.join(f'var x{i}={i};' for i in range(4))+'let held='+expr+';'+mutation+'}')
     conflict=target==write or (writing and target==read)
     for front in FRONTS:
      p=run([*front,'check',source]);assert p.returncode==(2 if conflict else 0) and (not conflict or 'conflicts' in p.stderr),(seed,expr,mutation,p)
     queries+=1
 print(f'exclusive storage: {queries} independent per-root read/write permission queries on both frontends PASS')
print(f'exclusive storage: mixed/generic/array/enum references, parent suspension/resumption, shared receivers and owning pointees; five engines/O2; {len(NEGATIVE)+len(WHOLE)} rejections on both frontends PASS')

with tempfile.TemporaryDirectory(prefix='cool-enabled-nested-') as enabled_tmp:
 enabled_source=Path(enabled_tmp)/'main.cool'
 for code in SUPPORTED_NESTED:
  enabled_source.write_text(PRELUDE+code if 'PRELUDE' in globals() else code)
  for front in FRONTS:
   result=run([*front,'check',enabled_source]);assert result.returncode==0,(code,result)
   result=run([*front,'run',enabled_source]);assert (result.returncode,result.stdout,result.stderr)==(0,'',''),(code,result)
print(f'nested storage: {len(SUPPORTED_NESTED)} former restrictions accepted and executed on both frontends PASS')
