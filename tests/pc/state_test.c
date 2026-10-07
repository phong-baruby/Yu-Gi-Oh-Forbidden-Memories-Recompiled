/* T1.7 acceptance: the game runs on its own stack (mmap'd with a guard page
 * below it, not at a fixed address -- see state.c's Memories_StateRunGame,
 * MEMORIES_LP64 branch) and calling VSync 1000 times in a row round-trips
 * through the real AAPCS64 entry/return trampoline (state_arm64.S) without
 * corrupting the native stack or any callee-saved register. MEMORIES_LP64-
 * only (see CMakeLists.txt).
 *
 * Does not link the real src/pc/guest/state.c: that file's own
 * Memories_StateRunGame pulls in its whole save/load/rewind dependency
 * tree (mods, spu, deck_menu, crash, ...), none of which this is testing.
 * This instead stands in its own small Memories_StateEntry definition and
 * a minimal copy of just the mmap-with-guard-page-plus-ucontext mechanism
 * (so the real state.c's own version is covered by reading its source, not
 * by linking it here), the same way gptr_test.c/fn_table_test.c stand in
 * their own ram/scratch buffer or function table instead of the real one. */
#ifdef __APPLE__
/* Same reasoning as state.c's own copy of this: macOS hides
 * getcontext/makecontext/swapcontext and MAP_ANON under strict POSIX
 * conformance unless both of these are defined before any header pulls in
 * <ucontext.h>/<sys/mman.h> transitively. */
#define _XOPEN_SOURCE 600
#define _DARWIN_C_SOURCE
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
#endif
#include "pc/guest/state.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <ucontext.h>
#include <unistd.h>

MemoriesStateEntry Memories_StateEntry;

/* state_arm64.S's own entry point: VSync(mode) captures the caller's
 * registers into Memories_StateEntry, then branches (not calls) into
 * Memories_VSync(mode) -- defined below, standing in for the real one
 * (src/pc/sdk/libetc.c), which has its own platform/graphics dependencies
 * this test has no reason to pull in. */
extern int VSync(int mode);
/* Declared by state.c itself (private to it + state_arm64.S), not state.h. */
void Memories_StateReturn(const MemoriesStateEntry *entry, int value) __attribute__((noreturn));

#define STACK_SIZE 0x00800000u

static unsigned frame_count;
/* Local state kept across every VSync() call, in registers the AAPCS64
 * callee-saved set covers (x19-x28): if state_arm64.S's entry/return ever
 * clobbered one of them instead of correctly saving/restoring it, this
 * canary would stop matching frame_count well before frame 1000. gcc/clang
 * are free to keep fewer of these in registers than there are slots, but
 * enough of them will land in x19-x28 across -O0 and -O2 alike to exercise
 * the whole saved set over 1000 iterations either way. */
static int entry_point(void)
{
    long a = 0, b = 0, c = 0, d = 0, e = 0, f = 0, g = 0, h = 0, i = 0, j = 0;
    int result;
    do {
        a++; b += 2; c += 3; d += 4; e += 5; f += 6; g += 7; h += 8; i += 9; j += 10;
        result = VSync(0);
    } while (result == 0);
    assert(a == 1000 && b == 2000 && c == 3000 && d == 4000 && e == 5000);
    assert(f == 6000 && g == 7000 && h == 8000 && i == 9000 && j == 10000);
    return result;
}

/* Stands in for src/pc/sdk/libetc.c's real Memories_VSync. Immediately
 * "returns" through the just-captured entry, same as state_i386.S's
 * jmp-based trampoline expects its C body to eventually do (directly or,
 * for the real VSync, after a save/load point) -- never returns normally. */
int Memories_VSync(int mode)
{
    (void)mode;
    frame_count++;
    Memories_StateReturn(&Memories_StateEntry, frame_count < 1000 ? 0 : 42);
    abort(); /* unreachable: Memories_StateReturn never returns */
}

static int run_result;

static void run_entry(void)
{
    run_result = entry_point();
}

int main(void)
{
    long page = sysconf(_SC_PAGESIZE);
    void *region;
    void *stack;
    ucontext_t game_context, service_context;
    int result;

    assert(page > 0);
    region = mmap(NULL, (size_t)page + STACK_SIZE, PROT_READ | PROT_WRITE,
                 MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(region != MAP_FAILED);
    assert(mprotect(region, (size_t)page, PROT_NONE) == 0);
    stack = (char *)region + page;

    getcontext(&game_context);
    game_context.uc_stack.ss_sp = stack;
    game_context.uc_stack.ss_size = STACK_SIZE;
    game_context.uc_link = &service_context;
    makecontext(&game_context, run_entry, 0);
    swapcontext(&service_context, &game_context);

    result = run_result;
    assert(frame_count == 1000);
    assert(result == 42);

    munmap(region, (size_t)page + STACK_SIZE);
    puts("state VSync entry/return: ok");
    return 0;
}
