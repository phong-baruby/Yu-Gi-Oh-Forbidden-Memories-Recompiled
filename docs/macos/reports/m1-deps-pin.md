# M1 — T1.9: Dependencies pin (SDL3 + FreeType cho arm64 macOS)

**Kết quả: `tools/pc/macos/build_deps.py` build thành công SDL3 3.4.16 + FreeType VER-2-14-3 tĩnh,
native arm64, vào `tmp/pc/macos-deps/`. Acceptance đầy đủ (cache hit lần 2, `otool -L` sạch Homebrew)
đã xác nhận bằng chạy thật.**

## Khác biệt so với milestone (đã hỏi fen, đã chốt trước khi code — xem plan đã duyệt)

1. Milestone nói "đúng version upstream pin trong `build_linux_sysroot.py`" nhưng file đó không pin
   FreeType riêng (lấy qua gói `.deb` Debian, không có SHA-256 độc lập). Version FreeType pin độc lập
   thật sự nằm ở `build_win32_deps.py` (`VER-2-14-3`) — dùng version này cho macOS, lý do nhất quán giữa
   3 platform (không có lý do kỹ thuật riêng để macOS khác).
2. SDL3 trên macOS build từ source (không có bản prebuilt macOS như Windows có MinGW archive) — đúng ý
   ADR-10.
3. Không cần pin zlib/libpng: FreeType build với `-DFT_DISABLE_ZLIB=ON -DFT_DISABLE_PNG=ON` (giống cờ
   Windows) nên không phụ thuộc cả hai.
4. Build native, không cross-compile — không cần toolchain file như `build_linux_sysroot.py`/
   `build_win32_deps.py` phải dùng (host arm64 chính là target).

## Lỗi thật phát hiện khi chạy thử (tự chạy, không đoán)

- **Bug trong chính `build_deps.py` lúc viết lần đầu**: `ROOT` tính bằng `dirname` 3 lần, đúng cho
  `tools/pc/build_win32_deps.py` (sâu 2 cấp dưới `tools/`) nhưng file này nằm ở `tools/pc/macos/`
  (sâu 3 cấp) — thiếu 1 `dirname`, khiến `tmp/pc/macos-deps` bị tạo nhầm trong `tools/tmp/pc/macos-deps`.
  Phát hiện ngay ở lần chạy đầu (đường dẫn log hiện `tools/tmp/...`), sửa còn 4 `dirname`, xoá thư mục
  sai, chạy lại sạch.
- **SDL3 build tĩnh thiếu framework khi link app thật**: lần link `smoke_test` đầu tiên báo thiếu symbol
  `AVCaptureDevice*`/`CMSampleBuffer*`/... (module camera `SDL_camera_coremedia.m` của SDL3, luôn compile
  vào khi target là macOS, không có cờ CMake nào tắt riêng module camera). Thêm
  `-framework AVFoundation -framework CoreMedia` vào lệnh link smoke-test là đủ (SDL3's CMake tự động bật
  mọi backend macOS có sẵn, không cần cờ riêng như Linux's PIPEWIRE/JACK/IBUS — macOS không có các cờ
  loại backend tương đương, đúng dự đoán trong plan).
- Không gặp lỗi gì khác — FreeType build sạch ngay, không cần chỉnh cờ.

## Cờ CMake thật đã dùng

**SDL3**: `-DSDL_SHARED=OFF -DSDL_STATIC=ON -DSDL_TESTS=OFF -DSDL_TEST_LIBRARY=OFF -DSDL_EXAMPLES=OFF
-DSDL_INSTALL=ON` (khác Linux ở `SDL_INSTALL=ON` vì macOS cần `cmake --build --target install` để lấy
header/lib vào `tmp/pc/macos-deps/{include,lib}`, Linux link thẳng từ thư mục build nên để `OFF`). Không
cần cờ tắt backend nào (không có flag tương đương `SDL_PIPEWIRE`/`SDL_JACK`/... cho macOS).

**FreeType**: `-DBUILD_SHARED_LIBS=OFF -DFT_DISABLE_ZLIB=ON -DFT_DISABLE_BZIP2=ON -DFT_DISABLE_PNG=ON
-DFT_DISABLE_HARFBUZZ=ON -DFT_DISABLE_BROTLI=ON` — copy nguyên từ `build_win32_deps.py`, không cần sửa.

Cả hai thêm `-DCMAKE_OSX_ARCHITECTURES=arm64` (chốt đúng arm64, không phải arm64e — CLAUDE.md luật #8) và
`-DCMAKE_POLICY_VERSION_MINIMUM=3.5` (tương thích `cmake_minimum_required` cũ của FreeType, giống Windows).

## Cơ chế cache

Mỗi lib (`sdl`, `freetype`) có 1 stamp file riêng (`tmp/pc/macos-deps/.sdl-complete`/`.freetype-complete`)
chứa URL archive đã pin. Lần sau nếu URL khớp thì bỏ qua hoàn toàn (không gọi `cmake`/`ninja`), in rõ
`"<lib>: cache hit (...), bo qua build"`. Xác minh bằng chạy `build_deps.py` 2 lần liên tiếp — lần 2 in
đúng 2 dòng cache hit cho cả `sdl` và `freetype`, không có log cấu hình/build nào khác.

## Acceptance đã chạy

- `python3 tools/pc/macos/build_deps.py` (lần 1): build xong, in `macos deps: .../tmp/pc/macos-deps`.
- `python3 tools/pc/macos/build_deps.py` (lần 2): `sdl: cache hit (...)`, `freetype: cache hit (...)` —
  không build lại.
- `otool -L tmp/pc/macos-deps/smoke_test`: toàn bộ 21 dòng đều `/System/Library/Frameworks/...` hoặc
  `/usr/lib/lib{System.B,objc.A}.dylib` — **không có `/opt/homebrew` hay `/usr/local`**.
- `lipo -info tmp/pc/macos-deps/lib/lib{SDL3,freetype}.a`: cả hai `Non-fat ... architecture: arm64`.
- `./tmp/pc/macos-deps/smoke_test`: in `smoke test ok: macOS`, exit 0 (gọi `SDL_Init`/`SDL_Quit` +
  `FT_Init_FreeType`/`FT_Done_FreeType` thật, không chỉ link thành công).

## File tạo/sửa phiên này

- Tạo: `tools/pc/macos/build_deps.py`, `tools/pc/macos/smoke_test.c`, file report này.
- Sửa: `docs/macos/PROGRESS.md` (không có file dùng chung của upstream bị chạm).
- Không commit: `tmp/pc/macos-deps/` (đã nằm trong `/tmp/` của `.gitignore` từ T0.1, không cần sửa thêm).
