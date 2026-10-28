# BÁO CÁO NGHIỆM THU TOÀN DIỆN HỆ THỐNG BAOHANHAI
**Bằng chứng kiểm chứng thực tế – Tách bạch phương pháp kiểm thử – Bảo vệ toàn vẹn CSDL**

---

## MỤC LỤC
1. [Làm rõ và xử lý mâu thuẫn quyền duyệt nhóm lỗi AI (RBAC)](#1-làm-rõ-và-xử-lý-mâu-thuẫn-quyền-duyệt-nhóm-lỗi-ai-rbac)
2. [Nguyên tắc an toàn dữ liệu & Kiểm chứng cách ly CSDL](#2-nguyên-tắc-an-toàn-dữ-liệu--kiểm-chứng-cách-ly-csdl)
3. [Bảng tổng hợp phân loại phương pháp kiểm chứng](#3-bảng-tổng-hợp-phân-loại-phương-pháp-kiểm-chứng)
4. [Chi tiết từng ca kiểm thử trình duyệt thực tế (E2E Browser Test)](#4-chi-tiết-từng-ca-kiểm-thử-trình-duyệt-thực-tế-e2e-browser-test)
   - [Kịch bản 1: Quản lý tài khoản (Tạo, khóa/mở khóa, thử đăng nhập tài khoản bị khóa)](#kịch-bản-1-quản-lý-tài-khoản-tạo-khóamở-khóa-thử-đăng-nhập-tài-khoản-bị-khóa)
   - [Kịch bản 2: Số sê-ri đã tồn tại, không có phiếu mở → Lập phiếu tiếp nhận mới](#kịch-bản-2-số-sê-ri-đã-tồn-tại-không-có-phiếu-mở--lập-phiếu-tiếp-nhận-mới)
   - [Kịch bản 3: Số sê-ri chưa tồn tại → Đăng ký thiết bị mới → Lập phiếu bảo hành](#kịch-bản-3-số-sê-ri-chưa-tồn-tại--đăng-ký-thiết-bị-mới--lập-phiếu-bảo-hành)
   - [Kịch bản 4: Toàn bộ chu trình sửa chữa từ Tiếp nhận đến Trả máy cho khách](#kịch-bản-4-toàn-bộ-chu-trình-sửa-chữa-từ-tiếp-nhận-đến-trả-máy-cho-khách)
   - [Kịch bản 5: KTV đề xuất từ chối → Quản lý không đồng ý → KTV tiếp tục sửa chữa](#kịch-bản-5-ktv-đề-xuất-từ-chối--quản-lý-không-đồng-ý--ktv-tiếp-tục-sửa-chữa)
   - [Kịch bản 6: KTV đề xuất từ chối → Quản lý duyệt từ chối → Tiếp nhận trả máy](#kịch-bản-6-ktv-đề-xuất-từ-chối--quản-lý-duyệt-từ-chối--tiếp-nhận-trả-máy)
   - [Kịch bản 7: Ba chức năng AI, sao chép thông báo, kiểm tra phản hồi lỗi giao diện](#kịch-bản-7-ba-chức-năng-ai-sao-chép-thông-báo-kiểm-tra-phản-hồi-lỗi-giao-diện)
   - [Kịch bản 8: Tạo/sửa khách hàng & thiết bị theo quyền; Kiểm tra RBAC ẩn nút](#kịch-bản-8-tạosửa-khách-hàng--thiết-bị-theo-quyền-kiểm-tra-rbac-ẩn-nút)
5. [Chi tiết kiểm thử trực tiếp API (Direct API Verification)](#5-chi-tiết-kiểm-thử-trực-tiếp-api-direct-api-verification)
6. [Bằng chứng kiểm tra mã nguồn (Code Inspection)](#6-bằng-chứng-kiểm-tra-mã-nguồn-code-inspection)
7. [Bảng theo dõi hạng mục chưa kiểm chứng](#7-bảng-theo-dõi-hạng-mục-chưa-kiểm-chứng)
8. [Danh mục tệp minh chứng và mã nguồn cập nhật](#8-danh-mục-tệp-minh-chứng-và-mã-nguồn-cập-nhật)

---

## 1. LÀM RÕ VÀ XỬ LÝ MÂU THUẪN QUYỀN DUYỆT NHÓM LỖI AI (RBAC)

### 1.1 Hiện trạng & Phân tích nguyên nhân gốc rễ
* **Nghiệp vụ cốt lõi:**
  - AI chỉ mang tính tham khảo, hỗ trợ kỹ thuật viên và quản lý gợi ý phân loại lỗi ban đầu.
  - Phân loại lỗi kỹ thuật là trách nhiệm chuyên môn. Nhân viên **Tiếp nhận (RECEPTIONIST)** chỉ tiếp nhận máy, ghi nhận triệu chứng khách hàng mô tả, không có chuyên môn kỹ thuật để duyệt kết luận nhóm lỗi.
  - **Kỹ thuật viên được phân công (Assigned TECHNICIAN)** và **Quản lý (MANAGER)** là những người có thẩm quyền kiểm tra thực tế bo mạch/linh kiện và duyệt kết luận nhóm lỗi.
  - Quyền duyệt chỉ hợp lệ khi phiếu **chưa đóng** (`RECEIVED`, `INSPECTING`, `REPAIRING`). Khi phiếu đã đóng (`COMPLETED`, `REJECTED`, `RETURNED`), không được phép thay đổi kết luận nhóm lỗi.
* **Xác định mâu thuẫn:**
  - Trong mã nguồn backend thực thi (`backend/app/services/ai_error_classifier.py` và `backend/app/services/auth_service.py`), quyền `ai.review` đã được cài đặt chặt chẽ: chỉ `MANAGER` và `TECHNICIAN` có quyền này, đồng thời hàm `review_ai_classification` kiểm tra KTV phải đúng người được giao cho phiếu.
  - **Sai lệch nằm ở tài liệu docstring và chú thích giao diện:**
    - Docstring tại `backend/app/routers/ai.py` (dòng 124) ghi sai chú thích: *"Duyệt kết quả AI (Tiếp nhận/KTV/Quản lý)"*.
    - Chú thích tại `frontend/index.html` (dòng 865) ghi sai: *"Tiếp nhận hoặc KTV duyệt loại lỗi"*.
* **Kết luận & Khắc phục:**
  - **Tài liệu & chú thích sai; logic mã nguồn nghiệp vụ đúng.**
  - Đã cập nhật chuẩn hóa docstring trong `backend/app/routers/ai.py` và chú thích trong `frontend/index.html` thể hiện chính xác: **Chỉ KTV phụ trách phiếu hoặc Quản lý được duyệt khi phiếu đang mở; Tiếp nhận chỉ xem gợi ý tham khảo.**
  - Đã tạo bộ kiểm thử trực tiếp API độc lập (`tests/test_ai_review_rbac_direct.py`) xác thực toàn bộ ma trận phân quyền.

---

## 2. NGUYÊN TẮC AN TOÀN DỮ LIỆU & KIỂM CHỨNG CÁCH LY CSDL

Để bảo đảm tuyệt đối tính toàn vẹn của cơ sở dữ liệu đang vận hành (`database/baohanh_ai.db`), toàn bộ quy trình kiểm thử tuân thủ nghiêm ngặt các nguyên tắc:
1. **Kiểm tra mã băm SHA256 trước và sau:**
   - CSDL vận hành: `database/baohanh_ai.db`
   - SHA256 trước khi thực hiện: `BB5766B670441CCFE137EA0BCBD66736D6370811D8809BB7E80BFF29DFDA03AE`
   - SHA256 sau khi hoàn tất toàn bộ kiểm thử: `BB5766B670441CCFE137EA0BCBD66736D6370811D8809BB7E80BFF29DFDA03AE`
   - **Kết quả: Trùng khớp 100%, CSDL vận hành hoàn toàn nguyên vẹn, không có bất kỳ thao tác ghi/xóa/reset nào.**
2. **Cơ chế cách ly môi trường kiểm thử:**
   - Bản sao lưu CSDL độc lập được sao chép ra tệp tạm: `database/temp_browser_e2e.db`.
   - Máy chủ kiểm thử chuyên dụng khởi chạy trên cổng `http://127.0.0.1:8088/` với biến môi trường `DATABASE_URL=sqlite:///database/temp_browser_e2e.db`.
   - Engine SQLAlchemy kiểm tra chặn cứng bằng mã: nếu đường dẫn CSDL chứa `baohanh_ai.db` sẽ lập tức kích hoạt `AssertionError` và dừng tiến trình.
   - Trình duyệt Chrome headless vận hành trên thư mục cấu hình tạm biệt lập và tự dọn dẹp sạch sẽ sau khi hoàn tất.

---

## 3. BẢNG TỔNG HỢP PHÂN LOẠI PHƯƠNG PHÁP KIỂM CHỨNG

Hệ thống phân tách rõ 4 nhóm phương pháp kiểm chứng cho toàn bộ các chức năng:

| STT | Chức năng / Ca nghiệp vụ | Phương pháp kiểm chứng | Trạng thái | Minh chứng đính kèm |
|:---:|:---|:---:|:---:|:---|
| 1 | Quản trị tài khoản: Tạo tài khoản KTV | **Trình duyệt (Browser E2E)** | **PASS** | `screenshots/01_account_locked_persisted.png` |
| 2 | Quản trị tài khoản: Khóa tài khoản & kiểm tra bền vững sau reload | **Trình duyệt (Browser E2E)** | **PASS** | `screenshots/01_account_locked_persisted.png` |
| 3 | Quản trị tài khoản: Chặn đăng nhập tài khoản bị khóa | **Trình duyệt (Browser E2E)** | **PASS** | `screenshots/01_locked_login_blocked.png` |
| 4 | Quản trị tài khoản: Mở khóa tài khoản & đăng nhập thành công | **Trình duyệt (Browser E2E)** | **PASS** | `screenshots/01_account_unlocked_persisted.png`<br>`screenshots/01_unlocked_login_success.png` |
| 5 | Lập phiếu cho Serial đã tồn tại (không có phiếu mở) | **Trình duyệt (Browser E2E)** | **PASS** | `screenshots/02_ticket_created_existing_serial.png` |
| 6 | Đăng ký máy mới (ô Ngày mua rỗng) & Lập phiếu | **Trình duyệt (Browser E2E)** | **PASS** | `screenshots/03_ticket_created_new_device.png` |
| 7 | Quản lý phân công KTV & bắt đầu kiểm tra (`INSPECTING`) | **Trình duyệt (Browser E2E)** | **PASS** | `screenshots/04_flow_inspecting.png` |
| 8 | KTV chẩn đoán & chuyển sang sửa chữa (`REPAIRING`) | **Trình duyệt (Browser E2E)** | **PASS** | `screenshots/04_flow_repairing.png` |
| 9 | KTV hoàn tất sửa chữa, nghiệm thu kiểm tra (`COMPLETED`) | **Trình duyệt (Browser E2E)** | **PASS** | `screenshots/04_flow_completed.png` |
| 10 | Tiếp nhận bàn giao trả máy cho khách (`RETURNED`) | **Trình duyệt (Browser E2E)** | **PASS** | `screenshots/04_flow_returned.png` |
| 11 | KTV đề xuất từ chối bảo hành (hộp chờ Quản lý duyệt) | **Trình duyệt (Browser E2E)** | **PASS** | `screenshots/05_rejection_proposed_pending.png` |
| 12 | Quản lý không đồng ý từ chối → KTV tiếp tục xử lý | **Trình duyệt (Browser E2E)** | **PASS** | `screenshots/05_rejection_declined_tech_continues.png` |
| 13 | Quản lý duyệt đề xuất từ chối → Phiếu sang `REJECTED` | **Trình duyệt (Browser E2E)** | **PASS** | `screenshots/06_rejection_approved_ticket_rejected.png` |
| 14 | Tiếp nhận bàn giao trả máy từ chối cho khách (`RETURNED`) | **Trình duyệt (Browser E2E)** | **PASS** | `screenshots/06_rejected_device_returned.png` |
| 15 | AI-01: Gợi ý phân loại lỗi & KTV duyệt kết luận trên UI | **Trình duyệt (Browser E2E)** | **PASS** | `screenshots/07_ai_01_suggest_and_review.png` |
| 16 | AI-02: Tóm tắt lịch sử bảo hành thiết bị bằng AI trên UI | **Trình duyệt (Browser E2E)** | **PASS** | `screenshots/07_ai_02_device_history_modal.png` |
| 17 | AI-03: Soạn tin nhắn tiến độ & Sao chép clipboard trên UI | **Trình duyệt (Browser E2E)** | **PASS** | `screenshots/07_ai_03_notification_copied.png` |
| 18 | Phản hồi lỗi form/API thân thiện bằng tiếng Việt trên UI | **Trình duyệt (Browser E2E)** | **PASS** | `screenshots/07_api_error_handling_toast.png` |
| 19 | Tiếp nhận tạo mới và sửa địa chỉ khách hàng trên UI | **Trình duyệt (Browser E2E)** | **PASS** | `screenshots/08_customer_create_and_edit.png` |
| 20 | Tiếp nhận đăng ký và sửa ngày mua thiết bị trên UI | **Trình duyệt (Browser E2E)** | **PASS** | `screenshots/08_device_create_and_edit.png` |
| 21 | Kiểm tra RBAC: KTV bị ẩn hoàn toàn các nút thêm khách/máy | **Trình duyệt (Browser E2E)** | **PASS** | `screenshots/08_technician_rbac_hidden_buttons.png` |
| 22 | Quyền duyệt AI: Tiếp nhận gọi API duyệt bị chặn 403 | **API trực tiếp (Direct API)** | **PASS** | `logs/api_ai_review_rbac.log` |
| 23 | Quyền duyệt AI: KTV không được phân công gọi API duyệt bị chặn 403 | **API trực tiếp (Direct API)** | **PASS** | `logs/api_ai_review_rbac.log` |
| 24 | Quyền duyệt AI: KTV được phân công gọi API duyệt đạt 200 OK | **API trực tiếp (Direct API)** | **PASS** | `logs/api_ai_review_rbac.log` |
| 25 | Quyền duyệt AI: Quản lý gọi API duyệt đạt 200 OK | **API trực tiếp (Direct API)** | **PASS** | `logs/api_ai_review_rbac.log` |
| 26 | Trạng thái duyệt AI: Phiếu đã đóng gọi API duyệt bị chặn 400 | **API trực tiếp (Direct API)** | **PASS** | `logs/api_ai_review_rbac.log` |
| 27 | Kiểm tra thuật toán Fallback & Cache Rules của AI Classifier | **Kiểm tra mã nguồn (Code)** | **PASS** | `backend/app/services/ai_error_classifier.py` |
| 28 | Kiểm tra phân quyền ma trận 13 quyền chi tiết trong Token JWT | **Kiểm tra mã nguồn (Code)** | **PASS** | `backend/app/services/auth_service.py` |
| 29 | Tích hợp gửi SMS thông báo thật qua nhà mạng (Brandname SMS) | **Chưa kiểm chứng** | *CHƯA LÀM* | Cần hợp đồng gateway viễn thông bên ngoài |
| 30 | Kết nối máy in nhiệt Bluetooth in phiếu biên nhận vật lý | **Chưa kiểm chứng** | *CHƯA LÀM* | Cần thiết bị phần cứng ngoại vi tại quầy |

---

## 4. CHI TIẾT TỪNG CA KIỂM THỬ TRÌNH DUYỆT THỰC TẾ (E2E BROWSER TEST)

> **Ghi chú bắt buộc:** Toàn bộ các ca dưới đây được thực hiện thông qua Chrome tương tác tự động trực tiếp trên các nút bấm, ô nhập liệu của giao diện; tải lại trang bằng `location.reload()` và đăng nhập lại bằng các vai trò tương ứng để xác nhận dữ liệu đã được lưu bền vững vào CSDL.

### Kịch bản 1: Quản lý tài khoản (Tạo, khóa/mở khóa, thử đăng nhập tài khoản bị khóa)
* **Dữ liệu thực tế:** Tạo tài khoản tên đăng nhập `tech_e2e_lock_demo`, vai trò Kỹ thuật viên, họ tên *"Kỹ Thuật Viên E2E Test"*.
* **Các bước thực hiện:**
  1. Quản lý (`manager01`) đăng nhập, chuyển sang tab *Quản lý tài khoản*, bấm nút *Thêm tài khoản*, điền form và lưu.
  2. Tại hàng của tài khoản vừa tạo, bấm nút *Khoá*. Bảng hiển thị ngay huy hiệu màu đỏ: `Đã khoá`.
  3. Thực hiện `location.reload()`, đăng nhập lại bằng `manager01`, vào lại tab *Quản lý tài khoản*. Trạng thái vẫn duy trì bền vững là `Đã khoá`.
  4. Đăng xuất. Thử đăng nhập vào hệ thống bằng `tech_e2e_lock_demo`. Hệ thống chặn đăng nhập và hiển thị thông báo tài khoản đã bị khóa.
  5. Đăng nhập lại `manager01`, bấm nút *Mở khoá*. Tải lại trang, tài khoản chuyển thành `Đang làm việc`.
  6. Đăng xuất, đăng nhập thành công bằng `tech_e2e_lock_demo`.
* **Ảnh minh chứng:**
  - `screenshots/01_account_locked_persisted.png`
  - `screenshots/01_locked_login_blocked.png`
  - `screenshots/01_account_unlocked_persisted.png`
  - `screenshots/01_unlocked_login_success.png`

---

### Kịch bản 2: Số sê-ri đã tồn tại, không có phiếu mở → Lập phiếu tiếp nhận mới
* **Dữ liệu thực tế:** Số sê-ri `SN-ASUS-VALID-01` (Laptop Asus ROG Strix G16 của khách hàng Nguyễn Văn An).
* **Các bước thực hiện:**
  1. Tiếp nhận (`receptionist01`) vào tab *Phiếu bảo hành* (quy trình Wizard Tiếp nhận tại quầy).
  2. Nhập `SN-ASUS-VALID-01` và bấm *Kiểm tra sê-ri*.
  3. Kết quả hiển thị đúng thông tin máy đã có trong hệ thống kèm trạng thái còn hạn bảo hành; nút *Tiếp tục bước 2* xuất hiện.
  4. Bấm *Tiếp tục bước 2*, điền mô tả sự cố: *"Bàn phím bị liệt cụm phím số bên phải, sạc chập chờn khi cắm nguồn"*, phụ kiện đi kèm và tình trạng ngoại quan. Bấm *Lập phiếu tiếp nhận*.
  5. Mã phiếu tạo thành công (ví dụ `TK-20261028-3902`). Tải lại trang (`location.reload()`), đăng nhập lại và mở danh sách phiếu: phiếu hiển thị bền vững ở trạng thái `Tiếp nhận` (`RECEIVED`).
* **Ảnh minh chứng:**
  - `screenshots/02_ticket_created_existing_serial.png`

---

### Kịch bản 3: Số sê-ri chưa tồn tại → Đăng ký thiết bị mới → Lập phiếu bảo hành
* **Dữ liệu thực tế:** Số sê-ri mới tạo động `SN-NEW-DELL-353381`.
* **Các bước thực hiện:**
  1. Tiếp nhận (`receptionist01`) tra cứu số sê-ri mới chưa từng có trên hệ thống.
  2. Hệ thống hiển thị form *Đăng ký thiết bị mới*. Kiểm tra ô *Ngày mua*: giá trị rỗng (`value = ''`), tuân thủ nghiêm ngặt yêu cầu không tự gán ngày ngầm định làm sai lệch hạn bảo hành.
  3. Điền thông tin chủ sở hữu, chọn dòng máy *Laptop Dell UltraBook XPS 13*, điền ngày mua `15/06/2025` (hệ thống tự động tính ngày hết hạn `15/06/2026`, nhận diện đã quá hạn 135 ngày).
  4. Điền mô tả hiện tượng hư hỏng và bấm *Đăng ký thiết bị & Lập phiếu*.
  5. Tải lại trang, chuyển sang tab *Thiết bị*: thiết bị mới đã được lưu vào danh mục với nhãn đỏ `🔴 Đã hết hạn`. Chuyển sang tab *Phiếu bảo hành*: phiếu mới hiển thị chuẩn với thông tin thiết bị vừa đăng ký.
* **Ảnh minh chứng:**
  - `screenshots/03_ticket_created_new_device.png`

---

### Kịch bản 4: Toàn bộ chu trình sửa chữa từ Tiếp nhận đến Trả máy cho khách
* **Mã phiếu kiểm thử:** `TK-20261028-3902` (Serial `SN-ASUS-VALID-01`).
* **Các bước thực hiện:**
  1. **Bước 1 (Phân công & Kiểm tra):** Quản lý (`manager01`) mở modal chi tiết phiếu, bấm nút *Phân công KTV*, chọn `technician01` (Trần Minh Tuấn), bấm xác nhận; sau đó bấm *Bắt đầu kiểm tra*. Tải lại trang, phiếu chuyển sang `Kiểm tra` (`INSPECTING`).
  2. **Bước 2 (Chẩn đoán & Bắt đầu sửa):** KTV (`technician01`) mở phiếu, bấm *Bắt đầu sửa chữa*. Điền kết luận chẩn đoán: *"Chập cáp ma trận phím số, chân cắm nguồn DC-in bị lỏng mối hàn"*, xác nhận đủ điều kiện bảo hành (`is_warranty_eligible = true`). Xác nhận. Tải lại trang, phiếu chuyển sang `Sửa chữa` (`REPAIRING`).
  3. **Bước 3 (Ghi nhận sửa chữa & Nghiệm thu):** KTV hoàn tất sửa chữa, bấm *Xác nhận hoàn tất*. Điền nội dung sửa: *"Thay mới cụm cáp phím số Asus, hàn gia cố chân cắm nguồn DC-in, vệ sinh tản nhiệt"*, linh kiện đã thay, chọn kết quả kiểm tra đạt yêu cầu (`repair_test_passed = true`). Xác nhận. Tải lại trang, phiếu chuyển sang `Hoàn tất` (`COMPLETED`).
  4. **Bước 4 (Bàn giao trả máy):** Nhân viên Tiếp nhận (`receptionist01`) mở phiếu Hoàn tất, bấm *Xác nhận trả máy*. Điền ghi chú bàn giao: *"Khách hàng đã kiểm tra thực tế máy hoạt động hoàn hảo, đã ký nhận biên bản bàn giao và nhận lại máy"*. Xác nhận. Tải lại trang, phiếu chuyển sang trạng thái đóng cuối cùng `Đã trả máy` (`RETURNED`).
* **Ảnh minh chứng:**
  - `screenshots/04_flow_inspecting.png`
  - `screenshots/04_flow_repairing.png`
  - `screenshots/04_flow_completed.png`
  - `screenshots/04_flow_returned.png`

---

### Kịch bản 5: KTV đề xuất từ chối → Quản lý không đồng ý → KTV tiếp tục sửa chữa
* **Dữ liệu thực tế:** Phiếu của thiết bị hết hạn bảo hành tạo ở Kịch bản 3 (`TK-20261028-4489`).
* **Các bước thực hiện:**
  1. Quản lý phân công KTV và chuyển phiếu sang `INSPECTING`.
  2. KTV (`technician01`) mở phiếu, phát hiện thiết bị bị rơi cấn móp, bấm nút *Đề xuất từ chối*. Điền lý do: *"Khách hàng làm rơi máy cấn móp nặng góc vỏ, rách tem bảo hành"*, gửi đề xuất.
  3. Tải lại trang, mở lại phiếu bằng tài khoản KTV: hộp cảnh báo màu vàng hiển thị rõ: *"Đề xuất từ chối bảo hành (chờ Quản lý duyệt)"*.
  4. Quản lý (`manager01`) đăng nhập, mở phiếu, thấy đề xuất của KTV kèm 2 nút *Duyệt từ chối* và *Không đồng ý*. Quản lý bấm *Không đồng ý*, nhập chỉ đạo: *"Không đồng ý từ chối, yêu cầu KTV hỗ trợ giá linh kiện ưu đãi để sửa dịch vụ"*.
  5. Tải lại trang: phiếu vẫn được giữ nguyên ở trạng thái `Kiểm tra` (`INSPECTING`). Đăng nhập KTV: KTV thấy nút *Bắt đầu sửa chữa* khả dụng trở lại để tiếp tục quy trình xử lý.
* **Ảnh minh chứng:**
  - `screenshots/05_rejection_proposed_pending.png`
  - `screenshots/05_rejection_declined_tech_continues.png`

---

### Kịch bản 6: KTV đề xuất từ chối → Quản lý duyệt từ chối → Tiếp nhận trả máy
* **Dữ liệu thực tế:** Lập phiếu mới `TK-20261028-4882` cho sự cố máy bị rơi xuống nước biển ăn mòn rỉ sét bo mạch.
* **Các bước thực hiện:**
  1. Tiếp nhận tạo phiếu; Quản lý phân công KTV và bắt đầu kiểm tra.
  2. KTV kiểm tra thấy nước biển gây rỉ sét nghiêm trọng, bấm *Đề xuất từ chối*, điền nội dung đề xuất.
  3. Quản lý (`manager01`) vào phiếu, bấm *Duyệt từ chối*, nhập lý do: *"Đã duyệt từ chối bảo hành theo biên bản giám định kỹ thuật nước vào máy"*. Tải lại trang: phiếu chuyển sang trạng thái `Từ chối` (`REJECTED`).
  4. Nhân viên Tiếp nhận (`receptionist01`) mở phiếu Từ chối, bấm *Xác nhận trả máy*, điền biên bản bàn giao trả máy từ chối cho khách. Tải lại trang: phiếu hoàn thành chu trình sang `Đã trả máy` (`RETURNED`).
* **Ảnh minh chứng:**
  - `screenshots/06_rejection_approved_ticket_rejected.png`
  - `screenshots/06_rejected_device_returned.png`

---

### Kịch bản 7: Ba chức năng AI, sao chép thông báo, kiểm tra phản hồi lỗi giao diện
* **Các bước thực hiện:**
  1. **AI-01 (Gợi ý loại lỗi & Phê duyệt):** KTV mở phiếu đang kiểm tra, bấm nút *Gợi ý loại lỗi (AI)*. Hộp gợi ý hiển thị nhãn *AI Engine*, loại lỗi gợi ý *"Lỗi màn hình hiển thị"*, độ chắc chắn 93%. KTV bấm nút *Xác nhận nhóm lỗi này*. Tải lại trang: kết luận chẩn đoán chính thức được ghi nhận vào phiếu.
  2. **AI-02 (Tóm tắt lịch sử bảo hành thiết bị):** Bấm nút *Tóm tắt lịch sử (AI)* tại thanh công cụ của phiếu. Hộp thoại modal mở ra, tải toàn bộ lịch sử các lần bảo hành trước đó bằng mô hình AI gpt-4o-mini kèm phân tích tần suất lỗi.
  3. **AI-03 (Soạn tin nhắn tiến độ & Sao chép):** Bấm nút *Soạn thông báo (AI)*. Hệ thống tự động soạn sẵn tin nhắn thông báo tiến độ gửi khách hàng. Bấm nút *Sao chép*. Giao diện cập nhật thông báo màu xanh *"✔ Đã sao chép tin nhắn!"* và nội dung được đưa vào clipboard hệ thống.
  4. **Kiểm tra phản hồi lỗi form/API:** Chuyển sang tab *Khách hàng*, bấm *Thêm khách hàng*, cố ý để trống ô Tên và nhập số điện thoại không hợp lệ (`12345`). Bấm Submit: giao diện bắt lỗi ngay lập tức, hiển thị thông báo tiếng Việt rõ ràng: *"Vui lòng nhập họ và tên khách hàng."* mà không bị crash hay hiển thị mã lỗi kỹ thuật khó hiểu.
* **Ảnh minh chứng:**
  - `screenshots/07_ai_01_suggest_and_review.png`
  - `screenshots/07_ai_02_device_history_modal.png`
  - `screenshots/07_ai_03_notification_copied.png`
  - `screenshots/07_api_error_handling_toast.png`

---

### Kịch bản 8: Tạo/sửa khách hàng & thiết bị theo quyền; Kiểm tra RBAC ẩn nút
* **Các bước thực hiện:**
  1. **Tạo & sửa khách hàng:** Nhân viên Tiếp nhận (`receptionist01`) tạo khách hàng mới *"GS Ngô Bảo Châu"*, SĐT `0981603202`, địa chỉ ban đầu tại Đống Đa, Hà Nội. Bấm nút *Sửa*, đổi địa chỉ thành *"Tòa nhà Vincom, 54A Nguyễn Chí Thanh, Hà Nội"*. Tải lại trang: thông tin khách hàng cập nhật chuẩn xác.
  2. **Đăng ký & sửa thiết bị:** Đăng ký máy mới `SN-MAC-603202` gán cho khách hàng GS Ngô Bảo Châu với ngày mua `15/03/2025`. Bấm *Sửa*, chỉnh lại ngày mua thành `15/03/2025`. Tải lại trang: máy hiển thị trong danh sách kèm thời hạn bảo hành 24 tháng tính chính xác đến `15/03/2027`.
  3. **Kiểm tra phân quyền RBAC ẩn nút:** Đăng xuất Tiếp nhận, đăng nhập bằng tài khoản KTV (`technician01`). Chuyển qua tab *Khách hàng* và tab *Thiết bị*: nút *Thêm khách hàng* và *Thêm thiết bị* bị ẩn hoàn toàn khỏi giao diện theo đúng thẩm quyền nghiệp vụ (KTV chỉ xem dữ liệu, không có quyền tạo mới/chỉnh sửa danh mục khách hàng và thiết bị).
* **Ảnh minh chứng:**
  - `screenshots/08_customer_create_and_edit.png`
  - `screenshots/08_device_create_and_edit.png`
  - `screenshots/08_technician_rbac_hidden_buttons.png`

---

## 5. CHI TIẾT KIỂM THỬ TRỰC TIẾP API (DIRECT API VERIFICATION)

Tệp thực thi: `tests/test_ai_review_rbac_direct.py`  
Tệp nhật ký kết quả: `logs/api_ai_review_rbac.log`

| STT | Endpoint | Phương thức | Tài khoản / Vai trò | Kỳ vọng | Kết quả thực tế | Trạng thái |
|:---:|:---|:---:|:---|:---:|:---:|:---:|
| 1 | `/api/v1/ai/results/{id}/review` | PATCH | `receptionist01` (RECEPTIONIST) | `403 Forbidden` (Chặn: Tiếp nhận không có quyền duyệt nhóm lỗi kỹ thuật) | `403 Forbidden` | **PASS** |
| 2 | `/api/v1/ai/results/{id}/review` | PATCH | `technician02` (KTV không được giao phiếu) | `403 Forbidden` (Chặn: Chỉ KTV phụ trách phiếu mới được duyệt) | `403 Forbidden` | **PASS** |
| 3 | `/api/v1/ai/results/{id}/review` | PATCH | `technician01` (KTV được giao phiếu) | `200 OK` (Duyệt thành công, cập nhật `error_category_id` vào phiếu) | `200 OK` | **PASS** |
| 4 | `/api/v1/ai/results/{id}/review` | PATCH | `manager01` (MANAGER) | `200 OK` (Quản lý duyệt thành công) | `200 OK` | **PASS** |
| 5 | `/api/v1/ai/results/{id}/review` | PATCH | Gọi duyệt khi phiếu đã ở trạng thái `COMPLETED` | `400 Bad Request` (Chặn: Không cho phép duyệt kết quả AI trên phiếu đã đóng) | `400 Bad Request` | **PASS** |

---

## 6. BẰNG CHỨNG KIỂM TRA MÃ NGUỒN (CODE INSPECTION)

1. **Ma trận phân quyền (RBAC Engine) – `backend/app/services/auth_service.py`:**
   - Cung cấp 13 quyền nguyên tử: `ai.classify`, `ai.review`, `ai.view`, `ticket.create`, `ticket.diagnose`, `ticket.repair`, `ticket.handover`, `ticket.reject`, `user.manage`, `customer.create`, `customer.update`, `device.manage`, `product.manage`.
   - `RECEPTIONIST` sở hữu các quyền: `ticket.create`, `ticket.handover`, `customer.*`, `device.manage`, `ai.view`, `ai.classify`. **Tuyệt đối không có quyền `ai.review`.**
   - `TECHNICIAN` sở hữu các quyền: `ticket.diagnose`, `ticket.repair`, `ticket.update_status`, `ai.classify`, `ai.review`, `ai.view`. Không có quyền tạo khách hàng, thêm thiết bị hay bàn giao trả máy.
2. **Logic xét duyệt phân loại AI – `backend/app/services/ai_error_classifier.py`:**
   - Hàm `review_ai_classification(db, result_id, reviewer_id, decision, note)`:
     - Kiểm tra trạng thái phiếu: `if ticket.status in ("COMPLETED", "REJECTED", "RETURNED"): raise HTTPException(400, "Phiếu đã đóng")`.
     - Kiểm tra quyền hạn KTV: `if reviewer.role == "TECHNICIAN" and ticket.assigned_technician_id != reviewer.id: raise HTTPException(403, "Chỉ KTV được phân công mới được duyệt")`.
     - Cập nhật nhất quán: Khi duyệt `APPROVED`, tự động ghi nhận `ticket.error_category_id = ai_result.suggested_category_id`.
3. **Cơ chế Fallback & Rules Matching của AI:**
   - Tích hợp 2 tầng xử lý: Mô hình OpenAI API (`gpt-4o-mini`) và bộ quy tắc từ khóa cục bộ tiếng Việt (`ErrorClassifierService._rule_based_classify`). Khi mất kết nối mạng ngoài, hệ thống tự động fallback về engine mô phỏng đảm bảo nghiệp vụ quầy tiếp nhận không bị gián đoạn.

---

## 7. BẢNG THEO DÕI HẠNG MỤC CHƯA KIỂM CHỨNG

Các chức năng sau được xác nhận chưa kiểm chứng bằng môi trường thực tế do giới hạn hạ tầng phần cứng và dịch vụ bên thứ ba:

1. **Tích hợp gửi SMS tự động qua Brandname Viettel/VNPT:**
   - *Lý do:* Hệ thống hiện mới hỗ trợ chức năng soạn tin nhắn thông báo tiến độ bằng AI và sao chép vào bộ nhớ tạm trên giao diện (`ai-noti-copy-status`). Chưa kết nối cổng Gateway viễn thông thực tế do cần hợp đồng thuê đầu số SMS Brandname thương mại.
2. **In phiếu biên nhận vật lý qua máy in nhiệt Bluetooth / POS tại quầy:**
   - *Lý do:* Giao diện đã có nút xem chi tiết và in phiếu qua hộp thoại in của trình duyệt (`window.print()`). Chưa kiểm thử kết nối trực tiếp với phần cứng máy in bill nhiệt 80mm tại bàn quầy tiếp nhận.

---

## 8. DANH MỤC TỆP MINH CHỨNG VÀ MÃ NGUỒN CẬP NHẬT

### 8.1 Danh mục tệp minh chứng (Đường dẫn tương đối trong dự án)
* **Báo cáo nghiệm thu:** `docs/evidence/BAO_CAO_NGHIEM_THU_TOAN_DIEN.md`
* **Nhật ký kiểm thử trình duyệt tự động:** `docs/evidence/logs/browser_e2e_test.log`
* **Nhật ký kiểm thử trực tiếp API AI Review:** `docs/evidence/logs/api_ai_review_rbac.log`
* **Thư mục ảnh chụp màn hình:** `docs/evidence/screenshots/`
  1. `screenshots/01_account_locked_persisted.png`
  2. `screenshots/01_account_unlocked_persisted.png`
  3. `screenshots/01_locked_login_blocked.png`
  4. `screenshots/01_unlocked_login_success.png`
  5. `screenshots/02_ticket_created_existing_serial.png`
  6. `screenshots/03_ticket_created_new_device.png`
  7. `screenshots/04_flow_inspecting.png`
  8. `screenshots/04_flow_repairing.png`
  9. `screenshots/04_flow_completed.png`
  10. `screenshots/04_flow_returned.png`
  11. `screenshots/05_rejection_proposed_pending.png`
  12. `screenshots/05_rejection_declined_tech_continues.png`
  13. `screenshots/06_rejection_approved_ticket_rejected.png`
  14. `screenshots/06_rejected_device_returned.png`
  15. `screenshots/07_ai_01_suggest_and_review.png`
  16. `screenshots/07_ai_02_device_history_modal.png`
  17. `screenshots/07_ai_03_notification_copied.png`
  18. `screenshots/07_api_error_handling_toast.png`
  19. `screenshots/08_customer_create_and_edit.png`
  20. `screenshots/08_device_create_and_edit.png`
  21. `screenshots/08_technician_rbac_hidden_buttons.png`

### 8.2 Danh mục tệp mã nguồn liên quan
* `backend/app/routers/ai.py` (Chuẩn hóa docstring quyền duyệt nhóm lỗi AI)
* `frontend/index.html` (Chuẩn hóa chú thích quyền duyệt AI trên giao diện)
* `tests/test_ai_review_rbac_direct.py` (Kịch bản kiểm thử API trực tiếp)
* `tests/run_e2e_server.py` (Máy chủ kiểm thử E2E cách ly)
* `tests/browser_e2e_full_scenarios.js` (Bộ kịch bản kiểm thử tự động trình duyệt Chrome qua CDP)

---
*Báo cáo được hoàn thiện và xác nhận tính toàn vẹn vào ngày 28/10/2026.*
