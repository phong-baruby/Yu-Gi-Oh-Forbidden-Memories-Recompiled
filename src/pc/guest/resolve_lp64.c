/* Memories_Resolve for LP64: same range/alignment checks as resolve.c (the
 * ILP32 build, excluded from this build -- its own comment says why: "a
 * guest address is already a host address", which is false here), but the
 * address a valid range resolves to goes through G2H instead of a raw
 * (void *)(uintptr_t) cast. Found while scoping T1.10's native file list:
 * src/pc/compat/libgs_ot.c and src/pc/render/packets.c (GPU ordering
 * tables/packets, part of every rendered frame) call this. */
#include "image.h"
#include "gptr.h"
#include "pc/memory.h"

void *Memories_Resolve(MemoriesMemory *memory, uint32_t address,
                       size_t length, size_t alignment)
{
    uint32_t physical = address & UINT32_C(0x1fffffff);
    (void)memory;
    if (!alignment || (alignment & (alignment - 1)) || (address & (alignment - 1)) ||
        (address >= UINT32_C(0x20000000) && (address < MEMORIES_GUEST_RAM ||
                                             address >= UINT32_C(0xc0000000)))) {
        return NULL;
    }
    if (physical >= UINT32_C(0x10000) && physical < MEMORIES_GUEST_RAM_SIZE) {
        return length <= MEMORIES_GUEST_RAM_SIZE - physical ? G2H(address) : NULL;
    }
    if (physical >= UINT32_C(0x1f800000) && physical < UINT32_C(0x1f800400) &&
        address < UINT32_C(0xa0000000)) {
        return length <= UINT32_C(0x1f800400) - physical ? G2H(address) : NULL;
    }
    return NULL;
}

uint32_t Memories_ReadLE32(const uint8_t *bytes)
{
    return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8) |
           ((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
}

void Memories_WriteLE32(uint8_t *bytes, uint32_t value)
{
    bytes[0] = (uint8_t)value;
    bytes[1] = (uint8_t)(value >> 8);
    bytes[2] = (uint8_t)(value >> 16);
    bytes[3] = (uint8_t)(value >> 24);
}
