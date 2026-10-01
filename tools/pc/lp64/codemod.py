#!/usr/bin/env python3
"""LP64 codemod, stage 1 (T1.3): ADR-05 transformation (1) -- pointer fields
in every struct/union of every header under src/*.h, src/game/**/*.h,
src/overlays/**/*.h and src/psyq/*.h become GPTR(T)/GPTR_FN(T), or an inline
#ifdef MEMORIES_LP64 block for the shapes neither macro can express. Also
fixes a second, pointer-unrelated hazard the same layout check caught: a
handful of PSY-Q SDK headers declare fields as plain `long`/`unsigned long`,
which is 4 bytes on the i386 host this project matches but 8 bytes under
any native 64-bit C ABI (arm64 macOS included) -- rewritten to the project's
own fixed-width `s32`/`u32` (src/types.h), already used everywhere else.

Reads from --in-dir (default src), writes the transformed copies under --out
(default tmp/lp64/src), mirroring each file's relative path. Never writes
into --in-dir. Idempotent: transforming its own output again produces
byte-identical text (see each case below for how it stays so).

T1.4a adds a second, much narrower job: every *.c under CODE_GLOBS (today
just src/psyq/*.c -- the forbidden-to-hand-edit *.c files ADR-05 (2)/(3)/(4)/
(6) can still reach) gets config/lp64/overrides.toml's literal substitutions
applied and is copied to --out, so its own relative #includes (e.g.
"../types.h") resolve against the already-transformed tree rather than the
original src/. No AST pass runs over these -- see CODE_GLOBS's own comment
and docs/macos/reports/m1-codemod-stage2a.md for why this batch did not need
one.

Four field shapes, four strategies:
  1. Pointer/array-of-pointer declared directly (`T *f`, `T *f[N]`) -> GPTR.
     Re-parsing GPTR(T) without -DMEMORIES_LP64 expands it back to `T *`,
     which parses to the same pointer shape, so the regenerated text is the
     same again.
  2. Pointer field declared through an existing pointer typedef (data or
     function pointer, e.g. a callback typedef) -> GPTR_FN. Its non-LP64
     expansion is the bare typedef name, which is exactly the original
     spelling, so it also round-trips.
  3. A function-pointer field declared *inline*, with no typedef backing it
     (`void (*f)(int)`, or an array of these) -- neither macro's `T *`/`T`
     expansion can be prepended to a name the way a function-pointer
     declarator requires (the `*name` has to sit inside the parens). Emit a
     literal `#ifdef MEMORIES_LP64` / `#else` / `#endif` block instead,
     keeping the original declarator verbatim in the #else branch. Re-
     parsing (without -DMEMORIES_LP64) takes that #else branch, which is the
     unmodified original text -- an identical field, spotted by the leading
     `/* lp64: inline fn ptr */` marker so it is not wrapped a second time.
  4. A field declared as bare `long`/`unsigned long` (not through any
     typedef -- checked the same way as case 2 tells a typedef'd pointer
     from an inline one) -> its leading type keyword is replaced with
     `s32`/`u32`, keeping the name and any array brackets verbatim. A
     second pass sees a field already typed `s32`/`u32` -- a typedef, not a
     bare long -- so it is left alone; no marker needed.

Multiple names sharing one type specifier (`long a, b;`, `RVECTOR *r0, *r1;`)
are common in these headers and need their own handling: libclang gives
every declarator after the first an extent starting all the way back at the
shared type keyword (so field 2 of `long a, b;` has extent `long a, b`, not
just `b`), which *overlaps* field 1's extent (`long a`) instead of sitting
after it. Editing each field independently, as if extents were always
disjoint, means the two edits' byte ranges collide -- whichever is applied
second (text-splicing runs back-to-front) slices into text the first edit
already rewrote, corrupting both. Consecutive fields sharing one extent
start are therefore grouped and edited as a unit (group_replacement below),
never one declarator at a time."""
import argparse, glob, os, subprocess, sys, tomllib
import clang.cindex as cindex

INLINE_FN_PTR_MARKER = b"/* lp64: inline fn ptr */"

DEFAULT_GLOBS = ["*.h", "game/**/*.h", "overlays/**/*.h", "psyq/*.h"]  # relative to --in-dir

# T1.4a: just the one *.c under src/psyq (the only directory in the
# hand-edit-forbidden list -- CLAUDE.md -- that has one); its expression-level
# fixes can only reach it through this codemod, via config/lp64/overrides.toml
# (see apply_overrides). src/pc/sdk's *.c files are NOT listed here: they are
# outside the forbidden list, so T1.4a fixed their handful of real ADR-05
# (2)/(3) sites directly in source, #ifdef MEMORIES_LP64-guarded (see
# docs/macos/reports/m1-codemod-stage2a.md) -- a generic AST-driven .c
# expression pass was not worth building for the ~9 sites the whole batch
# had. Later T1.4 batches touching src/game/src/overlays *.c (forbidden to
# hand-edit) will likely need to extend this list and this function.
CODE_GLOBS = ["psyq/*.c"]

# Psyq headers reach one another with <angled> includes in the SDK's own
# order; one that fails alone is retried with this prelude, as
# check_layouts.py also does.


def setup_libclang():
    libclang_path = os.environ.get("LIBCLANG_PATH")
    if libclang_path:
        cindex.Config.set_library_file(libclang_path)
    try:
        cindex.Index.create()
    except cindex.LibclangError as exc:
        sys.exit(f"error: cannot load libclang ({exc}). Set LIBCLANG_PATH "
                  f"(see tools/pc/macos/doctor.py).")


def sdk_path():
    # libclang (unlike the clang driver) does not auto-detect the macOS SDK,
    # so <stdint.h> et al are otherwise not found.
    try:
        return subprocess.run(["xcrun", "--show-sdk-path"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def clang_args(include_dir, prelude):
    # No -DMEMORIES_LP64: GPTR/GPTR_FN then expand to their non-LP64 form
    # (plain `T *`/`T`), and an already-wrapped #ifdef block takes its
    # #else branch -- both let a second pass reproduce the first pass's
    # output exactly (see the module docstring).
    args = ["-std=gnu11", "-DMEMORIES_PC", "-D_LANGUAGE_C", "-DLANGUAGE_C", "-ferror-limit=0",
            f"-I{include_dir}", "-include", os.path.join(include_dir, "pc/guest/gptr.h")]
    if prelude:
        args += ["-isystem", os.path.join(include_dir, "psyq"),
                  "-include", os.path.join(include_dir, "psyq/libgte.h"),
                  "-include", os.path.join(include_dir, "psyq/libgpu.h"),
                  "-include", os.path.join(include_dir, "psyq/libgs.h")]
    sdk = sdk_path()
    if sdk:
        args += ["-isysroot", sdk]
    return args


def parse(path, include_dir):
    """The header's translation unit, trying without then with the psyq
    prelude (a header that needs it fails to find its own dependencies
    without it). None if neither works."""
    idx = cindex.Index.create()
    last = None
    for prelude in (False, True):
        tu = idx.parse(path, args=clang_args(include_dir, prelude),
                        options=cindex.TranslationUnit.PARSE_SKIP_FUNCTION_BODIES)
        # >= Error, not >= Fatal, and not pattern-matched on "not found":
        # see tools/pc/lp64/check_layouts_lp64.py's parse() for why either
        # of those misses a header like libsnd.h, which needs the prelude
        # but whose own symptom is "unknown type name 's32'" (downstream of
        # the missing include, never mentioning a filename) at Error, not
        # Fatal, severity. Retry on any Error.
        broken = [d for d in tu.diagnostics if d.severity >= cindex.Diagnostic.Error]
        if not broken:
            return tu
        last = tu
    return last


def is_function_pointer(pointee_canonical):
    return pointee_canonical.kind in (cindex.TypeKind.FUNCTIONPROTO, cindex.TypeKind.FUNCTIONNOPROTO)


def field_shape(field):
    """(is_array, canonical_element, declared_element, via_typedef) for a
    pointer/array-of-pointer field, or None if the field is not one."""
    declared = field.type
    canonical = declared.get_canonical()
    is_array = canonical.kind in (cindex.TypeKind.CONSTANTARRAY, cindex.TypeKind.INCOMPLETEARRAY)
    canonical_element = canonical.get_array_element_type() if is_array else canonical
    if canonical_element.kind != cindex.TypeKind.POINTER:
        return None
    declared_element = declared.get_array_element_type() if is_array else declared
    via_typedef = declared_element.get_declaration().kind == cindex.CursorKind.TYPEDEF_DECL
    array_size = canonical.get_array_size() if is_array else None
    return canonical_element, declared_element, via_typedef, array_size


LONG_PREFIXES = ((b"unsigned long", b"u32"), (b"long", b"s32"))

GROUP_PTR_MARKER = b"/* lp64: shared-type declarator group */"


def long_prefix_swap(original, spelling_for_errors):
    """`original` (bytes, one field or a whole shared-type group) with its
    leading `long`/`unsigned long` keyword swapped for `s32`/`u32`, keeping
    everything after it -- names, array brackets, more comma-separated
    declarators -- verbatim."""
    for prefix, replacement in LONG_PREFIXES:
        if original.startswith(prefix):
            return replacement + original[len(prefix):] + b";"
    sys.exit(f"error: {spelling_for_errors} is LONG/ULONG-kind but does not start with a "
             f"recognized spelling: {original!r}")


def single_replacement(field, data, start, end):
    """Replacement bytes for a one-name declaration (field_shape's pointer
    cases, or a bare long/unsigned long), or None if it needs no change."""
    shape = field_shape(field)
    if shape is not None:
        canonical_element, declared_element, via_typedef, array_size = shape
        suffix = f"[{array_size}]" if array_size is not None else ""

        if not via_typedef and is_function_pointer(canonical_element.get_pointee().get_canonical()):
            # Exact byte-for-byte prefix this same field's wrapper would
            # have left immediately before it -- not just "the marker is
            # somewhere nearby", which a dense run of function-pointer
            # fields (fs.h's device_table, libgs.h's _GsFCALL) could
            # false-positive on by picking up a *different* field's marker.
            prefix = (f"{INLINE_FN_PTR_MARKER.decode()}\n"
                      f"#ifdef MEMORIES_LP64\n"
                      f"    gaddr {field.spelling}{suffix};\n"
                      f"#else\n"
                      f"    ").encode("utf-8")
            if data[max(0, start - len(prefix)):start] == prefix:
                return None  # already wrapped by an earlier pass; leave it alone
            original = data[start:end].decode("utf-8")
            return (f"{INLINE_FN_PTR_MARKER.decode()}\n"
                    f"#ifdef MEMORIES_LP64\n"
                    f"    gaddr {field.spelling}{suffix};\n"
                    f"#else\n"
                    f"    {original};\n"
                    f"#endif").encode("utf-8")

        if via_typedef:
            return f"GPTR_FN({declared_element.spelling}) {field.spelling}{suffix};".encode("utf-8")

        pointee = canonical_element.get_pointee()
        return f"GPTR({pointee.spelling}) {field.spelling}{suffix};".encode("utf-8")

    is_array = field.type.kind in (cindex.TypeKind.CONSTANTARRAY, cindex.TypeKind.INCOMPLETEARRAY)
    base_kind = field.type.get_array_element_type().kind if is_array else field.type.kind
    if base_kind not in (cindex.TypeKind.LONG, cindex.TypeKind.ULONG):
        return None
    return long_prefix_swap(data[start:end], field.spelling)


def group_replacement(members, data, start, end):
    """Replacement bytes for `long a, b;` / `RVECTOR *r0, *r1;` -- several
    names sharing one type specifier (see the module docstring for why this
    cannot be edited one declarator at a time) -- or None if the group
    needs no change. All members share one base type by C grammar, so
    whichever field_shape()/LONG check the first member satisfies, they all
    do; this does not re-decide per member, only reads each one's own
    name/array-size for the replacement text."""
    shapes = [field_shape(f) for f in members]
    if all(s is None for s in shapes):
        is_array = members[0].type.kind in (cindex.TypeKind.CONSTANTARRAY, cindex.TypeKind.INCOMPLETEARRAY)
        base_kind = members[0].type.get_array_element_type().kind if is_array else members[0].type.kind
        if base_kind not in (cindex.TypeKind.LONG, cindex.TypeKind.ULONG):
            return None
        return long_prefix_swap(data[start:end], members[0].spelling)

    if any(s is None for s in shapes):
        sys.exit(f"error: shared-type group at {members[0].spelling} mixes pointer and "
                 f"non-pointer declarators, which this codemod does not handle: "
                 f"{[m.spelling for m in members]}")

    def decl_text(field, shape):
        array_size = shape[3]
        return f"{field.spelling}[{array_size}]" if array_size is not None else field.spelling

    names = ", ".join(decl_text(f, s) for f, s in zip(members, shapes))

    # GPTR_FN alone is safe to emit once for the whole group: its non-LP64
    # expansion is a bare type name with no `*` of its own, so `T a, b;`
    # (the result) still types every name correctly. GPTR's `T *` is not --
    # expanding once only adds that `*` at the type position, leaving every
    # name after the first as plain T instead of T* -- so a group with any
    # non-typedef member (plain pointer or inline function pointer) always
    # goes through the verbatim #ifdef form instead, covering every member
    # in one block rather than trying to add a `*` per name.
    if all(via_typedef for _, _, via_typedef, _ in shapes):
        declared_element = shapes[0][1]
        return f"GPTR_FN({declared_element.spelling}) {names};".encode("utf-8")

    prefix = (f"{GROUP_PTR_MARKER.decode()}\n"
              f"#ifdef MEMORIES_LP64\n"
              f"    gaddr {names};\n"
              f"#else\n"
              f"    ").encode("utf-8")
    if data[max(0, start - len(prefix)):start] == prefix:
        return None  # already wrapped by an earlier pass; leave it alone
    original = data[start:end].decode("utf-8")
    return (f"{GROUP_PTR_MARKER.decode()}\n"
            f"#ifdef MEMORIES_LP64\n"
            f"    gaddr {names};\n"
            f"#else\n"
            f"    {original};\n"
            f"#endif").encode("utf-8")


def transform_bytes(data, tu, filename):
    edits = []
    seen_records = set()
    # walk_preorder, not get_children(): a struct/union nested inside another
    # one's body (common for an anonymous sub-struct field, e.g. mcgui.h's
    # `struct { ... } bgm;`) is not a top-level cursor, and get_children()
    # alone silently skipped every field inside one. walk_preorder can also
    # surface the exact same record cursor more than once (observed for an
    # anonymous struct immediately typedef'd, e.g. libgs.h's
    # `typedef struct { ... } _GsFCALL;`) -- `seen_records` processes each
    # one's fields only once regardless.
    for cursor in tu.cursor.walk_preorder():
        if cursor.kind not in (cindex.CursorKind.STRUCT_DECL, cindex.CursorKind.UNION_DECL):
            continue
        if not cursor.is_definition():
            continue
        if cursor.location.file is None or os.path.basename(str(cursor.location.file)) != filename:
            continue
        record_key = (cursor.extent.start.offset, cursor.extent.end.offset)
        if record_key in seen_records:
            continue
        seen_records.add(record_key)

        # Group consecutive fields that share one type specifier (`long a,
        # b;`): libclang gives every declarator after the first an extent
        # starting at the *shared* type keyword, not at its own name (see
        # the module docstring), so a shared start groups them correctly.
        groups, fields = [], [f for f in cursor.get_children() if f.kind == cindex.CursorKind.FIELD_DECL]
        for field in fields:
            start = field.extent.start.offset
            if groups and groups[-1][0] == start:
                groups[-1][1].append(field)
            else:
                groups.append((start, [field]))

        for group_start, members in groups:
            end = members[-1].extent.end.offset
            replacement = (single_replacement(members[0], data, group_start, end) if len(members) == 1
                          else group_replacement(members, data, group_start, end))
            if replacement is None:
                continue
            if end < len(data) and data[end:end + 1] == b";":
                end += 1  # the extent stops at the declarator, not the `;`
            edits.append((group_start, end, replacement))
    out = data
    for start, end, replacement in sorted(edits, reverse=True):
        out = out[:start] + replacement + out[end:]
    return out, len(edits)


def load_overrides(path):
    """config/lp64/overrides.toml's [[override]] entries, or [] if the file
    does not exist (so the tool stays usable before any override is needed)."""
    if not os.path.exists(path):
        return []
    with open(path, "rb") as handle:
        return tomllib.load(handle)["override"]


def apply_overrides(data, relpath, overrides):
    """`data` with every override whose `file` matches `relpath` applied, in
    order. Each `old` must occur in `data` exactly once -- not found, or
    upstream having changed the surrounding text so it now matches more than
    once, both abort rather than silently applying the wrong instance or
    skipping a fix this file still needs. Idempotent: `new` itself contains
    `old` verbatim (its #else branch), so a second pass over already-
    transformed output skips a match already inside a `new` it produced,
    rather than wrapping it again."""
    for override in overrides:
        if override["file"] != relpath:
            continue
        old, new = override["old"].encode("utf-8"), override["new"].encode("utf-8")
        if new in data:
            continue  # already applied by an earlier pass; leave it alone
        count = data.count(old)
        if count != 1:
            sys.exit(f"error: override {relpath!r}/{override['pattern']!r}: "
                     f"expected 1 occurrence of `old`, found {count}")
        data = data.replace(old, new)
    return data


def transform_code_file(path, out_path, relpath, overrides):
    """A *.c file's codemod output: config/lp64/overrides.toml's literal
    substitutions only (see CODE_GLOBS's comment for why this batch needs
    nothing more -- no struct/union defined in scope needs ADR-05 (1)/(8),
    and no GPTR-typed expression needing (2)/(3)/(4)/(6) was found in it)."""
    with open(path, "rb") as handle:
        data = handle.read()
    data = apply_overrides(data, relpath, overrides)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as handle:
        handle.write(data)


def transform_file(path, out_path, include_dir):
    with open(path, "rb") as handle:
        data = handle.read()
    tu = parse(path, include_dir)
    if tu is None:
        sys.exit(f"{path}: could not parse (even with the psyq prelude)")
    out_data, count = transform_bytes(data, tu, os.path.basename(path))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as handle:
        handle.write(out_data)
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--in-dir", default="src", help="source tree to read from")
    parser.add_argument("--out", default="tmp/lp64/src", help="output tree to write to")
    parser.add_argument("--overrides", default="config/lp64/overrides.toml",
                        help="ADR-05 override file (literal substitutions for *.c, see CODE_GLOBS)")
    parser.add_argument("headers", nargs="*",
                        help="headers under --in-dir to transform (default: every header "
                             "under src/*.h, src/game, src/overlays, src/psyq, plus every "
                             "*.c under CODE_GLOBS)")
    options = parser.parse_args()
    setup_libclang()

    if options.headers:
        relative, code_relative = options.headers, []
    else:
        relative = sorted(
            os.path.relpath(path, options.in_dir)
            for pattern in DEFAULT_GLOBS
            for path in glob.glob(os.path.join(options.in_dir, pattern), recursive=True)
        )
        code_relative = sorted(
            os.path.relpath(path, options.in_dir)
            for pattern in CODE_GLOBS
            for path in glob.glob(os.path.join(options.in_dir, pattern), recursive=True)
        )

    total_fields, total_files = 0, 0
    for header in relative:
        src = os.path.join(options.in_dir, header)
        dst = os.path.join(options.out, header)
        if not os.path.exists(src):
            sys.exit(f"{src}: not found")
        count = transform_file(src, dst, options.in_dir)
        if count:
            total_files += 1
        total_fields += count
    print(f"{len(relative)} header(s) processed, {total_fields} field(s) transformed "
          f"across {total_files} header(s)")

    if code_relative:
        overrides = load_overrides(options.overrides)
        for relpath in code_relative:
            src = os.path.join(options.in_dir, relpath)
            dst = os.path.join(options.out, relpath)
            if not os.path.exists(src):
                sys.exit(f"{src}: not found")
            transform_code_file(src, dst, relpath, overrides)
        print(f"{len(code_relative)} *.c file(s) processed (overrides only)")


if __name__ == "__main__":
    main()
