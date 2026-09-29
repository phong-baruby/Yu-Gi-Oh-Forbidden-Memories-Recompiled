# Kiến trúc port macOS arm64 (ADR)

Mỗi ADR có trạng thái **Accepted** (đã chốt), **Proposed** (cần xác nhận bằng một task discovery) hoặc **Superseded**. Khi một task làm thay đổi quyết định, cập nhật ADR ở đây và ghi thêm một dòng vào "Decision log" trong PROGRESS.md.

---

## ADR-01 — Mô hình bộ nhớ: guest pointer 32-bit trên host 64-bit — Accepted
**Bối cảnh.** Upstream build ILP32: con trỏ trong struct game là 4 byte và bằng đúng host pointer, vì RAM guest được map tại `0x80000000` (`src/pc/guest/image.c`). Trên macOS arm64, `__PAGEZERO` 4GB là bắt buộc nên không map được vùng thấp; Rosetta không chạy code 32-bit; macOS cũng không có ABI ILP32 (x32).
**Quyết định.** Build `MEMORIES_LP64`: RAM guest (2MB) và scratchpad được cấp phát ở đâu cũng được. Mọi con trỏ nằm **bên trong dữ liệu guest** (field struct, phần tử mảng, word trong RAM) được lưu bằng `uint32_t` guest address. Còn biến cục bộ và tham số hàm trong code C có thể vẫn là host pointer (`T *`) khi codemod chứng minh được giá trị không bị lưu ngược vào guest.
**Hệ quả.** Layout struct LP64 giống hệt i386, và điều này kiểm chứng được bằng máy (ADR-11, T1.3). RAM guest của bản LP64 giống từng byte với reference build, nên dùng làm oracle được. Cái giá là mọi chỗ đọc/ghi field con trỏ đều phải qua `G2H`/`H2G`, và việc đó do codemod đảm nhận (ADR-05).

## ADR-02 — Dịch địa chỉ — Accepted
```c
/* src/pc/guest/gptr.h — mọi build đều include file này */
#ifdef MEMORIES_LP64
typedef uint32_t gaddr;
#define GPTR(T) gaddr
extern uint8_t *g_ram;       /* 2 MiB */
extern uint8_t *g_scratch;   /* scratchpad */
static inline void *G2H(gaddr a) {
    uint32_t phys = a & 0x1FFFFFFFu;               /* bỏ KSEG0/KSEG1 */
    if ((phys - 0x1F800000u) < 0x400u) return g_scratch + (phys - 0x1F800000u);
    return g_ram + (phys & 0x1FFFFFu);             /* mirror vật lý */
}
gaddr H2G(const void *p);   /* chỉ nhận con trỏ nằm trong g_ram/g_scratch hoặc NULL; ngoài vùng thì abort kèm log */
#else
#define GPTR(T) T *
#define G2H(a) ((void *)(a))
#define H2G(p) (p)
#endif
```
Phép mask thay thế toàn bộ cơ chế trap/decode lệnh x86 mà `image.c` dùng cho vùng mirror `0x10000..0x200000`. `NULL` guest là `0`, và `G2H(0)` phải trả về `NULL` (xử lý riêng trường hợp này). Kích thước scratchpad đúng là 1KB; upstream map cả trang 4KB, nên cần xác minh trong T1.1.

## ADR-03 — Biến global của game — Accepted (chốt ở T0.6, xem `docs/macos/reports/m0-build-anatomy.md`)
**Bối cảnh (đã sửa sau T0.6 — bản cũ nói sai).** Upstream **không** link phần lớn biến game tại địa chỉ retail. Có hai cơ chế tách biệt: (1) `FIXED_SECTIONS` (`game_text=0x01000000`, `game_data=0x04000000`, `game_bss=0x05000000`, `build_game32.py:123-124`) — địa chỉ **tự chọn của build, không phải retail** — nơi code/data C đã biên dịch của build này nằm, cố định chỉ để save-state giữ được con trỏ native ổn định qua rebuild; dựa vào `-fno-pie` (tắt PIE) và `-Wl,--section-start` (cú pháp GNU `ld`). (2) `guest_symbols.ld` (từ `config/pc/guest_addresses.txt`) — pin **giá trị đúng địa chỉ retail** `0x800xxxxx` cho các symbol được tham chiếu nhưng chưa có định nghĩa trong build (ví dụ biến của overlay chưa link); hoạt động được như con trỏ thật vì RAM guest đang map tại `0x80000000` (ADR-01).
**Vì sao vẫn chọn "global sống trong RAM guest".** Cơ chế (1) — dùng cho đa số global — không tái tạo được trên arm64 macOS: PIE bắt buộc (không tắt được), `ld64` không có `--section-start` cùng hình dạng. Mô phỏng lại y hệt sẽ cần một cơ chế địa chỉ-cố-định-song-song thứ hai chỉ cho macOS. Đưa toàn bộ global vào RAM guest dùng lại đúng `G2H`/`H2G` mà ADR-01/02 đã cần cho pointer field — chỉ một cơ chế duy nhất cho cả field lẫn global, thay vì hai.
**Quyết định.** Trong build LP64, biến global của game **sống trong RAM guest**. Codemod biến `extern T gFoo;` thành một lvalue macro `(*(T *)G2H(0x800xxxxx))`, còn `&gFoo` trở thành guest address. Biến đã có định nghĩa C thật (đa số) giữ nguyên giá trị khởi tạo viết trong source đã decompile; biến "mồ côi" (không được unit nào trong build định nghĩa, ví dụ thuộc overlay khác) lấy giá trị từ PS-X EXE trên disc (copy vào RAM guest lúc load). Cách nạp cụ thể (đọc thẳng từ EXE hay giữ bảng init sinh từ build) để T0.7/M1 quyết định khi hiện thực codemod — cả hai cho cùng kết quả giá trị.

## ADR-04 — Con trỏ hàm lưu trong dữ liệu guest — Accepted
Field `GPTR(fn)` lưu **địa chỉ retail** của hàm. Bảng `g_fn_table` (địa chỉ → host function) được sinh từ `functions.csv` và `guest_addresses.txt`, sort sẵn để tra bằng binary search. Mọi lời gọi qua con trỏ lấy từ guest đều đi qua `GCALL(type, addr)(args...)`. Hàm native chỉ có ở PC mà vẫn được cài vào struct guest (ví dụ primitive driver của LIBGS) được cấp **địa chỉ tổng hợp** trong dải `0x9F000000 + index`. Dải này nằm ngoài vùng RAM/mirror, và index cố định theo tên hàm để save state không bị lệch.

## ADR-05 — Codemod thay vì diff — Accepted
LP64 là một **phép biến đổi được mã hoá**, chứ không phải một bộ patch. `tools/pc/lp64/codemod.py` dùng libclang (Python binding, đúng phong cách tools của upstream). Nó đọc `src/`, ghi kết quả vào `tmp/lp64/src/`, và build LP64 compile từ cây output đó. Những chỗ không tự suy ra được được khai báo trong `config/lp64/overrides.toml` theo `file + function + pattern` (không theo số dòng) để sống sót qua các lần sync upstream. Tiêu chí thành công: sync upstream thì chỉ cần chạy lại codemod; override mới chỉ phát sinh khi upstream thêm pattern mới.
Các biến đổi chính:
1. Field con trỏ trong struct/union → `GPTR(T)`.
2. Đọc field con trỏ → `((T *)G2H(x.f))`; ghi field con trỏ → `x.f = H2G(p)`.
3. Hằng số ép kiểu con trỏ `(T *)0x800xxxxx` → `(T *)G2H(0x800xxxxx)`.
4. Số học con trỏ trên field guest: tính trên host pointer rồi `H2G` lại.
5. Global → theo ADR-03.
6. Gọi qua con trỏ hàm lấy từ guest → `GCALL`.
7. (M5) Định nghĩa hàm game `foo` → `foo__impl` cộng với stub dispatch (ADR-06).

## ADR-06 — Hook mod bằng dispatch stub — Accepted
Apple Silicon áp W^X cho `__TEXT`, nên cách patch `jmp *slot` vào NOP (`src/pc/mods/hooks.c`, `-fpatchable-function-entry`) không dùng được. Thay vào đó, mỗi hàm game hook được có một stub assembly sinh tự động:
```asm
_foo:  adrp x16, _foo__slot@PAGE
       ldr  x16, [x16, _foo__slot@PAGEOFF]
       br   x16
```
`_foo__slot` mặc định trỏ tới `_foo__impl`. Hook chỉ ghi vào slot (vùng data), và chain hook giữ nguyên ngữ nghĩa của upstream (hook cuối cùng được gọi đầu tiên, `original` dẫn về hook trước đó). Stub dùng `x16` (IP0) nên không làm hỏng tham số. Backend mới đặt trong `src/pc/mods/hooks_arm64.c`; `hooks.c` của upstream giữ nguyên.

## ADR-07 — Code mod: loader ELF AArch64 + bộ nhớ JIT — Accepted
Upstream: một mod là **một object file** (`notes/portable-mods-plan.md`), do `src/pc/mods/object_loader.c` tự load và relocate, và mod chỉ được gọi một danh sách libc cố định (`mod_libc.c`, `exports.h`).
Cho macOS:
- Mod build bằng `clang --target=aarch64-none-elf -fno-pic -ffreestanding` (vẫn dùng định dạng ELF .o để loader dùng chung khung). Header SDK cũng đi qua codemod để mod thấy `GPTR`.
- Relocation cần hỗ trợ: `R_AARCH64_ABS64`, `PREL32`, `CALL26`/`JUMP26` (kèm veneer island khi đích xa hơn ±128MB), `ADR_PREL_PG_HI21`, `ADD_ABS_LO12_NC`, `LDST{8,16,32,64,128}_ABS_LO12_NC`. Nếu mod build ra relocation GOT thì báo lỗi rõ ràng, không đoán.
- Bộ nhớ code: `mmap(MAP_JIT)` rồi `pthread_jit_write_protect_np(0)` → ghi → `(1)` → `sys_icache_invalidate`.
- Mod i386 dạng binary **không** chạy được; mod có source thì build lại. Đây là một khác biệt ABI phải ghi rõ trong README macOS.
- Trên arm64 không có `__divdi3`; `mod_libc.c` đã có guard `__i386__` cho phần này.

## ADR-08 — Save state trên binary PIE — Proposed (chốt ở T4.1)
Upstream lưu RAM guest, biến của game, **stack game kèm return address native** và thanh ghi callee-saved lúc gọi `VSync`, và dựa vào việc code/stack nằm ở địa chỉ cố định (`src/pc/guest/state.h`). macOS arm64 bắt buộc PIE và ASLR.
**Hướng mặc định.** Header state ghi thêm `arch = "arm64-lp64"`, text/data range và slide của image, cùng base của stack game. Khi load, mọi word 8-byte (căn 8) trong chunk `stack` rơi vào text/data range cũ được cộng delta; tận dụng cơ chế remap (`Memories_StateRemapRange`) và "startup image" sẵn có. RAM guest không cần rebase (ADR-01). Entry được lưu theo AAPCS64: x19–x28, x29 (fp), x30 (lr), sp, d8–d15. Không bao giờ đụng x18 (thanh ghi platform của Apple). Load state có `arch` khác thì từ chối kèm thông báo rõ ràng.

## ADR-09 — Platform layer — Accepted
- Chỉ dùng backend SDL3 (`sdl.c`); bỏ qua X11, ALSA và evdev trên macOS.
- Giữ SIGALRM/`setitimer` (macOS hỗ trợ). Chỉ phần đọc PC lấy từ `ucontext` được port qua header `src/pc/compat/mcontext.h`: `uc_mcontext->__ss.__pc` / `__sp` / `__fp`.
- Cần xác minh (T1.8): Cocoa yêu cầu event loop chạy trên main thread, trong khi upstream chạy game trên một **stack riêng** ngay trên main thread. Nếu `SDL_PollEvent` gặp vấn đề khi chạy trên stack đó, phương án B là bơm event từ stack gốc tại điểm VSync.
- Đường dẫn user: `~/Library/Application Support/YFM-Recompiled/`. Font: bundle sẵn một TTF (không có fontconfig trên macOS).

## ADR-10 — Build và dependency — Accepted
- Build driver riêng `tools/pc/macos/build.py` (Python, cùng phong cách `build_game32.py`). Không sửa `build_game32.py`, nhưng tái sử dụng được logic bằng cách import nếu nó tách hàm được.
- Toolchain: Apple clang cho build game (Mach-O arm64). Homebrew `llvm` chỉ dùng cho libclang (codemod) và `aarch64-none-elf` (build mod).
- SDL3 được build **từ source, pin đúng version upstream đang dùng** (3.4.16) cùng FreeType, link static. `.app` phát hành không phụ thuộc runtime vào Homebrew.
- Dependency cho phép: SDL3, FreeType, libclang (tool), Python stdlib. Mọi thứ khác phải hỏi trước.

## ADR-11 — Oracle: tương đương từng byte với reference build — Accepted
Reference là bản i386 Linux **build từ cùng commit của fork** (đường i386 vẫn còn nguyên nhờ luật 2 trong CLAUDE.md), chạy trên máy Linux x86 (VPS, hoặc Docker `linux/386` qua QEMU trên Mac). Hai build cùng chạy một input script với clock theo frame, và cứ mỗi N frame dump hash của RAM guest + scratchpad (+ VRAM của soft GPU). Frame đầu tiên có hash lệch, kết hợp với offset và symbol tra từ `guest_addresses.txt`, chỉ thẳng tới hàm bị codemod làm sai. File hash được commit vào repo (hash không chứa dữ liệu game).

## ADR-12 — Chiến lược fork — Accepted
Chi tiết trong `FORK-MAINTENANCE.md`. Tóm tắt: patch stack nhỏ rebase lên `upstream/master`; theo dõi diff budget; nếu upstream tự làm 64-bit thì đánh giá chuyển sang abstraction của họ.
