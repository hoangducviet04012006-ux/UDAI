# BÁO CÁO: MÀN HÌNH CÔNG VIỆC THEO VAI TRÒ (Prompt 2)

> Mục tiêu: BaoHanhAI không còn là hệ thống "ai đăng nhập cũng thấy gần giống nhau".
> Sau khi đăng nhập, **bảng điều khiển trả lời ngay câu hỏi "Hiện tại tôi cần làm gì?"**
> cho đúng vai trò của người đó: Quản lý nhìn toàn trung tâm, Nhân viên tiếp nhận nhìn việc
> ở quầy, Kỹ thuật viên nhìn việc trên bàn kỹ thuật.

Thời điểm thực hiện: sau khi hoàn thành đợt "nghiệp vụ phiếu bảo hành" (Prompt 1).
Nguyên tắc xuyên suốt: **backend là nguồn sự thật** — giao diện không tự suy diễn trạng thái,
không tự quyết định quyền, không "lọc giả" dữ liệu ở trình duyệt.

---

## 1. Ba vai trò khác nhau ở đâu (bảng đối chiếu)

| Nội dung | QUẢN LÝ (`manager01`) | NHÂN VIÊN TIẾP NHẬN (`receptionist01`) | KỸ THUẬT VIÊN (`technician01`) |
|---|---|---|---|
| Tiêu đề bảng điều khiển | Tổng quan trung tâm | Việc tại quầy tiếp nhận | Công việc kỹ thuật |
| Nhóm công việc | Mới tiếp nhận · Đang kiểm tra · Đang sửa chữa · Chờ trả máy · Đã hoàn tất (toàn trung tâm) | Cần tiếp nhận · Đang xử lý (kiểm tra + sửa chữa) · Chờ trả máy | Chờ kiểm tra · Đang kiểm tra · Đang sửa chữa · Chờ hoàn thiện hồ sơ |
| Thẻ số liệu | 9 thẻ: Tổng phiếu + 6 trạng thái + Khách hàng + Máy đã đăng ký | 5 thẻ theo bước (Mới tiếp nhận → Đã hoàn tất) | 4 thẻ theo bước kỹ thuật |
| "Việc cần chú ý" | **Có** (lý do lấy từ dữ liệu thật của phiếu) | Không | Không |
| Thao tác nhanh chính | Xem toàn bộ phiếu | **Tiếp nhận máy mới** | Phiếu chờ kiểm tra |
| Biểu đồ phân bổ trạng thái | Có | Không (tập trung danh sách việc) | Không |
| Bảng phiếu ở dashboard | Toàn bộ phiếu đang xử lý | Phiếu tôi đang phụ trách / toàn bộ phiếu | Phiếu tôi đang xử lý / toàn bộ phiếu |
| Nút hành động trên mỗi phiếu | Theo trạng thái + quyền (gồm cả *Xác nhận đã trả máy*, *Từ chối bảo hành*) | *Chuyển vào phòng kiểm tra*, *Xác nhận đã trả máy* | *Bắt đầu kiểm tra*, *Cập nhật kết quả kiểm tra*, *Cập nhật sửa chữa* |
| Menu chính | 7 mục nghiệp vụ + *Tài khoản nhân viên* | 7 mục nghiệp vụ (không có *Tài khoản nhân viên*) | 4 mục việc hằng ngày + nhóm phụ **"Tra cứu nội bộ"** |
| Việc KHÔNG được làm (backend chặn 403) | – | Ghi chẩn đoán, xóa khách hàng, quản trị tài khoản | Tạo phiếu, xác nhận trả máy, quản trị tài khoản |

---

## 2. Backend thay đổi gì

### 2.1. `GET /api/v1/warranty-tickets/workboard` — bảng điều khiển theo vai trò

Một lần gọi API trả về **mọi thứ bảng điều khiển cần** (thay cho 4 lời gọi rời rạc trước đây):

| Trường | Ý nghĩa |
|---|---|
| `role`, `role_label`, `title`, `subtitle` | Tiêu đề + mô tả theo vai trò ("Công việc kỹ thuật", "Việc tại quầy tiếp nhận", …) |
| `cards[]` | Thẻ số liệu: `key`, `label`, `count`, `description`, `tone` (màu theo trạng thái) |
| `groups[]` | Nhóm công việc: `label`, `count`, `status_filter`, `scope` (`ALL`/`MINE`), `action_target`, `action_label`, `items[]` (tối đa 6 phiếu, mỗi phiếu đã kèm hành động được phép) |
| `focus[]` | "Việc cần làm ngay" — đã sắp theo thứ tự nghiệp vụ của vai trò |
| `attention[]` | "Việc cần chú ý" (chỉ Quản lý): `ticket_code`, `reason`, `days_since_update` |
| `active_tickets[]`, `my_tickets[]` | Phiếu đang xử lý toàn trung tâm / phiếu của chính tôi |
| `quick_actions[]` | Thao tác nhanh theo vai trò (đã lọc theo quyền) |
| `notes[]` | Ghi chú nghiệp vụ: việc này của ai (ví dụ "Kỹ thuật viên không tự xác nhận trả máy") |
| `scope`, `scope_label` | `DEFAULT` (theo vai trò) / `MINE` / `ALL` khi người dùng đổi phạm vi |

Tham số `?scope=MINE|ALL` cho phép nhân viên chuyển giữa *Việc của tôi* và *Toàn bộ phiếu*;
con số được tính lại ở backend, **không lọc giả trên giao diện**.

Mã nguồn: `backend/app/services/workboard.py` (bố cục theo vai trò: `ROLE_LAYOUT`,
`WORK_GROUPS`, `QUICK_ACTIONS`, `ROLE_NOTES`, `CARD_DEFS`) và
`backend/app/schemas.py` (`WorkboardResponse` và các schema con).

### 2.2. "Việc cần chú ý" chỉ dùng dữ liệu thật (không tự bịa tiêu chí)

`workboard._attention_reasons()` chỉ nêu những lý do **đọc trực tiếp từ phiếu**:

| Trạng thái | Lý do nêu ra |
|---|---|
| `RECEIVED` | Máy đã tiếp nhận nhưng chưa chuyển vào phòng kiểm tra |
| `INSPECTING` | Chưa có kết luận chẩn đoán của kỹ thuật viên |
| `REPAIRING` | Chưa cập nhật nội dung đã kiểm tra / đã sửa chữa |
| `WAITING_RETURN` | Máy đã sửa xong, đang chờ khách tới nhận |

Kèm dữ liệu **"đã N ngày kể từ lần cập nhật gần nhất"** như một con số tham khảo —
**không** tự đặt ngưỡng "quá lâu" khi hệ thống chưa có quy tắc đó.

### 2.3. Mỗi DÒNG danh sách phiếu biết trước "được bấm gì"

`WarrantyTicketResponse` được bổ sung 4 trường do backend tính theo **trạng thái + quyền của
người đang đăng nhập**:

- `available_actions[]`: mọi bước chuyển mà vai trò này được phép ở trạng thái hiện tại.
- `primary_action`: **một** hành động chính (ưu tiên bước tiến của quy trình).
- `action_label`: câu chữ của nút (ví dụ "Sửa xong – Chờ trả máy", hoặc "Xem thông tin trả máy"
  khi vai trò không có bước chuyển nào).
- `action_kind`: `transition` (bấm là chuyển bước) hoặc `read_only` (chỉ mở phiếu xem).

Nhờ vậy danh sách phiếu **không thể** hiển thị thao tác mà backend sẽ chặn (403) — và mỗi dòng
chỉ có một nút chính (các bước phụ nằm trong menu "Thêm").


### 2.4. Bộ lọc "việc của tôi" chạy ở tầng SQL

Trước đây `mine=1` lọc bằng Python **sau khi** đã giới hạn số dòng (`limit`), nên khi dữ liệu nhiều
thì danh sách và số liệu có thể lệch nhau. Nay:

- `crud/warranty_tickets.last_handler_subquery()` tạo bảng tra *người xử lý gần nhất* của từng phiếu
  (dòng `ticket_status_history` mới nhất; chưa có lịch sử thì lấy `created_by`).
- `get_warranty_tickets(..., mine_user_id=...)` và `count_tickets_by_status(db, mine_user_id=...)`
  dùng **cùng một điều kiện SQL** ⇒ danh sách, phân trang và số liệu luôn khớp nhau.

### 2.5. Menu theo vai trò do backend trả về

- `auth_service.MENU_DEFINITIONS`: danh mục menu của hệ thống (tab, nhãn, biểu tượng, quyền tối thiểu, nhóm).
- `auth_service.navigation_for_role(role)`: lọc theo quyền của vai trò và xếp nhóm
  `work` / `reference` / `admin`. Kỹ thuật viên được xếp lại *Khách hàng · Danh mục máy · Máy đã đăng ký*
  vào nhóm **"Tra cứu nội bộ"** (vẫn giữ nguyên quyền đọc đã kiểm chứng ở `tests/test_auth_rbac.py`).
- `GET /api/v1/auth/me` và `POST /api/v1/auth/login` trả thêm trường `menus` — giao diện chỉ vẽ lại.

### 2.6. Lọc nhiều trạng thái cho một nhóm việc

`GET /api/v1/warranty-tickets/?status=INSPECTING,REPAIRING` — nhóm "Đang xử lý" của Tiếp nhận gộp
2 bước nên khi bấm vào nhóm, danh sách mở đúng cả hai trạng thái (một giá trị đơn vẫn hoạt động như cũ).

### 2.7. Không đổi gì thuộc Prompt 1

- Vẫn **6 trạng thái** và `TRANSITION_RULES` cũ: `RECEIVED → INSPECTING → REPAIRING → WAITING_RETURN → COMPLETED`,
  nhánh `REJECTED` giữ nguyên; `PATCH /{id}/status`, `/diagnosis`, `/repair` không đổi hợp đồng.
- `GET /stats/summary`, `GET /meta/workflow`, `GET /code/{code}` vẫn hoạt động (tương thích ngược).
- Không thêm bảng/cột CSDL, không đổi dữ liệu seed.

---

## 3. Giao diện thay đổi gì

| Khu vực | Thay đổi |
|---|---|
| Thanh menu | Vẽ theo `menus` do backend trả về; nhóm phụ **"Tra cứu nội bộ"** (dropdown) cho các sổ/danh mục; màn hình nhỏ có nhãn nhóm tương ứng |
| Tab Tổng quan | Đầu trang theo vai trò (tiêu đề + chip vai trò + chip phạm vi) · "Việc thường làm" (thao tác nhanh theo vai trò + ghi chú nghiệp vụ) · thẻ số liệu động · "Công việc theo bước" (mỗi phiếu 1 nút hành động) · "Việc cần chú ý" + biểu đồ (Quản lý) · **"Việc cần làm ngay"** (danh sách có số thứ tự ưu tiên) · bảng phiếu + nút `[Việc của tôi]`/`[Toàn bộ phiếu]` (Quản lý: `[Toàn bộ hệ thống]`/`[Việc cần chú ý]`) |
| Danh sách phiếu | Bộ lọc nhanh 6 trạng thái + `[Phiếu của tôi]`; **tìm kiếm chạy ở backend** (`?q=`, chờ 350ms khi gõ); mỗi dòng 1 nút chính + menu "Thêm" cho bước phụ |
| Màn hình phiếu | Khối **"Hỗ trợ chẩn đoán"** tách 3 phần rõ ràng: ① Khách hàng mô tả ② Hệ thống gợi ý (chỉ tham khảo) ③ Kết luận của kỹ thuật viên — không gọi gợi ý là "kết luận", không tự ghi vào phiếu |
| Mở phiếu từ công việc | Bấm nút trên bảng điều khiển/danh sách → mở thẳng phiếu; nếu là bước chuyển thì mở luôn hộp thoại xác nhận của đúng bước đó (`openTicketModal(id, { autoAction })`) |
| Màu sắc | Mỗi trạng thái một màu cố định dùng lại ở mọi màn hình: Mới tiếp nhận (xanh dương) · Đang kiểm tra (vàng) · Đang sửa chữa (tím) · Chờ trả máy (xanh ngọc) · Đã hoàn tất (xanh lá) · Từ chối (đỏ) |
| Responsive | Bảng có `overflow-x-auto` + `min-w-*`; menu chính co nhãn ở ≤1180px; thẻ/khối dùng lưới `1 → 2 → 3` cột; nút tự xuống dòng (kiểm tra ở 1280px và 1024px) |

Chi tiết kỹ thuật giao diện: `frontend/README.md` (mục "Màn hình công việc theo vai trò").

---

## 4. Các kịch bản đã kiểm thử (`tests/test_role_workbench.py`)

| CASE | Nội dung | Kết quả |
|---|---|---|
| A | Tiếp nhận máy mới → dashboard Tiếp nhận cập nhật: nhóm "Cần tiếp nhận" có phiếu vừa tạo, có nút "Tiếp nhận máy mới", có ghi chú về bước trả máy | PASS |
| A2 | Số liệu thẻ "Mới tiếp nhận" khớp số lượng nhóm "Cần tiếp nhận" (cùng nguồn dữ liệu) | PASS |
| B1 | Kỹ thuật viên: nhóm "Chờ kiểm tra" thấy phiếu mới + nút theo vai trò; **không** có thao tác tiếp nhận máy; có ghi chú "không tự trả máy" | PASS |
| B2 | Kỹ thuật viên: Bắt đầu kiểm tra → Cập nhật kiểm tra → Chuyển "Chờ trả máy"; phiếu vào nhóm "Chờ hoàn thiện hồ sơ"; không có nút COMPLETED | PASS |
| C | Tiếp nhận: thấy phiếu ở nhóm "Chờ trả máy" → Xác nhận đã trả máy → phiếu rời khỏi hàng chờ | PASS |
| D | Quản lý: đủ 9 thẻ + 5 nhóm việc + "việc cần chú ý" có lý do thật ("Chưa cập nhật nội dung…") + lịch sử phiếu 5 bước | PASS |
| E | Phân quyền: kỹ thuật viên tạo phiếu / tự trả máy / xem tài khoản → **403**; tiếp nhận ghi chẩn đoán / xóa khách → **403**; cả 3 vai trò xem dashboard được (200) | PASS |
| F | Menu theo vai trò: Quản lý có *Tài khoản nhân viên*; Tiếp nhận & Kỹ thuật không có; sổ/danh mục của Kỹ thuật nằm trong nhóm `reference` | PASS |
| G | `mine=1` lọc ở SQL: danh sách = phiếu của chính mình, khớp số liệu `?mine=1`, phân trang vẫn đúng | PASS |
| H | Nút hành động theo trạng thái + quyền (phiếu hoàn tất = chỉ xem; "Chờ trả máy": kỹ thuật `[REPAIRING]` vs tiếp nhận `[COMPLETED, REPAIRING]`); nhóm nhiều trạng thái mở đúng 2 trạng thái; `scope=MINE/ALL` do backend quyết định | PASS |

Cách chạy:

```powershell
.\dev.ps1 workbench          # hoặc: py -3.12 tests\test_role_workbench.py
.\dev.ps1 check              # cổng kiểm tra tổng hợp (minh chứng + phiếu + màn hình công việc + giao diện)
```

> ⚠️ Các file test dùng chung một CSDL SQLite: **chạy tuần tự**, không chạy song song.

### 4.1. Cổng kiểm tra tổng hợp (`.\\dev.ps1 check`)

| Lớp kiểm tra | Kết quả |
|---|---|
| `tests/test_scenarios.py` (minh chứng KT2 + KT3) | 25/25 PASS |
| `tests/test_ticket_workflow.py` (vòng đời phiếu, CASE 1..8) | 10/10 PASS |
| `tests/test_role_workbench.py` (màn hình công việc, CASE A..H) | 10/10 PASS |
| `tests/smoke_frontend.js` (lớp hiển thị, Node) | 12/12 PASS |
| `tests/test_auth_rbac.py` (đăng nhập & phân quyền) | 13/13 PASS |

Ngoài ra: `py -3.12 -m compileall backend/app` **exit 0**, `node --check frontend/app.js` **exit 0**,
và kiểm tra chéo toàn bộ `id` mà `app.js` truy cập đều tồn tại trong `index.html`.

### 4.2. Kiểm tra bằng tay (3 tài khoản demo)

| Bước | manager01 | receptionist01 | technician01 |
|---|---|---|---|
| 1 | Mở Tổng quan → 9 thẻ, 5 nhóm việc, "Việc cần chú ý", biểu đồ | Mở Tổng quan → "Việc tại quầy tiếp nhận", thẻ theo bước, nút **Tiếp nhận máy mới** | Mở Tổng quan → "Công việc kỹ thuật", 4 nhóm việc kỹ thuật |
| 2 | Menu có *Tài khoản nhân viên*; mở phiếu bất kỳ → xem lịch sử | Menu **không** có *Tài khoản nhân viên* | Menu chính 4 mục việc hằng ngày; mở **Tra cứu nội bộ** để xem khách/danh mục/máy |
| 3 | Xem nút hành động trên từng dòng phiếu (khác nhau theo trạng thái) | Tiếp nhận máy mới → phiếu xuất hiện ngay ở nhóm "Cần tiếp nhận" | Bấm *Bắt đầu kiểm tra* trên phiếu chờ → hộp thoại xác nhận mở ngay |
| 4 | Bấm `[Việc cần chú ý]` → bảng chuyển sang danh sách phiếu cần để mắt kèm lý do | Ở phiếu "Chờ trả máy": bấm *Xác nhận đã trả máy* → phiếu hoàn tất, rời hàng chờ | Thử mở *Tài khoản nhân viên* bằng URL/console → bị chặn (403) |


---

## 5. Giới hạn đã biết (nói rõ để không hiểu sai)

1. **Chưa có ngưỡng cảnh báo tự động** ("quá lâu"): khối "Việc cần chú ý" chỉ nêu lý do lấy từ dữ liệu thật
   và số ngày kể từ lần cập nhật — muốn thành cảnh báo thì cần quy tắc nghiệp vụ riêng.
2. **Kỹ thuật viên vẫn có quyền đọc** sổ khách hàng/danh mục máy/máy đã đăng ký (đã có từ trước và được
   kiểm chứng ở `tests/test_auth_rbac.py`); đợt này chỉ **xếp lại vào nhóm menu phụ** cho gọn màn hình chính.
3. **Tiếp nhận vẫn cập nhật được trạng thái** theo State Machine (Prompt 1 đã chốt như vậy), nên trên danh
   sách phiếu Tiếp nhận có thể thấy nút *Sửa xong – Chờ trả máy* ở phiếu đang sửa; quyền chuyên môn
   (chẩn đoán/sửa chữa) vẫn thuộc Kỹ thuật viên.
4. **KTV không tự xác nhận trả máy** — nút này chỉ có với Tiếp nhận/Quản lý; ở "Chờ trả máy" KTV chỉ thấy
   *Xem thông tin trả máy* và (nếu cần) *Khách báo còn lỗi – Sửa lại*.
5. Bảng điều khiển giới hạn số dòng mỗi khối (nhóm việc 6, việc cần làm 10, việc cần chú ý 10, bảng 15)
   để tải nhanh; danh sách đầy đủ nằm ở màn **Phiếu bảo hành**.
6. Không thêm chatbot/RAG/LangGraph, không CRM/kho/thanh toán/SMS — đúng phạm vi Prompt 2.

---

## 6. Danh sách file đã sửa/thêm trong đợt này

**Backend**

| File | Việc đã làm |
|---|---|
| `backend/app/services/workboard.py` | **Mới**: bố cục bảng điều khiển theo vai trò, nhóm công việc, "việc cần chú ý", thẻ số liệu, thao tác nhanh, ghi chú nghiệp vụ |
| `backend/app/services/ticket_view.py` | Thêm `build_row_action()` + trường `available_actions` / `primary_action` / `action_label` / `action_kind` cho mỗi dòng danh sách |
| `backend/app/crud/warranty_tickets.py` | `last_handler_subquery()`, lọc `mine` và đếm theo trạng thái ở tầng SQL, lọc `status` nhiều giá trị |
| `backend/app/services/auth_service.py` | `MENU_DEFINITIONS`, `MENU_GROUP_OVERRIDES`, `navigation_for_role()` |
| `backend/app/routers/auth.py` | Trả `menus` trong `/auth/login` và `/auth/me` |
| `backend/app/routers/warranty_tickets.py` | Thêm `GET /workboard`; danh sách phiếu trả kèm hành động theo quyền |
| `backend/app/schemas.py` | `WorkboardResponse` + schema con, `SessionMenuEntry`, trường hành động trong `WarrantyTicketResponse` |

**Frontend**

| File | Việc đã làm |
|---|---|
| `frontend/index.html` | Bảng điều khiển theo vai trò (đầu trang, thao tác nhanh, thẻ số liệu động, nhóm việc, việc cần chú ý, việc cần làm ngay, bảng phiếu + nút chuyển cách xem); menu phụ "Tra cứu nội bộ"; khối "Hỗ trợ chẩn đoán" 3 phần |
| `frontend/app.js` | `loadDashboard()` gọi `/workboard`; các hàm `renderDash*`, `renderWorkGroups`, `setDashView`, `dashQuickAction`, `renderNavigation`, `handleTicketAction`; tìm kiếm phiếu qua backend |
| `frontend/styles.css` | Lớp CSS cho chip/thẻ/nhóm việc/việc cần làm/việc cần chú ý/menu "Thêm"/menu phụ + nhánh responsive ≤1180px |

**Kiểm thử – công cụ – tài liệu**

| File | Việc đã làm |
|---|---|
| `tests/test_role_workbench.py` | **Mới**: 10 kịch bản CASE A..H cho bảng điều khiển theo vai trò |
| `tests/smoke_frontend.js` | 8 → **12** kiểm tra hiển thị (nhóm việc, nhãn nút theo vai trò, thẻ số liệu, bảng điều khiển, việc cần chú ý) |
| `tests/init_db.py` | Thêm tham số `--reset` (xoá bảng rồi tạo lại) để đưa CSDL demo về trạng thái sạch |
| `dev.ps1` | Thêm task `workbench` và `resetdb`; `check` chạy thêm lớp kiểm thử màn hình công việc |
| `Makefile` | Thêm target `workbench`, `ui`, `resetdb`; `check` gọi đủ 4 lớp kiểm thử |
| `docs/BAO_CAO_MAN_HINH_CONG_VIEC_THEO_VAI_TRO.md` | **Mới**: báo cáo này |
| `docs/BAO_CAO_HOAN_THIEN_HE_THONG.md` | Cập nhật số endpoint (41), mục 9.1/9.2 (menu + bảng điều khiển theo vai trò) |
| `docs/README.md`, `README.md`, `frontend/README.md` | Cập nhật danh mục lệnh, danh sách file, mô tả bảng điều khiển/menu theo vai trò |

