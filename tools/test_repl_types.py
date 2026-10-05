#!/usr/bin/env python3
"""Lazy layouts and interned text participate in REPL rollback."""
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
    result = subprocess.run([*front, 'repl-quiet'], input=source+'\n:quit\n', text=True, capture_output=True, timeout=120)
    assert (result.returncode, result.stdout) == (0, output), (label, front, result)
    assert result.stderr.count('error:') == len(errors), (label, result.stderr)
    for error in set(errors):
        assert result.stderr.count(error) == errors.count(error), (label, result.stderr)

for front in fronts:
    check(front, 'dependent lazy layout retries preserve valid specializations',
          'struct Bad[T]{first:T;second:[2]T;}\nstruct Phantom[T]{}\n'
          'let phantom=Phantom[Bad[[65536]i64]]{};\n' + 'Bad[[65536]i64]{}\n'*128 +
          'let good=Bad[i64]{first:7,second:[2]i64{41,42}};\ngood.second[1]',
          '42\n', ['aggregate exceeds 512 KiB implementation limit']*128)
    check(front, 'invalid generic declaration does not reserve its name',
          'struct Retry[T]{first:T;second:Missing;}\n'*128 +
          'struct Missing{value:i64;}\nstruct Retry[T]{first:T;second:Missing;}\n'
          'let good=Retry[i64]{first:7,second:Missing{value:42}};\ngood.second.value',
          '42\n', ['unsupported or unknown type']*128)
    check(front, 'completed lazy layout rolls back with newly allocated type IDs',
          'struct Holder[T]{items:[2]T;}\nstruct Phantom[T]{}\n'
          'let phantom=Phantom[Holder[i64]]{};\n'
          'fn rejected(value:Holder[i64])->i64{return missing;}\n'
          'let unrelated=[3]i64{1,2,3};\n'
          'let good=Holder[i64]{items:[2]i64{7,8}};\ngood.items[1]\nunrelated[2]',
          '8\n3\n', ['unknown variable'])
    check(front, 'new nominal fields are discarded before descriptor reuse',
          'struct Rejected{first:i64;second:i64;bad:Missing;}\n'*512 +
          'struct Rejected{value:i64;}\nlet good=Rejected{value:42};\ngood.value',
          '42\n', ['unsupported or unknown type']*512)
    prefix = ('import "std/mem";\nstruct Holder[T]{value:own[T];}\nstruct Phantom[T]{}\n'
              'let phantom=Phantom[Holder[i64]]{};\n'
              'fn fail[T](value:Holder[T]){assert(false);}\n')
    check(front, 'runtime frames unwind before new layout fields are freed',
          prefix + 'fail[i64](Holder[i64]{value:new[i64](7)})\n'*128 +
          'let unrelated=[3]i64{};\nlet kept=Holder[i64]{value:new[i64](42)};\n'
          '*kept.value\nmem.owner_count()\n:forget kept\nmem.owner_count()',
          '42\n1\n0\n', ['assertion failed']*128)
    check(front, 'runtime failure keeps literals stored inside a surviving owner',
          'var kept=new[string]("old");\n'
          '{*kept="escaped in owner";assert(false); }\n'
          'fn rejected()->string{let value="cancelled";return missing;}\n'
          '*kept\n:forget kept', 'escaped in owner\n', ['assertion failed','unknown variable'])
    rejected = ''.join(f'fn rejected{i}()->string{{let text="unique {i}";return missing;}}\n' for i in range(2048))
    check(front, 'cancelled symbols and literals preserve committed and escaped text',
          'var kept="original";\nfn stable()->string{return "stable";}\n'
          '{kept="escaped before failure";assert(false);}\n'+rejected+
          'kept\nstable()\nfn rejected0()->string{return "reused";}\nrejected0()\nkept',
          'escaped before failure\nstable\nreused\nescaped before failure\n',
          ['assertion failed']+['unknown variable']*2048)
print('REPL type transactions: lazy-layout retry/repair, type ID reuse, field cleanup, runtime owner unwind and literal rollback on all frontends PASS')
