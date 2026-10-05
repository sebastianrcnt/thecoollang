#!/usr/bin/env python3
"""Compare typed payload selection with an independent product-graph oracle."""
import argparse, hashlib, json, os, random, re, shlex, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);p.add_argument('--legacy',action='store_true');p.add_argument('--copy',action='store_true');p.add_argument('--sanitize',action='store_true');p.add_argument('--output',type=Path);args=p.parse_args()
def run(command,**kwargs):
 return subprocess.run(list(map(str,command)),cwd=ROOT,capture_output=True,text=True,timeout=180,**kwargs)
def oracle(nodes,edges,path,start,root,mode,writing):
 if start<0 or root<0:return 0
 pending=[(start,0 if path else -1,int(bool(mode)))];seen=set()
 while pending:
  node,cursor,cap=pending.pop()
  if (node,cursor,cap) in seen:continue
  seen.add((node,cursor,cap));typ,physical,permission=nodes[node]
  if cursor<0:
   if physical==root and (not writing or cap and permission):return 1
  else:
   expected,kind,key,following=path[cursor]
   if typ!=expected:continue
   for source,edge_kind,edge_key,target,barrier in edges:
    if target>=0 and source==node and edge_kind==kind and (kind!=1 or key==edge_key):pending.append((target,following,cap & int(bool(barrier))))
 return 0
AUDIT='''extern "C" fn GraphAlloc(); extern "C" fn GraphDealloc();
fn GraphAuditAllocate(size:i64)->*u8 {unsafe{GraphAlloc();return CAlloc(size);}}
fn GraphAuditFree(value:*u8) {unsafe{GraphDealloc();Free(value);}}
struct GraphAudit { graph:ProvenanceGraph; copies:ProvenanceGraph; nodes:**ProvenanceNode; roots:*Local; count:i64; }
export "C" fn GraphNew(count:i64,edge_count:i64,nodes:*i64,edges:*i64)->*GraphAudit { unsafe {
 let a=cast[*GraphAudit](CAlloc(i64(sizeof(GraphAudit))));a.count=count;
 a.nodes=cast[**ProvenanceNode](CAlloc((count+2)*8));a.roots=cast[*Local](CAlloc(4*i64(sizeof(Local))));
 for(var i:i64=0;i<count;i=i+1){var root:*Local=null;if(nodes[3*i+1]>=0){root=&raw a.roots[nodes[3*i+1]];}a.nodes[i]=ProvenanceNodeNew(&raw a.graph,nodes[3*i],root,nodes[3*i+2]);a.nodes[i].opaque=i%2;}
 for(var i:i64=0;i<edge_count;i=i+1){var target:*ProvenanceNode=null;if(edges[5*i+3]>=0){target=a.nodes[edges[5*i+3]];}if(!ProvenanceEdgeNew(a.nodes[edges[5*i]],edges[5*i+1],edges[5*i+2],target,edges[5*i+4])){NativeExit(3);}}
 let other=cast[*ProvenanceGraph](CAlloc(i64(sizeof(ProvenanceGraph))));
 let foreign=ProvenanceNodeNew(other,0,null,1);
 if(ProvenanceEdgeNew(a.nodes[0],1,0,foreign,1) || ProvenanceEdgeNew(a.nodes[0],5,0,null,1) || ProvenanceEdgeNew(null,1,0,null,1)){NativeExit(4);}
 ProvenanceGraphFree(other);Free(cast[*u8](other));
 // COPY_AUDIT
 return a;
}}
export "C" fn GraphQuery(a:*GraphAudit,count:i64,path:*i64,start:i64,root:i64,mode:i64,writing:i64)->i64 { unsafe {
 let cursors=cast[*ProvenanceCursor](CAlloc((count+1)*i64(sizeof(ProvenanceCursor))));
 for(var i:i64=0;i<count;i=i+1){cursors[i].type=path[4*i];cursors[i].kind=path[4*i+1];cursors[i].key=path[4*i+2];if(path[4*i+3]>=0){cursors[i].next=&raw cursors[path[4*i+3]];}}
 var cursor:*ProvenanceCursor=null;if(count>0){cursor=cursors;}
 var node:*ProvenanceNode=null;if(start>=0){node=a.nodes[start];}
 var target:*Local=null;if(root>=0){target=&raw a.roots[root];}
 let result=BoolInt(ProvenanceQueryRoot(node,cursor,target,mode,writing!=0));Free(cast[*u8](cursors));return result;
}}
export "C" fn GraphEdges(a:*GraphAudit)->i64 { unsafe {var count:i64=0;var node=a.graph.nodes;if(node==null){node=a.copies.nodes;}while(node!=null){var edge=node.edges;while(edge!=null){count=count+1;edge=edge.next;}node=node.next;}return count;}}
export "C" fn GraphNodes(a:*GraphAudit)->i64 {unsafe{var count:i64=0;var node=a.graph.nodes;if(node==null){node=a.copies.nodes;}while(node!=null){count=count+1;node=node.next;}return count;}}
export "C" fn GraphFree(a:*GraphAudit){unsafe{ProvenanceGraphFree(&raw a.graph);ProvenanceGraphFree(&raw a.graph);ProvenanceGraphFree(&raw a.copies);ProvenanceGraphFree(&raw a.copies);Free(cast[*u8](a.nodes));Free(cast[*u8](a.roots));Free(cast[*u8](a));}}
'''
DRIVER=r'''
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
extern void *GraphNew(int64_t,int64_t,int64_t*,int64_t*);
extern int64_t GraphQuery(void*,int64_t,int64_t*,int64_t,int64_t,int64_t,int64_t);
extern int64_t GraphEdges(void*);extern int64_t GraphNodes(void*);
extern void GraphFree(void*);
static int64_t visits,scans,seen,balance;
void GraphAlloc(void){balance++;}void GraphDealloc(void){balance--;if(balance<0)abort();}
void GraphVisit(void){visits++;}void GraphScan(void){scans++;}void GraphSeen(void){seen++;}
static int64_t readnum(void){int64_t n;if(scanf("%"SCNd64,&n)!=1)abort();return n;}
int main(void){int64_t n,e,q;while(scanf("%"SCNd64" %"SCNd64" %"SCNd64,&n,&e,&q)==3){
 int64_t *nodes=calloc(n*3,sizeof(int64_t)),*edges=calloc(e*5+1,sizeof(int64_t));
 for(int64_t i=0;i<n*3;i++)nodes[i]=readnum();for(int64_t i=0;i<e*5;i++)edges[i]=readnum();
 void *a=GraphNew(n,e,nodes,edges);int64_t baseline=balance;if(baseline!=GraphNodes(a)+GraphEdges(a))abort();printf("E %"PRId64" %"PRId64"\n",GraphEdges(a),GraphNodes(a));
 for(int64_t i=0;i<q;i++){int64_t start=readnum(),root=readnum(),mode=readnum(),writing=readnum(),count=readnum();int64_t *path=calloc(count*4+1,sizeof(int64_t));for(int64_t j=0;j<count*4;j++)path[j]=readnum();visits=scans=seen=0;int64_t result=GraphQuery(a,count,path,start,root,mode,writing);if(balance!=baseline)abort();printf("Q %"PRId64" %"PRId64" %"PRId64" %"PRId64"\n",result,visits,scans,seen);free(path);}
 GraphFree(a);if(balance!=0)abort();free(nodes);free(edges);
}return 0;}
'''
def cases():
 nodes=[(10,-1,1),(20,0,0),(20,1,1),(10,-1,1)]
 edges=[(0,1,100,1,1),(0,1,101,2,1),(0,2,0,1,1),(0,2,0,2,0),(0,3,0,3,0),(3,3,0,0,1),(0,4,0,2,1),(0,1,100,1,1),(0,4,0,-1,1)]
 paths=[[]]
 paths += [[(10,k,key,-1)] for k in range(1,6) for key in (0,100,101,999)]
 paths += [[(10,3,0,1),(10,3,0,-1)],[(10,3,0,1),(10,3,0,0)],[(11,1,101,-1)]]
 yield 'fields-elements-barriers-cycles',nodes,edges,paths
 for seed in (7,42,2026):
  rng=random.Random(seed)
  for trial in range(5):
   nodes=[(rng.randrange(3),rng.randrange(-1,4),rng.randrange(2)) for _ in range(7)]
   edges=[(rng.randrange(7),rng.randrange(1,5),rng.randrange(3),rng.randrange(-1,7),rng.randrange(2)) for _ in range(28)]
   paths=[[]]+[[(rng.randrange(3),rng.randrange(1,5),rng.randrange(3),i+1 if i+1<length else -1) for i in range(length)] for length in (1,2,3,5) for _ in range(3)]
   # Include queries which actually follow an edge, as well as wrong types.
   paths += [[(nodes[s][0],k,key,-1)] for s,k,key,t,m in edges]
   yield f'seed-{seed}-{trial}',nodes,edges,paths
 depth=64;nodes=[(i,-1 if i<depth else 0,1) for i in range(depth+1)]
 edges=[(i,3,0,i+1,mode) for i in range(depth) for mode in (0,1) for _ in range(2)]
 paths=[[(i,3,0,i+1 if i+1<depth else -1) for i in range(depth)]]
 yield 'shared-depth-64',nodes,edges,paths
with tempfile.TemporaryDirectory(prefix='cool typed provenance ') as directory:
 tmp=Path(directory);file=ROOT/'compiler/38-provenance-graph.cool';source=file.read_text()
 source,count=re.subn(r'while \(current != null\) \{','while (current != null) { GraphVisit();',source,count=1);assert count==1
 start=source.index('fn ProvenanceQueryRoot(');body=source[start:];body,count=re.subn(r'while \(edge != null\) \{','while (edge != null) { GraphScan();',body,count=1);assert count==1
 source='extern "C" fn GraphVisit();extern "C" fn GraphScan();extern "C" fn GraphSeen();\n'+source[:start]+body
 source,count=re.subn(r'while \(state != null\) \{','while (state != null) { GraphSeen();',source,count=1);assert count==1
 source=source.replace('CAlloc(', 'GraphAuditAllocate(').replace('Free(cast[', 'GraphAuditFree(cast[')
 copied=tmp/file.name;copied.write_text(source);audit=tmp/'audit.cool';audit_source=AUDIT
 if args.copy:
  audit_source=audit_source.replace('// COPY_AUDIT', '''if(ProvenanceGraphCopy(&raw a.copies,null)!=null){NativeExit(5);}
 let sources=cast[**ProvenanceNode](CAlloc((count+2)*8));
 for(var round:i64=0;round<2;round=round+1){
  for(var i:i64=0;i<count;i=i+1){sources[i]=a.nodes[i];}
  sources[count]=sources[0];sources[count+1]=null;
  let saved=sources[1];if(ProvenanceGraphCopyRoots(&raw a.copies,sources,&raw sources[1],2) || sources[1]!=saved){NativeExit(11);}
  if(!ProvenanceGraphCopyRoots(&raw a.copies,sources,a.nodes,count+2)){NativeExit(6);}
  if(a.nodes[count]!=a.nodes[0] || a.nodes[count+1]!=null){NativeExit(7);}
  for(var i:i64=0;i<count;i=i+1){if(a.nodes[i]==sources[i] || a.nodes[i].graph!=&raw a.copies || a.nodes[i].type!=sources[i].type || a.nodes[i].root!=sources[i].root || a.nodes[i].exclusive!=sources[i].exclusive || a.nodes[i].opaque!=sources[i].opaque){NativeExit(8);}}
 }
 Free(cast[*u8](sources));
 // A malformed source fails after allocating partial copies. The existing
 // destination arena and output buffer must survive complete rollback.
 let broken=cast[*ProvenanceGraph](CAlloc(i64(sizeof(ProvenanceGraph))));
 let bad=ProvenanceNodeNew(broken,0,null,1);
 if(!ProvenanceEdgeNew(bad,1,0,bad,1)){NativeExit(9);}bad.edges.kind=5;
 let before=a.copies.nodes;var input=bad;var output=bad;
 if(ProvenanceGraphCopyRoots(&raw a.copies,&raw input,&raw output,1) || a.copies.nodes!=before || output!=null){NativeExit(10);}
 ProvenanceGraphFree(broken);Free(cast[*u8](broken));
 ProvenanceGraphFree(&raw a.graph);''')
 audit.write_text(audit_source)
 files=sorted((ROOT/'compiler').glob('*.cool'));manifest=tmp/'sources';manifest.write_text(''.join('__main\t'+str(copied if f==file else f)+'\n' for f in files)+'__main\t'+str(audit)+'\n')
 frontend=args.frontend.resolve() if args.frontend else ROOT/'build/cool-compiler'
 if args.legacy:
  assert not args.frontend,'--legacy and --frontend are mutually exclusive'
  frontend=tmp/'legacy';frontend.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' \"$@\"\n');frontend.chmod(0o755)
 ir=tmp/'compiler.ll'
 result=run([frontend,'llvm-bundle',manifest,ir]);assert result.returncode==0,result
 text,count=re.subn(r'^define i32 @main\(', 'define i32 @UnusedCompilerMain(',ir.read_text(),flags=re.M);assert count==1
 if args.sanitize:text='\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in text.splitlines())+'\n'
 ir.write_text(text);driver=tmp/'driver.c';driver.write_text(DRIVER);binary=tmp/'probe'
 flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if args.sanitize else ['-O2']
 objects=[ROOT/'build/compiler-host.o',ROOT/'build/language-runtime.o'];hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in objects}
 inputs=[]
 for obj in objects:
  dest=tmp/obj.name;dest.write_bytes(obj.read_bytes());assert hashlib.sha256(dest.read_bytes()).hexdigest()==hashes[obj.name];inputs.append(dest)
 if args.sanitize:
  checked=tmp/'checked.ll';result=run(['clang','-Wno-override-module','-O1','-fsanitize=address','-S','-emit-llvm',ir,'-o',checked]);assert result.returncode==0,result
  assert '__asan_report_load' in checked.read_text() and '__asan_report_store' in checked.read_text()
  inputs=[ROOT/'compiler/host.c',ROOT/'language/runtime.c']
 result=run(['clang','-Wno-override-module',*flags,'-I'+str(ROOT/'compiler'),'-I'+str(ROOT/'language'),ir,driver,*inputs,'-lffi','-o',binary]);assert result.returncode==0,result
 lines=[];expected=[];labels=[];graph_count=0
 for label,nodes,edges,paths in cases():
  for ordered in (edges,list(reversed(edges))):
   queries=[(start,root,mode,writing,path) for path in paths for start in range(-1,len(nodes)) for root in range(-1,4) for mode in (0,1) for writing in (0,1)] if len(nodes)<10 else [(0,root,mode,writing,paths[0]) for root in (-1,0,1) for mode in (0,1) for writing in (0,1)]
   lines.append(f'{len(nodes)} {len(ordered)} {len(queries)}\n'+''.join(' '.join(map(str,row))+'\n' for row in nodes+ordered))
   edge_count=len(set(ordered));node_count=len(nodes)
   if args.copy:edge_count*=2;node_count*=2
   expected.append(('E',edge_count));labels.append((label,len(nodes),len(edges),0,node_count))
   for start,root,mode,writing,path in queries:
    lines.append(f'{start} {root} {mode} {writing} {len(path)}\n'+''.join(' '.join(map(str,row))+'\n' for row in path))
    expected.append(('Q',oracle(nodes,edges,path,start,root,mode,writing)));labels.append((label,len(nodes),len(edges),len(path)))
   graph_count+=1
 result=run([binary],input=''.join(lines),env={**os.environ,'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'});assert result.returncode==0 and not result.stderr,result
 rows=result.stdout.splitlines();assert len(rows)==len(expected),(len(rows),len(expected))
 max_visits=0;max_comparisons=0
 for row,wanted,label in zip(rows,expected,labels):
  tag,*values=row.split();numbers=list(map(int,values));assert (tag,numbers[0])==wanted,(label,row,wanted)
  if tag=='E':assert numbers[1]==label[4],(label,row)
  if tag=='Q':
   _,n,e,l=label;assert numbers[1]<=2*n*(l+1) and numbers[2]<=2*n*(l+1)*e,(label,row);max_visits=max(max_visits,numbers[1]);assert numbers[3]<=2*n*(l+1)*numbers[2],(label,row);max_comparisons=max(max_comparisons,numbers[3])
 report={'graphs':graph_count,'queries':len(expected)-graph_count,'max_visits':max_visits,'max_state_comparisons':max_comparisons,'sanitize':args.sanitize,'legacy':args.legacy,'copy':args.copy,'compiler_source_sha256':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},'private_ir_sha256':hashlib.sha256(ir.read_bytes()).hexdigest(),'artifact_sha256':hashes,'platform_source_sha256':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [ROOT/'compiler/host.c',*(ROOT/'language'/name for name in ('runtime.c','memory.h','numeric.h','ffi.h','repl_io.h','args.h'))]},'method':('All roots jointly copied into independent arena and copied again within that arena, sharing and duplicate/null roots retained, malformed copy rolled back, source destroyed before all oracle queries; identity/mode and allocation ownership checked. ' if args.copy else '')+'Independent finite product-graph oracle for typed payload root selection, actual capabilities, cyclic cursor/graph termination, duplicate edges and instrumented allocation balance after every query and graph destruction (including repeated free). This module is not yet installed in scoped loans and does not establish nested borrowed-storage acceptance or physical ancestor overlap.'}
 if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
 print(f'typed provenance graph: {graph_count} graphs, {report["queries"]} queries, field identities, element unions, barriers, cycles, reversed edges and depth-64 shared paths PASS'+(' with ASan/UBSan' if args.sanitize else ''))
