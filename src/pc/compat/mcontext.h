#ifndef MEMORIES_PC_COMPAT_MCONTEXT_H
#define MEMORIES_PC_COMPAT_MCONTEXT_H
/* ADR-09: the PC/SP/FP a POSIX signal handler's `ucontext_t *` holds, by
 * platform -- the one piece of src/pc/platform/platform_common.c's and
 * src/pc/debug/crash.c's signal-based timing/crash reporting that is not
 * already common code (Windows has its own CONTEXT-based path already,
 * Win32_ContextRegisters, not touched here).
 *
 * i386 Linux (glibc): mcontext_t is a plain struct member of ucontext_t,
 * REG_EIP/REG_ESP/REG_EBP index its .gregs[] array.
 *
 * arm64 Darwin: mcontext_t is ITSELF a pointer type
 * (`typedef _STRUCT_MCONTEXT64 *mcontext_t;`), unlike Linux's plain struct
 * -- one more `->` than the glibc side needs. Field names verified by
 * compiling a throwaway program against the real SDK headers (ADR-09's own
 * text already said __pc/__sp/__fp, confirmed rather than assumed), not
 * used for any other register here (AAPCS64's x29 IS the frame pointer,
 * same role as i386's EBP, so FP below means exactly that on both). */
#include <stdint.h>

#if defined(__APPLE__)
#define MCONTEXT_PC(user) ((uintptr_t)(user)->uc_mcontext->__ss.__pc)
#define MCONTEXT_SP(user) ((uintptr_t)(user)->uc_mcontext->__ss.__sp)
#define MCONTEXT_FP(user) ((uintptr_t)(user)->uc_mcontext->__ss.__fp)
#else
#define MCONTEXT_PC(user) ((uintptr_t)(user)->uc_mcontext.gregs[REG_EIP])
#define MCONTEXT_SP(user) ((uintptr_t)(user)->uc_mcontext.gregs[REG_ESP])
#define MCONTEXT_FP(user) ((uintptr_t)(user)->uc_mcontext.gregs[REG_EBP])
#endif
#endif
