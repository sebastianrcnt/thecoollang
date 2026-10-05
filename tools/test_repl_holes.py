#!/usr/bin/env python3
"""Fragmented session storage, stable loans and transactional owner initialization."""
import argparse,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);args=p.parse_args()
fronts=[[ROOT/'build/cool-compiler'],[ROOT/'build/coolc','--run',ROOT/'build/language.BIN']]
if args.frontend:fronts.append([args.frontend.resolve()])
def check(front,name,source,output,errors=()):
 r=subprocess.run([*front,'repl-quiet'],input=source+'\n:quit\n',cwd=ROOT,text=True,capture_output=True,timeout=180)
 assert r.returncode==0 and r.stdout==output,(front,name,r)
 assert r.stderr.count('error:')==len(errors),(front,name,r)
 for error in set(errors):assert r.stderr.count(error)==errors.count(error),(front,name,r)
base='import "std/mem";\nvar large=[16384]i64{};\nvar keeper=42;\nlet r=&mut keeper;\n:forget large\n'
for front in fronts:
 check(front,'large interior region',base+'var next=[16384]i64{};\nnext[16383]=7;\n*r\nnext[16383]\n:forget next\n*r=43;\n:forget r\nkeeper', '42\n7\n43\n')
 check(front,'multiple arrays and returned aggregate',base+'fn make()->[1024]i64{var a=[1024]i64{};a[0]=7;a[1023]=9;return a;}\n{var a=[8192]i64{};var b=[4096]i64{};let c=make();a[0]=11;b[4095]=13;assert(a[0]+b[4095]+c[0]+c[1023]==40);}\n*r','42\n')
 reuse='var next=[8192]own[i64]{};\nnext[8191]=new[i64](7);\n:forget next\n'
 check(front,'repeated owner reuse',base+reuse*160+'*r\nmem.owner_count()','42\n0\n')
 failures='var bad=[8192]own[i64]{};missing;\n'
 check(front,'parse rollback',base+failures*160+'var next=[16384]i64{};\nnext[16383]=7;\nnext[16383]\n*r\nmem.owner_count()','7\n42\n0\n',['one statement per submission']*160)
 failed='fn fail()->own[i64]{let owner=new[i64](1);assert(false);return move owner;}\n'
 poison='var poison=123;\n:forget poison\nvar bad=fail();\n'
 check(front,'owner slots zero before runtime rollback',base+failed+poison*160+'*r\nmem.owner_count()','42\n0\n',['assertion failed']*160)
 check(front,'live root remains protected',base+':forget keeper\nvar next=[16384]i64{};\n*r=44;\n*r\n:forget r\nkeeper','44\n44\n',['live dependent loans'])
 # A live slice and its descriptor reference keep both backing and descriptor addresses.
 sliced='import "std/mem";\nvar hole=[16384]i64{};\nvar array=[2]i64{7,8};\nvar slice=array[:];\nlet view=&mut slice;\n:forget hole\n'
 check(front,'slice and descriptor roots',sliced+'var next=[16384]i64{};\n(*view)[0]=42;\n(*view)[0]\nlen(*view)\n:forget view\n:forget slice\narray[0]+array[1]','42\n2\n50\n')
 # The match scrutinee is anonymous storage and must remain reserved across arm allocations.
 matched='enum Result{Value(own[i64]);}\n'
 body='{match(Result.Value(new[i64](7))){Result.Value(value)=>{var scratch=[8192]i64{};scratch[0]=9;assert(*value+scratch[0]==16);}}}\n'
 check(front,'anonymous match storage and cleanup',base+matched+body*160+'*r\nmem.owner_count()','42\n0\n')
print(f'REPL holes: 8 fragmented-storage/stable-reference/slice/anonymous/owner-zero/rollback cases on {len(fronts)} frontends PASS')
