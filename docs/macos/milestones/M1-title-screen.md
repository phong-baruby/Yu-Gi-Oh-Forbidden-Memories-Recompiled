# M1 — Build LP64 lên được title screen (≈5–8 tuần, rủi ro cao nhất)

**Mục tiêu:** `python3 tools/pc/macos/build.py run` mở cửa sổ trên M4, vào title screen và main menu, NEW GAME chạy tới name entry (đúng mức upstream đạt được lần đầu).
**Scope OUT:** save state (M4), code mod và hook (M5, tạm tắt mod loader trên LP64), HD pack (M6).
**Nguyên tắc:** làm lát cắt dọc. Chạy được sớm, sửa đúng dần nhờ golden (M2).

---

### T1.1 — `gptr.h` hoàn chỉnh và unit test
- **Làm:** hoàn thiện `src/pc/guest/gptr.h` và `src/pc/guest/gptr_lp64.c` theo ADR-02 (`G2H`, `H2G`, NULL, KSEG0/KSEG1, mirror, scratchpad). Xác minh kích thước scratchpad với `image.c`. Thêm `tests/pc/gptr_test.c` vào CMake **chỉ khi** bật option `MEMORIES_LP64`.
- **Acceptance:** test pass, bao gồm: `G2H(0)==NULL`; `0x80001000`, `0xA0001000`, `0x00001000` cùng trỏ một byte; `H2G(G2H(a))` chuẩn hoá về KSEG0; con trỏ ngoài vùng thì abort.

### T1.2 — Image guest trên macOS
- **Đọc trước:** `src/pc/guest/image.c`, `src/pc/platform/game_files.c`.
- **Làm:** `src/pc/guest/image_lp64.c` cấp phát RAM và scratchpad, rồi copy PS-X EXE (đọc từ disc bằng code sẵn có của `game_files.c`) vào đúng offset. Không cần trap hay mirror nữa.
- **Acceptance:** một test nhỏ đọc header EXE từ `MEMORIES_DISC` và kiểm tra vài word tại entry point khớp giữa file và `G2H(entry)`.

### T1.3 — Codemod giai đoạn 1: toàn bộ struct và kiểm tra layout
- **Làm:** mở rộng codemod cho mọi struct/union/typedef trong mọi header (`src/*.h`, `src/game/**/*.h`, `src/overlays/**/*.h`, `src/psyq/*.h`, header của `src/pc` nếu được đặt vào RAM guest). Viết `tools/pc/lp64/check_layouts_lp64.py` so layout i386 gốc với arm64 LP64 cho **mọi** struct (tái dùng phần parse dump của `check_layouts.py` bằng import nếu được).
- **Acceptance:** 0 khác biệt layout; các size assertion trong `ygo_types.h` pass ở LP64.

### T1.4 — Codemod giai đoạn 2: biểu thức (chia nhỏ theo batch)
- **Làm:** biến đổi (2), (3), (4), (6) của ADR-05. Mỗi session làm một batch, bám theo census:
  - T1.4a: `src/psyq` và `src/pc/sdk` (lớp SDK trước, để game build lên trên được).
  - T1.4b: `src/game/ai_*`
  - T1.4c: `src/game/func_800[0-3]*`
  - T1.4d: `src/game/func_800[4-9]*` (64 file)
  - T1.4e: `src/pc/overrides`, `src/pc/compat` (GTE, libgs_ot) và `src/pc/render/packets.c` (packet GPU chứa địa chỉ 24-bit)
  - T1.4f-j: phần còn lại của `src/game` (352 file đặt tên theo hàm, không phải `func_800...`) — tách khỏi T1.4d ngày 2026-10-01 vì gộp chung 416 file là quá lớn cho một phiên (T1.4c, 78 file, đã cần một phiên rất dài). Đo thật ngày 2026-10-02 (libclang, không đoán): 293/352 file có điểm GPTR thật, tổng 4043 điểm — gấp ~36 lần T1.4d, tách tiếp thành 5 batch con theo thứ tự alphabet tên file (~70 file/batch, ranh giới đo được lúc đó, xem `docs/macos/reports/m1-codemod-stage2f.md`): T1.4f (`build_deck_active_card.c` → `duel_card_state_helpers.c`, 71 file, 724 điểm), T1.4g (`duel_card_turn_animations.c` → `duel_trap_resolution.c`, 71 file, 1034 điểm), T1.4h (`duel_update_card_pick_cursor.c` → `model_distance_queries.c`, 71 file, 878 điểm), T1.4i (`model_effect_coefficient_table.c` → `script_op_save_prompt.c`, 71 file, 856 điểm), T1.4j (`script_op_show_dialog.c` → `widget_update_pulse_colour.c`, 68 file, 551 điểm).
  - Overlay dời sang M3.
- **Quy tắc:** chỗ nào không suy ra được thì thêm entry vào `config/lp64/overrides.toml` kèm comment lý do. Không sửa `src/`.
- **Acceptance mỗi batch:** mọi unit trong batch compile sạch ở LP64 với `-Werror=int-conversion -Werror=pointer-to-int-cast -Werror=int-to-pointer-cast`; census tăng đúng bằng số unit của batch.

### T1.5 — Global theo ADR-03
- **Làm:** hiện thực đúng hướng đã chốt ở T0.6. Sinh `tmp/lp64/gen/globals.h` và bảng init cho biến không có trong EXE.
- **Acceptance:** link LP64 không còn undefined symbol thuộc nhóm global game; test đọc một global có initializer (chọn trong `guest_addresses.txt`) cho đúng giá trị EXE.

### T1.6 — Bảng con trỏ hàm và `GCALL` (ADR-04)
- **Làm:** generator `tools/pc/lp64/gen_fn_table.py` → `tmp/lp64/gen/fn_table.c`; `GCALL`; dải địa chỉ tổng hợp `0x9F000000+` cho callback native. Với địa chỉ không tìm thấy, log địa chỉ và symbol gần nhất rồi abort.
- **Acceptance:** test tra 3 hàm retail và 1 callback native; build LP64 link được.

### T1.7 — Entry VSync và stack game trên arm64
- **Đọc trước:** `src/pc/guest/state_i386.S`, `state.h`, `state.c` (`Memories_StateRunGame`, `Memories_StateReturn`).
- **Làm:** `src/pc/guest/state_arm64.S` (symbol Mach-O có tiền tố `_`), struct entry theo AAPCS64 (ADR-08), stack game cấp phát bằng `mmap` kèm guard page. Save state thì **chưa** làm, chỉ cần VSync chạy đúng.
- **Acceptance:** game chạy qua nhiều frame mà không hỏng stack (dùng một test gọi VSync liên tục 1000 lần).

### T1.8 — Platform macOS
- **Làm:**
  - `src/pc/compat/mcontext.h`: macro lấy PC/SP/FP cho i386-linux, i386-windows và arm64-darwin. Thay các chỗ dùng `REG_EIP` trong `platform_common.c` và `crash.c` bằng macro này. Đây là thay đổi nhỏ trên file dùng chung, nhớ ghi vào touch log.
  - Chỉ dùng SDL: loại `controls_linux.c`, `gamepad_evdev.c`, `audio_alsa.c` khỏi build macOS.
  - Đường dẫn `paths.c` → Application Support (thêm nhánh `__APPLE__`).
  - Xác minh rủi ro Cocoa với stack riêng (ADR-09). Nếu có vấn đề thì dùng phương án B.
- **Acceptance:** cửa sổ mở, nhận bàn phím và gamepad, có âm thanh test.

### T1.9 — Dependencies pin
- **Làm:** `tools/pc/macos/build_deps.py` tải SDL3 3.4.16 và FreeType (đúng version upstream pin trong `tools/pc/build_linux_sysroot.py`) kèm SHA-256, build static arm64 vào `tmp/pc/macos-deps/`.
- **Acceptance:** chạy lại lần hai không build lại (cache); `otool -L` của binary cuối không có đường dẫn Homebrew.

### T1.10 — Build driver và lần chạy đầu
- **Làm:** `tools/pc/macos/build.py`: chạy codemod → compile từ `tmp/lp64/src` với `-DMEMORIES_PC -DMEMORIES_LP64` → link Mach-O arm64 kèm deps, rồi `run`. Upstream có cơ chế stub tự log tên (`MEMORIES_STUB_TRACE`), giữ nguyên cơ chế này.
- **Acceptance:** title screen, main menu, NEW GAME → name entry. Ghi video hoặc ảnh vào `docs/macos/reports/` (không commit ảnh có nội dung game, chỉ ghi mô tả).
- **Trạng thái (2026-10-08):** build.py viết xong, chưa link được — dừng lại sau khi dọn các lỗi nhỏ
  tách biệt (xem `docs/macos/reports/m1-build-driver.md`, PROGRESS.md "Vấn đề mở"). Việc lớn còn lại
  (Gap A, ~123/145 file lỗi compile) tách sang T1.11 vì không milestone nào sau (M2-M6) giải quyết được.

### T1.11 — Gap A: con trỏ host thật ép xuống integer (biến cục bộ HOẶC field nguyên trần theo chủ ý)
- **Bối cảnh:** biết từ T1.4e (2026-10-02). Phiên 1 (2026-10-08, discovery, xem
  `docs/macos/reports/m1-t1.11-discovery.md`) đo lại bằng đúng flag cảnh báo clang: "Gap A" KHÔNG phải một
  nguyên nhân — tách lại phạm vi T1.11 CHỈ còn 2 hình dạng:
  - **A1** (đa số, hình dạng gốc đã biết): con trỏ host THẬT bị ép xuống kiểu 32-bit (ngay trong một biểu
    thức, ví dụ `u8 *indices = D_800EAE88; ... *(u8*)(i + (s32)indices)` — ở đây việc ép xuống là TẠM,
    không lưu vào biến riêng, nên hướng sửa là viết lại thành số học con trỏ thuần `indices + i`, KHÔNG
    phải "đổi kiểu biến cục bộ" như ghi nhận ban đầu; nhưng cũng có thể gặp dạng biến cục bộ ĐƯỢC lưu kiểu
    hẹp qua nhiều dòng — cần đọc hết, chưa giả định trước hình dạng nào chiếm đa số) — cắt cụt nửa trên
    con trỏ 8-byte, không an toàn để chỉ bọc `(uintptr_t)`.
  - **A2** (phát hiện ở phiên 1): field khai báo kiểu nguyên trần (`s32`/`u32`, KHÔNG phải `GPTR`) giữ con
    trỏ host THEO CHỦ Ý của bản decompile, cast tay tại mọi chỗ dùng (ví dụ `menu_record.h`'s
    `s32 grid[4][3]`, có comment xác nhận "Kept as s32 ..., with the pointer casts written out at use
    sites") — field này nằm trong `src/game`, cấm sửa tay, phải đổi kiểu qua codemod/`config/lp64/`,
    không phải quét AST trong thân hàm như A1. Quy mô ngoài `grid` chưa đo (chỉ 1 ví dụ có comment).
  Các hình dạng khác đo được ở phiên 1 ĐÃ TÁCH RA khỏi T1.11 (không phải Gap A thật, không cần task
  T1.12 riêng — gộp lại các thread sẵn có):
  - A3 (giá trị nhỏ/handle an toàn ép qua `void*`, không chứng minh tĩnh được) và A4 (global pointer-array
    dùng trực tiếp làm đối số hàm) + 15/21 file nhóm `-Wint-conversion` → về lại thread **Gap B** (T1.10
    phiên 3, `fix_global_pointer_chains`/CALL_EXPR đã thử 2 lần rồi revert).
  - 6/21 file nhóm `-Wint-conversion` (ghi `GPTR_FN` qua biến cục bộ/tham số) → về lại gap **ADR-04**
    đã biết từ T1.6 (trước đo 3 file, nay ít nhất 6).
  `transform_c_expressions` (codemod.py) hiện chỉ quét field struct (`MEMBER_REF_EXPR`)/global
  (`DeclRefExpr`) đã là `gaddr`, chưa quét biến cục bộ/biểu thức mang con trỏ host THẬT (không phải
  `gaddr`) như A1, cũng chưa có cơ chế đổi kiểu field nguyên trần như A2.
- **Làm:** đọc hết (không chỉ mẫu) 108 file A1/A2 để chốt tỉ lệ các hình dạng con, RỒI MỚI thiết kế cơ
  chế AST cho từng hình dạng (mở ADR-05 mục 10) — không viết transform tổng quát trước khi đo xong, đúng
  tinh thần ADR-05.
  **Phiên 1b (2026-10-08, census đầy đủ bằng libclang, xem `docs/macos/reports/m1-t1.11-discovery.md`):**
  598 cast site / 101/108 file đo được (7 file có cast trong macro ở file khác, chưa bắt được). Phát hiện
  thêm **A5** (literal địa chỉ trần, ví dụ `(SVECTOR *)0x1F800300`, không gắn field/global nào — 89 site/
  13 file, sửa bằng regex như `fix_offsetof_casts`, RẺ và TÁCH BIỆT nhất). A1 chia 4 hình dạng con:
  INLINE (46 site/22 file, viết lại số học con trỏ thuần), STORED (122 site/28 file, đổi kiểu khai báo
  biến), STORED_ARG (33 site/18 file, lan qua chữ ký hàm — rủi ro cao hơn), UNCLEAR (33 site/16 file, đọc
  tay). A2 rộng hơn ước lượng ban đầu: 13 file (không chỉ `grid`), gồm cả field truy cập qua macro
  (`DISPLAY_OBJECT_VIEW`, `SPRITE_SHEET_HEADER`).
  **Sửa lại (2026-10-08, trước khi làm A2 thật):** "đổi kiểu field qua codemod" ở trên SAI — mọi field A2
  nằm trong struct có static-assert offset tuyệt đối (`model.h`) hoặc stride cố định dùng nhiều nơi
  (`menu_record.h`) — đổi kiểu field phá layout retail (đúng thứ `check_layouts_lp64.py` chặn). Đọc sâu
  2 field (`field_4C`, `value_08`) lộ ra cả hai polymorphic THẬT theo thiết kế decompile (cùng 4 byte,
  nhiều mục đích khác nhau tuỳ code path — word màu/con trỏ hàm, hằng số địa chỉ nhỏ/con trỏ global đã
  H2G). Hướng khả thi nhất (CHƯA xác nhận hết 13 field): bọc G2H/H2G tại TỪNG điểm đọc/viết cụ thể (như
  field GPTR bình thường), không đổi field. Hỏi fen qua `AskUserQuestion`, fen chọn **tạm dừng A2, làm A1
  trước** (A1 không bị ràng buộc layout). A5 đã làm xong (`fix_literal_address_casts`, 0 regression,
  idempotent — xem PROGRESS.md decision log). **A1-INLINE đã làm xong** (`fix_pointer_narrowing_casts`,
  allow-list 20/22 file — 2 file loại ra vì shape trùng cú pháp nhưng khác ý nghĩa, xem ADR-05 mục 10 —
  137/617 unit lỗi, giảm 8, 0 regression). **A1-STORED đã làm xong** (`fix_pointer_narrowing_locals`,
  allow-list 4 file — census lại ra 23 site/14 file "STORED" thật sau khi tách field ra khỏi biến cục bộ,
  nhưng đọc hết 14 file lộ ra 10/14 không phải A1 (global thoát-ly-kiểu MỚI phát hiện trong `src/
  unmatched.h`, GPTR_FN-qua-biến-cục-bộ đã biết từ ADR-04/T1.6, 2-tầng gaddr decode đã biết từ T1.4j,
  bitmask/tự nhân đã biết từ A1-INLINE) — 135/617 unit lỗi, giảm 2, 0 regression, idempotent, layout
  0 khác biệt. **A1-STORED_ARG đã làm xong 3/4** (`config/lp64/overrides.toml`, không cần AST pass mới
  vì mỗi hàm là 1 shape riêng): `func_80052D2C.c` arg1/arg2, `duel_shuffle_deck.c` src, `func_800320BC.c`
  arg0 — cả 3 đọc hết caller xác nhận an toàn (int nhỏ hoặc 1 cast rõ ràng duy nhất). `display_object_
  helpers.c`'s `ot` (`DisplayObject_SubmitPacket`) KHÔNG sửa: đào callers lộ ra nó được gọi qua con trỏ
  hàm lưu trong field `field_4C` — CHÍNH LÀ field polymorphic A2 đã tạm dừng — sửa `ot` riêng mà không
  giải quyết A2 trước là vá nửa vời. 131/617 unit lỗi, giảm 4, 0 regression, idempotent, layout 0 khác
  biệt. **T1.11 A1 (INLINE+STORED+STORED_ARG) coi như xong.** Phát hiện phụ (riêng, không phải A2): bug
  "missed arm" trong `collect_global_edits` khi một global có nhiều spelling chọn qua guard-define chỉ
  wrap được 1 nhánh — đã sửa `D_800101D8` (2 file), để lại `D_8009B458` (~10 file, vướng hazard
  macro-argument khác). **A2 bắt đầu thật sự: `FileTransferDescriptor.value_08`/`value_0C` xong**
  (`fix_pseudo_gptr_fields`, H2G/G2H per-site, field lớn nhất — 12 file) — 128/617 unit lỗi, giảm 3
  (`duel_load_package_stage.c`, `main_menu_load_package_stage.c`, `model_texture_transfer.c` hết lỗi hoàn
  toàn), 0 regression, idempotent, layout khớp. Còn lại cho A2: `field_4C` (polymorphic, khoá luôn `ot`
  từ A1-STORED_ARG) + 6 field nhỏ hơn → rồi UNCLEAR+macro-khác-file (đọc tay) → quyết định về global
  thoát-ly-kiểu (`D_8009B118`/`D_8009B458` còn lại, cần phiên T1.5 riêng).
- **Acceptance:** số file compile-lỗi do A1/A2/A5 giảm về 0 (hoặc có danh sách loại trừ tường minh + lý
  do cho phần còn lại), không regression ở 472 file hiện đang compile sạch. Sau đó quay lại T1.10 để link
  thật (còn cần Gap B hoàn thiện + ADR-04 mở rộng trước khi 0 data blocker).

## Gate G1
Title screen chạy được. Cập nhật ước lượng M2–M6 trong PROGRESS.
