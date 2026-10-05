#!/usr/bin/env python3
"""Measure real project frontend/CLI costs and acknowledged REPL edit latency.
The default mode never builds the compiler; --default-cli uses a copied, verified
up-to-date development checkout with actual make dependency checks.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import runpy
import selectors
import shutil
import statistics
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]

def benchmark_default_cli(args):
    """Measure actual default driver calls in an independent source checkout."""
    from collections import Counter
    folders = ('compiler', 'language', 'tools', 'stdlib', 'coolc', 'examples/tally')
    artifacts = ('coolc', 'language.BIN', 'compiler.sources', 'compiler-stage1.ll',
                 'compiler-stage1', 'compiler-stage2.ll', 'compiler-host.o',
                 'language-runtime.o', 'cool-compiler')
    def inventory(root):
        paths = [root/'Makefile', root/'VERSION']
        for folder in folders:
            paths.extend(path for path in (root/folder).rglob('*')
                         if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc')
        paths.extend(root/'build'/name for name in artifacts)
        return {str(path.relative_to(root)):dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                                mtime_ns=path.stat().st_mtime_ns)
                for path in sorted(paths)}
    revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    initial = inventory(ROOT)
    results = {}
    with tempfile.TemporaryDirectory(prefix='cool-default-cli-bench-') as directory:
        tmp = Path(directory); snapshot = tmp/'checkout'; snapshot.mkdir()
        for folder in folders:
            shutil.copytree(ROOT/folder, snapshot/folder, ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        for name in ('Makefile','VERSION'):
            shutil.copy2(ROOT/name,snapshot/name)
        (snapshot/'build').mkdir()
        for name in artifacts:
            shutil.copy2(ROOT/'build'/name,snapshot/'build'/name)
        if inventory(ROOT) != initial or inventory(snapshot) != initial:
            raise RuntimeError('Source/artifact snapshot changed during capture; discard and rerun')
        env = dict(os.environ, COOL_CACHE=str(tmp/'cache'))
        env.pop('COOL_FRONTEND',None)
        for key in ('MAKEFLAGS','MFLAGS','MAKELEVEL'):
            env.pop(key,None)
        # This checks real prerequisites; failure never causes a timed rebuild.
        ready = subprocess.run(['make','-q','-C',snapshot,'build/cool-compiler','build/language-runtime.o'],
                               env=env,text=True,capture_output=True,timeout=60)
        if ready.returncode:
            raise RuntimeError('Captured checkout is not up to date; build beforehand: '+ready.stderr)
        print('Independent source/artifact snapshot captured; real make dependencies are up to date.', flush=True)
        frontend = snapshot/'build/cool-compiler'
        selected = {name:initial['build/'+name]['sha256'] for name in artifacts}
        def unchanged():
            for name,digest in selected.items():
                if hashlib.sha256((snapshot/'build'/name).read_bytes()).hexdigest()!=digest:
                    raise RuntimeError('Build artifact changed in timed snapshot: '+name)
        def measure(name, command, expected='', setup=None, oracle=None, selected_env=None):
            samples=[]
            for index in range(args.repeats):
                if setup:setup(index)
                started=time.perf_counter_ns()
                p=subprocess.run(command,cwd=tmp,env=selected_env or env,text=True,capture_output=True,timeout=180)
                samples.append((time.perf_counter_ns()-started)/1e6)
                if (p.returncode,p.stdout,p.stderr)!=(0,expected,''):
                    raise RuntimeError((command,p.returncode,p.stdout,p.stderr))
                if oracle:oracle()
                unchanged()
            results[name]=dict(median_ms=statistics.median(samples),min_ms=min(samples),
                               max_ms=max(samples),samples_ms=samples)
        measure('make_frontend_up_to_date', ['make','-s','-C',snapshot,'build/cool-compiler'])
        measure('make_runtime_up_to_date', ['make','-s','-C',snapshot,'build/language-runtime.o'])
        clang_version=subprocess.check_output(['clang','--version'],text=True,env=env)
        measure('clang_version_process', ['clang','--version'],expected=clang_version)
        workloads={};paired={}
        for label,extra in [('tally',0),('tally_expanded',args.files)]:
            project=tmp/label;shutil.copytree(snapshot/'examples/tally',project)
            for index in range(extra):
                (project/f'part-{index:04}.cool').write_text(
                    f'package main;fn bench_{index}(x:i64)->i64{{var value=x;'
                    'for(var j=0;j<20;j=j+1){value=value+j;}return value;}\n')
            cli=snapshot/'tools/cool';edited=project/'main.cool';original=edited.read_text()
            command=[str(cli),'check',str(project),'--offline','--frozen']
            clear_scan=lambda _:shutil.rmtree(tmp/'cache/scan',ignore_errors=True)
            measure(label+'_default_check_cold_metadata',command,setup=clear_scan)
            measure(label+'_default_check_warm_metadata',command)
            measure(label+'_default_check_one_file_edit',command,
                    setup=lambda i:edited.write_text(original+f'\n// default check edit {i}\n'))
            # Alternate order within pairs to reduce ordering bias. Both calls
            # see exactly the same source/cache contents and frontend revision.
            explicit={**env,'COOL_FRONTEND':str(frontend)};pairs=[]
            for repetition in range(args.repeats):
                row={}
                for mode in (('default','explicit') if repetition%2==0 else ('explicit','default')):
                    started=time.perf_counter_ns()
                    p=subprocess.run(command,cwd=tmp,env=env if mode=='default' else explicit,
                                     text=True,capture_output=True,timeout=180)
                    row[mode+'_ms']=(time.perf_counter_ns()-started)/1e6
                    if (p.returncode,p.stdout,p.stderr)!=(0,'',''):raise AssertionError(p)
                    unchanged()
                row['default_minus_explicit_ms']=row['default_ms']-row['explicit_ms'];pairs.append(row)
            paired[label]=dict(samples=pairs,median_default_minus_explicit_ms=statistics.median(
                               row['default_minus_explicit_ms'] for row in pairs))
            output=tmp/(label+'-model.json');labels=['apple','한글','','🙂','apple']*8
            def oracle():
                if json.loads(output.read_text())!=dict(Counter(labels)):
                    raise AssertionError('CLI result differs from Python Counter')
            run=[str(cli),'run',str(project),'--offline','--frozen','--',str(output),*labels]
            measure(label+'_default_run_cold_metadata',run,'40\n',setup=clear_scan,oracle=oracle)
            measure(label+'_default_run_warm_metadata',run,'40\n',oracle=oracle)
            measure(label+'_default_run_one_file_edit',run,'40\n',oracle=oracle,
                    setup=lambda i:edited.write_text(original+f'\n// default run edit {i}\n'))
            binary=tmp/(label+'-native')
            build=[str(cli),'build','--release',str(project),'--offline','--frozen','-o',str(binary)]
            def native_oracle():
                p=subprocess.run([str(binary),str(output),*labels],text=True,capture_output=True,timeout=60)
                if (p.returncode,p.stdout,p.stderr)!=(0,'40\n',''):raise AssertionError(p)
                oracle()
            measure(label+'_default_O2_build_cold_artifact',build,oracle=native_oracle,
                    setup=lambda _:shutil.rmtree(tmp/'cache/build',ignore_errors=True))
            measure(label+'_default_O2_build_cached_artifact',build,oracle=native_oracle)
            measure(label+'_default_O2_build_one_file_edit',build,oracle=native_oracle,
                    setup=lambda i:edited.write_text(original+f'\n// default build edit {i}\n'))
            llvm=[str(cli),'run','--backend','llvm',str(project),'--offline','--frozen','--',str(output),*labels]
            prime=subprocess.run(llvm,cwd=tmp,env=env,text=True,capture_output=True,timeout=180)
            if (prime.returncode,prime.stdout,prime.stderr)!=(0,'40\n',''):raise AssertionError(prime)
            oracle();unchanged()
            measure(label+'_default_llvm_run_cached_artifact',llvm,'40\n',oracle=oracle)
            saved=dict(os.environ)
            try:
                os.environ.update(explicit)
                driver=runpy.run_path(str(cli),run_name='benchmark_snapshot_driver')
                work=tmp/(label+'-manifest');work.mkdir()
                _,files=driver['bundle'](project,work,offline=True,frozen=True)
            finally:
                os.environ.clear();os.environ.update(saved)
            workloads[label]=dict(source_files=len(files),packages=len({identity for identity,_ in files}),
                                  source_bytes=sum(path.stat().st_size for _,path in files),extra_functions=extra)
        unchanged()
        report=dict(platform=platform.platform(),machine=platform.machine(),python=platform.python_version(),
                    mode='default_development_cli',source_revision=revision,repeats=args.repeats,workloads=workloads,results=results,
                    paired_warm_checks=paired,frontend_sha256=selected['cool-compiler'],
                    runtime_sha256=selected['language-runtime.o'],clang_version=clang_version,source_snapshot=initial,
                    methodology='Real copied checkout preserves source/artifact mtimes and verifies original/copy SHA256+mtime inventories during capture. make -q confirms frontend/runtime up to date before timing; timed default CLI unsets COOL_FRONTEND and includes actual locked make dependency checks. Artifact digests checked after every sample. Original checkout changes after snapshot cannot affect samples. Cold metadata clears only scan cache; cold O2 builds clear only native artifact cache, retaining warm metadata. Every edit is a unique comment and still a full frontend check/compile; edited O2 builds miss content-keyed artifacts. Program/standalone JSON output matches Python Counter outside timing. Native build timers include output copy but exclude oracle execution. Run timers include execution/JSON writing. Paired warm checks alternate order between default and explicit frontend; differences include the override branch and actual make checks, not a pure isolated make timer. No compiler/runtime rebuild is permitted or included.')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2)+'\n')
        for name,row in results.items():print(f'{name}: {row["median_ms"]:.3f} ms')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--default-cli', action='store_true', help='Measure default development CLI in an up-to-date independent source snapshot')
    parser.add_argument('--frontend', type=Path, default=ROOT/'build/cool-compiler', help='Pinned frontend for the original separated mode')
    parser.add_argument('--repeats', type=int, default=7)
    parser.add_argument('--files', type=int, default=512)
    parser.add_argument('--replacements', type=int, default=64)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if min(args.repeats, args.files, args.replacements) < 1:
        parser.error('counts must be positive')
    if args.default_cli:
        if args.frontend.resolve() != (ROOT/'build/cool-compiler').resolve():
            parser.error('--frontend cannot override the default CLI snapshot frontend')
        benchmark_default_cli(args)
        return
    frontend = args.frontend.resolve()
    digest = hashlib.sha256(frontend.read_bytes()).hexdigest()
    results = {}
    def record(name, samples):
        results[name] = dict(median_ms=statistics.median(samples), min_ms=min(samples),
                             max_ms=max(samples), samples_ms=samples)
    with tempfile.TemporaryDirectory(prefix='cool-project-bench-') as directory:
        tmp = Path(directory)
        env = {**os.environ, 'COOL_FRONTEND': str(frontend), 'COOL_CACHE': str(tmp/'cache')}
        # Import orchestration only; parsing and dependency scan stay in Cool.
        saved = dict(os.environ)
        os.environ.update(env)
        driver = runpy.run_path(str(ROOT/'tools/cool'), run_name='benchmark_driver')
        def run(command):
            started = time.perf_counter_ns()
            p = subprocess.run(command, cwd=tmp, env=env, text=True, capture_output=True, timeout=180)
            elapsed = (time.perf_counter_ns()-started)/1e6
            if p.returncode or p.stdout or p.stderr:
                raise RuntimeError((command, p.returncode, p.stdout, p.stderr))
            return elapsed
        def measure(name, command, setup=None):
            samples=[]
            for i in range(args.repeats):
                if setup: setup(i)
                samples.append(run(command))
            record(name, samples)
        workloads={}
        for label, extra in [('tally', 0), ('tally_expanded', args.files)]:
            project=tmp/label
            shutil.copytree(ROOT/'examples/tally', project)
            for i in range(extra):
                (project/f'part-{i:04}.cool').write_text(
                    f'package main;fn bench_{i}(x:i64)->i64{{var value=x;'
                    'for(var j=0;j<20;j=j+1){value=value+j;}return value;}\n')
            work=tmp/(label+'-manifest');work.mkdir()
            manifest, files=driver['bundle'](project,work,offline=True,frozen=True)
            workloads[label]=dict(source_files=len(files),source_bytes=sum(p.stat().st_size for _,p in files),
                                  packages=len({identity for identity,_ in files}),extra_functions=extra)
            measure(label+'_frontend_check', [str(frontend),'check-bundle',str(manifest)])
            measure(label+'_frontend_llvm', [str(frontend),'llvm-bundle',str(manifest),str(work/'app.ll')])
            measure(label+'_clang_O2_link', ['clang','-Wno-override-module','-O2',str(work/'app.ll'),
                                             str(ROOT/'build/language-runtime.o'),'-o',str(work/'app')])
            output = work/'model.json'
            labels = ['apple','한글','','🙂','apple']*8
            executed = subprocess.run([str(work/'app'),str(output),*labels],capture_output=True,text=True,timeout=60)
            if (executed.returncode,executed.stdout,executed.stderr)!=(0,'40\n',''):
                raise AssertionError(executed)
            from collections import Counter
            if json.loads(output.read_text()) != dict(Counter(labels)):
                raise AssertionError('native output disagrees with Python Counter')
            command=[str(ROOT/'tools/cool'),'check',str(project),'--offline','--frozen']
            measure(label+'_cli_cold_metadata', command, lambda _:shutil.rmtree(tmp/'cache'/'scan',ignore_errors=True))
            measure(label+'_cli_warm_metadata', command)
            edited=project/'main.cool';original=edited.read_text()
            measure(label+'_cli_one_file_edit',command,lambda i:edited.write_text(original+f'\n// edit {i}\n'))
            # Direct check after each content change still parses/checks the full graph.
            measure(label+'_frontend_one_file_edit', [str(frontend),'check-bundle',str(manifest)],
                    lambda i:edited.write_text(original+f'\n// direct edit {i}\n'))
        os.environ.clear();os.environ.update(saved)
        project=tmp/'tally'
        sessions=[]
        for repetition in range(args.repeats):
            started=time.perf_counter_ns()
            process=subprocess.Popen([str(ROOT/'tools/cool'),'repl','--offline','--frozen'],
                                     cwd=project,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE,bufsize=0)
            selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
            pending=b''
            def exchange(source,expected):
                nonlocal pending
                before=time.perf_counter_ns()
                process.stdin.write(source.encode());process.stdin.flush()
                while b'\n' not in pending:
                    if not selector.select(60):
                        process.kill();raise RuntimeError('REPL acknowledgment timed out')
                    chunk=os.read(process.stdout.fileno(),4096)
                    if not chunk:raise RuntimeError('REPL closed: '+process.stderr.read().decode())
                    pending+=chunk
                line,pending=pending.split(b'\n',1)
                if line.decode()!=str(expected):raise AssertionError((line,expected))
                return (time.perf_counter_ns()-before)/1e6
            startup=exchange('1\n',1)
            launch=(time.perf_counter_ns()-started)/1e6
            imported=exchange('import ledger "example.test/tally/ledger";\n2\n',2)
            initial=exchange('var book=ledger.create();\nfn apply(b:&mut ledger.Book,k:string,n:i64)->i64{return ledger.add(b,k,n);}\nfn update(b:&mut ledger.Book,k:string,n:i64)->i64{return apply(b,k,n);}\nupdate(&mut book,"apple",1)\n',1)
            for count in range(2,6):exchange('update(&mut book,"apple",1)\n',count)
            samples=[];expected=5
            for index in range(args.replacements):
                multiplier=1+index%3;expected+=multiplier
                samples.append(exchange(f'fn apply(b:&mut ledger.Book,k:string,n:i64)->i64{{return ledger.add(b,k,n*{multiplier});}}\nupdate(&mut book,"apple",1)\n',expected))
            exchange('ledger.get(&book,"apple")\n',expected)
            exchange(':forget book\nimport "std/mem";\nmem.owner_count()\n',0)
            process.stdin.write(b':stats\n:quit\n');process.stdin.close()
            tail=process.stdout.read().decode();error=process.stderr.read().decode()
            if process.wait(timeout=60) or error or pending or not tail.startswith('functions='):
                raise AssertionError((tail,error,pending))
            selector.close()
            sessions.append(dict(launch_to_ack_ms=launch,first_exchange_ms=startup,import_ack_ms=imported,
                                 initial_compile_call_ms=initial,replacement_call_samples_ms=samples,stats=tail.strip(),
                                 final_model_count=expected,final_owner_count=0))
        for field in ('launch_to_ack_ms','import_ack_ms','initial_compile_call_ms'):
            record('repl_'+field,[session[field] for session in sessions])
        record('repl_hot_replacement_and_call',[value for session in sessions for value in session['replacement_call_samples_ms']])
        if hashlib.sha256(frontend.read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Frontend changed during measurement; discard samples and rerun')
        report=dict(platform=platform.platform(),machine=platform.machine(),python=platform.python_version(),
                    frontend_sha256=digest,runtime_sha256=hashlib.sha256((ROOT/'build/language-runtime.o').read_bytes()).hexdigest(),repeats=args.repeats,replacements_per_session=args.replacements,
                    workloads=workloads,results=results,repl_sessions=sessions,
                    methodology='No make. Fresh CLI/frontend process timings include startup; manifests prepared outside timer. Explicit COOL_FRONTEND excludes build checks. Cold clears scan metadata only. One-file edits are unique comments and still full frontend checks. REPL timings end at checked numeric stdout acknowledgment, include pipe roundtrip, parsing/dispatch and final expression; import includes resolver and compilation. Warm callers precede replacements. Final count uses independent arithmetic model; forget verifies zero owners. No claim of isolated codegen or runtime-only latency.')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2)+'\n')
        for name,value in results.items():print(f'{name}: {value["median_ms"]:.3f} ms')

if __name__=='__main__':main()
