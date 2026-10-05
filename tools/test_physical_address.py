#!/usr/bin/env python3
"""Physical field separation must preserve prefix, array and owner protection."""
import argparse, hashlib, json, os, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path,default=ROOT/'build/cool-compiler');p.add_argument('--legacy',action='store_true');p.add_argument('--output',type=Path);args=p.parse_args()
frontend=args.frontend.resolve();env={**os.environ,'COOL_FRONTEND':str(frontend),'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
def run(cmd,**kw):return subprocess.run(list(map(str,cmd)),cwd=ROOT,env=env,text=True,capture_output=True,timeout=180,**kw)
PRELUDE='''import "std/io";
struct Point{x:i64;y:i64;}
struct Box{a:Point;b:Point;}
enum Choice{None;Some(i64);}
struct Heap{p:own[Point];q:own[Point];}
fn consume(p:own[Point])->i64{return (*p).y;}
fn replace(p:&mut own[Point])->i64{*p=new[Point](Point{x:3,y:4});return 5;}
fn bump(a:&mut i64,b:&mut i64){*a=10;*b=20;}
fn opaque(p:&mut i64)->&mut i64 borrows(p){return p;}
'''
POSITIVES=[
 'var p=Point{x:1,y:2};let r=&mut p;let x=&mut (*r).x;(*r).y=7;*x=9;assert((*r).y==7);assert(*x==9);',
 'var p=Point{x:1,y:2};let r=&mut p;let x=&mut (*r).x;let y=&mut (*r).y;*x=9;*y=7;assert(*x==9);assert(*y==7);',
 'var p=Point{x:1,y:2};let r=&mut p;let x=&(*r).x;(*r).y=7;assert(*x==1);',
 'var p=Point{x:1,y:2};let r=&p;let x=&(*r).x;assert((*r).y==2);assert(*x==1);',
 'var p=Point{x:1,y:2};let r=&mut p;bump(&mut (*r).x,&mut (*r).y);assert((*r).x==10);assert((*r).y==20);',
 'var b=Box{a:Point{x:1,y:2},b:Point{x:3,y:4}};let r=&mut b;let x=&mut (*r).a.x;(*r).a.y=7;(*r).b.x=8;*x=9;assert((*r).b.x==8);',
 'var b=Box{a:Point{x:1,y:2},b:Point{x:3,y:4}};var r=&mut b.a;r=&mut b.b;let x=&mut (*r).x;(*r).y=7;*x=9;assert((*r).y==7);',
 'var a=[2]Point{Point{x:1,y:2},Point{x:3,y:4}};let r=&mut a;let x=&mut (*r)[0].x;(*r)[1].y=7;*x=9;assert((*r)[1].y==7);',
 'var h=Heap{p:new[Point](Point{x:1,y:2}),q:new[Point](Point{x:3,y:4})};let x=&mut (*h.p).x;(*h.p).y=7;(*h.q).x=8;*x=9;assert((*h.q).x==8);',
 'var p=new[Point](Point{x:1,y:2});let x=&mut (*p).x;(*p).y=7;*x=9;assert((*p).y==7);',
 'var p=new[Point](Point{x:1,y:2});let x=&mut (*p).x;let y=&mut (*p).y;*x=9;*y=7;assert(*x==9);assert(*y==7);',
 'var p=new[Point](Point{x:1,y:2});let x=&(*p).x;(*p).y=7;assert(*x==1);',
 'var b=Box{a:Point{x:1,y:2},b:Point{x:3,y:4}};var owner=new[Box](move b);let x=&mut (*owner).a.x;(*owner).a.y=8;(*owner).b.x=9;*x=7;assert((*owner).b.x==9);',
 'var p=Point{x:1,y:2};let x=&mut p.x;p.y=7;*x=9;assert(p.y==7);assert(*x==9);',
 'var p=Point{x:1,y:2};let x=&mut p.x;let y=&mut p.y;*x=9;*y=7;assert(*x==9);assert(*y==7);',
 'var p=Point{x:1,y:2};let x=&p.x;p.y=7;assert(*x==1);assert(p.y==7);',
 'var p=Point{x:1,y:2};let x=&mut p.x;let y=&mut p.y;{let copy=x;*copy=9;}*y=7;assert(*x==9);',
 'var p=Point{x:1,y:2};bump(&mut p.x,&mut p.y);assert(p.x==10);assert(p.y==20);',
 'var p=Point{x:1,y:2};let x=&mut p.x;let y=&mut p.y;bump(x,y);assert(*x==10);assert(*y==20);',
 'var b=Box{a:Point{x:1,y:2},b:Point{x:3,y:4}};let x=&mut b.a.x;b.a.y=8;b.b.x=9;*x=7;assert(b.a.y==8);assert(b.b.x==9);',
 'var b=Box{a:Point{x:1,y:2},b:Point{x:3,y:4}};let a=&mut b.a;let c=&mut b.b;(*a).x=8;(*c).y=9;assert((*a).x==8);assert((*c).y==9);',
 'var a=[2]Point{Point{x:1,y:2},Point{x:3,y:4}};let x=&mut a[0].x;a[1].y=8;*x=9;assert(a[1].y==8);',
]
NEGATIVES=[
 'var p=Point{x:1,y:2};let r=&p;(*r).x=7;',
 'var p=new[Point](Point{x:1,y:2});let r=&mut *p;let x=&mut (*r).x;(*r).y=consume(move p);',
 'var p=Point{x:1,y:2};let r=&mut p;let x=&mut (*r).x;(*r).x=7;',
 'var p=Point{x:1,y:2};let r=&mut p;let x=&mut (*r).x;let read=(*r).x;',
 'var p=Point{x:1,y:2};let r=&mut p;let x=&mut (*r).x;let all=*r;',
 'var p=Point{x:1,y:2};let r=&mut p;let x=&mut (*r).x;let copy=r;',
 'var p=Point{x:1,y:2};var r=&mut p;let slot=&mut r;(*r).x=7;',
 'var b=Box{a:Point{x:1,y:2},b:Point{x:3,y:4}};var r=&mut b.a;r=&mut b.b;let x=&mut (*r).x;(*r).x=7;',
 'var a=[2]Point{Point{x:1,y:2},Point{x:3,y:4}};let r=&mut a;let x=&mut (*r)[0].x;(*r)[1].x=7;',
 'var p=new[Point](Point{x:1,y:2});let x=&mut (*p).x;(*p).y=consume(move p);',
 'var p=new[Point](Point{x:1,y:2});let x=&mut (*p).x;(*p).y=replace(&mut p);',
 'var h=Heap{p:new[Point](Point{x:1,y:2}),q:new[Point](Point{x:3,y:4})};let x=&mut (*h.p).x;h=Heap{p:new[Point](Point{x:5,y:6}),q:new[Point](Point{x:7,y:8})};',
 'var h=Heap{p:new[Point](Point{x:1,y:2}),q:new[Point](Point{x:3,y:4})};let x=&mut (*h.p).x;(*h.p).y=consume(move h.p);',
 'var p=new[Point](Point{x:1,y:2});let x=&mut (*p).x;(*p).x=3;',
 'var p=new[Point](Point{x:1,y:2});let x=&mut (*p).x;p=new[Point](Point{x:3,y:4});',
 'var p=new[Point](Point{x:1,y:2});let x=&mut (*p).x;let all=&mut *p;',
 'var p=new[Point](Point{x:1,y:2});let x=&mut (*p).x;let slot=&mut p;',
 'var p=Point{x:1,y:2};let anchor=&mut p.x;unsafe{let r=borrow_raw[&mut i64](cast[*i64](anchor),anchor);p.y=3;}',
 'var p=Point{x:1,y:2};var r=&mut p.x;r=&mut p.y;p.x=3;',
 'var p=Point{x:1,y:2};var r=&mut p.x;r=&mut p.y;p.y=3;',
 'var c=Choice.Some(1);let r=&mut c;c=Choice.None;',
 'var p=Point{x:1,y:2};let x=&mut p.x;p.x=3;',
 'var p=Point{x:1,y:2};let x=&mut p.x;let read=p.x;',
 'var p=Point{x:1,y:2};let x=&mut p.x;let y=&mut p.x;',
 'var p=Point{x:1,y:2};let x=&mut p.x;let all=&mut p;',
 'var p=Point{x:1,y:2};let x=&mut p.x;p=Point{x:3,y:4};',
 'var p=Point{x:1,y:2};let x=&mut p.x;let all=p;',
 'var a=[2]i64{1,2};let x=&mut a[0];a[1]=3;',
 'var a=[2]Point{Point{x:1,y:2},Point{x:3,y:4}};let x=&mut a[0].x;a[1].x=3;',
 'var p=new[Point](Point{x:1,y:2});let x=&mut (*p).x;let q=move p;',
 'var p=Point{x:1,y:2};let x=opaque(&mut p.x);p.y=3;',
 'var b=Box{a:Point{x:1,y:2},b:Point{x:3,y:4}};let x=&mut b.a.x;b.a=Point{x:3,y:4};',
]
fronts=[[frontend]]
if args.legacy:fronts.append([ROOT/'build/coolc','--run',ROOT/'build/language.BIN'])
with tempfile.TemporaryDirectory(prefix='cool physical address ') as directory:
 tmp=Path(directory);source=tmp/'main.cool';source.write_text(PRELUDE+'fn main(){'+''.join('{'+s+'}' for s in POSITIVES)+'io.println(42);}')
 for front in fronts:
  r=run([*front,'check',source]);assert r.returncode==0,r
 for engine in ('tree','interp','jit','llvm','llvm-jit'):
  r=run([ROOT/'tools/cool','run','--backend',engine,source]);assert (r.returncode,r.stdout,r.stderr)==(0,'42\n',''),(engine,r)
 binary=tmp/'native';r=run([ROOT/'tools/cool','build','--release',source,'-o',binary]);assert r.returncode==0,r
 r=run([binary]);assert (r.returncode,r.stdout,r.stderr)==(0,'42\n',''),r
 for body in NEGATIVES:
  source.write_text(PRELUDE+'fn main(){'+body+'}')
  for front in fronts:
   r=run([*front,'check',source]);diagnostics=('cannot assign through an immutable value',) if body=='var p=Point{x:1,y:2};let r=&p;(*r).x=7;' else ('conflicts','owner moved while an access','moved value','shared reference');assert r.returncode==2 and any(message in r.stderr for message in diagnostics),(body,r)
 repl='struct Point{x:i64;y:i64;}\nvar p=Point{x:1,y:2};\nlet x=&mut p.x;\nlet y=&mut p.y;\n*x=9;\n*y=7;\np.x=3;\n*x\n*y\n:forget x\np.x=11;\np.x\n:forget y\n:forget p\n:quit\n'
 for front in fronts:
  r=run([*front,'repl-quiet'],input=repl);assert r.returncode==0 and r.stdout=='9\n7\n11\n' and r.stderr.count('error:')==1,r
 owner_repl='struct Point{x:i64;y:i64;}\nvar p=new[Point](Point{x:1,y:2});\nlet x=&mut (*p).x;\nlet y=&mut (*p).y;\n*x=9;\n*y=7;\np=new[Point](Point{x:3,y:4});\n{*y=8;assert(false);}\n*x\n*y\n:forget x\n(*p).x=11;\n(*p).x\n:forget y\n:forget p\n:quit\n'
 for front in fronts:
  r=run([*front,'repl-quiet'],input=owner_repl);assert r.returncode==0 and r.stdout=='9\n8\n11\n' and r.stderr.count('error:')==2,r
 named_repl='struct Point{x:i64;y:i64;}\nvar p=Point{x:1,y:2};\nlet r=&mut p;\nlet x=&mut (*r).x;\nlet y=&mut (*r).y;\n*x=9;\n*y=7;\n(*r).x=3;\n{*y=8;assert(false);}\n*x\n*y\n:forget x\n(*r).x=11;\n(*r).x\n:forget y\n:forget r\n:forget p\n:quit\n'
 for front in fronts:
  r=run([*front,'repl-quiet'],input=named_repl);assert r.returncode==0 and r.stdout=='9\n8\n11\n' and r.stderr.count('error:')==2,r
 report={'frontend_sha256' :hashlib.sha256(frontend.read_bytes()).hexdigest(),'legacy_checked':args.legacy,'positive_cases':len(POSITIVES),'negative_cases':len(NEGATIVES),'engines':['tree','interp','jit','llvm','llvm-jit','native-O2'],'method':'Actual root-relative physical addresses: disjoint fields, named copies/call arguments, nested structs; owned payload field separation, conservative raw bridges and merged addresses; same-field/prefix/array/owner/opaque rejections and persistent REPL clone/recovery/forget.'}
 if args.output:args.output.write_text(json.dumps(report,indent=2)+'\n')
print(f'physical address: {len(POSITIVES)} accepted, {len(NEGATIVES)} rejected, five engines/O2 and persistent REPL PASS'+(' on both frontends' if args.legacy else ' on production frontend'))
