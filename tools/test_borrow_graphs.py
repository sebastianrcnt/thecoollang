#!/usr/bin/env python3
"""Independent reachability oracle and bounded-work audit for borrowed type graphs."""
import argparse, os, random, re, shlex, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);args=p.parse_args()
def run(command,**kw):return subprocess.run(list(map(str,command)),cwd=ROOT,capture_output=True,text=True,timeout=30,**kw)
def reachable(nodes,start,exclusive):
    seen=set();pending=[start]
    while pending:
        current=pending.pop()
        if current in seen:continue
        seen.add(current);node=nodes[current]
        if node['terminal'] in (('mut','slice') if exclusive else ('shared','mut','slice')):return 1
        pending.extend(target for target,_ in node['edges'])
    return 0

def source(nodes):
    declarations=[]
    for i,node in enumerate(nodes):
        fields=[f'e{j}:'+ (f'own[N{target}]' if kind=='own' else f'[2]own[N{target}]')+';' for j,(target,kind) in enumerate(node['edges'])]
        if node['terminal']:fields.append('terminal:'+{'shared':'&i64','mut':'&mut i64','slice':'[]i64'}[node['terminal']]+';')
        if not fields:fields=['value:i64;']
        declarations.append(f'struct N{i}{{'+''.join(fields)+'}')
    return '\n'.join(declarations)+ '\n'+ '\n'.join(f'fn inspect{i}(p:N{i}){{let q=move p;}}' for i in range(len(nodes)))+'\nfn main(){}\n'

def cases():
    yield 'empty cycle',[{'edges':[(0,'own')],'terminal':None}]
    yield 'late shared cycle',[{'edges':[(1,'own')],'terminal':None},{'edges':[(0,'own')],'terminal':'shared'}]
    yield 'late exclusive cycle',[{'edges':[(1,'array')],'terminal':None},{'edges':[(0,'own')],'terminal':'mut'}]
    yield 'two terminals',[{'edges':[(1,'own'),(2,'own')],'terminal':None},{'edges':[(0,'own')],'terminal':'shared'},{'edges':[(0,'own')],'terminal':'mut'}]
    for depth in (20,40):
        yield f'diamond {depth}',[{'edges':[],'terminal':None}]+[{'edges':[(i-1,'own'),(i-1,'own')],'terminal':None} for i in range(1,depth+1)]
    for seed in (7,42,2026):
        rng=random.Random(seed)
        for trial in range(4):
            nodes=[{'edges':[(rng.randrange(8),rng.choice(('own','array'))) for _ in range(rng.randrange(3))],'terminal':rng.choice((None,None,'shared','mut','slice'))} for _ in range(8)]
            yield f'seed {seed} trial {trial}',nodes
            yield f'seed {seed} trial {trial} reversed',[dict(node,edges=list(reversed(node['edges']))) for node in nodes]
SHIM=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <ctype.h>
#include <string.h>
static char names[4096][32];
static struct {int64_t type,mode,calls;} stack[1024];
static int depth;
void GraphName(int64_t type,int64_t pointer){
 const char *name=(const char *)(uintptr_t)pointer;
 if(type<1000 || type>=5096 || !name || name[0]!='N' || !isdigit((unsigned char)name[1]))return;
 for(const char *p=name+1;*p;p++)if(!isdigit((unsigned char)*p))return;
 if(strlen(name)>=32)abort();strcpy(names[type-1000],name);
 fprintf(stderr,"GRAPH_NAME %lld %s\n",(long long)type,name);
}
int64_t GraphMate(int64_t type){return type>=1000 && type<5096 && names[type-1000][0];}
void GraphBegin(int64_t type,int64_t mode){if(depth>=1024)abort();stack[depth].type=type;stack[depth].mode=mode;stack[depth].calls=0;depth++;}
void GraphVisit(void){if(depth && stack[depth-1].mode<2)stack[depth-1].calls++;}
void GraphValidateVisit(void){if(depth && stack[depth-1].mode==2)stack[depth-1].calls++;}
void GraphEnd(int64_t type,int64_t mode,int64_t result){
 if(!depth)abort();depth--;if(stack[depth].type!=type || stack[depth].mode!=mode)abort();
 fprintf(stderr,"GRAPH_PROP %lld %lld %lld %lld\n",(long long)type,(long long)mode,(long long)result,(long long)stack[depth].calls);
}
'''
with tempfile.TemporaryDirectory(prefix='cool borrowed graph ') as temporary:
    tmp=Path(temporary);wrapper=tmp/'bootstrap'
    wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');wrapper.chmod(0o755)
    fronts=[ROOT/'build/cool-compiler',wrapper]
    if args.frontend:fronts.append(args.frontend.resolve())
    # Export adapters in a private source copy identify internal IR symbols.
    # Semantic parsing and code emission are still performed by Cool itself.
    copied=tmp/'types.cool';text=(ROOT/'compiler/03-types.cool').read_text()
    for name in ('FindType','BorrowTypeProperty','BorrowTypeWalk','ValidateBorrowedElements','ValidateBorrowedGraph'):
        text,count=re.subn(r'\bfn '+name+r'\(', 'export "C" fn '+name+'(',text);assert count==1,name
    copied.write_text(text)
    manifest=tmp/'compiler.sources';manifest.write_text(''.join('__main\t'+str(copied if file.name=='03-types.cool' else file)+'\n' for file in sorted((ROOT/'compiler').glob('*.cool'))))
    irfile=tmp/'compiler.ll';result=run([fronts[0],'llvm-bundle',manifest,irfile]);assert result.returncode==0,result
    ir=irfile.read_text();symbols={}
    for name in ('FindType','BorrowTypeProperty','BorrowTypeWalk','ValidateBorrowedElements','ValidateBorrowedGraph'):
        body=re.search(r'^define [^\n]*@'+name+r'\([^\n]*\) \{.*?^\}',ir,re.M|re.S);assert body,name
        calls=re.findall(r'call i64 @(__cool_fn\d+)\(',body.group());assert len(calls)==1,(name,calls)
        symbols[name]=calls[0]
    for name,symbol in symbols.items():
        ir,count=re.subn(r'^define i64 @'+symbol+r'\(', 'define i64 @GraphOriginal'+name+'(',ir,flags=re.M);assert count==1,name
    ir+='\ndeclare void @GraphValidateVisit()\ndeclare void @GraphName(i64,i64)\ndeclare i64 @GraphMate(i64)\ndeclare void @GraphBegin(i64,i64)\ndeclare void @GraphVisit()\ndeclare void @GraphEnd(i64,i64,i64)\n'
    ir+=f'''define i64 @{symbols['FindType']}(i64 %a0,i64 %a1) {{
entry:
 %r = call i64 @GraphOriginalFindType(i64 %a0,i64 %a1)
 call void @GraphName(i64 %r,i64 %a1)
 ret i64 %r
}}
define i64 @{symbols['BorrowTypeWalk']}(i64 %a0,i64 %a1,i64 %a2) {{
entry:
 call void @GraphVisit()
 %r = call i64 @GraphOriginalBorrowTypeWalk(i64 %a0,i64 %a1,i64 %a2)
 ret i64 %r
}}
define i64 @{symbols['BorrowTypeProperty']}(i64 %a0,i64 %a1) {{
entry:
 call void @GraphBegin(i64 %a0,i64 %a1)
 %r = call i64 @GraphOriginalBorrowTypeProperty(i64 %a0,i64 %a1)
 call void @GraphEnd(i64 %a0,i64 %a1,i64 %r)
 %mate = call i64 @GraphMate(i64 %a0)
 %yes = icmp ne i64 %mate,0
 br i1 %yes,label %other,label %done
other:
 %mode = xor i64 %a1,1
 call void @GraphBegin(i64 %a0,i64 %mode)
 %s = call i64 @GraphOriginalBorrowTypeProperty(i64 %a0,i64 %mode)
 call void @GraphEnd(i64 %a0,i64 %mode,i64 %s)
 br label %done
done:
 ret i64 %r
}}
'''
    ir+=f'''define i64 @{symbols['ValidateBorrowedElements']}(i64 %a0) {{
entry:
 call void @GraphBegin(i64 %a0,i64 2)
 %r = call i64 @GraphOriginalValidateBorrowedElements(i64 %a0)
 call void @GraphEnd(i64 %a0,i64 2,i64 0)
 ret i64 %r
}}
define i64 @{symbols['ValidateBorrowedGraph']}(i64 %a0,i64 %a1) {{
entry:
 call void @GraphValidateVisit()
 %r = call i64 @GraphOriginalValidateBorrowedGraph(i64 %a0,i64 %a1)
 ret i64 %r
}}
'''
    irfile.write_text(ir);shim=tmp/'trace.c';shim.write_text(SHIM);traced=tmp/'traced-compiler'
    result=run(['clang','-Wno-override-module','-O2',irfile,shim,ROOT/'build/compiler-host.o',ROOT/'build/language-runtime.o','-lffi','-o',traced]);assert result.returncode==0,result
    file=tmp/'main.cool';queries=0;graphs=0
    for label,nodes in cases():
        program=source(nodes)
        if not reachable(nodes,len(nodes)-1,False):program=program.replace('fn main(){}',f'fn main(){{let p=new[N{len(nodes)-1}]();}}')
        file.write_text(program)
        for front in fronts:
            result=run([front,'check',file]);assert (result.returncode,result.stdout,result.stderr)==(0,'',''),(label,front,result)
        result=run([traced,'check',file]);assert result.returncode==0 and result.stdout=='',(label,result)
        mapping={int(type):int(name[1:]) for type,name in re.findall(r'^GRAPH_NAME (\d+) (N\d+)$',result.stderr,re.M)}
        assert set(mapping.values())==set(range(len(nodes))),(label,mapping)
        rows=[tuple(map(int,row)) for row in re.findall(r'^GRAPH_PROP (\d+) ([012]) ([01]) (\d+)$',result.stderr,re.M)]
        assert all(line.startswith(('GRAPH_NAME ','GRAPH_PROP ')) for line in result.stderr.splitlines()),result
        seen=set();bound=1+3*sum(len(node['edges']) for node in nodes)+3*len(nodes)
        for type,mode,value,calls in rows:
            if type not in mapping:continue
            index=mapping[type]
            assert calls<=bound,(label,index,mode,calls,bound)
            if mode==2:continue
            assert value==reachable(nodes,index,bool(mode)),(label,index,mode,value,nodes)
            seen.add((index,mode))
        if label.startswith('diamond'):assert any(mode==2 and type in mapping and mapping[type]==len(nodes)-1 for type,mode,_,_ in rows),(label,rows)
        assert seen=={(i,mode) for i in range(len(nodes)) for mode in (0,1)},(label,seen)
        queries+=len(seen);graphs+=1
    # A late invalid storage branch cannot be skipped after a shared safe DAG.
    file.write_text('struct A{v:i64;}struct B{a:own[A];b:own[A];}struct Bad{a:own[B];b:own[B];r:own[& &i64];}fn main(){let p=new[Bad]();}')
    for front in fronts:
        result=run([front,'check',file]);assert result.returncode==2 and 'nested borrowed references' in result.stderr,(front,result)
    # Lazy concrete layouts and rollback reuse must not see stale visited bits.
    for front in fronts:
        for element,borrowed in (('i64',False),('&i64',True),('&mut i64',True),('[]i64',True)):
            file.write_text('struct G[T]{value:T;}fn pass(p:own[G['+element+']])->own[G['+element+']]{return move p;}fn main(){}')
            result=run([front,'check',file]);assert result.returncode==(2 if borrowed else 0),(front,element,result)
            if borrowed:assert 'borrows(parameter) contract' in result.stderr,result
        result=run([front,'repl-quiet'],input='struct N{next:own[N];value:i64;}\nlet p=new[N]();\nstruct Failed{r:&Missing;}\nstruct Good{r:&i64;}\nvar x=7;\nlet q=new[Good](Good{r:&x});\nx=2;\n*(*q).r\n:forget q\nx=2;\nx\n:quit\n')
        assert result.returncode==0 and result.stdout=='7\n2\n' and result.stderr.count('error:')==2,(front,result)
print(f'borrow graphs: {graphs} cyclic/diamond/seeded graphs, {queries} independently modeled borrowed/mode queries with bounded walks; depth-40 DAG, lazy generic layouts and REPL rollback on {len(fronts)} frontends PASS')
