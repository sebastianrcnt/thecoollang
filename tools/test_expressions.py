#!/usr/bin/env python3
"""Expression grammar and observable sequencing contract across execution engines."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--frontend', type=Path)
args = parser.parse_args()
# Explicit outcomes distinguish adjacent precedence levels and associativity.
CASES = [
    ('false || true && false', False), ('true || false && false', True),
    ('1 | 2 ^ 3', 1), ('7 ^ 3 & 1', 6), ('1 & 3 == 3', None),
    ('2 == 1 < 3', None), ('8 >> 1 + 1', 2), ('1 << 2 + 1', 8),
    ('2 + 3 * 4', 14), ('20 - 6 - 3', 11), ('64 / 4 / 2', 8),
    ('32 >> 2 >> 1', 4), ('10 % 4 * 3', 6), ('~1 & 7', 6),
    ('-2 * 3 + 10', 4), ('-(2 + 3) * 4', -20), ('!!true', True),
    ('true == false == false', True), ('3 < 4 == true', True),
    ('(1 | 2) ^ 3', 0), ('8 >> (1 + 1)', 2),
]
# Ill-typed expressions expose the equality/relational boundary without coercing bool.
REJECT = [expression for expression, value in CASES if value is None]
REJECT += ['1 < 2 < 3', '1 && 2', 'true + false', '+1', 'true ? 1 : 2', '1, 2',
           'true || missing()', 'false && missing()', '1++', '(1=2)']
VALID = [(expression, value) for expression, value in CASES if value is not None]
PRELUDE = '''import "std/io";
struct Pair { first:i64; second:i64; }
fn mark(value:i64)->i64 { io.println(value); return value; }
fn flag(value:i64,result:bool)->bool { io.println(value); return result; }
fn combine(a:i64,b:i64,c:i64)->i64 { return a*100+b*10+c; }
fn make_values()->[2]i64 { io.println(50); return [2]i64{50,51}; }
fn make_pair()->Pair { io.println(80); return Pair{first:1,second:2}; }
fn Pair.sum(self:Pair,value:i64)->i64 { return self.first+self.second+value; }
fn main(){
'''
TRACE = '''
assert(mark(1)+mark(2)*mark(3)==7);
assert(combine(mark(4),mark(5),mark(6))==456);
assert(!flag(10,false) && flag(11,true));
assert(flag(12,true) || flag(999,false));
assert(!(flag(13,false) && flag(999,true)));
assert(flag(14,false) || flag(15,true));
let pair=Pair{second:mark(20),first:mark(21)};
assert(pair.first==21 && pair.second==20);
var values=[3]i64{mark(30),mark(31),mark(32)};
values[mark(0)]=mark(40);assert(values[0]==40);
let slice=values[mark(1):mark(3)];assert(len(slice)==2);
assert(make_values()[mark(1)]==51);
assert(make_pair().sum(mark(81))==84);
}
'''
expected = ''.join(f'{n}\n' for n in [1,2,3,4,5,6,10,11,12,13,14,15,20,21,30,31,32,0,40,1,3,50,1,80,81])
program = PRELUDE + ''.join(f'assert(({expr})=={str(value).lower()});\n' for expr,value in VALID) + TRACE

def run(command, env):
    return subprocess.run([str(x) for x in command], cwd=ROOT, capture_output=True,
                          text=True, timeout=180, env=env)

def success(result, label):
    assert (result.returncode,result.stdout,result.stderr)==(0,expected,''),(label,result)

with tempfile.TemporaryDirectory(prefix='cool expressions ') as temporary:
    directory=Path(temporary); source=directory/'main.cool'; wrapper=directory/'bootstrap'
    wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n')
    wrapper.chmod(0o755)
    frontends=[ROOT/'build/cool-compiler',wrapper]
    if args.frontend: frontends.append(args.frontend.resolve())
    for frontend in frontends:
        env={**os.environ,'COOL_FRONTEND':str(frontend),'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
        source.write_text(program)
        for engine in ('tree','interp','jit','llvm','llvm-jit'):
            success(run([ROOT/'tools/cool','run','--backend',engine,source],env),(frontend,engine))
        binary=directory/'program'
        result=run([ROOT/'tools/cool','build','--release',source,'-o',binary],env)
        assert result.returncode==0,result
        success(run([binary],env),(frontend,'O2'))
        for expression in REJECT:
            source.write_text('fn main(){let value='+expression+';}')
            result=run([ROOT/'tools/cool','check',source],env)
            assert result.returncode==2,(frontend,expression,result)
print(f'expressions: {len(VALID)} precedence/associativity cases, 25 side-effect events and {len(REJECT)} rejections on {len(frontends)} frontends; five engines + O2 PASS')
