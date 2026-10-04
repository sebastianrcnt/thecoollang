#!/usr/bin/env python3
"""Native diagnostics and LSP framing, overlays, versions and UTF-16 edits."""
from pathlib import Path
import io
import argparse
import json
import os
import queue
import shlex
import subprocess
import tempfile
import threading
from lsp_server import read_message, text_index, byte_position, Server
ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--frontend",type=Path)
args = parser.parse_args()

class Client:
    def __init__(self, frontend, cwd):
        self.process = subprocess.Popen([ROOT/'tools/cool','lsp'],cwd=cwd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            env={**os.environ,'COOL_FRONTEND':str(frontend),'COOL_CACHE':str(cwd/'cache')})
        self.messages = queue.Queue()
        def reader():
            try:
                while True:
                    item = read_message(self.process.stdout)
                    if item is None: break
                    self.messages.put(item)
            except Exception as error:
                self.messages.put(error)
        threading.Thread(target=reader,daemon=True).start()
        self.number = 0
    def send(self,method,params=None,identifier=None,fragmented=False):
        message = {'jsonrpc':'2.0','method':method}
        if params is not None: message['params'] = params
        if identifier is not None: message['id'] = identifier
        body = json.dumps(message,ensure_ascii=False).encode()
        data = f'Content-Length: {len(body)}\r\nContent-Type: application/vscode-jsonrpc; charset=utf-8\r\n\r\n'.encode()+body
        if fragmented:
            for byte in data:
                self.process.stdin.write(bytes([byte])); self.process.stdin.flush()
        else:
            self.process.stdin.write(data); self.process.stdin.flush()
    def until(self,identifier):
        received = []
        while True:
            item = self.messages.get(timeout=40)
            assert isinstance(item,dict), item
            if item.get('id') == identifier: return item,received
            received.append(item)
    def barrier(self):
        self.number += 1
        identifier = 'barrier'+str(self.number)
        self.send('cool/test-barrier',identifier=identifier)
        response,received = self.until(identifier)
        assert response['error']['code'] == -32601,response
        return {item['params']['uri']:item['params'] for item in received if item.get('method')=='textDocument/publishDiagnostics'}
    def close(self):
        self.send('shutdown',identifier='shutdown')
        response,_ = self.until('shutdown');assert response['result'] is None,response
        self.send('exit');assert self.process.wait(timeout=15)==0
        self.process.stdin.close();self.process.stdout.close();self.process.stderr.close()

with tempfile.TemporaryDirectory(prefix='cool editor 한글 ') as temporary:
    root = Path(temporary).resolve()
    project = root/'project';project.mkdir();(project/'cool.mod').write_text('module example.test/editor\n')
    main = project/'main.cool';main.write_text('package main;fn main(){}\n')
    library = project/'lib';library.mkdir();source = library/'lib.cool';source.write_text('package lib;pub fn answer()->i64{return 7;}\npub struct Box{pub value:i64;}\npub fn Box.read(self:&Box)->i64{return (*self).value;}\npub fn identity[T](value:T)->T{return value;}\n')
    original = {p:p.read_bytes() for p in (main,source,project/'cool.mod')}
    bootstrap = root/'bootstrap'
    bootstrap.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');bootstrap.chmod(0o755)
    for frontend in [ROOT/'build/cool-compiler',bootstrap]+([args.frontend.resolve()] if args.frontend else []):
        quoted = root/'quoted " 이름.cool';text='fn main(){let emoji="🙂";missing;}'
        quoted.write_text(text);manifest=root/'sources.list';manifest.write_text('__main\t'+str(quoted)+'\n')
        result = subprocess.run([frontend,'diagnostics-bundle',manifest],capture_output=True,text=True,timeout=30)
        record = json.loads(result.stdout)
        assert result.returncode==2 and record['file']==str(quoted) and record['start']==len(text[:text.index('missing')].encode()), result
        client = Client(frontend,project)
        try:
            client.send('test',identifier=1);response,_=client.until(1);assert response['error']['code']==-32002
            client.send('initialize',{'capabilities':{}},identifier=2,fragmented=True)
            response,_=client.until(2);assert response['result']['capabilities']['textDocumentSync']['change']==2
            assert response['result']['capabilities']['positionEncoding']=='utf-16'
            client.send('initialized',{})
            uri=main.as_uri();liburi=source.as_uri()
            text='package main;\r\nfn main(){let emoji="🙂";missing;}\r\n'
            client.send('textDocument/didOpen',{'textDocument':{'uri':uri,'languageId':'cool','version':1,'text':text}})
            diagnostics=client.barrier()[uri];assert diagnostics['version']==1
            error=diagnostics['diagnostics'][0]
            expected=byte_position(text,len(text[:text.index('missing')].encode()))
            assert error['range']['start']==expected and 'unknown variable' in error['message'],error
            start=expected;end={'line':start['line'],'character':start['character']+7}
            client.send('textDocument/didChange',{'textDocument':{'uri':uri,'version':2},'contentChanges':[{'range':{'start':start,'end':end},'text':'1'}]})
            assert client.barrier()[uri]['diagnostics']==[]
            # Changes in one notification are sequential, including a full replacement.
            client.send('textDocument/didChange',{'textDocument':{'uri':uri,'version':3},'contentChanges':[
                {'text':'package main;fn main(){missing;}'},
                {'range':{'start':{'line':0,'character':23},'end':{'line':0,'character':30}},'text':'1'}]})
            assert client.barrier()[uri]['diagnostics']==[]
            client.send('textDocument/didSave',{'textDocument':{'uri':uri}})
            assert client.barrier()[uri]['diagnostics']==[]
            client.send('workspace/didChangeWatchedFiles',{'changes':[]})
            assert client.barrier()[uri]['diagnostics']==[]
            client.send('textDocument/didChange',{'textDocument':{'uri':uri,'version':1},'contentChanges':[{'text':'broken'}]})
            assert client.barrier()=={}
            imported='package main;import l "example.test/editor/lib";fn main(){let value:i64=l.answer();}'
            client.send('textDocument/didChange',{'textDocument':{'uri':uri,'version':4},'contentChanges':[{'text':imported}]})
            assert client.barrier()[uri]['diagnostics']==[]
            badlib='package lib;pub fn answer()->i64{return missing;}'
            client.send('textDocument/didOpen',{'textDocument':{'uri':liburi,'languageId':'cool','version':1,'text':badlib}})
            diagnostics=client.barrier();assert len(diagnostics[liburi]['diagnostics'])==1 and diagnostics[uri]['diagnostics']==[]
            client.send('textDocument/didChange',{'textDocument':{'uri':liburi,'version':2},'contentChanges':[{'text':'package lib;pub fn answer()->string{return "value";}'}]})
            diagnostics=client.barrier();assert diagnostics[uri]['diagnostics'] and diagnostics[liburi]['diagnostics']==[]
            client.send('textDocument/didClose',{'textDocument':{'uri':liburi}})
            diagnostics=client.barrier();assert diagnostics[uri]['diagnostics']==[] and diagnostics[liburi]['diagnostics']==[],diagnostics
            client.send('textDocument/didChange',{'textDocument':{'uri':uri,'version':5},'contentChanges':[{'text':'package main;fn main(){helper();}'}]})
            assert client.barrier()[uri]['diagnostics']
            helper=project/'unsaved.cool';helperuri=helper.as_uri()
            client.send('textDocument/didOpen',{'textDocument':{'uri':helperuri,'languageId':'cool','version':1,'text':'package main;fn helper(){}'}})
            assert client.barrier()[uri]['diagnostics']==[] and not helper.exists()
            client.send('textDocument/didClose',{'textDocument':{'uri':helperuri}})
            assert client.barrier()[uri]['diagnostics']
            eof='package main;\nfn main(){'
            client.send('textDocument/didChange',{'textDocument':{'uri':uri,'version':6},'contentChanges':[{'text':eof}]})
            diagnostic=client.barrier()[uri]['diagnostics'][0]
            assert diagnostic['range']['start']=={'line':1,'character':10},diagnostic
            client.send('textDocument/didChange',{'textDocument':{'uri':uri,'version':7},'contentChanges':[{'text':'package main;fn main(){let x="bad\\q";}'}]})
            assert 'unsupported string escape' in client.barrier()[uri]['diagnostics'][0]['message']
            indexed='package main;\nimport l "example.test/editor/lib";\nfn main(){var box=l.Box{value:7};let typed:l.Box=box;var x=1;x=3;x=1;{let x=2;assert(x==2);}assert(x==1);assert(l.answer()==7);assert(typed.read()==7);assert(typed.value==7);assert(l.identity[i64](x)==1);}'
            client.send('textDocument/didChange',{'textDocument':{'uri':uri,'version':8},'contentChanges':[{'text':indexed}]})
            checked=client.barrier();assert checked[uri]['diagnostics']==[],checked
            def definition(document_uri,contents,offset,target_uri,target_text,target_offset,length):
                client.number+=1;identifier='definition'+str(client.number)
                client.send('textDocument/definition',{'textDocument':{'uri':document_uri},
                    'position':byte_position(contents,len(contents[:offset].encode()))},identifier=identifier)
                result,_=client.until(identifier)
                expected={'uri':target_uri,'range':{'start':byte_position(target_text,len(target_text[:target_offset].encode())),
                    'end':byte_position(target_text,len(target_text[:target_offset+length].encode()))}}
                assert result.get('result')==[expected],(offset,result,expected)
            libtext=source.read_text()
            definition(uri,indexed,indexed.index('x=3'),uri,indexed,indexed.index('x=1'),1)
            definition(uri,indexed,indexed.index('x==2'),uri,indexed,indexed.index('x=2'),1)
            definition(uri,indexed,indexed.index('x==1'),uri,indexed,indexed.index('x=1'),1)
            definition(uri,indexed,indexed.index('answer()'),liburi,libtext,libtext.index('answer()'),6)
            definition(uri,indexed,indexed.index('read()'),liburi,libtext,libtext.index('read('),4)
            definition(uri,indexed,indexed.index('value=='),liburi,libtext,libtext.index('value:i64'),5)
            definition(uri,indexed,indexed.index('value:7'),liburi,libtext,libtext.index('value:i64'),5)
            definition(uri,indexed,indexed.index('Box{'),liburi,libtext,libtext.index('Box{'),3)
            definition(uri,indexed,indexed.index('Box=box'),liburi,libtext,libtext.index('Box{'),3)
            definition(uri,indexed,indexed.index('identity['),liburi,libtext,libtext.index('identity['),8)
            definition(liburi,libtext,libtext.index('self).value'),liburi,libtext,libtext.index('self:&'),4)
            definition(liburi,libtext,libtext.index('return value')+7,liburi,libtext,libtext.index('value:T'),5)
            client.send('textDocument/didChange',{'textDocument':{'uri':uri,'version':9},'contentChanges':[{'text':indexed.replace('x=3','x=missing')}]})
            assert client.barrier()[uri]['diagnostics']
            client.send('textDocument/definition',{'textDocument':{'uri':uri},'position':{'line':2,'character':1}},identifier='stale-definition')
            response,_=client.until('stale-definition');assert response['result']==[]
            client.send('textDocument/didClose',{'textDocument':{'uri':uri}})
            assert client.barrier()[uri]['diagnostics']==[]
            client.close()
        finally:
            if client.process.poll() is None:client.process.kill();client.process.wait()
        assert all(path.read_bytes()==contents for path,contents in original.items())
        assert not (project/'cool.sum').exists()

assert text_index('a🙂b\r\nx',{'line':0,'character':3})==2
try:text_index('a🙂b',{'line':0,'character':2})
except ValueError:pass
else:raise AssertionError('split surrogate accepted')
for bad in (b'Content-Length: -1\r\n\r\n',b'Content-Length: 2\r\n\r\n{',b'Content-Length: 2\r\nContent-Length: 2\r\n\r\n{}'):
    try:read_message(io.BytesIO(bad))
    except ValueError:pass
    else:raise AssertionError(bad)
print('LSP: native diagnostics and definition lookup, shadowed locals/assignment/parameters, imported functions/types/fields/methods/generics, fragmented framing, UTF-16/CRLF, unsaved dependencies/new files, version ordering, index invalidation and no source writes PASS')

# No-argument lifecycle requests also accept explicit JSON null parameters.
output=io.BytesIO();server=Server(None,None,ROOT,output)
server.handle({'jsonrpc':'2.0','id':1,'method':'initialize','params':{}})
server.handle({'jsonrpc':'2.0','id':2,'method':'shutdown','params':None})
assert server.handle({'jsonrpc':'2.0','method':'exit','params':None})==0
output.seek(0);read_message(output);assert read_message(output)['result'] is None
