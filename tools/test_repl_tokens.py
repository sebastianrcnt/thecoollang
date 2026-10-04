#!/usr/bin/env python3
"""REPL token reuse preserves literals, retained source and error recovery."""
from pathlib import Path
import argparse
import subprocess

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--frontend', type=Path)
args = parser.parse_args()
fronts = [[ROOT / 'build/cool-compiler'], [ROOT / 'build/coolc', '--run', ROOT / 'build/language.BIN']]
if args.frontend:
    fronts.append([args.frontend.resolve()])


def check(front, label, source, output, errors=()):
    result = subprocess.run([*front, 'repl-quiet'], input=source + '\n:quit\n',
                            text=True, capture_output=True, timeout=120)
    assert result.returncode == 0 and result.stdout == output, (label, front, result)
    assert result.stderr.count('error:') == len(errors), (label, result.stderr)
    for error in set(errors):
        assert result.stderr.count(error) == errors.count(error), (label, result.stderr)


for front in fronts:
    # Retained source is proportional to live declarations, not their history.
    source = 'fn answer()->i64{return 0;}\nfn caller()->i64{return answer();}\n'
    source += 'caller()\n'*4
    source += ''.join(f'fn answer()->i64{{return {i};}}\n' for i in range(1, 40001))
    source += 'caller()\nfn answer()->i64{return missing;}\ncaller()'
    check(front, '40000 replacements exceed the old lifetime token limit', source,
          '0\n'*4+'40000\n40000\n', ['unknown variable'])

    # A hole before types/templates moves both lazy source and warm AST tokens.
    source = ('fn discarded()->string{return "retained string";}\n'
              'let kept=discarded();\n'
              'struct Box[T]{value:T;}\n'
              'fn get[T](value:Box[T])->T{return value.value;}\n'
              'fn Box.read[T](self:Box[T])->T{return self.value;}\n'
              'fn checked(n:i64)->i64{assert(n>0);return n;}\n'
              'checked(1)\n')
    source += 'checked(1)\n'*3
    source += 'fn discarded()->string{return "new";}\n'*128
    source += ('get[u8](Box[u8]{value:42})\n'
               'let box=Box[i64]{value:7};\nbox.read()\n'
               'checked(0)\nchecked(9)\nkept\ndiscarded()')
    check(front, 'compacted generic/type source, JIT diagnostics and escaped strings', source,
          '1\n'*4+'42\n7\n9\nretained string\nnew\n', ['assertion failed'])

    check(front, 'mixed batch remains live until its last function is replaced',
          'fn first()->i64{return 1;} fn second()->i64{return 2;}\n'
          'fn first()->i64{return 3;}\nsecond()\n'
          'fn second()->i64{return 4;}\nfirst()\nsecond()\n'
          'fn third()->i64{return first()+second();}\nthird()',
          '2\n3\n4\n7\n')
    check(front, 'relocated foreign declaration and cached safe wrapper',
          'fn before()->i64{return 0;}\nextern "C" fn abs(n:i32)->i32;\n'
          'fn wrapper()->i32{unsafe{return abs(-9);}}\n'
          + 'wrapper()\n'*4 + 'fn before()->i64{return 1;}\nwrapper()',
          '9\n'*5)

    prefix = '''import "std/mem";
fn identity[T](value:T)->T{return value;}
fn answer()->i64{return 41;}
var total=0;
let message="문자열 survives";
var kept=new[string]("owned literal");
'''
    # More than twice the former lifetime token-table capacity. Function and
    # generic source precedes the recycled input span and must remain usable.
    source = prefix + 'total=total+1;\n' * 100000
    source += 'total\nidentity[i64](answer())\nmessage\n*kept\nmem.owner_count()\n:forget kept\nmem.owner_count()'
    check(front, '100000 submissions with retained source and strings', source,
          '100000\n41\n문자열 survives\nowned literal\n1\n0\n')

    # Identifier spelling, float conversion buffers, string construction and
    # synthetic trailing semicolons all have distinct cleanup ownership.
    source = 'let stable="repeat";\nvar n=0;\n'
    source += '{let temporary="repeat";let real=1.25e2;assert(real==125.0);n=n+1;}\n' * 5000
    source += 'n\nstable\n"repeat"\n""\n"escaped\\nline"'
    check(front, 'repeated literals, floats and implicit semicolons', source,
          '5000\nrepeat\nrepeat\n\nescaped\nline\n')

    source = 'let stable="still alive";\nvar n=0;\n'
    source += ('let rejected="bad\\q";\nlet rejected=1e9999;\n/* unfinished\nn=n+1;\n') * 160
    source += 'n\nstable\nlet recovered=42;\nrecovered'
    check(front, 'partial lexing cleanup and recovery', source, '160\nstill alive\n42\n',
          ['unsupported string escape', 'floating literal out of range', 'unterminated comment'] * 160)

    # One genuinely oversized submission still has a limit, but its error is
    # recoverable and must not destroy earlier declarations, values or literals.
    source = prefix + '{' + 'total=total+1;' * 50000 + '}\n'
    source += 'total\nidentity[i64](answer())\n*kept\nmessage'
    check(front, 'single oversized submission', source,
          '0\n41\nowned literal\n문자열 survives\n', ['token limit exceeded'])

    # A rejected declaration is not a reason to retain its input span. The
    # original signature/body remain valid after token reclamation.
    source = 'fn answer()->i64{return 7;}\n'
    source += 'fn answer()->i64{return missing;}\n' * 160
    source += 'answer()\nfn answer()->i64{return 9;}\nanswer()'
    check(front, 'failed declaration token rollback', source, '7\n9\n', ['unknown variable'] * 160)

print('REPL tokens: 100000 inputs, literals/owners, cached generic source, partial lexing, declaration rollback and recoverable limits on all frontends PASS')
