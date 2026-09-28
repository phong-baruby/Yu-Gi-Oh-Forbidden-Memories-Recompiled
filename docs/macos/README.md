# Kit port macOS — cách dùng với Claude Code

## Cài đặt kit
1. Fork repo gốc và clone về Mac mini.
2. Copy toàn bộ nội dung kit (`CLAUDE.md`, `docs/macos/`, `.claude/commands/`) vào root của repo.
3. Đặt đường dẫn disc ngoài repo: `export MEMORIES_DISC=~/Games/YFM/yfm-usa.bin` (thêm vào `~/.zshrc`).
4. Mở terminal tại root repo và chạy `claude`.

## Vòng lặp hằng ngày
```
/next-task          → Claude đọc PROGRESS, chọn task, lập plan và CHỜ fen duyệt
(fen duyệt hoặc chỉnh plan)
... Claude làm ...
/review-diff        → Claude tự review diff theo checklist
/finish-task        → chạy acceptance, cập nhật PROGRESS, commit
/clear              → dọn context trước khi sang task mới
```
Mỗi tuần một lần: `/sync-upstream`.

## Mẹo
- Nên bắt đầu mỗi task bằng một session mới (`/clear`). File CLAUDE.md và PROGRESS.md đã đủ để Claude nắm lại bối cảnh.
- Task lớn (T1.4, T3.2, T5.6) đã được chia thành batch; đừng gộp nhiều batch vào một session.
- Khi Claude báo "plan sai so với thực tế": sửa file milestone trước, rồi mới làm tiếp.
- Các Gate G0–G6 là điểm **fen** quyết định, không để Claude tự đánh dấu.

## Tài liệu
- `ARCHITECTURE.md`: các quyết định kỹ thuật (ADR-01 đến ADR-12).
- `milestones/M0` đến `M6`: task chi tiết, acceptance, thứ tự.
- `PROGRESS.md`: trạng thái, số liệu, decision log, upstream touch log.
- `FORK-MAINTENANCE.md`: sync upstream, CI, versioning.
- `reports/`: báo cáo do các task discovery sinh ra.
