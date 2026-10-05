#!/usr/bin/env python3
"""Private nested-root experiments; known counterexamples are not release acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def function_span(text, name, prefix='fn '):
    """Locate exactly one ordinary Cool function, counting lexical braces."""
    needle = prefix + name + '('
    assert text.count(needle) == 1, name
    start = text.index(needle)
    opening = text.index('{', start)
    depth, i, state = 0, opening, 'code'
    while i < len(text):
        c = text[i]
        pair = text[i:i + 2]
        if state == 'line':
            if c == '\n': state = 'code'
        elif state == 'block':
            if pair == '*/': state = 'code'; i += 1
        elif state == 'string':
            if c == '\\': i += 1
            elif c == '"': state = 'code'
        elif pair == '//': state = 'line'; i += 1
        elif pair == '/*': state = 'block'; i += 1
        elif c == '"': state = 'string'
        elif c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: return start, i + 1
        i += 1
    raise AssertionError('unterminated function ' + name)


CASES = [
    ('outer_read', 'accept', '''struct Inner{r:&i64;}struct Outer{inner:&Inner;}
fn main(){var a=7;let inner=Inner{r:&a};let outer=Outer{inner:&inner};assert(*(*outer.inner).r==7);}
'''),
    ('external_return', 'accept', '''struct Inner{r:&i64;}struct Outer{inner:&Inner;}
fn get(o:Outer)->&i64 borrows(o){return (*o.inner).r;}
fn main(){var a=7;let inner=Inner{r:&a};let outer=Outer{inner:&inner};let q=get(outer);assert(*q==7);}
'''),
    ('local_inner_external_return', 'accept', '''struct Inner{r:&i64;}struct Outer{inner:&Inner;}
fn get(x:&i64)->&i64 borrows(x){let inner=Inner{r:x};let outer=Outer{inner:&inner};return (*outer.inner).r;}
fn main(){var a=7;let q=get(&a);assert(*q==7);}
'''),
    ('local_inner_address_return', 'accept', '''struct Inner{r:&i64;}struct Outer{inner:&Inner;}
fn get(x:&i64)->&i64 borrows(x){let inner=Inner{r:x};let outer=Outer{inner:&inner};return &*(*outer.inner).r;}
fn main(){var a=7;let q=get(&a);assert(*q==7);}
'''),
    ('local_inner_scalar_address_return', 'reject', '''struct Inner{r:&i64;v:i64;}struct Outer{inner:&Inner;}
fn get(x:&i64)->&i64 borrows(x){let inner=Inner{r:x,v:7};let outer=Outer{inner:&inner};return &(*outer.inner).v;}
fn main(){var a=7;let q=get(&a);assert(*q==7);}
'''),
    ('reference_parameter_slot_return', 'reject', '''fn bad(p:&i64)->& &i64 borrows(p){return &p;}
fn main(){var a=7;let q=bad(&a);assert(**q==7);}
'''),
    ('byvalue_parameter_slot_return', 'reject', '''struct Pair{r:&i64;}
fn bad(p:Pair)->& &i64 borrows(p){return &p.r;}
fn main(){var a=7;let q=bad(Pair{r:&a});assert(**q==7);}
'''),
    ('byvalue_owner_payload_return', 'reject', '''struct Wrapper{r:&i64;value:i64;}
fn bad(p:own[Wrapper])->&i64 borrows(p){return &(*p).value;}
fn main(){var a=7;let q=bad(new[Wrapper](Wrapper{r:&a,value:7}));assert(*q==7);}
'''),
    ('temporary_owner_slot_return', 'reject', '''struct Inner{r:&i64;v:i64;}
fn get(x:&i64)->&i64 borrows(x){return &(*new[Inner](Inner{r:x,v:9})).v;}
fn main(){var a=7;let q=get(&a);assert(*q==9);}
'''),
    ('stores_uncontracted_source_return', 'reject', '''struct Pair{r:&i64;}
fn get(dst:&mut Pair,src:&i64)->&i64 borrows(dst) stores(dst,src){(*dst).r=src;return (*dst).r;}
fn main(){var a=7;var b=9;var pair=Pair{r:&a};let q=get(&mut pair,&b);assert(*q==9);}
'''),
    ('short_inner_escape', 'reject', '''struct Inner{r:&i64;}struct Outer{inner:&Inner;}
fn main(){var a=7;let kept=Inner{r:&a};var outer=Outer{inner:&kept};{let short=Inner{r:&a};outer.inner=&short;}assert(*(*outer.inner).r==7);}
'''),
    ('shared_outer_mutable_inner', 'reject', '''struct Inner{r:&mut i64;}struct Outer{inner:&Inner;}
fn main(){var a=7;var inner=Inner{r:&mut a};let outer=Outer{inner:&inner};let q=(*outer.inner).r;*q=9;}
'''),
]


DEEP_CASES=[]
# Distinct physical descriptors at every level, with the final scalar caller
# root shared by copy/address returns. Rejection variants address a frame field
# at each depth, not only the outermost descriptor.
for depth in (2, 3, 4):
    declarations = 'struct L0{r:&i64;v:i64;}' + ''.join(
        f'struct L{i}{{next:&L{i-1};v:i64;}}' for i in range(1, depth))
    setup = 'let l0=L0{r:x,v:7};' + ''.join(
        f'let l{i}=L{i}{{next:&l{i-1},v:7}};' for i in range(1, depth))
    access = f'l{depth-1}'
    expressions = [(depth-1, access)]
    for level in reversed(range(depth-1)):
        access = f'(*{access}.next)'
        expressions.append((level, access))
    for form, value in (('copy', access+'.r'), ('address', '&*'+access+'.r')):
        source = declarations + f'fn get(x:&i64)->&i64 borrows(x){{{setup}return {value};}}' + 'fn main(){var a=7;let q=get(&a);assert(*q==7);}'
        DEEP_CASES.append((f'depth{depth}_{form}_external_return', 'accept', source))
    for level, projected in expressions:
        source = declarations + f'fn bad(x:&i64)->&i64 borrows(x){{{setup}return &{projected}.v;}}' + 'fn main(){}'
        DEEP_CASES.append((f'depth{depth}_level{level}_frame_return', 'reject', source))


STORE_CASES=[]
STORE_DIAGNOSTICS={}
for depth in (2, 3):
    declarations='struct L0{r:&i64;}' + ''.join(f'struct L{i}{{next:&mut L{i-1};}}' for i in range(1,depth))
    setup='var l0=L0{r:&a};' + ''.join(f'var l{i}=L{i}{{next:&mut l{i-1}}};' for i in range(1,depth))
    access='(*p)'
    for level in reversed(range(depth-1)):access=f'(*{access}.next)'
    prefix=declarations+'fn main(){var a=7;var b=9;'+setup+f'let p=&mut l{depth-1};'
    STORE_CASES.append((f'store_depth{depth}_replace', 'accept', prefix+f'{access}.r=&b;assert(*{access}.r==9);}}'))
    name=f'store_depth{depth}_short_source'
    STORE_CASES.append((name,'reject',prefix+f'{{var short=11;{access}.r=&short;}}assert(*{access}.r==11);}}'))
    STORE_DIAGNOSTICS[name]='outlive'
    name=f'store_depth{depth}_retained_source'
    STORE_CASES.append((name,'reject',prefix+f'{access}.r=&b;b=11;}}'))
    STORE_DIAGNOSTICS[name]='conflicts'
    function=declarations+f'fn set(p:&mut L{depth-1},src:&i64) stores(p,src){{{access}.r=src;assert(*{access}.r==*src);}}'
    STORE_CASES.append((f'store_depth{depth}_contract','accept',function+'fn main(){var a=7;var b=9;'+setup+f'set(&mut l{depth-1},&b);}}'))
    name=f'store_depth{depth}_missing_contract'
    STORE_CASES.append((name,'reject',function.replace(' stores(p,src)','')+'fn main(){}'))
    STORE_DIAGNOSTICS[name]='matching stores'

# Retarget an inner descriptor to another parameter, then write through it.
# A destination contract for the old outer parameter cannot authorize effects
# on the other parameter's caller storage.
retarget='struct L0{r:&i64;}struct L1{next:&mut L0;}fn bad(p:&mut L1,other:&mut L0,src:&i64) stores(p,other) stores(p,src){(*p).next=other;(*(*p).next).r=src;}fn main(){}'
STORE_CASES.append(('store_retarget_missing_destination_contract','reject',retarget))
STORE_DIAGNOSTICS['store_retarget_missing_destination_contract']='matching stores'
complete_retarget=retarget.replace(' stores(p,src){',' stores(p,src) stores(other,src){').replace('fn main(){}','fn main(){var a=7;var b=9;var c=11;var first=L0{r:&a};var second=L0{r:&b};var outer=L1{next:&mut first};bad(&mut outer,&mut second,&c);assert(*(*outer.next).r==11);}')
STORE_CASES.append(('store_retarget_complete_destination_contract','accept',complete_retarget))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend', type=Path, default=ROOT / 'build/cool-compiler')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--legacy', action='store_true')
    parser.add_argument('--unsafe-root-predicate', action='store_true', help='Private countermodel replacing explicit external-root identity with the disproven type predicate')
    parser.add_argument('--assert-expectations', action='store_true')
    parser.add_argument('--stores', action='store_true', help='Include nested receiver replacement and contract lifetime cases')
    parser.add_argument('--all-engines', action='store_true', help='Run accepted positives on tree/VM/JIT/LLVM/LLVM-JIT and release AOT')
    parser.add_argument('--deep', action='store_true', help='Include depth-2/3/4 lifetime cases; currently exposes unsupported deeper acquisition')
    args = parser.parse_args()
    if args.deep: CASES.extend(DEEP_CASES)
    if args.stores: CASES.extend(STORE_CASES)
    assert len({name for name, _, _ in CASES}) == len(CASES)
    sources = sorted((ROOT/'compiler').glob('*.cool'))
    legacy_sources = sorted((ROOT/'language').glob('*.cool')) if args.legacy else []
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in sources+legacy_sources}
    artifacts = [args.frontend.resolve(), ROOT/'build/compiler-host.o', ROOT/'build/language-runtime.o']
    artifact_hashes = {str(p): digest(p) for p in artifacts}
    env = {**os.environ, 'COOLC_COMPILER_BIN':str(ROOT/'coolc/seed/Compiler.BIN')}
    def run(cmd, **kw):
        return subprocess.run(list(map(str,cmd)),cwd=ROOT,env=env,capture_output=True,text=True,timeout=240,**kw)
    with tempfile.TemporaryDirectory(prefix='cool nested reference probe ') as directory:
        tmp=Path(directory);private=tmp/'compiler';private.mkdir()
        for original in sources:shutil.copy2(original,private/original.name)
        copies=[]
        for original in artifacts:
            copy=tmp/original.name;shutil.copy2(original,copy);copies.append(copy)
        assert all(digest(copy)==artifact_hashes[str(original)] for original,copy in zip(artifacts,copies))
        target=private/'16-references.cool';text=target.read_text()
        start,end=function_span(text,'ReferenceStorage')
        text=text[:start]+'fn ReferenceStorage(type:i64)->bool{return true;}'+text[end:]
        if args.unsafe_root_predicate:
            assert text.count('root.reference_external == 0')==1
            text=text.replace('root.reference_external == 0','(root.type != 0 && !IsReference(root.type))')
        target.write_text(text)
        manifest=tmp/'sources';manifest.write_text(''.join('__main\t'+str(p)+'\n' for p in sorted(private.glob('*.cool'))))
        ir=tmp/'compiler.ll';r=run([copies[0],'llvm-bundle',manifest,ir]);assert r.returncode==0,r
        frontend=tmp/'probe-frontend';r=run(['clang','-Wno-override-module','-O2',ir,*copies[1:],'-lffi','-o',frontend]);assert r.returncode==0,r
        fronts=[('production',[frontend])]
        if args.legacy:
            seed=tmp/'language';seed.mkdir()
            for original in legacy_sources:shutil.copy2(original,seed/original.name)
            refs=seed/'References.cool';text=refs.read_text();start,end=function_span(text,'ReferenceStorage','Bool ')
            text=text[:start]+'Bool ReferenceStorage(I64 type){return TRUE;}'+text[end:]
            if args.unsafe_root_predicate:
                assert text.count('!root->reference_external')==1
                text=text.replace('!root->reference_external','(root->type && !IsReference(root->type))')
            refs.write_text(text);binary=tmp/'frontend.BIN';r=run([ROOT/'build/coolc',seed/'Native.cool',binary]);assert r.returncode==0,r
            fronts.append(('seed',[ROOT/'build/coolc','--run',binary]))
        control_source=next(source for name,_,source in CASES if name=='reference_parameter_slot_return')
        control=tmp/'production-slot-control.cool';control.write_text(control_source)
        controlled=run([copies[0],'check',control])
        assert controlled.returncode==2 and 'returned borrow may outlive local storage' in controlled.stderr,controlled
        observations=[]
        for front_name,front in fronts:
            runner=tmp/(front_name+'-runner')
            runner.write_text('#!/bin/sh\nexec '+shlex.join(list(map(str,front)))+' "$@"\n');runner.chmod(0o755)
            engine_env={**env,'COOL_FRONTEND':str(runner)}
            for name,expected,source in CASES:
                fixture=tmp/(name+'.cool');fixture.write_text(source);r=run([*front,'check',fixture]);assert r.returncode in (0,2),r
                observed='accept' if r.returncode==0 else 'reject'
                row=dict(frontend=front_name,name=name,expected=expected,observed=observed,matches_expectation=observed==expected,source=source,source_sha256=digest(fixture),check_exit=r.returncode,check_stdout=r.stdout,check_stderr=r.stderr)
                if expected=='reject':
                    diagnostic=('assigned borrow may outlive local storage' if name=='short_inner_escape' else 'cannot mutate or move through a shared reference' if name=='shared_outer_mutable_inner' else 'reference requires a tracked local or parameter root' if name=='temporary_owner_slot_return' else 'returned borrow may outlive local storage')
                    diagnostic=STORE_DIAGNOSTICS.get(name,diagnostic)
                    row.update(expected_diagnostic=diagnostic,matches_diagnostic=diagnostic in r.stderr)
                if observed=='accept' and expected=='accept':
                    r=run([*front,'run',fixture]);row.update(run_exit=r.returncode,run_stdout=r.stdout,run_stderr=r.stderr)
                    assert (r.returncode,r.stdout,r.stderr)==(0,'',''),row
                    if args.all_engines:
                        row['engine_runs']=[]
                        for engine in ('interp','jit','llvm','llvm-jit','O2'):
                            if engine=='O2':
                                program=tmp/(front_name+'-'+name+'-program')
                                command=[ROOT/'tools/cool','build','--release',fixture,'-o',program]
                            else:command=[ROOT/'tools/cool','run','--backend',engine,fixture]
                            result=subprocess.run(list(map(str,command)),cwd=ROOT,env=engine_env,capture_output=True,text=True,timeout=240)
                            assert (result.returncode,result.stdout,result.stderr)==(0,'',''),(front_name,name,engine,result)
                            if engine=='O2':result=run([program])
                            row['engine_runs'].append(dict(engine=engine,exit=result.returncode,stdout=result.stdout,stderr=result.stderr))
                            assert (result.returncode,result.stdout,result.stderr)==(0,'',''),(front_name,name,engine,result)
                # Accepted negative cases are intentionally never executed.
                observations.append(row);print(front_name,name,expected,observed)
        assert hashes=={str(p.relative_to(ROOT)):digest(p) for p in sources+legacy_sources},'source changed during audit'
        report=dict(source_sha256=hashes,artifact_sha256=artifact_hashes,private_ir_sha256=digest(ir),unsafe_root_predicate=args.unsafe_root_predicate,deep=args.deep,stores=args.stores,all_engines=args.all_engines,production_slot_control=dict(source=control_source,exit=controlled.returncode,stderr=controlled.stderr),observations=observations,gaps=[dict(frontend=r['frontend'],name=r['name'],kind='unsafe_acceptance' if r['observed']=='accept' else 'over_rejection') for r in observations if not r['matches_expectation']],method='Private copies of actual frontends; only ReferenceStorage bypassed normally. Optional countermodel replaces explicit external-root identity with the disproven reference-type predicate. Positive tree runs always, plus optional five-engine/O2 execution records; accepted negatives never execute. Public frontend separately rejects parameter-slot escape. This is nested-lifetime readiness coverage, not production feature acceptance or cross-engine safety proof.')
        if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
        if args.assert_expectations:
            failures=[dict(frontend=r['frontend'],name=r['name'],expected=r['expected'],observed=r['observed'],diagnostic_matches=r.get('matches_diagnostic',True)) for r in observations if not r['matches_expectation'] or not r.get('matches_diagnostic',True)]
            assert not failures,failures
    return 0


if __name__=='__main__':raise SystemExit(main())
