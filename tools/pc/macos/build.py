#!/usr/bin/env python3
"""Compile and link the resident game as a 64-bit Mach-O arm64 executable.

First build driver for the LP64 memory model (ADR-01..05). Much simpler than
tools/pc/build_game32.py (the i386 Linux/Windows driver): ADR-03 (globals)
and ADR-04 (function pointers, GCALL) already resolve every guest address at
the C level through G2H/H2G/GCALL, computed at the call site -- this driver
needs none of build_game32.py's fixed-address linker-script pinning, weak-
symbol overriding or module bank renaming. Compile what currently survives
LP64 (src/game, src/psyq -- already run through tools/pc/lp64/codemod.py --
plus the native pc/ layer), link it, and generate a log-and-abort stub for
anything still undefined: the same resilience model build_game32.py already
uses for a not-yet-decompiled function, extended here to also cover a
src/game/src/psyq unit that does not currently compile under LP64 (known
gaps, see docs/macos/PROGRESS.md "Van de mo") -- this driver does not
require every unit to compile cleanly, only enough of the boot path to, per
M1's own "lat cat doc, chay duoc som" principle.

Not in this build yet (new, undesigned scope found while writing this
driver -- see docs/macos/PROGRESS.md decision log):
  - src/overlays (main_menu, password, overworld, free_duel): ADR-05's
    expression codemod only covers src/game and src/psyq so far (deferred
    2026-10-01, "overlay doi M3"). main_menu is what renders the title
    screen; its 13 files are not codemoded, so title screen is not reached
    yet -- the game is expected to stop at the first call into it.
  - The shared-bank overlay loader (password/overworld/free_duel, build_
    game32.py's MODULE_SECTIONS/bank-renaming) has no ADR for LP64 at all.
    src/pc/guest/modules_lp64.c stands in with "0 modules registered".
  - The real mod loader (ADR-06/07, src/pc/mods/{mods,hooks,manager,
    object_loader,events}.c) -- milestone's own scope already excludes it
    ("mod loader tam tat tren LP64"). src/pc/compat/mods_disabled_lp64.c
    gives the 2 functions src/game calls directly a real no-op body.
"""
import argparse, concurrent.futures, csv, glob, json, os, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT_SRC = os.path.join(ROOT, "tmp", "lp64", "src")
GEN = os.path.join(ROOT, "tmp", "lp64", "gen")
DEPS = os.path.join(ROOT, "tmp", "pc", "macos-deps")          # tools/pc/macos/build_deps.py
BUILD = os.path.join(ROOT, "tmp", "pc", "macos-build")
FUNCTIONS_CSV = os.path.join(ROOT, "config", "slus_01411", "functions.csv")

INCLUDES = ["-I" + OUT_SRC, "-Isrc", "-I" + os.path.join(DEPS, "include"),
            "-I" + os.path.join(DEPS, "include", "freetype2")]
COMMON = ["-arch", "arm64", "-std=gnu11", "-DMEMORIES_PC", "-DMEMORIES_LP64",
          "-D_LANGUAGE_C", "-DLANGUAGE_C", "-D_DARWIN_C_SOURCE", "-D_XOPEN_SOURCE=600",
          "-include", "src/pc/guest/gptr.h", *INCLUDES]
# -O0 for game units: original busy-waits poll non-volatile globals a VBlank
# handler updates elsewhere, same reasoning as build_game32.py's CFLAGS.
# -Werror=... (not -w: T1.4i found -w silently disables pointer-to-int-cast/
# int-to-pointer-cast regardless of position, see docs/macos/reports/
# m1-codemod-stage2i.md) -- a file with an unsafe cast must fail to compile
# here (excluded, its functions become log-abort stubs), never link with a
# silently truncated/garbage pointer.
CAST_WERROR = ["-Werror=int-conversion", "-Werror=pointer-to-int-cast", "-Werror=int-to-pointer-cast"]
GAME_CFLAGS = [*COMMON, "-g", "-O0", "-fno-strict-aliasing", "-fwrapv", "-fcommon", *CAST_WERROR]
NATIVE_CFLAGS = [*COMMON, "-g", "-O2", "-fno-strict-aliasing", "-Wno-builtin-declaration-mismatch",
                 "-D_FILE_OFFSET_BITS=64", *CAST_WERROR]
ASFLAGS = ["-arch", "arm64"]

EXCLUDE_GUEST = {"image.c", "modules.c", "mips.c", "setjmp_i386.S", "state_i386.S"}
EXCLUDE_PLATFORM = {"x11.c", "audio_alsa.c", "gamepad_evdev.c", "controls_linux.c", "win32.c"}
# src/pc/mods: only the generic utilities (no ADR-06/07 hook/loader machinery).
MODS_NATIVE = ["src/pc/mods/json.c", "src/pc/mods/mod_libc.c"]


def native_sources():
    guest = [f for f in glob.glob("src/pc/guest/*.[cS]") if os.path.basename(f) not in EXCLUDE_GUEST]
    platform = [f for f in glob.glob("src/pc/platform/*.c") if os.path.basename(f) not in EXCLUDE_PLATFORM]
    rest = (glob.glob("src/pc/sdk/*.c") + glob.glob("src/pc/overrides/*.c") + glob.glob("src/pc/audio/*.c") +
            glob.glob("src/pc/debug/*.c") + glob.glob("src/pc/cards/*.c") + glob.glob("src/pc/free_duel/*.c") +
            glob.glob("src/pc/saves/*.c") + glob.glob("src/pc/text/*.c") +
            ["src/pc/render/soft_gpu.c", "src/pc/render/texture_dump.c", "src/pc/render/texture_pack.c",
             "src/pc/render/packets.c", "src/pc/render/psyz_gpu.c",
             "src/pc/rng.c", "src/pc/compat/fs.c", "src/pc/compat/gte.c", "src/pc/compat/pgxp.c",
             "src/pc/compat/libgs_ot.c", "src/pc/compat/mods_disabled_lp64.c"] + MODS_NATIVE)
    return sorted(set(guest + platform + rest))


def run(command, **kwargs):
    result = subprocess.run(command, cwd=ROOT, **kwargs)
    if result.returncode:
        sys.exit(f"{' '.join(command[:4])} ...: lỗi, xem log phía trên")
    return result


def obj_path(source):
    return os.path.join(BUILD, "obj", source.replace("/", "_") + ".o")


def compile_unit(job):
    """(source, cflags) -> (source, ok, stderr). Never raises: a file that
    fails to compile under LP64 is excluded, not a fatal error (see module
    docstring) -- its own functions become undefined, and get a stub."""
    source, cflags = job
    out = obj_path(source)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    result = subprocess.run(["clang", *cflags, "-c", source, "-o", out], cwd=ROOT,
                            capture_output=True, text=True)
    return source, result.returncode == 0, result.stderr


def c_name(symbol):
    """The C name of a Mach-O symbol: every C global/function carries a
    leading underscore on this platform (like COFF/PE, unlike ELF --
    build_game32.py's own PREFIX/c_name handle the same thing for Windows;
    this driver never targets ELF at all, so it always strips it)."""
    return symbol[1:] if symbol.startswith("_") else symbol


def symbols(objects):
    defined, undefined = set(), set()
    if not objects:
        return defined, undefined
    result = subprocess.run(["nm", "-g", *objects], cwd=ROOT, capture_output=True, text=True, check=True)
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "U":
            undefined.add(c_name(parts[1]))
        elif len(parts) == 3 and parts[1] in "TDBSRVWtdbsrvw":
            defined.add(c_name(parts[2]))
    return defined, undefined


def guest_addresses_text_range():
    """(start, end): the resident image's own .text range (first line of
    config/pc/guest_addresses.txt). A retail address outside this range
    belongs to an overlay (its own separate range, build_game32.py tracks
    one per module) or is a data symbol -- this driver does not link any
    overlay, so it only needs the resident range to split "likely a
    function" from "likely data" among undefined symbols with a known
    retail address."""
    with open(os.path.join(ROOT, "config", "pc", "guest_addresses.txt")) as handle:
        for line in handle:
            parts = line.split()
            if parts and parts[0] == "text":
                return int(parts[1], 16), int(parts[2], 16)
    return 0, 0


def guest_addresses_map():
    addresses = {}
    with open(os.path.join(ROOT, "config", "pc", "guest_addresses.txt")) as handle:
        for line in handle:
            parts = line.split()
            if not parts or parts[0].startswith("#") or parts[0] == "text" or parts[0].startswith("["):
                continue
            if len(parts) == 2:
                addresses.setdefault(parts[0], int(parts[1], 16))
    return addresses


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", nargs="?", choices=("build", "run"), default="build")
    options = parser.parse_args()

    if not os.path.exists(os.path.join(DEPS, "lib", "libSDL3.a")):
        sys.exit(f"{DEPS}: chưa có (chạy `python3 tools/pc/macos/build_deps.py` trước, T1.9)")

    os.makedirs(BUILD, exist_ok=True)
    os.makedirs(GEN, exist_ok=True)
    print("== gen_globals.py (ADR-03 census) ==")
    run([sys.executable, "tools/pc/lp64/gen_globals.py"])
    print("== gen_fn_table.py (ADR-04 GCALL table) ==")
    run([sys.executable, "tools/pc/lp64/gen_fn_table.py"])
    print("== codemod.py ==")
    run([sys.executable, "tools/pc/lp64/codemod.py"])

    game_sources = sorted(glob.glob(os.path.join(OUT_SRC, "game", "*.c")) +
                          glob.glob(os.path.join(OUT_SRC, "psyq", "*.c")))
    native_sources_list = native_sources()
    fn_table_source = os.path.join(GEN, "fn_table.c")

    jobs = [(s, GAME_CFLAGS) for s in game_sources] + \
           [(s, NATIVE_CFLAGS) for s in native_sources_list] + \
           [(fn_table_source, NATIVE_CFLAGS)]
    print(f"== compile ({len(jobs)} unit) ==")
    with concurrent.futures.ThreadPoolExecutor(os.cpu_count()) as pool:
        results = list(pool.map(compile_unit, jobs))
    # .S files compile with a plain clang invocation too (no C flags they
    # do not understand); state_arm64.S needs none of GAME_CFLAGS/
    # NATIVE_CFLAGS's -D/-I at all, but sharing the job list keeps this
    # loop single-pass. Mach-O assembler accepts the extra -D/-I silently.

    failed = [(s, err) for s, ok, err in results if not ok]
    compiled = {s: obj_path(s) for s, ok, _ in results if ok}
    if failed:
        os.makedirs(os.path.join(BUILD, "fail-logs"), exist_ok=True)
        for source, stderr in failed:
            log = os.path.join(BUILD, "fail-logs", os.path.basename(source) + ".log")
            with open(log, "w") as handle:
                handle.write(stderr)
        print(f"   {len(failed)}/{len(jobs)} unit KHÔNG compile được dưới LP64 (loại khỏi build, "
              f"xem {BUILD}/fail-logs/*.log); hàm của chúng sẽ thành stub")

    objects = list(compiled.values())
    defined, undefined = symbols(objects)
    with open(FUNCTIONS_CSV) as handle:
        functions = {row["name"]: row["status"] for row in csv.DictReader(handle)}
    for overlay_csv in glob.glob(os.path.join(ROOT, "config", "slus_01411", "overlays", "*_functions.csv")):
        with open(overlay_csv) as handle:
            functions.update((row["name"], row["status"]) for row in csv.DictReader(handle))
    host_libc = {"printf", "sprintf", "snprintf", "vsnprintf", "fprintf", "strcmp", "strcpy", "strncpy",
                "strncmp", "strcat", "strlen", "strchr", "strrchr", "strstr", "strtol", "strtoul",
                "strtod", "strdup", "memcpy", "memset", "memmove", "memcmp", "qsort", "bsearch",
                "malloc", "calloc", "realloc", "free", "abort", "exit", "atoi", "atof", "rand", "srand",
                "fopen", "fclose", "fread", "fwrite", "fseek", "ftell", "fflush", "remove", "rename",
                "getenv", "setenv", "unsetenv", "puts", "putchar", "getchar", "tolower", "toupper",
                "isalpha", "isdigit", "isspace", "isalnum", "pow", "sqrt", "sin", "cos", "tan", "atan2",
                "floor", "ceil", "fabs", "fmod", "roundf", "sinf", "cosf"}
    wanted = sorted(undefined - defined - host_libc)

    # A function can be stubbed (log its name, abort) regardless of why it
    # is undefined -- real decompiled source whose .c failed to compile
    # (see `failed` above) or a retail function with no C yet, same as
    # build_game32.py's own resilience model. A GLOBAL VARIABLE cannot: it
    # has no calling convention to abort out of, a fake `void name(void)`
    # body would just be code sitting where callers expect readable/
    # writable storage. ADR-03 is the only correct fix for one of these
    # (ADR-03/T1.5 phien 3 just wired up most of it; remaining gaps are
    # tracked in docs/macos/PROGRESS.md, not papered over here) -- split
    # `wanted` by whether the name's retail address (if any) falls inside
    # the resident image's own .text range (a function) or not (data),
    # matching build_game32.py's own classify-by-address logic.
    addresses = guest_addresses_map()
    text_start, text_end = guest_addresses_text_range()
    data_blockers = sorted(name for name in wanted if name not in functions and
                           addresses.get(name) is not None and
                           not (text_start <= addresses[name] < text_end))
    if data_blockers:
        report_path = os.path.join(BUILD, "data-blockers.json")
        with open(report_path, "w") as handle:
            json.dump(data_blockers, handle, indent=1)
        sys.exit(f"build: {len(data_blockers)} global (du lieu, khong phai ham) van chua co cho luu tru "
                 f"(ADR-03 chua xong cho ten nay) -- khong the stub an toan. Danh sach: {report_path}\n"
                 f"  vi du: {', '.join(data_blockers[:10])}")

    stubs_path = os.path.join(BUILD, "stubs.c")
    with open(stubs_path, "w") as handle:
        handle.write('#include <stdio.h>\n#include <stdlib.h>\n\n')
        handle.write("void Memories_Unimplemented(const char *name)\n{\n")
        handle.write('    fprintf(stderr, "memories-pc: chua co ham nay: %s\\n", name);\n')
        handle.write("    abort();\n}\n\n")
        handle.writelines(f'void {name}(void) {{ Memories_Unimplemented("{name}"); }}\n' for name in wanted)
    run(["clang", *NATIVE_CFLAGS, "-c", stubs_path, "-o", os.path.join(BUILD, "stubs.o")])

    report = {"game_units": len(game_sources), "native_units": len(native_sources_list),
              "compile_failed": sorted(s for s, _ in failed),
              "stubbed": {kind: sorted(n for n in wanted if functions.get(n, "khong_trong_functions_csv") == kind)
                          for kind in sorted({functions.get(n, "khong_trong_functions_csv") for n in wanted})}}
    with open(os.path.join(BUILD, "link-report.json"), "w") as handle:
        json.dump(report, handle, indent=1)

    output = os.path.join(BUILD, "memories-pc")
    frameworks = ["Cocoa", "IOKit", "Carbon", "CoreAudio", "AudioToolbox", "CoreVideo", "CoreHaptics",
                 "GameController", "ForceFeedback", "Metal", "QuartzCore", "UniformTypeIdentifiers",
                 "AVFoundation", "CoreMedia", "OpenGL"]
    link_command = ["clang", "-arch", "arm64", "-o", output, *objects, os.path.join(BUILD, "stubs.o"),
                    os.path.join(DEPS, "lib", "libSDL3.a"), os.path.join(DEPS, "lib", "libfreetype.a")]
    for framework in frameworks:
        link_command += ["-framework", framework]
    print("== link ==")
    run(link_command)
    print(f"{output}: {len(game_sources)} game unit, {len(native_sources_list) + 1} native unit, "
          f"{len(failed)} compile lỗi (loại), {len(wanted)} stub "
          f"({', '.join(f'{len(v)} {k}' for k, v in report['stubbed'].items())})")

    if options.action == "run":
        print("== run ==")
        os.execv(output, [output])


if __name__ == "__main__":
    main()
