/* T1.2: allocate guest RAM/scratchpad and load the PS-X EXE for the LP64
 * build. Unlike image.c's ILP32 Memories_GuestMap, this never needs the
 * mirror/trap machinery -- G2H/H2G (gptr.h) already do the address
 * translation in software, so any host memory works, mapped at any address. */
#include "image.h"
#include "gptr.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SCRATCHPAD_SIZE 0x400u /* real PS1 hardware size; see gptr.h on g_scratch */

int Memories_GuestMap(void)
{
    g_ram = malloc(MEMORIES_GUEST_RAM_SIZE);
    g_scratch = malloc(SCRATCHPAD_SIZE);
    if (!g_ram || !g_scratch) {
        fprintf(stderr, "guest RAM/scratchpad: out of memory\n");
        free(g_ram);
        free(g_scratch);
        g_ram = g_scratch = NULL;
        return -1;
    }
    return 0;
}

static uint32_t le32(const unsigned char *bytes)
{
    return bytes[0] | ((uint32_t)bytes[1] << 8) | ((uint32_t)bytes[2] << 16) |
           ((uint32_t)bytes[3] << 24);
}

int Memories_GuestLoadExeData(const unsigned char *data, size_t length, const char *name)
{
    uint32_t address, size;
    if (length < 0x800 || memcmp(data, "PS-X EXE", 8) != 0) {
        fprintf(stderr, "%s: not a readable PS-X executable\n", name);
        return -1;
    }
    address = le32(data + 0x18);
    size = le32(data + 0x1c);
    if (address < MEMORIES_GUEST_RAM + 0x10000u || size > MEMORIES_GUEST_RAM_SIZE ||
        address - MEMORIES_GUEST_RAM > MEMORIES_GUEST_RAM_SIZE - size || size > length - 0x800) {
        fprintf(stderr, "%s: image does not fit guest RAM or is truncated\n", name);
        return -1;
    }
    memcpy(G2H(address), data + 0x800, size);
    return 0;
}

int Memories_GuestLoadExe(const char *path)
{
    unsigned char *data;
    long length;
    int result;
    FILE *file = fopen(path, "rb");
    if (!file || fseek(file, 0, SEEK_END) || (length = ftell(file)) < 0 || fseek(file, 0, SEEK_SET) ||
        !(data = malloc(length ? (size_t)length : 1))) {
        fprintf(stderr, "%s: not a readable PS-X executable\n", path);
        if (file) fclose(file);
        return -1;
    }
    if (fread(data, 1, (size_t)length, file) != (size_t)length) length = 0;
    fclose(file);
    result = Memories_GuestLoadExeData(data, (size_t)length, path);
    free(data);
    return result;
}
