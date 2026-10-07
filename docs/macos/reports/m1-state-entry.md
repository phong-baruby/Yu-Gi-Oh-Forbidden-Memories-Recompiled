# M1 — T1.7: entry VSync và stack game trên arm64

**Kết quả: xong, trong phạm vi đã duyệt.** `VSync` chạy đúng qua trampoline AAPCS64 trên stack riêng
cấp bằng `mmap` (không cố định địa chỉ) kèm guard page. Save state thật (đọc/ghi file) không làm — để
dành T4.1 theo đúng ADR-08.

## Khác biệt so với milestone/ADR-08 (đã hỏi fen, đã chốt)

1. ADR-08 (tiêu đề "Save state trên binary PIE — Proposed, chốt T4.1") vẫn dùng được: chỉ cần phần định
   nghĩa thanh ghi (`x19–x28, x29, x30, sp, d8–d15`), không đụng phần rebase/relocate ("Proposed").
2. **Phạm vi hẹp hơn lo ngại ban đầu.** `state.c` (1052 dòng) phần lớn là máy save/load
   (`serialize`/`apply`/`load`/`relocate`/`rewind`) — chỉ chạy khi có request
   (`Memories_StateRequest`), mà M1 không ai gọi. Đổi tên field `esp`→`sp` (dùng chung tên cho cả 2 kiến
   trúc, x86 build không đổi hành vi) khiến `from_game_code()` (hàm DUY NHẤT trong đường chạy MỌI frame)
   tự nhiên luôn `false` dưới LP64 — vì `STACK_BASE`/`STACK_TOP` vẫn là địa chỉ cố định kiểu x86, `sp`
   thật (từ `mmap(NULL, ...)`) không bao giờ rơi vào đó — `Memories_StatePoint` tự động no-op, **không
   cần bọc `#ifdef`/sửa logic nào trong toàn bộ phần save/load**.

## Lỗi thật khi compile `state.c` dưới `-DMEMORIES_LP64 -arch arm64` (phát hiện bằng cách tự biên dịch
trước khi sửa, không đoán)

- `<ucontext.h>` của macOS từ chối khai báo `getcontext`/`makecontext`/`swapcontext` nếu không có
  `_XOPEN_SOURCE` — API vẫn hoạt động đúng trên arm64 (đã biết từ trước, xem PROGRESS.md), chỉ là macro
  hiển thị bị thiếu.
- `_XOPEN_SOURCE` riêng lại ẨN `MAP_ANON`/`MAP_ANONYMOUS` (chế độ POSIX nghiêm ngặt loại BSD extension) —
  cần thêm `_DARWIN_C_SOURCE` nữa mới có cả hai cùng lúc.
- `MAP_FIXED_NOREPLACE` không tồn tại trên macOS (đã biết từ T0.6).
- `-Wmissing-field-initializer` (2 chỗ `MemoriesState state = {1, NULL, ...};` thiếu field `buffer`) —
  không liên quan LP64, chỉ lộ ra vì đây là lần ĐẦU TIÊN `state.c` được compile dưới cờ `-Werror` đầy đủ
  của dự án (chưa từng được link vào CMake test nào trước T1.7) — sửa luôn (thêm field thiếu, hành vi
  không đổi vì C đã zero-init ngầm).

## Bug phát hiện giữa phiên: `build_game32.py`'s `NATIVE` glob cuốn luôn file macOS-only

`glob.glob("src/pc/guest/*.[cS]")` không lọc theo tên — mọi file macOS-only cùng thư mục (đúng quy ước
CLAUDE.md cho phép, `*_lp64.*`/`*_arm64.*`) bị cuốn vào build i386: `gptr_lp64.c`/`image_lp64.c` (từ
T1.1/T1.2) ĐÃ bị cuốn từ trước — chưa ai thấy vì máy này không có toolchain i386 Linux/Windows để tự
chạy `build_game32.py` kiểm tra. Thêm `state_arm64.S` sẽ là lần thứ 3. Sửa glob loại tên có `_lp64.`/
`_arm64.` — xác minh bằng cách import trực tiếp module Python, in `NATIVE`, kiểm không còn file nào
khớp. Ghi vào Upstream touch log (PROGRESS.md).

## Cơ chế: `state_arm64.S`

Offset field khớp `offsetof` thật (kiểm bằng chương trình C nhỏ, không chỉ tính tay):
`x19..x28` tại 0..72, `x29/x30/sp` tại 80/88/96, `d8..d15` tại 104..160, tổng 168 byte.

```asm
_VSync:
    adrp x9, _Memories_StateEntry@PAGE
    add  x9, x9, _Memories_StateEntry@PAGEOFF
    stp  x19, x20, [x9, #0]
    ... (x21..x28, x29/x30, sp, d8..d15)
    b    _Memories_VSync        /* b, không bl -- giữ x30 (lr) của caller */

_Memories_StateReturn:          /* (entry, value): x0=entry, w1=value */
    ldp  x19, x20, [x0, #0]
    ... (khôi phục hết)
    mov  w0, w1
    mov  sp, x10
    ret                          /* nhảy tới x30 vừa khôi phục */
```

Mach-O luôn cần tiền tố `_` (không như `state_i386.S`'s `SYMBOL()` macro chỉ thêm cho `_WIN32`) — viết
thẳng, không qua macro, vì file này chỉ target Mach-O.

## `Memories_StateRunGame`: mmap không cố định địa chỉ + guard page

```c
#ifdef MEMORIES_LP64
    long page = sysconf(_SC_PAGESIZE);
    void *region = mmap(NULL, (size_t)page + STACK_SIZE, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    mprotect(region, (size_t)page, PROT_NONE);   /* guard page, dưới cùng */
    stack = (char *)region + page;
#else
    stack = mmap((void *)STACK_BASE, STACK_SIZE, ..., MAP_FIXED_NOREPLACE | ...);  /* không đổi */
#endif
```

Nhánh `ucontext` (POSIX, macOS dùng chung) giữ nguyên 100%, dùng `stack` bất kể nhánh nào tạo ra nó.

## Test: `tests/pc/state_test.c`

Không link `state.c` thật (kéo theo cả cây phụ thuộc mods/spu/deck_menu/crash — không cái nào liên quan
T1.7) — tự cấp `Memories_StateEntry` + bản mmap/guard-page/ucontext RIÊNG (giống cách `gptr_test.c`/
`fn_table_test.c` tự cấp `ram`/`scratch`/bảng hàm riêng), chỉ link `state_arm64.S` thật. `entry_point()`
chạy trên stack game, gọi `VSync(0)` lặp 1000 lần (không đệ quy — đúng mẫu game thật: main loop gọi lại
từ CÙNG một điểm mỗi frame), mỗi lần `Memories_VSync` (bản test, không phải bản thật `libetc.c`) tăng
`frame_count` rồi `Memories_StateReturn` ngay. 10 biến cục bộ cộng dồn số khác nhau qua 1000 vòng — nếu
assembly làm sai 1 trong 10 thanh ghi callee-saved x19-x28, canary sẽ sai sớm trước khi tới vòng 1000.
Chạy thêm dưới ASan (không bắt buộc, chỉ kiểm tra thêm): pass, chỉ có warning đã biết của ASan với
`ucontext` (stack switch không được ASan theo dõi đúng, vấn đề tool đã biết, không phải lỗi thật).

`CMakeLists.txt`: cần thêm `ASM` vào `project(... LANGUAGES C ASM)` — project trước giờ chỉ có `C`,
chưa từng cần compile file `.S` qua CMake (file `.S` khác, `state_i386.S`, chỉ dùng trong
`build_game32.py`, không qua CMake).

## Kết quả

`ctest` toàn bộ: 30 lỗi pre-existing không đổi (so khớp TÊN test, không chỉ số — số thứ tự lệch vì test
mới chèn giữa danh sách). `pc_state` mới: pass. `pc_gptr`/`pc_fn_table`: vẫn pass (không regression).
`state.c` compile sạch dưới `-DMEMORIES_LP64 -arch arm64 -Wall -Wextra -Wpedantic -Werror` (lần đầu tiên
được xác minh dưới cờ đầy đủ này).

## File tạo/sửa phiên này

- Tạo: `src/pc/guest/state_arm64.S`, `tests/pc/state_test.c`, `docs/macos/reports/m1-state-entry.md`
- Sửa: `src/pc/guest/state.h` (`MemoriesStateEntry` 2 nhánh, field `sp` dùng chung tên), `src/pc/guest/state.c`
  (`_XOPEN_SOURCE`/`_DARWIN_C_SOURCE`/pragma deprecate, đổi 7+ chỗ `.esp`→`.sp`, nhánh mmap LP64,
  2 struct initializer thiếu field), `tools/pc/build_game32.py` (lọc `_lp64.`/`_arm64.` khỏi `NATIVE`,
  ghi Upstream touch log), `CMakeLists.txt` (`LANGUAGES C ASM`, đăng ký `pc_state`)
