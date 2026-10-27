# BÁO CÁO HOÀN THIỆN HỆ THỐNG — BaoHanhAI

> Tài liệu này mô tả **đợt hoàn thiện cuối (Đợt 8)** của hệ thống quản lý bảo hành sản phẩm
> **BaoHanhAI**, sau khi đã có nền tảng KT1–KT4: chuẩn hoá vòng đời phiếu 6 trạng thái
> (bắt buộc qua `WAITING_RETURN`), phân quyền RBAC đầy đủ phía backend, giao diện tiếng Việt
> theo đúng vai trò nghiệp vụ, dữ liệu mẫu tự nhiên và bộ minh chứng tự động mở rộng.
>
> - Ngày hoàn thiện: **28/09/2026**
> - Kết quả kiểm thử cuối: **KT2 + KT3: 25/25 PASS** — **RBAC (Đợt 7): 13/13 PASS** (exit code 0)
> - Log minh chứng: [`docs/evidence/minh_chung_KT2_KT3.txt`](evidence/minh_chung_KT2_KT3.txt)

---

## 1. Mục tiêu và phạm vi

### 1.1. Mục tiêu
1. Biến bản demo KT2/KT3 thành **hệ thống có thể dùng thật** ở một trung tâm bảo hành:
   tiếp nhận máy → kiểm tra → sửa chữa → **chờ trả máy** → trả máy (hoàn tất), có phân quyền,
   có dấu vết ai làm gì, có tra cứu và báo cáo nhanh.
2. Loại bỏ các "lỗ hổng nghiệp vụ" của bản cũ: **thiếu bước chờ trả máy**, đóng phiếu ngay sau
   khi sửa xong, không phân biệt vai trò, lộ mã kỹ thuật của AI ra giao diện người dùng.
3. Giữ vững **tính tái lập minh chứng**: chạy một lệnh là in ra toàn bộ bằng chứng PASS/FAIL,
   dùng được để chụp ảnh/nộp bài, không ghi PASS giả.

### 1.2. Phạm vi
- Backend FastAPI + SQLAlchemy, CSDL SQLite (mặc định) / PostgreSQL (tuỳ chọn), 16 bảng.
- Giao diện web thuần HTML/CSS/JS (không build step) phục vụ tại `/`.

---

## 2. Hiện trạng trước khi hoàn thiện và vấn đề đặt ra

### 2.1. Vấn đề nghiệp vụ (đã khắc phục)
| # | Vấn đề | Hệ quả thực tế | Cách khắc phục |
|---|---|---|---|
| 1 | Không có trạng thái **chờ trả máy** | Máy sửa xong là "đóng phiếu" ngay, CSKH không biết máy còn nằm ở trung tâm | Thêm `WAITING_RETURN`, chặn `REPAIRING → COMPLETED` |
| 2 | Không phân biệt vai trò ở API | Nhân viên tiếp nhận có thể xoá dữ liệu, kỹ thuật viên có thể từ chối bảo hành | RBAC theo vai trò + quyền, kiểm tra ở backend |
| 3 | Không có "người thực hiện" đáng tin | Có thể khai khống `created_by` / `changed_by` | `ensure_actor_allowed()`: nhân viên chỉ ghi danh mình, quản lý ghi danh thay |
| 4 | Mã kỹ thuật AI hiển thị cho người dùng | Người dùng thấy `ERROR_CLASSIFICATION`, `suggested_category_id`… khó hiểu | Lớp hiển thị tiếng Việt: chỉ hiện tên nhóm lỗi + mức độ chắc chắn + giải thích |
| 5 | Phiếu "đang mở" định nghĩa thiếu | BR3 có thể cho tạo phiếu trùng khi máy đang chờ trả | Whitelist trạng thái mở gồm cả `WAITING_RETURN` |

### 2.2. Sự cố kỹ thuật trong quá trình hoàn thiện (minh bạch)
- Khi đang sửa kịch bản minh chứng, ổ đĩa bị **hết dung lượng** do một file log rác 171 GB
  (`D:\Nhom06\out_before_probe.txt`). Hệ quả: file `tests/test_scenarios.py` **bị ghi rỗng 0 byte**.
- Ổ đĩa đã được giải phóng; file kịch bản được **khôi phục và kiểm chứng lại byte-code**:
  1. Lấy bản gần nhất từ backup `D:\BaoHanhAI_Project_BACKUP_20260922_100719\scripts\test_scenarios.py`.
  2. Đối chiếu với file `.pyc` thật của phiên bản bị mất (`tests/__pycache__/test_scenarios.cpython-312.pyc`):
     trích xuất **frozenset tên bảng**, danh sách `co_consts`, bảng dòng và mã byte-code.
  3. Viết lại phần đã mất (khối "Minh chứng 1") rồi **so khớp tự động**: source khôi phục cho ra
     byte-code **trùng khớp 100%** với `.pyc` gốc (cùng số lệnh, cùng bảng dòng) — chỉ khác phần
     cố ý thêm mới (import tài khoản demo để đăng nhập RBAC).
- Sau đó bộ minh chứng chạy lại **25/25 PASS**, log được sinh lại bằng `.\dev.ps1 evidence`.

---

## 3. Kiến trúc hệ thống sau hoàn thiện

```
BaoHanhAI_Project/
├── backend/
│   ├── app/
│   │   ├── main.py                 # Khởi tạo FastAPI, mount giao diện tại "/", /static, /docs
│   │   ├── config.py               # Cấu hình (DB URL, phiên/token, PBKDF2, AI provider…)
│   │   ├── database.py             # Engine + SessionLocal + Base
│   │   ├── models.py               # 16 bảng ORM (khớp database/postgres_schema.sql)
│   │   ├── schemas.py              # Pydantic request/response
│   │   ├── crud/                   # Truy vấn CSDL theo nghiệp vụ
│   │   ├── routers/                # 8 router nghiệp vụ + auth + users + debug (9 file)
│   │   └── services/
│   │       ├── warranty_rules.py   # BR1–BR4, State Machine 6 trạng thái, nhãn tiếng Việt
│   │       ├── auth_service.py     # Vai trò, 20 quyền, PBKDF2, token phiên, guard RBAC
│   │       └── ai_service.py       # AI-01: phân loại lỗi + guardrail (PII, prompt injection)
│   └── requirements.txt
├── frontend/                       # index.html (1.045 dòng) + app.js (3.411 dòng) + styles.css
├── database/                       # baohanh_ai.db (SQLite) + postgres_schema.sql
├── tests/
│   ├── init_db.py                  # Tạo 16 bảng
│   ├── seed_data.py                # Dữ liệu mẫu tự nhiên + tài khoản demo
│   ├── test_scenarios.py           # 25 minh chứng KT2 + KT3
│   └── test_auth_rbac.py           # 13 minh chứng đăng nhập & phân quyền
├── docs/                           # Tài liệu + evidence/minh_chung_KT2_KT3.txt
├── dev.ps1                         # Lệnh chuẩn cho Windows
└── Makefile                        # Lệnh tương đương cho Git Bash/Linux/macOS
```

**Số liệu chính:** 16 bảng CSDL · 41 endpoint nghiệp vụ · 23 quyền / 3 vai trò ·
25 + 13 + 10 mục kiểm thử tự động · giao diện tiếng Việt thuần HTML/CSS/JS (không cần build).

---

## 4. Vòng đời phiếu bảo hành: 6 trạng thái (điểm cốt lõi của đợt hoàn thiện)

### 4.1. Nhãn tiếng Việt thống nhất
| Mã trạng thái | Nhãn hiển thị | Ý nghĩa nghiệp vụ |
|---|---|---|
| `RECEIVED` | Mới tiếp nhận | Đã lập phiếu tại quầy, máy chưa vào phòng kỹ thuật |
| `INSPECTING` | Đang kiểm tra | Kỹ thuật viên kiểm tra, xác định lỗi |
| `REPAIRING` | Đang sửa chữa | Đang xử lý / thay linh kiện |
| `WAITING_RETURN` | **Chờ trả máy** | Máy đã sửa xong, đang nằm ở trung tâm chờ khách tới nhận |
| `COMPLETED` | Đã hoàn tất | Đã bàn giao máy cho khách (ghi mốc `handed_over_at`) |
| `REJECTED` | Từ chối bảo hành | Không thuộc diện bảo hành (cần lý do, chỉ QUẢN LÝ xác nhận) |

Nhãn này được khai báo **một nguồn duy nhất** ở `backend/app/services/warranty_rules.py`
(`TICKET_STATUS_LABELS`) và phản chiếu ở giao diện (`STATUS_LABELS` trong `frontend/app.js`).

### 4.2. Ma trận chuyển trạng thái (`ALLOWED_TRANSITIONS`)
```
RECEIVED        -> INSPECTING
INSPECTING      -> REPAIRING | REJECTED
REPAIRING       -> WAITING_RETURN | INSPECTING        (quay lại kiểm tra khi phát sinh lỗi mới)
WAITING_RETURN  -> COMPLETED | REPAIRING              (khách báo còn lỗi -> sửa lại)
COMPLETED       -> (kết thúc)
REJECTED        -> (kết thúc)
```
- **Bắt buộc đi qua `WAITING_RETURN`**: `REPAIRING → COMPLETED` bị chặn và trả về
  `400 [STATE MACHINE ERROR]` kèm gợi ý các trạng thái hợp lệ tiếp theo (thông báo tiếng Việt).
- Mọi thao tác đổi trạng thái đều ghi `ticket_status_history` (từ trạng thái → trạng thái,
  người thực hiện, ghi chú, thời điểm). Phiếu mới sinh 1 dòng `START/None → RECEIVED`.

### 4.3. Mốc bàn giao `handed_over_at`
| Thời điểm | Giá trị | Vì sao |
|---|---|---|
| Vừa tạo phiếu | `null` | Chưa có gì để bàn giao |
| `RECEIVED/INSPECTING/REPAIRING` | `null` | Máy còn ở trung tâm |
| **`WAITING_RETURN`** | **`null`** | Đã sửa xong nhưng **chưa trả** khách |
| `COMPLETED` | thời điểm UTC | Máy đã rời trung tâm |

### 4.4. Ảnh hưởng dây chuyền (đã cập nhật đồng bộ)
| Nơi | Nội dung cập nhật |
|---|---|
| `warranty_rules.OPEN_TICKET_STATUSES` | `RECEIVED, INSPECTING, REPAIRING, WAITING_RETURN` → BR3 chặn tạo phiếu trùng khi máy đang chờ trả |
| API `/warranty-tickets/stats/summary` | Bổ sung `waiting_return`; "đang xử lý" = `inspecting + repairing + waiting_return` |
| Giao diện – bảng điều khiển | Thẻ **Chờ trả máy** riêng, lưới 8 thẻ thống kê |
| Giao diện – danh sách phiếu | 6 nút lọc trạng thái, sắp xếp ưu tiên phiếu đang xử lý (`WAITING_RETURN` xếp ngay trước `COMPLETED`) |
| Giao diện – chi tiết phiếu | Thanh tiến trình 5 bước: Tiếp nhận → Kiểm tra → Sửa chữa → **Chờ trả máy** → Hoàn tất |
| Giao diện – nút chuyển trạng thái | Từ `REPAIRING` chỉ hiện "Sửa xong – Chờ trả máy"; từ `WAITING_RETURN` mới hiện "Đã trả máy – Hoàn tất" |
| CSDL Postgres | `database/postgres_schema.sql` cập nhật CHECK/giá trị trạng thái |
| Kịch bản minh chứng | Minh chứng 9 đi **4 bước** (qua `WAITING_RETURN`) + kiểm tra `handed_over_at`; thêm minh chứng 10b |

---

## 5. Quy tắc nghiệp vụ BR1–BR4

| Mã | Quy tắc | Kiểm tra ở đâu | Lỗi trả về |
|---|---|---|---|
| **BR1** | Số serial phải tồn tại trong hệ thống | `validate_br1_serial_exists` | `404 [BR1 FAIL]` |
| **BR2** | Sản phẩm còn hạn bảo hành tại ngày tiếp nhận | `validate_br2_warranty_valid` | `400 [BR2 FAIL]` (kèm số ngày quá hạn) |
| **BR3** | Máy không được có phiếu đang mở | `validate_br3_no_open_tickets` | `400 [BR3 FAIL]` (kèm mã phiếu + trạng thái) |
| **BR4** | Người gửi máy phải đúng chủ sở hữu đã đăng ký | `validate_br4_owner_verification` | `400 [BR4 FAIL]` |

Bổ sung quy tắc kiểm tra dữ liệu vào:
- `validate_service_center_exists`, `validate_user_exists` (phiếu phải thuộc trung tâm và nhân viên có thật).
- Công cụ debug `GET /api/v1/debug/check-serial/{serial}` + `POST /api/v1/debug/check-warranty`
  trả về "trace log" từng bước để giải thích vì sao máy còn/không còn hạn (phục vụ minh chứng 11).

---

## 6. Phân quyền theo vai trò (RBAC) — Đợt 7

### 6.1. Ba vai trò trong trung tâm bảo hành
| Vai trò | Nhãn | Việc được làm chính |
|---|---|---|
| `MANAGER` | Quản lý | Toàn quyền nghiệp vụ + quản trị tài khoản nhân viên + **xác nhận từ chối bảo hành** |
| `RECEPTIONIST` | Nhân viên tiếp nhận | Tiếp nhận máy, lập phiếu, chăm sóc khách, xác nhận gợi ý loại lỗi của AI |
| `TECHNICIAN` | Kỹ thuật viên | Xử lý máy theo vòng đời phiếu (kiểm tra/sửa chữa/chờ trả máy/bàn giao) |

### 6.2. 20 quyền nghiệp vụ (`auth_service.py`) và ma trận cấp quyền
| Nhóm | Quyền | MANAGER | RECEPTIONIST | TECHNICIAN |
|---|---|:--:|:--:|:--:|
| Chung | `dashboard.view`, `lookup.view`, `ticket.view`, `ai.view`, `ai.classify`, `customer.view`, `product.view`, `device.view`, `staff.view` | ✔ | ✔ | ✔ |
| Phiếu | `ticket.create` | ✔ | ✔ | – |
| Phiếu | `ticket.update_status` | ✔ | ✔ | ✔ |
| Phiếu | `ticket.reject` | ✔ | – | – |
| AI | `ai.review` (duyệt gợi ý loại lỗi) | ✔ | ✔ | – |
| Khách hàng | `customer.create`, `customer.update` | ✔ | ✔ | – |
| Khách hàng | `customer.delete` | ✔ | – | – |
| Máy | `device.manage` | ✔ | ✔ | – |
| Danh mục máy | `product.manage` | ✔ | – | – |
| Tài khoản | `user.view`, `user.manage` | ✔ | – | – |

### 6.3. Cơ chế bảo vệ (kiểm tra ở backend, không chỉ ẩn menu)
- **Đăng nhập**: `POST /api/v1/auth/login` → token phiên; `GET /api/v1/auth/me` trả danh tính + vai trò + quyền;
  `POST /api/v1/auth/logout` **thu hồi token ngay**.
- **Mọi API nghiệp vụ** gắn `Depends(require_permissions(PERM_...))`:
  - Không có token / token sai chữ ký / token hết hạn / tài khoản bị vô hiệu hoá → **401**.
  - Có token nhưng vai trò không đủ quyền → **403** (ví dụ kỹ thuật viên xác nhận TỪ CHỐI bảo hành).
- **Vai trò luôn đọc từ CSDL** ở mỗi request: token không thể "tự phong quyền"; đổi vai trò trong CSDL
  có hiệu lực ngay với phiên đang mở.
- **Chống khai khống người thực hiện**: `ensure_actor_allowed()` — nhân viên chỉ được ghi danh chính mình
  vào `created_by`/`changed_by`; quản lý được ghi danh thay.
- **Mật khẩu**: băm `pbkdf2_sha256$<iterations>$<salt>$<hash>` (salt riêng từng tài khoản), không lưu thô,
  không trả hash/mật khẩu trong bất kỳ response nào; tài khoản cũ dùng placeholder được nâng cấp tự động khi seed.
- **Giao diện**: ẩn tab/không hiện nút theo quyền (`data-perm`) — chỉ là lớp trải nghiệm, không thay thế kiểm tra backend.

---

## 7. API sau hoàn thiện (41 endpoint nghiệp vụ / 30 đường dẫn nghiệp vụ; tổng 33 đường dẫn OpenAPI incl. 3 đường dẫn hệ thống `/`, `/api`, `/health`)

| Nhóm | Endpoint | Ghi chú |
|---|---|---|
| Xác thực | `POST /auth/login`, `GET /auth/me`, `POST /auth/logout` | Bắt buộc cho mọi thao tác nghiệp vụ; `/auth/me` trả thêm `menus` (menu theo vai trò, backend quyết định) |
| Tài khoản | `GET /users/`, `POST /users/`, `PATCH /users/{id}` | Chỉ `user.view` / `user.manage` (QUẢN LÝ) |
| Phiếu bảo hành | `POST /warranty-tickets/`, `GET /warranty-tickets/` (lọc `status` — hỗ trợ nhiều trạng thái `A,B` — `q`, `mine`), `GET /{id}`, `GET /code/{code}`, `GET /workboard` (bảng điều khiển theo vai trò), `GET /meta/demo-data`, `GET /meta/workflow`, `GET /stats/summary` (hỗ trợ `mine=1`), `PATCH /{id}/status`, `PATCH /{id}/diagnosis`, `PATCH /{id}/repair` | `PATCH .../status` là State Machine 6 trạng thái kèm thông tin xử lý; `/diagnosis` và `/repair` ghi dữ liệu chuyên môn **không đổi trạng thái**; mỗi dòng danh sách trả kèm `available_actions` / `primary_action` / `action_label` (xem `docs/BAO_CAO_NGHIEP_VU_PHIEU_BAO_HANH.md` và `docs/BAO_CAO_MAN_HINH_CONG_VIEC_THEO_VAI_TRO.md`) |
| Tra cứu | `GET /product-instances/by-serial/{serial}` | Tra cứu bảo hành theo serial |
| Máy đã đăng ký | `GET/POST/PUT/DELETE /product-instances/*` | CRUD theo serial |
| Sản phẩm | `GET/POST/PUT/DELETE /products/*` | Danh mục dòng máy |
| Khách hàng | `GET/POST/PUT/DELETE /customers/*` | Sổ khách hàng |
| AI-01 | `POST /ai/tickets/{id}/classify-error`, `GET /ai/tickets/{id}/results`, `GET /ai/results/{id}`, `PATCH /ai/results/{id}/review`, `GET /ai/config`, `GET /ai/demo/users` | Human-in-the-loop |
| Debug | `GET /debug/check-serial/{serial}`, `POST /debug/check-warranty` | Trace log BR2 |
| Hệ thống | `GET /api`, `GET /health`, `GET /docs`, `GET /redoc`, `GET /` (giao diện web) | Kiểm tra sống/chết + tài liệu OpenAPI |

---

## 8. Cơ sở dữ liệu: 16 bảng (11 core + 5 chatbot)

| Nhóm | Bảng |
|---|---|
| CORE (KT1–KT3) | `users`, `customers`, `products`, `product_instances`, `service_centers`, `error_categories`, `warranty_tickets`, `ticket_status_history`, `repair_logs`, `technician_assignments`, `ai_results` |
| Chatbot (KT4) | `chat_sessions`, `chat_messages`, `chat_handoffs`, `kb_documents`, `kb_chunks` |

- `warranty_tickets` (**28 cột, 10 FK**) lưu cả `rejection_reason`, `rejection_reviewed_*` và
  **`handed_over_at`** — mốc bàn giao cho khách; cùng 10 cột nghiệp vụ mới
  (`diagnosis_note/by/at`, `repair_content/parts/note/by/at`, `handed_over_by`, `handover_note`)
  để tách bạch *khách mô tả* – *AI gợi ý* – *kỹ thuật viên kết luận* – *bàn giao*.
  CSDL cũ được nâng cấp bằng `ADD COLUMN` (không mất dữ liệu) — xem
  `backend/app/services/schema_migration.py` và `docs/BAO_CAO_NGHIEP_VU_PHIEU_BAO_HANH.md`.
- `ticket_status_history` là "sổ nhật ký" của phiếu: từ trạng thái → trạng thái, người thực hiện, ghi chú.
- `ai_results` lưu vết toàn bộ lần gợi ý loại lỗi + `review_status`/`reviewed_by` (kiểm toán AI).
- Bản Postgres tương đương: `database/postgres_schema.sql` (dùng khi bật `DB_BACKEND=postgres`).
- Minh chứng 1 in ra **16 bảng, số cột và số khoá ngoại** của từng bảng, kèm đối chiếu
  `11/11 bảng core` và `5/5 bảng chatbot` ⇒ DAT (PASS).

---

## 9. Giao diện người dùng (tiếng Việt, theo vai trò)

### 9.1. Menu điều hướng: 7 mục nghiệp vụ + 1 mục quản trị — **theo vai trò, do backend quyết định**
| # | Tab | Quyền hiển thị | Việc người dùng làm |
|---|---|---|---|
| 1 | **Tổng quan** | `dashboard.view` | Bảng điều khiển **theo vai trò** (xem §9.2): nhóm công việc, việc cần làm ngay, việc cần chú ý |
| 2 | **Phiếu bảo hành** | `ticket.view` | Wizard tiếp nhận 2 bước + danh sách phiếu + lọc 6 trạng thái + tìm theo mã/serial/khách/SĐT |
| 3 | **Tra cứu bảo hành** | `lookup.view` | Nhập **số sê-ri hoặc mã phiếu** → biết ngay còn/không còn bảo hành, máy đang ở bước nào |
| 4 | **Hỗ trợ xác định lỗi** | `ai.view` | Gợi ý nhóm lỗi cho phiếu, xem mức độ chắc chắn, **xác nhận** hoặc **không dùng** gợi ý |
| 5 | **Khách hàng** | `customer.view` | Sổ khách hàng: thêm/sửa liên hệ, xem khách đang gửi máy nào |
| 6 | **Danh mục máy** | `product.view` | Dòng máy + thời hạn bảo hành mặc định |
| 7 | **Máy đã đăng ký** | `device.view` | Thiết bị theo số sê-ri (ngày mua, hạn bảo hành, chủ sở hữu) |
| – | *Tài khoản nhân viên* | `user.view` | Chỉ QUẢN LÝ: danh sách tài khoản, vai trò, kích hoạt/khoá |

`GET /api/v1/auth/me` trả `menus` (mã màn hình, nhãn, nhóm, quyền tối thiểu) — giao diện chỉ vẽ lại.
Kỹ thuật viên vẫn **được phép đọc** sổ khách hàng/danh mục máy/máy đã đăng ký (đã kiểm chứng ở
`tests/test_auth_rbac.py`), nhưng 3 mục này được xếp vào nhóm phụ **"Tra cứu nội bộ"** để menu chính
chỉ còn việc phục vụ trực tiếp ca kỹ thuật: *Tổng quan · Phiếu bảo hành · Tra cứu bảo hành · Hỗ trợ xác định lỗi*.

Tab không đủ quyền bị ẩn khỏi menu; nếu người dùng gọi thẳng API thì backend trả **403**.

### 9.2. Bảng điều khiển trả lời "Hiện tại tôi cần làm gì?" (theo vai trò)
Toàn bộ nội dung do `GET /api/v1/warranty-tickets/workboard` trả về: tiêu đề, thẻ số liệu, nhóm công việc
(kèm danh sách phiếu + nút hành động được phép), "việc cần làm ngay", "việc cần chú ý" (Quản lý) và ghi chú nghiệp vụ.

| Vai trò | Tiêu đề | Nhóm công việc | Việc cần chú ý |
|---|---|---|---|
| QUẢN LÝ | Tổng quan trung tâm | Mới tiếp nhận · Đang kiểm tra · Đang sửa chữa · Chờ trả máy · Đã hoàn tất (toàn trung tâm) | Có: phiếu thiếu kết luận chẩn đoán / thiếu nội dung sửa chữa / máy đã xong chờ khách nhận — kèm số ngày từ lần cập nhật gần nhất |
| TIẾP NHẬN | Việc tại quầy tiếp nhận | Cần tiếp nhận · Đang xử lý (kiểm tra + sửa chữa) · Chờ trả máy | Không |
| KỸ THUẬT VIÊN | Công việc kỹ thuật | Chờ kiểm tra · Đang kiểm tra · Đang sửa chữa · Chờ hoàn thiện hồ sơ | Không |

- Nút hành động trên từng phiếu do backend quyết định theo **trạng thái + quyền** (ví dụ kỹ thuật viên:
  *Bắt đầu kiểm tra · Cập nhật kết quả kiểm tra · Cập nhật sửa chữa*; tiếp nhận: *Chuyển vào phòng kiểm tra ·
  Xác nhận đã trả máy*; phiếu đã hoàn tất: *Xem phiếu*).
- Chuyển phạm vi `[Việc của tôi] / [Toàn bộ phiếu]` (hoặc `[Toàn bộ hệ thống] / [Việc cần chú ý]` với Quản lý)
  gọi lại backend với `?scope=MINE|ALL`, không lọc giả ở giao diện.

### 9.3. Wizard tiếp nhận **2 bước** (thay cho 9–10 bước rải rác ở 2 tab trước đây)
1. **Bước 1 – Máy của khách**: nhập số sê-ri → *Tra thiết bị*.
   - Máy đã đăng ký ⇒ hiện ngay khách hàng + sản phẩm + hạn bảo hành (chỉ để xem trước, backend vẫn quyết định).
   - Máy chưa có ⇒ mở nhánh "đăng ký máy mới" (khách hàng, ngày mua, thời hạn) và lưu thiết bị.
2. **Bước 2 – Ghi nhận lỗi & tạo phiếu**: mô tả lỗi (tuỳ chọn nhóm lỗi), người tiếp nhận → *Tạo phiếu*.
   Thành công thì mở ngay chi tiết phiếu để in/gửi mã phiếu cho khách.

### 9.4. Chi tiết phiếu (modal)
Thanh tiến trình **5 bước** (`Tiếp nhận → Kiểm tra → Sửa chữa → Chờ trả máy → Hoàn tất`),
thông tin máy/khách/hạn bảo hành, mô tả lỗi, lý do từ chối (nếu có), **lịch sử trạng thái** và
**nút chuyển trạng thái đúng luồng** — chọn người thực hiện trong hộp thoại xác nhận.

### 9.5. Không lộ mã kỹ thuật
- Nhãn người dùng: "Mới tiếp nhận", "Đang kiểm tra", "Đang sửa chữa", "Chờ trả máy", "Đã hoàn tất",
  "Từ chối bảo hành" — không hiện `RECEIVED/REPAIRING/...` trong ngữ cảnh nghiệp vụ.
- Khối AI chỉ hiện: **nhóm lỗi gợi ý (tên tiếng Việt)**, **mức độ chắc chắn (%)**, **giải thích**,
  **câu hỏi cần bổ sung**, **trạng thái xác nhận** — không hiện `ai_function`, `confidence_score`,
  `suggested_category_id`, tên provider/model.
- Thông báo lỗi từ backend là câu tiếng Việt đầy đủ, ví dụ:
  `[STATE MACHINE ERROR] Không được phép chuyển trạng thái từ 'REPAIRING' (Đang sửa chữa) sang 'COMPLETED' (Đã hoàn tất). Các trạng thái hợp lệ tiếp theo: WAITING_RETURN (Chờ trả máy), INSPECTING (Đang kiểm tra).`

---

## 10. AI-01: gợi ý loại lỗi + human-in-the-loop

| Thành phần | Nội dung |
|---|---|
| Chức năng | `POST /api/v1/ai/tickets/{id}/classify-error` gợi ý nhóm lỗi từ mô tả lỗi của khách |
| Guardrail | Loại bỏ PII (tên/điện thoại/email/địa chỉ) khỏi `input_data`; chống prompt injection; kiểm tra nhãn đầu ra thuộc danh mục `error_categories` và ngưỡng chắc chắn |
| Con người quyết định | Kết quả ở `PENDING` **không** tự ghi vào phiếu; chỉ khi MANAGER/RECEPTIONIST bấm xác nhận (APPROVED) mới ghi `warranty_tickets.error_category_id` |
| Không đủ căn cứ | Nhãn `null` + câu hỏi bổ sung; nút xác nhận bị vô hiệu hoá (không thể "duyệt" kết quả rỗng) |
| Kiểm toán | Mọi lần gợi ý/duyệt lưu trong `ai_results` (`ai_function`, `input_data`, `output_data`, `confidence_score`, `review_status`, `reviewed_by`) |
| Phân quyền | `ai.classify` (cả 3 vai trò), `ai.review` (MANAGER + RECEPTIONIST). Kỹ thuật viên duyệt → **403** |

---

## 11. Dữ liệu mẫu (seed) tự nhiên

`tests/seed_data.py` tạo dữ liệu đủ để demo và chụp ảnh, **không dùng mã giả kiểu "test 1, test 2"**:

| Nhóm | Dữ liệu |
|---|---|
| Trung tâm | `Trung tâm Bảo hành Hà Nội` |
| Nhóm lỗi | Lỗi phần cứng bo mạch/nguồn · Lỗi màn hình hiển thị · Lỗi bàn phím & Touchpad |
| Tài khoản | `manager01` / `receptionist01` / `technician01` (mật khẩu demo in ra khi seed, lưu dạng băm) |
| Khách hàng | 3 khách (Nguyễn, Trần, Lê…) có số điện thoại/địa chỉ hợp lý |
| Dòng máy | Laptop Asus, Điện thoại Samsung Galaxy S24 Ultra, Màn hình Dell UltraSharp |
| Máy theo serial | `SN-ASUS-VALID-01`, `SN-SAMS-EXPIRED-02` (hết hạn 2024), `SN-DELL-HAS-OPEN-03`, `SN-ASUS-OWNER-TEST-04`, **`SN-ASUS-2026-0001`** (kiểu mã nhà sản xuất) |
| Phiếu mẫu | `TK-INIT-OPEN-001` — **Đang kiểm tra** (dùng kiểm thử BR3) · **`TK-20260510-0001` — Chờ trả máy** kèm lịch sử 4 bước thật (đã sửa xong, chờ khách tới nhận) |

Nhờ phiếu "Chờ trả máy" có sẵn, bảng điều khiển và bộ lọc trạng thái **có dữ liệu thật để kiểm tra bằng mắt**,
đồng thời minh hoạ đúng vòng đời 6 trạng thái mà không cần thao tác thủ công.

---

## 12. Kiểm thử & minh chứng

### 12.1. Cách chạy
```powershell
.\dev.ps1 evidence     # chạy 25 minh chứng KT2 + KT3, lưu log UTF-8 vào docs\evidence\
.\dev.ps1 check        # cổng kiểm tra trước khi nộp: in bảng tổng hợp + exit code
.\dev.ps1 test         # chạy nhưng không ghi file
.\dev.ps1 seed         # nạp lại dữ liệu mẫu để chụp ảnh sau khi kiểm thử
py -3.12 tests\test_auth_rbac.py   # 13 minh chứng đăng nhập & phân quyền
```
> ⚠️ **Không chạy song song** hai tiến trình minh chứng trên cùng CSDL (script `drop_all/create_all`
> cùng một file SQLite). Đây cũng là lỗi đã gặp khi thao tác nhanh — nay đã ghi rõ trong
> `docs/evidence/README.md`.

### 12.2. Kết quả
| Bộ | Số mục | Kết quả | Exit code |
|---|---|---|---|
| KT2 (nghiệp vụ + State Machine) | 13 | **13/13 PASS** | 0 |
| KT3 (AI-01 + human-in-the-loop) | 12 | **12/12 PASS** | 0 |
| **Tổng KT2 + KT3** | **25** | **25/25 PASS** | 0 |
| Đăng nhập & phân quyền (RBAC) | 13 | **13/13 PASS** | 0 |
| **Vòng đời phiếu bảo hành (Prompt 1)** | 10 (CASE 1–8) | **10/10 PASS** | 0 |
| **Smoke test giao diện phiếu (Node)** | 8 | **8/8 PASS** | 0 |

### 12.5. Bộ kiểm thử vòng đời phiếu (`tests/test_ticket_workflow.py`)
```powershell
.\dev.ps1 workflow                 # chạy 10 kịch bản CASE 1..8 + báo cáo PASS/FAIL
.\dev.ps1 ui                       # smoke test lớp hiển thị (Node, không cần trình duyệt)
py -3.12 tests\test_ticket_workflow.py
```
Bộ này kiểm tra trực tiếp thứ mà KT2/KT3 chưa phủ: **thông tin nghiệp vụ gắn với từng bước chuyển trạng thái**,
**điều kiện hoàn tất**, **quyền theo bước** và **hành động hiển thị theo vai trò** — chi tiết ở
`docs/BAO_CAO_NGHIEP_VU_PHIEU_BAO_HANH.md`.

### 12.3. Danh sách minh chứng KT2 (13)
| # | Nội dung | Kết quả |
|---|---|---|
| 01 | DB tạo được **11 bảng core + 5 bảng chatbot** và ràng buộc FK (16 bảng) | PASS |
| 02 | FastAPI chạy ổn định + Swagger UI/OpenAPI | PASS |
| 03 | CRUD Products và Customers hoạt động tốt | PASS |
| 04 | Tạo phiếu bảo hành hợp lệ (đạt BR1–BR4, trạng thái `RECEIVED`) | PASS |
| 05 | Chặn tạo phiếu khi serial không tồn tại (**BR1**) | PASS |
| 06 | Chặn tạo phiếu khi sản phẩm hết hạn bảo hành (**BR2**) | PASS |
| 07 | Chặn tạo phiếu trùng khi đang có phiếu mở (**BR3**, whitelist gồm `WAITING_RETURN`) | PASS |
| 08 | Chặn tạo phiếu khi sai chủ sở hữu (**BR4**) | PASS |
| 09 | Cập nhật trạng thái đúng State Machine **bắt buộc qua `WAITING_RETURN`** + kiểm tra `handed_over_at` + lưu History | PASS |
| 10 | Chặn nhảy cóc `RECEIVED → COMPLETED` (`[STATE MACHINE ERROR]`) | PASS |
| 11 | **Chặn bỏ qua bước chờ trả máy** `REPAIRING → COMPLETED`: lỗi 400, phiếu vẫn `REPAIRING`, không phát sinh dòng lịch sử | PASS |
| 12 | Debug kiểm tra hạn bảo hành BR2 kèm trace log chi tiết | PASS |
| 13 | CRUD sản phẩm theo serial (thêm/tìm theo serial/cập nhật/xoá an toàn) | PASS |

### 12.4. Danh sách minh chứng KT3 (12)
`KT3-01` mô tả rõ → đúng nhãn (confidence > 0.70) · `KT3-02` lỗi nguồn → đúng nhãn ·
`KT3-03` mô tả mơ hồ → nhãn `null` + câu hỏi bổ sung · `KT3-04` thiếu mô tả → 422 ·
`KT3-05` PII bị loại khỏi `input_data` · `KT3-06` prompt injection bị chặn ·
`KT3-07` prompt system/user + validate đầu ra · `KT3-08` PENDING không tự ghi nhận, TECHNICIAN duyệt → 403 ·
`KT3-09` APPROVED ghi nhãn, **trạng thái phiếu không đổi** · `KT3-10` REJECTED chỉ đổi `review_status` ·
`KT3-11` kết quả AI không có nhãn hợp lệ → chặn APPROVED (400) · `KT3-12` API xem kết quả + lưu vết `ai_results`.
→ **12/12 PASS**.

---

## 13. Checklist tự kiểm (25 mục)

| # | Hạng mục cần kiểm | Cách kiểm | Kết quả |
|---:|---|---|---|
| 1 | 6 trạng thái phiếu đúng mã/nhãn | Đọc `warranty_rules.TICKET_STATUS_LABELS` + API `/stats/summary` | ✔ |
| 2 | Bắt buộc qua `WAITING_RETURN` | Minh chứng 09 (4 bước) | ✔ PASS |
| 3 | `REPAIRING → COMPLETED` bị chặn | Minh chứng 11 (10b) — 400 + `[STATE MACHINE ERROR]` | ✔ PASS |
| 4 | `RECEIVED → COMPLETED` bị chặn | Minh chứng 10 (10a) | ✔ PASS |
| 5 | `handed_over_at` = `null` ở `WAITING_RETURN` | Minh chứng 09 (`Tai WAITING_RETURN: handed_over_at = None`) | ✔ PASS |
| 6 | `handed_over_at` được ghi khi `COMPLETED` | Minh chứng 09 (`Tai COMPLETED: handed_over_at = 2026-…`) | ✔ PASS |
| 7 | Lịch sử trạng thái đủ số dòng (START + 4 bước = 5) | Minh chứng 09 | ✔ PASS |
| 8 | BR3 chặn cả khi phiếu đang `WAITING_RETURN` | Đọc `OPEN_TICKET_STATUSES` + minh chứng 07 | ✔ |
| 9 | 16 bảng, `11/11` core + `5/5` chatbot | Minh chứng 01 | ✔ PASS |
| 10 | 3 vai trò đăng nhập được, nhận đúng danh sách quyền | RBAC 01 | ✔ PASS |
| 11 | Sai mật khẩu / tài khoản lạ → 401, thông báo trung tính | RBAC 02 | ✔ PASS |
| 12 | Mọi API nghiệp vụ không token → 401 | RBAC 03 (16 API) | ✔ PASS |
| 13 | Token giả/sửa chữ ký/tự phong vai trò → 401 | RBAC 04 | ✔ PASS |
| 14 | Token hết hạn → 401 | RBAC 05 | ✔ PASS |
| 15 | Đăng xuất thu hồi token ngay | RBAC 07 | ✔ PASS |
| 16 | Khoá tài khoản → 401 (kể cả token còn hạn) | RBAC 08 | ✔ PASS |
| 17 | Thiếu quyền → 403 (ma trận RBAC) | RBAC 09 | ✔ PASS |
| 18 | Không khai khống `created_by`/`changed_by` | RBAC 10 | ✔ PASS |
| 19 | Chỉ QUẢN LÝ xác nhận TỪ CHỐI bảo hành | RBAC 11 | ✔ PASS |
| 20 | Mật khẩu chỉ lưu dạng băm PBKDF2 + salt riêng | RBAC 12 (+ kiểm tra cột `password_hash`) | ✔ PASS |
| 21 | Vai trò luôn đọc từ CSDL (đổi vai trò có hiệu lực ngay) | RBAC 13 | ✔ PASS |
| 22 | Giao diện: menu 7 mục + tab Tài khoản chỉ hiện với QUẢN LÝ | Đăng nhập 3 tài khoản, quan sát menu | ✔ |
| 23 | Giao diện: thẻ **Chờ trả máy** có số liệu từ seed | Tab Tổng quan sau `.\dev.ps1 seed` | ✔ |
| 24 | Giao diện: wizard 2 bước tạo được phiếu mới | Tab Phiếu bảo hành → "Tiếp nhận máy mới" | ✔ |
| 25 | Log minh chứng tái lập 100% (chạy lại cho cùng kết quả) | `.\dev.ps1 check` (exit code 0) | ✔ PASS |

---

## 14. Rủi ro, giới hạn, hướng phát triển và kết luận

### 14.1. Rủi ro/giới hạn đã biết (và cách xử lý)
| # | Giới hạn | Mức độ | Cách xử lý hiện tại |
|---|---|---|---|
| 1 | CSDL mặc định là **SQLite** (1 file), không phù hợp nhiều người dùng đồng thời | Trung bình | Có sẵn `postgres_schema.sql` + `docker compose` để chuyển Postgres (`. \dev.ps1 up`) |
| 2 | Mật khẩu demo công khai trong `seed_data.py` | Trung bình | Chỉ dùng cho môi trường đồ án; ghi rõ yêu cầu đổi mật khẩu khi triển khai; mật khẩu vẫn lưu dạng băm |
| 3 | Token phiên lưu trong bộ nhớ tiến trình | Trung bình | Phù hợp demo/đồ án; khi triển khai thật nên chuyển sang JWT có chữ ký + refresh token, hoặc bảng `sessions` |
| 4 | AI-01 chạy chế độ `mock` (rule-based) khi không cấu hình provider | Thấp | Đã có guardrail và kiểm thử; đổi `AI_PROVIDER` là dùng model thật, không phải sửa code nghiệp vụ |
| 5 | Kịch bản minh chứng xoá và tạo lại CSDL | Thấp | Đã ghi cảnh báo "không chạy song song", "tắt server demo trước khi chạy minh chứng" |
| 6 | Chưa có phân trang/CSDL đánh chỉ mục cho dữ liệu rất lớn | Thấp | Hiện `skip/limit` cho danh sách; có thể bổ sung index/keyset pagination |

### 14.2. Hướng phát triển tiếp theo
1. **PostgreSQL + Alembic** cho migration có version (hiện tạo bảng bằng `init_db.py`).
2. **Thông báo khách hàng** (SMS/Zalo/Email) khi phiếu chuyển sang `WAITING_RETURN` (mời tới nhận máy)
   và khi `COMPLETED` — đúng nhu cầu thực tế của trung tâm bảo hành.
3. **SLA & báo cáo**: thời gian xử lý trung bình theo từng bước, tỷ lệ từ chối bảo hành, tồn máy chờ trả quá N ngày.
4. **In phiếu/biên nhận** (PDF) và **QR** để khách tra cứu tình trạng máy.
5. **Audit log chi tiết** cho thao tác quản trị (tạo/khoá tài khoản, sửa danh mục).
6. **Chatbot KT4** (RAG) hoàn thiện: nối `chat_sessions/chat_messages/kb_documents` với CSDL nghiệp vụ.

### 14.3. Kết luận
- Hệ thống BaoHanhAI sau đợt hoàn thiện đã **đủ nghiệp vụ để vận hành thật**: vòng đời phiếu 6 trạng thái
  có bước "chờ trả máy", phân quyền 3 vai trò được kiểm tra ở backend, mọi thay đổi đều lưu vết,
  giao diện tiếng Việt đi theo vai trò và **không lộ mã kỹ thuật**.
- Tính đúng đắn được chứng minh bằng **bộ minh chứng tự động tái lập được**: **25/25 PASS** (KT2+KT3)
  và **13/13 PASS** (đăng nhập & phân quyền), chạy bằng một lệnh, có log lưu trong `docs/evidence/`.
- Sự cố mất file giữa chừng đã được xử lý minh bạch (khôi phục + đối chiếu byte-code + chạy lại toàn bộ),
  không ảnh hưởng đến kết quả cuối cùng.

---

# Phụ lục

## A. Lệnh thường dùng
| Việc | Lệnh |
|---|---|
| Cài đặt lần đầu | `.\dev.ps1 install` → `.\dev.ps1 initdb` → `.\dev.ps1 seed` |
| Chạy web + API | `.\dev.ps1 dev` → mở http://127.0.0.1:8000/ (Swagger: `/docs`) |
| Chạy minh chứng | `.\dev.ps1 evidence` / `.\dev.ps1 check` |
| Chạy minh chứng phân quyền | `py -3.12 tests\test_auth_rbac.py` |
| Nạp lại dữ liệu mẫu | `.\dev.ps1 seed` |
| Dọn cache | `.\dev.ps1 clean` |

## B. Tài khoản demo
| Vai trò | Tên đăng nhập | Mật khẩu | Ghi chú |
|---|---|---|---|
| Quản lý | `manager01` | `Manager@123` | Toàn quyền + quản trị tài khoản + từ chối bảo hành |
| Nhân viên tiếp nhận | `receptionist01` | `Reception@123` | Tiếp nhận máy, lập phiếu, xác nhận gợi ý AI, **xác nhận đã trả máy cho khách** |
| Kỹ thuật viên | `technician01` | `Technician@123` | Kiểm tra → chẩn đoán → sửa chữa → chuyển "Chờ trả máy"; không được từ chối bảo hành, không tự xác nhận đã trả máy |

## C. File thay đổi chính trong đợt hoàn thiện
| File | Thay đổi |
|---|---|
| `backend/app/services/warranty_rules.py` | Thêm `WAITING_RETURN`, nhãn tiếng Việt, ma trận chuyển 6 trạng thái, whitelist trạng thái mở |
| `backend/app/crud/warranty_tickets.py` | Chặn `REPAIRING → COMPLETED`, ghi `handed_over_at` **chỉ khi** `COMPLETED`, lưu `ticket_status_history` |
| `backend/app/routers/warranty_tickets.py` | `/stats` bổ sung `waiting_return`; tài liệu endpoint State Machine; guard quyền `ticket.reject` |
| `backend/app/models.py`, `schemas.py`, `database/postgres_schema.sql` | Đồng bộ 6 trạng thái + `handed_over_at` |
| `frontend/index.html`, `app.js`, `styles.css` | Menu theo quyền, 8 thẻ thống kê (có "Chờ trả máy"), wizard 2 bước, tra cứu, chi tiết phiếu 5 bước, nút chuyển trạng thái, badge `WAITING_RETURN`, lớp hiển thị tiếng Việt cho AI |
| `tests/test_scenarios.py` | Thêm bước đăng nhập RBAC; minh chứng 1 (11 core + 5 chatbot); minh chứng 9 luồng 4 bước + `handed_over_at`; thêm minh chứng 10b |
| `tests/seed_data.py` | Thêm serial `SN-ASUS-2026-0001` và phiếu mẫu `TK-20260510-0001` ở trạng thái **Chờ trả máy** |
| `dev.ps1`, `Makefile`, `README.md`, `docs/README.md`, `docs/evidence/README.md` | Cập nhật 24 → **25** minh chứng, mô tả lại nội dung log |
| `docs/evidence/minh_chung_KT2_KT3.txt` | Sinh lại từ lần chạy cuối (UTF-8 BOM) |
| `docs/BAO_CAO_HOAN_THIEN_HE_THONG.md` | Báo cáo này |
| **[Đợt hoàn thiện nghiệp vụ phiếu]** 12 file backend + 3 file frontend + 3 file test | Xem bảng chi tiết ở `docs/BAO_CAO_NGHIEP_VU_PHIEU_BAO_HANH.md` §2 (thông tin xử lý của phiếu, điều kiện hoàn tất, quyền theo bước, màn hình phiếu một trang) |

## E. Đợt hoàn thiện nghiệp vụ phiếu bảo hành (bổ sung sau báo cáo này)

Báo cáo đầy đủ: **`docs/BAO_CAO_NGHIEP_VU_PHIEU_BAO_HANH.md`**.

| Hạng mục | Trước | Sau |
|---|---|---|
| Thông tin xử lý của phiếu | Chỉ có mô tả lỗi + ghi chú ở lịch sử trạng thái | Thêm cột **chẩn đoán** (kết luận của kỹ thuật viên), **nội dung sửa chữa + linh kiện**, **bàn giao** — tách khỏi gợi ý của AI |
| Chuyển bước | Đổi trạng thái (có thể bấm "cho xong") | Mỗi bước **bắt buộc kèm thông tin xử lý**; hoàn tất phiếu phải qua checklist điều kiện |
| Hoàn tất phiếu | Chỉ kiểm tra state machine | Kiểm tra thêm: thiết bị + khách hàng tồn tại, đã có thông tin sửa chữa, lịch sử đủ các bước |
| Quyền | 20 quyền / 3 vai trò | **23 quyền** (+`ticket.diagnose`, `ticket.repair`, `ticket.handover`) — chặn thật ở backend theo từng bước |
| Thông báo lỗi | `detail` kỹ thuật | Thêm `message` tiếng Việt + `hint`; giao diện **không** hiển thị mã kỹ thuật |
| Màn hình phiếu | Modal 6 khối, phải sang màn khác để chẩn đoán/sửa chữa | **Một màn hình**: A–G + nút hành động theo quyền + checklist + lịch sử |
| Danh sách phiếu | Lọc trạng thái, tìm mã/serial/tên | Thêm **tìm theo số điện thoại**, **lọc "Phiếu của tôi"**, cột nhân viên phụ trách và loại lỗi |
| Kiểm thử | 25 minh chứng + 13 RBAC | Thêm **10 kịch bản vòng đời phiếu** + **8 kiểm tra hiển thị** |

## D. Ghi chú về quá trình khôi phục file (để tra cứu)
| Bước | Nội dung |
|---|---|
| 1 | Phát hiện `tests/test_scenarios.py` = 0 byte sau sự cố đầy ổ đĩa |
| 2 | Giải phóng 171 GB (xoá file log rác ở `D:\Nhom06`) |
| 3 | Tìm bản backup: `D:\BaoHanhAI_Project_BACKUP_20260922_100719\scripts\test_scenarios.py` (56.437 byte) |
| 4 | Trích xuất `.pyc` gốc (Python 3.12): frozenset tên bảng, `co_consts`, bảng dòng, byte-code |
| 5 | Viết lại khối "Minh chứng 1" khớp đúng thông điệp log cũ; sửa header import theo cấu trúc `backend/` + `tests/` |
| 6 | So khớp tự động: **byte-code trùng khớp** với `.pyc` (số lệnh, bảng dòng) — khác duy nhất phần thêm mới có chủ đích |
| 7 | Chạy lại: **25/25 PASS**, sinh lại log minh chứng bằng `.\dev.ps1 evidence` |



- Kịch bản minh chứng tự động: KT2 (13 mục), KT3 (12 mục), RBAC (13 mục).
- Tài liệu hoá: README gốc, README tài liệu, README minh chứng, báo cáo này.

### 1.3. Kết quả tóm tắt

| Hạng mục | Trước đợt hoàn thiện | Sau đợt hoàn thiện |
|---|---|---|
| Trạng thái phiếu | 5 (`RECEIVED, INSPECTING, REPAIRING, COMPLETED, REJECTED`) | **6**, thêm `WAITING_RETURN` — bắt buộc trước khi `COMPLETED` |
| `REPAIRING → COMPLETED` | Cho phép | **Chặn** bằng `[STATE MACHINE ERROR]` (phải qua `WAITING_RETURN`) |
| Mốc bàn giao | Ghi mơ hồ khi kết thúc | `handed_over_at` **chỉ ghi khi `COMPLETED`**, ở `WAITING_RETURN` luôn `null` |
| Phân quyền | Ẩn menu ở giao diện | **RBAC backend-side**: 20 quyền / 3 vai trò, chặn 401/403 ở mọi API nghiệp vụ |
| Xác thực | Không | Đăng nhập → token phiên (thu hồi khi logout), mật khẩu băm PBKDF2-HMAC-SHA256 |
| Minh chứng tự động | 24 mục (12 KT2 + 12 KT3) | **25 mục (13 KT2 + 12 KT3)** + 13 mục RBAC riêng |
| Tài khoản demo | Không có | 3 vai trò: `manager01`, `receptionist01`, `technician01` |
