from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from app.config import settings, BASE_DIR
from app.database import engine, Base
import app.models  # Đảm bảo tất cả 11 model được nạp trước khi create_all
from app.services.schema_migration import ensure_schema_upgrades
from app.services.warranty_rules import BusinessRuleError
from app.routers import products, customers, warranty_tickets, debug, product_instances, ai, auth, users

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Khởi tạo toàn bộ 11 bảng nếu chưa tồn tại
    Base.metadata.create_all(bind=engine)
    # [Đợt hoàn thiện nghiệp vụ] Thêm các cột nghiệp vụ phiếu còn thiếu vào CSDL đang dùng
    # (chỉ ADD COLUMN, KHÔNG xoá/đổi cột cũ -> dữ liệu hiện có không bị hỏng)
    added = ensure_schema_upgrades(engine)
    if added:
        print(f"[schema] Da bo sung {len(added)} cot nghiep vu phieu: {', '.join(added)}")
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
    * **Ràng buộc nghiệp vụ nghiêm ngặt**: BR1 (Tồn tại Serial), BR2 (Còn hạn BH), BR3 (Không trùng phiếu mở), BR4 (Khớp chủ sở hữu)
    * **Quản lý chuyển trạng thái theo State Machine (6 trạng thái)**: RECEIVED -> INSPECTING -> REPAIRING -> WAITING_RETURN -> COMPLETED (hoặc INSPECTING -> REJECTED); bắt buộc đi qua WAITING_RETURN trước khi hoàn tất
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

# Phục vụ giao diện web trong frontend/ (cấu trúc mới: frontend/ tách khỏi backend/)
STATIC_DIR = os.path.join(BASE_DIR, "frontend")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", tags=["Giao diện Web"])
def web_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
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
