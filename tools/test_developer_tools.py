#!/usr/bin/env python3
from pathlib import Path
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[1]

def command(*args, code=0, cwd=None):
    p = subprocess.run([ROOT/'tools/cool', *args], cwd=cwd, capture_output=True, text=True, timeout=20)
    assert p.returncode == code, (args, p.returncode, p.stdout, p.stderr)
    return p

with tempfile.TemporaryDirectory(prefix='cool-tools-') as tmp:
    tmp = Path(tmp)
    source = tmp/'main.cool'
    source.write_text('''// public API
package main; import "std/io";
/* block comment */ pub fn value(x:i64)->i64{return x+0x2A;}
fn main(){io.println(value(0));io.println("a \\\" b");}
// trailing comment
''')
    before = source.read_bytes()
    command('fmt', '--check', str(source), code=1)
    assert source.read_bytes() == before
    command('fmt', str(source))
    command('fmt', '--check', str(source))
    after = source.read_text()
    assert '// public API' in after and '/* block comment */' in after and '// trailing comment' in after
    assert command('run', str(source)).stdout == '42\na " b\n'
    assert command('doc', str(tmp)).stdout == 'pub fn value(x: i64) -> i64;\n'
    (tmp/'main_test.cool').write_text('package main; fn test_answer() { assert(value(0) == 42); }')
    for backend in ('interp', 'jit'):
        assert '1 tests passed' in command('test', str(tmp), '--backend', backend).stdout
    (tmp/'main_test.cool').write_text('package main; fn test_failure() { assert(false); }')
    assert 'assertion failed' in command('test', str(tmp), code=2).stderr
print('developer tools: token-preserving/idempotent formatting, API docs, test discovery and failure status PASS')
