import sys
import os

# Đảm bảo in UTF-8 không bị lỗi mã hóa trên Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Cấu trúc mới: tests/ nằm ở gốc dự án, code nằm trong backend/
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

from sqlalchemy import inspect
from app.database import engine, Base
import app.models
from app.services.schema_migration import ensure_schema_upgrades

def init_database(reset: bool = False):
    """
    Khởi tạo CSDL demo.

    `reset=True` (tham số dòng lệnh `--reset`): XOÁ toàn bộ bảng rồi tạo lại — dùng khi
    cần đưa CSDL demo về trạng thái sạch (sau khi chạy các bộ kiểm thử có tạo dữ liệu).
    Mặc định `reset=False`: chỉ tạo bảng còn thiếu và bổ sung cột còn thiếu (không mất dữ liệu).
    """
    print("==================================================")
    print("BaoHanhAI - Khoi tao bang Co so du lieu")
    print("==================================================")
    print(f"Ket noi URL: {engine.url}")

    if reset:
        print("[!] Che do --reset: xoa toan bo bang cu roi tao lai tu dau.")
        Base.metadata.drop_all(bind=engine)

    # Tạo tất cả các bảng
    Base.metadata.create_all(bind=engine)

    # [Đợt hoàn thiện nghiệp vụ] Bổ sung cột nghiệp vụ phiếu cho CSDL đã tồn tại
    # (chỉ ADD COLUMN, không mất dữ liệu đang có).
    added_columns = ensure_schema_upgrades(engine)
    if added_columns:
        print(f"\n[+] Da bo sung {len(added_columns)} cot nghiep vu phieu con thieu:")
        for column in added_columns:
            print(f"    - warranty_tickets.{column}")
    else:
        print("\n[OK] Cau truc bang phieu bao hanh da day du (khong can nang cap).")

    # Kiểm tra các bảng đã tạo
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    
    print(f"\n[OK] Da tao thanh cong {len(table_names)} bang trong co so du lieu:")
    for idx, name in enumerate(sorted(table_names), 1):
        columns = inspector.get_columns(name)
        fks = inspector.get_foreign_keys(name)
        print(f" {idx:2d}. Bang: {name:<25} ({len(columns)} cot, {len(fks)} FK)")
        
    print("\nKiem tra toan ven CSDL: HOAN TAT.")

if __name__ == "__main__":
    # Ví dụ: py -3.12 tests/init_db.py --reset   (đưa CSDL demo về trạng thái sạch)
    init_database(reset="--reset" in sys.argv[1:])
