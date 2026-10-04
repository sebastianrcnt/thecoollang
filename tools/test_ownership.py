#!/usr/bin/env python3
"""Move-only resources: native destruction, rejection and recoverable REPL errors."""
from pathlib import Path
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[1]
def cool(*args, **kwargs):
    return subprocess.run([ROOT/'tools/cool', *args], text=True, capture_output=True, timeout=40, **kwargs)
PROGRAM = 'import "std/io";\nimport "std/mem";\nimport r "std/result";\nimport o "std/option";\nstruct Pair { a: own[i64]; b: own[i64]; }\nfn make(n: i64) -> own[i64] { let p = new[i64](n); return move p; }\nfn release(p: own[i64]) { io.println(*p); }\nfn early(n: i64) -> i64 { let p = new[i64](n); if (n == 0) { return 9; } return *p; }\nfn main() {\n    { var p = make(1); p = make(2); io.println(*p); io.println(mem.owner_count()); }\n    io.println(mem.owner_count());\n    { let pair = Pair{a: make(3), b: make(4)}; let moved = move pair; io.println(*moved.a); }\n    io.println(mem.owner_count());\n    { let a = [2]own[i64]{make(5), make(6)}; let b = move a; io.println(*b[1]); }\n    io.println(mem.owner_count());\n    { let p = new[own[i64]](make(7)); io.println(**p); }\n    io.println(mem.owner_count());\n    { let p = make(8); defer release(move p); io.println(mem.owner_count()); }\n    io.println(mem.owner_count());\n    var i = 0;\n    while (i < 5) { let p = make(i); i = i + 1; if (i == 2) { continue; } if (i == 4) { break; } }\n    io.println(mem.owner_count());\n    io.println(early(0)); io.println(mem.owner_count());\n    { let p = r.value_or[own[i64],string](r.Result[own[i64],string].Ok(make(10)), make(11)); io.println(*p); }\n    io.println(mem.owner_count());\n    { let p = o.value_or[own[i64]](o.Option[own[i64]].None, make(12)); io.println(*p); }\n    io.println(mem.owner_count());\n    make(13); io.println(mem.owner_count());\n}\n'
EXPECTED = '2\n1\n0\n3\n0\n6\n0\n7\n0\n1\n8\n0\n0\n9\n0\n10\n0\n12\n0\n0\n'
NEGATIVE = [
    ('let p = new[i64](1); let q = p;', 'explicit move'),
    ('let p = new[i64](1); let q = move p; io.println(*p);', 'moved value'),
    ('let p = new[i64](1); if (true) { let q = move p; } io.println(*p);', 'moved value'),
    ('let p = new[i64](1); while (true) { let q = move p; }', 'outer owner'),
    ('let p = new[i64](1); for (; true; release(move p)) {}', 'outer owner'),
    ('let p = new[i64](1); while (consume(move p)) {}', 'outer owner'),
    ('var a = [1]own[i64]{new[i64](1)}; let s = a[:]; let gone=move a;', 'conflicts'),
    ('let p = new[[2]i64](); let s = (*p)[:]; let gone=move p;', 'conflicts'),
    ('var a = [1]i64{1}; let p = new[[]i64](a[:]);', 'borrowed references'),
]
with tempfile.TemporaryDirectory(prefix='cool-owners-') as tmp:
    source = Path(tmp)/'main.cool'; source.write_text(PROGRAM)
    for mode in ('tree', 'interp', 'jit', 'llvm', 'llvm-jit'):
        p = cool('run', '--backend', mode, str(source))
        assert (p.returncode,p.stdout,p.stderr)==(0,EXPECTED,''),(mode,p)
    # Both optimization levels must preserve exactly-once destruction.
    for opt in ('0', '2'):
        binary=Path(tmp)/('owner-O'+opt)
        p=cool('build',*(['--release'] if opt == '2' else []),'-o',str(binary),str(source))
        assert p.returncode==0,p
        p=subprocess.run([binary],capture_output=True,text=True,timeout=10)
        assert (p.returncode,p.stdout,p.stderr)==(0,EXPECTED,''),p
    for body, diagnostic in NEGATIVE:
        source.write_text('import "std/io"; fn release(p: own[i64]) {} fn consume(p: own[i64]) -> bool { return true; } fn main() {'+body+'}')
        p=cool('check',str(source))
        assert p.returncode!=0 and diagnostic in p.stderr,(body,p)
repl = '''import "std/mem";
var p = new[i64](42);
let failed = move p + 1;
*p
mem.owner_count()
fn boom(p: own[i64]) { let q = new[i64](9); assert(false); }
boom(move p);
mem.owner_count()
*p
p = new[i64](8);
*p
{ let q = new[i64](9); assert(false); }
mem.owner_count()
*p
:quit
'''
p=cool('repl',input=repl)
assert p.returncode==0 and p.stdout=='42\n1\n0\n8\n1\n8\n',p
assert p.stderr.count('assertion failed')==2 and 'moved value' in p.stderr,p
print('ownership: five engines, LLVM O0/O2, nested owners, Result/Option, defer, loop/return cleanup, rejection and REPL rollback PASS')
