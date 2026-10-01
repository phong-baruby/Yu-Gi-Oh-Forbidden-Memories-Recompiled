#!/usr/bin/env python3
"""Compare every struct/union's layout between the untouched i386 headers
(retail-matching) and the LP64 codemod's arm64 output (T1.3).

For each header under src/*.h, src/game/**/*.h, src/overlays/**/*.h and
src/psyq/*.h (the same set tools/pc/lp64/codemod.py transforms), parses it
twice with libclang -- i386-pc-linux-gnu against the original header,
arm64-apple-macos + MEMORIES_LP64 against the codemod's output -- and
compares (size, align, field offsets) for every struct/union it declares.

Unlike tools/pc/check_layouts.py (which shells out to
`clang -fdump-record-layouts` and parses the text dump), this computes
layout directly through libclang's own Type.get_size()/get_align() and
Cursor.get_field_offsetof(), and walks the *parsed AST* to find each
struct/union rather than reading clang's dump order. Both differences matter
here, not just in style: clang only dumps a record once something forces it
to be completed, and codemod.py's case-3 edit (an inline function-pointer
field becomes an `#ifdef MEMORIES_LP64` block, see its module docstring)
can leave a record completed on one side's branch but not the other's,
which silently shifts a dump-order or line-number based match onto the
wrong record from partway through a file. Walking the AST directly sees
every struct/union definition's source position regardless of whether
anything later forces its layout to be computed, so position within that
walk stays meaningful across the two sides.

A named struct/union is matched by tag; an anonymous one by its position
among the anonymous records *this same header's own AST walk* encounters,
which -- unlike dump order -- does not depend on what else in the file
happens to need completing."""
import argparse, glob, os, re, subprocess, sys
import clang.cindex as cindex

DEFAULT_GLOBS = ["*.h", "game/**/*.h", "overlays/**/*.h", "psyq/*.h"]
PORT_PRIVATE = os.path.join("pc", "platform") + os.sep

CLANG_ARGS = ["-std=gnu11", "-DMEMORIES_PC", "-D_LANGUAGE_C", "-DLANGUAGE_C", "-ferror-limit=0"]

TAGS = None  # struct/union tags declared anywhere in scope; set by main()


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
    try:
        return subprocess.run(["xcrun", "--show-sdk-path"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def resource_dir():
    try:
        return subprocess.run(["clang", "-print-resource-dir"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def clang_args(target, include_dir, extra_defines, prelude, gptr_header):
    # Bare libclang parsing (cindex.Index.parse()), unlike invoking the real
    # `clang` binary, does not compute a target's default header search path
    # on its own -- -resource-dir finds clang's own freestanding headers
    # (stdint.h, stddef.h, ...) regardless of target; -isysroot additionally
    # finds the macOS SDK's libc headers, needed for the arm64-apple-macos
    # side (i386-pc-linux-gnu does not have a real sysroot here, but nothing
    # in scope needs more than the freestanding set).
    #
    # gptr_header is always src/pc/guest/gptr.h (the real one), even on the
    # arm64+LP64 side: gptr.h has no pointer fields of its own, so
    # codemod.py's 4 glob patterns (src/*.h, game/**, overlays/**, psyq/*)
    # never copy it under tmp/lp64/src -- pointing -include at
    # f"{include_dir}/pc/guest/gptr.h" there is a dangling path, which
    # fails with "file not found" but does *not* reliably abort the parse:
    # clang's error recovery carries on and misreads the still-unexpanded
    # `GPTR(...)`/`GPTR_FN(...)` call on the next line as if `GPTR`/`GPTR_FN`
    # were themselves field names, silently corrupting just the structs
    # that use them, which is far more confusing than an outright failure.
    args = [f"--target={target}", *CLANG_ARGS, *extra_defines, f"-I{include_dir}",
            "-include", gptr_header]
    if prelude:
        args += ["-isystem", os.path.join(include_dir, "psyq"),
                  "-include", os.path.join(include_dir, "psyq/libgte.h"),
                  "-include", os.path.join(include_dir, "psyq/libgpu.h"),
                  "-include", os.path.join(include_dir, "psyq/libgs.h")]
    resdir = resource_dir()
    if resdir:
        args += ["-resource-dir", resdir]
    sdk = sdk_path()
    if sdk:
        args += ["-isysroot", sdk]
    return args


def parse(header, target, include_dir, extra_defines, gptr_header):
    """The header's translation unit, trying without then with the psyq
    prelude (a header that needs it fails to find its own dependencies
    without it)."""
    idx = cindex.Index.create()
    last = None
    for prelude in (False, True):
        tu = idx.parse(header, args=clang_args(target, include_dir, extra_defines, prelude, gptr_header),
                        options=cindex.TranslationUnit.PARSE_SKIP_FUNCTION_BODIES)
        # >= Error, not >= Fatal: a bad #include ("'r3000.h' file not found
        # with <angled> include", exactly the case the prelude retry exists
        # for) is Error severity, not Fatal -- clang treats it as
        # recoverable and carries on. Retrying on *any* Error, not just one
        # whose message happens to mention "not found": the symptom by the
        # time it is reported is often several steps downstream of the
        # actual missing include (libsnd.h's own text never names a missing
        # file -- the prelude-less parse just reports "unknown type name
        # 's32'" at every line that needed it), so pattern-matching the
        # message only catches some of these.
        broken = [d for d in tu.diagnostics if d.severity >= cindex.Diagnostic.Error]
        if not broken:
            return tu
        last = tu
    return last


def record_layout(cursor):
    """(size, align, [(field_name, bit_offset), ...]) for a complete
    struct/union cursor."""
    fields = [(f.spelling, f.get_field_offsetof())
              for f in cursor.get_children() if f.kind == cindex.CursorKind.FIELD_DECL]
    return cursor.type.get_size(), cursor.type.get_align(), fields


def record_key(cursor, tree_root, anon_seen):
    """("tag", name) for a named struct/union this project declares, or
    ("anon", path, n) for the n-th anonymous one (by AST position, not
    dump order -- see the module docstring) this file's walk has produced
    so far. None for a record outside what this script tracks.

    is_anonymous(), not a truthy cursor.spelling: libclang sets an
    anonymous struct's spelling to its typedef's name as a convenience
    (`typedef struct { ... } Foo;` -> spelling "Foo") when there is one,
    which looks exactly like a real `struct Foo { ... }` tag otherwise --
    almost every record in ygo_types.h is the anonymous-plus-typedef shape,
    so trusting spelling's truthiness here silently dropped nearly all of
    them (not in TAGS, since no literal "struct Foo {" text exists)."""
    if not cursor.is_anonymous():
        return ("tag", cursor.spelling) if cursor.spelling in TAGS else None
    path = os.path.relpath(os.path.normpath(str(cursor.location.file)), tree_root)
    if path.startswith("..") or path.startswith(PORT_PRIVATE):
        return None
    n = anon_seen.get(path, 0)
    anon_seen[path] = n + 1
    return ("anon", path, n)


def layouts_for(header, target, include_dir, extra_defines, filename, gptr_header):
    tu = parse(header, target, include_dir, extra_defines, gptr_header)
    if tu is None:
        return {}
    found, seen_records, anon_seen = {}, set(), {}
    for cursor in tu.cursor.walk_preorder():
        if cursor.kind not in (cindex.CursorKind.STRUCT_DECL, cindex.CursorKind.UNION_DECL):
            continue
        if not cursor.is_definition():
            continue
        if cursor.location.file is None or os.path.basename(str(cursor.location.file)) != filename:
            continue
        record = (cursor.extent.start.offset, cursor.extent.end.offset)
        if record in seen_records:
            continue  # walk_preorder can surface the same record twice; see codemod.py
        seen_records.add(record)
        key = record_key(cursor, include_dir, anon_seen)
        if key is not None:
            found[key] = record_layout(cursor)
    return found


def collect_tags(tree_root):
    tags = set()
    for path in glob.glob(os.path.join(tree_root, "**/*.h"), recursive=True):
        if os.path.normpath(path).startswith(os.path.join(tree_root, "pc", "platform")):
            continue
        with open(path, errors="replace") as handle:
            tags.update(re.findall(r"\b(?:struct|union)\s+(\w+)\s*\{", handle.read()))
    return tags


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--original", default="src", help="untouched source tree (i386 side)")
    parser.add_argument("--codemod", default="tmp/lp64/src", help="codemod output tree (arm64+LP64 side)")
    parser.add_argument("--verbose", action="store_true", help="show both layouts of every difference")
    options = parser.parse_args()
    setup_libclang()

    global TAGS
    TAGS = collect_tags(options.original) | collect_tags(options.codemod)

    headers = sorted(
        os.path.relpath(path, options.original)
        for pattern in DEFAULT_GLOBS
        for path in glob.glob(os.path.join(options.original, pattern), recursive=True)
    )

    gptr_header = os.path.join(options.original, "pc/guest/gptr.h")
    differing, compared, skipped = {}, set(), []
    for header in headers:
        filename = os.path.basename(header)
        i386 = layouts_for(os.path.join(options.original, header), "i386-pc-linux-gnu",
                           options.original, [], filename, gptr_header)
        arm64 = layouts_for(os.path.join(options.codemod, header), "arm64-apple-macos",
                            options.codemod, ["-DMEMORIES_LP64"], filename, gptr_header)
        if not i386 and not arm64:
            skipped.append(header)
            continue
        for key in set(i386) | set(arm64):
            if key in compared:
                continue
            left, right = i386.get(key), arm64.get(key)
            if left is None or right is None:
                continue  # declared in an included header, not this one; checked on its own turn
            compared.add(key)
            if left != right:
                differing[key] = (header, left, right)

    def describe(key):
        return f"struct/union {key[1]}" if key[0] == "tag" else f"the #{key[2]} anonymous record in {key[1]}"

    print(f"check_layouts_lp64: {len(headers)} header(s), {len(compared)} record(s) compared, "
          f"{len(skipped)} header(s) declare no struct/union of their own, {len(differing)} differ")
    for key, (header, left, right) in sorted(differing.items(), key=lambda kv: describe(kv[0])):
        print(f"{describe(key)} ({header}) differs between i386 and arm64+LP64")
        if options.verbose:
            l_size, l_align, l_fields = left
            r_size, r_align, r_fields = right
            print(f"  i386:       size={l_size} align={l_align} fields={l_fields}")
            print(f"  arm64+lp64: size={r_size} align={r_align} fields={r_fields}")
    if skipped and options.verbose:
        print("no struct/union found on either side: " + " ".join(skipped))
    return 1 if differing else 0


if __name__ == "__main__":
    sys.exit(main())
