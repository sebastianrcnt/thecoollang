#ifndef COOL_REPL_IO_H
#define COOL_REPL_IO_H
/* Driver-only package resolution transport. Cool owns language parsing. */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <fcntl.h>
#include <arpa/inet.h>
#include <sys/socket.h>
static int cool_repl_transfer(int fd, void *buffer, size_t size, int writing) {
    unsigned char *at = buffer;
    while (size) {
        ssize_t n = writing ? write(fd, at, size) : read(fd, at, size);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return 0;
        at += n; size -= (size_t)n;
    }
    return 1;
}
static const char *cool_repl_resolve(const char *package) {
    static char response[65536];
    const char *request_env=getenv("COOL_REPL_REQUEST_FD"), *response_env=getenv("COOL_REPL_RESPONSE_FD");
    if (!request_env || !response_env || !*request_env || !*response_env) return "error\tpackage imports require the cool project driver";
    char *end;
    long request=strtol(request_env,&end,10); if (*end || request<3 || request>INT32_MAX) return "error\tinvalid package resolver channel";
    long reply=strtol(response_env,&end,10); if (*end || reply<3 || reply>INT32_MAX) return "error\tinvalid package resolver channel";
    if (fcntl((int)request,F_SETFD,FD_CLOEXEC)<0 || fcntl((int)reply,F_SETFD,FD_CLOEXEC)<0) return "error\tpackage resolver channel closed";
#ifdef SO_NOSIGPIPE
    int no_sigpipe=1;
    if (setsockopt((int)request,SOL_SOCKET,SO_NOSIGPIPE,&no_sigpipe,sizeof(no_sigpipe))<0) return "error\tinvalid package resolver channel";
#endif
    size_t size=strlen(package);
    if (!size || size>4096) return "error\tinvalid package path length";
    uint32_t length=htonl((uint32_t)size);
    if (!cool_repl_transfer((int)request,&length,4,1) || !cool_repl_transfer((int)request,(void *)package,size,1) || !cool_repl_transfer((int)reply,&length,4,0)) return "error\tpackage resolver channel closed";
    size=ntohl(length);
    if (!size || size>=sizeof(response)) return "error\tinvalid package resolver response";
    if (!cool_repl_transfer((int)reply,response,size,0)) return "error\tpackage resolver channel closed";
    response[size]=0;
    if (memchr(response,0,size) || !((size>3 && memcmp(response,"ok\t",3)==0) || (size>6 && memcmp(response,"error\t",6)==0))) return "error\tinvalid package resolver response";
    return response;
}
#endif
