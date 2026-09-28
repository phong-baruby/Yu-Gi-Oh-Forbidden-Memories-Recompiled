---
description: Tự review diff hiện tại theo các luật của fork macOS
---
Review `git diff` (cả staged lẫn unstaged). Gắn mức 🔴 BLOCKING / 🟡 SUGGESTION / 🟢 NIT cho từng phát hiện, và sửa hết 🔴 trước khi báo cáo.

**Luật bất biến**
- [ ] Không có thay đổi trong `src/game/`, `src/overlays/`, `src/psyq/`, `src/ygo_types.h`, `src/types.h`
- [ ] Mọi thay đổi trên file dùng chung của upstream đều nằm trong guard (`MEMORIES_LP64` / `__APPLE__` / `__aarch64__`) và đã được ghi vào Upstream touch log
- [ ] Khi không có `MEMORIES_LP64`, các macro mới expand ra đúng code cũ (build i386 và `make match` không đổi)
- [ ] Không có dữ liệu game, đường dẫn tuyệt đối tới disc, hay output của `tmp/` trong diff

**Đúng đắn LP64**
- [ ] Không còn cast ngầm giữa con trỏ 64-bit và `uint32_t` (không có `(uint32_t)ptr` hay `(T *)u32` trần; phải đi qua `H2G`/`G2H`)
- [ ] `G2H(0)` và NULL được xử lý ở mọi chỗ mới
- [ ] Số học con trỏ trên guest address được tính đúng kích thước phần tử
- [ ] Mọi override mới trong `config/lp64/overrides.toml` đều có comment lý do và khớp theo pattern (không theo số dòng)

**arm64 / macOS**
- [ ] Không ghi vào `__TEXT`; code động chỉ nằm trong vùng `MAP_JIT` và có invalidate icache
- [ ] Assembly giữ đúng AAPCS64 (callee-saved x19–x29, x30, sp, d8–d15; không đụng x18); symbol có tiền tố `_`
- [ ] Không phụ thuộc runtime vào Homebrew; dependency đều được pin kèm SHA-256

**Chất lượng**
- [ ] Có test cho logic mới (dịch địa chỉ, relocation, rebase, bảng hàm)
- [ ] Log lỗi đủ thông tin (địa chỉ guest cùng symbol gần nhất khi có thể)
- [ ] Không có refactor ngoài scope của task
