#!/usr/bin/env python3
"""Slices retain lexical provenance and reborrow safely with scoped references."""
from pathlib import Path
import subprocess
import tempfile
import argparse
import random
import os
import shlex
ROOT=Path(__file__).resolve().parents[1]
FRONTS=[[ROOT/'build/cool-compiler'],[ROOT/'build/coolc','--run',ROOT/'build/language.BIN']]
PRELUDE='''import "std/io";import "std/mem";
enum SliceOption{None;Some([]i64);}
struct View{data:[]i64;}
struct OwnedView{tag:own[i64];data:[]i64;}
fn first(s:[]i64)->&mut i64 borrows(s){return &mut s[0];}
fn read_first(s:[]i64)->&i64 borrows(s){return &s[0];}
fn tail(s:[]i64)->[]i64 borrows(s){return s[1:];}
fn view(p:&mut [3]i64)->[]i64 borrows(p){return (*p)[:];}
fn pick(a:[]i64,b:[]i64,first:bool)->[]i64 borrows(a,b){if(first){return a;}return b;}
fn wrap(s:[]i64)->View borrows(s){return View{data:s};}
fn extract(v:View)->[]i64 borrows(v){return v.data;}
fn consume(p:own[[3]i64])->i64{return 0;}
fn release(p:own[i64])->i64{return *p;}
'''
POSITIVE=PRELUDE+'''fn tests(){
 var a=[3]i64{1,2,3};var b=[3]i64{10,20,30};
 {var s=a[:];s[0]=4;{let r=&mut s[1];assert(len(s)==3);*r=5;}{let t=tail(s);t[0]=6;}s[2]=7;{let r=&mut tail(s)[0];*r=6;}}
 assert(a[0]==4 && a[1]==6 && a[2]==7);
 {let r=first(a[:]);*r=4;}{let r=read_first(a[:]);assert(*r==4);}
 {let r=&mut a[0];*r=8;}{let s=a[:];assert(s[0]==8);}
 {var s=[]i64{};{s=a[:];}s[0]=9;}
 assert(a[0]==9);
 {var s=a[:];s=s[1:];s[0]=11;}
 assert(a[1]==11);
 {var holder=View{data:[]i64{}};{holder.data=b[:];}holder.data[0]=12;}
 assert(b[0]==12);
 {let containers=[2][]i64{a[:],b[:]};{let s=containers[1];s[0]=12;}}
 {let option=SliceOption.Some(a[:]);match(option){SliceOption.None=>{assert(false);}SliceOption.Some(s)=>{s[0]=9;}}}
 {let v=OwnedView{tag:new[i64](1),data:b[:]};let moved=move v;moved.data[0]=14;}assert(b[0]==14);
 {let combined=pick(a[:],b[:],true);combined[0]=13;}
 assert(a[0]==13);
 assert(extract(wrap(a[:]))[1]==11);
 {var p=new[[3]i64]([3]i64{1,2,3});{let s=view(&mut *p);s[0]=21;{let r=&s[0];assert(*r==21);}}assert((*p)[0]==21);}
 {var p=new[[3]i64]([3]i64{1,2,3});{let s=(*p)[:];s[1]=22;}assert((*p)[1]==22);}
}
fn owners(){
 var items=[2]own[i64]{new[i64](10),new[i64](20)};
 {let s=items[:];*s[0]=*s[0]+1;let old=move s[1];s[1]=new[i64](*old+1);assert(mem.owner_count()==3);}
 assert(*items[0]==11 && *items[1]==21);
}
fn main(){tests();owners();assert(mem.owner_count()==0);io.println(42);}
'''
NEGATIVE=[
 'let containers=[2][]i64{a[:],b[:]};let s=containers[0];b[0]=2;',
 'let option=SliceOption.Some(a[:]);a[0]=2;',
 'let s=a[:];let r=first(s);s[0]=2;',
 'let s=a[:];let r=read_first(s);s[0]=2;',
 'let v=OwnedView{tag:new[i64](1),data:a[:]};let moved=move v;let r=&mut moved.data[0];moved.data[0]=2;',
 'var s=a[:];s=s[1:];let r=&s[0];s[0]=2;',
 'var s=a[:];{let t=s[1:];s=t;}let r=&s[0];s[0]=2;',
 'var s=[]i64{};if(true){s=a[:];}else{s=b[:];}b[0]=2;',
 'var s=[]i64{};for(var i=0;i<1;i=i+1){s=a[:];}a[0]=2;',
 'let s=a[:];a[0]=2;',
 'let s=a[:];let x=a[0];',
 'let s=a[:];let r=&a[0];',
 'let r=&a[0];let s=a[:];',
 'let s=a[:];let child=s;let x=s[0];',
 'let s=a[:];let r=&s[0];s[0]=2;',
 'let s=a[:];let r=&mut s[0];let x=s[0];',
 'let s=a[:];let r=&mut s[0];let t=s;',
 'var s=[]i64{};{s=a[:];}let r=&mut a[0];',
 'var v=View{data:[]i64{}};{v.data=a[:];}let r=&mut a[0];',
 'let s=pick(a[:],b[:],true);b[0]=2;',
]
WHOLE=[
 ('fn main(){var a=[2]own[i64]{new[i64](1),new[i64](2)};let s=a[:];*s[0]=release(move s[0]);}','conflicts'),
 ('fn main(){var a=[2]own[i64]{new[i64](1),new[i64](2)};let s=a[:];let gone=move a;}','conflicts'),
 ('fn main(){var p=new[[3]i64]([3]i64{1,2,3});let s=(*p)[:consume(move p)];}','conflicts|moved'),
 ('fn main(){var p=new[[3]i64]([3]i64{1,2,3});let s=view(&mut *p);consume(move p);let x=s[0];}','conflicts'),
 ('fn main(){var p=new[[3]i64]([3]i64{1,2,3});let s=(*p)[:];consume(move p);}','conflicts'),
 ('fn main(){var s=[]i64{};{var a=[3]i64{1,2,3};s=a[:];}let x=s[0];}','outlive'),
 ('fn main(){var v=View{data:[]i64{}};{var a=[3]i64{1,2,3};v.data=a[:];}}','outlive'),
 ('fn bad(p:&[3]i64)->[]i64 borrows(p){return (*p)[:];}fn main(){}','var array'),
 ('fn main(){var p=new[[3]i64]([3]i64{1,2,3});let s=(*p)[consume(move p):];}','conflicts|moved'),
]
def run(command,**kwargs):return subprocess.run([str(x) for x in command],cwd=ROOT,text=True,capture_output=True,timeout=120,**kwargs)
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sanitize',action='store_true');args=parser.parse_args()
with tempfile.TemporaryDirectory(prefix='cool-slice-loans-') as tmp:
 source=Path(tmp)/'main.cool';source.write_text(POSITIVE)
 for front in FRONTS:
  p=run([*front,'check',source]);assert p.returncode==0,p
 for engine in ('tree','interp','jit','llvm','llvm-jit'):
  p=run([ROOT/'tools/cool','run','--backend',engine,source]);assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),(engine,p)
 binary=Path(tmp)/'program';p=run([ROOT/'tools/cool','build','--release',source,'-o',binary]);assert p.returncode==0,p
 p=run([binary]);assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),p
 if args.sanitize:
  ir=Path(tmp)/'slice.ll';instrumented=Path(tmp)/'slice-asan.ll'
  p=run([ROOT/'tools/cool','emit-ir',source,'-o',ir]);assert p.returncode==0,p
  ir.write_text('\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in ir.read_text().splitlines())+'\n')
  p=run(['clang','-Wno-override-module','-O1','-fsanitize=address','-S','-emit-llvm',ir,'-o',instrumented]);assert p.returncode==0,p
  assert '__asan_report_load' in instrumented.read_text()
  p=run(['clang','-Wno-override-module','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',ir,ROOT/'language/runtime.c','-o',binary]);assert p.returncode==0,p
  p=run([binary]);assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),p
  print('slice loans: instrumented Cool ASan + C runtime ASan/UBSan PASS')
 for body,error in [(PRELUDE+'fn main(){var a=[3]i64{1,2,3};var b=[3]i64{4,5,6};'+body+'}','conflicts') for body in NEGATIVE]+[(PRELUDE+body,error) for body,error in WHOLE]:
  source.write_text(body)
  for front in FRONTS:
   p=run([*front,'check',source]);assert p.returncode==2 and any(word in p.stderr for word in error.split('|')),(body,error,p)
 queries=0
 for seed in (7,42,2026):
  rng=random.Random(seed)
  for _ in range(4):
   left,right=rng.sample(range(4),2)
   mode=rng.choice(('single','union','assignment'))
   roots={left} if mode=='single' else {left,right}
   held=f'let held=x{left}[:];'
   if mode=='union':held=f'let held=pick(x{left}[:],x{right}[:],true);'
   if mode=='assignment':held=f'var held=x{left}[:];{{held=x{right}[:];}}'
   for target in range(4):
    for writing in (False,True):
     access=f'x{target}[0]=99;' if writing else f'let n=x{target}[0];'
     source.write_text(PRELUDE+'fn main(){'+''.join(f'var x{i}=[3]i64{{1,2,3}};' for i in range(4))+held+access+'}')
     conflict=target in roots
     for front in FRONTS:
      p=run([*front,'check',source]);assert p.returncode==(2 if conflict else 0) and (not conflict or 'conflicts' in p.stderr),(seed,held,access,p)
     queries+=1
 print(f'slice loans: {queries} independent source-set queries on both frontends PASS')
 for front in FRONTS:
  p=run([*front,'repl-quiet'],input='var p=new[[3]i64]([3]i64{1,2,3});\nlet s=(*p)[:];\n(*p)[0]\nvar a=[1]own[i64]{new[i64](7)};\nlet s=a[:];\n*a[0]\n:quit\n')
  assert p.returncode==0 and p.stdout=='1\n7\n' and p.stderr.count('owned slices in REPL submissions require persistent loan tracking')==2,p
 print('slice loans: REPL rejects unsupported owned slices and preserves previous owners on both frontends PASS')
 source.write_text('import slice "std/slice";import "std/io";fn main(){var a=[4]i64{1,2,3,4};{let s=a[:];slice.reverse[i64](s);{let rest=slice.tail[i64](s);slice.fill[i64](rest,9);}assert(s[0]==4 && s[1]==9);{let first=slice.take[i64](s,1);first[0]=8;}}assert(a[0]==8 && a[3]==9);io.println(42);}')
 bootstrap=Path(tmp)/'bootstrap';bootstrap.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');bootstrap.chmod(0o755)
 for front in (ROOT/'build/cool-compiler',bootstrap):
  p=run([ROOT/'tools/cool','check',source],env={**os.environ,'COOL_FRONTEND':str(front)});assert p.returncode==0,p
 for engine in ('tree','interp','jit','llvm','llvm-jit'):
  p=run([ROOT/'tools/cool','run','--backend',engine,source]);assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),(engine,p)
 print('slice loans: imported std/slice reverse/fill/tail/take integration, both frontends and five engines PASS')
print(f'slice loans: references, reslicing, assignment, aggregates, return contracts and owned arrays; five engines/O2; {len(NEGATIVE)+len(WHOLE)} rejections on both frontends PASS')
