# M1 — T1.10: Build driver (chưa xong — build.py viết xong, link chưa qua được)

**Kết quả: `tools/pc/macos/build.py` (codemod → compile → stub → link) đã viết xong và chạy thật, nhưng
CHƯA link được.** Giữa chừng phát hiện T1.5 chưa xong một phần RẤT lớn (global "data thuần", 86% tổng số
global) — làm luôn phần đó (fen duyệt qua `AskUserQuestion`), giảm được blocker từ 550 xuống 221, nhưng
vẫn còn 221 global data thật chưa có chỗ lưu trữ, nên **chưa đạt acceptance của T1.10** (chưa chạy được
binary nào).

## Phát hiện lớn: T1.5 "global data thuần" (749/871, 86%) thực ra CHƯA code, chỉ mới đo

`docs/macos/PROGRESS.md`'s dòng T1.5 tự ghi "để dành phiên T1.5 sau" nhưng không phiên nào quay lại —
T1.6→T1.9 đi thẳng sang ADR-04/08/09/10. `gen_globals.py` đã đo sẵn dữ liệu (`classified`/`declarations`)
nhưng `codemod.py`'s `load_globals()` trước đây chỉ đọc mục `canonical` (chỉ pointer/pointer-array, 80
symbol) — nhóm "data thuần" (736 "plain" + 13 "struct-with-pointer") CHƯA được nối vào codemod ở đâu cả.
Thử link thật lần đầu (sau khi build.py compile xong 568/618 unit) lộ ra >1100 symbol "undefined", trong
đó ~550 là GLOBAL DATA thật (không phải hàm) — khác hẳn 50 file compile-lỗi (stub được bằng hàm
log+abort): data không stub được (không có calling convention để abort ra, thân hàm giả sẽ nằm sai chỗ
bộ nhớ). Dừng lại, báo cáo fen, fen chọn "làm luôn T1.5 phiên 3 trong task này".

## T1.5 phiên 3 — macro-hoá "global data thuần"

ADR-03's văn bản đã nói đúng: nhóm này **không cần sửa `transform_c_expressions`**, chỉ cần macro
dereference trực tiếp `#define NAME (*(T *)G2H(addr))` (mảng: `(*(T (*)[N])G2H(addr))`) — KHÔNG cần
struct/typedef wrapper như pointer global (T1.5 phiên 2), vì text macro giống hệt ở mọi file khai báo lại
là hợp lệ (C11 6.10.3p2: redefine macro với token sequence giống hệt không phải lỗi), khác typedef (2
struct ẩn danh viết riêng biệt luôn là 2 kiểu khác nhau dù cấu trúc giống hệt — đúng lý do pointer global
phải loại trừ "vừa extern vừa định nghĩa thật").

**Thực hiện:**
- `gen_globals.py`: `type_shape()` giờ báo cả element+size cho mảng "plain" (trước chỉ báo cho
  pointer-array). Thêm vòng lặp mới build `canonical` cho `classified["plain"] + ["struct-with-pointer"]`,
  gắn `"kind": "plain"` (phân biệt với `"kind": "pointer"` của phiên 2).
- **Loại trừ 2 nhóm mới phát hiện khi đo thật** (không đoán, đo bằng code):
  - Mảng không nơi nào nói rõ kích thước (`T name[]` ở mọi chỗ, không có `T name[N]`): không có cách viết
    cast `T (*)[N]` nếu N không biết — 140 symbol.
  - **Xung đột kiểu thật giữa các file khai báo cùng 1 địa chỉ** (không phải khác size mảng — ví dụ
    `D_8009AF5C`: 1 file nói `unsigned char[]`, file khác nói `OptionsLayoutPositionData` là 1 struct hẳn
    hoi; `gInput_wPad1Held`: có chỗ scalar `unsigned short`, có chỗ `volatile unsigned short[4]`) — nếu cứ
    lấy kiểu của file đầu tiên quét được (`hits[0]`) sẽ sai ở MỌI file khác đồng ý kiểu khác. Chuẩn hoá bỏ
    kích thước mảng/`const`/`volatile` trước khi so — 54 symbol xung đột thật (khác `[]` vs `[N]`, vốn
    vô hại và không bị loại).
- `codemod.py`'s `global_wrapper_text` tách nhánh theo `info["kind"]`: `"pointer"` giữ nguyên 100% cơ chế
  phiên 2 (không regress 80 symbol đã có); `"plain"` phát macro trực tiếp như trên.
- **Kết quả đo thật**: 524/749 global data thuần được macro-hoá (140 loại vì không rõ size, 54 loại vì
  xung đột kiểu, loại trừ — ghi vào census để phiên sau tiếp tục nếu cần).

## Phát hiện phụ: "local extern" trong file native `src/pc/` né qua codemod — 15 file

`gen_globals.py` chỉ quét header (`DEFAULT_GLOBS`) + `CODE_GLOBS` (`src/game`, `src/psyq`) — các file
native `src/pc/**/*.c` (được phép sửa tay theo CLAUDE.md) đôi khi tự khai báo `extern TYPE NAME;` riêng
thay vì include header, nên không được T1.5 (bất kỳ phiên nào) đụng tới — mãi đến khi link thật mới lộ ra
(ví dụ `src/pc/overrides/model_polygon_drivers.c`'s `extern u32 D_8009AFAC, D_8009AFB0, ...;`). Sửa tay
trực tiếp (đúng quy ước ADR-05 cho file `.c` không cấm sửa) — bọc từng tên bằng
`#ifdef MEMORIES_LP64 #define NAME (*(T*)G2H(addr)) #else extern ... #endif`, giữ nguyên tên nào đã biết
là xung đột kiểu (không đụng, để lại làm "data blocker" như cũ). 15 file, ~26 điểm:
`src/pc/cards/{fusion_helper,rank_meter,tables}.c`, `src/pc/debug/cheats.c`, `src/pc/platform/{ai_trace,
credits}.c`, `src/pc/overlays/duel_effects.c`, `src/pc/overrides/{model_polygon_drivers,title_jump}.c`,
`src/pc/saves/{deck_menu,deck_shop}.c`, `src/pc/sdk/{libgs,libgs_unit,libgte_extra}.c`. Xác minh KHÔNG
tự ý wrap nhầm tên đã biết là xung đột kiểu bằng cách so từng site với `canonical` (script riêng, không
commit) — 2 chỗ phát hiện xung đột không nằm trong phạm vi quét của `gen_globals.py`
(`gDuel_aOpponentData`/`gFreeDuel_abGridAvailable` trong `src/pc/free_duel/duelists.c`: khai báo
`signed char [][N]` ở đó nhưng `AiOpponentData`/struct khác ở nơi khác) — **cố tình không sửa**, để nguyên
làm blocker, tránh cast sai kiểu im lặng.

## `tools/pc/macos/build.py` (mới)

Đơn giản hơn `build_game32.py` nhiều vì ADR-03/04 đã giải quyết addressing ở tầng C (không cần linker-script
pin địa chỉ/weak-symbol/module bank rename): chạy `gen_globals.py` → `gen_fn_table.py` → `codemod.py` →
compile mọi unit hiện LP64-compile-sạch (`-Werror=int-conversion -Werror=pointer-to-int-cast
-Werror=int-to-pointer-cast`, **không** `-w` — T1.4i đã phát hiện `-w` vô hiệu hoá 2 trong 3 cờ này bất kể
vị trí) → sinh stub (log tên + abort) cho hàm còn thiếu → link Mach-O arm64 với `tmp/pc/macos-deps` (T1.9).
Phân biệt rõ "hàm thiếu" (stub được) với "data thiếu" (KHÔNG stub được — dừng sạch, in danh sách, không cố
link) bằng cách so địa chỉ retail với range `.text` của ảnh resident (`config/pc/guest_addresses.txt`) +
`functions.csv` + mọi `config/slus_01411/overlays/*_functions.csv`.

Danh sách native file: mô phỏng `NATIVE` của `build_game32.py`, bỏ backend X11/ALSA/evdev (chỉ SDL),
bỏ `src/pc/mods/{mods,hooks,manager,object_loader,events}.c` thật (ADR-06/07 chưa xây cho arm64, đúng
milestone "mod loader tạm tắt trên LP64") — `mods_disabled_lp64.c` (mới) cho 2 hàm `Mods_Dispatch`/
`Mods_DamageLife` mà `src/game` gọi trực tiếp, no-op thật (không phải stub abort — "không mod" là hành vi
đúng, không phải lỗi). Bỏ `src/pc/guest/{image,modules,mips}.c` (i386-only / module loader chưa thiết
kế / bridge MIPS cho overlay chưa cần) — `resolve_lp64.c`, `modules_lp64.c` (mới) thay thế: `resolve.c`
bản gốc giả định "guest address đã là host address" (sai dưới LP64, dùng bởi `libgs_ot.c`/`packets.c` —
nằm trong pipeline render mỗi frame); `modules.c` cần cho hệ thống module nạp động (password/overworld/
free_duel) chưa thiết kế cho LP64 — `modules_lp64.c` trả "0 module đã đăng ký" (đúng vì main_menu không
cần hệ thống này — bank 0, nối tĩnh như resident; chỉ password/overworld/free_duel mới cần, chưa hỗ trợ).

## Chưa xong — lý do dừng lại

- **618 unit, 154 KHÔNG compile dưới LP64** (tăng từ 50 vì bật lại đúng `-Werror` thay vì `-w` — số cũ
  50 là SAI, bị `-w` che bớt lỗi thật, đúng bài học T1.4i).
- **221 global data còn "mồ côi"** (không stub được): trộn nhiều nguyên nhân — cascading từ 154 file
  compile-lỗi (ví dụ `gGraphics_sViewportX` định nghĩa thật trong `graphics_frame.c`, đang lỗi compile);
  54 xung đột kiểu bị loại trừ có chủ đích (`gInput_wPad1Held/Pressed/Repeat`, `gDuel_bOpponentID`,
  `gDialog_bChoice`, ...); 4 hàm cầu nối MODEL.MRG (`func_801462B0` và tương tự, build_game32.py hard-code
  riêng, build.py chưa làm); các nhóm khác chưa phân loại hết.
- `build.py` dừng sạch tại bước link (không cố và không dump lỗi `ld` dài) — in rõ "221 global ... xem
  tmp/pc/macos-build/data-blockers.json".

## Tiếp tục phiên sau nữa (2026-10-07, cùng ngày) — rà 154 file compile-lỗi

Bắt đầu rà từng nhóm lỗi thật (không đoán). Phát hiện thêm 3 bug thật do chính phiên T1.5 phiên 3 gây ra
(không phải pre-existing — xác minh bằng `git stash` rồi build lại trên cây sạch, lỗi `ygo_types.h`
"array size negative" đã có SẴN trên cây sạch, không liên quan):

1. **Mảng 2 chiều bị cast sai**: `type_shape()` (T1.5 phiên 3) chỉ bóc 1 lớp mảng, nên với global 2D
   thật (`DuelResultSpriteSpec D_80090960[2][7]`) sinh cast `(DuelResultSpriteSpec[7] (*)[2])` — cú pháp
   C không hợp lệ (dán nguyên text `T[7]` vào chỗ cần kiểu phần tử đơn). Sửa: loại trừ hẳn mảng 2D+ khỏi
   wrap (8 symbol, nhóm mới `plain_excluded_multi_dim` trong `gen_globals.py`) thay vì viết cast lồng
   nhiều chiều đúng — quy mô nhỏ, không đáng xây.
2. **2 file native `src/pc/cards/{card_browse,rank_meter}.c` đọc thẳng pointer global đã wrap (từ T1.5
   phiên 2) vào biến cục bộ/field mà không qua `G2H`** — lộ ra chỉ sau khi phiên trước sửa xong 1 lỗi
   extern khác trong cùng file (compiler mới đi xa hơn tới dòng này). Sửa bằng bọc `G2H(...)` tại chỗ đọc
   — không cần `#ifdef` vì `G2H` dưới non-LP64 là no-op macro, bọc luôn an toàn cho cả 2 nhánh (khác hẳn
   15 file phiên trước, vốn cần `#ifdef` vì phải xoá hẳn dòng `extern`).
3. **Xác nhận (không sửa, để dành)**: phần lớn lỗi "member reference type 'gaddr' is not a pointer" còn
   lại (`func_8004DE24.c`, `model_load_step.c` — file `src/game`, cấm sửa tay) đúng là khoảng trống
   `transform_c_expressions` chưa quét `DeclRefExpr` cho pointer-array GLOBAL ở chỗ SỬ DỤNG (không phải
   chỗ khai báo) mà T1.5 phiên 1 đã tự ghi "để lại cho phiên T1.5 tiếp theo" (2026-10-06) — vẫn chưa ai
   viết. Đây là việc AST thật, quy mô tương đương phần `MemberRefExpr` đã xây cho field GPTR, không phải
   sửa nhanh được.

**Số liệu sau khi sửa 3 bug trên**: 149/618 unit compile lỗi (giảm từ 154), 222 global data blocker (tăng
1 so với 221 — đúng, vì 8 symbol mảng 2D giờ bị loại trừ tường minh thay vì wrap sai). Phân loại lại lỗi
compile còn lại theo nhóm (không đoán, đo bằng regex trên log thật):
- **~189 lần "cast to/from smaller integer type"**: đúng khoảng trống đã biết từ T1.4e ("con trỏ host
  thật ép xuống s32/u32 qua biến cục bộ") — ghi nhận từ 2026-10-02, chưa quyết hướng xử lý, KHÔNG phải
  việc mới.
- **18 lần "`png.h`/khác file not found"**: thiếu hẳn (`art.c`, `controls_art.c`, `glyphs.c`, `menu.c`,
  `texture_pack.c`, ...) — phụ thuộc `libpng`/`fontconfig` không nằm trong ADR-10's danh sách dependency
  cho phép (SDL3/FreeType/libclang/Python stdlib) — việc KHÁC HẲN ADR-03, chưa có hướng.
- **10 lần "array size negative"**: xác nhận PRE-EXISTING (test trên `git stash`, không liên quan phiên
  này) — struct layout nào đó lệch, chưa rõ nguyên nhân, ngoài phạm vi T1.10.
- **4 lần "member reference type gaddr"**: khoảng trống `DeclRefExpr` nói ở trên.

**Kết luận: phần việc còn lại để T1.10 link được KHÔNG CÒN LÀ "vài chỗ lặt vặt"** — là 2 khoảng trống kiến
trúc thật, biết từ lâu, quy mô đáng kể (T1.4e's "con trỏ host thật" + T1.5 phiên 1's "DeclRefExpr cho
pointer-array global"), cộng 1 việc phụ thuộc mới (`libpng`/`fontconfig`, ngoài ADR-10). Đề xuất: KHÔNG
tiếp tục đào sâu trong T1.10 nữa — mỗi khoảng trống xứng đáng một task riêng có plan/acceptance riêng.

## Đề xuất cho phiên sau (không làm trong phiên này)

1. Rà 154 file compile-lỗi (lý do thật, không phải `-w` nữa): nhiều khả năng trùng nhóm đã biết (apfn,
   GPTR_FN qua biến cục bộ, pointer-stride, 2-tầng gaddr) — đo lại cho khớp thực tế mới.
2. Rà 54 xung đột kiểu: quyết định hướng xử lý đúng ("thay thế TỪNG khai báo bằng macro khớp đúng kiểu
   tại chính file đó" — ADR-03 đã gợi ý, chưa làm).
3. 4 hàm MODEL.MRG bridge: thêm vào `build.py` giống `build_game32.py`'s `mapped +=` (toạ độ cố định, dễ
   copy).
4. Sau khi data_blocker về 0: link thật, `run`, xem điểm dừng thật là đâu (dự đoán: overlay `main_menu`,
   vì `src/overlays` chưa qua codemod biểu thức — vẫn đúng như plan ban đầu đã nêu).

## File tạo/sửa phiên này

- Tạo: `tools/pc/macos/build.py`, `src/pc/guest/resolve_lp64.c`, `src/pc/guest/modules_lp64.c`,
  `src/pc/compat/mods_disabled_lp64.c`, file report này.
- Sửa (dùng chung upstream, ghi Upstream touch log): `tools/pc/lp64/gen_globals.py`,
  `tools/pc/lp64/codemod.py`, 15 file `src/pc/**/*.c` (danh sách ở trên).
- Không commit: `tmp/lp64/`, `tmp/pc/macos-build/` (gitignore `/tmp/`).
