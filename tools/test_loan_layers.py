#!/usr/bin/env python3
"""Independent storage roots and shared referent roots must not be conflated."""
from pathlib import Path
import subprocess
import tempfile
import random
ROOT=Path(__file__).resolve().parents[1]
FRONTS=[[ROOT/'build/cool-compiler'],[ROOT/'build/coolc','--run',ROOT/'build/language.BIN']]
PRELUDE='''import "std/io";
struct View{left:&i64;right:&i64;index:i64;}
fn create(a:&i64,b:&i64)->View borrows(a,b){return View{left:a,right:b,index:0};}
fn View.advance(self:&mut View){(*self).index=(*self).index+1;}
fn View.read(self:&View)->i64{return *(*self).left+*(*self).right+(*self).index;}
fn View.get(self:&View)->&i64 borrows(self){return (*self).right;}
fn identity(v:&mut View)->&mut View borrows(v){return v;}
fn both(a:&mut View,b:&mut View){(*a).index=(*a).index+1;(*b).index=(*b).index+1;}
'''
POSITIVE=PRELUDE+'''fn main(){
 var x=10;var y=20;
 {var a=create(&x,&y);var b=create(&x,&y);let data=&x;
  {let p=&mut a;let q=&mut b;(*p).index=1;(*q).index=2;assert(*data==10);
   let payload=(*p).left;(*p).index=3;assert(*payload==10);
   var copied=*p;copied.advance();assert(copied.index==4);(*p).index=5;
  }
  both(&mut a,&mut b);assert(a.index==6 && b.index==3);
  {let p=identity(&mut a);(*p).index=8;b.advance();(*p).index=6;b.index=3;}
  {var copied=*(&a);copied.advance();a.index=8;assert(copied.index==7);a.index=6;}
  {let payload=(*(&a)).left;a.index=8;assert(*payload==10);a.index=6;}
  {let field=&a.index;b.advance();assert(*field==6);}
  {let result=a.get();b.advance();assert(*result==20);}
  {let p=&mut a;{let field=&(*p).index;b.advance();assert(*field==6);}(*p).index=7;}
  {let r=&x;let q=&r;assert(**q==10);}
  {var r=&x;let q=&mut r;assert(**q==10);}
 }
 x=30;y=40;io.println(42);
}
'''
NEGATIVE=[
 ('let p=&mut a;a.index=3;','conflicts'),
 ('let p=&a;a.advance();','conflicts'),
 ('let p=&mut a;let copied=a;','conflicts'),
 ('let field=&a.index;a.index=3;','conflicts'),
 ('let p=&mut a;let field=&(*p).index;(*p).index=3;','conflicts'),
 ('let p=&mut a;let payload=(*p).left;x=30;','conflicts'),
 ('let p=&mut a;let payload=(*p).right;y=30;','conflicts'),
 ('let p=&mut a;*(*p).left=3;','immutable'),
 ('let p=&mut a;{var z=3;(*p).left=&z;}','outlive'),
 ('let p=&a;let q=&mut a;','conflicts'),
 ('let r=&x;let q=&r;let p=&mut r;','mutable place'),
 ('var r=&x;let q=&r;let p=&mut r;','conflicts'),
 ('var r=&x;let q=&mut r;let z=r;','conflicts'),
 ('var r=&x;let q=&mut r;let z=*r;','conflicts'),
]
def run(command):return subprocess.run([str(x) for x in command],cwd=ROOT,text=True,capture_output=True,timeout=120)
with tempfile.TemporaryDirectory(prefix='cool-loan-layers-') as tmp:
 source=Path(tmp)/'main.cool';source.write_text(POSITIVE)
 for front in FRONTS:
  p=run([*front,'check',source]);assert p.returncode==0,p
 for engine in ('tree','interp','jit','llvm','llvm-jit'):
  p=run([ROOT/'tools/cool','run','--backend',engine,source]);assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),(engine,p)
 binary=Path(tmp)/'program';p=run([ROOT/'tools/cool','build','--release',source,'-o',binary]);assert p.returncode==0,p
 p=run([binary]);assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),p
 for body,error in NEGATIVE:
  source.write_text(PRELUDE+'fn main(){var x=10;var y=20;var a=create(&x,&y);var b=create(&x,&y);'+body+'}')
  for front in FRONTS:
   p=run([*front,'check',source]);assert p.returncode==2 and error in p.stderr,(body,error,p)
 queries=0
 # Two independent container cells may share an arbitrary subset of referents.
 # All stored shared references freeze their referents. A receiver freezes only
 # its own container cell; it does not freeze a sibling cell sharing referents.
 for seed in (7,42,2026):
  rng=random.Random(seed)
  for _ in range(8):
   indices=[rng.randrange(3) for _ in range(4)];roots=set(indices)
   setup=''.join(f'var x{i}={i};' for i in range(3))+f'var a=create(&x{indices[0]},&x{indices[1]});var b=create(&x{indices[2]},&x{indices[3]});'
   setup+='let receiver='+rng.choice(['&a','&mut a'])+';'
   cases=[(f'x{i}=99;',i in roots) for i in range(3)]+[('a.advance();',True),('b.advance();',False)]
   for mutation,conflict in cases:
    source.write_text(PRELUDE+'fn main(){'+setup+mutation+'}')
    for front in FRONTS:
     p=run([*front,'check',source]);expected=2 if conflict else 0
     assert p.returncode==expected and (not conflict or 'conflicts' in p.stderr),(seed,indices,setup,mutation,p)
    queries+=1
 print(f'loan layers: {queries} independent storage/referent model queries on both frontends PASS')
print(f'loan layers: independent/copy receivers, payload extraction, scalar projections and reference slots; five engines/O2; {len(NEGATIVE)} rejections on both frontends PASS')
