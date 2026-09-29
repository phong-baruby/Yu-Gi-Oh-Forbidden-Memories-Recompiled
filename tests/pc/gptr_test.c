/* T1.1 acceptance: G2H(0)==NULL; the KSEG0/KSEG1/KUSEG mirrors of the same
 * physical word alias to one host byte; H2G(G2H(a)) normalizes to the KSEG0
 * form regardless of which mirror `a` named; a pointer outside guest
 * RAM/scratchpad makes H2G abort(). MEMORIES_LP64-only (see CMakeLists.txt). */
#include "pc/guest/gptr.h"
#include <assert.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    static uint8_t ram[0x200000];    /* stand-in for the real guest RAM (T1.2) */
    static uint8_t scratch[0x400];   /* stand-in for the real scratchpad (T1.2) */
    g_ram = ram;
    g_scratch = scratch;

    /* Re-invoked by the fork()+exec() below to exercise the abort path in a
     * child process, since H2G aborting can't be tested in-line and resumed. */
    if (argc > 1 && !strcmp(argv[1], "--abort-out-of-range")) {
        int stray;
        H2G(&stray); /* not inside g_ram/g_scratch: must abort() */
        return 0;    /* unreachable if H2G upheld its contract */
    }

    assert(G2H(0) == NULL);

    void *kseg0 = G2H(0x80001000u);
    void *kseg1 = G2H(0xA0001000u);
    void *kuseg = G2H(0x00001000u);
    assert(kseg0 != NULL);
    assert(kseg0 == kseg1 && kseg0 == kuseg); /* one physical byte, three names */
    assert(kseg0 == ram + 0x1000);

    assert(H2G(kseg0) == 0x80001000u);
    assert(H2G(G2H(0xA0001000u)) == 0x80001000u); /* normalizes to KSEG0 */
    assert(H2G(G2H(0x00001000u)) == 0x80001000u);
    assert(H2G(NULL) == 0);

    void *sp = G2H(0x1F800010u);
    assert(sp == scratch + 0x10);
    assert(H2G(sp) == 0x1F800010u);

    pid_t pid = fork();
    assert(pid >= 0);
    if (pid == 0) {
        execl(argv[0], argv[0], "--abort-out-of-range", (char *)NULL);
        _exit(127); /* exec itself failed */
    }
    int status = 0;
    assert(waitpid(pid, &status, 0) == pid);
    assert(WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT);

    puts("gptr G2H/H2G: ok");
    return 0;
}
