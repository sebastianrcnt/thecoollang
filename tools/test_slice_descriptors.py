#!/usr/bin/env python3
"""Descriptor and payload loans for shared/exclusive references to slices."""
import argparse, os, shlex, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);p.add_argument('--sanitize-runtime',action='store_true');args=p.parse_args()
prelude='''import "std/io";import "std/mem";
struct View{data:[]i64;tag:i64;}
struct Mixed{data:[]i64;label:&i64;}
fn count(s:&[]i64)->usize{return len(*s);}
fn first(s:&[]i64)->&i64 borrows(s){return &(*s)[0];}
fn mut_first(s:&mut []i64)->&mut i64 borrows(s){return &mut (*s)[0];}
fn same(s:&mut []i64)->&mut []i64 borrows(s){return s;}
fn choose(a:&[]i64,b:&[]i64,yes:bool)->&[]i64 borrows(a,b){if(yes){return a;}return b;}
fn sum(s:&[]i64)->i64{var n=0;for(var i:usize=0;i<len(*s);i=i+1){n=n+(*s)[i];}return n;}
fn mutate(s:&mut []i64){for(var i:usize=0;i<len(*s);i=i+1){(*s)[i]=(*s)[i]+1;}}
'''
program=prelude+'''fn main(){
 var a=[3]i64{1,2,3};var b=[3]i64{10,20,30};var label=7;
 {var s=a[:];{let r=&s;assert(count(r)==3);assert((*r)[1]==2);let e=first(r);assert(*e==1);assert(len(*r)==3);}s[0]=10;}
 {var s=a[:];{let r=&mut s;(*r)[0]=42;{let e=&mut (*r)[0];*e=43;assert(len(*r)==3);}(*r)[1]=44;{let e=mut_first(r);*e=43;}}s[2]=45;}
 assert(a[0]==43 && a[1]==44 && a[2]==45);
 {var s=a[:];{let r=same(&mut s);mutate(r);assert(sum(&*r)==135);}assert(s[2]==46);}
 {var holder=View{data:a[:],tag:1};{let r=&holder;assert(len((*r).data)==3);assert((*r).data[0]==44);}holder.data[1]=45;}
 {var mixed=Mixed{data:b[:],label:&label};{let r=&mixed;assert(len((*r).data)==3);assert((*r).data[2]==30);assert(*(*r).label==7);}mixed.data[0]=11;}
 {var sa=a[:];var sb=b[:];let r=choose(&sa,&sb,false);assert((*r)[0]==11);assert(sum(r)==61);}
 {var owners=[2]own[i64]{new[i64](1),new[i64](2)};{var s=owners[:];{let r=&s;assert(len(*r)==2);assert(*(*r)[0]==1);}{let r=&mut s;*(*r)[0]=3;let old=move (*r)[1];(*r)[1]=new[i64](*old+2);}}assert(*owners[0]==3 && *owners[1]==4);}
 assert(mem.owner_count()==0);io.println(42);
}
'''
invalid=[
 'let r=&s;(*r)[0]=9;', 'let r=&s;let e=&mut (*r)[0];',
 '(*choose(&s,&t,true))[0]=9;',
 'var h=Mixed{data:b[:],label:&a[0]};let r=&h;(*r).data[0]=9;',
 'let r=&s;let copy=*r;', 'let r=&s;let copy=(*r)[:];',
 'let r=&s;s[0]=9;', 'let r=&mut s;s[0]=9;', 'let r=&mut s;let x=s[0];',
 'let r=&mut s;let n=len(s);', 'let r=&s;s=b[:];', 'let r=&mut s;s=b[:];',
 'let r=&mut s;*r=b[:];',
 'let r=&mut s;let e=&(*r)[0];(*r)[1]=9;',
 'let r=&mut s;let e=&mut (*r)[0];let x=(*r)[1];',
 'let r=&mut s;let e=&mut (*r)[0];let copy=*r;',
 'let r=&mut s;let e=mut_first(r);let n=len(*r);',
 'let r=choose(&s,&t,true);t[0]=9;', 'let r=choose(&s,&t,true);s[0]=9;',
 'let r=choose(&s,&t,true);let e=&mut (*r)[0];',
 'var h=View{data:b[:],tag:0};let r=&mut h;(*r).data=a[:];',
 'let r=&s;let rr=&r;',
]
whole=[
 'fn bad()->&[]i64 borrows(){var a=[1]i64{1};var s=a[:];return &s;}fn main(){}',
 'fn bad(s:[]i64)->&[]i64 borrows(s){return &s;}fn main(){}',
 'fn bad(s:&[]i64)->[]i64 borrows(s){return *s;}fn main(){}',
 'fn bad(s:&mut []i64,a:[]i64){*s=a;}fn main(){}',
 'fn bad(s:&[][]i64){}fn main(){}',
 'struct Holder{slice:&[]i64;}fn main(){}',
 'fn main(){var a=[1]own[i64]{new[i64](1)};var s=a[:];let r=&s;let old=move (*r)[0];}',
 'fn main(){var a=[1]own[i64]{new[i64](1)};var s=a[:];let r=&s;*(*r)[0]=9;}',
 'fn main(){var p=new[[2]i64]([2]i64{1,2});var s=(*p)[:];let r=&s;let gone=move p;}',
]
def run(command,env,input=None):return subprocess.run(list(map(str,command)),cwd=ROOT,env=env,input=input,capture_output=True,text=True,timeout=180)
with tempfile.TemporaryDirectory(prefix='cool slice descriptors ') as temporary:
 root=Path(temporary);source=root/'main.cool';binary=root/'program';wrapper=root/'bootstrap'
 wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');wrapper.chmod(0o755)
 fronts=[ROOT/'build/cool-compiler',wrapper]
 if args.frontend:fronts.append(args.frontend.resolve())
 for front in fronts:
  env={**os.environ,'COOL_FRONTEND':str(front),'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
  source.write_text(program)
  engines=('tree','interp','jit','llvm','llvm-jit','O2')
  if args.sanitize_runtime and front==fronts[0]:engines+=('ASan/UBSan',)
  for engine in engines:
   if engine=='ASan/UBSan':
    ir=root/'program.ll';r=run([ROOT/'tools/cool','emit-ir',source,'-o',ir],env);assert r.returncode==0,r
    ir.write_text('\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in ir.read_text().splitlines())+'\n')
    checked=root/'instrumented.ll';r=run(['clang','-Wno-override-module','-O1','-fsanitize=address','-S','-emit-llvm',ir,'-o',checked],env);assert r.returncode==0,r
    assert '__asan_report_load' in checked.read_text() and '__asan_report_store' in checked.read_text()
    r=run(['clang','-Wno-override-module','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',ir,ROOT/'language/runtime.c','-o',binary],env);assert r.returncode==0,r
    r=run([binary],env)
   elif engine=='O2':
    r=run([ROOT/'tools/cool','build','--release',source,'-o',binary],env);assert r.returncode==0,r
    r=run([binary],env)
   else:r=run([ROOT/'tools/cool','run','--backend',engine,source],env)
   assert (r.returncode,r.stdout,r.stderr)==(0,'42\n',''),(front,engine,r)
  for code in [prelude+'fn main(){var a=[3]i64{1,2,3};var b=[3]i64{4,5,6};var s=a[:];var t=b[:];'+body+'}' for body in invalid]+[prelude+body for body in whole]:
   source.write_text(code);r=run([front,'check',source],env);assert r.returncode==2,(front,code,r)
  # Independent physical/payload permission model, both reference capabilities.
  queries=0
  for exclusive in (False,True):
   for child in ('none','shared','exclusive'):
    if child=='exclusive' and not exclusive:continue
    for operation in ('len_parent','len_ref','read_parent','write_parent','read_ref','write_ref'):
     allowed=operation=='len_ref' or (operation=='len_parent' and not exclusive)
     if operation=='read_parent':allowed=not exclusive and child!='exclusive'
     if operation=='read_ref':allowed=child!='exclusive'
     if operation=='write_ref':allowed=exclusive and child=='none'
     borrow='let r=&'+('mut ' if exclusive else '')+'s;'
     if child!='none':borrow+='let e=&'+('mut ' if child=='exclusive' else '')+'(*r)[0];'
     access={'len_parent':'let n=len(s);','len_ref':'let n=len(*r);','read_parent':'let n=s[0];','write_parent':'s[0]=9;','read_ref':'let n=(*r)[0];','write_ref':'(*r)[0]=9;'}[operation]
     source.write_text('fn main(){var a=[3]i64{1,2,3};var s=a[:];'+borrow+access+'}')
     r=run([front,'check',source],env);assert r.returncode==(0 if allowed else 2),(front,exclusive,child,operation,allowed,r)
     queries+=1
  r=run([front,'repl-quiet'],env,'var a=[2]i64{1,2};\nvar s=a[:];\nlet r=&mut s;\n(*r)[0]=42;\nlen(*r)\nlen(s)\n:forget s\n:forget r\ns[0]\n:forget s\na[0]\n:quit\n')
  assert r.returncode==0 and r.stdout=='2\n42\n42\n' and r.stderr.count('error:')==2,r
print(f'slice descriptors: mixed/owned storage, shared/exclusive projections and contracts, five engines + O2; {len(invalid)+len(whole)} rejections, {queries} modeled queries and persistent REPL on {len(fronts)} frontends PASS')
