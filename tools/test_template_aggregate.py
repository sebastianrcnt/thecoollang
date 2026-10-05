#!/usr/bin/env python3
"""Unused nominal template preflight, concrete execution and REPL rollback."""
import argparse, os, shlex, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);args=p.parse_args()
invalid=[
 ('struct Bad[T]{value:Missing;}','unknown type'),
 ('struct Bad[T]{value:T;value:i64;}','duplicate field'),
 ('struct Bad[T]{value:void;}','field cannot be void'),
 ('struct Bad[T]{value:own[void];}','invalid element'),
 ('struct Bad[T]{value:&void;}','invalid element'),
 ('struct Bad[T]{value:[]void;}','invalid element'),
 ('struct Bad[T]{value:[2]void;}','invalid element'),
 ('struct Bad[T]{value:[65537]T;}','array length'),
 ('struct Bad[T]{value:[18446744073709551615]T;}','array length'),
 ('struct Bad[T]{value:[-1]T;}','integer literal'),
 ('struct Bad[T]{value:[1+1]T;}','expected'),
 ('struct Bad[T]{value:T[i64];}','wrong generic'),
 ('struct Bad[T]{value:i64[T];}','wrong generic'),
 ('struct Bad[T]{value:G;}','wrong generic'),
 ('struct Bad[T]{value:G[T,T];}','wrong generic'),
 ('struct Bad[T]{value:G[void];}','cannot be void'),
 ('struct Bad[T]{value:T}','expected'),
 ('struct Bad[T]{value T;}','expected'),
 ('struct Bad[T]{pub pub value:T;}','expected'),
 ('struct Bad[T]{value:;}','expected'),
 ('struct Bad[T]{value:(T);}','expected'),
 ('struct Bad[T]{value:own[T;]}','expected'),
 ('struct Bad[T]{value:&mut;}','expected'),
 ('enum Bad[T]{}','enum must'),
 ('enum Bad[T]{Value(T);Value(i64);}','duplicate field'),
 ('enum Bad[T]{Value(Missing);}','unknown type'),
 ('enum Bad[T]{Value(G);}','wrong generic'),
 ('enum Bad[T]{Value([65537]T);}','array length'),
 ('enum Bad[T]{Value(T,T);}','expected'),
 ('enum Bad[T]{Value();}','expected'),
 ('enum Bad[T]{Value(T)}','expected'),
 ('enum Bad[T]{Value:T;}','expected'),
 ('enum Bad[T]{Value(own[void]);}','invalid element'),
 ('enum Bad[T]{pub pub Value(T);}','expected'),
]
program='''
import "std/io";
struct G[T]{value:T;}
struct Forward[T]{pub pair:Pair[T];pub ptr:*Forward[T];}
struct Pair[T]{pub left:T;pub right:T;}
struct Shadow[void]{value:void;}
struct Zero[T]{value:[0]T;}
enum Choice[T]{None;Value(T);Void(void);}
fn main(){
 let f=Forward[i32]{pair:Pair[i32]{left:7,right:9},ptr:null};
 assert(f.pair.left+f.pair.right==16);
 let e=Choice[i64].Value(42);
 match(e){Choice[i64].None=>{assert(false);}Choice[i64].Value(x)=>{io.println(x);}Choice[i64].Void=>{assert(false);}}
 let shadow=Shadow[i64]{value:5};assert(shadow.value==5);
 let zero=Zero[i64]{};assert(len(zero.value)==0);
}
'''
def run(command,env,input=None):
 return subprocess.run(list(map(str,command)),cwd=ROOT,env=env,input=input,capture_output=True,text=True,timeout=180)
with tempfile.TemporaryDirectory(prefix='cool template aggregate ') as temporary:
 root=Path(temporary);source=root/'main.cool';binary=root/'program';wrapper=root/'bootstrap'
 wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');wrapper.chmod(0o755)
 fronts=[ROOT/'build/cool-compiler',wrapper]
 if args.frontend:fronts.append(args.frontend.resolve())
 for front in fronts:
  env={**os.environ,'COOL_FRONTEND':str(front),'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
  source.write_text(program)
  for engine in ('tree','interp','jit','llvm','llvm-jit','O2'):
   if engine=='O2':
    r=run([ROOT/'tools/cool','build','--release',source,'-o',binary],env);assert r.returncode==0,r
    r=run([binary],env)
   else:r=run([ROOT/'tools/cool','run','--backend',engine,source],env)
   assert (r.returncode,r.stdout,r.stderr)==(0,'42\n',''),(front,engine,r)
  for declaration,error in invalid:
   source.write_text('struct G[T]{value:T;}'+declaration+'fn main(){}')
   r=run([front,'check',source],env);assert r.returncode==2 and error in r.stderr,(front,declaration,r)
  # Forward imported names and field privacy are checked before specialization.
  library=root/'library.cool';manifest=root/'bundle'
  library.write_text('package lib;struct Hidden[T]{value:T;}pub struct Visible[T]{pub value:T;}')
  manifest.write_text('__main\t'+str(source)+'\nlib\t'+str(library)+'\n')
  for field,error in [('lib.Hidden[T]','private'),('lib.Visible','wrong generic'),('lib.Missing[T]','unknown type')]:
   source.write_text('package main;import "lib";struct Unused[T]{value:'+field+';}fn main(){}')
   r=run([front,'check-bundle',manifest],env);assert r.returncode==2 and error in r.stderr,(front,field,r)
  source.write_text('package main;import "lib";struct Unused[T]{pub value:lib.Visible[T];}fn main(){let x=Unused[i64]{value:lib.Visible[i64]{value:42}};assert(x.value.value==42);}')
  for mode in ('check-bundle','run-bundle','bytecode-bundle','jit-bundle'):
   r=run([front,mode,manifest],env);assert (r.returncode,r.stdout,r.stderr)==(0,'',''),(front,mode,r)
  r=run([front,'repl-quiet'],env,'var kept=7;\nstruct Retry[T]{value:Missing;}\nstruct Retry[T]{value:T;}\nlet x=Retry[i64]{value:kept};\nx.value\n:quit\n')
  assert r.returncode==0 and r.stdout=='7\n' and r.stderr.count('error:')==1,r
print(f'template aggregate: forward/generic/layout execution on five engines + O2, {len(invalid)} unused declaration rejections, 3 imported type checks and REPL rollback on {len(fronts)} frontends PASS')
