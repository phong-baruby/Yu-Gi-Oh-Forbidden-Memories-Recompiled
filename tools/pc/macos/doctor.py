#!/usr/bin/env python3
"""Check that this Mac has everything the macOS arm64 port tooling needs.

Each check is independent and prints a fix hint on failure. Exit code is 0
only if every check passes except MEMORIES_DISC, which is a warning-only
convenience check (see CLAUDE.md invariant #4).
"""
import os
import shutil
import subprocess
import sys

OK, WARN, FAIL = "OK", "WARN", "FAIL"
ICONS = {OK: "\U0001F7E2", WARN: "\U0001F7E1", FAIL: "\U0001F534"}

BREW_LLVM_FALLBACK = "/opt/homebrew/opt/llvm"
MIN_PYTHON = (3, 11)


def run(*args):
    return subprocess.run(args, capture_output=True, text=True)


def check_xcode_clt():
    name = "Xcode Command Line Tools"
    sel = run("xcode-select", "-p")
    if sel.returncode != 0:
        return name, FAIL, "xcode-select -p thất bại", "Chạy `xcode-select --install`."

    ver = run("clang", "--version")
    if ver.returncode != 0 or "Apple clang" not in ver.stdout:
        return (
            name,
            FAIL,
            f"clang không phải Apple clang: {ver.stdout.strip() or ver.stderr.strip()}",
            "Cài Xcode Command Line Tools: `xcode-select --install`.",
        )

    target_line = next((l for l in ver.stdout.splitlines() if l.startswith("Target:")), "")
    if "arm64" not in target_line:
        return (
            name,
            FAIL,
            f"clang target không phải arm64: {target_line}",
            "Kiểm tra lại kiến trúc máy (uname -m) và cài đặt Xcode.",
        )
    return name, OK, ver.stdout.splitlines()[0], None


def find_brew_llvm_prefix():
    brew = shutil.which("brew")
    if brew:
        result = run(brew, "--prefix", "llvm")
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    if os.path.isdir(BREW_LLVM_FALLBACK):
        return BREW_LLVM_FALLBACK
    return None


def check_brew_llvm():
    name = "Homebrew llvm (libclang + aarch64-none-elf)"
    prefix = find_brew_llvm_prefix()
    if not prefix:
        return (
            name,
            FAIL,
            "Không tìm thấy Homebrew llvm",
            "Cài: `brew install llvm`.",
        )

    libclang = os.path.join(prefix, "lib", "libclang.dylib")
    if not os.path.exists(libclang):
        return (
            name,
            FAIL,
            f"Thiếu {libclang}",
            "Cài lại: `brew reinstall llvm`.",
        )

    clang_bin = os.path.join(prefix, "bin", "clang")
    target_check = run(clang_bin, "--target=aarch64-none-elf", "-E", "-x", "c", "/dev/null", "-o", "/dev/null")
    if target_check.returncode != 0:
        return (
            name,
            FAIL,
            f"{clang_bin} --target=aarch64-none-elf thất bại: {target_check.stderr.strip()}",
            "Cài lại: `brew reinstall llvm`.",
        )
    return name, OK, f"prefix={prefix}", None


def check_cmake_ninja():
    name = "cmake, ninja"
    missing = [tool for tool in ("cmake", "ninja") if shutil.which(tool) is None]
    if missing:
        return (
            name,
            FAIL,
            f"Thiếu: {', '.join(missing)}",
            f"Cài: `brew install {' '.join(missing)}`.",
        )
    versions = {tool: run(tool, "--version").stdout.splitlines()[0] for tool in ("cmake", "ninja")}
    return name, OK, "; ".join(f"{k}: {v}" for k, v in versions.items()), None


def check_python_version():
    name = f"python3 ≥ {MIN_PYTHON[0]}.{MIN_PYTHON[1]}"
    have = sys.version_info[:2]
    detail = f"{sys.executable} ({sys.version.split()[0]})"
    if have < MIN_PYTHON:
        return (
            name,
            FAIL,
            detail,
            "python3 đang trỏ tới bản cũ. Kiểm tra thứ tự PATH (ví dụ các khối "
            "`Setting PATH for Python ...` do trình cài Python.org thêm vào "
            "~/.zprofile) và đảm bảo /opt/homebrew/bin đứng trước chúng, hoặc "
            "gọi thẳng /opt/homebrew/bin/python3.",
        )
    return name, OK, detail, None


def check_python_clang_binding():
    name = "Python binding `clang` (khớp libclang)"
    try:
        import clang.cindex as cindex
    except ImportError:
        return (
            name,
            FAIL,
            "Chưa cài package `clang`",
            "Cài: `python3 -m pip install --user --break-system-packages clang` "
            "(Homebrew Python là externally-managed nên cần --break-system-packages).",
        )

    try:
        cindex.Index.create()
        return name, OK, "libclang tự phát hiện được", None
    except Exception:
        pass

    libclang_path = os.environ.get("LIBCLANG_PATH")
    if not libclang_path:
        return (
            name,
            FAIL,
            "libclang không tự phát hiện được và LIBCLANG_PATH chưa được set",
            "Set `export LIBCLANG_PATH=$(brew --prefix llvm)/lib/libclang.dylib` "
            "trong ~/.zprofile.",
        )

    try:
        cindex.Config.set_library_file(libclang_path)
        cindex.Index.create()
        return name, OK, f"libclang qua LIBCLANG_PATH={libclang_path}", None
    except Exception as exc:
        return (
            name,
            FAIL,
            f"LIBCLANG_PATH={libclang_path} nhưng vẫn load lỗi: {exc}",
            "Kiểm tra LIBCLANG_PATH có trỏ đúng kiến trúc arm64 và version khớp "
            "với `brew --prefix llvm` không.",
        )


def check_memories_disc():
    name = "MEMORIES_DISC (chỉ cảnh báo)"
    value = os.environ.get("MEMORIES_DISC")
    if not value:
        return name, WARN, "chưa set", "export MEMORIES_DISC=~/Games/YFM/yfm-usa.bin (thêm vào ~/.zshrc)."
    if not os.path.isfile(value):
        return name, WARN, f"file không tồn tại: {value}", "Kiểm tra lại đường dẫn disc."
    return name, OK, value, None


CHECKS = (
    check_xcode_clt,
    check_brew_llvm,
    check_cmake_ninja,
    check_python_version,
    check_python_clang_binding,
    check_memories_disc,
)


def main():
    had_failure = False
    for check in CHECKS:
        name, status, detail, hint = check()
        print(f"{ICONS[status]} {name}: {detail}")
        if hint:
            print(f"   -> {hint}")
        if status == FAIL:
            had_failure = True
    return 1 if had_failure else 0


if __name__ == "__main__":
    sys.exit(main())
