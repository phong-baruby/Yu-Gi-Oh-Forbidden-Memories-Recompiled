# M5 — Hook và code mod (≈3–5 tuần)

**Mục tiêu:** hệ thống mod đầy đủ trên arm64. Toàn bộ mod đi kèm upstream (`mods/3d-monsters`, `ai-hard-mode`, `drop-missing-cards`, `hand-camera`, `yamyi-mods`) và các `examples/mods` chạy được. **3D Monsters là một code mod**, nên M6 phụ thuộc vào milestone này.

---

### T5.1 — Discovery hệ thống mod
- **Đọc trước:** `notes/modding.md`, `notes/portable-mods-plan.md`, `src/pc/mods/*` (đặc biệt `object_loader.c`, `hooks.c`, `modapi.h`, `exports.h`, `mod_libc.c`), `tools/pc/build_mod.py`, `check_mod_abi.py`, `check_mod_exports.py`, `tests/pc/hooks_test.c`, `tools/pc/test_object_loader.py`.
- **Trả lời trong `docs/macos/reports/m5-mod-anatomy.md`:** định dạng object; các loại relocation i386 đang hỗ trợ; mod truy cập struct game như thế nào; mod API đang ở version mấy; những hàm nào hook được.
- **Acceptance:** report, kèm danh sách relocation AArch64 cần hỗ trợ (xác nhận hoặc sửa ADR-07).

### T5.2 — Dispatch stub (ADR-06)
- **Làm:** codemod đổi tên định nghĩa hàm game hook được thành `__impl`; generator `tools/pc/lp64/gen_dispatch.py` sinh file `.S` chứa stub và bảng slot; `src/pc/mods/hooks_arm64.c` hiện thực đúng API mà `hooks.h` mô tả.
- **Acceptance:** `hooks_test.c` (bản LP64) pass; overhead mỗi lời gọi qua stub nằm trong mức đo được và chấp nhận được (ghi số đo vào report).

### T5.3 — Bộ cấp phát bộ nhớ JIT
- **Làm:** `src/pc/mods/jit_arm64.c` dùng `MAP_JIT`, bật/tắt write protect theo thread, `sys_icache_invalidate`.
- **Acceptance:** test ghi một hàm `ret 42` vào vùng JIT, gọi nó và nhận 42.

### T5.4 — Relocation AArch64 trong loader
- **Làm:** `src/pc/mods/object_loader_aarch64.c` hỗ trợ các relocation của ADR-07 cộng veneer island; relocation không hỗ trợ thì báo lỗi rõ.
- **Acceptance:** `test_object_loader` (bản arm64) pass với object mẫu có đủ mọi loại relocation.

### T5.5 — Mod SDK arm64
- **Làm:** `build_mod.py` có target `aarch64` (thêm tuỳ chọn, không làm hỏng target cũ); header SDK đi qua codemod; export libc khớp với `exports.h`.
- **Acceptance:** build được `examples/mods/gameplay-rules`, load thành công và thấy hiệu ứng trong game.

### T5.6 — Port mod đi kèm (mỗi session một mod)
- **Thứ tự:** `drop-missing-cards` → `ai-hard-mode` → `hand-camera` → `yamyi-mods` → `3d-monsters` → `examples/*` còn lại.
- **Acceptance mỗi mod:** load được, test hoặc smoke tương ứng pass (`test_ai_hard_mode.py`, `test_yamyi_mods.py`, ...), và golden của các script không bật mod vẫn không đổi.

## Gate G5
Toàn bộ mod đi kèm chạy được. README macOS ghi rõ: mod i386 dạng binary không tương thích, mod có source thì build lại bằng SDK arm64.
