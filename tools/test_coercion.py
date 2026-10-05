#!/usr/bin/env python3
"""Order-independent implicit numeric typing with an integer oracle."""
import argparse, os, shlex, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);args=p.parse_args()
types=[(prefix+str(width),prefix=='i',width) for prefix in ('i','u') for width in (8,16,32,64)]
def target(a,b):
 if a[1]==b[1]:return a if a[2]>=b[2] else b
 signed=a if a[1] else b;unsigned=b if a[1] else a
 return signed if signed[2]>unsigned[2] else None
def bounds(t):return (-(1<<(t[2]-1)),(1<<(t[2]-1))-1) if t[1] else (0,(1<<t[2])-1)
def wrap(n,t):
 n%=1<<t[2]
 return n-(1<<t[2]) if t[1] and n>=(1<<(t[2]-1)) else n
body=[];expected=[];invalid=[];serial=0
for a in types:
 for b in types:
  t=target(a,b)
  if t is None:
   invalid.append(f'let a={a[0]}(1);let b={b[0]}(2);let result=a+b;');continue
  for left,right in ((bounds(a)[1],bounds(b)[1]),(bounds(a)[0],1)):
   av=f'a{serial}';bv=f'b{serial}';serial+=1
   body.append(f'let {av}={a[0]}({left});let {bv}={b[0]}({right});')
   for op,value in [('+',wrap(left+right,t)),('-',wrap(left-right,t)),('*',wrap(left*right,t)),('<',left<right),('==',left==right),('>',left>right)]:
    body.append(f'io.println({av}{op}{bv});');expected.append(str(value).lower() if isinstance(value,bool) else str(value))
body.append('let tiny=i8(127);io.println(tiny+1);io.println(1+tiny);io.println(tiny+128);io.println(128+tiny);')
expected+=['-128','-128','255','255']
body.append('let single=f32(16777216.0);let double=1.0;io.println(single+double);io.println(double+single);io.println(single+1);io.println(1+single);')
expected+=['16777217','16777217','16777216','16777216']
body.append('io.println(18446744073709551615+1);io.println(1+18446744073709551615);')
expected+=['0','0']
body.append('let count=i64(1);io.println(i8(127)<<count);let high=u64(7);io.println(i8(-128)>>high);io.println(u8(255)>>high);')
expected+=['-2','-1','1']
body.append('unsafe{let p=cast[*i64](0);let erased=cast[*void](p);assert(p==null && null==p);assert(p==erased && erased==p);}')
invalid += ['let a=f32(1.0);let b=i32(2);let result=a+b;','let a=f32(1.0);let b=i32(2);let result=b+a;',
 'let a=i8(1);let b=f64(1.0);let result=a<<b;','let a=f64(1.0);let b=i8(1);let result=a>>b;',
 'let a:i8=1+2;',
 'let a:f64=18446744073709551615;','let a:f32=18446744073709551615;',
 'let a=f64(1.0);let result=a+18446744073709551615;',
 'let a=f64(1.0);let result=18446744073709551615+a;',
 'let a:f32=1.0;','let a=i64(1);let b:i8=a;','let a=u64(1);let b:i64=a;',
 'let a=f64(1.0);let b:f32=a;','let a=f64(1.0);let b=16777217;let result=a+b;',
 'let a=f64(1.0);let result=a+16777217;','let a=f64(1.0);let result=16777217+a;']
body.append('let narrow=i8(7);let fraction=f32(1.5);io.println(combine(narrow,fraction,narrow));let pair=Pair{y:fraction,x:narrow};io.println(pair.x);io.println(pair.y);')
expected+=['15.5','7','1.5']
program='import "std/io";struct Pair{x:i64;y:f64;}fn combine(a:i64,b:f64,c:i64)->f64{return f64(a)+b+f64(c);}fn main(){'+''.join(body)+'}'
output=''.join(line+'\n' for line in expected)
def run(command,env):return subprocess.run(list(map(str,command)),cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)
with tempfile.TemporaryDirectory(prefix='cool coercion ') as temporary:
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
   assert (r.returncode,r.stdout,r.stderr)==(0,output,''),(front,engine,r)
  for statement in invalid:
   source.write_text('fn main(){'+statement+'}')
   r=run([front,'check',source],env);assert r.returncode==2,(front,statement,r)
  source.write_text('fn narrow()->i8{return 1+2;}fn main(){}')
  r=run([front,'check',source],env);assert r.returncode==2 and 'explicit cast' in r.stderr,r
  for ty,value in [('i64','8'),('u64','18446744073709551615')]:
   source.write_text(f'fn shifted(n:{ty})->i8{{let a=i8(1);return a<<n;}}fn main(){{shifted({value});}}')
   r=run([front,'check',source],env);assert r.returncode==0,r
   for engine in ('tree','interp','jit','llvm','llvm-jit','O2'):
    if engine=='O2':
     r=run([ROOT/'tools/cool','build','--release',source,'-o',binary],env);assert r.returncode==0,r
     r=run([binary],env)
    else:r=run([ROOT/'tools/cool','run','--backend',engine,source],env)
    assert r.returncode==2 and 'shift count outside operand width' in r.stderr,(front,engine,r)
print(f'coercion: {len(expected)} independent numeric outputs, null/void pointer symmetry and {len(invalid)} safe-conversion rejections on {len(fronts)} frontends; five engines + O2 PASS')
