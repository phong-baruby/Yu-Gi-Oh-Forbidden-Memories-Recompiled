#!/usr/bin/env python3
"""Syntax-check every game/overlay C unit with clang targeting arm64 macOS.

Baseline for the LP64 (8-byte pointer) memory model: which units survive an
arm64 front end today, and what breaks, grouped by error kind. Says nothing
about linking, fixed addresses or behavior -- see tools/pc/host_census.py for
the ILP32/LP64-on-host counterpart this mirrors. Read-only: never touches
src/game, src/overlays, src/psyq, ygo_types.h or types.h."""
import argparse, collections, concurrent.futures, glob, json, os, re, subprocess

CLANG_FLAGS = ["--target=arm64-apple-macos", "-std=gnu11", "-DMEMORIES_PC",
               "-D_LANGUAGE_C", "-DLANGUAGE_C", "-ferror-limit=0"]

def check(path):
    run = subprocess.run(["clang", *CLANG_FLAGS, "-fsyntax-only", "-w", "-Isrc", path],
                         capture_output=True, text=True)
    errors = [re.sub(r"[‘'][^’']*[’']", "X", line.split("error: ", 1)[1])
              for line in run.stderr.splitlines() if "error: " in line]
    return path, run.returncode == 0, errors

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="tmp/lp64/census.json")
    options = parser.parse_args()
    units = sorted(glob.glob("src/game/*.c") + glob.glob("src/overlays/*/*.c"))
    with concurrent.futures.ThreadPoolExecutor(os.cpu_count()) as pool:
        results = list(pool.map(check, units))
    kinds = collections.Counter(e for _, _, errors in results for e in errors)
    passed = sum(ok for _, ok, _ in results)
    report = {"passed": passed, "units": len(units),
              "failed": [p for p, ok, _ in results if not ok],
              "error_kinds": dict(kinds.most_common())}
    print(f"lp64 (arm64 clang -fsyntax-only): {passed} / {len(units)} units pass")
    for kind, count in kinds.most_common(10):
        print(f"  {count:4d}  {kind}")
    os.makedirs(os.path.dirname(options.output), exist_ok=True)
    with open(options.output, "w") as handle:
        json.dump(report, handle, indent=1)

if __name__ == "__main__":
    main()
