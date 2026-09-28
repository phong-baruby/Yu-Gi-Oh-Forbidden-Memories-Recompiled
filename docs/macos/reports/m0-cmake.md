# M0 — CMake portable target trên arm64 macOS (T0.4)

**Máy:** Mac mini M4, Apple clang 17.0.0, CMake 4.1.2, Ninja 1.13.1 (qua T0.2).
**Không sửa code nào** — đây chỉ là đo đạc theo yêu cầu T0.4.

## Lệnh dùng

```sh
cmake -S . -B tmp/pc/cmake-mac -G Ninja -DCMAKE_BUILD_TYPE=Debug
cmake --build tmp/pc/cmake-mac -- -k 0   # -k 0: build hết, không dừng ở lỗi đầu
ctest --test-dir tmp/pc/cmake-mac --output-on-failure
```

`CMakeLists.txt` không có nhánh riêng cho macOS/Darwin/arm64 (chỉ rẽ theo
`WIN32`/`MSVC` và `CMAKE_SYSTEM_NAME STREQUAL "Linux"`), nên toàn bộ kết quả
dưới đây là target rơi vào nhánh generic (POSIX-not-Linux) lần đầu tiên.

## Kết quả tổng

- **Configure:** thành công, không lỗi (tìm đủ ZLIB, PNG qua Homebrew, Python 3.14).
- **Build:** 195 bước, dừng ở 176 (ninja mặc định dừng sau lỗi; đã build lại
  với `-k 0` để thấy hết). **26 compile unit fail**, phần còn lại (~170 bước,
  gồm nhiều thư viện/executable test) build sạch.
- **ctest:** 59 test case đăng ký.
  - ✅ **27 passed**
  - ⏭️ **2 skipped** (chủ động, không liên quan macOS — xem mục "Khác" bên dưới)
  - ❌ **30 failed** (toàn bộ là "Not Run" — executable không build được, không
    phải test logic sai)

## Phân loại nguyên nhân (4 nhóm)

### 1. LP64 — struct layout static assert (nhóm lớn nhất)

`src/ygo_types.h` và các header vệ tinh trong `src/game/` (`display_object.h`,
`duel_card.h`, `duel_card_effects.h`, `duel_result_display.h`) dùng kỹ thuật
"mảng kích thước âm" để static-assert offset/size của struct khớp bản retail
32-bit (ví dụ `YGO_TYPE_OFFSET(LibraryMotionState, render) == 0x44`). Trên
arm64 LP64, con trỏ 8 byte thay vì 4 → struct chứa con trỏ phình to hơn offset
retail mong đợi → assert fail.

```
src/game/../ygo_types.h:463:5: error: 'LibraryMotionState_size_must_be_0x48'
  declared as an array with a negative size
```

Đây **đúng là vấn đề mà ADR-05 / T0.7 (prototype codemod GPTR) sẽ giải quyết**
— không phải lỗi bất ngờ, mà là xác nhận bằng số liệu thật cho lý do M1 cần
codemod.

**Test fail chỉ vì nhóm này:** `pc_card_drops`, `pc_deck_draft`,
`pc_yamyi_mods`, `pc_rank`.

### 2. ELF/GNU-only linker section attribute

`src/game/graphics_frame.h:182` và `src/game/display_object_helpers.h:60`
dùng `__attribute__((section(".data")))` / `__attribute__((section(".sdata")))`
— cú pháp tên section kiểu ELF. Clang trên Mach-O đòi cú pháp
`"SEGMENT,section"` (ví dụ `"__DATA,__data"`), nên báo lỗi thẳng:

```
error: argument to 'section' attribute is not valid for this target:
  mach-o section specifier requires a segment and section separated by a comma
```

Không liên quan LP64 — sẽ fail kể cả trên một target 32-bit Mach-O giả định.
Xuất hiện cùng lúc với nhóm 1 trong đơn vị biên dịch của `pc_rank`
(`duel_result_runtime.c`), không có test case nào fail *chỉ* vì lỗi này.

### 3. Linux-only mmap flag

`src/pc/mods/mods.c` và `src/pc/mods/object_loader.c` (code cổng của **dự án
này**, không phải file cấm sửa) dùng `MAP_FIXED_NOREPLACE` (chỉ có từ Linux
4.17+, macOS không có tương đương) và `MAP_ANONYMOUS` (macOS định nghĩa dưới
tên `MAP_ANON`):

```
src/pc/mods/mods.c:343:54: error: use of undeclared identifier 'MAP_FIXED_NOREPLACE'
src/pc/mods/mods.c:343:90: error: use of undeclared identifier 'MAP_ANONYMOUS'
```

**Test fail liên quan:** `pc_mods`, `pc_mods_manager`, `pc_mods_window`,
`pc_disc`, `pc_disc_capacity`, `pc_disc_failed_code` (6 case, từ 2 file nguồn).

### 4. Darwin libc: `mkdtemp` bị ẩn dưới `_POSIX_C_SOURCE` tường minh

15 file test (`game_files_test.c`, `fs_test.c`, `save_slots_test.c`,
`save_menu_test.c`, `deck_slots_test.c`, `cards_identity_test.c`,
`audio_replace_test.c`, `controls_config_test.c`, `controls_runtime_test.c`,
`controls_window_test.c`, `texture_pack_test.c`, cùng 4 file đã tính ở nhóm 3:
`disc_test.c`, `mods_test.c`, `mods_manager_test.c`, `mods_window_test.c`) đều
mở đầu bằng `#define _POSIX_C_SOURCE 200809L` rồi gọi `mkdtemp()`. Trên glibc
(Linux), macro này đủ để lộ `mkdtemp`. Trên libc của Darwin, việc định nghĩa
tường minh `_POSIX_C_SOURCE` lại **thu hẹp** phạm vi hiển thị và ẩn luôn
`mkdtemp` (cần thêm `_DARWIN_C_SOURCE`, hoặc không định nghĩa
`_POSIX_C_SOURCE` để dùng mặc định mở của Darwin).

```
tests/pc/game_files_test.c:87:12: error: call to undeclared function 'mkdtemp';
  ISO C99 and later do not support implicit function declarations
```

**Test fail liên quan (20 case chỉ vì lý do này, cộng 4 case ở nhóm 3 cũng
dính lỗi này trong chính file test của chúng):**
`pc_game_files_select/cancel/retry/remembered/moved/headless/override/
picker-failure/malformed/write-failure` (10), `pc_fs`, `pc_save_slots`,
`pc_save_menu`, `pc_deck_slots`, `pc_cards_identity`, `pc_audio_replace`,
`pc_controls_config`, `pc_controls_runtime`, `pc_controls_window`,
`pc_texture_pack`.

### Khác — skip chủ động, không phải lỗi macOS

`pc_rank_art` và `pc_font_art` tự thoát với `SKIP_RETURN_CODE 77` (quy ước
CTest cho "skip"), theo đúng thiết kế trong `CMakeLists.txt` — không phải do
thiếu hỗ trợ macOS, thường là do thiếu asset/tài nguyên tùy chọn trong checkout
trần này.

## Cộng dồn (khớp đúng 30 fail)

| Nhóm | Số test fail | Phân loại |
|---|---|---|
| 1. LP64 struct layout | 4 (chỉ nhóm 1) | LP64 |
| 2. Section attribute ELF-only | 0 riêng (đi kèm nhóm 1 ở `pc_rank`) | Linux/ELF-only |
| 3. mmap flag Linux-only | 6 | Linux-only |
| 4. `mkdtemp` ẩn trên Darwin | 20 (+4 trùng nhóm 3) | Linux-only (giả định glibc) |
| **Tổng fail** | **30** | |
| Skip chủ động (không phải lỗi) | 2 | Khác |
| Pass | 27 | |

## Giới hạn của report này

- Clang dừng ở 20 lỗi/file theo mặc định (`-ferror-limit=20`). Với các file đã
  chạm trần 20 lỗi trước khi thấy hết (đa số file ở nhóm 1), **có thể còn lỗi
  khác ẩn phía sau** chưa lộ ra — sẽ chỉ thấy khi nhóm lỗi đầu được sửa và build
  lại. Không coi 4 nhóm trên là danh sách đầy đủ tuyệt đối, chỉ là đầy đủ với
  những gì quan sát được ở lần build này.
- Không đụng tới file trong `src/game/`, `src/overlays/`, `src/psyq/`,
  `src/ygo_types.h`, `src/types.h` — chỉ đọc/quan sát lỗi, đúng luật bất biến #1.
- `tmp/pc/cmake-mac/` không commit (đã gitignore theo quy ước `tmp/`).

## Ý nghĩa cho T0.7 / Gate G0

Nhóm 1 (LP64) là nhóm lớn nhất và đúng như dự đoán trong ADR-05 — số liệu này
là baseline tham khảo tốt khi đánh giá kết quả prototype codemod ở T0.7: nếu
codemod xử lý sạch nhóm 1, phần lớn số fail ở đây sẽ biến mất. Nhóm 2–4 là các
vấn đề portability nhỏ, độc lập với LP64, sẽ cần xử lý riêng ở M1 (không nằm
trong scope T0.7).
