#ifndef COOL_ARGS_H
#define COOL_ARGS_H
#include <stdint.h>
static int64_t cool_argc, cool_args_start = 1;
static char **cool_argv;
void cool_args_init(int32_t argc, char **argv) { cool_argc=argc; cool_argv=argv; cool_args_start=1; }
void CoolArgsStart(int64_t start) { cool_args_start=start; }
int64_t CoolArgsCount(void) { return cool_argc>cool_args_start ? cool_argc-cool_args_start : 0; }
char *CoolArgsAt(int64_t index) { return index>=0 && index<CoolArgsCount() ? cool_argv[cool_args_start+index] : 0; }
#endif
