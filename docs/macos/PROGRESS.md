# Tiến độ port macOS

> Claude cập nhật file này ở cuối **mỗi** task (`/finish-task`). Fen là người duy nhất được đổi trạng thái của các Gate.

**Task hiện tại:** T1.2
**Upstream base:** `818a0d4f6c9c12b23e13593ff319ee2474c7cb3c` (upstream/master)

## Trạng thái
Ký hiệu: `[ ]` chưa làm · `[~]` đang làm · `[x]` xong · `[!]` bị chặn · `[-]` bỏ qua (ghi lý do)

### M0 — Nền móng
- [x] T0.1 Fork, remote, branch, guard dữ liệu, diff_budget
- [x] T0.2 Toolchain và doctor
- [x] T0.3 Spike CrossOver (checklist + fen chạy thử)
- [x] T0.4 CMake portable trên arm64
- [x] T0.5 Census LP64
- [x] T0.6 Giải phẫu build upstream (chốt ADR-03)
- [x] T0.7 Prototype codemod 5 struct
- [x] **Gate G0** — GO (fen quyết định 2026-09-29)

### M1 — Title screen
- [x] T1.1 gptr.h và test
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
| 2026-09-29 | 64/546 (11.7%) | — | — | 8 (.gitignore) |

## Decision log
| Ngày | Quyết định | ADR | Lý do |
|---|---|---|---|
| 2026-09-29 | **Gate G0: GO** — tiếp tục M1 | — | Fen quyết định dựa trên T0.5 (census LP64: 64/546 unit pass, baseline) và T0.7 (prototype codemod 5 struct: layout khớp tuyệt đối, idempotent, chỉ 1/15 field (6.7%) cần override dạng `GPTR_FN`, dưới xa ngưỡng 30%). Không có tín hiệu nào cho thấy cần xét lại ADR-05 hay lộ trình 15–25 tuần. |
| 2026-09-29 | ADR-03 → Accepted, giữ hướng "global sống trong RAM guest" | ADR-03 | Cơ chế fixed-address hiện tại của build (FIXED_SECTIONS, `-fno-pie` + `--section-start`) không tái tạo được trên arm64 macOS (PIE bắt buộc, `ld64` khác cú pháp); dùng lại `G2H`/`H2G` cho cả global lẫn field tránh phải duy trì 2 cơ chế song song. Bối cảnh ADR-03 bản cũ ghi sai (nói toàn bộ biến link tại địa chỉ retail) — đã sửa. Chi tiết: `docs/macos/reports/m0-build-anatomy.md`. |
| 2026-09-29 | Thêm macro `GPTR_FN(T)` vào ADR-02/05 | ADR-02, ADR-05 | Prototype codemod T0.7 phát hiện: field khai báo qua typedef con trỏ sẵn có (callback) bị `GPTR(T)` nhân đôi dấu `*` ở nhánh không-LP64. `GPTR_FN(T)` không thêm `*`. 1/15 field trong prototype cần dạng này (6.7%, dưới ngưỡng 30% Gate G0). Chi tiết: `docs/macos/reports/m0-codemod-prototype.md`. |

## Upstream touch log
Mỗi lần sửa file dùng chung của upstream thì ghi một dòng. Danh sách này càng ngắn càng tốt.
| File | Thay đổi | Lý do | Task |
|---|---|---|---|

## Vấn đề mở / rủi ro
- Cocoa event loop khi chạy trên stack game riêng (ADR-09) — kiểm tra ở T1.8.
- `mmap(..., MAP_FIXED_NOREPLACE | MAP_ANONYMOUS, ...)` cho stack game (`state.c:1003`) không build được trên macOS (2 flag không tồn tại) — cần thay bằng `MAP_ANON` + kiểm tra thủ công thay `MAP_FIXED_NOREPLACE`. `ucontext` bên dưới đã tự test chạy tốt trên arm64, không phải blocker.
- `objcopy --weaken-symbol` (native override thắng game code) không hỗ trợ Mach-O (`llvm-objcopy` báo lỗi thẳng) — cần cơ chế khác (`__attribute__((weak))` lúc compile) ở M1.

## Nhật ký session (ngắn, mới nhất ở trên)
- 2026-09-29 — T1.1 xong. Hoàn thiện `src/pc/guest/gptr.h` + `src/pc/guest/gptr_lp64.c` (H2G, `g_ram`/`g_scratch` storage). **Bug tìm thấy:** `G2H(0)` bản T0.7 không trả về NULL (underflow unsigned che mất case này) — đã sửa. **Xác minh scratchpad:** `image.c` map 4KB (`0x1000`) trên cả Windows/POSIX nhưng scratchpad thật PS1 chỉ 1KB — giữ nguyên biên `0x400` trong `G2H`, không cần sửa gì. `tests/pc/gptr_test.c` pass cả 4 tiêu chí (G2H(0)==NULL, 3 mirror KSEG0/1/KUSEG cùng 1 byte, H2G chuẩn hoá KSEG0, con trỏ ngoài vùng abort — test bằng fork+exec). CMake: option `MEMORIES_LP64` mới (mặc định OFF), test `pc_gptr` chỉ đăng ký khi bật (đã xác minh build mặc định không có target này). Không hồi quy: 30/60 test fail với `-DMEMORIES_LP64=ON -k 0`, khớp đúng con số T0.4 (chỉ thêm 1 test mới pass). Chi tiết: `docs/macos/reports/m1-gptr.md`.
- 2026-09-29 — **Gate G0: GO.** Fen chốt tiếp tục M1 dựa trên số liệu T0.5/T0.7. Task hiện tại → T1.1.
- 2026-09-29 — T0.7 xong, M0 hoàn thành phần của Claude (còn Gate G0 chờ fen). Chọn 5 struct trong `ygo_types.h` theo tần suất dùng thật (dò bằng libclang, không phải regex tay — regex ban đầu sai vì struct lồng nhau): `DuelEffectChannel` (285 lần dùng, 6 field con trỏ), `FileTransferDescriptor` (100 lần, 3 field), `TextStreamOwner` (25 lần, 1 field mảng 22 con trỏ), `DisplayObjectStreamState` (22 lần, 3 field), `LibraryMotionState` (16 lần, 2 field) — tổng 15 field. Viết `src/pc/guest/gptr.h` (bản macro-only đúng ADR-02, cộng `GPTR_FN` mới phát hiện) và `tools/pc/lp64/codemod.py` (libclang, đọc `src/`, ghi `tmp/lp64/src/`). Kết quả: **cả 2 tiêu chí acceptance đạt** — layout 5 struct khớp tuyệt đối giữa i386 gốc và arm64+`MEMORIES_LP64` trên output codemod (dump bằng `-fdump-record-layouts-*`, cách làm theo `check_layouts.py`); codemod idempotent (chạy 2 lần byte-identical). Phát hiện cần macro `GPTR_FN(T)` cho field khai báo qua typedef con trỏ sẵn có (`FileTransferDescriptor.phase_callback`) — 1/15 field (6.7%), dưới xa ngưỡng 30% milestone đặt ra. Đã cập nhật ADR-02/05. Chi tiết đầy đủ, kể cả 3 lỗi tự vấp phải và cách sửa: `docs/macos/reports/m0-codemod-prototype.md`.
- 2026-09-29 — T0.6 xong. Đọc `build_game32.py` (832 dòng), `image.c`, `state.c`, `guest_addresses.txt`; tự test trên máy (`llvm-objcopy`, `nm -S`, `ucontext`). Phát hiện chính: ADR-03 bản cũ ghi sai — build KHÔNG link đa số biến game tại địa chỉ retail, mà dùng 2 cơ chế tách biệt: `FIXED_SECTIONS` (địa chỉ tự chọn `0x01-0x05` triệu, chỉ để save-state ổn định qua rebuild, dựa `-fno-pie`+`--section-start` — cả 2 đều không dùng được trên arm64 macOS) và `guest_symbols.ld` (pin giá trị retail thật cho symbol "mồ côi" chưa link). Đã sửa ADR-03 → Accepted, giữ hướng "global sống trong RAM guest" nhưng với lý do đúng (tránh phải duy trì 2 cơ chế fixed-address song song). Phát hiện thêm: `mmap(MAP_FIXED_NOREPLACE|MAP_ANONYMOUS)` cho stack game không build trên macOS nhưng `ucontext` bên dưới chạy tốt (đã tự test); `objcopy --weaken-symbol` không hỗ trợ Mach-O; `nm -S` luôn = 0 trên Mach-O (cần suy size từ khoảng cách địa chỉ, đã có sẵn nhánh tương tự cho Windows/PE); `readelf`/`objdump` không cần cho macOS (chỉ dùng regenerate guest_addresses.txt, ta đọc thẳng file .txt có sẵn). Chi tiết đầy đủ: `docs/macos/reports/m0-build-anatomy.md`.
- 2026-09-29 — T0.5 xong. Viết `tools/pc/lp64/census.py` (theo mẫu `host_census.py`, dùng đúng define `MEMORIES_PC/_LANGUAGE_C/LANGUAGE_C` mà `build_game32.py` dùng cho unit game/overlay thật). Syntax-check `clang --target=arm64-apple-macos -fsyntax-only -ferror-limit=0` (bỏ trần lỗi mặc định sau khi thấy 425/546 file chạm trần ở lần chạy đầu). Kết quả: **64/546 unit pass (11.7%)** — 60/514 `src/game`, 4/32 `src/overlays`. Chỉ đúng 2 loại lỗi tồn tại: struct-offset LP64 assert (27,811 lần — 94.5%, đúng vấn đề ADR-05/T0.7) và section attribute ELF-only (1,623 lần, độc lập LP64). Baseline này dùng để đối chiếu kết quả codemod ở T0.7. Chi tiết: `docs/macos/reports/m0-census.md`.
- 2026-09-28 — T0.4 xong. Configure sạch (không nhánh macOS riêng trong CMakeLists.txt, rơi vào nhánh generic). Build (`-k 0`): 195 bước, 26 compile unit fail, phần còn lại sạch. ctest: 59 test, 27 pass, 2 skip chủ động (SKIP_RETURN_CODE 77, không liên quan macOS), 30 fail — tất cả do build fail, không phải logic sai. 4 nhóm nguyên nhân: (1) LP64 struct-offset assert trong `ygo_types.h`+vệ tinh — 4 test, đúng vấn đề ADR-05/T0.7 sẽ giải; (2) section attribute kiểu ELF trong 2 header `src/game/` (mach-o cần `SEGMENT,section`) — đi kèm nhóm 1; (3) `MAP_FIXED_NOREPLACE`/`MAP_ANONYMOUS` (Linux-only) trong `src/pc/mods/{mods,object_loader}.c` — 6 test; (4) `mkdtemp` bị Darwin libc ẩn khi có `_POSIX_C_SOURCE` tường minh (khác glibc) — 20+4 test. Chi tiết đầy đủ: `docs/macos/reports/m0-cmake.md`. Không sửa code, không đụng file cấm.
- 2026-09-28 — T0.3 xong. Fen chạy CrossOver 26.3 (Apple Silicon), bottle Windows 10 64-bit tạo qua flow "Install an unlisted application", ROM test là bản mod `YGOFM Mod 2023 15x.bin` (chưa có dump đĩa gốc hợp lệ — 2 bản `.bin` khác kiểm tra hash không khớp retail SLUS-01411, xem chi tiết trong checklist). Kết quả: lên được tới màn build deck (data bài render đúng), nhưng giật lag, âm thanh rè liên tục, và **đơ cứng tái hiện 3/3 lần** khi vào menu Game > Controller (kể cả không đổi gì). Chưa kịp bắt log "taken by Windows" vì bị đơ trước. Kết luận: CrossOver dùng tạm được nhưng không đủ ổn định làm bản chơi chính; không chặn lộ trình port native. Full chi tiết: `docs/macos/reports/m0-crossover-checklist.md`.
- 2026-09-28 — T0.3 đang làm. Claude soạn `docs/macos/reports/m0-crossover-checklist.md`. Trong lúc bàn công cụ: phát hiện Whisky (gợi ý ban đầu) có hàng loạt fork GitHub đáng ngờ (mô tả giống hệt nhau, username lạ) — nghi spam/malware, khuyến nghị không cài; `wine-stable` Homebrew phổ thông không chạy được 32-bit trên Apple Silicon (memories-pc.exe là build 32-bit) — cần `gcenx/wine-crossover` (tap uy tín, wine32on64) hoặc CrossOver. Fen chọn CrossOver trả phí (dùng thử 14 ngày, ~$40–64 nếu mua) để chắc ăn nhất. Việc còn dở: fen tự chạy theo checklist, ghi kết quả vào bảng tổng kết trong file checklist rồi báo Claude để chốt T0.3 (`[x]`) và commit.
- 2026-09-28 — T0.2 xong. Viết `tools/pc/macos/doctor.py` (check Xcode CLT/clang arm64, brew llvm + `aarch64-none-elf` + libclang, cmake/ninja, python3 ≥3.11, binding `clang` python, warn MEMORIES_DISC). Lần chạy đầu phát hiện `python3` mặc định trỏ Python.framework 3.8 (x86_64, không load được libclang arm64) do 3 khối PATH-prepend trong `~/.zprofile` (3.12/3.10/3.8, khối 3.8 thêm sau cùng nên thắng — mà bản 3.12 thực ra đã bị gỡ khỏi máy). Đã comment 2 khối 3.10/3.8 trong `~/.zprofile` → `python3` rơi xuống Homebrew 3.14.6 (arm64, ≥3.11). Cài `clang==17.0.6` cho Homebrew python3 (`pip install --user --break-system-packages`, Homebrew Python là externally-managed). Thêm `export LIBCLANG_PATH=/opt/homebrew/opt/llvm/lib/libclang.dylib` vào `~/.zprofile` để `clang.cindex` load được libclang của brew llvm. Doctor chạy xanh (5 🟢, 1 🟡 MEMORIES_DISC) trong shell login mới; `diff_budget.py` vẫn pass. Lưu ý: các thay đổi PATH/pip chỉ áp dụng cho shell login mới, không áp dụng ngược cho các shell/tool đã mở từ trước.
- 2026-09-28 — T0.1 xong. Clone fork `phong-baruby/Yu-Gi-Oh-Forbidden-Memories-Recompiled`, thêm remote `upstream`, tạo `macos/main` từ `upstream/master` (818a0d4). `.gitignore` chỉ append (không sửa dòng cũ; `*.bin`/`*.cue`/`*.BIN`/`game/`/`tmp/` đã có sẵn dạng case-insensitive nên không lặp lại, chỉ thêm `*.state`, `docs/macos/reports/*.png`, và thêm `.DS_Store`/`.omc/` cho gọn máy dev). Cài kit vào `docs/macos/` + `.claude/commands/`. Viết `tools/pc/macos/diff_budget.py`, chạy pass: nhóm (a)=8 dòng (`.gitignore`), nhóm (b)=0. Push `macos/main` lên `origin` qua SSH (đổi origin từ HTTPS sang `git@github.com:...` vì không có `gh`/credential HTTPS). Việc còn dở: không có.
