# Vận hành fork lâu dài

## Branch
- `upstream/master`: không bao giờ sửa.
- `macos/main`: **patch stack**, gồm một chuỗi commit nhỏ và mạch lạc nằm trên upstream. Rebase định kỳ, không tạo merge commit.
- `macos/wip/<task>`: nhánh làm từng task, squash gọn trước khi đưa vào `macos/main`.

Patch stack nên được nhóm thành các commit logic, mỗi nhóm thuộc một đường riêng (ví dụ: kit/docs · gptr runtime · codemod · platform macOS · golden · save state · mods · packaging). Khi rebase, conflict sẽ khoanh vùng theo nhóm.

## Quy trình sync (hằng tuần, hoặc khi upstream có thay đổi lớn) — dùng `/sync-upstream`
1. `git fetch upstream`; đọc log các commit mới, **đặc biệt** những commit chạm tới: `src/pc/guest/`, `src/pc/mods/`, `tools/pc/build_game32.py`, `src/ygo_types.h`, header struct, `notes/pc-build.md`.
2. Rebase `macos/main` lên một branch tạm `macos/sync-<date>`.
3. Chạy codemod, rồi `check_layouts_lp64.py`, build, ctest, golden toàn bộ.
4. Nếu fail: ưu tiên sửa **codemod** (pattern mới). Chỉ khi pattern đó thật sự hiếm mới thêm override.
5. Tạo lại golden trên reference cho commit mới (golden có thể thay đổi hợp lệ khi upstream sửa game).
6. Xanh hết thì fast-forward `macos/main`, rồi cập nhật `Upstream base` trong PROGRESS.

## Tripwire tự động
- Size assertion của `ygo_types.h` cùng `check_layouts_lp64.py`: upstream thêm field con trỏ mà codemod chưa bắt được thì build fail ngay.
- `diff_budget.py`: diff trên các thư mục game bị cấm phải bằng 0; diff trên file dùng chung được theo dõi theo thời gian.
- Golden: bắt lỗi hành vi.

## Khi upstream tự làm 64-bit
Tác giả chỉ "hoãn" 64-bit (từ 2026-09-20). Nếu upstream bắt đầu làm:
1. Đọc thiết kế của họ và so với ADR-01/02/04.
2. Nếu tương thích về ý tưởng: chuyển sang abstraction của họ, biến fork thành lớp mỏng chỉ còn platform macOS và packaging. Chấp nhận bỏ phần codemod.
3. Nếu khác hướng: giữ hướng của fork, nhưng ghi rõ lý do vào Decision log.

## Versioning
`v<upstream-release>-mac.<n>`, ví dụ `v1.4.0-mac.2`. Mỗi release macOS ghi rõ base commit của upstream.

## License và dữ liệu
- PC port dùng MIT: giữ copyright notice, link về repo gốc, ghi công memories-decomp.
- Không bao giờ phân phối dữ liệu game; người dùng tự cung cấp `.bin` của disc USA (SLUS-01411).
