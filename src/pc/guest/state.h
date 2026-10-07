#ifndef MEMORIES_PC_GUEST_STATE_H
#define MEMORIES_PC_GUEST_STATE_H
/* Save states. A state is taken and resumed at one kind of place only: a
 * VSync(0) call made from game code. What is stored there is
 *
 * - guest RAM and the scratchpad,
 * - the game objects' host variables (game_data/game_bss and each module's
 *   ovl_* sections),
 * - the game stack above the VSync call and the callee-saved registers the
 *   caller expects back,
 * - each native subsystem's state, as a tagged chunk it describes itself.
 *
 * States are meant to outlive a rebuild of the native side, which is the
 * common debugging loop (reach a stub, implement it, come back). For that the
 * build links every game object's code and variables at fixed addresses and
 * the game runs on a stack mapped at a fixed address, so return addresses and
 * pointers held in a state still mean the same thing. Nothing native is
 * stored by address. A state does not survive a change to game sources; the
 * header carries a fingerprint of the game code and a mismatch is reported.
 *
 * Words of game data that the linker relocated (pointers to native
 * functions, for instance) differ between builds. The file keeps the
 * startup image of that data beside the saved one, and a word still at its
 * startup value is taken from the running build instead. */
#include <stddef.h>
#include <stdint.h>

typedef struct MemoriesState MemoriesState;
typedef struct MemoriesStateField {
    void *data;
    size_t size;
} MemoriesStateField;

/* Subsystems: save or load one chunk made of these fields, in order. When
 * loading, a missing chunk or one of another size (a layout that changed
 * since) is reported and left alone. Returns 1 if the fields were loaded. */
int Memories_StateChunk(MemoriesState *state, const char *tag, const MemoriesStateField *fields, size_t count);
int Memories_StateLoading(const MemoriesState *state);

/* Before restoring the game image, rebase pointers into a native allocation
 * recreated by a subsystem. Only the saved game memory, variables, stack
 * and entry registers are scanned; native chunks keep their own formats. */
void Memories_StateRemapRange(MemoriesState *state, uint32_t from, uint32_t to, uint32_t size);

/* Registers on entry to VSync, written by the assembly entry
 * (state_i386.S / state_arm64.S, T1.7). `sp` is named the same across both
 * architectures (i386: `esp`, which points at the return address since
 * VSync was entered by a `call`; arm64: `sp` itself, the return address is
 * `x30` instead, captured as its own field) so state.c's own use of it
 * (entirely save/load file bookkeeping, dead code under MEMORIES_LP64 until
 * M4/ADR-08 builds real state files for it -- see that ADR's own note) needs
 * no #ifdef of its own, just the one shared field name. */
#ifdef MEMORIES_LP64
typedef struct MemoriesStateEntry {
    /* AAPCS64 callee-saved: x19-x28, x29 (fp), x30 (lr) -- the game's own
     * return address, since the assembly entry reaches VSync by a plain
     * branch, not `bl`, leaving the caller's x30 untouched -- sp, and the
     * low 64 bits of d8-d15 (the only part of v8-v15 AAPCS64 requires a
     * callee to preserve). Never x18 (Apple's own platform register). */
    uint64_t x19, x20, x21, x22, x23, x24, x25, x26, x27, x28;
    uint64_t x29, x30, sp;
    uint64_t d8, d9, d10, d11, d12, d13, d14, d15;
} MemoriesStateEntry;
#else
typedef struct MemoriesStateEntry {
    uint32_t ebx, esi, edi, ebp, sp; /* sp points at the return address */
} MemoriesStateEntry;
#endif
extern MemoriesStateEntry Memories_StateEntry;

/* main(): run `entry` on the fixed game stack. Does not return. */
int Memories_StateRunGame(int (*entry)(void));
/* VSync(0), after presenting: act on a pending save or load request. */
void Memories_StatePoint(unsigned presented_frames);
/* 1 save, 2 load; taken up at the next state point. Async-signal-safe. */
void Memories_StateRequest(int what, int slot);
/* The rewind key (F8) is held or not. With the `rewind` setting on, state
 * points keep a ring of recent states in memory and, while held, go back
 * through it (state.c, rewind.h). Returns whether the setting is on: only
 * then is F8 the rewind key, so with it off the key reaches the game like
 * any other. Async-signal-safe. */
int Memories_RewindHold(int held);
/* Locate the running build's symbol table beside the executable. */
int Memories_SymbolTablePath(char *out, size_t size);
int Memories_LastStateSlot(void);

/* Each subsystem's chunk. */
void Spu_State(MemoriesState *state);
void LibSpu_State(MemoriesState *state);
void LibDs_State(MemoriesState *state);
void LibEtc_State(MemoriesState *state);
void LibGpu_State(MemoriesState *state);
void LibGte_State(MemoriesState *state);
void LibPress_State(MemoriesState *state);
void LibMcrd_State(MemoriesState *state);
void SaveMenu_State(MemoriesState *state);
void DeckMenu_ShopState(MemoriesState *state);
void TitleJump_State(MemoriesState *state);
void Platform_State(MemoriesState *state);
#endif
