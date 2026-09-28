# M4 — Save state và rewind (≈2–3 tuần)

**Mục tiêu:** F1–F4/F5/F7 và rewind F8 hoạt động trên macOS; state sống sót qua lần rebuild phần native, giống upstream.

---

### T4.1 — Discovery định dạng state (chốt ADR-08)
- **Đọc trước:** `src/pc/guest/state.h`, `state.c`, rewind (`rewind.h`), phần save state trong `notes/pc-build.md`.
- **Trả lời trong `docs/macos/reports/m4-state-format.md`:** chunk layout, fingerprint, cách "startup image" xử lý word bị relocate, những chỗ còn giả định địa chỉ cố định.
- **Acceptance:** ADR-08 chuyển sang Accepted hoặc được sửa.

### T4.2 — Header mở rộng
- **Làm:** thêm tag `arch`, slide và range của `__TEXT`/`__DATA` (lấy qua `_dyld_get_image_header` / `getsegbyname`), base của stack game. Load state khác arch thì từ chối kèm thông báo.
- **Acceptance:** save rồi load trong cùng một lần chạy hoạt động.

### T4.3 — Rebase stack khi load
- **Làm:** rebase theo ADR-08, bổ sung vào cơ chế remap sẵn có thay vì viết lại.
- **Acceptance:** save → thoát → chạy lại (ASLR slide khác) → load → chơi tiếp được. Tiếp theo: save → sửa một file native **không** thuộc game → rebuild → load → chơi tiếp được.

### T4.4 — Rewind
- **Acceptance:** giữ F8 tua lại 10 giây ở 60 FPS mà không tụt frame (đo bằng `MEMORIES_TRACE_FRAMES`).

### T4.5 — Golden cho save state
- **Làm:** trong script `free_duel_basic`, save ở frame N, load ngay, rồi chạy tiếp.
- **Acceptance:** chuỗi hash sau frame N khớp với lần chạy không save/load.

## Gate G4
Save state và rewind ổn định; save memory card (định dạng PS1) vẫn dùng chung được với bản Linux/Windows.
