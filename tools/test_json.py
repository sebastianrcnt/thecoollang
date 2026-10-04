#!/usr/bin/env python3
"""JSON parser/encoder against Python Decimal decoding, with malformed input and leaks."""
import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import random
import re
import subprocess
ROOT=Path(__file__).resolve().parents[1]
PROGRAM='''import j "std/json";import t "std/text";import r "std/result";import v "std/vector";import fs "std/fs";import "std/os";import "std/io";import "std/mem";import o "std/option";
fn label(kind:j.ErrorKind){match(kind){j.ErrorKind.Syntax=>{io.print("syntax");}j.ErrorKind.DepthLimit=>{io.print("depth");}j.ErrorKind.InvalidUtf8=>{io.print("utf8");}j.ErrorKind.ExpectedNumber=>{io.print("number");}}}
fn key(value:string)->t.Text{return r.value_or[t.Text,t.Utf8Error](t.from_literal(value),t.create());}
fn deep(count:i64)->own[j.Value]{if(count==0){return j.null_value();}let parent=j.array_value();j.array_push(&mut *parent,deep(count-1));return move parent;}
fn api(){
 let object=j.object_value();j.object_insert(&mut *object,key("minimum"),j.integer_value(-9223372036854775808));
 let name=key("minimum");assert(j.object_contains(&*object,&name));assert(j.object_len(&*object)==1);
 assert(t.equal(j.number_text(j.object_at(&*object,&name)),&name)==false);
 let array=j.array_value();j.array_push(&mut *array,j.boolean_value(true));j.array_push(&mut *array,j.string_value(key("한글🙂")));
 assert(j.array_len(&*array)==2);assert(j.as_bool(j.array_at(&*array,0)));assert(t.scalar_len(j.as_text(j.array_at(&*array,1)))==3);
 j.object_insert(&mut *object,key("array"),move array);
 let encoded=r.value_or[t.Text,j.ErrorKind](j.encode(&*object),t.create());
 let again=r.value_or[own[j.Value],j.ParseError](j.parse(&encoded),j.null_value());assert(j.object_len(&*again)==2);
 assert(!r.is_ok[own[j.Value],j.ParseError](j.number_value(key("true"))));
 assert(!r.is_ok[own[j.Value],j.ParseError](j.number_value(key("01"))));
 assert(r.is_ok[own[j.Value],j.ParseError](j.number_value(key("-0.000e+9999"))));
 let array_name=key("array");
 {let child=j.object_at_mut(&mut *object,&array_name);j.array_push(child,j.array_value());
  {let nested=j.array_at_mut(child,2);j.array_push(nested,j.integer_value(42));}
  let removed=o.value_or[own[j.Value]](j.array_pop(child),j.null_value());assert(j.array_len(&*removed)==1);
 }
 let names=j.object_keys(&*object);assert(v.len[t.Text](&names)==2);
 let removed=o.value_or[own[j.Value]](j.object_remove(&mut *object,&array_name),j.null_value());assert(j.array_len(&*removed)==2);
 assert(!o.is_some[own[j.Value]](j.object_remove(&mut *object,&array_name)));
 assert(j.object_len(&*object)==1);assert(t.equal(v.at[t.Text](&names,0),&array_name));
 let too_deep=deep(129);assert(!r.is_ok[t.Text,j.ErrorKind](j.encode(&*too_deep)));
}
fn main(){
 api();assert(mem.owner_count()==0);
 for(var i:usize=0;i<os.arg_count();i=i+2){
  {
   let bytes=r.value_or[v.Vector[u8],i32](fs.read(os.arg(i)),v.create[u8]());
   match(j.parse_bytes(move bytes)){
    r.Result[own[j.Value],j.ParseError].Ok(value)=>{
     let out=r.value_or[t.Text,j.ErrorKind](j.encode(&*value),t.create());
     assert(r.is_ok[usize,i32](fs.write(os.arg(i+1),t.as_bytes(&out))));io.println("ok");
    }
    r.Result[own[j.Value],j.ParseError].Err(error)=>{io.print("error:");label(error.kind);io.print(":");io.println(error.offset);}
   }
  }
  assert(mem.owner_count()==0);
 }
}
'''

def decoded(data):
 def reject(value):raise ValueError(value)
 return json.loads(data.decode('utf-8'),parse_int=Decimal,parse_float=Decimal,parse_constant=reject)

def normalized(value):
 if value is None:return ('null',)
 if isinstance(value,bool):return ('bool',value)
 if isinstance(value,Decimal):return ('number',value)
 if isinstance(value,str):return ('string',value)
 if isinstance(value,list):return ('array',tuple(normalized(x) for x in value))
 return ('object',tuple(sorted((k,normalized(v)) for k,v in value.items())))

def corpus():
 valid=[b'null',b'true',b'false',b'0',b'-0',b'1234567890123456789012345678901234567890',b'1e9999',b'-0.123e+4',
        b' [ 1,2,3 ] ',b'{}',b'[]',b'"\\u0000\\b\\f\\n\\r\\t\\\\\\\"\\/"',b'"\\ud83d\\ude42"',
        b'{"duplicate":{"old":[1,2]},"duplicate":[true,null]}',b'{"\\u0000key":0,"":1}',
        ('["한글","🙂","e\\u0301"]').encode(),b'['*128+b'0'+b']'*128,json.dumps(list(range(1500))).encode()]
 rng=random.Random(20261005)
 def value(depth):
  choices=6 if depth<4 else 4
  choice=rng.randrange(choices)
  if choice==0:return None
  if choice==1:return bool(rng.randrange(2))
  if choice==2:return rng.randrange(-10**25,10**25)
  if choice==3:return ''.join(rng.choice(['a','"','\\','\n','\0','한','🙂','é']) for _ in range(rng.randrange(30)))
  if choice==4:return [value(depth+1) for _ in range(rng.randrange(5))]
  return {str(i)+rng.choice(['','한','🙂','\0']):value(depth+1) for i in range(rng.randrange(5))}
 valid += [json.dumps(value(0),ensure_ascii=bool(i%2),separators=(',',':')).encode() for i in range(50)]
 invalid=[(b'', 'syntax',0),(b' \n\t','syntax',3),(b'trux','syntax',3),(b'null true','syntax',5),
          (b'[1,]','syntax',3),(b'{"a" 1}','syntax',5),(b'"a','syntax',2),
          (b'['*129+b'0'+b']'*129,'depth',129),(b'\xff','utf8',0),(b'"\xc2','utf8',2)]
 for data in [b'01',b'-01',b'+1',b'.1',b'1.',b'1e',b'1e+',b'NaN',b'Infinity',b'--1',b'truee',b'[',b'{',b'[,]',
              b'{"a":}',b'{"a":1,}',b'{1:2}',b'"\\x"',b'"\0"',b'"\n"',b'"\\ud800"',b'"\\udc00"',
              b'"\\ud800\\u0041"',b'"\\uZZZZ"',b'/*x*/null',b'\xef\xbb\xbfnull','\u00a0null'.encode()]:
  invalid.append((data,'syntax',None))
 return [(data,True,None,None) for data in valid]+[(data,False,kind,offset) for data,kind,offset in invalid]


def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sanitize',action='store_true');args=parser.parse_args()
 directory=ROOT/'build/json-tests';directory.mkdir(parents=True,exist_ok=True)
 source=directory/'main.cool';source.write_text(PROGRAM);cases=corpus();paths=[]
 for i,(data,_,_,_) in enumerate(cases):
  input=directory/f'input-{i}.json';output=directory/f'output-{i}.json';input.write_bytes(data);output.unlink(missing_ok=True);paths += [input,output]
 def validate(p):
  assert p.returncode==0 and not p.stderr,(p.returncode,p.stdout,p.stderr)
  lines=p.stdout.splitlines();assert len(lines)==len(cases),(len(lines),p)
  for i,((data,valid,kind,offset),line) in enumerate(zip(cases,lines)):
   if valid:
    assert line=='ok',(data,line)
    output=paths[2*i+1].read_bytes();assert normalized(decoded(output))==normalized(decoded(data)),(data,output)
    if re.fullmatch(rb'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?',data):assert output==data,(data,output)
    parsed=json.loads(output,parse_int=str,parse_float=str);assert not isinstance(parsed,dict) or list(parsed)==sorted(parsed,key=lambda k:k.encode())
   else:
    assert line.startswith('error:'+kind+':'),(data,line)
    actual=int(line.rsplit(':',1)[1]);assert 0<=actual<=len(data),(data,line)
    if offset is not None:assert actual==offset,(data,line)
    assert not paths[2*i+1].exists(),data
 def run(command):
  return subprocess.run([str(x) for x in command],cwd=ROOT,capture_output=True,text=True,timeout=180,env={**os.environ,'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'})
 for engine in ('tree','interp','jit','llvm','llvm-jit'):
  validate(run([ROOT/'tools/cool','run','--backend',engine,source,'--',*paths]))
  print('JSON '+engine+' PASS',flush=True)
 binary=directory/'native';p=run([ROOT/'tools/cool','build','--release',source,'-o',binary]);assert p.returncode==0,p;validate(run([binary,*paths]))
 if args.sanitize:
  ir=directory/'json.ll';instrumented=directory/'json-asan.ll';p=run([ROOT/'tools/cool','emit-ir',source,'-o',ir]);assert p.returncode==0,p
  ir.write_text('\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in ir.read_text().splitlines())+'\n')
  p=run(['clang','-Wno-override-module','-O1','-fsanitize=address','-S','-emit-llvm',ir,'-o',instrumented]);assert p.returncode==0,p;assert '__asan_report_load' in instrumented.read_text()
  p=run(['clang','-Wno-override-module','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',ir,ROOT/'language/runtime.c','-o',binary]);assert p.returncode==0,p;validate(run([binary,*paths]))
 negative=directory/'negative.cool'
 prelude=PROGRAM.split('fn main(){',1)[0]
 for body in (
  'let child=j.array_at(&*array,0);j.array_pop(&mut *array);',
  'let child=j.array_at_mut(&mut *array,0);j.array_len(&*array);',
  'let child=j.array_at(&*array,0);let moved=move array;',
  'let child=j.object_at(&*object,&name);j.object_remove(&mut *object,&name);',
  'let child=j.object_at_mut(&mut *object,&name);j.object_insert(&mut *object,key("one"),j.null_value());',
 ):
  negative.write_text(prelude+'fn main(){let array=j.array_value();j.array_push(&mut *array,j.null_value());let object=j.object_value();let name=key("one");j.object_insert(&mut *object,key("one"),j.null_value());'+body+'}')
  p=run([ROOT/'tools/cool','check',negative]);assert p.returncode==2 and 'conflicts' in p.stderr,(body,p.stderr)
 print(f'JSON: {len(cases)} oracle/error cases, exact number lexemes, Unicode/NUL, duplicate keys, depth limits, public builders and zero leaked owners; O2'+(' + ASan/UBSan' if args.sanitize else '')+' PASS')


if __name__=='__main__':main()
