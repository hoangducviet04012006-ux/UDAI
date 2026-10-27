# BÁO CÁO ĐỢT 2 — HOÀN THIỆN FRONTEND + CRUD + UX

> **Phạm vi:** CHỈ frontend (`frontend/index.html`, `frontend/app.js`, `frontend/styles.css`, `frontend/README.md`). **Không sửa một dòng backend nào.**
> **Bối cảnh:** kế tiếp Đợt 1 (AUD-01 / AUD-24 / AUD-06 / AUD-10 — backend) và dựa trên audit `docs/AUDIT_HE_THONG.md`.
> **Ngày thực hiện:** 25/09/2026 · **Môi trường:** Windows, `py -3.12`, uvicorn tại `http://127.0.0.1:8013` (chạy thật để kiểm thử end-to-end).
> **Ràng buộc đã giữ:** không chatbot / RAG / LangGraph / module mới / đổi framework / đổi schema / sửa test.

---

## 1. Các lỗi đã phát hiện

### 1.1. Lỗi kế thừa từ audit (đã sửa trong đợt này)

| Mã audit | Lỗi | Bằng chứng trước khi sửa |
|---|---|---|
| **AUD-02** | **Biểu đồ Tổng quan không bao giờ vẽ** | `app.js` gọi `#stat-products`/`#stat-customers` không tồn tại trong HTML → `TypeError` → hàm dừng trước `renderStatusChart()` → canvas trống |
| **AUD-03** | Ngày đối chiếu hard-code `2026-09-07` ở 3 chỗ | Cùng một serial: kiểm tra trước báo "CÒN HẠN (Còn 8 ngày)" nhưng lưu phiếu trả **400 [BR2 FAIL] (quá hạn 10 ngày)** |
| **AUD-04** | Dropdown khách hàng hard-code **sai SĐT cả 3 dòng** + không thể thêm khách hàng mới trên UI | `Nguyễn Văn An … 0901234567` trong khi DB là `Nguyen Van An … 0912345678` |
| **AUD-05** | Phiếu không hiển thị Serial / Sản phẩm / Khách hàng / Hạn bảo hành / Lý do từ chối | API trả đủ 4 trường nhưng bảng & modal không render |
| **AUD-11** | Thuật ngữ Anh/kỹ thuật trên giao diện | "Product Instance", "State", "BR1-4", "Debug", "Demo Buttons", "Customer", "Confidence", `error_category_id`, "Swagger Docs"… |
| **AUD-12** | Thành phần nội bộ lộ ra người dùng | Link "Swagger Docs", badge "FastAPI Online", badge "KT2 + KT3 LIVE", nút "Thử nhảy cóc trái phép" |
| **AUD-13** | Nhân viên thao tác hard-code | `DEFAULT_STAFF_ID = 2`, `created_by: 2`, `service_center_id: 1`, `changed_by: 2` |
| **AUD-14** | Form Tiếp nhận **luôn** gán `error_category_id` (mặc định 1) | Phiếu tạo từ UI luôn đã có nhãn → panel AI không minh hoạ đúng luồng KT3 |
| **AUD-15** | Danh mục sản phẩm thiếu nút **Sửa/Xóa** | Bảng chỉ có Thêm |
| **AUD-16** | Dùng `prompt()`/`confirm()` của trình duyệt | Chuyển trạng thái mở `prompt` 1–2 lần; xóa dùng `confirm` |
| **AUD-17** | Thiếu empty/loading state, lỗi bị `console.error` im lặng | Bảng Model/Khách trắng khi rỗng hoặc khi lỗi |
| **AUD-18** | Dead code trùng lặp | 2 listener `DOMContentLoaded`; 2 định nghĩa `runDebugWarrantyCheck`; 2 định nghĩa `loadProductsAndCustomers` |
| **AUD-19** | Serial mẫu + số ngày hard-code, `demo_instances` không dùng | "Còn hạn 495 ngày"/"Quá hạn 980 ngày" ghi cứng theo mốc 07/09 |
| **AUD-28** | Chưa có ô tra cứu phiếu theo mã dù API đã có | `GET /api/v1/warranty-tickets/code/{code}` không được dùng |

### 1.2. Phát hiện thêm trong quá trình audit frontend của Đợt 2

| # | Phát hiện | Ghi chú |
|---|---|---|
| A | Menu chính trộn chức năng kỹ thuật với nghiệp vụ: 5 tab trong đó tab "Kiểm Tra Bảo Hành (Debug)" chiếm vị trí ngang hàng nghiệp vụ, còn "Khách hàng"/"Sản phẩm" bị gộp chung 1 tab | Đã tách thành 6 tab nghiệp vụ |
| B | Toast lỗi dùng `data.detail` từ body không phải JSON (lỗi 500 plain text) → hiện "Lỗi kết nối máy chủ" cho cả lỗi nghiệp vụ | Đã có bảng ánh xạ lỗi 400/403/404/409/422/5xx |
| C | Panel AI trong modal chi tiết phiếu trùng chức năng với màn hình Phân tích lỗi (2 nơi cùng có nút Duyệt/Từ chối) | Đã gom 1 nơi duyệt (tab Phân tích lỗi), modal chỉ hiển thị thông tin + nút mở sang tab |
| D | Số liệu Dashboard có sẵn trong API (`total_customers`, `total_instances`) nhưng UI không dùng, đồng thời không có thẻ "Đang xử lý" | Đã dùng đủ, không cần thêm API thống kê mới |
| E | `frontend/README.md` mô tả sai hành vi form (ghi rằng form luôn gửi `error_category_id`) | Đã cập nhật tài liệu theo hành vi mới |

---

## 2. Các lỗi đã sửa (kèm cách xác minh)

| Mã | Cách sửa | Xác minh |
|---|---|---|
| AUD-02 | Viết lại `loadDashboard()`: chỉ gán vào phần tử **tồn tại**, thêm guard `if (!el) return;`; biểu đồ dùng nhãn tiếng Việt + chip số liệu theo trạng thái | E2E #18/#18b: API thống kê đủ 9 trường; kiểm tra tĩnh 92 id JS ↔ 119 id HTML **không lệch** |
| AUD-03 | Bỏ hoàn toàn `2026-09-07`: pre-check gọi `GET /debug/check-serial/{serial}` **không truyền `check_date`**; ô "Ngày kiểm tra" mặc định `todayISO()` | Kiểm tra tĩnh: `2026-09-07` không còn trong `app.js`/`index.html`; E2E #11a `is_valid = True` khớp với #11 tạo phiếu `201` |
| AUD-04 | Dropdown khách hàng của form Tiếp nhận nạp từ `GET /api/v1/customers/`; thêm **modal Thêm/Sửa khách hàng** + nút **Xóa** | E2E #1–#6 (thêm → reload → sửa → reload), #7–#8 (xóa bị chặn 409 khi còn thiết bị), #19 |
| AUD-05 | Bảng phiếu thêm cột "Thiết bị (số serial)" + tên sản phẩm; modal thêm khối Serial / Sản phẩm / Khách hàng / Hạn bảo hành / Người tiếp nhận (giải mã id → tên qua API users) / Lý do từ chối | E2E #12 kiểm tra đúng bộ ba `(serial_number, product_name, customer_name)` |
| AUD-11 | Việt hoá toàn bộ nhãn (bảng chi tiết ở mục 7); trạng thái hiển thị tiếng Việt, mã gốc vẫn giữ trong dữ liệu & tài liệu | Kiểm tra tĩnh: không còn "Product Instance", "Demo Buttons", "Confidence", "Swagger" |
| AUD-12 | Bỏ link Swagger, badge "FastAPI Online"/"KT2 + KT3 LIVE" khỏi header; bỏ nút "Thử nhảy cóc trái phép" khỏi luồng người dùng (state machine vẫn chặn ở backend, kiểm chứng E2E #14c) | Kiểm tra tĩnh: `"Debug"`, `"Swagger"`, `"KT2"/"KT3"` đều **không còn** trong HTML |
| AUD-13 | Thêm ô **"Người tiếp nhận"** trong form tạo phiếu và **"Người thực hiện"** trong modal chi tiết phiếu, nạp từ `GET /api/v1/ai/demo/users` (dữ liệu thật), mặc định chọn RECEPTIONIST | E2E #14b: lịch sử ghi đúng `changed_by` theo người được chọn (`[2, 3]`) |
| AUD-14 | Option mặc định của danh mục lỗi là **"— Chưa phân loại (để AI gợi ý) —"**; chỉ gửi `error_category_id` khi nhân viên chủ động chọn | E2E #11b: phiếu tạo từ UI có `error_category_id = null` |
| AUD-15 | Bảng sản phẩm thêm cột Thao tác với **Sửa** (dùng lại modal) và **Xóa** (modal xác nhận + hiển thị đúng thông báo 409) | E2E #9/#9b (tạo/sửa); xóa khi còn thiết bị trả 409 theo đúng logic backend |
| AUD-16 | Thêm **modal xác nhận dùng chung** `#action-modal`: xác nhận xóa, ghi chú chuyển trạng thái, **lý do từ chối (bắt buộc)**; đóng bằng `Esc` | Kiểm tra tĩnh: không còn lời gọi `confirm()/prompt()`; E2E #13/#16 gửi đúng payload |
| AUD-17 | Mọi bảng có 3 trạng thái: "Đang tải dữ liệu…" (spinner) / "Chưa có …" / có dữ liệu; lỗi API hiện toast tiếng Việt thay vì im lặng | Kiểm tra tĩnh: 6 bảng đều gọi `setTableLoading`/`setTableMessage` |
| AUD-18 | Viết lại `app.js` với **1 điểm khởi tạo** (`DOMContentLoaded → init`); không còn hàm định nghĩa trùng | Kiểm tra tĩnh: "hàm định nghĩa trùng lặp: không" |
| AUD-19 | Nút "Chọn nhanh thiết bị" lấy từ `GET /api/v1/product-instances/` và tự tính "(còn hạn)/(hết hạn)" theo ngày hôm nay; bỏ mọi số ngày ghi cứng | Kiểm tra tĩnh: không còn `495 ngày`/`980 ngày` |
| AUD-28 | Thêm ô "Nhập mã phiếu" + nút **"Tra cứu mã"** gọi `GET /warranty-tickets/code/{code}` và mở chi tiết | E2E #17 (thấy 200) và #17b (không tồn tại → 404 có thông báo tiếng Việt) |

---

## 3. File đã sửa

| File | Số dòng trước → sau | Nội dung thay đổi |
|---|---|---|
| `frontend/index.html` | 803 → 760 | Cấu trúc lại thành 6 tab nghiệp vụ; dashboard số liệu thật; tách bảng Khách hàng / Sản phẩm / Thiết bị; gộp form Tiếp nhận vào tab Phiếu bảo hành; thêm modal Khách hàng / Sản phẩm / Thiết bị / Xác nhận thao tác; thêm tab Phân tích lỗi; chuyển "Kiểm tra hạn bảo hành" thành công cụ phụ trong tab Thiết bị; bỏ header kỹ thuật |
| `frontend/app.js` | 1283 → 1741 | Viết lại theo mô-đun: `apiFetch` + bảng ánh xạ lỗi; tiện ích UI dùng chung (toast/loading/empty/escape/format/trạng thái tiếng Việt); 6 màn hình + 4 modal; validation; CRUD đầy đủ khách hàng/sản phẩm/thiết bị; modal xác nhận thay `prompt/confirm`; tab Phân tích lỗi có lịch sử phân tích |
| `frontend/styles.css` | 210 → 233 | Thêm bộ class dùng chung: `.btn/.btn-primary/.btn-secondary/.btn-danger/.btn-success/.btn-warning/.btn-sm`, `.table-th/.table-td/.table-row/.table-msg`, `.chip`, `.form-label/.form-error`, `.nav-tab-btn` |
| `frontend/README.md` | 29 → 51 | Cập nhật bảng 6 tab + API tương ứng, nguyên tắc dữ liệu, cách hiển thị lỗi, lưu ý kỹ thuật |

**Không file backend nào bị sửa** (đã đối chiếu timestamp: `backend/**` giữ nguyên từ Đợt 1).
Bản gốc frontend trước khi sửa được sao lưu **ngoài repository** tại `d:\Nhom06\frontend_backup_truoc_dot2\`.

---

## 4. Chức năng CRUD đã kiểm tra

| Đối tượng | Create | Read | Update | Delete | Bằng chứng E2E |
|---|---|---|---|---|---|
| **Khách hàng** | ✅ UI + API | ✅ danh sách + tìm kiếm | ✅ modal Sửa | ✅ modal Xóa (409 khi còn thiết bị/phiếu) | #1 → #6 (tạo → reload còn dữ liệu → sửa → reload thấy dữ liệu mới), #7–#8, #19 |
| **Sản phẩm** | ✅ | ✅ + tìm kiếm | ✅ (modal dùng lại) | ✅ (409 khi còn thiết bị) | #9, #9b |
| **Thiết bị** | ✅ gắn khách hàng + sản phẩm thật, ngày hết hạn tự tính | ✅ + tìm kiếm theo serial/tên | ✅ đầy đủ trường | ✅ (409 khi có phiếu) | #10, #10b, #10c, #10d, #19b |
| **Phiếu bảo hành** | ✅ form Tiếp nhận có kiểm tra điều kiện trước | ✅ danh sách / lọc / tra cứu mã / chi tiết | ✅ chuyển trạng thái theo đúng quy trình | ⛔ không có API xóa (đúng thiết kế – không thêm) | #11, #12, #13, #14, #17 |
| **Phân tích lỗi (AI)** | ✅ gọi phân tích | ✅ kết quả + lịch sử | ✅ duyệt / từ chối (human-in-the-loop) | – | #15, #15b–#15e, #16, #16b–#16d |

Luồng **UI → API → Service → Database → API → UI** đã được kiểm chứng bằng thao tác thật
(tạo rồi *reload* bằng request mới để chắc chắn dữ liệu nằm trong DB, không phải chỉ đổi giao diện).

---

## 5. Chức năng còn CHƯA hoàn thiện (ghi nhận trung thực)

| # | Hạng mục | Lý do / đề xuất |
|---|---|---|
| 5.1 | **Không có đăng nhập / phân quyền thật** | Ngoài phạm vi môn học. Hiện người dùng **chọn tay** "Người tiếp nhận"/"Người thực hiện"/"Người xét duyệt" từ danh sách thật (`/api/v1/ai/demo/users`). Backend vẫn kiểm tra vai trò khi duyệt AI (TECHNICIAN → 403). |
| 5.2 | `service_center_id` vẫn gửi cố định `1` khi tạo phiếu | Hệ thống chỉ có 1 trung tâm và **không có API liệt kê** trung tâm bảo hành → không thể nạp động mà không thêm endpoint. Backend đã validate tồn tại (Đợt 1: AUD-06). Đề xuất Đợt 3 nếu cần. |
| 5.3 | Khi Sửa thiết bị mà giữ nguyên tên sản phẩm, ô "Thương hiệu"/"Ngành hàng" không được gửi lên | Cố ý: các trường này thuộc **model sản phẩm dùng chung**, sửa ở đây sẽ đổi cho mọi thiết bị cùng model. Muốn sửa thì dùng màn hình **Sản phẩm** (đã có nút Sửa). |
| 5.4 | Validation phía backend còn hở (AUD-07/08/09) | Frontend đã chặn trước (email/SĐT/tên/số tháng/mô tả), nhưng gọi API trực tiếp vẫn lọt → **Đợt 3**. |
| 5.5 | Chưa phân trang danh sách | Giới hạn `limit=200` (thiết bị) / `100` (phiếu) — đủ cho quy mô môn học. Không mở rộng. |
| 5.6 | Danh mục lỗi chưa có CRUD | Ngoài phạm vi hiện tại (đã kết luận ở audit mục 9: không nên thêm). |
| 5.7 | Phụ thuộc CDN (Tailwind/Lucide/Chart.js) | Nếu mất internet: biểu đồ tự bỏ qua (đã guard `typeof Chart`), các bảng và CRUD vẫn hoạt động. |
| 5.8 | Không có màn hình quản lý trạng thái thiết bị theo hạn bảo hành | Cột `status` vẫn do người dùng chọn (`Đang hoạt động` / `Ngừng theo dõi`), chưa tự đồng bộ theo `warranty_end_date` → **Đợt 3** nếu muốn (cần thống nhất nghiệp vụ). |

---

## 6. Dữ liệu hard-code đã xử lý

| # | Hard-code trước Đợt 2 | Sau Đợt 2 |
|---|---|---|
| 1 | Dropdown khách hàng ở form Tiếp nhận: 3 `<option>` viết cứng, **sai SĐT cả 3** | Nạp từ `GET /api/v1/customers/`, hiển thị `Họ tên – Số điện thoại` thật |
| 2 | Ngày `2026-09-07` (input + query string + fallback) | `todayISO()` — ô "Ngày kiểm tra" mặc định là ngày hôm nay; pre-check **không** truyền `check_date` |
| 3 | `DEFAULT_STAFF_ID = 2`, `created_by: 2`, `changed_by: 2` | Ô chọn "Người tiếp nhận"/"Người thực hiện" nạp từ `GET /api/v1/ai/demo/users` |
| 4 | Mảng `samples` 4 serial viết cứng trong `renderDemoButtons` (API `demo_instances` bị bỏ qua) | Nút chọn nhanh lấy từ `GET /api/v1/product-instances/` + tự tính "(còn hạn)/(hết hạn)" |
| 5 | Nhãn "Còn hạn 495 ngày"/"Quá hạn 980 ngày" ghi cứng | Bỏ số ngày; trạng thái tính động từ `warranty_end_date` so với ngày hôm nay |
| 6 | `error_category_id` mặc định `1` khi tạo phiếu | Mặc định **"Chưa phân loại (để AI gợi ý)"** — chỉ gửi khi nhân viên chọn |
| 7 | Thống kê Dashboard: 2 thẻ `#stat-products`/`#stat-customers` không tồn tại + biểu đồ chết | 6 thẻ số liệu thật từ `stats/summary` + biểu đồ donut vẽ được + chip số theo trạng thái |
| 8 | Nút "Thử nhảy cóc trái phép" hiển thị cho mọi người dùng | Đã bỏ khỏi giao diện (nghiệp vụ chặn vẫn kiểm chứng được qua API và qua nút hợp lệ) |
| 9 | Link "Swagger Docs", badge "FastAPI Online"/"KT2 + KT3 LIVE" | Đã bỏ khỏi giao diện người dùng |
| 10 | `service_center_id: 1` | **Còn** (ghi nhận ở mục 5.2 — không có API liệt kê trung tâm; backend đã validate tồn tại) |

---

## 7. Các tên giao diện đã đổi

| Trước | Sau |
|---|---|
| Tab "Tổng Quan" | **Tổng quan** |
| Tab "Tiếp Nhận (BR1-4)" | (gộp vào) **Phiếu bảo hành** → khối "Tiếp nhận thiết bị & tạo phiếu bảo hành" |
| Tab "Quản Lý Phiếu (State)" | **Phiếu bảo hành** |
| Tab "Kiểm Tra Bảo Hành" (Debug & … BR2, code endpoint…) | Công cụ phụ **"Kiểm tra hạn bảo hành"** (nằm trong tab Thiết bị) |
| Tab "Sản Phẩm & Khách" | Tách thành **Khách hàng** và **Sản phẩm**; thêm **Thiết bị** |
| (không có) | **Phân tích lỗi** |
| "Quản Lý Sản Phẩm - Product Instance (Theo Serial)" | **Thiết bị đã đăng ký** |
| "Danh Mục Model Sản Phẩm (Products)" | **Danh mục sản phẩm** |
| "Danh Sách Khách Hàng (Customers)" | **Danh sách khách hàng** |
| "Serial Number", "Customer", "Ngày đăng ký" | **Số serial**, **Khách hàng**, **Ngày mua**, **Hết hạn bảo hành** |
| "Demo Buttons", "Chọn nhanh Serial mẫu để thử nghiệm quy tắc" | **Chọn nhanh thiết bị đang có trong hệ thống** |
| `RECEIVED / INSPECTING / REPAIRING / COMPLETED / REJECTED` | **Đã tiếp nhận / Đang kiểm tra / Đang sửa chữa / Hoàn tất / Từ chối bảo hành** (mã gốc vẫn giữ trong API, tài liệu và minh chứng) |
| `PENDING / APPROVED / REJECTED` (duyệt AI) | **Chờ duyệt / Đã duyệt / Đã từ chối** |
| "AI-01: Gợi Ý Phân Loại Lỗi Bảo Hành" + badge "KT3 • AI CHỈ ĐỀ XUẤT" | **Kết quả phân tích lỗi** + câu giải thích "nhãn chỉ được ghi khi nhân viên duyệt" |
| "Quy Tắc Nghiệp Vụ Core (BR1 - BR5)" | **Quy tắc nghiệp vụ & quy trình xử lý phiếu** (khối thu gọn, diễn giải tiếng Việt) |
| `error_category_id`, `ai_result_id`, "Confidence", "provider", "ticket_status_history" | **Nhãn lỗi hiện tại của phiếu / Mã kết quả / Độ tin cậy / Thời điểm / Lịch sử xử lý** |
| "Chạy Debug Trace", "Console" | **Kiểm tra**, **Chi tiết kỹ thuật từng bước đối chiếu** (thu gọn) |
| Nút "Xử lý →", "Create", "Submit" | **Xem & xử lý / Thêm … / Lưu / Huỷ / Sửa / Xóa / Kiểm tra / Phân tích lỗi / Duyệt / Từ chối** |

---

## 8. UX đã cải thiện

| # | Hạng mục | Trước | Sau |
|---|---|---|---|
| 8.1 | **Loading** | Chỉ bảng phiếu & bảng thiết bị có "Đang tải…" | **Mọi bảng** đều có dòng "Đang tải dữ liệu…" + spinner (6 bảng) |
| 8.2 | **Empty state** | Bảng Model/Khách trắng trơn khi rỗng | "Chưa có khách hàng nào trong hệ thống." / "Chưa có sản phẩm nào trong danh mục." / "Chưa có thiết bị nào được đăng ký." / "Chưa có phiếu bảo hành nào phù hợp." |
| 8.3 | **Tìm kiếm không kết quả** | Không có thông báo | "Không tìm thấy … khớp với "<từ khoá>"." |
| 8.4 | **Error handling** | Mọi lỗi → "Lỗi kết nối máy chủ!" | Ánh xạ theo mã: 400/403/404/**409**/422/5xx với câu tiếng Việt riêng; lỗi 409 hiển thị **nguyên văn lý do nghiệp vụ** của backend (ví dụ "Khách hàng đang có 10 thiết bị / 10 phiếu bảo hành nên không thể xóa…") |
| 8.5 | **Success** | Toast chung | Toast nêu rõ đối tượng: "Đã thêm khách hàng "X"."; "Đã tạo phiếu bảo hành **TK-…** ở trạng thái "Đã tiếp nhận"." |
| 8.6 | **Xác nhận xóa** | `confirm()` thô của trình duyệt | Modal nội bộ: "Bạn có chắc muốn xóa …?" + cảnh báo "… đang có thiết bị hoặc phiếu bảo hành sẽ không thể xóa." |
| 8.7 | **Chuyển trạng thái** | `prompt()` ghi chú (và `prompt` thứ hai cho lý do từ chối) | Modal nội bộ: ghi chú xử lý; riêng **từ chối bảo hành bắt buộc nhập lý do** (không thể bấm xác nhận khi trống) |
| 8.8 | **Chi tiết phiếu** | Không có thông tin thiết bị/khách | Bổ sung 4 khối thông tin thật + người tiếp nhận (tên thật) + lý do từ chối + lịch sử xử lý có tên người thực hiện |
| 8.9 | **Điều hướng** | 5 tab trộn kỹ thuật/nghiệp vụ | **6 tab nghiệp vụ**; nút "Tiếp nhận máy mới" ở header đưa thẳng tới form |
| 8.10 | **Lọc trạng thái** | Nút không thể hiện trạng thái đang chọn | Nút đang chọn chuyển sang màu chính (active state rõ ràng) |
| 8.11 | **Esc để đóng modal** | Không hỗ trợ | Tất cả 5 modal đóng được bằng `Esc` |
| 8.12 | **Tra cứu nhanh** | Không có | Ô nhập mã phiếu + nút "Tra cứu mã"; nút "Chọn nhanh thiết bị" ở form Tiếp nhận và ở công cụ kiểm tra |
| 8.13 | **Nhất quán** | Nhiều kiểu nút/bảng/cỡ chữ khác nhau | Bộ class dùng chung trong `styles.css`; cùng spacing, cùng kiểu bảng, cùng cỡ chữ |

---

## 9. Validation đã thêm (phía giao diện)

| Form | Trường | Quy tắc | Thông báo lỗi |
|---|---|---|---|
| **Khách hàng** | Họ và tên | bắt buộc, ≥ 2 ký tự | "Vui lòng nhập họ và tên khách hàng." / "Họ và tên quá ngắn." |
| | Số điện thoại | bắt buộc, `^(0|\+84)\d{8,10}$` (bỏ khoảng trắng/`.`/`-`) | "Số điện thoại không hợp lệ (ví dụ: 0912345678)." |
| | Email | tuỳ chọn, nhưng nếu nhập phải đúng định dạng | "Email không hợp lệ (ví dụ: an.nguyen@gmail.com)." |
| **Sản phẩm** | Tên sản phẩm | bắt buộc, không chỉ khoảng trắng | "Vui lòng nhập tên sản phẩm." |
| | Thời hạn bảo hành | bắt buộc, 1–120 tháng | "Thời hạn bảo hành phải từ 1 đến 120 tháng." |
| **Thiết bị** | Số serial | bắt buộc | "Vui lòng nhập số serial." |
| | Khách hàng | bắt buộc, **chọn từ danh sách thật** | "Vui lòng chọn khách hàng (chủ sở hữu)." |
| | Tên sản phẩm | bắt buộc; khớp danh mục thì gửi `product_id`, chưa có thì tạo mới | "Vui lòng chọn hoặc nhập tên sản phẩm." |
| | Ngày mua | bắt buộc; ngày hết hạn **tự tính** (chỉ đọc) | "Vui lòng chọn ngày mua." |
| | Thời hạn bảo hành | tuỳ chọn, 1–120 tháng | "Thời hạn bảo hành phải từ 1 đến 120 tháng." |
| **Phiếu bảo hành** | Số serial | bắt buộc + **kiểm tra điều kiện bảo hành** trước khi cho gửi | "Vui lòng nhập số serial thiết bị." / "Số serial không tồn tại trong hệ thống…" / "Thiết bị đã hết hạn bảo hành" |
| | Khách hàng | bắt buộc | "Vui lòng chọn khách hàng (chủ sở hữu thiết bị)." |
| | Mô tả lỗi | bắt buộc, ≥ 5 ký tự | "Vui lòng nhập mô tả tình trạng lỗi." / "Mô tả lỗi quá ngắn…" |
| | Người tiếp nhận | bắt buộc | "Vui lòng chọn người tiếp nhận." |
| **Chuyển trạng thái** | Lý do từ chối | bắt buộc khi REJECTED | "Vui lòng nhập nội dung trước khi xác nhận." |
| | Người thực hiện | bắt buộc | "Vui lòng chọn người thực hiện." |

> Validation **chỉ ở giao diện** — **không** thay đổi business rules: backend vẫn là nơi quyết định cuối cùng
> (BR1–BR4, State Machine, FK, quyền duyệt AI). Nếu dữ liệu vượt qua frontend, backend vẫn chặn và frontend hiển thị đúng lỗi.

---

## 10. API integration đã kiểm tra

| Màn hình / thao tác | Endpoint (không đổi so với backend hiện có) | Trạng thái |
|---|---|---|
| Tổng quan – số liệu + biểu đồ | `GET /api/v1/warranty-tickets/stats/summary` | ✅ dùng đủ 9 trường |
| Tổng quan – phiếu mới nhất | `GET /api/v1/warranty-tickets/?limit=5` | ✅ |
| Khách hàng – danh sách/thêm/sửa/xóa | `GET/POST /api/v1/customers/`, `PUT/DELETE /api/v1/customers/{id}` | ✅ |
| Sản phẩm – danh sách/thêm/sửa/xóa | `GET/POST /api/v1/products/`, `PUT/DELETE /api/v1/products/{id}` | ✅ |
| Thiết bị – danh sách/tìm/chi tiết/thêm/sửa/xóa | `GET/POST /api/v1/product-instances/`, `GET/PUT/DELETE /api/v1/product-instances/{id}` | ✅ |
| Thiết bị – kiểm tra hạn (công cụ phụ) | `POST /api/v1/debug/check-warranty` | ✅ (mặc định ngày hôm nay) |
| Phiếu – kiểm tra trước khi tạo | `GET /api/v1/debug/check-serial/{serial}` | ✅ (không truyền `check_date`) |
| Phiếu – tạo mới | `POST /api/v1/warranty-tickets/` | ✅ (gửi `serial_number`, `customer_id`, `service_center_id`, `created_by`, `issue_description`, `error_category_id?`) |
| Phiếu – danh sách + lọc | `GET /api/v1/warranty-tickets/?status=` | ✅ |
| Phiếu – chi tiết | `GET /api/v1/warranty-tickets/{id}` | ✅ (đọc cả `serial_number/product_name/customer_name/warranty_end_date/status_history`) |
| Phiếu – tra cứu theo mã | `GET /api/v1/warranty-tickets/code/{code}` | ✅ (mới đưa lên UI) |
| Phiếu – chuyển trạng thái | `PATCH /api/v1/warranty-tickets/{id}/status` | ✅ (`new_status`, `changed_by`, `note`, `rejection_reason`) |
| Danh mục lỗi | `GET /api/v1/warranty-tickets/meta/demo-data` | ✅ |
| Người dùng hệ thống | `GET /api/v1/ai/demo/users` | ✅ (dùng cho 3 ô chọn người) |
| Phân tích lỗi | `POST /api/v1/ai/tickets/{id}/classify-error` | ✅ |
| Duyệt kết quả | `PATCH /api/v1/ai/results/{id}/review` | ✅ |
| Lịch sử phân tích | `GET /api/v1/ai/tickets/{id}/results` | ✅ (đọc `output_data`) |

**Không có API giả, không có endpoint mới được thêm.** Tất cả dữ liệu hiển thị đều đến từ backend/DB.

---

## 11. Kết quả END-TO-END (server thật, cổng 8013)

Kịch bản `verify_dot2_e2e.py` mô phỏng đúng chuỗi request mà giao diện gọi cho từng thao tác UI:

```
0.  GET /  → 200 ; trang có đủ 6 tab nghiệp vụ ; không còn "Debug"/"Swagger"/"KT2-KT3"   PASS
0e. GET /static/app.js → 200 ; có init + 6 loader ; không còn confirm()/prompt()          PASS
0h. GET /static/styles.css → 200 ; có .btn/.table-th                                       PASS
1-6. Thêm khách hàng → reload còn dữ liệu → sửa → reload thấy dữ liệu mới                  PASS
7-8. Xóa khách hàng đang có thiết bị → 409 + lý do tiếng Việt                              PASS
9.   Tạo sản phẩm → 201 ; sửa sản phẩm → 200                                                PASS
10.  Tạo thiết bị (khách + sản phẩm thật) → 201 ; ngày hết hạn tự tính 2028-03-01           PASS
10e. Chặn tạo thiết bị với khách hàng không tồn tại → 404                                    PASS
10f. Chặn tạo thiết bị với sản phẩm không tồn tại → 404                                      PASS
11.  Kiểm tra điều kiện bảo hành (CÒN HẠN) → tạo phiếu 201, error_category_id = null        PASS
12.  Chi tiết phiếu có Serial/Sản phẩm/Khách hàng đúng                                     PASS
13.  Chuyển trạng thái → Đang kiểm tra (200) ; reload thấy INSPECTING                       PASS
14b. Lịch sử ghi đúng người thực hiện theo lựa chọn trên UI                                  PASS
14c. State machine vẫn chặn nhảy cóc (400)                                                  PASS
15.  Phân tích lỗi → nhãn "Loi man hinh hien thi" (conf 0.95) ; lịch sử PENDING              PASS
15c. AI KHÔNG tự ghi nhãn vào phiếu ; trạng thái phiếu không đổi                             PASS
16.  Duyệt nhãn (receptionist) → nhãn được ghi vào phiếu ; trạng thái vẫn không đổi           PASS
16d. Kỹ thuật viên bị chặn duyệt (403)                                                      PASS
17.  Tra cứu phiếu theo mã → 200 ; mã sai → 404 có thông báo                                 PASS
18.  Số liệu tổng quan đủ trường cho dashboard (không cần API thống kê mới)                   PASS
19.  Xóa thiết bị đang có phiếu → 409 (chặn đúng thiết kế, giữ toàn vẹn)                      PASS

  TONG KET E2E: 46 PASS | 0 FAIL
```

Ngoài ra đã kiểm tra **tĩnh** (script `check_frontend_ids.py`):
- 92 id mà JS tham chiếu ↔ 119 id trong HTML: **không lệch một id nào** (không có `getElementById` trả `null`).
- Mọi hàm gọi từ `onclick/onsubmit` trong HTML đều **tồn tại** trong `app.js`.
- **Không còn hàm định nghĩa trùng lặp** (dead code đã bị loại).
- `node --check app.js` → **cú pháp hợp lệ**.
- Không còn `2026-09-07`, `0901234567`, `0923456789`, `495 ngày`, `980 ngày`, `DEFAULT_STAFF_ID`.

---

## 12. Kết quả `.\dev.ps1 check` (regression)

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

- **KT2: 12/12 PASS** · **KT3: 12/12 PASS** · **Tổng: 24/24 PASS**
- Đã chạy `.\dev.ps1 check` **4 lần** trong đợt này (sau mỗi cụm thay đổi lớn + lần cuối sau khi viết tài liệu) — tất cả đều 24/24.
- **Không sửa** `tests/test_scenarios.py`, `tests/seed_data.py`, `tests/init_db.py` (giữ nguyên 100%).

---

## 13. Các vấn đề còn lại — **Phát hiện để Đợt 3** (KHÔNG tự sửa)

| # | Phát hiện | Loại | Đề xuất |
|---|---|---|---|
| P3.1 | **AUD-07** – backend vẫn nhận `email="khong-phai-email"`, `full_name="   "`, `phone="   "` (201) | Validation backend | Dùng `EmailStr`, strip + `min_length`, `pattern` cho phone trong `schemas.py`. **Bắt buộc chạy lại check** vì đang chạm dữ liệu seed. |
| P3.2 | **AUD-08** – backend vẫn nhận `name=""` / `name="   "` cho sản phẩm (201) | Validation backend | Thêm validator strip + `min_length=1`. |
| P3.3 | **AUD-09** – backend vẫn nhận `issue_description="    "` (201) | Validation backend | Validator strip + `min_length` cho `issue_description`. |
| P3.4 | **AUD-25** – `?status=SAI` trả 200 rỗng; `?limit=999999` không giới hạn | Validation API | `Literal[...]`/enum cho `status`, `Query(..., le=500)` cho `limit`. |
| P3.5 | **AUD-22** – dữ liệu seed **không dấu** (`Nguyen Van An`, `Dien thoai Samsung…`) trong khi UI có dấu | Chất lượng dữ liệu | Việt hoá `seed_data.py`. **Lưu ý:** minh chứng #2/#3 đang so khớp tên khách/model cụ thể → phải chạy `check` ngay sau khi sửa. |
| P3.6 | **AUD-23** – AI mock bỏ trống nhãn với mô tả "không lên nguồn, đèn báo nhấp nháy" (0.35, lý do "nhiều nhóm lỗi") | Chất lượng AI | Tinh chỉnh trọng số từ khoá trong `MockAIProvider` (chỉ dữ liệu, **không** đổi prompt/guardrail/ngưỡng). |
| P3.7 | **AUD-21** – khái niệm "BR5" có trong code/thông báo nhưng không có trong đặc tả BR1–BR4 | Nhất quán thuật ngữ | Chọn 1 hướng (bổ sung BR5 vào tài liệu **hoặc** đổi thông báo), không đổi logic chặn. |
| P3.8 | **AUD-26** – `Makefile` target `evidence` dùng `Out-File` (PowerShell) → không chạy trên bash | Công cụ | Đổi sang `tee`, hoặc ghi chú rõ Makefile chỉ dành cho bash. |
| P3.9 | **AUD-27** – cổng `check` **không** bao phủ: `DELETE /customers`, validation khoảng trắng, và toàn bộ giao diện | Kiểm thử | Thêm **minh chứng mới** (không sửa 24 minh chứng cũ) + tuỳ chọn test tĩnh cho `app.js`. |
| P3.10 | Không có API liệt kê **trung tâm bảo hành** → frontend phải gửi `service_center_id = 1` | API nhỏ | Chỉ thêm nếu thật cần: `GET /api/v1/service-centers/` (rất nhỏ). |
| P3.11 | Không có API **danh mục lỗi** dạng CRUD (chỉ đọc qua `meta/demo-data`) | Phạm vi | Đã kết luận **không nên thêm** (ngoài phạm vi môn học). |
| P3.12 | Trạng thái thiết bị (`ACTIVE/EXPIRED`) do người dùng chọn tay, không đồng bộ theo `warranty_end_date` | Nghiệp vụ | Cần thống nhất yêu cầu trước khi tự động hoá (ví dụ job cập nhật hoặc tính động khi hiển thị). |
| P3.13 | Sửa thiết bị **không** cập nhật thương hiệu/ngành hàng của model | UX nhỏ | Cố ý (tránh đổi ảnh hưởng nhiều thiết bị). Nếu muốn cho phép, cần thông báo rõ "sửa áp dụng cho cả model". |
| P3.14 | Chưa có phân trang; giới hạn cứng `limit=100/200` | Hiệu năng | Chỉ cần khi dữ liệu lớn hơn quy mô môn học. |
| P3.15 | Không có đăng nhập/phân quyền thật | Ngoài phạm vi | Đã ghi nhận; hiện dùng chọn tay + backend kiểm tra vai trò khi duyệt AI. |

---

## PHỤ LỤC — Tình trạng repository sau Đợt 2

| Hạng mục | Trạng thái |
|---|---|
| Backend (`backend/**`) | **Không thay đổi** trong đợt này (giữ nguyên các sửa của Đợt 1: AUD-01, AUD-24, AUD-06, AUD-10) |
| Frontend đã sửa | `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`, `frontend/README.md` |
| Tài liệu thêm mới | `docs/BAO_CAO_DOT_2_FRONTEND.md` (báo cáo này) |
| Test | Không sửa (`tests/**` giữ nguyên) |
| CSDL | Đã chạy `.\dev.ps1 check` lần cuối → DB ở trạng thái seed chuẩn, dữ liệu test của quá trình kiểm thử đã được dọn |
| File tạm | Log server đã xoá; script kiểm thử/đối chiếu đặt **ngoài** repository (`d:\Nhom06\verify_dot2_e2e.py`, `check_frontend_ids.py`); bản gốc frontend ở `d:\Nhom06\frontend_backup_truoc_dot2\` |
| Minh chứng KT2/KT3 | **24/24 PASS** |

**Kết luận:** mục tiêu "ít chức năng hơn – dễ hiểu hơn – dữ liệu thật – chức năng chạy đúng – giao diện thống nhất – 24/24 minh chứng PASS" đã đạt,
trong khi **không** mở rộng phạm vi (không chatbot/RAG/LangGraph/module mới), **không** sửa backend, **không** sửa test và **không** đổi nghiệp vụ BR1–BR4 / State Machine / AI-01.






