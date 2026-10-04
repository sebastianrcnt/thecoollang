#!/usr/bin/env python3
"""Nominal methods, inferred receiver generics, visibility, ownership and loans."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
PRELUDE='''import "std/io";import "std/mem";
struct Point{x:i64;y:i64;items:[2]i64;}
fn Point.sum(self:&Point)->i64{return (*self).x+(*self).y;}
fn Point.copy_sum(self:Point)->i64{return self.x+self.y;}
fn Point.add(self:&mut Point,value:i64){(*self).x=(*self).x+value;}
fn Point.xref(self:&mut Point)->&mut i64 borrows(self){return &mut (*self).x;}
fn Point.shared(self:&Point)->&Point borrows(self){return self;}
fn Point.take(self:own[Point])->i64{return (*self).x;}
fn create(counter:&mut i64)->Point{*counter=*counter+1;return Point{x:3,y:4,items:[2]i64{8,9}};}
struct Box[T]{value:T;}
fn Box.get[T](self:&Box[T])->&T borrows(self){return &(*self).value;}
fn Box.replace[T](self:&mut Box[T],value:T){(*self).value=move value;}
fn Box.choose[T,U](self:&Box[T],value:U)->U{return move value;}
enum Flag{On;Off;}
fn Flag.enabled(self:Flag)->bool{match(self){Flag.On=>{return true;}Flag.Off=>{return false;}}}
'''
POSITIVE=PRELUDE+'''fn tests(){
 var point=Point{x:1,y:2,items:[2]i64{3,4}};point.add(4);assert(point.sum()==7);assert(point.items[1]==4);
 *point.xref()=8;assert(point.sum()==10);assert(point.shared().sum()==10);
 {let exclusive=&mut point;exclusive.add(1);assert(exclusive.sum()==11);assert(exclusive.copy_sum()==11);}
 let owner=new[Point](Point{x:42,y:1,items:[2]i64{}});assert(owner.sum()==43);assert(owner.copy_sum()==43);assert((move owner).take()==42);
 var calls=0;assert(create(&mut calls).copy_sum()==7);assert(calls==1);
 var box=Box[i64]{value:12};assert(*box.get()==12);box.replace(18);assert(*box.get()==18);assert(box.choose[u8](255)==255);
 var owned=Box[own[i64]]{value:new[i64](12)};owned.replace(new[i64](19));{let item=owned.get();assert(**item==19);}
 assert(Flag.On.enabled());assert(!Flag.Off.enabled());
}
fn main(){tests();assert(mem.owner_count()==0);io.println(42);}
'''
NEGATIVE=[
 (PRELUDE+'fn main(){let p=Point{};p.add(1);}','mutable place'),
 (PRELUDE+'fn main(){var p=Point{};let child=p.xref();p.add(1);}','conflicts'),
 (PRELUDE+'fn main(){let p=new[Point]();let child=p.shared();let moved=move p;}','conflicts'),
 (PRELUDE+'fn consume(value:own[Point])->i64{return 0;}fn main(){let p=new[Point]();p.add(consume(move p));}','conflicts'),
 (PRELUDE+'fn consume(value:own[Point])->i64{return 0;}fn main(){let p=new[Point]();*p.xref()=consume(move p);}','conflicts'),
 (PRELUDE+'fn main(){let p=new[Point]();p.take();}','explicit move'),
 (PRELUDE+'fn main(){let p=new[Point]();(move p).take();p.sum();}','moved value'),
 (PRELUDE+'fn main(){var p=Point{};p.absent();}','unknown method'),
 (PRELUDE+'fn main(){var p=Point{};p.add();}','wrong argument count'),
 (PRELUDE+'fn main(){let b=Box[i64]{};b.choose(1);}','generic argument count'),
 ('fn Missing.foo(self:i64){}fn main(){}','declared in this package'),
 ('struct P{}fn P.foo(){}fn main(){}','explicit first receiver'),
 ('struct P{}struct Q{}fn P.foo(self:Q){}fn main(){}','declared owner type'),
 ('struct P{x:i64;}fn P.x(self:&P){}fn main(){}','conflicts with a field'),
 ('enum E{Value;}fn E.Value(self:E){}fn main(){}','conflicts with a field'),
 ('struct P{}extern "C" fn P.foo(self:i64);fn main(){}','C ABI'),
 ('struct B[T]{}fn B.foo[U](self:&B[U]){}fn main(){}','receiver type parameters first'),
 ('struct P{}fn P.foo(self:&P){}fn P.foo(self:&P){}fn main(){}','duplicate function'),
 ('struct P{}fn P.borrow(self:&P)->&P borrows(self){let local=P{};return &local;}fn main(){}','outlive'),
]
LIBRARY='''import v "std/vector";import t "std/text";import m "std/map";import r "std/result";import o "std/option";import "std/mem";import "std/io";
fn text(value:string)->t.Text{return r.value_or[t.Text,t.Utf8Error](t.from_literal(value),t.create());}
fn tests(){
 var values=v.create[own[i64]]();values.append(new[i64](42));assert(values.len()==1);{let value=values.at(0);assert(**value==42);}
 let popped=o.value_or[own[i64]](values.pop(),new[i64](0));assert(*popped==42);values.clear();
 var word=text("한글");assert(word.scalar_len()==2);word.append_scalar(128578);assert(word.byte_len()==10);
 let clone=word.clone();assert(word.equal(&clone));assert(word.compare(&clone)==0);assert(word.as_bytes().len()==10);
 var map=m.create[t.Text]();map.insert(text("key"),move word);let key=text("key");assert(map.contains(&key));assert(map.at(&key).scalar_len()==3);
 map.at_mut(&key).append_literal("!");assert(map.at(&key).scalar_len()==4);assert(map.at_mut(&key).scalar_len()==4);
 let names=map.keys();assert(names.len()==1);map.remove(&key);map.clear();assert(map.len()==0);
}
fn main(){tests();assert(mem.owner_count()==0);io.println(42);}
'''
def run(args,**kw):return subprocess.run([str(x) for x in args],cwd=ROOT,capture_output=True,text=True,timeout=180,**kw)
with tempfile.TemporaryDirectory(prefix='cool-methods-') as tmp:
 directory=Path(tmp);source=directory/'main.cool';bootstrap=directory/'bootstrap'
 bootstrap.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');bootstrap.chmod(0o755)
 fronts=(ROOT/'build/cool-compiler',bootstrap)
 for program in (POSITIVE,LIBRARY):
  source.write_text(program)
  for front in fronts:
   p=run([ROOT/'tools/cool','check',source],env={**os.environ,'COOL_FRONTEND':str(front)});assert p.returncode==0,(p.stdout,p.stderr)
  for engine in ('tree','interp','jit','llvm','llvm-jit'):
   p=run([ROOT/'tools/cool','run','--backend',engine,source]);assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),(engine,p.stdout,p.stderr)
  binary=directory/'program';p=run([ROOT/'tools/cool','build','--release',source,'-o',binary]);assert p.returncode==0,p
  p=run([binary]);assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),p
  p=run([ROOT/'tools/cool','fmt',source]);assert p.returncode==0,p
  p=run([ROOT/'tools/cool','fmt','--check',source]);assert p.returncode==0,p
  p=run([ROOT/'tools/cool','check',source]);assert p.returncode==0,p
 for program,diagnostic in NEGATIVE:
  source.write_text(program)
  for front in fronts:
   p=run([ROOT/'tools/cool','check',source],env={**os.environ,'COOL_FRONTEND':str(front)});assert p.returncode==2 and diagnostic in p.stderr,(diagnostic,p.stdout,p.stderr,program)
 project=directory/'project';project.mkdir()
 p=subprocess.run([ROOT/'tools/cool','mod','init','example.com/methods'],cwd=project,text=True,capture_output=True);assert p.returncode==0,p
 for package,value in (('first',7),('second',19)):
  folder=project/package;folder.mkdir();(folder/'point.cool').write_text('package '+package+';pub struct Point{value:i64;}pub fn create()->Point{return Point{value:'+str(value)+'};}pub fn Point.read(self:&Point)->i64{return (*self).value;}fn Point.hidden(self:&Point)->i64{return 0;}')
 main=project/'main.cool';imports='import a "example.com/methods/first";import b "example.com/methods/second";import "std/io";'
 main.write_text(imports+'fn main(){let first=a.create();let second=b.create();assert(first.read()==7);assert(second.read()==19);io.println(42);}')
 for front in fronts:
  p=run([ROOT/'tools/cool','check',main],env={**os.environ,'COOL_FRONTEND':str(front)});assert p.returncode==0,p
 for engine in ('tree','interp','jit','llvm','llvm-jit'):
  p=run([ROOT/'tools/cool','run','--backend',engine,main]);assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),p
 p=run([ROOT/'tools/cool','doc',project/'first']);assert p.returncode==0 and 'pub fn Point.read(self: &Point) -> i64;' in p.stdout and 'hidden' not in p.stdout,p
 main.write_text(imports+'fn main(){let first=a.create();first.hidden();}')
 for front in fronts:
  p=run([ROOT/'tools/cool','check',main],env={**os.environ,'COOL_FRONTEND':str(front)});assert p.returncode==2 and 'method is private' in p.stderr,p
 # Compiled functions may use references/methods even while top-level persistent
 # REPL reference bindings remain explicitly unsupported.
 p=run([ROOT/'tools/cool','repl'],input='struct P{x:i64;}\nfn P.get(self:&P)->i64{return (*self).x;}\nfn use()->i64{let p=P{x:1};return p.get();}\nuse()\nfn P.get(self:&P)->i64{return (*self).x+1;}\nuse()\n:quit\n')
 assert p.returncode==0 and p.stdout=='1\n2\n' and not p.stderr,p
 print(f'methods: struct/enum/owned/generic receivers, explicit extra generics, safe collection methods, five engines/O2, formatting and {len(NEGATIVE)} rejections on both frontends PASS')
