# M1 — Codemod giai đoạn 2, batch h: src/game chunk 3/5 (T1.4h)

> **Sửa lại (2026-10-05, phát hiện ở T1.4i):** con số "64/71" dưới đây SAI, cùng nguyên nhân đã ghi ở
> đầu `m1-codemod-stage2f.md` (lỗi cờ `-w` trong lệnh compile-check). Số liệu đúng: **52/71 file thật sự
> compile sạch**; 6 file ADR-03/04 + 1 file pointer-stride bên dưới vẫn đúng, cộng thêm **12 file khác**
> thuộc nhóm "con trỏ host thật bị ép xuống s32/u32 qua biến cục bộ" (T1.4e): `file_set_position_table.c`,
> `free_duel_load_package_stage.c`, `frontend_package_stages.c`, `game_over.c`, `gpu_packets.c`,
> `input_pads.c`, `library_runtime.c`, `main_boot_load_stages.c`, `main_menu_load_package_stage.c`,
> `main_services.c`, `mem_card_driver.c`, `model_control.c`. Chi tiết:
> `docs/macos/reports/m1-codemod-stage2i.md` và `PROGRESS.md`'s decision log 2026-10-05.

**Kết quả: 64/71 file đạt acceptance. 7 file loại khỏi tiêu chí: 6 khớp ADR-03/ADR-04 đã biết, 1 thuộc
nhóm nguyên nhân MỚI (hỏi fen qua `AskUserQuestion` trước khi quyết định) — con trỏ-đôi native stride đi
bộ qua mảng gaddr, không phải lỗi compile đơn thuần mà là rủi ro bộ nhớ thật nếu ép kiểu cho qua.**

**Lệnh:**
```sh
python3 tools/pc/lp64/codemod.py                 # mở rộng CODE_GLOBS/EXPR_GLOBS += 71 file T1.4h
python3 tools/pc/lp64/check_layouts_lp64.py       # vẫn 0 khác biệt
```

## Kiểm chứng giả định trước khi làm

Boundary 71 file (`duel_update_card_pick_cursor.c` → `model_distance_queries.c`) đo lại bằng script
(loại `ai_*`/`func_800[0-9A-Fa-f]*`/142 file T1.4f+g đã xong khỏi `src/game/*.c`, lấy 71 file tiếp theo
theo alphabet) khớp chính xác với milestone ghi — không có khác biệt.

## Phát hiện mới quan trọng: hazard con trỏ-đôi native stride đi bộ qua mảng gaddr

`model_control_slot_animation.c:37`: `parts = m->field_1E0;` rồi đi bộ bằng `parts++`/`(*parts)->...`
khắp hàm. `field_1E0` là `ModelSlotPart *field_1E0[58]` (`model.h`) — dưới LP64 trở thành `gaddr
field_1E0[58]` (mảng uint32_t 4-byte mỗi phần tử), nhưng `parts` khai báo `ModelSlotPart **parts` — một
con trỏ host thật, stride 8-byte trên arm64. Nếu chỉ ép kiểu cho qua compile (`(ModelSlotPart
**)G2H(m->field_1E0)`), `parts++` sẽ nhảy 8 byte mỗi bước trong khi storage thật chỉ cách nhau 4 byte —
đọc sai hoàn toàn từ phần tử thứ 2 trở đi, không phải lỗi compile mà là lỗi bộ nhớ thật lúc chạy. Khác
hẳn mọi lớp override đã gặp trước đó (đều chỉ cần bọc `G2H`/`H2G` đúng chỗ, không đổi stride).

**Đo nhanh phạm vi trước khi hỏi fen**: `field_1E0` còn được dùng trong ít nhất 9 file khác
(`func_8004DC38.c`, `func_800540B4.c`, `func_800597C8.c`, `model_packet_handlers.c`,
`model_scene_setup.c`, `model_load_step.c`, `model_slot_setup.c`, `model_slot_row_tables.c`,
`model_slot_updates.c`), trong đó **ít nhất 3 file khác** (`model_load_step.c`, `model_slot_setup.c`,
`model_slot_updates.c`) dùng đúng idiom "gán thẳng mảng GPTR vào biến con trỏ-đôi rồi đi bộ" — nhiều khả
năng lan rộng hơn, cần đo đầy đủ trước khi quyết định hướng sửa (có thể là vấn đề ADR-03/T1.5 mới, hoặc
cần một macro/kiểu riêng cho "mảng con trỏ guest được đi bộ kiểu native" không có trong ADR-05 hiện tại).

**Hỏi fen qua `AskUserQuestion`**: 2 lựa chọn — (a) loại trừ file này, ghi nhận, tiếp tục batch theo kế
hoạch gốc (giống cách xử lý ADR-03/04); (b) dừng batch, đào sâu phạm vi toàn bộ ngay. **Fen chọn (a)**.
Không sửa gì ở file này (không thêm override giả tạo cho qua compile) — để nguyên trạng thái "chưa xử
lý" cho tới khi có quyết định ADR. Ghi đầy đủ vào "Vấn đề mở" trong `PROGRESS.md`.

## 3 pattern mới cho `transform_c_expressions`/override (ngoài phát hiện trên), không pattern nào tổng quát hoá

1. **Macro accessor 1 tham số kiểu khác (`W(p, o)`/`H(p, o)` của chính file, không phải `_VIEW` macro)** —
   cùng lớp macro-argument degenerate extent đã biết (T1.4d-g), chỉ khác macro cụ thể:
   `library_runtime.c` tự định nghĩa `W(p,o)`/`H(p,o)`/`S(p,o)`/`B(p,o)` (cast `p` sang `u8 *` rồi đọc
   offset) — `rec->object_04`/`rec->object_00`/`D_800EB0F8[3].field_28` (3 field gaddr khác nhau, 2
   struct khác nhau — `DuelEffectResourceRecord` và `DuelEffectChannel` toàn cục) truyền trực tiếp làm
   tham số `p`, cần `G2H`. 3 override (1 `all=true` cho 2 điểm giống hệt, 2 đơn lẻ).
2. **Macro wrap ở RHS phép gán field gaddr, lần thứ 2 gặp** (`library_runtime.c:791`,
   `LIBRARY_MOTION_STATE_VIEW(r)->render = DISPLAY_OBJECT_VIEW(o);`) — đúng lớp override đã có từ T1.4f/g
   (`func_800323F8.c`), chỉ là điểm gặp mới.
3. **Field con trỏ VÔ HƯỚNG bị subscript kiểu mảng (lần thứ 2 gặp, macro `addPrim`/`getaddr`/`setaddr`
   thay vì truy cập trực tiếp)** (`gpu_packets.c`, 3 điểm giống hệt): `ot->org[index & 0xFFFF]` — `org`
   (`GPTR(GsOT_TAG) org`, scalar, `GsOT`) dùng cú pháp subscript, đơn giản hơn 1 bậc so với override
   `func_80033DB0.c`'s `arg->tagp->org[z]` đã có (không phải chain 2 tầng, `ot` là tham số trực tiếp). Áp
   dụng `all = true`, 1 override.

Không pattern nào trong 3 pattern trên tổng quát hoá vào classifier — mỗi cái chỉ gặp 1-3 lần trong 1-2
file, dưới ngưỡng biện minh mở rộng (nhất quán T1.4b-g).

## 6 file loại khỏi tiêu chí batch khớp ADR-03/ADR-04 đã biết

**ADR-03/T1.5** (global con trỏ host thật trong header, như T1.4c-g): `fade_runtime.c`,
`graphics_frame.c` (`ordering_tables.h`); `main_mode_runners.c` (`display_object_work_slots.h`).

**ADR-04/T1.6** (lưu/gọi con trỏ hàm native qua field guest, như T1.4c-g) — lần này trên
`FileTransferDescriptor.phase_callback` (chính field `GPTR_FN` đã phát hiện từ T0.7!): `file_stream.c`
(`transfer->phase_callback = callback;`, lưu callback thật vào field), `file_transfer_flags.c`,
`file_transfer_runtime.c` (2 điểm, `object->phase_callback(object, count);` — GỌI TRỰC TIẾP field như hàm,
đúng ADR-05 mục (6)/ADR-04 cả hai chiều lưu và gọi).

## Xác minh

- `check_layouts_lp64.py`: `0 differ` (95 record, 586 header).
- `codemod.py` idempotent.
- **64/71 file compile sạch** dưới đúng 3 cờ milestone trên arm64+LP64 (1 file, `model_control_slot_animation.c`,
  cố tình để nguyên "chưa xử lý" theo quyết định của fen, không fake-fix).
- **Sweep hồi quy toàn bộ `CODE_GLOBS` (376 file: 305 cũ + 71 mới)**: đúng 46 lỗi = 39 đã biết từ
  T1.4a-g + 7 mới của T1.4h — **0 hồi quy ngoài dự kiến**.
- `ctest` (cấu hình mặc định): 30/59 fail — khớp baseline T0.4, không đổi.
- Đọc trực tiếp diff của mọi file có override: khớp đúng ý, không text rác.

## Số liệu cuối

| | |
|---|---|
| File trong scope (chunk 3/5, `duel_update_card_pick_cursor.c` → `model_distance_queries.c`) | 71 |
| File bị codemod/override thay đổi thật | 15 |
| Khối override thêm (toml) | 6 |
| Pattern mới cho `transform_c_expressions` (không tổng quát hoá) | 3 |
| Nhóm nguyên nhân loại trừ MỚI phát hiện (hỏi fen) | 1 (con trỏ-đôi native stride đi bộ mảng gaddr) |
| File compile sạch / tổng | 64/71 |
| File loại trừ — ADR-03/T1.5 | 3 |
| File loại trừ — ADR-04/T1.6 | 3 |
| File loại trừ — nhóm mới (chưa xử lý, chờ quyết định ADR) | 1 |
| Hồi quy layout (T1.3) | 0 |
| Hồi quy toàn bộ CODE_GLOBS trước đó (376 file) | 0 (đúng 46 lỗi = 39 đã biết + 7 mới) |
| Hồi quy ctest baseline | 0 |
