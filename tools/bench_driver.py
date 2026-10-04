#!/usr/bin/env python3
"""Measure package-driver latency with cold, warm and one-file-changed scan caches."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--driver',type=Path,default=ROOT/'tools/cool');parser.add_argument('--files',type=int,default=256)
parser.add_argument('--repeats',type=int,default=5);parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
if args.files<1 or args.repeats<1:parser.error('files and repeats must be positive')
results={}
with tempfile.TemporaryDirectory(prefix='cool-driver-benchmark-') as tmp:
 tmp=Path(tmp);project=tmp/'app';project.mkdir();cache=tmp/'cache'
 for i in range(args.files):
  (project/f'part-{i:04}.cool').write_text(f'package main;fn f_{i}()->i64{{var value=0;for(var j=0;j<20;j=j+1){{value=value+j;}}return value+{i};}}')
 (project/'main.cool').write_text('package main;fn main(){assert(f_0()==190);}')
 env={**os.environ,'COOL_FRONTEND':str(ROOT/'build/cool-compiler'),'COOL_CACHE':str(cache)}
 command=[str(args.driver.resolve()),'check',str(project)]
 def measure(name,setup=None):
  samples=[]
  for i in range(args.repeats):
   if setup:setup(i)
   start=time.perf_counter_ns();p=subprocess.run(command,env=env,capture_output=True,text=True,timeout=60)
   samples.append((time.perf_counter_ns()-start)/1e6);assert p.returncode==0 and not p.stderr and not p.stdout,p
  results[name]={'median_ms':round(statistics.median(samples),3),'samples_ms':samples}
 measure('cold_metadata',lambda _:shutil.rmtree(cache/'scan',ignore_errors=True))
 measure('warm_metadata')
 changed=project/'part-0000.cool';original=changed.read_text()
 measure('one_file_changed',lambda i:changed.write_text(original.replace('return value+0;',f'return value+{10000+i};')))
report={'platform':platform.platform(),'python':sys.version.split()[0],'source_files':args.files+1,
 'repeats':args.repeats,'driver':str(args.driver.resolve()),
 'note':'Synthetic directory package: integer loops in each file. Includes process startup, metadata and frontend check; explicit COOL_FRONTEND excludes make. Setup excluded. Changed file is rechecked, not incremental code generation.',
 'results':results}
args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
