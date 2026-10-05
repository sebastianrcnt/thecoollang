#!/usr/bin/env python3
"""Borrowing shared-reference containers retains every source and lexical loan."""
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
FRONTS=[[ROOT/'build/cool-compiler'],[ROOT/'build/coolc','--run',ROOT/'build/language.BIN']]
PRELUDE='''import "std/io";
struct View {left:&i64;right:&i64;index:i64;}
fn create(a:&i64,b:&i64)->View borrows(a,b){return View{left:a,right:b,index:0};}
fn View.read(self:&View)->i64{return *(*self).left+*(*self).right+(*self).index;}
fn View.advance(self:&mut View){(*self).index=(*self).index+1;}
fn View.get(self:&View)->&i64 borrows(self){return (*self).right;}
fn shared(v:&mut View)->&View borrows(v){return &*v;}
fn exclusive(v:&mut View)->&mut View borrows(v){return v;}
fn array_get(v:&[2]&i64,index:usize)->&i64 borrows(v){return (*v)[index];}
fn observe(v:&View,n:i64){}
fn consume(p:own[i64])->i64{return *p;}
'''
POSITIVE=PRELUDE+'''fn main(){
 var a=1;var b=2;
 {var v=create(&a,&b);assert(v.read()==3);v.advance();assert(v.read()==4);
  {let p=&mut v;(*p).index=2;{let q=&*p;assert((*q).read()==5);}(*p).index=3;}
  assert(v.read()==6);{let q=shared(&mut v);assert((*q).read()==6);}
  (*exclusive(&mut v)).index=4;assert(v.read()==7);
  {let r=v.get();assert(*r==2);}v.advance();assert(v.read()==8);
 }
 a=3;b=4;
 {let array=[2]&i64{&a,&b};let p=&array;assert(*array_get(p,1)==4);}
 {let p=&a;let q=&p;assert(**q==3);}
 {let owner=new[i64](9);{var v=create(&*owner,&b);v.advance();assert(v.read()==14);}let moved=move owner;assert(*moved==9);}
 io.println(42);
}
'''
NEGATIVE=[]
for root in ('a','b'):
 NEGATIVE += [
  (f'fn main(){{var a=1;var b=2;var v=create(&a,&b);let r=&v;{root}=3;}}','conflicts'),
  (f'fn main(){{var a=1;var b=2;var v=create(&a,&b);let r=&mut v;{root}=3;}}','conflicts'),
  (f'fn main(){{let a=new[i64](1);let b=new[i64](2);var v=create(&*a,&*b);let r=&v;let gone=move {root};}}','conflicts'),
  (f'fn main(){{let a=new[i64](1);let b=new[i64](2);var v=create(&*a,&*b);observe(&v,consume(move {root}));}}','conflicts'),
 ]
NEGATIVE += [
 ('fn main(){var a=1;var b=2;var v=create(&a,&b);let r=&v;v.advance();}','conflicts'),
 ('fn main(){var a=1;var b=2;var v=create(&a,&b);let r=&mut v;let value=v.read();}','conflicts'),
 ('fn main(){var a=1;var b=2;var v=create(&a,&b);let r=v.get();v.advance();}','conflicts'),
 ('fn main(){var a=1;var b=2;var v=create(&a,&b);let r=&v;(*r).index=3;}','immutable'),
 ('fn main(){var a=1;var b=2;var v=create(&a,&b);let r=&mut v;*(*r).left=3;}','immutable'),
 ('fn main(){var a=1;var b=2;var v=create(&a,&b);let r=&mut v;{var z=3;(*r).left=&z;}}','outlive'),
 ('fn main(){var a=1;var b=2;var v=create(&a,&b);let r=&mut v;{var z=3;*r=create(&a,&z);}}','outlive'),
 ('fn bad(a:&i64,b:&i64)->&View borrows(a,b){let v=create(a,b);return &v;}fn main(){}','outlive'),
 ('fn bad(v:View)->&View borrows(v){return &v;}fn main(){}','outlive'),
 ('fn bad(a:&i64,b:&i64)->&i64 borrows(a,b){let v=create(a,b);return v.get();}fn main(){}','outlive'),
 ('fn bad(v:&View)->&mut View borrows(v){return &mut *v;}fn main(){}','mutable place'),
 ('fn bad(v:&[][]i64){}fn main(){}','nested borrowed'),
 ('fn main(){var a=[2]i64{1,2};var s=a[:];let p=&s;let q=&p;}','nested borrowed'),
 ('fn bad(p:&mut &mut &mut i64){}fn main(){}','nested borrowed'),
]
def run(args):return subprocess.run([str(x) for x in args],cwd=ROOT,text=True,capture_output=True,timeout=120)
with tempfile.TemporaryDirectory(prefix='cool-nested-refs-') as tmp:
 source=Path(tmp)/'main.cool';source.write_text(POSITIVE)
 for front in FRONTS:
  p=run([*front,'check',source]);assert p.returncode==0,p
 for engine in ('tree','interp','jit','llvm','llvm-jit'):
  p=run([ROOT/'tools/cool','run','--backend',engine,source]);assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),(engine,p)
 binary=Path(tmp)/'program';p=run([ROOT/'tools/cool','build','--release',source,'-o',binary]);assert p.returncode==0,p
 p=run([binary]);assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),p
 for body,error in NEGATIVE:
  source.write_text(PRELUDE+body)
  for front in FRONTS:
   p=run([*front,'check',source]);assert p.returncode==2 and error in p.stderr,(body,error,p)
print(f'nested shared storage: receiver mutation, reborrows, arrays, owners and scope release; five engines/O2 and {len(NEGATIVE)} rejections on both frontends PASS')
