#!/usr/bin/env python3
"""Native ctypes layout oracle plus Cool enum/sequence representation probes."""
import argparse
import ctypes as c
import os
from pathlib import Path
import random
import shlex
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);p.add_argument('--sanitize-runtime',action='store_true');args=p.parse_args()
rng=random.Random(20261008)
choices=[('bool',c.c_bool),('u8',c.c_uint8),('i16',c.c_int16),('u32',c.c_uint32),('i64',c.c_int64),('f32',c.c_float),('f64',c.c_double),('*u8',c.c_void_p),('string',c.c_void_p),('[3]i16',c.c_int16*3),('[0]i64',c.c_int64*0)]
declarations=[];functions=[];calls=[];expected=[]
for index in range(24):
 name=f'S{index}'
 fields=[(f'f{i}',*rng.choice(choices)) for i in range(rng.randrange(0,7))]
 native=type(name,(c.Structure,),{'_fields_':[(field,ctype) for field,_,ctype in fields]})
 declarations.append('struct '+name+'{'+''.join(f'{field}:{ty};' for field,ty,_ in fields)+'}')
 wrapper=type('Wrapper'+name,(c.Structure,),{'_fields_':[('prefix',c.c_uint8),('value',native),('suffix',c.c_uint8)]})
 declarations.append(f'struct Wrapper{name}{{prefix:u8;value:{name};suffix:u8;}}')
 body=f'var value={name}{{}};var wrapper=Wrapper{name}{{}};unsafe{{let base=cast[u64](&raw value);let outer=cast[u64](&raw wrapper);io.println(sizeof({name}));'
 expected.append(c.sizeof(native))
 for field,_,_ in fields:
  body+=f'io.println(cast[u64](&raw value.{field})-base);';expected.append(getattr(native,field).offset)
 body+=f'io.println(sizeof(Wrapper{name}));io.println(cast[u64](&raw wrapper.value)-outer);io.println(cast[u64](&raw wrapper.suffix)-outer);}}'
 expected.extend([c.sizeof(wrapper),wrapper.value.offset,wrapper.suffix.offset])
 functions.append(f'fn test_{name}(){{'+body+'}');calls.append(f'test_{name}();')
 choices.append((name,native))
primitives=[('void',0),('i8',1),('u8',1),('i16',2),('u16',2),('i32',4),('u32',4),('i64',8),('u64',8),('isize',8),('usize',8),('f32',4),('f64',8),('bool',1),('string',8),('*void',8),('own[i64]',8),('&i64',8),('&mut i64',8),('[]i64',16),('[0]i64',0),('[65536]u64',524288)]
for ty,size in primitives:calls.append(f'io.println(sizeof({ty}));');expected.append(size)
declarations += ['struct Pair{a:i64;b:i64;}','enum Choice{None;Small(u8);Big(Pair);}']
# Explicit byte reads check the declared tag/payload offset and target byte order.
calls.append('''io.println(sizeof(Choice));var choice=Choice.None;unsafe{let words=cast[*i64](&raw choice);io.println(words[0]);}
choice=Choice.Small(17);unsafe{let bytes=cast[*u8](&raw choice);io.println(bytes[0]);io.println(bytes[8]);}
choice=Choice.Big(Pair{a:41,b:42});unsafe{let words=cast[*i64](&raw choice);io.println(words[0]);io.println(words[1]);io.println(words[2]);}
var number:u64=0x0102030405060708;unsafe{let bytes=cast[*u8](&raw number);io.println(bytes[0]);io.println(bytes[7]);}
''')
expected += [24,0,1,17,2,41,42,8,1]
program='import "std/io";'+''.join(declarations+functions)+'fn main(){'+''.join(calls)+'}'
expected=''.join(str(n)+'\n' for n in expected)
invalid=['struct S{a:[65536]u64;b:u8;}fn main(){}','struct S{a:S;}fn main(){}','struct S{a:[1]S;}fn main(){}','enum E{Again(E);}fn main(){}']
def run(command,env):return subprocess.run([str(x) for x in command],cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)
with tempfile.TemporaryDirectory(prefix='cool layout contract ') as temporary:
 directory=Path(temporary);source=directory/'main.cool';binary=directory/'program';wrapper=directory/'bootstrap'
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
   actual=result.stdout.splitlines();wanted=expected.splitlines()
   difference=next(((i,a,b) for i,(a,b) in enumerate(zip(actual,wanted)) if a!=b),None)
   assert (result.returncode,result.stdout,result.stderr)==(0,expected,''),(frontend,engine,result.returncode,result.stderr,difference,len(actual),len(wanted))
  if args.sanitize_runtime and frontend==fronts[0]:
   ir=directory/'program.ll'
   result=run([ROOT/'tools/cool','emit-ir',source,'-o',ir],env);assert result.returncode==0,result
   ir.write_text('\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in ir.read_text().splitlines())+'\n')
   result=run(['clang','-Wno-override-module','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',ir,ROOT/'language/runtime.c','-o',binary],env);assert result.returncode==0,result
   result=run([binary],env);assert (result.returncode,result.stdout,result.stderr)==(0,expected,''),result
  for text in invalid:
   source.write_text(text);result=run([frontend,'check',source],env);assert result.returncode==2,(frontend,text,result)
 print(f'layout: 24 structs plus alignment wrappers, {len(expected.splitlines())} ctypes/representation oracle values and 4 limit/cycle rejections on {len(fronts)} frontends; five engines + O2 PASS')

if args.sanitize_runtime:print('layout: emitted LLVM ASan and C runtime ASan/UBSan PASS')
