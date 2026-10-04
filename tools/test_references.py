#!/usr/bin/env python3
"""Scoped-reference semantics, exclusivity, lifetime and temporary-loan checks."""
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
FRONTS=[[ROOT/'build/cool-compiler'],[ROOT/'build/coolc','--run',ROOT/'build/language.BIN']]
POSITIVE='''import "std/io"; import "std/mem";
struct Pair { value:i64; }
fn plus(x:&mut i64){*x=*x+1;}
fn read(x:&i64)->i64{return *x;}
fn identity(x:&i64)->&i64 borrows(x){return x;}
fn identity_mut(x:&mut i64)->&mut i64 borrows(x){return x;}
fn second(x:&i64,y:&i64)->&i64 borrows(y){return y;}
fn field(x:&mut Pair)->&mut i64 borrows(x){return &mut (*x).value;}
fn later(x:&mut i64){*x=90;}
fn bridge(x:&mut i64)->&mut i64 borrows(x){unsafe{return borrow_raw[&mut i64](cast[*i64](x),x);}}
fn bridge_read(x:&i64)->&i64 borrows(x){unsafe{return borrow_raw[&i64](cast[*i64](x),x);}}
fn swap[T](left:&mut T,right:&mut T){let old=move *left;*left=move *right;*right=move old;}
fn main(){
 assert(sizeof(&i64)==8);assert(sizeof(&mut Pair)==8);
 var x=40;
 {let r=&mut x;plus(r);assert(*r==41);plus(r);}
 {let a=&x;let b=&x;assert(read(a)+read(b)==84);}
 {let r=identity(&x);assert(*r==42);}
 {let r=bridge(&mut x);*r=43;}
 {let r=bridge_read(&x);assert(*r==43);}
 {let r=&mut x;{let child=&mut *r;*child=44;}*r=45;}
 {let r=&mut x;{let child=&*r;assert(*child==45);assert(*r==45);}*r=46;}
 {let r=&mut x;let alias=r;*alias=47;}
 assert(x==47);
 {let r=identity(identity(identity(&x)));assert(*r==47);}
 {let r=identity_mut(identity_mut(&mut x));*r=48;}assert(x==48);x=47;
 {var first=1;var last=2;let selected=second(identity(&first),identity(&last));first=9;assert(*selected==2);}
 {let anchor=&mut x;{let child=identity_mut(identity_mut(anchor));*child=49;}*anchor=47;}
 {let r=identity(bridge_read(identity(&x)));assert(*r==47);}
 var pair=Pair{value:3};{let r=field(&mut pair);*r=7;}assert(pair.value==7);
 let p=new[i64](10);{let r=&mut *p;*r=11;}assert(*p==11);
 {let r=&*p;assert(*r==11);}let q=move p;assert(*q==11);
 var array=[2]i64{4,5};{let r=&mut array[1];*r=8;}assert(array[1]==8);
 for(var i=0;i<5;i=i+1){plus(&mut x);}assert(x==52);
 {defer later(&mut x);}assert(x==90);
 let immutable=12;{let r=&immutable;assert(read(r)==12);}
 {var left=new[i64](21);var right=new[i64](22);
  swap[own[i64]](&mut left,&mut right);assert(*left==22);assert(*right==21);
  assert(mem.owner_count()==3);
 }
 assert(mem.owner_count()==1);
 io.println(x);io.println(*q);
}
'''
NEGATIVE=[
 ('var x=1;let r=&x;*r=2;', 'immutable'),
 ('let x=1;let r=&mut x;', 'mutable place'),
 ('var x=1;let r=&mut x;let s=&mut x;', 'conflicts'),
 ('var x=1;let r=&x;let s=&mut x;', 'conflicts'),
 ('var x=1;let r=&mut x;let y=x;', 'conflicts'),
 ('var x=1;let r=&x;x=2;', 'conflicts'),
 ('let p=new[i64](1);let r=&*p;let q=move p;', 'conflicts'),
 ('var p=new[i64](1);let r=&*p;p=new[i64](2);', 'conflicts'),
 ('let p=new[i64](1);let r=&p;let q=move *r;', 'shared reference'),
 ('var x=1;let r=&mut x;let s=r;*r=2;', 'conflicts'),
 ('var x=1;let r=&mut x;let s=&mut *r;let y=*r;', 'conflicts'),
 ('var x=1;let r=&mut x;let s=&*r;*r=2;', 'conflicts'),
 ('var x=1;let r=&x;var y=2;r=&y;', 'let binding'),
 ('var x=1;var r=&mut x;var y=2;r=&mut y;', 'cannot be reassigned'),
 ('var x=1;defer set(&mut x);x=2;', 'conflicts'),
 ('var x=1;both(&mut x,&mut x);', 'conflicts'),
 ('let p=new[i64](1);*(&mut *p)=consume(move p);', 'conflicts'),
 ('let p=new[i64](1);*identity(&mut *p)=consume(move p);', 'conflicts'),
 ('var x=1;let anchor=&mut x;unsafe{let p=cast[*i64](anchor);let r=identity(borrow_raw[&mut i64](p,anchor));*anchor=2;}', 'conflicts'),
 ('let p=new[i64](1);observe(&*p,consume(move p));', 'conflicts'),
 ('var x=1;both(&mut x,identity(&mut x));', 'conflicts'),
 ('var x=1;let r=identity(identity(&mut x));x=2;', 'conflicts'),
 ('var x=1;let parent=&mut x;let r=identity(identity(parent));*parent=2;', 'conflicts'),
 ('var x=1;both(identity(identity(&mut x)),&mut x);', 'conflicts'),
 ('let p=new[i64](1);*identity(identity(&mut *p))=consume(move p);', 'conflicts'),
 ('let p=new[i64](1);hold(identity(identity(&mut *p)),consume(move p));', 'conflicts'),
 ('var x=1;defer set(identity(identity(&mut x)));x=2;', 'conflicts'),
 ('var a=[2]i64{1,2};let s=a[:];let r=&mut a[0];', 'conflicts'),
 ('var a=[2]i64{1,2};let s=a[:];let r=&mut s[0];s[0]=3;', 'conflicts'),
 ('var a=[2]i64{1,2};let r=&mut a[0];let s=a[:];', 'conflicts'),
 ('var x=1;let r=&mut x;unsafe{let p=&raw x;}', 'conflicts'),
]
WHOLE_NEGATIVE=[
 ('fn f(x:&i64){let p=cast[*i64](x);}fn main(){}','require unsafe'),
 ('fn f(x:&i64){unsafe{let p=cast[*u8](x);}}fn main(){}','element type mismatch'),
 ('fn f(x:&i64){let r=borrow_raw[&i64](null,x);}fn main(){}','requires unsafe'),
 ('fn f(x:&i64){unsafe{let r=borrow_raw[&mut i64](cast[*i64](x),x);}}fn main(){}','exclusive anchor'),
 ('fn f(x:&i64){unsafe{let r=borrow_raw[&i64](cast[*u8](0),x);}}fn main(){}','element type mismatch'),
 ('fn f(x:&i64){unsafe{let r=borrow_raw[&i64](cast[*i64](x),&1);}}fn main(){}','stable place'),
 ('fn f(x:&i64){unsafe{let r=borrow_raw[i64](cast[*i64](x),x);}}fn main(){}','reference result'),

 ('fn bad()->&i64 borrows() {let x=1;return &x;}fn main(){}', 'outlive'),
 ('fn bad(x:&i64)->&i64 borrows(x){let y=1;return &y;}fn main(){}', 'outlive'),
 ('fn id(x:&i64)->&i64 borrows(x){return x;}fn bad(x:&i64)->&i64 borrows(x){let y=1;return id(id(&y));}fn main(){}', 'outlive'),
 ('struct S{r:&mut &i64;}fn main(){}', 'aggregate storage'),
 ('fn f(x:&[]i64){}fn main(){}', 'nested borrowed'),
 ('fn main(){var x=1;let p=new[&i64](&x);}', 'owned storage'),
]
PRELUDE='fn consume(p:own[i64])->i64{return 0;}fn observe(p:&i64,n:i64){}fn hold(p:&mut i64,n:i64){}fn set(x:&mut i64){*x=1;}fn both(x:&mut i64,y:&mut i64){}fn identity(x:&mut i64)->&mut i64 borrows(x){return x;} '


def run(args,**kwargs):
 return subprocess.run([str(x) for x in args],cwd=ROOT,capture_output=True,text=True,timeout=90,**kwargs)


with tempfile.TemporaryDirectory(prefix='cool-references-') as tmp:
 path=Path(tmp)/'main.cool';path.write_text(POSITIVE)
 for front in FRONTS:
  result=run([*front,'check',path]);assert result.returncode==0,result
 for engine in ('tree','interp','jit','llvm','llvm-jit'):
  result=run([ROOT/'tools/cool','run','--backend',engine,path]);assert (result.returncode,result.stdout,result.stderr)==(0,'90\n11\n',''),(engine,result)
 binary=Path(tmp)/'program';result=run([ROOT/'tools/cool','build','--release',path,'-o',binary]);assert result.returncode==0,result
 result=run([binary]);assert (result.returncode,result.stdout,result.stderr)==(0,'90\n11\n',''),result
 for program,diagnostic in [(PRELUDE+'fn main(){'+body+'}',d) for body,d in NEGATIVE]+WHOLE_NEGATIVE:
  path.write_text(program)
  for front in FRONTS:
   result=run([*front,'check',path]);assert result.returncode==2 and diagnostic in result.stderr,(program,front,result)
 path.write_text(POSITIVE)
 result=run([ROOT/'tools/cool','fmt',path]);assert result.returncode==0,result
 result=run([ROOT/'tools/cool','fmt','--check',path]);assert result.returncode==0,result
 result=run([ROOT/'tools/cool','check',path]);assert result.returncode==0,result
 result=run([ROOT/'tools/cool','repl'],input='var x=1;\nlet r=&mut x;\nx=2;\nx\n:quit\n')
 assert result.returncode==0 and result.stdout=='2\n' and 'persistent loan tracking' in result.stderr,result
print(f'references: shared/exclusive/reborrow/return/defer on five engines + O2; {len(NEGATIVE)+len(WHOLE_NEGATIVE)} rejection cases on both frontends; formatter and REPL rollback PASS')
