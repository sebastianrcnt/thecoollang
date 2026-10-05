#!/usr/bin/env python3
"""Independent two-channel dataflow oracle for reference origins/storage effects."""
import argparse, hashlib, json, random, re, shlex, shutil, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);p.add_argument('--output',type=Path);args=p.parse_args()
def run(command,**kw):return subprocess.run(list(map(str,command)),cwd=ROOT,capture_output=True,text=True,timeout=60,**kw)
def oracle(bindings,stores):
    initial={'a':1,'b':2,'s':4,'t':8}
    names=set(initial)|set(bindings)
    origins={name:initial.get(name,0) for name in names}
    value_edges={name:set(bindings.get(name,())) for name in names}
    # Independent worklist closes aliases before propagating store effects.
    for dst,src in stores:
        pending=[dst];seen=set()
        while pending:
            name=pending.pop()
            if name in seen:continue
            seen.add(name);value_edges[name].add(src)
            pending.extend(bindings.get(name,()))
    values=dict(origins)
    changed=True
    while changed:
        changed=False
        for name in names:
            old=(values[name],origins[name])
            for source in value_edges[name]:values[name]|=values[source]
            for source in bindings.get(name,()):origins[name]|=origins[source]
            changed|=old!=(values[name],origins[name])
    return {name:(values[name],origins[name]) for name in names}
def cases():
    for seed in (7,42,2026):
        rng=random.Random(seed)
        for count in (2,6,12):
            bindings={};lines=[]
            for i in range(count):
                name=f'r{i}';source=rng.choice(['a','b']+list(bindings))
                bindings[name]={source};lines.append(f'var {name}={source};')
            for _ in range(count*2):
                dst,src=rng.choice(list(bindings)),rng.choice(['a','b']+list(bindings))
                bindings[dst].add(src);lines.append(f'{dst}={src};')
            stores=[]
            for _ in range(3):
                dst,src=rng.choice(list(bindings)),rng.choice(['s','t'])
                stores.append((dst,src));lines.append(f'(*{dst}).r={src};')
            yield f'seed{seed}-{count}',lines,oracle(bindings,stores)
    # Binding sources are gathered first even when a later branch introduces one.
    bindings={'r':{'a','b'}}
    yield 'late branch',['var r=a;','(*r).r=s;','if(true){r=b;}'],oracle(bindings,[('r','s')])
    yield 'computed reborrow',['var r=a;','let q=&mut *r;','(*q).r=s;'],oracle({'r':{'a'},'q':{'r'}},[('q','s')])
    yield 'stored alias source',['var r=a;','let q=s;','(*r).r=q;'],oracle({'r':{'a'},'q':{'s'}},[('r','q')])
    yield 'seed cyclic queries',['var r0=a;','var r1=b;','r0=r1;','r1=r0;','(*r0).r=s;','(*r1).r=t;'],oracle({'r0':{'a','r1'},'r1':{'b','r0'}},[('r0','s'),('r1','t')])
    bindings={'r0':{'a'}};lines=['var r0=a;']
    for i in range(1,33):bindings[f'r{i}']={f'r{i-1}'};lines.extend([f'var r{i}=r{i-1};',f'r{i}=r{i-1};'])
    lines.append('(*r32).r=s;')
    yield 'seed diamond32',lines,oracle(bindings,[('r32','s')])
    yield 'contract result',['var r=pick(a,b,true);','(*r).r=t;'],oracle({'r':{'a','b'}},[('r','t')])
SHIM='''#include <stdint.h>
#include <stdio.h>
#include <string.h>
static const void *queries[256];static int visits[256],total;
int64_t BorrowVisit(const void *source){int i;for(i=0;i<total;i++)if(queries[i]==source)break;if(i==total){if(total==256)__builtin_trap();queries[total++]=source;}visits[i]++;return 0;}
__attribute__((destructor)) static void finish(void){for(int i=0;i<total;i++)fprintf(stderr,"BORROW_DEST %d\\n",visits[i]);}
int64_t BorrowAudit(const char *function,const char *name,int64_t value,int64_t origin){
 if(!strcmp(function,"Audit"))fprintf(stderr,"BORROW_ORIGIN %s %lld %lld\\n",name,(long long)value,(long long)origin);
 return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='cool borrow origins ') as directory:
    tmp=Path(directory);wrapper=tmp/'bootstrap'
    wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');wrapper.chmod(0o755)
    fronts=[ROOT/'build/cool-compiler',wrapper]
    if args.frontend:fronts.append(args.frontend.resolve())
    copied=tmp/'borrow.cool';text=(ROOT/'compiler/04-borrow.cool').read_text()
    hook=' CheckBorrowReturns(function.body,function);'
    assert text.count(hook)==1
    text=text.replace('fn RecordBorrowDestination(node:*Node,source:*Node){unsafe{','fn RecordBorrowDestination(node:*Node,source:*Node){unsafe{BorrowVisit(source);')
    text=text.replace(hook,' PropagateBorrowRegions(function);var local=function.all_locals;while(local!=null){BorrowAudit(function.name,local.name,local.region,local.place_region);local=local.all_next;}\n'+hook)
    copied.write_text('extern "C" fn BorrowVisit(source:*Node)->i64;\nextern "C" fn BorrowAudit(function:*u8,name:*u8,value:i64,origin:i64)->i64;\n'+text)
    manifest=tmp/'compiler.sources';manifest.write_text(''.join('__main\t'+str(copied if file.name=='04-borrow.cool' else file)+'\n' for file in sorted((ROOT/'compiler').glob('*.cool'))))
    ir=tmp/'compiler.ll';result=run([fronts[0],'llvm-bundle',manifest,ir]);assert result.returncode==0,result
    shim=tmp/'audit.c';shim.write_text(SHIM);traced=tmp/'traced-compiler'
    objects=[]
    for name in ('compiler-host.o','language-runtime.o'):
        target=tmp/name;shutil.copy2(ROOT/'build'/name,target);objects.append(target)
    digests={str(file.relative_to(ROOT)):hashlib.sha256(file.read_bytes()).hexdigest() for file in sorted((ROOT/'compiler').glob('*.cool'))}
    for file in objects+[copied,ir,shim]:digests['private/'+file.name]=hashlib.sha256(file.read_bytes()).hexdigest()
    digests['build/cool-compiler']=hashlib.sha256(fronts[0].read_bytes()).hexdigest()
    result=run(['clang','-Wno-override-module','-O2',ir,shim,*objects,'-lffi','-o',traced]);assert result.returncode==0,result
    source=tmp/'main.cool';queries=0;observations=[]
    prelude='struct View{r:&i64;}fn pick(a:&mut View,b:&mut View,yes:bool)->&mut View borrows(a,b){if(yes){return a;}return b;}'
    for label,lines,expected in cases():
        code=prelude+'fn Audit(a:&mut View,b:&mut View,s:&i64,t:&i64){'+''.join(lines)+'}fn main(){}'
        source.write_text(code)
        for front in fronts:
            result=run([front,'check',source]);assert result.returncode==2 and ('replaced through a reference' in result.stderr or (label.startswith('seed') and 'conflicts' in result.stderr)),(label,front,result)
        result=run([traced,'check',source]);assert result.returncode==2 and ('replaced through a reference' in result.stderr or (label.startswith('seed') and 'conflicts' in result.stderr)),(label,result)
        actual={name:(int(value),int(origin)) for name,value,origin in re.findall(r'^BORROW_ORIGIN (\w+) (\d+) (\d+)$',result.stderr,re.M)}
        assert actual==expected,(label,actual,expected)
        visits=list(map(int,re.findall(r'^BORROW_DEST (\d+)$',result.stderr,re.M)))
        assert len(visits)==sum('.r=' in line for line in lines),(label,visits)
        # Two propagation passes, conservatively bounded by generated nodes.
        assert all(count<=20*len(expected) for count in visits),(label,visits,expected)
        observations.append(dict(case=label,channels=expected,destination_visits=visits));queries+=2*len(expected)
    # Accepted direct replacement, payload loads, and return contract checking.
    source.write_text('struct View{r:&i64;}fn Audit(a:&i64,b:&i64)->View borrows(a,b){var v=View{r:a};v.r=b;let q=v.r;return v;}fn main(){}')
    for front in fronts:
        result=run([front,'check',source]);assert (result.returncode,result.stdout,result.stderr)==(0,'',''),(front,result)
    result=run([traced,'check',source]);assert result.returncode==0,result
    actual={name:(int(value),int(origin)) for name,value,origin in re.findall(r'^BORROW_ORIGIN (\w+) (\d+) (\d+)$',result.stderr,re.M)}
    assert actual=={'a':(1,1),'b':(2,2),'v':(3,1),'q':(3,3)},actual;queries+=8
    source.write_text(source.read_text().replace('borrows(a,b)','borrows(a)'))
    for front in fronts:
        result=run([front,'check',source]);assert result.returncode==2 and 'borrows contract' in result.stderr,(front,result)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(dict(artifact_sha256=digests,queries=queries,observations=observations,method='Private source-instrumented native compiler; two monotone propagation passes, separate Python worklist oracle and per-store destination visit bound. Runtime/host object copies; normal frontend rejects unsupported receiver writes. No cross-call mutation acceptance claimed.'),indent=2,sort_keys=True)+'\n')
print(f'borrow origins: 15 seeded/alias/branch/computed graphs and direct replacement; {queries} independently modeled value/origin channels; idempotent propagation and bounded alias diamond32 walks, unsupported receiver writes and return contracts enforced on {len(fronts)} frontends PASS')
