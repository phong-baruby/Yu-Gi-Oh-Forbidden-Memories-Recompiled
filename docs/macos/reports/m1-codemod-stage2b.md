# M1 — Codemod giai đoạn 2, batch b: AI script VM (T1.4b)

**Kết quả: acceptance đạt cho toàn bộ 20 file trong scope.**

**Lệnh:**
```sh
python3 tools/pc/lp64/codemod.py                 # mở rộng EXPR_GLOBS += game/ai_*.c
python3 tools/pc/lp64/check_layouts_lp64.py       # vẫn 0 khác biệt (không hồi quy T1.3/T1.4a)
```

## Khác T1.4a: lần này thật sự cần codemod AST cho biểu thức `.c`

`src/game/*.c` nằm trong danh sách cấm sửa tay (CLAUDE.md luật 1) — không thể lặp lại cách T1.4a
làm với `src/pc/sdk` (sửa tay + `#ifdef`). Đo thật bằng libclang trên 20 file `ai_*.c`: phần lớn
(17/20) không có điểm GPTR nào; đúng 3 file (`ai_script_vm.c`, `ai_script_control_flow.c`,
`ai_turn_action.c`) có tổng cộng 18 điểm thật — đủ lặp lại (VM đọc bytecode qua
`AiScriptState.script_cursor`/`script_base`, cùng 1 idiom lặp 7 lần trong `ai_script_control_flow.c`)
để lần này xây hẳn bộ biến đổi AST cho biểu thức (`transform_c_expressions`), đúng như đã đề xuất
và fen duyệt.

## Thiết kế bộ phân loại — và 2 nguyên tắc giảm rủi ro đã thống nhất trước khi code

Trước khi viết, fen và em đã thống nhất 3 biện pháp giảm rủi ro "sai thầm lặng": (1) lệch hướng —
*thiếu* `H2G` (giá trị guest sai nhưng không crash) nguy hiểm hơn *thừa* `H2G` (sẽ crash ngay do
`H2G` tự abort khi con trỏ ngoài `g_ram`/`g_scratch`) — nên bộ phân loại thiên về báo lỗi dừng hẳn
(`sys.exit`) thay vì đoán khi không chắc; (2) chỉ tự động hoá phần đã đo được, không đoán cho
trường hợp chưa gặp; (3) không chỉ tin "compile sạch" — đọc từng diff thật.

**Biện pháp (3) đã cứu đúng 1 lần**, trong lúc code: bug macro-argument của `DISPLAY_OBJECT_VIEW`
(xem dưới) bị `-Werror` các cờ milestone **bỏ sót hoàn toàn** — code sinh ra sai cú pháp
(`G2H()DISPLAY_OBJECT_VIEW(...)`) nhưng rủi ro là token rác đó tình cờ **vẫn parse được** ở một vài
cấu hình cờ khác; chỉ bắt được bằng cách đọc diff so với bản gốc, không phải nhờ compile.

4 dạng phân loại, dựa trên cursor cha trực tiếp (bỏ qua `PAREN_EXPR`/implicit-cast) của field
`gaddr`:
- **Đọc, ép sang con trỏ** (`(T*)x.f`, hoặc khai báo `T *p = x.f;`) → bọc `G2H`.
- **Đọc + dereference**, kể cả dạng `*x.f++` (VM đọc byte rồi tự tăng con trỏ) → chỉ bọc phần
  dereference bằng `G2H`; phần `++` **không đổi** — tăng 1 lên giá trị `gaddr` (số nguyên) cho đúng
  số byte y hệt tăng con trỏ `u8*` gốc, không cần `H2G`.
- **Ghi, giá trị là con trỏ host thật** (ví dụ tham số hàm) → bọc `H2G`.
- **Ghi, giá trị là số học hoàn toàn trong không gian địa chỉ guest** (ví dụ
  `state->script_cursor = (u8 *)(result + (s32)state->script_base);` — `script_base` chỉ được
  dùng như số, cộng offset, rồi ép sang con trỏ theo thói quen code cũ) → **chỉ bỏ phép ép kiểu**,
  không gọi `H2G` (gọi `H2G` ở đây sẽ nhận một giá trị không phải con trỏ host thật — đúng hướng
  "lỗi phải kêu to" nhưng vẫn là code sai).

## 2 bug tự vấp phải khi viết (trước khi có diff đúng)

1. **`clang` tạo node AST "che" kiểu thật khi code đang lỗi kiểu (đúng lý do đang cần sửa!):**
   với `gAiScript_State.script_base = script;` (`script` kiểu `u8*` thật, gán vào field `gaddr`),
   node RHS libclang trả về không phải `script` mà một `UNEXPOSED_EXPR` báo **kiểu đích** (`gaddr`)
   thay vì kiểu thật của `script`. Bộ phân loại ban đầu tin thẳng `rhs.type` nên coi field này "đã
   đúng kiểu, khỏi sửa" — sai hoàn toàn, im lặng bỏ qua một điểm ghi thật. Sửa: hàm
   `unwrap_transparent` lách qua lớp bọc đó trước khi hỏi kiểu.
2. **`CSTYLE_CAST_EXPR.get_children()` trả về `TYPE_REF` trước, toán hạng sau:** lấy nhầm
   `children()[0]` tưởng là toán hạng (`offset`) hoá ra là node kiểu đích (`u8`) — sinh ra
   `s->script_cursor = u8;` (mất hẳn `offset`, một lỗi cú pháp lộ rõ khi đọc diff, nhưng **không**
   phải loại lỗi mà riêng việc "có compile được không" chắc chắn bắt được nếu tình cờ `u8` tình cờ
   là identifier hợp lệ ở đó). Sửa: lấy toán hạng đúng ở `children()[-1]`.

## Giới hạn thật của libclang với macro — xử lý bằng override, không ép AST

`DISPLAY_OBJECT_VIEW(source->ptr)` (macro mở ra `((DisplayObject *)(source->ptr))`) — field
`source->ptr` là tham số của macro, nên cursor của nó có **extent rỗng** (start == end), libclang
không gán được vị trí byte thật trong file cho một node sinh từ tham số macro theo kiểu này. Dùng
offset đó để chèn text sinh ra `G2H()DISPLAY_OBJECT_VIEW(source->ptr)` — lỗi, phát hiện bằng đọc
diff. Đã thêm guard `start == end` → `sys.exit` rõ ràng (không bao giờ chèn vào extent rỗng im
lặng), rồi xử lý 4 điểm này (2 dòng × 2 chỗ gọi, `ai_turn_action.c`) qua
`config/lp64/overrides.toml` dạng mới: bọc `G2H` trực tiếp vào text tham số macro, né hẳn vấn đề vị
trí AST.

## Phát hiện phụ, đã mở rộng xử lý (fen duyệt): lỗi Mach-O section attribute là vấn đề toàn dự án

Compile thử 20 file lộ thêm 2 vị trí MỚI của lỗi đã biết từ T0.4 (`ai_opponent_data.h`,
`duel_terrain_boost.h`), nâng tổng số đã gặp lên 5 (2 đã vá tay từng file ở T1.4a/T1.4b, 2 còn mở từ
T1.3). Đếm thật: **265 lần xuất hiện trên 58 file toàn dự án** (151 trong đúng phạm vi 4 glob
pattern milestone, phần còn lại ở `overlays/*.c` — chưa tới lượt batch nào). Thay vì tiếp tục vá
từng file một (sẽ còn phát sinh mỗi khi một batch sau đụng trúng file mới), fen duyệt viết hẳn một
quy tắc chung: macro `MEMORIES_SECTION(name)` mới trong `src/pc/guest/gptr.h` (luôn được
`-include`, đúng ADR-02) tự mở ra `section("__DATA," name)` trên Apple hoặc `section(name)` nơi
khác; `codemod.py`'s `fix_mach_o_sections` thay mọi `__attribute__((section("X")))` thành
`__attribute__((MEMORIES_SECTION("X")))` bằng regex thuần (không cần AST, không rủi ro ngữ nghĩa) —
áp dụng tự động cho **mọi** file codemod ghi ra, không giới hạn batch nào. 3 override tay đã viết ở
T1.4a/b (`startup_data.c`, `unmatched.h` ×2) bị thay thế, xoá khỏi `overrides.toml`.

## Xác minh

- `check_layouts_lp64.py`: vẫn `0 differ` (không hồi quy T1.3).
- `codemod.py` idempotent: output byte-identical qua 2 lần chạy (kể cả `game/ai_*.c` mới và sweep
  Mach-O section mới).
- **20/20 file `game/ai_*.c`** compile sạch dưới `arm64-apple-macos -DMEMORIES_LP64` với đúng 3 cờ
  milestone (`-Werror=int-conversion -Werror=pointer-to-int-cast -Werror=int-to-pointer-cast`).
- `src/pc/sdk/libgte.c`/`libgte_extra.c` (T1.4a) biên dịch lại sạch sau khi thêm macro
  `MEMORIES_SECTION` vào `gptr.h` — không hồi quy.
- `src/pc/guest/gptr.h` tự nó biên dịch sạch ở cả 3 cấu hình (arm64+LP64, arm64 không-LP64,
  i386 không-LP64 — cấu hình thật của upstream).
- `ctest` (cấu hình mặc định, không `MEMORIES_LP64`): 30/59 fail — khớp đúng baseline T0.4, không
  hồi quy.
- `src/psyq/startup_data.c` vẫn còn 1 lỗi KHÔNG liên quan phần việc T1.4b (`gGraphics_aFrameBuffers`
  undeclared) — đã xác nhận lại đây là lỗi **đã có từ trước T1.4a**, xảy ra giống hệt khi compile
  bằng đúng cờ `NATIVE_CFLAGS` thật trên `i386-pc-linux-gnu`, không phải hồi quy.

## Số liệu cuối

| | |
|---|---|
| File trong scope | 20 (`game/ai_*.c`) |
| File có điểm GPTR thật | 3 |
| Điểm ADR-05 (2)/(4) sửa (AST) | 18 |
| Điểm sửa qua override (giới hạn libclang với macro) | 4 (2 dòng × 2 lệnh gọi) |
| Bug tự vấp phải khi viết bộ phân loại | 2 (unwrap_transparent, children()[-1]) |
| Vị trí Mach-O section attribute vá tay trước khi tổng quát hoá | 3 |
| Vị trí Mach-O section attribute tổng quát hoá xử lý (toàn dự án) | 265 (151 trong 4 glob pattern, còn lại chờ batch overlay) |
| File compile sạch / tổng | 20/20 |
| Hồi quy layout (T1.3) | 0 |
| Hồi quy ctest baseline | 0 |
