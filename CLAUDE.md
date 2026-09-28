# YFM Recompiled — fork macOS arm64

Fork của `Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled`. Mục tiêu: bản native macOS arm64 (dev trên Mac mini M4), đủ tính năng (HD pack, 4x, 3D monsters, code mods, save state/rewind), maintain lâu dài song song upstream.

## Đọc trước mỗi session
1. `docs/macos/PROGRESS.md`: task nào đang làm, quyết định nào đã chốt.
2. File milestone của task hiện tại trong `docs/macos/milestones/`.
3. `docs/macos/ARCHITECTURE.md` mỗi khi đụng đến memory model, globals, function pointer, save state, hooks hoặc object loader.
4. Notes gốc của upstream khi task yêu cầu (`notes/pc-build.md`, `notes/modding.md`, `notes/portable-mods-plan.md`, ...).

## Luật bất biến (sắp vi phạm thì DỪNG và hỏi)
1. **Không sửa tay** `src/game/`, `src/overlays/`, `src/psyq/`, `src/ygo_types.h`, `src/types.h`. Mọi thay đổi phục vụ LP64 đi qua codemod `tools/pc/lp64/` hoặc qua `config/lp64/overrides.toml`. Output của codemod nằm trong `tmp/lp64/` và không commit.
2. **Không phá build upstream.** Khi không có `MEMORIES_LP64`, mọi macro mới (`GPTR`, `G2H`, `GCALL`, ...) phải expand ra đúng code cũ. `make match` và build i386 Linux/Windows phải giữ nguyên kết quả.
3. **Code macOS nằm trong file mới**: `src/pc/platform/macos/`, `src/pc/guest/*_arm64.*`, `src/pc/compat/*_lp64.h`, `tools/pc/lp64/`, `tools/pc/macos/`. Nếu buộc phải chạm file dùng chung của upstream thì chỉ thêm vài dòng `#if`, và ghi vào mục "Upstream touch log" trong PROGRESS.md kèm lý do.
4. **Không bao giờ commit dữ liệu game**: `*.bin`, `*.cue`, file trích từ disc, save state, texture dump, screenshot có chứa nội dung game. Đường dẫn disc lấy từ env `MEMORIES_DISC` (upstream đã dùng biến này).
5. **Mỗi session một task (T-id).** Quy trình: `/next-task` (lập plan và chờ duyệt) → làm → `/finish-task` (chạy acceptance, review, cập nhật PROGRESS, commit). Không tự nhảy sang task kế tiếp.
6. **Plan có thể sai.** Nếu repo thực tế khác giả định trong plan (tên file, cơ chế, flag), dừng lại, mô tả khác biệt, đề xuất sửa file milestone rồi chờ duyệt. Không lặng lẽ rẽ sang hướng khác.
7. Không thêm dependency ngoài những thứ đã liệt kê trong ARCHITECTURE (ADR-10). Mọi dependency tải về đều pin version và SHA-256, theo đúng cách upstream đang làm.
8. Target là `arm64`, **không phải** `arm64e`. Không bật hardened runtime cho đến M6.

## Lệnh (cột "Có từ" cho biết task nào tạo ra lệnh đó)
| Việc | Lệnh | Có từ |
|---|---|---|
| Kiểm tra môi trường | `python3 tools/pc/macos/doctor.py` | T0.2 |
| Chạy codemod | `python3 tools/pc/lp64/codemod.py --out tmp/lp64` | T0.7 |
| Census LP64 | `python3 tools/pc/lp64/census.py` | T0.5 |
| So layout struct LP64 với i386 | `python3 tools/pc/lp64/check_layouts_lp64.py` | T1.3 |
| Build deps (SDL3, FreeType) | `python3 tools/pc/macos/build_deps.py` | T1.9 |
| Build và chạy game | `python3 tools/pc/macos/build.py [run]` | T1.10 |
| Test portable (CMake) | `cmake -S . -B tmp/pc/cmake-mac -G Ninja && cmake --build tmp/pc/cmake-mac && ctest --test-dir tmp/pc/cmake-mac` | T0.4 |
| So golden | `python3 tools/pc/macos/golden.py compare <script>` | T2.4 |
| Kiểm tra diff budget với upstream | `python3 tools/pc/macos/diff_budget.py` | T0.1 |

## Bản đồ nhanh
- Game đã decompile: `src/game/`, `src/overlays/`; SDK: `src/psyq/`; kiểu dữ liệu: `src/ygo_types.h`.
- PC port: `src/pc/` (`guest/` là memory image và save state, `platform/` là cửa sổ/input/audio, `render/`, `mods/`, `compat/`).
- Build upstream: `tools/pc/build_game32.py`; địa chỉ retail: `config/pc/guest_addresses.txt`, `config/slus_01411/functions.csv`.
- Kit macOS: `docs/macos/`, `.claude/commands/`.

## Thuật ngữ
- **guest address**: địa chỉ PS1 dạng 32-bit (`0x80xxxxxx`). **host pointer**: con trỏ 64-bit của macOS.
- `GPTR(T)`: field con trỏ trong struct game. Build LP64 lưu dưới dạng `uint32_t`, các build khác là `T *`.
- `G2H(a)` / `H2G(p)`: đổi guest address sang host pointer và ngược lại.
- **reference build**: bản i386 Linux build từ cùng commit, dùng làm oracle. **golden**: hash RAM guest theo frame.

## Quy ước commit
`macos(M1/T1.4b): <mô tả>`. Mỗi commit chỉ một concern. Không commit output của `tmp/`.
