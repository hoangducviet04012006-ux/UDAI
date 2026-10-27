# frontend/ — Giao diện web BaoHanhAI

Giao diện là **HTML/CSS/JS thuần**, được backend FastAPI phục vụ trực tiếp (không cần build, không cần npm):

| Đường dẫn | File |
|---|---|
| `http://127.0.0.1:8000/` | `frontend/index.html` |
| `http://127.0.0.1:8000/static/app.js` | `frontend/app.js` |
| `http://127.0.0.1:8000/static/styles.css` | `frontend/styles.css` |

Backend mount thư mục này qua biến `STATIC_DIR` trong `backend/app/main.py`
(đang trỏ `<root>/frontend`) và trả `index.html` cho route `/`.

## Các màn hình (8 tab theo vai trò)

> **Menu theo vai trò (backend quyết định):** `GET /api/v1/auth/me` trả `menus` kèm mỗi phiên;
> `app.js` chỉ vẽ lại danh sách đó. Kỹ thuật viên có 4 mục việc hằng ngày (*Tổng quan · Phiếu bảo hành ·
> Tra cứu bảo hành · Hỗ trợ xác định lỗi*), còn *Khách hàng · Danh mục máy · Máy đã đăng ký* được gom vào
> dropdown **"Tra cứu nội bộ"**. Quản lý thấy thêm *Tài khoản nhân viên*.

| Tab | Nội dung | API sử dụng |
|---|---|---|
| **Tổng quan** | **Bảng điều khiển theo vai trò**: tiêu đề + chip vai trò/phạm vi, "Việc thường làm" (thao tác nhanh theo vai trò + ghi chú nghiệp vụ), thẻ số liệu động, **Công việc theo bước** (mỗi phiếu 1 nút hành động), **Việc cần chú ý** + biểu đồ (Quản lý), **Việc cần làm ngay**, bảng phiếu `[Việc của tôi]`/`[Toàn bộ phiếu]` (`[Toàn bộ hệ thống]`/`[Việc cần chú ý]` với Quản lý) | `GET /api/v1/warranty-tickets/workboard` (`?scope=MINE|ALL`) |
| **Tra cứu bảo hành** | Một ô nhập duy nhất: **số sê-ri** hoặc **mã phiếu** → card kết quả (sản phẩm, hãng, số sê-ri, khách hàng, ngày mua, hạn bảo hành, **tình trạng bảo hành**, phiếu gần nhất) + nút dẫn tiếp (tạo phiếu, đối chiếu điều kiện bảo hành) | `GET /api/v1/product-instances/by-serial/{serial}`, `GET /api/v1/warranty-tickets/code/{code}`, `POST /api/v1/debug/check-warranty` |
| **Khách hàng** | Danh sách kèm **số thiết bị / số phiếu**, tìm kiếm, **chi tiết khách** (thiết bị + phiếu của khách), Thêm/Sửa/Xóa | `GET/POST/PUT/DELETE /api/v1/customers`, `/api/v1/product-instances`, `/api/v1/warranty-tickets` |
| **Sản phẩm** | Danh mục sản phẩm kèm **số thiết bị đang quản lý**, tìm kiếm, Thêm/Sửa/Xóa | `GET/POST/PUT/DELETE /api/v1/products` |
| **Thiết bị** | Thiết bị theo số sê-ri (gắn khách hàng + sản phẩm), **tình trạng bảo hành** tính theo hạn, **chi tiết thiết bị**, **kiểm tra bảo hành theo từng dòng**, Thêm/Sửa/Xóa | `/api/v1/product-instances`, `POST /api/v1/debug/check-warranty` |
| **Phiếu bảo hành** | **Tiếp nhận máy mới dạng wizard 2 bước** (tra số sê-ri → đăng ký thiết bị nếu chưa có → xác nhận + mô tả lỗi → tạo phiếu), danh sách + lọc trạng thái, tìm theo **mã phiếu / số sê-ri / khách hàng / số điện thoại**, nút **Phiếu của tôi**, **MỘT màn hình xử lý phiếu** (A–G + nút hành động theo quyền + tiến trình 5 bước + lịch sử) | `/api/v1/warranty-tickets` (kèm `?q=`, `?mine=1`), `/api/v1/warranty-tickets/{id}`, `/{id}/status`, `/{id}/diagnosis`, `/{id}/repair`, `/meta/workflow` |
| **Hỗ trợ xác định lỗi** | Chọn phiếu → **Gợi ý loại lỗi** (AI) → chọn người xác nhận → **Xác nhận loại lỗi / Không dùng gợi ý**, xem lịch sử gợi ý | `POST /api/v1/ai/tickets/{id}/classify-error`, `PATCH /api/v1/ai/results/{id}/review`, `GET /api/v1/ai/tickets/{id}/results`, `GET /api/v1/ai/demo/users` |

Nút **Tra cứu bảo hành** ở tab *Thiết bị* chỉ chuyển sang tab Tra cứu — không còn công cụ kiểm tra
trùng lặp với 2 kết quả khác nhau. Việc kiểm tra điều kiện bảo hành (KT2) được truy cập từ
tab Tra cứu và từ **chi tiết thiết bị**.

## Nguyên tắc dữ liệu (Đợt 2)

- **Không hard-code dữ liệu nghiệp vụ**: danh sách khách hàng, sản phẩm, thiết bị, danh mục lỗi,
  người dùng hệ thống và số liệu tổng quan đều nạp từ API.
- **Không cố định ngày demo**: ô "Ngày kiểm tra" mặc định là **ngày hôm nay** (tính bằng JS);
  phần kiểm tra trước khi tạo phiếu gọi API **không truyền `check_date`** để khớp đúng điều kiện khi lưu phiếu.
- **Không dùng `confirm()`/`prompt()`** của trình duyệt: mọi xác nhận xóa và ghi chú/lý do
  chuyển trạng thái đều dùng modal nội bộ (`#action-modal`).
  Modal này hỗ trợ **nhiều trường nghiệp vụ** (`fields`) — ví dụ bước "Sửa xong – Chờ trả máy" hỏi
  *nội dung đã sửa*, *linh kiện thay thế*, *ghi chú kỹ thuật*; bước "Xác nhận đã trả máy" hỏi
  *thông tin bàn giao*. Backend vẫn kiểm tra lại toàn bộ (bỏ trống thông tin bắt buộc → 400 kèm câu tiếng Việt).
- **Nút hành động do backend quyết định**: màn hình phiếu chỉ vẽ nút từ `available_actions` mà API trả về
  (đã lọc theo quyền của tài khoản đang đăng nhập); những bước không thuộc vai trò hiện tại được giải thích
  ở khối ghi chú thay vì hiện nút rồi báo lỗi.
- **Hiển thị lỗi theo đúng bản chất**: 400 (yêu cầu không hợp lệ), 403 (không có quyền),
  404 (không tìm thấy), 409 (xung đột dữ liệu – ví dụ khách hàng còn thiết bị), 422 (dữ liệu nhập sai),
  5xx (lỗi hệ thống). Không gộp mọi lỗi thành "Lỗi kết nối máy chủ".

## Ngôn ngữ hiển thị (Đợt 3 — lớp hiển thị tiếng Việt)

Giao diện dành cho nhân viên bảo hành **không hiển thị mã kỹ thuật**. Toàn bộ việc dịch/mã hoá nằm ở
**lớp hiển thị trong `app.js`** — backend, CSDL và API **không đổi**:

| Nhóm dữ liệu | Trong CSDL / API | Hiển thị trên giao diện |
|---|---|---|
| Vai trò | `MANAGER` / `RECEPTIONIST` / `TECHNICIAN` | Quản lý / Nhân viên tiếp nhận / Kỹ thuật viên |
| Trạng thái phiếu | `RECEIVED` / `INSPECTING` / `REPAIRING` / `COMPLETED` / `REJECTED` | Đã tiếp nhận / Đang kiểm tra / Đang sửa chữa / Hoàn tất / Từ chối bảo hành |
| Trạng thái thiết bị | `ACTIVE` / `EXPIRED` | Đang hoạt động / Ngừng theo dõi |
| Duyệt gợi ý lỗi | `PENDING` / `APPROVED` / `REJECTED` | Chờ xác nhận / Đã xác nhận / Không dùng gợi ý này |
| Độ chắc chắn | `0.93` | `93%` |
| Nhóm lỗi của bộ phân loại | `DISPLAY`, `POWER_MAINBOARD`, … | màn hình hiển thị, nguồn / bo mạch, … |
| Tên dữ liệu mẫu không dấu | `Nguyen Van An`, `Loi man hinh hien thi`, … | Nguyễn Văn An, Lỗi màn hình hiển thị, … |
| Thẻ kỹ thuật trong thông báo | `[BR2 FAIL] …`, `[AI-01] …`, `(FK RESTRICT)` | Thông báo tiếng Việt tự nhiên (thẻ bị loại bỏ) |
| Trace đối chiếu bảo hành | `[Step 5] effective_end_date … -> True`, `BR2` | `[Bước 5] ngày hết hạn áp dụng … → Đạt`, "điều kiện bảo hành" |

Hàm tương ứng trong `app.js`: `displayText()`, `roleLabel()`, `deviceStatusLabel()`, `statusLabel()`,
`reviewLabel()`, `confidencePercent()`, `humanizeText()`, `humanizeTraceStep()`.

**Lưu ý quan trọng:** các ô nhập liệu và truy vấn vẫn dùng **giá trị gốc** trong CSDL
(ví dụ tên sản phẩm trong `datalist` giữ đúng tên gốc) để việc lưu/cập nhật khớp chính xác —
chỉ phần **hiển thị** (bảng, chi tiết, thông báo, nhãn `label` của datalist) mới được Việt hoá.

## Tái cấu trúc UX (Đợt 4)

Đợt 4 **chỉ thay đổi lớp giao diện** (`index.html`, `app.js`, `README.md`). Backend, CSDL, API,
`tests/**` và nghiệp vụ (BR1–BR4, máy trạng thái phiếu, AI-01 human-in-the-loop) **không đổi**.

| Nhóm | Nội dung đã làm |
|---|---|
| Điều hướng | Menu 7 mục, thêm tab **Tra cứu bảo hành** gộp 3 cửa vào cũ (tìm thiết bị / tra mã phiếu / kiểm tra hạn) thành **một ô nhập** |
| Tổng quan | Thêm **Thao tác nhanh** (4 việc thường làm + ô tra cứu nhanh), tách thẻ **Chờ tiếp nhận** (`stats.received`), bảng **Phiếu đang xử lý** (ưu tiên phiếu đang mở), hạ khối **Quy tắc nghiệp vụ** xuống cuối trang |
| Thiết bị | Bảng có cột **Tình trạng bảo hành**, nút **Chi tiết** (modal: thiết bị + khách hàng + phiếu), **kiểm tra bảo hành ngay trên từng dòng**, bỏ danh sách "chọn nhanh" trùng lặp |
| Phiếu bảo hành | **Wizard 2 bước**: (1) tra số sê-ri → có thì dùng ngay, chưa có thì đăng ký thiết bị mới; (2) xem lại thiết bị + nhập mô tả lỗi + người tiếp nhận → tạo phiếu. Chi tiết phiếu có **tiến trình 4 bước**, tên **nhân viên phụ trách**, ô tìm kiếm theo mã/sê-ri/khách |
| Khách hàng / Sản phẩm | Bổ sung cột **số thiết bị / số phiếu** (đếm từ dữ liệu API đang dùng), **chi tiết khách hàng**, bỏ cột mã kỹ thuật `#id`, tiêu đề modal đổi sang tên thật |
| Ngôn ngữ | Đồng nhất **"Số sê-ri"** toàn giao diện; tình trạng bảo hành luôn có **cả chữ lẫn màu** ("Còn bảo hành" / "Đã hết hạn" / "Không xác định") |
| Gợi ý lỗi | Modal phiếu hiển thị tóm tắt kết quả gợi ý + nút **Phân tích phiếu này** và **xác nhận ngay trong modal** (không mất ngữ cảnh phiếu đang xem) |

Ghi chú kiểm chứng: `node --check frontend/app.js` · kiểm tra ngôn ngữ/UI **49/49 PASS** ·
`.\dev.ps1 check` **24/24 PASS** · E2E chạy trên hệ thống thật.

## Màn hình công việc theo vai trò (Prompt 2)

Mục tiêu: sau khi đăng nhập, mỗi nhân viên **nhìn thấy đúng việc của mình** mà không phải mở từng menu.
Toàn bộ nội dung bảng điều khiển do backend trả về qua `GET /api/v1/warranty-tickets/workboard`;
giao diện không tự suy diễn trạng thái hay quyền.

| Hàm trong `app.js` | Việc |
|---|---|
| `loadDashboard(showToast, scope)` | Gọi `/workboard` (`?scope=MINE|ALL`) rồi vẽ lại toàn bộ bảng điều khiển |
| `renderDashHeader` / `renderDashQuickActions` / `renderDashNotes` | Tiêu đề theo vai trò, thao tác nhanh, ghi chú nghiệp vụ ("việc này của ai") |
| `renderDashCards` | Thẻ số liệu động; bấm thẻ có trạng thái ⇒ mở danh sách phiếu đã lọc |
| `renderWorkGroups` | Nhóm công việc + danh sách phiếu, mỗi phiếu 1 nút theo `action_kind` |
| `renderDashFocus` | "Việc cần làm ngay" — đã sắp theo thứ tự ưu tiên của vai trò |
| `renderDashAttention` | "Việc cần chú ý" (Quản lý) + lý do lấy từ dữ liệu thật |
| `renderDashTable` / `setDashView` / `renderDashViewButtons` | Bảng phiếu: `[Việc của tôi]`/`[Toàn bộ phiếu]` (Quản lý: `[Toàn bộ hệ thống]`/`[Việc cần chú ý]`) |
| `handleTicketAction(id, target)` | Mở thẳng phiếu; nếu là bước chuyển thì mở luôn hộp thoại xác nhận |
| `rowExtraActionsHtml` | Các bước phụ của một dòng nằm trong menu "Thêm" (mỗi dòng chỉ 1 nút chính) |
| `renderNavigation(menus)` / `toggleNavMore` | Vẽ menu theo vai trò; gom nhóm `reference` vào dropdown "Tra cứu nội bộ" |
| `renderDiagnosisSupport(t)` | Khối "Hỗ trợ chẩn đoán" 3 phần: khách mô tả / hệ thống gợi ý / kết luận của kỹ thuật viên |

Quy ước màu trạng thái dùng chung (không lệch giữa các màn hình):
Mới tiếp nhận (xanh dương) · Đang kiểm tra (vàng) · Đang sửa chữa (tím) · Chờ trả máy (xanh ngọc) ·
Đã hoàn tất (xanh lá) · Từ chối bảo hành (đỏ).

Chi tiết nghiệp vụ + kết quả kiểm thử: `docs/BAO_CAO_MAN_HINH_CONG_VIEC_THEO_VAI_TRO.md`.

## Tinh gọn & dễ hiểu hoá (Đợt 5)

Đợt 5 **chỉ sửa lớp hiển thị** (`index.html`, `app.js`, `styles.css`, `README.md`). Backend, CSDL,
API, `tests/**`, BR1–BR4, máy trạng thái phiếu và AI-01 **không đổi**.

| Nhóm | Nội dung đã làm |
|---|---|
| Tiếng Việt tự nhiên | Thêm `accentRestore()` + 2 bảng từ (`PHRASE_ACCENT_MAP`, `WORD_ACCENT_MAP`) khôi phục dấu cho mô tả lỗi/ghi chú/lý do do dữ liệu lưu không dấu (ví dụ `Man hinh Dell bi chap chon cong Type-C` → *Màn hình Dell bị chập chờn cổng Type-C*). Không áp dụng cho tên khách hàng/sản phẩm do người dùng nhập nên **không đoán sai tên riêng**. |
| Thông báo lỗi | `FIELD_LABELS` + `SERVER_MESSAGE_LABELS` dịch thông báo dữ liệu nhập (`full_name: Field required` → *Họ và tên: là trường bắt buộc*). Bỏ hẳn câu kỹ thuật "kiểm tra backend đã chạy chưa"/"máy chủ". |
| Nút bấm rõ nghĩa | `Lưu` → **Lưu khách hàng / Lưu sản phẩm / Lưu thiết bị**; cột *Hồ sơ* → **Trạng thái hồ sơ**; nút trong phiếu → **Xem đầy đủ ở màn hình xác định lỗi**. |
| Form | Thêm dòng "* là trường bắt buộc" ở 3 form CRUD và bước 2 của wizard; giữ nguyên số trường. |
| Tra cứu / tiếp nhận | Giải thích **số sê-ri là dãy ký tự in trên tem máy**; nút chọn nhanh hiển thị **sản phẩm · khách hàng · tình trạng bảo hành** (số sê-ri xuống dòng nhỏ) thay vì chỉ hiện mã máy; rút danh sách gợi ý còn 4 mục. |
| Gợi ý loại lỗi | Lọc kết quả gợi ý **không khớp danh mục lỗi** → hiện "Không xác định" kèm giải thích; kết quả bị hệ thống chặn nội dung can thiệp được thay bằng **lời khuyên hỏi khách cụ thể hơn**; đổi `fixture`/`product_instance`/`PII` sang tiếng Việt. |
| Nhắc trước khi tạo phiếu | Bước 2 wizard cảnh báo khi thiết bị **đang có phiếu chưa kết thúc** và cho mở luôn phiếu đó (việc chặn thật vẫn do hệ thống quyết định). |
| Sửa lỗi hiển thị | Bảng Thiết bị khai báo đúng 8 cột cho dòng "Đang tải/Không tải được"; không còn hiện mã nội bộ kiểu `#12` trong thông báo. |

Ghi chú kiểm chứng Đợt 5: `node --check` OK · UI Đợt 3 **49/49 PASS** · bộ kiểm Đợt 5 **43/43 PASS** ·
bộ kiểm lớp hiển thị (Node) **26/26 PASS** · `.\dev.ps1 check` **24/24 PASS** · E2E **76 PASS / 0 FAIL**.

## Lưu ý kỹ thuật

- Thư viện ngoài nạp qua CDN (Tailwind, Lucide icons, Chart.js) ⇒ máy cần internet khi mở giao diện.
  Nếu CDN bị chặn, biểu đồ sẽ tự bỏ qua (có kiểm tra `typeof Chart`) và các bảng vẫn hoạt động.
- API base là đường dẫn tương đối (`/api/v1/...`) nên giao diện phải mở **qua backend**,
  không mở trực tiếp `index.html` bằng `file://`.
- Wizard **Tiếp nhận máy mới** mặc định để **"Chưa xác định (để hệ thống gợi ý)"** cho loại lỗi ⇒ phiếu tạo từ giao diện
  không có `error_category_id`, đúng luồng KT3 (AI gợi ý → nhân viên xác nhận).
  Nhân viên vẫn có thể tự chọn danh mục lỗi nếu muốn.
- Mọi số liệu mới ở bảng Khách hàng/Sản phẩm (số thiết bị, số phiếu) đều **đếm từ dữ liệu API đang tải**
  (`state.devices`, `state.tickets`) — không hard-code, không tạo dữ liệu giả.
  Tình trạng bảo hành trên giao diện chỉ để **hiển thị**; quyết định bảo hành vẫn do backend
  (`warranty_end_date >= check_date`).
- Class dùng chung trong `styles.css`: `.btn/.btn-primary/.btn-secondary/.btn-danger/.btn-success/.btn-warning`,
  `.table-th/.table-td/.table-row/.table-msg`, `.chip`, `.form-label/.form-error`, `.nav-tab-btn`, `.btn-stack` (nút nhiều dòng),
  và các thành phần bảng điều khiển: `.dash-chip`, `.dash-card`, `.dash-work-item`, `.dash-focus-row`,
  `.dash-attention-row`, `.row-more*` (menu "Thêm"), `.nav-more-panel` (dropdown "Tra cứu nội bộ").
- Lớp hiển thị tiếng Việt xử lý theo thứ tự: bỏ thẻ kỹ thuật → bảng dịch nguyên văn (`DISPLAY_TEXT_MAP`) →
  mã trạng thái/nhóm lỗi → khôi phục dấu (`accentRestore`). Tất cả chỉ ảnh hưởng phần **hiển thị**;
  giá trị gửi lên hệ thống vẫn là dữ liệu gốc.

