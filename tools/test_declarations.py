#!/usr/bin/env python3
"""Declaration/type grammar acceptance, boundaries and signature rejection."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--frontend',type=Path);args=parser.parse_args()
fronts=[[ROOT/'build/cool-compiler'],[ROOT/'build/coolc','--run',ROOT/'build/language.BIN']]
if args.frontend:fronts.append([args.frontend.resolve()])
valid=[
 'enum E{Unit(void);}fn main(){let unit=E.Unit();}',
 'package main;fn main(){}',
 'pub struct S{pub x:i64;y:[2]u8;};pub enum E{None;Some(S);};fn main(){let e=E.Some(S{});}',
 'struct Link{next:*Link;value:i64;}fn main(){let link=Link{};}',
 'struct Box[T]{value:T;}fn identity[T](value:T)->T{return move value;}fn main(){let b=identity[Box[i64]](Box[i64]{value:1});}',
 'struct S{x:i64;}fn S.read(self:&S)->i64{return (*self).x;}fn main(){let s=S{};s.read();}',
 'fn same(value:&i64)->&i64 borrows(value){return value;}fn main(){let n=1;let r=same(&n);}',
 'extern "C" fn f(x:*void,y:usize)->i32;export "C" fn exported(x:i32)->i32{return x;}fn main(){}',
 'fn f(x:&mut i64,y:[]u8,z:own[i64],p:**i64,a:[0]i64){}fn main(){}',
 'fn f('+','.join(f'p{i}:i64' for i in range(32))+'){}fn main(){}',
 'struct G[A,B,C,D,E,F,G,H]{value:A;}fn main(){let g=G[i64,i64,i64,i64,i64,i64,i64,i64]{};}',
]
duplicates=[
 'extern "C" fn f(x:i64,x:i64);fn main(){}',
 'extern "C" fn f(x:i64,x:f64);fn main(){}',
 'fn f(x:i64,x:i64){}fn main(){}',
 'export "C" fn f(x:i64,x:i64){}fn main(){}',
 'fn f[T](x:T,x:T){}fn main(){f[i64](1,2);}',
]
invalid=[
 'struct i64{}fn main(){}','struct S{}struct S{}fn main(){}',
 'struct S{x:i64;x:i64;}fn main(){}','enum E{A;A;}fn main(){}','enum E{}fn main(){}',
 'struct S{x:void;}fn main(){}','struct S{x:S;}fn main(){}',
 'struct S[T,T]{}fn main(){}','struct S[]{}fn main(){}',
 'struct S[T]{}fn main(){let s=S[i64, u8]{};}',
 'struct S{}fn S(){}fn main(){}','fn f(){}fn f(){}fn main(){}',
 'fn f(x:void){}fn main(){}','fn f(x:i64,){}fn main(){}','fn f(x i64){}fn main(){}',
 'fn f[T,](){ }fn main(){}','fn f[](){}fn main(){}',
 'extern "Other" fn f();fn main(){}','extern "C" fn f(x:string);fn main(){}',
 'struct S{}extern "C" fn f(x:S);fn main(){}',
 'extern "C" fn f[T](x:T);fn main(){}','fn f();fn main(){}',
 'fn Missing.read(self:i64){}fn main(){}','struct S{}fn S.read(){}fn main(){}',
 'fn f()->&i64{return null;}fn main(){}',
 'fn f(x:&i64)->&i64 borrows(missing){return x;}fn main(){}',
 'fn f(x:[65537]u8){}fn main(){}','fn f(x:[1+1]u8){}fn main(){}',
 'fn f('+','.join(f'p{i}:i64' for i in range(33))+'){}fn main(){}',
 'struct G[A,B,C,D,E,F,G,H,I]{}fn main(){}',
]
env={**os.environ,'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
with tempfile.TemporaryDirectory(prefix='cool declarations ') as temporary:
 source=Path(temporary)/'main.cool'
 for frontend in fronts:
  for program in valid:
   source.write_text(program);r=subprocess.run([*frontend,'check',source],capture_output=True,text=True,env=env,timeout=30)
   assert r.returncode==0,(frontend,program,r)
  for program in duplicates+invalid:
   source.write_text(program);r=subprocess.run([*frontend,'check',source],capture_output=True,text=True,env=env,timeout=30)
   assert r.returncode==2,(frontend,program,r)
   if program in duplicates:assert 'duplicate parameter name' in r.stderr,r
print(f'declarations: {len(valid)} valid grammar/boundary cases, {len(duplicates)} duplicate signatures and {len(invalid)} invalid declarations on {len(fronts)} frontends PASS')
