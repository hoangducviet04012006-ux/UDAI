# BÁO CÁO ĐỢT 3 — CẢI THIỆN NGÔN NGỮ & TRẢI NGHIỆM NGƯỜI DÙNG FRONTEND

> **Phạm vi đợt này:** chỉ **lớp hiển thị frontend** (ngôn ngữ, tên chức năng, cách hiển thị mã kỹ thuật, thông báo, dữ liệu mẫu hiển thị).
> **Không thay đổi:** backend, CSDL/schema, API contract, nghiệp vụ BR1–BR4, State Machine, AI-01, quyền hạn, và **không sửa** `tests/**`.
> **Bối cảnh:** tiếp nối Đợt 1 (backend) và Đợt 2 (frontend CRUD/UX). Trước đợt này: E2E 46/46 PASS, minh chứng 24/24 PASS.

---

## 1. Những file đã sửa

| File | Thay đổi |
|---|---|
| `frontend/app.js` | Thêm **lớp hiển thị tiếng Việt**: `displayText()`, `roleLabel()`, `deviceStatusLabel()`, `confidencePercent()`, `stripTechTags()`, `humanizeText()`, `humanizeTraceStep()` + các bảng ánh xạ (`DISPLAY_TEXT_MAP`, `ROLE_LABELS`, `DEVICE_STATUS_LABELS`, `ERROR_GROUP_LABELS`, `INLINE_CODE_MAP`, `KEYWORD_DISPLAY_MAP`). Áp dụng vào toàn bộ bảng/chi tiết/thông báo. Đổi cách hiển thị độ chắc chắn sang **%**, bỏ mã kết quả nội bộ, bỏ mã vai trò, làm sạch thông báo lỗi và trace. |
| `frontend/index.html` | Đổi nhãn menu/tab/nút/cột bảng: tab 6 thành **“Hỗ trợ xác định lỗi”**; nút **“Gợi ý loại lỗi”**, **“Xác nhận loại lỗi”**, **“Không dùng gợi ý”**; cột **“Loại lỗi”**; nhãn **“Người xác nhận”**, **“Mức độ chắc chắn”**, **“Trạng thái xác nhận”**; bỏ ghi chú “(mã 403)” và từ “kỹ thuật”; option mặc định của loại lỗi thành “-- Chưa xác định (để hệ thống gợi ý) --”. |
| `frontend/README.md` | Bổ sung mục **“Ngôn ngữ hiển thị (Đợt 3)”**: bảng đối chiếu “trong CSDL/API ↔ hiển thị trên giao diện” + lưu ý rằng ô nhập liệu vẫn dùng giá trị gốc. |
| `database/baohanh_ai.db` | Chỉ được **tạo lại** bởi `.\dev.ps1 check` (theo thiết kế của bộ minh chứng) — không sửa tay. |

## 2. Những file KHÔNG sửa

| Khu vực | Ghi chú |
|---|---|
| `backend/**` (toàn bộ) | **Không sửa** — file backend sửa gần nhất vẫn là **25/09/2026 08:25** (thuộc Đợt 1). |
| `database/postgres_schema.sql`, `backend/app/models.py` | Không đổi schema/CSDL. |
| `tests/test_scenarios.py`, `tests/seed_data.py`, `tests/init_db.py` | **Không sửa** (giữ nguyên 24 minh chứng + dữ liệu seed). |
| `frontend/styles.css` | Không đổi (bộ class dùng chung của Đợt 2 vẫn đủ). |
| `dev.ps1`, `Makefile`, `docker-compose.yml`, `docs/README.md`, `docs/AUDIT_HE_THONG.md`, `docs/BAO_CAO_DOT_2_FRONTEND.md` | Không sửa. |
| API contract | Không đổi endpoint/field nào; payload gửi lên vẫn là **giá trị gốc** trong CSDL. |

---

## 3. Những thuật ngữ kỹ thuật đã chuyển thành tiếng Việt

### 3.1. Vai trò người dùng (trước đây hiện mã `RECEPTIONIST` trong ô chọn người và lịch sử xử lý)

| Trong CSDL/API | Hiển thị |
|---|---|
| `RECEPTIONIST` | **Nhân viên tiếp nhận** |
| `TECHNICIAN` | **Kỹ thuật viên** |
| `MANAGER` | **Quản lý** |

### 3.2. Trạng thái (trước đây hiện mã enum)

| Trong CSDL/API | Hiển thị |
|---|---|
| `RECEIVED` | Đã tiếp nhận |
| `INSPECTING` | Đang kiểm tra |
| `REPAIRING` | Đang sửa chữa |
| `COMPLETED` | **Đã hoàn tất** (trước là “Hoàn tất”) |
| `REJECTED` | Từ chối bảo hành |
| `ACTIVE` | Đang hoạt động |
| `EXPIRED` | Ngừng theo dõi |
| `PENDING` | **Chờ xác nhận** (trước là “Chờ duyệt”) |
| `APPROVED` | **Đã xác nhận** (trước là “Đã duyệt”) |
| `REJECTED` (kết quả gợi ý) | **Không dùng gợi ý này** (trước là “Đã từ chối”) |

### 3.3. Nhóm lỗi của bộ phân loại (trước đây hiện trong lý do phân tích)

| Trong code/API | Hiển thị |
|---|---|
| `DISPLAY` | màn hình hiển thị |
| `POWER_MAINBOARD` / `POWER` | nguồn / bo mạch |
| `POWER_FAILURE` | thiết bị không lên nguồn |
| `HARDWARE_ERROR` | lỗi phần cứng |
| `SOFTWARE_ERROR` | lỗi phần mềm |
| `NETWORK_ERROR` | lỗi kết nối mạng |
| `KEYBOARD_TOUCHPAD` / `KEYBOARD` / `TOUCHPAD` | bàn phím & touchpad / bàn phím / touchpad |
| `UNKNOWN` | chưa xác định |

### 3.4. Thẻ/mã kỹ thuật trong thông báo của backend (bị loại bỏ khi hiển thị)

| Thông báo backend | Hiển thị cho người dùng |
|---|---|
| `[BR1 FAIL] Không tìm thấy sản phẩm với số serial 'SN-X' …` | “Không tìm thấy sản phẩm với số serial 'SN-X' …” |
| `[BR2 FAIL] Sản phẩm với serial 'SN-SAMS-EXPIRED-02' đã hết hạn bảo hành …` | giữ nguyên nội dung, **bỏ thẻ**, **giữ nguyên số serial** (không bị dịch) |
| `[BR3 FAIL] … (Trạng thái hiện tại: 'INSPECTING')` | “… (Trạng thái hiện tại: 'Đang kiểm tra')” |
| `[STATE MACHINE ERROR] Không được phép chuyển trạng thái từ 'RECEIVED' sang 'COMPLETED'` | “Không được phép chuyển trạng thái từ 'Đã tiếp nhận' sang 'Đã hoàn tất'” |
| `[BR5 REQUIRED] Khi chuyển phiếu sang trạng thái REJECTED, bắt buộc phải cung cấp lý do…` | “Khi chuyển phiếu sang trạng thái Từ chối bảo hành, bắt buộc phải cung cấp lý do…” |
| `… nên không thể xóa để bảo toàn tính toàn vẹn dữ liệu (FK RESTRICT).` | “… nên không thể xóa để bảo toàn tính toàn vẹn dữ liệu.” |
| `[AI-01] … Triệu chứng khớp nhóm 'DISPLAY' … Đề xuất nhãn lỗi 'Loi man hinh hien thi'.` | “… Triệu chứng khớp nhóm 'màn hình hiển thị' … Đề xuất loại lỗi 'Lỗi màn hình hiển thị'.” |
| `[GUARDRAIL] Phát hiện chỉ dẫn can thiệp … [AI-01] Không đủ căn cứ.` | “Phát hiện chỉ dẫn can thiệp … Không đủ căn cứ.” |
| Trace: `[Step 5] Đối chiếu BR2: effective_end_date (…) >= check_date (…) -> True` | `[Bước 5] Đối chiếu điều kiện bảo hành: ngày hết hạn áp dụng (…) >= ngày kiểm tra (…) → Đạt` |
| Trace: `[Result PASS] Điều kiện BR2 ĐẠT …` | `[Kết quả] Điều kiện bảo hành ĐẠT …` |

### 3.5. Từ ngữ giao diện đã đổi cho dễ hiểu

| Trước | Sau |
|---|---|
| Tab “Phân tích lỗi” / “Kết quả phân tích lỗi” | **Hỗ trợ xác định lỗi** |
| Nút “Phân tích lỗi” | **Gợi ý loại lỗi** |
| “Nhãn lỗi hiện tại của phiếu” / “Nhãn đề xuất” | **“Loại lỗi đã ghi trên phiếu”** / **“Loại lỗi được gợi ý”** |
| “Độ tin cậy: 0.93” | **“Mức độ chắc chắn: 93%”** |
| “Mã kết quả: 11” (ID nội bộ `ai_results`) | **không hiển thị** |
| “Chưa đủ căn cứ để đề xuất nhãn” | **“Chưa xác định được loại lỗi”** |
| “Chưa phân loại (để AI gợi ý)” | **“Chưa xác định (để hệ thống gợi ý)”** |
| Nút “Duyệt” / “Từ chối” (kết quả gợi ý) | **“Xác nhận loại lỗi”** / **“Không dùng gợi ý”** |
| “Người xét duyệt” / “Người duyệt” | **“Người xác nhận”** |
| “Trạng thái duyệt” | **“Trạng thái xác nhận”** |
| “Danh mục lỗi” | **“Loại lỗi”** |
| “Lịch sử phân tích của phiếu” | **“Lịch sử gợi ý loại lỗi của phiếu đang chọn”** |
| “Chỉ tài khoản tiếp nhận hoặc quản lý mới có quyền duyệt. Kỹ thuật viên sẽ bị từ chối (mã 403).” | **“Chỉ nhân viên tiếp nhận hoặc quản lý có quyền xác nhận. Kỹ thuật viên không có quyền này.”** |
| “Chi tiết kỹ thuật từng bước đối chiếu” | **“Thông tin đối chiếu chi tiết”** |
| “Lỗi hệ thống phía máy chủ. Vui lòng thử lại.” | **“Hệ thống đang gặp sự cố, vui lòng thử lại sau ít phút.”** |
| “Bạn không có quyền thực hiện thao tác này.” | **“Tài khoản này không có quyền thực hiện thao tác.”** |

---

## 4. Những màn hình đã được cải thiện

| # | Màn hình | Nội dung cải thiện |
|---|---|---|
| 4.1 | **Tổng quan** | Không đổi bố cục; giữ số liệu thật + biểu đồ; phần “Quy tắc nghiệp vụ” vẫn thu gọn và không còn mã BR trên giao diện |
| 4.2 | **Khách hàng** | Tên khách hiển thị có dấu (Nguyễn Văn An / Trần Thị Bình / Lê Hoàng Cường); thông báo thêm/sửa/xóa dùng tên có dấu; hộp thoại xóa nói rõ hậu quả (“còn thiết bị hoặc phiếu bảo hành sẽ không xóa được, hệ thống sẽ báo số lượng còn lại”) |
| 4.3 | **Sản phẩm** | Tên sản phẩm hiển thị có dấu (Điện thoại Samsung…, Màn hình Dell…); **datalist** trong form thiết bị hiển thị nhãn tiếng Việt nhưng vẫn gửi đúng giá trị gốc |
| 4.4 | **Thiết bị** | Chips trạng thái lấy từ một bảng ánh xạ duy nhất (không còn chuỗi trùng lặp); tên sản phẩm/khách hàng có dấu; mục “Thông tin đối chiếu chi tiết” (trace) đã được diễn giải: `[Bước n]`, “ngày hết hạn áp dụng”, “ngày kiểm tra”, “Đạt/Không đạt”, không còn `BR2`, `effective_end_date`, `True/False` |
| 4.5 | **Phiếu bảo hành** | Cột “Loại lỗi” (thay “Danh mục lỗi”); lịch sử xử lý hiển thị ghi chú có dấu và tên người thực hiện kèm **chức danh nghiệp vụ**; thông báo lỗi nghiệp vụ (hết hạn, trùng phiếu, sai chủ sở hữu) đã bỏ thẻ `[BRx FAIL]`; ghi chú seed “Chuyen sang kiem tra ky thuat (Da co san trong seed de test BR3).” → “Chuyển sang kiểm tra kỹ thuật (phiếu có sẵn trong dữ liệu mẫu để kiểm thử điều kiện bảo hành).” |
| 4.6 | **Hỗ trợ xác định lỗi** (tab 6) | Đổi tên tab/tiêu đề; mô tả mới dễ hiểu; nút “Gợi ý loại lỗi”; kết quả hiển thị “Loại lỗi được gợi ý”, “Mức độ chắc chắn: 93%”, “Giải thích”, “Nên hỏi thêm khách hàng…”, trạng thái “Chờ xác nhận / Đã xác nhận / Không dùng gợi ý này”; bỏ “Mã kết quả”, bỏ “AI-01”, bỏ mã vai trò; bảng lịch sử đổi tên cột và hiển thị % |
| 4.7 | **Modal chi tiết phiếu** | Khối gợi ý đổi thành “Gợi ý loại lỗi” + “Loại lỗi đã ghi trên phiếu”, hiển thị % và trạng thái xác nhận; nút mở sang tab mới tên |
| 4.8 | **Thông báo (toast) & hộp thoại** | Lỗi nghiệp vụ hiển thị **lý do thật** bằng tiếng Việt; 409/404/422/403 có câu riêng; thông báo thành công nêu rõ đối tượng (tên khách/sản phẩm/số serial/mã phiếu) |

---

## 5. Những dữ liệu mẫu đã tinh giản / thay đổi

| # | Vấn đề | Xử lý |
|---|---|---|
| 5.1 | Tên **khách hàng / sản phẩm / người dùng / danh mục lỗi** trong seed lưu **không dấu**, hiện thẳng lên giao diện | **Không sửa seed** (tests đang phụ thuộc) → xử lý bằng **lớp hiển thị** `DISPLAY_TEXT_MAP` (20 mục). Người dùng thấy tiếng Việt có dấu; dữ liệu trong CSDL không đổi. |
| 5.2 | Ghi chú lịch sử phiếu của seed/test không dấu và có mã `BR3`/`BR1-BR4` | Ánh xạ hiển thị 4 ghi chú + làm sạch thẻ kỹ thuật |
| 5.3 | Dữ liệu **rác do thử tay** (`hoàng đức việt`, sản phẩm `ss23`, serial `đabsbfsfb`, phiếu “ko bật đc nguồn”) | **Đã được dọn sạch** khi chạy `.\dev.ps1 check` cuối đợt (kịch bản minh chứng tạo lại CSDL từ đầu) — không xóa tay, không ảnh hưởng test |
| 5.4 | Dữ liệu **phục vụ test tự động** (`SN-KT3-AI-01…06`, `SN-KT2-CRUD-2026`, mô tả “Phieu duoc tao de kiem thu…”) | **GIỮ NGUYÊN** — theo yêu cầu, không can thiệp để tránh phá 24 minh chứng |
| 5.5 | Số lượng sản phẩm mẫu | Hiện chỉ có **3 sản phẩm** trong danh mục (Laptop Asus ROG Strix G16, Điện thoại Samsung Galaxy S24 Ultra, Màn hình Dell UltraSharp U2723QE) → **đã vừa phải**, không cần tinh giản, **không thêm** dữ liệu giả |

> **Ghi chú kỹ thuật quan trọng:** các ô nhập liệu vẫn nạp **giá trị gốc** từ CSDL (ví dụ form Sửa khách hàng, form thiết bị) để thao tác lưu/cập nhật khớp chính xác với API — chỉ **phần hiển thị** mới được Việt hoá. Nhờ vậy việc Việt hoá **không** làm sai lệch dữ liệu gửi lên backend.

---

## 6. Những lỗi UX/ngôn ngữ đã phát hiện (audit trước khi sửa)

### A. Khó hiểu với người dùng phổ thông
| # | Phát hiện | Xử lý |
|---|---|---|
| A1 | Tab “Phân tích lỗi” không nói rõ người dùng được lợi gì | Đổi thành **“Hỗ trợ xác định lỗi”** + mô tả nghiệp vụ |
| A2 | “Nhãn lỗi” / “Nhãn đề xuất” (thuật ngữ AI) xuất hiện 6 chỗ | → “Loại lỗi” / “Loại lỗi được gợi ý” |
| A3 | “Độ tin cậy: 0.93” (thang 0–1) | → **“Mức độ chắc chắn: 93%”** |
| A4 | “Mã kết quả: 11” là ID nội bộ bảng `ai_results` | **Ẩn khỏi giao diện** |
| A5 | “Chưa đủ căn cứ để đề xuất nhãn” | → “Chưa xác định được loại lỗi” |
| A6 | “Chưa phân loại” | → “Chưa xác định” |
| A7 | Nút “Duyệt”/“Từ chối” cho gợi ý AI dễ nhầm với duyệt bảo hành | → “Xác nhận loại lỗi” / “Không dùng gợi ý” |
| A8 | “Người xét duyệt”/“Người duyệt” mơ hồ | → “Người xác nhận” |
| A9 | Ghi chú “Kỹ thuật viên sẽ bị từ chối (mã 403)” | → “Kỹ thuật viên không có quyền này.” |
| A10 | “Chi tiết kỹ thuật từng bước đối chiếu” | → “Thông tin đối chiếu chi tiết” |

### B. Thuật ngữ kỹ thuật lộ trên giao diện
| # | Phát hiện | Nguồn | Xử lý |
|---|---|---|---|
| B1 | `[AI-01]` trong lý do phân tích | backend | Lọc bỏ khi hiển thị |
| B2 | `[BR1 FAIL] … [BR5 REQUIRED]`, `[STATE MACHINE ERROR]` | backend | Lọc bỏ, giữ nội dung nghiệp vụ |
| B3 | `(FK RESTRICT)` trong thông báo xóa | backend | Lọc bỏ |
| B4 | `[GUARDRAIL]`, `[INVALID AI OUTPUT]`, `[VALIDATION 422]`, `[REVIEW]` | backend | Lọc bỏ |
| B5 | Mã vai trò `RECEPTIONIST/TECHNICIAN/MANAGER` ở ô chọn người + lịch sử | frontend | Ánh xạ sang chức danh tiếng Việt |
| B6 | Nhóm lỗi `DISPLAY`, `POWER`, … trong lý do | backend | Ánh xạ sang mô tả tiếng Việt |
| B7 | Trace: `BR2`, `effective_end_date`, `check_date`, `-> True` | backend | Diễn giải lại (xem 3.4) |
| B8 | Mã trạng thái trong câu: `'INSPECTING'`, `'RECEIVED'` | backend | Thay bằng tiếng Việt trong ngoặc kép |

### C. Tiếng Việt chưa có dấu (nguồn: dữ liệu backend; frontend **0 lỗi** về chuỗi của chính nó)
| # | Phát hiện | Xử lý |
|---|---|---|
| C1 | 3 khách seed: `Nguyen Van An`, `Tran Thi Binh`, `Le Hoang Cuong` | Ánh xạ hiển thị |
| C2 | 2 sản phẩm seed: `Dien thoai Samsung…`, `Man hinh Dell…` | Ánh xạ hiển thị |
| C3 | 3 người dùng seed: `Nguyen Quan Ly`, `Tran Tiep Nhan`, `Le Ky Thuat` | Ánh xạ hiển thị |
| C4 | 3 danh mục lỗi + mô tả seed không dấu | Ánh xạ hiển thị |
| C5 | Ghi chú lịch sử phiếu (seed/test) không dấu | Ánh xạ 4 ghi chú phổ biến |
| C6 | Từ khoá trong lý do phân tích: “man hinh, ke soc, soc, diem chet” | Ánh xạ từ khoá (chỉ khớp chữ thường) |

### D. Dữ liệu mẫu chưa phù hợp demo
| # | Phát hiện | Xử lý |
|---|---|---|
| D1 | Rác do thử tay trong CSDL hiện tại | Đã dọn bằng `.\dev.ps1 check` cuối đợt |
| D2 | Dữ liệu test (`SN-KT3-AI-*`, mô tả kiểm thử) | Giữ nguyên (theo yêu cầu) |
| D3 | Số sản phẩm mẫu | Chỉ 3 → đã vừa phải |

### E. Hai lỗi **do chính lớp hiển thị mới gây ra** — đã phát hiện bằng kiểm thử runtime và sửa ngay
| # | Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|---|
| E1 | **Số serial bị dịch sai**: `SN-SAMS-EXPIRED-02` → `SN-SAMS-Ngừng theo dõi-02` | Thay mã trạng thái bằng `\b…\b` khớp cả trong chuỗi có dấu `-` | Dùng ranh giới an toàn `(^|[^\w-])…(?![\w-])` — chỉ khớp mã đứng riêng |
| E2 | Ánh xạ tiếng Việt **thiếu một phần** trong lý do AI: `'Loi màn hình hien thi'` | Thay từ khoá chạy **trước** khi thay chuỗi nguyên văn | Đổi thứ tự: khớp **nguyên văn** trước, rồi mới thay mã/từ khoá |

Cả hai đã được xác minh lại bằng script Node `test_humanize.js` (chạy hàm thật trong `app.js`).

---

## 7. Những lỗi KHÔNG sửa vì có thể ảnh hưởng nghiệp vụ (giữ nguyên có chủ đích)

| # | Vấn đề | Vì sao không sửa | Đề xuất |
|---|---|---|---|
| 7.1 | Dữ liệu seed **không dấu** trong CSDL (`Nguyen Van An`, `Loi man hinh hien thi`, …) | Sửa `tests/seed_data.py` có thể phá **minh chứng #2/#3** (đang so khớp tên khách/sản phẩm/danh mục lỗi). Yêu cầu Đợt 3: *“KHÔNG sửa test để PASS”* và *“phải xác định chắc chắn dữ liệu không được tests sử dụng trước khi sửa”* → chọn giải pháp **lớp hiển thị**, dữ liệu gốc giữ nguyên. | Nếu muốn Việt hoá cả trong CSDL: làm ở **Đợt 4** kèm cập nhật đồng bộ minh chứng, chạy `.\dev.ps1 check` sau mỗi bước. |
| 7.2 | Dữ liệu do test tự sinh (`SN-KT3-AI-01…06`, mô tả “Phieu duoc tao de kiem thu…”) xuất hiện trong danh sách demo | Là dữ liệu **phục vụ automated tests** → yêu cầu giữ nguyên | Nếu cần demo “sạch”, chạy `.\dev.ps1 initdb` + `.\dev.ps1 seed` trên CSDL chưa chạy `check`. |
| 7.3 | Thông báo backend vẫn chứa thẻ kỹ thuật `[BR2 FAIL]`, `[AI-01]` trong **response API** | Yêu cầu: mã kỹ thuật được phép tồn tại ở backend/API, chỉ **không hiển thị** cho người dùng. Sửa backend sẽ đổi nội dung mà **minh chứng đang in ra** | Có thể làm sạch ở backend trong đợt riêng, **không bắt buộc**. |
| 7.4 | `provider` (`mock-rule-based`) vẫn có trong response | Không hiển thị trên UI; là thông tin vận hành cho minh chứng KT3 | Giữ nguyên. |
| 7.5 | `service_center_id` vẫn gửi cố định `1` khi tạo phiếu | Hệ thống chỉ có 1 trung tâm và **không có API liệt kê trung tâm**; thêm endpoint là mở rộng phạm vi | Ghi nhận (đã nêu ở báo cáo Đợt 2, mục 5.2). |
| 7.6 | Không có đăng nhập/phân quyền thật | Ngoài phạm vi môn học; backend vẫn kiểm tra vai trò khi xác nhận gợi ý | Giữ nguyên. |
| 7.7 | Ngành hàng trong danh mục sản phẩm là tiếng Anh (`Laptop`, `Smartphone`, `Monitor`) | Đây là **dữ liệu người dùng nhập**, không phải thuật ngữ hệ thống | Không đổi (tránh sửa dữ liệu). |

---

## 8. Kết quả syntax check

| Kiểm tra | Kết quả |
|---|---|
| `node --check frontend/app.js` | **exit code 0 — cú pháp hợp lệ** |
| ID HTML ↔ JS (`check_dot3_ui.py`, mục D) | **PASS** — mọi id JS tham chiếu đều tồn tại trong HTML (không lệch id nào) |
| Handler `onclick/onsubmit` ↔ hàm trong `app.js` | **PASS** — không thiếu hàm nào |
| Hàm định nghĩa trùng lặp | **PASS** — không có |
| Text hiển thị + thuật ngữ kỹ thuật + tiếng Việt không dấu (mục A/B/C) | **PASS** — **49/49** |

---

## 9. Kết quả E2E (server thật, cổng 8014)

Kịch bản `verify_dot3_e2e.py` mô phỏng đúng chuỗi request mà giao diện gọi:

| Nhóm kiểm tra | Kết quả |
|---|---|
| Static: `/`, `/static/app.js`, `/static/styles.css` | PASS (200) |
| 6 tab đúng tên mới; không còn Debug/Swagger/KT2-KT3/AI-01/BR1-BR4/Nhãn/Độ tin cậy/Mã kết quả trong trang phục vụ | PASS |
| `app.js`: không dùng `confirm()/prompt()`, độ chắc chắn dạng %, có lớp hiển thị, không lộ mã vai trò | PASS |
| Thêm khách hàng → reload còn dữ liệu → sửa → reload thấy dữ liệu mới | PASS |
| Xóa khách hàng đang có thiết bị → **409 kèm lý do nghiệp vụ** | PASS |
| Tạo / sửa sản phẩm | PASS |
| Tạo thiết bị (khách + sản phẩm thật), ngày hết hạn tự tính | PASS |
| Chặn tạo thiết bị với khách hàng / sản phẩm không tồn tại (404) | PASS |
| Kiểm tra điều kiện bảo hành trước khi tạo phiếu → tạo phiếu 201, chưa có loại lỗi | PASS |
| Chi tiết phiếu có Serial / Sản phẩm / Khách hàng | PASS |
| Chuyển trạng thái → reload thấy trạng thái mới; lịch sử đúng người thực hiện | PASS |
| State machine vẫn chặn nhảy cóc (400) | PASS |
| Phân tích lỗi → gợi ý “Loi man hinh hien thi” (0.95), lịch sử PENDING | PASS |
| Gợi ý **không** tự ghi vào phiếu; trạng thái phiếu không đổi | PASS |
| **Xác nhận bằng tài khoản có quyền** (nhân viên tiếp nhận) → ghi loại lỗi vào phiếu | PASS |
| **Tài khoản không có quyền** (kỹ thuật viên) → bị chặn 403 | PASS |
| Tra cứu phiếu theo mã (200) / mã sai (404) | PASS |
| Số liệu tổng quan đủ trường cho dashboard | PASS |
| Xóa thiết bị đang có phiếu → 409 (giữ toàn vẹn) | PASS |

```
  TONG KET E2E: 50 PASS | 0 FAIL
```
(46 kiểm tra của Đợt 2 + 4 kiểm tra mới của Đợt 3)

---

## 10. Kết quả `.\dev.ps1 check`

```
== Cong kiem tra truoc khi nop bai

  => TONG KET KT3: 12/12 PASS | FAIL: 0

===========================================================================
  TONG KET CHUNG KT2 + KT3
===========================================================================
  - Tong minh chung KT2: 12 | PASS: 12 | FAIL:  0
  - Tong minh chung KT3: 12 | PASS: 12 | FAIL:  0
  - TONG CONG         : 24 | PASS: 24 | FAIL:  0

===========================================================================
  >>> XAC NHAN: TOAN BO 100% CAC MUC MINH CHUNG KT2 + KT3 DEU DAT (PASS)! <<<
===========================================================================

OK: toan bo minh chung PASS
```

Đã chạy **4 lần** trong đợt này (trước khi sửa để lấy mốc, sau khi thêm lớp hiển thị, sau khi reset CSDL cho E2E, và lần cuối sau khi viết tài liệu) — **tất cả đều 24/24**.

---

## 11. Xác nhận cuối cùng

| Hạng mục | Kết quả |
|---|---|
| **KT2** | **12/12 PASS** |
| **KT3** | **12/12 PASS** |
| **Tổng** | **24/24 PASS** |
| Không sửa `tests/**` | ✅ giữ nguyên 100% |
| Không sửa backend | ✅ (file backend sửa gần nhất: 25/09/2026 08:25 — thuộc Đợt 1) |
| Không đổi CSDL/schema | ✅ |
| Không đổi API contract | ✅ (payload vẫn dùng giá trị gốc từ CSDL) |
| Không đổi BR1–BR4 / State Machine / AI-01 | ✅ (24/24 minh chứng + E2E xác nhận) |
| Không làm chatbot/RAG/LangGraph, không thêm module | ✅ |
| Không tạo dữ liệu giả mới | ✅ (chỉ ánh xạ *hiển thị* cho dữ liệu đang có) |
| File tạm trong repo | ✅ 0 file (`*.log`, `*.tmp`, `*.bak`) |

**Tiêu chí hoàn thành (mục XVII):** A ✅ người không hiểu kỹ thuật đọc được giao diện · B ✅ tiếng Việt có dấu, tự nhiên, thống nhất · C ✅ không còn mã kỹ thuật trên UI · D ✅ tên chức năng mang tính nghiệp vụ · E ✅ dữ liệu mẫu vừa phải · F ✅ CRUD vẫn hoạt động thật · G ✅ không phá API/backend · H–J ✅ BR1–BR4, State Machine, AI-01 nguyên vẹn · K ✅ không sửa 24 minh chứng cũ · L ✅ **24/24 PASS**.





