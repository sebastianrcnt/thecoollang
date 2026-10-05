#!/usr/bin/env python3
"""Manifest/workspace/checksum contracts and real tagged Git fetches, without make."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from modules import Graph, Manifest, tree_hash, validate_version, version_key

ROOT=Path(__file__).resolve().parents[1]

def rejects(action, text):
    try:action()
    except ValueError as error:
        assert text in str(error),(text,str(error))
    else:raise AssertionError('accepted invalid module input: '+text)

def git(root,*args):
    return subprocess.run(['git','-C',root,*args],check=True,text=True,capture_output=True)

def test_local_graph_roots(tmp, frontend):
    for style in ('replace', 'workspace'):
        base=tmp/('roots-'+style);base.mkdir()
        app=base/'main';app.mkdir();local=base/'local';local.mkdir();peer=base/'peer';peer.mkdir()
        main_path='example.test/seeds/main_'+style
        local_path='example.test/seeds/local_'+style
        peer_path='example.test/seeds/peer_'+style
        dep_path='example.test/seeds/dep_'+style
        manifest=Manifest(app,main_path)
        Manifest(local,local_path,requires={dep_path:'v1.0.0'}).write()
        Manifest(peer,peer_path,requires={dep_path:'v1.2.0'}).write()
        (app/'common').mkdir()
        (app/'common/common.cool').write_text('package common;pub fn value()->i64{return 30;}')
        (local/'lib.cool').write_text('package lib;import dep "'+dep_path+'";import common "'+main_path+'/common";pub fn value()->i64{return dep.value()+common.value();}')
        (peer/'peer.cool').write_text('package peer;pub fn unused(){}')
        (app/'main.cool').write_text('package main;import "std/io";import lib "'+local_path+'";fn main(){io.println(lib.value());}')
        dependencies={}
        for version,value in [('v1.0.0',10),('v1.2.0',12)]:
            root=Path(os.environ['COOL_CACHE'])/'mod'/(dep_path+'@'+version);root.mkdir(parents=True)
            # A tagged requirement back to main must not replace the invoking
            # checkout, be fetched, become selected, or demand a main checksum.
            Manifest(root,dep_path,requires={main_path:'v1.0.0'}).write()
            source=root/'dep.cool';source.write_text(f'package dep;pub fn value()->i64{{return {value};}}')
            dependencies[version]=(root,source,source.read_text())
        shadow=Path(os.environ['COOL_CACHE'])/'mod'/(main_path+'@v1.0.0');shadow.mkdir(parents=True)
        Manifest(shadow,main_path).write();(shadow/'common').mkdir()
        (shadow/'common/common.cool').write_text('package common;pub fn value()->i64{return 999;}')
        if style=='replace':
            manifest.replaces={local_path:str(local),peer_path:str(peer)}
        else:
            # The same main checkout can appear in use, but is seeded once.
            (app/'cool.work').write_text('cool 1.0\nuse (\n'+repr(str(app))+'\n'+repr(str(local))+'\n'+repr(str(peer))+'\n)\n')
        manifest.write()
        if style=='replace':
            manifest.replaces[main_path]=str(shadow);manifest.write()
            rejects(lambda:Graph(Manifest.read(app),offline=True).resolve(),'conflicting local main module identity')
            manifest.replaces[main_path]=str(app);manifest.write()
        assert Manifest.read(app).requires=={}
        rejects(lambda:Graph(Manifest.read(app),offline=True,frozen=True).resolve(),'frozen: missing checksum')
        graph=Graph(Manifest.read(app),offline=True).resolve()
        assert graph.selected=={dep_path:'v1.2.0'},graph.selected
        assert graph.roots[main_path]==app.resolve()
        assert graph.package(main_path+'/common')==app.resolve()/'common'
        assert local_path not in graph.selected and peer_path not in graph.selected
        assert set(graph.visited_roots)=={(dep_path,'v1.0.0'),(dep_path,'v1.2.0')}
        assert set(graph.pending_sums)==set(graph.visited_roots)
        graph.save_sums();sums=(app/'cool.sum').read_bytes()
        Graph(Manifest.read(app),offline=True,frozen=True).resolve()
        env={**os.environ,'COOL_FRONTEND':str(frontend)}
        for command in (['check','--offline','--frozen','.'],['run','--backend','interp','--offline','--frozen','.']):
            result=subprocess.run([ROOT/'tools/cool',*command],cwd=app,env=env,text=True,capture_output=True,timeout=60)
            assert (result.returncode,result.stdout,result.stderr)==(0,'42\n' if command[0]=='run' else '',''),(style,result)
        assert (app/'cool.sum').read_bytes()==sums
        high,source,original=dependencies['v1.2.0']
        source.write_text(original+'// tamper')
        rejects(lambda:Graph(Manifest.read(app),offline=True,frozen=True).resolve(),'checksum mismatch')
        source.write_text(original)
        missing=high.with_name(high.name+'-removed');high.rename(missing)
        rejects(lambda:Graph(Manifest.read(app),offline=True,frozen=True).resolve(),'offline: missing cached module')
        missing.rename(high)
        Graph(Manifest.read(app),offline=True,frozen=True).resolve()
        if style=='workspace':
            duplicate=base/'duplicate';duplicate.mkdir();Manifest(duplicate,local_path).write()
            (app/'cool.work').write_text('use '+repr(str(local))+'\nuse '+repr(str(duplicate))+'\n')
            rejects(lambda:Graph(Manifest.read(app),offline=True),'conflicting workspace module identity')
            (app/'cool.work').write_text('use '+repr(str(local))+'\nuse '+repr(str(local))+'\n')
            duplicate_graph=Graph(Manifest.read(app),offline=True,frozen=True).resolve()
            assert duplicate_graph.roots[local_path]==local.resolve()
            conflict=base/'conflict';conflict.mkdir();Manifest(conflict,main_path).write()
            (app/'cool.work').write_text('use '+repr(str(conflict))+'\n')
            rejects(lambda:Graph(Manifest.read(app),offline=True),'conflicting workspace main module identity')


with tempfile.TemporaryDirectory(prefix='cool module contract ') as directory:
    tmp=Path(directory);app=tmp/'app';app.mkdir()
    original_env=dict(os.environ)
    os.environ['COOL_CACHE']=str(tmp/'cache')
    os.environ.pop('COOL_OFFLINE',None)
    os.environ.pop('COOL_GIT_SSH',None)
    try:
        manifest=Manifest(app,'example.test/team/app');manifest.write()
        for directive,error in [('format 2','invalid directive'),('cool 2.0','unsupported language'),
                                ('cool 1.0\ncool 1.0','duplicate cool'),('require (','unclosed block'),
                                (')','unexpected )'),('unknown future','invalid directive')]:
            (app/'cool.mod').write_text('module example.test/team/app\n'+directive+'\n')
            rejects(lambda:Manifest.read(app),error)
        manifest.write()
        # The format already permits shell quoting for paths; // inside quotes
        # must survive write/read rather than becoming a comment.
        local=tmp/'local space';local.mkdir();Manifest(local,'example.test/team/local').write()
        manifest.replaces={'example.test/team/local':str(tmp)+'//local space'};manifest.write()
        assert Manifest.read(app).replaces==manifest.replaces
        Graph(Manifest.read(app),offline=True).resolve()
        for path in ('relative//local', "relative//a'b"):
            manifest.replaces={'example.test/team/local':path};manifest.write()
            assert Manifest.read(app).replaces==manifest.replaces
        manifest.replaces={'example.test/team/wrong':str(local)};manifest.write()
        rejects(lambda:Graph(Manifest.read(app),offline=True).resolve(),'replacement module path mismatch')
        manifest.replaces={};manifest.write()
        work=app/'cool.work'
        for content,error in [('cool 999\n','unsupported workspace'),('cool future extra\n','invalid'),
                              ('cool 1.0\ncool 1.0\n','duplicate'),('use (\n','unclosed'),
                              (')\n','unexpected'),('use (\nuse (\n','nested'),
                              ('format 2\n','expected use'),('use (\ncool 1.0\n)\n','invalid')]:
            work.write_text(content);rejects(lambda:Graph(Manifest.read(app)),error)
        work.write_text('cool 1.0\nuse (\n'+repr(str(local))+' // actual comment\n)\n')
        graph=Graph(Manifest.read(app),offline=True).resolve()
        assert graph.package('example.test/team/local')==local.resolve()
        work.unlink()
        checksum=app/'cool.sum';digest='h1:'+base64.b64encode(bytes(32)).decode()
        for content,error in [
            ('example.test/team/unused v1.0.0 h2:future','unsupported checksum'),
            ('../bad v1.0.0 '+digest,'invalid module path'),
            ('example.test/team/unused v01.0.0 '+digest,'invalid semantic'),
            ('example.test/team/unused v1.0.0 h1:AA==','invalid h1'),
            ('example.test/team/unused v1.0.0 h1:not-base64','invalid h1'),
            ('format 2','expected module version'),
            ('example.test/team/unused v1.0.0 '+digest+' extra','expected module version')]:
            checksum.write_text(content+'\n');rejects(lambda:Graph(Manifest.read(app)),error)
        checksum.write_text(('example.test/team/unused v1.0.0 '+digest+'\n')*2)
        Graph(Manifest.read(app))  # Existing identical duplicate rows remain valid.
        checksum.write_text('example.test/team/unused v1.0.0 '+digest+'\nexample.test/team/unused v1.0.0 h1:'+base64.b64encode(bytes([1])*32).decode()+'\n')
        rejects(lambda:Graph(Manifest.read(app)),'conflicting checksums')
        checksum.unlink()
        for major in (2,9,10,19,20,100):
            validate_version(f'example.test/team/lib/v{major}',f'v{major}.0.0')
            rejects(lambda major=major:validate_version('example.test/team/lib',f'v{major}.0.0'),f'/v{major}')
        versions=['v1.0.0-alpha','v1.0.0-alpha.1','v1.0.0-alpha.beta','v1.0.0-beta',
                  'v1.0.0-beta.2','v1.0.0-beta.11','v1.0.0-rc.1','v1.0.0']
        assert sorted(reversed(versions),key=version_key)==versions
        for version in ('v1.0.0-alpha.01','v1.0.0-a..b','v01.0.0','v1.0','v1.0.0+build'):
            rejects(lambda version=version:version_key(version),'invalid')
        # Git's URL rewrite redirects the real HTTPS clone/archive code path to
        # a local tagged repository; no subprocess mocking or external service.
        repository=tmp/'remotes/team/lib.git';repository.mkdir(parents=True)
        git(repository,'init','-q');git(repository,'config','user.email','test@example.test')
        git(repository,'config','user.name','Module Test')
        module='example.test/team/lib/v10'
        for tag,value in [('v10.0.0',10),('v10.1.0-alpha.2',12),('v10.1.0-alpha.10',20)]:
            Manifest(repository,module).write()
            (repository/'lib.cool').write_text(f'package lib;pub fn value()->i64{{return {value};}}\n')
            git(repository,'add','.');git(repository,'commit','-qm',tag);git(repository,'tag',tag)
        config=tmp/'gitconfig'
        config.write_text('[url "'+(tmp/'remotes').as_uri()+'/"]\n\tinsteadOf = https://example.test/\n')
        os.environ.update(GIT_CONFIG_GLOBAL=str(config),GIT_CONFIG_NOSYSTEM='1',GIT_TERMINAL_PROMPT='0')
        manifest.requires={module:'v10.1.0-alpha.10'}
        rejects(lambda:Graph(manifest,offline=True).resolve(),'offline: missing')
        # Two immutable tagged graph paths require different prereleases. MVS
        # must select numeric alpha.10 while visiting/checksumming both versions.
        for name, requirement in [('left','v10.1.0-alpha.2'),('right','v10.1.0-alpha.10')]:
            folder=tmp/'cache/mod'/('example.test/team/'+name+'@v1.0.0');folder.mkdir(parents=True)
            Manifest(folder,'example.test/team/'+name,requires={module:requirement}).write()
        manifest.requires={'example.test/team/left':'v1.0.0','example.test/team/right':'v1.0.0'}
        graph=Graph(manifest).resolve()
        assert graph.selected[module]=='v10.1.0-alpha.10'
        assert (module,'v10.1.0-alpha.2') in graph.visited_roots
        graph.save_sums();Graph(manifest,offline=True,frozen=True).resolve()
        manifest.requires={module:'v10.1.0-alpha.10'};manifest.write()
        fetched=Graph(manifest).resolve();fetched.save_sums()
        assert fetched.selected[module]=='v10.1.0-alpha.10'
        cache_root=fetched.roots[module];assert tree_hash(cache_root)==fetched.sums.get((module,'v10.1.0-alpha.10'),fetched.pending_sums[module,'v10.1.0-alpha.10'])
        Graph(manifest,offline=True,frozen=True).resolve()
        # Actual CLI import from fetched tagged module, with a pinned executable.
        frontend=tmp/'frontend';shutil.copy2(Path(os.environ.get('COOL_FRONTEND',ROOT/'build/cool-compiler')),frontend)
        (app/'main.cool').write_text('package main;import "std/io";import lib "'+module+'";fn main(){io.println(lib.value());}\n')
        env={**os.environ,'COOL_FRONTEND':str(frontend)}
        for command in (['check','--offline','--frozen','.'],['run','--backend','interp','--offline','--frozen','.']):
            result=subprocess.run([ROOT/'tools/cool',*command],cwd=app,env=env,text=True,capture_output=True,timeout=60)
            assert (result.returncode,result.stdout,result.stderr)==(0,'20\n' if command[0]=='run' else '',''),result
        test_local_graph_roots(tmp,frontend)
        before=checksum.read_bytes()
        (cache_root/'lib.cool').write_text('tampered')
        rejects(lambda:Graph(manifest,offline=True,frozen=True).resolve(),'checksum mismatch')
        assert checksum.read_bytes()==before
        (cache_root/'lib.cool').write_text('package lib;pub fn value()->i64{return 20;}\n')
        # Wrong cached identity is rejected independently of frozen checksums.
        Manifest(cache_root,'example.test/team/wrong').write()
        rejects(lambda:Graph(manifest,offline=True).resolve(),'cached module path mismatch')
        Manifest(cache_root,module).write()
        Graph(manifest,offline=True,frozen=True).resolve()
        vendor=app/'vendor';target=vendor/module;target.parent.mkdir(parents=True)
        shutil.copytree(cache_root,target)
        index=vendor/'cool.vendor.json'
        for invalid in ('[]','{"format":2,"modules":{}}',json.dumps({module:2}),json.dumps({module:'v99.0.0'})):
            index.write_text(invalid)
            rejects(lambda:Graph(manifest,offline=True,frozen=True).resolve(),
                    'require /v99' if 'v99' in invalid else 'unsupported vendor index format')
        index.write_text('{'+json.dumps(module)+':"v10.1.0-alpha.2",'+json.dumps(module)+':"v10.1.0-alpha.10"}')
        rejects(lambda:Graph(manifest,offline=True,frozen=True).resolve(),'duplicate vendor index')
        index.write_text(json.dumps({module:'v10.1.0-alpha.10'}))
        Graph(manifest,offline=True,frozen=True).resolve()
        Manifest(target,'example.test/team/wrong').write()
        rejects(lambda:Graph(manifest,offline=True,frozen=True).resolve(),'vendored module path mismatch')
    finally:
        os.environ.clear();os.environ.update(original_env)
print('module contract: strict manifests/workspaces/checksums/vendor, major suffixes, prerelease ordering, real tagged Git fetch, offline/frozen CLI, addressable local/workspace graph roots, main root shadow prevention, tamper and identity rejection PASS')
