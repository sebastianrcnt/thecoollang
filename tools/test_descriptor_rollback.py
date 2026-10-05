#!/usr/bin/env python3
"""Actual live graph descriptors must survive REPL type/layout rollback."""
import argparse, hashlib, json, os, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--sanitize',action='store_true');p.add_argument('--output',type=Path);args=p.parse_args()
def run(cmd,**kw):return subprocess.run(list(map(str,cmd)),cwd=ROOT,text=True,capture_output=True,timeout=240,**kw)
AUDIT='''
fn AuditTypeEqual(type:i64,removed:i64)->bool{var normalized=type;while(normalized>=100000){normalized=normalized-100000;}return normalized==removed;}
fn AuditDescriptorType(removed:i64){unsafe{
 let ctx=cast[*CompilerState](NativeCompilerState(i64(sizeof(CompilerState))));
 Out(cast[*u8]("AUDIT_TYPE_CLEAR\\n"));
 if(ctx.v_repl_graph!=null){var node=ctx.v_repl_graph.nodes;while(node!=null){
  if(AuditTypeEqual(node.type,removed) || (node.root!=null && AuditTypeEqual(node.root.type,removed)) || (node.summary_root!=null && AuditTypeEqual(node.summary_root.type,removed))){NativeExit(91);}node=node.next;}}
 var loan=ctx.v_repl_loans;while(loan!=null){
  if(AuditTypeEqual(loan.provenance_type,removed) || (loan.holder!=null && AuditTypeEqual(loan.holder.type,removed)) || (loan.root!=null && AuditTypeEqual(loan.root.type,removed))){NativeExit(91);}
  if(loan.parent!=null && AuditTypeEqual(loan.parent.type,removed)){Out(cast[*u8]("AUDIT_PARENT_TYPE\\n"));NativeExit(93);}
  loan=loan.next;
 }
}}
fn AuditDescriptorField(field:*Field){unsafe{
 let ctx=cast[*CompilerState](NativeCompilerState(i64(sizeof(CompilerState))));
 Out(cast[*u8]("AUDIT_FIELD_FREE\\n"));
 if(ctx.v_repl_graph!=null){var node=ctx.v_repl_graph.nodes;while(node!=null){var edge=node.edges;while(edge!=null){if(edge.kind==1 && edge.key==cast[i64](field)){NativeExit(92);}edge=edge.next;}node=node.next;}}
}}
export "C" fn AuditAncestryGuards(){unsafe{
 let ctx=cast[*CompilerState](NativeCompilerState(i64(sizeof(CompilerState))));
 var locals=[6]Local{};var loans=[6]ReferenceLoan{};var graph=ProvenanceGraph{};
 for(var i:i64=0;i<6;i=i+1){locals[i].type=1001;loans[i].parent=&raw locals[i];if(i<5){loans[i].next=&raw loans[i+1];}}
 locals[0].depth=3;locals[0].slot=7;locals[0].name=cast[*u8]("ancestry");locals[0].next=&raw locals[1];
 loans[1].root=&raw locals[1];loans[2].holder=&raw locals[2];ctx.v_repl_loans=&raw loans[0];ctx.v_repl_locals=&raw locals[3];ctx.v_repl_graph=&raw graph;
 let node=ProvenanceNodeNew(&raw graph,1,&raw locals[4],1);node.summary_root=&raw locals[5];
 for(var i:i64=0;i<6;i=i+1){if(ReplAncestryOnly(loans[i].parent,ctx.v_repl_locals)){loans[i].parent=null;}}
 if(locals[0].type!=1001 || locals[0].depth!=3 || locals[0].slot!=7 || Eq(locals[0].name,cast[*u8]("ancestry"))==i8(0) || locals[0].next!=&raw locals[1]){NativeExit(94);}
 for(var i:i64=1;i<6;i=i+1){if(locals[i].type!=1001 || loans[i].parent!=&raw locals[i]){NativeExit(95);}}
 if(loans[0].parent!=null){NativeExit(95);}
 ctx.v_repl_graph=null;ctx.v_repl_loans=null;ctx.v_repl_locals=null;ProvenanceGraphFree(&raw graph);NativeExit(0);
}}
export "C" fn AuditNegativeType(){unsafe{
 let ctx=cast[*CompilerState](NativeCompilerState(i64(sizeof(CompilerState))));var graph=ProvenanceGraph{};ctx.v_repl_graph=&raw graph;
 ProvenanceNodeNew(&raw graph,101001,null,1);AuditDescriptorType(1001);NativeExit(99);
}}
export "C" fn AuditNegativeField(){unsafe{
 let ctx=cast[*CompilerState](NativeCompilerState(i64(sizeof(CompilerState))));var graph=ProvenanceGraph{};ctx.v_repl_graph=&raw graph;var field=Field{};
 let node=ProvenanceNodeNew(&raw graph,1,null,1);if(!ProvenanceEdgeNew(node,1,cast[i64](&raw field),node,1)){NativeExit(99);}AuditDescriptorField(&raw field);NativeExit(99);
}}
'''
LEGACY='''
Bool AuditTypeEqual(I64 type,I64 removed){while(type>=100000)type-=100000;return type==removed;}
U0 AuditDescriptorType(I64 removed){ProvenanceNode *node;ReferenceLoan *loan;Out("AUDIT_TYPE_CLEAR\\n");if(repl_graph)for(node=repl_graph->nodes;node;node=node->next)if(AuditTypeEqual(node->type,removed) || (node->root && AuditTypeEqual(node->root->type,removed)) || (node->summary_root && AuditTypeEqual(node->summary_root->type,removed)))NativeExit(91);for(loan=repl_loans;loan;loan=loan->next){if(AuditTypeEqual(loan->provenance_type,removed) || (loan->holder && AuditTypeEqual(loan->holder->type,removed)) || (loan->root && AuditTypeEqual(loan->root->type,removed)))NativeExit(91);if(loan->parent && AuditTypeEqual(loan->parent->type,removed)){Out("AUDIT_PARENT_TYPE\\n");NativeExit(93);}}}
U0 AuditDescriptorField(Field *field){ProvenanceNode *node;ProvenanceEdge *edge;Out("AUDIT_FIELD_FREE\\n");if(repl_graph)for(node=repl_graph->nodes;node;node=node->next)for(edge=node->edges;edge;edge=edge->next)if(edge->kind==1 && edge->key==field)NativeExit(92);}
U0 AuditAncestryGuards(){Local locals[6];ReferenceLoan loans[6];ProvenanceGraph graph;ProvenanceNode *node;I64 i;MemSet(locals,0,6*sizeof(Local));MemSet(loans,0,6*sizeof(ReferenceLoan));MemSet(&graph,0,sizeof(ProvenanceGraph));for(i=0;i<6;i++){locals[i].type=1001;loans[i].parent=&locals[i];if(i<5)loans[i].next=&loans[i+1];}locals[0].depth=3;locals[0].slot=7;locals[0].name="ancestry";locals[0].next=&locals[1];loans[1].root=&locals[1];loans[2].holder=&locals[2];repl_loans=loans;repl_locals=&locals[3];repl_graph=&graph;node=ProvenanceNodeNew(&graph,1,&locals[4],1);node->summary_root=&locals[5];for(i=0;i<6;i++)if(ReplAncestryOnly(loans[i].parent,repl_locals))loans[i].parent=NULL;if(locals[0].type!=1001 || locals[0].depth!=3 || locals[0].slot!=7 || !Eq(locals[0].name,"ancestry") || locals[0].next!=&locals[1])NativeExit(94);for(i=1;i<6;i++)if(locals[i].type!=1001 || loans[i].parent!=&locals[i])NativeExit(95);if(loans[0].parent)NativeExit(95);repl_graph=NULL;repl_loans=NULL;repl_locals=NULL;ProvenanceGraphFree(&graph);NativeExit(0);}
U0 AuditNegativeType(){ProvenanceGraph graph;MemSet(&graph,0,sizeof(ProvenanceGraph));repl_graph=&graph;ProvenanceNodeNew(&graph,101001,NULL,1);AuditDescriptorType(1001);NativeExit(99);}
U0 AuditNegativeField(){ProvenanceGraph graph;Field field;ProvenanceNode *node;MemSet(&graph,0,sizeof(ProvenanceGraph));MemSet(&field,0,sizeof(Field));repl_graph=&graph;node=ProvenanceNodeNew(&graph,1,NULL,1);if(!ProvenanceEdgeNew(node,1,&field,node,1))NativeExit(99);AuditDescriptorField(&field);NativeExit(99);}
'''
DRIVER='''#include <string.h>
extern int OriginalCompilerMain(int,char**);
extern void AuditNegativeType(void),AuditNegativeField(void),AuditAncestryGuards(void);
int main(int argc,char**argv){if(argc==2 && !strcmp(argv[1],"audit-ancestry-guards"))AuditAncestryGuards();if(argc==2 && !strcmp(argv[1],"audit-negative-type"))AuditNegativeType();if(argc==2 && !strcmp(argv[1],"audit-negative-field"))AuditNegativeField();return OriginalCompilerMain(argc,argv);}
'''
CASES=[
 ('generic_parent', 'struct G[T]{r:&i64;v:T;}\nvar a=1;\nvar b=2;\nvar r=&a;\n{var temp=G[i64]{r:&b,v:3};r=temp.r;assert(false);}\n*r\nb=7;\n:forget r\nb=7;\nb\n','2\n7\n',2),
 ('generic_type_reuse', 'struct G[T]{r:&i64;v:T;}\nvar a=1;\nvar b=2;\nvar r=&a;\n{var temp=G[i64]{r:&b,v:3};r=temp.r;assert(false);}\nvar recycled=G[[2]i64]{r:&a,v:[2]i64{4,5}};\n*r\n*recycled.r\nb=7;\n:forget r\nb=7;\nb\n:forget recycled\n','2\n1\n7\n',2),
 ('generic_copy', 'struct G[T]{r:&i64;v:T;}\nvar a=1;\nvar b=2;\nvar r=&a;\n{let temp=G[[2]i64]{r:&b,v:[2]i64{3,4}};r=temp.r;assert(false);}\n*r\n:forget r\nb=8;\nb\n','2\n8\n',1),
 ('generic_return','struct G[T]{r:&i64;v:T;}\nfn get[T](p:G[T])->&i64 borrows(p){return p.r;}\nvar a=1;\nvar b=2;\nvar r=&a;\n{r=get[i64](G[i64]{r:&b,v:3});assert(false);}\n*r\n:forget r\nb=9;\nb\n','2\n9\n',1),
 ('physical_generic','struct G[T]{x:T;y:T;}\nvar p=G[i64]{x:1,y:2};\nlet r=&mut p;\nlet x=&mut (*r).x;\n{(*r).y=3;let temp=G[[2]i64]{x:[2]i64{1,2},y:[2]i64{3,4}};assert(false);}\n*x\n(*r).y\n:forget x\n:forget r\n:forget p\n','1\n3\n',1),
 ('lazy_failure','struct Bad[T]{item:Bad[T];}\nstruct View{r:&i64;}\nvar a=1;\nvar v=View{r:&a};\nfn bad(){let x=Bad[i64]{};}\n*v.r\n:forget v\na=5;\na\n','1\n5\n',1),
]
with tempfile.TemporaryDirectory(prefix='cool descriptor rollback ') as directory:
 tmp=Path(directory);production=sorted((ROOT/'compiler').glob('*.cool'));legacy=sorted((ROOT/'language').glob('*.cool'));files=production+legacy;hashes={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
 prod=tmp/'compiler';prod.mkdir()
 for f in production:(prod/f.name).write_bytes(f.read_bytes())
 types=prod/'28-repl-types.cool';s=types.read_text();assert s.count('Free(cast[*u8](current));')==1;s=s.replace('Free(cast[*u8](current));','AuditDescriptorField(current);Free(cast[*u8](current));');needle='ReplFreeFields(ctx.v_aggregate_types[i].fields);';assert s.count(needle)==1;s=s.replace(needle,'AuditDescriptorType(i + 1000);'+needle);types.write_text(s)
 audit=prod/'99-descriptor-audit.cool';audit.write_text(AUDIT);manifest=tmp/'sources';manifest.write_text(''.join('__main\t'+str(f)+'\n' for f in sorted(prod.glob('*.cool'))));ir=tmp/'compiler.ll'
 r=run([ROOT/'build/cool-compiler','llvm-bundle',manifest,ir]);assert r.returncode==0,r
 text=ir.read_text();assert text.count('define i32 @main(')==1;text=text.replace('define i32 @main(', 'define i32 @OriginalCompilerMain(')
 if args.sanitize:text='\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in text.splitlines())+'\n'
 ir.write_text(text);driver=tmp/'driver.c';driver.write_text(DRIVER);binary=tmp/'frontend'
 flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if args.sanitize else ['-O2']
 r=run(['clang','-Wno-override-module',*flags,'-I'+str(ROOT/'compiler'),'-I'+str(ROOT/'language'),ir,driver,ROOT/'compiler/host.c',ROOT/'language/runtime.c','-lffi','-o',binary]);assert r.returncode==0,r
 if args.sanitize:
  checked=tmp/'checked.ll';r=run(['clang','-Wno-override-module','-O1','-fsanitize=address','-S','-emit-llvm',ir,'-o',checked]);assert r.returncode==0,r
  assert '__asan_report_load' in checked.read_text() and '__asan_report_store' in checked.read_text()
 seed=tmp/'language';seed.mkdir()
 for f in legacy:(seed/f.name).write_bytes(f.read_bytes())
 types=seed/'ReplTypes.cool';s=types.read_text();s='extern U0 AuditDescriptorField(Field *field);extern U0 AuditDescriptorType(I64 type);\n'+s;s=s.replace('next=field->next;Free(field);','next=field->next;AuditDescriptorField(field);Free(field);');s=s.replace('ReplFreeFields(aggregate_types[i].fields);','AuditDescriptorType(i+1000);ReplFreeFields(aggregate_types[i].fields);');types.write_text(s)
 native=seed/'Native.cool';s=native.read_text();assert s.endswith('LanguageMain;\n');s=s[:-len('LanguageMain;\n')]+LEGACY+'if(NativeArgCount()==2 && Eq(NativeArg(1),"audit-ancestry-guards"))AuditAncestryGuards();\nif(NativeArgCount()==2 && Eq(NativeArg(1),"audit-negative-type"))AuditNegativeType();\nif(NativeArgCount()==2 && Eq(NativeArg(1),"audit-negative-field"))AuditNegativeField();\nLanguageMain;\n';native.write_text(s)
 seed_binary=tmp/'frontend.BIN';env={**os.environ,'COOLC_COMPILER_BIN':str(ROOT/'coolc/seed/Compiler.BIN'),'ASAN_OPTIONS':'halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
 r=run([ROOT/'build/coolc',native,seed_binary],env=env);assert r.returncode==0,r
 observations=[]
 for name,front in [('production',[binary]),('seed',[ROOT/'build/coolc','--run',seed_binary])]:
  for mode,exit_code in [('audit-ancestry-guards',0),('audit-negative-type',91),('audit-negative-field',92)]:
   r=run([*front,mode],env=env);assert r.returncode==exit_code,(name,mode,r)
  for case,source,output,errors in CASES:
   r=run([*front,'repl-quiet'],input=source+':quit\n',env=env)
   cleaned=''.join(line+'\n' for line in r.stdout.splitlines() if not line.startswith('AUDIT_'))
   assert (r.returncode,cleaned,r.stderr.count('error:'))==(0,output,errors),(name,case,r)
   rows={key:r.stdout.count('AUDIT_'+label+'\n') for key,label in [('freed_fields','FIELD_FREE'),('cleared_types','TYPE_CLEAR'),('parent_type_matches','PARENT_TYPE')]}
   assert rows['parent_type_matches']==0,(name,case,rows)
   assert rows['cleared_types']>0 and (case=='lazy_failure' or rows['freed_fields']>0),(name,case,rows)
   print(name,case,rows)
   observations.append({'frontend':name,'case':case,**rows})
 assert hashes=={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},'source changed during audit'
 report={'source_sha256':hashes,'sanitize':args.sanitize,'observations':observations,'method':'Private copies of both actual frontends; before each rollback Field free and new type clear, reject matching live compact graph nodes/Field edges (including physical and auxiliary nodes), node roots/summary roots and loan root/holder/result types; negative controls prove detection. Dead ancestry leaves must be pruned before rollback; private role guards prove visible/root/holder/graph-root/summary-root descriptors remain unchanged and dead leaf metadata is not mutated. Direct encoded type IDs checked; this audit does not prove all recursive descriptor dependencies or arbitrary nested acceptance.'}
 if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
 print('descriptor rollback: '+str(len(observations))+' actual frontend histories, negative controls and live graph/Field/type checks PASS'+(' with ASan/UBSan' if args.sanitize else ''))
 print(json.dumps(observations))
