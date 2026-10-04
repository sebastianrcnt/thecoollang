#!/usr/bin/env python3
"""Verify new-syntax fixed point and execution without the legacy loader/seed."""
from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
def run(*args, **kw):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=90, **kw)
with tempfile.TemporaryDirectory(prefix='cool-selfhost-') as tmp:
    tmp=Path(tmp)
    compiler=tmp/'cool-compiler'; shutil.copy2(ROOT/'build/cool-compiler', compiler)
    env=dict(os.environ, COOLC_COMPILER_BIN='/does/not/exist', COOL_FRONTEND=str(compiler))
    ir=tmp/'stage3.ll'
    run(compiler,'llvm',ROOT/'compiler/main.cool',ir,cwd=tmp,env=env)
    first=(ROOT/'build/compiler-stage1.ll').read_bytes()
    second=(ROOT/'build/compiler-stage2.ll').read_bytes()
    assert first==second==ir.read_bytes(),'new compiler does not converge'
    (tmp/'next').mkdir()
    next_compiler=tmp/'next/cool-compiler'
    run('clang','-Wno-override-module','-O2',ir,ROOT/'build/compiler-host.o',ROOT/'build/language-runtime.o','-lffi','-o',next_compiler)
    assert (next_compiler).read_bytes()==compiler.read_bytes(),'native self-hosted binaries differ'
    sample=tmp/'hello.cool';sample.write_text('import "std/io"; fn main() { io.println(42); }')
    for mode in ('run','bytecode','jit'):
        p=run(next_compiler,mode,sample,cwd=tmp,env=env)
        assert (p.stdout,p.stderr)==('42\n',''),p
    print('self-host: bootstrap/stage2/stage3 IR and stage2/stage3 native binaries identical; standalone tree/VM/JIT PASS')
    print('IR SHA256:',hashlib.sha256(second).hexdigest())
