#!/usr/bin/env python3
"""Owned UTF-8 text against Python's independent strict decoder and scalar oracle."""
from pathlib import Path
import random
import argparse
import os
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
BASE='''import text "std/text";import v "std/vector";import r "std/result";import "std/mem";import "std/io";import "std/os";import fs "std/fs";
fn basics(){
 var value=r.value_or[text.Text,text.Utf8Error](text.from_literal("한글🙂"),text.create());
 assert(text.byte_len(&value)==10);assert(text.scalar_len(&value)==3);
 assert(text.scalar_at(&value,0)==54620);assert(text.scalar_at(&value,2)==128578);
 let copy=text.clone(&value);assert(text.equal(&copy,&value));
 assert(text.compare(&copy,&value)==0);
 let prefix=r.value_or[text.Text,text.Utf8Error](text.from_literal("한글"),text.create());
 let suffix=r.value_or[text.Text,text.Utf8Error](text.from_literal("🙂"),text.create());
 let empty=text.create();
 assert(text.starts_with(&value,&prefix));assert(text.ends_with(&value,&suffix));
 assert(text.starts_with(&value,&empty));assert(text.ends_with(&value,&empty));
 assert(!text.starts_with(&prefix,&value));assert(!text.ends_with(&suffix,&value));
 assert(text.compare(&prefix,&value)<0);assert(text.compare(&value,&prefix)>0);
 assert(text.compare(&prefix,&suffix)<0);
 var big=text.create();
 for(var i=0;i<3000;i=i+1){assert(text.append_scalar(&mut big,128578));}
 assert(text.byte_len(&big)==12000);assert(text.scalar_len(&big)==3000);
 assert(text.scalar_at(&big,2999)==128578);text.clear(&mut big);
 assert(text.byte_len(&big)==0);
 assert(r.is_ok[usize,text.Utf8Error](text.append_literal(&mut value,"abc")));
 assert(text.scalar_len(&value)==6);assert(!text.equal(&copy,&value));
 assert(text.append_scalar(&mut value,0));assert(text.append_scalar(&mut value,1114111));
 assert(!text.append_scalar(&mut value,55296));assert(!text.append_scalar(&mut value,1114112));
 assert(text.scalar_len(&value)==8);assert(text.scalar_at(&value,6)==0);assert(text.scalar_at(&value,7)==1114111);
 assert(r.is_ok[usize,i32](fs.write(os.arg(0),text.as_bytes(&value))));
 let bytes=r.value_or[v.Vector[u8],i32](fs.read(os.arg(0)),v.create[u8]());
 let read=r.value_or[text.Text,text.Utf8Error](text.from_bytes(move bytes),text.create());
 assert(text.equal(&value,&read));
 text.clear(&mut value);assert(text.byte_len(&value)==0);assert(text.scalar_len(&value)==0);
 text.append(&mut value,&copy);assert(text.equal(&value,&copy));
 let transferred=text.into_bytes(move value);assert(v.len[u8](&transferred)==10);
}
fn error_at(bytes:v.Vector[u8],truncated:bool)->usize{
 match(text.from_bytes(move bytes)){
  r.Result[text.Text,text.Utf8Error].Ok(value)=>{assert(false);return 999;}
  r.Result[text.Text,text.Utf8Error].Err(error)=>{
   match(error){
    text.Utf8Error.Invalid(index)=>{assert(!truncated);return index;}
    text.Utf8Error.Truncated(index)=>{assert(truncated);return index;}
   }
  }
 }
}
'''


def cases():
    fixed=[b'',b'ASCII',b'\0',b'\x7f',b'\xc2\x80',b'\xdf\xbf',b'\xe0\xa0\x80',b'\xed\x9f\xbf',
           b'\xee\x80\x80',b'\xef\xbf\xbf',b'\xf0\x90\x80\x80',b'\xf4\x8f\xbf\xbf',
           b'\x80',b'\xc0\x80',b'\xc1\xbf',b'\xc2',b'\xe0\x9f\xbf',b'\xed\xa0\x80',
           b'\xf0\x8f\xbf\xbf',b'\xf4\x90\x80\x80',b'\xf5\x80\x80\x80',b'\xff',
           b'\xe2\x82',b'\xf0\x9f\x99',b'\xe2A\x80',b'a'*31+'🙂한글'.encode(),
           ('e\u0301👩\u200d💻\0'*12).encode()]
    rng=random.Random(20261005)
    for _ in range(50):
        points=[rng.randrange(0x110000) for _ in range(rng.randrange(1,25))]
        fixed.append(''.join(chr(p) for p in points if not 0xd800<=p<=0xdfff).encode())
    for _ in range(50):
        fixed.append(bytes(rng.randrange(256) for _ in range(rng.randrange(1,25))))
    return fixed


def generate():
    functions=[]
    for i,data in enumerate(cases()):
        try:
            decoded=data.decode('utf-8',errors='strict')
        except UnicodeDecodeError:
            decoded=None
        lines=[f'fn case_{i}(){{var bytes=v.create[u8]();']
        lines += [f'v.append[u8](&mut bytes,{byte});' for byte in data]
        lines += ['match(text.from_bytes(move bytes)){','r.Result[text.Text,text.Utf8Error].Ok(value)=>{']
        if decoded is None:
            lines += ['assert(false);']
        else:
            lines += [f'assert(text.byte_len(&value)=={len(data)});assert(text.scalar_len(&value)=={len(decoded)});']
            lines += [f'assert(text.scalar_at(&value,{index})=={ord(char)});' for index,char in enumerate(decoded)]
            lines += ['let copy=text.clone(&value);assert(text.equal(&copy,&value));']
        lines += ['}','r.Result[text.Text,text.Utf8Error].Err(error)=>{assert('+('true' if decoded is None else 'false')+');}','}}']
        functions.append('\n'.join(lines))
    main=['fn main(){basics();assert(mem.owner_count()==0);']
    main += [f'case_{i}();assert(mem.owner_count()==0);' for i in range(len(functions))]
    for data,truncated,index in [(b'\xc2',True,1),(b'abc\xf0\x9f',True,5),(b'\xed\xa0\x80',False,1),(b'A\x80',False,1)]:
        main += ['{var bytes=v.create[u8]();']+[f'v.append[u8](&mut bytes,{b});' for b in data]
        main += [f'assert(error_at(move bytes,{str(truncated).lower()})=={index});'+'}assert(mem.owner_count()==0);']
    main += ['io.println(127);}']
    return BASE+'\n'.join(functions+main)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--sanitize",action="store_true");args=parser.parse_args()
    directory=ROOT/'build/text-tests';directory.mkdir(parents=True,exist_ok=True)
    source=directory/'generated.cool';source.write_text(generate())
    def run(args,expected=None):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,capture_output=True,text=True,timeout=120,env={**os.environ,"ASAN_OPTIONS":"halt_on_error=1","UBSAN_OPTIONS":"halt_on_error=1:print_stacktrace=1"})
        assert p.returncode==0 and p.stderr=='' and (expected is None or p.stdout==expected),(args,p)
    for backend in ('tree','interp','jit','llvm','llvm-jit'):
        output=directory/f'{backend}.bin'
        run([ROOT/'tools/cool','run','--backend',backend,source,'--',output],'127\n')
        assert output.read_bytes()=='한글🙂abc\0\U0010ffff'.encode()
    binary=directory/'native'
    run([ROOT/'tools/cool','build','--release',source,'-o',binary])
    run([binary,directory/'native.bin'],'127\n')
    if args.sanitize:
        ir=directory/'text.ll';instrumented=directory/'text-asan.ll'
        run([ROOT/'tools/cool','emit-ir',source,'-o',ir])
        ir.write_text('\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in ir.read_text().splitlines())+'\n')
        run(['clang','-Wno-override-module','-O1','-fsanitize=address','-S','-emit-llvm',ir,'-o',instrumented])
        assert '__asan_report_load' in instrumented.read_text()
        run(['clang','-Wno-override-module','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',ir,ROOT/'language/runtime.c','-o',binary])
        run([binary,directory/'sanitized.bin'],'127\n')
    with tempfile.TemporaryDirectory(prefix='cool-text-negative-') as tmp:
        path=Path(tmp)/'main.cool'
        for body in ('let bytes=text.as_bytes(&value);text.clear(&mut value);',
                     'let copy=value;',
                     'text.append(&mut value,&value);'):
            path.write_text('import text "std/text";fn main(){var value=text.create();'+body+'}')
            p=subprocess.run([ROOT/'tools/cool','check',path],capture_output=True,text=True,timeout=30)
            assert p.returncode==2 and ('conflicts' in p.stderr or 'explicit move' in p.stderr),(body,p)
    print('owned text: 127 strict UTF-8 oracle cases, scalar access, ordering/prefix/suffix, 12 KiB growth, NUL files and zero leaked owners across five engines + O2' + (' + ASan/UBSan' if args.sanitize else '') + ' PASS')


if __name__=='__main__':main()
