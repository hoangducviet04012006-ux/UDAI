"""
Script cap nhat du lieu mau va dat lai mat khau mot lan (One-time deliberate update).
Ap dung cho database/baohanh_ai.db da duoc sao luu.
"""
import sys
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

from app.database import engine, SessionLocal
from app.services.schema_migration import ensure_schema_upgrades
from app.models import User, WarrantyTicket
from app.services.auth_service import hash_password, verify_password

def apply_updates():
    print("[*] 1. Thuc hien nang cap schema an toan...")
    added = ensure_schema_upgrades(engine)
    print(f"    -> Cac cot da them hoac da ton tai: {added}")

    print("[*] 2. Cap nhat tai khoan nguoi dung va dat mat khau thanh 123456...")
    with SessionLocal() as db:
        users = db.query(User).all()
        for u in users:
            # Dat lai mat khau thanh 123456 qua PBKDF2 salt rieng
            u.password_hash = hash_password("123456")
            
            # Cap nhat ho ten tu nhien theo yeu cau E
            if u.username == "manager01":
                u.full_name = "Hoàng Đức Việt"
                u.email = "viet.hoang@baohanhai.vn"
            elif u.username == "receptionist01":
                u.full_name = "Nguyễn Thu Hà"
                u.email = "ha.nguyen@baohanhai.vn"
            elif u.username == "technician01":
                u.full_name = "Trần Minh Tuấn"
                u.email = "tuan.tran@baohanhai.vn"
        
        # Bo sung technician02 neu chua co
        tech2 = db.query(User).filter_by(username="technician02").first()
        if not tech2:
            tech2 = User(
                username="technician02",
                password_hash=hash_password("123456"),
                full_name="Lê Quốc Huy",
                role="TECHNICIAN",
                service_center_id=1,
                email="huy.le@baohanhai.vn",
                phone="0904444444",
                active=True,
            )
            db.add(tech2)
            print("    -> Da them technician02 (Lê Quốc Huy)")

        # Cap nhat device_condition va accessories_accompanying cho cac phieu hien co neu trong
        tickets = db.query(WarrantyTicket).all()
        for t in tickets:
            if not t.device_condition:
                if "Dell" in t.issue_description or (t.product_instance and "Dell" in getattr(t.product_instance.product, "name", "")):
                    t.device_condition = "Máy trầy xước nhẹ mặt lưng, không cấn móp, màn hình nguyên vẹn"
                    t.accessories_accompanying = "Củ sạc Dell Type-C 90W theo máy, cáp Type-C"
                elif "Asus" in t.issue_description or (t.product_instance and "Asus" in getattr(t.product_instance.product, "name", "")):
                    t.device_condition = "Máy còn mới 95%, nguyên tem bảo hành, phím và touchpad hoạt động tốt"
                    t.accessories_accompanying = "Củ sạc Asus 240W, dây nguồn, túi chống sốc"
                else:
                    t.device_condition = "Thân máy nguyên vẹn, có xước dăm theo thời gian sử dụng"
                    t.accessories_accompanying = "Máy trần, không kèm phụ kiện"

        db.commit()
        print("    -> Da commit thay doi thanh cong.")

        # Kiem tra lai dang nhap cua tat ca user
        users = db.query(User).all()
        print(f"\n[*] 3. Kiem tra xac thuc mat khau 123456 tren {len(users)} tai khoan:")
        for u in users:
            ok = verify_password("123456", u.password_hash)
            print(f"    - {u.username:<15} ({u.role:<13}) | {u.full_name:<20} | Mat khau 123456 hop le: {ok}")

if __name__ == "__main__":
    apply_updates()
