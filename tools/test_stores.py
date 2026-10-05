#!/usr/bin/env python3
"""Checked stores contracts retain external provenance at caller destination lifetimes."""
import argparse, os, shlex, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);p.add_argument('--sanitize-runtime',action='store_true');args=p.parse_args()
prelude='''import "std/io";import "std/mem";
struct View{r:&i64;}
struct Mut{r:&mut i64;}
struct Mixed{r:&i64;p:own[i64];}
enum Choice{None;Some(&i64);}
fn set(dst:&mut View,src:&i64) stores(dst,src){(*dst).r=src;}
fn mset(dst:&mut Mut,src:&mut i64) stores(dst,src){(*dst).r=src;}
fn refset(dst:&mut &i64,src:&i64) stores(dst,src){*dst=src;}
fn slicep(dst:&mut []i64,src:[]i64) stores(dst,src){*dst=src;}
fn owners(dst:&mut own[View],src:own[View]) stores(dst,src){*dst=move src;}
fn replace[T](dst:&mut T,src:T) stores(dst,src){*dst=move src;}
fn forward(dst:&mut View,src:&i64) stores(dst,src){set(dst,src);}
fn returned(dst:&mut View,src:&i64)->&i64 borrows(dst,src) stores(dst,src){set(dst,src);return (*dst).r;}
fn selfset(dst:&mut View) stores(dst,dst){(*dst).r=(*dst).r;}
fn pick(a:&mut View,b:&mut View,yes:bool)->&mut View borrows(a,b){if(yes){return a;}return b;}
fn chain(dst:&mut View,src:&i64,n:i64) stores(dst,src){if(n==0){set(dst,src);}else{chain(dst,src,n-1);}}
fn double(a:&mut View,b:&mut View,src:&i64) stores(a,src) stores(b,src){set(a,src);set(b,src);}
fn reversed(a:&mut View,b:&mut View,src:&i64) stores(b,src) stores(a,src){set(b,src);set(a,src);}
'''
program=prelude+'''fn tests(){var x=7;var y=8;var z=9;
 {var v=View{r:&x};set(&mut v,&y);assert(*v.r==8);forward(&mut v,&z);assert(*v.r==9);selfset(&mut v);}
 {var v=View{r:&x};let r=&mut v;set(r,&y);assert(*(*r).r==8);}
 {var v=View{r:&x};let parent=&mut v;{let child=&mut *parent;set(child,&y);assert(*(*child).r==8);}assert(*(*parent).r==8);}
 {var v=Mut{r:&mut x};let r=&mut v;mset(r,&mut y);*(*r).r=10;}assert(y==10);y=8;
 {var r=&x;refset(&mut r,&y);assert(*r==8);}
 {var a=[2]i64{1,2};var b=[2]i64{3,4};var s=a[:];slicep(&mut s,b[:]);assert(s[0]==3);s[1]=5;assert(s[1]==5);}
 {var p=new[View](View{r:&x});owners(&mut p,new[View](View{r:&y}));assert(mem.owner_count()==1);assert(*(*p).r==8);}
 {var v=View{r:&x};replace[View](&mut v,View{r:&y});assert(*v.r==8);}
 {var v=Mixed{r:&x,p:new[i64](11)};replace[Mixed](&mut v,Mixed{r:&y,p:new[i64](12)});assert(mem.owner_count()==1);assert(*v.p==12);assert(*v.r==8);}
 {var c=Choice.Some(&x);replace[Choice](&mut c,Choice.Some(&y));match(c){Choice.None=>{assert(false);}Choice.Some(r)=>{assert(*r==8);}}}
 {var a=View{r:&x};var b=View{r:&y};set(pick(&mut a,&mut b,true),&z);assert(*a.r==9);assert(*b.r==8);}
 {var v=View{r:&x};let r=returned(&mut v,&y);assert(*r==8);}
 {var a=View{r:&x};var b=View{r:&y};double(&mut a,&mut b,&z);assert(*a.r==9);assert(*b.r==9);reversed(&mut a,&mut b,&x);assert(*a.r==7);assert(*b.r==7);}
 {var v=View{r:&x};chain(&mut v,&y,4);assert(*v.r==8);}
 assert(mem.owner_count()==0);x=18;y=8;io.println(x+y);}
fn main(){tests();assert(mem.owner_count()==0);}
'''
invalid=[
 ('fn bad(dst:&mut View,src:&i64){set(dst,src);}fn main(){}','matching stores'),
 ('fn bad(dst:&mut View,src:&i64) stores(dst,src){let x=1;(*dst).r=&x;}fn main(){}','outlive'),
 ('fn bad(a:&mut View,b:&mut View,src:&i64) stores(a,src){var p=a;p=b;(*p).r=src;}fn main(){}','matching stores'),
 ('fn main(){var x=1;var v=View{r:&x};{var y=2;set(&mut v,&y);}}','outlive'),
 ('fn main(){var x=1;var y=2;var v=View{r:&x};set(&mut v,&y);y=3;}','conflicts'),
 ('fn main(){var x=1;var y=2;var v=View{r:&x};set(&mut v,&y);x=3;}','conflicts'),
 ('fn main(){var x=1;var y=2;var v=View{r:&x};let p=&v;set(&mut v,&y);}','conflicts'),
 ('fn main(){var x=1;var y=2;var v=View{r:&x};let p=&v;set(p,&y);}','incompatible types'),
 ('fn bad(a:&i64,b:&i64)->View borrows(a){var v=View{r:a};set(&mut v,b);return v;}fn main(){}','borrows contract'),
 ('fn bad(dst:&mut View,src:&i64)->&i64 borrows(dst) stores(dst,src){set(dst,src);return (*dst).r;}fn main(){}','borrows contract'),
 ('fn bad(dst:&mut View,src:&i64) stores(dst,src) stores(dst,src){}fn main(){}','duplicate stores'),
 ('fn bad(dst:&mut View,src:&i64) stores(missing,src){}fn main(){}','unknown parameter'),
 ('fn bad(dst:&mut View,src:&i64) stores(dst,missing){}fn main(){}','unknown parameter'),
 ('fn bad(dst:&View,src:&i64) stores(dst,src){}fn main(){}','stores destination'),
 ('fn bad(dst:&mut i64,src:&i64) stores(dst,src){}fn main(){}','stores destination'),
 ('fn bad(dst:&mut View,src:i64) stores(dst,src){}fn main(){}','stores source'),
 ('extern "C" fn bad(dst:&mut View,src:&i64) stores(dst,src);fn main(){}','checked Cool body'),
 ('fn bad[T](dst:&mut T,src:T) stores(dst,missing){}fn main(){}','unknown parameter'),
 ('fn main(){var x=1;var y=2;var r=&x;{var z=3;refset(&mut r,&z);}}','outlive'),
 ('fn main(){var a=[1]i64{1};var s=a[:];{var b=[1]i64{2};slicep(&mut s,b[:]);}}','outlive'),
 ('fn main(){var x=1;var y=2;var p=new[View](View{r:&x});{var z=3;owners(&mut p,new[View](View{r:&z}));}}','outlive'),
 ('fn bad[T](dst:&View,src:T) stores(dst,src){}fn main(){}','stores destination'),
 ('fn bad[T](dst:&mut T,src:i64) stores(dst,src){}fn main(){}','stores source'),
 ('fn main(){var x=1;var y=2;var v=View{r:&x};{var w=View{r:&y};var z=3;set(pick(&mut v,&mut w,true),&z);}}','outlive'),
 ('fn bad(v:View)->&View borrows(v){return &v;}fn main(){}','outlive'),
 ('fn main(){var x=1;var y=2;var v=Mut{r:&mut x};mset(&mut v,&mut y);y=3;}','conflicts'),
]
def run(command,env,input=None):return subprocess.run(list(map(str,command)),cwd=ROOT,env=env,input=input,capture_output=True,text=True,timeout=180)
with tempfile.TemporaryDirectory(prefix='cool borrowed heaps ') as temporary:
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
   assert (r.returncode,r.stdout,r.stderr)==(0,'26\n',''),(front,engine,r)
  diagnostics=[diagnostic for _,diagnostic in invalid]
  for body,diagnostic in zip([body for body,_ in invalid],diagnostics):
   code=prelude+body;source.write_text(code);r=run([front,'check',source],env)
   assert r.returncode==2 and diagnostic in r.stderr,(front,diagnostic,code,r)
  # Independent model: both old and installed roots remain protected until
  # the destination holder dies. Shared payloads permit reads, exclusive do not.
  for exclusive in (False,True):
   ref='&mut ' if exclusive else '&';kind='Mut' if exclusive else 'View';setter='mset' if exclusive else 'set'
   for receiver in ('temporary','named','child','computed'):
    prefix='var v='+kind+'{r:'+ref+'x};'
    if receiver=='computed' and exclusive:continue
    if receiver=='temporary':call=f'{setter}(&mut v,{ref}y);'
    if receiver=='named':call=f'let r=&mut v;{setter}(r,{ref}y);'
    if receiver=='child':call=f'let r=&mut v;{{let c=&mut *r;{setter}(c,{ref}y);}}'
    if receiver=='computed':call='var w=View{r:&x};set(pick(&mut v,&mut w,true),&y);'
    for rootname in ('x','y'):
     for write in (False,True):
      expected=2 if write or exclusive else 0
      action=f'{rootname}=3;' if write else f'let observed={rootname};'
      source.write_text(prelude+'fn main(){var x=1;var y=2;'+prefix+call+action+'}')
      r=run([front,'check',source],env);assert r.returncode==expected,(front,receiver,exclusive,rootname,write,r)
      if expected:assert 'conflicts' in r.stderr,r
  # Runtime failure may occur after the store: retain installed provenance.
  repl='struct View{r:&i64;}\nfn set(dst:&mut View,src:&i64) stores(dst,src){(*dst).r=src;}\nvar x=7;\nvar y=8;\nvar v=View{r:&x};\n'
  r=run([front,'repl-quiet'],env,repl+'{set(&mut v,&y);assert(false);}\n*v.r\nx=2;\ny=2;\n:forget y\n:forget v\nx=2;\ny=2;\ny\n:quit\n')
  assert r.returncode==0 and r.stdout=='8\n2\n' and r.stderr.count('error:')==4,r
  r=run([front,'repl-quiet'],env,repl+'let receiver=&mut v;\nfn fail(dst:&mut View,src:&i64) stores(dst,src){set(dst,src);assert(false);}\nfail(receiver,&y);\n*(*receiver).r\ny=2;\n:forget v\n:forget receiver\n:forget v\ny=2;\ny\n:quit\n')
  assert r.returncode==0 and r.stdout=='8\n2\n' and r.stderr.count('error:')==3,r
  # Body replacement is compatible only if its stored-provenance ABI matches.
  r=run([front,'repl-quiet'],env,repl+'fn caller(dst:&mut View,src:&i64) stores(dst,src){set(dst,src);}\ncaller(&mut v,&y);\ncaller(&mut v,&y);\nfn set(dst:&mut View,src:&i64){(*dst).r=src;}\ncaller(&mut v,&y);\n*v.r\n:quit\n')
  assert r.returncode==0 and r.stdout=='8\n' and r.stderr.count('error:')==1 and 'signature' in r.stderr,r
  # Failed compilation must roll back attempted source provenance.
  r=run([front,'repl-quiet'],env,repl+'set(&mut v,&y);missing;\ny=9;\n*v.r\nx=2;\n:forget v\nx=2;\nx\n:quit\n')
  assert r.returncode==0 and r.stdout=='7\n2\n' and r.stderr.count('error:')==2,r
print(f'stores: shared/exclusive/reference/slice/owning/generic/enum replacement, forwarding/recursion/computed receivers/returns; {len(invalid)} lifetime/contract/capability rejections; five engines + O2 on {len(fronts)} frontends PASS')
