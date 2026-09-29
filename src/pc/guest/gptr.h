#ifndef MEMORIES_GUEST_GPTR_H
#define MEMORIES_GUEST_GPTR_H

/* T1.1: G2H/H2G and the macros ADR-02 defines. g_ram/g_scratch are declared
 * here but only *defined* in gptr_lp64.c as plain (initially NULL) storage --
 * pointing them at real memory is T1.2's job (loading the guest image). */

#include <stddef.h>
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
/* Scratchpad is 1 KiB on real PS1 hardware (ADR-02). image.c maps a full
 * 4 KiB page for it (Windows VirtualAlloc and the POSIX map_at both reserve
 * 0x1000 at 0x1f800000) only because that is the smallest a page-granular
 * mapping can be -- the extra 3 KiB was never valid scratchpad on retail, so
 * G2H below still only recognizes the real 0x400-byte window (verified at
 * T1.1 against image.c; see docs/macos/reports/m1-gptr.md). */
extern uint8_t *g_scratch;

static inline void *G2H(gaddr a)
{
    if (a == 0) return NULL; /* guest NULL is 0; G2H(0) must stay NULL (ADR-02) */
    uint32_t phys = a & 0x1FFFFFFFu; /* drop KSEG0/KSEG1 */
    if ((phys - 0x1F800000u) < 0x400u) return g_scratch + (phys - 0x1F800000u);
    return g_ram + (phys & 0x1FFFFFu); /* physical mirror */
}

/* Only accepts a pointer inside g_ram/g_scratch, or NULL; anything else
 * logs and abort()s (ADR-02). Normalizes to the KSEG0 form (0x80xxxxxx),
 * regardless of which mirror G2H's argument originally named. Defined in
 * gptr_lp64.c. */
gaddr H2G(const void *p);

#else
#define GPTR(T) T *
#define GPTR_FN(T) T
#define G2H(a) ((void *)(a))
#define H2G(p) (p)
#endif

#endif
