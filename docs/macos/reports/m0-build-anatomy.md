# M0 — Giải phẫu build upstream (T0.6)

**Nguồn:** `tools/pc/build_game32.py` (832 dòng, đọc toàn bộ), `src/pc/guest/image.c`,
`src/pc/guest/state.c`, `config/pc/guest_addresses.txt`. Một số điểm được
kiểm chứng trực tiếp trên máy (Mac mini M4, Apple clang 17, brew llvm 17.0.5)
thay vì chỉ đọc code, ghi rõ ở từng mục.

## Phát hiện trung tâm — sửa lại giả định trong ADR-03

ADR-03 (bản cũ) viết: *"Upstream link biến của game (game_data/game_bss,
`ovl_*`) tại địa chỉ retail."* **Không đúng.** Build hiện tại dùng **hai cơ
chế địa chỉ hoàn toàn tách biệt**, không phải một:

1. **`FIXED_SECTIONS`** (`build_game32.py:123-124`):
   ```python
   FIXED_SECTIONS = {"game_text": 0x01000000, "game_rodata": 0x03000000,
                      "game_data": 0x04000000, "game_bss": 0x05000000}
   ```
   Đây là địa chỉ **tự chọn của build, không phải địa chỉ retail PS1**
   (retail luôn ở dải `0x800xxxxx`). Comment ngay phía trên (dòng 121-122)
   nói rõ lý do: *"Save states outlive native rebuilds because everything a
   state can point at in the game objects stays put... their code and
   variables are collected into sections linked at these addresses."* — mục
   đích là để **con trỏ native trỏ vào code/data đã biên dịch của chính
   build này** giữ nguyên giá trị qua các lần rebuild (cho save state), không
   liên quan gì tới việc mô phỏng bộ nhớ PS1.

2. **`guest_symbols.ld`** (`build_game32.py:696-699`, dữ liệu từ
   `config/pc/guest_addresses.txt`): pin **giá trị bằng đúng địa chỉ retail
   `0x800xxxxx`** cho các symbol được **tham chiếu nhưng không được định
   nghĩa** trong build này (ví dụ biến thuộc một overlay khác chưa được
   link). Các giá trị này hoạt động được như con trỏ thật *ngay bây giờ*
   chỉ vì RAM guest đang được `mmap` đúng tại `0x80000000`
   (`src/pc/guest/image.c`, đã ghi trong ADR-01) — không có cơ chế dịch địa
   chỉ nào ở đây cả, nó là con trỏ host trực tiếp.

Việc này quan trọng cho ADR-03 vì: cơ chế (1) — dùng cho **đa số** biến
global (những biến thực sự được decompile/compile) — dựa vào `-fno-pie` +
`-Wl,--section-start`, cả hai đều **không dùng được trên arm64 macOS**
(PIE bắt buộc, `ld64` không có `--section-start` dạng này). Cơ chế (2) chỉ
áp dụng cho một tập nhỏ symbol "mồ côi" (chưa link). Xem mục "Ý nghĩa cho
ADR-03" cuối report.

---

## 1. Biến của game được đặt tại địa chỉ retail bằng cách nào?

**Không phải toàn bộ đều đặt tại địa chỉ retail** (xem phát hiện trung tâm ở trên).
- Biến **có định nghĩa C thật** trong build → nằm trong section `game_data`/
  `game_bss`, đặt tại `0x04000000`/`0x05000000` (không phải retail) qua
  `-Wl,--section-start=game_data=0x04000000` (`build_game32.py:772`).
- Biến **không có định nghĩa** (thuộc overlay khác) → pin đúng giá trị retail
  `0x800xxxxx` qua linker-script-fragment `guest_symbols.ld`, mỗi dòng
  `NAME = 0xADDRESS;` (`build_game32.py:696-699`), lấy địa chỉ từ
  `config/pc/guest_addresses.txt` (qua hàm `guest_addresses()`,
  `build_game32.py:265-299`).
- Việc gán code/data C của TỪNG object vào đúng section `game_text`/
  `game_data`/`game_bss` (thay vì `.text`/`.data`/`.bss` mặc định) làm bằng
  `objcopy --rename-section` **sau khi biên dịch** (`build_game32.py:591-593`),
  không phải bằng `__attribute__((section(...)))` lúc compile.

## 2. Initializer của biến game lấy từ object C hay từ EXE trên disc?

**Cả hai, tuỳ loại biến** (`build_game32.py:650-670`):
- Biến được compile thật (`game_defined`) → initializer là giá trị viết
  trong C source đã decompile, như bất kỳ global C bình thường nào.
- Biến "mồ côi" (undefined/tentative, không thuộc unit nào trong build này,
  ví dụ biến của overlay chưa link) → không có object C nào định nghĩa giá
  trị; giá trị thật của nó đến từ **nội dung EXE trên disc**, được copy vào
  vùng RAM guest lúc load (cơ chế đã có ở `image.c`/`state.c`, ngoài phạm vi
  `build_game32.py`).

## 3. Code game có link ở địa chỉ cố định không? Stack game map ở đâu?

**Code:** có, tại `0x01000000` (`game_text`, `FIXED_SECTIONS`,
`build_game32.py:123`) — **không phải địa chỉ retail**, chỉ cố định để
save-state ổn định qua rebuild. Biên giới section lấy qua symbol linker sinh
tự động: `__start_game_text[]`/`__stop_game_text[]` (`state.c:48`).

**Stack:** map cố định bằng `mmap` tại `STACK_BASE` — `0x70000000` (Linux)
hoặc `0xB0000000` (Windows), kích thước `0x00800000` (8MB)
(`state.c:33-42,1003-1006`):
```c
void *stack = mmap((void *)(uintptr_t)STACK_BASE, STACK_SIZE, PROT_READ | PROT_WRITE,
                   MAP_FIXED_NOREPLACE | MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
```
Chuyển sang chạy trên stack này bằng `ucontext` (`getcontext`/`makecontext`/
`swapcontext`, `state.c:1038-1042`), không phải thread hay fiber riêng.

**Đã tự kiểm chứng trên máy này (Mac mini M4, arm64):**
- `MAP_FIXED_NOREPLACE` và `MAP_ANONYMOUS` **không tồn tại** trên macOS
  (đã xác nhận ở T0.4/T0.5 — không có tương đương `MAP_FIXED_NOREPLACE`;
  `MAP_ANONYMOUS` cần đổi tên thành `MAP_ANON`). Dòng `mmap` này **sẽ không
  build được nguyên trạng** trên macOS.
- **Tin tốt:** `ucontext` (`getcontext`/`makecontext`/`swapcontext`) **chạy
  đúng trên arm64 macOS** — đã tự viết chương trình test, compile với
  `_XOPEN_SOURCE`, chạy context-switch qua lại thành công (chỉ có warning
  deprecated từ macOS 10.6, không phải lỗi/không bị gỡ bỏ). Đây từng là lo
  ngại mở trong "Vấn đề mở/rủi ro" của PROGRESS — không phải blocker như
  nghĩ ban đầu; blocker thật chỉ nằm ở lệnh `mmap` cố định địa chỉ, không
  phải cơ chế chuyển stack.

## 4. Build gọi `nm`/`readelf`/`objcopy` để làm gì? Mach-O thay bằng gì?

- **`readelf -sW`/`readelf -SW`** (`build_game32.py:276,282`) — chỉ dùng để
  **regenerate** `config/pc/guest_addresses.txt` từ ELF của matching build
  (MIPS), khi các ELF đó tồn tại cục bộ. **Không cần cho port macOS**: ta
  không có (và không cần) matching build MIPS; build luôn rơi vào nhánh
  `elif not os.path.exists(ADDRESSES)` — đọc thẳng file `.txt` đã commit sẵn
  (`build_game32.py:297-298`). `objdump -h` (dòng 584) cũng chỉ phục vụ
  discovery tương tự cho overlay, cùng kết luận.
- **`nm -g` / `nm -A -g --defined-only` / `nm -u` / `nm -n -S`** — dùng
  xuyên suốt để phân loại symbol (defined/undefined/tentative, ai định nghĩa
  gì) và để sinh bảng symbol cho save state từ executable cuối cùng
  (`build_game32.py:151,162,231,640,685,786`).
  **Đã tự kiểm chứng:** `/usr/bin/nm` trên Mac **đã là `llvm-nm`** ("compatible
  with GNU nm"), phần lớn flag (`-g`, `-u`, `-A`, `-n`) hoạt động tương tự.
  Nhưng **`nm -S` (in size symbol) luôn trả về 0 trên Mach-O** — tool tự in
  cảnh báo rõ: `"warning: sizes with --print-size for Mach-O files are
  always zero"`. Bảng symbol save-state (dòng 786) cần size thật →
  **phải suy size từ khoảng cách địa chỉ giữa 2 symbol liên tiếp**, đúng
  cách code đã làm sẵn cho Windows/PE (dòng 797-804, PE cũng không có size
  symbol) — không cần thiết kế mới, chỉ áp dụng lại nhánh đã có.
- **`objcopy`** — dùng cho `--rename-section` (gán code/data vào
  `game_text`/`game_data`/`game_bss`, dòng 591-593), `--weaken-symbol` (cho
  native override thắng định nghĩa game, dòng 649), và thao tác COFF thủ
  công (`rename_coff_sections`/`unset_coff_commons`, chỉ nhánh Windows).
  **Đã tự kiểm chứng:** GNU `objcopy` **không có sẵn trên macOS**.
  `llvm-objcopy` (có qua `brew install llvm`, không có trên PATH mặc định)
  hỗ trợ Mach-O nhưng **`--weaken-symbol` báo thẳng lỗi
  `"option is not supported for MachO"`** — cơ chế native-override-thắng-game
  **không port được nguyên trạng**, cần cách khác (ví dụ đánh dấu
  `__attribute__((weak))` ngay lúc compile thay vì patch binary sau khi
  build). `--rename-section` cũng cư xử khác hẳn cú pháp ELF/COFF trong vài
  lần thử nhanh trên máy này — cần nghiên cứu thêm cú pháp đúng ở M1, không
  chắc dùng được kiểu tương tự.

## 5. Build dùng những flag nào? Cái nào áp dụng được trên macOS arm64?

`CFLAGS` cho unit game (`build_game32.py:55-61`):
```
-m32 -std=gnu11 -fpermissive -w -O0 -g -fno-strict-aliasing
-fpatchable-function-entry=8,6 -fwrapv -fcommon -fno-pie -fno-stack-protector
-DMEMORIES_PC -D_LANGUAGE_C -DLANGUAGE_C -Isrc -include src/pc/compat/pgxp_game.h
```
`NATIVE_CFLAGS` cho code port (`build_game32.py:75-82`) thêm
`-I/usr/include/freetype2 -D_FILE_OFFSET_BITS=64`. Link cuối
(`build_game32.py:771-775`): `-m32 -no-pie` + `-Wl,--section-start=...`.

| Flag | Áp dụng cho arm64 macOS? |
|---|---|
| `-m32` | Không — ADR-01 đã chốt LP64 (arm64 native), không dùng ILP32. |
| `-fno-pie` | **Không dùng được** — Apple Silicon bắt buộc PIE, không có cách tắt (khớp `ARCHITECTURE.md` dòng 72, giờ xác định rõ flag nào là nguồn gốc). |
| `-fpatchable-function-entry=8,6` | Không cần — ADR-06 (Accepted) đã thay hook-bằng-patch-nhị-phân bằng dispatch stub, không cần chỗ trống NOP nữa. |
| `-fcommon` | **Cần giữ trên clang arm64** — mặc định Clang ≥11 là `-fno-common`; cơ chế pin qua COMMON symbol (`tentative` set, `build_game32.py:161-166`) sẽ vỡ nếu thiếu flag này. |
| `-fwrapv`, `-fno-stack-protector`, `-fno-strict-aliasing`, `-std=gnu11`, `-DMEMORIES_PC`/`-D_LANGUAGE_C`/`-DLANGUAGE_C` | Portable, giữ nguyên trên clang arm64. |
| `-fpermissive` | GCC-only, clang không hỗ trợ tương đương đầy đủ — các lỗi thực tế cần macOS chịu đã lộ ra ở census T0.5 (không phải do thiếu `-fpermissive`, là LP64/section-attribute), nhưng có thể còn vài trường hợp GCC-leniency khác chưa lộ (T0.5 dừng ở 2 loại lỗi vì census stop trước khi tới các file thực sự cần K&R leniency — cần theo dõi ở M1). |
| `-I/usr/include/freetype2` | Đường dẫn cứng kiểu Linux — trên macOS FreeType đến từ Homebrew (`/opt/homebrew/include/freetype2` hoặc qua `pkg-config`), cần sửa. |
| `-D_FILE_OFFSET_BITS=64` | Vô nghĩa trên LP64 (off_t đã 64-bit sẵn) — giữ cũng không hại, có thể bỏ. |
| `-Wl,--section-start=NAME=0xADDR` | Cú pháp GNU `ld`. `ld64` (macOS) có cơ chế khác hẳn hình dạng (`-segaddr <segname> <addr>` cho cả segment, `-sectcreate` cho section riêng) — cần nghiên cứu ở M1, không phải chuyện đổi tên flag đơn giản. |

## 6. Có bao nhiêu biến global chứa con trỏ?

`notes/global-usage.csv` ghi theo **lượt truy cập** (mỗi dòng là một hàm
dùng một global), không ghi kiểu dữ liệu trực tiếp, nên không có con số
chính xác tuyệt đối từ file này — chỉ ước lượng heuristic:

- **717 địa chỉ global khác nhau** được track trong CSV.
- Trong đó, **~248 (34.6%)** có ít nhất một dòng `context` cho thấy dấu hiệu
  con trỏ (dereference `->`, ép kiểu `(T *)` quanh tên biến) — đây là **cận
  dưới**, không phải số chính xác (nhiều cách dùng con trỏ trong C không
  khớp pattern đơn giản này, ví dụ gán qua biến trung gian).

Số liệu **đáng tin hơn** cho quy mô ảnh hưởng con trỏ đã có sẵn từ T0.5
(census LP64): **27.811 lỗi struct-offset** trên **482/546 unit** — đây là
đo trực tiếp bằng compiler thật, không phải heuristic, và đo đúng thứ ADR-05
(codemod field con trỏ trong struct) cần biết. Câu hỏi #6 ở đây là về biến
**global đứng riêng** (không phải field trong struct) — quy mô nhỏ hơn hẳn
struct field, và với hướng "global sống trong RAM guest" (xem mục dưới),
**bản thân global không cần biết nó có phải con trỏ hay không** — mọi global
đều được truy cập qua `G2H(retail_addr)` như nhau, con trỏ hay không con trỏ.

## Ý nghĩa cho ADR-03

Phát hiện trung tâm ở đầu report (2 cơ chế tách biệt) thực ra **củng cố**
hướng "global sống trong RAM guest" mà ADR-03 đã đề xuất, chứ không phủ
nhận: cơ chế FIXED_SECTIONS/`-fno-pie`/`--section-start` hiện dùng cho đa số
global **không thể tái tạo trên arm64 macOS** (PIE bắt buộc, `ld64` không
tương thích cú pháp). Nếu cố mô phỏng lại y hệt, sẽ phải phát minh một cơ chế
địa chỉ-cố-định-song-song-nhưng-khác-retail thứ hai chỉ cho macOS. Đưa toàn
bộ global vào RAM guest (dùng lại đúng cơ chế `G2H`/`H2G` mà ADR-01/02 đã
cần cho pointer field) tránh phải duy trì 2 cơ chế song song — chỉ 1 cơ chế
duy nhất cho cả field lẫn global.

**Đề xuất cập nhật ADR-03 → Accepted**, giữ hướng "global sống trong RAM
guest" như bản Proposed đã viết, chỉ sửa lại phần "Bối cảnh" cho đúng thực
tế (không còn nói "upstream link tại địa chỉ retail" một cách chung chung).
Với initializer: với biến ĐÃ có định nghĩa C thật, giữ nguyên giá trị C viết
sẵn (không bắt buộc phải luôn đọc từ EXE-on-disc, dù cả hai cách cho cùng
kết quả về mặt giá trị) — quyết định implementaion cụ thể (đọc từ EXE hay
giữ init C) để lại cho T0.7/M1, ngoài phạm vi discovery của T0.6.
