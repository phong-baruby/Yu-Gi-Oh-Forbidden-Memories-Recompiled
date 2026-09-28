---
description: Đồng bộ fork với upstream theo FORK-MAINTENANCE.md
---
Làm theo `docs/macos/FORK-MAINTENANCE.md`, mục "Quy trình sync":
1. `git fetch upstream`. Tóm tắt các commit mới kể từ `Upstream base` trong PROGRESS, và **đánh dấu** các commit chạm tới vùng nhạy cảm (`src/pc/guest/`, `src/pc/mods/`, `tools/pc/build_game32.py`, header struct, `notes/pc-build.md`). Nếu thấy dấu hiệu upstream bắt đầu làm 64-bit, báo ngay cho fen.
2. Tạo `macos/sync-<YYYYMMDD>` từ `macos/main` rồi rebase lên `upstream/master`. Gặp conflict thì dừng lại, trình bày từng conflict kèm đề xuất cách giải, và chờ fen duyệt.
3. Chạy lần lượt: codemod → `check_layouts_lp64.py` → build → ctest → golden (toàn bộ script đã pass trước đó).
4. Báo cáo: pass/fail, những pattern mới mà codemod cần học, override mới đề xuất, golden cần tạo lại.
5. **Không** tự fast-forward `macos/main`. Chờ fen xác nhận, sau đó cập nhật `Upstream base` trong PROGRESS.
