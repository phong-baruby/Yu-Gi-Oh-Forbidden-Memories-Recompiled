# M1 — T1.6: bảng con trỏ hàm (`g_fn_table`) + `GCALL` (ADR-04)

**Kết quả: hạ tầng GCALL xong và kiểm chứng được; phần ghi field GPTR_FN mở rộng đúng phạm vi đã
duyệt (gán trực tiếp bằng tên hàm literal). Phần ghi qua biến cục bộ/tham số trung gian (đổi kiểu biến,
lan sang chữ ký hàm) phát hiện giữa phiên, fen duyệt loại khỏi scope — để dành phiên T1.6 sau.**

## Khác biệt so với milestone/ADR-04 (đã hỏi fen, đã chốt)

1. **Acceptance đổi từ "build LP64 link được"** (milestone gốc) → test độc lập (`tests/pc/fn_table_test.c`,
   theo đúng khuôn `gptr_test.c`/`image_test.c`): T1.10 (build driver) chưa tồn tại, không có cách nào
   "link" toàn bộ game. Giống hệt tình huống T1.5 phiên 1.
2. **Cơ chế KHÔNG tái dùng được `image.c`'s `guest_call_target`/trap x86**: cơ chế ILP32 hiện có dựa vào
   RAM guest map không có quyền thực thi — gọi qua con trỏ hàm retail (chính là địa chỉ guest) fault tại
   `EIP == address`, handler tra `Memories_FunctionMap` rồi redirect EIP, hoàn toàn trong suốt với call
   site. arm64 macOS không tái tạo được (ADR-01 đã bác bỏ map RAM guest ở địa chỉ cố định, PIE bắt buộc).
   `GCALL` thay bằng tra cứu TƯỜNG MINH tại call site, tái dùng `MemoriesGuestFunction` (struct có sẵn,
   platform-trung-lập) nhưng KHÔNG tái dùng được code tiêu thụ của `image.c`.
3. **`gen_fn_table.py` không dùng được cách `build_game32.py` xác định "hàm nào có symbol thật"** (`nm`
   trên `.o` đã compile) vì chưa có build driver để compile trước — thay bằng xác minh qua libclang quét
   trực tiếp source (`src/game`, `src/psyq`, `src/pc/compat`, `src/pc/sdk`) cho một `FUNCTION_DECL` thật
   khớp tên, không tin suông cột `status` của `functions.csv`.
4. **Phát hiện giữa phiên (hỏi fen, đã chốt): field GPTR_FN không chỉ bị ĐỌC-rồi-GỌI mà còn bị GHI** ở
   nhiều nơi (`object->update = (DisplayObjectCallback)SomeDecompiledFunc;`), và ghi cần chiều NGƯỢC của
   GCALL (encode địa chỉ retail của hàm, không phải `H2G` — `H2G` chỉ nhận con trỏ trong `g_ram`/
   `g_scratch`, địa chỉ hàm thì không). Chia 2 lớp: (a) gán trực tiếp bằng tên hàm literal — **làm trong
   phiên này**, tra `functions.csv` lúc codemod, thay bằng hằng địa chỉ retail literal; (b) gán qua biến
   cục bộ/tham số trung gian (`duel_scene_battle.c`'s `cb`, `file_stream.c`'s tham số hàm `callback`) —
   cần đổi KIỂU biến/tham số thành `gaddr`, một dạng biến đổi MỚI (T1.3/T1.4/T1.5 chưa từng đổi kiểu biến
   cục bộ/tham số, chỉ field struct/global) — **fen duyệt loại khỏi phiên này**, để dành phiên T1.6 sau.

## Cơ chế: `Memories_GuestFunctionLookup` + `GCALL`

```c
/* gptr.h, dưới #ifdef MEMORIES_LP64 */
void (*Memories_GuestFunctionLookup(gaddr address))(void);
#define GCALL(type, address) ((type)Memories_GuestFunctionLookup(address))
```

`Memories_GuestFunctionLookup` (`fn_table_lp64.c`): binary search `Memories_FunctionMap` (cùng struct
`MemoriesGuestFunction` upstream ILP32 đã dùng, khai báo sẵn trong `image.h`), lọc theo
`Memories_ModuleIsResident` cho entry có `bank != 0` (M3, chưa cần cho M1 — mọi entry hiện tại đều
`bank=0`, luôn resident). Không tìm thấy: log địa chỉ + symbol gần nhất (tra `Memories_SymbolTable`, bảng
MỚI chỉ để phục vụ chẩn đoán này — `image.c`'s `report_guest_fault` không có, milestone acceptance của
T1.6 yêu cầu rõ) rồi `abort()`.

## Công cụ sinh bảng: `tools/pc/lp64/gen_fn_table.py`

Đọc `config/slus_01411/functions.csv` (1786 hàm), xác minh TỪNG tên bằng libclang quét
`game/*.c`, `psyq/*.c`, `pc/compat/*.c`, `pc/sdk/*.c` tìm `FUNCTION_DECL` có `is_definition()` thật khớp
tên (không tin suông cột `status`). Lưu ý kỹ thuật: `codemod.parse()` (dùng `PARSE_SKIP_FUNCTION_BODIES`)
khiến MỌI hàm báo `is_definition() == False`, kể cả hàm có thân thật trong chính file đang parse — phải
dùng `codemod.parse_code()` (parse đầy đủ) cho việc này.

| status | tổng | có định nghĩa C thật trong phạm vi quét |
|---|---|---|
| `matching_c` | 1134 | 1134 (100%) |
| `sdk_asm` | 591 | 219 (tái hiện native dưới `src/pc/compat`/`src/pc/sdk`, ví dụ `libgs.c`'s `GsSortFastSprite`) |
| `handwritten_asm` | 61 | 0 |

→ 1353 hàm thật + 433 stub (`Memories_Unimplemented`, hàm đã platform-trung-lập, dùng lại y nguyên từ
`build_game32.py`'s `stubs.c`) = 1786 entry trong `Memories_FunctionMap`. Output `tmp/lp64/gen/fn_table.c`
(gitignore, không commit).

## Bug sửa cùng phiên: `.type.kind == POINTER` không rút gọn typedef

Phát hiện khi mở rộng codemod cho field GPTR_FN: `DisplayObjectCallback fn = e->update;` không được sửa,
dù `field_pointee` trả đúng `is_fn=True`. Nguyên nhân: libclang báo `fn`'s `.type.kind` là `ELABORATED`
(không phải `POINTER`) cho một biến khai báo qua typedef con trỏ — chỉ `.type.get_canonical().kind` mới
đúng `POINTER`. Đây là bug CÓ TRƯỚC T1.6 (ảnh hưởng mọi nhánh `transform_c_expressions` so sánh
`.type.kind == POINTER` trực tiếp, 7 chỗ, cộng `is_pointer_like`), chỉ lộ ra lần này vì đây là lần đầu
`transform_c_expressions` gặp một biến cục bộ kiểu con trỏ khai báo QUA TYPEDEF (field GPTR dữ liệu
thường hầu hết gán vào biến `T *`, không qua typedef). Sửa cả 7 chỗ + `is_pointer_like` dùng
`get_canonical()`.

## Mở rộng codemod cho field GPTR_FN (`update`, `phase_callback`)

- **Đọc-rồi-gán vào biến cục bộ** (`VAR_DECL`, gán RHS trực tiếp): dùng `GCALL(pointee, x.f)` thay
  `(pointee)G2H(x.f)`.
- **Ép kiểu tường minh** (`(SomeType)object->update`): `GCALL` đã trả đúng kiểu `DisplayObjectCallback`,
  phép ép kiểu nguồn gốc giữ nguyên văn bản, giờ ép từ kiểu đó thay vì từ `void *` của `G2H`.
- **Gọi trực tiếp** (`q->phase_callback(q, ...)`): nhánh MỚI, dò bằng text (ký tự ngay sau extent của
  field là `(`) vì clang's error recovery gộp hẳn shape này xuống thành statement bao quanh, không còn
  `CALL_EXPR` — đúng như comment cũ trong code đã dự đoán ("left genuinely broken on purpose... until
  GCALL exists").
- **Ghi bằng tên hàm literal** (`classify_write_fn`, hàm MỚI): `x.f = (T)SomeDecompiledFunc;` → tra
  `functions.csv`, thay bằng `0x80xxxxxxu` (hằng số, tính lúc codemod — không phải runtime, vì không có
  cách viết static initializer gọi hàm runtime, và `H2G` không nhận địa chỉ mã). Không tìm thấy địa chỉ
  retail cho tên hàm → dừng hẳn (trường hợp PC-only cần dải `0x9F000000+`, chưa nối vào
  `gen_fn_table.py`). RHS không phải tên hàm literal/0 (biến cục bộ, tham số) → **không sửa** (khác với
  dừng hẳn — cùng cách xử lý "không có luật khớp" như nhóm con trỏ-đôi stride/2-tầng-gaddr đã biết từ
  T1.4, để file đó tự nhiên không compile sạch thay vì chặn cả batch).

## Kết quả đo

| | Trước T1.6 (T1.5 cuối) | Sau T1.6 |
|---|---|---|
| File `.c` compile sạch (`CODE_GLOBS`, 515 file) | 386 | 392 |
| Regression | — | 0 |
| File mới sạch | — | 6 (`dialog_update_choice.c`, `display_object_alpha_transition.c`, `display_parent_links.c`, `duel_draw_resolution.c`, `file_transfer_flags.c`, `func_8001D518.c`) |

`check_layouts_lp64.py`: 0 lệch. Idempotent: 2 lần `rm -rf` + chạy lại, byte-for-byte giống nhau.
`tests/pc/fn_table_test.c` (3 hàm retail thật + 1 callback native synthetic `0x9F000000`, cộng đường
abort khi tra trượt): pass. `ctest` toàn bộ: 30 lỗi pre-existing không đổi (xác nhận bằng `git stash`,
không liên quan T1.6 — `mkdtemp`/`MAP_FIXED_NOREPLACE` thiếu trên macOS, lỗi macOS-portability có trước
phiên này).

## Vấn đề mở để lại cho phiên T1.6 sau

- **Ghi field GPTR_FN qua biến cục bộ/tham số trung gian**: `duel_scene_battle.c`'s `cb`
  (`DisplayObjectCallback cb; cb = (DisplayObjectCallback)func_8001ED20; ...; o->update = cb;`, lặp
  nhiều lần), `duel_scene_card_placement.c` (tương tự), `file_stream.c`'s tham số hàm
  `FileTransferCallback callback` (lan qua chữ ký hàm + mọi nơi gọi). Cần: đo quy mô thật (bao nhiêu
  file/hàm), thiết kế cơ chế đổi kiểu biến cục bộ/tham số sang `gaddr` dựa theo cách dùng — ngoài phạm vi
  AST hiện tại của `transform_c_expressions` (chỉ quét `MEMBER_REF_EXPR`, không quét `VAR_DECL`/tham số
  hàm nói chung).
- **16 bảng "apfn" global đã loại trừ ở T1.5** (`gMain_apfnModeRunner`, ...): để bọc được bằng GPTR_FN
  (giờ GCALL đã tồn tại), cần thêm: (a) `global_wrapper_text` phát ra `GPTR_FN(pointee)` thay vì
  `GPTR(pointee)` khi pointee là kiểu hàm; (b) xử lý ĐỊNH NGHĨA THẬT của các bảng này (initializer list
  tên hàm literal, ví dụ `{FuncA, FuncB, ...}`) bằng CÙNG cơ chế tra-functions.csv-rồi-thay-hằng-số, nhưng
  cho `INIT_LIST_EXPR` thay vì phép gán đơn — AST shape khác, chưa viết.
- **11 symbol "orphan" function-pointer-typed khác** (không có định nghĩa thật trong phạm vi quét, ví dụ
  `D_80090F58`) — có thể bọc ngay bằng GPTR_FN (không có vấn đề initializer), nhưng CHƯA làm trong phiên
  này (gói chung với quyết định "dừng ở gán tên hàm literal", để đo/làm đồng thời với 16 bảng có định
  nghĩa cho nhất quán).

## File tạo/sửa phiên này

- Tạo: `tools/pc/lp64/gen_fn_table.py`, `src/pc/guest/fn_table_lp64.c`, `tests/pc/fn_table_test.c`,
  `docs/macos/reports/m1-fn-table.md` (report này)
- Sửa: `src/pc/guest/gptr.h` (`GCALL`), `src/pc/guest/image.h` (`MemoriesGuestSymbol`), `CMakeLists.txt`
  (đăng ký `pc_fn_table`), `tools/pc/lp64/codemod.py` (`load_function_addresses`, `classify_write_fn`,
  `field_is_fn`, mở rộng các nhánh đọc/gọi GPTR_FN, sửa bug `.type.kind`/`is_pointer_like`)
