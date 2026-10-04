#!/usr/bin/env python3
"""Lexical POSIX paths against Python's independent normpath/join implementation."""
import argparse
import json
import os
from pathlib import Path
import posixpath
import random
import subprocess
ROOT=Path(__file__).resolve().parents[1]
PROGRAM='''import p "std/path";import t "std/text";import j "std/json";import r "std/result";import fs "std/fs";import "std/os";import "std/mem";
fn text(value:string)->t.Text{return r.value_or[t.Text,t.Utf8Error](t.from_literal(value),t.create());}
fn row(input:&t.Text)->t.Text{
 let out=j.array_value();
 j.array_push(&mut *out,j.string_value(p.clean(input)));j.array_push(&mut *out,j.string_value(p.name(input)));
 j.array_push(&mut *out,j.string_value(p.parent(input)));j.array_push(&mut *out,j.string_value(p.extension(input)));
 j.array_push(&mut *out,j.boolean_value(p.is_absolute(input)));
 let base=text("root/한글/..");j.array_push(&mut *out,j.string_value(p.join(&base,input)));
 let root=text("/root/한글");j.array_push(&mut *out,j.string_value(p.join(&root,input)));
 let clean=p.clean(input);let again=p.clean(&clean);assert(t.equal(&clean,&again));
 return r.value_or[t.Text,j.ErrorKind](j.encode(&*out),t.create());
}
fn tests(){
 var output=t.create();
 for(var i:usize=1;i<os.arg_count();i=i+1){
  let input=text(os.arg(i));let encoded=row(&input);t.append(&mut output,&encoded);t.append_scalar(&mut output,10);
 }
 assert(r.is_ok[usize,i32](fs.write(os.arg(0),t.as_bytes(&output))));
 var nul=text("a/");t.append_scalar(&mut nul,0);t.append_literal(&mut nul,"/b");
 let cleaned=p.clean(&nul);assert(t.equal(&cleaned,&nul));
 let empty=t.create();let joined=p.join(&empty,&empty);let dot=text(".");assert(t.equal(&joined,&dot));
}
fn main(){tests();assert(mem.owner_count()==0);}
'''

def clean(value):
 value=posixpath.normpath(value)
 return '/'+value.lstrip('/') if value.startswith('/') else value

def expected(value):
 normalized=clean(value)
 name=normalized.rsplit('/',1)[-1] if normalized!='/' else '/'
 parent=clean(posixpath.dirname(normalized))
 dot=name.rfind('.');extension=name[dot:] if 0<dot<len(name)-1 else ''
 return [normalized,name,parent,extension,value.startswith('/'),clean(posixpath.join('root/한글/..',value)),clean(posixpath.join('/root/한글',value))]

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sanitize',action='store_true');args=parser.parse_args()
 cases=['','.', '..','/','//','///','a/','/a//b/.././c/','a/../../b','/../../a','.gitignore','.config.json','file.','file.tar.gz','a.b/../file','../..','../../..','한글/🙂.txt','a/line\nb','back\\slash','.hidden/..','a/..','///../../..']
 rng=random.Random(20261005)
 for _ in range(100):
  cases.append(rng.choice(['','/','//'])+'/'.join(rng.choice(['a','b','..','.','','한글','🙂.txt','.dot','space space']) for _ in range(rng.randrange(20))))
 cases+=['/'.join(['long'+str(i) for i in range(200)]),'/'+'/'.join(['a','..']*200),'🙂'*600+'.json']
 directory=ROOT/'build/path-tests';directory.mkdir(parents=True,exist_ok=True);source=directory/'main.cool';source.write_text(PROGRAM);output=directory/'rows.jsonl'
 def run(command):return subprocess.run([str(x) for x in command],cwd=ROOT,capture_output=True,text=True,timeout=180,env={**os.environ,'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'})
 def check(p):
  assert (p.returncode,p.stdout,p.stderr)==(0,'',''),(p.returncode,p.stdout,p.stderr)
  actual=[json.loads(line) for line in output.read_text().splitlines()];assert len(actual)==len(cases)
  for path,row in zip(cases,actual):assert row==expected(path),(path,row,expected(path))
 for engine in ('tree','interp','jit','llvm','llvm-jit'):
  output.unlink(missing_ok=True);check(run([ROOT/'tools/cool','run','--backend',engine,source,'--',output,*cases]));print('path '+engine+' PASS',flush=True)
 binary=directory/'native';p=run([ROOT/'tools/cool','build','--release',source,'-o',binary]);assert p.returncode==0,(p.stdout,p.stderr);check(run([binary,output,*cases]))
 if args.sanitize:
  ir=directory/'path.ll';instrumented=directory/'path-asan.ll';p=run([ROOT/'tools/cool','emit-ir',source,'-o',ir]);assert p.returncode==0,p
  ir.write_text('\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in ir.read_text().splitlines())+'\n')
  p=run(['clang','-Wno-override-module','-O1','-fsanitize=address','-S','-emit-llvm',ir,'-o',instrumented]);assert p.returncode==0,p;assert '__asan_report_load' in instrumented.read_text()
  p=run(['clang','-Wno-override-module','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',ir,ROOT/'language/runtime.c','-o',binary]);assert p.returncode==0,p;check(run([binary,output,*cases]))
 print(f'path: {len(cases)} oracle cases, normalization/name/parent/extension/join, Unicode/NUL and idempotence; all engines and O2'+(' + ASan/UBSan' if args.sanitize else '')+' PASS')
if __name__=='__main__':main()
