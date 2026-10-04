#!/usr/bin/env python3
"""Decimal floating-token grammar, long significands and formatter preservation."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--frontend',type=Path);args=parser.parse_args()
valid=['0.0','1.25','1e0','1E+2','1e-2','0001.5','0.0e-999',
       '18446744073709551616.0','18446744073709551616e-19',
       '1'+('0'*308)+'.0','1'+('0'*309)+'e-309','1'+('0'*1999)+'e-1999',
       '1.7976931348623157e308','2.2250738585072014e-308','1e-310','5e-324']
# Sweep across the u64 integer-accumulator boundary, retaining the whole token.
valid += [str(2**64+offset)+suffix for offset in (-1,0,1,123456789) for suffix in ('.0','e0','e-20')]
invalid=['1e','1e+','1e-','1E+','1_0.0','1.0_0','1e1_0','1.0f','1e2x',
         '.5','1.','1.e2','0x1.2','0b1.0','1e999','1e-999',
         '18446744073709551616','0x10000000000000000','0b1'+('0'*64)]
program='import "std/io";fn main(){'+''.join(f'io.println({text});' for text in valid)+'io.println(7);}'
expected=''.join(format(float(text),'.17g')+'\n' for text in valid)+'7\n'
def run(command,env):return subprocess.run([str(x) for x in command],cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)
with tempfile.TemporaryDirectory(prefix='cool float literals ') as temporary:
    directory=Path(temporary);source=directory/'main.cool';formatted=directory/'formatted.cool';binary=directory/'program';wrapper=directory/'bootstrap'
    wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');wrapper.chmod(0o755)
    fronts=[ROOT/'build/cool-compiler',wrapper]
    if args.frontend:fronts.append(args.frontend.resolve())
    for frontend in fronts:
        env={**os.environ,'COOL_FRONTEND':str(frontend),'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
        source.write_text(program)
        for engine in ('tree','interp','jit','llvm','llvm-jit','O2'):
            if engine=='O2':
                result=run([ROOT/'tools/cool','build','--release',source,'-o',binary],env);assert result.returncode==0,result
                result=run([binary],env)
            else:result=run([ROOT/'tools/cool','run','--backend',engine,source],env)
            assert (result.returncode,result.stdout,result.stderr)==(0,expected,''),(frontend,engine,result)
        result=run([frontend,'fmt',source,formatted],env);assert result.returncode==0,result
        result=run([frontend,'run',formatted],env)
        assert (result.returncode,result.stdout,result.stderr)==(0,expected,''),(frontend,'formatted',result)
        for literal in invalid:
            source.write_text(f'fn main(){{let value={literal};}}')
            result=run([frontend,'check',source],env)
            assert result.returncode==2,(frontend,literal,result)
    print(f'float literals: {len(valid)} oracle values including 2000-digit significands, {len(invalid)} rejected forms and formatter round trip on {len(fronts)} frontends; five engines + O2 PASS')
