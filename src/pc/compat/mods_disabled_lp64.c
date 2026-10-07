/* The mod loader (ADR-06/07: hooks_arm64.c, ELF object loader) is not built
 * for arm64 yet -- milestone M1's own scope already says so ("mod loader
 * tam tat tren LP64"). src/pc/mods/{mods,hooks,manager,object_loader,
 * events}.c are therefore not part of this build; these two functions are
 * the only ones src/game calls directly (grep "Mods_" src/game), so they
 * get a real no-op body here instead of falling through to build.py's
 * generic log-and-abort stub -- "no mods installed" is the correct normal
 * behavior for every duel, not an error. */
#include "pc/mods/mods.h"

void Mods_Dispatch(MemoriesModEvent *event)
{
    (void)event;
}

int Mods_DamageLife(int side, int life, int damage, int kind)
{
    (void)side;
    (void)life;
    (void)kind;
    return damage;
}
