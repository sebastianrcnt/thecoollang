#!/usr/bin/env python3
"""Whole-input UTF-8 validation against Python decoding, byte ranges and recovery."""
import argparse,json,os,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);args=p.parse_args()
fronts=[[ROOT/'build/cool-compiler'],[ROOT/'build/coolc','--run',ROOT/'build/language.BIN']]
if args.frontend:fronts.append([args.frontend.resolve()])
env={**os.environ,'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
bad=[bytes([n]) for n in range(128,256)]
bad += [b'\xc0\x80',b'\xc1\xbf',b'\xe0\x80\x80',b'\xe0\x9f\xbf',b'\xed\xa0\x80',b'\xed\xbf\xbf',b'\xf0\x80\x80\x80',b'\xf0\x8f\xbf\xbf',b'\xf4\x90\x80\x80',b'\xf4\xbf\xbf\xbf',b'\xc2A',b'\xe1\x80A',b'\xf1\x80\x80A',b'\xe1\x80',b'\xf1\x80\x80']
for value in bad:
 try:value.decode('utf-8')
 except UnicodeDecodeError:pass
 else:raise AssertionError(value)
scalars=[1,9,10,13,31,127,128,2047,2048,0xd7ff,0xe000,0xffff,0x10000,0x10ffff]
valid=b''.join(b'/*'+chr(n).encode()+b'*/' for n in scalars)+b'fn main(){}'
prefix='// 🙂\r\n// '.encode()
def run(front,*command,input=None):return subprocess.run([*front,*map(str,command)],input=input,capture_output=True,env=env,timeout=30)
with tempfile.TemporaryDirectory(prefix='cool source UTF8 ') as temporary:
 root=Path(temporary);source=root/'source.cool';output=root/'output.cool';manifest=root/'sources.list'
 for front in fronts:
  source.write_bytes(valid);assert run(front,'check',source).returncode==0
  manifest.write_text('__main\t'+str(source)+'\n')
  for value in bad:
   source.write_bytes(prefix+value)
   result=run(front,'diagnostics-bundle',manifest);record=json.loads(result.stdout)
   assert result.returncode==2 and record['message']=='invalid UTF-8 in input',result
   assert (record['file'],record['start'],record['end'],record['line'],record['column'])==(str(source),len(prefix),len(prefix)+1,2,4),record
  for data in (b'\xfffn main(){}',b'fn main(){}//\xed\xa0\x80',b'fn main(){let s="\xf4\x90\x80\x80";}',b'/*\xc0\x80*/fn main(){}'):
   source.write_bytes(data);output.write_bytes(b'preserve')
   for mode in ('check','scan','run','bytecode','jit'):
    result=run(front,mode,source);assert result.returncode==2 and b'invalid UTF-8' in result.stderr,result
   result=run(front,'fmt',source,output);assert result.returncode==2,result
   assert source.read_bytes()==data and output.read_bytes()==b'preserve'
  source.write_text('fn main(){}');manifest.write_bytes(b'\xff')
  result=run(front,'check-bundle',manifest);assert result.returncode==2 and b'invalid UTF-8' in result.stderr,result
  result=run(front,'repl-quiet',input=b'var kept=7;\nkept=99;//\xff\nkept\n:quit\n')
  assert result.returncode==0 and result.stdout==b'7\n' and b'invalid UTF-8' in result.stderr,result
 print(f'source UTF8: {len(bad)} Python-confirmed invalid sequences/ranges, {len(scalars)} valid boundaries, file/manifest/format/REPL preservation on {len(fronts)} frontends PASS')
