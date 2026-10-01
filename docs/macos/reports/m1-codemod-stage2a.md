# M1 — Codemod giai đoạn 2, batch a: SDK (T1.4a)

**Kết quả: acceptance đạt cho toàn bộ scope đo được, trừ 1 ngoại lệ đã ghi nhận rõ (xem "Phát hiện mới, để lại cho T1.5/T1.6").**

**Lệnh:**
```sh
python3 tools/pc/lp64/codemod.py                 # cũng copy + override src/psyq/*.c vào tmp/lp64/src
python3 tools/pc/lp64/check_layouts_lp64.py       # vẫn 0 khác biệt (không hồi quy so với T1.3)
```

## Quy mô thật — đo bằng compile thử (libclang/clang), không đoán

Scope milestone: `src/psyq` (chỉ 1 file `.c`, `startup_data.c`) và `src/pc/sdk` (12 file `.c`).
Trước khi sửa, đo bằng cách parse cả 13 file dưới `arm64-apple-macos + MEMORIES_LP64` chống lại
header đã codemod T1.3 (`tmp/lp64/src`), tìm mọi truy cập field kiểu `gaddr` và mọi ép kiểu hằng số
địa chỉ guest:

| Loại (ADR-05) | Số điểm | File |
|---|---|---|
| (2) Đọc field con trỏ | 2 | `libgte_extra.c` (`get_lw`, field `super` của `GsCOORDINATE2`) |
| (3) Ép kiểu hằng địa chỉ guest → con trỏ | 6 | `libgte.c` ×4, `libgte_extra.c` ×2 (bảng sin/cos trong EXE) |
| (4) Số học con trỏ trên field guest | 0 | — |
| (6) Gọi qua con trỏ hàm lấy từ guest | 0 | — |

Batch SDK hầu như không tự đụng field guest trực tiếp: phần lớn hàm nhận tham số đã là host
pointer (được gọi nơi khác G2H trước khi truyền vào), nên (4)/(6) không xuất hiện trong batch này.

## Cách làm — khác với T1.3, và vì sao

T1.3 tổng quát hoá bằng một bộ biến đổi AST áp dụng cho **mọi** header. Với quy mô (2)+(3)+(4)+(6)
đo được ở batch này (9 điểm thật trên 13 file), xây một bộ quét/biến đổi AST tổng quát cho biểu
thức trong `.c` là over-engineering. Thay vào đó:

- **`src/pc/sdk/*.c`** không nằm trong danh sách cấm sửa tay của CLAUDE.md (chỉ `src/game`,
  `src/overlays`, `src/psyq`, `ygo_types.h`, `types.h` bị cấm) — đây là "file dùng chung của
  upstream" theo luật 3, nên sửa tay trực tiếp, bọc `#ifdef MEMORIES_LP64` giữ nguyên 100% hành vi
  nhánh không-LP64 (`G2H`/`H2G` tự thân đã là no-op cast ở nhánh đó, xem `gptr.h`), ghi vào Upstream
  touch log.
- **`src/psyq/startup_data.c`** nằm trong danh sách cấm — chỉ sửa được qua codemod. T1.4a mở rộng
  `codemod.py` với `CODE_GLOBS` (hiện chỉ `psyq/*.c`) và cơ chế `config/lp64/overrides.toml` mới
  (thay thế chuỗi literal, khớp đúng 1 lần mới cho qua, báo lỗi rõ nếu 0 hoặc >1 lần) — không chạy
  AST transform cho `.c` (file này không có struct/union, không có biểu thức GPTR nào trong scope).
  `.c` trong `CODE_GLOBS` được copy sang `tmp/lp64/src` để `#include "../types.h"` kiểu tương đối
  trỏ đúng cây đã biến đổi.

## Phát hiện nghiêm trọng: `DividePolygon4`/`DivideLevel` tràn vùng scratchpad cố định

`src/pc/sdk/libgte.c` tự khai báo cục bộ `DivideLevel`/`DividePolygon4` (không qua header, T1.3
không đụng tới), có `_Static_assert(... sizeof(DivideLevel) == 0x8c, ...)` và comment "work area is
**the caller's DIVPOLYGON4, laid out as in libgte.h**". Theo dấu người gọi thật
(`src/game/display_object_helpers.c:12-18`): buffer này nằm ở **scratchpad cố định `0x1F800000`**,
vùng kế tiếp bắt đầu tại `0x1F8002E0`. Compile thử thật trên arm64 (không giả định):
`sizeof(DividePolygon4)` với con trỏ gốc 8-byte = **928 byte**, vượt quá budget 736 byte — một lỗi
ghi đè bộ nhớ thật lúc chạy game, không chỉ lỗi compile. Đã hỏi fen (`AskUserQuestion`), được duyệt
sửa thật ngay (không chỉ nới lỏng assert).

**Fix:** 3 field cần nén về 4 byte dưới LP64 (giữ nguyên hành vi/kích thước ở nhánh không-LP64):
- `DivideLevel.corner[4]` (`DivideVertex*[4]`): luôn trỏ vào bên trong **cùng** buffer `work` →
  nén thành offset-byte-từ-`work` (`uint32_t[4]`), qua 2 hàm helper `corner_get`/`corner_set`
  (thân khác nhau theo `#ifdef`, chữ ký giống nhau — phần thân `divide_ft4`/`emit_ft4` không đổi).
- `DivideLevel.unused_return` (`uint32_t*`): xác nhận **chưa từng được đọc/ghi** ở đâu trong file —
  chỉ tồn tại để giữ đúng kích thước; đổi thẳng thành `uint32_t` dưới LP64.
- `DividePolygon4.ot`: trỏ ra NGOÀI buffer (bảng sắp xếp thứ tự GPU, guest RAM thật, xác nhận qua
  người gọi: `(u32 *)GS_OT_VIEW(ot)->org + pri`) → dùng thẳng `GPTR(unsigned int)` (macro có sẵn
  trong `gptr.h`, không cần `#ifdef` riêng) và bọc `G2H`/`H2G` ở 3 điểm đọc/ghi.

Compile thật xác nhận: `sizeof(DivideLevel) == 0x8c` và static assert pass dưới cả
`arm64 + MEMORIES_LP64` lẫn `i386` (nhánh không-LP64 giữ nguyên byte-for-byte, không re-test lại vì
không đổi gì ở đó).

## Phát hiện mới, để lại cho T1.5/T1.6 (không sửa trong T1.4a)

`src/psyq/startup_data.c`'s `D_800906E8[7]` là một bảng dữ liệu nhúng ở địa chỉ retail
(`0x800906E8`), chứa `(u32)entrypoint`, `(u32)&initialized_data_start`,
`(u32)gGraphics_aFrameBuffers` — ép kiểu **con trỏ host xuống 4 byte trần**, không qua `H2G`.
Compile thử xác nhận đây là `-Wpointer-to-int-cast` thật dưới arm64 (không xảy ra trên i386, nơi
con trỏ đã là 4 byte). Đây không phải việc của ADR-05 (2)/(3)/(4)/(6) (field nào cũng không phải
GPTR cả — `entrypoint` là hàm, không phải field guest; bảng này rõ ràng thuộc phạm trù ADR-03
"global sống trong RAM guest" / ADR-04 "bảng con trỏ hàm" mà T1.5/T1.6 sẽ xây cơ chế, T1.4a chưa có
gì để gọi đúng). Ghi vào "Vấn đề mở" để T1.5/T1.6 xử lý cùng lúc.

## 2 quan sát phụ, không phải việc của T1.4a

- `libapi_krom.c` cần FreeType (có qua Homebrew, `-I/opt/homebrew/opt/freetype/include/freetype2`)
  **và** `fontconfig` (không có trên macOS — đã biết, ADR-09/T1.8: "không có fontconfig trên macOS,
  bundle sẵn TTF"). Không phải lỗi LP64/con trỏ; để T1.8 xử lý nhánh `__APPLE__` riêng.
  Không có điểm GPTR nào trong file này (đã xác nhận bằng quét AST).
- Compile tách rời `startup_data.c` báo `gGraphics_aFrameBuffers` undeclared (field này chỉ khai
  báo khi *không* có `MEMORIES_PC`, bản khai báo thật cho `MEMORIES_PC` nằm ở
  `src/game/graphics_frame_buffer.h`, không được include trực tiếp). Đã xác nhận: lỗi **giống hệt**
  khi compile bằng đúng `NATIVE_CFLAGS` thật trên `i386-pc-linux-gnu` — có từ trước, không phải hồi
  quy của T1.4a, không điều tra thêm (ngoài scope).

## Xác minh

- `check_layouts_lp64.py`: vẫn `0 differ` trên toàn bộ 586 header (không hồi quy T1.3).
- `codemod.py` idempotent: chạy 2 lần (kể cả phần `.c` mới qua `overrides.toml`) cho output
  byte-identical.
- 11/12 file `src/pc/sdk/*.c` (trừ `libapi_krom.c`, chặn bởi fontconfig — môi trường, không phải
  code) compile sạch dưới `arm64-apple-macos -DMEMORIES_LP64` **và** `i386-pc-linux-gnu` (nhánh
  không-LP64) với đúng 3 cờ milestone yêu cầu: `-Werror=int-conversion -Werror=pointer-to-int-cast
  -Werror=int-to-pointer-cast`, dùng đúng include thật của từng file (không psyq prelude giả định
  — prelude đó từng tạo ra 44 lỗi "conflicting types" giả, do ép include chéo header mà file gốc
  không hề dùng).
- `src/psyq/startup_data.c`: lỗi Mach-O section attribute đã hết; còn lại 2 cảnh báo
  `pointer-to-int-cast` thật (mục "để lại cho T1.5/T1.6" ở trên) — chưa đạt "0 lỗi tuyệt đối" cho
  riêng file này, có chủ đích, đã ghi rõ lý do.
- `ctest --test-dir tmp/pc/cmake-mac` (cấu hình mặc định, không `MEMORIES_LP64`): 30/59 fail — khớp
  đúng baseline T0.4 (30/59), không hồi quy (các file T1.4a sửa không nằm trong target CMake nào
  ngoài `libds.c`, không đụng).

## Số liệu cuối

| | |
|---|---|
| File trong scope | 13 (1 `psyq/*.c` + 12 `pc/sdk/*.c`) |
| Điểm ADR-05 (2) sửa | 2 |
| Điểm ADR-05 (3) sửa | 6 |
| Điểm ADR-05 (4)/(6) | 0 (đo, không có) |
| Struct cục bộ nén lại (ngoài ADR-05 liệt kê, duyệt riêng) | 1 (`DivideLevel`/`DividePolygon4`, 3 field) |
| Override `.toml` mới (Mach-O section attribute) | 1 |
| File compile sạch / tổng | 11/12 (1 chặn bởi thiếu fontconfig trên máy, môi trường) |
| Vấn đề mới để lại cho task sau | 1 (bảng `D_800906E8`, → T1.5/T1.6) |
| Hồi quy layout (T1.3) | 0 |
| Hồi quy ctest baseline | 0 |
