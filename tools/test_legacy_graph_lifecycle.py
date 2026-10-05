#!/usr/bin/env python3
"""Track actual HolyC frontend graph allocations through private source copies."""
import argparse, hashlib, json, os, re, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--counts',type=int,nargs='+',default=[64,1024]);p.add_argument('--output',type=Path);args=p.parse_args()
if len(args.counts)<2 or min(args.counts)<1:p.error('provide at least two positive history lengths')
TRACKER='''class AuditAllocation{U8 *pointer;I64 size;AuditAllocation *next;};
AuditAllocation *audit_allocations;I64 audit_live,audit_count,audit_peak;
U8 *AuditGraphAlloc(I64 size){U8 *pointer=CAlloc(size);AuditAllocation *item=CAlloc(sizeof(AuditAllocation));item->pointer=pointer;item->size=size;item->next=audit_allocations;audit_allocations=item;audit_live+=size;audit_count++;if(audit_live>audit_peak)audit_peak=audit_live;return pointer;}
U0 AuditGraphFree(U8 *pointer){AuditAllocation **link=&audit_allocations,*item;while(*link && (*link)->pointer!=pointer)link=&(*link)->next;if(!*link)Error("untracked graph free");item=*link;*link=item->next;audit_live-=item->size;audit_count--;Free(item);Free(pointer);}
U0 AuditGraphMaybeFree(U8 *pointer){AuditAllocation *item=audit_allocations;while(item && item->pointer!=pointer)item=item->next;if(item)AuditGraphFree(pointer);else Free(pointer);}
U0 AuditGraphReport(){Text *text=TextNew();Append(text,"GRAPH_ALLOCATION_REPORT ");Number(text,audit_live);Append(text," ");Number(text,audit_count);Append(text," ");Number(text,audit_peak);Append(text,"\\n");Out(text->data);Free(text->data);Free(text);}
'''
BARRIER='''U0 AuditWriteBarrier(ReferenceCheck *check,Node *node){Local *local=node->local_ref;ReferenceLoan *loan;ProvenanceEdge *edge,*item;ProvenanceNode *group;Field *field;I64 inner;ProvenanceCursor tail,path,referent;Bool changed=FALSE,computed=node->kind==N_CALL && node->slot>=0 && node->slot<nfun && functions[node->slot].name && (Eq(functions[node->slot].name,"probe_return") || Eq(functions[node->slot].name,"prefix_return")),prefix;if(!computed && (!local || !local->name || !Eq(local->name,"write_probe") && !Eq(local->name,"prefix_probe")))return;prefix=(computed && Eq(functions[node->slot].name,"prefix_return")) || (!computed && Eq(local->name,"prefix_probe"));inner=Shape(node->type)->element;for(field=Shape(inner)->fields;field;field=field->next)if(Eq(field->name,"right"))break;if(!field)Error("missing audit field");for(loan=check->loans;loan;loan=loan->next)if(((computed && !loan->holder && loan->expression==node) || (!computed && loan->holder==local)) && loan->indirect==1 && loan->root && Eq(loan->root->name,"b")){for(edge=loan->provenance->edges;edge;edge=edge->next)if(edge->kind==3){group=edge->target;for(item=group->edges;item;item=item->next)if(item->kind==1 && item->key==field){if(!ProvenanceEdgeNew(group,1,item->key,item->target,0))Error("audit insertion failed");if(prefix){loan->provenance->root=loan->root;loan->provenance->exclusive=1;}MemSet(&tail,0,sizeof(ProvenanceCursor));MemSet(&path,0,sizeof(ProvenanceCursor));tail.type=inner;tail.kind=1;tail.key=item->key;path.type=node->type;path.kind=3;path.next=&tail;if(!ProvenanceQueryRoot(loan->provenance,&path,loan->root,loan->exclusive,TRUE))Error("audit exclusive missing");if(ReferencePathWriteModes(loan,&path,1)!=prefix || ReferencePathCopyModes(loan,&path,1)!=3 || ReferencePathCopyModes(loan,NULL,1)!=prefix)Error("audit copy boundary failed");MemSet(&referent,0,sizeof(ProvenanceCursor));referent.type=item->target->type;referent.kind=3;tail.next=&referent;if(ReferencePathWriteModes(loan,&path,1)!=3)Error("audit alternatives missing");changed=TRUE;break;}}}if(!changed)Error("audit holder missing");}
'''
def workload(name,count):
 if name in ('prefix_write','prefix_copy','computed_prefix_write','computed_prefix_copy'):
  original={'prefix_write':'write_barrier','prefix_copy':'copy_barrier','computed_prefix_write':'computed_write','computed_prefix_copy':'computed_copy'}[name]
  source,output,errors=workload(original,count)
  return source.replace('write_probe','prefix_probe').replace('probe_return','prefix_return'),output,errors
 if name in ('generic_parent_success','generic_parent_runtime_failure'):
  prefix='struct G[T]{r:&i64;v:T;}\nvar a=1;\nvar b=2;\nvar r=&a;\n'
  cycle='{var temp=G[i64]{r:&b,v:3};r=temp.r;'
  if name=='generic_parent_runtime_failure':cycle+='assert(false);'
  cycle+='}\n'
  suffix='*r\na=7;\nb=7;\n:forget r\na=7;\nb=9;\nb\n'
  return (prefix+cycle*count+suffix,'2\n9\n',2+(count if name=='generic_parent_runtime_failure' else 0))
 if name=='named_physical_fields':
  return ('struct Point{x:i64;y:i64;}\nvar p=Point{x:1,y:2};\nlet r=&mut p;\nlet x=&mut (*r).x;\n'+'{let y=&mut (*r).y;*y=*y+1;}\n'*count+'*x\n(*r).y\n:forget x\n:forget r\n:forget p\n',f'1\n{count+2}\n',0)
 if name=='named_physical_recovery':
  return ('struct Point{x:i64;y:i64;}\nvar p=Point{x:1,y:2};\nlet r=&mut p;\nlet x=&mut (*r).x;\n'+''.join('(*r).x=3;\n' if i%2==0 else '{(*r).y=(*r).y+1;assert(false);}\n' for i in range(count))+'*x\n(*r).y\n:forget x\n:forget r\n:forget p\n',f'1\n{count//2+2}\n',count)
 if name=='owner_descriptor_fields':
  return ('struct Point{x:i64;y:i64;}\nvar p=new[Point](Point{x:1,y:2});\nlet x=&mut (*p).x;\nlet y=&mut (*p).y;\n'+'*y=*y+1;\n'*count+'*x\n*y\n:forget x\n:forget y\n:forget p\n',f'1\n{count+2}\n',0)
 if name=='owner_descriptor_recovery':
  return ('struct Point{x:i64;y:i64;}\nvar p=new[Point](Point{x:1,y:2});\nlet x=&mut (*p).x;\n'+''.join('(*p).x=3;\n' if i%2==0 else '{(*p).y=(*p).y+1;assert(false);}\n' for i in range(count))+'*x\n(*p).y\n:forget x\n:forget p\n',f'1\n{count//2+2}\n',count)
 if name=='field_access':
  return ('struct Pair{left:&mut i64;right:&mut i64;}\nvar a=1;\nvar b=2;\nvar pair=Pair{left:&mut a,right:&mut b};\nlet r=&mut pair;\nlet q=&mut *(*r).left;\n'+'*(*r).right=*(*r).right+1;\n'*count+'*(*r).right\n*q\n',f'{count+2}\n1\n',0)
 if name=='opaque_returns':
  return ('struct Pair{left:&i64;right:&i64;}\nfn swap(a:&i64,b:&i64)->Pair borrows(a,b){return Pair{left:b,right:a};}\nvar a=7;\nvar b=8;\nvar pair=Pair{left:&a,right:&b};\n'+'pair=swap(&a,&b);\n'*count+'*pair.left\n*pair.right\n','8\n7\n',0)
 if name=='write_barrier':
  return ('struct Pair{left:&mut i64;right:&mut i64;}\nvar a=1;\nvar b=2;\nvar pair=Pair{left:&mut a,right:&mut b};\nlet write_probe=&mut pair;\n'+'*(*write_probe).right=9;\n'*count+'*(*write_probe).right\n','2\n',count)
 if name=='copy_barrier':
  return ('struct Pair{left:&mut i64;right:&mut i64;}\nvar a=1;\nvar b=2;\nvar pair=Pair{left:&mut a,right:&mut b};\nlet write_probe=&mut pair;\n'+''.join(('let q=(*write_probe).right;\n' if i%2==0 else 'let q=*write_probe;\n') for i in range(count))+'*(*write_probe).right\n','2\n',count)
 if name in ('computed_write','computed_copy'):
  prefix='struct Pair{left:&mut i64;right:&mut i64;}\nfn probe_return(p:&mut Pair)->&mut Pair borrows(p){return p;}\nvar a=1;\nvar b=2;\nvar pair=Pair{left:&mut a,right:&mut b};\n'
  if name=='computed_write':statements=['*(*probe_return(&mut pair)).right=9;\n','*(*probe_return(&mut pair)).right=10;\n']
  else:statements=['let q=(*probe_return(&mut pair)).right;\n','let q=*probe_return(&mut pair);\n','let q=&mut *(*probe_return(&mut pair)).right;\n']
  return (prefix+''.join(statements[i%len(statements)] for i in range(count))+'*pair.right\n','2\n',count)
 if name=='recursive_returns':
  return ('import "std/mem";\nenum Chain{End;Link(Entry);}struct Entry{next:own[Chain];r:&i64;}\nfn identity(p:own[Chain])->own[Chain] borrows(p){return move p;}\nvar a=7;\nvar p=new[Chain](Chain.Link(Entry{next:new[Chain](Chain.End),r:&a}));\n'+'p=identity(move p);\n'*count+'mem.owner_count()\n:forget p\nmem.owner_count()\n','2\n0\n',0)
 if name=='failed_functions':return ('fn fail(){var a=1;let q=&a;a=2;}\n'*count+'var kept=7;\nkept\n','7\n',count)
 if name=='stores':return ('struct Pair{left:&i64;right:&i64;}\nfn setright(dst:&mut Pair,src:&i64) stores(dst,src){(*dst).right=src;}\nvar a=7;\nvar b=8;\nvar c=9;\nvar pair=Pair{left:&a,right:&b};\nlet r=&mut pair;\n'+'setright(r,&c);\n'*count+'*(*r).left\n*(*r).right\n','7\n9\n',0)
 raise AssertionError(name)
with tempfile.TemporaryDirectory(prefix='cool legacy graph lifecycle ') as directory:
 tmp=Path(directory);files=sorted((ROOT/'language').glob('*.cool'));hashes={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
 for f in files:(tmp/f.name).write_bytes(f.read_bytes())
 graph=tmp/'Provenance.cool';text=graph.read_text();text=re.sub(r'\bCAlloc\(', 'AuditGraphAlloc(',text);text=re.sub(r'\bFree\(', 'AuditGraphFree(',text);graph.write_text(TRACKER+text)
 loan=tmp/'LoanProvenance.cool';loan.write_text(re.sub(r'\bFree\(', 'AuditGraphMaybeFree(',loan.read_text()))
 loan.write_text(loan.read_text()+BARRIER)
 refs=tmp/'References.cool';text=refs.read_text()
 marker='check->loans=loan;return;}'
 assert text.count(marker)==1
 text=text.replace(marker,'check->loans=loan;AuditWriteBarrier(check,node);return;}')
 header='class ReferenceCheck { ReferenceLoan *loans; Function *function; ProvenanceGraph *graph; ReferenceCheck *next; };'
 assert text.count(header)==1
 call_end='        }return;\n    }\n    if(node->kind==N_AGG_LITERAL || node->kind==N_NEW){'
 assert text.count(call_end)==1;text=text.replace(call_end,'        }AuditWriteBarrier(check,node);return;\n    }\n    if(node->kind==N_AGG_LITERAL || node->kind==N_NEW){')
 refs.write_text(text.replace(header,header+'\nextern U0 AuditWriteBarrier(ReferenceCheck *check,Node *node);'))
 native=tmp/'Native.cool';text=native.read_text();assert text.endswith('LanguageMain;\n');native.write_text(text+'AuditGraphReport;\n')
 binary=tmp/'frontend.BIN';env={**os.environ,'COOLC_COMPILER_BIN':str(ROOT/'coolc/seed/Compiler.BIN')}
 r=subprocess.run([ROOT/'build/coolc',native,binary],env=env,cwd=ROOT,text=True,capture_output=True,timeout=90);assert r.returncode==0,r
 observations=[]
 for name in ('generic_parent_success','generic_parent_runtime_failure','named_physical_fields','named_physical_recovery','owner_descriptor_fields','owner_descriptor_recovery','field_access','opaque_returns','recursive_returns','failed_functions','stores','write_barrier','copy_barrier','computed_write','computed_copy','prefix_write','prefix_copy','computed_prefix_write','computed_prefix_copy'):
  rows=[]
  for count in args.counts:
   source,output,errors=workload(name,count)
   r=subprocess.run([ROOT/'build/coolc','--run',binary,'repl-quiet'],input=source+':quit\n',cwd=ROOT,text=True,capture_output=True,timeout=120)
   matched=re.findall(r'^GRAPH_ALLOCATION_REPORT (\d+) (\d+) (\d+)\n',r.stdout,re.M);assert len(matched)==1,r
   assert (name not in ('write_barrier','computed_write','prefix_write','computed_prefix_write') or r.stderr.count('cannot mutate or move through a shared reference')==count),r
   assert (name not in ('copy_barrier','computed_copy','prefix_copy','computed_prefix_copy') or r.stderr.count('cannot copy or move an exclusive reference through a shared path')==count),r
   assert r.returncode==0 and r.stdout.split('GRAPH_ALLOCATION_REPORT ')[0]==output and r.stderr.count('error:')==errors,(name,count,r)
   live,allocations,peak=map(int,matched[0]);assert (live,allocations)==(0,0),(name,count,matched)
   row={'workload':name,'submissions':count,'live_bytes':live,'live_count':allocations,'peak_bytes':peak};rows.append(row);observations.append(row)
  assert len({r['peak_bytes'] for r in rows})==1,rows
  print(name+': '+', '.join(f'{r["submissions"]} => final {r["live_bytes"]}/{r["live_count"]}, peak {r["peak_bytes"]}' for r in rows))
 assert hashes=={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},'source changed during snapshot audit'
 report={'source_sha256':hashes,'counts':args.counts,'observations':observations,'method':'Private copies of actual legacy frontend sources; track allocations/frees inside Provenance.cool only (nodes, edges, product-query/copy scratch). Tracking bookkeeping excluded; graph arenas, loans, other compiler metadata and JIT mappings not measured. Actual seed-compiled BIN REPL; all tracked graph allocations must reach zero on cleanup and peaks remain equal across repeated history lengths. No production artifacts modified.'}
 if args.output:args.output.write_text(json.dumps(report,indent=2)+'\n')
print('legacy graph lifecycle PASS')
