#!/usr/bin/env python3
"""Exercise the checked-in tally application and sustained stateful development."""
from collections import Counter
from pathlib import Path
import argparse
import json
import os
import platform
import random
import re
import shlex
import shutil
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--frontend', type=Path)
parser.add_argument('--rounds', type=int, default=128)
parser.add_argument('--rss-output', type=Path, help='macOS frontend-only peak RSS observations')
args = parser.parse_args()
assert 1 <= args.rounds <= 4096
assert not args.rss_output or platform.system() == 'Darwin'
measurements = []

def run(command, cwd, **kwargs):
    return subprocess.run([str(item) for item in command], cwd=cwd, text=True, capture_output=True, timeout=240, **kwargs)

with tempfile.TemporaryDirectory(prefix='cool tally 한글 ') as tmp:
    directory = Path(tmp)
    project = directory/'project'
    shutil.copytree(ROOT/'examples/tally', project)
    bootstrap = directory/'bootstrap'
    bootstrap.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n')
    bootstrap.chmod(0o755)
    fronts = [ROOT/'build/cool-compiler', bootstrap]
    if args.frontend:
        fronts.append(args.frontend.resolve())
    environment = {**os.environ, 'COOL_CACHE':str(directory/'cache')}
    labels = ['apple', '한글', '', 'quote"', 'line\nbreak', '🙂', 'apple', '한글']*9
    if not args.frontend and not args.rss_output:
        for front in fronts:
            result = run([ROOT/'tools/cool', 'check', '.'], project, env={**environment,'COOL_FRONTEND':str(front)})
            assert result.returncode == 0, result
        formatted = run([ROOT/'tools/cool', 'fmt', '--check', '.'], project, env=environment)
        assert formatted.returncode == 0, formatted
        documented = run([ROOT/'tools/cool', 'doc', 'ledger'], project, env=environment)
        assert documented.returncode == 0 and 'pub fn add(' in documented.stdout and 'pub fn snapshot(' in documented.stdout and 'fn label(' not in documented.stdout, documented
        for engine in ('tree', 'interp', 'jit', 'llvm', 'llvm-jit'):
            output = directory/(engine+'.json')
            result = run([ROOT/'tools/cool', 'run', '--backend', engine, '.', '--', output, *labels], project, env=environment)
            assert (result.returncode, result.stdout, result.stderr) == (0, str(len(labels))+'\n', ''), (engine, result)
            assert json.loads(output.read_text()) == dict(Counter(labels)), engine
        binary = directory/'tally'
        result = run([ROOT/'tools/cool', 'build', '--release', '.', '-o', binary], project, env=environment)
        assert result.returncode == 0, result
        output = directory/'native.json'
        result = run([binary, output, *labels], directory, env=environment)
        assert (result.returncode,result.stdout,result.stderr) == (0,str(len(labels))+'\n',''), result
        assert json.loads(output.read_text()) == dict(Counter(labels))
        failed = run([binary, directory/'missing'/'output.json', 'apple'], directory, env=environment)
        assert failed.returncode != 0 and 'assertion failed' in failed.stderr, failed
        invalid = subprocess.run([os.fsencode(binary),os.fsencode(output),b'\xff'],capture_output=True,timeout=30)
        assert invalid.returncode != 0 and b'assertion failed' in invalid.stderr, invalid
        result = run([binary], directory, env=environment)
        assert (result.returncode,result.stdout,result.stderr) == (0,'Usage: tally OUTPUT.json [LABEL ...]\n',''), result
        print('tally project: both frontends, five engines and standalone O2 JSON output match Python Counter PASS')

    keys = ['apple', '한글', '', '🙂'] + [f'item{i}' for i in range(12)]
    expected = Counter()
    lines = ['import ledger "example.test/tally/ledger";', 'import fs "std/fs";',
             'import text "std/text";', 'import result "std/result";', 'import "std/mem";',
             'var book=ledger.create();',
             'fn apply(book:&mut ledger.Book,key:string,amount:i64)->i64{return ledger.add(book,key,amount);}',
             'fn update(book:&mut ledger.Book,key:string,amount:i64)->i64{return apply(book,key,amount);}',
             'fn save(book:&ledger.Book){let encoded=ledger.snapshot(book);assert(result.is_ok[usize,i32](fs.write("session.json",text.as_bytes(&encoded))));}']
    values = []
    errors = Counter()
    rng = random.Random(20261005)
    for round_index in range(args.rounds):
        multiplier = (1,2,-1,3)[round_index%4]
        lines.append(f'fn apply(book:&mut ledger.Book,key:string,amount:i64)->i64{{return ledger.add(book,key,amount*({multiplier}));}}')
        for step in range(32):
            key = rng.choice(keys)
            amount = rng.randrange(-3,8)
            expected[key] += amount*multiplier
            call = f'update(&mut book,{json.dumps(key,ensure_ascii=False)},{amount})'
            if step == 15:
                lines.append('{let observed='+call+';assert(false);}')
                errors['assertion failed'] += 1
                lines.append('ledger.get(&book,'+json.dumps(key,ensure_ascii=False)+')')
                values.append(str(expected[key]))
            else:
                lines.append('{let observed='+call+';assert(observed=='+str(expected[key])+');}')
        lines.append('fn apply(book:&mut ledger.Book,key:string,amount:i64)->i64{let temporary=new[i64](1);return missing;}')
        errors['unknown variable'] += 1
        if round_index%8 == 0:
            lines.extend(['let held=ledger.view(&book);', 'update(&mut book,"apple",1000)', ':forget book', ':forget held'])
            errors['conflicts'] += 1
            errors['live dependent loans'] += 1
        lines.append('ledger.total(&book)')
        values.append(str(sum(expected.values())))
        if round_index%8 == 0:
            lines.append('save(&book)')
    for key in keys:
        lines.append('ledger.get(&book,'+json.dumps(key,ensure_ascii=False)+')')
        values.append(str(expected[key]))
    lines.extend(['save(&book)', ':forget book', 'mem.owner_count()', ':stats', ':quit'])
    values.append('0')
    source = '\n'.join(lines)+'\n'
    for index, front in enumerate(fronts):
        selected = front
        if args.rss_output:
            selected = directory/f'measured-{index}'
            selected.write_text('#!/bin/sh\nexec /usr/bin/time -l '+shlex.quote(str(front))+' \"$@\"\n')
            selected.chmod(0o755)
        result = run([ROOT/'tools/cool', 'repl', '--offline', '--frozen'], project, input=source,
                     env={**environment,'COOL_FRONTEND':str(selected)})
        if args.rss_output:
            rss = re.findall(r'(\d+)\s+maximum resident set size',result.stderr)
            assert len(rss) == 1, result.stderr
            measurements.append(dict(frontend='bootstrap' if front==bootstrap else str(front), rounds=args.rounds, updates=args.rounds*32, peak_rss_bytes=int(rss[0])))
        assert result.returncode == 0, (front,result)
        output = result.stdout.splitlines()
        assert output[:-1] == values, (front,output[:20],values[:20],result.stderr[:2000])
        stats = re.fullmatch(r'functions=(\d+) compiled=(\d+) bytecode_compilations=(\d+) jit_compilations=(\d+)',output[-1])
        assert stats and int(stats[4]) >= args.rounds, (front,output[-1])
        assert result.stderr.count('error:') == sum(errors.values()), (front,result.stderr)
        for diagnostic,count in errors.items():
            assert result.stderr.count(diagnostic) == count, (front,diagnostic,result.stderr)
        assert json.loads((project/'session.json').read_text()) == dict(expected), front
    print(f'tally REPL: {args.rounds*32} modeled updates, {args.rounds} replacements/runtime recoveries, cached callers, live loans, JSON checkpoints and zero surviving owners on {len(fronts)} frontends PASS')

if args.rss_output:
    args.rss_output.write_text(json.dumps(dict(platform=platform.platform(), method='macOS time -l around frontend only; one fresh process per frontend; includes cold compilation and full workload', measurements=measurements),indent=2)+'\n')
