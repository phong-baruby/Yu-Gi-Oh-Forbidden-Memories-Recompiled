# M6 — Hoàn thiện đồ hoạ, đóng gói và CI (≈1–2 tuần)

**Mục tiêu:** một `.app` tải về là chạy được trên Apple Silicon, đầy đủ HD pack, 4x, HD text và 3D Monsters, kèm CI chạy hằng đêm.

---

### T6.1 — HD pack, 4x, HD text
- **Làm:** kiểm tra presenter OpenGL (GL 4.1 core profile trên macOS) và fallback SDL_Render (Metal); cài HD pack theo hướng dẫn của upstream; bật 4x và HD text.
- **Acceptance:** không có lỗi shader; 60 FPS ổn định ở 4x khi bật 3D Monsters trên M4 (đo bằng `MEMORIES_TRACE_FRAMES`).

### T6.2 — Bundle `.app`
- **Làm:** `tools/pc/macos/package.py` tạo `YFM Recompiled.app` với `Info.plist` (bundle id của fork, `LSMinimumSystemVersion` 14.0, `NSHighResolutionCapable`), icon riêng (không dùng artwork của Konami), `Resources/mods` chứa mod đi kèm; mod của người dùng nằm trong Application Support. Lần chạy đầu cho chọn file `.bin` (giống upstream).
- **Acceptance:** kéo app vào `/Applications`, chạy được mà không cần repo.

### T6.3 — Ký và Gatekeeper
- **Làm:** ký ad-hoc (`codesign -s -`). Nếu bật hardened runtime thì phải có entitlement `com.apple.security.cs.allow-jit` cho code mod. README hướng dẫn gỡ quarantine (`xattr -dr com.apple.quarantine`). Notarization để sau (cần Apple Developer account).
- **Acceptance:** code mod load được trong app đã ký.

### T6.4 — CI
- **Làm:**
  - Self-hosted runner trên Mac mini (label `macos-m4`), disc nằm local, được đọc qua `MEMORIES_DISC`.
  - `.github/workflows/macos-nightly.yml`: fetch upstream → rebase thử trên branch tạm → codemod → build → ctest → golden (mọi script) → báo kết quả. **Không** tự push lên `macos/main`.
  - Workflow chỉ chạy trên fork (điều kiện `github.repository`).
- **Acceptance:** chạy tay thành công một lần; có báo cáo khi fail.

### T6.5 — Release
- **Làm:** tag theo quy ước `v<upstream-version>-mac.<n>`, zip `.app`, kèm `README-macOS.md` (cài đặt, disc cần có, khác biệt về mod, license MIT kèm link về repo gốc và ghi công memories-decomp; không phân phối dữ liệu game).
- **Acceptance:** release đầu tiên trên GitHub của fork.

## Gate G6
Phát hành `mac.1`. Từ đây vào chế độ bảo trì theo `FORK-MAINTENANCE.md`.
