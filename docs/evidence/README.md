# docs/evidence/ — Minh chứng kiểm thử (KT2 + KT3)

Thư mục này chứa **log minh chứng** sinh ra tự động — không sửa tay.

## Sinh minh chứng
```powershell
.\dev.ps1 evidence        # Windows (khuyến nghị)
# tương đương:
py -3.12 tests/test_scenarios.py | Out-File -Encoding utf8 docs\evidence\minh_chung_KT2_KT3.txt
make evidence             # Git Bash / Linux / macOS
```

Kết quả: `docs/evidence/minh_chung_KT2_KT3.txt` (UTF-8 **có BOM** ⇒ mở bằng Notepad/Word không lỗi tiếng Việt).

## Nội dung log (25 minh chứng)
| Phần | Số mục | Nội dung |
|---|---|---|
| Xác thực | 1 | Đăng nhập RBAC lấy `access_token` (mọi API nghiệp vụ đều được bảo vệ) trước khi chạy minh chứng |
| KT2 | 13 | 11 bảng core + 5 bảng chatbot KT4 (⇒ 16 bảng), FastAPI chạy, CRUD, BR1–BR4, State Machine 6 trạng thái (4 bước bắt buộc qua `WAITING_RETURN` + kiểm tra `handed_over_at`), chặn nhảy cóc `RECEIVED -> COMPLETED` (10a) và chặn bỏ qua bước chờ trả máy `REPAIRING -> COMPLETED` (10b), Debug BR2, CRUD theo Serial |
| KT3 | 12 | `KT3-01` → `KT3-12`: AI-01 gợi ý phân loại lỗi, guardrail PII/prompt injection, prompt + validate đầu ra, human review 403/404/422/400, duyệt APPROVED/REJECTED, lưu vết `ai_results` |
| Tổng hợp | 3 bảng | `BANG TONG HOP TOAN BO MINH CHUNG KT2`, `... KT3`, `TONG KET CHUNG KT2 + KT3` |

Log kết thúc bằng:
```
- TONG CONG         : 25 | PASS: 25 | FAIL:  0
>>> XAC NHAN: TOAN BO 100% CAC MUC MINH CHUNG KT2 + KT3 DEU DAT (PASS)! <<<
```
Script trả **exit code 0** khi toàn bộ PASS (điều kiện để `.\dev.ps1 check` báo OK).

> Vòng đời phiếu 6 trạng thái: `RECEIVED → INSPECTING → REPAIRING → WAITING_RETURN → COMPLETED`
> (hoặc `INSPECTING → REJECTED`). Máy sửa xong vẫn phải ở `WAITING_RETURN` (chờ trả máy) và chỉ khi
> `COMPLETED` hệ thống mới ghi mốc `handed_over_at`.

## Minh chứng đăng nhập & phân quyền (Đợt 7)
- Script riêng: `tests/test_auth_rbac.py` (13 mục: đăng nhập 3 vai trò, 401/403, token hết hạn/giả mạo,
  thu hồi khi đăng xuất, vô hiệu hoá tài khoản, ma trận RBAC, chống khai khống `created_by`/`changed_by`,
  chỉ QUẢN LÝ xác nhận `REJECTED`, mật khẩu chỉ lưu dạng băm PBKDF2-HMAC-SHA256).
- Sinh minh chứng: `py -3.12 tests\test_auth_rbac.py` (exit code 0 = 13/13 PASS).

## Lưu ý khi chạy
- ⚠️ **Không chạy 2 tiến trình minh chứng cùng lúc** (`.\dev.ps1 test` / `.\dev.ps1 evidence` /
  `py -3.12 tests/test_scenarios.py`): script `drop_all/create_all` trên cùng một file CSDL nên chạy
  song song sẽ gây lỗi kiểu `ObjectDeletedError` hoặc kết quả sai.
- Nên tắt/dừng server demo (`.\dev.ps1 dev`) trước khi chạy minh chứng, vì script sẽ xoá và tạo lại CSDL.
- Sau khi chạy minh chứng, muốn có dữ liệu để chụp ảnh giao diện thì chạy `.\dev.ps1 seed` rồi F5 lại trình duyệt.

## Dùng cho báo cáo Word
- Dán trực tiếp đoạn log (font `Consolas` 8.5–9pt) cho phần "Kết quả kiểm thử" và bảng tổng hợp.
- Ảnh chụp giao diện/Swagger: xem checklist chi tiết tại
  [`../DANH_SACH_ANH_MINH_CHUNG_KT3.md`](../DANH_SACH_ANH_MINH_CHUNG_KT3.md) (12 mục KT3 cần chụp).
- Lưu ảnh minh chứng tạm thời vào thư mục này với tên theo mã: `KT3-01_ui.png`, `KT3-07a_system_prompt.png`…
