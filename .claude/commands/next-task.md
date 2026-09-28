---
description: Chọn task kế tiếp trong PROGRESS, lập plan và chờ duyệt
argument-hint: "[T-id tuỳ chọn, ví dụ T1.4b]"
---
1. Đọc `docs/macos/PROGRESS.md`. Nếu có `$ARGUMENTS` thì chọn task đó; nếu không, chọn task đầu tiên có trạng thái `[ ]` hoặc `[~]` mà các task phía trước và Gate liên quan đã xong. Nếu task bị chặn bởi một Gate chưa được duyệt, dừng lại và báo.
2. Đọc phần của task đó trong `docs/macos/milestones/`, các ADR liên quan trong `docs/macos/ARCHITECTURE.md`, cùng mọi file trong mục "Đọc trước".
3. **Kiểm chứng giả định:** dùng grep/đọc code để xác nhận các tên file, hàm, flag mà plan nhắc tới. Liệt kê những chỗ khác với thực tế.
4. Trình bày plan theo dạng sau, rồi **dừng lại chờ duyệt, chưa viết code**:
   - **Task:** T-id và mục tiêu trong một câu
   - **Khác biệt so với plan** (nếu có) kèm đề xuất sửa file milestone
   - **Scope IN / OUT**
   - **File sẽ tạo / sửa** (đánh dấu file nào là file dùng chung của upstream)
   - **Các bước**, mỗi bước kiểm tra được
   - **Acceptance** (lệnh cụ thể sẽ chạy)
   - **Rủi ro** (tối đa 3)
5. Sau khi được duyệt: đổi trạng thái task thành `[~]` trong PROGRESS rồi bắt đầu làm.
