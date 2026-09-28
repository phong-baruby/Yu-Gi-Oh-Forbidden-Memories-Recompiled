#!/usr/bin/env python3
"""Report how far macos/main has drifted from upstream/master.

Group (a): existing upstream files that were modified — the "diff budget"
we want to keep small so future `sync-upstream` rebases stay cheap.

Group (b): the decompiled/PSX-SDK directories and headers we are never
allowed to hand-edit (see CLAUDE.md invariant #1). Must always be empty;
non-zero exit code otherwise.
"""
import subprocess
import sys

BASE_REF = "upstream/master"

FORBIDDEN_PREFIXES = (
    "src/game/",
    "src/overlays/",
    "src/psyq/",
)
FORBIDDEN_FILES = (
    "src/ygo_types.h",
    "src/types.h",
)


def is_forbidden(path):
    return path in FORBIDDEN_FILES or any(path.startswith(p) for p in FORBIDDEN_PREFIXES)


def git(*args):
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout


def repo_root():
    try:
        return git("rev-parse", "--show-toplevel").strip()
    except subprocess.CalledProcessError:
        print("error: not inside a git repository", file=sys.stderr)
        sys.exit(2)


def main():
    import os

    os.chdir(repo_root())

    try:
        name_status = git("diff", "--name-status", BASE_REF).splitlines()
        numstat = git("diff", "--numstat", BASE_REF).splitlines()
    except subprocess.CalledProcessError as exc:
        print(f"error: git diff against '{BASE_REF}' failed: {exc.stderr.strip()}", file=sys.stderr)
        print("hint: run `git fetch upstream` first.", file=sys.stderr)
        return 2

    status_by_path = {}
    for line in name_status:
        if not line:
            continue
        parts = line.split("\t")
        status_by_path[parts[-1]] = parts[0]

    group_a = []  # shared upstream files touched: (path, added, deleted)
    group_b = []  # forbidden files touched: (path, added, deleted)
    new_files = []  # brand-new macOS-port files, informational only

    for line in numstat:
        if not line:
            continue
        added, deleted, path = line.split("\t")
        added_n = 0 if added == "-" else int(added)
        deleted_n = 0 if deleted == "-" else int(deleted)
        status = status_by_path.get(path, "M")

        if is_forbidden(path):
            group_b.append((path, added_n, deleted_n))
        elif status.startswith("A"):
            new_files.append((path, added_n, deleted_n))
        else:
            group_a.append((path, added_n, deleted_n))

    print(f"Base: {BASE_REF}\n")

    print("(a) Shared upstream files touched (diff budget):")
    if group_a:
        total = 0
        for path, added_n, deleted_n in sorted(group_a):
            print(f"  +{added_n:<5} -{deleted_n:<5} {path}")
            total += added_n + deleted_n
        print(f"  total changed lines: {total}")
    else:
        print("  (none)")

    print(f"\nNew macOS-port files (informational, not counted in budget): {len(new_files)}")
    for path, added_n, deleted_n in sorted(new_files):
        print(f"  +{added_n:<5} -{deleted_n:<5} {path}")

    print("\n(b) Forbidden directories/files touched (must be empty):")
    if group_b:
        for path, added_n, deleted_n in sorted(group_b):
            print(f"  +{added_n:<5} -{deleted_n:<5} {path}")
        print(f"\nFAIL: {len(group_b)} forbidden file(s) touched.", file=sys.stderr)
        return 1

    print("  (none)")
    print("\nOK: forbidden directories untouched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
