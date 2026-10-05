#!/usr/bin/env python3
"""Compare two vector implementations on identical standalone byte workloads."""
import argparse,hashlib,json,statistics,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--before-ref',required=True);p.add_argument('--count',type=int,default=500000);p.add_argument('--samples',type=int,default=7);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
assert args.count>0 and args.samples>0
project=ROOT/'build/vector-storage-benchmark';project.mkdir(exist_ok=True);(project/'cool.mod').write_text('module example.test/vectorcost\n')
r=subprocess.run(['git','show',args.before_ref+':stdlib/vector/vector.cool'],cwd=ROOT,capture_output=True,text=True,check=True);before=r.stdout
after=(ROOT/'stdlib/vector/vector.cool').read_text();expected=sum(i%251 for i in range(args.count));rows=[]
for name,body in [('before',before),('after',after)]:
 directory=project/name;directory.mkdir(exist_ok=True)
 helper='pub fn chunk_size[T]()->usize{if(sizeof(T)==1){return usize(sizeof(SmallChunk));}return usize(sizeof(BigChunk[T]));}' if 'struct SmallChunk' in body else 'pub fn chunk_size[T]()->usize{return usize(sizeof(Chunk[T]));}'
 (directory/'vector.cool').write_text(body.replace('package vector;','package '+name+';',1)+'\n'+helper+'\n')
 app=project/(name+'app');app.mkdir(exist_ok=True)
 source='package main;import v "example.test/vectorcost/'+name+'";import "std/io";fn main(){var bytes=v.create[u8]();for(var i=0;i<'+str(args.count)+';i=i+1){bytes.append(u8(i%251));}var sum:i64=0;unsafe{var it=v.cursor[u8](&bytes);for(var i=0;i<'+str(args.count)+';i=i+1){sum=sum+i64(*v.next[u8](&raw it));}}assert(sum=='+str(expected)+');bytes.clear();io.println(v.chunk_size[u8]());}'
 (app/'main.cool').write_text(source);binary=project/(name+'-program')
 r=subprocess.run([ROOT/'tools/cool','build','--release',app,'-o',binary],cwd=ROOT,capture_output=True,text=True);assert r.returncode==0,r
 rows.append(dict(name=name,binary=str(binary),binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),vector_sha256=hashlib.sha256(body.encode()).hexdigest(),source=source,samples_ms=[]))
def execute(row,record):
 start=time.perf_counter_ns();r=subprocess.run([row['binary']],capture_output=True,text=True);duration=(time.perf_counter_ns()-start)/1e6
 assert r.returncode==0 and not r.stderr,r
 row['chunk_bytes']=int(r.stdout)
 if record:row['samples_ms'].append(duration)
for row in rows:execute(row,False)
for sample in range(args.samples):
 for row in (rows if sample%2==0 else list(reversed(rows))):execute(row,True)
for row in rows:row['median_ms']=statistics.median(row['samples_ms'])
report=dict(before_ref=args.before_ref,count=args.count,expected_sum=expected,compiler_sha256=hashlib.sha256((ROOT/'build/cool-compiler').read_bytes()).hexdigest(),rows=rows,method='LLVM release O2 standalone native processes. One warm-up each, then alternating order. Duration includes process launch, append, raw cursor traversal and explicit clear. Chunk bytes are sizeof selected private byte chunk, excluding owner/runtime overhead; no RSS claim.')
args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
for row in rows:print(row['name'],row['chunk_bytes'],'chunk bytes;',round(row['median_ms'],3),'ms median')
