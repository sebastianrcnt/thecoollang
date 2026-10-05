#!/usr/bin/env python3
"""Stored shared-reference loans survive copying, projection and return."""
from pathlib import Path
import subprocess
import tempfile
import random
import argparse
ROOT=Path(__file__).resolve().parents[1]
FRONTS=[[ROOT/'build/cool-compiler'],[ROOT/'build/coolc','--run',ROOT/'build/language.BIN']]
PRELUDE='''import "std/io";import "std/mem";
struct View {left:&i64;right:&i64;}
struct Box[T] {value:T;}
enum Maybe {None;Some(&i64);}
fn pair(a:&i64,b:&i64)->View borrows(a,b){return View{left:a,right:b};}
fn field(v:View)->&i64 borrows(v){return v.right;}
fn array(a:&i64,b:&i64)->[2]&i64 borrows(a,b){return [2]&i64{a,b};}
fn maybe(a:&i64)->Maybe borrows(a){return Maybe.Some(a);}
fn mutate(a:&mut i64)->Maybe borrows(a){*a=*a+1;return Maybe.Some(&*a);}
fn none()->Maybe borrows(){return Maybe.None;}
fn identity[T](x:T)->T borrows(x){return x;}
fn View.total(self:View)->i64{return *self.left+*self.right;}
fn View.get(self:View)->&i64 borrows(self){return self.right;}
fn view_read(v:View)->i64{return *v.left+*v.right;}
fn observe(v:View,n:i64){}
fn consume(x:own[i64])->i64{return *x;}
fn index(x:&mut i64)->usize{*x=*x+1;return 1;}
'''
POSITIVE=PRELUDE+'''fn tests(){
 var x=1;var y=2;
 {let v=pair(&x,&y);let c=v;assert(*field(c)==2);assert(view_read(c)==3);assert(c.total()==3);assert(*c.get()==2);
  assert(*pair(&x,&y).left==1);let arr=array(&x,&y);assert(*arr[1]==2);
  var count=0;assert(*array(&x,&y)[index(&mut count)]==2);assert(count==1);
  let box=Box[View]{value:v};let copied=identity[Box[View]](box);assert(*copied.value.right==2);
  let matrix=[2][2]&i64{arr,arr};assert(*matrix[1][0]==1);
  match(maybe(&x)){Maybe.None=>{}Maybe.Some(r)=>{assert(*r==1);}}
  let empty=none();let e=identity[Maybe](empty);match(e){Maybe.None=>{}Maybe.Some(r)=>{assert(false);}}
 }
 x=3;y=4;
 {match(mutate(&mut x)){Maybe.None=>{}Maybe.Some(r)=>{assert(*r==4);}}}assert(x==4);
 {let one=new[i64](11);let two=new[i64](22);{let view=pair(&*one,&*two);assert(view_read(view)==33);}let moved=move one;assert(*moved==11);}
 {var count=0;let arr=array(&x,&y);let r=arr[index(&mut count)];count=8;assert(*r==4 && count==8);}
 {var a=[2]i64{5,6};{let v=pair(&a[0],&a[1]);assert(view_read(v)==11);}a[0]=7;}
}
fn main(){tests();assert(mem.owner_count()==0);io.println(42);}
'''
INTEGRATION='import option "std/option";import "std/io";\nfn main(){var x=10;var y=20;{\n let some=option.Option[&i64].Some(&x);assert(option.is_some[&i64](some));\n let r=option.value_or[&i64](some,&y);assert(*r==10);\n let none=option.Option[&i64].None;assert(!option.is_some[&i64](none));\n let fallback=option.value_or[&i64](none,&y);assert(*fallback==20);\n}x=30;y=40;io.println(x+y);}\n'
NEGATIVE=[]
for name in ('x','y'):
 for expr in ('pair(&x,&y)','identity[View](pair(&x,&y))','Box[View]{value:pair(&x,&y)}','array(&x,&y)','[2]Maybe{maybe(&x),maybe(&y)}'):
  NEGATIVE.append((f'fn main(){{var x=1;var y=2;let stored={expr};{name}=3;}}','conflicts'))
 NEGATIVE.extend([
  (f'fn main(){{let x=new[i64](1);let y=new[i64](2);let stored=pair(&*x,&*y);let gone=move {name};}}','conflicts'),
  (f'fn main(){{let x=new[i64](1);let y=new[i64](2);observe(pair(&*x,&*y),consume(move {name}));}}','conflicts'),
  (f'fn main(){{var x=1;var y=2;let v=pair(&x,&y);let r=field(v);{name}=3;}}','conflicts'),
  (f'fn main(){{var x=1;var y=2;defer observe(pair(&x,&y),0);{name}=3;}}','conflicts'),
 ])
NEGATIVE += [
 ('fn main(){var x=1;match(mutate(&mut x)){Maybe.None=>{x=4;}Maybe.Some(r)=>{assert(*r==2);}}}', 'conflicts'),
 ('struct Mixed{r:&i64;count:i64;}fn bad(x:Mixed)->&i64 borrows(x){return &x.count;}fn main(){}','outlive'),
 ('struct Mixed{r:&i64;count:i64;}fn main(){var x=1;var s=Mixed{r:&x,count:2};let r=&s.count;s.count=3;}','conflicts'),
 ('fn bad(a:&i64)->View borrows(a){let x=1;return pair(a,&x);}fn main(){}','outlive'),
 ('fn bad(a:&i64,b:&i64)->View borrows(a){return pair(a,b);}fn main(){}','outlive'),
 ('fn bad()->Maybe borrows(){let x=1;return maybe(&x);}fn main(){}','outlive'),
 ('fn bad(a:&i64)->[2]&i64 borrows(a){let x=1;return array(a,&x);}fn main(){}','outlive'),
 ('fn main(){let v=View{};}','explicit initializer'),
 ('fn main(){let v=[2]&i64{};}','explicit initializer'),
 ('fn main(){let v=Box[View]{};}','explicit initializer'),
 ('fn main(){var x=1;var y=2;var v=pair(&x,&y);v=pair(&x,&y);}','cannot be reassigned'),
 ('fn main(){var x=1;var y=2;var v=pair(&x,&y);v.left=&y;}','cannot be reassigned'),
 ('fn main(){var x=1;var y=2;var a=array(&x,&y);a[0]=&y;}','cannot be reassigned'),
 ('fn main(){var x=1;var y=2;let v=pair(&x,&y);*v.left=3;}','immutable'),
 ('fn main(){var x=1;var y=2;let v=pair(&x,&y);let r=&mut *v.left;}','mutable place'),
 ('struct Bad{r:&mut &i64;}fn main(){}','aggregate storage'),
 ('struct Bad{r:&i64;bytes:&[]u8;}fn main(){}','aggregate storage'),
 ('struct Bad{r:&i64;p:own[&View];}fn main(){}','owned storage'),
 ('fn main(){var x=1;let v=pair(&x,&x);let p=new[&View](&v);}','owned storage'),
 ('fn main(){var x=1;let v=pair(&x,&x);let r=&v;x=2;}','conflicts'),
 ('fn main(){var x=1;var a=[2]&i64{&x,&x};let s=a[:];}','slice elements'),
 ('fn main(){var x=1;var y=2;let arr=array(&x,&y);let r=arr[index(&mut x)];}','conflicts'),
]
def run(command,**kwargs):
 return subprocess.run([str(x) for x in command],cwd=ROOT,text=True,capture_output=True,timeout=120,**kwargs)
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sanitize',action='store_true');args=parser.parse_args()
with tempfile.TemporaryDirectory(prefix='cool-stored-refs-') as tmp:
 source=Path(tmp)/'main.cool';source.write_text(POSITIVE)
 for front in FRONTS:
  p=run([*front,'check',source]);assert p.returncode==0,(p.stdout,p.stderr)
 for engine in ('tree','interp','jit','llvm','llvm-jit'):
  p=run([ROOT/'tools/cool','run','--backend',engine,source]);assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),(engine,p)
 binary=Path(tmp)/'native';p=run([ROOT/'tools/cool','build','--release',source,'-o',binary]);assert p.returncode==0,p
 p=run([binary]);assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),p
 if args.sanitize:
  ir=Path(tmp)/'stored.ll';instrumented=Path(tmp)/'stored-asan.ll'
  p=run([ROOT/'tools/cool','emit-ir',source,'-o',ir]);assert p.returncode==0,p
  ir.write_text('\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in ir.read_text().splitlines())+'\n')
  p=run(['clang','-Wno-override-module','-O1','-fsanitize=address','-S','-emit-llvm',ir,'-o',instrumented]);assert p.returncode==0,p
  assert '__asan_report_load' in instrumented.read_text(),'Cool loads were not instrumented'
  p=run(['clang','-Wno-override-module','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',ir,ROOT/'language/runtime.c','-o',binary]);assert p.returncode==0,p
  p=run([binary]);assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),p
  print('stored shared references: instrumented Cool ASan + C runtime ASan/UBSan PASS')
 for body,error in NEGATIVE:
  source.write_text(PRELUDE+body)
  for front in FRONTS:
   p=run([*front,'check',source]);assert p.returncode==2 and error in p.stderr,(body,error,p)
 # Independent root-set model across stored values and nested projections.
 queries=0
 for seed in (7,42,2026):
  rng=random.Random(seed)
  for _ in range(8):
   left,right=rng.randrange(5),rng.randrange(5);roots={left,right}
   base=f'pair(&v{left},&v{right})'
   cases=[(base,'stored.get()'),(f'Box[View]{{value:{base}}}','stored.value.left'),
          (f'[2]View{{{base},{base}}}','stored[1].right'),
          (f'identity[View]({base})','field(stored)')]
   expr,projection=rng.choice(cases)
   for target in range(6):
    body=''.join(f'var v{i}={i};' for i in range(6))+f'let stored={expr};let child={projection};v{target}=99;'
    source.write_text(PRELUDE+'fn main(){'+body+'}')
    for front in FRONTS:
     p=run([*front,'check',source]);expected=2 if target in roots else 0
     assert p.returncode==expected and (expected==0 or 'conflicts' in p.stderr),(seed,expr,target,roots,p)
    queries+=1
 print(f'stored root-set model: {queries} deterministic mutation queries on both frontends PASS')
 source.write_text(INTEGRATION)
 for engine in ('tree','interp','jit','llvm','llvm-jit'):
  p=run([ROOT/'tools/cool','run','--backend',engine,source]);assert (p.returncode,p.stdout,p.stderr)==(0,'70\n',''),(engine,p)
 print('stored shared references: imported std/option generic payloads and returned fallback loans, five engines PASS')
print(f'stored shared references: structures/arrays/enums/generics, copies, projections, contracts, owner lifetime; five engines/O2 and {len(NEGATIVE)} rejections on both frontends PASS')
