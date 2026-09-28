# Tiến độ port macOS

> Claude cập nhật file này ở cuối **mỗi** task (`/finish-task`). Fen là người duy nhất được đổi trạng thái của các Gate.

**Task hiện tại:** T0.1
**Upstream base:** `<commit sha của upstream/master lúc rebase gần nhất>`

## Trạng thái
Ký hiệu: `[ ]` chưa làm · `[~]` đang làm · `[x]` xong · `[!]` bị chặn · `[-]` bỏ qua (ghi lý do)

### M0 — Nền móng
- [ ] T0.1 Fork, remote, branch, guard dữ liệu, diff_budget
- [ ] T0.2 Toolchain và doctor
- [ ] T0.3 Spike CrossOver (checklist + fen chạy thử)
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
