#!/usr/bin/env python3
"""Check typed AST projection identities in a private production compiler copy."""
import argparse, hashlib, json, os, re, shlex, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);p.add_argument('--sanitize',action='store_true');p.add_argument('--output',type=Path);args=p.parse_args()
def run(command,**kw):return subprocess.run(list(map(str,command)),cwd=ROOT,capture_output=True,text=True,timeout=180,**kw)
AUDIT='''extern "C" fn ProjectionRecord(function:*u8,role:i64,parent:i64,parent_kind:i64,parent_name:*u8,field_name:*u8,key:i64,field_type:i64,tag:i64,field_offset:i64,node_kind:i64,node_type:i64,value:i64,offset:i64,edge:i64,through:i64,valid:i64);
fn ProjectionAuditField(function:*Function,node:*Node,parent:i64,key:i64,role:i64){unsafe{
 let shape=Shape(parent);let field=cast[*Field](key);var member=shape.fields;
 while(member!=null && member!=field){member=member.next;}
 var valid=member!=null;var name=cast[*u8]("missing");var type:i64=0;var tag:i64=0;var offset:i64=0;
 if(member!=null){name=field.name;type=field.type;tag=field.tag;offset=field.offset;
  if(role==1){valid=valid && node.type==100000+type && node.value==offset;}
  if(role==2 || role==4){valid=valid && node.type==type && node.offset==offset;}
  if(role==3 || role==5){valid=valid && node.type==1 && node.value==tag;}
 }
 ProjectionRecord(function.name,role,parent,shape.kind,shape.name,name,key,type,tag,offset,node.kind,node.type,node.value,node.offset,PlaceProjectionKind(node),BoolInt(ReferenceThroughStored(node)),BoolInt(valid));
}}
fn ProjectionAuditNode(function:*Function,node:*Node){unsafe{
 if(node==null){return;}
 let edge=PlaceProjectionKind(node);
 if(edge==1){ProjectionAuditField(function,node,PlaceProjectionType(node),node.field_key,1);}
 if(edge==2 || edge==3 || edge==4){
  let parent=PlaceProjectionType(node);let shape=Shape(parent);var valid=true;
  if(edge==2){valid=(shape.kind==2 || shape.kind==3) && node.type==100000+shape.element;}
  if(edge==3 || edge==4){valid=node.type==100000+shape.element;}
  ProjectionRecord(function.name,0,parent,shape.kind,cast[*u8]("sequence"),cast[*u8]("none"),0,shape.element,0,0,node.kind,node.type,node.value,node.offset,edge,BoolInt(ReferenceThroughStored(node)),BoolInt(valid));
 }
 if(node.kind==23 && AggregateKind(node.type)==1){var item=node.a;while(item!=null){ProjectionAuditField(function,item,node.type,item.field_key,2);item=item.next;}}
 if(node.kind==23 && AggregateKind(node.type)==4){ProjectionAuditField(function,node.a,node.type,node.a.field_key,3);if(node.a.next!=null){ProjectionAuditField(function,node.a.next,node.type,node.a.next.field_key,4);}}
 if(node.kind==5 && node.op==259 && node.b!=null && node.b.field_key!=0){ProjectionAuditField(function,node.b,node.a.a.type-100000,node.b.field_key,5);}
 ProjectionAuditNode(function,node.a);ProjectionAuditNode(function,node.b);ProjectionAuditNode(function,node.c);ProjectionAuditNode(function,node.next);
}}
export "C" fn ProjectionAudit(){unsafe{
 let ctx=cast[*CompilerState](NativeCompilerState(i64(sizeof(CompilerState))));
 for(var i:i64=0;i<ctx.v_nfun;i=i+1){let function=&raw ctx.v_functions[i];let name=function.name;
  if(name!=null && StrLen(name)>=5 && name[0]==u8(65) && name[1]==u8(117) && name[2]==u8(100) && name[3]==u8(105) && name[4]==u8(116)){ProjectionAuditNode(function,function.body);}
 }
}}
'''
SHIM=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
void ProjectionRecord(const char *function,int64_t role,int64_t parent,int64_t parent_kind,const char *parent_name,const char *field_name,int64_t key,int64_t field_type,int64_t tag,int64_t field_offset,int64_t node_kind,int64_t node_type,int64_t value,int64_t offset,int64_t edge,int64_t through,int64_t valid){
 fprintf(stderr,"PROJECTION %s %lld %lld %lld %s %s %lld %lld %lld %lld %lld %lld %lld %lld %lld %lld %lld\n",function,(long long)role,(long long)parent,(long long)parent_kind,parent_name?parent_name:"sequence",field_name?field_name:"missing",(long long)key,(long long)field_type,(long long)tag,(long long)field_offset,(long long)node_kind,(long long)node_type,(long long)value,(long long)offset,(long long)edge,(long long)through,(long long)valid);
 if(!valid)abort();
}
'''
PROGRAM='''import "std/io";
struct Zero{left:[0]i64;right:[0]i64;}
struct Pair[T]{left:T;right:T;}
struct Outer{first:Pair[i64];second:Pair[i64];}
enum Choice{None;A(i64);B(i64);}
fn Pair.sum[T](self:&Pair[T])->i64{return i64((*self).left)+i64((*self).right);}
fn Pair.copy[T](self:&Pair[T])->Pair[T] borrows(self){return *self;}
fn AuditZero(){let z=Zero{left:[0]i64{},right:[0]i64{}};assert(len(z.left)==0);assert(len(z.right)==0);}
fn AuditEnum(){var c=Choice.A(1);c=Choice.B(2);match(c){Choice.None=>{}Choice.A(a)=>{assert(a==1);}Choice.B(b)=>{assert(b==2);}}c=Choice.None;}
fn AuditGenericGet[T](p:&Pair[T])->T borrows(p){return (*p).left;}
fn AuditGeneric(){var x=3;var y=4;let p=Pair[&i64]{left:&x,right:&y};assert(*AuditGenericGet[&i64](&p)==3);let q=Pair[i64]{left:5,right:6};assert(AuditGenericGet[i64](&q)==5);assert(q.copy().left==5);assert(q.sum()==11);}
fn AuditRef(p:&mut Outer){(*p).first.left=8;assert((*p).second.right==4);}
fn AuditOwner(){let p=new[Pair[i64]](Pair[i64]{left:1,right:2});(*p).left=3;assert((*p).right==2);}
fn AuditElements(){var a=[2]i64{1,2};a[0]=3;var s=a[:];s[1]=4;let r=&mut s;(*r)[0]=5;assert((*r)[1]==4);}
fn AuditMain(){AuditZero();AuditEnum();AuditGeneric();AuditOwner();AuditElements();var p=Outer{first:Pair[i64]{left:1,right:2},second:Pair[i64]{left:3,right:4}};AuditRef(&mut p);assert(p.first.left==8);io.println(42);}
fn main(){AuditMain();}
'''
with tempfile.TemporaryDirectory(prefix='cool typed projections ') as directory:
 tmp=Path(directory);parser=tmp/'parser.cool';source=(ROOT/'compiler/06-parser.cool').read_text();source,count=re.subn(r'\bfn ParseProgram\(', 'export "C" fn ParseProgram(',source);assert count==1;parser.write_text(source)
 adapter=tmp/'audit.cool';adapter.write_text(AUDIT);files=sorted((ROOT/'compiler').glob('*.cool'));manifest=tmp/'compiler.sources'
 manifest.write_text(''.join('__main\t'+str(parser if file.name=='06-parser.cool' else file)+'\n' for file in files)+'__main\t'+str(adapter)+'\n')
 frontend=args.frontend.resolve() if args.frontend else ROOT/'build/cool-compiler';env={**os.environ,'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
 ir=tmp/'compiler.ll';r=run([frontend,'llvm-bundle',manifest,ir],env=env);assert r.returncode==0,r;text=ir.read_text()
 wrapper=re.search(r'^define [^\n]*@ParseProgram\([^\n]*\) \{.*?^\}',text,re.M|re.S);assert wrapper
 symbols=re.findall(r'call i64 @(__cool_fn\d+)\(',wrapper.group());assert len(symbols)==1;symbol=symbols[0]
 text,count=re.subn(r'^define i64 @'+symbol+r'\(', 'define i64 @ProjectionOriginalParseProgram(',text,flags=re.M);assert count==1
 text+=f'\ndefine i64 @{symbol}() {{\nentry:\n %r = call i64 @ProjectionOriginalParseProgram()\n call void @ProjectionAudit()\n ret i64 %r\n}}\n'
 if args.sanitize:text='\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in text.splitlines())+'\n'
 ir.write_text(text);shim=tmp/'trace.c';shim.write_text(SHIM);traced=tmp/'traced';objects=['compiler-host.o','language-runtime.o'];digests={name:hashlib.sha256((ROOT/'build'/name).read_bytes()).hexdigest() for name in objects}
 for name in objects:(tmp/name).write_bytes((ROOT/'build'/name).read_bytes());assert hashlib.sha256((tmp/name).read_bytes()).hexdigest()==digests[name]
 flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if args.sanitize else ['-O2'];inputs=[tmp/name for name in objects]
 if args.sanitize:
  checked=tmp/'instrumented.ll';r=run(['clang','-Wno-override-module','-O1','-fsanitize=address','-S','-emit-llvm',ir,'-o',checked]);assert r.returncode==0,r
  assert '__asan_report_load' in checked.read_text() and '__asan_report_store' in checked.read_text();inputs=[ROOT/'compiler/host.c',ROOT/'language/runtime.c']
 r=run(['clang','-Wno-override-module',*flags,ir,shim,*inputs,'-lffi','-o',traced]);assert r.returncode==0,r
 file=tmp/'main.cool';file.write_text(PROGRAM);r=run([traced,'check',file],env=env);assert r.returncode==0 and r.stdout=='',r
 rows=[]
 for line in r.stderr.splitlines():
  parts=line.split();assert parts[0]=='PROJECTION' and len(parts)==18,line
  row=dict(zip(('function','role','parent','parent_kind','parent_name','field_name','key','field_type','tag','field_offset','node_kind','node_type','value','offset','edge','through','valid'),parts[1:]))
  for key in row:
   if key not in ('function','parent_name','field_name'):row[key]=int(row[key])
  assert row['valid']==1,row;rows.append(row)
 assert {row['edge'] for row in rows}>={1,2,3,4},rows
 # Independently declared identities: same byte offset must not merge members.
 for name,fields,offset in [('Zero',{'left','right'},0),('Choice',{'A','B'},8)]:
  selected=[row for row in rows if row['parent_name']==name and row['field_name'] in fields]
  assert {row['field_name'] for row in selected}==fields,(name,selected)
  keys={field:{row['key'] for row in selected if row['field_name']==field} for field in fields}
  assert all(len(value)==1 for value in keys.values()) and len(set.union(*keys.values()))==2,(name,keys)
  assert all(row['field_offset']==offset for row in selected),(name,selected)
 assert {row['role'] for row in rows if row['parent_name']=='Choice'}>={1,3,4,5},rows
 # Concrete generic layouts retain separate descriptor identities and types.
 pairs=[row for row in rows if row['parent_name']=='Pair' and row['field_name']=='left']
 assert len({row['parent'] for row in pairs})==2 and len({row['key'] for row in pairs})==2,pairs
 wrapper=tmp/'bootstrap';wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(ROOT/'build/coolc'))+' --run '+shlex.quote(str(ROOT/'build/language.BIN'))+' "$@"\n');wrapper.chmod(0o755)
 fronts=[ROOT/'build/cool-compiler',wrapper]
 if args.frontend:fronts.append(args.frontend.resolve())
 binary=tmp/'program'
 for front in fronts:
  runtime_env={**env,'COOL_FRONTEND':str(front)}
  for engine in ('tree','interp','jit','llvm','llvm-jit','O2'):
   if engine=='O2':
    r=run([ROOT/'tools/cool','build','--release',file,'-o',binary],env=runtime_env);assert r.returncode==0,r;r=run([binary],env=runtime_env)
   else:r=run([ROOT/'tools/cool','run','--backend',engine,file],env=runtime_env)
   assert (r.returncode,r.stdout,r.stderr)==(0,'42\n',''),(front,engine,r)
 # Retained field descriptors must stay valid after body/source replacement
 # and a failed signature that temporarily materializes a lazy layout.
 repl='struct Pair[T]{left:T;right:T;}\nfn AuditRead(p:&Pair[i64])->i64{return (*p).left;}\nvar p=Pair[i64]{left:3,right:4};\nAuditRead(&p)\nfn AuditRead(p:&Pair[i64])->i64{return (*p).right;}\nAuditRead(&p)\nstruct Lazy[T]{first:T;second:[2]T;}\nstruct Phantom[T]{}\nlet phantom=Phantom[Lazy[i64]]{};\nfn AuditRejected(p:Lazy[i64])->i64{return missing;}\nfn AuditGood(p:&Lazy[i64])->i64{return (*p).second[1];}\nvar value=Lazy[i64]{first:7,second:[2]i64{8,9}};\nAuditGood(&value)\n:quit\n'
 r=run([traced,'repl-quiet'],input=repl,env=env)
 assert r.returncode==0 and r.stdout=='3\n4\n9\n' and r.stderr.count('error:')==1,r
 assert 'unknown variable' in r.stderr and 'PROJECTION ' in r.stderr and all(line.startswith('PROJECTION ') or 'error:' in line for line in r.stderr.splitlines()),r
 report={'projection_records':len(rows),'records':rows,'compiler_source_sha256':{str(file.relative_to(ROOT)):hashlib.sha256(file.read_bytes()).hexdigest() for file in files},'artifact_sha256':digests,'private_ir_sha256':hashlib.sha256(ir.read_bytes()).hexdigest(),'sanitize':args.sanitize,'method':'Private production parser/compiler LLVM copy audits resolved declaration membership, field types/offsets, variant identities, projection parent types and stored traversal; independent equal-offset identity/generic instantiation checks. This preserves AST provenance inputs and does not certify nested stored loans.'}
 if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
 print(f'place projections: {len(rows)} typed field/element/referent/owner records, equal-offset fields/variants, generic descriptors; five engines + O2 on {len(fronts)} frontends'+(' and instrumented private AST audit' if args.sanitize else '')+' PASS')
