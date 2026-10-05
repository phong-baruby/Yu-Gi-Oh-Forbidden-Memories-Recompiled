# M1 — Codemod giai đoạn 2, batch f: src/game phần còn lại, chunk 1/5 (T1.4f)

> **Sửa lại (2026-10-05, phát hiện ở T1.4i):** con số "61/71" dưới đây SAI do lỗi trong chính lệnh
> compile-check (cờ `-w` vô hiệu hoá luôn `-Werror=pointer-to-int-cast`/`-Werror=int-to-pointer-cast`,
> chỉ `-Werror=int-conversion` còn tác dụng — lỗi quy trình xác minh, không phải code sai thêm). Số
> liệu đúng: **50/71 file thật sự compile sạch**; 10 file loại trừ ADR-03/04 bên dưới vẫn đúng, cộng
> thêm **11 file khác** hoá ra cũng chưa compile sạch, thuộc đúng nhóm "con trỏ host thật bị ép xuống
> s32/u32 qua biến cục bộ" đã ghi nhận từ T1.4e (`build_deck_pane_input.c`,
> `campaign_load_scene_package_stage.c`, `campaign_map_load_package_stage.c`, `card_list_sort.c`,
> `dialog_transition.c`, `display_effect_process_menu_records.c`, `display_effect_update_callbacks.c`,
> `display_object_helpers.c`, `display_object_projection_checks.c`,
> `display_object_render_sprite_sheet.c`, `display_object_update_command_stream.c`). Chi tiết đầy đủ:
> `docs/macos/reports/m1-codemod-stage2i.md` và `PROGRESS.md`'s decision log 2026-10-05.

**Kết quả: 61/71 file đạt acceptance. 10 file loại khỏi tiêu chí, đều thuộc 2 nguyên nhân ADR-03/ADR-04
đã biết từ T1.4c/d — không có nguyên nhân mới trong nhóm loại trừ.**

**Lệnh:**
```sh
python3 tools/pc/lp64/codemod.py                 # mở rộng CODE_GLOBS/EXPR_GLOBS += 71 file T1.4f (liệt kê thẳng, không glob — xem lý do dưới)
python3 tools/pc/lp64/check_layouts_lp64.py       # vẫn 0 khác biệt
```

## Tiếp nối từ phiên trước (session này chỉ hoàn thiện, không khởi tạo lại)

Phiên trước đã: (1) đo quy mô thật 352 file còn lại của `src/game` bằng libclang (293/352 file có điểm
GPTR thật, 4043 điểm — gấp ~36 lần T1.4d), tách thành 5 batch con theo thứ tự alphabet tên file (sửa
`M1-title-screen.md`); (2) bắt đầu T1.4f (71 file đầu, `build_deck_active_card.c` →
`duel_card_state_helpers.c`) — thêm `T14F_FILES` (danh sách liệt kê thẳng vào `codemod.py`, không phải
glob, vì các file này đặt tên theo hàm chứ không theo tiền tố địa chỉ như `func_800...*`) vào
`CODE_GLOBS`/`EXPR_GLOBS`; (3) chạy codemod và tự vá 8 điểm bằng override (`duel_card_effects.c` ×6 khối,
`display_effect_update_callbacks.c` ×2, `display_object_stream_read_next_command.c` ×1 `all=true`). Phiên
đó dừng lại ở đây: chưa compile-check toàn batch, chưa viết report này (dù milestone đã trỏ tới nó), chưa
cập nhật `PROGRESS.md` xong, chưa commit. Phiên này tiếp tục từ trạng thái uncommitted đó.

## Vá lỗ hổng trong chính quy trình xác minh thủ công trước khi đo

Trước khi tin bất kỳ con số "compile sạch" nào, phát hiện 2 vấn đề trong cách gọi lệnh, không liên quan
tới code đã sửa:

1. `codemod.py --out tmp/lp64` (đúng như bảng lệnh ở `CLAUDE.md` của dự án) ghi thẳng vào `tmp/lp64/`,
   nhưng `check_layouts_lp64.py --codemod` mặc định đọc từ `tmp/lp64/src/` — và mọi report trước đó
   (`m1-codemod-stage2a` → `2e`) đều gọi `codemod.py` **không kèm `--out`** (dùng default `tmp/lp64/src`).
   Bảng lệnh ở `CLAUDE.md` bị lệch so với quy ước thật đang dùng (có thể đúng tại thời điểm T0.7, không
   được cập nhật sau đó) — **không tự sửa `CLAUDE.md`** (nằm ngoài scope T1.4f, để fen quyết định), chỉ
   ghi nhận ở đây để phiên sau không vấp lại. Dùng đúng mặc định `tmp/lp64/src` cho toàn bộ xác minh dưới
   đây.
2. Compile thử trực tiếp từng file `.c` trong `tmp/lp64/src/game/*.c` cần `-I` tới cả cây đã codemod lẫn
   `src/` gốc (cho mọi thứ codemod không chạm tới, như `pc/mods/mods.h`) **và** một include tường minh
   `gptr.h` (`-include src/pc/guest/gptr.h`) — không có nó, `gaddr` không tồn tại, toàn bộ 71 file báo lỗi
   giả `unknown type name 'gaddr'`. Thêm vào đó, 1 file (`psyq/inline_c.h`, include gián tiếp qua
   `../psyq/inline_c.h` ở một số file) có include tương đối `"../pc/compat/inline_c_native.h"` giả định
   `pc/` là thư mục anh em của `psyq/` — đúng khi compile từ `src/` gốc, sai khi compile bản sao ở
   `tmp/lp64/src/psyq/` (không có `pc/` cạnh nó, vì `pc/` không nằm trong `DEFAULT_GLOBS`/`CODE_GLOBS`,
   không được codemod chạm tới). Vá bằng 1 symlink cục bộ, không commit:
   `ln -s $(pwd)/src/pc tmp/lp64/src/pc`. Không sửa `codemod.py` vì đây thuần là vấn đề của bộ gõ lệnh
   compile thử tay, không phải của chính codemod (bản thân `codemod.py`'s `parse_code` không cần toàn bộ
   TU sạch để hoạt động — nó chỉ cần node AST nó quan tâm parse được).

Lệnh compile thử dùng cho mọi số liệu dưới đây:
```sh
clang --target=arm64-apple-macos -std=gnu11 -DMEMORIES_PC -D_LANGUAGE_C -DLANGUAGE_C -DMEMORIES_LP64 \
  -Werror=int-conversion -Werror=pointer-to-int-cast -Werror=int-to-pointer-cast \
  -fsyntax-only -w -Itmp/lp64/src -Isrc -include src/pc/guest/gptr.h tmp/lp64/src/game/<file>.c
```

## 1 override mới (phiên này), cùng lớp với 1 override đã duyệt ở T1.4e

`display_object_helpers.c:320`:
```c
return object->base + ((data[1] << 8) | data[0]);
```
`object->base` (`GPTR(u8) base`, struct `DisplayObjectStream`) dùng làm toán hạng `+` trần dưới `return`
— `transform_c_expressions` không có case cho gaddr field làm toán hạng trần dưới `return` (đã có case
cho gán, từ override T1.4e `p = object->current + ...`, nhưng không phải cho `return`). Xác nhận cần
`G2H` qua kiểu trả về khai báo của hàm (`u8 *DisplayObjectStream_ResolveOffset`) — khác hẳn
`display_object_runtime.c:331/342` và `display_object_stream_read_next_command.c:30`, nơi **cùng cú
pháp** `object->base + offset` được gán vào MỘT FIELD GADDR KHÁC (`object->current`/`object->field_4C`)
và đúng là phải giữ nguyên dạng số học gaddr thuần (không G2H) — cùng idiom nguồn, đích khác nhau, đáp án
đúng khác nhau. Sửa bằng override, không tổng quát hoá case `return` (chỉ 1 điểm gặp phải, không đủ lặp
lại để biện minh mở rộng bộ phân loại — đúng nguyên tắc "chỉ tự động hoá phần đã đo").

## 10 file loại khỏi tiêu chí batch — cả 10 đều khớp đúng 1 trong 2 nguyên nhân đã biết, không có nguyên nhân mới

**Nhóm ADR-03/T1.5 (global con trỏ host thật `ordering_tables.h`'s `D_800E9D90[4]`, giống hệt lý do loại
trừ ở T1.4c/d)** — `sizeof(D_800E9D90)` tăng gấp đôi dưới con trỏ 8-byte, vỡ static assert
`OrderingTable_slots_size_must_be_0x10`, chặn mọi file include `ordering_tables.h`:
`display_object_core.c`, `display_object_render_sprite_sheet_list.c`, `display_object_runtime.c`,
`display_object_updates.c`, `display_projection.c` (5 file).

**Nhóm ADR-04/T1.6 (lưu con trỏ hàm NATIVE thật vào field guest kiểu `DisplayObjectCallback`/tương tự,
giống hệt lý do loại trừ `func_80014294.c`/`func_8001D518.c` ở T1.4c/d — field đó cần cơ chế GCALL chưa
xây)**, xác nhận từng điểm bằng cách đọc code thật (đều là `field = (CallbackType)SomeNativeFunction;`):
`dialog_update_choice.c:39` (`e->update = (DisplayObjectCallback)Widget_UpdatePulseColour;`),
`display_object_alpha_transition.c:40` (`arg0->update = (DisplayObjectCallback)DisplayObject_UpdateAlphaTransition;`),
`display_parent_links.c:21` (`object->update = (DisplayObjectCallback)DuelSelection_UpdateLinkedObject;`),
`duel_card_effects.c:521` (`target->callback = DuelEffect_UpdateRevealCard;`),
`duel_card_record_lifecycle.c:215` (`obj->field_10 = (void *)DisplayObject_SetResourceVariantFromSign;`) —
cộng 4 file đã nằm trong nhóm ADR-03 ở trên (`display_object_core.c`, `display_object_render_sprite_sheet_list.c`,
`display_object_runtime.c` ×2 điểm, `display_object_updates.c` ×3 điểm) cũng có cùng lỗi callback này.
Tổng 9 file có lỗi nhóm này, 4 trong số đó trùng với nhóm ADR-03 → 10 file duy nhất trong cả batch.

Không có file nào bị loại vì nguyên nhân khác 2 nhóm trên.

## Xác minh

- `check_layouts_lp64.py`: `0 differ` (95 record so sánh, 586 header).
- `codemod.py` idempotent (so 2 lần chạy, byte-identical ngoài symlink `pc/` tôi tự thêm để xác minh).
- **61/71 file compile sạch** dưới đúng 3 cờ milestone trên arm64+LP64.
- **Sweep hồi quy toàn bộ `CODE_GLOBS` (234 file: SDK + `ai_*` + `func_800[0-3]*` + `func_800[4-9]*` +
  T1.4f)**: đúng 25 lỗi = 14 file `func_800...` đã biết từ T1.4c/d + `psyq/startup_data.c` đã biết từ
  T1.4a + 10 file mới của T1.4f — **0 hồi quy ngoài dự kiến** trên phần đã làm trước đó.
- `ctest` (cấu hình mặc định, không `MEMORIES_LP64`): 30/59 fail — khớp baseline T0.4, không đổi.
- Đọc trực tiếp diff của mọi file có override (không chỉ tin compile sạch): `duel_card_effects.c`,
  `display_effect_update_callbacks.c`, `display_object_stream_read_next_command.c`,
  `display_object_helpers.c` — cả 4 khớp đúng ý override, không có text rác hay vị trí sai.

## Số liệu cuối

| | |
|---|---|
| File trong scope (chunk 1/5, alphabet `build_deck_active_card.c` → `duel_card_state_helpers.c`) | 71 |
| File bị codemod/override thay đổi thật | 22 |
| Khối override thêm (toml, cả phiên trước + phiên này) | 10 (9 phiên trước, 1 phiên này) |
| File compile sạch / tổng | 61/71 |
| File loại trừ — ADR-03/T1.5 (`ordering_tables.h`, như T1.4c/d) | 5 |
| File loại trừ — ADR-04/T1.6 (callback native → field guest, như T1.4c/d) | 9 (4 trùng nhóm trên) |
| File loại trừ duy nhất (hợp nhất 2 nhóm) | 10 |
| Hồi quy layout (T1.3) | 0 |
| Hồi quy toàn bộ CODE_GLOBS trước đó (234 file) | 0 (đúng 25 lỗi = 15 đã biết + 10 mới) |
| Hồi quy ctest baseline | 0 |
