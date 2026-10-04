#!/usr/bin/env python3
"""Public map API, multiple value layouts, binary text keys and borrowing."""
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
PRELUDE='''import m "std/map";import t "std/text";import r "std/result";import o "std/option";import v "std/vector";import "std/mem";import "std/io";
fn key(value:string)->t.Text{return r.value_or[t.Text,t.Utf8Error](t.from_literal(value),t.create());}
'''
PROGRAM=PRELUDE+'''fn main(){
 {
  var bytes=m.create[u8]();let search=key("one");
  assert(!o.is_some[u8](m.insert[u8](&mut bytes,key("one"),255)));
  assert(o.value_or[u8](m.insert[u8](&mut bytes,key("one"),7),0)==255);
  *m.at_mut[u8](&mut bytes,&search)=9;assert(*m.at[u8](&bytes,&search)==9);
  assert(o.value_or[u8](m.remove[u8](&mut bytes,&search),0)==9);
  assert(!o.is_some[u8](m.remove[u8](&mut bytes,&search)));assert(m.len[u8](&bytes)==0);
  var floats=m.create[f32]();m.insert[f32](&mut floats,key("one"),f32(1.25));assert(*m.at[f32](&floats,&search)==f32(1.25));
 }
 assert(mem.owner_count()==0);
 {
  var values=m.create[t.Text]();let search=key("one");
  m.insert[t.Text](&mut values,key("one"),key("한글🙂"));
  let old=o.value_or[t.Text](m.insert[t.Text](&mut values,key("one"),key("new")),t.create());
  assert(t.scalar_len(&old)==3);assert(t.scalar_len(m.at[t.Text](&values,&search))==3);
  var nul=t.create();assert(t.append_scalar(&mut nul,0));
  m.insert[t.Text](&mut values,t.clone(&nul),key("nul"));
  m.insert[t.Text](&mut values,t.create(),key("empty"));assert(m.len[t.Text](&values)==3);
  let names=m.keys[t.Text](&values);m.clear[t.Text](&mut values);
  assert(v.len[t.Text](&names)==3);assert(t.byte_len(v.at[t.Text](&names,0))==0);
  assert(t.equal(v.at[t.Text](&names,1),&nul));assert(t.equal(v.at[t.Text](&names,2),&search));
 }
 assert(mem.owner_count()==0);io.println(42);
}
'''
NEGATIVE=[
 'let value=m.at[i64](&map,&search);m.remove[i64](&mut map,&search);',
 'let value=m.at[i64](&map,&search);m.insert[i64](&mut map,key("two"),2);',
 'let value=m.at[i64](&map,&search);let moved=move map;',
 'let value=m.at_mut[i64](&mut map,&search);let other=m.at[i64](&map,&search);',
 '*m.at[i64](&map,&search)=3;',
 '*m.at_mut[i64](&mut map,&search)=invalidate(&mut map);',
]
with tempfile.TemporaryDirectory(prefix='cool-map-api-') as tmp:
 path=Path(tmp)/'main.cool';path.write_text(PROGRAM)
 for mode in ('tree','interp','jit','llvm','llvm-jit'):
  p=subprocess.run([ROOT/'tools/cool','run','--backend',mode,path],capture_output=True,text=True,timeout=90)
  assert (p.returncode,p.stdout,p.stderr)==(0,'42\n',''),(mode,p)
 for body in NEGATIVE:
  path.write_text(PRELUDE+'fn invalidate(map:&mut m.Map[i64])->i64{m.clear[i64](map);return 9;}fn main(){var map=m.create[i64]();m.insert[i64](&mut map,key("one"),1);let search=key("one");'+body+'}')
  p=subprocess.run([ROOT/'tools/cool','check',path],capture_output=True,text=True,timeout=60)
  assert p.returncode==2 and ('conflicts' in p.stderr or 'immutable' in p.stderr),(body,p)
 path.write_text(PRELUDE+'fn main(){let map=m.create[i64]();let search=key("missing");m.at[i64](&map,&search);}')
 for mode in ('tree','interp','jit','llvm','llvm-jit'):
  p=subprocess.run([ROOT/'tools/cool','run','--backend',mode,path],capture_output=True,text=True,timeout=90)
  assert p.returncode!=0 and 'assertion failed' in p.stderr,(mode,p)
print('map API: u8/f32/owned text, NUL and empty keys, independent sorted snapshots, missing-key traps and loan conflicts PASS')
