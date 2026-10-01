# M1 — Codemod giai đoạn 1: toàn bộ struct/union (T1.3)

**Kết quả: cả 2 tiêu chí acceptance đạt.**
- `check_layouts_lp64.py`: **0 khác biệt layout** trên toàn bộ struct/union có con trỏ hoặc `long`/`unsigned long` trần, trong cả 586 header thuộc 4 pattern milestone nêu (`src/*.h`, `src/game/**/*.h`, `src/overlays/**/*.h`, `src/psyq/*.h`).
- Toàn bộ static assert (`X_size_must_be_0xNN`, `X_offset_must_be_...`) trong `src/ygo_types.h` pass khi compile arm64+`MEMORIES_LP64` trên output codemod.
- `codemod.py` vẫn idempotent trên quy mô đầy đủ (586 header, không chỉ 5 struct như T0.7).

**Lệnh:**
```sh
python3 tools/pc/lp64/codemod.py                 # đọc src/, ghi tmp/lp64/src/
python3 tools/pc/lp64/check_layouts_lp64.py       # so layout i386 gốc vs arm64+LP64
```

## Mở rộng phạm vi so với T0.7

T0.7 hard-code 5 struct trong 1 file (`ygo_types.h`). T1.3 tổng quát hoá: dò **mọi**
struct/union trong **586 header** thuộc 4 pattern milestone yêu cầu, không còn
danh sách cố định. Quy mô thật (dò bằng chính libclang trước khi code, không
đoán): **126 struct, 353 field con trỏ, 48 header**.

## Phát hiện ngoài phạm vi ban đầu: `long`/`unsigned long` trần

Layout check đầu tiên lộ ra **30 struct khác layout mà KHÔNG liên quan con
trỏ** — ví dụ `struct TCB { long status; long mode; unsigned long reg[40]; ... };`
trong `src/psyq/kernel.h`. Nguyên nhân: `long` là 4 byte trên i386 (host build
hiện tại khớp) nhưng **8 byte trên bất kỳ ABI C 64-bit gốc nào, kể cả arm64
macOS** — không liên quan gì `MEMORIES_LP64`, đây là quy ước của compiler/kiến
trúc. Đã hỏi fen và được duyệt mở rộng codemod xử lý luôn (xem Decision log):
field `long`/`unsigned long` trần (không qua typedef) → `s32`/`u32` (đã có sẵn
trong `src/types.h`, dùng khắp nơi trong dự án). **156 field, 10 header**, chủ
yếu trong PSY-Q SDK (`libgs.h` 72, `kernel.h` 31, `libspu.h` 21...). Đã ghi
vào ADR-05 (mục 8) trong `ARCHITECTURE.md`.

## 6 bug tự vấp phải và cách sửa — đáng đọc trước khi làm T1.4

### 1. Offset byte của libclang lệch với offset ký tự của Python string
`field.extent.start.offset` là **byte offset** trong file gốc. Đọc file bằng
Python text string (`open(path).read()`) rồi slice theo offset đó **sai** nếu
file có bất kỳ byte non-ASCII nào trước field (`é`, ký tự Nhật trong comment —
vài header có thật). **Sửa:** đọc/ghi toàn bộ bằng `bytes` (`open(path, "rb")`),
không decode sang `str` cho đến khi tạo text thay thế (ASCII, encode lúc ghép).

### 2. `walk_preorder` thay vì `get_children()` cho struct lồng nhau
Struct ẩn danh **lồng bên trong** struct khác (`struct { unsigned long* seq; } bgm;`
trong `mcgui.h`) không phải cursor cấp đỉnh — `tu.cursor.get_children()` chỉ
thấy struct cấp đỉnh, bỏ sót hoàn toàn field bên trong struct lồng. **Sửa:**
`tu.cursor.walk_preorder()` (đệ quy toàn cây), kèm lọc theo file đúng tên.

### 3. `walk_preorder` có thể duyệt trùng đúng 1 record
Struct ẩn danh + typedef ngay sau (`typedef struct {...} _GsFCALL;`) đôi khi bị
`walk_preorder` liệt kê **2 lần** (cùng extent) — sinh ra 2 edit chồng lấn
offset, splice hỏng (brace mất cân bằng, text lặp). **Sửa:** `seen_records`
(set theo `(start, end)` của record) khử trùng trước khi xử lý field.

### 4. `field.type.kind` báo `ELABORATED` chứ không phải `TYPEDEF`
Đã phát hiện từ T0.7, nhắc lại vì quan trọng: field khai báo qua typedef con
trỏ (`FileTransferCallback phase_callback;`) có `field.type.kind ==
TypeKind.ELABORATED`, không phải `TYPEDEF`. Dùng
`field.type.get_declaration().kind == CursorKind.TYPEDEF_DECL` mới đúng.

### 5. `cursor.spelling` của struct ẩn danh trả về tên typedef — không phải dấu hiệu có tag thật
Khi viết `check_layouts_lp64.py`: với `typedef struct {...} Foo;`, libclang gán
**`cursor.spelling = "Foo"`** cho struct cursor dù nó ẩn danh (tiện ích hiển
thị của libclang) — trông y hệt một struct có tag thật (`struct Foo {...}`).
Kiểm `if cursor.spelling:` để quyết định "có tag hay không" là **sai**: gần
như toàn bộ struct trong `ygo_types.h` là dạng ẩn danh+typedef này, nên cách
kiểm đó âm thầm loại gần hết chúng khỏi so sánh (không khớp tên trong
`TAGS`, vì không có text `struct Foo {` thật trong source). **Sửa:** dùng
`cursor.is_anonymous()` — API libclang có sẵn cho đúng việc này.

### 6. Khai báo nhiều biến chung 1 kiểu (`long a, b;`) có extent chồng lấn
Phổ biến trong codebase này (1256 field dạng này toàn bộ scope, không hiếm).
`field.extent` của declarator **thứ 2 trở đi** trong một khai báo nhiều biến
**bao gồm cả phần trước nó**: với `long vx, vy;`, field `vx` có extent
`"long vx"`, nhưng field `vy` có extent **`"long vx, vy"`** (không phải chỉ
`"vy"`) — hai extent chồng lấn thay vì nối tiếp. Edit từng field độc lập (giả
định extent rời nhau) làm 2 edit cùng offset bắt đầu chồng lên nhau, splice
sau dùng offset đã lệch (do splice trước làm đổi độ dài buffer), sinh text hỏng
(`s32 vx; vy;` — dấu phẩy biến thành chấm phẩy, `vy` mất kiểu). **Sửa:** gom
các field liên tiếp có cùng `extent.start.offset` thành 1 nhóm, sửa 1 lần cho
cả nhóm (giữ nguyên phần sau từ khoá kiểu, kể cả dấu phẩy/tên khác) thay vì
từng field riêng lẻ. Nhóm có field con trỏ không qua typedef (GPTR hoặc con
trỏ hàm inline) phải dùng khối `#ifdef` verbatim cho cả nhóm (không thể gọi
macro 1 lần cho nhiều tên, vì `GPTR(T) a, b;` ở nhánh non-LP64 chỉ thêm `*`
đúng 1 lần ở vị trí kiểu, làm `b` thành `T` trần thay vì `T*`) — nhóm chỉ gồm
field typedef con trỏ (`GPTR_FN`) thì an toàn gọi macro 1 lần, vì nhánh
non-LP64 của `GPTR_FN(T)` là `T` trần, không thêm `*`, nên đúng cho mọi tên.

### Thêm: 2 bug trong chính `check_layouts_lp64.py` khi viết nó (không phải codemod.py)
- **Severity `>= Fatal` bỏ sót lỗi `Error`:** `'r3000.h' file not found with
  <angled> include` là severity `Error` (3), không phải `Fatal` (4) — clang
  coi include hỏng là lỗi phục hồi được, chạy tiếp. Lọc theo `>= Fatal` không
  bắt được, nên logic retry-với-prelude không bao giờ chạy.
- **Pattern-match text "not found" bỏ sót lỗi downstream:** `libsnd.h` cần
  prelude nhưng lỗi hiển thị lại là `"unknown type name 's32'"` (không nhắc
  tên file nào) — hệ quả gián tiếp của việc thiếu include, không phải thông
  báo "not found" trực tiếp. Sửa: retry hễ còn **bất kỳ** diagnostic `>= Error`,
  không lọc theo nội dung message. **Cùng bug này cũng có trong `codemod.py`
  — đã sửa đồng thời**, vì nếu không sửa, `codemod.py` sẽ âm thầm dùng kết quả
  parse hỏng (thiếu `types.h`) cho các header cần prelude, có thể bỏ sót field
  cần biến đổi mà không báo lỗi gì.

## 2 vấn đề còn lại — đã biết từ trước, ngoài phạm vi T1.3

Sau khi sửa hết 6 bug trên, `game/display_object_helpers.h` và
`game/mem_card_work.h` vẫn còn lỗi parse ở phía arm64+LP64 — nhưng là lỗi
**section attribute kiểu ELF** (`__attribute__((section(".data")))`, Mach-O
cần `"SEGMENT,section"`) đã ghi nhận từ T0.4/T0.5/T0.6, hoàn toàn không liên
quan con trỏ hay `long`. Không phải việc của T1.3 (ADR-05 transformation 1),
để M1 sau xử lý bằng `#if defined(__APPLE__)` riêng.

## Số liệu cuối

| | |
|---|---|
| Header xử lý | 586 |
| Header codemod thực sự đổi | 49 |
| Field con trỏ biến đổi (GPTR/GPTR_FN/`#ifdef`) | 353 |
| Field `long`/`unsigned long` biến đổi | 156 |
| Struct/union so sánh layout | 95 (số unique sau khi gộp field thành nhóm; 126 struct gốc có field cần đổi) |
| Khác biệt layout còn lại | **0** |
| Idempotent | Có (toàn bộ 586 header, byte-identical) |
