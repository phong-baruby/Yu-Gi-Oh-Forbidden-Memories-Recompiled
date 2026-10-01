# M1 — Codemod giai đoạn 2, batch c: func_800[0-3]* (T1.4c)

**Kết quả: 67/78 file đạt acceptance. 11 file loại khỏi tiêu chí, có lý do cụ thể, đã fen xác nhận
hai lần (lúc phát hiện `phase_callback` và lại khi quy mô loại trừ tăng lên 11 file).**

**Lệnh:**
```sh
python3 tools/pc/lp64/codemod.py                 # mở rộng CODE_GLOBS/EXPR_GLOBS += game/func_800[0-3]*.c
python3 tools/pc/lp64/check_layouts_lp64.py       # vẫn 0 khác biệt
```

## Quy mô đo được

78 file; 37 có điểm GPTR thật; đo tổng 107 điểm. Bộ phân loại kế thừa từ T1.4b xử lý được phần lớn,
nhưng batch này đa dạng hơn hẳn T1.4b (không phải một VM lặp một idiom) — buộc sửa **4 bug thật
trong chính bộ phân loại** (không phải chỉ thêm case mới) và phát hiện **2 nhóm bị chặn bởi hạ tầng
chưa tồn tại** (T1.5, T1.6), cả hai đều đã hỏi và được fen duyệt loại khỏi batch này.

## 4 bug tự vấp phải trong bộ phân loại kế thừa từ T1.4b — đáng đọc trước khi làm T1.4d

1. **`classify_write` thiếu guard cho extent suy biến của chính RHS nó xử lý.** T1.4b chỉ guard
   extent suy biến ở field đang được phân loại (field cha); không guard khi RHS của một phép GHI
   cũng đi qua macro (`field = SOME_VIEW_MACRO(ptr);`). Bắt được qua đọc diff (không phải compile):
   sinh ra `field = H2G();` — macro bị bỏ trống hoàn toàn. Sửa: thêm guard tương tự ngay trong
   `classify_write`, nhận `context` để báo lỗi rõ ràng.
2. **Thứ tự kiểm tra sai: nhánh "đọc gán thẳng" (mới thêm cho T1.4c) chặn trước nhánh dereference
   đã có từ T1.4b.** `skip_transparent` coi `UNEXPOSED_EXPR` là lớp bọc trong suốt để bỏ qua — đúng
   trong đa số trường hợp, nhưng SAI khi chính `UNEXPOSED_EXPR` đó là dạng suy biến của một phép
   dereference thật (`*x.f`, xem `wraps_dereference`). Đặt nhánh "đọc gán thẳng" trước nhánh
   dereference (dùng `parent` đã bỏ qua lớp bọc) khiến `*row.words` bị nhận nhầm là "x.f được gán
   thẳng vào `val`" thay vì "dereference". Sửa: chuyển kiểm tra dereference (dùng `raw_parent`, một
   bước, không qua `skip_transparent`) lên **đầu tiên**, trước mọi nhánh dùng `parent`.
3. **`is_gaddr_type` không nhận diện field KIỂU MẢNG** (`GPTR(T) f[N]` → `gaddr f[N]`, kiểu báo
   `"gaddr[8]"` chứ không phải `"gaddr"` trần). Bộ lọc đầu vào bỏ sót hoàn toàn mọi field dạng mảng
   con trỏ guest khi dùng qua chỉ số (`arr->slots[i] = ptr;`) — không sinh edit nào, không báo lỗi,
   chỉ lộ ra khi compile thật (`-Wint-conversion`). Sửa: kiểm phần tử mảng khi `t.kind` là
   `CONSTANTARRAY`/`INCOMPLETEARRAY`.
4. **`CSTYLE_CAST_EXPR.get_children()` thứ tự con** (đã biết từ T1.4a, nhắc lại ở đây vì liên quan):
   không phải bug mới, nhưng `classify_write`'s cast-operand logic dựa đúng vào thứ tự này.

## 2 phát hiện bị chặn bởi hạ tầng chưa có (T1.5, T1.6) — đã hỏi fen, được duyệt loại khỏi batch

- **Toàn cục con trỏ thật (ADR-03, T1.5)**: `ordering_tables.h`'s `extern GsOT *D_800E9D90[4];` và
  `display_object_work_slots.h`'s `sizeof(DisplayObject *) * 5 == 0x14` — cả hai là **global**
  (không phải field trong struct), mảng con trỏ host thật, `sizeof` tăng gấp đôi dưới con trỏ 8-byte
  arm64. Đây đúng là việc T1.5 làm ("Codemod biến `extern T gFoo;` thành lvalue macro qua `G2H`") —
  ngoài phạm vi ADR-05 (2)/(3)/(4) của T1.4. **9 file** transitively include 1 trong 2 header này.
- **Lưu/gọi con trỏ hàm native vào field guest (ADR-04, T1.6)**: `p->phase_callback(p, ...)` (gọi
  qua field guest — mục 6) và `obj->update = (DisplayObjectCallback)fnv;` (lưu một con trỏ hàm NATIVE
  vào field guest để gọi lại sau — cùng họ GCALL, hướng ngược lại). `H2G` không áp dụng được cho địa
  chỉ MÃ (không nằm trong `g_ram`/`g_scratch`); cần dải địa chỉ tổng hợp `0x9F000000+` ADR-04 mô tả,
  chưa xây. **3 file** (1 trùng với nhóm trên).

Tổng cộng (loại trùng): **11/78 file**. Danh sách đầy đủ + lý do từng file trong bảng số liệu cuối.

## Xác minh

- `check_layouts_lp64.py`: vẫn `0 differ`.
- `codemod.py` idempotent (đã kiểm riêng, loại trừ symlink `tmp/lp64/src/pc` chỉ dùng cho việc
  compile-verify cục bộ — không phải phần codemod, không commit).
- **67/78 file compile sạch** dưới `arm64-apple-macos -DMEMORIES_LP64` với đúng 3 cờ milestone.
- `ctest` (cấu hình mặc định): 30/59 fail — khớp baseline T0.4, không hồi quy.

## Số liệu cuối

| | |
|---|---|
| File trong scope | 78 |
| File có điểm GPTR thật | 37 |
| Điểm ADR-05 (2)/(4) sửa (AST) | 66 |
| Điểm sửa qua override (giới hạn libclang: macro-argument, chuỗi 2 tầng) | 15 |
| Bug tự vấp phải trong bộ phân loại (kế thừa T1.4b) | 4 |
| File loại trừ — ADR-03/T1.5 (global con trỏ) | 9 |
| File loại trừ — ADR-04/T1.6 (GCALL) | 3 (1 trùng nhóm trên) |
| File loại trừ — tổng (không trùng) | 11 |
| File compile sạch / tổng | 67/78 |
| Hồi quy layout (T1.3) | 0 |
| Hồi quy ctest baseline | 0 |
