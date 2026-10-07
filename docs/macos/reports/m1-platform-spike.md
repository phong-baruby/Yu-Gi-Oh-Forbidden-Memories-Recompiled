# M1 — T1.8: Platform macOS (mcontext, paths, spike Cocoa)

**Kết quả: 3 phần đã duyệt đều xong; spike Cocoa KẾT LUẬN "phương án A" (kiến trúc hiện tại) đủ dùng,
không cần "phương án B".** Acceptance đầy đủ của milestone (cửa sổ+bàn phím+gamepad+âm thanh TRONG GAME
THẬT) để dành T1.10 (chưa có SDL3 pin/build driver).

## Khác biệt so với milestone (đã hỏi fen, đã chốt)

1. Acceptance đầy đủ cần SDL3 build thật (T1.9) + build driver macOS (T1.10) — cả hai chưa tồn tại.
   Dùng spike độc lập (SDL3 cài tạm qua Homebrew, KHÔNG commit, KHÔNG phải bản pin của T1.9) để xác minh
   đúng rủi ro ADR-09 nêu — không chờ T1.9/T1.10.
2. "Loại 3 file khỏi build macOS": không có gì để sửa — `audio_alsa.c`/`gamepad_evdev.c` đã tự động bị
   loại bởi cơ chế `BACKENDS` có sẵn trong `build_game32.py` (chỉ build khi `--backend x11`, macOS luôn
   `--backend sdl`); `controls_linux.c` đã tự an toàn (nhánh `#ifndef __linux__`, compile thử sạch trên
   macOS). Ghi nhận để T1.10 tái dùng đúng cơ chế, không tạo file build-list mới (T1.10 chưa tồn tại).

## Lỗi thật phát hiện khi compile `platform_common.c`/`crash.c`/`paths.c` dưới `-DMEMORIES_LP64 -arch
arm64 -Werror` (tự biên dịch trước khi sửa, không đoán)

- `_XOPEN_SOURCE`/`_DARWIN_C_SOURCE`/pragma deprecate cho `ucontext.h` — cùng mẫu đã gặp ở T1.7.
- **`pthread_getattr_np`/`pthread_attr_getstack` (glibc) không tồn tại trên macOS** — `crash.c` dùng để
  lấy biên stack main thread cho báo cáo treo máy. Thay bằng `pthread_get_stackaddr_np`/
  `pthread_get_stacksize_np` (API riêng của Apple, cho top+size thay vì low+size — tính ngược lại).
- **`timer_create`/`SIGEV_THREAD_ID`/`struct itimerspec`/`timer_t` (POSIX timer, glibc) hoàn toàn không
  tồn tại trên macOS** — không phải thiếu macro hiển thị, API không hề có trên Darwin. Phát hiện quan
  trọng: `platform_common.c` đã CÓ SẴN nhánh dự phòng dùng `setitimer(ITIMER_REAL, ...)` cho trường hợp
  `timer_create` thất bại ("process-wide timer is only a fallback") — đúng ý ADR-09 ("Giữ SIGALRM/
  setitimer (macOS hỗ trợ)"). Chỉ cần bọc `#ifndef __APPLE__` quanh khối `timer_create`, đi thẳng xuống
  nhánh `setitimer` có sẵn — không cần viết cơ chế mới. Vẫn nhắm đúng main thread vì mọi thread khác
  tiến trình tạo ra đã tự chặn `SIGALRM` (comment gốc trong file), tín hiệu process-wide không còn chỗ
  nào khác để rơi vào.
- **`Paths_ProgramDir()`'s `readlink("/proc/self/exe", ...)` không hoạt động trên macOS** (không phải
  lỗi compile — `/proc` không tồn tại trên Darwin, hàm fail êm rồi rơi về `"."`) — phát hiện khi đọc kỹ
  `paths.c` lúc thêm nhánh Application Support. Thuộc đúng phạm vi "paths.c cho macOS" đã duyệt (ảnh
  hưởng `Paths_Program()`, dùng để tìm file đóng gói cạnh executable — ADR-09 có nhắc tới việc bundle
  TTF, phụ thuộc cơ chế này hoạt động đúng). Sửa bằng `_NSGetExecutablePath` (`<mach-o/dyld.h>`, API
  chính thức Apple cho đúng việc này).

## `paths.c`: nhánh `__APPLE__`

```c
#elif defined(__APPLE__)
    const char *home = getenv("HOME");
    if (home && *home) snprintf(root, sizeof(root), "%s/Library/Application Support", home);
```

Xác minh bằng chương trình nhỏ độc lập (không sửa `fs_test.c`'s test case — file đó hiện bị chặn bởi 1
lỗi `mkdtemp` macOS KHÁC, pre-existing, không liên quan T1.8, xem "Vấn đề mở"): gọi `Paths_UserDir()`
thật (không set `MEMORIES_USER_DIR`), so khớp `"$HOME/Library/Application Support/YFM Re-Decomp"` — khớp
đúng. Dọn thư mục rỗng tạo ra sau khi xác minh xong.

## Spike Cocoa: kết luận "phương án A" đủ dùng

**Phương pháp:** cài `sdl3` qua Homebrew (3.4.18, chỉ để chạy spike, không thêm vào build/CMake chính
thức). Viết chương trình độc lập (không commit): `main()` `mmap`+guard page+`swapcontext` sang 1 stack
riêng (ĐÚNG kiến trúc `Memories_StateRunGame` của T1.7 — không phải thread riêng, cùng 1 OS thread), trên
đó gọi `SDL_Init(VIDEO|EVENTS)` → `SDL_CreateWindow` → vòng lặp `SDL_PollEvent` + `SDL_Delay(8)` khoảng
600+ "frame" (~5 giây) → `SDL_DestroyWindow`/`SDL_Quit` → `swapcontext` quay lại main thread.

**Kết quả (chạy 3+ lần, nhất quán):**
- Không crash, không treo — thoát sạch (exit 0) mỗi lần, ~610-666 frame xử lý xong trong ~5 giây (khớp
  dự kiến 1000/8 ≈ 625).
- **Cocoa thực sự khởi tạo đầy đủ từ stack đã swap**: menu bar đổi tên app ("cocoa_spike") và tự tạo
  menu "Window" mặc định — đây là dấu hiệu `NSApplication`/`NSMenu` chạy đúng, không chỉ API không crash
  mà UI thật sự phản hồi.
- Xác minh cửa sổ THẬT tồn tại trên màn hình bằng `CGWindowListCopyWindowInfo` (không cần quyền
  Accessibility/Screen Recording, không có trong sandbox agent này): `bounds=(1120,557 320x268)` — toạ
  độ hợp lệ, không phải 0/garbage. Không chụp được ảnh màn hình trực tiếp cửa sổ do `screencapture -l`
  cần quyền Screen Recording mà phiên agent này không có — hạn chế môi trường, không phải hạn chế của
  kiến trúc game.

**Kết luận:** không phát hiện vấn đề gì với việc chạy SDL3/Cocoa trên stack đã `swapcontext` (kiến trúc
T1.7 đã xây) trên máy test này (Apple Silicon, macOS hiện tại). "Phương án A" (giữ nguyên, không cần bơm
event từ stack gốc) đủ dùng — không cần "phương án B". Lưu ý rủi ro: SDL3 dùng ở đây là bản Homebrew
(3.4.18), khác bản sẽ pin ở T1.9 — nhưng cơ chế đang kiểm (stack-switch qua ucontext) không phụ thuộc
version SDL, nên kết luận vẫn áp dụng được.

## Kết quả

`platform_common.c`/`crash.c`/`paths.c` compile sạch dưới `-DMEMORIES_LP64 -arch arm64 -Wall -Wextra
-Wpedantic -Werror`. `ctest` toàn bộ: 30 lỗi pre-existing không đổi (so khớp TÊN, không chỉ số).

## Vấn đề mở phát hiện thêm (không thuộc phạm vi T1.8, ghi nhận cho phiên sau)

**`mkdtemp` thiếu khai báo trên macOS, ảnh hưởng ít nhất 17 file test** (`fs_test.c`, `texture_pack_test.c`,
`controls_window_test.c`, `mods_test.c`, ... — xem `grep -rl mkdtemp tests/pc/`), cùng họ lỗi với
`MAP_ANON`/`ucontext` (macOS ẩn `mkdtemp` dưới `_POSIX_C_SOURCE` nghiêm ngặt, cần `_DARWIN_C_SOURCE`
thêm). Rất có thể là nguyên nhân của một phần đáng kể trong 30 lỗi pre-existing đã theo dõi từ T1.6. Sửa
nhanh (thêm `_DARWIN_C_SOURCE` đúng chỗ) nhưng ảnh hưởng nhiều file ngoài phạm vi T1.8 đã duyệt — để dành
một phiên riêng (có thể gộp vào T1.9/T1.10 hoặc một phiên dọn dẹp test macOS).

## File tạo/sửa phiên này

- Tạo: `src/pc/compat/mcontext.h`, `docs/macos/reports/m1-platform-spike.md`
- Sửa: `src/pc/platform/platform_common.c`, `src/pc/debug/crash.c`, `src/pc/platform/paths.c` (đều file
  dùng chung — ghi Upstream touch log), `docs/macos/PROGRESS.md`, `docs/macos/ARCHITECTURE.md`
- Không commit: spike Cocoa (`cocoa_spike.c`, chỉ chạy trong scratchpad), SDL3 Homebrew (cài hệ thống,
  không phải dependency của repo)
