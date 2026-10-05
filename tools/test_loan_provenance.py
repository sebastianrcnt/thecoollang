#!/usr/bin/env python3
"""Audit production loan metadata without changing permission decisions."""
import argparse,hashlib,json,os,re,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path);p.add_argument('--sanitize',action='store_true');p.add_argument('--output',type=Path);args=p.parse_args()
def run(cmd,**kw):return subprocess.run(list(map(str,cmd)),cwd=ROOT,capture_output=True,text=True,timeout=180,**kw)
AUDIT='''extern "C" fn LoanRecord(stage:i64,holder:*u8,root:*u8,field:*u8,reading:i64,writing:i64,valid:i64);
fn LoanAudit(check:*ReferenceCheck,node:*Node){unsafe{
 let local=node.local_ref;if(local==null || local.name==null){return;}
 if(Eq(local.name,cast[*u8]("picked"))!=0 || Eq(local.name,cast[*u8]("picked_copy"))!=0 || Eq(local.name,cast[*u8]("uncertain"))!=0 || Eq(local.name,cast[*u8]("indexed"))!=0){
  var loan=check.loans;while(loan!=null){if(loan.holder==local && loan.root!=null){
   let valid=loan.provenance_type==local.type && (loan.provenance==null || (loan.provenance.graph==check.graph && loan.provenance.type==local.type));
   LoanRecord(node.kind,local.name,loan.root.name,cast[*u8]("value"),BoolInt(ReferenceLoanQuery(loan,null,loan.root,false)),loan.provenance_known,BoolInt(valid));
  }loan=loan.next;}return;
 }
 if(AggregateKind(local.type)!=1){return;}
 if(Eq(local.name,cast[*u8]("tracked"))==0 && Eq(local.name,cast[*u8]("copied"))==0 && Eq(local.name,cast[*u8]("assigned"))==0 && Eq(local.name,cast[*u8]("mixed"))==0){return;}
 var loan=check.loans;while(loan!=null){if(loan.holder==local && loan.root!=null){
  var field=Shape(local.type).fields;while(field!=null){
   var cursor=ProvenanceCursor{type:local.type,kind:1,key:cast[i64](field),next:null};
   // A structural parent has no root permission. Joining a shared opaque
   // source must not inherit that parent's neutral capability as write access.
   var probe=ReferenceLoan{};probe.root=loan.root;probe.exclusive=1;
   probe.provenance=ProvenanceNodeNew(check.graph,local.type,null,1);
   var shared=ReferenceLoan{};shared.root=loan.root;
   shared.provenance=ProvenanceNodeNew(check.graph,local.type,loan.root,0);
   ReferenceProvenanceJoin(check,&raw probe,&raw shared);
   if(ReferenceLoanQuery(&raw probe,null,loan.root,true)){NativeExit(43);}
   probe.exclusive=0;probe.provenance=ProvenanceNodeNew(check.graph,local.type,loan.root,1);
   if(ReferenceLoanQuery(&raw probe,null,loan.root,true)){NativeExit(44);}
   let reading=BoolInt(ReferenceLoanQuery(loan,&raw cursor,loan.root,false));let writing=BoolInt(ReferenceLoanQuery(loan,&raw cursor,loan.root,true));
   let valid=loan.provenance!=null && loan.provenance.graph==check.graph && loan.provenance.type==local.type;
   LoanRecord(node.kind,local.name,loan.root.name,field.name,reading,writing,BoolInt(valid));field=field.next;
  }
 }loan=loan.next;}
}}
'''
SHIM=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
void LoanRecord(int64_t stage,const char *holder,const char *root,const char *field,int64_t reading,int64_t writing,int64_t valid){fprintf(stderr,"LOAN %lld %s %s %s %lld %lld %lld\n",(long long)stage,holder,root,field,(long long)reading,(long long)writing,(long long)valid);if(!valid)abort();}
'''
PROGRAM='''import "std/io";struct Pair{left:&i64;right:&i64;}
fn AuditPair(){var x=7;var y=8;let tracked=Pair{left:&x,right:&y};let copied=tracked;var assigned=Pair{left:&x,right:&y};assigned=copied;assert(*assigned.left==7);assert(*assigned.right==8);}
fn AuditSame(){var x=7;let tracked=Pair{left:&x,right:&x};let copied=tracked;assert(*copied.left==7);assert(*copied.right==7);}
struct Mixed{left:&i64;right:&mut i64;}fn AuditMixed(){var x=7;var y=8;let mixed=Mixed{left:&x,right:&mut y};assert(*mixed.left==7);assert(*mixed.right==8);}
struct Outer{inner:Pair;}
fn swap(a:&i64,b:&i64)->Pair borrows(a,b){return Pair{left:b,right:a};}
fn AuditSelection(){
 var x=7;var y=8;
 let tracked=Pair{left:&x,right:&y};
 let receiver=&tracked;let picked=(*receiver).left;let picked_copy=picked;assert(*picked_copy==7);
 let outer=Outer{inner:tracked};{let picked=outer.inner.left;assert(*picked==7);}
 let array=[2]&i64{&x,&y};{let indexed=array[0];assert(*indexed==7);}
 let owner=new[Pair](tracked);{let picked=(*owner).left;assert(*picked==7);}
 {let picked=(*new[Pair](tracked)).left;assert(*picked==7);}
 let opaque=swap(&x,&y);let uncertain=opaque.left;assert(*uncertain==8);
}
fn main(){AuditPair();AuditSame();AuditMixed();AuditSelection();io.println(42);}
'''
with tempfile.TemporaryDirectory(prefix='cool live loan graph ') as directory:
 tmp=Path(directory);source=(ROOT/'compiler/16-references.cool').read_text();
 needle='            check.loans = marker;\n            return;';assert source.count(needle)==1;source=source.replace(needle,'            check.loans = marker;\n            LoanAudit(check,node);\n            return;')
 needle='        if (node.kind != 15) {';assert source.count(needle)==1;source=source.replace(needle,'        if(node.kind==8){LoanAudit(check,node);}\n'+needle)
 copied=tmp/'references.cool';copied.write_text(source);adapter=tmp/'audit.cool';adapter.write_text(AUDIT);files=sorted((ROOT/'compiler').glob('*.cool'));manifest=tmp/'sources';manifest.write_text(''.join('__main\t'+str(copied if f.name=='16-references.cool' else f)+'\n' for f in files)+'__main\t'+str(adapter)+'\n')
 frontend=args.frontend.resolve() if args.frontend else ROOT/'build/cool-compiler';ir=tmp/'compiler.ll';env={**os.environ,'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
 r=run([frontend,'llvm-bundle',manifest,ir],env=env);assert r.returncode==0,r
 text=ir.read_text()
 if args.sanitize:text='\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in text.splitlines())+'\n'
 ir.write_text(text);shim=tmp/'shim.c';shim.write_text(SHIM);binary=tmp/'compiler'
 flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if args.sanitize else ['-O2']
 inputs=[];digests={}
 for name in ('compiler-host.o','language-runtime.o'):
  original=ROOT/'build'/name;copy=tmp/name;copy.write_bytes(original.read_bytes());digests[name]=hashlib.sha256(copy.read_bytes()).hexdigest();inputs.append(copy)
 if args.sanitize:
  checked=tmp/'checked.ll';r=run(['clang','-Wno-override-module','-O1','-fsanitize=address','-S','-emit-llvm',ir,'-o',checked]);assert r.returncode==0,r
  assert '__asan_report_load' in checked.read_text() and '__asan_report_store' in checked.read_text()
  inputs=[ROOT/'compiler/host.c',ROOT/'language/runtime.c']
 r=run(['clang','-Wno-override-module',*flags,'-I'+str(ROOT/'compiler'),'-I'+str(ROOT/'language'),ir,shim,*inputs,'-lffi','-o',binary]);assert r.returncode==0,r
 program=tmp/'main.cool';program.write_text(PROGRAM);r=run([binary,'check',program],env=env);assert r.returncode==0,r
 records=[]
 for line in r.stderr.splitlines():
  tag,stage,holder,root,field,reading,writing,valid=line.split();assert tag=='LOAN';record=(int(stage),holder,root,field,int(reading),int(writing));assert valid=='1';records.append(record)
 selection=[r for r in records if r[1] in ('picked','picked_copy','uncertain','indexed')]
 assert selection,records
 for stage,holder,root,field,reading,known in selection:
  assert field=='value' and root in ('x','y','tracked'),(stage,holder,root,field,reading,known)
  if holder in ('picked','picked_copy'):assert (reading,known)==(int(root=='x'),1),(stage,holder,root,reading,known)
  elif holder=='indexed':assert (reading,known)==(1,1),(stage,holder,root,reading,known)
  else:assert (reading,known)==(1,0),(stage,holder,root,reading,known)
 assert sum(r[1]=='picked' and r[2]=='x' for r in selection)==4,selection
 assert any(r[1]=='picked_copy' and r[2]=='x' for r in selection),selection
 records=[r for r in records if r not in selection]
 # Original roots are independent of queried field. In Pair, only x reaches
 # left and y reaches right; AuditSame additionally puts x in both fields.
 by_holder={}
 for stage,holder,root,field,reading,writing in records:
  assert writing==int(holder=='mixed' and root=='y' and field=='right') and (root in ('x','y')),(stage,holder,root,field,reading,writing)
  if root=='y':assert reading==int(field=='right'),records
  by_holder.setdefault((stage,holder),[]).append((root,field,reading))
 for key in ((7,'tracked'),(7,'copied'),(7,'assigned'),(8,'assigned')):assert key in by_holder,key
 # Pair must carry the left root through initializer, copy and assignment.
 for key,rows in by_holder.items():assert ('x','left',1) in rows,(key,rows)
 assert any(root=='x' and field=='right' and not reading for stage,holder,root,field,reading,writing in records),records
 assert any(root=='x' and field=='right' and reading for stage,holder,root,field,reading,writing in records),records
 for engine in ('tree','interp','jit','llvm','llvm-jit'):
  r=run([ROOT/'tools/cool','run','--backend',engine,program],env={**env,'COOL_FRONTEND':str(binary)});assert r.returncode==0 and r.stdout=='42\n',r
  assert all(line.startswith('LOAN ') for line in r.stderr.splitlines()),r
 native=tmp/'native';r=run([ROOT/'tools/cool','build','--release',program,'-o',native],env={**env,'COOL_FRONTEND':str(binary)});assert r.returncode==0,r
 r=run([native],env=env);assert (r.returncode,r.stdout,r.stderr)==(0,'42\n',''),r
 repl='struct Pair{left:&i64;right:&i64;}\nvar x=7;\nvar y=8;\nvar assigned=Pair{left:&x,right:&y};\n{assigned=Pair{left:&x,right:&y};assert(false);}\nfn broken(){var a=1;let r=&a;a=2;}\nassigned=assigned;\n*assigned.left\n*assigned.right\n:forget assigned\nx=3;\nx\n:quit\n'
 r=run([binary,'repl-quiet'],input=repl,env=env);assert r.returncode==0 and r.stdout=='7\n8\n3\n' and r.stderr.count('error:')==2,r
 assert 'AddressSanitizer' not in r.stderr and 'runtime error:' not in r.stderr,r
 assert sum(line.startswith('LOAN ') for line in r.stderr.splitlines())>=8,r
 report={'records':records,'selection_records':selection,'sanitize':args.sanitize,'artifact_sha256':digests,'private_ir_sha256':hashlib.sha256(ir.read_bytes()).hexdigest(),'compiler_source_sha256':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},'platform_source_sha256':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [ROOT/'compiler/host.c',*(ROOT/'language'/name for name in ('runtime.c','memory.h','numeric.h','ffi.h','repl_io.h','args.h'))]},'audit_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'method':'Private production compiler hook at actual binding/copy/whole-assignment checks; typed field root/mode oracle mixed shared/exclusive fields, five engines/O2 and partial-runtime/failed-function-check REPL recovery. Scoped permissions still use the existing coarse checker; graph substitution and nested acceptance are not certified.'}
 if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
 print(f'live loan provenance: {len(records)} field/root/mode and {len(selection)} selection records, initializers/copies/whole assignments/same-root fields mixed permissions, five engines/O2 and REPL recovery PASS'+(' with ASan/UBSan' if args.sanitize else ''))
