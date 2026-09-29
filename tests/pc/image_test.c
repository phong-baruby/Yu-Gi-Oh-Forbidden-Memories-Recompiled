/* T1.2 acceptance: read the PS-X EXE header from MEMORIES_DISC, load it
 * through the LP64 guest image, and check a few words at the entry point
 * match between the file and G2H(entry). Skips (77) when no disc is set or
 * it cannot be read -- not everyone running the suite has a copy of the
 * game (CLAUDE.md invariant #4). */
#include "pc/guest/gptr.h"
#include "pc/guest/image.h"
#include "pc/platform/game_files.h"
#include "pc/platform/platform.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* GameFiles_Setup's interactive path is unreachable here (MEMORIES_DISC is
 * either usable or we skip before calling it), but game_files.c still
 * references these -- link stubs, as tests/pc/game_files_test.c also does. */
void Platform_ShowError(const char *title, const char *message) { (void)title; (void)message; }
int Platform_SelectDisc(char *path, size_t size, char *why, size_t why_size)
{
    (void)path; (void)size; (void)why; (void)why_size;
    return 0; /* cancelled */
}

static uint32_t le32(const unsigned char *bytes)
{
    return bytes[0] | ((uint32_t)bytes[1] << 8) | ((uint32_t)bytes[2] << 16) |
           ((uint32_t)bytes[3] << 24);
}

int main(void)
{
    char why[1024];
    const char *disc = GameFiles_Disc(why, sizeof(why));
    unsigned char *exe;
    size_t size, file_offset;
    uint32_t entry, address;
    const uint8_t *guest_entry;

    if (!disc) {
        printf("no usable MEMORIES_DISC: skipped (%s)\n", why);
        return 77;
    }
    exe = GameFiles_ReadExecutable(disc, &size);
    if (!exe) {
        printf("%s: could not read the executable: skipped\n", disc);
        return 77;
    }
    assert(size >= 0x800 && !memcmp(exe, "PS-X EXE", 8));
    entry = le32(exe + 0x10);
    address = le32(exe + 0x18);
    assert(entry >= address); /* the entry point is inside the loaded image */
    file_offset = 0x800 + (entry - address);
    assert(file_offset + 16 <= size);

    assert(!Memories_GuestMap());
    assert(!Memories_GuestLoadExeData(exe, size, disc));

    guest_entry = G2H(entry);
    assert(guest_entry != NULL);
    assert(!memcmp(guest_entry, exe + file_offset, 16));

    free(exe);
    puts("image_lp64 guest load: ok");
    return 0;
}
