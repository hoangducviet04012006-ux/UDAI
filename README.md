# BaoHanhAI — Hệ thống Quản lý Bảo hành Sản phẩm có tích hợp AI (KT2 + KT3)

Backend **FastAPI** + CSDL **SQLAlchemy** + giao diện web, kèm **AI-01** (gợi ý phân loại lỗi bảo hành
+ human review) và bộ **25 minh chứng tự động** (13 KT2 + 12 KT3).

> Chi tiết nghiệp vụ BR1–BR4, State Machine, thiết kế 11 bảng, đặc tả AI-01, danh sách API…
> xem **[`docs/README.md`](docs/README.md)**.

---

## 1. Cấu trúc dự án

```
BaoHanhAI_Project/
├── backend/                 FastAPI + SQLAlchemy (package `app/`)
│   ├── app/
│   │   ├── config.py            Cấu hình (đọc backend/.env, đường dẫn CSDL tuyệt đối)
│   │   ├── database.py          Kết nối CSDL (SQLite demo / PostgreSQL)
│   │   ├── models.py            16 model (11 core ERD KT1 + 5 nền tảng chatbot KT4)
│   │   ├── schemas.py           Pydantic request/response
│   │   ├── crud/                products, product_instances, customers, warranty_tickets
│   │   ├── routers/             products, product_instances, customers, warranty_tickets, debug, ai
│   │   ├── services/            warranty_rules (BR1–BR4, State Machine) + ai_error_classifier (KT3)
│   │   └── main.py              Entrypoint (mount frontend/, /docs)
│   ├── requirements.txt
│   ├── requirements-ai-chat.txt  Thư viện AI cho chatbot (tùy chọn — `.\dev.ps1 install-chat`)
│   └── .env / .env.example      Biến môi trường (không commit .env)
├── frontend/                Giao diện web (HTML/CSS/JS) — backend phục vụ tại `/`
│   ├── index.html, app.js, styles.css
├── database/                CSDL & schema
│   ├── baohanh_ai.db            SQLite demo (tự sinh lại được)
│   └── postgres_schema.sql      DDL PostgreSQL: 16 bảng (11 core + 5 chatbot), 30 FK, index
├── docs/                    Tài liệu & minh chứng
│   ├── README.md                Mô tả nghiệp vụ KT1–KT3 + hướng dẫn chạy chi tiết
│   ├── DANH_SACH_ANH_MINH_CHUNG_KT3.md   Checklist chụp ảnh minh chứng KT3
│   └── evidence/                Log minh chứng sinh bằng `.\dev.ps1 evidence`
├── tests/                   Kịch bản kiểm thử / minh chứng
│   ├── init_db.py, seed_data.py, test_scenarios.py (25 minh chứng)
├── dev.ps1                  Lệnh chuẩn cho Windows (khuyến nghị)
├── Makefile                 Lệnh tương đương cho Git Bash / Linux / macOS
├── docker-compose.yml       PostgreSQL 16 (tuỳ chọn — mặc định chạy SQLite)
├── .env.example             Mẫu biến môi trường cho Docker Compose
├── .editorconfig, .gitignore
```

---

## 2. Chạy nhanh (Windows / PowerShell)

```powershell
# 1) Cài dependencies (tạo backend\.venv)
.\dev.ps1 install

# 2) Khởi tạo CSDL (16 bảng: 11 core KT1 + 5 nền tảng chatbot KT4) + nạp dữ liệu mẫu
.\dev.ps1 initdb
.\dev.ps1 seed

# 3) Chạy API + giao diện web
.\dev.ps1 dev
```

Mở trình duyệt:

| URL | Nội dung |
|---|---|
| http://127.0.0.1:8000/ | Giao diện web (8 tab theo vai trò: Tổng quan · Phiếu bảo hành · Tra cứu bảo hành · Hỗ trợ xác định lỗi · Khách hàng · Danh mục máy · Máy đã đăng ký · Tài khoản nhân viên) |
| http://127.0.0.1:8000/docs | Swagger UI (nhóm **AI (KT3) - Phân loại lỗi bảo hành**) |
| http://127.0.0.1:8000/redoc | ReDoc |
| http://127.0.0.1:8000/health | `{"status":"healthy","database":"connected"}` |

Nếu máy chưa tạo venv, các lệnh trên tự dùng `py -3.12` (đúng bản đã cài đủ thư viện).
Chạy tay tương đương:

```powershell
py -3.12 tests/init_db.py
py -3.12 tests/seed_data.py
py -3.12 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload   # chạy trong thư mục backend/
```

---

## 3. Lệnh thường dùng

| Lệnh (Windows) | Lệnh (make) | Việc |
|---|---|---|
| `.\dev.ps1 install` | `make install` | Tạo `backend\.venv` + cài `backend\requirements.txt` |
| `.\dev.ps1 install-chat` | `make install-chat` | Cài thư viện AI cho chatbot (`backend\requirements-ai-chat.txt`) — **tùy chọn** |
| `.\dev.ps1 initdb` | `make initdb` | Tạo 16 bảng (11 core + 5 chatbot) trong `database\baohanh_ai.db` |
| `.\dev.ps1 resetdb` | `make resetdb` | Xoá dữ liệu demo → tạo lại bảng → nạp seed (CSDL về trạng thái sạch) |
| `.\dev.ps1 seed` | `make seed` | Nạp dữ liệu mẫu |
| `.\dev.ps1 dev` | `make dev` | Chạy API (reload) |
| `.\dev.ps1 evidence` | `make evidence` | Chạy 25 minh chứng → `docs\evidence\minh_chung_KT2_KT3.txt` |
| `.\dev.ps1 test` | `make test` | Chạy 25 minh chứng (chỉ in màn hình) |
| `.\dev.ps1 check` | `make check` | Chạy minh chứng KT2/KT3 + nghiệp vụ phiếu + màn hình công việc theo vai trò + smoke test giao diện |
| `.\dev.ps1 workflow` | – | Kiểm thử vòng đời phiếu bảo hành (CASE 1..8) — `tests\test_ticket_workflow.py` |
| `.\dev.ps1 workbench` | – | Kiểm thử màn hình công việc theo vai trò (CASE A..H) — `tests\test_role_workbench.py` |
| `.\dev.ps1 ui` | – | Smoke test lớp hiển thị phiếu + bảng điều khiển bằng Node — `tests\smoke_frontend.js` |
| `.\dev.ps1 health` | `make health` | Gọi `/health`, `/api` |
| `.\dev.ps1 tree` | `make tree` | In cây thư mục |
| `.\dev.ps1 clean` | `make clean` | Xoá `__pycache__`, `.pytest_cache` |
| `.\dev.ps1 up/down/logs/psql` | `make up/down/logs/psql` | PostgreSQL 16 bằng Docker |

Kết quả mong đợi của `.\dev.ps1 evidence`:

```
=> TONG KET KT2: 13/13 PASS | FAIL: 0
=> TONG KET KT3: 12/12 PASS | FAIL: 0
- TONG CONG         : 25 | PASS: 25 | FAIL:  0
>>> XAC NHAN: TOAN BO 100% CAC MUC MINH CHUNG KT2 + KT3 DEU DAT (PASS)! <<<
```

---

## 4. CSDL

- **Mặc định (không cần cài gì):** SQLite demo `database/baohanh_ai.db`, dùng **đường dẫn tuyệt đối**
  (khai báo trong `backend/app/config.py`) nên chạy từ `backend/`, `tests/` hay gốc dự án đều trỏ đúng
  một file CSDL. Muốn dựng lại từ đầu: `.\dev.ps1 initdb` + `.\dev.ps1 seed`
  (hoặc `.\dev.ps1 test` — kịch bản minh chứng tự drop/create + seed).
- **PostgreSQL thật (tuỳ chọn):** `.\dev.ps1 up` → nạp `database/postgres_schema.sql`
  → bỏ comment `DATABASE_URL` trong `backend/.env` (hướng dẫn chi tiết ngay trong file đó).

## 5. AI-01 (KT3)

- Provider mặc định `mock` → chạy **offline 100%**, không cần API key (`GET /api/v1/ai/config`).
- AI **chỉ đề xuất**: không tự ghi `error_category_id`, không đổi trạng thái phiếu, không quyết định bảo hành.
- Chỉ khi **RECEPTIONIST/MANAGER** duyệt `APPROVED` thì nhãn mới được ghi vào phiếu (human-in-the-loop).
- Guardrail: loại PII, chặn prompt injection, kiểm tra hợp lệ nhãn/confidence đầu ra.

## 6. Chatbot hỗ trợ bảo hành (KT4) — hiện tại: nền tảng P0 + P1

> ⚠️ **Chưa bật RAG/LangGraph Agent.** Phase P0 + P1 chỉ chuẩn bị nền tảng (cấu hình + schema).
> Endpoint `/api/v1/chatbot` và luồng RAG/Agent sẽ được thêm ở P2–P5.

- **Cấu hình** (`backend/.env`, đều có mặc định nên **không cần khai báo gì** để chạy):
  `CHATBOT_ENABLED` (feature flag), `CHATBOT_PROVIDER` (`mock` = offline 100%),
  `CHATBOT_EMBEDDING_PROVIDER` (`hash` = offline, tất định), `CHATBOT_TOP_K`,
  `CHATBOT_MAX_TURNS`, `CHATBOT_MAX_CONTEXT_CHARS`, `CHATBOT_REQUIRE_OWNER_VERIFICATION`,
  `CHATBOT_KB_DIR`, `CHATBOT_VECTOR_DIR`, `CHATBOT_PROMPT_VERSION`.
- **Thư viện AI tách riêng**: `backend/requirements-ai-chat.txt` (LangChain / LangGraph / FAISS / numpy)
  → cài bằng `.\dev.ps1 install-chat`. Baseline KT2/KT3 **không** cần các thư viện này.
- **CSDL đã sẵn 5 bảng nền tảng**: `kb_documents`, `kb_chunks`, `chat_sessions`, `chat_messages`, `chat_handoffs`.
- **Giữ nguyên nguyên tắc AI-01**: AI **không** quyết định chấp nhận/từ chối bảo hành, không tự ghi
  `error_category_id`/trạng thái phiếu; mọi đề xuất phải qua nhân viên (MANAGER/RECEPTIONIST) duyệt;
  `chat_messages.content` chỉ lưu bản đã khử PII.

## 7. Nguyên tắc giữ dự án chạy được

1. Không sửa tay file CSDL — mọi thay đổi đi qua API hoặc `tests/init_db.py` + `tests/seed_data.py`.
2. Không commit `backend/.env` (chỉ commit `backend/.env.example`).
3. Sau mỗi thay đổi code: chạy `.\dev.ps1 check` để chắc chắn **25/25 minh chứng KT2+KT3**,
   **10/10 kịch bản vòng đời phiếu**, **10/10 kịch bản màn hình công việc theo vai trò** và
   **12/12 kiểm tra lớp hiển thị** vẫn PASS.
4. Thư mục `frontend/` được backend mount tại `/` và `/static` — đổi tên file giao diện phải sửa
   `STATIC_DIR` trong `backend/app/main.py` (đang trỏ `<root>/frontend`).
