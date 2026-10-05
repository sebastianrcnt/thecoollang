#!/usr/bin/env python3
"""Private nested-root experiments; known counterexamples are not release acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def function_span(text, name):
    """Locate exactly one ordinary Cool function, counting lexical braces."""
    needle = 'fn ' + name + '('
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend', type=Path, default=ROOT / 'build/cool-compiler')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--graph-returns', action='store_true', help='Privately replace scalar reference return Region check with actual loan root validation')
    parser.add_argument('--routing', action='store_true', help='Apply experimental private typed copy/address layer routing')
    parser.add_argument('--assert-expectations', action='store_true', help='Assert all expanded expected classifications after writing report')
    args = parser.parse_args()
    assert len({name for name, _, _ in CASES}) == len(CASES), 'duplicate fixture names'
    sources = sorted((ROOT / 'compiler').glob('*.cool'))
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in sources}
    artifacts = [args.frontend.resolve(), ROOT / 'build/compiler-host.o', ROOT / 'build/language-runtime.o']
    artifact_hashes = {str(p): digest(p) for p in artifacts}
    env = {**os.environ, 'ASAN_OPTIONS': 'halt_on_error=1', 'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'}
    def run(cmd, **kw):
        return subprocess.run(list(map(str, cmd)), cwd=ROOT, env=env,
                              capture_output=True, text=True, timeout=240, **kw)
    with tempfile.TemporaryDirectory(prefix='cool nested reference probe ') as directory:
        tmp = Path(directory)
        private = tmp / 'compiler'; private.mkdir()
        for original in sources: shutil.copy2(original, private / original.name)
        copies = []
        for original in artifacts:
            copy = tmp / original.name; shutil.copy2(original, copy); copies.append(copy)
        assert hashes == {str(p.relative_to(ROOT)): digest(p) for p in sources}, 'source changed during snapshot'
        assert all(digest(copy) == artifact_hashes[str(original)] for original, copy in zip(artifacts, copies)), 'artifact changed during snapshot'
        target = private / '16-references.cool'
        original = target.read_text(); start, end = function_span(original, 'ReferenceStorage')
        patched = original[:start] + 'fn ReferenceStorage(type: i64) -> bool { return true; }' + original[end:]
        if args.routing:
            old = 'let preserve = nested && NestedReference(via.type) && !physical && !bridge;'
            assert patched.count(old) == 1
            patched = patched.replace(old, 'if (!IsReference(via.type) && !bridge) { layer = ReferenceCopiedPayloadLayer(place, via, expression, layer); }\n        let preserve = nested && TrackedBorrow(via.type) && !physical && !bridge;')
            patched += """
fn ReferenceCopiedPayloadLayer(place:*Node,via:*Local,expression:*Node,fallback:i64)->i64{unsafe{
 var cursor=ReferencePlaceCursor(place,via,null);var layer=fallback;var seen=false;
 let copying=expression.kind==3 || expression.kind==18 || expression.kind==29;
 let address=expression.kind==23 && expression.op==0;
 if(cursor.complete!=0){var step=cursor.path;while(step!=null){
  if(step.kind==3){
   if(address && seen){layer=1;}
   if(NestedReference(step.type)){seen=true;if(copying){layer=1;}}
  }step=step.next;
 }}
 ReferenceCursorFree(cursor.path);return layer;
}}
"""
        if args.graph_returns:
            borrow = private / '04-borrow.cool'
            text = borrow.read_text()
            old = 'if(node.kind==9 && Borrowed(function.result)!=i8(0) && (Region(node.a)&~function.borrow_contract)!=0)'
            assert text.count(old) == 1
            borrow.write_text(text.replace(old, 'if(node.kind==9 && !IsReference(function.result) && Borrowed(function.result)!=i8(0) && (Region(node.a)&~function.borrow_contract)!=0)'))
            start, end = function_span(patched, 'ReferenceStatement')
            statement = patched[start:end]
            old = '        if (node.kind != 15) {'
            assert statement.count(old) == 1
            statement = statement.replace(old, '        if (node.kind == 9 && IsReference(check.function.result)) { ReferenceReturnRoots(check, node.a, saved); }\n' + old)
            patched = patched[:start] + statement + patched[end:]
            patched += """
fn ReferenceReturnRoots(check:*ReferenceCheck,value:*Node,stop:*ReferenceLoan){unsafe{
 var loan=check.loans;var found=false;
 while(loan!=stop){if(loan.expression==value && loan.holder==null && loan.root!=null){
  let root=loan.root;found=true;
  if(root.depth!=0 || root.place_region==0 || (root.type!=0 && !IsReference(root.type)) || (root.place_region & ~check.function.borrow_contract)!=0){ErrorAt(value.token,cast[*u8]("returned borrow may outlive local storage or violate its borrows contract"));}
 }loan=loan.next;}
 if(!found){ErrorAt(value.token,cast[*u8]("returned borrow may outlive local storage or violate its borrows contract"));}
}}
"""
        target.write_text(patched)
        manifest = tmp / 'sources'
        manifest.write_text(''.join('__main\t' + str(p) + '\n' for p in sorted(private.glob('*.cool'))))
        ir = tmp / 'compiler.ll'
        result = run([copies[0], 'llvm-bundle', manifest, ir]); assert result.returncode == 0, result
        frontend = tmp / 'probe-frontend'
        result = run(['clang', '-Wno-override-module', '-O2', ir, *copies[1:], '-lffi', '-o', frontend])
        assert result.returncode == 0, result
        # Keep the real frontend's slot-lifetime rejection as an independent
        # control. Accepted negative experiments are checked only, never run.
        control_source = next(source for name, expected, source in CASES
                              if name == 'reference_parameter_slot_return')
        control = tmp / 'production-slot-control.cool'; control.write_text(control_source)
        controlled = run([copies[0], 'check', control])
        assert controlled.returncode == 2 and 'returned borrow may outlive local storage' in controlled.stderr, controlled
        production_control = dict(source=control_source, check_exit=controlled.returncode,
                                  check_stdout=controlled.stdout, check_stderr=controlled.stderr)
        observations = []
        for name, expected, source in CASES:
            fixture = tmp / (name + '.cool'); fixture.write_text(source)
            checked = run([frontend, 'check', fixture])
            assert checked.returncode in (0, 2), checked
            observed = 'accept' if checked.returncode == 0 else 'reject'
            row = dict(name=name, expected=expected, observed=observed,
                       matches_expectation=observed == expected, source=source,
                       source_sha256=digest(fixture), check_exit=checked.returncode,
                       check_stdout=checked.stdout, check_stderr=checked.stderr)
            if expected == 'reject':
                diagnostic = ('assigned borrow may outlive local storage' if name == 'short_inner_escape'
                              else 'returned borrow may outlive local storage' if name in ('local_inner_scalar_address_return', 'byvalue_parameter_slot_return', 'byvalue_owner_payload_return', 'stores_uncontracted_source_return', 'reference_parameter_slot_return')
                              else 'cannot mutate or move through a shared reference')
                row['expected_diagnostic'] = diagnostic
                if name == 'temporary_owner_slot_return':
                    diagnostic = 'reference requires a tracked local or parameter root'
                    row['expected_diagnostic'] = diagnostic
                row['matches_diagnostic'] = diagnostic in checked.stderr
            if observed == 'accept' and expected == 'accept':
                executed = run([frontend, 'run', fixture])
                row.update(run_exit=executed.returncode, run_stdout=executed.stdout, run_stderr=executed.stderr)
                row['valid_output'] = (executed.returncode, executed.stdout, executed.stderr) == (0, '', '')
                assert row['valid_output'], row
            observations.append(row)
            print(name + ': expected ' + expected + ', observed ' + observed)
        report = dict(production_slot_control=production_control,
                      gaps=[dict(name=r['name'], kind='unsafe_acceptance' if r['observed']=='accept' else 'over_rejection') for r in observations if not r['matches_expectation']],
                      graph_returns=args.graph_returns, routing=args.routing, source_sha256=hashes, artifact_sha256=artifact_hashes,
                      private_references_sha256=digest(target), private_borrow_sha256=digest(private / '04-borrow.cool'), private_ir_sha256=digest(ir),
                      observations=observations,
                      method='Private source copy: only ReferenceStorage function replaced with true using lexical balanced brace scan. Existing frontend emitted LLVM; private executable linked existing host/runtime object copies. Optional routing changes only private Acquire preserve and copy payload-layer selection. Optional graph-returns replaces coarse Region for reference outputs only with actual temporary loan root validation. Other guards unchanged. Accepted negative or rejected positive cases are experimental gaps; this is not nested-storage safety or release acceptance.')
        if args.output: args.output.write_text(json.dumps(report, indent=2) + '\n')
        if args.assert_expectations:
            assert all(r['matches_expectation'] and r.get('matches_diagnostic', True) for r in observations), observations
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
