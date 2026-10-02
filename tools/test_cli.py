#!/usr/bin/env python3
"""Exercise the public CLI from an unrelated directory and standalone execution."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
COOL = ROOT / 'tools/cool-legacy'


def call(*args, code=0, **kwargs):
    result = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=60, **kwargs)
    assert result.returncode == code, (args, result.returncode, result.stdout, result.stderr)
    return result.stdout


with tempfile.TemporaryDirectory(prefix='cool cli ') as tmp:
    work = Path(tmp)
    source = work / 'hello world.cool'
    shutil.copy2(ROOT / 'examples/hello.cool', source)
    assert call(COOL, 'run', source, cwd=work) == 'Hello, Cool!\n'
    output = work / 'hello app'
    call(COOL, 'build', source, '-o', output, cwd=work)
    # Only the executable is placed in the deployment directory; no BIN or source.
    deployed = work / 'deploy'
    deployed.mkdir()
    shutil.copy2(output, deployed / 'hello')
    assert call(deployed / 'hello', cwd=deployed, env={'PATH': '/usr/bin:/bin'}) == 'Hello, Cool!\n'
    assert (deployed / 'hello').read_bytes()[:4] == bytes.fromhex('cffaedfe')
    source.write_text('''import I64i NativeArgCount();
import U8i *NativeArg(I64i index);
import U0 NativeExit(I64i status);
extern U0 Print(U8i *fmt, ...);
Print("%s|%s\\n", NativeArg(1), NativeArg(2));
NativeExit(7);
''')
    assert call(COOL, 'run', source, '--', 'two words', '--flag', code=7, cwd=work) == 'two words|--flag\n'
    call(COOL, 'build', source, '-o', output, cwd=work)
    assert call(output, 'two words', '--flag', code=7, cwd=work) == 'two words|--flag\n'
    # Relative include lookup, working directory and file output remain caller-relative.
    (work / 'value.coolh').write_text('I64i Value() { return 42; }\n')
    source.write_text('#include "value.coolh"\nextern U0 Print(U8i *fmt, ...);\nPrint("%d\\n", Value());\n')
    assert call(COOL, 'run', source, cwd=work) == '42\n'
    before = source.read_bytes()
    call(COOL, 'compile', source, '-o', source, code=2, cwd=work)
    assert source.read_bytes() == before
    binary = work / 'program.BIN'
    call(COOL, 'compile', source, '-o', binary, cwd=work)
    assert call(COOL, 'run', binary, cwd=work) == '42\n'
    source.write_text('this is not valid Cool;\n')
    prior_bin = binary.read_bytes()
    result = subprocess.run([COOL, 'compile', source, '-o', binary], cwd=work, capture_output=True, timeout=60)
    assert result.returncode != 0 and binary.read_bytes() == prior_bin
    previous = output.read_bytes()
    result = subprocess.run([COOL, 'build', source, '-o', output], cwd=work, capture_output=True, timeout=60)
    assert result.returncode != 0
    assert output.read_bytes() == previous
    source.write_text('I64i Add(I64i a,I64i b){return a+b;}\n')
    original = source.read_bytes()
    call(COOL, 'fmt', '--check', source, code=1, cwd=work)
    assert source.read_bytes() == original
    call(COOL, 'fmt', source, cwd=work)
    call(COOL, 'fmt', '--check', source, cwd=work)
    call(COOL, 'run', work / 'missing.cool', code=2, cwd=work)
print('CLI: external paths, standalone Mach-O, arguments, exit codes, includes, BIN, errors, formatter: PASS')
