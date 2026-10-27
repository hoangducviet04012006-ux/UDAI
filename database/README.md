# database/ — CSDL của BaoHanhAI

| File | Nội dung |
|---|---|
| `baohanh_ai.db` | CSDL **SQLite** dùng cho demo/kiểm thử (được sinh lại tự động, có thể xoá) |
| `postgres_schema.sql` | Script DDL **PostgreSQL**: 16 bảng (11 core KT1 + 5 chatbot KT4), 30 khoá ngoại, index |

## Dựng lại CSDL SQLite demo (nhanh nhất)
```powershell
.\dev.ps1 initdb      # tạo 16 bảng (11 core + 5 chatbot)  (tương đương: py -3.12 tests/init_db.py)
.\dev.ps1 seed        # nạp dữ liệu mẫu (py -3.12 tests/seed_data.py)
```
Hoặc chỉ cần: `.\dev.ps1 test` — kịch bản minh chứng tự `drop_all/create_all` + seed lại CSDL.

Đường dẫn CSDL được tính **tuyệt đối** trong `backend/app/config.py`:

```python
BASE_DIR = <root dự án>
DEFAULT_SQLITE_PATH = <root>/database/baohanh_ai.db
```

⇒ chạy lệnh từ `backend/`, `tests/` hay gốc dự án đều dùng **cùng một file CSDL**
(không còn tình trạng vô tình tạo `baohanh_ai.db` rỗng ở thư mục khác).

## Dùng PostgreSQL 16
```powershell
Copy-Item .env.example .env      # ở gốc dự án
.\dev.ps1 up                     # docker compose up -d db
# nạp schema (từ gốc dự án):
docker compose exec -T db psql -U baohanh -d baohanh_ai -f - < database/postgres_schema.sql
```
Sau đó bỏ comment `DATABASE_URL` trong `backend/.env`:
```ini
DATABASE_URL=postgresql://baohanh:baohanh_dev_pw@localhost:5432/baohanh_ai
```
và chạy lại `.\dev.ps1 seed` để có dữ liệu demo.

## Ghi chú thiết kế
- 11 bảng theo ERD KT1: `service_centers`, `error_categories`, `users`, `customers`, `products`,
  `product_instances`, `warranty_tickets`, `technician_assignments`, `ticket_status_history`,
  `repair_logs`, `ai_results`.
- KT3 **không thêm bảng mới** — dùng `ai_results` + `warranty_tickets.error_category_id` sẵn có.
- **KT4 (P1) thêm 5 bảng nền tảng chatbot**: `kb_documents`, `kb_chunks`, `chat_sessions`,
  `chat_messages`, `chat_handoffs` ⇒ tổng **16 bảng / 30 FK**. Ở P1 **chưa có endpoint chatbot**
  (P2–P5 mới thêm RAG + LangGraph Agent). Vector store của RAG nằm ở `database/vectorstore/`
  (đã `.gitignore`, sinh lại bằng script ingest ở P2).
- Không sửa tay dữ liệu trong `baohanh_ai.db`; hãy dùng API hoặc script seed để dữ liệu luôn tái lập được.
