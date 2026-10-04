#!/usr/bin/env python3
"""Safe vector iteration checks boundaries, ownership and retained source loans."""
from pathlib import Path
import argparse
import os
import shlex
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
IMPORTS='import v "std/vector";import o "std/option";import "std/io";import "std/mem";'
PROGRAM=IMPORTS+'''
fn integer_case(count:usize){
 var values=v.create[i64]();
 for(var i:usize=0;i<count;i=i+1){values.append(i64(i)*3-7);}
 let allocations=mem.owner_count();
 {var it=values.iter();var seen:usize=0;var sum:i64=0;
  while(it.remaining()>0){
   assert(it.remaining()==count-seen);
   match(it.next()){
    o.Option[&i64].None=>{assert(false);}
    o.Option[&i64].Some(value)=>{assert(*value==i64(seen)*3-7);sum=sum+*value;seen=seen+1;}
   }
  }
  assert(seen==count);assert(sum==i64(count)*i64(count-1)*3/2-i64(count)*7);
  for(var n=0;n<3;n=n+1){match(it.next()){o.Option[&i64].None=>{}o.Option[&i64].Some(value)=>{assert(false);}}}
  assert(it.remaining()==0);assert(mem.owner_count()==allocations);
 }
 values.append(42);assert(*values.at(count)==42);values.clear();assert(values.len()==0);
}
fn owner_case(){
 var values=v.create[own[i64]]();
 for(var i=0;i<97;i=i+1){values.append(new[i64](i));}
 let allocations=mem.owner_count();
 {var it=values.iter();var count=0;
  while(it.remaining()>0){match(it.next()){
   o.Option[&own[i64]].None=>{assert(false);}
   o.Option[&own[i64]].Some(value)=>{assert(**value==count);count=count+1;}
  }}assert(count==97);assert(mem.owner_count()==allocations);
 }
 {var it=v.iter[own[i64]](&values);while(it.remaining()>0){match(it.next()){
  o.Option[&own[i64]].None=>{assert(false);}
  o.Option[&own[i64]].Some(value)=>{assert(**value==0);break;}
 }}}
 values.clear();assert(values.len()==0);
}
fn independent_case(){
 var values=v.create[i64]();for(var i=0;i<65;i=i+1){values.append(i);}
 {var left=values.iter();var right=values.iter();let first=values.at(0);
  var seen=0;
  while(left.remaining()>0){
   match(left.next()){
    o.Option[&i64].None=>{assert(false);}
    o.Option[&i64].Some(a)=>{
     match(right.next()){
      o.Option[&i64].None=>{assert(false);}
      o.Option[&i64].Some(b)=>{assert(*a==seen && *b==seen);}
     }
     // Copying a read-only iterator copies its position, not its source.
     {var copied=left;assert(copied.remaining()==left.remaining());
      if(copied.remaining()>0){match(copied.next()){
       o.Option[&i64].None=>{assert(false);}
       o.Option[&i64].Some(c)=>{assert(*c==seen+1);}
      }}
     }
     assert(*first==0);seen=seen+1;
    }
   }
  }
  assert(seen==65 && right.remaining()==0);
 }
 values.clear();
}
fn main(){
'''+''.join(f'integer_case({n});assert(mem.owner_count()==0);' for n in (0,1,2,31,32,33,63,64,65,127,128,129))+'''
 owner_case();assert(mem.owner_count()==0);independent_case();assert(mem.owner_count()==0);io.println(42);
}
'''
# usize subtraction in the zero-length oracle must not underflow.
PROGRAM=PROGRAM.replace('i64(count-1)','(i64(count)-1)')
NEGATIVE=[
 ('var it=values.iter();values.clear();','conflicts'),
 ('var it=values.iter();values.append(2);','conflicts'),
 ('var it=values.iter();values.pop();','conflicts'),
 ('var it=values.iter();let moved=move values;','conflicts'),
 ('var it=values.iter();*values.at_mut(0)=2;','conflicts'),
 ('var it=values.iter();let item=it.next();it.next();','conflicts'),
 ('var it=values.iter();let item=it.next();values.clear();','conflicts'),
 ('var it=values.iter();match(it.next()){o.Option[&i64].None=>{}o.Option[&i64].Some(value)=>{*value=2;}}','immutable'),
 ('var it=values.iter();let r=&it;it.next();','conflicts'),
 ('var it=values.iter();it.position.remaining=0;','private'),
 ('let it=v.Iterator[i64]{};','private'),
]
WHOLE=[
 (IMPORTS+'fn bad()->v.Iterator[i64] borrows(){var values=v.create[i64]();return values.iter();}fn main(){}','outlive'),
 (IMPORTS+'fn bad(values:&v.Vector[i64])->&i64 borrows(values){var it=v.iter[i64](values);match(it.next()){o.Option[&i64].None=>{assert(false);return values.at(0);}o.Option[&i64].Some(value)=>{return value;}}}fn main(){}','outlive'),
 (IMPORTS+'fn main(){var values=v.create[own[i64]]();values.append(new[i64](1));var it=values.iter();match(it.next()){o.Option[&own[i64]].None=>{}o.Option[&own[i64]].Some(value)=>{let moved=move *value;}}}','shared reference'),
]
def run(args,**kwargs):return subprocess.run([str(x) for x in args],cwd=ROOT,text=True,capture_output=True,timeout=180,**kwargs)
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sanitize',action='store_true');args=parser.parse_args()
with tempfile.TemporaryDirectory(prefix='cool-tracked-iteration-') as tmp:
 directory=Path(tmp);source=directory/'main.cool';binary=directory/'program';bootstrap=directory/'bootstrap'
 bootstrap.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');bootstrap.chmod(0o755)
 fronts=(ROOT/'build/cool-compiler',bootstrap)
 source.write_text(PROGRAM)
 for front in fronts:
  p=run([ROOT/'tools/cool','check',source],env={**os.environ,'COOL_FRONTEND':str(front)});assert p.returncode==0,p
 for engine in ('tree','interp','jit','llvm','llvm-jit'):
  p=run([ROOT/'tools/cool','run','--backend',engine,source]);assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),(engine,p)
 p=run([ROOT/'tools/cool','build','--release',source,'-o',binary]);assert p.returncode==0,p
 p=run([binary]);assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),p
 if args.sanitize:
  ir=directory/'iteration.ll';instrumented=directory/'iteration-asan.ll'
  p=run([ROOT/'tools/cool','emit-ir',source,'-o',ir]);assert p.returncode==0,p
  ir.write_text('\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in ir.read_text().splitlines())+'\n')
  p=run(['clang','-Wno-override-module','-O1','-fsanitize=address','-S','-emit-llvm',ir,'-o',instrumented]);assert p.returncode==0,p
  assert '__asan_report_load' in instrumented.read_text()
  p=run(['clang','-Wno-override-module','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',ir,ROOT/'language/runtime.c','-o',binary]);assert p.returncode==0,p
  p=run([binary]);assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),p
  print('tracked iteration: instrumented Cool ASan + C runtime ASan/UBSan PASS')
 for body,error in [(IMPORTS+'fn main(){var values=v.create[i64]();values.append(1);'+body+'}',error) for body,error in NEGATIVE]+WHOLE:
  source.write_text(body)
  for front in fronts:
   p=run([ROOT/'tools/cool','check',source],env={**os.environ,'COOL_FRONTEND':str(front)});assert p.returncode==2 and error in p.stderr,(body,error,p)
 print(f'tracked iteration: 12 boundary sizes, owner elements, independent/copy iterators, retained shared elements, exhaustion, early break and allocation counts; five engines/O2; {len(NEGATIVE)+len(WHOLE)} rejections on both frontends PASS')
