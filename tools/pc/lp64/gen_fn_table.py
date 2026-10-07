#!/usr/bin/env python3
"""T1.6 (ADR-04): generates tmp/lp64/gen/fn_table.c -- Memories_FunctionMap,
the LP64 equivalent of tools/pc/build_game32.py's own generation of the same
table (its stubs.c, ~line 700) for the ILP32 build. There, the mapping is
verified against *compiled* object files (`nm` after linking); no build
driver exists yet for LP64 (T1.10), so this verifies against *source*
instead: libclang scanning every *.c file that could plausibly hold a real,
correctly-named implementation (src/game, src/psyq, src/pc/compat,
src/pc/sdk -- the last two are where this fork's native PC reimplementations
of PSY-Q SDK routines live, e.g. src/pc/sdk/libgs.c's GsSortFastSprite) for a
FUNCTION_DECL with that exact name that `cursor.is_definition()`.

config/slus_01411/functions.csv's `status` column is informative, not
authoritative: every name is independently checked against source regardless
of status, since a decompile's status can go stale. A name with no real
definition anywhere in scanned scope gets a generated stub that calls
Memories_Unimplemented (src/pc/guest/image.c; already platform-neutral,
reused as-is from tools/pc/build_game32.py's own stubs.c) -- same contract
as upstream's ILP32 stub generation for any undefined retail symbol.

Also emits Memories_SymbolTable (address, name; every functions.csv row,
whether or not a host function was found) purely for GCALL's "nearest
symbol" diagnostic on a lookup miss (src/pc/guest/fn_table_lp64.c) -- the
existing ILP32 fault path (image.c's report_guest_fault) does not have this,
added here because T1.6's milestone acceptance explicitly asks for it.

Read-only except for --output. Never touches src/game, src/psyq,
src/overlays, ygo_types.h or types.h."""
import argparse, csv, glob, os, sys

sys.path.insert(0, os.path.dirname(__file__))
import clang.cindex as cindex
import codemod

SCAN_GLOBS = ["game/*.c", "psyq/*.c", "pc/compat/*.c", "pc/sdk/*.c"]


def load_functions(path):
    rows = []
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append({
                "address": int(row["address"], 16),
                "name": row["name"],
                "status": row["status"],
                "module": row["module"],
            })
    return rows


def scan_definitions(src_dir, wanted):
    """name -> True for every `wanted` name with a real top-level
    FUNCTION_DECL definition in its own file (not a prototype pulled in via
    #include) under SCAN_GLOBS. Needs a full parse (parse_code, which does
    not skip function bodies) -- codemod.py's own parse() uses
    PARSE_SKIP_FUNCTION_BODIES for speed, which makes is_definition() return
    False for every function, including ones with a real body (verified
    empirically before writing this; skip-bodies parsing does not commit to
    "this has a body" at all, not even for the file being parsed itself)."""
    found = set()
    files = sorted({p for pattern in SCAN_GLOBS
                     for p in glob.glob(os.path.join(src_dir, pattern))})
    for path in files:
        tu = codemod.parse_code(path, src_dir, src_dir)
        if tu is None:
            continue
        filename = os.path.basename(path)
        for cursor in tu.cursor.get_children():
            if cursor.kind != cindex.CursorKind.FUNCTION_DECL:
                continue
            if cursor.spelling not in wanted or cursor.spelling in found:
                continue
            if not cursor.is_definition():
                continue
            if cursor.location.file is None or os.path.basename(str(cursor.location.file)) != filename:
                continue
            found.add(cursor.spelling)
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--functions", default="config/slus_01411/functions.csv")
    parser.add_argument("--src", default="src")
    parser.add_argument("--output", default="tmp/lp64/gen/fn_table.c")
    options = parser.parse_args()
    codemod.setup_libclang()

    rows = load_functions(options.functions)
    wanted = {row["name"] for row in rows}
    print(f"functions.csv: {len(rows)} row(s), {len(wanted)} distinct name(s)")

    found = scan_definitions(options.src, wanted)
    by_status = {}
    for row in rows:
        by_status.setdefault(row["status"], [0, 0])
        by_status[row["status"]][0] += 1
        if row["name"] in found:
            by_status[row["status"]][1] += 1
    for status, (total, matched) in sorted(by_status.items()):
        print(f"  {status:20s} {matched:5d}/{total:<5d} have a real definition in scanned scope")

    # functions.csv should already be one row per address; guard against a
    # surprise rather than silently emit a duplicate address in the table
    # the binary search in src/pc/guest/fn_table_lp64.c depends on being
    # sorted with each address appearing once.
    by_address = {}
    conflicts = []
    for row in rows:
        existing = by_address.get(row["address"])
        if existing is not None and existing["name"] != row["name"]:
            conflicts.append((row["address"], existing["name"], row["name"]))
            continue
        by_address[row["address"]] = row
    if conflicts:
        print(f"WARNING: {len(conflicts)} address(es) claimed by two different names "
              f"-- keeping the first seen, dropping the rest: {conflicts[:5]}"
              + (" ..." if len(conflicts) > 5 else ""))

    entries = sorted(by_address.values(), key=lambda r: r["address"])
    real = sorted((r for r in entries if r["name"] in found), key=lambda r: r["name"])
    stub = sorted((r for r in entries if r["name"] not in found), key=lambda r: r["name"])

    os.makedirs(os.path.dirname(options.output) or ".", exist_ok=True)
    with open(options.output, "w") as handle:
        handle.write("/* Generated by tools/pc/lp64/gen_fn_table.py -- do not edit, do not commit\n"
                      " * (tmp/lp64/ is gitignored). See the module docstring for how entries are\n"
                      " * classified real vs. stub. */\n")
        handle.write('#include "pc/guest/image.h"\n\n')
        for row in real:
            handle.write(f"extern void {row['name']}(void);\n")
        handle.write("\n")
        for row in stub:
            handle.write(f'static void {row["name"]}_stub(void) {{ Memories_Unimplemented("{row["name"]}"); }}\n')
        handle.write("\nconst MemoriesGuestFunction Memories_FunctionMap[] = {\n")
        for row in entries:
            target = row["name"] if row["name"] in found else f'{row["name"]}_stub'
            handle.write(f'    {{0x{row["address"]:08X}u, {target}, 0, 0}},\n')
        handle.write("};\n")
        handle.write(f"const unsigned Memories_FunctionMapCount = {len(entries)};\n\n")
        handle.write("const MemoriesGuestSymbol Memories_SymbolTable[] = {\n")
        for row in entries:
            handle.write(f'    {{0x{row["address"]:08X}u, "{row["name"]}"}},\n')
        handle.write("};\n")
        handle.write(f"const unsigned Memories_SymbolTableCount = {len(entries)};\n")
    print(f"wrote {options.output}: {len(entries)} entries ({len(real)} real, {len(stub)} stub)")


if __name__ == "__main__":
    main()
