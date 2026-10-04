#!/usr/bin/env python3
"""Direct argv spawning, inherited process context, exit/signal status and errors."""
import argparse
import os
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
PROGRAM=r'''import p "std/process";import t "std/text";import v "std/vector";import r "std/result";import "std/mem";import "std/io";import "std/os";
fn text(value:string)->t.Text{return r.value_or[t.Text,t.Utf8Error](t.from_literal(value),t.create());}
fn run(program:string,args:&v.Vector[t.Text])->p.Status{
 let name=text(program);
 match(p.run(&name,args)){r.Result[p.Status,p.Error].Ok(status)=>{return status;}r.Result[p.Status,p.Error].Err(error)=>{assert(false);return p.Status.Exit(99);}}
}
fn tests(){
 let empty=v.create[t.Text]();assert(p.success(run("true",&empty)));
 assert(p.success(run("/bin/pwd",&empty)));
 {var args=v.create[t.Text]();v.append[t.Text](&mut args,text("COOL_PROCESS_TEST"));assert(p.success(run("/usr/bin/printenv",&args)));}
 {var args=v.create[t.Text]();v.append[t.Text](&mut args,text("<%s>"));
  v.append[t.Text](&mut args,text(""));v.append[t.Text](&mut args,text("a b"));v.append[t.Text](&mut args,text("한글🙂"));
  v.append[t.Text](&mut args,text("$HOME;$(echo BAD)"));v.append[t.Text](&mut args,text("\"'\\"));v.append[t.Text](&mut args,text("\n"));
  assert(p.success(run("/usr/bin/printf",&args)));
 }
 io.println("");
 {var args=v.create[t.Text]();v.append[t.Text](&mut args,text("-c"));v.append[t.Text](&mut args,text("exit 37"));
  let status=run("/bin/sh",&args);assert(!p.success(status));match(status){p.Status.Exit(code)=>{assert(code==37);}p.Status.Signal(signal)=>{assert(false);}}
 }
 {var args=v.create[t.Text]();v.append[t.Text](&mut args,text("-c"));v.append[t.Text](&mut args,text("kill -TERM $$"));
  let status=run("/bin/sh",&args);assert(!p.success(status));match(status){p.Status.Exit(code)=>{assert(false);}p.Status.Signal(signal)=>{assert(signal==15);}}
 }
 {var args=v.create[t.Text]();for(var i=0;i<300;i=i+1){v.append[t.Text](&mut args,text("some argument"));}assert(p.success(run("true",&args)));}
 for(var i=0;i<20;i=i+1){
  let name=text("/no-such-directory/cool-test");match(p.run(&name,&empty)){
   r.Result[p.Status,p.Error].Ok(status)=>{assert(false);}
   r.Result[p.Status,p.Error].Err(error)=>{match(error){p.Error.Spawn(code)=>{assert(code==2);}p.Error.EmptyProgram=>{assert(false);}p.Error.NulByte(index)=>{assert(false);}p.Error.TooLarge=>{assert(false);}p.Error.Wait(code)=>{assert(false);}}}
  }
 }
 {let name=t.create();match(p.run(&name,&empty)){
  r.Result[p.Status,p.Error].Ok(status)=>{assert(false);}
  r.Result[p.Status,p.Error].Err(error)=>{match(error){p.Error.EmptyProgram=>{}p.Error.Spawn(code)=>{assert(false);}p.Error.NulByte(index)=>{assert(false);}p.Error.TooLarge=>{assert(false);}p.Error.Wait(code)=>{assert(false);}}}
 }}
 for(var bad:usize=0;bad<2;bad=bad+1){
  var name=text("true");var args=v.create[t.Text]();
  if(bad==0){t.append_scalar(&mut name,0);t.append_literal(&mut name,"ignored");}
  else{var arg=text("before");t.append_scalar(&mut arg,0);t.append_literal(&mut arg,"after");v.append[t.Text](&mut args,move arg);}
  match(p.run(&name,&args)){r.Result[p.Status,p.Error].Ok(status)=>{assert(false);}
   r.Result[p.Status,p.Error].Err(error)=>{match(error){p.Error.NulByte(index)=>{assert(index==bad);}p.Error.EmptyProgram=>{assert(false);}p.Error.Spawn(code)=>{assert(false);}p.Error.TooLarge=>{assert(false);}p.Error.Wait(code)=>{assert(false);}}}
  }
 }
 {let name=text(os.arg(0));match(p.run(&name,&empty)){r.Result[p.Status,p.Error].Ok(status)=>{assert(false);}
  r.Result[p.Status,p.Error].Err(error)=>{match(error){p.Error.Spawn(code)=>{assert(code==13);}p.Error.EmptyProgram=>{assert(false);}p.Error.NulByte(index)=>{assert(false);}p.Error.TooLarge=>{assert(false);}p.Error.Wait(code)=>{assert(false);}}}
 }}
}
fn main(){tests();assert(mem.owner_count()==0);io.println("process ok");}
'''

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sanitize',action='store_true');args=parser.parse_args()
 directory=ROOT/'build/process-tests';directory.mkdir(parents=True,exist_ok=True)
 source=directory/'main.cool';source.write_text(PROGRAM)
 denied=directory/'not-executable';denied.write_text('#!/bin/sh\nexit 0\n');denied.chmod(0o600)
 expected=str(ROOT)+'\ninherited value 한글\n<><a b><한글🙂><$HOME;$(echo BAD)><"\'\\><\n>\nprocess ok\n'
 def run(command):return subprocess.run([str(x) for x in command],cwd=ROOT,capture_output=True,text=True,timeout=180,env={**os.environ,'COOL_PROCESS_TEST':'inherited value 한글','ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'})
 def check(p):assert (p.returncode,p.stdout,p.stderr)==(0,expected,''),(p.returncode,p.stdout,p.stderr)
 for engine in ('tree','interp','jit','llvm','llvm-jit'):
  check(run([ROOT/'tools/cool','run','--backend',engine,source,'--',denied]));print('process '+engine+' PASS',flush=True)
 binary=directory/'native';p=run([ROOT/'tools/cool','build','--release',source,'-o',binary]);assert p.returncode==0,(p.stdout,p.stderr);check(run([binary,denied]))
 if args.sanitize:
  ir=directory/'process.ll';instrumented=directory/'process-asan.ll';p=run([ROOT/'tools/cool','emit-ir',source,'-o',ir]);assert p.returncode==0,p
  ir.write_text('\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in ir.read_text().splitlines())+'\n')
  p=run(['clang','-Wno-override-module','-O1','-fsanitize=address','-S','-emit-llvm',ir,'-o',instrumented]);assert p.returncode==0,p;assert '__asan_report_load' in instrumented.read_text()
  # Track explicit raw allocations separately from owned-value allocations.
  # The unchanged runtime uses renamed helpers internally; generated mem.alloc
  # and mem.free calls go through these accounting wrappers.
  runtime=directory/'runtime-tracked.o';shim=directory/'checks.c'
  shim.write_text(r'''#include <stdint.h>
#include <assert.h>
#include <errno.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <dlfcn.h>
extern int64_t base_cool_alloc(int64_t);
extern void base_cool_free(int64_t);
static int64_t raw_live;
static int interrupted;
int64_t cool_alloc(int64_t n){int64_t p=base_cool_alloc(n);raw_live++;return p;}
void cool_free(int64_t p){assert(p && raw_live>0);raw_live--;base_cool_free(p);}
pid_t waitpid(pid_t pid,int *status,int options){
 if(!interrupted){interrupted=1;errno=EINTR;return -1;}
 pid_t (*real_wait)(pid_t,int*,int)=(pid_t(*)(pid_t,int*,int))dlsym(RTLD_NEXT,"waitpid");
 assert(real_wait);return real_wait(pid,status,options);
}
__attribute__((destructor)) static void check_resources(void){assert(raw_live==0);assert(interrupted);}
''')
  p=run(['clang','-O1','-g','-fsanitize=address,undefined','-Dcool_alloc=base_cool_alloc','-Dcool_free=base_cool_free','-c',ROOT/'language/runtime.c','-o',runtime]);assert p.returncode==0,p
  p=run(['clang','-Wno-override-module','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',ir,runtime,shim,'-o',binary]);assert p.returncode==0,p;check(run([binary,denied]))
 print('process: direct argv/Unicode/empty arguments, PATH/cwd/environment, 300 args, exit/signal/start errors, NUL rejection and owner cleanup; O2'+(' + ASan/UBSan, raw-buffer accounting and interrupted-wait retry' if args.sanitize else '')+' PASS')
if __name__=='__main__':main()
