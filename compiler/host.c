// OS, memory, C ABI and executable-page adapter for the new-syntax compiler.
// Parsing, checking, interpretation and code generation remain in Cool.
#include <stdint.h>
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <crt_externs.h>
#include <sys/mman.h>
#include <pthread.h>
#include "../language/ffi.h"
#include "../language/memory.h"
#include "../language/repl_io.h"
const char *NativeReplResolve(const char *package) { return cool_repl_resolve(package); }
static void host_fail(const char *message) { fprintf(stderr,"cool-host: %s\n",message); exit(70); }
void *CAlloc(int64_t size) { if(size<0)host_fail("negative allocation"); void *p=calloc(1,size ? (size_t)size : 1); if(!p)host_fail("allocation failed"); return p; }
void *MAlloc(int64_t size) { return CAlloc(size); }
void Free(void *p) { free(p); }
void *MemSet(void *p,int64_t value,int64_t size) { return memset(p,(int)value,(size_t)size); }
void *MemCpy(void *p,const void *q,int64_t size) { return memcpy(p,q,(size_t)size); }
int64_t StrLen(const char *s) { return (int64_t)strlen(s); }
int64_t StrCmp(const char *a,const char *b) { return strcmp(a,b); }
char *StrNew(const char *s) { char *p=CAlloc((int64_t)strlen(s)+1); strcpy(p,s); return p; }
void *NativeCompilerState(int64_t size) { static void *state; if(!state) { setbuf(stdout,NULL); state=CAlloc(size); } return state; }
void *FileRead(const char *path,int64_t *size,void *attrs) {
    (void)attrs; FILE *f=fopen(path,"rb"); if(!f)return NULL;
    if(fseek(f,0,SEEK_END))host_fail("file seek"); long n=ftell(f); if(n<0)host_fail("file size"); rewind(f);
    char *p=CAlloc(n+1); if(fread(p,1,(size_t)n,f)!=(size_t)n)host_fail("file read"); fclose(f); if(size)*size=n; return p;
}
int64_t FileWrite(const char *path,const void *data,int64_t size) {
    if(size<0)return 0; FILE *f=fopen(path,"wb"); if(!f)return 0;
    size_t n=fwrite(data,1,(size_t)size,f); int closed=fclose(f); return n==(size_t)size && !closed;
}
int64_t NativeWrite(int64_t fd,const void *data,int64_t size) { return write((int)fd,data,(size_t)size); }
void NativeExit(int64_t code) { exit((int)code); }
extern void CoolArgsStart(int64_t start);
void NativeSetProgramArgs(int64_t start) { CoolArgsStart(start); }
int64_t NativeArgCount(void) { return *_NSGetArgc(); }
char *NativeArg(int64_t i) { return i>=0 && i<*_NSGetArgc() ? (*_NSGetArgv())[i] : NULL; }
int64_t NativeGetChar(void) { return getchar(); }
int64_t NativeParseFloat(const char *text,int64_t *ok) { return cool_parse_float(text,ok); }
int64_t NativeNumericCast(int64_t bits,int64_t from,int64_t to,int64_t *ok) { return cool_numeric_cast(bits,from,to,ok); }
void NativePrintFloat(int64_t bits) { printf("%.17g",cool_double(bits)); }
int64_t NativeForeignCall(const char *name,int64_t result,const int64_t *types,const int64_t *values,int64_t count,int64_t *ok) { return cool_foreign_call(name,result,types,values,count,ok); }
int64_t NativeMemoryRead(int64_t address,int64_t type) { return cool_memory_read(address,type); }
void NativeMemoryWrite(int64_t address,int64_t type,int64_t value) { cool_memory_write(address,type,value); }
void *NativeJitAlloc(int64_t size) {
    void *p=mmap(NULL,size>0 ? (size_t)size : 1,PROT_READ|PROT_WRITE|PROT_EXEC,MAP_PRIVATE|MAP_ANON|MAP_JIT,-1,0);
    if(p==MAP_FAILED)host_fail("JIT allocation"); return p;
}
void NativeJitFree(void *code,int64_t size) {
    if (!code) return;
    if (size <= 0 || munmap(code,(size_t)size) != 0) host_fail("JIT release");
}
void NativeJitCommit(void *code,const void *scratch,int64_t size) {
    if(size<0)host_fail("JIT length"); pthread_jit_write_protect_np(0); memcpy(code,scratch,(size_t)size);
    __builtin___clear_cache(code,(char *)code+size); pthread_jit_write_protect_np(1);
}
extern int64_t CoolCompute(void *instruction,int64_t *values);
uint64_t NativeComputeAddress(void) { return (uintptr_t)&CoolCompute; }
int64_t NativeJitCall(void *code,int64_t *values) { return ((int64_t (*)(int64_t *))code)(values); }

// The recovery point lives in the C callback frame until the Cool call returns.
// This avoids longjmp into a returned wrapper frame after LLVM inlining.
static jmp_buf recovery;
static int recovery_active;
extern void CoolSubmission(void *text);
int64_t NativeRecover(void *text) {
    recovery_active=1;
    int failed=setjmp(recovery);
    if(!failed)CoolSubmission(text);
    recovery_active=0;
    return failed;
}
void NativeRaise(int64_t *context) {
    (void)context;
    if(!recovery_active)host_fail("no recovery frame");
    longjmp(recovery,1);
}
