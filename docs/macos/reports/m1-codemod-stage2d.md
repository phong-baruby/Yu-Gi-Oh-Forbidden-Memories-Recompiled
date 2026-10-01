# M1 — Codemod giai đoạn 2, batch d: func_800[4-9]* (T1.4d)

**Kết quả: 61/64 file đạt acceptance. 3 file loại khỏi tiêu chí, cùng nguyên nhân ADR-03/T1.5 đã
biết từ T1.4c (`ordering_tables.h`'s `D_800E9D90[4]`, global con trỏ host thật).**

**Lệnh:**
```sh
python3 tools/pc/lp64/codemod.py                 # mở rộng CODE_GLOBS/EXPR_GLOBS += game/func_800[4-9]*.c
python3 tools/pc/lp64/check_layouts_lp64.py       # vẫn 0 khác biệt
```

## Tách khỏi milestone gốc trước khi làm

Milestone gốc gộp T1.4d = `func_800[4-9]*` (64 file) **+ phần còn lại của `src/game`** (352 file đặt
tên theo hàm) = 416 file — hơn 5 lần T1.4c (78 file, vốn đã cần một phiên rất dài). Fen duyệt tách:
phiên này chỉ làm 64 file `func_800[4-9]*`; 352 file còn lại chuyển sang **T1.4f** (file milestone đã
cập nhật), đo quy mô thật khi tới lượt.

## 3 bug thật mới trong bộ phân loại (cộng dồn lên 7, tính từ T1.4b)

1. **`classify_write` tự tạo edit lồng nhau, splice chồng lên nhau, sinh text hỏng.**
   `base->entries = (u8 *)GsMapCoordUnit((u32 *)hmd, (u32 *)ev.ptr);` — RHS cần bọc `H2G` (toàn bộ),
   nhưng bên trong nó `ev.ptr` **cũng** là field `gaddr` cần `G2H` riêng — hai edit lồng nhau, splice
   độc lập cho ra `H2G(GsMapCoordUnit(...ev.ptr))ptr));` (rác ở cuối). Sửa: thêm bước kiểm tra edit
   lồng nhau **trước khi splice**, dừng hẳn (`sys.exit`) nếu phát hiện thay vì liều áp dụng — rồi xử
   lý điểm duy nhất gặp phải bằng override tay.
2. **Thiếu case tổng quát "field mảng gaddr dùng làm cơ sở truy cập tiếp" (`x.f[i]->g`).** Dạng kết
   hợp subscript + chain mà cả hai case hiện có (subscript-write/read, chain `->`) đều không khớp
   riêng lẻ — bắt được qua compile thật (`slot->field_1E0[k]->rewrite_idx`), sửa bằng override (2
   điểm, 1 file).
3. **Field `gaddr` dùng trực tiếp làm toán hạng `+`/`-` (số học con trỏ), không qua cast/gán.**
   `lim = p->field_DD8 + e->ti;`, `x = q - p->field_DD8;` — field cần xử lý như con trỏ thật (xác
   nhận qua cả comment header lẫn thông báo lỗi compiler), nhưng nằm NGOÀI mọi case hiện có (cast,
   var-decl, call-arg, array, chain) vì cha trực tiếp của nó là chính toán tử `+`/`-`. **Không tổng
   quát hoá**: cùng dạng cú pháp này ở nơi khác (T1.4b/c, họ AiScript_Jump) lại mang ý nghĩa số học
   nguyên thuần tuý, không phải con trỏ — không có quy tắc cú pháp nào phân biệt an toàn hai trường
   hợp mà không có rủi ro áp `G2H` sai chỗ (hướng nguy hiểm, sai thầm lặng) — xử lý từng điểm bằng
   override sau khi tự xác minh ngữ nghĩa qua header.

## 1 case được tổng quát hoá thành công — khác 2 case trên

**Field `gaddr` dùng làm cơ sở cho `->` tiếp theo** (`object->record->field_30`, đã vá tay ở T1.4c)
**lần này tổng quát hoá được**: kiểm tra thuần văn bản — ký tự ngay sau `extent` của field (biết
chắc bao gồm cả phần cơ sở, ví dụ `s->object` chứ không chỉ `object`) có phải `->` không — độc lập
hoàn toàn với cấu trúc AST (vốn luôn suy biến ở dạng này). Thay thế 1 vị trí cho **35 điểm tự động**
trên nhiều file, bao gồm cả những điểm đã vá tay thủ công trước đó trong T1.4c/đầu T1.4d.

**Bug khi tổng quát hoá, bắt được qua đọc diff:** thiếu ngoặc bao ngoài. `->` (hậu tố) bám chặt hơn
phép ép kiểu kiểu C, nên `(T *)G2H(x.f)->g` phân tích thành `(T *)(G2H(x.f)->g)` — áp `->g` lên kết
quả `void *` của `G2H` trước, không phải lên kết quả ép kiểu — sai. Case dereference (`*`) không gặp
vấn đề này vì cả `*` và phép ép kiểu đều là tiền tố, kết hợp phải-sang-trái đúng sẵn mà không cần
ngoặc thêm. Sửa: bọc `((T *)G2H(x.f))` (ngoặc kép) riêng cho case `->`.

## 1 phát hiện giới hạn libclang mới: node AST biến mất hoàn toàn

`g_SDValue->field_043C[(u16)sound_id] == 0xFFFF` — không chỉ suy biến (extent rỗng như các trường
hợp trước), mà clang gộp **toàn bộ điều kiện** thành một `UNEXPOSED_EXPR` duy nhất, không hề có node
con cho `field_043C` — xác nhận bằng cách duyệt mọi cursor tại dòng đó, không node nào mang tên
`field_043C`. Không có cách tổng quát để bắt; xử lý bằng override.

## Xác minh

- `check_layouts_lp64.py`: vẫn `0 differ`.
- `codemod.py` idempotent.
- **61/64 file compile sạch** dưới đúng 3 cờ milestone trên arm64+LP64; 3 file còn lại chặn bởi đúng
  1 nguyên nhân đã biết (ADR-03/T1.5).
- Không hồi quy trên các file đã qua T1.4b (`ai_*`) và T1.4c (`func_800[0-3]*`) — biên dịch lại toàn
  bộ, không file nào phát sinh lỗi mới ngoài 11 file đã biết từ T1.4c.
- `ctest` (cấu hình mặc định): 30/59 fail — khớp baseline T0.4.

## Số liệu cuối

| | |
|---|---|
| File trong scope | 64 (`game/func_800[4-9]*.c`) |
| File có điểm GPTR thật | 17 |
| Điểm ADR-05 (2)/(4) sửa (AST, bao gồm case `->` mới tổng quát hoá) | 132 |
| Điểm sửa qua override | ~20 (macro-argument, số học con trỏ, mảng+chain kết hợp, node AST biến mất) |
| Bug thật trong bộ phân loại (T1.4d) | 3 (cộng dồn từ T1.4b: 7) |
| Case tổng quát hoá thành công | 1 (field gaddr làm cơ sở `->`, thay ~35 điểm) |
| File loại trừ — ADR-03/T1.5 (như T1.4c) | 3 |
| File compile sạch / tổng | 61/64 |
| Hồi quy layout (T1.3) | 0 |
| Hồi quy T1.4b/T1.4c | 0 |
| Hồi quy ctest baseline | 0 |
