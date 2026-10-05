#!/usr/bin/env python3
"""Track compiler-owned allocations in copied emitted IR, never rebuild shared artifacts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--counts',type=int,nargs='+',default=[64,1024])
parser.add_argument('--output',type=Path)
parser.add_argument('--observe',action='store_true',help='Collect lifecycle deltas without asserting bounded retention')
args=parser.parse_args()
if len(args.counts)<2 or min(args.counts)<1:parser.error('provide at least two positive counts')
SHIM=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern void *CAlloc(int64_t);
extern void Free(void *);
extern char *StrNew(const char *);
extern void *FileRead(const char *,int64_t *,void *);
struct allocation {void *ptr;int64_t size;struct allocation *next;};
static struct allocation *head;
static int64_t live_bytes,peak_bytes,live_count;
static void record(void *ptr,int64_t size){
    struct allocation *item=malloc(sizeof(*item));if(!item)abort();
    item->ptr=ptr;item->size=size;item->next=head;head=item;
    live_bytes+=size;live_count++;if(live_bytes>peak_bytes)peak_bytes=live_bytes;
}
void *ReplTrackedAlloc(int64_t size){void *ptr=CAlloc(size);record(ptr,size);return ptr;}
void *ReplTrackedFileRead(const char *path,int64_t *size,void *attrs){void *ptr=FileRead(path,size,attrs);if(ptr && size)record(ptr,*size+1);return ptr;}
char *ReplTrackedStrNew(const char *text){char *ptr=StrNew(text);record(ptr,strlen(text)+1);return ptr;}
void ReplTrackedFree(void *ptr){
    struct allocation **link=&head;
    while(*link && (*link)->ptr!=ptr)link=&(*link)->next;
    if(*link){struct allocation *item=*link;*link=item->next;live_bytes-=item->size;live_count--;free(item);}
    Free(ptr);
}
__attribute__((destructor)) static void finish(void){
    fprintf(stderr,"REPL_ALLOCATION_REPORT {\"live_bytes\":%lld,\"peak_bytes\":%lld,\"live_count\":%lld,\"sizes\":{",(long long)live_bytes,(long long)peak_bytes,(long long)live_count);
    int first=1;
    for(struct allocation *item=head;item;item=item->next){
        int seen=0;for(struct allocation *prior=head;prior!=item;prior=prior->next)if(prior->size==item->size){seen=1;break;}
        if(seen)continue;
        long long count=0;for(struct allocation *other=item;other;other=other->next)if(other->size==item->size)count++;
        fprintf(stderr,"%s\"%lld\":%lld",first?"":",",(long long)item->size,count);first=0;
    }
    fprintf(stderr,"}}\n");
}
'''

def workload(name,count):
    if name=='rejected_literals':
        return ('var kept="stable";\n'+''.join(f'fn rejected{i}()->string{{let text="unique {i}";return missing;}}\n' for i in range(count))+'kept\n', 'stable\n',count)
    if name=='rejected_types':
        return ('var kept=7;\n'+ 'struct Rejected{first:i64;bad:Missing;}\n'*count+'kept\n','7\n',count)
    if name=='lazy_layout_rollback':
        return ('struct Bad[T]{first:T;second:[2]T;}\nstruct Phantom[T]{}\nlet phantom=Phantom[Bad[[65536]i64]]{};\n'+'Bad[[65536]i64]{}\n'*count+'let good=Bad[i64]{first:7,second:[2]i64{41,42}};\ngood.second[1]\n','42\n',count)
    if name=='lexer_rollback':
        return ('let kept="stable";\n'+ 'let rejected="bad\\q";\n'*count+'kept\n','stable\n',count)
    if name=='replacements':
        return ('fn value()->i64{return 7;}\nfn caller()->i64{return value();}\n'+'fn value()->i64{return 7;}\n'*count+'caller()\n','7\n',0)
    if name=='scratch_calls':
        return ('fn identity[T](value:T)->T{return value;}\nvar total=0;\n'+'{assert(identity[i64](7)==7);total=total+1;}\n'*count+'total\n',str(count)+'\n',0)
    if name=='runtime_rollback':
        return ('import "std/mem";\nvar kept=7;\n'+'{let temporary=new[i64](9);assert(false);}\n'*count+'kept\nmem.owner_count()\n','7\n0\n',count)
    if name=='rejected_imports':
        return ('var kept=7;\n'+''.join(f'import alias{i} "std/mem";fn rejected()->i64{{return missing;}}\n' for i in range(count))+'kept\n','7\n',count)
    if name=='mixed_declaration_rollback':
        return ('var kept=7;\n'+ 'struct Rejected{first:i64;}fn rejected(value:Rejected)->i64{return missing;}\n'*count+'kept\n','7\n',count)
    if name=='existing_layout_signature_rollback':
        return ('struct Holder[T]{first:T;second:[2]T;}\nstruct Phantom[T]{}\nlet phantom=Phantom[Holder[i64]]{};\n'+ 'fn rejected(value:Holder[i64])->i64{return missing;}\n'*count+'let good=Holder[i64]{first:7,second:[2]i64{41,42}};\ngood.second[1]\n','42\n',count)
    if name=='source_generic_compaction':
        return ('fn value()->i64{return 7;}\nstruct Box[T]{value:T;}\nfn get[T](value:Box[T])->T{return value.value;}\n'+'fn value()->i64{return 7;}\n'*count+'get[i64](Box[i64]{value:value()})\n','7\n',0)
    if name=='duplicate_batch_rollback':
        return ('fn value()->i64{return 7;}\n'+'fn value()->i64{return 8;}fn value()->i64{return 9;}\n'*count+'value()\n','7\n',count)
    if name=='oversized_local_rollback':
        return ('var kept=7;\n'+'var rejected=[32768]i64{};\n'*count+'kept\n','7\n',count)
    if name=='package_rollback':
        return ('var kept=7;\n'+'import bad "example.test/lifecycle/bad";\n'*count+'kept\n','7\n',count)
    if name=='interior_owner_reuse':
        prefix='import "std/mem";\nvar hole=[16384]i64{};\nvar keeper=42;\nlet r=&mut keeper;\n:forget hole\n'
        cycle='var next=[8192]own[i64]{};\nnext[8191]=new[i64](7);\n:forget next\n'
        return (prefix+cycle*count+'*r\nmem.owner_count()\n','42\n0\n',0)
    if name=='interior_runtime_rollback':
        prefix='import "std/mem";\nvar hole=[16384]i64{};\nvar keeper=42;\nlet r=&mut keeper;\n:forget hole\nfn fail()->own[i64]{let owner=new[i64](7);assert(false);return move owner;}\n'
        cycle='var poison=123;\n:forget poison\nvar bad=fail();\n'
        return (prefix+cycle*count+'*r\nmem.owner_count()\n','42\n0\n',count)
    if name=='reference_replacement_roots':
        prefix='var x=7;\nvar y=8;\nvar r=&x;\n'
        return (prefix+'r=&y;\n'*count+'*r\nx=2;\ny=2;\n:forget r\nx=2;\ny=2;\ny\n','8\n2\n',2)
    if name=='stored_call_roots':
        prefix='struct View{r:&i64;}\nfn set(dst:&mut View,src:&i64) stores(dst,src){(*dst).r=src;}\nvar x=7;\nvar y=8;\nvar v=View{r:&x};\n'
        return (prefix+'set(&mut v,&y);\n'*count+'*v.r\nx=2;\ny=2;\n:forget v\nx=2;\ny=2;\ny\n','8\n2\n',2)
    if name=='stored_parameter_replacements':
        prefix='struct View{r:&i64;}\n'
        setter='fn set(dst:&mut View,src:&i64) stores(dst,src){(*dst).r=src;}\n'
        return (prefix+setter*count+'var x=7;\nvar y=8;\nvar v=View{r:&x};\nset(&mut v,&y);\n*v.r\n','8\n',0)
    if name=='shared_ancestry_diamonds':
        prefix='fn choose(a:&i64,b:&i64)->&i64 borrows(a,b){return a;}\nvar x=7;\nlet a=&x;\nlet b=&x;\nvar q=choose(a,b);\n'
        return (prefix+'q=choose(a,b);\n'*count+'*q\n:forget a\n:forget q\n:forget a\n:forget b\nx=8;\nx\n','7\n8\n',1)
    if name=='kept_field_graphs':
        prefix='struct Pair{left:&i64;right:&i64;}\nvar x=7;\nvar y=8;\nvar assigned=Pair{left:&x,right:&y};\n'
        return (prefix+'assigned=Pair{left:&x,right:&y};\n'*count+'*assigned.left\n*assigned.right\n','7\n8\n',0)
    if name=='kept_selected_graphs':
        prefix='struct Pair{left:&i64;right:&i64;}\nstruct Outer{inner:Pair;}\nvar x=7;\nvar y=8;\nlet other=Outer{inner:Pair{left:&x,right:&y}};\nvar assigned=other;\n'
        return (prefix+'assigned=Outer{inner:other.inner};\n'*count+'*assigned.inner.left\n*assigned.inner.right\n','7\n8\n',0)
    if name=='kept_partial_store_graphs':
        prefix='struct Pair{left:&i64;right:&i64;}\nvar x=7;\nvar y=8;\nvar z=9;\nvar stored=Pair{left:&x,right:&y};\nlet receiver=&mut stored;\n'
        return (prefix+'(*receiver).left=&z;\n'*count+'*(*receiver).left\n*(*receiver).right\n','9\n8\n',0)
    if name=='kept_opaque_store_graphs':
        prefix='struct Pair{left:&i64;right:&i64;}\nfn setright(dst:&mut Pair,src:&i64) stores(dst,src){(*dst).right=src;}\nvar x=7;\nvar y=8;\nvar z=9;\nvar stored=Pair{left:&x,right:&y};\nlet receiver=&mut stored;\n'
        return (prefix+'setright(receiver,&z);\n'*count+'*(*receiver).left\n*(*receiver).right\n','7\n9\n',0)
    if name=='typed_parameter_replacements':
        prefix='struct Probe{shared:&i64;mutable:&mut i64;count:i64;}\nenum Chain{End;Link(Entry);}struct Entry{next:own[Chain];r:&i64;}\n'
        cycle='fn param(p:own[Chain]){}\nfn fields(p:Probe){}\nfn slice(p:[]i64){}\n'
        return (prefix+cycle*count+'var kept=7;\nkept\n','7\n',0)
    if name=='computed_reborrow_graphs':
        prefix='struct Pair{left:&i64;right:&i64;}\nvar x=7;\nvar y=8;\nvar container=Pair{left:&x,right:&y};\nvar q=&(*(&container)).left;\n'
        return (prefix+'q=&(*(&container)).left;\n'*count+'**q\n','7\n',0)
    if name=='opaque_return_graphs':
        prefix='struct Pair{left:&i64;right:&i64;}\nfn swap(a:&i64,b:&i64)->Pair borrows(a,b){return Pair{left:b,right:a};}\nvar x=7;\nvar y=8;\nvar result=Pair{left:&x,right:&y};\n'
        return (prefix+'result=swap(&x,&y);\n'*count+'*result.left\n*result.right\n','8\n7\n',0)
    if name=='nested_return_graphs':
        prefix='struct Pair{left:&i64;right:&i64;}\nfn identity(p:&mut Pair)->&mut Pair borrows(p){return p;}\nvar x=7;\nvar y=8;\nvar container=Pair{left:&x,right:&y};\nvar r=&mut container;\n'
        return (prefix+'r=identity(r);\n'*count+'*(*r).left\n*(*r).right\n','7\n8\n',0)
    if name=='recursive_return_graphs':
        prefix='import "std/mem";\nenum Chain{End;Link(Entry);}struct Entry{next:own[Chain];r:&i64;}\nfn identity(p:own[Chain])->own[Chain] borrows(p){return move p;}\nvar x=7;\nvar p=new[Chain](Chain.Link(Entry{next:new[Chain](Chain.End),r:&x}));\n'
        return (prefix+'p=identity(move p);\n'*count+'mem.owner_count()\n:forget p\nmem.owner_count()\n','2\n0\n',0)
    if name=='rejected_loan_analysis':
        return ('fn fail(){var x=1;let r=&x;x=2;}\n'*count+'var x=1;\nx\n','1\n',count)
    if name=='distinct_literals_policy':
        return ('var kept="stable";\n'+''.join(f'{{let temporary="unique {i}";assert(false);}}\n' for i in range(count))+'kept\n','stable\n',count)
    raise AssertionError(name)

with tempfile.TemporaryDirectory(prefix='cool-repl-lifecycle-') as directory:
    tmp=Path(directory);names=['compiler-stage2.ll','compiler-host.o','language-runtime.o']
    digests={name:hashlib.sha256((ROOT/'build'/name).read_bytes()).hexdigest() for name in names}
    for name in names:shutil.copy2(ROOT/'build'/name,tmp/name)
    if any(hashlib.sha256((ROOT/'build'/name).read_bytes()).hexdigest()!=digests[name] or hashlib.sha256((tmp/name).read_bytes()).hexdigest()!=digests[name] for name in names):
        raise RuntimeError('Shared artifacts changed during diagnostic snapshot; retry after build completes')
    ir=(tmp/'compiler-stage2.ll').read_text()
    for original,replacement in [('CAlloc','ReplTrackedAlloc'),('StrNew','ReplTrackedStrNew'),('Free','ReplTrackedFree'),('FileRead','ReplTrackedFileRead')]:
        if '@'+original+'(' not in ir:raise AssertionError('instrumentation target missing: '+original)
        ir=ir.replace('@'+original+'(', '@'+replacement+'(')
    (tmp/'tracked.ll').write_text(ir);(tmp/'tracker.c').write_text(SHIM)
    frontend=tmp/'tracked-compiler'
    subprocess.run(['clang','-Wno-override-module','-O2',tmp/'tracked.ll',tmp/'tracker.c',tmp/'compiler-host.o',tmp/'language-runtime.o','-lffi','-o',frontend],check=True,capture_output=True)
    project=tmp/'project';(project/'bad').mkdir(parents=True)
    (project/'cool.mod').write_text('module example.test/lifecycle\n')
    (project/'bad/bad.cool').write_text('package bad;pub fn broken()->i64{return missing;}')
    observations=[]
    for name in ('rejected_literals','rejected_types','lazy_layout_rollback','lexer_rollback','replacements','scratch_calls','runtime_rollback','rejected_imports','mixed_declaration_rollback','existing_layout_signature_rollback','source_generic_compaction','duplicate_batch_rollback','oversized_local_rollback','package_rollback','interior_owner_reuse','interior_runtime_rollback','reference_replacement_roots','stored_call_roots','stored_parameter_replacements','shared_ancestry_diamonds','kept_field_graphs','kept_selected_graphs','kept_partial_store_graphs','kept_opaque_store_graphs','typed_parameter_replacements','computed_reborrow_graphs','opaque_return_graphs','nested_return_graphs','recursive_return_graphs','rejected_loan_analysis','distinct_literals_policy'):
        rows=[]
        for count in args.counts:
            source,output,errors=workload(name,count)
            command=[ROOT/'tools/cool','repl','--offline','--frozen'] if name=='package_rollback' else [frontend,'repl-quiet']
            result=subprocess.run(command,cwd=project,env={**os.environ,'COOL_FRONTEND':str(frontend),'COOL_CACHE':str(tmp/'cache')},input=source+':quit\n',text=True,capture_output=True,timeout=120)
            assert result.returncode==0 and result.stdout==output and result.stderr.count('error:')==errors,(name,count,result)
            matched=re.findall(r'^REPL_ALLOCATION_REPORT (.*)$',result.stderr,re.M)
            assert len(matched)==1,result.stderr
            row=dict(workload=name,submissions=count,**json.loads(matched[0]));rows.append(row);observations.append(row)
        bounded=name!='distinct_literals_policy'
        if bounded and not args.observe:
            assert all(row['live_bytes']==rows[0]['live_bytes'] and row['live_count']==rows[0]['live_count'] for row in rows),rows
        if name in ('reference_replacement_roots','stored_call_roots','stored_parameter_replacements','shared_ancestry_diamonds','kept_field_graphs','kept_selected_graphs','kept_partial_store_graphs','kept_opaque_store_graphs','typed_parameter_replacements','computed_reborrow_graphs','opaque_return_graphs','nested_return_graphs','recursive_return_graphs','rejected_loan_analysis') and not args.observe:
            assert all(row['peak_bytes']==rows[0]['peak_bytes'] for row in rows),rows
        print(name+': '+', '.join(f'{row["submissions"]} => {row["live_bytes"]} bytes/{row["live_count"]} allocations' for row in rows))
    report=dict(artifact_sha256=digests,counts=args.counts,observations=observations,method='Copied emitted compiler IR call-site instrumentation for CAlloc, StrNew, FileRead (with size output) and Free; fresh REPL process per observation. Shim bookkeeping uses separate host malloc. Final live allocations measured at process exit after REPL cleanup, including fixed compiler tables/live declarations and policy-retained literal text. Other host-internal allocations and JIT mappings are not covered; peak bytes are diagnostic instrumentation data, not production RSS. No compiler source regeneration or shared artifact mutation.')
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
print('REPL lifecycle allocation instrumentation '+('observations complete' if args.observe else 'PASS'))
