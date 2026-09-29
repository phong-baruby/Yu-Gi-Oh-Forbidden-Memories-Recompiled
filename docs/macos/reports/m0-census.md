# M0 — Census LP64 bằng clang arm64 (T0.5)

**Lệnh:** `python3 tools/pc/lp64/census.py`
**Máy:** Mac mini M4, Apple clang 17.0.0 (target `arm64-apple-macos`).
**Không sửa code nào** — chỉ syntax-check (`-fsyntax-only`), đúng bản chất census.

Mỗi unit trong `src/game/*.c` + `src/overlays/*/*.c` được chạy:

```sh
clang --target=arm64-apple-macos -std=gnu11 -DMEMORIES_PC -D_LANGUAGE_C \
  -DLANGUAGE_C -ferror-limit=0 -fsyntax-only -w -Isrc <file>
```

Bộ define (`MEMORIES_PC`, `_LANGUAGE_C`, `LANGUAGE_C`) khớp đúng flags mà
`tools/pc/build_game32.py` dùng cho các unit này trên build thật, để census
phản ánh đúng điều kiện biên dịch thật thay vì một cấu hình tuỳ tiện.
`-ferror-limit=0` (bỏ trần 20 lỗi mặc định của clang) được thêm sau khi lần
chạy đầu cho thấy 425/546 file chạm trần — nếu giữ trần mặc định, số liệu lỗi
sẽ bị cắt cụt và không dùng làm baseline đáng tin được.

## Kết quả tổng — đây là baseline cho M1

**64 / 546 unit pass** (11.7%).

| Nhóm | Tổng unit | Pass | Fail |
|---|---|---|---|
| `src/game/*.c` | 514 | 60 | 454 |
| `src/overlays/*/*.c` | 32 | 4 | 28 |
| **Tổng** | **546** | **64** | **482** |

(Không có số liệu `tools/pc/host_census.py` cũ để so sánh — chưa từng chạy
trong workspace này. Con số ILP32 hiện có duy nhất là từ `notes/pc-build.md`
ghi ngày 2026-09-20: 465/546 pass ILP32 với GCC. Không so trực tiếp được vì
khác compiler (GCC 2.8.1-lenient vs Apple clang 17) và khác kiến trúc đích.)

## Top loại lỗi (chỉ có đúng 2 loại — không phải bị cắt bớt)

| # | Số lần | Loại lỗi |
|---|---|---|
| 1 | 27,811 | `'X' declared as an array with a negative size` — static assert offset/size struct trong `ygo_types.h` và các header vệ tinh (`display_object.h`, `duel_card.h`, `duel_card_effects.h`, `duel_result_display.h`, ...) fail vì con trỏ 8 byte trên arm64 làm struct phình to hơn offset retail 32-bit mong đợi. |
| 2 | 1,623 | `argument to 'section' attribute is not valid for this target: mach-o section specifier requires a segment and section separated by a comma` — `__attribute__((section(".data")))` / `(".sdata")` kiểu ELF trong `graphics_frame.h`, `display_object_helpers.h`; Mach-O cần cú pháp `"SEGMENT,section"`. |

Cả 2 loại này đã xuất hiện y hệt ở quy mô nhỏ hơn trong report T0.4
(`m0-cmake.md`) — census xác nhận đây là 2 nguyên nhân bao trùm gần như toàn
bộ diện fail của `src/game`/`src/overlays`, không có loại lỗi thứ 3 ẩn nào
khác nổi lên khi bỏ trần lỗi. (T0.4 còn thấy thêm 2 nhóm nữa — mmap flag
Linux-only và `mkdtemp` bị ẩn trên Darwin — nhưng cả 2 nằm trong
`tests/pc/*.c` và `src/pc/mods/*.c`, ngoài phạm vi census này chỉ quét
`src/game`/`src/overlays`.)

## Ý nghĩa

- Loại lỗi #1 (LP64 struct layout) chiếm **94.5%** tổng số lỗi (27,811 /
  29,434) và gần như chắc chắn là nguyên nhân khiến phần lớn 482 unit fail —
  đây chính xác là vấn đề ADR-05 / codemod `GPTR` (T0.7) nhắm tới giải quyết.
- Loại lỗi #2 (section attribute ELF-only) độc lập với LP64, quy mô nhỏ hơn
  nhiều (2 file nguồn), sẽ cần một `#if defined(__APPLE__)` riêng khi tới M1
  (không phải việc của codemod LP64).
- 64 unit đã pass ngay hôm nay (ví dụ `ai_script_source_line_format.c`,
  `duel_card_checks.c`, `duel_cursor_status.c`, `checkerboard_background.c`)
  — đa số là các unit không chạm struct con trỏ nặng hoặc section attribute,
  cho thấy không phải toàn bộ codebase đều cần codemod.
- Baseline này (64/546, 27,811 lỗi loại #1) là con số T0.7 nên đối chiếu sau
  khi chạy prototype codemod cho 5 struct: nếu codemod xử lý đúng, số lỗi
  loại #1 trên các struct đó phải giảm về 0 mà không phát sinh loại lỗi mới.

## Giới hạn

- Chỉ syntax-check (`-fsyntax-only`), không link, không kiểm tra hành vi,
  không kiểm tra địa chỉ cố định.
- `-w` tắt warning, chỉ đếm `error:`. Một file có thể còn nhiều warning không
  được phản ánh ở đây.
- Không đụng tới `src/game/`, `src/overlays/`, `src/psyq/`, `src/ygo_types.h`,
  `src/types.h` — đúng luật bất biến #1. `tmp/lp64/census.json` không commit
  (đã gitignore).
