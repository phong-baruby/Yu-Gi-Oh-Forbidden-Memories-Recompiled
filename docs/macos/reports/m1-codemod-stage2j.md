# M1 — Codemod giai đoạn 2, batch j: src/game chunk 5/5 (T1.4j, batch cuối)

**Kết quả: 60/68 file đạt acceptance.** 1 file loại trừ ADR-04 (đã biết), 5 file loại trừ nhóm
"con trỏ host thật bị ép xuống s32/u32" (đã biết từ T1.4e), 2 file loại trừ nhóm MỚI "giải mã 2 tầng
không chắc chắn" (giống `model_slot_properties.c`'s `primtop` ở T1.4i).

**Đây là batch cuối cùng của T1.4** — sau batch này, toàn bộ `src/game/*.c` (546 file, trừ `src/overlays`
dời sang M3) đã qua codemod giai đoạn 2.

## Kiểm chứng giả định

Boundary 68 file (`script_op_show_dialog.c` → `widget_update_pulse_colour.c`) khớp milestone.

## Phát hiện phương pháp quan trọng: phân biệt 2 lớp lỗi trông giống hệt nhau

Batch này có rất nhiều lỗi dạng `cast to smaller integer type 'X' from 'Y *'` /
`cast to 'Y *' from smaller integer type 'X'` — cùng DẠNG THÔNG BÁO như nhóm "con trỏ host thật bị ép
xuống s32/u32" đã biết từ T1.4e. Ban đầu định xếp tất cả vào nhóm đó (loại trừ, không sửa) như T1.4i đã
làm với 48 file. Đọc kỹ từng trường hợp lộ ra **2 lớp hoàn toàn khác nhau** đằng sau cùng 1 dạng thông báo:

1. **Con trỏ host THẬT bị cắt cụt** (nhóm T1.4e gốc, không có cách sửa an toàn): nguồn của phép ép kiểu
   là một global/local THẬT (`extern u16 D_801C0000[];`, một biến stack cục bộ, một tham số con trỏ host
   thật) — không liên quan field GPTR nào cả. Ép `(uintptr_t)` sẽ ẩn mất việc mất bit cao thật.
2. **Giá trị gaddr (từ field GPTR, hoặc hằng địa chỉ guest trần) bị tính toán rồi QUÊN bọc G2H trước khi
   ép kiểu con trỏ cuối cùng** (lớp MỚI, an toàn để sửa): nguồn là MỘT FIELD GPTR (đã là `gaddr`/`uint32_t`
   sau transform) hoặc một hằng số địa chỉ guest trần (`0x801E7800`, vùng KSEG0) — phép tính chỉ là số học
   guest-address thuần tuý, bản thân không mất thông tin gì; lỗi chỉ là **thiếu đúng 1 lệnh `G2H()`** ở
   bước ép kiểu cuối cùng thành con trỏ thật. Khác hẳn lớp 1 — sửa đúng, an toàn, không đoán.

**Cách phân biệt thực hiện**: đọc khai báo của biến/field ở gốc biểu thức. Field GPTR → lớp 2 (sửa được).
Global/local khai báo kiểu con trỏ thật, không qua `GPTR(T)` → lớp 1 (loại trừ). Việc này áp dụng cho
**10 file trong batch này** (9 override mới dạng "bare arithmetic/literal-address rồi ép kiểu, thiếu G2H"
— xem danh sách dưới) — không file nào trong 10 file đó thực ra thuộc lớp 1.

**Lưu ý cho các batch trước**: T1.4f-i chỉ đọc DÒNG LỖI ĐẦU TIÊN của mỗi file khi phân loại 48+ file vào
nhóm T1.4e (do khối lượng lớn, dùng suy luận nhanh dựa trên dạng thông báo) — CÓ RỦI RO đã lẫn vài trường
hợp lớp 2 (sửa được) vào nhóm loại trừ lớp 1 (không sửa) mà không phát hiện ra. Không có thời gian rà lại
toàn bộ 48 file trong phiên này; ghi nhận làm rủi ro cần kiểm tra lại, không giả định kết luận.

## Override mới (9 cái, lớp 2 ở trên) — ngoài các pattern scalar-as-array/chain-base đã quen thuộc

- `sound_find_midi_track_chunk.c`: field gaddr bare `+` operand làm đối số hàm, thiếu G2H.
- `sd_queue_value_link_transfer.c` (×2): field gaddr bare `+`/biến cục bộ giữ giá trị gaddr, ép kiểu con
  trỏ cuối thiếu G2H.
- `sound_effect_request.c` (×2): tương tự, 2 biến cơ sở khác nhau (`a`, `b`).
- `sound_voice_data.c` (×3): 2 cái dùng HẰNG SỐ ĐỊA CHỈ GUEST TRẦN (`0x801E7800`, không qua field nào —
  cơ chế quét field của codemod không có gì để bắt vào) + 1 cái offsetof-via-NULL cộng field gaddr.

## 2 file loại trừ — nhóm MỚI "giải mã 2 tầng không chắc chắn" (giống `model_slot_properties.c`, T1.4i)

- **`sound_output_state.c`**: `table = (u8 **)a->bank_0518[1];` (field GPTR mảng, sửa an toàn — nhưng
  KHÔNG sửa riêng lẻ vì không đổi kết quả cuối) rồi `first = (s32)*table;` — dereference giá trị đã resolve
  để lấy MỘT GIÁ TRỊ KHÁC, không rõ giá trị đó là con trỏ guest cần G2H lần 2 hay một con số phần cứng SPU
  thuần (bank/voice address format), rồi gán vào trường request gửi cho SPU — cùng lớp bất định như
  `model_slot_properties.c`'s `primtop`, cần hiểu định dạng nhị phân SPU bank thật mới dám sửa.
- **`sound_transfer_lifecycle.c`**: `SD_VabTransBody(s32 value, ...)` — `value` ép thẳng sang `u8 *` mà
  không rõ `value` (tham số, không gọi trực tiếp trong cây nguồn — có thể qua con trỏ hàm/callback) mang
  giá trị gaddr hay dữ liệu khác; không tìm được call site để xác nhận.

Không tự sửa, không đoán — theo đúng nguyên tắc đã dùng cho `model_slot_properties.c`.

## 1 file loại trừ — ADR-04 (đã biết)

`sd_init_state.c`: `sec->field_050C = SD_UpdateVoiceSlots;` — `field_050C` là `GPTR_FN` (hàm callback
native lưu vào field guest, `void (*field_050C)(void)` trong header gốc) — đúng lớp ADR-04/T1.6 đã biết
từ T1.4c (field FN con trỏ, không phải field dữ liệu).

## 5 file loại trừ — nhóm "con trỏ host thật bị ép xuống s32/u32" (xác nhận đúng, đã kiểm tra khai báo gốc)

`text_box_build_step.c`, `text_lookup_string.c` (cùng dùng `extern u16 D_801C0000[]` — global thật,
không GPTR); `text_init_decimal_digit_glyph_map.c` (biến stack cục bộ `buf.bytes` decay pointer thật);
`text_box_layout_helpers.c` (`field_4C` là `s32` TRẦN, không phải GPTR — lưu địa chỉ hàm native vào field
dữ liệu thường, không phải GPTR_FN, nên không phải ADR-04 mà là chính nhóm cắt-cụt-con-trỏ-thật này);
`text_control_commands.c` (tham số `object`/`arg0` kiểu `DuelEffectChannel *` — con trỏ host thật — bị
ép `(u32)object` trực tiếp để tính offset; cũng có 4 điểm khác CÓ THỂ sửa được trong cùng file — dereference-
postinc quen thuộc, nested read-write qua `Text_Retarget` — nhưng không sửa vì file vẫn bị loại bởi lỗi
không sửa được ở trên, không đáng công đọc kỹ thêm).

## Xác minh

- `check_layouts_lp64.py`: `0 differ`.
- `codemod.py` idempotent (fresh `rm -rf` trước mỗi lần).
- **60/68 file compile sạch**.
- **Sweep toàn bộ 515 file `CODE_GLOBS`** (toàn bộ `src/game` trừ overlays, cộng `ai_*`/`func_800*`/
  `psyq`): đúng 134 lỗi = 126 đã biết (T1.4a-i) + 8 mới (T1.4j) — 0 hồi quy ngoài dự kiến.
- `ctest`: 30/59 fail — khớp baseline T0.4.
- Đọc trực tiếp diff mọi override — khớp đúng ý.

## Tổng kết T1.4 (5 batch src/game, sau khi sửa lại số liệu T1.4f/g/h ở T1.4i)

| Batch | File | Compile sạch | ADR-03/04 | Pointer-stride | Con-trỏ-ép-s32 | Giải-mã-2-tầng-bất-định |
|---|---|---|---|---|---|---|
| T1.4a (SDK) | 13 | 11 | — | — | — | — |
| T1.4b (ai_*) | 20 | 20 | — | — | — | — |
| T1.4c (func_800[0-3]) | 78 | 67 | 11 | — | — | — |
| T1.4d (func_800[4-9]) | 64 | 61 | 3 | — | — | — |
| T1.4e (pc/overrides...) | 6 | 6 | — | — | — | — |
| T1.4f | 71 | 50 | 10 | 0 | 11 | 0 |
| T1.4g | 71 | 50 | 14 | 0 | 7 | 0 |
| T1.4h | 71 | 52 | 6 | 1 | 12 | 0 |
| T1.4i | 71 | 48 | 0 | 4 | 19 | 1 (`model_slot_properties.c`) |
| T1.4j | 68 | 60 | 1 | 0 | 5 | 2 |
| **Tổng `src/game`+SDK** | **533** | **425** | **45** | **5** | **54** | **3** |

(`src/overlays` dời sang M3, chưa tính.)

## Số liệu cuối T1.4j

| | |
|---|---|
| File trong scope T1.4j | 68 |
| File bị codemod/override thay đổi thật | 23 |
| Khối override thêm (toml) | 29 |
| File compile sạch / tổng | 60/68 |
| File loại trừ — ADR-04 | 1 |
| File loại trừ — con-trỏ-ép-s32 (xác nhận đúng) | 5 |
| File loại trừ — giải-mã-2-tầng-bất-định (nhóm mới) | 2 |
| Hồi quy layout (T1.3) | 0 |
| Hồi quy toàn bộ CODE_GLOBS (515 file) | 0 (đúng 134 lỗi = 126 đã biết + 8 mới) |
| Hồi quy ctest baseline | 0 |
