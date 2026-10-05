#!/usr/bin/env python3
"""Typed payload absence affects conflicts; physical roots remain protected."""
import argparse, hashlib, json, os, random, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path,default=ROOT/'build/cool-compiler');p.add_argument('--legacy',action='store_true');p.add_argument('--output',type=Path);args=p.parse_args()
frontend=args.frontend.resolve();env={**os.environ,'COOL_FRONTEND':str(frontend),'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
def run(cmd,**kw):return subprocess.run(list(map(str,cmd)),cwd=ROOT,env=env,text=True,capture_output=True,timeout=180,**kw)
PRELUDE='''import "std/io";
struct Pair{left:&mut i64;right:&mut i64;}
struct Shared{left:&i64;right:&mut i64;}
struct Box{inner:Pair;count:i64;}
struct Quad{f0:&mut i64;f1:&mut i64;f2:&mut i64;f3:&mut i64;}
fn opaque(a:&mut i64,b:&mut i64)->Pair borrows(a,b){return Pair{left:a,right:b};}
'''
POSITIVE=PRELUDE+'''fn main(){
 var a=1;var b=2;
 {var pair=Pair{left:&mut a,right:&mut b};let r=&mut pair;let q=&mut *(*r).left;
  *(*r).right=7;*q=9;assert(*(*r).right==7);assert(*q==9);}
 {var pair=Pair{left:&mut a,right:&mut b};let r=&mut pair;let q=&mut *(*r).left;let s=&mut *(*r).right;
  *q=11;*s=12;assert(*q==11);assert(*s==12);}
 {var pair=Shared{left:&a,right:&mut b};let r=&mut pair;let q=&*(*r).left;
  *(*r).right=13;assert(*q==11);assert(*(*r).right==13);}
 {var box=Box{inner:Pair{left:&mut a,right:&mut b},count:0};let r=&mut box;let q=&mut *(*r).inner.left;
  *(*r).inner.right=14;(*r).count=3;assert(*q==11);assert((*r).count==3);}
 io.println(42);
}
'''
NEGATIVE=[
 'var pair=Pair{left:&mut a,right:&mut b};let r=&mut pair;let q=&mut *(*r).left;*(*r).left=7;',
 'var pair=Pair{left:&mut a,right:&mut b};let r=&mut pair;let q=&mut *(*r).left;let value=*(*r).left;',
 'var pair=Pair{left:&mut a,right:&mut b};let r=&mut pair;let q=&mut *(*r).left;a=7;',
 'var pair=Pair{left:&mut a,right:&mut b};let r=&mut pair;let q=&mut *(*r).left;pair=Pair{left:&mut a,right:&mut b};',
 'var pair=Pair{left:&mut a,right:&mut b};let r=&mut pair;let q=&mut *(*r).right;*(*r).right=7;',
 'var pair=opaque(&mut a,&mut b);let r=&mut pair;let q=&mut *(*r).left;*(*r).right=7;',
 'var array=[2]&mut i64{&mut a,&mut b};let r=&mut array;let q=&mut *(*r)[0];*(*r)[1]=7;',
]
# Deterministic independent fixture: four distinct root bindings, permuted
# initializer order and field/root mappings. Only the held field is blocked.
rng=random.Random(20261005);seeded=[];seeded_negative=[]
for i in range(24):
 roots=list('abcd');rng.shuffle(roots);order=list(range(4));rng.shuffle(order);held=rng.randrange(4)
 setup='var a=1;var b=2;var c=3;var d=4;var quad=Quad{'+','.join(f'f{j}:&mut {roots[j]}' for j in order)+'};let r=&mut quad;let q=&mut *(*r).f'+str(held)+';'
 writes=''.join(f'*(*r).f{j}={100+i*4+j};assert(*(*r).f{j}=={100+i*4+j});' for j in range(4) if j!=held)
 seeded.append('{'+setup+writes+f'*q={200+i};assert(*q=={200+i});'+'}')
 seeded_negative.append(setup+f'*(*r).f{held}=99;')
POSITIVE=POSITIVE.replace(' io.println(42);',''.join(seeded)+' io.println(42);')
fronts=[[frontend]]
if args.legacy:fronts.append([ROOT/'build/coolc','--run',ROOT/'build/language.BIN'])
with tempfile.TemporaryDirectory(prefix='cool payload access ') as directory:
 tmp=Path(directory);source=tmp/'main.cool';source.write_text(POSITIVE)
 for front in fronts:
  r=run([*front,'check',source]);assert r.returncode==0,r
 for engine in ('tree','interp','jit','llvm','llvm-jit'):
  r=run([ROOT/'tools/cool','run','--backend',engine,source]);assert (r.returncode,r.stdout,r.stderr)==(0,'42\n',''),(engine,r)
 binary=tmp/'native';r=run([ROOT/'tools/cool','build','--release',source,'-o',binary]);assert r.returncode==0,r
 r=run([binary]);assert (r.returncode,r.stdout,r.stderr)==(0,'42\n',''),r
 for body in NEGATIVE+seeded_negative:
  source.write_text(PRELUDE+'fn main(){'+('' if body in seeded_negative else 'var a=1;var b=2;')+body+'}')
  for front in fronts:
   r=run([*front,'check',source]);assert r.returncode==2 and 'conflicts' in r.stderr,(body,r)
 repl='struct Pair{left:&mut i64;right:&mut i64;}\nvar a=1;\nvar b=2;\nvar pair=Pair{left:&mut a,right:&mut b};\nlet r=&mut pair;\nlet q=&mut *(*r).left;\n*(*r).right=7;\n*(*r).left=8;\n*q=9;\n*(*r).right\n*q\n:forget q\n:forget r\n:forget pair\na=10;\na\n:quit\n'
 for front in fronts:
  r=run([*front,'repl-quiet'],input=repl);assert r.returncode==0 and r.stdout=='7\n9\n10\n' and r.stderr.count('error:')==1,r
 report={'frontend_sha256':hashlib.sha256(frontend.read_bytes()).hexdigest(),'legacy_checked':args.legacy,'positive_cases':4,'seed':20261005,'seeded_cases':24,'negative_cases':len(NEGATIVE)+len(seeded_negative),'engines':['tree','interp','jit','llvm','llvm-jit','native-O2'],'method':'Actual typed payload access/reborrow precision; unrelated field roots, shared paths, physical root protection, array union and opaque call conservatism; persistent REPL rejection/recovery/forget. Nested storage restrictions remain.'}
 if args.output:args.output.write_text(json.dumps(report,indent=2)+'\n')
print(f'payload access: 4 disjoint-root and 24 seeded permutation cases, {len(NEGATIVE)+len(seeded_negative)} physical/alias/opaque/element rejections, five engines/O2 and persistent REPL PASS'+(' on both frontends' if args.legacy else ' on production frontend'))
