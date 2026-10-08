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
    """(shape, canonical_spelling, pointee_spelling, array_size) for a
    VAR_DECL's type: "pointer", "pointer-array", "struct-with-pointer", or
    "plain". Mirrors codemod.py's field_shape/is_gaddr_type reasoning but at
    file scope: an array of pointers is the ordering_tables.h shape
    (GsOT *D_800E9D90[4]); a direct pointer covers scalars (u8 *D_8015C424
    is itself declared as an array `u8 D_8015C424[]` in that case, not a
    pointer -- see its own entry, "plain" is correct for it: an array of
    plain bytes, no pointer). pointee_spelling/array_size are only
    meaningful for "pointer"/"pointer-array" (the shapes gen_globals.py's
    codemod companion needs to emit a `gaddr`/`gaddr[N]` wrapper for);
    array_size is None for a scalar pointer or an incomplete array (`T *[]`,
    size not stated at this declaration -- the caller picks a canonical
    size across every declaration of the same name)."""
    canonical = field_type.get_canonical()
    if canonical.kind == cindex.TypeKind.POINTER:
        pointee = canonical.get_pointee()
        return "pointer", canonical.spelling, pointee.spelling, None
    if canonical.kind in (cindex.TypeKind.CONSTANTARRAY, cindex.TypeKind.INCOMPLETEARRAY):
        element = canonical.get_array_element_type()
        element_canonical = element.get_canonical()
        size = canonical.get_array_size() if canonical.kind == cindex.TypeKind.CONSTANTARRAY else None
        if element_canonical.kind == cindex.TypeKind.POINTER:
            return "pointer-array", canonical.spelling, element_canonical.get_pointee().spelling, size
        # T1.5 phien 3: a plain (non-pointer) array also needs its element
        # type/size reported, not just None -- codemod.py's plain-global
        # wrapper (ADR-03's direct macro, no GPTR) casts to a pointer-to-
        # array-of-element, which needs both to build the cast text.
        return "plain", canonical.spelling, element.spelling, size
    if canonical.kind == cindex.TypeKind.RECORD:
        decl = canonical.get_declaration()
        for field in decl.get_children():
            if field.kind != cindex.CursorKind.FIELD_DECL:
                continue
            ft = field.type.get_canonical()
            if ft.kind == cindex.TypeKind.POINTER:
                return "struct-with-pointer", canonical.spelling, None, None
            if ft.kind in (cindex.TypeKind.CONSTANTARRAY, cindex.TypeKind.INCOMPLETEARRAY) and \
                    ft.get_array_element_type().get_canonical().kind == cindex.TypeKind.POINTER:
                return "struct-with-pointer", canonical.spelling, None, None
        return "plain", canonical.spelling, None, None
    return "plain", canonical.spelling, None, None


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
        shape, spelling, pointee, array_size = type_shape(cursor.type)
        is_extern = cursor.storage_class == cindex.StorageClass.EXTERN
        found.setdefault(name, []).append({
            "file": path,
            "shape": shape,
            "type": spelling,
            "pointee": pointee,
            "array_size": array_size,
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
    # gGraphics_pActiveFrameBuffer: found by T1.10's build driver (link sweep,
    # 2026-10-08) as a 5th case of the same "extern in a header + a real
    # definition elsewhere" problem as the 4 above, missed by the
    # cursor.is_definition() check because its own defining line in
    # graphics_frame.c is a tentative definition (`GraphicsFrameBuffer
    # *gGraphics_pActiveFrameBuffer;`, no initializer) -- libclang's
    # is_definition() is false for that shape, same as every tentative
    # definition of every OTHER successfully-wrapped pointer global, so
    # generalizing the check to "any non-extern hit" would wrongly exclude
    # all of those too. What is actually different here: graphics_frame.c
    # both defines the symbol AND #include-s graphics_frame.h, which also
    # declares (and, via this same canonical/wrap mechanism, would also
    # macro-wrap) it -- two independent typedefs of the same anonymous
    # struct shape in one translation unit, a hard compile error
    # (`typedef redefinition with different types`) regardless of
    # initializers. Narrow, name-only exclusion (not a general rule) until
    # someone measures how many other pointer globals have this same
    # include-their-own-declaring-header shape.
    has_definition.add("gGraphics_pActiveFrameBuffer")
    orphans = {name for name in wanted if name in found and name not in has_definition}

    # Canonical shape for every "pointer"/"pointer-array" global: one
    # pointee spelling (all declarations already agree, by construction --
    # "conflicting" names were split out above) and the largest array size
    # seen across every declaration (an incomplete `T *name[]` elsewhere is
    # just that file not stating the count, not a different count).
    #
    # Excludes every name with a real C definition somewhere (not just
    # `extern`): T1.5 phien 2's compile sweep found 20 of these among the
    # 111 pointer/pointer-array symbols, and they split into two groups
    # neither of which this simple gaddr-wrapper macro can handle --
    # confirmed with fen, both deferred rather than worked around here:
    #   - 16 are function-pointer tables (pointee is a function type, the
    #     "apfn"-prefixed naming convention and its un-prefixed siblings --
    #     gMain_apfnModeRunner, gAiScript_apfnCommand, ...): calling through
    #     one (`gMain_apfnModeRunner[v & 0x1F]()`) needs a real native
    #     function pointer recovered from guest storage, which is ADR-04/
    #     T1.6's job, not yet built -- wrapping them here only produced
    #     "called object type 'gaddr' is not a function" everywhere they are
    #     read, both at their own definition site and every caller.
    #   - 4 are plain data pointers (D_8009AF18, D_8009AF88, D_8009B074,
    #     gFile_apszName) declared `extern` in one header and defined with a
    #     real initializer in a .c file -- wrapping both declarations
    #     produces two conflicting `NAME_global_t` typedefs in any
    #     translation unit that sees both (the .c file includes the
    #     header), and even with that deduplicated the real initializer
    #     (`= &gFile_PrimaryTransferDescriptor;`) has no storage left to
    #     write once NAME is a macro -- needs some other init-time
    #     mechanism (e.g. a startup function writing into guest RAM) not
    #     yet designed.
    canonical = {}
    for name in classified["pointer"] + classified["pointer-array"]:
        if name in has_definition:
            continue
        hits = found[name]
        pointee = hits[0]["pointee"]
        # ADR-04/T1.6 territory regardless of whether a definition was found
        # in CODE_GLOBS/DEFAULT_GLOBS's scan scope -- a function-typed
        # pointee is a function-pointer table (or scalar) either way, and
        # calling through one needs a real native function pointer recovered
        # from guest storage, not this gaddr-wrapper macro (see the
        # has_definition exclusion comment above for the 16 found this way
        # by their own definition site; this catches the rest, found by
        # T1.5 phien 2's compile sweep hitting "called object type 'gaddr'
        # is not a function" on an orphan-only -- extern-only -- symbol like
        # D_80090F58, never caught by the has_definition check since no
        # definition of it exists in scanned scope at all).
        if "(" in pointee:
            continue
        sizes = [h["array_size"] for h in hits if h["array_size"] is not None]
        canonical[name] = {
            "kind": "pointer",
            "address": addresses[name],
            "is_array": name in classified["pointer-array"],
            "pointee": pointee,
            "array_size": max(sizes) if sizes else None,
        }

    # T1.5 phien 3 (2026-10-07): "global data thuan" -- ADR-03's own text
    # already says this needs no struct/typedef trick, just a direct
    # dereferencing macro (codemod.py's plain_global_wrapper_text), so
    # unlike the pointer loop above there is no has_definition exclusion
    # here: the same macro TEXT (not a typedef) at both the header's extern
    # site and the .c's real-definition site is a harmless identical-token
    # redefinition (C11 6.10.3p2), not two incompatible anonymous struct
    # types. An array whose every declaration leaves its size unstated
    # (`T name[]` everywhere, never `T name[N]`) is excluded -- a pointer-
    # to-incomplete-array cast has no settled C spelling to build the macro
    # from; found while building T1.10's build driver, see
    # docs/macos/PROGRESS.md.
    # "plain" only groups declarations by SHAPE (type_shape's return value),
    # not by exact type -- two sites can both be "plain" while one calls the
    # same address `unsigned char D_8009AF5C[]` and another
    # `OptionsLayoutPositionData D_8009AF5C` (a named struct, not even an
    # array). Picking hits[0]'s type arbitrarily would silently wrap the
    # name with whichever site happened to be scanned first, wrong for
    # every other site that disagrees. Normalizing away array-size digits,
    # const and volatile first (benign: `T[]` vs `T[12]` is the same macro
    # with the larger size picked below, same as the no-size check above)
    # isolates the real conflicts -- found while building T1.10's build
    # driver, see docs/macos/PROGRESS.md.
    def base_type(text):
        return re.sub(r"\[\d*\]", "[]", text).replace("const ", "").replace("volatile ", "").strip()

    plain_excluded_no_size = []
    plain_excluded_type_conflict = []
    plain_excluded_multi_dim = []
    for name in classified["plain"] + classified["struct-with-pointer"]:
        hits = found[name]
        if len({base_type(h["type"]) for h in hits}) > 1:
            plain_excluded_type_conflict.append(name)
            continue
        is_array = hits[0]["pointee"] is not None
        # A 2D+ array's element type is itself an array ("DuelResultSpriteSpec[7]",
        # not a plain/struct type) -- codemod.py's plain-global cast
        # (`T (*)[N]`) assumes a scalar/struct T and pastes this text in
        # unchanged, producing invalid C (`DuelResultSpriteSpec[7] (*)[2]`).
        # Caught by a real compile failure while continuing T1.10 (not
        # measured in advance) -- excluded rather than taught to build a
        # correct multi-dimension cast, only 8 names affected. See
        # docs/macos/PROGRESS.md.
        if is_array and "[" in hits[0]["pointee"]:
            plain_excluded_multi_dim.append(name)
            continue
        sizes = [h["array_size"] for h in hits if h["array_size"] is not None]
        if is_array and not sizes:
            plain_excluded_no_size.append(name)
            continue
        canonical[name] = {
            "kind": "plain",
            "address": addresses[name],
            "is_array": is_array,
            "pointee": hits[0]["pointee"] if is_array else hits[0]["type"],
            "array_size": max(sizes) if sizes else None,
        }

    print(f"guest_addresses.txt data-range candidates: {len(wanted)}")
    for shape in ("plain", "pointer", "pointer-array", "struct-with-pointer"):
        names = classified[shape]
        with_def = sum(1 for n in names if n in has_definition)
        print(f"  {shape:20s} {len(names):5d}  ({with_def} have a real definition, "
              f"{len(names) - with_def} orphan -- extern only)")
    print(f"  {'conflicting':20s} {len(classified['conflicting']):5d}  (different shape across declarations)")
    print(f"  {'no-match':20s} {len(classified['no-match']):5d}  (not found as a VAR_DECL in scanned scope)")
    print(f"  plain/struct-with-pointer wrapped: {len(canonical) - len(classified['pointer']) - len(classified['pointer-array'])}"
          f"  (excluded, no stated size: {len(plain_excluded_no_size)}; "
          f"excluded, type conflict across sites: {len(plain_excluded_type_conflict)}; "
          f"excluded, 2D+ array: {len(plain_excluded_multi_dim)})")

    os.makedirs(os.path.dirname(options.output) or ".", exist_ok=True)
    with open(options.output, "w") as handle:
        json.dump({
            "addresses": addresses,
            "classified": classified,
            "canonical": canonical,
            "conflicts": conflicts,
            "orphans": sorted(orphans),
            "declarations": found,
            "plain_excluded_no_size": sorted(plain_excluded_no_size),
            "plain_excluded_type_conflict": sorted(plain_excluded_type_conflict),
            "plain_excluded_multi_dim": sorted(plain_excluded_multi_dim),
        }, handle, indent=1)
    print(f"wrote {options.output}")


if __name__ == "__main__":
    main()
