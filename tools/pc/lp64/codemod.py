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

T1.4a adds a second, much narrower job: every *.c under CODE_GLOBS gets
config/lp64/overrides.toml's literal substitutions applied and is copied to
--out, so its own relative #includes (e.g. "../types.h") resolve against the
already-transformed tree rather than the original src/. T1.4a's own file
(src/psyq/startup_data.c) needed nothing past that -- see
docs/macos/reports/m1-codemod-stage2a.md for why a generic AST pass was not
worth building for its ~9-site scope.

T1.4b adds the AST pass T1.4a skipped, now that src/game/*.c -- all
forbidden to hand-edit -- needs ADR-05 (2)/(4) applied to real, repeating
code (transform_c_expressions): a gaddr-typed struct field read as a pointer
(cast to one, or dereferenced -- possibly via `*field++`, common for a byte
cursor) gets G2H; a real host pointer written into one gets H2G; a
gaddr-to-gaddr copy, or a gaddr field used as the plain integer it already
is (arithmetic, a `+=`, comparisons), needs neither and is left alone. The
field's pointee type T (for the G2H cast) cannot be read back from the
parsed type once MEMORIES_LP64 is defined -- GPTR(T) has already erased to
gaddr by then -- so it is recovered from the field's own GPTR(T)/GPTR_FN(T)
declaration text instead (field_pointee). Anything this cannot classify
confidently aborts and asks for a config/lp64/overrides.toml entry rather
than guess: wrongly adding H2G is loud (H2G aborts on a pointer outside
g_ram/g_scratch, ADR-02), but wrongly *omitting* H2G around a real pointer
is silent (the stored gaddr just reads back wrong later) -- see
docs/macos/reports/m1-codemod-stage2b.md for the full reasoning and the
three sites it would have missed if it guessed instead of refusing.
overrides.toml's substitutions now also apply to *.h, not just *.c (needed
for src/unmatched.h, a third location of the known Mach-O section-attribute
hazard already tracked in docs/macos/PROGRESS.md's "Vấn đề mở" -- same class
as src/game/display_object_helpers.h and mem_card_work.h).

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
import argparse, glob, os, re, subprocess, sys, tomllib
import clang.cindex as cindex

INLINE_FN_PTR_MARKER = b"/* lp64: inline fn ptr */"

DEFAULT_GLOBS = ["*.h", "game/**/*.h", "overlays/**/*.h", "psyq/*.h"]  # relative to --in-dir

# *.c this codemod also processes (always via config/lp64/overrides.toml;
# src/game and src/overlays additionally get transform_c_expressions, see the
# module docstring). psyq/*.c is the only directory in CLAUDE.md's
# hand-edit-forbidden list with *.c files at all -- its one file needed
# nothing past overrides.toml (T1.4a). src/pc/sdk's *.c files are NOT listed
# here: outside the forbidden list, so T1.4a fixed their handful of real
# ADR-05 (2)/(3) sites directly in source instead, #ifdef MEMORIES_LP64-
# guarded (docs/macos/reports/m1-codemod-stage2a.md). Later T1.4 batches add
# their own src/game/src/overlays patterns here.
# T1.4f: chunk 1/5 of the 352 src/game/*.c files left after T1.4a-e (ai_*,
# func_800[0-3]*, func_800[4-9]* already done; T1.4e's pc/ files needed no
# codemod entry at all -- see m1-codemod-stage2e.md). No common filename
# prefix across these (they're named after their function, not an address
# range), so listed explicitly rather than as a glob pattern -- alphabetical
# slice, boundaries measured in m1-codemod-stage2f.md. T1.4g-j (the other 4
# chunks) get their own such list when their turn comes.
T14F_FILES = [
    "game/build_deck_active_card.c",
    "game/build_deck_card_counts.c",
    "game/build_deck_deck_capacity.c",
    "game/build_deck_pane_input.c",
    "game/campaign_ensure_story_flag.c",
    "game/campaign_load_scene_package_stage.c",
    "game/campaign_load_scene_package.c",
    "game/campaign_map_load_package_stage.c",
    "game/campaign_test_story_flag.c",
    "game/card_list_render_deck_box_stats.c",
    "game/card_list_sort.c",
    "game/card_list_text_boxes.c",
    "game/card_preview_update_variant.c",
    "game/card_type_icon_table.c",
    "game/checkerboard_background.c",
    "game/color_transform.c",
    "game/credits_secret_numbers.c",
    "game/data_80091510.c",
    "game/data_8009af10.c",
    "game/data_8009af6c.c",
    "game/debug_effect_screen.c",
    "game/debug_font_format_data.c",
    "game/debug_menu_bust_up_entry.c",
    "game/debug_menu_editor_entries.c",
    "game/debug_menu_leave_entries.c",
    "game/debug_menu_two_player_entry.c",
    "game/debug_menu_update_cursor_layout.c",
    "game/debug_menu_update.c",
    "game/dialog_choice_cursor.c",
    "game/dialog_transition.c",
    "game/dialog_update_choice.c",
    "game/display_effect_lifecycle.c",
    "game/display_effect_process_menu_records.c",
    "game/display_effect_resource_setup.c",
    "game/display_effect_step_table.c",
    "game/display_effect_update_callbacks.c",
    "game/display_flat_lights.c",
    "game/display_object_alpha_transition.c",
    "game/display_object_brightness.c",
    "game/display_object_core.c",
    "game/display_object_fade_callbacks.c",
    "game/display_object_fade_helpers.c",
    "game/display_object_helpers.c",
    "game/display_object_interpolation.c",
    "game/display_object_list_renderer_table.c",
    "game/display_object_motion.c",
    "game/display_object_projection_checks.c",
    "game/display_object_property_transitions.c",
    "game/display_object_render_spotlight_mask.c",
    "game/display_object_render_sprite_sheet_list.c",
    "game/display_object_render_sprite_sheet.c",
    "game/display_object_runtime.c",
    "game/display_object_stream_read_next_command.c",
    "game/display_object_transition.c",
    "game/display_object_update_command_stream.c",
    "game/display_object_updates.c",
    "game/display_parent_links.c",
    "game/display_projection.c",
    "game/duel_action_lock.c",
    "game/duel_apply_card_object_flags.c",
    "game/duel_battle_stats.c",
    "game/duel_calc_card_stats.c",
    "game/duel_calc_guardian_star_matchup.c",
    "game/duel_card_checks.c",
    "game/duel_card_data_transfer.c",
    "game/duel_card_effects.c",
    "game/duel_card_frame_draw.c",
    "game/duel_card_object_helpers.c",
    "game/duel_card_record_lifecycle.c",
    "game/duel_card_stat_display.c",
    "game/duel_card_state_helpers.c",
]

# T1.4g: chunk 2/5, same reasoning as T14F_FILES above -- alphabetical slice
# measured in m1-codemod-stage2f.md, boundaries re-verified before this batch.
T14G_FILES = [
    "game/duel_card_turn_animations.c",
    "game/duel_card_type_icon.c",
    "game/duel_check_quit_input.c",
    "game/duel_check_ritual.c",
    "game/duel_create_card_effect_overlay.c",
    "game/duel_cursor_status.c",
    "game/duel_deck_lookup.c",
    "game/duel_draw_resolution.c",
    "game/duel_draw_status_numbers.c",
    "game/duel_effect_basic_commands.c",
    "game/duel_effect_command.c",
    "game/duel_effect_command_table.c",
    "game/duel_effect_create_channel.c",
    "game/duel_effect_dialog_state.c",
    "game/duel_effect_entry_control.c",
    "game/duel_effect_entry_occupancy.c",
    "game/duel_effect_entry_ranges.c",
    "game/duel_effect_init_entry.c",
    "game/duel_effect_init_entry_default_flags.c",
    "game/duel_effect_mark_object_if_active.c",
    "game/duel_effect_mode_7.c",
    "game/duel_effect_noop_handlers.c",
    "game/duel_effect_object_commands.c",
    "game/duel_effect_object_pool.c",
    "game/duel_effect_process_entries.c",
    "game/duel_effect_request_update.c",
    "game/duel_effect_resource_setup.c",
    "game/duel_effect_sound_commands.c",
    "game/duel_effect_state_callbacks.c",
    "game/duel_effect_tables.c",
    "game/duel_effect_update_object_layout.c",
    "game/duel_effect_update_state.c",
    "game/duel_field_card_objects.c",
    "game/duel_field_display_objects.c",
    "game/duel_field_effect_steps.c",
    "game/duel_field_equip_search.c",
    "game/duel_field_layout.c",
    "game/duel_get_base_card_stat.c",
    "game/duel_grid_offsets.c",
    "game/duel_init_model_scene.c",
    "game/duel_init_scene.c",
    "game/duel_interface_setup.c",
    "game/duel_load_package_stage.c",
    "game/duel_load_terrain_package.c",
    "game/duel_magic_effect_dispatch.c",
    "game/duel_magic_effect_format.c",
    "game/duel_monster_removal_rules.c",
    "game/duel_phase_entry.c",
    "game/duel_projection_axes.c",
    "game/duel_request_combined_deck_data.c",
    "game/duel_result_runtime.c",
    "game/duel_reward_setup.c",
    "game/duel_ritual_effect.c",
    "game/duel_scene_battle.c",
    "game/duel_scene_callbacks.c",
    "game/duel_scene_card_placement.c",
    "game/duel_scene_field_actions.c",
    "game/duel_scene_hand_actions.c",
    "game/duel_scene_turn_switch.c",
    "game/duel_scene_update.c",
    "game/duel_screen_tables.c",
    "game/duel_select_trap_play.c",
    "game/duel_selected_card_checks.c",
    "game/duel_selection_update_linked_object.c",
    "game/duel_shuffle_deck.c",
    "game/duel_side_view_angles.c",
    "game/duel_state_init.c",
    "game/duel_swords_effect.c",
    "game/duel_terrain_boost.c",
    "game/duel_transition_step_table.c",
    "game/duel_trap_resolution.c",
]

# T1.4h: chunk 3/5, same reasoning as T14F_FILES above -- alphabetical slice
# measured in m1-codemod-stage2f.md, boundaries re-verified before this batch.
T14H_FILES = [
    "game/duel_update_card_pick_cursor.c",
    "game/duel_update_draw_card_slide.c",
    "game/fade_init.c",
    "game/fade_runtime.c",
    "game/fade_step_bands.c",
    "game/file_cd_helpers.c",
    "game/file_names.c",
    "game/file_query_wrappers.c",
    "game/file_request_game_over_package.c",
    "game/file_set_position_table.c",
    "game/file_stream.c",
    "game/file_transfer_flags.c",
    "game/file_transfer_runtime.c",
    "game/file_wait_for_transfers.c",
    "game/free_duel_load_package_stage.c",
    "game/frontend_debug_constants.c",
    "game/frontend_debug_tables.c",
    "game/frontend_package_stages.c",
    "game/frontend_scene_states.c",
    "game/frontend_step_tables.c",
    "game/game_over.c",
    "game/gpu_packets.c",
    "game/graphics_frame.c",
    "game/input_is_pad1_confirm_pressed.c",
    "game/input_pad1_backup.c",
    "game/input_pads.c",
    "game/library_grid_cursor.c",
    "game/library_runtime.c",
    "game/library_update_card_used_flag.c",
    "game/main_apply_menu_selection.c",
    "game/main_boot_load_stages.c",
    "game/main_debug.c",
    "game/main_frame.c",
    "game/main_init.c",
    "game/main_init_free_duel_menu.c",
    "game/main_loop.c",
    "game/main_menu_load_package_stage.c",
    "game/main_menu_load_rect.c",
    "game/main_mode_runners.c",
    "game/main_modes.c",
    "game/main_reset_frontend_runtime.c",
    "game/main_run_animated_battle.c",
    "game/main_run_boot_sequence.c",
    "game/main_run_build_deck_menu.c",
    "game/main_run_campaign.c",
    "game/main_run_credits.c",
    "game/main_run_duel.c",
    "game/main_run_duel_and_library.c",
    "game/main_run_free_duel_menu.c",
    "game/main_run_frontend_loop.c",
    "game/main_run_frontend_menus.c",
    "game/main_run_name_entry.c",
    "game/main_run_password_menu.c",
    "game/main_run_selection_menus.c",
    "game/main_run_two_player_duel_setup.c",
    "game/main_services.c",
    "game/mdec_sync.c",
    "game/mem_card_dialog_load_save.c",
    "game/mem_card_dialog_runtime.c",
    "game/mem_card_dialog_steps.c",
    "game/mem_card_driver.c",
    "game/mem_card_io_result_callbacks.c",
    "game/menu_record_reset.c",
    "game/model_apply_texture_tint.c",
    "game/model_buffer_getters.c",
    "game/model_build_camera_relative_coordinate_unit.c",
    "game/model_control.c",
    "game/model_control_slot_animation.c",
    "game/model_debug_controller.c",
    "game/model_disc_effect.c",
    "game/model_distance_queries.c",
]

CODE_GLOBS = ["psyq/*.c", "game/ai_*.c", "game/func_800[0-3]*.c", "game/func_800[4-9]*.c"] + T14F_FILES + T14G_FILES + T14H_FILES

# src/game/*.c, forbidden to hand-edit, is the only CODE_GLOBS entry that
# additionally gets transform_c_expressions (ADR-05 (2)/(4) on real code, not
# just literal substitutions). src/psyq/*.c's one file needed nothing past
# overrides.toml (T1.4a); src/overlays/*.c will likely need this too once a
# batch reaches it.
EXPR_GLOBS = ["game/ai_*.c", "game/func_800[0-3]*.c", "game/func_800[4-9]*.c"] + T14F_FILES + T14G_FILES + T14H_FILES

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


def resource_dir():
    # Only needed for code_clang_args below: a --target=arm64-apple-macos
    # parse (unlike the header passes, which take no --target and so use
    # whatever libclang itself was built for) does not find clang's own
    # freestanding headers (stdint.h et al) without this.
    try:
        return subprocess.run(["clang", "-print-resource-dir"], capture_output=True,
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


def code_clang_args(out_dir, in_dir, prelude):
    # Unlike clang_args: --target=arm64-apple-macos (needs -resource-dir to
    # still find stdint.h et al) and -DMEMORIES_LP64 are both deliberate here
    # -- transform_c_expressions needs to see gaddr, which only exists once
    # LP64 is on, and only matters for the arm64 LP64 target this is all for.
    # -I{out_dir} first: the file being parsed already lives under out_dir
    # (transform_code_file writes it there before parsing), so its own
    # same-directory or ../-relative #includes resolve against the
    # already-transformed tree. gptr.h is always the real one (in_dir, not
    # out_dir): it has no pointer fields of its own, so CODE_GLOBS/DEFAULT_GLOBS
    # never copy it (see check_layouts_lp64.py's clang_args for the same point).
    args = ["--target=arm64-apple-macos", "-std=gnu11", "-DMEMORIES_PC", "-D_LANGUAGE_C",
            "-DLANGUAGE_C", "-DMEMORIES_LP64", "-ferror-limit=0",
            f"-I{out_dir}", "-include", os.path.join(in_dir, "pc/guest/gptr.h")]
    if prelude:
        args += ["-isystem", os.path.join(out_dir, "psyq"),
                  "-include", os.path.join(out_dir, "psyq/libgte.h"),
                  "-include", os.path.join(out_dir, "psyq/libgpu.h"),
                  "-include", os.path.join(out_dir, "psyq/libgs.h")]
    sdk = sdk_path()
    if sdk:
        args += ["-isysroot", sdk]
    resdir = resource_dir()
    if resdir:
        args += ["-resource-dir", resdir]
    return args


def parse_code(path, out_dir, in_dir):
    """Like parse(), but for transform_c_expressions: full function bodies
    (not PARSE_SKIP_FUNCTION_BODIES -- the whole point is to walk into them),
    arm64 + MEMORIES_LP64 (parse() deliberately omits both; see its own
    docstring and the module docstring for why they differ)."""
    idx = cindex.Index.create()
    last = None
    for prelude in (False, True):
        tu = idx.parse(path, args=code_clang_args(out_dir, in_dir, prelude))
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


MACH_O_SECTION_RE = re.compile(rb'__attribute__\(\(section\("([^",]*)"\)\)\)')


def fix_mach_o_sections(data):
    """`__attribute__((section("name")))` -> `__attribute__((MEMORIES_SECTION("name")))`,
    project-wide, every file this codemod writes (headers and *.c alike) --
    ADR-05, a hazard class unrelated to pointers/longs: ELF and PE accept a
    bare section name, Mach-O requires "SEGMENT,section" ("mach-o section
    specifier requires a segment and section separated by a comma"). 265
    occurrences across 58 files when this was written (T1.4b), after hand
    patching 3 of them one file at a time (T1.4a/b) made clear this needed a
    general rule, not a growing pile of config/lp64/overrides.toml entries
    for each file a later batch happens to reach -- see
    docs/macos/reports/m1-codemod-stage2b.md. MEMORIES_SECTION
    (src/pc/guest/gptr.h, always -include'd, see ADR-02) expands per-platform,
    so no #ifdef wrapping is needed at each site, unlike the three it
    replaces. [^",]* excludes an already-comma-shaped (already Mach-O) name,
    so a second pass over this function's own output has nothing left to
    match -- idempotent without needing a separate marker."""
    return MACH_O_SECTION_RE.sub(rb'__attribute__((MEMORIES_SECTION("\1")))', data)


# (TYPE)&(((T *)0)->member), (TYPE)&((T *)0)->member, (TYPE)&((T *)0)[i],
# (TYPE)&((T (*)[N])0)[i] -- a hand-rolled offsetof via null-pointer member
# or element access. The lookahead's tail (`)` then `0` then `)`) requires
# the cast-to-pointer be applied to the literal 0, which is what makes this
# safe: the resulting address is always a small in-struct/in-array offset,
# known at compile time, never a real 64-bit host address -- unlike a bare
# `(u32)&real_object` (see startup_data.c's D_800906E8 table, ADR-03/T1.5,
# deliberately NOT matched here since its base isn't 0).
OFFSETOF_CAST_RE = re.compile(
    rb'\(u32\)&(?=\([A-Za-z0-9_ ,\[\]\*\(\)]{0,120}?\)\s*0\))'
)


def fix_offsetof_casts(data):
    """(u32)&(((T *)0)->member) -> (u32)(uintptr_t)&(((T *)0)->member),
    project-wide, every file this codemod writes (headers and *.c alike) --
    a new ADR-05 case (see ARCHITECTURE.md item 9), found while measuring
    T1.4e: used throughout for layout static asserts (X_offset_must_be_...),
    the YGO_TYPE_OFFSET/MAIN_MENU_STATE_OFFSET macros, and real runtime
    pointer arithmetic (e.g. util_memory.c, model_slot_row_tables.c) --
    207 occurrences/85 files when measured, 21 of them in *.c files already
    shipped in T1.4b/c/d without this fix (re-verified clean after it).
    Routing through (uintptr_t) first (ptr -> same-width int, allowed) before
    the lossless-by-construction narrowing to u32 (plain int narrowing, not
    -Wpointer-to-int-cast) produces the exact same bits as the bare cast on
    every ABI, LP64 or not -- see docs/macos/reports/m1-codemod-stage2e.md.
    [A-Za-z0-9_ ,\\[\\]*()]{0,120}? deliberately allows nested parens/brackets
    (the T (*)[N] function/array-pointer declarator shape) in the type
    between `&` and the literal `0`, bounded so it can't run away across an
    unrelated later `)0)` possibly present elsewhere on the same line."""
    return OFFSETOF_CAST_RE.sub(rb'(u32)(uintptr_t)&', data)


def load_overrides(path):
    """config/lp64/overrides.toml's [[override]] entries, or [] if the file
    does not exist (so the tool stays usable before any override is needed)."""
    if not os.path.exists(path):
        return []
    with open(path, "rb") as handle:
        return tomllib.load(handle)["override"]


def apply_overrides(data, relpath, overrides):
    """`data` with every override whose `file` matches `relpath` applied, in
    order. By default each `old` must occur in `data` exactly once -- not
    found, or upstream having changed the surrounding text so it now matches
    more than once, both abort rather than silently applying the wrong
    instance or skipping a fix this file still needs. An override with
    `all = true` instead requires at least one occurrence and replaces every
    one -- only for a substitution that is correct regardless of which call
    site it lands on (no file-specific context baked into `new`), the same
    text repeated verbatim rather than one-off (T1.4c: addPrim(&arg->tagp->org[z], out)
    appears identically seven times across two files). Idempotent either
    way: `new` itself contains `old` verbatim (its #else branch, or -- for
    `all` -- simply because `new` no longer contains the literal `old` text
    once applied), so a second pass over already-transformed output skips a
    match already inside a `new` it produced, rather than wrapping it
    again."""
    for override in overrides:
        if override["file"] != relpath:
            continue
        old, new = override["old"].encode("utf-8"), override["new"].encode("utf-8")
        if new in data:
            continue  # already applied by an earlier pass; leave it alone
        count = data.count(old)
        if override.get("all"):
            if count < 1:
                sys.exit(f"error: override {relpath!r}/{override['pattern']!r}: "
                         f"expected at least 1 occurrence of `old`, found 0")
            data = data.replace(old, new)
        else:
            if count != 1:
                sys.exit(f"error: override {relpath!r}/{override['pattern']!r}: "
                         f"expected 1 occurrence of `old`, found {count}")
            data = data.replace(old, new)
    return data


GPTR_FIELD_RE = re.compile(r"GPTR(_FN)?\(([^)]*)\)")

TRANSPARENT_WRAPPER_KINDS = (cindex.CursorKind.PAREN_EXPR, cindex.CursorKind.UNEXPOSED_EXPR)

TRANSLATE_CALLS = ("G2H", "H2G")


def is_gaddr_type(t):
    # An array field (GPTR(T) f[N] -> gaddr f[N]) reports its own type as
    # the array (e.g. "gaddr[8]"), not "gaddr" -- check the element type
    # instead so x.f[i] (array of guest pointers, T1.4c) is still found.
    if t.kind in (cindex.TypeKind.CONSTANTARRAY, cindex.TypeKind.INCOMPLETEARRAY):
        t = t.get_array_element_type()
    return t.spelling == "gaddr" or t.get_canonical().spelling == "gaddr"


def is_pointer_like(t):
    # An array-typed expression used as an rvalue decays to a pointer (e.g.
    # `e->table = (ModelBurstPalette *)D_800916D4;` where D_800916D4 is
    # `extern u32 D_800916D4[]` -- a real host array/global, T1.4d) --
    # classify_write's "is this RHS a real pointer, needing H2G" checks need
    # to recognize this the same way a cast or a real `T *` would, not just
    # TypeKind.POINTER itself.
    return t.kind == cindex.TypeKind.POINTER or t.kind in (cindex.TypeKind.CONSTANTARRAY, cindex.TypeKind.INCOMPLETEARRAY)


def build_parent_map(cursor, parent_map, parent=None):
    """cursor.hash -> its parent cursor (or None for the TU root), for every
    cursor in the tree. libclang gives children but not parents; the
    classifiers below all need "what is this expression's role in its
    enclosing one" (assignment LHS? cast operand? deref target?), which
    needs walking upward."""
    parent_map[cursor.hash] = parent
    for child in cursor.get_children():
        build_parent_map(child, parent_map, cursor)


def skip_transparent(cursor, parent_map):
    """The nearest ancestor of `cursor` that is not a paren or an implicit
    cast libclang exposes as UNEXPOSED_EXPR -- both are invisible in the
    original text, so a classifier asking "what construct directly contains
    this" wants the first one that actually appears in source."""
    node = parent_map.get(cursor.hash)
    while node is not None and node.kind in TRANSPARENT_WRAPPER_KINDS:
        node = parent_map.get(node.hash)
    return node


def unwrap_transparent(cursor):
    """skip_transparent's downward counterpart: the innermost cursor inside
    a chain of transparent wrappers. Needed for an assignment's RHS
    specifically because the code being transformed is, by construction,
    still type-incorrect (that is the whole reason it needs transforming) --
    clang's error recovery wraps a RHS whose type does not match the LHS
    field's (gaddr) in an implicit UNEXPOSED_EXPR node that reports the
    LHS's type, not the RHS expression's own, which would make every write
    look like it is already gaddr-typed and need no edit. Unwrapping finds
    the real expression (and its real type) underneath."""
    while cursor.kind in TRANSPARENT_WRAPPER_KINDS:
        children = list(cursor.get_children())
        if len(children) != 1:
            break
        cursor = children[0]
    return cursor


def wraps_dereference(node, data):
    """True if `node` represents `*inner` for whatever its own single child
    is. A proper UNARY_OPERATOR(*) cursor only shows up when the operand's
    type actually supports dereferencing; gaddr never does, so clang's error
    recovery (this code being transformed is by construction still
    type-incorrect) instead produces a plain UNEXPOSED_EXPR of "<dependent
    type>" whose own extent is still the real `*...` source text -- checked
    here the only way left available, by its first byte."""
    if node.kind == cindex.CursorKind.UNARY_OPERATOR:
        return unary_operator(node) == "*"
    if node.kind == cindex.CursorKind.UNEXPOSED_EXPR:
        return data[node.extent.start.offset:node.extent.start.offset + 1] == b"*"
    return False


def already_translated(cursor, parent_map):
    """True if `cursor` sits directly inside a G2H(...)/H2G(...) call --
    idempotency: a second pass over this same codemod's own *.c output must
    not wrap an already-wrapped site again. There is no marker comment to
    check here (unlike the header cases): the call itself is the marker."""
    node = skip_transparent(cursor, parent_map)
    return node is not None and node.kind == cindex.CursorKind.CALL_EXPR and node.spelling in TRANSLATE_CALLS


def binop_operator(cursor):
    """The operator token of a BINARY_OPERATOR/COMPOUND_ASSIGNMENT_OPERATOR
    cursor -- libclang's Cursor has no direct accessor for this, only the
    token lying between the LHS's and RHS's extents."""
    children = list(cursor.get_children())
    if len(children) != 2:
        return None
    lhs, rhs = children
    for tok in cursor.get_tokens():
        if tok.extent.start.offset >= lhs.extent.end.offset and tok.extent.end.offset <= rhs.extent.start.offset:
            return tok.spelling
    return None


def unary_operator(cursor):
    """The operator token of a UNARY_OPERATOR cursor, prefix or postfix --
    same "libclang does not expose this directly" situation as
    binop_operator, distinguished here by whether the operand's extent
    starts where the whole expression's extent does (postfix: operand first)
    or not (prefix: operator first)."""
    children = list(cursor.get_children())
    if len(children) != 1:
        return None
    operand = children[0]
    toks = list(cursor.get_tokens())
    if not toks:
        return None
    if cursor.extent.start.offset == operand.extent.start.offset:
        return toks[-1].spelling  # postfix
    return toks[0].spelling  # prefix


def is_assign_lhs(assign_cursor, member_cursor):
    children = list(assign_cursor.get_children())
    return bool(children) and children[0].extent.start.offset == member_cursor.extent.start.offset \
        and children[0].extent.end.offset == member_cursor.extent.end.offset


def field_pointee(field_cursor, header_cache):
    """(pointee type spelling, is_gptr_fn) for a gaddr FIELD_DECL, read from
    its own GPTR(T)/GPTR_FN(T) declaration text -- the only place T still
    exists. The parsed type cannot give it back: GPTR(T) has already expanded
    to gaddr by the time MEMORIES_LP64 is defined, same as every other field
    (that erasure is the whole point of the macro). None for a field whose
    declaration is not a plain single-name GPTR(T)/GPTR_FN(T) call -- the
    inline-function-pointer #ifdef block and the shared-declarator-group
    #ifdef block (transform_bytes's case 3/the group path) do not have one;
    no field in EXPR_GLOBS's scope has needed either shape yet, so this is
    intentionally not handled -- add a config/lp64/overrides.toml entry if
    one is found."""
    path = str(field_cursor.location.file)
    if path not in header_cache:
        with open(path, "rb") as handle:
            header_cache[path] = handle.read()
    text = header_cache[path][field_cursor.extent.start.offset:field_cursor.extent.end.offset].decode("utf-8")
    m = GPTR_FIELD_RE.search(text)
    if m is None:
        return None
    return m.group(2).strip(), m.group(1) is not None


def classify_write(rhs, data, context):
    """Replacement (start, end, bytes) for the RHS of `x.f = rhs` (f gaddr),
    or None if no edit is needed. Three shapes, by rhs's own kind/type:
      - `(T *)expr` where expr is itself a pointer (a real pointer re-cast to
        a different pointer type on its way into the field) -> drop the now
        pointless cast and H2G the operand.
      - `(T *)expr` where expr is NOT a pointer (e.g. `(u8 *)(offset)` where
        `offset` is plain s32 arithmetic that was always a guest address, not
        a host one -- AiScript_Jump's family) -> the cast was only ever there
        to satisfy the old `u8 *` field type; drop it, keep expr verbatim.
        H2G must NOT run here: its argument would be a guest-address-sized
        integer wearing a pointer cast, not a real host pointer, and H2G
        aborts on exactly that (outside g_ram/g_scratch) -- the one case
        where guessing wrong is loud, not the dangerous direction, but still
        wrong code.
      - anything else with pointer type (no cast -- a bare pointer variable,
        a dereference, &something, ...) -> a real host pointer -> H2G it.
      - gaddr already, or a plain integer with no cast at all -> both valid
        as-is (gaddr IS a uint32_t), no edit.
    Anything not matching one of these (checked by the caller) aborts rather
    than guess. `context` is only for the degenerate-extent abort message
    (see transform_c_expressions's own "degenerate source extent" check,
    which this duplicates: a macro-wrapped RHS, e.g. `f = DISPLAY_OBJECT_VIEW(x)`,
    degrades the same way an LHS field read through a macro does, but this
    is the one place that check does not already run first -- found as a
    real `f = H2G();` -- RHS silently dropped entirely -- while reviewing a
    diff, T1.4c)."""
    def degenerate_or_exit(node, label):
        if node.extent.start.offset == node.extent.end.offset:
            sys.exit(f"error: {context}: RHS ({label}) has a degenerate source extent "
                     f"-- add a config/lp64/overrides.toml entry")
    if rhs.kind == cindex.CursorKind.CSTYLE_CAST_EXPR and rhs.type.kind == cindex.TypeKind.POINTER:
        # get_children() on a CSTYLE_CAST_EXPR gives the destination type's
        # own TYPE_REF first, then the operand -- the *last* child, not the
        # first, and itself possibly wrapped (unwrap_transparent) in the
        # same kind of implicit node described in unwrap_transparent's
        # docstring.
        degenerate_or_exit(rhs, "cast")
        operand = unwrap_transparent(list(rhs.get_children())[-1])
        degenerate_or_exit(operand, "cast operand")
        ostart, oend = operand.extent.start.offset, operand.extent.end.offset
        if is_pointer_like(operand.type):
            return (rhs.extent.start.offset, rhs.extent.end.offset, b"H2G(" + data[ostart:oend] + b")")
        return (rhs.extent.start.offset, rhs.extent.end.offset, data[ostart:oend])
    if is_pointer_like(rhs.type):
        degenerate_or_exit(rhs, "pointer value")
        rstart, rend = rhs.extent.start.offset, rhs.extent.end.offset
        return (rstart, rend, b"H2G(" + data[rstart:rend] + b")")
    return None  # gaddr already, or a plain integer: both fine as-is


def transform_c_expressions(data, tu, filename):
    """Edits for ADR-05 (2)/(4) in a *.c file's function bodies -- see the
    module docstring for the overall shape, classify_write's docstring for
    the write side. Every gaddr-typed MEMBER_REF_EXPR in `filename` is
    classified by its immediate (skip_transparent) parent; anything not one
    of the shapes below aborts and asks for a config/lp64/overrides.toml
    entry rather than silently leaving a type error (or worse, a wrong but
    type-correct edit) for the compiler or a human to find later."""
    parent_map = {}
    build_parent_map(tu.cursor, parent_map)
    header_cache = {}
    edits = []

    def pointee_or_exit(ref, context):
        info = field_pointee(ref, header_cache)
        if info is None:
            sys.exit(f"error: {context}: cannot recover the pointee type of "
                     f"{ref.spelling!r} (not a plain GPTR(T)/GPTR_FN(T) field) -- "
                     f"add a config/lp64/overrides.toml entry")
        return info

    for cursor in tu.cursor.walk_preorder():
        if cursor.kind != cindex.CursorKind.MEMBER_REF_EXPR:
            continue
        if cursor.location.file is None or os.path.basename(str(cursor.location.file)) != filename:
            continue
        ref = cursor.referenced
        if ref is None or not is_gaddr_type(ref.type):
            continue
        if already_translated(cursor, parent_map):
            continue

        parent = skip_transparent(cursor, parent_map)
        start, end = cursor.extent.start.offset, cursor.extent.end.offset
        context = f"{filename}:{cursor.location.line}"

        if start == end:
            # clang's error recovery sometimes cannot attribute a real file
            # span to this MEMBER_REF_EXPR at all -- `extent` collapses to a
            # zero-width point -- splicing at it would corrupt the file (an
            # empty G2H() landing next to otherwise-untouched text, observed
            # while building this, both from a gaddr field passed as a
            # function-like macro's argument, e.g. `DISPLAY_OBJECT_VIEW(x.f)`
            # expanding to `(T *)(x.f)` -- T1.4b -- and, T1.4c found, from a
            # gaddr field used in a shape clang cannot type at all even
            # without a macro, e.g. array-subscripting one directly
            # (`x.f[i]`, valid once f is a real pointer, not before). No
            # general fix for either; add a config/lp64/overrides.toml entry
            # for this exact site.
            sys.exit(f"error: {context}: {cursor.spelling!r} has a degenerate source extent "
                     f"-- add a config/lp64/overrides.toml entry")

        # *x.f (a direct dereference, no cast), checked ahead of everything
        # below that routes on skip_transparent's `parent`: skip_transparent
        # treats UNEXPOSED_EXPR as a transparent wrapper to see through, but
        # when that UNEXPOSED_EXPR is itself standing in for a broken `*...`
        # (wraps_dereference, see its docstring for why a proper
        # UNARY_OPERATOR(*) cursor never shows up here), it is NOT
        # transparent -- it is the dereference. Checking raw_parent (one hop,
        # not skip_transparent's walk) here, first, stops a later branch
        # (found: the plain-assignment-read one below, matching `val = ...`
        # one level further up, past the dereference) from quietly deciding
        # no edit is needed because that outer LHS (`val`) is not a pointer --
        # wrong: the dereference itself always needs G2H regardless of what
        # the whole expression is eventually assigned into.
        raw_parent = parent_map.get(cursor.hash)
        if raw_parent is not None and wraps_dereference(raw_parent, data):
            pointee, is_fn = pointee_or_exit(ref, context)
            cast = pointee if is_fn else f"{pointee} *"
            edits.append((start, end, f"({cast})G2H(".encode() + data[start:end] + b")"))
            continue

        # x.f->g (f itself gaddr, used as the base of a further `->` access,
        # e.g. `object->record->field_30`, T1.4c/T1.4d's "chained field"
        # overrides, generalized): checked purely textually, the character
        # right after `cursor`'s own extent (which -- a MemberExpr's extent
        # always includes its base, confirmed empirically -- spans the whole
        # `object->record`, not just `record`) rather than via any parent at
        # all. `object->record->field_30` degrades the same way a
        # dereference does (wraps_dereference's docstring) -- no stable
        # parent/raw_parent shape to route on -- but unlike a dereference,
        # the text immediately following is reliable regardless: splicing in
        # a cast+G2H right after `x.f`'s own span and leaving `->g` (and
        # anything further right) untouched composes correctly without
        # needing to know what encloses the whole chain.
        if data[end:end + 2] == b"->":
            # Extra outer parens matter here, unlike every other cast-insert
            # in this function: `->` is a postfix operator, binding tighter
            # than a C-style cast, so `(T *)G2H(x.f)->g` parses as
            # `(T *)(G2H(x.f)->g)` -- applying `->g` to G2H's `void *`
            # result first, not to the cast result -- wrong (found: this
            # exact shape, missing its outer parens, while reviewing a
            # diff). The dereference branch above does not need this: `*`
            # is also prefix, so `*(T *)G2H(...)` already associates
            # right-to-left correctly without extra grouping.
            pointee, is_fn = pointee_or_exit(ref, context)
            cast = pointee if is_fn else f"{pointee} *"
            edits.append((start, end, f"(({cast})G2H(".encode() + data[start:end] + b"))"))
            continue

        if parent is not None and parent.kind == cindex.CursorKind.BINARY_OPERATOR \
                and is_assign_lhs(parent, cursor) and binop_operator(parent) == "=":
            edit = classify_write(unwrap_transparent(list(parent.get_children())[1]), data, context)
            if edit is not None:
                edits.append(edit)
            continue

        if parent is not None and parent.kind == cindex.CursorKind.BINARY_OPERATOR \
                and binop_operator(parent) == "=" and not is_assign_lhs(parent, cursor):
            # `realPtr = x.f;`: x.f read directly as the whole RHS of a plain
            # assignment (not a declaration's initializer -- VAR_DECL's case
            # above -- and not nested inside a cast/call/deref -- those cases
            # above already matched if so, this one only fires when none of
            # them did) into a real-pointer-typed LHS. Found missing (a real
            # pointer-vs-gaddr -Wint-conversion error from the compiler, not
            # silent -- this asymmetry is why guessing wrong the other way,
            # adding H2G where not needed, is the safer default) while
            # compile-verifying a batch this case had not come up in yet.
            lhs = list(parent.get_children())[0]
            if lhs.type.kind == cindex.TypeKind.POINTER:
                edits.append((start, end, f"({lhs.type.spelling})G2H(".encode() + data[start:end] + b")"))
            continue  # LHS not a pointer either: both sides already gaddr/int, no edit

        if parent is not None and parent.kind == cindex.CursorKind.COMPOUND_ASSIGNMENT_OPERATOR \
                and is_assign_lhs(parent, cursor):
            rhs = unwrap_transparent(list(parent.get_children())[1])
            if rhs.type.kind == cindex.TypeKind.POINTER:
                sys.exit(f"error: {context}: compound assignment to {cursor.spelling!r} with a "
                         f"pointer-typed RHS -- add a config/lp64/overrides.toml entry")
            continue  # gaddr += <int>: already valid, same arithmetic either way

        if parent is not None and parent.kind == cindex.CursorKind.CSTYLE_CAST_EXPR:
            if parent.type.kind == cindex.TypeKind.POINTER:
                edits.append((start, end, b"G2H(" + data[start:end] + b")"))
            continue  # cast to a non-pointer type (e.g. (s32)x.f): already valid

        if parent is not None and parent.kind == cindex.CursorKind.VAR_DECL:
            # `T *p = x.f;`: a declaration's initializer, not a cast -- same
            # "read as a pointer" shape, the pointer type just comes from the
            # declaration instead of an explicit cast.
            if parent.type.kind == cindex.TypeKind.POINTER:
                edits.append((start, end, f"({parent.type.spelling})G2H(".encode() + data[start:end] + b")"))
            continue  # declared as a non-pointer (e.g. `u32 x = f.field;`): already valid

        if parent is not None and parent.kind == cindex.CursorKind.CALL_EXPR:
            # `fn(x.f, ...)`: x.f passed by value as some argument (never the
            # callee -- see the comment a few lines down for why a field
            # called directly never reaches here). No cast needed even
            # though a plain G2H(...) is only `void *`: that converts
            # implicitly to whatever pointer type the parameter actually is
            # (verified -- T1.4c found some of these callees have no visible
            # prototype in scope at all, where this matters even more, since
            # there is no parameter type to read back and match anyway).
            edits.append((start, end, b"G2H(" + data[start:end] + b")"))
            continue

        if parent is not None and parent.kind == cindex.CursorKind.UNARY_OPERATOR:
            op = unary_operator(parent)
            if op in ("++", "--"):
                raw_grandparent = parent_map.get(parent.hash)
                if raw_grandparent is not None and wraps_dereference(raw_grandparent, data):
                    # `*x.f++` and friends: the dereference needs G2H, but the
                    # advance does not (it is pure guest-address arithmetic,
                    # numerically identical whether applied to a real u8* or
                    # the gaddr integer directly) -- wrap the whole `x.f++`,
                    # leaving the outer `*` and the increment untouched.
                    pointee, is_fn = pointee_or_exit(ref, context)
                    cast = pointee if is_fn else f"{pointee} *"
                    pstart, pend = parent.extent.start.offset, parent.extent.end.offset
                    edits.append((pstart, pend, f"({cast})G2H(".encode() + data[pstart:pend] + b")"))
                continue  # bare x.f++/--: pure guest-address arithmetic, no edit
            continue

        if parent is not None and parent.kind == cindex.CursorKind.ARRAY_SUBSCRIPT_EXPR:
            # x.f[i] where f is itself a gaddr *array* field (an array of
            # guest pointers, e.g. GPTR(T) f[N]) -- not f being indexed by a
            # gaddr value, the array element x.f[i] as a whole being read or
            # written. Mirrors the plain-field write/VAR_DECL/plain-
            # assignment-read branches above, one level up (on `parent`, the
            # whole subscript expression, instead of `cursor`).
            pstart, pend = parent.extent.start.offset, parent.extent.end.offset
            grandparent = skip_transparent(parent, parent_map)
            if grandparent is not None and grandparent.kind == cindex.CursorKind.BINARY_OPERATOR \
                    and binop_operator(grandparent) == "=" and is_assign_lhs(grandparent, parent):
                edit = classify_write(unwrap_transparent(list(grandparent.get_children())[1]), data, context)
                if edit is not None:
                    edits.append(edit)
                continue
            if grandparent is not None and grandparent.kind == cindex.CursorKind.VAR_DECL:
                if grandparent.type.kind == cindex.TypeKind.POINTER:
                    edits.append((pstart, pend, f"({grandparent.type.spelling})G2H(".encode() + data[pstart:pend] + b")"))
                continue
            if grandparent is not None and grandparent.kind == cindex.CursorKind.BINARY_OPERATOR \
                    and binop_operator(grandparent) == "=" and not is_assign_lhs(grandparent, parent):
                lhs = list(grandparent.get_children())[0]
                if lhs.type.kind == cindex.TypeKind.POINTER:
                    edits.append((pstart, pend, f"({lhs.type.spelling})G2H(".encode() + data[pstart:pend] + b")"))
                continue
            # Anything else reading x.f[i] (a cast, a call argument, a plain
            # comparison, ...): not seen yet in this batch -- falls through
            # to the catch-all below rather than guess, same as everywhere
            # else in this function.
            continue

        # Anything else (plain integer use: arithmetic operand, comparison,
        # ...): gaddr already IS the right type here, no edit needed. This
        # includes a field called directly as a function (`x.f(args)`, ADR-05
        # (6)) -- clang's error recovery collapses that whole shape down to
        # the field's immediate parent being its enclosing statement, not a
        # CALL_EXPR, so it already falls through to here on its own; left
        # genuinely broken on purpose (fen's call, T1.4c) until GCALL exists
        # (ADR-04, T1.6) -- see docs/macos/reports/m1-codemod-stage2c.md for
        # the one site this applied to (func_80014294.c's phase_callback).

    # Two edits can nest: classify_write (and the CALL_EXPR-argument branch's
    # bare G2H wrap, when its target itself sits inside a write) build a
    # replacement by copying a sub-range of `data` verbatim, e.g. the whole
    # RHS of `x.f = (T *)fn(a, y.g)` -- if that sub-range itself contains
    # ANOTHER gaddr field (y.g above) needing its own edit, splicing both
    # independently corrupts the file: the outer edit's copy predates the
    # inner one, so the two ranges overlap on top of each other. Found as
    # exactly that -- `H2G(GsMapCoordUnit(...ev.ptr))ptr));`, mangled
    # trailing text -- composing them correctly (apply the inner edit inside
    # the outer one's own copy, recursively) is possible but not implemented
    # here; aborting is safe and the one site found so far was fixed with a
    # config/lp64/overrides.toml entry instead (T1.4d).
    ordered = sorted(edits, key=lambda e: (e[0], -e[1]))
    for i, (start, end, _) in enumerate(ordered):
        for other_start, other_end, _ in ordered[i + 1:]:
            if other_start >= end:
                break
            sys.exit(f"error: {filename}: nested edits at offsets {start}-{end} and "
                     f"{other_start}-{other_end} -- add a config/lp64/overrides.toml entry "
                     f"for the outer one (see transform_c_expressions's final comment)")

    out = data
    for start, end, replacement in sorted(edits, reverse=True):
        out = out[:start] + replacement + out[end:]
    return out, len(edits)


def transform_code_file(path, out_path, relpath, overrides, out_dir, in_dir, expr_pass):
    """A *.c file's codemod output: config/lp64/overrides.toml's literal
    substitutions, then (only for files under EXPR_GLOBS) transform_c_expressions
    on the result. Writes to out_path before the expression pass parses it
    (not the original path): that pass needs MEMORIES_LP64 and the file's own
    relative #includes resolved against the already-transformed tree, both of
    which only work from out_path's location under out_dir."""
    with open(path, "rb") as handle:
        data = handle.read()
    data = fix_mach_o_sections(data)
    data = fix_offsetof_casts(data)
    data = apply_overrides(data, relpath, overrides)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as handle:
        handle.write(data)
    if not expr_pass:
        return 0
    tu = parse_code(out_path, out_dir, in_dir)
    if tu is None:
        sys.exit(f"{out_path}: could not parse for expression codemod (even with the psyq prelude)")
    out_data, count = transform_c_expressions(data, tu, os.path.basename(path))
    with open(out_path, "wb") as handle:
        handle.write(out_data)
    return count


def transform_file(path, out_path, include_dir, relpath, overrides):
    with open(path, "rb") as handle:
        data = handle.read()
    tu = parse(path, include_dir)
    if tu is None:
        sys.exit(f"{path}: could not parse (even with the psyq prelude)")
    out_data, count = transform_bytes(data, tu, os.path.basename(path))
    out_data = fix_mach_o_sections(out_data)
    out_data = fix_offsetof_casts(out_data)
    out_data = apply_overrides(out_data, relpath, overrides)
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
        relative, code_relative, expr_relative = options.headers, [], set()
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
        expr_relative = set(
            os.path.relpath(path, options.in_dir)
            for pattern in EXPR_GLOBS
            for path in glob.glob(os.path.join(options.in_dir, pattern), recursive=True)
        )

    overrides = load_overrides(options.overrides)

    total_fields, total_files = 0, 0
    for header in relative:
        src = os.path.join(options.in_dir, header)
        dst = os.path.join(options.out, header)
        if not os.path.exists(src):
            sys.exit(f"{src}: not found")
        count = transform_file(src, dst, options.in_dir, header, overrides)
        if count:
            total_files += 1
        total_fields += count
    print(f"{len(relative)} header(s) processed, {total_fields} field(s) transformed "
          f"across {total_files} header(s)")

    if code_relative:
        total_expr = 0
        for relpath in code_relative:
            src = os.path.join(options.in_dir, relpath)
            dst = os.path.join(options.out, relpath)
            if not os.path.exists(src):
                sys.exit(f"{src}: not found")
            total_expr += transform_code_file(src, dst, relpath, overrides, options.out,
                                              options.in_dir, relpath in expr_relative)
        print(f"{len(code_relative)} *.c file(s) processed, {total_expr} expression(s) transformed")


if __name__ == "__main__":
    main()
