# M3 — Chơi được toàn bộ game và khớp golden (≈2–4 tuần)

**Mục tiêu:** mọi script trong M2 đều pass golden; chơi thủ công một mạch dài không crash.
**Scope OUT:** save state, mod.

---

### T3.1 — Codemod cho overlay
- **Làm:** phủ codemod cho `src/overlays/` và `src/pc/overlays/`: `free_duel`, `main_menu`, `overworld_before_coup`, `overworld_after_coup`, `password`, `model_modules`, `duel_effects`. Kiểm tra cách upstream load overlay (địa chỉ, và hàm nào được gọi qua bảng) để bảng hàm của ADR-04 phủ cả hàm của overlay.
- **Acceptance:** 100% unit compile LP64; census = toàn bộ.

### T3.2 — Vòng sửa lệch golden (mỗi session một script)
- **Làm:** `golden.py compare <script>`, tìm nguyên nhân, sửa ở **codemod hoặc override** (không sửa `src/`), rồi chạy lại toàn bộ các script đã pass để bắt regression.
- **Thứ tự:** `boot_title` → `new_game_name_entry` → `first_story_duel` → `free_duel_basic` → `fusion_chain` → `deck_build` → `password_shop` → `overworld_walk`.
- **Acceptance:** script pass và các script trước đó vẫn pass.

### T3.3 — Font, menu bar, HiDPI
- **Làm:** thay fontconfig bằng một TTF được bundle (chọn font có license cho phép phân phối, ghi rõ license); kiểm tra menu (F10) và logical coordinates trên màn Retina.
- **Acceptance:** menu hiển thị sắc nét, click trúng item ở mọi mức scale.

### T3.4 — Update checker
- **Làm:** trỏ checker về release của fork (hoặc tắt mặc định) và đặt tên asset macOS.
- **Acceptance:** không gọi về release Windows/Linux của upstream.

### T3.5 — Playthrough thủ công
- **Làm:** Claude soạn checklist `docs/macos/reports/m3-playthrough.md` (các mốc cốt truyện, free duel, build deck, password, memory card save); fen tự chơi và ghi lại lỗi.
- **Acceptance:** không có crash; lỗi hiển thị (nếu có) được mở issue.

## Gate G3
Toàn bộ golden pass và playthrough sạch. Đây là **bản chơi được đầu tiên**; có thể gắn tag `v<upstream>-mac.0-alpha`.
