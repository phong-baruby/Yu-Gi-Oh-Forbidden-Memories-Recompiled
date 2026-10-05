# M1 — Codemod giai đoạn 2, batch i: src/game chunk 4/5 (T1.4i) + sửa lỗi quy trình xác minh

**Kết quả T1.4i: 48/71 file đạt acceptance.** 4 file loại trừ nhóm "con trỏ-đôi native stride" (đã biết
từ T1.4h), 19 file loại trừ nhóm "con trỏ host thật bị ép xuống s32/u32" (đã biết từ T1.4e).

**Phát hiện phụ quan trọng hơn cả T1.4i: lệnh compile-check dùng để xác minh "compile sạch" từ T1.4f có
lỗi, khiến số liệu đã báo cáo/commit cho T1.4f (61/71), T1.4g (57/71), T1.4h (64/71) đều sai — số đúng
lần lượt là 50/71, 50/71, 52/71. Đã sửa lại.**

## Phần 1 — Lỗi trong quy trình xác minh (ảnh hưởng ngược T1.4f/g/h)

### Phát hiện

Lệnh compile-check dùng từ T1.4f (xem `m1-codemod-stage2f.md`):
```sh
clang --target=arm64-apple-macos -std=gnu11 -DMEMORIES_PC -D_LANGUAGE_C -DLANGUAGE_C -DMEMORIES_LP64 \
  -Werror=int-conversion -Werror=pointer-to-int-cast -Werror=int-to-pointer-cast \
  -fsyntax-only -w -Itmp/lp64/src -Isrc -include src/pc/guest/gptr.h <file>
```
Cờ `-w` (thêm vào để lọc bớt warning không liên quan trong output, ví dụ `-Wgnu-folding-constant` từ
`fix_offsetof_casts`) **vô hiệu hoá luôn `-Werror=pointer-to-int-cast` và `-Werror=int-to-pointer-cast`**
— xác nhận bằng so sánh trực tiếp cùng 1 file, cùng mọi cờ khác, chỉ thêm/bớt `-w`:
```sh
# Có -w: 3 lỗi (chỉ -Wint-conversion còn tác dụng)
# Không -w: 4 lỗi (đủ cả 3 cờ, thêm 1 lỗi -Wint-to-pointer-cast bị -w nuốt mất)
```
Thử cả hai thứ tự đặt cờ (`-w` trước hay sau `-Werror=...`) đều cho cùng kết quả sai — không phải vấn đề
thứ tự, `-w` luôn thắng cho 2 cờ này bất kể vị trí. Chỉ `-Werror=int-conversion` không bị ảnh hưởng (có
vẻ clang coi một số dạng "incompatible pointer/integer conversion" là lỗi mặc định theo chuẩn C, không
phải warning tùy chọn, nên miễn nhiễm với `-w`).

**Sửa:** bỏ hẳn `-w` khỏi lệnh compile-check, lọc output bằng `grep "error:"` (warning không khớp pattern
này nên không nhiễu). Dùng lệnh này cho mọi xác minh từ đây về sau.

### Quét lại toàn bộ

Quét lại 447 file `CODE_GLOBS` (T1.4a-i) bằng lệnh đã sửa: **126 lỗi, thay vì ~46 đã báo cáo trước đó.**
Hỏi fen qua `AskUserQuestion` 2 câu trước khi xử lý: (1) 48 file lỗi mới (ngoài 44 file ADR-03/04 đã
biết) xử lý sao — fen chọn "phân loại từng file: sửa nếu an toàn/rõ ràng, gộp phần còn lại vào nhóm đã
biết"; (2) có sửa lại số liệu đã commit của T1.4f/g/h không — fen chọn "có, sửa ngay".

### Phân loại 48 file lỗi mới

Đọc lỗi đầu tiên của cả 48 file: **toàn bộ đều khớp đúng nhóm "con trỏ host thật bị ép xuống s32/u32 qua
biến cục bộ/toàn cục rồi ép ngược"** đã ghi nhận từ T1.4e (`docs/macos/ARCHITECTURE.md`'s ADR-05, mục
ngay sau mục 9) — dạng `cast to smaller integer type 'X' from 'Y *'` / `cast to 'Y *' from smaller
integer type 'X'`, với Y là một kiểu con trỏ host thật (`DisplayObject *`, `u8 *`, function pointer,
...), không phải field gaddr. Không file nào thuộc nhóm khác. Theo đúng lý do T1.4e đã nêu, nhóm này
**không có cách sửa an toàn bằng override**: đây là con trỏ host THẬT, khác offsetof-qua-NULL (ADR-05
mục 9, nơi `(uintptr_t)` luôn an toàn vì giá trị luôn nhỏ/base NULL) — bọc `(uintptr_t)` ở đây sẽ ẩn đi
việc cắt cụt bit cao thật của một con trỏ 8-byte, một lỗi bộ nhớ thật lúc chạy, không chỉ lỗi compile.

Phân theo batch (file đầy đủ liệt kê trong `PROGRESS.md`'s "Vấn đề mở"):

| Batch | Tổng | ADR-03/04 (không đổi) | Pointer-stride | Con trỏ-ép-s32 (mới đo) | Compile sạch thật |
|---|---|---|---|---|---|
| T1.4f | 71 | 10 | 0 | 11 | **50** (không phải 61) |
| T1.4g | 71 | 14 | 0 | 7 | **50** (không phải 57) |
| T1.4h | 71 | 6 | 1 | 12 | **52** (không phải 64) |
| T1.4i | 71 | 0 | 4 | 19 | **48** |

### Sửa báo cáo cũ

Thêm ghi chú sửa lại ở đầu `m1-codemod-stage2f.md`, `m1-codemod-stage2g.md`, `m1-codemod-stage2h.md`
(không viết lại toàn bộ report — giữ nguyên làm hồ sơ tại thời điểm đo, chỉ trỏ tới số liệu đúng — đúng
cách T1.4e đã làm với `m1-codemod-stage2a/b/c/d.md` khi gặp tình huống tương tự).

## Phần 2 — T1.4i tự thân

### Kiểm chứng giả định

Boundary 71 file (`model_effect_coefficient_table.c` → `script_op_save_prompt.c`) khớp milestone.
Trước khi duyệt, đã báo fen: batch chứa đúng 3 file nghi vấn pointer-stride nêu tên ở T1.4h
(`model_load_step.c`, `model_slot_setup.c`, `model_slot_updates.c`) — fen chọn vẫn loại trừ + ghi nhận,
không đào sâu ADR giữa batch.

### Pattern mới cho `transform_c_expressions`/override

1. **Offsetof-via-macro nhắm vào field con trỏ, bên trong file `.c`** (`model_slot_updates.c`):
   `MODEL_UNIT_OFFSET(super)` (macro cục bộ `#define MODEL_UNIT_OFFSET(member) ((u32)&(((GsCOORDUNIT
   *)0)->member))`) — `fix_offsetof_casts` (ADR-05 mục 9) đã tự sửa đúng trên dòng ĐỊNH NGHĨA macro
   (text thuần), nhưng AST walk của `transform_c_expressions` vẫn duyệt riêng field `super` (gaddr, vì
   là con trỏ) qua LỜI GỌI macro và không đặt được edit (degenerate extent) — hai pass độc lập, pass
   AST không biết pass text đã xử lý macro definition. Lần đầu gặp offsetof-qua-macro nhắm field CON TRỎ
   trong `.c` (mọi lần trước đều ở header, nơi `transform_c_expressions` không chạy).
2. **Macro 1 tham số riêng của file, không phải macro `_VIEW` chuẩn** (`library_runtime.c`'s
   `W(p,o)`/`H(p,o)`): cùng lớp macro-argument degenerate extent đã biết, chỉ khác hình dạng macro.
3. **Macro đọc `.field` của tham số thay vì cast thẳng tham số** (`script_image_rebuild.c`'s
   `SCRIPT_IMAGE_ENTRY_OBJECT(entry) ((DisplayObject *)(entry).pointer)`) — lớp macro-argument hazard
   mới (mọi macro trước chỉ cast thẳng, không có field access thêm bên trong).
4. **Field gaddr làm chain base sau subscript, lặp lại ở field TRUE ARRAY** (`model_scene_setup.c`,
   `model_slot_row_tables.c`'s `field_1E0[i]->...`) — cùng lớp gap đã biết từ T1.4g/h (case
   `ARRAY_SUBSCRIPT_EXPR` không nhận diện chain `->` tiếp theo), lần này trên field THẬT SỰ là mảng
   (khác T1.4g's field vô hướng dùng sai cú pháp mảng).
5. **Field con trỏ vô hướng dùng kiểu mảng, lặp lại nhiều lần trong 1 file**
   (`model_slot_row_tables.c`'s `field_DD8`, 5 điểm subscript + 3 điểm trừ con trỏ bare operand;
   `model_interpolate_transform.c`'s `output`) — cùng lớp đã biết T1.4g-i.
6. **`NULL` hệ thống (`(void *)0`) khác `NULL` của psyq (`0`) gán vào field gaddr**
   (`model_update_view_metrics.c:128`): file không include `psyq/stddef.h`, `NULL` rơi về định nghĩa
   SDK hệ thống (`(void*)0`, một hằng con trỏ thật) thay vì literal `0` — `classify_write`'s nhánh cast
   lẽ ra xử lý được NHƯNG macro NULL che mất cấu trúc cast khỏi AST giống mọi macro khác. Sửa bằng thay
   literal `0` (tương đương giá trị, universal trên mọi nền tảng).
7. **`model_slot_properties.c`'s `GsUNIT.primtop` — ban đầu tưởng là 1 nhóm bất định riêng ("đọc giá trị
   gaddr lồng 2 tầng từ dữ liệu TMD"), hoá ra cùng gốc với nhóm con-trỏ-ép-xuống-s32 một khi đo đúng**:
   dòng gây lỗi KHÁC (`(s32)p->field_000 + ...` ở dòng trước) chứ không phải `primtop` — không cần phân
   loại riêng, không cần hỏi fen thêm về nhóm này.

Không pattern nào trong 6 pattern đầu được tổng quát hoá vào classifier (mỗi cái 1-9 lần, 1-2 file).

### 4 file loại trừ — nhóm pointer-stride (đã biết từ T1.4h, không đào sâu)

`model_load_step.c`, `model_slot_setup.c`, `model_slot_updates.c` — xác nhận cùng field `field_1E0`
(`ModelSlotPart **x = slot->field_1E0;` rồi `x++`). `model_subdivided_effect.c` — field KHÁC
(`vertex_links[24]`/`color_links[24]`, cùng idiom: `SVECTOR **vertices = effect->vertex_links;` rồi
`vertices++`/`*vertices = ...`). Không sửa, không đào sâu — theo đúng quyết định đã chốt ở T1.4h.

## Xác minh

- `check_layouts_lp64.py`: `0 differ`.
- `codemod.py` idempotent — xác nhận bằng `rm -rf` trước MỖI lần chạy (phát hiện phụ: so 2 lần chạy mà
  không `rm -rf` giữa chừng — "warm rerun" — từng cho khác biệt trên 1 file ngoài scope T1.4i
  (`func_8001B938.c`), không điều tra sâu nguyên nhân; 4 lần chạy fresh liên tiếp đều nhất quán. Từ nay
  luôn `rm -rf tmp/lp64` trước mỗi lần so sánh idempotent).
- **Sweep toàn bộ 447 file `CODE_GLOBS`**: ổn định ở đúng 126 lỗi qua nhiều lần chạy lại (đã tính hết
  ADR-03/04 + pointer-stride + con-trỏ-ép-s32, không có gì ngoài dự kiến).
- `ctest` (cấu hình mặc định): 30/59 fail — khớp baseline T0.4, không đổi.
- Đọc trực tiếp diff của mọi file có override (kể cả 2 pattern mới phức tạp nhất — offsetof-qua-macro,
  macro đọc field của tham số) — khớp đúng ý, không text rác.

## Số liệu cuối

| | |
|---|---|
| File trong scope T1.4i (`model_effect_coefficient_table.c` → `script_op_save_prompt.c`) | 71 |
| File bị codemod/override thay đổi thật | 30 |
| Khối override thêm (toml, T1.4i) | 14 |
| Pattern mới cho `transform_c_expressions` (T1.4i, không tổng quát hoá) | 6 |
| File compile sạch / tổng (T1.4i) | 48/71 |
| File loại trừ — pointer-stride (T1.4i) | 4 |
| File loại trừ — con trỏ-ép-s32 (T1.4i) | 19 |
| **Sửa lại T1.4f** | 61/71 → **50/71** |
| **Sửa lại T1.4g** | 57/71 → **50/71** |
| **Sửa lại T1.4h** | 64/71 → **52/71** |
| Tổng lỗi thật qua sweep 447 file (T1.4a-i) | 126 (44 ADR-03/04 + 5 pointer-stride + 77 con-trỏ-ép-s32) |
| Hồi quy layout (T1.3) | 0 |
| Hồi quy ctest baseline | 0 |
