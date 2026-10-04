#!/usr/bin/env python3
"""Length-aware input rejection, formatter preservation and REPL recovery."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--frontend',type=Path);args=parser.parse_args()
frontends=[[ROOT/'build/cool-compiler'],[ROOT/'build/coolc','--run',ROOT/'build/language.BIN']]
if args.frontend:frontends.append([args.frontend.resolve()])
env={**os.environ,'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
def run(front,*args,input=None):
    return subprocess.run([*front,*args],input=input,capture_output=True,timeout=30,env=env)
inputs=[b'\0fn main(){}',b'fn main(){}\0invalid tokens',b'// comment\0hidden\nfn main(){}',
    b'/* comment\0hidden */fn main(){}',b'fn main(){let s="hello\0world";}',
    'fn main(){let s="🙂";}\r\n\0ignored'.encode(),b'fn main(){}\0']
with tempfile.TemporaryDirectory(prefix='cool input bytes ') as directory:
    root=Path(directory).resolve();source=root/'input.cool';output=root/'out.cool';manifest=root/'sources.list'
    for front in frontends:
        for data in inputs:
            source.write_bytes(data);output.write_bytes(b'preserve destination')
            for mode in ('check','scan','run','bytecode','jit'):
                result=run(front,mode,source)
                assert result.returncode==2 and b'embedded NUL byte' in result.stderr,(front,mode,data,result)
            result=run(front,'fmt',source,output)
            assert result.returncode==2 and b'embedded NUL byte' in result.stderr,result
            assert source.read_bytes()==data and output.read_bytes()==b'preserve destination'
            manifest.write_text('__main\t'+str(source)+'\n')
            result=run(front,'diagnostics-bundle',manifest)
            record=json.loads(result.stdout)
            offset=data.index(b'\0')
            assert result.returncode==2 and record['file']==str(source) and record['start']==offset and record['end']==offset+1,record
            assert record['line']==data[:offset].count(b'\n')+1,record
            assert record['column']==len(data[:offset].rsplit(b'\n',1)[-1])+1,record
        source.write_text('fn main(){assert(true);}')
        manifest.write_bytes(('__main\t'+str(source)+'\n').encode()+b'\0ignored')
        result=run(front,'check-bundle',manifest)
        assert result.returncode==2 and b'embedded NUL byte' in result.stderr,result
        session=b'var kept=7;\nkept=99;\0ignored\nkept\n:quit\0ignored\nkept\n:quit\n'
        result=run(front,'repl-quiet',input=session)
        assert result.returncode==0 and result.stdout==b'7\n7\n' and result.stderr.count(b'embedded NUL byte')==2,result
print(f'input bytes: {len(inputs)} NUL placements across check/scan/execution/format/JSON, manifest rejection, preserved files and REPL recovery on {len(frontends)} frontends PASS')
