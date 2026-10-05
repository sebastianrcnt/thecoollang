"""LSP transport and unsaved-file orchestration; Cool performs all analysis."""
from dataclasses import dataclass
from bisect import bisect_right
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit
from driver_common import find_root

ROOT = Path(__file__).resolve().parents[1]


def import_candidates(workspace):
    """Import paths offered inside an import string: stdlib plus workspace packages."""
    candidates = {'std/io', 'std/mem'}
    stdlib = ROOT / 'stdlib'
    if stdlib.is_dir():
        for entry in sorted(stdlib.iterdir()):
            if entry.is_dir() and (entry / (entry.name + '.cool')).is_file():
                candidates.add('std/' + entry.name)
    if workspace:
        module = None
        manifest = workspace / 'cool.mod'
        if manifest.is_file():
            for line in manifest.read_text().splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0] == 'module':
                    module = parts[1]
                    break
        if module:
            for base, dirs, files in os.walk(workspace):
                dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in ('build', 'vendor'))
                if any(name.endswith('.cool') for name in files):
                    relative = Path(base).relative_to(workspace)
                    candidates.add(module if str(relative) == '.' else module + '/' + str(relative).replace(os.sep, '/'))
    return sorted(candidates)

MAX_MESSAGE = 16 * 1024 * 1024


def read_message(stream):
    headers = {}
    for _ in range(32):
        line = stream.readline(8193)
        if not line:
            if not headers:
                return None
            raise ValueError('truncated LSP header')
        if len(line) > 8192:
            raise ValueError('LSP header too large')
        if line in (b'\r\n', b'\n'):
            break
        name, separator, value = line.partition(b':')
        if not separator or name.lower() in headers:
            raise ValueError('invalid LSP header')
        headers[name.lower()] = value.strip()
    else:
        raise ValueError('too many LSP headers')
    length = int(headers.get(b'content-length', b'-1'))
    if length < 0 or length > MAX_MESSAGE:
        raise ValueError('invalid LSP Content-Length')
    content = stream.read(length)
    if len(content) != length:
        raise ValueError('truncated LSP message')
    def invalid_constant(value):
        raise ValueError('invalid JSON constant: '+value)
    return json.loads(content.decode('utf-8'),parse_constant=invalid_constant)


def write_message(stream, message):
    content = json.dumps(message, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    stream.write(f'Content-Length: {len(content)}\r\n\r\n'.encode('ascii') + content)
    stream.flush()


def uri_path(uri):
    if not isinstance(uri,str):
        raise ValueError('document URI must be a string')
    parsed = urlsplit(uri)
    if parsed.scheme != 'file' or parsed.netloc not in ('', 'localhost') or parsed.query or parsed.fragment:
        raise ValueError('Cool currently supports local file URIs only')
    path = Path(unquote(parsed.path))
    if not path.is_absolute() or '\x00' in str(path) or path.suffix != '.cool':
        raise ValueError('expected an absolute .cool file URI')
    return path.resolve()


def text_index(text, position):
    line, character = position['line'], position['character']
    if type(line) is not int or type(character) is not int or line < 0 or character < 0:
        raise ValueError('invalid document position')
    lines = text.split('\n')
    if line >= len(lines):
        raise ValueError('document line out of range')
    value = lines[line]
    if line < len(lines)-1 and value.endswith('\r'):
        value = value[:-1]
    units = 0
    for index, char in enumerate(value):
        if units == character:
            return sum(len(part)+1 for part in lines[:line]) + index
        units += 2 if ord(char) > 0xffff else 1
        if units > character:
            raise ValueError('position splits a UTF-16 surrogate pair')
    if units != character:
        raise ValueError('document character out of range')
    return sum(len(part)+1 for part in lines[:line]) + len(value)


class PositionMap:
    def __init__(self,text):
        self.raw = text if isinstance(text,bytes) else text.encode('utf-8')
        self.decode_errors = 'ignore'
        if isinstance(text,bytes):
            try:
                text.decode('utf-8')
            except UnicodeDecodeError:
                self.decode_errors = 'replace'
        self.lines = [0]
        self.lines.extend(index+1 for index,byte in enumerate(self.raw) if byte==10)

    def position(self,offset):
        offset = max(0,min(int(offset),len(self.raw)))
        line = bisect_right(self.lines,offset)-1
        prefix = self.raw[self.lines[line]:offset].decode('utf-8',errors=self.decode_errors)
        return {'line':line,'character':len(prefix.encode('utf-16-le'))//2}


def byte_position(text,offset):
    return PositionMap(text).position(offset)


@dataclass
class Document:
    uri: str
    text: str
    version: int


class Server:
    def __init__(self, frontend, bundle, root, output):
        self.frontend, self.bundle, self.root, self.output = frontend, bundle, root, output
        self.documents = {}
        self.published = set()
        self.references = {}
        self.initialized = False
        self.shutdown = False

    def send(self, **message):
        write_message(self.output, {'jsonrpc':'2.0', **message})

    def error(self, identifier, code, message):
        self.send(id=identifier, error={'code':code, 'message':message})

    def analyze(self):
        diagnostics = {}
        references = {}
        reference_keys = {}
        position_maps = {}
        def positions(path):
            if path not in position_maps:
                text = self.documents[path].text if path in self.documents else path.read_bytes().decode('utf-8')
                position_maps[path] = PositionMap(text)
            return position_maps[path]

        with tempfile.TemporaryDirectory(prefix='cool-editor-') as directory:
            work = Path(directory)
            overlays = {}
            for index, (path, document) in enumerate(self.documents.items()):
                snapshot = work/f'buffer-{index}.cool'
                snapshot.write_bytes(document.text.encode('utf-8'))
                overlays[path] = snapshot
            originals = {snapshot:path for path,snapshot in overlays.items()}
            visited = set()
            for path, document in self.documents.items():
                entry = path.parent if find_root(path) else path
                if entry in visited:
                    continue
                visited.add(entry)
                output, failure = '', ''
                try:
                    manifest, _ = self.bundle(entry,work,True,True,True,overlays=overlays,editor=True)
                    result = subprocess.run([self.frontend,'editor-index-bundle',manifest],capture_output=True,text=True,timeout=20)
                    output = result.stdout
                    if result.returncode:
                        failure = result.stderr.strip() or 'compiler analysis failed'
                except subprocess.CalledProcessError as error:
                    output = error.stdout or ''
                    failure = error.stderr or 'package scan failed'
                except subprocess.TimeoutExpired:
                    failure = 'compiler analysis timed out'
                except (OSError, ValueError) as error:
                    failure = str(error)
                if not failure:
                    for line in output.splitlines():
                        try:
                            record = json.loads(line)
                        except ValueError:
                            continue
                        if not isinstance(record,dict) or record.get('kind') != 'reference':
                            continue
                        source = originals.get(Path(record['file']),Path(record['file']))
                        target = originals.get(Path(record['targetFile']),Path(record['targetFile']))
                        target_positions = positions(target)
                        uri = self.documents[target].uri if target in self.documents else target.as_uri()
                        location = {'uri':uri,'range':{'start':target_positions.position(record['targetStart']),
                            'end':target_positions.position(record['targetEnd'])}}
                        item = (record['start'],record['end'],location)
                        bucket = references.setdefault(source,[])
                        key = (record['start'],record['end'],target,record['targetStart'],record['targetEnd'])
                        seen = reference_keys.setdefault(source,set())
                        if key not in seen:
                            seen.add(key)
                            bucket.append(item)
                found = False
                for line in output.splitlines():
                    try:
                        record = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    if not isinstance(record,dict) or not all(key in record for key in ('file','start','end','message')):
                        continue
                    target = originals.get(Path(record['file']),Path(record['file']))
                    try:
                        content = self.documents[target].text if target in self.documents else target.read_bytes()
                    except OSError:
                        content = document.text
                        target = path
                    uri = self.documents[target].uri if target in self.documents else target.as_uri()
                    start = max(0,int(record['start']))
                    end = max(start,int(record['end']))
                    diagnostic = {'range':{'start':byte_position(content,start),'end':byte_position(content,end)},
                                  'severity':1,'source':'cool','message':record['message']}
                    bucket = diagnostics.setdefault(uri,[])
                    if diagnostic not in bucket:
                        bucket.append(diagnostic)
                    found = True
                if failure and not found:
                    diagnostics.setdefault(document.uri,[]).append({'range':{'start':{'line':0,'character':0},'end':{'line':0,'character':0}},
                        'severity':1,'source':'cool','message':failure[:8192]})
        self.references = references
        versions = {document.uri:document.version for document in self.documents.values()}
        current = set(diagnostics) | set(versions)
        for uri in sorted(self.published | current):
            params = {'uri':uri,'diagnostics':diagnostics.get(uri,[])}
            if uri in versions:
                params['version'] = versions[uri]
            self.send(method='textDocument/publishDiagnostics',params=params)
        self.published = current

    def complete(self,params):
        path = uri_path(params['textDocument']['uri'])
        content = self.documents[path].text if path in self.documents else path.read_bytes().decode('utf-8')
        cursor = text_index(content,params['position'])
        offset = len(content[:cursor].encode('utf-8'))
        positions = PositionMap(content)
        # An import string is completed from the module graph rather than the token stream.
        import_prefix = re.search(r'import[ \t]*"([^"\n]*)$', content[:cursor])
        if import_prefix:
            prefix = import_prefix.group(1)
            start = len(content[:import_prefix.start(1)].encode('utf-8'))
            items = [{'label': name, 'kind': 9,
                      'textEdit': {'range': {'start': positions.position(start), 'end': positions.position(offset)},
                                   'newText': name}}
                     for name in import_candidates(find_root(path)) if name.startswith(prefix)]
            return {'isIncomplete': False, 'items': items}
        with tempfile.TemporaryDirectory(prefix='cool-completion-') as directory:
            work = Path(directory)
            overlays = {}
            for index,(original,document) in enumerate(self.documents.items()):
                snapshot = work/f'buffer-{index}.cool'
                snapshot.write_bytes(document.text.encode('utf-8'))
                overlays[original] = snapshot
            try:
                entry = path.parent if find_root(path) else path
                manifest,_ = self.bundle(entry,work,True,True,True,overlays=overlays,editor=True,completion_source=path)
                result = subprocess.run([self.frontend,'editor-complete-bundle',manifest,overlays.get(path,path),str(offset)],
                    capture_output=True,text=True,timeout=20)
            except (subprocess.CalledProcessError,subprocess.TimeoutExpired,OSError,ValueError):
                return {'isIncomplete':True,'items':[]}
            items = {}
            for line in result.stdout.splitlines():
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(record,dict) or record.get('kind')!='completion':
                    continue
                label = record['label']
                items.setdefault(label,{'label':label,'kind':record['completionKind'],
                    'textEdit':{'range':{'start':positions.position(record['start']),'end':positions.position(record['end'])},'newText':label}})
            return {'isIncomplete':result.returncode!=0,'items':sorted(items.values(),key=lambda item:item['label'])}

    def handle(self, message):
        if not isinstance(message,dict) or message.get('jsonrpc') != '2.0' or not isinstance(message.get('method'),str):
            self.error(None,-32600,'invalid JSON-RPC request')
            return None
        if 'id' in message and type(message['id']) not in (int,str):
            self.error(None,-32600,'invalid request ID')
            return None
        # No-argument lifecycle requests commonly encode params as JSON null.
        if message.get('params',{}) is None and message['method'] in ('shutdown','exit'):
            message = {**message,'params':{}}
        if not isinstance(message.get('params',{}),dict):
            if 'id' in message:
                self.error(message['id'],-32602,'params must be an object')
            return None
        method = message['method']
        identifier = message.get('id')
        request = 'id' in message
        params = message.get('params',{})
        if method == 'exit':
            return 0 if self.shutdown else 1
        if method in ('initialize','shutdown') and not request:
            return None
        if method == 'initialize':
            if self.initialized:
                self.error(identifier,-32600,'already initialized')
            else:
                self.initialized = True
                self.send(id=identifier,result={'capabilities':{'positionEncoding':'utf-16','definitionProvider':True,'completionProvider':{'triggerCharacters':['.'],'resolveProvider':False},'textDocumentSync':{'openClose':True,'change':2,'save':{'includeText':False}}},
                    'serverInfo':{'name':'Cool','version':(self.root/'VERSION').read_text().strip()}})
            return None
        if not self.initialized or self.shutdown:
            if request:
                self.error(identifier,-32002 if not self.initialized else -32600,'server is not running')
            return None
        if method == 'shutdown':
            self.shutdown = True
            self.send(id=identifier,result=None)
        elif method in ('initialized','$/cancelRequest','$/setTrace'):
            pass
        elif method in ('textDocument/didOpen','textDocument/didChange','textDocument/didClose','textDocument/didSave'):
            descriptor = params['textDocument']
            path = uri_path(descriptor['uri'])
            if method == 'textDocument/didOpen':
                text, version = descriptor['text'], descriptor['version']
                if type(version) is not int or not isinstance(text,str):
                    raise ValueError('invalid document contents/version')
                text.encode('utf-8')
                self.documents[path] = Document(descriptor['uri'],text,version)
            elif method == 'textDocument/didChange':
                document = self.documents[path]
                version = descriptor['version']
                if type(version) is not int:
                    raise ValueError('invalid document version')
                if version <= document.version:
                    return None
                text = document.text
                for change in params['contentChanges']:
                    replacement = change['text']
                    if not isinstance(replacement,str):
                        raise ValueError('edit text must be a string')
                    replacement.encode('utf-8')
                    if 'range' not in change:
                        text = replacement
                    else:
                        start = text_index(text,change['range']['start'])
                        end = text_index(text,change['range']['end'])
                        if end < start:
                            raise ValueError('reversed edit range')
                        text = text[:start] + replacement + text[end:]
                self.documents[path] = Document(document.uri,text,version)
            elif method == 'textDocument/didClose':
                self.documents.pop(path,None)
            self.analyze()
        elif method == 'textDocument/completion' and request:
            self.send(id=identifier,result=self.complete(params))
        elif method == 'textDocument/definition' and request:
            path = uri_path(params['textDocument']['uri'])
            content = self.documents[path].text if path in self.documents else path.read_bytes().decode('utf-8')
            offset = len(content[:text_index(content,params['position'])].encode('utf-8'))
            candidates = self.references.get(path,[])
            matches = [location for start,end,location in candidates if start <= offset < end]
            if not matches:
                matches = [location for start,end,location in candidates if start < offset == end]
            unique = []
            for location in matches:
                if location not in unique:
                    unique.append(location)
            self.send(id=identifier,result=unique)
        elif method == 'workspace/didChangeWatchedFiles':
            self.analyze()
        elif request:
            self.error(identifier,-32601,'method not implemented')
        return None


def serve(frontend, bundle, root, input_stream=None, output_stream=None):
    input_stream = input_stream or sys.stdin.buffer
    output_stream = output_stream or sys.stdout.buffer
    server = Server(frontend,bundle,root,output_stream)
    while True:
        try:
            message = read_message(input_stream)
        except (ValueError, UnicodeError) as error:
            server.error(None,-32700,str(error))
            return 1
        if message is None:
            return 0 if server.shutdown else 1
        try:
            result = server.handle(message)
            if result is not None:
                return result
        except (KeyError, TypeError, ValueError, OSError) as error:
            if isinstance(message,dict) and 'id' in message:
                server.error(message['id'],-32602,str(error))
            else:
                server.send(method='window/logMessage',params={'type':1,'message':str(error)})
