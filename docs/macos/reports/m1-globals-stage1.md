# M1 — T1.5 phiên 1: đo quy mô + prototype cơ chế global (ADR-03)

**Kết quả: đo quy mô thật xong, cơ chế macro xác nhận đúng qua prototype thật — chưa viết codemod đầy
đủ.** Đây là phiên "đo + prototype" (giống T0.7 làm với field GPTR trước khi T1.3 tổng quát hoá), không
phải phiên hoàn thành T1.5 — phần việc kỹ thuật chính (mở rộng `transform_c_expressions`, sinh
`globals.h`/áp dụng vào 871 symbol) để lại cho phiên sau.

## Khác biệt so với milestone/ADR-03 (đã hỏi fen, đã chốt)

1. **Acceptance đổi từ "link LP64 không còn undefined symbol" → compile sạch** (giống T1.4): T1.9/T1.10
   (build driver) chưa tồn tại, không có cách nào "link" thật lúc này. Link-level verification để dành
   cho T1.10.
2. **"&gFoo trở thành guest address" (câu gốc ADR-03) không đúng theo nghĩa đen** — xem chi tiết dưới.
   Đã sửa `ARCHITECTURE.md`'s ADR-03 với cơ chế thật.

## Công cụ đo: `tools/pc/lp64/gen_globals.py`

Cross-reference `config/pc/guest_addresses.txt` (~3719 candidate trong dải địa chỉ RAM guest) với khai
báo `extern T name;` thật (dùng libclang, quét top-level `VAR_DECL`, không phải `FUNCTION_DECL`) trong
586 header (`DEFAULT_GLOBS`) + 533 file `.c` (`CODE_GLOBS`, toàn bộ phạm vi T1.4 đã làm). Kết quả:

| Phân loại | Số lượng | Có định nghĩa C thật | Mồ côi (chỉ extern) |
|---|---|---|---|
| `plain` (data thuần, không con trỏ) | 736 | 140 | 596 |
| `pointer` (chính global là 1 con trỏ) | 80 | 3 | 77 |
| `pointer-array` (mảng con trỏ) | 31 | 17 | 14 |
| `struct-with-pointer` (struct value, field riêng đã GPTR bởi T1.3) | 13 | 0 | 13 |
| `conflicting` (nhiều kiểu khác nhau theo file) | 11 | — | — |
| `no-match` (không thấy `VAR_DECL`, đa số là hàm) | 2848 | — | — |

→ **871 symbol khớp được** (23% của 3719 candidate thô — phần lớn phần còn lại là tên HÀM nằm chung
dải địa chỉ, không phải global thật). Trong 871: **749 (86%) là `plain`+`struct-with-pointer`**, chỉ
cần macro dereference đơn giản; **111 (13%) là `pointer`/`pointer-array`**, cần xử lý như field GPTR;
**11 (1.3%) "xung đột"**.

## Prototype: xác nhận cơ chế bằng compile thật

Dựng lại chính xác tình huống `ordering_tables.h`'s `D_800E9D90` (`GsOT *D_800E9D90[4]`, 1 trong các file
bị loại trừ suốt T1.4 vì `sizeof(...) == 0x10` sai dưới con trỏ 8-byte thật):

- **Thử dereference macro ra kiểu con trỏ GỐC** (`(*(GsOT *(*)[4])G2H(addr))`): `sizeof` vẫn SAI (32
  byte, vì phần tử mảng vẫn là `GsOT*` thật 8-byte) — **không đủ**.
- **Dereference ra kiểu `gaddr`** (`(*(gaddr (*)[4])G2H(addr))`): `sizeof` ĐÚNG (16 byte, khớp retail).
  Đọc/ghi phần tử cần bọc `G2H`/`H2G` tay (giống hệt field GPTR) — compile sạch dưới cả 3 cờ milestone
  khi làm đúng vậy.

→ Xác nhận: global LÀ con trỏ/mảng con trỏ **bắt buộc** phải dereference ra `gaddr`, không phải kiểu gốc
— và cần cơ chế phân loại G2H/H2G theo ngữ cảnh giống field, nghĩa là `transform_c_expressions` cần mở
rộng thật (không phải chỉ sinh macro là xong).

Với global `plain` (test nhanh bằng suy luận từ cùng cơ chế, không cần prototype riêng — đơn giản hơn
hẳn, không có sự khác biệt kiểu-gốc-vs-gaddr nào để lo): macro dereference thẳng kiểu gốc hoạt động đúng
ngay, `&gFoo` tự nhiên rút gọn về con trỏ host thật qua ngữ nghĩa C thường (`&*p == p`), và khi giá trị đó
cần lưu vào field/global khác đã là `gaddr`, `classify_write` hiện có (chỉ xét KIỂU của RHS, không quan
tâm RHS là field hay global) tự bọc `H2G` đúng — không cần sửa gì thêm cho 86% này.

## Phát hiện: "xung đột kiểu" không phải lỗi — là nhiều view hợp lệ trên cùng byte retail

Đọc code thật cho 2/11 case xung đột để xác nhận không phải bug:
- `g_SDValue`: hầu hết file dùng `SDValue *g_SDValue;` (con trỏ), riêng `func_800464F0.c` khai báo mảng
  `SDValue *g_SDValue[];` rồi dùng `g_SDValue[0]->...` — cùng ý nghĩa, chỉ khác cú pháp viết.
- `D_800E9EF0`: `display_object_work_slots.h` xem là mảng con trỏ `struct DisplayObject *[]`, riêng
  `duel_ritual_effect.c` xem CÙNG VÙNG NHỚ như 1 struct `DisplayObjectRitualWorkArea` (`D_800E9EF0.ritual.result`,
  `D_800E9EF0.slots[i]`) — 2 view khác nhau trên cùng byte, bình thường trong code đã decompile.

→ Giải pháp không cần xử lý riêng: thay THEO TỪNG FILE (khớp đúng kiểu khai báo tại file đó), không dùng
1 header macro dùng chung toàn dự án — xung đột tự biến mất vì mỗi nơi tự lo đúng view của mình (đúng
tinh thần override theo `file + pattern` của ADR-05).

## Hướng cho phiên T1.5 tiếp theo (chưa làm)

1. Mở rộng `transform_c_expressions` (hoặc file mới tương tự) quét `DeclRefExpr` khớp danh sách global đã
   đo, áp cùng logic classify đã có cho field — cho 111 global `pointer`/`pointer-array`.
2. Sinh macro cho 749 global `plain`/`struct-with-pointer` — không cần AST, chỉ cần thay text
   `extern T name;` → `#define name (*(T*)G2H(addr))` tại đúng vị trí khai báo (per-file, không header
   dùng chung, để tự động né xung đột).
3. Xử lý việc XOÁ định nghĩa C thật (140+3+17+0=160 global có định nghĩa) — file đang chứa `T name =
   {...};`/`T name;` thật cần loại bỏ phần lưu trữ đó (macro đã thay thế hoàn toàn, không thể vừa là
   macro vừa là biến thật).
4. Chia batch như T1.4 (871 symbol, tương đương quy mô ~1 nửa T1.4) — đo lại chính xác số file bị ảnh
   hưởng mỗi batch trước khi làm.
5. Kỳ vọng: các file ADR-03 đã loại trừ suốt T1.4 (44 file: `ordering_tables.h`, `display_object_work_slots.h`,
   ...) sẽ compile sạch sau khi global tương ứng được xử lý — tín hiệu xác nhận rõ ràng nhất.

## File tạo/sửa phiên này

- `tools/pc/lp64/gen_globals.py` (mới, công cụ đo — giữ lại dùng cho các phiên sau)
- `docs/macos/ARCHITECTURE.md` (sửa ADR-03 theo cơ chế thật)
- `docs/macos/reports/m1-globals-stage1.md` (report này)
- Không sửa `src/game`, `src/overlays`, `src/psyq`, không sinh `globals.h` thật (chỉ prototype trong
  `/tmp`, không commit)
