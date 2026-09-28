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
  - T1.4d: `src/game/func_800[4-9]*` và phần còn lại của `src/game`
  - T1.4e: `src/pc/overrides`, `src/pc/compat` (GTE, libgs_ot) và `src/pc/render/packets.c` (packet GPU chứa địa chỉ 24-bit)
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

## Gate G1
Title screen chạy được. Cập nhật ước lượng M2–M6 trong PROGRESS.
