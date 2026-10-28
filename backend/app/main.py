from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from app.config import settings, BASE_DIR
import app.database as app_db
from app.database import Base
import app.models  # Đảm bảo tất cả 11 model được nạp trước khi create_all
from app.services.schema_migration import ensure_schema_upgrades
from app.services.support_schema import backup_before_support_schema
from app.services.auth_service import ensure_demo_accounts_configured
from app.services.warranty_rules import BusinessRuleError
from app.routers import products, customers, warranty_tickets, debug, product_instances, ai, auth, users, chatbot


def __getattr__(name: str):
    """Ủy quyền động engine và SessionLocal sang app.database để tránh giữ tham chiếu cũ khi test cách ly."""
    if name in ("engine", "SessionLocal"):
        return getattr(app_db, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lấy engine và SessionLocal động từ app.database để đảm bảo khi test
    # chạy trên CSDL tạm và override engine/SessionLocal, lifespan KHÔNG BAO GIỜ chạm vào CSDL thật.
    active_engine = app_db.engine
    active_session_maker = app_db.SessionLocal

    # Khởi tạo toàn bộ 11 bảng nếu chưa tồn tại
    backup_before_support_schema(active_engine)
    Base.metadata.create_all(bind=active_engine)
    # [Đợt hoàn thiện nghiệp vụ] Thêm các cột nghiệp vụ phiếu còn thiếu vào CSDL đang dùng
    # (chỉ ADD COLUMN, KHÔNG xoá/đổi cột cũ -> dữ liệu hiện có không bị hỏng)
    added = ensure_schema_upgrades(active_engine)
    if added:
        print(f"[schema] Da bo sung {len(added)} cot nghiep vu phieu: {', '.join(added)}")

    # [Khắc phục đăng nhập CSDL cũ] Nâng cấp tài khoản demo có hash giả sang PBKDF2 chuẩn
    # (chỉ nâng cấp bản ghi có hash giả, không chạm mật khẩu người dùng đã đổi)
    try:
        with active_session_maker() as db:
            upgraded_accounts = ensure_demo_accounts_configured(db)
            if upgraded_accounts:
                print(f"[auth] Da nang cap mat khau cho {upgraded_accounts} tai khoan demo tu CSDL cu.")
    except Exception as exc:
        print(f"[auth] Canh bao kiem tra tai khoan demo: {exc}")
    yield

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
    Hệ thống Quản lý Bảo hành Sản phẩm có tích hợp AI (BaoHanhAI) - Giai đoạn KT2 & KT3.
    
    Các tính năng chính:
    * **CRUD Danh mục & Sản phẩm** (`products`)
    * **CRUD Khách hàng** (`customers`)
    * **CRUD & Quy trình Tiếp nhận Phiếu bảo hành** (`warranty_tickets`)
    * **Quản lý chuyển trạng thái theo State Machine (6 trạng thái)**:
      - Luồng sửa chữa: TIẾP NHẬN (RECEIVED) -> KIỂM TRA (INSPECTING) -> SỬA CHỮA (REPAIRING) -> HOÀN TẤT (COMPLETED) -> ĐÃ TRẢ MÁY (RETURNED).
      - Luồng từ chối: KIỂM TRA (INSPECTING) -> TỪ CHỐI (REJECTED) -> ĐÃ TRẢ MÁY (RETURNED).
    * **Debug kiểm tra hạn bảo hành BR2** (Nội dung KT2)
    * **AI-01: Gợi ý phân loại lỗi bảo hành** + Human-in-the-loop review (`ai`) - Nội dung KT3
    """,
    lifespan=lifespan
)

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# =====================================================================
# [AUD-24] Chuẩn hóa lỗi ràng buộc dữ liệu (IntegrityError) thành JSON.
# ---------------------------------------------------------------------
# Trước đây lỗi FK / NOT NULL / UNIQUE thoát ra thành HTTP 500 dạng
# plain text "Internal Server Error" nên frontend không đọc được `detail`.
# Ở đây chỉ bắt DUY NHẤT IntegrityError (lỗi dữ liệu đã biết) -> 409 JSON.
# Các lỗi lập trình khác KHÔNG bị "che": vẫn do FastAPI xử lý như cũ.
# =====================================================================
@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": "Dữ liệu không thể thực hiện vì đang được sử dụng ở nơi khác.",
            "message": "Dữ liệu này đang được dùng ở nơi khác nên chưa thể thực hiện. Vui lòng kiểm tra lại.",
            "error_code": "DATA_IN_USE",
        },
    )

# =====================================================================
# [Đợt hoàn thiện nghiệp vụ] Chuẩn hóa lỗi NGHIỆP VỤ thành câu tiếng Việt.
# ---------------------------------------------------------------------
# `detail` giữ nguyên nội dung kỹ thuật (các minh chứng KT2/KT3 đang trích trường này),
# còn giao diện đọc `message` (tiếng Việt, không có mã kỹ thuật) để hiển thị cho nhân viên.
# Ngoài ra trả thêm `error_code` và `hint` (việc cần làm tiếp theo).
# =====================================================================
@app.exception_handler(BusinessRuleError)
async def business_rule_error_handler(request: Request, exc: BusinessRuleError):
    content = {
        "detail": exc.detail,
        "message": exc.user_message,
        "error_code": exc.error_code,
    }
    if exc.hint:
        content["hint"] = exc.hint
    return JSONResponse(status_code=exc.status_code, content=content)

# Đăng ký các router
app.include_router(auth.router)                # Đợt 7: đăng nhập / phiên làm việc
app.include_router(users.router)               # Đợt 7: quản trị tài khoản nhân viên
app.include_router(products.router)
app.include_router(product_instances.router)
app.include_router(customers.router)
app.include_router(warranty_tickets.router)
app.include_router(debug.router)
app.include_router(ai.router)
app.include_router(chatbot.router)

@app.get('/support', include_in_schema=False)
def support_page():
    return FileResponse(os.path.join(BASE_DIR, 'frontend', 'support.html'))

# Phục vụ giao diện web trong frontend/ (cấu trúc mới: frontend/ tách khỏi backend/)
STATIC_DIR = os.path.join(BASE_DIR, "frontend")
os.makedirs(STATIC_DIR, exist_ok=True)

# Đảm bảo trình duyệt luôn tải file HTML, JS, CSS mới nhất, không dùng cache cũ
@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path in ("/", "/support") or path.startswith(("/static", "/api/v1/chatbot")):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", tags=["Giao diện Web"])
def web_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        response = FileResponse(index_file)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    return {
        "app_name": settings.app_name,
        "version": settings.app_version,
        "status": "ONLINE",
        "docs_url": "/docs"
    }

@app.get("/api", tags=["Hệ thống"])
def api_root():
    return {
        "app_name": settings.app_name,
        "version": settings.app_version,
        "status": "ONLINE",
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "message": "BaoHanhAI Backend API đang hoạt động ổn định."
    }

@app.get("/health", tags=["Hệ thống"])
def health_check():
    return {"status": "healthy", "database": "connected"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
