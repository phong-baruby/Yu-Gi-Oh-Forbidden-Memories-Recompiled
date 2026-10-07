/* Stand-in for modules.c (the shared-bank overlay registry: password,
 * overworld, free_duel -- build_game32.py's MODULE_SECTIONS/bank-renaming
 * dance) until a runtime module loader is designed for LP64 (new scope,
 * found while building T1.10's build driver -- see docs/macos/PROGRESS.md).
 * main_menu does not need this: its bank is 0 (build_game32.py's own
 * comment -- "linked like resident code"), so it compiles and links as an
 * ordinary resident unit once its own codemod exists (not yet, same
 * reason). No banked module is ever loaded yet, so "0 registered, never
 * resident" is correct, not a placeholder approximation. */
#include "image.h"

int Memories_ModulesInit(void)
{
    return 0;
}

int Memories_ModuleIsResident(unsigned bank, unsigned identifier)
{
    (void)bank;
    (void)identifier;
    return 0;
}

void Memories_GuestWritten(void *destination, size_t length)
{
    /* Save state/rewind write-tracking: ADR-08 says save state on LP64 is
     * not built yet either (T4.1), so there is nothing to track into. */
    (void)destination;
    (void)length;
}
