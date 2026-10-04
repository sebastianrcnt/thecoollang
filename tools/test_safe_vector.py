#!/usr/bin/env python3
"""Public owning-vector APIs must be usable without unsafe and retain their loans."""
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
PROGRAM='''import v "std/vector";import o "std/option";import "std/io";import "std/mem";import fs "std/fs";import r "std/result";import "std/os";
fn main(){
 {
  var values=v.create[own[i64]]();
  for(var i=0;i<80;i=i+1){v.append[own[i64]](&mut values,new[i64](i));}
  assert(v.len[own[i64]](&values)==80);
  {let value=v.at[own[i64]](&values,40);assert(**value==40);}
  {let value=v.at_mut[own[i64]](&mut values,40);*value=new[i64](99);}
  assert(**v.at[own[i64]](&values,40)==99);
  {let value=o.value_or[own[i64]](v.pop[own[i64]](&mut values),new[i64](-1));assert(*value==79);}
  v.clear[own[i64]](&mut values);assert(v.len[own[i64]](&values)==0);
  v.append[own[i64]](&mut values,new[i64](123));
  let transferred=move values;assert(**v.at[own[i64]](&transferred,0)==123);
 }
 assert(mem.owner_count()==0);
 {var bytes=v.create[u8]();v.append[u8](&mut bytes,65);v.append[u8](&mut bytes,0);v.append[u8](&mut bytes,255);
  assert(r.is_ok[usize,i32](fs.write(os.arg(0),&bytes)));
  let read=r.value_or[v.Vector[u8],i32](fs.read(os.arg(0)),v.create[u8]());
  assert(v.len[u8](&read)==3);assert(*v.at[u8](&read,2)==255);
 }
 assert(mem.owner_count()==0);io.println(123);
}
'''
NEGATIVE=[
 'let item=v.at[i64](&values,0);v.clear[i64](&mut values);',
 'let item=v.at[i64](&values,0);let moved=move values;',
 'let item=v.at_mut[i64](&mut values,0);v.append[i64](&mut values,2);',
 'let item=v.at_mut[i64](&mut values,0);let other=v.at[i64](&values,0);',
 'let item=v.at[i64](&values,0);*item=2;',
 '*v.at_mut[i64](&mut values,0)=clear(&mut values);',
]
with tempfile.TemporaryDirectory(prefix='cool-safe-vector-') as tmp:
 path=Path(tmp)/'main.cool';path.write_text(PROGRAM)
 for mode in ('tree','interp','jit','llvm','llvm-jit'):
  p=subprocess.run([ROOT/'tools/cool','run','--backend',mode,path,'--',Path(tmp)/'bytes.bin'],capture_output=True,text=True,timeout=90)
  assert (p.returncode,p.stdout,p.stderr)==(0,'123\n',''),(mode,p)
  assert (Path(tmp)/'bytes.bin').read_bytes()==bytes([65,0,255])
 for body in NEGATIVE:
  path.write_text('import v "std/vector";fn clear(values:&mut v.Vector[i64])->i64{v.clear[i64](values);return 2;}fn main(){var values=v.create[i64]();v.append[i64](&mut values,1);'+body+'}')
  p=subprocess.run([ROOT/'tools/cool','check',path],capture_output=True,text=True,timeout=60)
  assert p.returncode==2 and ('conflicts' in p.stderr or 'immutable' in p.stderr),(body,p)
print('safe vector: no-unsafe owning collection and binary-file program across five engines; live element loans reject removal, growth, move and mutation PASS')
