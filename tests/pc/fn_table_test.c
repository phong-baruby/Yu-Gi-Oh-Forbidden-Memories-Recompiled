/* T1.6 acceptance: GCALL resolves 3 real retail addresses (picked from
 * config/slus_01411/functions.csv) and 1 synthetic native-only address
 * (ADR-04's 0x9F000000+ range, for a PC-only function installed into guest
 * data) to the right host function; an address with no entry logs the
 * nearest known symbol and aborts. MEMORIES_LP64-only (see CMakeLists.txt).
 *
 * This test provides its own small Memories_FunctionMap/Memories_SymbolTable
 * instead of linking the real generated tmp/lp64/gen/fn_table.c (1786
 * entries, not committed -- built by tools/pc/lp64/gen_fn_table.py): it
 * exercises Memories_GuestFunctionLookup's own lookup/abort logic, not the
 * real table's content, the same way gptr_test.c stands in its own
 * ram/scratch buffers instead of a real loaded EXE. */
#include "pc/guest/gptr.h"
#include "pc/guest/image.h"
#include <assert.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

static int calls[4];

static void RetailFuncA(void) { calls[0]++; }
static void RetailFuncB(void) { calls[1]++; }
static void RetailFuncC(void) { calls[2]++; }
static void NativeOnlyCallback(void) { calls[3]++; }

const MemoriesGuestFunction Memories_FunctionMap[] = {
    {0x80012B50u, RetailFuncA, 0, 0}, /* Main_Init */
    {0x80012CD4u, RetailFuncB, 0, 0}, /* Main_VBlankCB */
    {0x80012D4Cu, RetailFuncC, 0, 0}, /* Main_AdvanceFrame */
    {0x9F000000u, NativeOnlyCallback, 0, 0},
};
const unsigned Memories_FunctionMapCount = 4;

const MemoriesGuestSymbol Memories_SymbolTable[] = {
    {0x80012B50u, "Main_Init"},
    {0x80012CD4u, "Main_VBlankCB"},
    {0x80012D4Cu, "Main_AdvanceFrame"},
    {0x9F000000u, "NativeOnlyCallback"},
};
const unsigned Memories_SymbolTableCount = 4;

/* Not exercised (every test entry has bank 0, the "always resident" case
 * Memories_GuestFunctionLookup checks first) -- defined only so the test
 * binary does not need to link src/pc/guest/modules.c (M3's module
 * registry) just to satisfy this extern. */
int Memories_ModuleIsResident(unsigned bank, unsigned identifier)
{
    (void)bank;
    (void)identifier;
    return 1;
}

int main(int argc, char **argv)
{
    /* Re-invoked by the fork()+exec() below to exercise the abort path in a
     * child process, since abort() can't be tested in-line and resumed. */
    if (argc > 1 && !strcmp(argv[1], "--lookup-miss")) {
        GCALL(void (*)(void), 0x80099999u)(); /* not in the table: must log + abort() */
        return 0;                            /* unreachable if the contract holds */
    }

    GCALL(void (*)(void), 0x80012B50u)();
    GCALL(void (*)(void), 0x80012CD4u)();
    GCALL(void (*)(void), 0x80012D4Cu)();
    GCALL(void (*)(void), 0x9F000000u)();
    assert(calls[0] == 1 && calls[1] == 1 && calls[2] == 1 && calls[3] == 1);

    pid_t pid = fork();
    assert(pid >= 0);
    if (pid == 0) {
        execl(argv[0], argv[0], "--lookup-miss", (char *)NULL);
        _exit(127); /* exec itself failed */
    }
    int status = 0;
    assert(waitpid(pid, &status, 0) == pid);
    assert(WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT);

    puts("fn_table GCALL: ok");
    return 0;
}
