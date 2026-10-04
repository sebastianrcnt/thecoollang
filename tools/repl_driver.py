"""Resolve frontend-requested package graphs over a private framed channel."""
import hashlib
import os
from pathlib import Path
import struct
import socket
import shutil
import subprocess
import threading
from modules import validate_path


def exact(stream, size):
    chunks=[]
    while size:
        chunk=stream.read(size)
        if not chunk:raise EOFError
        chunks.append(chunk);size-=len(chunk)
    return b''.join(chunks)


def run_repl(frontend, prompt, work, resolve):
    parent,child=socket.socketpair()
    def serve():
        try:
            with parent, parent.makefile('rwb',buffering=0) as channel:
                requests=responses=channel
                while True:
                    try:
                        size=struct.unpack('!I',exact(requests,4))[0]
                        if not 0<size<=4096:raise ValueError('invalid package request length')
                        package=exact(requests,size).decode('utf-8')
                        validate_path(package)
                        # The frontend consumes the complete previous response
                        # before asking again; token storage no longer needs its
                        # source files. Keep only one request's disk snapshots.
                        snapshots=work/'snapshots'
                        if snapshots.exists():shutil.rmtree(snapshots)
                        files=resolve(package)
                        packages={}
                        for identity,source in files:packages.setdefault(identity,[]).append((source,source.read_bytes()))
                        rows=[]
                        for identity,sources in packages.items():
                            digest=hashlib.sha256()
                            for source,data in sources:
                                name=source.name.encode()
                                digest.update(struct.pack('!Q',len(name))+name+struct.pack('!Q',len(data))+data)
                            fingerprint=digest.hexdigest()
                            folder=work/'snapshots'/hashlib.sha256((identity+'\0'+fingerprint).encode()).hexdigest()
                            folder.mkdir(parents=True,exist_ok=True)
                            for source,data in sources:
                                snapshot=folder/source.name
                                snapshot.write_bytes(data)
                                rows.append(f'{identity}\t{fingerprint}\t{source}\t{snapshot}\n')
                        manifest=work/'resolved.list';manifest.write_text(''.join(rows))
                        payload=('ok\t'+str(manifest)).encode()
                    except EOFError:return
                    except (ValueError,OSError,UnicodeError,subprocess.SubprocessError) as error:
                        message=error.stderr if isinstance(error,subprocess.CalledProcessError) and error.stderr else str(error)
                        payload=('error\t'+message).encode('utf-8',errors='replace')[:60000].decode('utf-8',errors='replace').encode('utf-8')
                    frame=memoryview(struct.pack('!I',len(payload))+payload)
                    while frame:
                        count=responses.write(frame)
                        if not count:raise BrokenPipeError
                        frame=frame[count:]
        except (BrokenPipeError,OSError):
            return
    thread=threading.Thread(target=serve,name='cool-package-resolver',daemon=True)
    process=None
    try:
        descriptor=child.fileno()
        process=subprocess.Popen([frontend,'repl' if prompt else 'repl-quiet'],pass_fds=(descriptor,),env={**os.environ,'COOL_REPL_REQUEST_FD':str(descriptor),'COOL_REPL_RESPONSE_FD':str(descriptor)})
        child.close()
        thread.start()
        code=process.wait()
        if code:raise subprocess.CalledProcessError(code,process.args)
    finally:
        child.close()
        if process is None:
            parent.close()
        elif thread.ident is not None:
            thread.join(timeout=2)
