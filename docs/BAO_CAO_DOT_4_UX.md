# BÁO CÁO ĐỢT 4 — TÁI CẤU TRÚC UX FRONTEND (BaoHanhAI)

> **Trạng thái:** ĐÃ THỰC HIỆN XONG (G1 → G4) — có kiểm chứng sau mỗi giai đoạn.
> **Ngày thực hiện:** 27/09/2026 · Kiểm tra bằng đọc code + chạy hệ thống thật (server + API + DB).
> **Căn cứ:** `docs/AUDIT_DOT_4_UX.md` (audit 257 dòng đã được duyệt, phạm vi G1→G4).
> **Kết quả chốt:** `node --check` OK · kiểm tra ngôn ngữ/UI **49/49 PASS** · `.\dev.ps1 check` **24/24 PASS** (KT2 12/12, KT3 12/12) · E2E **76 PASS / 0 FAIL**.

---

## 1. Mục tiêu & nguyên tắc

| # | Nguyên tắc | Cách thực hiện |
|---|---|---|
| 1 | **Chỉ sửa `frontend/`** | Chỉ đổi `index.html`, `app.js`, `README.md`. **Không** sửa backend, CSDL, API, `tests/**` (kiểm chứng bằng dấu thời gian: file backend/tests mới nhất = 25/09/2026, thuộc Đợt 1). |
| 2 | **Không thêm API, không thêm module** | Chỉ dùng 31 endpoint đang có; mọi thông tin mới đều **tính từ dữ liệu API đang dùng**. |
| 3 | **Không dữ liệu giả, không hard-code** | Số thiết bị / số phiếu của khách, số thiết bị của sản phẩm, tình trạng bảo hành đều tính từ `state.devices`, `state.tickets`, `warranty_end_date`. |
| 4 | **Không đổi nghiệp vụ** | `OPEN_TICKET_STATUSES`, `ALLOWED_TRANSITIONS`, BR1–BR4 + BR5 (lý do từ chối), AI-01 human-in-the-loop giữ nguyên; giao diện **chỉ hiển thị**, quyết định vẫn ở backend. |
| 5 | **Giữ tinh thần visual** | HTML/CSS/JS thuần, dark theme, `styles.css` **không đổi** (dùng lại class `.btn*`, `.table-*`, `.glass-panel`, `.chip`…). |
| 6 | **Kiểm chứng sau mỗi nhóm việc** | `node --check` → kiểm tra UI/ngôn ngữ (49 mục) → `.\dev.ps1 check` (24/24) → E2E trên server thật. |

## 2. Cấu trúc menu sau Đợt 4 (7 mục)

| # | Menu | Thay đổi chính so với trước |
|---|---|---|
| 1 | **Tổng quan** | Thêm khối **Thao tác nhanh** (4 nút + ô tra cứu nhanh), tách thẻ **Chờ tiếp nhận**, đổi bảng "5 phiếu mới nhất" → **Phiếu đang xử lý**, hạ khối **Quy tắc nghiệp vụ** xuống cuối trang |
| 2 | **Tra cứu bảo hành** *(mới)* | Gộp 3 cửa vào cũ (tìm thiết bị / tra mã phiếu / kiểm tra hạn) thành **1 ô nhập** + 1 card kết quả thống nhất |
| 3 | **Khách hàng** | Bỏ cột `#id`, thêm **Số thiết bị / Số phiếu**, thêm **Chi tiết khách**, tiêu đề modal đổi sang tên thật |
| 4 | **Sản phẩm** | Bỏ cột `#id`, thêm **Số thiết bị đang quản lý**, tiêu đề modal đổi sang tên sản phẩm |
| 5 | **Thiết bị** | Thêm cột **Tình trạng bảo hành**, nút **Chi tiết** (modal), **kiểm tra bảo hành theo từng dòng**, bỏ danh sách "chọn nhanh" trùng lặp |
| 6 | **Phiếu bảo hành** | **Wizard tiếp nhận 2 bước**, tìm kiếm theo mã/sê-ri/khách, chi tiết phiếu có **tiến trình 4 bước** + nhân viên phụ trách |
| 7 | **Hỗ trợ xác định lỗi** | Giữ nguyên luồng AI + xác nhận; modal phiếu nay xác nhận được ngay trong modal |


---

## 3. Chi tiết việc đã làm (đối chiếu từng mã việc trong audit)

### G1 — Tinh giản, thống nhất từ ngữ (C1, C2, C3, B4, A9) ✅

| Mã | Nội dung | Kết quả trong code |
|---|---|---|
| C1 | Thống nhất **"Số sê-ri"** | Nhãn/nơi hiển thị/placeholder/thông báo dùng "Số sê-ri"; **không đổi tên field API** (`serial_number`). |
| C2 | Nút bị mờ phải có giải thích tại chỗ | Wizard không còn nút bị mờ; chỗ **còn** nút mờ (xác nhận gợi ý lỗi trong modal) đã có dòng hướng dẫn ngay dưới: *"Hai nút Xác nhận / Không dùng chỉ bật khi phiếu có kết quả gợi ý đang chờ duyệt — hãy bấm Phân tích phiếu này trước."* |
| C3 | Bỏ công cụ "Kiểm tra hạn bảo hành" gần giống tên nút "Kiểm tra" | Công cụ trùng lặp bị gỡ; chỉ còn **một** điểm kiểm tra (tab Tra cứu + chi tiết thiết bị, đều gọi `POST /api/v1/debug/check-warranty`). |
| B4 | Bỏ cột `#id` ở Khách hàng/Sản phẩm | `<th>Mã</th>` không còn trong `index.html`; `renderCustomers`/`renderProducts` không in `${c.id}`/`${p.id}`; colspan cập nhật (Khách hàng 6→7, Sản phẩm vẫn 6). |
| A9 | Chọn người thực hiện trong hộp thoại chuyển trạng thái | `showActionModal` nhận `selectLabel/selectOptions/selectDefault`; select "Người thực hiện" nằm trong `#action-modal`, giá trị vẫn ghi đúng `changed_by` (E2E bước 14b kiểm `[2, 3]`). |

### G2 — Tổng quan, Thiết bị, Phiếu (A1, A2, A5, A6, A7, A8) ✅

| Mã | Nội dung | Kết quả trong code |
|---|---|---|
| A1 | **Thao tác nhanh** ở Tổng quan | 4 nút: Tiếp nhận thiết bị · Tạo phiếu bảo hành · Tra cứu bảo hành · Hỗ trợ xác định lỗi (`quickAction()`), kèm ô `#dash-lookup-input` tra cứu nhanh (`dashLookup()` chuyển tab và chạy luôn). |
| A2 | Tách "Chờ tiếp nhận" + bảng **Phiếu đang xử lý** | Thẻ `#stat-received` lấy `stats.received`; bảng `#dash-active-body` chỉ chứa `RECEIVED/INSPECTING/REPAIRING`, ưu tiên phiếu lâu nhất (`renderActiveTickets`). |
| A5 | Màn **Tra cứu bảo hành** | Tab `#tab-lookup`: ô `#lookup-input` + `#lookup-samples` + `#lookup-result`; `runLookup()` tự nhận diện (`TK-…` → mã phiếu, còn lại → số sê-ri); card `deviceWarrantyCardHtml()` và `lookupTicketByCode()`; nút "Tạo phiếu bảo hành cho thiết bị này" (`startTicketForSerial`). |
| A6 | **Chi tiết thiết bị** | Modal `#device-detail-modal` (`openDeviceDetailModal()`): thông tin thiết bị + khách hàng + tình trạng bảo hành + danh sách phiếu của thiết bị + nút kiểm tra bảo hành. |
| A7 | Bảng Thiết bị rõ nghĩa | 8 cột: Số sê-ri · Sản phẩm · Khách hàng · Ngày mua · Hết hạn BH · **Tình trạng bảo hành** (chữ + màu) · **Hồ sơ** · Thao tác (Chi tiết/Sửa/Xóa); kiểm tra bảo hành ngay trên dòng (`runDeviceWarrantyCheck`). |
| A8 | Danh sách phiếu dễ tra hơn | Ô tìm kiếm nhận **mã phiếu / số sê-ri / tên khách** (`filterTickets`), sắp xếp theo việc cần làm (`sortTicketsForWork`), thêm cột **Nhân viên phụ trách**, chi tiết phiếu có **tiến trình 4 bước** (`ticketProgressHtml`). |
| A8 phụ | Tìm theo **mã phiếu** vẫn giữ | `searchTicketByCode()` dùng `GET /api/v1/warranty-tickets/code/{code}` (E2E bước 17, 17b). |

### G3 — Tab Tra cứu (A3) + Wizard tiếp nhận (A4) ✅

| Mã | Nội dung | Kết quả trong code |
|---|---|---|
| A3 | Tra cứu **một ô cho hai loại** | Nhập `SN-ASUS-VALID-01` → `GET /api/v1/product-instances/by-serial/{x}`; nhập `TK-…` → `GET /api/v1/warranty-tickets/code/{x}`; không thấy → `lookupNotFoundCard()` nói rõ **chưa đăng ký** kèm gợi ý tiếp nhận. |
| A4 | **Wizard "Tiếp nhận máy mới" 2 bước** | `#wizard-step1` (tra số sê-ri → có thì dùng ngay, chưa có thì mở form đăng ký `#wiz-new-device`) và `#wizard-step2` (xem lại thiết bị `#wiz-preview` + mô tả lỗi + người tiếp nhận + loại lỗi tùy chọn → tạo phiếu). Hàm: `wizardLookupSerial`, `wizardSaveDevice`, `wizardGoToStep2`, `wizardBackToStep1`, `wizardSubmitTicket`, `wizardReset`, `recalcWizardEndDate`. |
| A4 phụ | Gỡ công cụ kiểm tra trùng lặp | `verifyBeforeCreate`, `useSerialForTicket`, `toggleCheckPanel`, `refreshCheckSamples`, `submitCreateTicket`, `loadReceptionOptions`, `#demo-serials-container`, `#create-ticket-form`, `#ticket-serial-input`, `#serial-verify-*` **đã gỡ hẳn** (E2E bước 0f3 tự kiểm tra điều này). |
| A4 phụ | Vẫn đúng nghiệp vụ | Phiếu tạo qua wizard gửi `serial_number` + `customer_id` (**lấy theo chủ sở hữu thiết bị**) + `created_by` + `issue_description`; **mặc định không gửi `error_category_id`** để đúng luồng AI (AI gợi ý → nhân viên xác nhận). |

### G4 — Bổ sung thông tin & hoàn thiện (B1, B2, B3, C4, C5, C6, D1, D2) ✅

| Mã | Nội dung | Kết quả trong code |
|---|---|---|
| B1 | Khách hàng: cột **Số thiết bị** + **Số phiếu** | `countDevicesOfCustomer()`, `countTicketsOfCustomer()` đếm từ `state.devices`/`state.tickets`; `ensureCountData()` nạp danh sách thiết bị + phiếu khi vào tab Khách hàng/Sản phẩm. |
| B2 | **Chi tiết khách hàng** | Modal `#customer-detail-modal` (`openCustomerDetailModal()`): thông tin khách + bảng **Thiết bị của khách** (có tình trạng bảo hành, nút sang chi tiết thiết bị) và bảng **Phiếu bảo hành của khách** (trạng thái, nút xem phiếu). |
| B3 | Sản phẩm: cột **Số thiết bị đang quản lý** | `countDevicesOfProduct()` đếm theo `product_id` từ `state.devices`. |
| C4 | Hạ khối **Quy tắc nghiệp vụ** xuống cuối Tổng quan | Khối `<details>` "Quy tắc nghiệp vụ & quy trình xử lý" nằm **sau** bảng Phiếu đang xử lý, vẫn thu gọn. |
| C5 | Bỏ "Chọn nhanh thiết bị" trùng lặp | Chỉ còn trong **wizard** (`#wiz-samples`); tab Thiết bị dùng ô tìm kiếm + nút dẫn sang màn Tra cứu. |
| C6 | Modal phiếu: tóm tắt AI + **"Phân tích phiếu này"** | `refreshModalAiPanel()` hiển thị tóm tắt gợi ý, cho **xác nhận / không dùng ngay trong modal** (`submitAiReviewModal`) và vẫn giữ link sang tab AI để xem đầy đủ. |
| D1 | Hướng dẫn tại chỗ khi nút bị mờ | Xem mục C2 ở trên (chỉ còn một chỗ nút mờ, đã có dòng giải thích ngay dưới). |
| D2 | 3 tình trạng bảo hành **đủ chữ + màu** | `warrantyInfoFor()`/`warrantyStatusHtml()`: "🟢 Còn bảo hành" / "🔴 Đã hết hạn" / "⚪ Không xác định", kèm số ngày còn/quá hạn. |
| — | Cập nhật `frontend/README.md` | Đổi thành **7 tab nghiệp vụ**, mô tả wizard + các cột đếm, thêm mục **"Tái cấu trúc UX (Đợt 4)"**. |


---

## 4. Ánh xạ thuật ngữ kỹ thuật ↔ ngôn ngữ người dùng (bổ sung Đợt 4)

| Trong CSDL / API | Hiển thị trên giao diện |
|---|---|
| `serial_number` | **Số sê-ri** |
| `product-instances` / "instance" | **Thiết bị** |
| `warranty_end_date`, `is_valid`, `days_remaining` | **Tình trạng bảo hành**: Còn bảo hành / Đã hết hạn / Không xác định (+ số ngày còn hoặc quá hạn) |
| `RECEIVED` | **Đã tiếp nhận** (bước 1/4 trong tiến trình phiếu) |
| `INSPECTING` → `REPAIRING` → `COMPLETED` | **Đang kiểm tra** → **Đang sửa chữa** → **Hoàn tất** (bước 2, 3, 4) |
| `REJECTED` | **Từ chối bảo hành** (nhánh kết thúc, có lý do bắt buộc) |
| `created_by`, `changed_by` | **Người tiếp nhận**, **Người thực hiện**, **Nhân viên phụ trách** |
| `debug_traces` | Gọn sau nút **"Chi tiết kỹ thuật (dành cho kiểm thử)"** |
| `PENDING` / `APPROVED` / `REJECTED` (kết quả AI) | **Chờ xác nhận** / **Đã xác nhận** / **Không dùng gợi ý này** |
| `confidence` (0.95) | **95%** |

## 5. API sử dụng (không thêm endpoint nào)

| Endpoint | Dùng cho |
|---|---|
| `GET /api/v1/product-instances/by-serial/{serial}` | Tra cứu bảo hành, bước 1 wizard, đọc lại thiết bị vừa đăng ký |
| `GET /api/v1/warranty-tickets/code/{code}` | Tra cứu theo mã phiếu, tìm kiếm trong danh sách phiếu |
| `POST /api/v1/debug/check-warranty` | "Đối chiếu điều kiện bảo hành" (tab Tra cứu, chi tiết thiết bị, kiểm tra theo dòng) |
| `GET /api/v1/product-instances/`, `GET /api/v1/warranty-tickets/` | Đếm số thiết bị / số phiếu cho Khách hàng & Sản phẩm, danh sách chọn nhanh trong wizard |
| `POST /api/v1/product-instances/` | Bước 1 wizard: đăng ký thiết bị mới (theo `product_id` hoặc `product_name` + `brand` + `category`) |
| `POST /api/v1/warranty-tickets/` | Bước 2 wizard: tạo phiếu bảo hành |
| `PATCH /api/v1/ai/results/{id}/review` | Xác nhận / không dùng gợi ý lỗi (cả trong modal chi tiết phiếu) |

**Không gọi** `GET /api/v1/debug/check-serial/{serial}` nữa (công cụ cũ đã gỡ) — endpoint vẫn tồn tại ở backend, không sửa gì.

## 6. File thay đổi & file giữ nguyên

| File | Trạng thái | Ghi chú |
|---|---|---|
| `frontend/index.html` (886 dòng) | **Sửa** | 7 tab, tab Tra cứu, wizard 2 bước, modal chi tiết thiết bị/khách hàng, bảng bỏ `#id` + cột đếm |
| `frontend/app.js` (2.770 dòng) | **Sửa** | Thêm ~40 hàm mới (lookup, wizard, chi tiết, đếm, tiến trình phiếu), gỡ ~10 hàm cũ trùng lặp |
| `frontend/README.md` (99 dòng) | **Sửa** | Mô tả 7 tab + mục "Tái cấu trúc UX (Đợt 4)" |
| `frontend/styles.css` | **Không đổi** | Dùng lại toàn bộ class sẵn có |
| `backend/**`, `tests/**`, CSDL, `dev.ps1`, `docker-compose.yml` | **Không đổi** | Dấu thời gian mới nhất vẫn là **25/09/2026** (Đợt 1) |
| `docs/AUDIT_DOT_4_UX.md` | Đã có | Audit được duyệt (không sửa nội dung) |
| `docs/BAO_CAO_DOT_4_UX.md` | **Tạo mới** | Tài liệu này |


---

## 7. Kiểm chứng (chạy trên máy, server thật + CSDL thật)

| Hạng mục | Lệnh / công cụ | Kết quả |
|---|---|---|
| Cú pháp JS | `node --check frontend/app.js` | **exit 0** (không lỗi cú pháp) |
| Ngôn ngữ + cấu trúc UI | kiểm tra 49 mục (đủ 7 tab, mọi id JS gọi đều tồn tại hoặc do JS sinh ra, mọi handler đều có hàm, không hàm trùng lặp, không chuỗi seed lộ ra) | **49 PASS / 0 FAIL** |
| Minh chứng KT2 + KT3 | `.\dev.ps1 check` | **24/24 PASS** (KT2 12/12, KT3 12/12) |
| E2E luồng UI → API → DB → UI | `verify_dot4_e2e.py` (server `127.0.0.1:8014`) | **76 PASS / 0 FAIL** |
| Dữ liệu test | `.\dev.ps1 check` sau khi chạy E2E | đã dọn sạch, không còn dữ liệu rác |

Các bước E2E mới của Đợt 4 (ngoài baseline 50 bước cũ):

| Bước | Nội dung kiểm |
|---|---|
| 0b → 0b4 | Đủ 7 tab (có **Tra cứu bảo hành**) · có wizard 2 bước · bảng Khách hàng/Sản phẩm **bỏ cột `Mã`** và có cột đếm · có 2 modal chi tiết |
| 0f2 → 0f3 | Có hàm màn Tra cứu + wizard + chi tiết + tiến trình phiếu; **đã gỡ hẳn** 6 hàm công cụ cũ |
| 20 → 20c | Tra cứu theo số sê-ri ra card đủ trường; số sê-ri lạ → 404 |
| 20d → 20e | "Đối chiếu điều kiện bảo hành" trả kết luận + có `debug_traces` cho mục "Chi tiết kỹ thuật" |
| 20f → 20g | Cùng một ô tra cứu dùng được **mã phiếu**, card có thiết bị + khách hàng + trạng thái |
| 21 → 21g | Wizard máy mới: tra → 404 → đăng ký thiết bị → đọc lại theo số sê-ri (hạn BH do backend tính) → tạo phiếu → tiến trình có lịch sử |
| 22 → 22d | Dữ liệu đếm số thiết bị/số phiếu lấy đúng từ API và khớp dữ liệu vừa tạo (2 thiết bị / 2 phiếu) |
| 23 → 23c | Kiểm tra bảo hành theo dòng + modal chi tiết thiết bị đủ trường |

> Ghi chú: script E2E và các script kiểm tra đặt **ngoài repo** (thư mục làm việc cá nhân) — sản phẩm nộp bài không thêm file test mới, không sửa `tests/**`.

## 8. Ràng buộc nghiệp vụ được giữ nguyên (đã kiểm chứng lại)

| # | Bất biến | Kiểm chứng |
|---|---|---|
| BR1–BR2 | Điều kiện bảo hành (`warranty_end_date >= check_date`) do **backend** quyết định | E2E 11a, 20d, 23b; giao diện chỉ hiển thị |
| BR3 | Một thiết bị chỉ có **một** phiếu đang xử lý | Không đổi backend; wizard vẫn nhận lỗi 409 từ API và hiển thị thông báo tiếng Việt |
| BR4 | Đúng chủ sở hữu | Wizard **tự lấy `customer_id` theo thiết bị**, không cho chọn khách khác — giảm nguy cơ sai chủ |
| BR5 | Từ chối phải có lý do | Modal xác nhận chuyển trạng thái vẫn `textRequired` |
| State machine | `RECEIVED→INSPECTING→REPAIRING→COMPLETED`, nhánh `REJECTED` | E2E 14c: nhảy cóc vẫn bị chặn (400) |
| AI-01 | AI chỉ đề xuất, người có quyền xác nhận | E2E 15c, 16, 16d: kỹ thuật viên vẫn bị chặn 403; xác nhận trong modal dùng đúng endpoint và quyền |

**Cố tình KHÔNG làm** (theo audit, mục N1–N5): không thêm mục "Kết quả kiểm tra / linh kiện thay" (backend chưa có API `repair_logs`), không sửa `tests/`/seed/CSDL/API, không thêm chatbot–RAG–LangGraph–đăng nhập, không tách "dữ liệu test" khỏi dữ liệu demo, không đổi framework/visual.

## 9. Ghi nhận cho đợt sau

1. **Kết quả kiểm tra kỹ thuật (chẩn đoán, linh kiện thay)** — cần API cho `repair_logs` trước khi làm giao diện, nếu không sẽ phải bịa dữ liệu.
2. **Phân quyền thật** — hiện chọn người thực hiện bằng danh sách người dùng mẫu (`/api/v1/ai/demo/users`); đăng nhập/phân quyền ngoài phạm vi môn học.
3. **Bộ lọc nâng cao cho danh sách phiếu** (theo khoảng ngày, theo kỹ thuật viên) — có thể làm hoàn toàn ở frontend nếu cần.

---

**Kết luận:** Đợt 4 hoàn thành đủ 4 giai đoạn G1–G4 với **24/24 minh chứng KT2+KT3**, **49/49 kiểm tra ngôn ngữ/UI** và **76/76 bước E2E đạt**; toàn bộ thay đổi nằm trong `frontend/` + tài liệu, không đụng tới backend, CSDL, API hay bộ kiểm thử.

