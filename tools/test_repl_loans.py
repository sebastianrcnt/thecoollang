#!/usr/bin/env python3
"""Persistent REPL references, slice roots, release and partial-error recovery."""
from pathlib import Path
import random
import argparse
import os
import subprocess
ROOT=Path(__file__).resolve().parents[1]
FRONTS=[[ROOT/'build/cool-compiler'],[ROOT/'build/coolc','--run',ROOT/'build/language.BIN']]
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sanitize',action='store_true');args=parser.parse_args()
if args.sanitize:
 directory=ROOT/'build/repl-loans-asan';directory.mkdir(parents=True,exist_ok=True)
 ir=directory/'compiler.ll';checked=directory/'instrumented.ll';binary=directory/'cool-compiler'
 ir.write_text('\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in (ROOT/'build/compiler-stage2.ll').read_text().splitlines())+'\n')
 subprocess.run(['clang','-Wno-override-module','-O1','-fsanitize=address','-S','-emit-llvm',ir,'-o',checked],check=True,timeout=180)
 assert '__asan_report_load' in checked.read_text() and '__asan_report_store' in checked.read_text()
 subprocess.run(['clang','-Wno-override-module','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',ir,ROOT/'compiler/host.c',ROOT/'language/runtime.c','-lffi','-o',binary],check=True,timeout=180)
 FRONTS.append([binary])
CASES=[
('borrow contracts cannot change under live callers', 'fn first(a:&i64,b:&i64)->&i64 borrows(a){return a;}\nfn caller(a:&i64,b:&i64)->&i64 borrows(a){return first(a,b);}\nvar x=1;\nvar y=2;\n*caller(&x,&y)\n*caller(&x,&y)\n*caller(&x,&y)\n*caller(&x,&y)\nlet r=caller(&x,&y);\nfn first(a:&i64,b:&i64)->&i64 borrows(b){return b;}\ny=3;\nx=4;\n*r\n:forget r\nx=5;\n*caller(&x,&y)\n:quit\n','1\n1\n1\n1\n1\n5\n',{'signature change':1,'conflicts':1}),
('borrowed calls survive JIT and body replacement', 'var x=1;\nlet r=&mut x;\nfn bump(p:&mut i64){*p=*p+1;}\nbump(r);\nbump(r);\nbump(r);\nbump(r);\n*r\nfn bump(p:&mut i64){*p=*p+10;}\nbump(r);\n*r\nx=0;\n:forget r\nx\n:quit\n','5\n15\n15\n',{'conflicts':1}),
('exclusive and explicit release', '''var x=1;
let r=&mut x;
*r=2;
x=3;
*r
:forget x
:forget r
x=4;
x
:forget missing
:quit
''','2\n4\n',{'conflicts':1,'live dependent loans':1,'unknown session binding':1}),
('child reference ancestry', '''var x=1;
let parent=&mut x;
let child=&mut *parent;
*child=7;
*parent=8;
:forget parent
:forget child
*parent
:forget parent
x=9;
x
:quit
''','7\n9\n',{'conflicts':1,'live dependent loans':1}),
('compile rollback', '''var x=1;
let bad=&mut x; extra;
x=3;
x
let r=&mut x;
let conflicting=&x;
*r=5;
*r
:forget r
x=6;
x
:quit
''','3\n5\n6\n',{'one statement':1,'conflicts':1}),
('partial execution keeps assigned roots', '''var a=[2]i64{1,2};
var b=[2]i64{7,8};
var s=a[:];
{s=b[:];assert(false);}
s[0]
b[0]=9;
a[0]=9;
:forget s
a[0]=3;
b[0]=4;
a[0]+b[0]
:quit
''','7\n7\n',{'assertion failed':1,'conflicts':2}),
('failed new reference releases its loans', '''var a=[2]i64{1,2};
let invalid=&mut a[99];
a[0]=3;
a[0]
{let r=&mut a[0];*r=4;assert(false);}
a[0]=5;
a[0]
:quit
''','3\n5\n',{'bounds':1,'assertion failed':1}),
('owned slice and deterministic release', '''import "std/mem";
var p=new[[2]i64]([2]i64{1,2});
let s=(*p)[:];
s[0]=8;
:forget p
s[0]
:forget s
(*p)[0]
:forget p
mem.owner_count()
var a=[1]own[i64]{new[i64](7)};
let owners=a[:];
let r=&mut owners[0];
**r=9;
:forget owners
:forget r
*owners[0]
:forget owners
:forget a
mem.owner_count()
:quit
''','8\n8\n0\n9\n0\n',{'live dependent loans':2}),
('inner storage cannot escape', '''var a=[1]i64{1};
var s=a[:];
{var b=[1]i64{7};s=b[:];assert(false);}
s[0]
:forget s
a[0]=2;
a[0]
:quit
''','1\n2\n',{'outlive local storage':1}),
('forget command validates before mutation', '''var x=1;
:forget x extra
x
:forget x;
var x=2;
x
:unknown
:quit
''','1\n2\n',{'expected one binding':1,'unknown session command':1}),
]
def run(front,source):return subprocess.run([str(x) for x in [*front,'repl-quiet']],input=source,cwd=ROOT,text=True,capture_output=True,timeout=120,env={**os.environ,'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'})
for name,source,expected,errors in CASES:
 for front in FRONTS:
  p=run(front,source)
  assert p.returncode==0 and p.stdout==expected,(name,front,p)
  assert p.stderr.count('error:')==sum(errors.values()) and all(p.stderr.count(message)==count for message,count in errors.items()),(name,front,p)
print(f'REPL loans: {len(CASES)} persistence/release/compile/runtime recovery scenarios on both frontends PASS')
# Independent permission oracle: shared roots permit reads, exclusive roots do
# not; both prohibit writes until the named holder is explicitly forgotten.
lines=[];expected=[];conflicts=0
for seed in (7,42,2026):
 rng=random.Random(seed)
 for n in range(12):
  exclusive=rng.choice((False,True));source=rng.randrange(4)
  names=[f'x{seed}_{n}_{i}' for i in range(4)];holder=f'r{seed}_{n}'
  lines += [f'var {name}={i};' for i,name in enumerate(names)]
  lines += [f'let {holder}=&'+('mut ' if exclusive else '')+names[source]+';']
  for i,name in enumerate(names):
   lines.append(name)
   if i==source and exclusive:conflicts+=1
   else:expected.append(str(i))
   lines.append(name+'=9;')
   if i==source:conflicts+=1
  lines += [':forget '+holder,names[source]+'=11;',names[source]];expected.append('11')
lines+=[':quit','']
for front in FRONTS:
 p=run(front,'\n'.join(lines));assert p.returncode==0 and p.stdout.splitlines()==expected and p.stderr.count('error:')==conflicts and p.stderr.count('conflicts')==conflicts,p
print('REPL loans: 288 independently modeled read/write queries plus release/resumption on both frontends PASS')

if args.sanitize:print('REPL loans: self-hosted compiler loads/stores instrumented with ASan; host/runtime ASan/UBSan PASS')
