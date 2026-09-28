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

- [x] Có — vượt xa hơn dự kiến: qua title screen, nhập tên, tới tận màn
  **build deck** (danh sách bài render đúng, đọc được rõ ràng).
- Ghi chú: dùng bottle "Windows 10 64 Bit" tạo qua flow **Install an unlisted
  application** (không qua flow "New Bottle" thủ công như hướng dẫn gốc ở
  Bước 2 — CrossOver bản 26.3 gộp 2 bước làm một, tự nhận diện file `.exe` và
  tự tạo bottle 64-bit phù hợp).
- ROM dùng để test: **không phải đĩa gốc** — dùng tạm bản mod
  `YGOFM Mod 2023 15x.bin` (drop rate x15) vì chưa có dump đĩa gốc USA hợp lệ
  (2 bản `.bin` khác kiểm tra hash không khớp bản retail SLUS-01411).

### 4.2 Log "physical RAM mirror ... taken by Windows"

- [ ] **Chưa kiểm tra được.** Game bị đơ (xem mục 4.5) trước khi kịp thực hiện
  bước chạy qua Terminal để bắt `stderr`. Không phải ưu tiên để thử lại lần
  4 — không ảnh hưởng tới quyết định go/no-go của T0.3.

### 4.3 FPS

- [x] **Giật/lag** — không mượt. (Lần thử đầu bị nhiễu bởi một tiến trình cài
  đặt "Unlisted application" chạy song song trong CrossOver chưa xong; lần
  thử lại sau khi cài xong vẫn giật, nên không chỉ do install chạy nền.)

### 4.4 Âm thanh

- [x] Nhạc nền + SFX **có phát**, nhưng **rè liên tục** trong suốt quá trình
  chơi, không phải hiện tượng thoáng qua.

### 4.5 Input

- [x] Bàn phím **có nhận lúc đầu** (chọn menu, build deck bình thường).
- [x] **Đơ hoàn toàn** (không bấm được gì nữa, kể cả sau khi vào menu
  **Game > Controller** rồi thoát ra mà **chưa đổi gì**) — tái hiện **3 lần
  liên tiếp** (thử lại từ đầu 3 lần, kể cả sau khi force-quit qua Activity
  Monitor và mở lại), nên là lỗi thật của tổ hợp CrossOver/Wine + màn hình
  Controller config, không phải ngẫu nhiên.
- Gamepad: chưa thử (dừng lại sau khi bàn phím đã đơ).

## Bảng tổng kết

| Ngày thử | Lên title screen | Log "taken by Windows" | FPS | Âm thanh | Kết luận nhanh |
|---|---|---|---|---|---|
| 2026-09-28 | Có, tới tận build deck | Chưa kiểm tra được (đơ trước khi kịp bắt log) | Giật/lag | Có phát, rè liên tục | Chạy được ở mức cơ bản nhưng **không ổn định**: đơ hẳn khi vào Game > Controller (tái hiện 3/3 lần), không đủ tin cậy làm bản chơi tạm. Không chặn lộ trình port native. |

**Kết luận T0.3:** CrossOver có thể load và chạy sâu được bản Windows hiện tại
trên Apple Silicon (kể cả build deck với dữ liệu bài đầy đủ), nhưng gặp treo
cứng có thể tái hiện khi vào màn hình cấu hình Controller, cộng thêm giật lag
và rè âm thanh liên tục. Không đủ ổn định để dùng làm bản chơi tạm đáng tin
cậy trong lúc port macOS native — nhưng đúng như milestone đã ghi, **điều này
không chặn lộ trình port**, chỉ là T0.3 không mang lại một "bản chơi tạm" hữu
dụng như kỳ vọng ban đầu.
