# M2 — Oracle golden: so từng byte với reference build (≈1–2 tuần)

**Mục tiêu:** có công cụ trả lời được câu "bản macOS lệch reference ở frame nào, byte nào, thuộc symbol nào". Milestone này làm **trước** M3, vì M3 dựa vào nó để sửa lỗi.
**Scope OUT:** chưa đòi hỏi mọi script đều pass. Đó là việc của M3.

---

### T2.1 — Discovery: tính tất định của upstream
- **Đọc trước:** `tools/pc/smoke.py`, `tests/pc/smoke/`, `src/pc/platform/platform_common.c` (scripted input, interrupt clock), `src/pc/rng.c`.
- **Trả lời trong `docs/macos/reports/m2-determinism.md`:** smoke cố định input và thời gian bằng cách nào? Clock ngắt có chạy theo frame được không, hay phụ thuộc thời gian thật? Còn nguồn bất định nào khác (thời gian hệ thống, thứ tự thread audio)?
- **Acceptance:** report kèm đề xuất một chế độ "clock theo frame" nếu chưa có.

### T2.2 — Hook dump hash
- **Làm:** thêm env `MEMORIES_GOLDEN=<path>` và `MEMORIES_GOLDEN_EVERY=60`. Tại mỗi điểm VSync thứ N, ghi một dòng `frame ram_xxh64 scratch_xxh64 vram_xxh64`. Hàm hash tự viết (không thêm dependency), đặt trong file mới `src/pc/debug/golden.c`. Chỉ thêm đúng một lời gọi vào điểm VSync, nhớ ghi touch log. Cả build i386 lẫn LP64 phải dùng được hook này.
- **Acceptance:** chạy i386 hai lần liên tiếp với cùng một script cho ra file giống hệt nhau.

### T2.3 — Reference runner trên Linux x86
- **Làm:** `tools/pc/macos/golden_ref.sh <script>`: checkout đúng commit, `./build-pc.sh` (Linux, `MEMORIES_SKIP_WINDOWS=1`), chạy script với `MEMORIES_GOLDEN`, rồi xuất `tests/golden/<script>.txt`. Có hai chế độ: chạy qua SSH trên máy Linux x86 (disc nằm sẵn trên máy đó, không bao giờ upload qua CI), hoặc Docker `--platform linux/386` trên Mac (chậm, dùng làm dự phòng).
- **Acceptance:** tạo được file golden cho script `boot_title`.

### T2.4 — Công cụ so sánh
- **Làm:** `tools/pc/macos/golden.py compare <script>` chạy bản macOS, so từng dòng với file golden và dừng ở frame lệch đầu tiên. Ở frame đó, chạy lại với chế độ dump toàn bộ RAM (chỉ lưu local trong `tmp/`), diff với dump của reference (lấy qua runner), gom các vùng lệch rồi tra symbol từ `guest_addresses.txt` / `functions.csv`.
- **Acceptance:** cố tình làm hỏng một override, và tool chỉ ra đúng biến/struct bị lệch.

### T2.5 — Bộ script input
- **Làm:** thu input script (định dạng của upstream) cho: `boot_title`, `new_game_name_entry`, `first_story_duel`, `free_duel_basic`, `fusion_chain`, `password_shop`, `deck_build`, `overworld_walk`. Script chỉ chứa input, không chứa dữ liệu game, nên commit được.
- **Acceptance:** có golden cho từng script (sinh từ reference).

## Gate G2
`golden.py compare boot_title` cho kết quả rõ ràng (pass, hoặc chỉ ra điểm lệch đầu tiên).
