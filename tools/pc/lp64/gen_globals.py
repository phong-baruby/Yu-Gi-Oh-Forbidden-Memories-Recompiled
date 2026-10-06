#!/usr/bin/env python3
"""T1.5 stage 1 (measurement, not yet a codemod): how big is ADR-03's
"globals live in guest RAM" job, and what shapes do the real declarations
take? Cross-references config/pc/guest_addresses.txt (retail name -> 0x800...
address) against the actual top-level `extern` variable declarations already
in src/ -- headers under codemod.py's DEFAULT_GLOBS, plus *.c files under its
CODE_GLOBS (the 533 files T1.4 already brought under LP64) -- using libclang,
the same way codemod.py's own T1.3 struct-field scan works, just aimed at
file-scope VAR_DECL cursors instead of field decls inside a RecordDecl.

Why this matters before writing any codemod: T1.3's GPTR(T) transform only
touches pointer fields *inside* a struct/union -- a top-level
`extern GsOT *D_800E9D90[4];` (ordering_tables.h, one of the known T1.4
ADR-03 exclusions) is untouched by it and still a real 8-byte-pointer array
under LP64, which is exactly why its `sizeof(...) == 0x10` static assert
fails. A plain-data global (no pointer anywhere in its own declared type)
only needs a dereferencing macro -- `#define NAME (*(T *)G2H(0x800xxxxx))`
-- and every read/write/member-access already works through ordinary C
semantics, no AST work needed. A global that IS a pointer, or an array of
pointers, is structurally identical to a GPTR struct field and is expected
to need the same context-sensitive G2H/H2G classification
transform_c_expressions already does for MEMBER_REF_EXPR, extended to also
recognize a gaddr-typed DeclRefExpr -- real engineering, not yet written,
and this script's whole job is to measure how much of that is actually
needed before deciding whether to build it.

Classifies every guest_addresses.txt data-shaped name into:
  plain              -- no pointer anywhere in the declared type -> macro only
  pointer             -- the global itself is a pointer
  pointer-array        -- an array of pointers (ordering_tables.h's shape)
  struct-with-pointer  -- a struct/union VALUE type whose own immediate
                          fields contain a pointer (T1.3 already GPTR's
                          those fields; flagged separately from "plain"
                          only so the census is honest about it, since it's
                          not nothing-to-do, just already-someone-else's-job)
  no-match             -- name is in guest_addresses.txt but no VAR_DECL
                          found in the scanned scope (a function; an
                          overlay-only global out of scope; a name this
                          script's glob/parse does not reach)
  conflicting          -- matched more than once with incompatible types
                          (e.g. gpu_packets.h's D_800FE240, declared both
                          `s32` and `u32 *` under different #ifdef branches)

Read-only: writes only --output (default tmp/lp64/gen/globals_census.json).
Never touches src/game, src/overlays, src/psyq, ygo_types.h or types.h."""
import argparse, glob, json, os, re, sys

sys.path.insert(0, os.path.dirname(__file__))
import clang.cindex as cindex
import codemod

ADDR_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*)\s+([0-9A-Fa-f]{8})$")


def load_guest_addresses(path):
    """name -> address (int), one entry per base name (the file repeats
    many as a plain name and a `.NON_MATCHING` twin at the same address;
    keep the base name only). Skips the leading `text ADDR ADDR` line and
    `[SLUS_...]` section markers -- neither is a name/address pair."""
    addresses = {}
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("["):
                continue
            m = ADDR_LINE_RE.match(line)
            if not m:
                continue
            name, address = m.group(1), int(m.group(2), 16)
            if name.endswith(".NON_MATCHING"):
                name = name[:-len(".NON_MATCHING")]
            if address < 0x80000000 or address >= 0x80200000:
                continue  # text/data range only (ADR-01's guest RAM window)
            addresses.setdefault(name, address)
    return addresses


def type_shape(field_type):
    """(shape, canonical_spelling) for a VAR_DECL's type: "pointer",
    "pointer-array", "struct-with-pointer", or "plain". Mirrors
    codemod.py's field_shape/is_gaddr_type reasoning but at file scope: an
    array of pointers is the ordering_tables.h shape (GsOT *D_800E9D90[4]);
    a direct pointer covers scalars (u8 *D_8015C424 is itself declared as
    an array `u8 D_8015C424[]` in that case, not a pointer -- see its own
    entry, "plain" is correct for it: an array of plain bytes, no pointer)."""
    canonical = field_type.get_canonical()
    if canonical.kind == cindex.TypeKind.POINTER:
        return "pointer", canonical.spelling
    if canonical.kind in (cindex.TypeKind.CONSTANTARRAY, cindex.TypeKind.INCOMPLETEARRAY):
        element = canonical.get_array_element_type().get_canonical()
        if element.kind == cindex.TypeKind.POINTER:
            return "pointer-array", canonical.spelling
        return "plain", canonical.spelling
    if canonical.kind == cindex.TypeKind.RECORD:
        decl = canonical.get_declaration()
        for field in decl.get_children():
            if field.kind != cindex.CursorKind.FIELD_DECL:
                continue
            ft = field.type.get_canonical()
            if ft.kind == cindex.TypeKind.POINTER:
                return "struct-with-pointer", canonical.spelling
            if ft.kind in (cindex.TypeKind.CONSTANTARRAY, cindex.TypeKind.INCOMPLETEARRAY) and \
                    ft.get_array_element_type().get_canonical().kind == cindex.TypeKind.POINTER:
                return "struct-with-pointer", canonical.spelling
        return "plain", canonical.spelling
    return "plain", canonical.spelling


def scan_file(path, include_dir, wanted, found):
    tu = codemod.parse(path, include_dir)
    if tu is None:
        return
    for cursor in tu.cursor.get_children():
        if cursor.kind != cindex.CursorKind.VAR_DECL:
            continue
        name = cursor.spelling
        if name not in wanted:
            continue
        shape, spelling = type_shape(cursor.type)
        is_extern = cursor.storage_class == cindex.StorageClass.EXTERN
        found.setdefault(name, []).append({
            "file": path,
            "shape": shape,
            "type": spelling,
            "extern": is_extern,
            "definition": cursor.is_definition() and not is_extern,
        })


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--src", default="src", help="source tree to scan")
    parser.add_argument("--addresses", default="config/pc/guest_addresses.txt")
    parser.add_argument("--output", default="tmp/lp64/gen/globals_census.json")
    options = parser.parse_args()
    codemod.setup_libclang()

    addresses = load_guest_addresses(options.addresses)
    wanted = set(addresses)

    headers = sorted({p for pattern in codemod.DEFAULT_GLOBS
                       for p in glob.glob(os.path.join(options.src, pattern), recursive=True)})
    code = sorted({p for pattern in codemod.CODE_GLOBS
                    for p in glob.glob(os.path.join(options.src, pattern), recursive=True)})

    found = {}
    for path in headers + code:
        scan_file(path, options.src, wanted, found)

    classified = {"plain": [], "pointer": [], "pointer-array": [],
                  "struct-with-pointer": [], "conflicting": [], "no-match": []}
    conflicts = {}
    for name in sorted(wanted):
        hits = found.get(name)
        if not hits:
            classified["no-match"].append(name)
            continue
        shapes = {h["shape"] for h in hits}
        if len(shapes) > 1:
            classified["conflicting"].append(name)
            conflicts[name] = hits
            continue
        classified[hits[0]["shape"]].append(name)

    has_definition = {name for name, hits in found.items() if any(h["definition"] for h in hits)}
    orphans = {name for name in wanted if name in found and name not in has_definition}

    print(f"guest_addresses.txt data-range candidates: {len(wanted)}")
    for shape in ("plain", "pointer", "pointer-array", "struct-with-pointer"):
        names = classified[shape]
        with_def = sum(1 for n in names if n in has_definition)
        print(f"  {shape:20s} {len(names):5d}  ({with_def} have a real definition, "
              f"{len(names) - with_def} orphan -- extern only)")
    print(f"  {'conflicting':20s} {len(classified['conflicting']):5d}  (different shape across declarations)")
    print(f"  {'no-match':20s} {len(classified['no-match']):5d}  (not found as a VAR_DECL in scanned scope)")

    os.makedirs(os.path.dirname(options.output) or ".", exist_ok=True)
    with open(options.output, "w") as handle:
        json.dump({
            "addresses": addresses,
            "classified": classified,
            "conflicts": conflicts,
            "orphans": sorted(orphans),
            "declarations": found,
        }, handle, indent=1)
    print(f"wrote {options.output}")


if __name__ == "__main__":
    main()
