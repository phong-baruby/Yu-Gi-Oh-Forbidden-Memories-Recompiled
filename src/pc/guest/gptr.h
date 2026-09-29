#ifndef MEMORIES_GUEST_GPTR_H
#define MEMORIES_GUEST_GPTR_H

/* Minimal version (T0.7 prototype): the macros ADR-02 defines, nothing else.
 * No runtime yet -- g_ram/g_scratch/H2G are declared but not implemented;
 * that lands with the real guest image in T1.1/T1.2. */

#include <stdint.h>

#ifdef MEMORIES_LP64
typedef uint32_t gaddr;

/* A struct/union field that holds a guest address to T (T *, or T *arr[N]
 * for an array of guest pointers). */
#define GPTR(T) gaddr

/* Like GPTR, but for a field declared through a pointer typedef (e.g. a
 * callback typedef `typedef void (*Foo)();`) -- T is already a pointer type,
 * so this must not add another `*` the way GPTR's non-LP64 branch does. */
#define GPTR_FN(T) gaddr

extern uint8_t *g_ram;     /* 2 MiB guest RAM */
extern uint8_t *g_scratch; /* scratchpad, ADR-02 says 1 KiB (verify at T1.1) */

static inline void *G2H(gaddr a)
{
    uint32_t phys = a & 0x1FFFFFFFu; /* drop KSEG0/KSEG1 */
    if ((phys - 0x1F800000u) < 0x400u) return g_scratch + (phys - 0x1F800000u);
    return g_ram + (phys & 0x1FFFFFu); /* physical mirror */
}

/* Only accepts a pointer inside g_ram/g_scratch, or NULL; anything else
 * aborts with a log (ADR-02). Not implemented yet -- prototype/layout only. */
gaddr H2G(const void *p);

#else
#define GPTR(T) T *
#define GPTR_FN(T) T
#define G2H(a) ((void *)(a))
#define H2G(p) (p)
#endif

#endif
