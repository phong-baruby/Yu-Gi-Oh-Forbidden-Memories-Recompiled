---
description: Chạy acceptance, review, cập nhật PROGRESS và commit task hiện tại
---
1. Chạy **đúng** các lệnh acceptance của task hiện tại (xem PROGRESS và file milestone), rồi dán kết quả rút gọn. Nếu chưa đạt thì dừng lại, báo cáo, và không commit.
2. Thực hiện checklist trong `.claude/commands/review-diff.md` trên `git diff`. Sửa hết các mục 🔴.
3. Chạy `python3 tools/pc/macos/diff_budget.py` (nếu đã có); nhóm thư mục cấm sửa phải bằng 0.
4. Cập nhật `docs/macos/PROGRESS.md`:
   - trạng thái task → `[x]`, "Task hiện tại" → task kế tiếp;
   - thêm dòng vào bảng số liệu nếu có thay đổi (census, golden, override, diff budget);
   - Decision log / Upstream touch log nếu có;
   - một dòng vào Nhật ký session: ngày, task, kết quả, việc còn dở.
5. Nếu task làm thay đổi quyết định kiến trúc, cập nhật ADR trong `ARCHITECTURE.md`.
6. Commit với message `macos(<M>/<T-id>): <mô tả ngắn>`. Không commit `tmp/`, dữ liệu game hay ảnh có nội dung game.
7. Gợi ý fen chạy `/clear` rồi `/next-task`.
