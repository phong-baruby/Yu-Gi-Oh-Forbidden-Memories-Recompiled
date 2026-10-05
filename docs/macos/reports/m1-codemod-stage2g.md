# M1 — Codemod giai đoạn 2, batch g: src/game chunk 2/5 (T1.4g)

> **Sửa lại (2026-10-05, phát hiện ở T1.4i):** con số "57/71" dưới đây SAI, cùng nguyên nhân đã ghi ở
> đầu `m1-codemod-stage2f.md` (lỗi cờ `-w` trong lệnh compile-check). Số liệu đúng: **50/71 file thật sự
> compile sạch**; 14 file loại trừ ADR-03/04 bên dưới vẫn đúng, cộng thêm **7 file khác** thuộc nhóm
> "con trỏ host thật bị ép xuống s32/u32 qua biến cục bộ" (T1.4e): `duel_effect_command.c`,
> `duel_effect_resource_setup.c`, `duel_load_package_stage.c`, `duel_request_combined_deck_data.c`,
> `duel_reward_setup.c`, `duel_shuffle_deck.c`, `duel_trap_resolution.c`. Chi tiết:
> `docs/macos/reports/m1-codemod-stage2i.md` và `PROGRESS.md`'s decision log 2026-10-05.

**Kết quả: 57/71 file đạt acceptance. 14 file loại khỏi tiêu chí, đều thuộc 2 nguyên nhân ADR-03/ADR-04
đã biết từ T1.4c-f — không có nguyên nhân mới trong nhóm loại trừ. 4 pattern mới cho
`transform_c_expressions`, cả 4 xử lý bằng override (không tổng quát hoá, quy mô quá nhỏ).**

**Lệnh:**
```sh
python3 tools/pc/lp64/codemod.py                 # mở rộng CODE_GLOBS/EXPR_GLOBS += 71 file T1.4g
python3 tools/pc/lp64/check_layouts_lp64.py       # vẫn 0 khác biệt
```

## Kiểm chứng giả định trước khi làm

Boundary 71 file (`duel_card_turn_animations.c` → `duel_trap_resolution.c`) đo lại bằng script (loại
`ai_*`/`func_800[0-9A-Fa-f]*`/71 file T1.4f khỏi danh sách `src/game/*.c`, lấy 71 file tiếp theo theo
alphabet) khớp chính xác với milestone ghi ở `m1-codemod-stage2f.md` — không có khác biệt.

## 4 pattern mới cho `transform_c_expressions`, không pattern nào tổng quát hoá

1. **Macro-argument degenerate extent (lặp lại nhiều lần, nhiều macro view khác nhau)** — cùng lớp đã
   biết từ T1.4d/e/f (`DISPLAY_OBJECT_VIEW`/`DUEL_CARD_DISPLAY_OBJECT_VIEW`/`DUEL_FIELD_EFFECT_OBJECT_VIEW`/
   `HAND_CARD_OBJECT_VIEW`), chỉ là các điểm gặp mới (biến/trường cơ sở khác): `duel_field_effect_steps.c`
   (`entry->object`), `duel_phase_entry.c` (`rec->object`, lặp 3 lần), `duel_scene_hand_actions.c`
   (`hand->object` lặp 5 lần dưới nhiều ngữ cảnh khác nhau — gán thẳng và chain `->` — cùng 1 override vì
   chỉ cần sửa đúng tham số macro bất kể theo sau là gì; `D_800EA030[n].object`, `card->object`,
   `slot->object`, `hand->child`).
2. **Macro-argument degenerate extent ở RHS của một phép gán field gaddr (không phải đọc field)** —
   `duel_scene_hand_actions.c:139`: `side->cursor_object = DISPLAY_OBJECT_VIEW(obj);` — cùng lớp override
   đã có ở T1.4f (`func_800323F8.c`'s `BUILD_DECK_TRANSITION_STATE_VIEW`), áp dụng y hệt cách sửa (bỏ
   macro vô nghĩa, `H2G` thẳng biến host thật).
3. **Field mảng gaddr bị dereference kèm hậu tố `++`** (`duel_effect_command.c:215`):
   `t = *TEXT_STREAM_OWNER(object)->streams[object->stream_58]++;` — `streams` (`GPTR(u8) streams[22]`,
   `TextStreamOwner`) được index rồi dereference trực tiếp qua `*x++`. `transform_c_expressions` **không
   báo lỗi dừng hẳn cho trường hợp này** — lặng lẽ bỏ qua (không sửa gì), chỉ lộ ra qua compile thật
   (giống đúng lớp lỗ hổng đã ghi nhận ở `classify_write`'s docstring về "found as ... silently dropped,
   while reviewing a diff" — khác ở chỗ lần này không hề có edit nào được tạo ra, không phải edit sai).
   Mọi vị trí `...streams[object->stream_58]` khác trong cùng file đều là `&...` (lấy địa chỉb, không cần
   G2H vì không đổi kiểu `u8 **`/`gaddr *`) hoặc gán gaddr-sang-gaddr thẳng (hợp lệ, không cần sửa) — chỉ
   đúng 1 điểm dereference thật trong cả file.
4. **Field con trỏ VÔ HƯỚNG (không phải mảng) bị subscript theo kiểu mảng, rồi chain tiếp `->`**
   (`duel_field_display_objects.c`, 7 điểm): `source->entries[i].object`/`.field_04` — `entries` khai báo
   `GPTR(DisplayLinkEntry) entries;` (con trỏ đơn, KHÔNG phải `entries[N]`), nhưng code dùng cú pháp
   subscript `entries[i]` (idiom C hợp lệ: con trỏ + subscript = phần tử mảng). Case `ARRAY_SUBSCRIPT_EXPR`
   hiện có (tổng quát hoá ở T1.4d) giả định field BẢN THÂN là mảng gaddr thật và chỉ nhận diện
   grandparent là phép gán/`VAR_DECL` — không nhận diện chain `->` tiếp theo, rơi vào nhánh "chưa gặp,
   không sửa" đã có sẵn trong code (comment tự nhận biết trước: *"not seen yet in this batch"*). Sửa bằng
   1 override thay thế chuỗi con `source->entries[i]` (đồng nhất ở cả 7 vị trí, bất kể theo sau là gì) —
   `all = true`.
5. **Field mảng gaddr thật dùng làm tham số hàm trực tiếp** (`duel_init_model_scene.c:13`):
   `func_80056250(2, D_80010000[0].payload_bases[0], 0x63000, 4);` — `payload_bases` là mảng gaddr thật
   (`GPTR(u8) payload_bases[3]`), nhưng case `ARRAY_SUBSCRIPT_EXPR` chỉ xử lý gán/`VAR_DECL`/đọc-RHS, không
   xử lý đọc làm đối số lời gọi hàm — cũng là nhánh "not seen yet" đã tự nhận biết trước trong code. Sửa
   bằng 1 override (1 điểm duy nhất đo được, không tổng quát hoá).
6. **Nested read-and-write qua một hàm `.c` khác, không phải cast** (`duel_effect_object_commands.c`, 2
   lần lặp y hệt ở 2 hàm): `owner->streams[idx] = Text_Retarget(owner->streams[idx], value & 0xFFFF);` —
   cùng lớp nguy hiểm "nested edit" đã biết từ T1.4d (`GsMapCoordUnit`/`ev.ptr`) và T1.4f
   (`duel_card_effects.c`'s `q->buffer`), nhưng cơ chế phát hiện edit lồng nhau hiện tại trong
   `classify_write` chỉ xét nhánh `CSTYLE_CAST_EXPR` (ép kiểu) làm RHS — ở đây RHS là một **lời gọi hàm
   thường** (`Text_Retarget(...)`, không phải cast), nên hoàn toàn không bị bắt, không sinh edit nào cho cả
   2 vế (khác T1.4d/f, nơi codemod ít nhất phát hiện và dừng hẳn hoặc sinh text rác) — một khoảng trống
   thật trong cơ chế phát hiện edit lồng nhau. Sửa bằng 1 override (`all = true`, 2 vị trí giống hệt).

**Không có pattern nào trong 6 pattern trên được tổng quát hoá vào `transform_c_expressions`** — mỗi cái
chỉ gặp 1-7 lần trong đúng 1-2 file, dưới ngưỡng biện minh mở rộng bộ phân loại (nguyên tắc "chỉ tự động
hoá phần đã đo", nhất quán T1.4b-f).

## 14 file loại khỏi tiêu chí batch — cả 14 đều khớp đúng 1 trong 2 nguyên nhân đã biết

**Nhóm ADR-03/T1.5 (global con trỏ host thật trong header, giống hệt T1.4c-f)**:
- `ordering_tables.h`'s `D_800E9D90[4]`: `duel_draw_status_numbers.c`, `duel_effect_object_pool.c`,
  `duel_effect_request_update.c` (3 file).
- `display_object_work_slots.h` (global tương tự, đã biết từ T1.4c): `duel_ritual_effect.c`,
  `duel_scene_battle.c`, `duel_scene_card_placement.c`, `duel_scene_field_actions.c`,
  `duel_scene_hand_actions.c` (5 file).

**Nhóm ADR-04/T1.6 (lưu con trỏ hàm native vào field guest kiểu callback, giống hệt T1.4c-f)**, xác nhận
từng điểm bằng đọc code thật (đều là `field = (CallbackType)SomeNativeFunction;` hoặc không cast):
`duel_card_type_icon.c`, `duel_draw_resolution.c`, `duel_field_display_objects.c` (3 điểm,
`object`/`o`/`o`'s `->update`), `duel_field_effect_steps.c` (`current->callback`), `duel_init_scene.c` (2
điểm, `field_10`/`field_4C`), `duel_result_runtime.c` (3 điểm), `duel_scene_battle.c` (2 điểm, cộng nhóm
ADR-03 ở trên), `duel_scene_card_placement.c` (1 điểm, cộng nhóm ADR-03), `duel_scene_hand_actions.c` (2
điểm, `obj->update = func_8001EC70;`, cộng nhóm ADR-03) — 9 file, 3 trong số đó trùng nhóm ADR-03 → 14
file duy nhất trong cả batch.

Không có file nào bị loại vì nguyên nhân khác 2 nhóm trên.

## Xác minh

- `check_layouts_lp64.py`: `0 differ` (95 record, 586 header).
- `codemod.py` idempotent (so 2 lần chạy, byte-identical).
- **57/71 file compile sạch** dưới đúng 3 cờ milestone trên arm64+LP64.
- **Sweep hồi quy toàn bộ `CODE_GLOBS` (305 file: 234 file T1.4a-f + 71 file T1.4g)**: đúng 39 lỗi = 25 đã
  biết từ T1.4a-f + 14 file mới của T1.4g — **0 hồi quy ngoài dự kiến**.
- `ctest` (cấu hình mặc định, không `MEMORIES_LP64`): 30/59 fail — khớp baseline T0.4, không đổi.
- Đọc trực tiếp diff của mọi file có override (không chỉ tin compile sạch): cả 8 file có override (kể cả
  2 pattern "nested edit"/"array-as-pointer" phức tạp nhất) khớp đúng ý, không text rác, không sai vị trí
  — kể cả chỗ 2 lớp transform chồng lên nhau (`source->entries[i]`'s override + case chain `->` tổng quát
  hoá sẵn có áp dụng tiếp theo sau nó trong cùng biểu thức).

## Số liệu cuối

| | |
|---|---|
| File trong scope (chunk 2/5, alphabet `duel_card_turn_animations.c` → `duel_trap_resolution.c`) | 71 |
| File bị codemod/override thay đổi thật | 26 |
| Khối override thêm (toml) | 12 |
| Pattern mới cho `transform_c_expressions` gặp phải (không tổng quát hoá) | 6 |
| File compile sạch / tổng | 57/71 |
| File loại trừ — ADR-03/T1.5 (`ordering_tables.h`/`display_object_work_slots.h`) | 8 |
| File loại trừ — ADR-04/T1.6 (callback native → field guest) | 9 (3 trùng nhóm trên) |
| File loại trừ duy nhất (hợp nhất 2 nhóm) | 14 |
| Hồi quy layout (T1.3) | 0 |
| Hồi quy toàn bộ CODE_GLOBS trước đó (305 file) | 0 (đúng 39 lỗi = 25 đã biết + 14 mới) |
| Hồi quy ctest baseline | 0 |
