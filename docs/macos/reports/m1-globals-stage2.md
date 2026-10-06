# M1 — T1.5 phiên 2: codemod cho global LÀ con trỏ/mảng con trỏ (ADR-03)

**Kết quả: T1.5 xong (trong phạm vi đã duyệt).** 80/111 symbol `pointer`/`pointer-array` đo được ở
phiên 1 đã được codemod hoá tự động; 31 symbol (16 bảng con trỏ hàm phát hiện mới + 4 "vừa extern vừa có
định nghĩa thật" + 11 "xung đột" đã biết từ phiên 1) loại trừ, có lý do rõ ràng, để lại cho T1.6 hoặc một
phiên T1.5 sau.

## Cơ chế: tái dùng `GPTR(T)` + field `.value`

Global LÀ con trỏ/mảng con trỏ (`GsOT *D_800E9D90[4]`) được viết lại thành:

```c
#ifdef MEMORIES_LP64
typedef struct { GPTR(GsOT) value[4]; } D_800E9D90_global_t;
#define D_800E9D90 (*(D_800E9D90_global_t *)G2H(0x800E9D90u)).value
#else
extern GsOT *D_800E9D90[4];
#endif
```

Điểm mấu chốt (xác nhận bằng prototype thật ở phiên 1, rồi xác nhận lại lúc code thật): field `value`
phải viết bằng macro `GPTR(T)` — KHÔNG được viết thẳng `gaddr` đã rút gọn — vì `field_pointee()` (cơ chế
tái dùng từ T1.3) đọc lại TEXT GỐC của khai báo field để suy ra `T`, và text đó chỉ còn `GPTR(T)` chứ
không còn `T` một khi macro đã rút gọn tay. Mọi use site `D_800E9D90[idx]`/`D_800E9D90[idx] = p` sau đó
tự động được `transform_c_expressions` đã có (T1.3/T1.4) phân loại đúng, không cần sửa engine AST.

## Công cụ: `gen_globals.py` sinh `canonical`, `codemod.py` tiêu thụ

`gen_globals.py` sinh thêm field `"canonical"` (địa chỉ, `is_array`, kiểu trỏ tới, kích thước mảng) cho
mỗi symbol `pointer`/`pointer-array` hợp lệ — vào `tmp/lp64/gen/globals_census.json` (gitignore, không
commit). `codemod.py` thêm `load_globals()`, `global_wrapper_text()`, `collect_global_edits()`; `--globals`
(mặc định đúng đường dẫn trên) nạp map này và truyền vào cả hai vòng lặp của `main()` (header và `.c`).

## Phát hiện giữa chừng: 31/111 symbol không dùng được cơ chế này — loại trừ, hỏi fen

Compile sweep đầu tiên với đủ 111 symbol lộ ra 2 nhóm không nằm trong phạm vi ADR-03 đơn thuần (hỏi fen
qua `AskUserQuestion`, cả hai được duyệt loại trừ):

1. **16 symbol là bảng con trỏ hàm** (đặt tên "apfn": `gMain_apfnModeRunner`, `gAiScript_apfnCommand`,
   `gDuelEffect_apfnGroupHandler`, ... cộng `D_80090F58` phát hiện sau vì nó mồ côi — không có định
   nghĩa thật trong phạm vi quét nên không lọt vào nhóm "có định nghĩa thật" ban đầu). Gọi qua bảng này
   (`gMain_apfnModeRunner[v & 0x1F]()`) cần con trỏ hàm native thật phục hồi từ guest storage — đúng
   ADR-04/T1.6, chưa xây. Bọc bằng macro gaddr đơn thuần sinh lỗi "called object type 'gaddr' is not a
   function" ở cả nơi định nghĩa lẫn mọi nơi gọi — lan ra ~35 file nếu không loại trừ.
2. **4 symbol con trỏ dữ liệu thường vừa `extern` trong header vừa có định nghĩa thật trong `.c`**
   (`D_8009AF18`, `D_8009AF88`, `D_8009B074`, `gFile_apszName`): bọc cả hai bên sinh 2 `typedef` trùng
   tên trong cùng 1 translation unit; định nghĩa thật (`= &gFile_PrimaryTransferDescriptor;`) mất chỗ
   lưu trữ khi `NAME` thành macro — cần cơ chế khởi tạo khác (có thể: hàm chạy lúc startup ghi giá trị
   vào guest RAM), chưa thiết kế.

Tiêu chí loại trừ trong `gen_globals.py`'s `canonical`: bất kỳ symbol nào có `pointee` chứa `"("`
(kiểu hàm) HOẶC có định nghĩa C thật ở đâu đó — loại cả hai, không chỉ loại theo "có định nghĩa".

## Bug phát hiện khi code thật: `binop_operator`/`unary_operator` câm lặng trên macro

`cursor.get_tokens()` (cách cũ lấy token toán tử `=`/`++`/...) trả về RỖNG bất cứ khi nào cursor cắt
ngang biên macro expansion — đúng tình huống MỌI lần dùng global T1.5 (bản thân nó là 1 macro giống
đối tượng). Hậu quả: MỌI phép gán trực tiếp `GLOBAL = thật;` bị bỏ qua lặng lẽ (không lỗi dừng hẳn, chỉ
để nguyên — compiler sau đó báo "incompatible pointer to integer conversion", không phải crash của
codemod). Sửa: đọc toán tử thẳng từ `data` giữa 2 khoảng LHS/RHS (văn phạm C đảm bảo không có gì khác ở
đó) thay vì dựa vào tokenizer của libclang. Đây KHÔNG xảy ra với field struct T1.3/T1.4 vì field luôn
truy cập bằng cú pháp `.f` thật trong source, không qua macro riêng.

## Override mới cần thêm (phát hiện qua sweep thật, không đoán)

- **Macro-argument trên global** (đã biết từ T1.4, giờ gặp lại với global thay vì field): `VIEW_MACRO(D_xxx)`
  truyền global qua 1 macro function-like khác luôn làm mất extent — fix bằng cách inline macro, bọc
  `G2H`/`H2G` trực tiếp, bỏ lớp macro ngoài. ~25 override loại này across nhiều file.
- **`GLOBAL = SOMEMACRO(arg)`** (macro ở RHS gán): cùng lớp, không chỉ G2H-bọc đối số bên trong — phải
  bỏ hẳn macro ngoài vì bản thân việc LÀ đối số macro mới là vấn đề, không phải nội dung đối số.
  (`duel_scene_battle.c`, `duel_scene_field_actions.c`, `duel_scene_hand_actions.c`, `func_800323F8.c`)
- **Nested edits** (đã biết từ T1.4): global vừa đọc vừa ghi trong cùng 1 câu lệnh
  (`file_transfer_runtime.c`'s `D_8009B0F8 = (u32 *)((u8 *)D_8009B0F8 + n);`).
- **AST "mù" trên `global->field = real_ptr;`** (MỚI, chưa gặp ở T1.3/T1.4): clang's error recovery gộp
  cả chuỗi `((Cast *)G2H(GLOBAL))->field` thành 1 `UNEXPOSED_EXPR` duy nhất khi field đó cũng là gaddr,
  không còn `MEMBER_REF_EXPR` riêng cho field để `classify_write` bắt được — xác nhận bằng cách đi bộ
  AST trực tiếp (`func_800218F0.c`'s `root`/`children[N]`, `duel_phase_entry.c`'s
  `gDuel_apSwordsEffectObjects[idx]->field_1A`, `sound_secondary_commands.c`'s `field_050C` — field này
  còn là `GPTR_FN`, override giữ nguyên hành vi `G2H` đã có từ trước T1.5 cho field hàm, không phải
  cách làm mới, chỉ bảo toàn parity với baseline).
- **gaddr tính bằng số học rồi ép kiểu không qua G2H** (đã biết từ T1.4j, lần này nhiều điểm trong 1 file
  `movie_frame_pipeline.c`, global vô hướng `D_8009B498` cộng offset rồi ép `(T *)`/gán thẳng vào biến
  con trỏ — G2H trả `void *`, số học `void * + int` hợp lệ C nên chỉ cần bọc tên định danh trần).
- Thứ tự pass: `fix_offsetof_casts` chạy TRƯỚC `apply_overrides` — override cho văn bản chứa
  `(u32)&(...)` phải viết sẵn dạng ĐÃ sửa (`(u32)(uintptr_t)&(...)`), lặp lại đúng bug đã gặp ở T1.4j.

## Kết quả đo

| | Trước T1.5 phiên 2 (baseline, không bọc global nào) | Sau T1.5 phiên 2 |
|---|---|---|
| Header xử lý | 586 | 586 |
| Field/global transform | 494 | 568 |
| File `.c` compile sạch (`CODE_GLOBS`, 515 file) | 376 | 386 |
| Regression (đã sạch, giờ hỏng) | — | 0 |
| File mới sạch | — | 10 |

10 file mới compile sạch: `fade_runtime.c`, `duel_effect_request_update.c`,
`duel_effect_process_entries.c` (và 7 file khác trong danh sách "ADR-03" cũ của PROGRESS.md — xem mục
"Vấn đề mở" đã cập nhật). `check_layouts_lp64.py`: 0 lệch. Idempotent: 2 lần chạy liên tiếp từ `rm -rf`,
byte-for-byte giống nhau. `ctest`/`cmake --build tmp/pc/cmake-mac`: build đã hỏng từ trước T1.5 (lỗi
`MAP_FIXED_NOREPLACE`/`MAP_ANONYMOUS` không tồn tại trên macOS trong `src/pc/mods/mods.c`, tái hiện y hệt
khi `git stash` hết thay đổi của phiên này) — không liên quan T1.5, không phải regression, không sửa
(ngoài phạm vi task).

## File tạo/sửa phiên này

- `tools/pc/lp64/gen_globals.py` — thêm `canonical`, 2 lớp loại trừ (hàm, định nghĩa thật trùng lặp)
- `tools/pc/lp64/codemod.py` — `load_globals`/`global_wrapper_text`/`collect_global_edits`;
  `transform_bytes`/`transform_code_file`/`transform_file`/`main()` nhận `globals_map`; sửa
  `binop_operator`/`unary_operator` đọc toán tử từ `data` thay vì `cursor.get_tokens()`
- `config/lp64/overrides.toml` — ~35 override mới (macro-argument trên global, nested edits, AST-mù
  trên field lồng, số học-rồi-ép-kiểu)
- `docs/macos/reports/m1-globals-stage2.md` — report này
