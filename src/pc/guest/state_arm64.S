/* T1.7/ADR-08: the AAPCS64 equivalent of state_i386.S -- see that file's own
 * header comment for what this is for (save-state's VSync boundary) and
 * docs/macos/ARCHITECTURE.md's ADR-08 for the register set this captures.
 * Mach-O (unlike ELF/PE, state_i386.S's two targets) always prefixes every
 * symbol with `_`; this file only ever targets Mach-O, so that is written
 * in directly instead of through state_i386.S's SYMBOL() macro.
 *
 * Offsets below are MemoriesStateEntry's layout (state.h, MEMORIES_LP64):
 * x19..x28 at 0..72, x29/x30/sp at 80/88/96, d8..d15 at 104..160 (8 bytes
 * each, 168 bytes total) -- verified against the real struct's offsetof
 * while writing this, not just computed by hand. */
    .text
    .p2align 2
    .globl _VSync
_VSync:
    adrp x9, _Memories_StateEntry@PAGE
    add  x9, x9, _Memories_StateEntry@PAGEOFF
    stp  x19, x20, [x9, #0]
    stp  x21, x22, [x9, #16]
    stp  x23, x24, [x9, #32]
    stp  x25, x26, [x9, #48]
    stp  x27, x28, [x9, #64]
    stp  x29, x30, [x9, #80]
    mov  x10, sp
    str  x10, [x9, #96]
    stp  d8,  d9,  [x9, #104]
    stp  d10, d11, [x9, #120]
    stp  d12, d13, [x9, #136]
    stp  d14, d15, [x9, #152]
    /* `b`, not `bl`: x30 (lr) above is still the caller's own return
     * address, exactly as state_i386.S's `jmp` leaves eip's return address
     * on the stack where the caller put it -- Memories_VSync's own `ret`
     * later returns straight to VSync's caller, not back into this
     * trampoline. */
    b    _Memories_VSync

/* void Memories_StateReturn(const MemoriesStateEntry *entry, int value):
 * return `value` from the VSync call that `entry` describes. AAPCS64: x0 is
 * `entry`, w1 is `value`. */
    .globl _Memories_StateReturn
_Memories_StateReturn:
    ldp  x19, x20, [x0, #0]
    ldp  x21, x22, [x0, #16]
    ldp  x23, x24, [x0, #32]
    ldp  x25, x26, [x0, #48]
    ldp  x27, x28, [x0, #64]
    ldp  x29, x30, [x0, #80]
    ldr  x10, [x0, #96]
    ldp  d8,  d9,  [x0, #104]
    ldp  d10, d11, [x0, #120]
    ldp  d12, d13, [x0, #136]
    ldp  d14, d15, [x0, #152]
    mov  w0, w1
    mov  sp, x10
    ret
