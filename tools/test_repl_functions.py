#!/usr/bin/env python3
"""Function replacement/rollback owns code, syntax and metadata independently."""
from pathlib import Path
import argparse
import subprocess
ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--frontend', type=Path)
args = parser.parse_args()
fronts = [[ROOT/'build/cool-compiler'], [ROOT/'build/coolc', '--run', ROOT/'build/language.BIN']]
if args.frontend:
    fronts.append([args.frontend.resolve()])


def check(front, label, source, output, errors=()):
    result = subprocess.run([*front, 'repl-quiet'], input=source+'\n:quit\n',
                            text=True, capture_output=True, timeout=120)
    assert result.returncode == 0 and result.stdout == output, (front, label, result)
    assert result.stderr.count('error:') == len(errors), (label, result.stderr)
    for error in set(errors):
        assert result.stderr.count(error) == errors.count(error), (label, result.stderr)


for front in fronts:
    check(front, 'repeated session statistics keep no formatting buffers', ':stats\n'*512,
          'functions=0 compiled=0 bytecode_compilations=0 jit_compilations=0\n'*512)
    check(front, 'branch snapshots have submission lifetime',
          'var total=0;\n' + 'if(total>=0){total=total+1;}else{total=0;}\n'*100000 + 'total',
          '100000\n')
    prefix = 'import "std/mem";\nenum Choice{Left;Right;}\nlet kept=new[i64](42);\n'
    failure = 'match(Choice.Left){Choice.Left=>{let moved=move kept;}}\n'
    check(front, 'rejected match scratch and moves roll back together',
          prefix + failure*512 + '*kept\nmem.owner_count()\n:forget kept\nmem.owner_count()',
          '42\n1\n0\n', ['non-exhaustive match']*512)

    methods = ('struct Counter{value:i64;}\n'
               'struct CounterExtra{value:i64;}\n'
               'fn C()->i64{return 0;}\n'
               'fn CounterExtra.read(self:CounterExtra)->i64{return 99;}\n'
               'fn Counter.reader(self:Counter)->i64{return 98;}\n'
               'fn Counter.read(self:Counter)->i64{return self.value;}\n'
               'var counter=Counter{value:1};\nvar sum=0;\n')
    check(front, '100000 method lookups retain no per-call names',
          methods + 'sum=sum+counter.read();\n'*100000 + 'sum', '100000\n')
    check(front, 'unknown names do not displace the exact method',
          methods + ''.join(f'counter.absent{i}();\n' for i in range(256)) + 'counter.read()',
          '1\n', ['unknown method']*256)
    check(front, 'cached method caller survives replacement and rejection',
          methods + 'fn call()->i64{return counter_missing;}\n'
          + 'fn call()->i64{let value=Counter{value:7};return value.read();}\n'
          + 'call()\n'*4 + 'fn Counter.read(self:Counter)->i64{return self.value+1;}\n'
          + 'call()\nfn Counter.read(self:Counter)->i64{return missing;}\ncall()',
          '7\n'*4+'8\n8\n', ['unknown variable']*2)

    source = 'import "std/mem";\nvar total=0;\nfn value()->i64{return 1;}\nfn caller()->i64{return value();}\n'
    source += '{total=caller();total=caller();total=caller();total=caller();}\n'
    expected = ''
    for value in range(2, 130):
        source += f'fn value()->i64{{var owned=new[i64]({value});return *owned;}}\n'
        source += '{total=caller();total=caller();total=caller();total=caller();}\ntotal\nmem.owner_count()\n'
        expected += f'{value}\n0\n'
    check(front, 'replacement releases callee code while retaining JIT callers', source, expected)

    failures = ('fn value()->i64{var owned=new[i64](7);return missing;}\n'
                'fn value()->i64{var oversized=[32769]i64{};return 0;}\n'
                'fn value(n:i64)->i64{return n;}\n') * 80
    source = 'fn value()->i64{return 7;}\nfn caller()->i64{return value();}\n'
    source += 'caller()\n' * 4 + failures + 'caller()\n'
    check(front, 'rejected definitions preserve old syntax, bytecode and JIT', source, '7\n'*5,
          ['unknown variable', 'function storage limit exceeded', 'signature change'] * 80)

    source = 'fn broken[T](value:T)->i64{var owned=new[i64](7);return missing;}\nvar survivor=9;\n'
    source += 'broken[i64](1)\n' * 160
    source += 'survivor\nfn fresh()->i64{return 42;}\nfresh()\n:stats'
    check(front, 'rejected specialization disposes its artifacts', source,
          '9\n42\nfunctions=2 compiled=1 bytecode_compilations=1 jit_compilations=0\n', ['unknown variable'] * 160)

    prefix = 'import "std/mem";\nvar total=0;\nfn bomb(n:i64)->i64{var owner=new[i64](n);assert(n<4);return *owner;}\n'
    failing = '{total=bomb(1);total=bomb(2);total=bomb(3);total=bomb(4);}\n'
    check(front, 'cold compilation and new JIT unwind', prefix + failing*160 + 'total\nmem.owner_count()\nbomb(2)\nmem.owner_count()',
          '3\n0\n2\n0\n', ['assertion failed']*160)
    check(front, 'new JIT rollback retains earlier bytecode',
          prefix + 'bomb(1)\n{total=bomb(2);total=bomb(3);total=bomb(4);}\nbomb(2)\nmem.owner_count()',
          '1\n2\n0\n', ['assertion failed'])
    check(front, 'runtime rollback retains earlier JIT',
          prefix + 'bomb(1)\n'*4 + 'bomb(4)\nbomb(2)\nmem.owner_count()',
          '1\n1\n1\n1\n2\n0\n', ['assertion failed'])

    check(front, 'escaped function literals outlive discarded AST and code',
          'fn word()->string{return "old";}\nword()\nword()\nword()\nlet kept=word();\nfn word()->string{return "new";}\nword()\nkept',
          'old\nold\nold\nnew\nold\n')
    check(front, 'whole declaration batch rolls back before old artifacts die',
          'fn first()->i64{return 1;}\nfirst()\nfirst()\nfirst()\nfirst()\nfn first()->i64{return 8;} fn broken()->i64{return missing;}\nfirst()\nfn fresh()->i64{return 3;}\nfresh()',
          '1\n1\n1\n1\n1\n3\n', ['unknown variable'])

    # Cached safe callers must not acquire a foreign call through replacement.
    source = 'fn abs(n:i32)->i32{return n;}\nfn safe()->i32{return abs(-9);}\n'
    source += 'safe()\n'*4 + 'extern "C" fn abs(n:i32)->i32;\nsafe()\n'
    source += 'export "C" fn abs(n:i32)->i32{return 0;}\nsafe()'
    check(front, 'replacement preserves C ABI mode', source, '-9\n'*6, ['C ABI change']*2)
    check(front, 'foreign declarations cannot become Cool bodies',
          'extern "C" fn abs(n:i32)->i32;\nfn abs(n:i32)->i32{return n;}\nunsafe{io.println(abs(-7));}',
          '7\n', ['C ABI change'])
print('REPL functions: repeated JIT replacement, failed bodies/specialization, staged cache rollback, owner cleanup and stable C ABI mode on all frontends PASS')
