#!/usr/bin/env python3
"""Observe actual retained-body analysis and compare with a Python call graph."""
import argparse, hashlib, json, os, random, re, shutil, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--sanitize',action='store_true');p.add_argument('--legacy',action='store_true');p.add_argument('--output',type=Path);args=p.parse_args()
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def run(command,**kw):
 r=subprocess.run(list(map(str,command)),cwd=ROOT,text=True,capture_output=True,timeout=240,**kw)
 assert r.returncode==0,r
 return r
# Read the real field through Cool's layout, rather than hard-coding an offset.
HELPER='''export "C" fn AuditRegistrySlot(name:*u8)->**ReplNode {unsafe{
 let ctx=cast[*CompilerState](NativeCompilerState(i64(sizeof(CompilerState))));
 for(var i:i64=1;i<ctx.v_nfun;i=i+1){if(Eq(ctx.v_functions[i].name,name)!=i8(0)){return &raw ctx.v_functions[i].nodes;}}
 return null;
}}
export "C" fn AuditSpecialRegistry(original:*ReplNode, clone:i64)->*ReplNode {unsafe{
 let ctx=cast[*CompilerState](NativeCompilerState(i64(sizeof(CompilerState))));
 let allocation=cast[*ReplNode](CAlloc(i64(sizeof(ReplNode))));allocation.next=original;
 if(clone!=0){var source=original;while(source!=null && source.value.kind!=4){source=source.next;}if(source==null){NativeExit(93);}allocation.value=source.value;}
 else{allocation.value.kind=4;allocation.value.slot=ctx.v_repl_saved_nfun;}
 return allocation;
}}
''' 
SHIM=r'''
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
extern void **AuditRegistrySlot(const char *);
extern void *AuditSpecialRegistry(void *,int64_t);
static void **hidden_slot;static void *saved,*fake;
void AuditAnalyzeTrace(void *function){
 const char *name=*(const char **)function;
 if(hidden_slot){*hidden_slot=saved;hidden_slot=0;free(fake);fake=0;}
 fprintf(stderr,"AUDIT_ANALYZE %s\n",name);
 if(!strcmp(name,"missing_marker") || !strcmp(name,"invalid_marker") || !strcmp(name,"clone_marker")){
  hidden_slot=AuditRegistrySlot("f1");saved=*hidden_slot;
  if(!strcmp(name,"missing_marker"))*hidden_slot=0;
  else{fake=AuditSpecialRegistry(saved,!strcmp(name,"clone_marker"));*hidden_slot=fake;}
 }
}
'''
def closure(edges,seeds):
 reached=set(seeds);pending=list(seeds)
 while pending:
  callee=pending.pop()
  for caller, targets in edges.items():
   if callee in targets and caller not in reached:reached.add(caller);pending.append(caller)
 return reached-set(seeds)
def fixture(edges,seeds,missing=False,unrelated=0,restricted=None):
 source=''
 for name,targets in edges.items():
  contract='a' if name==restricted else 'a,b'
  body='return a;'
  if targets:
   body=''.join('if(false){return '+target+'(a,b);}' for target in targets[:-1])+'return '+targets[-1]+'(a,b);'
  source+='fn '+name+'(a:[]i64,b:[]i64)->[]i64 borrows('+contract+'){'+body+'} '
 source+='\n'
 for i in range(unrelated):source+='fn u%d(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return a;}\n'%i
 source+=''.join('fn '+name+'(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return b;} ' for name in seeds)
 marker=str(missing)+'_marker' if missing else 'audit_marker'
 source+='fn '+marker+'()->i64{return 0;}\n'
 if restricted:source+='var a=[1]i64{7};\nvar b=[1]i64{9};\nf0(a[:],b[:])[0]\nf1(a[:],b[:])[0]\n'
 source+=':quit\n'
 return source,marker
rng=random.Random(20261006)
cases=[('chain',{'f0':[],'f1':['f0'],'f2':['f1'],'f3':['f2']},['f0'],False,256,None),
 ('diamond_duplicates',{'f0':[],'f1':['f0','f0'],'f2':['f0'],'f3':['f1','f2']},['f0'],False,0,None),
 ('mutual_cycle',{'f0':[],'f1':['f0','f2'],'f2':['f1']},['f0'],False,0,None),
 ('multiple_seeds',{'f0':[],'g0':[],'f1':['f0'],'f2':['g0'],'f3':['f1','f2']},['f0','g0'],False,0,None),
 ('missing_registry_fallback',{'f0':[],'f1':['f0'],'f2':[]},['f0'],'missing',2,None),
 ('invalid_slot_fallback',{'f0':[],'f1':['f0'],'f2':[]},['f0'],'invalid',2,None),
 ('value_copy_call_clone',{'f0':[],'f1':['f0'],'f2':[]},['f0'],'clone',2,None),
 ('caller_failure_rollback',{'f0':[],'f1':['f0'],'f2':['f1']},['f0'],False,0,'f1')]
for trial in range(12):
 edges={'f0':[]}
 for i in range(1,17):edges['f%d'%i]=['f%d'%rng.randrange(i) for _ in range(rng.randrange(3))]
 cases.append(('seeded_%d'%trial,edges,['f0'],False,16,None))
with tempfile.TemporaryDirectory(prefix='cool REPL dependencies ') as directory:
 tmp=Path(directory);private=tmp/'compiler';private.mkdir();files=sorted((ROOT/'compiler').glob('*.cool'));hashes={str(f.relative_to(ROOT)):digest(f) for f in files}
 for f in files:shutil.copy2(f,private/f.name)
 refs=private/'16-references.cool';text=refs.read_text();assert text.count('fn AnalyzeReferences(function: *Function)')==1
 refs.write_text(text.replace('fn AnalyzeReferences(function: *Function)','export "C" fn AnalyzeReferences(function: *Function)'))
 (private/'99-audit.cool').write_text(HELPER)
 manifest=tmp/'sources';manifest.write_text(''.join('__main\t'+str(f)+'\n' for f in sorted(private.glob('*.cool'))))
 ir=tmp/'compiler.ll';run([ROOT/'build/cool-compiler','llvm-bundle',manifest,ir])
 text=ir.read_text()
 exported=re.search(r'define void @AnalyzeReferences\([^}]+}',text).group()
 targets=re.findall(r'call [^@\n]*@(__cool_fn[0-9]+)\(',exported)
 assert len(targets)==1,exported
 symbol=targets[0]
 pattern=r'(define i64 @'+symbol+r'\(i64 (%[^,)]+)\) \{\nentry:\n)'
 def instrument(match):
  return match[1]+'  %audit_pointer = inttoptr i64 '+match[2]+' to ptr\n  call void @AuditAnalyzeTrace(ptr %audit_pointer)\n'
 text,n=re.subn(pattern,instrument,text);assert n==1,(symbol,exported)
 text+='\ndeclare void @AuditAnalyzeTrace(ptr)\n'

 if args.sanitize:text='\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in text.splitlines())+'\n'
 ir.write_text(text);flags=['-O2'];env={**os.environ,'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
 if args.sanitize:
  instrumented=tmp/'instrumented.ll';run(['clang','-Wno-override-module','-O1','-fsanitize=address','-S','-emit-llvm',ir,'-o',instrumented]);assert '__asan_report_load' in instrumented.read_text();ir=instrumented;flags=['-O1','-fsanitize=address,undefined','-fno-omit-frame-pointer']
 shim=tmp/'shim.c';shim.write_text(SHIM);frontend=tmp/'frontend'
 run(['clang','-Wno-override-module',*flags,ir,shim,ROOT/'build/compiler-host.o',ROOT/'build/language-runtime.o','-lffi','-o',frontend])
 fronts=[('production',[frontend])]
 if args.legacy:
  legacy=tmp/'language';legacy.mkdir();legacy_files=sorted((ROOT/'language').glob('*.cool'))
  hashes.update({str(f.relative_to(ROOT)):digest(f) for f in legacy_files});files+=legacy_files
  for f in legacy_files:shutil.copy2(f,legacy/f.name)
  refs=legacy/'References.cool';text=refs.read_text();needle='U0 AnalyzeReferences(Function *function){';assert text.count(needle)==1
  trace_code='''ReplNode **audit_hidden_slot;ReplNode *audit_saved,*audit_fake;
U0 AuditAnalyzeTrace(Function *function){I64 i;ReplNode *source;if(audit_hidden_slot){*audit_hidden_slot=audit_saved;audit_hidden_slot=NULL;Free(audit_fake);audit_fake=NULL;}Out("AUDIT_ANALYZE ");Out(function->name);Out("\\n");if(Eq(function->name,"missing_marker") || Eq(function->name,"invalid_marker") || Eq(function->name,"clone_marker")){for(i=1;i<nfun;i++)if(Eq(functions[i].name,"f1")){audit_hidden_slot=&functions[i].nodes;audit_saved=*audit_hidden_slot;if(Eq(function->name,"missing_marker"))*audit_hidden_slot=NULL;else{audit_fake=CAlloc(sizeof(ReplNode));audit_fake->next=audit_saved;if(Eq(function->name,"clone_marker")){source=audit_saved;while(source && source->value.kind!=N_CALL)source=source->next;if(!source)Error("audit CALL node missing");audit_fake->value=source->value;}else{audit_fake->value.kind=N_CALL;audit_fake->value.slot=nfun;}*audit_hidden_slot=audit_fake;}}}
}

'''
  refs.write_text(trace_code+text.replace(needle,needle+'AuditAnalyzeTrace(function);'))
  binary=tmp/'legacy.BIN';run([ROOT/'build/coolc',legacy/'Native.cool',binary],env={**env,'COOLC_COMPILER_BIN':str(ROOT/'coolc/seed/Compiler.BIN')})
  fronts.append(('legacy',[ROOT/'build/coolc','--run',binary]))
 observations=[]
 for front_name,command in fronts:
  for name,edges,seeds,missing,unrelated,restricted in cases:
   source,marker=fixture(edges,seeds,missing,unrelated,restricted);r=run([*command,'repl-quiet'],input=source,env=env)
   stream=r.stdout if front_name=='legacy' else r.stderr;trace=re.findall(r'^AUDIT_ANALYZE (.*)$',stream,re.M);assert marker in trace,(trace,r.stderr);at=trace.index(marker);actual=trace[at+1:];expected=closure(edges,seeds)
   errors=re.sub(r'^AUDIT_ANALYZE .*\n','',r.stderr,flags=re.M)
   if restricted:
    assert errors.count('error:')==1 and 'returned borrow may outlive local storage' in errors,errors
    assert actual==[restricted],actual
   elif missing in ('missing','invalid'):
    assert not errors,errors
    assert set(edges)-set(seeds) <= set(actual) and {'u0','u1'} <= set(actual),actual
   else:
    assert not errors,errors
    assert set(actual)==expected and len(actual)==len(expected),(name,actual,expected)
   assert re.sub(r'^AUDIT_ANALYZE .*\n','',r.stdout,flags=re.M)==('7\n7\n' if restricted else ''),r.stdout
   observations.append(dict(frontend=front_name,name=name,edges=edges,seeds=seeds,expected_callers=sorted(expected),analyzed=actual,errors=errors,unrelated=unrelated,metadata_hook=missing))
   print(front_name,name,'PASS',len(actual),'retained analyses')
 assert hashes=={str(f.relative_to(ROOT)):digest(f) for f in files},'source changed during audit'
 report=dict(source_sha256=hashes,audit_sha256=digest(Path(__file__)),sanitize=args.sanitize,legacy=args.legacy,observations=observations,method='Copied actual compiler sources; export existing AnalyzeReferences, trace its internal emitted function entry through C; legacy adds the equivalent entry trace; independent Python reverse reachability. Metadata hooks temporarily hide a registry or prepend an invalid-slot/value-copy CALL wrapper, restore it before analysis and retain the original AST. Rejected replacement is followed by execution of the restored producer/caller. No production source or semantic guard is bypassed. Fixed seed 20261006.')
 if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
print('REPL dependency reachability PASS')
