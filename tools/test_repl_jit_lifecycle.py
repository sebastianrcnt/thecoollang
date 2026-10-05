#!/usr/bin/env python3
"""Audit JIT mapping ownership using a private snapshot; never regenerate compiler IR."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SHIM = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
extern void *NativeJitAlloc(int64_t);
extern void NativeJitFree(void *,int64_t);
struct mapping {void *address;int64_t size,pages;struct mapping *next;};
static struct mapping *head;
static int64_t live_count,live_bytes,requested_bytes,peak_bytes,allocations,releases;
static void fail(const char *reason){fprintf(stderr,"JIT_MAPPING_ERROR %s\n",reason);exit(71);}
void *ReplTrackedJitAlloc(int64_t size){
    if(size<=0)fail("nonpositive allocation size");
    void *address=NativeJitAlloc(size);
    for(struct mapping *p=head;p;p=p->next)if(p->address==address)fail("duplicate live mapping");
    long page=sysconf(_SC_PAGESIZE);if(page<=0)fail("invalid page size");
    struct mapping *p=malloc(sizeof(*p));if(!p)fail("tracker allocation");
    p->address=address;p->size=size;p->pages=((size-1)/page+1)*page;p->next=head;head=p;
    live_count++;requested_bytes+=size;live_bytes+=p->pages;allocations++;
    if(live_bytes>peak_bytes)peak_bytes=live_bytes;
    return address;
}
void ReplTrackedJitFree(void *address,int64_t size){
    if(!address)return;
    struct mapping **link=&head;while(*link && (*link)->address!=address)link=&(*link)->next;
    if(!*link)fail("unknown or double free");
    struct mapping *p=*link;if(p->size!=size)fail("release size mismatch");
    NativeJitFree(address,size);*link=p->next;
    live_count--;requested_bytes-=size;live_bytes-=p->pages;releases++;free(p);
}
__attribute__((destructor)) static void finish(void){
    fprintf(stderr,"REPL_JIT_REPORT {\"live_count\":%lld,\"live_bytes\":%lld,\"requested_bytes\":%lld,\"peak_bytes\":%lld,\"allocations\":%lld,\"releases\":%lld,\"mappings\":[",(long long)live_count,(long long)live_bytes,(long long)requested_bytes,(long long)peak_bytes,(long long)allocations,(long long)releases);
    int first=1;while(head){struct mapping *p=head;head=p->next;
        fprintf(stderr,"%s{\"address\":\"%p\",\"size\":%lld,\"page_bytes\":%lld}",first?"":",",p->address,(long long)p->size,(long long)p->pages);first=0;free(p);
    }fprintf(stderr,"]}\n");
}
'''


def workload(name, count):
    prefix = 'import "std/mem";\nvar total=0;\n'
    calls = '{total=caller();total=caller();total=caller();total=caller();}\n'
    if name == 'warm_replacements':
        source = prefix+'fn value()->i64{return 1;}\nfn caller()->i64{return value();}\n'+calls
        output = ''
        for value in range(2, count+2):
            source += f'fn value()->i64{{var owned=new[i64]({value});return *owned;}}\n'+calls+'total\nmem.owner_count()\n'
            output += f'{value}\n0\n'
        return source, output, 0, 2
    prefix += 'fn bomb(n:i64)->i64{var owner=new[i64](n);assert(n<4);return *owner;}\n'
    if name == 'cold_new_jit_rollback':
        source = prefix+'{total=bomb(1);total=bomb(2);total=bomb(3);total=bomb(4);}\n'*count
        return source+'total\nmem.owner_count()\nbomb(2)\nmem.owner_count()\n', '3\n0\n2\n0\n', count, 0
    if name == 'new_jit_preserves_bytecode':
        source = prefix+'bomb(1)\n'+'{total=bomb(2);total=bomb(3);total=bomb(4);}\n'*count
        return source+'bomb(2)\nmem.owner_count()\n', '1\n2\n0\n', count, 0
    if name == 'existing_jit_rollback':
        source = prefix+'bomb(1)\n'*4+'bomb(4)\n'*count
        return source+'bomb(2)\nmem.owner_count()\n', '1\n'*4+'2\n0\n', count, 1
    raise AssertionError(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--counts', type=int, nargs='+', default=[64, 1024])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--observe', action='store_true', help='Collect reports without bounded-history assertions')
    args = parser.parse_args()
    if len(args.counts)<2 or min(args.counts)<1:
        parser.error('provide at least two positive counts')
    with tempfile.TemporaryDirectory(prefix='cool-repl-jit-lifecycle-') as directory:
        tmp = Path(directory)
        names = ['compiler-stage2.ll', 'compiler-host.o', 'language-runtime.o']
        digests = {name: hashlib.sha256((ROOT/'build'/name).read_bytes()).hexdigest() for name in names}
        for name in names:
            shutil.copy2(ROOT/'build'/name, tmp/name)
        for name in names:
            if any(hashlib.sha256(path.read_bytes()).hexdigest()!=digests[name] for path in (ROOT/'build'/name,tmp/name)):
                raise RuntimeError('Shared artifacts changed during snapshot; retry after build completes')
        ir = (tmp/'compiler-stage2.ll').read_text()
        for original, replacement in [('NativeJitAlloc','ReplTrackedJitAlloc'),('NativeJitFree','ReplTrackedJitFree')]:
            if '@'+original+'(' not in ir:
                raise AssertionError('instrumentation target missing: '+original)
            ir = ir.replace('@'+original+'(', '@'+replacement+'(')
        (tmp/'tracked.ll').write_text(ir)
        (tmp/'tracker.c').write_text(SHIM)
        frontend = tmp/'tracked-compiler'
        subprocess.run(['clang','-Wno-override-module','-O2',tmp/'tracked.ll',tmp/'tracker.c',tmp/'compiler-host.o',tmp/'language-runtime.o','-lffi','-o',frontend], check=True, capture_output=True)
        observations = []
        for name in ('warm_replacements','cold_new_jit_rollback','new_jit_preserves_bytecode','existing_jit_rollback'):
            rows = []
            for count in args.counts:
                source, output, errors, expected_live = workload(name,count)
                result = subprocess.run([frontend,'repl-quiet'], input=source+':quit\n', text=True, capture_output=True, cwd=ROOT, timeout=120)
                assert result.returncode==0 and result.stdout==output, (name,count,result)
                assert result.stderr.count('error:')==errors and result.stderr.count('assertion failed')==errors, (name,count,result.stderr)
                reports = re.findall(r'^REPL_JIT_REPORT (.*)$',result.stderr,re.M)
                assert len(reports)==1 and 'JIT_MAPPING_ERROR' not in result.stderr, result.stderr
                row = dict(workload=name,submissions=count,**json.loads(reports[0]))
                expected_allocations = count+2 if name=='warm_replacements' else (1 if name=='existing_jit_rollback' else count)
                expected_releases = 0 if name=='existing_jit_rollback' else count
                assert (row['allocations'],row['releases'])==(expected_allocations,expected_releases), row
                assert row['allocations']-row['releases']==row['live_count']==len(row['mappings']), row
                if not args.observe:
                    assert row['live_count']==expected_live, row
                rows.append(row);observations.append(row)
            if not args.observe:
                assert all((row['live_count'],row['live_bytes'],row['requested_bytes'])==(rows[0]['live_count'],rows[0]['live_bytes'],rows[0]['requested_bytes']) for row in rows), rows
            print(name+': '+', '.join(f'{row["submissions"]} => {row["live_count"]} mappings/{row["live_bytes"]} page bytes, {row["allocations"]} allocated/{row["releases"]} released' for row in rows))
        report = dict(artifact_sha256=digests,counts=args.counts,observations=observations,method='Private copied emitted IR NativeJitAlloc/Free call-site wrappers; fresh process for each observation. Unknown/double free and requested-size mismatch fail immediately. Page bytes use host sysconf page size; mapping addresses are diagnostic and vary by process. Current function mappings survive until process exit by policy. Counts do not measure RSS, arbitrary host/library allocations, all possible REPL inputs, or prove absence of dangling accesses.')
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(report,indent=2)+'\n')
    print('REPL JIT mapping lifecycle '+('observations complete' if args.observe else 'PASS'))


if __name__ == '__main__':
    main()
