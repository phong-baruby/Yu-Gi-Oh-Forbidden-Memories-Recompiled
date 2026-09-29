# M0 — Prototype codemod, 5 struct (T0.7) — dữ liệu cho Gate G0

**Kết quả ngắn gọn: cả 2 tiêu chí acceptance đều đạt.**
- Layout của cả 5 struct giống hệt nhau giữa i386 gốc (retail) và arm64+`MEMORIES_LP64` trên output codemod.
- Codemod idempotent: chạy 2 lần cho output byte-identical.
- Trong 15 field con trỏ ở 5 struct, chỉ **1 field (6.7%)** cần xử lý khác quy tắc chung (`GPTR_FN` thay vì `GPTR`) — dưới xa ngưỡng 30% mà milestone đặt ra để cân nhắc lại ADR-05.

## Chọn 5 struct

Milestone yêu cầu "5 struct có con trỏ, dùng nhiều nhất". Dò toàn bộ struct/union định nghĩa trực tiếp trong `src/ygo_types.h` bằng chính libclang (không phải regex tay — regex tay ban đầu bị lỗi vì struct lồng nhau, xem mục "Sai lầm đã sửa" cuối report), tìm được **13 struct có field con trỏ**. Đếm tần suất dùng tên struct trong `src/game` + `src/overlays`:

| Struct | Số lần xuất hiện | Số file | Số field con trỏ |
|---|---|---|---|
| `DuelEffectChannel` | 285 | 95 | 6 |
| `FileTransferDescriptor` | 100 | 43 | 3 |
| `TextStreamOwner` | 25 | 15 | 1 (mảng 22 con trỏ) |
| `DisplayObjectStreamState` | 22 | 7 | 3 |
| `LibraryMotionState` | 16 | 7 | 2 |
| *(8 struct còn lại)* | ≤9 mỗi struct | | |

5 struct đầu được chọn — vừa dùng nhiều nhất, vừa trải đều độ phức tạp (1 đến 6 field/struct), tốt cho việc đo go/no-go hơn là chọn 5 struct giống nhau.

## Deliverable

- `src/pc/guest/gptr.h` — bản tối thiểu đúng ADR-02, cộng thêm macro mới phát hiện cần thiết: `GPTR_FN(T)` (xem mục dưới).
- `tools/pc/lp64/codemod.py` — dùng libclang, đọc `src/ygo_types.h`, ghi `tmp/lp64/src/ygo_types.h`. Chỉ làm transformation (1) của ADR-05 (field con trỏ struct/union → `GPTR`) cho đúng 5 struct trên. Không sửa `src/` (chỉ đọc).

## Phát hiện: cần thêm macro `GPTR_FN(T)` — ADR-02/05 cần cập nhật

`FileTransferDescriptor.phase_callback` có kiểu `FileTransferCallback`
(`typedef void (*FileTransferCallback)();`) — **bản thân typedef đã là con
trỏ**. Áp `GPTR(FileTransferCallback)` sẽ nhân đôi dấu `*` ở nhánh không-LP64
(`#define GPTR(T) T *` → `FileTransferCallback *phase_callback;`, sai — biến
thành con trỏ-tới-con-trỏ-hàm thay vì con trỏ hàm).

Thêm macro riêng cho trường hợp field được khai báo **qua một typedef con
trỏ** (không tự viết dấu `*`):
```c
#define GPTR_FN(T) gaddr   /* LP64 */
#define GPTR_FN(T) T       /* không LP64 — T đã là con trỏ, không thêm * */
```
`codemod.py` phát hiện case này bằng `field.type.get_declaration().kind ==
CursorKind.TYPEDEF_DECL` trên type **đã khai báo** (chưa canonical hoá) —
lưu ý: `field.type.kind` của một field kiểu typedef báo về
`TypeKind.ELABORATED`, **không phải** `TypeKind.TYPEDEF` trực tiếp trong
libclang (bẫy đã tự vấp phải, xem "Sai lầm đã sửa"). Kết quả:
```c
GPTR_FN(FileTransferCallback) phase_callback;
```
**Ý nghĩa cho ADR-05:** transformation (1) ("field con trỏ → `GPTR(T)`") cần
viết lại chính xác hơn: field con trỏ khai báo **trực tiếp** (`T *f`,
`T *f[N]`) → `GPTR(T)`; field khai báo **qua typedef con trỏ đã có sẵn**
(callback, function pointer) → `GPTR_FN(T)`. Đây là bổ sung nhỏ, không đổi
hướng ADR-05, đã cập nhật vào `ARCHITECTURE.md`.

## 15 field đã biến đổi

| Struct | Field | Kiểu gốc | Kết quả |
|---|---|---|---|
| `TextStreamOwner` | `streams` | `u8 *[22]` | `GPTR(unsigned char) streams[22];` |
| `LibraryMotionState` | `slots` | `struct DisplayObject *[8]` | `GPTR(struct DisplayObject) slots[8];` |
| `LibraryMotionState` | `render` | `struct DisplayObject *` | `GPTR(struct DisplayObject) render;` |
| `DuelEffectChannel` | `text_00` | `u8 *` | `GPTR(unsigned char) text_00;` |
| `DuelEffectChannel` | `entry_end_20` | `DuelEffectEntry *` | `GPTR(DuelEffectEntry) entry_end_20;` |
| `DuelEffectChannel` | `entry_head_24` | `DuelEffectEntry *` | `GPTR(DuelEffectEntry) entry_head_24;` |
| `DuelEffectChannel` | `field_28` | `struct DisplayObject *` | `GPTR(struct DisplayObject) field_28;` |
| `DuelEffectChannel` | `field_2C` | `struct DisplayObject *` | `GPTR(struct DisplayObject) field_2C;` |
| `DuelEffectChannel` | `field_30` | `struct DisplayObject *` | `GPTR(struct DisplayObject) field_30;` |
| `FileTransferDescriptor` | `loader_argument` | `u8 *` | `GPTR(unsigned char) loader_argument;` |
| `FileTransferDescriptor` | `phase_callback` | `FileTransferCallback` | `GPTR_FN(FileTransferCallback) phase_callback;` |
| `FileTransferDescriptor` | `callback_data` | `void *` | `GPTR(void) callback_data;` |
| `DisplayObjectStreamState` | `field_4C` | `u8 *` | `GPTR(unsigned char) field_4C;` |
| `DisplayObjectStreamState` | `current` | `u8 *` | `GPTR(unsigned char) current;` |
| `DisplayObjectStreamState` | `base` | `u8 *` | `GPTR(unsigned char) base;` |

14/15 dùng `GPTR` (quy tắc chung), 1/15 dùng `GPTR_FN` (6.7%, dưới ngưỡng 30%).

## Kiểm chứng idempotent

```sh
python3 tools/pc/lp64/codemod.py                              # round 1
# chạy lại trên chính output round 1, ghi ra thư mục khác để so sánh:
python3 -c "
import sys; sys.path.insert(0, 'tools/pc/lp64'); import codemod
codemod.setup_libclang()
codemod.transform_file('tmp/lp64/src/ygo_types.h', 'tmp/lp64/src-round2/ygo_types.h', 'src')
"
diff tmp/lp64/src/ygo_types.h tmp/lp64/src-round2/ygo_types.h   # rỗng
```
Kết quả: **rỗng** — round 2 tạo ra output byte-identical với round 1. Đạt.
Lý do kỹ thuật: `GPTR`/`GPTR_FN` không định nghĩa `MEMORIES_LP64` lúc codemod
tự parse, nên chúng expand về `T *`/`T` (nhánh không-LP64) — field đã
codemod ở vòng 1 nhìn giống hệt field gốc ở cấp AST (cùng là con trỏ/cùng là
typedef con trỏ), nên vòng 2 tạo lại đúng cùng text.

## Kiểm chứng layout (i386 gốc vs arm64+LP64 trên output codemod)

```sh
# i386 gốc (retail-matching), trên src/ygo_types.h chưa đổi:
clang --target=i386-pc-linux-gnu -std=gnu11 -DMEMORIES_PC -D_LANGUAGE_C -DLANGUAGE_C -Isrc \
  -fsyntax-only -w -Xclang -fdump-record-layouts-complete -Xclang -fdump-record-layouts-simple \
  -include src/ygo_types.h -x c /dev/null > layout-i386.txt

# arm64 + MEMORIES_LP64, trên output codemod tmp/lp64/src/ygo_types.h:
clang --target=arm64-apple-macos -std=gnu11 -DMEMORIES_PC -D_LANGUAGE_C -DLANGUAGE_C \
  -DMEMORIES_LP64 -Isrc -fsyntax-only -w -ferror-limit=0 \
  -Xclang -fdump-record-layouts-complete -Xclang -fdump-record-layouts-simple \
  -include src/pc/guest/gptr.h -include tmp/lp64/src/ygo_types.h -x c /dev/null > layout-arm64-lp64.txt
```
Cách trích/so sánh: giống `tools/pc/check_layouts.py` — parse khối
`*** Dumping AST Record Layout` / dòng `Type: ...`, so từng struct bằng tên
(struct có tag như `DuelEffectChannel`) hoặc bằng vị trí `(unnamed at
file:line:col)` cho struct ẩn danh (`typedef struct { ... } Name;`) — 3/5
struct mục tiêu là dạng ẩn danh này. Vì codemod chỉ thay text trong 1 dòng
cho mỗi field (không thêm/bớt dòng), số dòng file không đổi, nên vị trí
`line:col` của struct ẩn danh giữ nguyên giữa bản gốc và bản codemod, so
sánh được trực tiếp.

**Kết quả — cả 5 struct đều khớp tuyệt đối** (layout text, tức Size/
DataSize/Alignment/FieldOffsets, giống hệt byte-for-byte giữa 2 phía):

| Struct | Size (bit) | Khớp? |
|---|---|---|
| `TextStreamOwner` | 0x58 | ✅ |
| `LibraryMotionState` | 0x48 | ✅ |
| `DuelEffectChannel` | 0x64 (800 bit) | ✅ |
| `FileTransferDescriptor` | 0x48 | ✅ |
| `DisplayObjectStreamState` | 0x5C | ✅ |

(Size khớp đúng với các assert `X_size_must_be_0xNN` đã có sẵn trong
`ygo_types.h` — ví dụ `DuelEffectChannel`: dump ra 800 bit = 100 byte =
0x64, đúng `DuelEffectChannel_size_must_be_0x64`.)

## Sai lầm đã sửa trong lúc làm (đáng ghi lại cho M1)

1. **Regex tay để tìm struct có field con trỏ bị sai** vì struct lồng nhau
   (ví dụ union chứa struct ẩn danh bên trong) làm lệch việc ghép thân struct
   với tên struct cho mọi struct sau điểm lồng đầu tiên. Chuyển sang dùng
   libclang thật (chính công cụ codemod sẽ dùng) để dò — vừa đúng, vừa là
   phép thử sớm cho môi trường libclang trước khi viết codemod.
2. **`field.type.kind` không báo `TypeKind.TYPEDEF`** cho field khai báo qua
   typedef (báo `TypeKind.ELABORATED` thay vào đó) — phải dùng
   `field.type.get_declaration().kind == CursorKind.TYPEDEF_DECL` mới phát
   hiện đúng. Đây là bẫy cụ thể của libclang Python binding, không phải lỗi
   thiết kế — ghi lại để M1 không vấp lại.
3. **`-ferror-limit` mặc định (20)** chặn ngang việc parse `ygo_types.h`
   trước khi tới struct ở cuối file (nhiều struct KHÔNG nằm trong 5 mục tiêu
   vẫn còn lỗi LP64 offset assert do chưa được codemod, đúng như T0.5 đã đo)
   — thêm `-ferror-limit=0` vào cả codemod lẫn bước dump layout để libclang
   parse hết file bất kể AST phía sau vẫn còn lỗi ở phần chưa động tới.

## Ý nghĩa cho Gate G0

Milestone đặt ngưỡng: nếu codemod cần override tay trên 30% số chỗ dùng,
cân nhắc lại ADR-05. Số liệu thực tế: **1/15 field (6.7%)** cần một macro
biến thể (`GPTR_FN`) — không phải override tay ngoại lệ, mà là một quy tắc
tổng quát hoá thêm (áp dụng lại được cho mọi field cùng dạng "khai báo qua
typedef con trỏ", không phải sửa từng chỗ một). Layout khớp tuyệt đối trên
cả 5 struct, codemod idempotent. Không phát hiện gì cho thấy ADR-05 cần đổi
hướng.

**Đề xuất (fen quyết định ở Gate G0):** đủ cơ sở để đi tiếp M1 theo đúng lộ
trình đã vạch, với ghi chú bổ sung `GPTR_FN` vào bộ macro chuẩn.
