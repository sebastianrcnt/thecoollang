#!/usr/bin/env python3
"""Ordered owning map: Python dict oracle plus independent AVL shape audit."""
import argparse
import json
import math
import os
from pathlib import Path
import random
import subprocess
ROOT=Path(__file__).resolve().parents[1]
AUDIT='''package map;
import text "std/text";
struct Audit {count:usize;height:i64;}
fn inspect(node:*Node[own[i64]],lower:*text.Text,upper:*text.Text)->Audit{
 unsafe{
  if(node==null){return Audit{};}
  if(lower!=null){assert(text.compare(&(*node).key,&*lower)>0);}
  if(upper!=null){assert(text.compare(&(*node).key,&*upper)<0);}
  let left=inspect(pointer[own[i64]](&raw (*node).left),lower,&raw (*node).key);
  let right=inspect(pointer[own[i64]](&raw (*node).right),&raw (*node).key,upper);
  assert(left.height-right.height<=1);assert(right.height-left.height<=1);
  var h=left.height;if(right.height>h){h=right.height;}h=h+1;
  assert((*node).height==h);return Audit{count:left.count+right.count+1,height:h};
 }
}
pub fn audit(map:&Map[own[i64]]){
 unsafe{let found=inspect(root_pointer[own[i64]](map),null,null);assert(found.count==(*map).count);}
}
'''
PRELUDE='''package main;import m "example.test/map-model/internal";import t "std/text";import r "std/result";import o "std/option";import v "std/vector";import "std/mem";import "std/io";
fn key(value:string)->t.Text{return r.value_or[t.Text,t.Utf8Error](t.from_literal(value),t.create());}
fn main(){ {var map=m.create[own[i64]]();
'''

def literal(value):return json.dumps(value,ensure_ascii=False)

def generate(seed,steps):
 rng=random.Random(seed);model={};source=[PRELUDE]
 domain=[f'key-{i:03}' for i in range(80)]+['','한글','🙂','é','é','x'*70,'line\nbreak']
 operations=[]
 for order in ([2,1,0],[0,1,2],[2,0,1],[0,2,1],[3,1,5,0,2,4,6]):
  operations += [('insert',domain[i]) for i in order]
  operations += [('remove',domain[order[0]])]+[('remove',domain[i]) for i in order[1:]]
 operations += [('insert',k) for k in domain[:80]]+[('remove',k) for k in domain[:40]]
 operations += [(rng.choice(['insert']*6+['remove']*3+['mutate','move','clear']),rng.choice(domain)) for _ in range(steps)]
 for index,(operation,k) in enumerate(operations):
  value=rng.randrange(-100000,100001)
  source += [f'// seed={seed}, operation={index}: {operation} {literal(k)}','{']
  if operation=='insert':
   old=model.get(k,-999999);model[k]=value
   source += [f'let old=o.value_or[own[i64]](m.insert[own[i64]](&mut map,key({literal(k)}),new[i64]({value})),new[i64](-999999));assert(*old=={old});']
  elif operation=='remove':
   old=model.pop(k,-999999)
   source += [f'let search=key({literal(k)});let old=o.value_or[own[i64]](m.remove[own[i64]](&mut map,&search),new[i64](-999999));assert(*old=={old});']
  elif operation=='mutate' and k in model:
   model[k]=value
   source += [f'let search=key({literal(k)});**m.at_mut[own[i64]](&mut map,&search)={value};']
  elif operation=='move':source += ['let transferred=move map;map=move transferred;']
  elif operation=='clear':model.clear();source += ['m.clear[own[i64]](&mut map);']
  source += ['}',f'assert(m.len[own[i64]](&map)=={len(model)});m.audit(&map);']
  allocated=sum(2+math.ceil(len(s.encode())/32) for s in model)
  source += [f'assert(mem.owner_count()=={allocated});']
  for item in sorted(set([k,*list(model)[:1],*list(model)[-1:]])):
   present=item in model
   source += ['{',f'let search=key({literal(item)});assert(m.contains[own[i64]](&map,&search)=={str(present).lower()});']
   if present:source += [f'assert(**m.at[own[i64]](&map,&search)=={model[item]});']
   source += ['}']
  if index%20==0 or index==len(operations)-1:
   source += ['{let keys=m.keys[own[i64]](&map);',f'assert(v.len[t.Text](&keys)=={len(model)});']
   for position,item in enumerate(sorted(model,key=lambda s:s.encode())):
    source += ['{',f'let expected=key({literal(item)});assert(t.equal(v.at[t.Text](&keys,{position}),&expected));','}']
   source += ['}']
 source += ['}assert(mem.owner_count()==0);io.println(123);}']
 return '\n'.join(source)


def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sanitize',action='store_true');parser.add_argument('--seeds',default='7,2026');parser.add_argument('--steps',type=int,default=120);args=parser.parse_args()
 for seed in map(int,args.seeds.split(',')):
  directory=ROOT/f'build/map-tests/seed-{seed}';directory.mkdir(parents=True,exist_ok=True)
  def run(command,expected=None):
   p=subprocess.run([str(x) for x in command],cwd=directory,capture_output=True,text=True,timeout=180,env={**os.environ,'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'})
   assert p.returncode==0 and p.stderr=='' and (expected is None or p.stdout==expected),(command,p)
  if not (directory/'cool.mod').exists():run([ROOT/'tools/cool','mod','init','example.test/map-model'])
  package=directory/'internal';package.mkdir(exist_ok=True)
  (package/'map.cool').write_text((ROOT/'stdlib/map/map.cool').read_text())
  (package/'audit.cool').write_text(AUDIT)
  (directory/'main.cool').write_text(generate(seed,args.steps))
  for engine in ('tree','interp','jit','llvm','llvm-jit'):run([ROOT/'tools/cool','run','--backend',engine,'.'],'123\n')
  binary=directory/'program';run([ROOT/'tools/cool','build','--release','-o',binary]);run([binary],'123\n')
  if args.sanitize:
   ir=directory/'map.ll';instrumented=directory/'map-asan.ll';run([ROOT/'tools/cool','emit-ir','-o',ir])
   ir.write_text('\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in ir.read_text().splitlines())+'\n')
   run(['clang','-Wno-override-module','-O1','-fsanitize=address','-S','-emit-llvm',ir,'-o',instrumented]);assert '__asan_report_load' in instrumented.read_text()
   run(['clang','-Wno-override-module','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',ir,ROOT/'language/runtime.c','-o',binary]);run([binary],'123\n')
  print(f'map model seed {seed}: dict values, sorted keys, AVL bounds/heights/count and exact owner counts across five engines + O2'+(' + ASan/UBSan' if args.sanitize else '')+' PASS',flush=True)


if __name__=='__main__':main()
