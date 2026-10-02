# M1 — Codemod giai đoạn 2, batch e: T1.4e (`pc/overrides`, `pc/compat`, `packets.c`)

## Phát hiện phụ trước khi đo scope T1.4e: offsetof-qua-NULL bị `-Wpointer-to-int-cast`

Khi đo compile thật cho 2 file trong scope T1.4e (`src/pc/overrides/narrow_returns.c`,
`title_jump.c`) dưới đúng 3 cờ milestone (`-Werror=int-conversion -Werror=pointer-to-int-cast
-Werror=int-to-pointer-cast`, arm64+LP64), lỗi đầu tiên gặp phải không nằm trong 2 file này mà
nằm **trong `src/ygo_types.h`**: idiom `(u32)&(((T *)0)->member)` / `(u32)&((T *)0)[i]` — mô
phỏng `offsetof` bằng cách lấy địa chỉ field/phần tử qua con trỏ NULL rồi ép xuống `u32`. Dưới
con trỏ 8-byte, phép ép này bị `-Wpointer-to-int-cast` chặn thật, dù giá trị luôn nhỏ và đúng (base
là NULL, không phải địa chỉ thật).

Đo lại quy mô bằng script quét toàn bộ `src/` (không đoán): **207 điểm / 85 file** — chủ yếu trong
header (`static assert` layout `X_offset_must_be_...`, 2 macro `YGO_TYPE_OFFSET`/
`MAIN_MENU_STATE_OFFSET`), nhưng cũng xuất hiện trong `.c` thật (số học con trỏ runtime, ví dụ
`util_memory.c`, `model_slot_row_tables.c`). Trong đó: 1 điểm ở `ai_*.c` (T1.4b), 11 ở
`func_800[0-3]*.c` (T1.4c), 9 ở `func_800[4-9]*.c` (T1.4d) — nghĩa là **một số file đã báo "compile
sạch" ở các batch trước thực ra có lỗi này**, không bị bắt vì quy trình đo thủ công lúc đó không
được lưu lại thành script để đối chiếu — không rõ nguyên nhân chính xác, không suy đoán thêm.

**Phân biệt với ADR-05 mục (4)** (số học con trỏ trên field guest — con trỏ host THẬT, cần tính
trên host pointer rồi `H2G` lại): mục mới này (ADR-05 mục 9) không có con trỏ thật nào — base của
phép `&` luôn là literal `0`, nên giá trị luôn là một offset nhỏ, biết trước lúc dịch. Phân biệt
bằng văn bản: base là `0` hay không.

**Sửa:** `codemod.py`'s `fix_offsetof_casts` (regex, giống cách làm với Mach-O section ở T1.4b) —
`(u32)&` ngay trước `(...)0)` → `(u32)(uintptr_t)&...`. Ép qua `uintptr_t` trước (pointer → int cùng
độ rộng, hợp lệ) rồi mới thu hẹp về `u32` (thu hẹp số nguyên thường, không phải
`-Wpointer-to-int-cast`) cho ra đúng y hệt bit trên mọi ABI, không mất thông tin vì giá trị luôn nhỏ
sẵn. Áp dụng tự động cho **mọi** file codemod ghi ra (header lẫn `.c`), không riêng batch nào.

1 override cũ (`game/func_8001B7AC.c`, `gaddr-field-as-array-subscript-base`) có chứa literal
idiom này trong `old`/`new` — phải cập nhật cả hai để khớp văn bản sau khi `fix_offsetof_casts`
chạy trước `apply_overrides`.

**Xác minh:** `check_layouts_lp64.py` vẫn 0 khác biệt; codemod idempotent; sweep lại toàn bộ
T1.4a-d (121/163 file CODE_GLOBS, trừ 42 file đã biết lỗi vì lý do khác — xem dưới) không phát
sinh lỗi mới nào; `ctest` cấu hình mặc định vẫn 30/59 fail (khớp baseline T0.4).

## Phát hiện phụ thứ hai: con trỏ host thật ép xuống s32/u32 qua biến cục bộ — CHƯA SỬA

Khi sweep hồi quy lại toàn bộ T1.4a-d sau khi thêm `fix_offsetof_casts`, lộ ra **28 file khác**
(27 trong CODE_GLOBS + `psyq/startup_data.c` đã biết từ T1.4a vì lý do riêng) với một lỗi hoàn
toàn khác: con trỏ host **thật** (không phải base NULL) bị ép xuống `s32`/`u32` để làm số học rồi
ép ngược lại thành con trỏ. Ví dụ `ai_fusion.c`:

```c
u8 *indices = D_800EAE88;                    /* D_800EAE88: global thật, mảng đã compile */
s32 index = *(u8 *)(i + (s32)indices);       /* ép con trỏ host xuống s32 rồi cộng i */
```

Khác hẳn idiom offsetof (mục trên): ở đây giá trị bị ép xuống là một **địa chỉ host thật**, có thể
nằm bất kỳ đâu trong không gian địa chỉ 64-bit — ép qua `uintptr_t` không giải quyết được gì (chỉ
tắt warning, không tắt được việc mất bit thật). T1.5 (ADR-03, global sống trong RAM guest) **không**
giải quyết được vấn đề này: `G2H(...)` vẫn trả về một con trỏ host thật, vẫn có thể bị cắt cụt y
hệt. `transform_c_expressions` hiện chỉ quét `MEMBER_REF_EXPR` (field struct), không quét biến cục
bộ/tham số mang con trỏ như `indices` ở trên — nên không có cơ chế hiện tại xử lý được, kể cả khi
muốn.

Danh sách đầy đủ 28 file (đo bằng sweep thật, không đoán): `psyq/startup_data.c`, `ai_fusion.c`,
`ai_turn_action.c`, `func_80019CC8.c`, `func_8001B938.c`, `func_80020BE4.c`, `func_80027DF8.c`,
`func_800289BC.c`, `func_8002ABB4.c`, `func_8002F4C0.c`, `func_800320BC.c`, `func_800323F8.c`,
`func_800339D0.c`, `func_80033DB0.c`, `func_80034830.c`, `func_80036C14.c`, `func_8003A01C.c`,
`func_8003DA40.c`, `func_8003DC1C.c`, `func_80045514.c`, `func_80046A08.c`, `func_80049138.c`,
`func_80051A48.c`, `func_80052D2C.c`, `func_80058938.c`, `func_80059AA8.c`, `func_8005CEF0.c`,
`func_80061008.c`. Đo trên mẫu 121 file đã "xong" ở T1.4a-d: **28/121 (~23%)** — chưa đo hết 352
file còn lại của T1.4f, tỉ lệ thật có thể khác.

Đã hỏi fen qua `AskUserQuestion` ngay khi phát hiện (không tự ý sửa hay đào sâu thêm). Fen chọn:
ghi nhận đầy đủ vào `PROGRESS.md`'s "Vấn đề mở" (đã làm), không sửa ngay, tiếp tục T1.4e theo đúng
scope gốc. Cần bàn kiến trúc riêng (tổng quát hoá ADR-05 mục (4) cho biến cục bộ, không chỉ field
struct) trước khi quay lại xử lý — chưa chốt hướng.

## T1.4e: batch thật — scope `pc/overrides`, `pc/compat` (GTE, libgs_ot), `pc/render/packets.c`

**Kết quả: cả 6 file đã compile sạch, không cần sửa code gì (không codemod, không override, không
sửa tay).**

Khác `src/game`/`src/psyq`, các file này **không nằm trong danh sách cấm sửa tay** (luật 1,
CLAUDE.md) — đúng cách làm của T1.4a. Nhưng khác cả T1.4a (SDK, cần 9 điểm sửa tay +
`#ifdef MEMORIES_LP64`), đo thật (`grep` cho `G2H`/`H2G`/`GPTR`/`gaddr`, rồi compile trực tiếp dưới
đúng 3 cờ milestone) cho thấy **0 điểm cần sửa**:

- `src/pc/compat/gte.c`, `src/pc/compat/libgs_ot.c`, `src/pc/render/packets.c`: không hề dùng
  `GPTR`/`gaddr` — nhận `uint32_t address` làm tham số và gọi `Memories_Resolve(memory, address,
  length, alignment)`, một tầng trừu tượng tách biệt sẵn độ rộng con trỏ (trả `void *` sau khi tự
  kiểm biên/căn chỉnh) thay vì thao tác trực tiếp trên field GPTR nào — ADR-05 không áp dụng vì
  không có field con trỏ nào ở đây cả.
- `src/pc/overrides/model_polygon_drivers.c`, `title_jump.c`: dùng con trỏ host thật trực tiếp
  (tham số, biến cục bộ), không qua field GPTR nào.
- `src/pc/overrides/narrow_returns.c`, `title_jump.c`: include `../ygo_types.h` — đây chính là 2
  file lộ ra lỗi offsetof-qua-NULL ở trên; sau khi `fix_offsetof_casts` sửa, compile sạch.

**Xác minh:** 6/6 file compile sạch dưới đúng 3 cờ milestone (arm64+LP64); `check_layouts_lp64.py`
0 khác biệt (không đổi so với trước vì không có thay đổi nào riêng cho T1.4e ngoài
`fix_offsetof_casts` đã xác minh ở trên); `ctest` cấu hình mặc định 30/59 fail (khớp baseline T0.4).

## Số liệu cuối (toàn bộ T1.4e, gồm cả `fix_offsetof_casts`)

| | |
|---|---|
| File trong scope T1.4e | 6 (`pc/overrides` ×3, `pc/compat` GTE+libgs_ot ×2 `.c`, `pc/render/packets.c`) |
| File T1.4e cần sửa code | 0 |
| Điểm `fix_offsetof_casts` sửa tự động (toàn bộ cây codemod hiện tại) | 131 |
| Điểm `fix_offsetof_casts` đo được toàn `src/` (bao gồm file chưa vào CODE_GLOBS) | 207 / 85 file |
| File đã "xong" ở T1.4a-d lộ thêm lỗi offsetof (nay đã sạch) | 21 (1 ai_b + 11 func03_c + 9 func49_c) |
| File đã "xong" ở T1.4a-d lộ lỗi con trỏ-thật-ép-int (CHƯA sửa, ghi vào Vấn đề mở) | 28 |
| Override cũ phải cập nhật theo `fix_offsetof_casts` | 1 (`func_8001B7AC.c`) |
| Hồi quy layout (T1.3) | 0 |
| Hồi quy T1.4a/b/c/d (ngoài 28 file mới phát hiện, không phải hồi quy do T1.4e mà là lỗi có sẵn) | 0 |
| Hồi quy ctest baseline | 0 |

