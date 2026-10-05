#!/usr/bin/env python3
"""Compare production subtree selection against an independent finite-state oracle."""
import argparse, hashlib, json, os, random, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);p.add_argument('--sanitize',action='store_true');p.add_argument('--output',type=Path);args=p.parse_args()
def run(cmd,**kw):return subprocess.run(list(map(str,cmd)),cwd=ROOT,capture_output=True,text=True,timeout=240,**kw)
def query(nodes,edges,path,start,mode,write):
 todo=[(start,0 if path else -1,mode)];seen=set()
 while todo:
  n,c,m=todo.pop()
  if n<0 or (n,c,m) in seen:continue
  seen.add((n,c,m));typ,root,cap,opaque=nodes[n]
  if c<0:
   if root==0 and (not write or m&cap):return 1
  elif typ==path[c][0]:
   _,kind,key,nxt=path[c]
   todo += [(t,nxt,m&cap) for s,k,v,t,cap in edges if s==n and k==kind and (kind!=1 or v==key)]
 return 0
def overlap(nodes,edges,path,start,complete,known):
 # Access overlap is a different relation: modes never erase shared roots,
 # a terminal root protects descendants, and a whole value includes children.
 if not complete:return 1
 if start<0:return int(not known)
 pending={(start,0 if path else -1)};visited=set()
 while pending:
  n,c=pending.pop()
  if n<0 or (n,c) in visited:continue
  visited.add((n,c));typ,root,cap,opaque=nodes[n]
  if root==0 or opaque or (c>=0 and typ!=path[c][0]):return 1
  if c<0:pending.update((t,-1) for s,k,key,t,m in edges if s==n and t>=0)
  else:
   _,kind,key,nxt=path[c]
   pending.update((t,nxt) for s,k,v,t,m in edges if s==n and t>=0 and k==kind and (kind!=1 or v==key))
 return 0
def write_modes(nodes,edges,path,start,mode,complete,known):
 if not complete:return 4
 if start<0:return 0 if known else 4
 pending=[(start,0 if path else -1,mode)];visited=set();result=0
 while pending:
  n,c,m=pending.pop()
  if n<0 or (n,c,m) in visited:continue
  visited.add((n,c,m));typ,root,cap,opaque=nodes[n]
  if c<0:continue
  if opaque or typ!=path[c][0]:result|=4
  else:
   if root==0:result|=1 if m&cap else 2
   _,kind,key,nxt=path[c]
   pending.extend((t,nxt,m&barrier) for s,k,v,t,barrier in edges if s==n and t>=0 and k==kind and (kind!=1 or v==key))
 return result
def copy_modes(nodes,edges,path,start,mode,complete,known):
 if not complete:return 4
 if start<0:return 0 if known else 4
 pending=[(start,0 if path else -1,mode)];visited=set();result=0
 while pending:
  n,c,m=pending.pop()
  if n<0 or (n,c,m) in visited:continue
  visited.add((n,c,m));typ,root,cap,opaque=nodes[n]
  if opaque or (c>=0 and typ!=path[c][0]):result|=4;continue
  if c<0:
   if typ in (0,1,20,30,40):
    if typ not in (0,30) and root==0:result|=1 if m&cap else 2
   else:pending.extend((t,-1,m&barrier) for s,k,v,t,barrier in edges if s==n and t>=0)
  else:
   if root==0:result|=1 if m&cap else 2
   _,kind,key,nxt=path[c]
   pending.extend((t,nxt,m&barrier) for s,k,v,t,barrier in edges if s==n and t>=0 and k==kind and (kind!=1 or v==key))
 return result
def address_root_possible(nodes,edges,start):
 pending=[start];seen=set()
 while pending:
  n=pending.pop()
  if n<0 or n in seen:continue
  seen.add(n)
  if nodes[n][1]==0 or nodes[n][3]:return True
  pending.extend(t for s,k,v,t,m in edges if s==n and t>=0)
 return False
def address_overlap(nodes,edges,left,right):
 if left<0 or right<0:return 1
 pending=[(left,right)];seen=set()
 while pending:
  a,b=pending.pop()
  if (a,b) in seen:continue
  seen.add((a,b));at,ar,ac,ao=nodes[a];bt,br,bc,bo=nodes[b]
  if ao or bo or at!=bt:return 1
  if ar==0:
   if address_root_possible(nodes,edges,b):return 1
  elif br==0:
   if address_root_possible(nodes,edges,a):return 1
  else:
   pending.extend((xt,yt) for xs,xk,xv,xt,xm in edges for ys,yk,yv,yt,ym in edges if xs==a and ys==b and xt>=0 and yt>=0 and xk==yk and (xk!=1 or xv==yv or at==2))
 return 0
def oracle(nodes,edges,path,start,mode,complete,typ,known,extra,write):
 # Independent selection returns a union of original endpoint states and
 # opaque root alternatives, then queries that union with another cursor.
 bound=0;todo=[(start,mode)];seen=set()
 while todo:
  n,m=todo.pop()
  if n<0 or (n,m) in seen:continue
  seen.add((n,m));_,root,cap,_=nodes[n]
  if root==0:bound |= m&cap
  todo += [(t,m&cap) for s,k,v,t,cap in edges if s==n]
 if start<0:bound=mode if not known else 0
 states=[];fallback=[];precise=1
 if start<0:
  if not known:fallback.append(mode);precise=0
 elif not complete:fallback.append(bound);precise=0
 else:
  todo=[(start,0 if path else -1,mode)];seen=set()
  while todo:
   n,c,m=todo.pop()
   if n<0 or (n,c,m) in seen:continue
   seen.add((n,c,m));nt,root,cap,opaque=nodes[n]
   if c<0:
    if nt==typ:states.append((n,m));precise &= not opaque
    else:fallback.append(m&bound);precise=0
   else:
    ct,kind,key,nxt=path[c]
    if opaque or nt!=ct or root>=0:fallback.append(m&cap&bound);precise=0
    if nt==ct:todo += [(t,nxt,m&cap) for s,k,v,t,cap in edges if s==n and k==kind and (kind!=1 or v==key)]
 reading=int(any(query(nodes,edges,extra,n,m,write) for n,m in states) or (not extra and any(not write or m for m in fallback)))
 return reading,int(precise)
AUDIT='''
export "C" fn StoreGraphProbe(){unsafe{
 var graph=ProvenanceGraph{};var external=Local{};var holder=Local{};holder.type=10;
 var check=ReferenceCheck{};check.graph=&raw graph;
 var address=Node{};address.kind=22;address.type=100010;address.local_ref=&raw holder;
 var field=Node{};field.kind=24;field.type=100020;field.a=&raw address;field.field_key=100;
 var nested=Node{};nested.kind=24;nested.type=100030;nested.a=&raw field;nested.field_key=200;
 var tail=ProvenanceCursor{type:20,kind:1,key:200,next:null};
 var path=ProvenanceCursor{type:10,kind:1,key:100,next:&raw tail};
 for(var mode:i64=0;mode<2;mode=mode+1){for(var cap:i64=0;cap<2;cap=cap+1){
  var source=ReferenceLoan{};source.root=&raw external;source.exclusive=mode;source.provenance_type=30;source.provenance_known=1;
  source.provenance=ProvenanceNodeNew(&raw graph,30,&raw external,cap);
  var installed=ReferenceInstalledGraph(&raw check,&raw source,10,&raw nested,false);
  if(installed.provenance_type!=10 || installed.provenance_known!=1 || !ReferenceLoanQuery(&raw installed,&raw path,&raw external,false) || BoolInt(ReferenceLoanQuery(&raw installed,&raw path,&raw external,true))!=(mode&cap)){NativeExit(61);}
  path.key=101;if(ReferenceLoanQuery(&raw installed,&raw path,&raw external,false)){NativeExit(62);}path.key=100;
  let head=graph.nodes;
  for(var i:i64=0;i<128;i=i+1){installed=ReferenceInstalledGraph(&raw check,&raw source,10,&raw nested,false);if(graph.nodes!=head){NativeExit(63);}}
 }}
 var absent=ReferenceLoan{};absent.root=&raw external;absent.provenance_type=30;absent.provenance_known=1;
 var missing=ReferenceInstalledGraph(&raw check,&raw absent,10,&raw nested,false);
 if(missing.provenance!=null || missing.provenance_known!=1 || missing.provenance_type!=10){NativeExit(64);}
 var unknown=absent;unknown.provenance_known=0;
 var fallback=ReferenceInstalledGraph(&raw check,&raw unknown,10,null,false);
 if(fallback.provenance==null || fallback.provenance_known!=0 || ReferenceLoanQuery(&raw fallback,null,&raw external,true)){NativeExit(65);}
 ProvenanceGraphFree(&raw graph);
}}
export "C" fn SelectJoinProbe(){unsafe{
 var graph=ProvenanceGraph{};var root=Local{};var check=ReferenceCheck{};check.graph=&raw graph;
 var shared=ReferenceLoan{};shared.root=&raw root;shared.provenance_type=20;
 var absent=ReferenceLoan{};absent.root=&raw root;absent.provenance_type=20;absent.provenance_known=1;
 ReferenceProvenanceJoin(&raw check,&raw absent,&raw shared);
 if(absent.provenance==null || absent.provenance_known!=0 || !ReferenceLoanQuery(&raw absent,null,&raw root,false)){NativeExit(51);}
 let child=ProvenanceNodeNew(&raw graph,30,&raw root,1);
 let parent=ReferenceGraphParent(&raw graph,20,1,100,child);
 var precise=ReferenceLoan{};precise.root=&raw root;precise.provenance_type=20;precise.provenance_known=1;precise.exclusive=1;precise.provenance=parent;
 ReferenceProvenanceJoin(&raw check,&raw precise,&raw shared);
 if(precise.provenance_known!=0 || ReferenceLoanQuery(&raw precise,null,&raw root,true)){NativeExit(52);}
 let head=graph.nodes;
 for(var i:i64=0;i<128;i=i+1){ReferenceProvenanceJoin(&raw check,&raw precise,&raw shared);if(graph.nodes!=head){NativeExit(53);}}
 ReferenceProvenanceJoin(&raw check,&raw shared,&raw precise);
 if(shared.provenance_known!=0 || !ReferenceLoanQuery(&raw shared,null,&raw root,false)){NativeExit(54);}
 var mismatch=ReferenceLoan{};mismatch.root=&raw root;mismatch.provenance_type=30;mismatch.provenance=ProvenanceNodeNew(&raw graph,30,&raw root,0);mismatch.provenance_known=1;
 var destination=ReferenceLoan{};destination.root=&raw root;destination.provenance_type=20;destination.provenance_known=1;destination.exclusive=1;
 ReferenceProvenanceJoin(&raw check,&raw destination,&raw mismatch);
 if(destination.provenance==null || destination.provenance.type!=20 || destination.provenance_known!=0 || ReferenceLoanQuery(&raw destination,null,&raw root,true)){NativeExit(55);}
 ProvenanceGraphFree(&raw graph);
}}
fn CopyProbeType(type:i64)->i64{unsafe{
 var token=Token{};
 if(type==0){return SequenceType(6,1,0,&raw token);}
 if(type==1){return SequenceType(6,1,1,&raw token);}
 if(type==20){return SequenceType(6,2,1,&raw token);}
 if(type==30){return SequenceType(6,2,0,&raw token);}
 if(type==40){return SequenceType(3,1,0,&raw token);}
 return type;
}}
export "C" fn SelectProbe(n:i64,e:i64,ns:*i64,es:*i64,c:i64,ps:*i64,start:i64,mode:i64,complete:i64,type:i64,known:i64,q:i64,qs:*i64,writing:i64)->i64{unsafe{
 var graph=ProvenanceGraph{};var root=Local{};var check=ReferenceCheck{};check.graph=&raw graph;
 let nodes=cast[**ProvenanceNode](CAlloc((n+1)*8));
 for(var i:i64=0;i<n;i=i+1){var r:*Local=null;if(ns[4*i+1]==0){r=&raw root;}nodes[i]=ProvenanceNodeNew(&raw graph,ns[4*i],r,ns[4*i+2]);nodes[i].opaque=ns[4*i+3];}
 for(var i:i64=0;i<e;i=i+1){var t:*ProvenanceNode=null;if(es[5*i+3]>=0){t=nodes[es[5*i+3]];}ProvenanceEdgeNew(nodes[es[5*i]],es[5*i+1],es[5*i+2],t,es[5*i+4]);}
 let paths=cast[*ProvenanceCursor](CAlloc((c+q+1)*i64(sizeof(ProvenanceCursor))));
 for(var i:i64=0;i<c;i=i+1){paths[i].type=ps[4*i];paths[i].kind=ps[4*i+1];paths[i].key=ps[4*i+2];if(ps[4*i+3]>=0){paths[i].next=&raw paths[ps[4*i+3]];}}
 for(var i:i64=0;i<q;i=i+1){paths[c+i].type=qs[4*i];paths[c+i].kind=qs[4*i+1];paths[c+i].key=qs[4*i+2];if(qs[4*i+3]>=0){paths[c+i].next=&raw paths[c+qs[4*i+3]];}}
 var source=ReferenceLoan{};source.root=&raw root;source.exclusive=mode;source.provenance_known=known;if(start>=0){source.provenance=nodes[start];}
 var path:*ProvenanceCursor=null;if(c>0){path=paths;}var extra:*ProvenanceCursor=null;if(q>0){extra=&raw paths[c];}
 var selected=ReferenceSelectGraph(&raw check,&raw source,path,complete,type);
 var result=BoolInt(ProvenanceQueryRoot(selected.node,extra,&raw root,1,writing!=0))+2*selected.known+4*BoolInt(ReferencePathMayAccess(&raw source,path,complete))+8*ReferencePathWriteModes(&raw source,path,complete);
 let ctx=cast[*CompilerState](NativeCompilerState(i64(sizeof(CompilerState))));
 ctx.v_naggregates=0;ctx.v_aggregate_types=cast[*AggregateType](CAlloc(8*i64(sizeof(AggregateType))));
 var token=Token{};let enum_type=NewType(4,&raw token);
 for(var i:i64=0;i<n;i=i+1){if(nodes[i].type==2){nodes[i].type=enum_type;}}
 var partner:*ProvenanceNode=null;if(start>=0){partner=nodes[(start+1)%n];}
 result=result+512*BoolInt(ProvenanceAddressOverlap(source.provenance,partner,&raw root));
 for(var i:i64=0;i<n;i=i+1){nodes[i].type=ns[4*i];}
 for(var i:i64=0;i<n;i=i+1){nodes[i].type=CopyProbeType(nodes[i].type);}
 for(var i:i64=0;i<c;i=i+1){paths[i].type=CopyProbeType(paths[i].type);}
 result=result+64*ReferencePathCopyModes(&raw source,path,complete);
 Free(cast[*u8](ctx.v_aggregate_types));ctx.v_aggregate_types=null;ctx.v_naggregates=0;
 Free(cast[*u8](paths));Free(cast[*u8](nodes));ProvenanceGraphFree(&raw graph);return result;
}}
'''
DRIVER=r'''
#include <stdint.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
extern void SelectJoinProbe(void);extern void StoreGraphProbe(void);
extern int64_t SelectProbe(int64_t,int64_t,int64_t*,int64_t*,int64_t,int64_t*,int64_t,int64_t,int64_t,int64_t,int64_t,int64_t,int64_t*,int64_t);
static int64_t get(void){int64_t v;if(scanf("%"SCNd64,&v)!=1)abort();return v;}
int main(void){SelectJoinProbe();StoreGraphProbe();int64_t n;while(scanf("%"SCNd64,&n)==1){int64_t e=get(),c=get(),q=get(),start=get(),mode=get(),complete=get(),type=get(),known=get(),writing=get();
 int64_t *ns=calloc(n*4+1,8),*es=calloc(e*5+1,8),*ps=calloc(c*4+1,8),*qs=calloc(q*4+1,8);
 for(int64_t i=0;i<n*4;i++)ns[i]=get();for(int64_t i=0;i<e*5;i++)es[i]=get();for(int64_t i=0;i<c*4;i++)ps[i]=get();for(int64_t i=0;i<q*4;i++)qs[i]=get();
 printf("%"PRId64"\n",SelectProbe(n,e,ns,es,c,ps,start,mode,complete,type,known,q,qs,writing));free(ns);free(es);free(ps);free(qs);
}return 0;}
'''
rng=random.Random(20261005);cases=[]
for trial in range(160):
 nodes=[(rng.randrange(3),rng.randrange(-1,1),rng.randrange(2),rng.randrange(2)) for _ in range(7)]
 edges=list(set((rng.randrange(7),rng.randrange(1,5),rng.randrange(3),rng.randrange(-1,7),rng.randrange(2)) for _ in range(24)))
 paths=[[]]
 paths += [[(nodes[s][0],k,v,-1)] for s,k,v,t,m in edges[:3]]
 paths += [[(rng.randrange(3),rng.randrange(1,5),rng.randrange(3),1),(rng.randrange(3),rng.randrange(1,5),rng.randrange(3),rng.choice((-1,0)))]]
 for path in paths:
  for writing in (0,1):
   extra=rng.choice(paths);start=rng.randrange(-1,7);mode=rng.randrange(2);complete=int(rng.random()>.15);typ=rng.randrange(3);known=rng.randrange(2)
   cases.append((nodes,edges,path,start,mode,complete,typ,known,extra,writing))
# Explicit precise missing branches, shared barriers, and graph/cursor cycles.
nodes=[(10,-1,1,0),(20,0,1,0),(20,0,0,0),(10,-1,1,0)]
edges=[(0,1,100,1,1),(0,1,101,2,1),(0,3,0,3,0),(3,3,0,0,1)]
for path in ([],[(10,1,100,-1)],[(10,1,101,-1)],[(10,1,999,-1)],[(10,3,0,1),(10,3,0,0)]):
 for mode in (0,1):
  for writing in (0,1):cases.append((nodes,edges,path,0,mode,1,20,1,[],writing))
# Same field/root reached through both capabilities must retain shared status,
# irrespective of edge order, even when an exclusive alternative arrives first.
for es in ([(0,1,100,1,1),(0,1,100,2,0)],[(0,1,100,2,0),(0,1,100,1,1)]):
 ns=[(10,-1,1,0),(20,0,1,0),(20,0,1,0)]
 for mode in (0,1):
  case=(ns,es,[(10,1,100,1),(20,3,0,-1)],0,mode,1,20,1,[],1);cases.append(case)
  assert write_modes(ns,es,case[2],0,mode,1,1)==(3 if mode else 2)
# Handle boundaries: shared references do not need exclusive authority, mutable
# references/slices do; their referent/element payloads are not copied handles.
for typ in (20,30,40):
 for mode in (0,1):
  ns=[(typ,0,1,0),(20,0,0,0)]
  es=[(0,3 if typ!=40 else 2,0,1,0),(1,3,0,0,1)]
  cases.append((ns,es,[],0,mode,1,typ,1,[],1))
  assert copy_modes(ns,es,[],0,mode,1,1)==(0 if typ==30 else 1 if mode else 2)
# The same root is physical storage at an exclusive prefix and a shared
# external referent deeper in its payload. The exclusive prefix must not stop
# either authority query. Cycle and reversed edge variants preserve that fact.
for cyclic in (False,True):
 for reverse in (False,True):
  ns=[(20,0,1,0),(10,-1,1,0),(30,0,0,0)]
  es=[(0,3,0,1,1),(1,1,100,2,0)]
  if cyclic:es.append((1,3,0,0,1))
  if reverse:es.reverse()
  path=[(20,3,0,1),(10,1,100,2),(30,3,0,-1)]
  assert write_modes(ns,es,path,0,1,1,1)==3
  assert copy_modes(ns,es,path,0,1,1,1)==3
  cases.append((ns,es,path,0,1,1,30,1,[],1))
for prefix_cap in (0,1):
 for child_cap in (0,1):
  ns=[(20,0,prefix_cap,0),(10,-1,1,0),(20,0,child_cap,0)]
  es=[(0,3,0,1,1),(1,1,100,2,1)]
  path=[(20,3,0,1),(10,1,100,2),(20,3,0,-1)]
  expected=(1 if prefix_cap else 2)|(1 if child_cap else 2)
  assert write_modes(ns,es,path,0,1,1,1)==expected
  assert copy_modes(ns,es,path,0,1,1,1)==expected
  cases.append((ns,es,path,0,1,1,20,1,[],1))
for prefix_cap in (0,1):
 ns=[(20,0,prefix_cap,0),(10,-1,1,1)]
 es=[(0,3,0,1,1)];path=[(20,3,0,1),(10,1,100,-1)]
 expected=(1 if prefix_cap else 2)|4
 assert write_modes(ns,es,path,0,1,1,1)==expected
 assert copy_modes(ns,es,path,0,1,1,1)==expected
 cases.append((ns,es,path,0,1,1,10,1,[],1))
for mode in (0,1):
 ns=[(20,0,1,0),(20,0,0,0)];es=[(0,3,0,1,1),(1,3,0,0,1)]
 path=[(20,3,0,0)]
 assert write_modes(ns,es,path,0,mode,1,1)==(3 if mode else 2)
 assert copy_modes(ns,es,path,0,mode,1,1)==(3 if mode else 2)
 cases.append((ns,es,path,0,mode,1,20,1,[],1))
with tempfile.TemporaryDirectory(prefix='cool provenance selection ') as directory:
 tmp=Path(directory);audit=tmp/'audit.cool';audit.write_text(AUDIT);files=sorted((ROOT/'compiler').glob('*.cool'));manifest=tmp/'sources';manifest.write_text(''.join('__main\t'+str(f)+'\n' for f in files)+'__main\t'+str(audit)+'\n');ir=tmp/'compiler.ll'
 frontend=args.frontend.resolve() if args.frontend else ROOT/'build/cool-compiler';env={**os.environ,'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
 r=run([frontend,'llvm-bundle',manifest,ir],env=env);assert r.returncode==0,r
 text=ir.read_text();text=text.replace('define i32 @main(', 'define i32 @unused_compiler_main(')
 if args.sanitize:text='\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in text.splitlines())+'\n'
 ir.write_text(text);driver=tmp/'driver.c';driver.write_text(DRIVER);binary=tmp/'probe'
 flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if args.sanitize else ['-O2']
 inputs=[];artifacts={}
 for name in ('compiler-host.o','language-runtime.o'):
  original=ROOT/'build'/name;copy=tmp/name;copy.write_bytes(original.read_bytes());artifacts[name]=hashlib.sha256(copy.read_bytes()).hexdigest();inputs.append(copy)
 if args.sanitize:
  checked=tmp/'checked.ll';r=run(['clang','-Wno-override-module','-O1','-fsanitize=address','-S','-emit-llvm',ir,'-o',checked]);assert r.returncode==0,r
  assert '__asan_report_load' in checked.read_text() and '__asan_report_store' in checked.read_text()
  inputs=[ROOT/'compiler/host.c',ROOT/'language/runtime.c']
 r=run(['clang','-Wno-override-module',*flags,'-I'+str(ROOT/'compiler'),'-I'+str(ROOT/'language'),ir,driver,*inputs,'-lffi','-o',binary]);assert r.returncode==0,r
 lines=[];expected=[]
 for nodes,edges,path,start,mode,complete,typ,known,extra,write in cases:
  lines.append(' '.join(map(str,[len(nodes),len(edges),len(path),len(extra),start,mode,complete,typ,known,write,*[v for row in nodes+edges+path+extra for v in row]])))
  read,precise=oracle(nodes,edges,path,start,mode,complete,typ,known,extra,write);expected.append(read+2*precise+4*overlap(nodes,edges,path,start,complete,known)+8*write_modes(nodes,edges,path,start,mode,complete,known)+64*copy_modes(nodes,edges,path,start,mode,complete,known)+512*address_overlap(nodes,edges,start,(start+1)%len(nodes) if start>=0 else -1))
 r=run([binary],input='\n'.join(lines)+'\n',env=env);assert r.returncode==0,r
 actual=list(map(int,r.stdout.split()));assert len(actual)==len(expected),(len(actual),len(expected),r)
 for i,(a,b) in enumerate(zip(actual,expected)):assert a==b,(i,a,b,cases[i])
 report={'cases':len(cases),'seed':20261005,'sanitize':args.sanitize,'source_sha256':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},'artifact_sha256':artifacts,'private_ir_sha256':hashlib.sha256(ir.read_bytes()).hexdigest(),'audit_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'method':'Independent Python product-state selection/alternative-query and independent physical address pair-product overlap and access overlap/universal write-mode/copy-mode oracles (synthetic labels map to actual mutable/shared reference and slice descriptors); shared/exclusive alternatives, reversed edges, unknown and absence; physical terminal prefixes, whole-value descendants, opaque/type/incomplete fallback and precise absence;  same external root per loan, opaque and precise/null alternatives, wrong types, shared barriers, field/element/referent/owner edges, cyclic paths and graphs. Nested store cursor wrapping, wrong sibling exclusion, source entry/terminal capabilities, precise absence/unknown fallback and repeated wrapper interning probes. Metadata only, not permission authorization.'}
 if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
 print(f'provenance selection/overlap/authority: {len(cases)} independent oracle cases PASS'+(' with ASan/UBSan' if args.sanitize else ''))
