#!/usr/bin/env python3
"""IEEE boundary conversion oracle, including adjacent representable doubles."""
import argparse
import math
import os
import random
from pathlib import Path
import shlex
import struct
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--frontend',type=Path)
parser.add_argument('--sanitize-runtime',action='store_true')
args=parser.parse_args()
valid=[];invalid=[]
def literal(value):
    text=repr(value)
    return text if '.' in text or 'e' in text else text+'.0'
def single(value):
    return struct.unpack('f',struct.pack('f',value))[0]
def integer_single(value):
    # Round the exact integer to 24 significant binary digits. No float is
    # involved until the rounded integer is exactly representable in binary32.
    magnitude=abs(value)
    shift=max(0,magnitude.bit_length()-24)
    if shift:
        quotient,remainder=divmod(magnitude,1<<shift)
        halfway=1<<(shift-1)
        if remainder>halfway or (remainder==halfway and quotient%2):quotient+=1
        magnitude=quotient<<shift
    return float(-magnitude if value<0 else magnitude)

for signed in (True,False):
    for width in (8,16,32,64):
        ty=('i' if signed else 'u')+str(width)
        edge=float(2**(width-int(signed)))
        lower=-edge if signed else 0.0
        for value in [lower,math.nextafter(lower,math.inf),math.nextafter(edge,0.0),0.0,-0.0,0.75,1.75]:
            # Tiny subnormal literals are intentionally generated at runtime;
            # source literal underflow is a distinct lexer contract.
            if value and abs(value)<1e-300:continue
            valid.append((f'{ty}({literal(value)})',str(math.trunc(value))))
        if signed:
            valid += [(f'{ty}(-1.75)','-1'),(f'{ty}(-0.75)','0')]
        for value in [edge,math.nextafter(lower,-math.inf) if signed else -0.75]:
            invalid.append((ty,literal(value)))
        for value in [-(2**(width-1)) if signed else 0,2**(width-int(signed))-1]:
            for target in ('f64','f32'):
                converted=float(value)
                if target=='f32':converted=integer_single(value)
                valid.append((f'{target}({ty}({value}))',format(converted,'.17g')))
# Exact tie-to-even rounding at binary32's integer precision boundary.
for value in [16777215.0,16777216.0,16777217.0,16777218.0,16777219.0,-16777217.0]:
    valid.append((f'f32({literal(value)})',format(single(value),'.17g')))
valid += [('i64(f32(3.75))','3'),('u64(f32(3.75))','3'),('f64(f32(-0.0))','-0')]
invalid += [('i64','0.0/0.0'),('i64','1.0/0.0'),('u64','-1.0/0.0'),('i8','f32(128.0)'),('u8','f32(256.0)')]
for value in (1e-310,5e-324,-5e-324):
    valid.append((literal(value),format(value,'.17g')))
valid.append(('f32(1e-45)',format(single(1e-45),'.17g')))
# Probe both sides of exact binary32 midpoints, including those finer than
# binary64 can retain. Odd/even significands distinguish both tie directions.
integers={0,1,-1,2**64-1,-2**63}
for exponent in (24,31,53,54,62,63):
    spacing=1<<(exponent-23)
    for significand_offset in (0,1,2):
        midpoint=(1<<exponent)+significand_offset*spacing+spacing//2
        for delta in (-1,0,1):
            value=midpoint+delta
            if value<2**64:integers.add(value)
            if value<=2**63:integers.add(-value)
rng=random.Random(20261007)
integers.update(rng.randrange(-2**63,2**64) for _ in range(64))
for value in sorted(integers):
    source='i64' if value<2**63 else 'u64'
    valid.append((f'f32({source}({value}))',format(integer_single(value),'.17g')))
program='import "std/io";fn main(){'+''.join(f'io.println({expression});' for expression,_ in valid)+'}'
expected=''.join(value+'\n' for _,value in valid)

def run(command,env):
    return subprocess.run([str(x) for x in command],cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)

with tempfile.TemporaryDirectory(prefix='cool float conversions ') as temporary:
    directory=Path(temporary);source=directory/'main.cool';binary=directory/'program';wrapper=directory/'bootstrap'
    wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');wrapper.chmod(0o755)
    fronts=[ROOT/'build/cool-compiler',wrapper]
    if args.frontend:fronts.append(args.frontend.resolve())
    for frontend in fronts:
        env={**os.environ,'COOL_FRONTEND':str(frontend),'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
        programs=[program]+[f'fn convert(n:f64)->{ty}{{return {ty}(n);}}fn main(){{convert({value});}}' for ty,value in invalid]
        for index,text in enumerate(programs):
            source.write_text(text)
            engines=('tree','interp','jit','llvm','llvm-jit','O2')
            if args.sanitize_runtime and frontend==fronts[0]:engines+=('ASan/UBSan',)
            for engine in engines:
                if engine=='ASan/UBSan':
                    ir=directory/'program.ll'
                    result=run([ROOT/'tools/cool','emit-ir',source,'-o',ir],env);assert result.returncode==0,result
                    ir.write_text('\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in ir.read_text().splitlines())+'\n')
                    result=run(['clang','-Wno-override-module','-O1','-g','-fsanitize=address,undefined,float-cast-overflow','-fno-omit-frame-pointer',ir,ROOT/'language/runtime.c','-o',binary],env);assert result.returncode==0,result
                    result=run([binary],env)
                elif engine=='O2':
                    result=run([ROOT/'tools/cool','build','--release',source,'-o',binary],env);assert result.returncode==0,result
                    result=run([binary],env)
                else:result=run([ROOT/'tools/cool','run','--backend',engine,source],env)
                if index:
                    assert result.returncode==2 and result.stdout=='' and 'floating conversion out of range' in result.stderr,(frontend,engine,index,result)
                else:
                    actual=result.stdout.splitlines();wanted=expected.splitlines()
                    difference=next(((i,a,b) for i,(a,b) in enumerate(zip(actual,wanted)) if a!=b),None)
                    assert (result.returncode,result.stdout,result.stderr)==(0,expected,''),(frontend,engine,result.returncode,result.stderr,difference,len(actual),len(wanted))
        for text in ('1e999','1e-999'):
            source.write_text(f'fn main(){{let value={text};}}')
            result=run([ROOT/'tools/cool','check',source],env)
            assert result.returncode==2 and 'floating literal out of range or invalid' in result.stderr,result
        print(f'float conversions: {frontend.name}: {len(valid)} oracle values, {len(invalid)} checked failures and 2 literal range rejections; five engines + O2 PASS',flush=True)
if args.sanitize_runtime:print('float conversions: LLVM ASan and runtime ASan/UBSan/float-cast-overflow PASS')
