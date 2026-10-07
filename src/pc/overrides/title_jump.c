/* The retail game-over return sequence, called only between mode runners. */
#include "pc/platform/title_jump.h"
#include "types.h"
#include "game/display_object_core.h"
#include "game/fade.h"
#include "game/file_transfer.h"
#include "game/func_80035A64.h"
#include "game/main_modes.h"
#include "game/sound.h"
#include <stdio.h>

extern u8 D_8009B26C;
#ifdef MEMORIES_LP64
#define D_8009B268 (*(unsigned char *)G2H(0x8009B268u))
#define D_8009B26D (*(unsigned char *)G2H(0x8009B26Du))
#define D_800E9DC0 (*(int (*)[12])G2H(0x800E9DC0u))
#else
extern u8 D_8009B268, D_8009B26D;
extern int D_800E9DC0[];
#endif
void Psx_longjmp(int *env, int value);

void TitleJump_Execute(void)
{
    fprintf(stderr, "memories-pc: back to the title screen from mode %u\n", D_8009B26C & 0x1F);
    File_WaitForTransfers();
    SD_BGMFadeOut();
    Fade_WaitOut();
    DisplayObject_Reset();
    func_80035A64();
    D_8009B268 = 1;
    D_8009B26D = 0;
    D_8009B26C = MAIN_MODE_MENU;
    Psx_longjmp(D_800E9DC0, 1);
}
