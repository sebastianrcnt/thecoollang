#!/usr/bin/env python3
"""Explicit raw addresses stay unsafe and preserve address/value semantics."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
POSITIVE = '''struct Pair { value:i64; }
fn main(){
 var x=3; var pair=Pair{value:5}; var items=[2]i64{7,9};
 let owner=new[i64](11);
 unsafe {
  let px=&raw x; *px=13; assert(x==13);
  let pf=&raw pair.value; *pf=17; assert(pair.value==17);
  let pa=&raw items[1]; *pa=19; assert(items[1]==19);
  let po=&raw *owner; *po=23; assert(*owner==23);
  assert((x & 3)==1); assert((x & (3))==1);
 }
}
'''
NEGATIVE = [
 ('fn main(){var x=1;let p=&raw x;}', 'requires unsafe'),
 ('fn main(){let x=1;unsafe{let p=&raw x;}}', 'mutable address'),
 ('fn main(){unsafe{let p=&raw 1;}}', 'mutable address'),
]


def run(command):
 return subprocess.run([str(x) for x in command], cwd=ROOT, capture_output=True, text=True, timeout=60)


with tempfile.TemporaryDirectory(prefix='cool-raw-address-') as directory:
 source=Path(directory)/'main.cool'
 source.write_text(POSITIVE)
 for front in ([ROOT/'build/cool-compiler'], [ROOT/'build/coolc','--run',ROOT/'build/language.BIN']):
  result=run([*front,'check',source]);assert result.returncode==0,result
 for backend in ('tree','interp','jit','llvm','llvm-jit'):
  result=run([ROOT/'tools/cool','run','--backend',backend,source])
  assert (result.returncode,result.stdout,result.stderr)==(0,'',''),result
 result=run([ROOT/'tools/cool','fmt',source]);assert result.returncode==0,result
 result=run([ROOT/'tools/cool','fmt','--check',source]);assert result.returncode==0,result
 result=run([ROOT/'tools/cool','check',source]);assert result.returncode==0,result
 for program, diagnostic in NEGATIVE:
  source.write_text(program)
  for front in ([ROOT/'build/cool-compiler'],[ROOT/'build/coolc','--run',ROOT/'build/language.BIN']):
   result=run([*front,'check',source])
   assert result.returncode==2 and diagnostic in result.stderr,result
print('raw addresses: both frontends, five engines, formatter and unsafe/mutability rejection PASS')
