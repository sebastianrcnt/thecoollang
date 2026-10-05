#!/usr/bin/env python3
"""Exact rational IEEE arithmetic oracle; no host float arithmetic for results."""
import argparse, math, os, random, shlex, struct, subprocess, tempfile
from fractions import Fraction
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);p.add_argument('--sanitize-runtime',action='store_true');args=p.parse_args()

def value(bits,width):
 return struct.unpack('>f' if width==32 else '>d',bits.to_bytes(width//8,'big'))[0]

def rounded(number,width,negative_zero=False):
 precision,emin,emax,bias=(24,-126,127,127) if width==32 else (53,-1022,1023,1023)
 sign=int(number<0 or (number==0 and negative_zero))<<(width-1)
 number=abs(number)
 if not number:return sign
 exponent=number.numerator.bit_length()-number.denominator.bit_length()
 power=Fraction(2**exponent) if exponent>=0 else Fraction(1,2**(-exponent))
 if number<power:exponent-=1
 exponent=max(exponent,emin)
 shift=exponent-(precision-1)
 scaled=number/Fraction(2**shift) if shift>=0 else number*2**(-shift)
 quotient,remainder=divmod(scaled.numerator,scaled.denominator)
 if 2*remainder>scaled.denominator or (2*remainder==scaled.denominator and quotient%2):quotient+=1
 if quotient>=1<<precision:quotient>>=1;exponent+=1
 if exponent>emax:return sign|(((1<<(width-precision))-1)<<(precision-1))
 if quotient<1<<(precision-1):return sign|quotient
 return sign|((exponent+bias)<<(precision-1))|(quotient-(1<<(precision-1)))

def expected(a,b,op,width):
 x,y=Fraction.from_float(a),Fraction.from_float(b)
 sa,sb=math.copysign(1,a)<0,math.copysign(1,b)<0
 if op=='+':result=x+y;zero=sa and sb
 elif op=='-':result=x-y;zero=sa and not sb
 elif op=='*':result=x*y;zero=sa!=sb
 else:
  if y==0:
   if x==0:return 'nan'
   precision=24 if width==32 else 53
   return str((int(sa!=sb)<<(width-1))|(((1<<(width-precision))-1)<<(precision-1)))
  result=x/y;zero=sa!=sb
 return str(rounded(result,width,zero))

def literal(n):return repr(n)

# Self-check boundary construction independently against known IEEE bit patterns.
assert rounded(Fraction(1),32)==0x3f800000
assert rounded(Fraction(1,2**149),32)==1
assert rounded(Fraction(1,2**150),32)==0
assert rounded(Fraction(3,2**150),32)==2
assert rounded(Fraction(1)+Fraction(1,2**24),32)==0x3f800000
assert rounded(Fraction(1)+Fraction(3,2**24),32)==0x3f800002
assert rounded(Fraction(1,2**1074),64)==1
assert rounded(Fraction(1),64)==0x3ff0000000000000
program=['import "std/io";struct F32{value:f32;}struct F64{value:f64;}',
 'fn emit32(value:f32){if(value!=value){io.println("nan");}else{var bits=F32{value:value};unsafe{io.println(*cast[*u32](&raw bits));}}}',
 'fn emit64(value:f64){if(value!=value){io.println("nan");}else{var bits=F64{value:value};unsafe{io.println(*cast[*u64](&raw bits));}}}',
 'fn main(){']
outputs=[];pairs_count=0
for width in (32,64):
 fraction=23 if width==32 else 52
 exponent=8 if width==32 else 11
 sign=1<<(width-1);maximum=((1<<exponent)-2)<<fraction | ((1<<fraction)-1)
 patterns=[0,sign,1,2,3,sign|1,1<<fraction,(1<<fraction)-1,maximum,maximum|sign,
           (127 if width==32 else 1023)<<fraction,((127 if width==32 else 1023)<<fraction)+1,
           ((127 if width==32 else 1023)<<fraction)|sign]
 randomizer=random.Random(20261005+width)
 while len(patterns)<37:
  bits=randomizer.getrandbits(width)
  if (bits>>fraction)&((1<<exponent)-1)!=(1<<exponent)-1:patterns.append(bits)
 pairs=[(a,b) for a in patterns[:13] for b in patterns[:13]]
 pairs += [(a,patterns[(i*7+3)%len(patterns)]) for i,a in enumerate(patterns[13:])]
 # Limit code/slot growth by putting each width in independent helper functions.
 program[-1:]=[f'fn cases{width}(){{']
 for abits,bbits in pairs:
  a,b=value(abits,width),value(bbits,width);left=f'f{width}({literal(a)})';right=f'f{width}({literal(b)})'
  for op in ('+','-','*','/'):
   program.append(f'emit{width}({left}{op}{right});');outputs.append(expected(a,b,op,width))
  pairs_count+=1
 program.append('}')
 # Next iteration replaces only this placeholder, keeping prior helper closed.
 program.append('fn main(){')
program += ['cases32();cases64();',
 'let nan=0.0/0.0;let infinity=1.0/0.0;',
 'io.println(nan==nan);io.println(nan!=nan);io.println(nan<0.0);io.println(nan<=0.0);io.println(nan>0.0);io.println(nan>=0.0);',
 'io.println(infinity>1.7976931348623157e308);io.println(-infinity< -1.7976931348623157e308);',
 'emit32(f32(infinity-infinity));emit64(infinity/infinity);emit32(f32(0.0*infinity));',
 '}']
outputs+=['false','true','false','false','false','false','true','true','nan','nan','nan']
program.pop() # Extend the main function with ordered/unordered comparisons.
for width in (32,64):
 program.append(f'let n{width}=f{width}(0.0/0.0);')
 for other in (f'f{width}(0.0)',f'f{width}(-0.0)',f'f{width}(1.0)',f'f{width}(-infinity)',f'n{width}',f'-n{width}'):
  for left,right in ((f'n{width}',other),(other,f'n{width}')):
   for op in ('==','!=','<','<=','>','>='):
    program.append(f'io.println({left}{op}{right});');outputs.append('true' if op=='!=' else 'false')
 for op in ('==','!=','<','<=','>','>='):
  program.append(f'io.println(f{width}(0.0){op}f{width}(-0.0));');outputs.append('true' if op in ('==','<=','>=') else 'false')
program.append('}')
expected_text='\n'.join(outputs)+'\n'
invalid=['1.0%2.0','1.0&2.0','1.0|2.0','1.0^2.0','1.0<<2','~1.0','!1.0']
def run(command,env):return subprocess.run(list(map(str,command)),cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)
with tempfile.TemporaryDirectory(prefix='cool float arithmetic ') as temporary:
 root=Path(temporary);source=root/'main.cool';binary=root/'program';wrapper=root/'bootstrap'
 source.write_text('\n'.join(program))
 wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');wrapper.chmod(0o755)
 fronts=[ROOT/'build/cool-compiler',wrapper]
 if args.frontend:fronts.append(args.frontend.resolve())
 for front in fronts:
  env={**os.environ,'COOL_FRONTEND':str(front),'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
  engines=('tree','interp','jit','llvm','llvm-jit','O2')
  if args.sanitize_runtime and front==fronts[0]:engines+=('ASan/UBSan',)
  for engine in engines:
   if engine=='ASan/UBSan':
    ir=root/'program.ll'
    r=run([ROOT/'tools/cool','emit-ir',source,'-o',ir],env);assert r.returncode==0,r
    ir.write_text('\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in ir.read_text().splitlines())+'\n')
    r=run(['clang','-Wno-override-module','-O1','-g','-fsanitize=address,undefined,float-cast-overflow','-fno-omit-frame-pointer',ir,ROOT/'language/runtime.c','-o',binary],env);assert r.returncode==0,r
    r=run([binary],env)
   elif engine=='O2':
    r=run([ROOT/'tools/cool','build','--release',source,'-o',binary],env);assert r.returncode==0,r
    r=run([binary],env)
   else:r=run([ROOT/'tools/cool','run','--backend',engine,source],env)
   if (r.returncode,r.stdout,r.stderr)!=(0,expected_text,''):
    actual=r.stdout.splitlines()
    mismatch=next(((i,want,actual[i] if i<len(actual) else '<missing>') for i,want in enumerate(outputs) if i>=len(actual) or actual[i]!=want),None)
    raise AssertionError((front,engine,r.returncode,r.stderr,mismatch))
  for expression in invalid:
   source.write_text('fn main(){let x='+expression+';}');r=run([front,'check',source],env);assert r.returncode==2,(front,expression,r)
  source.write_text('\n'.join(program))
print(f'float arithmetic: {pairs_count} rational-modeled finite operand pairs, {len(outputs)} exact bit/NaN/comparison results and {len(invalid)} rejections; five engines + O2 on {len(fronts)} frontends PASS')
