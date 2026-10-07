/* T1.9 acceptance: links statically against the SDL3 + FreeType just built
 * by build_deps.py, calls one function from each. otool -L on the result
 * must show no Homebrew (/opt/homebrew, /usr/local) path. */
#include <SDL3/SDL.h>
#include <ft2build.h>
#include FT_FREETYPE_H
#include <stdio.h>

int main(void)
{
    if (!SDL_Init(SDL_INIT_VIDEO)) {
        fprintf(stderr, "SDL_Init: %s\n", SDL_GetError());
        return 1;
    }
    SDL_Quit();

    FT_Library library;
    if (FT_Init_FreeType(&library) != 0) {
        fprintf(stderr, "FT_Init_FreeType failed\n");
        return 1;
    }
    FT_Done_FreeType(library);

    printf("smoke test ok: %s\n", SDL_GetPlatform());
    return 0;
}
