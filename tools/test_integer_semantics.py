#!/usr/bin/env python3
"""Fixed-width integer semantics against Python's unbounded integer arithmetic."""
import argparse
import os
from pathlib import Path
import random
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--frontend', type=Path)
parser.add_argument('--sanitize-runtime', action='store_true')
args = parser.parse_args()
rng = random.Random(20261006)
functions = []
calls = []
expected = []
checks = 0

def normalize(value, width, signed):
    bits = value % (1 << width)
    return bits - (1 << width) if signed and bits >= (1 << (width - 1)) else bits

def quotient(a, b):
    magnitude = abs(a) // abs(b)
    return -magnitude if (a < 0) != (b < 0) else magnitude

for signed in (True, False):
    for width in (8, 16, 32, 64):
        ty = ('i' if signed else 'u') + str(width)
        lo = -(1 << (width-1)) if signed else 0
        hi = (1 << (width-int(signed))) - 1
        pairs = [(lo,1),(hi,1),(hi,hi),(lo,hi),(1,hi),(0,1)]
        if signed:
            pairs += [(lo,-1),(-7,3),(7,-3),(-7,-3)]
        pairs += [(rng.randint(lo,hi),rng.randint(lo,hi) or 1) for _ in range(12)]
        # Signed minimum / -1 is a checked failure at every width.
        pairs = [(a,b) for a,b in pairs if not (signed and a==lo and b==-1)]
        ops = ['a+b','a-b','a*b','a/b','a%b','a&b','a|b','a^b','-a','~a',
               'a<<count','a>>count','a<b','a<=b','a>b','a>=b','a==b','a!=b']
        functions.append(f'fn calc_{ty}(a:{ty},b:{ty},count:{ty}){{'+''.join(f'io.println({op});' for op in ops)+'}')
        for a,b in pairs:
            count = rng.choice([0,1,width-1])
            calls.append(f'calc_{ty}({ty}({a}),{ty}({b}),{ty}({count}));')
            q = quotient(a,b)
            numbers = [a+b,a-b,a*b,q,a-q*b,a&b,a|b,a^b,-a,~a,a<<count,a>>count]
            expected += [str(normalize(n,width,signed)) for n in numbers]
            expected += [str(v).lower() for v in [a<b,a<=b,a>b,a>=b,a==b,a!=b]]
            checks += len(ops)
# Explicit integer casts wrap into the destination range, across widths/signs.
for source_ty,source_value in [('i64',-1),('u64',2**64-1),('i64',-129),('u64',65536)]:
    for signed in (True,False):
        for width in (8,16,32,64):
            ty=('i' if signed else 'u')+str(width)
            calls.append(f'io.println({ty}({source_ty}({source_value})));')
            expected.append(str(normalize(source_value,width,signed)));checks+=1
program='import "std/io";'+''.join(functions)+'fn main(){'+''.join(calls)+'}'
expected='\n'.join(expected)+'\n'
failures=[]
for width in (8,16,32,64):
    for prefix in ('i','u'):
        ty=prefix+str(width)
        failures.append((f'fn bad(a:{ty},b:{ty})->{ty}{{return a<<b;}}fn main(){{bad(1,{width});}}','shift count outside operand width'))
failures += [
    ('fn bad(a:i64,b:i64)->i64{return a>>b;}fn main(){bad(1,-1);}','shift count outside operand width'),
    ('fn bad(a:i64,b:i64)->i64{return a/b;}fn main(){bad(7,0);}','invalid integer division'),
    ('fn bad(a:u64,b:u64)->u64{return a%b;}fn main(){bad(7,0);}','invalid integer division'),
    ('fn bad(a:i64,b:i64)->i64{return a/b;}fn main(){bad(-9223372036854775808,-1);}','invalid integer division'),
    ('fn bad(a:i64,b:i64)->i64{return a%b;}fn main(){bad(-9223372036854775808,-1);}','invalid integer division'),
]

for width in (8,16,32):
    for operator in ('/','%'):
        ty='i'+str(width);minimum=-(1 << (width-1))
        failures.append((f'fn bad(a:{ty},b:{ty})->{ty}{{return a{operator}b;}}fn main(){{bad({minimum},-1);}}','invalid integer division'))

def run(command,env):
    return subprocess.run([str(x) for x in command],cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)

with tempfile.TemporaryDirectory(prefix='cool integer semantics ') as temporary:
    directory=Path(temporary);source=directory/'main.cool';binary=directory/'program';wrapper=directory/'bootstrap'
    wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');wrapper.chmod(0o755)
    frontends=[ROOT/'build/cool-compiler',wrapper]
    if args.frontend:frontends.append(args.frontend.resolve())
    for frontend in frontends:
        env={**os.environ,'COOL_FRONTEND':str(frontend),'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
        for index,(text,output,diagnostic) in enumerate([(program,expected,None)]+[(text,'',diagnostic) for text,diagnostic in failures]):
            source.write_text(text)
            engines=('tree','interp','jit','llvm','llvm-jit','O2')
            if args.sanitize_runtime and frontend==frontends[0]: engines+=('ASan/UBSan',)
            for engine in engines:
                if engine=='ASan/UBSan':
                    ir=directory/'program.ll'
                    result=run([ROOT/'tools/cool','emit-ir',source,'-o',ir],env)
                    assert result.returncode==0,result
                    ir.write_text('\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in ir.read_text().splitlines())+'\n')
                    result=run(['clang','-Wno-override-module','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',ir,ROOT/'language/runtime.c','-o',binary],env)
                    assert result.returncode==0,result
                    result=run([binary],env)
                elif engine=='O2':
                    result=run([ROOT/'tools/cool','build','--release',source,'-o',binary],env)
                    assert result.returncode==0,(frontend,index,result)
                    result=run([binary],env)
                else:
                    result=run([ROOT/'tools/cool','run','--backend',engine,source],env)
                if diagnostic:
                    assert result.returncode==2 and result.stdout=='' and diagnostic in result.stderr,(frontend,engine,index,result)
                else:
                    actual=result.stdout.splitlines(); wanted=output.splitlines()
                    difference=next(((i,a,b) for i,(a,b) in enumerate(zip(actual,wanted)) if a!=b),None)
                    assert (result.returncode,result.stdout,result.stderr)==(0,output,''),(frontend,engine,index,result.returncode,result.stderr,difference,len(actual),len(wanted))
        print(f'integer semantics: {frontend.name}: {checks} oracle results, {len(failures)} checked runtime failures, five engines + O2 PASS',flush=True)

if args.sanitize_runtime: print('integer semantics: emitted LLVM with ASan and C runtime with ASan/UBSan: all oracle and runtime failure cases PASS')
