# M0 — Nền móng và đo độ khó (≈1 tuần)

**Mục tiêu:** chuẩn bị fork, toolchain và số liệu thật, rồi quyết định go/no-go dựa trên một prototype codemod.
**Scope OUT:** chưa build game LP64, chưa viết platform code.

---

### T0.1 — Fork, remote, branch, guard dữ liệu
- **Làm:**
  - Fork trên GitHub. Clone về, thêm remote `upstream`, tạo branch `macos/main` từ `upstream/master`.
  - Thêm vào `.gitignore` (chỉ thêm, không sửa dòng cũ): `*.bin`, `*.cue`, `*.BIN`, `game/`, `tmp/`, `*.state`, `docs/macos/reports/*.png`.
  - Copy toàn bộ kit này vào root.
  - Viết `tools/pc/macos/diff_budget.py`: in số dòng diff so với `upstream/master` trên (a) các file dùng chung của upstream và (b) các thư mục bị cấm sửa (`src/game`, `src/overlays`, `src/psyq`, `src/ygo_types.h`, `src/types.h`). Nhóm (b) phải bằng 0, không thì exit code khác 0.
- **Acceptance:** `git remote -v` có `upstream`; `diff_budget.py` chạy, cho (b)=0 và in ra (a).
- **Ước lượng:** 1 session.

### T0.2 — Toolchain và doctor
- **Làm:** viết `tools/pc/macos/doctor.py`, kiểm tra các điều kiện sau và in hướng dẫn cài cho từng lỗi:
  - Xcode Command Line Tools; `clang --version` là Apple clang và target arm64.
  - Homebrew `llvm` (lấy libclang và `clang --target=aarch64-none-elf`), `cmake`, `ninja`, `python3` ≥ 3.11.
  - Python binding `clang` import được, và version khớp với libclang của brew llvm (gợi ý đặt `LIBCLANG_PATH`).
  - `MEMORIES_DISC` trỏ tới một file tồn tại (chỉ cảnh báo, không fail).
- **Acceptance:** doctor xanh trên Mac mini M4.
- **Ước lượng:** 1 session.

### T0.3 — Spike CrossOver (người làm, Claude soạn checklist)
- **Làm:** Claude viết `docs/macos/reports/m0-crossover-checklist.md`, gồm cách tải release Windows, tạo bottle Win10 64-bit, chạy `memories-pc.exe`, và những thứ cần ghi lại: có lên title screen không, log `memory ... taken by Windows`, FPS, âm thanh. Fen tự chạy thử và ghi kết quả vào PROGRESS.
- **Ý nghĩa:** không chặn lộ trình. Nếu chạy được, fen có bản chơi tạm trong lúc port.
- **Ước lượng:** 1 session (Claude) cộng 30 phút (fen).

### T0.4 — Target CMake portable chạy native arm64
- **Đọc trước:** `CMakeLists.txt`, `notes/pc-build.md` (phần CMake target), `notes/continuous-integration.md`.
- **Làm:** configure và build target CMake (upstream nói nó build được 64-bit), chạy `ctest`. **Chưa sửa gì.** Ghi các test fail cùng nguyên nhân sơ bộ vào `docs/macos/reports/m0-cmake.md`.
- **Acceptance:** có report. Mỗi test fail được phân loại: do LP64 / do Linux-only / do lỗi khác.
- **Ước lượng:** 1 session.

### T0.5 — Census LP64 bằng clang arm64
- **Đọc trước:** `tools/pc/host_census.py`.
- **Làm:** viết `tools/pc/lp64/census.py` (wrapper, không sửa file gốc). Nó syntax-check toàn bộ unit game/overlay bằng `clang --target=arm64-apple-macos -fsyntax-only` và nhóm lỗi theo loại: size assertion, cast con trỏ↔int, `jmp_buf`, `DIRENTRY`, ... Xuất `tmp/lp64/census.json` và bản tóm tắt vào `docs/macos/reports/m0-census.md`.
- **Acceptance:** report có số pass/fail và top 10 loại lỗi. Con số này là **baseline** cho M1.
- **Ước lượng:** 1 session.

### T0.6 — Giải phẫu build upstream (discovery, chốt ADR-03)
- **Đọc trước:** `tools/pc/build_game32.py`, `src/pc/guest/image.c`, `src/pc/guest/state.c` (phần link cố định), `config/pc/guest_addresses.txt`.
- **Làm:** viết `docs/macos/reports/m0-build-anatomy.md` trả lời các câu:
  1. Biến của game được đặt tại địa chỉ retail bằng cách nào (linker script, `--section-start`, hay cách khác)?
  2. Initializer của biến game lấy từ object C hay từ EXE trên disc?
  3. Code game có được link ở địa chỉ cố định không? Stack game map ở đâu?
  4. Build gọi `nm`/`readelf`/`objcopy` để làm gì? Trên Mach-O thay thế bằng gì?
  5. Build dùng những flag nào (`-fpatchable-function-entry`, `-m32`, `-fno-pic`, ...)?
  6. Có bao nhiêu biến global chứa con trỏ (tra `notes/global-usage.csv` nếu hữu ích)?
- Sau đó cập nhật ADR-03 trong ARCHITECTURE.md: chuyển sang Accepted hoặc đề xuất hướng khác.
- **Acceptance:** report trả lời đủ 6 câu kèm trích dẫn file:dòng; ADR-03 đã cập nhật.
- **Ước lượng:** 1–2 session.

### T0.7 — Prototype codemod (quyết định go/no-go)
- **Làm:**
  - `tools/pc/lp64/codemod.py` bản đầu, dùng libclang, chỉ làm biến đổi (1) của ADR-05 (field con trỏ → `GPTR`) cho **5 struct có con trỏ** trong `src/ygo_types.h`. Chọn struct được dùng nhiều nhất.
  - Viết `src/pc/guest/gptr.h` bản tối thiểu (chỉ macro, chưa có runtime).
  - Dump record layout bằng clang (`-fdump-record-layouts`) cho 5 struct này ở cả hai phía: i386 gốc và arm64 + `MEMORIES_LP64` trên output của codemod. Cách dump tham khảo `tools/pc/check_layouts.py`.
- **Acceptance:** layout của 5 struct giống hệt nhau; codemod idempotent (chạy 2 lần cho cùng output).
- **Ước lượng:** 2–3 session.

## Gate G0 (fen quyết định)
Dựa vào T0.5 và T0.7, ước lượng lại M1. Nếu codemod cho 5 struct cần nhiều override tay hơn dự kiến (ví dụ trên 30% số chỗ dùng), cân nhắc lại ADR-05 trước khi đi tiếp. Ghi quyết định vào Decision log.
