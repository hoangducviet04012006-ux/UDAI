# BÁO CÁO — HOÀN THIỆN NGHIỆP VỤ PHIẾU BẢO HÀNH (BaoHanhAI)

> Đợt bổ sung sau báo cáo `docs/BAO_CAO_HOAN_THIEN_HE_THONG.md`.
> Mục tiêu: làm cho **nghiệp vụ phiếu bảo hành hoạt động giống hệ thống bảo hành thực tế**,
> dùng được cho nhân viên **không chuyên kỹ thuật**: backend + CSDL + phân quyền + giao diện thống nhất.

**Quy trình mục tiêu (đã triển khai):**

```
TIẾP NHẬN MÁY → KIỂM TRA → GHI NHẬN CHẨN ĐOÁN → SỬA CHỮA → CHỜ TRẢ MÁY → HOÀN TẤT
   RECEIVED  → INSPECTING →  REPAIRING  → WAITING_RETURN → COMPLETED
                              ↘ Từ chối bảo hành (REJECTED, chỉ Quản lý)
```

---

## 1. Tóm tắt thay đổi nghiệp vụ

| # | Nội dung | Trước đây | Sau khi hoàn thiện |
|---|---|---|---|
| 1 | Thông tin xử lý của phiếu | Chỉ có `issue_description` + ghi chú trong lịch sử trạng thái | Thêm cột **chẩn đoán** (kết luận kỹ thuật viên), **nội dung đã sửa + linh kiện thay**, **ghi chú bàn giao** (10 cột mới trên `warranty_tickets`) |
| 2 | Ba nguồn thông tin | Trộn lẫn trong một câu | Tách rõ: **khách mô tả** (`issue_description`) – **AI gợi ý** (`ai_results`) – **kỹ thuật viên kết luận** (`diagnosis_*`, `repair_*`) |
| 3 | Chuyển trạng thái | Chỉ cần đúng state machine | Mỗi bước **bắt buộc kèm thông tin xử lý** (`WORKFLOW_INPUT_REQUIRED` nếu bỏ trống) |
| 4 | Hoàn tất phiếu | Chỉ cần ở `WAITING_RETURN` | Checklist điều kiện: phiếu + thiết bị + khách hàng tồn tại, đã ghi thông tin sửa chữa, lịch sử đủ 4 bước |
| 5 | Chờ trả máy | Chỉ là một trạng thái | Là **bước nghiệp vụ thật**: hiển thị "Thiết bị đã sửa xong và đang chờ khách nhận máy", có mốc hoàn thành sửa chữa + người hoàn thành |
| 6 | Ghi nhận chuyên môn | Phải chuyển trạng thái mới ghi được | Thêm API `PATCH /{id}/diagnosis` và `PATCH /{id}/repair` — ghi dữ liệu **không đổi trạng thái** |
| 7 | Phân quyền | 20 quyền / 3 vai trò | **23 quyền** — thêm `ticket.diagnose`, `ticket.repair`, `ticket.handover`; chặn 403 theo **từng bước** |
| 8 | Thông báo lỗi | Chỉ `detail` kỹ thuật (`[BR3 FAIL]`, `STATE MACHINE ERROR`…) | Thêm `message` (tiếng Việt) + `hint` (việc cần làm); giao diện ưu tiên `message` |
| 9 | Màn hình phiếu | Modal 6 khối, thiếu chẩn đoán/sửa chữa, phải sang màn khác | **Một màn hình**: A–G + nút hành động theo quyền + checklist + lịch sử + gợi ý AI |
| 10 | Danh sách phiếu | Lọc trạng thái; tìm mã/serial/tên | Thêm **tìm theo số điện thoại**, **"Phiếu của tôi"**, cột nhân viên phụ trách và loại lỗi |
| 11 | Bảng điều khiển | Số liệu chung cho mọi vai trò | Khối **"Việc cần làm" theo vai trò** + nút chuyển phạm vi *Toàn hệ thống / Việc của tôi* |
| 12 | AI-01 | AI chỉ gợi ý (đã đúng) | Giữ nguyên: AI **không** tự ghi `error_category_id`, **không** đổi trạng thái; nếu thiếu dữ liệu hiện "Chưa đủ thông tin để gợi ý loại lỗi" + câu hỏi cần hỏi thêm khách |


---

## 2. File đã sửa / đã tạo

### 2.1. Backend
| File | Nội dung |
|---|---|
| `backend/app/models.py` | Thêm 10 cột nghiệp vụ cho `warranty_tickets` + 3 quan hệ người thực hiện (chẩn đoán / sửa chữa / bàn giao) |
| `backend/app/services/schema_migration.py` | **Mới** – nâng cấp CSDL đang dùng bằng `ALTER TABLE ADD COLUMN` (idempotent, không mất dữ liệu, chạy cả SQLite & PostgreSQL) |
| `backend/app/services/warranty_rules.py` | `BusinessRuleError` (kèm `message` tiếng Việt), `TRANSITION_RULES` (nhãn nút + quyền + trường nghiệp vụ), `available_transitions`, `validate_transition_input`, `completion_blockers/checklist`, `validate_ticket_completion`, `validate_error_category_exists`; 5 lỗi BR1–BR5 trả kèm câu tiếng Việt (giữ nguyên `detail` cũ) |
| `backend/app/services/ticket_view.py` | **Mới** – dựng payload màn hình phiếu: khối A–G, tiến trình 5 bước, gợi ý AI, lịch sử có tên người, `available_actions`, `completion_checklist`, `permission_notes`, workload theo vai trò |
| `backend/app/schemas.py` | `WarrantyTicketStatusUpdate` nhận thêm trường nghiệp vụ; thêm `TicketDiagnosisUpdate`, `TicketRepairUpdate`, `WarrantyTicketDetailResponse` và các schema chi tiết; danh sách bổ sung `customer_phone`, `error_category_name`, `handler_name`, `status_label` |
| `backend/app/crud/warranty_tickets.py` | Lưu thông tin xử lý theo bước, chốt mốc `repair_at`/`handed_over_by`, ghi `repair_logs`, chặn hoàn tất thiếu điều kiện, tìm kiếm theo mã/serial/tên/SĐT, đếm phiếu theo nhân viên |
| `backend/app/routers/warranty_tickets.py` | Chi tiết phiếu trả đủ dữ liệu màn hình xử lý; `GET /` hỗ trợ `q` + `mine`; thêm `GET /meta/workflow`, `PATCH /{id}/diagnosis`, `PATCH /{id}/repair`; chặn quyền theo từng bước |
| `backend/app/services/auth_service.py` | 3 quyền mới (`ticket.diagnose`, `ticket.repair`, `ticket.handover`) và phân bổ theo vai trò |
| `backend/app/main.py` | Bộ xử lý `BusinessRuleError` → `{detail, message, error_code, hint}`; chạy nâng cấp schema khi khởi động |
| `database/postgres_schema.sql` | Bổ sung 10 cột + 3 FK mới cho bảng `warranty_tickets` |
| `tests/init_db.py` | Báo cáo số cột nghiệp vụ được bổ sung khi chạy `.\dev.ps1 initdb` |
| `tests/seed_data.py` | Phiếu mẫu `TK-20260510-0001` (Chờ trả máy) có chẩn đoán + nội dung sửa chữa + linh kiện + nhật ký `repair_logs`; phiếu `TK-INIT-OPEN-001` có chẩn đoán sơ bộ |

### 2.2. Frontend
| File | Nội dung |
|---|---|
| `frontend/index.html` | Modal phiếu được thiết kế lại thành **màn hình xử lý một trang** (A–G, khối hành động, checklist); modal xác nhận hỗ trợ **nhiều trường**; danh sách phiếu có nút "Phiếu của tôi" + tìm theo SĐT; bảng điều khiển có khối "Việc cần làm" + chuyển phạm vi xem |
| `frontend/app.js` | Vẽ màn hình phiếu từ dữ liệu backend (`renderTicketWorkspace`, `renderDiagnosisSection`, `renderRepairSection`, `renderHandoverSection`, `renderCompletionChecklist`, `renderStepsHtml`); nút hành động lấy từ `available_actions`; hộp thoại xác nhận đa trường (`showActionModal`); ghi chẩn đoán/sửa chữa (`openDiagnosisModal`, `openRepairModal`, `saveDiagnosis`, `saveRepair`); `errorMessage` ưu tiên `message` tiếng Việt; bảng điều khiển theo vai trò (`renderWorkload`, `setDashScope`); lọc/tìm kiếm có SĐT + "Phiếu của tôi" |
| `frontend/styles.css` | Không đổi (dùng lại hệ class có sẵn: `glass-panel`, `btn-*`, `badge-*`, `table-*`) |

### 2.3. Kiểm thử & công cụ
| File | Nội dung |
|---|---|
| `tests/test_ticket_workflow.py` | **Mới** – 10 kịch bản CASE 1–8 (exit code 0/1) |
| `tests/smoke_frontend.js` | **Mới** – 8 kiểm tra lớp hiển thị bằng Node (không cần trình duyệt) |
| `dev.ps1` | Thêm task `workflow`, `ui`; `check` nay chạy đủ 3 lớp: minh chứng KT2/KT3 → nghiệp vụ phiếu → giao diện |
| `docs/BAO_CAO_NGHIEP_VU_PHIEU_BAO_HANH.md` | Báo cáo này |

### 2.4. Nâng cấp CSDL không mất dữ liệu
`backend/app/services/schema_migration.py` chạy tự động khi khởi động ứng dụng và khi chạy `.\dev.ps1 initdb`:
- Chỉ `ALTER TABLE warranty_tickets ADD COLUMN ...` cho cột còn thiếu — **không** xoá/đổi cột cũ.
- Cột mới đều cho phép `NULL` nên dữ liệu hiện có vẫn hợp lệ; chạy lại nhiều lần không gây lỗi.
- Ứng dụng vẫn khởi động được kể cả khi CSDL ở chế độ chỉ đọc (chỉ ghi log cảnh báo).

**Không thay đổi (để không phá phần đã hoàn thành):** BR1–BR4, ma trận `ALLOWED_TRANSITIONS` (vẫn bắt buộc qua
`WAITING_RETURN`), cơ chế token/RBAC hiện có, bảng `ticket_status_history`, và toàn bộ nội dung minh chứng KT2/KT3.

---

## 3. Hành vi nghiệp vụ chi tiết (những gì backend bắt buộc)

### 3.1. Ma trận hành động (nguồn sự thật: `TRANSITION_RULES`)

| Từ trạng thái | Hành động (nhãn nút) | Quyền cần có | Thông tin bắt buộc kèm theo |
|---|---|---|---|
| Mới tiếp nhận | Chuyển sang kiểm tra | `ticket.update_status` | Ghi chú (không bắt buộc) |
| Đang kiểm tra | Bắt đầu sửa chữa | `ticket.update_status` | Kết luận chẩn đoán **hoặc** ghi chú kỹ thuật |
| Đang kiểm tra | Từ chối bảo hành | `ticket.reject` (chỉ Quản lý) | **Lý do từ chối** (BR5) |
| Đang sửa chữa | Sửa xong – Chờ trả máy | `ticket.update_status` | **Nội dung đã sửa** hoặc ghi chú kỹ thuật (chốt `repair_at`, ghi `repair_logs`) |
| Đang sửa chữa | Cần kiểm tra lại | `ticket.update_status` | Lý do kiểm tra lại |
| Chờ trả máy | **Xác nhận đã trả máy** | `ticket.handover` (Tiếp nhận / Quản lý) | **Thông tin bàn giao** → ghi `handed_over_at`, `handed_over_by`, `handover_note` |
| Chờ trả máy | Khách báo còn lỗi – Sửa lại | `ticket.update_status` | Lý do sửa lại |
| Đã hoàn tất / Từ chối | (không còn hành động) | – | – |

Ghi chú: **Kỹ thuật viên không có** `ticket.reject` và `ticket.handover`; **Nhân viên tiếp nhận không có**
`ticket.diagnose`/`ticket.repair`. Giao diện chỉ vẽ nút theo `available_actions` do backend trả về, còn
backend vẫn kiểm tra quyền ở từng request (401/403) — không chỉ ẩn nút.

### 3.2. Điều kiện hoàn tất (chuỗi kiểm tra thật khi bấm "Xác nhận đã trả máy")
1. Phiếu tồn tại, người thực hiện là nhân viên có thật.
2. Chuyển trạng thái hợp lệ (`WAITING_RETURN → COMPLETED`), bắt buộc đi qua "Chờ trả máy".
3. Thiết bị của phiếu tồn tại; khách hàng của phiếu tồn tại.
4. Đã ghi nhận **thông tin sửa chữa** (nội dung/ghi chú hoặc mốc `repair_at`).
5. Lịch sử đã có đủ 4 bước (Tiếp nhận → Kiểm tra → Sửa chữa → Chờ trả máy).
6. Có thông tin bàn giao (ghi chú / người nhận).

Thiếu bất kỳ mục nào → HTTP 400 với `message` tiếng Việt, ví dụ:
> "Chưa thể hoàn tất phiếu. Thiết bị vẫn đang ở trạng thái sửa chữa, cần chuyển sang "Chờ trả máy" sau khi sửa xong,
> rồi mới xác nhận đã trả máy cho khách."

### 3.3. Mã lỗi nghiệp vụ trả về (trường `error_code`)
`BR1_SERIAL_NOT_FOUND`, `BR2_WARRANTY_EXPIRED`, `BR3_OPEN_TICKET_EXISTS`, `BR4_OWNER_MISMATCH`,
`BR5_REJECTION_REASON_REQUIRED`, `STATE_MACHINE_ERROR`, `WORKFLOW_INPUT_REQUIRED`,
`WORKFLOW_COMPLETE_BLOCKED`, `WORKFLOW_STATE_CLOSED`, `TICKET_NOT_FOUND`, `ERROR_CATEGORY_NOT_FOUND`.
Trường `detail` (kỹ thuật) được giữ nguyên để không phá các minh chứng KT2/KT3 đang trích nó.

### 3.4. Gợi ý AI không trở thành kết luận
- `error_category_id` của phiếu chỉ được ghi khi **người có quyền** xác nhận (kỹ thuật viên qua
  `PATCH /{id}/diagnosis`, hoặc duyệt kết quả AI qua `PATCH /ai/results/{id}/review`).
- AI không đổi trạng thái phiếu; nếu AI không đủ căn cứ, màn hình phiếu hiển thị
  "Chưa đủ thông tin để gợi ý loại lỗi" + danh sách thông tin cần hỏi thêm khách hàng.


---

## 4. Kiểm thử đã chạy và kết quả

### 4.1. Lệnh đã chạy (theo thứ tự, **không chạy song song** vì dùng chung file SQLite)
```powershell
py -3.12 -m compileall -q backend\app tests        # 1. cú pháp toàn bộ backend + test
node --check frontend\app.js                       # 2. cú pháp JavaScript
py -3.12 tests\test_scenarios.py                   # 3. 25 minh chứng KT2 + KT3
py -3.12 tests\test_auth_rbac.py                   # 4. 13 minh chứng RBAC
py -3.12 tests\test_ticket_workflow.py             # 5. 10 kịch bản vòng đời phiếu
node tests\smoke_frontend.js                       # 6. 8 kiểm tra lớp hiển thị
.\dev.ps1 check                                    # 7. cổng kiểm tra tổng hợp (chạy cả 3 lớp trên)
```

### 4.2. Kết quả từng bộ
| # | Bộ kiểm thử | Nội dung | Kết quả | Exit code |
|---|---|---|---|---|
| 1 | `compileall backend\app tests` | Cú pháp Python toàn bộ backend + test | OK | 0 |
| 2 | `node --check frontend\app.js` | Cú pháp JavaScript | OK | 0 |
| 3 | `tests/test_scenarios.py` | 13 minh chứng KT2 + 12 minh chứng KT3 | **25/25 PASS** | 0 |
| 4 | `tests/test_auth_rbac.py` | 13 minh chứng đăng nhập & phân quyền | **13/13 PASS** | 0 |
| 5 | `tests/test_ticket_workflow.py` | 10 kịch bản CASE 1–8 (bảng dưới) | **10/10 PASS** | 0 |
| 6 | `tests/smoke_frontend.js` | 8 kiểm tra hàm hiển thị | **8/8 PASS** | 0 |

### 4.3. Chi tiết 10 kịch bản vòng đời phiếu
| CASE | Nội dung kiểm | Kết quả |
|---|---|---|
| CASE 1 | Tiếp nhận → Kiểm tra → Sửa chữa → Chờ trả máy → Hoàn tất; lưu đủ chẩn đoán, nội dung sửa, linh kiện, nhật ký `repair_logs`, người trả máy | PASS |
| CASE 2 | `REPAIRING → COMPLETED` (bỏ qua "Chờ trả máy") bị chặn 400, phiếu giữ nguyên, `message` tiếng Việt không chứa mã kỹ thuật | PASS |
| CASE 3a | Kỹ thuật viên tạo phiếu → 403; Nhân viên tiếp nhận ghi chẩn đoán → 403 | PASS |
| CASE 3b | Kỹ thuật viên tự "Xác nhận đã trả máy" → 403 (chỉ Tiếp nhận/Quản lý) | PASS |
| CASE 4a | AI gợi ý xong: phiếu **vẫn chưa** có `error_category_id`, trạng thái không đổi | PASS |
| CASE 4b | Chỉ sau khi người có quyền duyệt thì nhãn lỗi mới được ghi vào phiếu, trạng thái vẫn không đổi | PASS |
| CASE 5 | "Chờ trả máy" hiện đúng ở bảng điều khiển (workload `mine`), danh sách (kèm người phụ trách + SĐT khách) và chi tiết phiếu | PASS |
| CASE 6 | Hoàn tất → lịch sử đủ 5 bước đúng nhãn tiếng Việt, mỗi bước có thời gian + người thực hiện + ghi chú | PASS |
| CASE 7 | Gọi lại API nhiều lần ("tải lại trang") + đối chiếu trực tiếp CSDL: trạng thái, lịch sử, `handed_over_by`, nhật ký sửa chữa khớp | PASS |
| CASE 8 | Đăng nhập 3 vai trò: quyền backend đúng (Quản lý 23 / Tiếp nhận 16 / Kỹ thuật 12) và nút hành động hiển thị đúng theo vai trò | PASS |

### 4.4. Chi tiết 8 kiểm tra lớp hiển thị
Nhãn trạng thái tiếng Việt · thông báo lỗi ưu tiên `message` (không lộ `STATE MACHINE ERROR`) ·
thanh tiến trình 5 bước có bước hiện tại · hộp thoại xác nhận hiển thị thiết bị + phiếu + khách hàng ·
khối "Việc cần làm" theo vai trò · checklist điều kiện hoàn tất · lịch sử xử lý có người/thời gian/ghi chú ·
nút hành động chỉ vẽ theo `available_actions`. → **8/8 PASS**.

### 4.5. Kiểm tra thủ công thêm (đã thực hiện)
- Chạy thật server `uvicorn` và gọi HTTP: `/` (200, có đủ id mới của màn hình phiếu), `/static/app.js` (200),
  `/static/styles.css` (200), `/docs` (200).
- Đăng nhập `technician01` và gọi API thật: `GET /warranty-tickets/meta/workflow` → 5 bước, ở trạng thái
  *Chờ trả máy* chỉ có hành động "Khách báo còn lỗi – Sửa lại" (không có nút trả máy) ⇒ đúng phân quyền;
  `GET /stats/summary?mine=1` → `scope=MINE`; `GET /?q=0912345678` → tìm được phiếu theo số điện thoại.


---

## 5. Đối chiếu 16 tiêu chí hoàn thành

| # | Tiêu chí | Trạng thái | Bằng chứng |
|---:|---|---|---|
| 1 | Luồng phiếu bảo hành hoạt động hoàn chỉnh | ✔ | CASE 1 |
| 2 | Không thể bỏ qua trạng thái | ✔ | CASE 2 (400) + `ALLOWED_TRANSITIONS` không đổi |
| 3 | "Chờ trả máy" là trạng thái nghiệp vụ thực | ✔ | CASE 1/5 + `handover.status_message`, `repair_completed_at` |
| 4 | Hoàn tất chỉ sau khi trả máy | ✔ | CASE 2/6 + `validate_ticket_completion` |
| 5 | Lịch sử đầy đủ | ✔ | CASE 6 (5 bước, đủ nhãn/thời gian/người/ghi chú) |
| 6 | Người thực hiện được ghi nhận | ✔ | CASE 1/7 (`changed_by`, `repair_by`, `handed_over_by`) |
| 7 | Phân quyền backend hoạt động | ✔ | CASE 3a/3b/8 (403 thật, 23/16/12 quyền) |
| 8 | UI dễ hiểu với người không biết kỹ thuật | ✔ | Màn hình A–G + câu mô tả từng bước + checklist |
| 9 | Không lộ mã kỹ thuật trong giao diện | ✔ | `message`/`hint` từ backend; CASE 2 assert `message` không chứa `[` |
| 10 | AI chỉ đóng vai trò gợi ý | ✔ | CASE 4a/4b |
| 11 | Không phá chức năng hiện tại | ✔ | 25/25 KT2+KT3 và 13/13 RBAC vẫn PASS |
| 12 | Không tạo dữ liệu rác | ✔ | Chỉ bổ sung thông tin xử lý cho 2 phiếu mẫu sẵn có trong seed |
| 13 | Tự chạy kiểm tra sau khi sửa | ✔ | §4.1 |
| 14 | Tự sửa lỗi phát hiện | ✔ | Đã phát hiện & sửa 3 lỗi trong quá trình kiểm thử (xem §6.2) |
| 15 | Nghiệp vụ + backend + CSDL + frontend + RBAC thống nhất | ✔ | Cùng một nguồn sự thật: `TRANSITION_RULES` → `available_actions` → nút trên giao diện |
| 16 | Báo cáo chính xác file/nghiệp vụ/test/lỗi còn lại | ✔ | Báo cáo này (§2, §3, §4, §6) |

---

## 6. Lỗi còn tồn tại / giới hạn đã biết

### 6.1. Giới hạn có chủ ý (không nằm trong phạm vi yêu cầu)
1. **Kỹ thuật viên không trả máy cho khách**: quy trình yêu cầu máy phải ra quầy để Tiếp nhận/Quản lý xác nhận bàn giao.
   Với trung tâm chỉ có 1 người, quản lý cần xác nhận bước này (hoặc cấp thêm quyền `ticket.handover` cho kỹ thuật viên).
2. **Nhân viên tiếp nhận vẫn có thể chuyển Đang kiểm tra → Đang sửa chữa** (với ghi chú bắt buộc) để không chặn công việc
   khi kỹ thuật viên vắng; dữ liệu chẩn đoán chuyên môn vẫn chỉ kỹ thuật viên/quản lý ghi được.
3. **Chưa có tệp đính kèm ảnh tình trạng máy** và **chưa có tính phí sửa chữa ngoài bảo hành** (ngoài phạm vi Prompt 1).
4. **Chưa có thông báo tự động cho khách** (SMS/email) khi máy sửa xong — hiện nhân viên gọi khách thủ công theo cột "Chờ trả máy".
5. **Phân trang danh sách phiếu**: API có `skip/limit`, giao diện đang tải tối đa 200 phiếu một lần (phù hợp quy mô đồ án).

### 6.2. Lỗi đã phát hiện và sửa trong quá trình kiểm thử
| # | Lỗi phát hiện | Cách sửa |
|---|---|---|
| 1 | Danh sách phiếu thiếu `handler_name`, `customer_phone`, `error_category_name`, `status_label` (bị `response_model` của danh sách lọc bỏ) | Bổ sung 4 trường vào `WarrantyTicketResponse`; thêm assertion CASE 5 để không tái diễn |
| 2 | Lỗi `NameError: Customer` khi lọc danh sách (thiếu import sau khi thêm join) | Bổ sung import trong `crud/warranty_tickets.py` |
| 3 | Ở giao diện, nút "Xác nhận đã trả máy" vẫn hiện với kỹ thuật viên (vì quyền của bước đang là `ticket.update_status`) | Gán quyền bước hoàn tất cho `ticket.handover` trong `TRANSITION_RULES` + chặn 403 ở router |

### 6.3. Rủi ro vận hành cần lưu ý
- **Không chạy song song** hai script kiểm thử (chúng `drop_all/create_all` trên cùng file SQLite → xung đột giả).
- Khi sao chép CSDL cũ sang máy khác: chạy `.\dev.ps1 initdb` (hoặc mở ứng dụng một lần) để tự nâng cấp cột mới.

---

## 7. Cách chạy demo và kiểm tra lại

```powershell
# 0) Nếu chưa có môi trường: .\dev.ps1 install
.\dev.ps1 initdb        # tạo 16 bảng + tự bổ sung cột nghiệp vụ phiếu cho CSDL cũ
.\dev.ps1 seed          # dữ liệu mẫu (có phiếu TK-20260510-0001 ở trạng thái Chờ trả máy)
.\dev.ps1 dev           # mở http://127.0.0.1:8000/  (đăng nhập theo 3 tài khoản demo)

.\dev.ps1 workflow      # kiểm thử vòng đời phiếu (CASE 1..8)
.\dev.ps1 ui            # smoke test hiển thị (cần Node.js)
.\dev.ps1 check         # cổng kiểm tra tổng hợp trước khi nộp
```

**Kịch bản demo đề xuất (5 phút, 3 vai trò, 2 luồng hoàn chỉnh):**

* **Ca 1 – Sửa chữa bảo hành (Thiết bị lỗi linh kiện nhà sản xuất, đủ điều kiện bảo hành):**
  1. `receptionist01` (Tiếp nhận): Tiếp nhận thiết bị Asus Zenbook (`SN-ASUS-ROG-2026-001`, còn hạn bảo hành 18 tháng, tem nguyên vẹn, lỗi sập nguồn tự nhiên trong điều kiện sử dụng bình thường). Tạo phiếu bảo hành mới ở trạng thái `RECEIVED` (Tiếp nhận).
  2. `manager01` (Quản lý): Mở phiếu vừa lập, bấm nút **Phân công KTV**, chọn `technician01` (Lê Kỹ Thuật) phụ trách phiếu.
  3. `technician01` (Kỹ thuật viên): Thấy phiếu trong danh sách "Phiếu được giao". Bấm **Bắt đầu kiểm tra** (`INSPECTING`). Sau khi tháo máy kiểm tra bo mạch, xác định chập IC nguồn chính RT8205 do lỗi linh kiện từ nhà sản xuất, tem niêm phong nguyên vẹn, không ngấm chất lỏng. KTV bấm **Bắt đầu sửa chữa** (`REPAIRING`), xác nhận đủ điều kiện bảo hành.
  4. `technician01`: Thay IC nguồn RT8205 và tụ lọc chính hãng, chạy thử test tải 60 phút nhiệt độ ổn định. KTV bấm **Hoàn tất sửa chữa** (`COMPLETED`), xác nhận kiểm tra sau sửa đạt yêu cầu. Phiếu chuyển sang chờ trả máy. KTV không có quyền trả máy.
  5. `receptionist01`: Mở phiếu đang ở trạng thái Hoàn tất, bấm **Xác nhận trả máy** (`RETURNED`), ghi nhận thông tin bàn giao máy cho khách tại quầy. Phiếu được đóng với kết quả `resolution = 'COMPLETED'`.

* **Ca 2 – Từ chối bảo hành (Thiết bị hết hạn theo quy định BR2 của chính sách mẫu):**
  1. `receptionist01`: Khách mang máy Samsung Galaxy (`SN-SAMS-EXPIRED-02`, đã quá hạn bảo hành 70 ngày) đến kiểm tra. Tiếp nhận lập phiếu ở trạng thái `RECEIVED` để phòng kỹ thuật kiểm tra hiện trạng thiết bị. Hệ thống tự động ghi nhận máy quá hạn bảo hành.
  2. `manager01`: Quản lý phân công `technician01` kiểm tra máy.
  3. `technician01`: Bấm **Bắt đầu kiểm tra** (`INSPECTING`). Hệ thống chặn tuyệt đối không cho chuyển sang sửa chữa bảo hành miễn phí (`REPAIRING`). KTV lập biên bản kiểm tra và bấm **Đề xuất từ chối bảo hành**, ghi nhận thiết bị đã hết thời hạn bảo hành tiêu chuẩn theo quy định BR2.
  4. `manager01`: Mở phiếu xem đề xuất của KTV, bấm **Từ chối bảo hành** (`REJECTED`), phê duyệt lý do từ chối căn cứ quy định thời hạn bảo hành của nhà sản xuất.
  5. `receptionist01`: Mở phiếu ở trạng thái Từ chối, bấm **Xác nhận trả máy** (`RETURNED`), bàn giao lại máy nguyên trạng cho khách kèm biên bản từ chối bảo hành và tư vấn dịch vụ sửa chữa tính phí. Phiếu đóng với kết quả `resolution = 'REJECTED'`.

---

## 8. Liên quan: màn hình công việc theo vai trò (đợt tiếp theo)

Bảng điều khiển **Tổng quan** sau đó được nâng cấp thành *màn hình công việc theo vai trò*
(Quản lý / Tiếp nhận / Kỹ thuật viên), kèm menu do backend trả về, bộ lọc "việc của tôi" chạy ở SQL
và nút hành động theo trạng thái + quyền trên từng dòng phiếu:
xem `docs/BAO_CAO_MAN_HINH_CONG_VIEC_THEO_VAI_TRO.md` (kiểm thử `.\dev.ps1 workbench`, CASE A..H).
Luồng phiếu (6 trạng thái, quyền theo bước) **không thay đổi** trong đợt đó.

