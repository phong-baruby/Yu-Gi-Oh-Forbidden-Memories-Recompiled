# M1 — `gptr.h`/`gptr_lp64.c` hoàn chỉnh (T1.1)

**Lệnh test:**
```sh
cmake -S . -B tmp/pc/cmake-lp64 -G Ninja -DCMAKE_BUILD_TYPE=Debug -DMEMORIES_LP64=ON
cmake --build tmp/pc/cmake-lp64 --target memories_gptr_test
ctest --test-dir tmp/pc/cmake-lp64 -R pc_gptr --output-on-failure
```

## Kết quả

`pc_gptr` pass, cả 4 tiêu chí acceptance của T1.1:
- `G2H(0) == NULL`
- `G2H(0x80001000)` == `G2H(0xA0001000)` == `G2H(0x00001000)` (cùng trỏ 1 byte trong `g_ram`)
- `H2G(G2H(a))` luôn trả về dạng KSEG0 (`0x80xxxxxx`), bất kể `a` là biến thể KSEG0/KSEG1/KUSEG nào
- Con trỏ ngoài `g_ram`/`g_scratch` làm `H2G` abort (kiểm bằng subprocess: fork + exec lại chính binary với arg `--abort-out-of-range`, cha kiểm `WIFSIGNALED && WTERMSIG==SIGABRT`)

## Bug tìm thấy và sửa: `G2H(0)` không trả về NULL

Bản `gptr.h` từ T0.7 (chỉ macro, đúng như milestone T0.7 yêu cầu) có `G2H`
chưa xử lý `a==0`: với `a=0`, biểu thức `(phys - 0x1F800000u) < 0x400u` (với
`phys=0`) underflow số unsigned thành số rất lớn, điều kiện false, nên rơi
xuống `return g_ram + 0` — tức trả về `g_ram` (khác NULL trừ khi `g_ram`
chính nó là NULL). ADR-02 đã ghi rõ yêu cầu này ("`G2H(0)` phải trả về
NULL, xử lý riêng trường hợp này") nhưng bản T0.7 chưa hiện thực — đúng
như T0.7 tự mô tả là "chỉ macro, chưa có runtime". Đã thêm
`if (a == 0) return NULL;` ở đầu `G2H`.

## Xác minh kích thước scratchpad (yêu cầu của T1.1)

`src/pc/guest/image.c` map scratchpad **4KB** (`0x1000`) ở cả 2 nhánh:
```c
// Windows (image.c:287)
VirtualAlloc((void *)0x1f800000u, 0x1000, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE)
// POSIX (image.c:378)
map_at(0x1f800000u, 0x1000, -1, 0);
```
Nhưng scratchpad thật của PS1 chỉ có **1KB** (giới hạn phần cứng D-cache
dùng làm scratchpad) — 3KB còn lại trong trang map chỉ là hệ quả của việc
`mmap`/`VirtualAlloc` không cấp phát nhỏ hơn 1 trang, chưa từng là scratchpad
hợp lệ trên máy thật. **Kết luận: giữ nguyên biên `0x400` (1KB) trong `G2H`**
— logic này đã đúng từ bản T0.7, không cần sửa. `gptr.h` đã ghi rõ lý do
bằng comment để không ai nhầm là bug khi đọc lại sau này.

## Thiết kế `g_ram`/`g_scratch` cho T1.1 vs T1.2

`gptr_lp64.c` chỉ khai báo `uint8_t *g_ram;`/`uint8_t *g_scratch;` (con trỏ
NULL mặc định) và hiện thực `H2G`. **Không cấp phát bộ nhớ thật** — đúng
theo milestone tách T1.1 (macro + test) khỏi T1.2 (cấp phát RAM/scratchpad
thật, copy EXE từ disc). `tests/pc/gptr_test.c` tự cấp phát 2 buffer test
(`static uint8_t ram[0x200000]`, `static uint8_t scratch[0x400]`) rồi gán
vào `g_ram`/`g_scratch` — không phụ thuộc vào việc T1.2 đã xong hay chưa.

## Wiring CMake

`option(MEMORIES_LP64 ...)` mới, mặc định `OFF`. `memories_gptr_test` +
`add_test(NAME pc_gptr ...)` chỉ đăng ký khi `MEMORIES_LP64=ON` (đã xác minh:
build mặc định không có target `memories_gptr_test` — `ninja: error: unknown
target`, đúng ý milestone "chỉ khi bật option").

## Không có hồi quy

Build toàn bộ với `-DMEMORIES_LP64=ON -- -k 0`: 30/60 test fail — **khớp
đúng con số 30 test fail đã ghi trong `m0-cmake.md` (T0.4)**, chỉ khác biệt
duy nhất là tổng số test tăng từ 59 lên 60 (thêm `pc_gptr`, pass). Không có
test nào trước đây pass giờ fail. Các fail còn lại là vấn đề đã biết từ
T0.4/T0.5 (LP64 struct-offset ở phần chưa codemod, `mkdtemp` Darwin,
`MAP_ANONYMOUS`/`MAP_FIXED_NOREPLACE`), sẽ giải quyết dần ở T1.3/T1.4/T1.7 —
không phải việc của T1.1.
