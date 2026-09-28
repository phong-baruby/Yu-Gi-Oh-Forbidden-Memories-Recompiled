# Tiến độ port macOS

> Claude cập nhật file này ở cuối **mỗi** task (`/finish-task`). Fen là người duy nhất được đổi trạng thái của các Gate.

**Task hiện tại:** T0.4
**Upstream base:** `818a0d4f6c9c12b23e13593ff319ee2474c7cb3c` (upstream/master)

## Trạng thái
Ký hiệu: `[ ]` chưa làm · `[~]` đang làm · `[x]` xong · `[!]` bị chặn · `[-]` bỏ qua (ghi lý do)

### M0 — Nền móng
- [x] T0.1 Fork, remote, branch, guard dữ liệu, diff_budget
- [x] T0.2 Toolchain và doctor
- [x] T0.3 Spike CrossOver (checklist + fen chạy thử)
- [ ] T0.4 CMake portable trên arm64
- [ ] T0.5 Census LP64
- [ ] T0.6 Giải phẫu build upstream (chốt ADR-03)
- [ ] T0.7 Prototype codemod 5 struct
- [ ] **Gate G0** — go/no-go

### M1 — Title screen
- [ ] T1.1 gptr.h và test
- [ ] T1.2 Image guest trên macOS
- [ ] T1.3 Codemod struct và kiểm tra layout
- [ ] T1.4a SDK · [ ] T1.4b ai_* · [ ] T1.4c func_800[0-3] · [ ] T1.4d phần còn lại của src/game · [ ] T1.4e pc/overrides, compat, packets
- [ ] T1.5 Globals
- [ ] T1.6 Bảng con trỏ hàm và GCALL
- [ ] T1.7 VSync entry và stack game trên arm64
- [ ] T1.8 Platform macOS
- [ ] T1.9 Deps pin
- [ ] T1.10 Build driver, chạy lần đầu
- [ ] **Gate G1**

### M2 — Golden oracle
- [ ] T2.1 · [ ] T2.2 · [ ] T2.3 · [ ] T2.4 · [ ] T2.5 · [ ] **Gate G2**

### M3 — Full game
- [ ] T3.1 Overlay · [ ] T3.2 golden: boot_title · new_game_name_entry · first_story_duel · free_duel_basic · fusion_chain · deck_build · password_shop · overworld_walk · [ ] T3.3 · [ ] T3.4 · [ ] T3.5 · [ ] **Gate G3**

### M4 — Save state
- [ ] T4.1 · [ ] T4.2 · [ ] T4.3 · [ ] T4.4 · [ ] T4.5 · [ ] **Gate G4**

### M5 — Code mods
- [ ] T5.1 · [ ] T5.2 · [ ] T5.3 · [ ] T5.4 · [ ] T5.5 · [ ] T5.6: drop-missing-cards · ai-hard-mode · hand-camera · yamyi-mods · 3d-monsters · examples · [ ] **Gate G5**

### M6 — Release
- [ ] T6.1 · [ ] T6.2 · [ ] T6.3 · [ ] T6.4 · [ ] T6.5 · [ ] **Gate G6**

## Số liệu theo dõi
| Ngày | Census LP64 (pass/tổng) | Script golden pass | Override entries | Diff budget (dòng, file dùng chung) |
|---|---|---|---|---|
| 2026-09-28 | — | — | — | 8 (.gitignore) |

## Decision log
| Ngày | Quyết định | ADR | Lý do |
|---|---|---|---|

## Upstream touch log
Mỗi lần sửa file dùng chung của upstream thì ghi một dòng. Danh sách này càng ngắn càng tốt.
| File | Thay đổi | Lý do | Task |
|---|---|---|---|

## Vấn đề mở / rủi ro
- Cocoa event loop khi chạy trên stack game riêng (ADR-09) — kiểm tra ở T1.8.
- Hướng xử lý global (ADR-03) — chốt ở T0.6.

## Nhật ký session (ngắn, mới nhất ở trên)
- 2026-09-28 — T0.3 xong. Fen chạy CrossOver 26.3 (Apple Silicon), bottle Windows 10 64-bit tạo qua flow "Install an unlisted application", ROM test là bản mod `YGOFM Mod 2023 15x.bin` (chưa có dump đĩa gốc hợp lệ — 2 bản `.bin` khác kiểm tra hash không khớp retail SLUS-01411, xem chi tiết trong checklist). Kết quả: lên được tới màn build deck (data bài render đúng), nhưng giật lag, âm thanh rè liên tục, và **đơ cứng tái hiện 3/3 lần** khi vào menu Game > Controller (kể cả không đổi gì). Chưa kịp bắt log "taken by Windows" vì bị đơ trước. Kết luận: CrossOver dùng tạm được nhưng không đủ ổn định làm bản chơi chính; không chặn lộ trình port native. Full chi tiết: `docs/macos/reports/m0-crossover-checklist.md`.
- 2026-09-28 — T0.3 đang làm. Claude soạn `docs/macos/reports/m0-crossover-checklist.md`. Trong lúc bàn công cụ: phát hiện Whisky (gợi ý ban đầu) có hàng loạt fork GitHub đáng ngờ (mô tả giống hệt nhau, username lạ) — nghi spam/malware, khuyến nghị không cài; `wine-stable` Homebrew phổ thông không chạy được 32-bit trên Apple Silicon (memories-pc.exe là build 32-bit) — cần `gcenx/wine-crossover` (tap uy tín, wine32on64) hoặc CrossOver. Fen chọn CrossOver trả phí (dùng thử 14 ngày, ~$40–64 nếu mua) để chắc ăn nhất. Việc còn dở: fen tự chạy theo checklist, ghi kết quả vào bảng tổng kết trong file checklist rồi báo Claude để chốt T0.3 (`[x]`) và commit.
- 2026-09-28 — T0.2 xong. Viết `tools/pc/macos/doctor.py` (check Xcode CLT/clang arm64, brew llvm + `aarch64-none-elf` + libclang, cmake/ninja, python3 ≥3.11, binding `clang` python, warn MEMORIES_DISC). Lần chạy đầu phát hiện `python3` mặc định trỏ Python.framework 3.8 (x86_64, không load được libclang arm64) do 3 khối PATH-prepend trong `~/.zprofile` (3.12/3.10/3.8, khối 3.8 thêm sau cùng nên thắng — mà bản 3.12 thực ra đã bị gỡ khỏi máy). Đã comment 2 khối 3.10/3.8 trong `~/.zprofile` → `python3` rơi xuống Homebrew 3.14.6 (arm64, ≥3.11). Cài `clang==17.0.6` cho Homebrew python3 (`pip install --user --break-system-packages`, Homebrew Python là externally-managed). Thêm `export LIBCLANG_PATH=/opt/homebrew/opt/llvm/lib/libclang.dylib` vào `~/.zprofile` để `clang.cindex` load được libclang của brew llvm. Doctor chạy xanh (5 🟢, 1 🟡 MEMORIES_DISC) trong shell login mới; `diff_budget.py` vẫn pass. Lưu ý: các thay đổi PATH/pip chỉ áp dụng cho shell login mới, không áp dụng ngược cho các shell/tool đã mở từ trước.
- 2026-09-28 — T0.1 xong. Clone fork `phong-baruby/Yu-Gi-Oh-Forbidden-Memories-Recompiled`, thêm remote `upstream`, tạo `macos/main` từ `upstream/master` (818a0d4). `.gitignore` chỉ append (không sửa dòng cũ; `*.bin`/`*.cue`/`*.BIN`/`game/`/`tmp/` đã có sẵn dạng case-insensitive nên không lặp lại, chỉ thêm `*.state`, `docs/macos/reports/*.png`, và thêm `.DS_Store`/`.omc/` cho gọn máy dev). Cài kit vào `docs/macos/` + `.claude/commands/`. Viết `tools/pc/macos/diff_budget.py`, chạy pass: nhóm (a)=8 dòng (`.gitignore`), nhóm (b)=0. Push `macos/main` lên `origin` qua SSH (đổi origin từ HTTPS sang `git@github.com:...` vì không có `gh`/credential HTTPS). Việc còn dở: không có.
