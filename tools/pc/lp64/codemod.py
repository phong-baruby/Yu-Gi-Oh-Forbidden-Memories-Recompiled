#!/usr/bin/env python3
"""Prototype LP64 codemod (T0.7): ADR-05 transformation (1) only -- pointer
fields in a struct/union become GPTR(T) (or GPTR_FN(T) for a field declared
through a pointer typedef, e.g. a callback typedef).

Scope for this prototype: five hand-picked structs in src/ygo_types.h,
chosen as the most-referenced pointer-bearing structs there (see
docs/macos/reports/m0-codemod-prototype.md). The real codemod (M1) will
cover every struct under src/.

Reads a header from --in-dir (default src), writes the transformed copy
under --out (default tmp/lp64/src), mirroring its relative path. Never
writes into --in-dir. Idempotent: transforming its own output again (with
gptr.h force-included, same as here) produces byte-identical text, because
macro-expanded GPTR/GPTR_FN fields parse back to the same pointer/typedef
shape they started from."""
import argparse, os, subprocess, sys
import clang.cindex as cindex

TARGET_STRUCTS = {
    "TextStreamOwner",
    "LibraryMotionState",
    "DuelEffectChannel",
    "FileTransferDescriptor",
    "DisplayObjectStreamState",
}

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


def clang_args(include_dir):
    # No -DMEMORIES_LP64: GPTR/GPTR_FN then expand to their non-LP64 form
    # (plain `T *`/`T`), which is what lets a first pass (real `T *` fields)
    # and a second pass (already-GPTR'd fields) parse to the same pointer
    # shape and produce identical replacement text -- that sameness is the
    # idempotency check.
    args = ["-std=gnu11", "-DMEMORIES_PC", "-D_LANGUAGE_C", "-DLANGUAGE_C", "-ferror-limit=0",
            f"-I{include_dir}", "-include", os.path.join(include_dir, "pc/guest/gptr.h")]
    sdk = sdk_path()
    if sdk:
        args += ["-isysroot", sdk]
    return args


def gptr_replacement(field):
    """Replacement source text for a pointer field, or None if untouched."""
    declared = field.type
    canonical = declared.get_canonical()
    is_array = canonical.kind in (cindex.TypeKind.CONSTANTARRAY, cindex.TypeKind.INCOMPLETEARRAY)
    canonical_element = canonical.get_array_element_type() if is_array else canonical
    if canonical_element.kind != cindex.TypeKind.POINTER:
        return None

    # A field declared through a pointer typedef (`FileTransferCallback cb;`)
    # spells no `*` of its own -- GPTR's non-LP64 branch (`T *`) would add an
    # extra pointer level. Detect it from the *declared* (non-canonical)
    # element type's declaration cursor: a reference to a typedef shows up as
    # TypeKind.ELABORATED, not TYPEDEF, so `.kind` alone cannot tell an
    # inline `T *`/`T *[N]` declarator from a bare typedef name -- only
    # `get_declaration()` (the cursor the type names, if any) can.
    declared_element = declared.get_array_element_type() if is_array else declared
    via_typedef = declared_element.get_declaration().kind == cindex.CursorKind.TYPEDEF_DECL

    if via_typedef:
        macro, type_arg = "GPTR_FN", declared_element.spelling
    else:
        pointee = canonical_element.get_pointee()
        macro, type_arg = "GPTR", pointee.spelling

    suffix = f"[{canonical.get_array_size()}]" if is_array else ""
    return f"{macro}({type_arg}) {field.spelling}{suffix};"


def transform_text(text, tu, filename):
    edits = []
    for cursor in tu.cursor.get_children():
        if cursor.kind not in (cindex.CursorKind.STRUCT_DECL, cindex.CursorKind.UNION_DECL):
            continue
        if cursor.spelling not in TARGET_STRUCTS or not cursor.is_definition():
            continue
        if cursor.location.file is None or os.path.basename(str(cursor.location.file)) != filename:
            continue
        for field in cursor.get_children():
            if field.kind != cindex.CursorKind.FIELD_DECL:
                continue
            replacement = gptr_replacement(field)
            if replacement is None:
                continue
            start, end = field.extent.start.offset, field.extent.end.offset
            if end < len(text) and text[end] == ";":
                end += 1  # the extent stops at the declarator, not the `;`
            edits.append((start, end, replacement))
    out = text
    for start, end, replacement in sorted(edits, reverse=True):
        out = out[:start] + replacement + out[end:]
    return out, len(edits)


def transform_file(path, out_path, include_dir):
    with open(path) as handle:
        text = handle.read()
    idx = cindex.Index.create()
    tu = idx.parse(path, args=clang_args(include_dir),
                    options=cindex.TranslationUnit.PARSE_SKIP_FUNCTION_BODIES)
    fatal = [d for d in tu.diagnostics if d.severity >= cindex.Diagnostic.Fatal]
    if fatal:
        sys.exit(f"{path}: fatal parse error(s): " + "; ".join(str(d) for d in fatal))
    out_text, count = transform_text(text, tu, os.path.basename(path))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as handle:
        handle.write(out_text)
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--in-dir", default="src", help="source tree to read from")
    parser.add_argument("--out", default="tmp/lp64/src", help="output tree to write to")
    parser.add_argument("header", nargs="?", default="ygo_types.h",
                        help="header under --in-dir to transform (default: ygo_types.h)")
    options = parser.parse_args()
    setup_libclang()
    src = os.path.join(options.in_dir, options.header)
    dst = os.path.join(options.out, options.header)
    if not os.path.exists(src):
        sys.exit(f"{src}: not found")
    count = transform_file(src, dst, options.in_dir)
    print(f"{src} -> {dst}: {count} field(s) transformed "
          f"({len(TARGET_STRUCTS)} target struct(s))")


if __name__ == "__main__":
    main()
