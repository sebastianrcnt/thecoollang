#!/usr/bin/env python3
"""Nested borrowed-storage lifetime, authority and cross-engine regressions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def function_span(text, name, prefix='fn '):
    """Locate exactly one ordinary Cool function, counting lexical braces."""
    needle = prefix + name + '('
    assert text.count(needle) == 1, name
    start = text.index(needle)
    opening = text.index('{', start)
    depth, i, state = 0, opening, 'code'
    while i < len(text):
        c = text[i]
        pair = text[i:i + 2]
        if state == 'line':
            if c == '\n': state = 'code'
        elif state == 'block':
            if pair == '*/': state = 'code'; i += 1
        elif state == 'string':
            if c == '\\': i += 1
            elif c == '"': state = 'code'
        elif pair == '//': state = 'line'; i += 1
        elif pair == '/*': state = 'block'; i += 1
        elif c == '"': state = 'string'
        elif c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: return start, i + 1
        i += 1
    raise AssertionError('unterminated function ' + name)


CASES = [
    ('outer_read', 'accept', '''struct Inner{r:&i64;}struct Outer{inner:&Inner;}
fn main(){var a=7;let inner=Inner{r:&a};let outer=Outer{inner:&inner};assert(*(*outer.inner).r==7);}
'''),
    ('external_return', 'accept', '''struct Inner{r:&i64;}struct Outer{inner:&Inner;}
fn get(o:Outer)->&i64 borrows(o){return (*o.inner).r;}
fn main(){var a=7;let inner=Inner{r:&a};let outer=Outer{inner:&inner};let q=get(outer);assert(*q==7);}
'''),
    ('local_inner_external_return', 'accept', '''struct Inner{r:&i64;}struct Outer{inner:&Inner;}
fn get(x:&i64)->&i64 borrows(x){let inner=Inner{r:x};let outer=Outer{inner:&inner};return (*outer.inner).r;}
fn main(){var a=7;let q=get(&a);assert(*q==7);}
'''),
    ('local_inner_address_return', 'accept', '''struct Inner{r:&i64;}struct Outer{inner:&Inner;}
fn get(x:&i64)->&i64 borrows(x){let inner=Inner{r:x};let outer=Outer{inner:&inner};return &*(*outer.inner).r;}
fn main(){var a=7;let q=get(&a);assert(*q==7);}
'''),
    ('local_inner_scalar_address_return', 'reject', '''struct Inner{r:&i64;v:i64;}struct Outer{inner:&Inner;}
fn get(x:&i64)->&i64 borrows(x){let inner=Inner{r:x,v:7};let outer=Outer{inner:&inner};return &(*outer.inner).v;}
fn main(){var a=7;let q=get(&a);assert(*q==7);}
'''),
    ('reference_parameter_slot_return', 'reject', '''fn bad(p:&i64)->& &i64 borrows(p){return &p;}
fn main(){var a=7;let q=bad(&a);assert(**q==7);}
'''),
    ('byvalue_parameter_slot_return', 'reject', '''struct Pair{r:&i64;}
fn bad(p:Pair)->& &i64 borrows(p){return &p.r;}
fn main(){var a=7;let q=bad(Pair{r:&a});assert(**q==7);}
'''),
    ('byvalue_owner_payload_return', 'reject', '''struct Wrapper{r:&i64;value:i64;}
fn bad(p:own[Wrapper])->&i64 borrows(p){return &(*p).value;}
fn main(){var a=7;let q=bad(new[Wrapper](Wrapper{r:&a,value:7}));assert(*q==7);}
'''),
    ('temporary_owner_slot_return', 'reject', '''struct Inner{r:&i64;v:i64;}
fn get(x:&i64)->&i64 borrows(x){return &(*new[Inner](Inner{r:x,v:9})).v;}
fn main(){var a=7;let q=get(&a);assert(*q==9);}
'''),
    ('stores_uncontracted_source_return', 'reject', '''struct Pair{r:&i64;}
fn get(dst:&mut Pair,src:&i64)->&i64 borrows(dst) stores(dst,src){(*dst).r=src;return (*dst).r;}
fn main(){var a=7;var b=9;var pair=Pair{r:&a};let q=get(&mut pair,&b);assert(*q==9);}
'''),
    ('short_inner_escape', 'reject', '''struct Inner{r:&i64;}struct Outer{inner:&Inner;}
fn main(){var a=7;let kept=Inner{r:&a};var outer=Outer{inner:&kept};{let short=Inner{r:&a};outer.inner=&short;}assert(*(*outer.inner).r==7);}
'''),
    ('shared_outer_mutable_inner', 'reject', '''struct Inner{r:&mut i64;}struct Outer{inner:&Inner;}
fn main(){var a=7;var inner=Inner{r:&mut a};let outer=Outer{inner:&inner};let q=(*outer.inner).r;*q=9;}
'''),
]


DEEP_CASES=[]
# Distinct physical descriptors at every level, with the final scalar caller
# root shared by copy/address returns. Rejection variants address a frame field
# at each depth, not only the outermost descriptor.
for depth in (2, 3, 4):
    declarations = 'struct L0{r:&i64;v:i64;}' + ''.join(
        f'struct L{i}{{next:&L{i-1};v:i64;}}' for i in range(1, depth))
    setup = 'let l0=L0{r:x,v:7};' + ''.join(
        f'let l{i}=L{i}{{next:&l{i-1},v:7}};' for i in range(1, depth))
    access = f'l{depth-1}'
    expressions = [(depth-1, access)]
    for level in reversed(range(depth-1)):
        access = f'(*{access}.next)'
        expressions.append((level, access))
    for form, value in (('copy', access+'.r'), ('address', '&*'+access+'.r')):
        source = declarations + f'fn get(x:&i64)->&i64 borrows(x){{{setup}return {value};}}' + 'fn main(){var a=7;let q=get(&a);assert(*q==7);}'
        DEEP_CASES.append((f'depth{depth}_{form}_external_return', 'accept', source))
    for level, projected in expressions:
        source = declarations + f'fn bad(x:&i64)->&i64 borrows(x){{{setup}return &{projected}.v;}}' + 'fn main(){}'
        DEEP_CASES.append((f'depth{depth}_level{level}_frame_return', 'reject', source))


STORE_CASES=[]
STORE_DIAGNOSTICS={}
for depth in (2, 3):
    declarations='struct L0{r:&i64;}' + ''.join(f'struct L{i}{{next:&mut L{i-1};}}' for i in range(1,depth))
    setup='var l0=L0{r:&a};' + ''.join(f'var l{i}=L{i}{{next:&mut l{i-1}}};' for i in range(1,depth))
    access='(*p)'
    for level in reversed(range(depth-1)):access=f'(*{access}.next)'
    prefix=declarations+'fn main(){var a=7;var b=9;'+setup+f'let p=&mut l{depth-1};'
    STORE_CASES.append((f'store_depth{depth}_replace', 'accept', prefix+f'{access}.r=&b;assert(*{access}.r==9);}}'))
    name=f'store_depth{depth}_short_source'
    STORE_CASES.append((name,'reject',prefix+f'{{var short=11;{access}.r=&short;}}assert(*{access}.r==11);}}'))
    STORE_DIAGNOSTICS[name]='outlive'
    name=f'store_depth{depth}_retained_source'
    STORE_CASES.append((name,'reject',prefix+f'{access}.r=&b;b=11;}}'))
    STORE_DIAGNOSTICS[name]='conflicts'
    function=declarations+f'fn set(p:&mut L{depth-1},src:&i64) stores(p,src){{{access}.r=src;assert(*{access}.r==*src);}}'
    STORE_CASES.append((f'store_depth{depth}_contract','accept',function+'fn main(){var a=7;var b=9;'+setup+f'set(&mut l{depth-1},&b);}}'))
    name=f'store_depth{depth}_missing_contract'
    STORE_CASES.append((name,'reject',function.replace(' stores(p,src)','')+'fn main(){}'))
    STORE_DIAGNOSTICS[name]='matching stores'

# Retarget an inner descriptor to another parameter, then write through it.
# A destination contract for the old outer parameter cannot authorize effects
# on the other parameter's caller storage.
retarget='struct L0{r:&i64;}struct L1{next:&mut L0;}fn bad(p:&mut L1,other:&mut L0,src:&i64) stores(p,other) stores(p,src){(*p).next=other;(*(*p).next).r=src;}fn main(){}'
STORE_CASES.append(('store_retarget_missing_destination_contract','reject',retarget))
STORE_DIAGNOSTICS['store_retarget_missing_destination_contract']='matching stores'
complete_retarget=retarget.replace(' stores(p,src){',' stores(p,src) stores(other,src){').replace('fn main(){}','fn main(){var a=7;var b=9;var c=11;var first=L0{r:&a};var second=L0{r:&b};var outer=L1{next:&mut first};bad(&mut outer,&mut second,&c);assert(*(*outer.next).r==11);}')
STORE_CASES.append(('store_retarget_complete_destination_contract','accept',complete_retarget))

for style in ('direct','alias','forward'):
    declarations='struct L0{r:&i64;}struct L1{next:&mut L0;}'
    helper='fn set0(dst:&mut L0,src:&i64) stores(dst,src){(*dst).r=src;}' if style=='forward' else ''
    write='(*(*p).next).r=src;' if style=='direct' else 'let alias=(*p).next;(*alias).r=src;' if style=='alias' else 'set0((*p).next,src);'
    body=f'if(yes){{(*p).next=other;}}{write}'
    header='fn change(p:&mut L1,other:&mut L0,src:&i64,yes:bool) stores(p,other)'
    runtime='fn main(){var a=7;var b=9;var c=11;'
    for yes in ('true','false'):
        runtime+='{var first=L0{r:&a};var second=L0{r:&b};var outer=L1{next:&mut first};change(&mut outer,&mut second,&c,'+yes+');assert(*(*outer.next).r==11);}'
    runtime+='}'
    for omitted in ('old','new','none'):
        contracts=(' stores(p,src)' if omitted!='old' else '')+(' stores(other,src)' if omitted!='new' else '')
        name=f'store_branch_{style}_{omitted}_destination_contract'
        code=declarations+helper+header+contracts+'{'+body+'}'+(runtime if omitted=='none' else 'fn main(){}')
        STORE_CASES.append((name,'accept' if omitted=='none' else 'reject',code))
        if omitted!='none':STORE_DIAGNOSTICS[name]='matching stores'

for container in ('array','owned'):
    declarations='struct L0{r:&i64;}struct L1{next:&mut L0;}'
    if container=='array':
        parameter='&mut [2]&mut L0';replace='(*p)[0]=other;';access='(*(*p)[index])'
        args='yes:bool,index:usize';runtime='fn main(){var a=7;var b=9;var c=11;var first=L0{r:&a};var second=L0{r:&b};var third=L0{r:&a};var array=[2]&mut L0{&mut first,&mut second};change(&mut array,&mut third,&c,true,0);assert(*(*array[0]).r==11);}'
    else:
        declarations='import "std/mem";'+declarations
        parameter='&mut own[L1]';replace='(*(*p)).next=other;';access='(*(*(*p)).next)'
        args='yes:bool';runtime='fn main(){var a=7;var b=9;var c=11;var first=L0{r:&a};var second=L0{r:&b};{var owner=new[L1](L1{next:&mut first});change(&mut owner,&mut second,&c,true);assert(*(*(*owner).next).r==11);}assert(mem.owner_count()==0);}'
    header=f'fn change(p:{parameter},other:&mut L0,src:&i64,{args}) stores(p,other)'
    for omitted in ('old','new','none'):
        contracts=(' stores(p,src)' if omitted!='old' else '')+(' stores(other,src)' if omitted!='new' else '')
        name=f'store_{container}_{omitted}_destination_contract'
        code=declarations+header+contracts+f'{{if(yes){{{replace}}}{access}.r=src;}}'+(runtime if omitted=='none' else 'fn main(){}')
        STORE_CASES.append((name,'accept' if omitted=='none' else 'reject',code))
        if omitted!='none':STORE_DIAGNOSTICS[name]='matching stores'

# A pending owned address must still block moves and aliasing replacements
# evaluated on another AST path, even with complete stores contracts.
owned_types='struct L0{r:&i64;}struct L1{next:&mut L0;}'
for operation, helper, parameters, contracts, rhs in (
    ('move', 'fn take(p:own[L1],src:&i64)->&i64 borrows(src){return src;}',
     '', '', 'take(move *p,src)'),
    ('replace', 'fn replace(p:&mut own[L1],other:own[L1],src:&i64)->&i64 borrows(src) stores(p,other){*p=move other;return src;}',
     ',other:own[L1]', ' stores(p,other)', 'replace(p,move other,src)'),
):
    name='store_owned_pending_'+operation
    code=owned_types+helper+f'fn change(p:&mut own[L1],src:&i64{parameters}) stores(p,src){contracts}{{(*(*(*p)).next).r={rhs};}}fn main(){{}}'
    STORE_CASES.append((name,'reject',code))
    STORE_DIAGNOSTICS[name]='conflicts'

SLICE_CASES = [
    ('slice_reference_read', 'accept', 'fn main(){var a=7;var b=9;var refs=[2]&i64{&a,&b};var s=refs[:];assert(*s[0]==7 && *s[1]==9);}'),
    ('slice_local_payload_return', 'accept', 'fn get(x:&i64)->&i64 borrows(x){var refs=[1]&i64{x};var s=refs[:];return s[0];}fn main(){var a=7;let r=get(&a);assert(*r==7);}'),
    ('slice_local_payload_address_return', 'accept', 'fn get(x:&i64)->&i64 borrows(x){var refs=[1]&i64{x};var s=refs[:];return &*s[0];}fn main(){var a=7;let r=get(&a);assert(*r==7);}'),
    ('slice_local_scalar_return', 'reject', 'fn bad(x:&i64)->&i64 borrows(x){var a=7;var refs=[1]&i64{&a};var s=refs[:];return s[0];}fn main(){}'),
    ('slice_local_slot_return', 'reject', 'fn bad(x:&i64)->& &i64 borrows(x){var refs=[1]&i64{x};var s=refs[:];return &s[0];}fn main(){}'),
    ('slice_local_descriptor_return', 'reject', 'fn bad(x:&i64)->[]&i64 borrows(x){var refs=[1]&i64{x};return refs[:];}fn main(){}'),
    ('slice_parameter_payload_return', 'accept', 'fn get(s:[]&i64)->&i64 borrows(s){return s[0];}fn main(){var a=7;var refs=[1]&i64{&a};let r=get(refs[:]);assert(*r==7);}'),
    ('slice_parameter_slot_return', 'accept', 'fn get(s:[]&i64)->& &i64 borrows(s){return &s[0];}fn main(){var a=7;var refs=[1]&i64{&a};let r=get(refs[:]);assert(**r==7);}'),
    ('slice_short_payload_store', 'reject', 'fn main(){var a=7;var refs=[1]&i64{&a};var s=refs[:];{var b=9;s[0]=&b;}assert(*s[0]==7);}'),
    ('slice_retained_payload_mutation', 'reject', 'fn main(){var a=7;var b=9;var refs=[1]&i64{&a};var s=refs[:];s[0]=&b;b=11;}'),
    ('slice_array_mutation_while_borrowed', 'reject', 'fn main(){var a=7;var b=9;var refs=[1]&i64{&a};var s=refs[:];refs[0]=&b;}'),
    ('slice_mutable_payload', 'accept', 'fn main(){var a=7;var refs=[1]&mut i64{&mut a};{var s=refs[:];*s[0]=9;assert(*s[0]==9);}assert(*refs[0]==9);}'),
    ('slice_shared_descriptor_mutable_copy', 'reject', 'fn bad(s:&[]&mut i64){let r=(*s)[0];*r=9;}fn main(){}'),
    ('slice_shared_descriptor_mutable_address', 'reject', 'fn bad(s:&[]&mut i64){let r=&mut *(*s)[0];*r=9;}fn main(){}'),
]
SLICE_CASES.extend([
    ('slice_computed_local_payload_return', 'accept', 'fn identity(s:[]&i64)->[]&i64 borrows(s){return s;}fn get(x:&i64)->&i64 borrows(x){var refs=[1]&i64{x};return identity(refs[:])[0];}fn main(){var a=7;let r=get(&a);assert(*r==7);}'),
    ('slice_computed_local_slot_return', 'reject', 'fn identity(s:[]&i64)->[]&i64 borrows(s){return s;}fn bad(x:&i64)->& &i64 borrows(x){var refs=[1]&i64{x};return &identity(refs[:])[0];}fn main(){}'),
    ('slice_parameter_descriptor_return', 'reject', 'fn bad(s:[]&i64)->&[]&i64 borrows(s){return &s;}fn main(){}'),
    ('slice_subslice_payload_return', 'accept', 'fn get(x:&i64)->&i64 borrows(x){var refs=[2]&i64{x,x};var s=refs[:];var t=s[1:];return t[0];}fn main(){var a=7;let r=get(&a);assert(*r==7);}'),
    ('slice_subslice_slot_return', 'reject', 'fn bad(x:&i64)->& &i64 borrows(x){var refs=[2]&i64{x,x};var s=refs[:];var t=s[1:];return &t[0];}fn main(){}'),
    ('slice_subslice_store', 'accept', 'fn main(){var a=7;var b=9;var refs=[2]&i64{&a,&a};{var s=refs[:];{var t=s[1:];t[0]=&b;assert(*t[0]==9);}}assert(*refs[0]==7 && *refs[1]==9);}'),
])

SLICE_CASES.extend([
    ('slice_stored_local_payload_return', 'reject', 'fn bad(x:&i64)->&i64 borrows(x){var refs=[1]&i64{x};var s=refs[:];var b=9;s[0]=&b;return s[0];}fn main(){}'),
    ('slice_stored_external_payload_return', 'accept', 'fn get(x:&i64,y:&i64)->&i64 borrows(x,y){var refs=[1]&i64{x};var s=refs[:];s[0]=y;return s[0];}fn main(){var a=7;var b=9;let r=get(&a,&b);assert(*r==9);}'),
])

SLICE_CASES.extend([
    ('slice_live_mutable_payload_alias', 'reject', 'fn main(){var a=7;var refs=[1]&mut i64{&mut a};var s=refs[:];let r=&mut *s[0];*s[0]=9;assert(*r==9);}'),
    ('slice_released_mutable_payload_alias', 'accept', 'fn main(){var a=7;var refs=[1]&mut i64{&mut a};var s=refs[:];{let r=&mut *s[0];*r=8;}*s[0]=9;assert(*s[0]==9);}'),
])
STORE_DIAGNOSTICS['slice_live_mutable_payload_alias']='conflicts'

SLICE_CASES.extend([
    ('receiver_slice_read', 'accept', 'struct View{items:[]i64;}fn first(v:&View)->i64 borrows(v){return (*v).items[0];}fn main(){var a=[2]i64{7,9};var view=View{items:a[:]};assert(first(&view)==7);}'),
    ('receiver_slice_mutable_write', 'accept', 'struct View{items:[]i64;}fn set(v:&mut View,x:i64){(*v).items[0]=x;}fn main(){var a=[1]i64{7};var view=View{items:a[:]};set(&mut view,9);assert(view.items[0]==9);}'),
    ('receiver_slice_shared_mutate', 'reject', 'struct View{items:[]i64;}fn set(v:&View,x:i64){(*v).items[0]=x;}fn main(){}'),
    ('receiver_stored_reference_return', 'accept', 'struct Holder{r:&i64;}fn get(h:&Holder)->&i64 borrows(h){return (*h).r;}fn main(){var a=7;var h=Holder{r:&a};assert(*get(&h)==7);}'),
    ('receiver_stored_reference_retarget', 'accept', 'struct Holder{r:&i64;}fn retarget(h:&mut Holder,src:&i64) stores(h,src){(*h).r=src;}fn main(){var a=7;var b=9;var h=Holder{r:&a};retarget(&mut h,&b);assert(*h.r==9);}'),
    ('receiver_stored_reference_shared_retarget', 'reject', 'struct Holder{r:&i64;}fn retarget(h:&Holder,src:&i64){(*h).r=src;}fn main(){}'),
    ('stored_reference_reassign', 'accept', 'struct Holder{r:&i64;}fn main(){var a=7;var b=9;var h=Holder{r:&a};h.r=&b;assert(*h.r==9);}'),
    ('stored_reference_reassign_dead', 'reject', 'struct Holder{r:&i64;}fn main(){var a=7;var h=Holder{r:&a};{var b=9;h.r=&b;}assert(*h.r==7);}'),
])
STORE_DIAGNOSTICS.update({
    'receiver_slice_shared_mutate':'shared reference',
    'receiver_stored_reference_shared_retarget':'immutable',
    'stored_reference_reassign_dead':'outlive',
})

SLICE_CASES.extend([
    ('nested_slice_read', 'accept', 'fn main(){var a=[2]i64{7,9};var rows=[1][]i64{a[:]};var s=rows[:];assert(s[0][0]==7 && s[0][1]==9);}'),
    ('nested_slice_external_address_return', 'accept', 'fn get(x:[]i64)->&i64 borrows(x){var rows=[1][]i64{x};var s=rows[:];return &s[0][0];}fn main(){var a=[1]i64{7};let r=get(a[:]);assert(*r==7);}'),
    ('nested_slice_local_address_return', 'reject', 'fn bad(x:[]i64)->&i64 borrows(x){var a=[1]i64{7};var rows=[1][]i64{a[:]};var s=rows[:];return &s[0][0];}fn main(){}'),
    ('nested_slice_local_slot_return', 'reject', 'fn bad(x:[]i64)->&[]i64 borrows(x){var rows=[1][]i64{x};var s=rows[:];return &s[0];}fn main(){}'),
    ('nested_slice_short_replacement', 'reject', 'fn main(){var a=[1]i64{7};var rows=[1][]i64{a[:]};var s=rows[:];{var b=[1]i64{9};s[0]=b[:];}}'),
    ('nested_slice_retained_inner_mutation', 'reject', 'fn main(){var a=[1]i64{7};var b=[1]i64{9};var rows=[1][]i64{a[:]};var s=rows[:];s[0]=b[:];b[0]=11;}'),
    ('recursive_slice_read', 'accept', 'struct Node{kids:[]Node;value:i64;}fn main(){var none=[0]Node{};var leaf=Node{kids:none[:],value:7};var kids=[1]Node{leaf};var root=Node{kids:kids[:],value:9};assert(root.kids[0].value==7);}'),
    ('recursive_slice_short_replacement', 'reject', 'struct Node{kids:[]Node;value:i64;}fn main(){var none=[0]Node{};var root=Node{kids:none[:],value:7};{var shortnone=[0]Node{};var short=[1]Node{Node{kids:shortnone[:],value:9}};root.kids=short[:];}}'),
])
STORE_DIAGNOSTICS.update({
    'nested_slice_short_replacement':'assigned borrow may outlive local storage',
    'nested_slice_retained_inner_mutation':'conflicts',
    'recursive_slice_short_replacement':'assigned borrow may outlive local storage',
})

SLICE_CASES.append(('recursive_slice_reference_initializer','reject','struct Node{next:[]Node;r:&i64;}fn main(){let node=new[Node]();}'))
STORE_DIAGNOSTICS['recursive_slice_reference_initializer']='reference storage requires an explicit initializer'


SLICE_CASES.extend([
    ('mutual_slice_read', 'accept', 'struct Left{right:[]Right;value:i64;}struct Right{left:[]Left;value:i64;}fn main(){var empty=[0]Left{};var right=Right{left:empty[:],value:7};var rights=[1]Right{right};var left=Left{right:rights[:],value:9};assert(left.right[0].value==7);}'),
    ('mutual_slice_reference_initializer', 'reject', 'struct Left{right:[]Right;}struct Right{left:[]Left;r:&i64;}fn main(){let node=new[Left]();}'),
    ('recursive_slice_external_address_return', 'accept', 'struct Node{kids:[]Node;value:i64;}fn get(x:[]Node)->&i64 borrows(x){var root=Node{kids:x,value:9};return &root.kids[0].value;}fn main(){var none=[0]Node{};var leaf=Node{kids:none[:],value:7};var kids=[1]Node{leaf};let r=get(kids[:]);assert(*r==7);}'),
    ('recursive_slice_local_field_return', 'reject', 'struct Node{kids:[]Node;value:i64;}fn bad(x:[]Node)->&i64 borrows(x){var root=Node{kids:x,value:9};return &root.value;}fn main(){}'),
    ('recursive_slice_retained_backing_mutation', 'reject', 'struct Node{kids:[]Node;value:i64;}fn main(){var none=[0]Node{};var leaf=Node{kids:none[:],value:7};var kids=[1]Node{leaf};var root=Node{kids:kids[:],value:9};kids[0].value=11;}'),
    ('nested_slice_external_descriptor_return', 'accept', 'fn get(x:[]i64)->[]i64 borrows(x){var rows=[1][]i64{x};var s=rows[:];return s[0];}fn main(){var a=[1]i64{7};let r=get(a[:]);assert(r[0]==7);}'),
    ('nested_slice_computed_descriptor_return', 'accept', 'fn identity(s:[][]i64)->[][]i64 borrows(s){return s;}fn get(x:[]i64)->[]i64 borrows(x){var rows=[1][]i64{x};return identity(rows[:])[0];}fn main(){var a=[1]i64{7};let r=get(a[:]);assert(r[0]==7);}'),
    ('nested_slice_local_descriptor_return', 'reject', 'fn bad(x:[]i64)->[]i64 borrows(x){var a=[1]i64{7};var rows=[1][]i64{a[:]};var s=rows[:];return s[0];}fn main(){}'),
])
STORE_DIAGNOSTICS.update({
    'mutual_slice_reference_initializer':'reference storage requires an explicit initializer',
    'recursive_slice_local_field_return':'outlive',
    'recursive_slice_retained_backing_mutation':'conflicts',
    'nested_slice_local_descriptor_return':'outlive',
})

STORE_DIAGNOSTICS.update({
    'slice_short_payload_store':'assigned borrow may outlive local storage',
    'slice_retained_payload_mutation':'conflicts',
    'slice_array_mutation_while_borrowed':'conflicts',
    'slice_shared_descriptor_mutable_copy':'shared reference',
    'slice_shared_descriptor_mutable_address':'shared path',
})

for contract in (False, True):
    header='fn set(s:&mut []&i64,x:&i64)'+(' stores(s,x)' if contract else '')
    body='{(*s)[0]=x;}'
    main='fn main(){var a=7;var b=9;var refs=[1]&i64{&a};{var s=refs[:];set(&mut s,&b);assert(*s[0]==9);}assert(*refs[0]==9);}' if contract else 'fn main(){}'
    name='slice_store_'+('complete_contract' if contract else 'missing_contract')
    SLICE_CASES.append((name,'accept' if contract else 'reject',header+body+main))
    if not contract:STORE_DIAGNOSTICS[name]='matching stores'


SLICE_CASES.extend([
    ('plain_slice_local_backing_return', 'reject', 'fn bad(x:[]i64)->[]i64 borrows(x){var a=[1]i64{7};return a[:];}fn main(){}'),
    ('plain_slice_empty_local_backing_return', 'reject', 'fn bad(x:[]i64)->[]i64 borrows(x){var a=[0]i64{};return a[:];}fn main(){}'),
    ('plain_slice_zero_length_local_return', 'reject', 'fn bad(x:[]i64)->[]i64 borrows(x){var a=[1]i64{7};return a[0:0];}fn main(){}'),
    ('plain_slice_empty_value_return', 'accept', 'fn empty()->[]i64 borrows(){return []i64{};}fn main(){let s=empty();assert(len(s)==0);}'),
    ('plain_slice_empty_binding_return', 'accept', 'fn empty()->[]i64 borrows(){let s=[]i64{};return s;}fn main(){let s=empty();assert(len(s)==0);}'),
    ('nested_slice_stores_return_missing_source', 'reject', 'fn bad(dst:&mut [][]i64,src:[]i64)->[]i64 borrows(dst) stores(dst,src){(*dst)[0]=src;return (*dst)[0];}fn main(){}'),
])
STORE_DIAGNOSTICS.update({name:'outlive' for name in ('plain_slice_local_backing_return','plain_slice_empty_local_backing_return','plain_slice_zero_length_local_return','nested_slice_stores_return_missing_source')})


SLICE_CASES.extend([
    ('generic_recursive_slice_read', 'accept', 'struct Node[T]{kids:[]Node[T];value:T;}fn main(){var none=[0]Node[i64]{};var leaf=Node[i64]{kids:none[:],value:7};var kids=[1]Node[i64]{leaf};var root=Node[i64]{kids:kids[:],value:9};assert(root.kids[0].value==7);}'),
    ('generic_recursive_reference_initializer', 'reject', 'struct Node[T]{kids:[]Node[T];value:T;}fn main(){let node=new[Node[&i64]]();}'),
    ('enum_slice_external_descriptor_return', 'accept', 'enum View{None;Some([]i64);}fn get(x:[]i64)->[]i64 borrows(x){var views=[1]View{View.Some(x)};var s=views[:];match(s[0]){View.None=>{return []i64{};}View.Some(v)=>{return v;}}}fn main(){var a=[1]i64{7};let r=get(a[:]);assert(r[0]==7);}'),
    ('enum_slice_local_descriptor_return', 'reject', 'enum View{None;Some([]i64);}fn bad(x:[]i64)->[]i64 borrows(x){var a=[1]i64{7};var views=[1]View{View.Some(a[:])};var s=views[:];match(s[0]){View.None=>{return []i64{};}View.Some(v)=>{return v;}}}fn main(){}'),
    ('depth3_slice_external_descriptor_return', 'accept', 'fn get(x:[]i64)->[]i64 borrows(x){var rows=[1][]i64{x};var layers=[1][][]i64{rows[:]};var s=layers[:];return s[0][0];}fn main(){var a=[1]i64{7};let r=get(a[:]);assert(r[0]==7);}'),
    ('depth3_slice_local_descriptor_return', 'reject', 'fn bad(x:[]i64)->[]i64 borrows(x){var a=[1]i64{7};var rows=[1][]i64{a[:]};var layers=[1][][]i64{rows[:]};var s=layers[:];return s[0][0];}fn main(){}'),
    ('nested_slice_shared_mutable_copy', 'reject', 'fn bad(s:&[][]i64){let inner=(*s)[0];inner[0]=9;}fn main(){}'),
    ('nested_slice_live_inner_alias', 'reject', 'fn main(){var a=[1]i64{7};var rows=[1][]i64{a[:]};var s=rows[:];let inner=s[0];s[0][0]=9;assert(inner[0]==9);}'),
    ('nested_slice_released_inner_alias', 'accept', 'fn main(){var a=[1]i64{7};var rows=[1][]i64{a[:]};var s=rows[:];{let inner=s[0];inner[0]=8;}s[0][0]=9;assert(s[0][0]==9);}'),
])
STORE_DIAGNOSTICS.update({
    'generic_recursive_reference_initializer':'reference storage requires an explicit initializer',
    'enum_slice_local_descriptor_return':'outlive',
    'depth3_slice_local_descriptor_return':'outlive',
    'nested_slice_live_inner_alias':'conflicts',
    'nested_slice_shared_mutable_copy':'cannot mutate or move through a shared reference',
})


SLICE_CASES.extend([
    ('depth3_slice_local_descriptor_address_return','reject','fn bad(x:[]i64)->&[]i64 borrows(x){var rows=[1][]i64{x};var layers=[1][][]i64{rows[:]};var s=layers[:];return &s[0][0];}fn main(){}'),
    ('depth3_slice_intermediate_descriptor_return','reject','fn bad(x:[]i64)->[][]i64 borrows(x){var rows=[1][]i64{x};var layers=[1][][]i64{rows[:]};var s=layers[:];return s[0];}fn main(){}'),
    ('depth3_slice_computed_descriptor_return','accept','fn identity(s:[][][]i64)->[][][]i64 borrows(s){return s;}fn get(x:[]i64)->[]i64 borrows(x){var rows=[1][]i64{x};var layers=[1][][]i64{rows[:]};return identity(layers[:])[0][0];}fn main(){var a=[1]i64{7};let r=get(a[:]);assert(r[0]==7);}'),
])
STORE_DIAGNOSTICS.update({name:'outlive' for name in ('depth3_slice_local_descriptor_address_return','depth3_slice_intermediate_descriptor_return')})


SLICE_CASES.extend([
    ('depth3_slice_computed_local_address_return','reject','fn identity(s:[][][]i64)->[][][]i64 borrows(s){return s;}fn bad(x:[]i64)->&[]i64 borrows(x){var rows=[1][]i64{x};var layers=[1][][]i64{rows[:]};return &identity(layers[:])[0][0];}fn main(){}'),
    ('depth3_slice_computed_local_payload_return','reject','fn identity(s:[][][]i64)->[][][]i64 borrows(s){return s;}fn bad(x:[]i64)->[]i64 borrows(x){var a=[1]i64{7};var rows=[1][]i64{a[:]};var layers=[1][][]i64{rows[:]};return identity(layers[:])[0][0];}fn main(){}'),
    ('depth3_slice_computed_intermediate_return','reject','fn identity(s:[][][]i64)->[][][]i64 borrows(s){return s;}fn bad(x:[]i64)->[][]i64 borrows(x){var rows=[1][]i64{x};var layers=[1][][]i64{rows[:]};return identity(layers[:])[0];}fn main(){}'),
    ('depth3_slice_resliced_call_descriptor_return','accept','fn tail(s:[][][]i64)->[][][]i64 borrows(s){return s[0:];}fn get(x:[]i64)->[]i64 borrows(x){var rows=[1][]i64{x};var layers=[1][][]i64{rows[:]};return tail(layers[:])[0][0];}fn main(){var a=[1]i64{7};let r=get(a[:]);assert(r[0]==7);}'),
    ('slice_exact_overdeclared_source_return','accept','fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return a;}fn get(x:[]i64)->[]i64 borrows(x){var local=[1]i64{9};return first(x,local[:]);}fn main(){var a=[1]i64{7};let r=get(a[:]);assert(r[0]==7);}'),
])
STORE_DIAGNOSTICS.update({name:'outlive' for name in ('depth3_slice_computed_local_address_return','depth3_slice_computed_local_payload_return','depth3_slice_computed_intermediate_return')})


STORE_DIAGNOSTICS['depth3_slice_computed_local_address_return']='conflicts'
SLICE_CASES.extend([
    ('depth3_slice_bound_local_address_return','reject','fn identity(s:[][][]i64)->[][][]i64 borrows(s){return s;}fn bad(x:[]i64)->&[]i64 borrows(x){var rows=[1][]i64{x};var layers=[1][][]i64{rows[:]};var tmp=identity(layers[:]);return &tmp[0][0];}fn main(){}'),
    ('slice_identity_external_descriptor_address','accept','fn identity(s:[][]i64)->[][]i64 borrows(s){return s;}fn get(x:[][]i64)->&[]i64 borrows(x){var tmp=identity(x);return &tmp[0];}fn main(){var a=[1]i64{7};var rows=[1][]i64{a[:]};let r=get(rows[:]);assert((*r)[0]==7);}'),
])
STORE_DIAGNOSTICS['depth3_slice_bound_local_address_return']='outlive'


SLICE_CASES.extend([
    ('depth3_slice_forward_projection_return','accept','fn get(x:[]i64)->[]i64 borrows(x){var rows=[1][]i64{x};var layers=[1][][]i64{rows[:]};return identity(layers[:])[0][0];}fn identity(s:[][][]i64)->[][][]i64 borrows(s){return s;}fn main(){var a=[1]i64{7};let r=get(a[:]);assert(r[0]==7);}'),
    ('depth3_slice_generic_projection_return','accept','fn identity[T](s:[]T)->[]T borrows(s){return s;}fn get(x:[]i64)->[]i64 borrows(x){var rows=[1][]i64{x};var layers=[1][][]i64{rows[:]};return identity[[][]i64](layers[:])[0][0];}fn main(){var a=[1]i64{7};let r=get(a[:]);assert(r[0]==7);}'),
])


# Straight-line aliases retain the original parameter origin, including unused
# aliases of other parameters. Unsupported statements retain opaque summaries.
SLICE_CASES.extend([
 ('slice_alias_chain_return','accept','fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){let copy=a;var tail=copy[0:];let result=tail[:];return result;}fn get(x:[]i64)->[]i64 borrows(x){var local=[1]i64{9};return first(x,local[:]);}fn main(){var a=[1]i64{7};assert(get(a[:])[0]==7);}'),
 ('slice_alias_unused_other_origin','accept','fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){let unused=b;let copy=a;return copy;}fn get(x:[]i64)->[]i64 borrows(x){var local=[1]i64{9};return first(x,local[:]);}fn main(){var a=[1]i64{7};assert(get(a[:])[0]==7);}'),
 ('slice_alias_second_origin','accept','fn second(a:[]i64,b:[]i64)->[]i64 borrows(a,b){let first=a;let next=b;var result=next;return result;}fn get(x:[]i64)->[]i64 borrows(x){var local=[1]i64{9};return second(local[:],x);}fn main(){var a=[1]i64{7};assert(get(a[:])[0]==7);}'),
 ('depth3_slice_alias_projection','accept','fn identity(s:[][][]i64)->[][][]i64 borrows(s){let copy=s;var result=copy[:];return result;}fn get(x:[]i64)->[]i64 borrows(x){var rows=[1][]i64{x};var layers=[1][][]i64{rows[:]};return identity(layers[:])[0][0];}fn main(){var a=[1]i64{7};assert(get(a[:])[0]==7);}'),
 ('slice_alias_local_origin_escape','reject','fn second(a:[]i64,b:[]i64)->[]i64 borrows(a,b){let unused=a;let copy=b;return copy;}fn bad(x:[]i64)->[]i64 borrows(x){var local=[1]i64{9};return second(x,local[:]);}fn main(){}'),
 ('slice_alias_reassignment_opaque','reject','fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){var copy=a;copy=b;return copy;}fn bad(x:[]i64)->[]i64 borrows(x){var local=[1]i64{9};return first(x,local[:]);}fn main(){}'),
 ('slice_alias_effect_opaque','reject','fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){let copy=a;assert(true);return copy;}fn bad(x:[]i64)->[]i64 borrows(x){var local=[1]i64{9};return first(x,local[:]);}fn main(){}'),
 ('slice_alias_dynamic_reslice_opaque','reject','fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){let copy=a;let n=0;return copy[n:];}fn bad(x:[]i64)->[]i64 borrows(x){var local=[1]i64{9};return first(x,local[:]);}fn main(){}'),
])
for aliases, expected in ((30,'accept'),(31,'reject')):
    body=''.join('let c%d=%s;'%(i, 'a' if i==0 else 'c%d'%(i-1)) for i in range(aliases))
    program='fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){'+body+'return c%d;}'%(aliases-1)
    program+='fn get(x:[]i64)->[]i64 borrows(x){var local=[1]i64{9};return first(x,local[:]);}fn main(){var a=[1]i64{7};assert(get(a[:])[0]==7);}'
    SLICE_CASES.append(('slice_alias_capacity_%d'%aliases,expected,program))
STORE_DIAGNOSTICS.update({name:'outlive' for name, expected, _ in SLICE_CASES if name.startswith('slice_alias_') and expected=='reject'})

SLICE_CASES.extend([
 ('slice_alias_shared_subtree_mutation','reject','fn identity(s:[][]i64)->[][]i64 borrows(s){let copy=s;var result=copy[:];return result;}fn bad(s:&[][]i64){let copy=identity(*s);let inner=copy[0];inner[0]=9;}fn main(){}'),
 ('slice_alias_shadow_parameter','reject','fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){let a=b;return a;}fn bad(x:[]i64)->[]i64 borrows(x){var local=[1]i64{9};return first(x,local[:]);}fn main(){}'),
 ('slice_alias_duplicate_name','reject','fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){let copy=a;let copy=b;return copy;}fn bad(x:[]i64)->[]i64 borrows(x){var local=[1]i64{9};return first(x,local[:]);}fn main(){}'),
 ('slice_alias_truncated_reslice','reject','fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){let copy=a[:;return copy;}fn main(){}'),
 ('slice_alias_long_body_opaque','reject','fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){'+'assert(true);'*100+'let copy=a;return copy;}fn bad(x:[]i64)->[]i64 borrows(x){var local=[1]i64{9};return first(x,local[:]);}fn main(){}'),
])
STORE_DIAGNOSTICS['slice_alias_long_body_opaque']='outlive'
STORE_DIAGNOSTICS.update({'slice_alias_shared_subtree_mutation':'cannot mutate or move through a shared reference','slice_alias_duplicate_name':'duplicate local declaration','slice_alias_truncated_reslice':'expected identifier'})


# Branch proofs retain every possible returned source, excluding unused contracts.
for name,body,expected in [
 ('union','if(flag){return a;}else{return b;}','accept'),
 ('early','if(flag){return a;}return b;','accept'),
 ('negated','if(!flag){return b;}else{return a;}','accept'),
 ('sibling_alias','if(flag){let copy=a[:];return copy;}else{let copy=b[0:];return copy;}','accept'),
 ('nested','if(flag){if(other){return a;}else{return b;}}else{return b;}','accept'),
 ('same_origin','if(flag){return a;}else{return a;}','accept'),
 ('hidden_local','if(flag){return a;}else{return c;}','reject'),
 ('literal_other_path','if(true){return a;}else{return c;}','reject'),
 ('effect_opaque','if(flag){assert(true);return a;}else{return b;}','reject'),
 ('dynamic_condition_opaque','if(flag==other){return a;}else{return b;}','reject'),
]:
    program=('fn pick(a:[]i64,b:[]i64,c:[]i64,flag:bool,other:bool)->[]i64 borrows(a,b,c){'+body+'}'
      'fn get(x:[]i64,y:[]i64,flag:bool,other:bool)->[]i64 borrows(x,y){var local=[1]i64{11};return pick(x,y,local[:],flag,other);}'
      'fn main(){var a=[1]i64{7};var b=[1]i64{9};')
    if expected=='accept':
        first=7 if name!='nested' else 9
        second=7 if name=='same_origin' else 9
        program+=f'assert(get(a[:],b[:],true,false)[0]=={first});assert(get(a[:],b[:],false,true)[0]=={second});'
    program+='}'
    case='slice_branch_'+name
    SLICE_CASES.append((case,expected,program))
    if expected=='reject':STORE_DIAGNOSTICS[case]='outlive'
# The top-level block consumes one depth; exhaustion must use opaque provenance.
for depth,expected in [(16,'accept'),(17,'reject')]:
    body='{'*(depth-1)+'return a;'+'}'*(depth-1)
    case='slice_branch_depth_'+str(depth)
    program='fn pick(a:[]i64,b:[]i64)->[]i64 borrows(a,b){'+body+'}fn get(x:[]i64)->[]i64 borrows(x){var local=[1]i64{9};return pick(x,local[:]);}fn main(){var a=[1]i64{7};assert(get(a[:])[0]==7);}'
    SLICE_CASES.append((case,expected,program))
    if expected=='reject':STORE_DIAGNOSTICS[case]='outlive'
# An origin in bit 31 must remain a positive mask, not an argument index.
params=','.join(['unused:[]i64']+[f'q{i}:bool' for i in range(30)]+['source:[]i64'])
args=','.join(['local[:]']+['false']*30+['x'])
SLICE_CASES.append(('slice_branch_bit31','accept','fn pick('+params+')->[]i64 borrows(unused,source){if(q0){return source;}else{return source;}}fn get(x:[]i64)->[]i64 borrows(x){var local=[1]i64{9};return pick('+args+');}fn main(){var a=[1]i64{7};assert(get(a[:])[0]==7);}'))


SLICE_CASES.extend([
 ('slice_branch_continuing_alias','accept','fn pick(a:[]i64,b:[]i64,c:[]i64,flag:bool)->[]i64 borrows(a,b,c){let copy=a;if(flag){return copy;}else{let unused=c;}return b;}fn get(x:[]i64,y:[]i64,flag:bool)->[]i64 borrows(x,y){var local=[1]i64{11};return pick(x,y,local[:],flag);}fn main(){var a=[1]i64{7};var b=[1]i64{9};assert(get(a[:],b[:],true)[0]==7);assert(get(a[:],b[:],false)[0]==9);}'),
 ('slice_branch_nested_continuation','accept','fn pick(a:[]i64,b:[]i64,c:[]i64,flag:bool,other:bool)->[]i64 borrows(a,b,c){if(flag){if(other){return a;}}return b;}fn get(x:[]i64,y:[]i64,flag:bool,other:bool)->[]i64 borrows(x,y){var local=[1]i64{11};return pick(x,y,local[:],flag,other);}fn main(){var a=[1]i64{7};var b=[1]i64{9};assert(get(a[:],b[:],true,true)[0]==7);assert(get(a[:],b[:],true,false)[0]==9);assert(get(a[:],b[:],false,true)[0]==9);}'),
 ('slice_branch_nested_hidden_continuation','reject','fn pick(a:[]i64,b:[]i64,c:[]i64,flag:bool,other:bool)->[]i64 borrows(a,b,c){if(flag){if(other){return a;}}return c;}fn bad(x:[]i64,y:[]i64)->[]i64 borrows(x,y){var local=[1]i64{11};return pick(x,y,local[:],true,true);}fn main(){}'),
 ('slice_branch_shared_union_mutation','reject','fn pick(a:[][]i64,b:[][]i64,flag:bool)->[][]i64 borrows(a,b){if(flag){return a;}else{return b;}}fn bad(a:&[][]i64,b:[][]i64){let copy=pick(*a,b,false);let inner=copy[0];inner[0]=9;}fn main(){}'),
 ('depth3_slice_branch_union','accept','fn pick(a:[][][]i64,b:[][][]i64,c:[][][]i64,flag:bool)->[][][]i64 borrows(a,b,c){if(flag){let copy=a;return copy;}else{return b;}}fn get(x:[]i64,y:[]i64,flag:bool)->[]i64 borrows(x,y){var rowsx=[1][]i64{x};var rowsy=[1][]i64{y};var layersx=[1][][]i64{rowsx[:]};var layersy=[1][][]i64{rowsy[:]};var storage=[1]i64{11};var rowsz=[1][]i64{storage[:]};var unused=[1][][]i64{rowsz[:]};return pick(layersx[:],layersy[:],unused[:],flag)[0][0];}fn main(){var a=[1]i64{7};var b=[1]i64{9};assert(get(a[:],b[:],true)[0]==7);assert(get(a[:],b[:],false)[0]==9);}'),
])
STORE_DIAGNOSTICS.update({'slice_branch_nested_hidden_continuation':'outlive','slice_branch_shared_union_mutation':'cannot mutate or move through a shared reference'})


SLICE_CASES.append(('slice_branch_scope_escape','reject','fn pick(a:[]i64,b:[]i64,flag:bool)->[]i64 borrows(a,b){if(flag){let copy=a;}return copy;}fn main(){}'))
STORE_DIAGNOSTICS['slice_branch_scope_escape']='unknown variable'


# Iteration must retain both receiver identities for cross-call stored effects.
for omitted in ('old','new','none'):
    contracts=(' stores(p,src)' if omitted!='old' else '')+(' stores(other,src)' if omitted!='new' else '')
    program=('struct L0{r:&i64;}struct L1{next:&mut L0;}'
      'fn change(p:&mut L1,other:&mut L0,src:&i64,yes:bool) stores(p,other)'+contracts+
      '{var again=yes;while(again){(*p).next=other;again=false;}let alias=(*p).next;(*alias).r=src;}')
    main='fn main(){var a=7;var b=9;var c=11;'
    for yes in ('true','false'):
        main+='{var first=L0{r:&a};var second=L0{r:&b};var outer=L1{next:&mut first};change(&mut outer,&mut second,&c,'+yes+');assert(*(*outer.next).r==11);}'
    main+='}'
    case='nested_loop_store_'+omitted
    SLICE_CASES.append((case,'accept' if omitted=='none' else 'reject',program+(main if omitted=='none' else 'fn main(){}')))
    if omitted!='none':STORE_DIAGNOSTICS[case]='matching stores'
SLICE_CASES.extend([
 ('recursive_exclusive_slice_payload','accept','struct Node{kids:[]Node;r:&mut i64;}fn get(p:&mut Node)->&mut i64 borrows(p){return (*p).kids[0].r;}fn main(){var a=7;var b=9;var none=[0]Node{};var leaf=Node{kids:none[:],r:&mut a};var kids=[1]Node{leaf};var root=Node{kids:kids[:],r:&mut b};{let r=get(&mut root);*r=11;}assert(*root.kids[0].r==11);}'),
 ('recursive_shared_slice_payload','reject','struct Node{kids:[]Node;r:&mut i64;}fn bad(p:&Node){let r=(*p).kids[0].r;*r=11;}fn main(){}'),
 ('nested_raw_shared_read','accept','struct View{r:&i64;}fn main(){var a=7;let view=View{r:&a};let anchor=&view;unsafe{let copy=borrow_raw[&View](cast[*View](anchor),anchor);assert(*(*copy).r==7);}}'),
 ('nested_raw_shared_payload_mutation','reject','struct View{r:&mut i64;}fn bad(view:&View){unsafe{let copy=borrow_raw[&View](cast[*View](view),view);let r=(*copy).r;*r=9;}}fn main(){}'),
 ('nested_raw_local_payload_escape','reject','struct View{r:&i64;}fn bad(x:&i64)->&i64 borrows(x){var local=7;let view=View{r:&local};let anchor=&view;unsafe{let copy=borrow_raw[&View](cast[*View](anchor),anchor);return (*copy).r;}}fn main(){}'),
])
STORE_DIAGNOSTICS.update({'recursive_shared_slice_payload':'cannot mutate or move through a shared reference','nested_raw_shared_payload_mutation':'cannot mutate or move through a shared reference','nested_raw_local_payload_escape':'outlive'})


SLICE_CASES.extend([
 ('zero_reference_array_initializer','accept','import "std/mem";struct Wrap{empty:[0]&i64;value:i64;}fn main(){let empty=[0]&i64{};assert(len(empty)==0);let wrapper=Wrap{};assert(wrapper.value==0);{let owner=new[[0]&mut i64]();assert(len(*owner)==0);}assert(mem.owner_count()==0);}'),
 ('nonzero_reference_array_initializer','reject','fn main(){let bad=[1]&i64{};}'),
 ('zero_array_other_reference_initializer','reject','struct Wrap{empty:[0]&i64;r:&i64;}fn main(){let bad=Wrap{};}'),
])
STORE_DIAGNOSTICS.update({'nonzero_reference_array_initializer':'explicit initializer','zero_array_other_reference_initializer':'explicit initializer'})


# Moving a borrowed owner must transport payload loans as well as physical ones.
owned_nested='struct Mixed{r:&i64;p:own[i64];}struct Nested{p:own[&Mixed];}'
setup='let view=Mixed{r:x,p:new[i64](9)};let owner=new[&Mixed](&view);let nested=Nested{p:move owner};'
SLICE_CASES.extend([
 ('nested_owner_move_external_return','accept',owned_nested+'fn get(x:&i64)->&i64 borrows(x){'+setup+'return (**nested.p).r;}fn main(){var a=7;let r=get(&a);assert(*r==7);}'),
 ('nested_owner_move_slot_return','reject',owned_nested+'fn bad(x:&i64)->& &Mixed borrows(x){'+setup+'return &*nested.p;}fn main(){}'),
 ('nested_owner_move_heap_address_return','reject',owned_nested+'fn bad(x:&i64)->&i64 borrows(x){'+setup+'return &*(**nested.p).p;}fn main(){}'),
 ('nested_owner_move_shared_payload_mutation','reject','struct Mixed{r:&mut i64;}struct Nested{p:own[&Mixed];}fn bad(x:&mut i64){let view=Mixed{r:x};let owner=new[&Mixed](&view);let nested=Nested{p:move owner};let r=(**nested.p).r;*r=9;}fn main(){}'),
])
STORE_DIAGNOSTICS.update({'nested_owner_move_slot_return':'outlive','nested_owner_move_heap_address_return':'outlive','nested_owner_move_shared_payload_mutation':'cannot mutate or move through a shared reference'})


relocation_types='struct View{r:&i64;}struct Carrier{p:own[&View];}enum Box{None;Some(own[&View]);}'
for style,transport in [
 ('field','var source=Carrier{p:move owner};let result=Carrier{p:move source.p};return (**result.p).r;'),
 ('array','var source=[1]own[&View]{move owner};let result=Carrier{p:move source[0]};return (**result.p).r;'),
 ('slice','var source=[1]own[&View]{move owner};var values=source[:];let result=Carrier{p:move values[0]};return (**result.p).r;'),
 ('enum','let source=Box.Some(move owner);match(move source){Box.None=>{return x;}Box.Some(value)=>{let result=Carrier{p:move value};return (**result.p).r;}}'),
]:
    program=relocation_types+'fn get(x:&i64)->&i64 borrows(x){let view=View{r:x};let owner=new[&View](&view);'+transport+'}fn main(){var a=7;let r=get(&a);assert(*r==7);}'
    SLICE_CASES.append(('nested_owner_relocation_'+style,'accept',program))
SLICE_CASES.append(('nested_owner_relocation_shared_receiver','reject',relocation_types+'fn bad(source:&Carrier){let result=Carrier{p:move (*source).p};}fn main(){}'))
STORE_DIAGNOSTICS['nested_owner_relocation_shared_receiver']='cannot mutate or move through a shared reference'

SLICE_CASES.append(('nested_owner_relocation_computed_slice','accept','struct View{r:&i64;}struct Carrier{p:own[&View];}fn identity(s:[]Carrier)->[]Carrier borrows(s){return s;}fn get(x:&i64)->&i64 borrows(x){let view=View{r:x};let owner=new[&View](&view);var source=[1]Carrier{Carrier{p:move owner}};var values=source[:];let result=Carrier{p:move identity(values)[0].p};return (**result.p).r;}fn main(){var a=7;let r=get(&a);assert(*r==7);}'))

SLICE_CASES.append(('nested_owner_relocation_computed_receiver','accept','struct View{r:&i64;}struct Carrier{p:own[&View];}fn receiver(s:&mut Carrier)->&mut Carrier borrows(s){return s;}fn get(x:&i64)->&i64 borrows(x){let view=View{r:x};let owner=new[&View](&view);var source=[1]Carrier{Carrier{p:move owner}};var values=source[:];let result=Carrier{p:move (*receiver(&mut values[0])).p};return (**result.p).r;}fn main(){var a=7;let r=get(&a);assert(*r==7);}'))

SLICE_CASES.append(('nested_owner_relocation_computed_shared_receiver','reject','struct View{r:&i64;}struct Carrier{p:own[&View];}fn receiver(s:&Carrier)->&Carrier borrows(s){return s;}fn get(x:&i64)->&i64 borrows(x){let view=View{r:x};let owner=new[&View](&view);var source=[1]Carrier{Carrier{p:move owner}};var values=source[:];let result=Carrier{p:move (*receiver(&values[0])).p};return (**result.p).r;}fn main(){var a=7;let r=get(&a);assert(*r==7);}'))
STORE_DIAGNOSTICS['nested_owner_relocation_computed_shared_receiver']='cannot mutate or move through a shared reference'
SLICE_CASES.append(('nested_owner_relocation_local_payload','reject','struct View{r:&i64;}struct Carrier{p:own[&View];}fn receiver(s:&mut Carrier)->&mut Carrier borrows(s){return s;}fn get(x:&i64)->&i64 borrows(x){var local=9;let view=View{r:&local};let owner=new[&View](&view);var source=[1]Carrier{Carrier{p:move owner}};var values=source[:];let result=Carrier{p:move (*receiver(&mut values[0])).p};return (**result.p).r;}fn main(){var a=7;let r=get(&a);assert(*r==7);}'))
STORE_DIAGNOSTICS['nested_owner_relocation_local_payload']='outlive'
SLICE_CASES.append(('nested_owner_relocation_slot_escape','reject','struct View{r:&i64;}struct Carrier{p:own[&View];}fn receiver(s:&mut Carrier)->&mut Carrier borrows(s){return s;}fn get(x:&i64)->& &View borrows(x){let view=View{r:x};let owner=new[&View](&view);var source=[1]Carrier{Carrier{p:move owner}};var values=source[:];let result=Carrier{p:move (*receiver(&mut values[0])).p};return &*result.p;}fn main(){var a=7;let r=get(&a);}'))
STORE_DIAGNOSTICS['nested_owner_relocation_slot_escape']='outlive'
SLICE_CASES.append(('reference_identity_unused_local', 'accept', 'fn first(x:&i64,y:&i64)->&i64 borrows(x,y){return x;}fn get(x:&i64)->&i64 borrows(x){var local=9;return first(x,&local);}fn main(){var a=7;assert(*get(&a)==7);}'))
SLICE_CASES.append(('reference_branch_local_union', 'reject', 'fn choose(c:bool,x:&i64,y:&i64)->&i64 borrows(x,y){if(c){return x;}else{return y;}}fn get(x:&i64)->&i64 borrows(x){var local=9;return choose(true,x,&local);}fn main(){}'))
STORE_DIAGNOSTICS['reference_branch_local_union']='outlive'

SLICE_CASES.append(('empty_borrowed_direct', 'accept', 'enum Maybe{None;Some(&i64);}struct Container{p:own[Maybe];}fn put(dst:&mut Container){(*dst).p=new[Maybe](Maybe.None);}fn main(){}'))
SLICE_CASES.append(('empty_borrowed_named', 'accept', 'enum Maybe{None;Some(&i64);}struct Container{p:own[Maybe];}fn put(dst:&mut Container){let p=new[Maybe](Maybe.None);(*dst).p=move p;}fn main(){}'))
SLICE_CASES.append(('empty_borrowed_unit', 'accept', 'enum Maybe{None;Some(&i64);}struct Container{p:own[Maybe];}fn put(dst:&mut Maybe){let value=Maybe.None;*dst=value;}fn main(){}'))
SLICE_CASES.append(('empty_unit_return', 'accept', 'enum Maybe{None;Some(&i64);}fn empty()->Maybe borrows(){let v=Maybe.None;return v;}fn main(){match(empty()){Maybe.None=>{}Maybe.Some(r)=>{assert(false);}}}'))
SLICE_CASES.append(('empty_owner_return', 'accept', 'enum Maybe{None;Some(&i64);}fn empty()->own[Maybe] borrows(){let p=new[Maybe](Maybe.None);return move p;}fn main(){let p=empty();match(*p){Maybe.None=>{}Maybe.Some(r)=>{assert(false);}}}'))
SLICE_CASES.append(('nonempty_unit_local_escape', 'reject', 'enum Maybe{None;Some(&i64);}fn bad(dst:&mut Maybe){var local=7;let v=Maybe.Some(&local);*dst=v;}fn main(){}'))
SLICE_CASES.append(('empty_owner_physical_escape', 'reject', 'enum Maybe{None;Some(&i64);}fn bad()->&Maybe borrows(){let p=new[Maybe](Maybe.None);return &*p;}fn main(){}'))
STORE_DIAGNOSTICS.update({'nonempty_unit_local_escape':'outlive','empty_owner_physical_escape':'outlive'})

SLICE_CASES.append(('empty_borrowed_pending_index_move','reject','enum Maybe{None;Some(&i64);}fn consume(p:own[[2]Maybe])->usize{let gone=move p;return 0;}fn main(){var p=new[[2]Maybe]([2]Maybe{Maybe.None,Maybe.None});(*p)[consume(move p)]=Maybe.None;}'))
STORE_DIAGNOSTICS['empty_borrowed_pending_index_move']='owner moved while an access to its storage is pending'
SLICE_CASES.append(('empty_borrowed_live_address_move','reject','enum Maybe{None;Some(&i64);}fn main(){var p=new[Maybe](Maybe.None);let r=&*p;let gone=move p;}'))
STORE_DIAGNOSTICS['empty_borrowed_live_address_move']='conflicts'

SLICE_REPL_CASES = [('backing_forget',
  'var a=7;\nvar refs=[1]&i64{&a};\nvar s=refs[:];\n:forget refs\n:quit\n',
  '',
  {'live dependent loans': 1}),
 ('backing_mutation',
  'var a=7;\nvar b=9;\nvar refs=[1]&i64{&a};\nvar s=refs[:];\nrefs[0]=&b;\n:quit\n',
  '',
  {'conflicts': 1}),
 ('stored_source_release',
  'var a=7;\n'
  'var b=9;\n'
  'var refs=[1]&i64{&a};\n'
  'var s=refs[:];\n'
  's[0]=&b;\n'
  'b=11;\n'
  '*s[0]\n'
  ':forget s\n'
  ':forget refs\n'
  'b=13;\n'
  'b\n'
  ':quit\n',
  '9\n13\n',
  {'conflicts': 1}),
 ('stored_source_runtime_recovery',
  'var a=7;\n'
  'var b=9;\n'
  'var refs=[1]&i64{&a};\n'
  'var s=refs[:];\n'
  '{s[0]=&b;assert(false);}\n'
  '*s[0]\n'
  'b=11;\n'
  ':forget s\n'
  ':forget refs\n'
  'b=13;\n'
  'b\n'
  ':quit\n',
  '9\n13\n',
  {'assertion failed': 1, 'conflicts': 1}),
 ('stored_source_compile_recovery',
  'var a=7;\n'
  'var b=9;\n'
  'var refs=[1]&i64{&a};\n'
  'var s=refs[:];\n'
  's[0]=&b;\n'
  '{var c=13;s[0]=&c;}\n'
  '*s[0]\n'
  'b=11;\n'
  ':forget s\n'
  ':forget refs\n'
  'b=13;\n'
  'b\n'
  ':quit\n',
  '9\n13\n',
  {'assigned borrow may outlive local storage': 1, 'conflicts': 1}),
 ('identity_replacement',
  'fn identity(s:[]&i64)->[]&i64 borrows(s){return s;}\n'
  'var a=7;\n'
  'var b=9;\n'
  'var refs=[2]&i64{&a,&b};\n'
  'var s=identity(refs[:]);\n'
  's=identity(s);\n'
  '*s[0]\n'
  's=identity(s);\n'
  '*s[0]\n'
  's=identity(s);\n'
  '*s[0]\n'
  's=identity(s);\n'
  '*s[0]\n'
  'fn identity(s:[]&i64)->[]&i64 borrows(s){return s[1:];}\n'
  's=identity(s);\n'
  '*s[0]\n'
  ':forget refs\n'
  ':quit\n',
  '7\n7\n7\n7\n9\n',
  {'live dependent loans': 1})]


SLICE_REPL_CASES.extend([
 ('projection_source_replacement',
  'fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return a;}\n'
  'var a=[2]i64{7,8};\nvar b=[2]i64{9,10};\n'
  'first(a[:],b[:])[0]\n'
  'fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return b;}\n'
  'first(a[:],b[:])[0]\n:quit\n',
  '7\n9\n', {}),
 ('projection_opaque_replacement',
  'fn identity(s:[]i64)->[]i64 borrows(s){return s;}\n'
  'var a=[2]i64{7,9};\nidentity(a[:])[0]\n'
  'fn identity(s:[]i64)->[]i64 borrows(s){assert(true);let copy=s;return copy;}\n'
  'identity(a[:])[0]\n:quit\n',
  '7\n7\n', {}),
 ('projection_reslice_replacement',
  'fn identity(s:[]i64)->[]i64 borrows(s){return s;}\n'
  'var a=[2]i64{7,9};\nidentity(a[:])[0]\n'
  'fn identity(view:[]i64)->[]i64 borrows(view){return view[1:];}\n'
  'identity(a[:])[0]\n:quit\n',
  '7\n9\n', {}),
])

SLICE_REPL_CASES.extend([
 ('projection_existing_caller_source_replacement',
  'fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return a;}\n'
  'fn use(a:[]i64,b:[]i64)->[]i64 borrows(a){return first(a,b);}\n'
  'var a=[1]i64{7};\nvar b=[1]i64{9};\nuse(a[:],b[:])[0]\n'
  'fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return b;} fn trigger(a:[]i64,b:[]i64)->[]i64 borrows(a){return use(a,b);}\n'
  'use(a[:],b[:])[0]\n:quit\n',
  '7\n7\n', {'returned borrow may outlive local storage':1}),
 ('projection_existing_caller_opaque_replacement',
  'fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return a;}\n'
  'fn use(a:[]i64,b:[]i64)->[]i64 borrows(a){return first(a,b);}\n'
  'var a=[1]i64{7};\nvar b=[1]i64{9};\nuse(a[:],b[:])[0]\n'
  'fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){assert(true);let copy=a;return copy;} fn trigger(a:[]i64,b:[]i64)->[]i64 borrows(a){return use(a,b);}\n'
  'use(a[:],b[:])[0]\n:quit\n',
  '7\n7\n', {'returned borrow may outlive local storage':1}),
])


SLICE_REPL_CASES.extend([
 ('projection_alias_same_source_replacement',
  'fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return a;}\n'
  'fn use(a:[]i64,b:[]i64)->[]i64 borrows(a){return first(a,b);}\n'
  'var a=[2]i64{7,8};\nvar b=[2]i64{9,10};\nuse(a[:],b[:])[0]\n'
  'fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){let unused=b;var copy=a[1:];let result=copy[:];return result;}\n'
  'use(a[:],b[:])[0]\n:quit\n', '7\n8\n', {}),
 ('projection_alias_other_source_replacement',
  'fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){let copy=a;return copy;}\n'
  'fn use(a:[]i64,b:[]i64)->[]i64 borrows(a){return first(a,b);}\n'
  'var a=[1]i64{7};\nvar b=[1]i64{9};\nuse(a[:],b[:])[0]\n'
  'fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){let unused=a;let copy=b;return copy;}\n'
  'use(a[:],b[:])[0]\n:quit\n', '7\n7\n', {'returned borrow may outlive local storage':1}),
])

SLICE_REPL_CASES.extend([
 ('projection_revalidate_safe_caller_and_live_result',
  'fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return a;}\n'
  'fn use(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return first(a,b);}\n'
  'var a=[1]i64{7};\nvar b=[1]i64{9};\nvar past=use(a[:],b[:]);\npast[0]\n'
  'fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return b;}\n'
  'past[0]\n:forget a\n:forget past\nuse(a[:],b[:])[0]\n:forget a\n:quit\n',
  '7\n7\n9\n', {'live dependent loans':1}),
 ('projection_revalidate_updated_caller_batch',
  'fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return a;}\n'
  'fn use(a:[]i64,b:[]i64)->[]i64 borrows(a){return first(a,b);}\n'
  'var a=[1]i64{7};\nvar b=[1]i64{9};\nuse(a[:],b[:])[0]\n'
  'fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return b;} fn use(a:[]i64,b:[]i64)->[]i64 borrows(a){return a;}\n'
  'use(a[:],b[:])[0]\nfirst(a[:],b[:])[0]\n:quit\n', '7\n7\n9\n', {}),
])

SLICE_REPL_CASES.extend([
 ('projection_revalidate_multiple_replacements_rollback',
  'fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return a;}\n'
  'fn second(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return a;}\n'
  'fn valid(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return first(a,b);}\n'
  'fn restricted(a:[]i64,b:[]i64)->[]i64 borrows(a){return second(a,b);}\n'
  'var a=[1]i64{7};\nvar b=[1]i64{9};\nvalid(a[:],b[:])[0]\nrestricted(a[:],b[:])[0]\n'
  'fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return b;} fn second(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return b;}\n'
  'valid(a[:],b[:])[0]\nrestricted(a[:],b[:])[0]\nfirst(a[:],b[:])[0]\n:quit\n',
  '7\n7\n7\n7\n7\n', {'returned borrow may outlive local storage':1}),
 ('projection_revalidate_instantiated_generic_caller',
  'fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return a;}\n'
  'fn use[T](a:[]T,b:[]T)->[]T borrows(a){return first(a,b);}\n'
  'var a=[1]i64{7};\nvar b=[1]i64{9};\nuse[i64](a[:],b[:])[0]\n'
  'fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return b;}\n'
  'use[i64](a[:],b[:])[0]\n:quit\n', '7\n7\n', {'returned borrow may outlive local storage':1}),
 ('projection_revalidate_retained_owner_cleanup',
  'fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return a;}\n'
  'fn work(x:&i64)->i64{let owned=new[i64](*x);defer assert(*owned==7);return *owned;}\n'
  'var x=7;\nwork(&x)\n'
  'fn first(a:[]i64,b:[]i64)->[]i64 borrows(a,b){return b;}\n'
  'work(&x)\n:quit\n', '7\n7\n', {}),
])


SLICE_REPL_CASES.extend([
 ('projection_branch_union_expansion_rollback',
  'fn pick(a:[]i64,b:[]i64,flag:bool)->[]i64 borrows(a,b){return a;}\n'
  'fn middle(a:[]i64,b:[]i64,flag:bool)->[]i64 borrows(a){return pick(a,b,flag);}\n'
  'fn use(a:[]i64,b:[]i64,flag:bool)->[]i64 borrows(a){return middle(a,b,flag);}\n'
  'var a=[1]i64{7};\nvar b=[1]i64{9};\nuse(a[:],b[:],false)[0]\n'
  'fn pick(a:[]i64,b:[]i64,flag:bool)->[]i64 borrows(a,b){if(flag){return a;}else{return b;}}\n'
  'use(a[:],b[:],false)[0]\npick(a[:],b[:],false)[0]\n:quit\n',
  '7\n7\n7\n', {'returned borrow may outlive local storage':1}),
 ('projection_branch_union_narrowing',
  'fn pick(a:[]i64,b:[]i64,flag:bool)->[]i64 borrows(a,b){if(flag){return a;}else{return b;}}\n'
  'fn use(a:[]i64,b:[]i64,flag:bool)->[]i64 borrows(a,b){return pick(a,b,flag);}\n'
  'var a=[1]i64{7};\nvar b=[1]i64{9};\nuse(a[:],b[:],false)[0]\n'
  'fn pick(a:[]i64,b:[]i64,flag:bool)->[]i64 borrows(a,b){if(flag){return a;}else{return a;}}\n'
  'use(a[:],b[:],false)[0]\n:quit\n','9\n7\n',{}),
 ('projection_branch_same_union_swap',
  'fn pick(a:[]i64,b:[]i64,flag:bool)->[]i64 borrows(a,b){if(flag){return a;}else{return b;}}\n'
  'fn use(a:[]i64,b:[]i64,flag:bool)->[]i64 borrows(a,b){return pick(a,b,flag);}\n'
  'var a=[1]i64{7};\nvar b=[1]i64{9};\nuse(a[:],b[:],true)[0]\n'
  'fn pick(a:[]i64,b:[]i64,flag:bool)->[]i64 borrows(a,b){if(flag){return b;}else{return a;}}\n'
  'use(a[:],b[:],true)[0]\n:quit\n','7\n9\n',{}),
])

SLICE_REPL_CASES.append(('nested_owned_recursive_runtime_recovery','import "std/mem";\nstruct View{r:&i64;}\nstruct Node{kids:[]Node;payload:own[View];}\nfn set(dst:&mut Node,src:&i64) stores(dst,src){(*(*dst).payload).r=src;}\nvar a=7;\nvar b=9;\nvar none=[0]Node{};\nvar root=new[Node](Node{kids:none[:],payload:new[View](View{r:&a})});\n{set(&mut *root,&b);assert(false);}\n*(*(*root).payload).r\na=8;\nb=10;\n:forget root\na=8;\nb=10;\na\nb\nmem.owner_count()\n:forget none\n:quit\n','9\n8\n10\n0\n',{'assertion failed':1,'access conflicts with a live scoped reference':2}))

SLICE_REPL_CASES.append(('reference_identity_revalidation_rollback', 'fn choose(x:&i64,y:&i64)->&i64 borrows(x,y){return x;}\nfn caller(x:&i64)->&i64 borrows(x){var b=9;return choose(x,&b);}\nvar a=7;\n*caller(&a)\nfn choose(x:&i64,y:&i64)->&i64 borrows(x,y){return y;}\n*caller(&a)\n:quit\n', '7\n7\n', {'returned borrow may outlive local storage or violate its borrows contract': 1}))

SLICE_REPL_CASES.append(('borrowed_vector_binding_recovery', 'import vector "std/vector";\nimport "std/mem";\nvar a=7;\nvar b=9;\nvar values=vector.create[&i64]();\nvalues.append(&a);\nvalues.append(&b);\n{let popped=values.pop();assert(false);}\n**values.at(0)\na=8;\nb=10;\n:forget values\na=8;\nb=10;\na\nb\nmem.owner_count()\n:quit\n', '7\n8\n10\n0\n', {'assertion failed': 1, 'access conflicts with a live scoped reference': 2}))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend', type=Path, default=ROOT / 'build/cool-compiler')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--legacy', action='store_true')
    parser.add_argument('--unsafe-root-predicate', action='store_true', help='Private countermodel replacing explicit external-root identity with the disproven type predicate')
    parser.add_argument('--assert-expectations', action='store_true')
    parser.add_argument('--stores', action='store_true', help='Include nested receiver replacement and contract lifetime cases')
    parser.add_argument('--sanitize', action='store_true', help='Instrument the private production frontend with AddressSanitizer/UBSan')
    parser.add_argument('--all-engines', action='store_true', help='Run accepted positives on tree/VM/JIT/LLVM/LLVM-JIT and release AOT')
    parser.add_argument('--deep', action='store_true', help='Include depth-2/3/4 lifetime cases')
    parser.add_argument('--slices', action='store_true', help='Include borrowed slice element, lifetime, capability and stores cases')
    parser.add_argument('--repl', action='store_true', help='Audit persistent borrowed slice roots, forgetting and compile/runtime recovery')
    args = parser.parse_args()
    if args.repl and not args.slices: parser.error('--repl requires --slices')
    if args.slices: CASES.extend(SLICE_CASES)
    if args.deep: CASES.extend(DEEP_CASES)
    if args.stores: CASES.extend(STORE_CASES)
    assert len({name for name, _, _ in CASES}) == len(CASES)
    sources = sorted((ROOT/'compiler').glob('*.cool'))
    legacy_sources = sorted((ROOT/'language').glob('*.cool')) if args.legacy else []
    hash_sources = sources+legacy_sources+sorted((ROOT/'stdlib').rglob('*.cool'))
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in hash_sources}
    artifacts = [args.frontend.resolve(), ROOT/'build/compiler-host.o', ROOT/'build/language-runtime.o']
    artifact_hashes = {str(p): digest(p) for p in artifacts}
    env = {**os.environ, 'COOLC_COMPILER_BIN':str(ROOT/'coolc/seed/Compiler.BIN')}
    def run(cmd, **kw):
        return subprocess.run(list(map(str,cmd)),cwd=ROOT,env=env,capture_output=True,text=True,timeout=240,**kw)
    with tempfile.TemporaryDirectory(prefix='cool nested reference probe ') as directory:
        tmp=Path(directory);private=tmp/'compiler';private.mkdir()
        for original in sources:shutil.copy2(original,private/original.name)
        copies=[]
        for original in artifacts:
            copy=tmp/original.name;shutil.copy2(original,copy);copies.append(copy)
        assert all(digest(copy)==artifact_hashes[str(original)] for original,copy in zip(artifacts,copies))
        if args.unsafe_root_predicate:
            target=private/'16-references.cool';text=target.read_text()
            assert text.count('root.reference_external == 0')==1
            target.write_text(text.replace('root.reference_external == 0','(root.type != 0 && !IsReference(root.type))'))
        else:
            assert all((private/p.name).read_bytes()==p.read_bytes() for p in sources)
        manifest=tmp/'sources';manifest.write_text(''.join('__main\t'+str(p)+'\n' for p in sorted(private.glob('*.cool'))))
        ir=tmp/'compiler.ll';r=run([copies[0],'llvm-bundle',manifest,ir]);assert r.returncode==0,r
        frontend_flags=[]
        if args.sanitize:
            ir.write_text('\n'.join(line.replace(' {',' sanitize_address {') if line.startswith('define ') else line for line in ir.read_text().splitlines())+'\n')
            checked=tmp/'instrumented-frontend.ll'
            r=run(['clang','-Wno-override-module','-O1','-fsanitize=address','-S','-emit-llvm',ir,'-o',checked]);assert r.returncode==0,r
            assert '__asan_report_load' in checked.read_text() and '__asan_report_store' in checked.read_text()
            frontend_flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
            env.update(ASAN_OPTIONS='halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
        frontend=tmp/'probe-frontend';r=run(['clang','-Wno-override-module','-O2',*frontend_flags,ir,*copies[1:],'-lffi','-o',frontend]);assert r.returncode==0,r
        fronts=[('production',[frontend])]
        if args.legacy:
            seed=tmp/'language';seed.mkdir()
            for original in legacy_sources:shutil.copy2(original,seed/original.name)
            if args.unsafe_root_predicate:
                refs=seed/'References.cool';text=refs.read_text()
                assert text.count('!root->reference_external')==1
                refs.write_text(text.replace('!root->reference_external','(root->type && !IsReference(root->type))'))
            else:
                assert all((seed/p.name).read_bytes()==p.read_bytes() for p in legacy_sources)
            binary=tmp/'frontend.BIN';r=run([ROOT/'build/coolc',seed/'Native.cool',binary]);assert r.returncode==0,r
            fronts.append(('seed',[ROOT/'build/coolc','--run',binary]))
        control_source=next(source for name,_,source in CASES if name=='reference_parameter_slot_return')
        control=tmp/'production-slot-control.cool';control.write_text(control_source)
        controlled=run([copies[0],'check',control])
        assert controlled.returncode==2 and 'returned borrow may outlive local storage' in controlled.stderr,controlled
        observations=[]
        for front_name,front in fronts:
            runner=tmp/(front_name+'-runner')
            runner.write_text('#!/bin/sh\nexec '+shlex.join(list(map(str,front)))+' "$@"\n');runner.chmod(0o755)
            engine_env={**env,'COOL_FRONTEND':str(runner)}
            for name,expected,source in CASES:
                fixture=tmp/(name+'.cool');fixture.write_text(source);r=run([*front,'check',fixture]);assert r.returncode in (0,2),r
                observed='accept' if r.returncode==0 else 'reject'
                row=dict(frontend=front_name,name=name,expected=expected,observed=observed,matches_expectation=observed==expected,source=source,source_sha256=digest(fixture),check_exit=r.returncode,check_stdout=r.stdout,check_stderr=r.stderr)
                if expected=='reject':
                    diagnostic=('assigned borrow may outlive local storage' if name=='short_inner_escape' else 'cannot mutate or move through a shared reference' if name=='shared_outer_mutable_inner' else 'reference requires a tracked local or parameter root' if name=='temporary_owner_slot_return' else 'returned borrow may outlive local storage')
                    diagnostic=STORE_DIAGNOSTICS.get(name,diagnostic)
                    row.update(expected_diagnostic=diagnostic,matches_diagnostic=diagnostic in r.stderr)
                if observed=='accept' and expected=='accept':
                    r=run([*front,'run',fixture]);row.update(run_exit=r.returncode,run_stdout=r.stdout,run_stderr=r.stderr)
                    assert (r.returncode,r.stdout,r.stderr)==(0,'',''),row
                    if args.all_engines:
                        row['engine_runs']=[]
                        for engine in ('interp','jit','llvm','llvm-jit','O2'):
                            if engine=='O2':
                                program=tmp/(front_name+'-'+name+'-program')
                                command=[ROOT/'tools/cool','build','--release',fixture,'-o',program]
                            else:command=[ROOT/'tools/cool','run','--backend',engine,fixture]
                            result=subprocess.run(list(map(str,command)),cwd=ROOT,env=engine_env,capture_output=True,text=True,timeout=240)
                            assert (result.returncode,result.stdout,result.stderr)==(0,'',''),(front_name,name,engine,result)
                            if engine=='O2':result=run([program])
                            row['engine_runs'].append(dict(engine=engine,exit=result.returncode,stdout=result.stdout,stderr=result.stderr))
                            assert (result.returncode,result.stdout,result.stderr)==(0,'',''),(front_name,name,engine,result)
                # Accepted negative cases are intentionally never executed.
                observations.append(row);print(front_name,name,expected,observed)
        repl_observations=[]
        if args.repl:
            for front_name,front in fronts:
                for name,source,expected,errors in SLICE_REPL_CASES:
                    execution='repl-quiet'
                    if name=='borrowed_vector_binding_recovery':
                        execution='project_driver'
                        runner=tmp/(front_name+'-repl-runner')
                        runner.write_text('#!/bin/sh\nexec '+shlex.join(list(map(str,front)))+' "$@"\n');runner.chmod(0o755)
                        result=subprocess.run([str(ROOT/'tools/cool'),'repl'],cwd=ROOT,env={**env,'COOL_FRONTEND':str(runner)},input=source,capture_output=True,text=True,timeout=240)
                    else:result=run([*front,'repl-quiet'],input=source)
                    matches=(result.returncode==0 and result.stdout==expected and result.stderr.count('error:')==sum(errors.values()) and all(result.stderr.count(message)==count for message,count in errors.items()))
                    repl_observations.append(dict(frontend=front_name,execution=execution,name=name,source=source,expected_stdout=expected,expected_errors=errors,exit=result.returncode,stdout=result.stdout,stderr=result.stderr,matches_expectation=matches))
                    print(front_name,'repl',name,'PASS' if matches else 'FAIL')
        repl_lifecycle=None
        if args.repl:
            lifecycle=tmp/'slice-lifecycle.json'
            result=run(['python3',ROOT/'tools/test_repl_lifecycle.py','--compiler-ir',ir,'--borrowed-slices','--output',lifecycle])
            assert result.returncode==0,result
            repl_lifecycle=json.loads(lifecycle.read_text())
            print(result.stdout,end='')
        assert hashes=={str(p.relative_to(ROOT)):digest(p) for p in hash_sources},'source changed during audit'
        report=dict(source_sha256=hashes,artifact_sha256=artifact_hashes,private_ir_sha256=digest(ir),unsafe_root_predicate=args.unsafe_root_predicate,deep=args.deep,stores=args.stores,slices=args.slices,sanitize=args.sanitize,repl=args.repl,repl_observations=repl_observations,repl_lifecycle=repl_lifecycle,all_engines=args.all_engines,production_slot_control=dict(source=control_source,exit=controlled.returncode,stderr=controlled.stderr),observations=observations,gaps=[dict(frontend=r['frontend'],name=r['name'],kind='unsafe_acceptance' if r['observed']=='accept' else 'over_rejection') for r in observations if not r['matches_expectation']],method='Byte-identical copies of production/seed frontend sources, without feature bypasses. Optional explicit countermodel changes external-root authorization. Positive programs execute on tree and optional five engines/O2; accepted negatives never execute. Source hash stability, parameter-slot lifetime rejection, persistent REPL and allocation histories are verified. Sanitizer instruments the production frontend; generated program runtime sanitizer coverage is supplied by complementary suites.')
        if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
        if args.assert_expectations:
            failures=[dict(frontend=r['frontend'],name=r['name'],expected=r['expected'],observed=r['observed'],diagnostic_matches=r.get('matches_diagnostic',True)) for r in observations if not r['matches_expectation'] or not r.get('matches_diagnostic',True)]
            assert not failures,failures
            assert all(row['matches_expectation'] for row in repl_observations),repl_observations
    return 0


if __name__=='__main__':raise SystemExit(main())
