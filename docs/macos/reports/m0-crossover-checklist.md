# M0 — Spike CrossOver (T0.3)

**Người làm:** fen (Claude không chạy được GUI/CrossOver). Claude chỉ soạn checklist này.

**Ý nghĩa:** không chặn lộ trình port macOS native. Đây chỉ là một phép thử nhanh:
nếu bản Windows hiện tại chạy được qua CrossOver, fen có một bản chơi tạm trong
lúc port macOS arm64 (M1–M6) đang được làm. Nếu không chạy được hoặc chạy tệ,
không sao — không đổi hướng đi của dự án.

## Chuẩn bị

- [ ] CrossOver đã cài ở `/Applications/CrossOver.app` (đã xong).
- [ ] Disc gốc USA, file `.bin` raw của `SLUS-01411` (theo `notes/setup.md`, dùng
      bản dump chưa bị patch anti-piracy).

## Bước 1 — Tải bản release Windows

1. Vào [Releases của upstream](https://github.com/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled/releases),
   lấy bản mới nhất, file ZIP cho Windows.
2. Giải nén. Trong đó có `memories-pc.exe` + `SDL3.dll` (game 32-bit, không có
   console window — quan trọng cho bước bắt log ở dưới).

## Bước 2 — Tạo bottle Windows 10 64-bit

1. Mở CrossOver, bấm **+ Install a Windows Application** hoặc menu bottle > **New Bottle**.
2. Chọn kiểu bottle **Windows 10 64-bit**, đặt tên dễ nhớ, ví dụ `yfm`.
3. Đợi CrossOver dựng xong bottle (vài phút lần đầu).

## Bước 3 — Đưa game vào bottle và chạy

Cách A (kéo thả — nhanh nhất):
1. Trong CrossOver, chọn bottle `yfm` > **Open C: Drive** (hoặc **Configure** > **Open C: Drive**).
2. Tạo một thư mục, ví dụ `C:\Games\yfm\`, copy `memories-pc.exe` và `SDL3.dll` vào đó.
3. Double-click `memories-pc.exe` ngay trong cửa sổ Finder đó (CrossOver sẽ tự chạy qua Wine).

Cách B (Run Command, nếu cách A không hiện đúng):
1. Bottle `yfm` > menu (⋯) > **Run Command...**
2. Browse tới `memories-pc.exe` đã copy ở bước A.2, chạy.

Lần đầu chạy: nếu chưa có disc path nhớ sẵn, game hiện dialog thông tin và nút
**Choose ROM...** — chọn file `.bin` USA đã chuẩn bị. Không cần set biến môi
trường `MEMORIES_DISC` trong bottle (đó là cơ chế riêng của macOS/Linux).

## Bước 4 — Ghi lại kết quả

### 4.1 Lên title screen chưa?

- [ ] Có / Không
- Ghi chú (đứng ở dialog chọn ROM, crash ngay, màn hình đen, v.v.): ___
- Chụp ảnh màn hình nếu tiện, lưu vào `docs/macos/reports/` (đã có trong
  `.gitignore`: `docs/macos/reports/*.png`, nên không sợ commit nhầm ảnh chứa
  nội dung game).

### 4.2 Log "physical RAM mirror ... taken by Windows"

Vì `memories-pc.exe` là GUI app không có console, log này (in ra `stderr` ở
`src/pc/guest/image.c:281`) sẽ không tự hiện ra. Hai cách bắt:

**Cách 1 — chạy qua Terminal (đáng tin cậy nhất):**
```sh
export WINEPREFIX="$HOME/Library/Application Support/CrossOver/Bottles/yfm"
"/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/bin/wine" \
  "C:\\Games\\yfm\\memories-pc.exe"
```
(Đổi `yfm` nếu đặt tên bottle khác. Nếu đường dẫn `WINEPREFIX` không đúng, mở
CrossOver > bottle > **Configure** để xem đường dẫn thật của bottle.) Log lỗi
sẽ in thẳng ra Terminal.

**Cách 2 — xem log qua CrossOver:** bottle `yfm` > **Configure** > tab
**Diagnostics** (tên tab có thể khác theo phiên bản CrossOver) thường có nút
xem/mở log gần nhất. Nếu không thấy, thử **View in Finder** trên bottle rồi
tìm file log trong đó.

- [ ] Log "taken by Windows" có xuất hiện không? Có / Không
- Nếu có, ghi lại số KiB: ___

### 4.3 FPS

- [ ] Cảm nhận: mượt (khớp 60 FPS gốc PS1) / giật / không chơi được
- Có hiện tượng xé hình (tearing) không: ___
- (Không cần đo số chính xác, chỉ ghi cảm nhận chủ quan.)

### 4.4 Âm thanh

- [ ] Nhạc nền có phát không: ___
- [ ] Hiệu ứng âm thanh (SFX) có phát không: ___
- Có rè, lệch tiếng, hay bị cắt quãng không: ___

### 4.5 Input (tham khảo, không bắt buộc)

- [ ] Bàn phím có nhận không: ___
- [ ] Gamepad (nếu có) có nhận không: ___

## Bảng tổng kết (điền vào đây rồi copy dòng tương ứng sang `PROGRESS.md`)

| Ngày thử | Lên title screen | Log "taken by Windows" | FPS | Âm thanh | Kết luận nhanh |
|---|---|---|---|---|---|
| | | | | | |

Sau khi điền xong, cập nhật `docs/macos/PROGRESS.md`: đổi T0.3 thành `[x]`
(hoặc `[!]`/`[-]` kèm lý do nếu không chạy được), copy dòng tổng kết vào mục
Nhật ký session, rồi báo Claude để commit.
