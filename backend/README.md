# backend/ — FastAPI + SQLAlchemy (BaoHanhAI KT2 + KT3)

## Chạy
```powershell
# từ gốc dự án
.\dev.ps1 dev                      # tương đương: cd backend; py -3.12 -m uvicorn app.main:app --port 8000 --reload
```
- API docs: http://127.0.0.1:8000/docs
- Giao diện web: http://127.0.0.1:8000/ (file lấy từ `../frontend`)

## Thành phần
| File / thư mục | Vai trò |
|---|---|
| `app/main.py` | Entrypoint FastAPI, CORS, mount giao diện `../frontend`, đăng ký 6 router |
| `app/config.py` | `Settings` + `BASE_DIR`/`BACKEND_DIR`; **nạp `backend/.env` bằng `load_dotenv`**; đường dẫn SQLite demo tuyệt đối |
| `app/database.py` | Engine + `SessionLocal` + `Base` + dependency `get_db` |
| `app/models.py` | 16 model: 11 model core theo ERD KT1 (không đổi) + 5 model nền tảng chatbot KT4 |
| `app/schemas.py` | Pydantic v2 request/response (gồm schema KT3 `AIClassification*`, `AIReview*`) |
| `app/crud/` | Truy cập dữ liệu: products, product_instances, customers, warranty_tickets |
| `app/routers/` | `/api/v1/products`, `/product-instances`, `/customers`, `/warranty-tickets`, `/debug`, `/ai` |
| `app/services/warranty_rules.py` | BR1–BR4, State Machine, trace debug BR2 |
| `app/services/ai_error_classifier.py` | KT3: `SYSTEM_PROMPT`, `USER_PROMPT_TEMPLATE`, provider (mock/openai), guardrail PII + injection, `validate_ai_output`, human review |

## Biến môi trường
Copy `backend/.env.example` → `backend/.env` rồi chỉnh khi cần.
Không khai báo gì thêm cũng chạy được (SQLite demo + AI provider `mock`).

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `DATABASE_URL` | (trống → SQLite `database/baohanh_ai.db`) | Đổi sang PostgreSQL khi cần |
| `DEBUG` | `True` | Cờ debug ứng dụng |
| `AI_PROVIDER` | `mock` | `mock` / `auto` / `openai` |
| `AI_MODEL`, `AI_API_KEY`, `AI_BASE_URL` | — | Chỉ dùng khi gọi provider thật (**không commit key**) |
| `AI_MAX_CONFIDENCE_WHEN_NULL` | `0.40` | Ngưỡng confidence tối đa khi AI không chọn được nhãn |
| `CHATBOT_ENABLED` | `True` | [KT4/P0] Feature flag chatbot (`false` → 503, không ảnh hưởng KT2/KT3) |
| `CHATBOT_PROVIDER` | theo `AI_PROVIDER` (`mock`) | Provider LLM của chatbot: `mock` (offline) / `auto` / `openai` |
| `CHATBOT_EMBEDDING_PROVIDER` | `hash` | Embedding cho RAG: `hash` (offline, tất định) / `openai` |
| `CHATBOT_TOP_K`, `CHATBOT_MAX_TURNS`, `CHATBOT_MAX_CONTEXT_CHARS` | `4`, `20`, `6000` | Truy hồi & kiểm soát chi phí |
| `CHATBOT_REQUIRE_OWNER_VERIFICATION` | `True` | Bắt buộc xác minh chủ sở hữu (BR4) trước khi trả thông tin phiếu |
| `CHATBOT_KB_DIR`, `CHATBOT_VECTOR_DIR` | `<root>/database/knowledge`, `<root>/database/vectorstore` | Knowledge base & vector store cục bộ |
| `CHATBOT_PROMPT_VERSION` | `chatbot_v1` | Phiên bản prompt lưu vào `chat_messages.prompt_version` |

Thư viện AI cho chatbot nằm **riêng** ở `backend/requirements-ai-chat.txt` (LangChain / LangGraph /
FAISS / numpy — **tùy chọn**): cài bằng `.\dev.ps1 install-chat`. Baseline KT2/KT3 **không** cần
các thư viện này, chatbot vẫn chạy offline với provider `mock`.

## Kiểm thử
Minh chứng nằm ở tầng gốc: `tests/test_scenarios.py` (24 case, tự drop/create + seed CSDL).
```powershell
.\dev.ps1 check        # hoặc: py -3.12 tests/test_scenarios.py
```

## Quy ước
- Không tạo bảng CSDL trong `lifespan` ngoài `Base.metadata.create_all` hiện có (dự án demo dùng SQLite/SQL script).
- Nghiệp vụ BR chỉ nằm trong `app/services/` và `app/crud/` — router không chứa logic nghiệp vụ.
- Sau khi sửa code: chạy lại `.\dev.ps1 check` (24/24 PASS) trước khi commit/nộp bài.
