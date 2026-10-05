#!/usr/bin/env python3
"""Audit all-parent scoped loan ancestry against an independent graph oracle."""
import argparse, hashlib, json, os, random, re, shlex, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);p.add_argument('--sanitize',action='store_true');p.add_argument('--output',type=Path);args=p.parse_args()
def run(command,**kw):return subprocess.run(list(map(str,command)),cwd=ROOT,capture_output=True,text=True,timeout=180,**kw)
def reachable(edges,target,start,root):
 if target<0 or start<0:return 0
 seen=set();pending=[start]
 while pending:
  node=pending.pop()
  if node in seen:continue
  seen.add(node)
  if node==target:return 1
  pending.extend(parent for holder,parent,r in edges if holder==node and r==root and parent>=0)
 return 0

def graphs():
 yield 'empty graph',1,[]
 yield 'second parent',4,[(0,1,3),(0,2,3)]
 yield 'diamond',5,[(0,1,4),(0,2,4),(1,3,4),(2,3,4)]
 yield 'cycle',4,[(0,1,3),(1,2,3),(2,0,3)]
 yield 'self cycle and disconnected target',4,[(0,0,3),(1,2,3)]
 yield 'root filtering and null parents',5,[(0,1,3),(1,2,4),(2,0,3),(2,-1,3),(-1,1,3),(0,4,-1)]
 for seed in (7,42,2026):
  rng=random.Random(seed)
  for trial in range(6):
   edges=[(rng.randrange(8),rng.randrange(-1,8),rng.randrange(-1,8)) for _ in range(24)]
   yield f'seed {seed} trial {trial}',8,edges
 for depth in (32,128):
  # Duplicate shared paths must not cause exponential repeated visits.
  edges=[(i,i+1,depth) for i in range(depth) for _ in range(2)]
  edges+=[(i,i+2,depth) for i in range(depth-1)]
  yield f'diamond depth {depth}',depth+1,edges

AUDIT='''struct AncestryAudit{locals:*Local;loans:*ReferenceLoan;check:ReferenceCheck;count:i64;}
export "C" fn AncestryNew(count:i64,edge_count:i64,edges:*i64)->*AncestryAudit{unsafe{
 let graph=cast[*AncestryAudit](CAlloc(i64(sizeof(AncestryAudit))));graph.count=count;
 graph.locals=cast[*Local](CAlloc(count*i64(sizeof(Local))));
 graph.loans=cast[*ReferenceLoan](CAlloc(edge_count*i64(sizeof(ReferenceLoan))));
 for(var i:i64=0;i<edge_count;i=i+1){
  let edge=&raw graph.loans[i];
  if(edges[3*i]>=0){edge.holder=&raw graph.locals[edges[3*i]];}
  if(edges[3*i+1]>=0){edge.parent=&raw graph.locals[edges[3*i+1]];}
  if(edges[3*i+2]>=0){edge.root=&raw graph.locals[edges[3*i+2]];}
  edge.next=graph.check.loans;graph.check.loans=edge;
 }
 return graph;
}}
export "C" fn AncestryQuery(graph:*AncestryAudit,target:i64,start:i64,root:i64)->i64{unsafe{
 var holder:*Local=null;var via:*Local=null;var physical:*Local=null;
 if(target>=0){holder=&raw graph.locals[target];}if(start>=0){via=&raw graph.locals[start];}if(root>=0){physical=&raw graph.locals[root];}
 var result=BoolInt(ReferenceAncestor(&raw graph.check,holder,via,physical));
 for(var i:i64=0;i<graph.count;i=i+1){if(graph.locals[i].reference_visit!=0 || graph.locals[i].reference_next!=null){result=result|2;}}
 return result;
}}
export "C" fn AncestryFree(graph:*AncestryAudit){unsafe{Free(cast[*u8](graph.locals));Free(cast[*u8](graph.loans));Free(cast[*u8](graph));}}
'''
DRIVER=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
extern void *AncestryNew(int64_t,int64_t,int64_t*);
extern int64_t AncestryQuery(void*,int64_t,int64_t,int64_t);
extern void AncestryFree(void*);
static int64_t visits,scans;
void AncestryVisit(void){visits++;}
void AncestryScan(void){scans++;}
int main(void){
 long long n,e,q,a,b,r;
 while(scanf("%lld %lld %lld",&n,&e,&q)==3){
  int64_t *edges=calloc((size_t)(3*e+1),sizeof(int64_t));if(!edges)abort();
  for(long long i=0;i<e;i++){if(scanf("%lld %lld %lld",&a,&b,&r)!=3)abort();edges[3*i]=a;edges[3*i+1]=b;edges[3*i+2]=r;}
  void *graph=AncestryNew(n,e,edges);free(edges);
  for(long long i=0;i<q;i++){
   if(scanf("%lld %lld %lld",&a,&b,&r)!=3)abort();visits=scans=0;
   long long value=AncestryQuery(graph,a,b,r);
   printf("%lld %lld %lld\n",value,(long long)visits,(long long)scans);
  }
  AncestryFree(graph);
 }
 return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='cool ancestry graph ') as directory:
 tmp=Path(directory);copied=tmp/'references.cool';source=(ROOT/'compiler/16-references.cool').read_text()
 start=source.index('fn ReferenceAncestor(');end=source.index('fn ReferenceAccess(',start)
 body=source[start:end]
 body,count=re.subn(r'while \(current != null\) \{', 'while (current != null) {\n            AncestryVisit();',body,count=1);assert count==1
 body,count=re.subn(r'while \(loan != null\) \{','while (loan != null) {\n                AncestryScan();',body,count=1);assert count==1
 source='extern "C" fn AncestryVisit();extern "C" fn AncestryScan();\n'+source[:start]+body+source[end:]
 copied.write_text(source);audit=tmp/'audit.cool';audit.write_text(AUDIT)
 files=sorted((ROOT/'compiler').glob('*.cool'));manifest=tmp/'compiler.sources'
 manifest.write_text(''.join('__main\t'+str(copied if file.name=='16-references.cool' else file)+'\n' for file in files)+'__main\t'+str(audit)+'\n')
 frontend=args.frontend.resolve() if args.frontend else ROOT/'build/cool-compiler'
 ir=tmp/'compiler.ll';r=run([frontend,'llvm-bundle',manifest,ir],env={**os.environ,'ASAN_OPTIONS':'halt_on_error=1'});assert r.returncode==0,r
 text=ir.read_text();text,count=re.subn(r'^define i32 @main\(', 'define i32 @UnusedCompilerMain(',text,flags=re.M);assert count==1
 if args.sanitize:text='\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in text.splitlines())+'\n'
 ir.write_text(text)
 objects=['compiler-host.o','language-runtime.o'];digests={name:hashlib.sha256((ROOT/'build'/name).read_bytes()).hexdigest() for name in objects}
 for name in objects:(tmp/name).write_bytes((ROOT/'build'/name).read_bytes());assert hashlib.sha256((tmp/name).read_bytes()).hexdigest()==digests[name]
 driver=tmp/'driver.c';driver.write_text(DRIVER);binary=tmp/'probe'
 flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if args.sanitize else ['-O2']
 link_inputs=[tmp/name for name in objects]
 if args.sanitize:
  checked=tmp/'instrumented.ll'
  r=run(['clang','-Wno-override-module','-O1','-fsanitize=address','-S','-emit-llvm',ir,'-o',checked]);assert r.returncode==0,r
  assert '__asan_report_load' in checked.read_text() and '__asan_report_store' in checked.read_text()
  link_inputs=[ROOT/'compiler/host.c',ROOT/'language/runtime.c']
 r=run(['clang','-Wno-override-module',*flags,'-I'+str(ROOT/'compiler'),'-I'+str(ROOT/'language'),ir,driver,*link_inputs,'-lffi','-o',binary]);assert r.returncode==0,r
 inputs=[];expected=[];labels=[];graph_count=0
 for label,n,edges in graphs():
  for reverse in (False,True):
   ordering=list(reversed(edges)) if reverse else edges
   if n<=8:queries=[(target,start,root) for target in range(-1,n) for start in range(-1,n) for root in range(-1,n)]
   else:queries=[(target,start,n-1) for target in (0,n//2,n-1) for start in range(-1,n)]
   # A second pass on the same graph interleaves previous root selections.
   queries+=list(reversed(queries))
   inputs.append(f'{n} {len(ordering)} {len(queries)}\n'+''.join(f'{a} {b} {r}\n' for a,b,r in ordering)+''.join(f'{a} {b} {r}\n' for a,b,r in queries))
   for target,start,root in queries:
    expected.append(reachable(edges,target,start,root));labels.append((label,reverse,n,len(edges),target,start,root))
   graph_count+=1
 result=run([binary],input=''.join(inputs),env={**os.environ,'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'})
 assert result.returncode==0 and result.stderr=='',result
 rows=[tuple(map(int,line.split())) for line in result.stdout.splitlines()];assert len(rows)==len(expected),(len(rows),len(expected))
 for row,value,label in zip(rows,expected,labels):
  actual,visits,scans=row;n,e=label[2:4]
  assert actual==value,(label,row,value)
  assert visits<=n and scans<=n*e,(label,row)
 report={'graphs':graph_count,'queries':len(expected),'max_visits':max(row[1] for row in rows),'max_scans':max(row[2] for row in rows),'artifact_sha256':digests,'private_ir_sha256':hashlib.sha256(ir.read_bytes()).hexdigest(),'platform_source_sha256':{str(file.relative_to(ROOT)):hashlib.sha256(file.read_bytes()).hexdigest() for file in [ROOT/'compiler/host.c',*(ROOT/'language'/name for name in ('runtime.c','memory.h','numeric.h','ffi.h','repl_io.h','args.h'))]},'compiler_source_sha256':{str(file.relative_to(ROOT)):hashlib.sha256(file.read_bytes()).hexdigest() for file in files},'source_sha256':hashlib.sha256((ROOT/'compiler/16-references.cool').read_bytes()).hexdigest(),'sanitize':args.sanitize,'method':'Private production-source LLVM copy; independent Python reachability over holder/parent/root triples, reversed loan order, repeated queries on reused graph objects, nulls/cycles/shared DAGs; instrumented node visits <= V and loan inspections <= V*E. Marks and queue links must be cleared after every query. This establishes ancestry reachability, not arbitrary nested stored-reference acceptance.'}
 if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
 # Source-level diamonds exercise the production/legacy analyses, engines and
 # persistent REPL graph ownership in addition to the synthetic oracle.
 wrapper=tmp/'bootstrap';wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');wrapper.chmod(0o755)
 fronts=[ROOT/'build/cool-compiler',wrapper]
 if args.frontend:fronts.append(args.frontend.resolve())
 prelude='import "std/io";fn choose(a:&i64,b:&i64)->&i64 borrows(a,b){if(*a==1){return a;}return b;}\n'
 program=prelude+'fn main(){var x=1;{let e=&mut x;let a=&*e;let b=&*e;let q=choose(a,b);let r=&*q;assert(*r==1);}{var a=&x;var b=&x;a=b;b=a;let q=choose(b,a);assert(*q==1);}x=4;io.println(x);}'
 rejected=[
  'var x=1;let e=&mut x;let a=&*e;let b=&*e;let q=choose(a,b);*e=9;',
  'var x=1;let a=&mut x;let b=&mut x;',
  'var x=1;var y=2;let q=choose(&x,&y);y=3;',
  'var x=1;var y=2;let q=choose(&y,&x);x=3;',
 ]
 file=tmp/'main.cool';binary=tmp/'program'
 for front in fronts:
  env={**os.environ,'COOL_FRONTEND':str(front),'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
  file.write_text(program)
  for engine in ('tree','interp','jit','llvm','llvm-jit','O2'):
   if engine=='O2':
    r=run([ROOT/'tools/cool','build','--release',file,'-o',binary],env=env);assert r.returncode==0,r
    r=run([binary],env=env)
   else:r=run([ROOT/'tools/cool','run','--backend',engine,file],env=env)
   assert (r.returncode,r.stdout,r.stderr)==(0,'4\n',''),(front,engine,r)
  for body in rejected:
   file.write_text(prelude+'fn main(){'+body+'}');r=run([front,'check',file],env=env)
   assert r.returncode==2 and 'conflicts' in r.stderr,(front,body,r)
  repl=prelude.replace('import "std/io";','')+'var x=1;\nlet a=&x;\nlet b=&x;\nlet q=choose(a,b);\n*q\n:forget a\n:forget q\n:forget a\n:forget b\nx=2;\nx\n:quit\n'
  r=run([front,'repl-quiet'],input=repl,env=env)
  assert r.returncode==0 and r.stdout=='1\n2\n' and r.stderr.count('error:')==1 and 'dependent loans' in r.stderr,(front,r)
 print(f'reference ancestry: {graph_count} root-filtered graphs, {len(expected)} oracle queries, cycles/nulls/reversed parents/reused marks and depth-128 DAG bounds'+(' with ASan/UBSan' if args.sanitize else '')+' PASS')

print(f'ancestry source: shared/mutual/common-exclusive diamonds, four live-loan conflicts, five engines + O2 and REPL dependent release on {len(fronts)} frontends PASS')
