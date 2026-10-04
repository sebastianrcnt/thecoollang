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
