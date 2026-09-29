/* T1.1: storage for g_ram/g_scratch and the H2G direction of ADR-02's
 * address translation. Only compiled under MEMORIES_LP64.
 *
 * g_ram/g_scratch start NULL: pointing them at real allocated memory (and
 * loading the guest image into it) is T1.2's job, not this file's. */
#include "gptr.h"
#include <stdio.h>
#include <stdlib.h>

#define GUEST_RAM_SIZE 0x200000u    /* 2 MiB */
#define SCRATCHPAD_SIZE 0x400u      /* 1 KiB, see the comment on g_scratch in gptr.h */

uint8_t *g_ram;
uint8_t *g_scratch;

gaddr H2G(const void *p)
{
    const uint8_t *b = p;
    if (b == NULL) return 0;
    if (g_scratch && b >= g_scratch && b < g_scratch + SCRATCHPAD_SIZE) {
        return 0x1F800000u + (uint32_t)(b - g_scratch);
    }
    if (g_ram && b >= g_ram && b < g_ram + GUEST_RAM_SIZE) {
        return 0x80000000u + (uint32_t)(b - g_ram); /* always the KSEG0 form */
    }
    fprintf(stderr, "H2G: %p is not inside guest RAM (%p+%#x) or the scratchpad (%p+%#x)\n",
            p, (void *)g_ram, GUEST_RAM_SIZE, (void *)g_scratch, SCRATCHPAD_SIZE);
    abort();
}
