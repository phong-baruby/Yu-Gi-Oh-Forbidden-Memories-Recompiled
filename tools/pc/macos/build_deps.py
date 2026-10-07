#!/usr/bin/env python3
"""Fetch and build SDL3 + FreeType from source, static, for the macOS arm64 build.

Linux borrows a Debian 11 sysroot and builds only SDL3 from source
(tools/pc/build_linux_sysroot.py); Windows builds zlib/libpng/FreeType from
source but takes SDL3 as a prebuilt MinGW release (tools/pc/build_win32_deps.py).
macOS has neither a borrowable system sysroot nor a prebuilt SDL3 macOS
archive to lean on, so both SDL3 and FreeType are built from source here --
natively (no cross-compile, no toolchain file: the host IS the target, arm64
only per CLAUDE.md invariant #8). zlib/libpng are not needed: FreeType's own
-DFT_DISABLE_ZLIB/-DFT_DISABLE_PNG flags (same ones Windows already uses)
avoid both dependencies entirely, matching ADR-10's dependency list (SDL3,
FreeType, libclang, Python stdlib -- no zlib/libpng).

cmake and ninja are expected on PATH (tools/pc/macos/doctor.py already
requires them via Homebrew, a dev tool, not a shipped dependency)."""
import hashlib, os, shutil, subprocess, sys, tarfile, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT = os.path.join(ROOT, "tmp", "pc", "macos-deps")
ARCHIVES = {
    # Same release Linux pins (tools/pc/build_linux_sysroot.py).
    "sdl": ("https://github.com/libsdl-org/SDL/releases/download/release-3.4.16/SDL3-3.4.16.tar.gz",
            "7322236cd12090c3eb40b9728be4d49c76f66ad17d04369584d4ecad5cf77c68"),
    # Same release Windows pins (tools/pc/build_win32_deps.py) -- no macOS-
    # specific reason to diverge, kept for consistency across platforms.
    "freetype": ("https://github.com/freetype/freetype/archive/refs/tags/VER-2-14-3.tar.gz",
                 "dc49de6b01a266eef4876a4dd34d9842c475d3e28ff2eff63bd2fb760ab56261"),
}


def fetch(name):
    url, digest = ARCHIVES[name]
    path = os.path.join(OUT, "downloads", os.path.basename(url))
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        print(f"fetch {url}")
        with urllib.request.urlopen(url, timeout=120) as response, open(path + ".part", "wb") as handle:
            shutil.copyfileobj(response, handle)
        os.replace(path + ".part", path)
    with open(path, "rb") as handle:
        actual = hashlib.sha256(handle.read()).hexdigest()
    if actual != digest:
        sys.exit(f"build_deps: {path} SHA-256 {actual}, expected {digest}; run again")
    source = os.path.join(OUT, "src", name)
    if not os.path.isdir(source):
        with tarfile.open(path) as archive:
            top = archive.getnames()[0].split("/")[0]
            if hasattr(tarfile, "data_filter"):
                archive.extractall(os.path.join(OUT, "src"), filter="data")
            else:
                archive.extractall(os.path.join(OUT, "src"))
        os.replace(os.path.join(OUT, "src", top), source)
    return source


def cmake_build(name, source, *options):
    """Configure, build and install `name` into OUT. Skipped entirely (no
    cmake/ninja invocation) when a stamp file from a previous run still
    names the same pinned archive URL -- the cache-hit path the T1.9
    acceptance check runs twice in a row to confirm."""
    stamp = os.path.join(OUT, f".{name}-complete")
    url = ARCHIVES[name][0]
    if os.path.exists(stamp):
        with open(stamp) as handle:
            if handle.read() == url:
                print(f"{name}: cache hit ({stamp}), bo qua build")
                return
    build = os.path.join(OUT, "build", name)
    subprocess.run(["cmake", "-S", source, "-B", build, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
                    "-DCMAKE_OSX_ARCHITECTURES=arm64",
                    f"-DCMAKE_INSTALL_PREFIX={OUT}", f"-DCMAKE_PREFIX_PATH={OUT}",
                    "-DCMAKE_POLICY_VERSION_MINIMUM=3.5", *options], check=True)
    subprocess.run(["cmake", "--build", build, "--target", "install"], check=True)
    with open(stamp, "w") as handle:
        handle.write(url)


def build_smoke_test():
    """A tiny static-linked executable calling one SDL3 function and one
    FreeType function. T1.10 (the real build driver) does not exist yet, so
    this is the only way to run `otool -L` and confirm no Homebrew
    (/opt/homebrew, /usr/local) path leaked into a build of this repo."""
    source = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smoke_test.c")
    binary = os.path.join(OUT, "smoke_test")
    include = os.path.join(OUT, "include")
    lib = os.path.join(OUT, "lib")
    subprocess.run(["clang", "-arch", "arm64", source, "-o", binary,
                    f"-I{include}", f"-I{os.path.join(include, 'freetype2')}",
                    f"-L{lib}", "-lSDL3", "-lfreetype",
                    "-framework", "Cocoa", "-framework", "IOKit", "-framework", "Carbon",
                    "-framework", "CoreAudio", "-framework", "AudioToolbox", "-framework", "CoreVideo",
                    "-framework", "CoreHaptics", "-framework", "GameController", "-framework", "ForceFeedback",
                    "-framework", "Metal", "-framework", "QuartzCore", "-framework", "UniformTypeIdentifiers",
                    "-framework", "AVFoundation", "-framework", "CoreMedia"],
                   check=True)
    return binary


def main():
    if shutil.which("cmake") is None or shutil.which("ninja") is None:
        sys.exit("build_deps: thieu cmake/ninja tren PATH (xem tools/pc/macos/doctor.py)")
    os.makedirs(OUT, exist_ok=True)
    cmake_build("sdl", fetch("sdl"),
                "-DSDL_SHARED=OFF", "-DSDL_STATIC=ON", "-DSDL_TESTS=OFF", "-DSDL_TEST_LIBRARY=OFF",
                "-DSDL_EXAMPLES=OFF", "-DSDL_INSTALL=ON")
    cmake_build("freetype", fetch("freetype"),
                "-DBUILD_SHARED_LIBS=OFF", "-DFT_DISABLE_ZLIB=ON", "-DFT_DISABLE_BZIP2=ON",
                "-DFT_DISABLE_PNG=ON", "-DFT_DISABLE_HARFBUZZ=ON", "-DFT_DISABLE_BROTLI=ON")
    binary = build_smoke_test()
    print(f"macos deps: {OUT}")
    print(f"smoke test: {binary}")


if __name__ == "__main__":
    main()
