#!/usr/bin/env python3
"""Borrowed vector values preserve capabilities, lifetime roots and slot cleanup."""
import argparse,hashlib,json,os,shlex,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);p.add_argument('--sanitize-runtime',action='store_true');p.add_argument('--output',type=Path);args=p.parse_args()
sources=sorted((ROOT/'compiler').glob('*.cool'))+sorted((ROOT/'language').glob('*.cool'))+sorted((ROOT/'stdlib').rglob('*.cool'))
def source_hashes():return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
hashes=source_hashes()
values=[((i*37+11)%101)-50 for i in range(65)]
prefix='import v "std/vector";import o "std/option";import "std/mem";import "std/io";struct View{r:&i64;}\n'
program=prefix+'fn main(){\nvar backing=[65]i64{'+','.join(map(str,values))+'};\n{var items=v.create[&i64]();\n'
for i,n in enumerate(values):program+=f'items.append(&backing[{i}]);assert(items.len()=={i+1});assert(mem.owner_count()=={(i+32)//32});assert(**items.at({i})=={n});\n'
program+='{var it=items.iter();\n'
for n in values:program+=f'match(it.next()){{o.Option[& &i64].None=>{{assert(false);}}o.Option[& &i64].Some(r)=>{{assert(**r=={n});}}}}\n'
program+='assert(it.remaining()==0);match(it.next()){o.Option[& &i64].None=>{}o.Option[& &i64].Some(r)=>{assert(false);}}}\n'
for remaining,n in reversed(list(enumerate(values))):
 program+=f'{{let last=items.pop();match(move last){{o.Option[&i64].None=>{{assert(false);}}o.Option[&i64].Some(r)=>{{assert(*r=={n});}}}}}}assert(items.len()=={remaining});assert(mem.owner_count()=={(remaining+31)//32});\n'
program+='items.append(&backing[0]);items.clear();assert(items.len()==0);assert(mem.owner_count()==0);}\nbacking[0]=99;\n'
program+='''var old_source=7;var new_source=9;
 {var items=v.create[&i64]();items.append(&old_source);items.append(&old_source);items.append(&old_source);
  {let removed=items.pop();match(move removed){o.Option[&i64].None=>{assert(false);}o.Option[&i64].Some(r)=>{assert(*r==7);}}}
  assert(items.len()==2 && mem.owner_count()==1);items.append(&new_source);assert(**items.at(2)==9);assert(mem.owner_count()==1);items.clear();}
 old_source=8;new_source=10;assert(mem.owner_count()==0);
var a=7;var b=8;
 {var items=v.create[&mut i64]();items.append(&mut a);items.append(&mut b);**items.at_mut(0)=17;
  {var it=items.iter_mut();match(it.next()){o.Option[&mut &mut i64].None=>{assert(false);}o.Option[&mut &mut i64].Some(r)=>{**r=**r+1;}}}
  {let last=items.pop();match(move last){o.Option[&mut i64].None=>{assert(false);}o.Option[&mut i64].Some(r)=>{*r=19;}}}
  items.clear();}
 assert(a==18 && b==19);assert(mem.owner_count()==0);
 {var items=v.create[View]();items.append(View{r:&a});assert(*(*items.at(0)).r==18);items.clear();}
 {var items=v.create[own[View]]();items.append(new[View](View{r:&a}));assert(mem.owner_count()==2);
  {let p=items.at(0);assert(*(**p).r==18);}
  {let popped=items.pop();match(move popped){o.Option[own[View]].None=>{assert(false);}o.Option[own[View]].Some(p)=>{assert(*(*p).r==18);assert(mem.owner_count()==1);}}}
  assert(mem.owner_count()==0);items.append(new[View](View{r:&b}));items.clear();}
 assert(mem.owner_count()==0);a=20;b=21;io.println(123);}
'''
negative=[
 ('shared_at_mutable_payload','var a=1;var items=v.create[&mut i64]();items.append(&mut a);**items.at(0)=2;','shared reference'),
 ('shared_iterator_mutable_payload','var a=1;var items=v.create[&mut i64]();items.append(&mut a);var it=items.iter();match(it.next()){o.Option[& &mut i64].None=>{}o.Option[& &mut i64].Some(r)=>{**r=2;}}','shared reference'),
 ('installed_source_mutation','var a=1;var items=v.create[&i64]();items.append(&a);a=2;','conflicts'),
 ('short_source','var items=v.create[&i64]();{var a=1;items.append(&a);}','outlive'),
 ('popped_source_mutation','var a=1;var items=v.create[&mut i64]();items.append(&mut a);let last=items.pop();a=2;','conflicts'),
 ('live_element_growth','var a=1;var b=2;var items=v.create[&i64]();items.append(&a);let r=items.at(0);items.append(&b);','conflicts'),
 ('iterator_parent_suspension','var a=1;var items=v.create[&mut i64]();items.append(&mut a);var it=items.iter_mut();let r=it.next();let again=it.next();','conflicts'),
]
negative.extend([
 ('live_element_pop','var a=1;var items=v.create[&i64]();items.append(&a);let r=items.at(0);let last=items.pop();','conflicts'),
 ('live_element_clear','var a=1;var items=v.create[&i64]();items.append(&a);let r=items.at(0);items.clear();','conflicts'),
 ('reused_slot_source_mutation','var a=1;var b=2;var items=v.create[&i64]();items.append(&a);items.append(&a);{let removed=items.pop();}items.append(&b);b=3;','conflicts'),
])

def run(command,env):return subprocess.run(list(map(str,command)),cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)
observations=[]
with tempfile.TemporaryDirectory(prefix='cool borrowed vector ') as directory:
 root=Path(directory);source=root/'main.cool';binary=root/'program';wrapper=root/'seed'
 wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');wrapper.chmod(0o755)
 fronts=[ROOT/'build/cool-compiler',wrapper]
 if args.frontend:fronts.append(args.frontend.resolve())
 for front in fronts:
  env={**os.environ,'COOL_FRONTEND':str(front),'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
  source.write_text(program)
  for engine in ('tree','interp','jit','llvm','llvm-jit','O2')+ (('ASan/UBSan',) if args.sanitize_runtime and front==fronts[0] else ()):
   if engine=='ASan/UBSan':
    ir=root/'program.ll';r=run([ROOT/'tools/cool','emit-ir',source,'-o',ir],env);assert r.returncode==0,r
    ir.write_text('\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in ir.read_text().splitlines())+'\n')
    checked=root/'checked.ll';r=run(['clang','-Wno-override-module','-O1','-fsanitize=address','-S','-emit-llvm',ir,'-o',checked],env);assert r.returncode==0,r
    assert '__asan_report_load' in checked.read_text() and '__asan_report_store' in checked.read_text()
    r=run(['clang','-Wno-override-module','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',ir,ROOT/'language/runtime.c','-o',binary],env);assert r.returncode==0,r
    r=run([binary],env)
   elif engine=='O2':
    r=run([ROOT/'tools/cool','build','--release',source,'-o',binary],env);assert r.returncode==0,r
    r=run([binary],env)
   else:r=run([ROOT/'tools/cool','run','--backend',engine,source],env)
   observations.append(dict(frontend=front.name,engine=engine,exit=r.returncode,stdout=r.stdout,stderr=r.stderr))
   assert (r.returncode,r.stdout,r.stderr)==(0,'123\n',''),(front,engine,r)
  for name,body,diagnostic in negative:
   source.write_text(prefix+'fn main(){'+body+'}');r=run([ROOT/'tools/cool','check',source],env)
   assert r.returncode==2 and diagnostic in r.stderr,(front,name,r)
   observations.append(dict(frontend=front.name,name=name,exit=r.returncode,diagnostic=diagnostic,stderr=r.stderr))
assert hashes==source_hashes(),'source changed during borrowed vector audit'
if args.output:
 args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(dict(source_sha256=hashes,model_values=values,program=program,observations=observations),indent=2)+'\n')
print('borrowed vector: 65 independently modeled shared values/chunk boundaries, shared/mutable iterators, aggregate/owned payloads, pop/clear/reuse and exact owner counts; ten lifetime/capability rejections PASS')
