#!/usr/bin/env python3
"""Native lexical boundary cases against independent Python integer values."""
from pathlib import Path
import argparse
import os
import random
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--frontend',type=Path)
args=parser.parse_args()
frontends=[[ROOT/'build/cool-compiler'],[ROOT/'build/coolc','--run',ROOT/'build/language.BIN']]
if args.frontend:frontends.append([args.frontend.resolve()])
env={**os.environ,'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
rng=random.Random(20261005)
valid=[('0',0),('0x_FF_',255),('0b_10__01_',9),('1__234_',1234),('0xffff_ffff_ffff_ffff',2**64-1)]
for base,prefix,format_code in ((16,'0x','x'),(2,'0b','b')):
    for _ in range(48):
        value=rng.randrange(2**64)
        digits=format(value,format_code)
        spelling=prefix+'_'.join(digits)
        valid.append((spelling,value))
invalid=[prefix+'_'*count for prefix in ('0x','0b') for count in range(0,17)]
invalid+=['0b2','0xg','0x___g','0b___2','0x1g','0b102']
with tempfile.TemporaryDirectory(prefix='cool integer tokens ') as directory:
    source=Path(directory)/'literal.cool'
    program='import "std/io";fn main(){'+''.join(f'io.println({literal});' for literal,_ in valid)+'}'
    expected=''.join(str(value)+'\n' for _,value in valid)
    for frontend in frontends:
        source.write_text(program)
        for mode in ('run','bytecode','jit'):
            result=subprocess.run([*frontend,mode,source],capture_output=True,text=True,timeout=30,env=env)
            assert (result.returncode,result.stdout,result.stderr)==(0,expected,''),(frontend,mode,result)
        for literal in invalid:
            source.write_text(f'fn main(){{let value={literal};}}')
            result=subprocess.run([*frontend,'check',source],capture_output=True,text=True,timeout=15,env=env)
            assert result.returncode==2 and 'invalid integer literal' in result.stderr,(frontend,literal,result)
print(f'integer tokens: {len(valid)} independently modeled values on tree/bytecode/JIT and {len(invalid)} malformed tokens rejected on {len(frontends)} frontends PASS')
