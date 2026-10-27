# AUDIT ĐỢT 4 — TÁI CẤU TRÚC UX FRONTEND (BaoHanhAI)

> **Trạng thái:** AUDIT — **chưa sửa code**. Tài liệu này là căn cứ để chốt danh sách đề xuất trước khi thực hiện.
> **Ngày audit:** 25/09/2026 · Kiểm tra bằng đọc code + chạy hệ thống thật.
> **Baseline trước khi thay đổi (đã xác nhận lại trong đợt này):** `.\dev.ps1 check` = **24/24 PASS** (KT2 12/12, KT3 12/12); kiểm tra ngôn ngữ/UI = **49/49 PASS**; E2E gần nhất = **50 PASS / 0 FAIL**.

## 0. Phạm vi đã đọc & xác minh

| Hạng mục | Nội dung |
|---|---|
| Frontend | `index.html` 761 dòng · `app.js` 1966 dòng / 94 hàm · `styles.css` 233 dòng · `README.md` 75 dòng |
| Backend đã đọc | `routers/*` (6 router), `crud/*` (4), `models.py` (16 bảng), `schemas.py`, `services/warranty_rules.py`, `services/ai_error_classifier.py`, `database.py`, `main.py` |
| Dữ liệu thật | SQLite: 4 khách · 4 sản phẩm · 12 thiết bị · 11 phiếu · 3 danh mục lỗi · 3 người dùng · 11 kết quả AI |
| API hiện có | **31 endpoint** (khách hàng 5, sản phẩm 5, thiết bị 6, phiếu 7, debug 2, AI 6) — đủ cho mọi đề xuất, **không cần thêm API** |
| Nghiệp vụ bất biến | `OPEN_TICKET_STATUSES = [RECEIVED, INSPECTING, REPAIRING]`; `ALLOWED_TRANSITIONS = {RECEIVED→INSPECTING; INSPECTING→REPAIRING|REJECTED; REPAIRING→INSPECTING|COMPLETED}`; BR1–BR4 + BR5 (lý do từ chối); AI-01 human-in-the-loop |

---

## A. Những chức năng hiện tại

| # | Khu vực | Chức năng | API dùng |
|---|---|---|---|
| A1 | **Tổng quan** | 6 thẻ số liệu (tổng phiếu, đang xử lý, hoàn tất, từ chối, khách hàng, thiết bị) · biểu đồ tròn 5 trạng thái + chips · bảng 5 phiếu mới nhất · khối “Quy tắc nghiệp vụ & quy trình xử lý” (thu gọn) · nút làm mới | `stats/summary`, `warranty-tickets/?limit=5` |
| A2 | **Khách hàng** | Tìm kiếm (tên/SĐT) · bảng (#id, họ tên, SĐT, email, địa chỉ) · Thêm/Sửa (modal) · Xóa (modal xác nhận, chặn 409) | `/customers` |
| A3 | **Sản phẩm** | Tìm kiếm (tên/hãng/ngành) · bảng (#id, tên, hãng, ngành hàng, thời hạn BH) · Thêm/Sửa · Xóa | `/products` |
| A4 | **Thiết bị** | Tìm kiếm (serial/tên SP) · bảng (serial, sản phẩm, khách hàng, ngày mua, hết hạn BH, trạng thái hồ sơ) · modal Thêm/Sửa · công cụ **“Kiểm tra hạn bảo hành”** (serial + ngày → banner + trace) | `/product-instances`, `POST /debug/check-warranty`, `GET /debug/check-serial/{serial}` |
| A5 | **Phiếu bảo hành** | Khối tiếp nhận (chọn nhanh serial · serial + “Kiểm tra” · khách hàng · loại lỗi (tuỳ chọn) · người tiếp nhận · mô tả · box kết quả · nút Tạo phiếu) · danh sách + 6 nút lọc + tra cứu theo **mã phiếu** · modal chi tiết (badge trạng thái, serial/sản phẩm, khách hàng + hạn BH, ngày tiếp nhận, người tiếp nhận, mô tả, lý do từ chối, lịch sử, người thực hiện + nút chuyển trạng thái, khối gợi ý loại lỗi) | `/warranty-tickets`, `/ai/tickets/{id}/results` |
| A6 | **Hỗ trợ xác định lỗi** | Chọn phiếu (select) · “Gợi ý loại lỗi” · kết quả (loại lỗi, mức độ chắc chắn %, giải thích, câu hỏi thêm, trạng thái xác nhận) · chọn người xác nhận + “Xác nhận loại lỗi” / “Không dùng gợi ý” · bảng lịch sử | `POST /ai/tickets/{id}/classify-error`, `PATCH /ai/results/{id}/review`, `GET /ai/tickets/{id}/results`, `GET /ai/demo/users` |
| A7 | **Chung** | Toast · modal xác nhận dùng chung · loading/empty/error mọi bảng · lớp hiển thị tiếng Việt (20 ánh xạ) · nút “Tiếp nhận máy mới” ở header | — |

---

## B. Những chức năng trùng nhau

| # | Trùng lặp | Chi tiết | Mức độ |
|---|---|---|---|
| B1 | **“Chọn nhanh thiết bị” xuất hiện 2 nơi** | Khối tiếp nhận (tab Phiếu) và công cụ kiểm tra (tab Thiết bị) cùng liệt kê serial để bấm nhanh | Trung bình |
| B2 | **Kiểm tra hạn bảo hành có 2 cửa vào khác nhau** | Nút “Kiểm tra” trong khối tiếp nhận dùng `check-serial`; công cụ riêng dùng `check-warranty` → cùng câu hỏi “còn hạn?”, 2 UI/kết quả khác nhau | **Cao** |
| B3 | **3 điểm vào cho “tra cứu 1 thiết bị/phiếu”** | Ô tìm kiếm Thiết bị · ô “Tra cứu mã” Phiếu · công cụ kiểm tra hạn | **Cao** |
| B4 | **Kết quả gợi ý lỗi ở 2 nơi** | Modal chi tiết phiếu (chỉ đọc) và tab Hỗ trợ xác định lỗi (đầy đủ) | Thấp |
| B5 | **“Đang xử lý”** trên Tổng quan trùng bộ lọc trạng thái ở tab Phiếu | Gộp 3 trạng thái vs 3 nút lọc | Thấp |

---

## C. Những chức năng khó hiểu với người dùng phổ thông

| # | Vấn đề | Hệ quả |
|---|---|---|
| C1 | Nút header **“Tiếp nhận máy mới”** dẫn tới khối **“Tiếp nhận thiết bị & tạo phiếu bảo hành”** trong tab “Phiếu bảo hành” | 2 tên cho 1 việc; không biết nút dẫn đi đâu |
| C2 | Nút **“Tạo phiếu bảo hành” bị mờ (disabled)** cho tới khi bấm “Kiểm tra”, **không có dòng giải thích** | Người mới tưởng nút lỗi |
| C3 | Công cụ **“Kiểm tra hạn bảo hành”** vs nút **“Kiểm tra”** gần giống tên | Nhầm lẫn |
| C4 | Tab **Hỗ trợ xác định lỗi** bắt chọn phiếu trong `select` dài (mã + serial + trạng thái + ghi chú) | Không biết chọn phiếu nào |
| C5 | Trường **“Loại lỗi”** là `select` mặc định “Chưa xác định (để hệ thống gợi ý)” | Tưởng bắt buộc chọn |
| C6 | Nút **“Mở màn hình hỗ trợ xác định lỗi”** trong modal làm **đóng modal + đổi tab** | Mất ngữ cảnh phiếu đang xem |
| C7 | Cột **“Trạng thái”** ở bảng Thiết bị là **trạng thái hồ sơ** (`Đang hoạt động`/`Ngừng theo dõi`), không phải tình trạng bảo hành | Đọc nhầm thành còn/hết bảo hành |

---

## D. Những thuật ngữ kỹ thuật còn xuất hiện trên UI

| # | Vị trí | Hiện tại | Ghi chú |
|---|---|---|---|
| D1 | Bảng Khách hàng & Sản phẩm | Cột **“Mã”** hiển thị `#id` (khoá chính CSDL) | Người dùng không cần |
| D2 | Tiêu đề modal | **“Sửa khách hàng #5”**, **“Sửa sản phẩm #3”** | Lộ ID kỹ thuật |
| D3 | Toàn giao diện | Chưa thống nhất **“Số serial”** ↔ **“Số sê-ri”** | Cần chuẩn hoá theo yêu cầu XI |
| D4 | Trace kiểm tra (chế độ độc lập) | Lộ chuỗi tiếng Anh: **“Chế độ kiểm tra độc lập (Standalone simulation không dùng serial DB)”** | Lớp hiển thị đã map `DB` nhưng chưa map “Standalone simulation” |
| D5 | Khối “Quy tắc nghiệp vụ & quy trình xử lý” (Tổng quan) | Nội dung học thuật, không phải việc hằng ngày | Nên hạ ưu tiên |
| D6 | Mục “Thông tin đối chiếu chi tiết” | Trace kỹ thuật backend (đã diễn giải phần lớn) | Nên ẩn sau nút nhỏ / dành cho minh chứng |
| D7 | (Đã tốt — giữ nguyên) | Không còn `AI-01`, `BR1..BR5`, `STATE MACHINE`, enum trạng thái, `RECEPTIONIST/TECHNICIAN/MANAGER`, `0.xx`, “Mã kết quả”, “Độ tin cậy” | Kết quả Đợt 3 |

---

## E. Những màn hình đang thiếu thông tin quan trọng

| # | Màn hình | Thiếu gì | API sẵn có? |
|---|---|---|---|
| E1 | **Khách hàng** | **Số thiết bị**, **số phiếu bảo hành**; **chi tiết khách** (thiết bị + phiếu của khách) | ✅ ghép phía client |
| E2 | **Sản phẩm** | **Số thiết bị đang quản lý** | ✅ ghép phía client |
| E3 | **Thiết bị** | Cột **hãng**; **tình trạng bảo hành dạng chữ** (“Đang được bảo hành / Đã hết hạn / Không xác định”); **xem chi tiết thiết bị**; nút **“Kiểm tra bảo hành”** theo dòng | ✅ `by-serial`, `check-warranty` |
| E4 | **Phiếu — danh sách** | Tìm theo **số sê-ri** & **khách hàng** (hiện chỉ mã phiếu); cột **nhân viên phụ trách** | ✅ `status_history` có trong list |
| E5 | **Phiếu — chi tiết** | **Tiến trình 4 bước** (Tiếp nhận → Kiểm tra → Sửa chữa → Hoàn tất); **tình trạng bảo hành thiết bị**; **trạng thái xác nhận AI** đặt ngay đầu modal; mục “Kết quả kiểm tra” | ✅ trừ “Kết quả kiểm tra”: **backend chưa có API** cho `repair_logs` |
| E6 | **Tổng quan** | Thẻ **“Chờ tiếp nhận”** (RECEIVED); danh sách **“Phiếu đang xử lý”**; khu **“Thao tác nhanh”**; ô **tra cứu nhanh** | ✅ `stats/summary`, `?status=` |
| E7 | **Toàn hệ thống** | **Màn hình Tra cứu bảo hành tập trung** (“Số sê-ri / Mã phiếu” → 1 kết quả thống nhất) | ✅ `by-serial`, `code/{code}`, `check-warranty` |

---

## F. Những thao tác có quá nhiều bước

| # | Thao tác | Hiện tại | Đề xuất |
|---|---|---|---|
| F1 | **Đăng ký thiết bị + tạo phiếu cho máy mới** | ~9–10 bước, **2 tab** (Thiết bị → thêm thiết bị → Lưu → sang tab Phiếu → nhập lại serial → Kiểm tra → mô tả → người tiếp nhận → Tạo) | **Wizard 2 bước** tại một chỗ |
| F2 | **Tra cứu 1 thiết bị** | Tìm ở bảng → muốn biết còn hạn phải mở công cụ riêng và **nhập lại serial** | Tra cứu 1 lần, kết quả gồm cả tình trạng bảo hành |
| F3 | **Xem/duyệt kết quả AI** | Modal phiếu → bấm “Mở màn hình…” → **mất modal** → chọn lại phiếu | Chọn sẵn phiếu đang xem; cho xác nhận ngay trong modal |
| F4 | **Chuyển trạng thái phiếu** | Ô chọn “Người thực hiện” nằm cách xa nút hành động | Đưa cạnh nút hành động |

---

## G. Những dữ liệu mẫu thừa

| # | Loại | Nhận xét | Xử lý đề xuất |
|---|---|---|---|
| G1 | **Dữ liệu test tự sinh** (`SN-KT3-AI-01…06`, `SN-KT2-CRUD-2026`, phiếu “Phieu duoc tao de kiem thu…”, phiếu mô tả rỗng/khoảng trắng, phiếu PII demo, phiếu prompt-injection) | Đang hiện trong danh sách nhưng **phục vụ 24 minh chứng → phải giữ** | Giữ nguyên; chỉ **sắp xếp phiếu đang xử lý lên đầu** |
| G2 | Danh mục lỗi seed (3), sản phẩm seed (4) | Đã vừa phải, tên dễ hiểu | Giữ nguyên |
| G3 | Rác do thử tay (`ss23`, `đabsbfsfb`, khách viết thường) | Đã được dọn bởi `check` | Không còn |
| G4 | Dữ liệu mẫu **không dấu** trong CSDL | Đã xử lý bằng **lớp hiển thị** | Giữ nguyên (không sửa CSDL) |

---

## H. Những chỗ người dùng mới có thể không biết phải làm gì

| # | Điểm mơ hồ | Đề xuất |
|---|---|---|
| H1 | Tổng quan **không có nút dẫn tới hành động tiếp theo** (chỉ “Làm mới số liệu”) | Thêm khu **“Thao tác nhanh”** |
| H2 | Không rõ **“Đang xử lý”** gồm trạng thái nào | Ghi chú phụ + tách “Chờ tiếp nhận” |
| H3 | Nút **“Tạo phiếu” mờ** mà không nói lý do | Thêm dòng: “Bấm **Kiểm tra** để xác nhận thiết bị còn bảo hành trước khi lưu phiếu.” |
| H4 | Tab Hỗ trợ xác định lỗi **không gợi ý nên chọn phiếu nào** | Mặc định chọn phiếu **chưa xác định loại lỗi** + nút “Phân tích phiếu này” trong chi tiết phiếu |
| H5 | Không nói **phải thêm thiết bị trước khi tạo phiếu** | Nút “Thêm thiết bị này” ngay trong kết quả kiểm tra |
| H6 | Cột “Trạng thái” thiết bị dễ hiểu sai (C7) | Tách **Tình trạng bảo hành** và **Hồ sơ** |

---

## I. Những chức năng nên gom lại

| # | Gom gì | Thành gì |
|---|---|---|
| I1 | 2 công cụ kiểm tra hạn (B2) | **Một khối “Kiểm tra bảo hành”** duy nhất |
| I2 | 3 điểm vào tra cứu (B3) | **Màn “Tra cứu bảo hành”** (số sê-ri *hoặc* mã phiếu) |
| I3 | Đăng ký thiết bị + tạo phiếu (F1) | **Wizard 2 bước: Thiết bị → Phiếu bảo hành** |
| I4 | Chọn “người thực hiện” xa nút hành động (F4) | Chọn trong hộp thoại xác nhận chuyển trạng thái |
| I5 | “Chọn nhanh serial” ở 2 nơi (B1) | Chỉ giữ trong Wizard; nơi khác dùng ô nhập + gợi ý |
| I6 | Thông tin khách rải rác (E1) | **Chi tiết khách hàng**: thông tin + thiết bị + phiếu |
| I7 | 2 nơi hiển thị kết quả gợi ý (B4) | Modal phiếu: **tóm tắt + xác nhận ngay**; tab AI: xem đầy đủ |

---

## J. Những chức năng nên đưa lên Tổng quan

| # | Đưa lên | Lý do |
|---|---|---|
| J1 | **Thao tác nhanh**: Tiếp nhận thiết bị · Tạo phiếu bảo hành · Tra cứu bảo hành · Hỗ trợ xác định lỗi | Người dùng biết ngay phải bấm gì (H1) |
| J2 | Thẻ **“Chờ tiếp nhận”** (RECEIVED) | Việc cần làm ngay |
| J3 | **“Phiếu đang xử lý”** (RECEIVED/INSPECTING/REPAIRING) | Đúng nhu cầu quầy tiếp nhận |
| J4 | **Ô tra cứu nhanh** (số sê-ri / mã phiếu) | Việc lặp lại nhiều nhất |
| J5 | Giữ **biểu đồ + chips** | Đã tốt |

---

## K. Những chức năng nên ẩn khỏi người dùng phổ thông

| # | Ẩn/hạ ưu tiên | Cách làm |
|---|---|---|
| K1 | Khối **“Quy tắc nghiệp vụ & quy trình xử lý”** | Chuyển xuống **cuối trang Tổng quan**, vẫn thu gọn |
| K2 | **“Thông tin đối chiếu chi tiết”** (trace) | Ẩn sau nút nhỏ **“Chi tiết kỹ thuật”** (phục vụ minh chứng KT2) |
| K3 | Cột **“Mã” (#id)** ở Khách hàng/Sản phẩm | **Bỏ cột** |
| K4 | Tiêu đề **“Sửa khách hàng #5”** | Đổi thành “Sửa khách hàng: Nguyễn Văn An” |
| K5 | Chuỗi tiếng Anh trong trace (D4) | Map sang tiếng Việt |

---

## L. Giới hạn — không làm nếu không sửa backend (ghi nhận, không tự ý mở rộng)

| # | Mong muốn | Lý do |
|---|---|---|
| L1 | Mục “**Kết quả kiểm tra**” trong phiếu (chẩn đoán của kỹ thuật viên, linh kiện thay) | Backend **chưa có API** cho bảng `repair_logs` → sẽ là dữ liệu giả. Đề xuất để **đợt sau** |
| L2 | Lọc “chỉ dữ liệu mẫu” / tách test khỏi demo | Phân biệt test/demo là **giả tạo**, dễ phá minh chứng |
| L3 | Sửa seed cho dữ liệu có dấu trong CSDL | Phá minh chứng #2/#3 |
| L4 | Đăng nhập/phân quyền thật | Ngoài phạm vi môn học |

---

# ĐỀ XUẤT THỰC HIỆN (chờ xác nhận — chưa code)

## Nguyên tắc
1. **Chỉ sửa `frontend/`** (index.html, app.js, styles.css, README) — **không** sửa backend, **không** thêm API, **không** đổi CSDL, **không** sửa `tests/`.
2. **Không thêm module mới**: chỉ tái cấu trúc + gom + bổ sung thông tin **đã có trong API**.
3. Mọi con số/thông tin mới (số thiết bị của khách, số phiếu, tình trạng bảo hành, nhân viên phụ trách) đều **tính từ dữ liệu API đang dùng** (không hard-code, không tạo dữ liệu giả).
4. Giữ nguyên lớp hiển thị tiếng Việt của Đợt 3; giữ tinh thần visual hiện tại (dark, card, màu trạng thái nhất quán).
5. Sau **mỗi** nhóm việc: `node --check` → `check_dot3_ui.py` → `.\dev.ps1 check` (24/24) → E2E.

## Cấu trúc menu đề xuất (7 mục)

| # | Menu | Vai trò |
|---|---|---|
| 1 | **Tổng quan** | Số liệu + **Thao tác nhanh** + **Phiếu đang xử lý** |
| 2 | **Tra cứu bảo hành** *(mới)* | Nhập **Số sê-ri / Mã phiếu** → kết quả thống nhất (thiết bị + tình trạng bảo hành + phiếu gần nhất) |
| 3 | **Khách hàng** | CRUD + **số thiết bị / số phiếu** + **chi tiết khách** |
| 4 | **Sản phẩm** | CRUD + **số thiết bị đang quản lý** |
| 5 | **Thiết bị** | CRUD + **hãng** + **tình trạng bảo hành** + **chi tiết thiết bị** + **kiểm tra bảo hành theo dòng** |
| 6 | **Phiếu bảo hành** | Tiếp nhận (wizard) + danh sách (tìm theo mã/sê-ri/khách) + **chi tiết có tiến trình 4 bước** |
| 7 | **Hỗ trợ xác định lỗi** | Giữ nguyên luồng AI + xác nhận (human-in-the-loop) |

## Nhóm việc A — UX cốt lõi (rủi ro thấp, tác động lớn)

| ID | Việc | Cách làm (chỉ frontend) | Kiểm chứng |
|---|---|---|---|
| **A1** | **Tổng quan có “Thao tác nhanh”** | 4 nút: Tiếp nhận thiết bị · Tạo phiếu bảo hành · Tra cứu bảo hành · Hỗ trợ xác định lỗi → gọi `switchTab` + mở đúng form | Mở trang, bấm từng nút thấy đúng màn hình |
| **A2** | **Tổng quan: tách “Chờ tiếp nhận” + “Phiếu đang xử lý”** | Dùng `stats.received` cho thẻ mới; đổi bảng “5 phiếu mới nhất” → **“Phiếu đang xử lý”** (lọc `RECEIVED/INSPECTING/REPAIRING` từ `?status=` hoặc list hiện có), **ưu tiên phiếu lâu nhất/đang xử lý** | Số liệu khớp `stats/summary`; bảng chỉ chứa phiếu đang xử lý |
| **A3** | **Màn “Tra cứu bảo hành” (menu #2)** | Ô nhập 1 trường (Số sê-ri **hoặc** Mã phiếu) + nút **Tra cứu**: thử `GET /product-instances/by-serial/{x}` → nếu 404 thì `GET /warranty-tickets/code/{x}`; hiển thị **card kết quả**: sản phẩm, hãng, số sê-ri, khách hàng, ngày mua, hạn bảo hành, **tình trạng** (🟢 Còn bảo hành / 🔴 Đã hết hạn / ⚪ Không xác định) + nút dẫn tiếp: “Tạo phiếu bảo hành cho thiết bị này”, “Xem phiếu gần nhất” | Tra cứu serial seed & mã phiếu seed → ra đúng kết quả; serial lạ → “Không tìm thấy…” |
| **A4** | **Wizard “Tiếp nhận máy mới” 2 bước** | **Bước 1 – Thiết bị**: nhập số sê-ri → tự tra: nếu **đã có** → hiện thông tin + tình trạng bảo hành, cho đi tiếp; nếu **chưa có** → hiện form đăng ký (chọn khách hàng từ API, chọn sản phẩm từ API, ngày mua, thời hạn) → Lưu thiết bị (`POST /product-instances`). **Bước 2 – Phiếu**: xem trước (khách, thiết bị, hạn BH, tình trạng) + mô tả lỗi + người tiếp nhận → **Xác nhận tiếp nhận** (`POST /warranty-tickets`) — **không** gửi `error_category_id` (để AI gợi ý) | Tạo máy mới end-to-end: 1 luồng, 2 bước; RB1–BR4 vẫn do backend chặn (thử serial hết hạn → hiện lý do tiếng Việt) |
| **A5** | **Thiết bị: cột Hãng + Tình trạng bảo hành + nút theo dòng** | Thêm cột hãng (từ `product_brand` đã có trong response), cột **tình trạng bảo hành** dạng chữ (tính từ `warranty_end_date` so với hôm nay — **chỉ để hiển thị**, quyết định vẫn ở backend), nút **“Kiểm tra”** mở kết quả kiểm tra ngay dưới dòng/panel; đổi nhãn trạng thái hồ sơ thành **“Hồ sơ: …”** | Cột mới hiện đúng; nút kiểm tra trả đúng kết quả của backend |
| **A6** | **Chi tiết thiết bị (modal mới)** | Thông tin thiết bị + **trạng thái bảo hành** + khối **lịch sử phiếu của thiết bị** (lấy từ danh sách phiếu đã tải, lọc theo serial) + nút Tạo phiếu / Kiểm tra bảo hành | Mở chi tiết 1 thiết bị seed → thấy phiếu liên quan |
| **A7** | **Phiếu: tìm kiếm + nhân viên phụ trách** | Ô tìm kiếm lọc **mã phiếu / số sê-ri / tên khách** (client-side trên list đã tải); thêm cột **“Nhân viên phụ trách”** = người ở bước xử lý mới nhất (`status_history` cuối) | Gõ “ASUS”/“An” ra đúng phiếu; cột phụ trách khớp lịch sử |
| **A8** | **Chi tiết phiếu: tiến trình 4 bước** | Stepper: **1 Tiếp nhận → 2 Kiểm tra → 3 Sửa chữa → 4 Hoàn tất** (bước hiện tại tô sáng; từ chối hiện nhánh riêng) + khối **tình trạng bảo hành thiết bị** + **trạng thái xác nhận AI** đặt ngay dưới tiêu đề | Mở phiếu RECEIVED/INSPECTING/REPAIRING/COMPLETED/REJECTED → stepper đúng |
| **A9** | **Chọn người thực hiện trong hộp thoại chuyển trạng thái** | Bỏ select rời rạc; đưa select vào modal xác nhận (cạnh nút xác nhận) | Chuyển trạng thái vẫn ghi đúng `changed_by` |

## Nhóm việc B — Bổ sung thông tin từ dữ liệu sẵn có (rủi ro thấp)

| ID | Việc | Cách làm |
|---|---|---|
| **B1** | Khách hàng: cột **Số thiết bị** + **Số phiếu** | Đếm từ `state.devices`/`state.tickets` (đã tải) |
| **B2** | Khách hàng: **chi tiết khách** (modal) | Thông tin + bảng thiết bị của khách + bảng phiếu của khách (từ dữ liệu đã tải) |
| **B3** | Sản phẩm: cột **Số thiết bị đang quản lý** | Đếm từ `state.devices` theo `product_id` |
| **B4** | Bỏ cột **“Mã” (#id)** ở Khách hàng/Sản phẩm; đổi tiêu đề modal sang tên | Bỏ cột + đổi `modal-title` |

## Nhóm việc C — Tinh giản, ẩn thông tin kỹ thuật & thống nhất từ ngữ

| ID | Việc | Cách làm |
|---|---|---|
| **C1** | Thống nhất **“Số sê-ri”** toàn giao diện | Đổi đồng loạt “số serial/serial” → **“Số sê-ri”** trong nhãn hiển thị (giữ nguyên field API) |
| **C2** | Ẩn trace sau nút **“Chi tiết kỹ thuật”** | Kết quả kiểm tra chỉ hiện kết luận; trace để trong `<details>` có nhãn “Chi tiết kỹ thuật (dành cho kiểm thử)” |
| **C3** | Map nốt chuỗi tiếng Anh trong trace | `Standalone simulation` → “chế độ kiểm tra độc lập”; các chuỗi Anh còn lại → tiếng Việt |
| **C4** | Hạ khối “Quy tắc nghiệp vụ” xuống cuối Tổng quan | Giữ nội dung, vẫn thu gọn |
| **C5** | Bỏ “Chọn nhanh thiết bị” trùng lặp | Chỉ giữ trong Wizard (A4); tab Thiết bị dùng ô tìm kiếm + kết quả kiểm tra |
| **C6** | Modal phiếu: tóm tắt AI + nút **“Phân tích phiếu này”** | Không còn “nhảy tab mất ngữ cảnh”; vẫn giữ link sang tab AI để xem đầy đủ |

## Nhóm việc D — Thông báo & trạng thái (đã tốt ở Đợt 3, chỉ bổ sung)

| ID | Việc |
|---|---|
| **D1** | Hướng dẫn rõ tại chỗ khi nút bị mờ: “Bấm **Kiểm tra** để xác nhận thiết bị còn bảo hành trước khi lưu phiếu.” |
| **D2** | 3 trạng thái bảo hành **luôn có cả chữ + màu**: “Còn bảo hành” / “Đã hết hạn” / “Không xác định” (đủ cho người khó phân biệt màu) |
| **D3** | Thông báo lỗi giữ nguyên như Đợt 3 (409/404/422/403 có câu riêng, tiếng Việt) |

## Những thứ **CỐ TÌNH KHÔNG LÀM** trong đợt này

| # | Không làm | Lý do |
|---|---|---|
| N1 | Mục “Kết quả kiểm tra” (chẩn đoán của kỹ thuật viên) | Backend chưa có API `repair_logs` → sẽ phải bịa dữ liệu. Ghi nhận cho đợt sau |
| N2 | Sửa `tests/**`, `seed_data.py`, CSDL, API, nghiệp vụ | Ràng buộc bất biến |
| N3 | Thêm chatbot/RAG/LangGraph/auth/ERP | Ngoài phạm vi |
| N4 | Lọc/tách “dữ liệu test” khỏi danh sách demo | Giả tạo, dễ phá minh chứng |
| N5 | Đổi framework (React/Vue…) hay thiết kế lại visual | Giữ HTML/CSS/JS thuần + tinh thần dark theme hiện tại |

## Kế hoạch thực thi (4 giai đoạn, có kiểm chứng sau mỗi giai đoạn)

| Giai đoạn | Nội dung | Kiểm chứng bắt buộc |
|---|---|---|
| **G1** | C1, C2, C3, B4, A9 (tinh giản + thống nhất từ ngữ + chi tiết phiếu nhỏ) | `node --check` · `check_dot3_ui.py` ≥ 49 PASS · `.\dev.ps1 check` 24/24 |
| **G2** | A1, A2, A5, A6, A7, A8 (Tổng quan + Thiết bị + Phiếu) | như trên + E2E (mở rộng thêm bước Tra cứu) |
| **G3** | A3 (Tra cứu bảo hành — tab mới) + A4 (Wizard tiếp nhận) | như trên + E2E bổ sung: tra cứu serial/mã phiếu; tạo máy mới qua wizard |
| **G4** | B1, B2, B3, C4, C5, C6, D1, D2 + cập nhật `frontend/README.md` | như trên + E2E đầy đủ 20 bước |

**Điều kiện hoàn thành:** giữ **KT2 12/12 · KT3 12/12 · TỔNG 24/24 PASS**, E2E không giảm so với baseline (≥ 50 PASS), UI check ≥ 49 PASS, không phát sinh dữ liệu rác sau kiểm thử (kết thúc bằng `.\dev.ps1 check`).




