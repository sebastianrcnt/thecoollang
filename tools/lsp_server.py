"""LSP transport and unsaved-file orchestration; Cool performs all analysis."""
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit
from driver_common import find_root

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


def byte_position(text, offset):
    raw = text.encode('utf-8')
    prefix = raw[:max(0, min(int(offset), len(raw)))].decode('utf-8', errors='ignore')
    return {'line':prefix.count('\n'), 'character':len(prefix.rsplit('\n',1)[-1].encode('utf-16-le'))//2}


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
        self.initialized = False
        self.shutdown = False

    def send(self, **message):
        write_message(self.output, {'jsonrpc':'2.0', **message})

    def error(self, identifier, code, message):
        self.send(id=identifier, error={'code':code, 'message':message})

    def analyze(self):
        diagnostics = {}
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
                    result = subprocess.run([self.frontend,'diagnostics-bundle',manifest],capture_output=True,text=True,timeout=20)
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
                        content = self.documents[target].text if target in self.documents else target.read_bytes().decode('utf-8')
                    except (OSError, UnicodeError):
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
        versions = {document.uri:document.version for document in self.documents.values()}
        current = set(diagnostics) | set(versions)
        for uri in sorted(self.published | current):
            params = {'uri':uri,'diagnostics':diagnostics.get(uri,[])}
            if uri in versions:
                params['version'] = versions[uri]
            self.send(method='textDocument/publishDiagnostics',params=params)
        self.published = current

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
                self.send(id=identifier,result={'capabilities':{'positionEncoding':'utf-16','textDocumentSync':{'openClose':True,'change':2,'save':{'includeText':False}}},
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
