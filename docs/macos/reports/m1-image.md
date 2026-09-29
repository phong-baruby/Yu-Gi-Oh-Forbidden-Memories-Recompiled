# M1 — Image guest trên macOS (T1.2)

**Lệnh test:**
```sh
cmake -S . -B tmp/pc/cmake-lp64 -G Ninja -DCMAKE_BUILD_TYPE=Debug -DMEMORIES_LP64=ON
cmake --build tmp/pc/cmake-lp64 --target memories_image_test
MEMORIES_DISC=/path/to/your.bin ctest --test-dir tmp/pc/cmake-lp64 -R pc_image --output-on-failure
```

## Kết quả

`pc_image` pass — kiểm tra thật với disc thật (không mock): so 16 byte tại
entry point giữa file EXE gốc và `G2H(entry)` sau khi `image_lp64.c` load
xong. Khớp tuyệt đối.

Không có `MEMORIES_DISC`, hoặc trỏ tới file không phải disc hợp lệ (kiểm
bằng `GameFiles_Disc` có sẵn) → test tự `return 77`, CTest báo Skipped chứ
không Fail — đúng pattern `SKIP_RETURN_CODE 77` đã có sẵn trong repo
(`card_plate_test.c`, `rank_art_test.c`, `font_art_test.c`) cho resource tuỳ
chọn.

## Thiết kế `image_lp64.c`

So với `image.c` (ILP32): bỏ hẳn cơ chế map cố định địa chỉ + trap/decode
lệnh x86 cho vùng mirror (đúng ghi chú của milestone: "Không cần trap hay
mirror nữa"). `g_ram`/`g_scratch` chỉ là `malloc()` thường — không cần nằm ở
địa chỉ host cụ thể nào, vì `G2H`/`H2G` (T1.1) đã làm toàn bộ việc dịch địa
chỉ trong phần mềm. Logic đọc header PS-X EXE (`address` ở offset 0x18,
`size` ở 0x1C, dữ liệu bắt đầu từ offset 0x800 trong file) giữ y hệt
`image.c`, chỉ đổi đúng 1 chỗ: `memcpy((void*)address, ...)` (coi guest
address = host pointer, chỉ đúng với ILP32) → `memcpy(G2H(address), ...)`.

## Test đọc disc thật, không mock

Milestone yêu cầu rõ: dùng code có sẵn của `game_files.c`
(`GameFiles_Disc`, `GameFiles_ReadExecutable`) để đọc EXE thật từ
`MEMORIES_DISC`, không tự viết lại logic đọc ISO9660/CD sector. Test cần
stub tối thiểu `Platform_SelectDisc`/`Platform_ShowError` (nhánh
`GameFiles_Setup` không dùng tới nhưng linker vẫn cần symbol) — cùng cách
`tests/pc/game_files_test.c` đã làm cho các Platform_* khác.

**Xác minh thật với 2 file `.bin` mod đã có** (không phải retail — xem
`m0-crossover-checklist.md` T0.3 về việc chưa có dump gốc hợp lệ):
- `YGOFM Mod 2023 15x.bin`: `GameFiles_Disc` từ chối ("không phải raw image
  hợp lệ") — không rõ nguyên nhân cụ thể (không phải việc của T1.2 để điều
  tra sâu, bản mod này có thể đóng gói khác cấu trúc ISO9660 chuẩn).
- `Drop 15 Card 722 Full.bin`: được nhận diện đúng, đọc EXE, load, so byte
  entry point khớp 100%. Dùng file này để tự verify acceptance thật (không
  chỉ dừng ở việc test skip đúng cách).

## Không có hồi quy

`-DMEMORIES_LP64=ON -k 0`: 30/61 test fail (61 = 60 của T1.1 + `pc_image`
mới) — **vẫn đúng 30**, khớp T0.4/T1.1. `pc_image` tự skip khi chạy qua
`ctest` không set `MEMORIES_DISC` (đúng thiết kế, không phải lỗi).
