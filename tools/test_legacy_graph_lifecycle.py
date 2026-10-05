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
def workload(name,count):
 if name=='field_access':
  return ('struct Pair{left:&mut i64;right:&mut i64;}\nvar a=1;\nvar b=2;\nvar pair=Pair{left:&mut a,right:&mut b};\nlet r=&mut pair;\nlet q=&mut *(*r).left;\n'+'*(*r).right=*(*r).right+1;\n'*count+'*(*r).right\n*q\n',f'{count+2}\n1\n',0)
 if name=='opaque_returns':
  return ('struct Pair{left:&i64;right:&i64;}\nfn swap(a:&i64,b:&i64)->Pair borrows(a,b){return Pair{left:b,right:a};}\nvar a=7;\nvar b=8;\nvar pair=Pair{left:&a,right:&b};\n'+'pair=swap(&a,&b);\n'*count+'*pair.left\n*pair.right\n','8\n7\n',0)
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
 native=tmp/'Native.cool';text=native.read_text();assert text.endswith('LanguageMain;\n');native.write_text(text+'AuditGraphReport;\n')
 binary=tmp/'frontend.BIN';env={**os.environ,'COOLC_COMPILER_BIN':str(ROOT/'coolc/seed/Compiler.BIN')}
 r=subprocess.run([ROOT/'build/coolc',native,binary],env=env,cwd=ROOT,text=True,capture_output=True,timeout=90);assert r.returncode==0,r
 observations=[]
 for name in ('field_access','opaque_returns','recursive_returns','failed_functions','stores'):
  rows=[]
  for count in args.counts:
   source,output,errors=workload(name,count)
   r=subprocess.run([ROOT/'build/coolc','--run',binary,'repl-quiet'],input=source+':quit\n',cwd=ROOT,text=True,capture_output=True,timeout=120)
   matched=re.findall(r'^GRAPH_ALLOCATION_REPORT (\d+) (\d+) (\d+)\n',r.stdout,re.M);assert len(matched)==1,r
   assert r.returncode==0 and r.stdout.split('GRAPH_ALLOCATION_REPORT ')[0]==output and r.stderr.count('error:')==errors,(name,count,r)
   live,allocations,peak=map(int,matched[0]);assert (live,allocations)==(0,0),(name,count,matched)
   row={'workload':name,'submissions':count,'live_bytes':live,'live_count':allocations,'peak_bytes':peak};rows.append(row);observations.append(row)
  assert len({r['peak_bytes'] for r in rows})==1,rows
  print(name+': '+', '.join(f'{r["submissions"]} => final {r["live_bytes"]}/{r["live_count"]}, peak {r["peak_bytes"]}' for r in rows))
 assert hashes=={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},'source changed during snapshot audit'
 report={'source_sha256':hashes,'counts':args.counts,'observations':observations,'method':'Private copies of actual legacy frontend sources; track allocations/frees inside Provenance.cool only (nodes, edges, product-query/copy scratch). Tracking bookkeeping excluded; graph arenas, loans, other compiler metadata and JIT mappings not measured. Actual seed-compiled BIN REPL; all tracked graph allocations must reach zero on cleanup and peaks remain equal across repeated history lengths. No production artifacts modified.'}
 if args.output:args.output.write_text(json.dumps(report,indent=2)+'\n')
print('legacy graph lifecycle PASS')
