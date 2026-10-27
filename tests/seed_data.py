import sys
import os
from datetime import date, datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Cấu trúc mới: tests/ nằm ở gốc dự án, code nằm trong backend/
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

from app.database import SessionLocal, engine, Base
from app.models import (
    ServiceCenter, User, ErrorCategory, Product, Customer,
    ProductInstance, WarrantyTicket, TicketStatusHistory, RepairLog
)
from app.services.auth_service import hash_password, is_legacy_hash

# =====================================================================
# Đợt 7 - Tài khoản demo & mật khẩu khởi tạo
# ---------------------------------------------------------------------
# Mật khẩu dưới đây CHỈ dùng cho môi trường phát triển/đồ án. Khi triển khai
# thật: tạo tài khoản qua màn hình "Tài khoản" và đổi mật khẩu ngay lần đầu.
# Mật khẩu KHÔNG lưu dạng thô trong CSDL, chỉ lưu hash PBKDF2-HMAC-SHA256.
# =====================================================================
DEMO_ACCOUNTS = [
    ("manager01", "Manager@123", "Nguyen Quan Ly", "MANAGER"),
    ("receptionist01", "Reception@123", "Tran Tiep Nhan", "RECEPTIONIST"),
    ("technician01", "Technician@123", "Le Ky Thuat", "TECHNICIAN"),
]
DEMO_PASSWORDS = {username: password for username, password, _, _ in DEMO_ACCOUNTS}


def print_demo_credentials():
    """In bảng tài khoản demo để người dùng biết thông tin đăng nhập (mật khẩu demo, không phải hash)."""
    print("\n[*] TAI KHOAN DANG NHAP (moi vai tro 1 tai khoan):")
    for username, password, full_name, role in DEMO_ACCOUNTS:
        print(f"    - {role:<13} | ten dang nhap: {username:<15} | mat khau: {password}")
    print("    (Chi dung cho moi truong phat trien/demo. Doi mat khau khi trien khai that.)")

def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        print("Dang nap du lieu mau khoi tao...")

        # 1. Trung tâm bảo hành
        sc = db.query(ServiceCenter).first()
        if not sc:
            sc = ServiceCenter(
                name="Trung tam Bao hanh Ha Noi",
                address="123 Cau Giay, Ha Noi",
                phone="02438889999",
                email="bh-hanoi@baohanhai.vn",
                active=True
            )
            db.add(sc)
            db.commit()
            db.refresh(sc)
            print(f"[+] Da tao ServiceCenter: {sc.name}")

        # 2. Danh mục lỗi
        cat1 = db.query(ErrorCategory).filter_by(name="Loi phan cung bo mach / nguon").first()
        if not cat1:
            cat1 = ErrorCategory(name="Loi phan cung bo mach / nguon", description="Thiet bi khong len nguon hoac sap nguon dot ngot")
            cat2 = ErrorCategory(name="Loi man hinh hien thi", description="Man hinh ke soc, diem chet hoac chop nhay")
            cat3 = ErrorCategory(name="Loi ban phim & Touchpad", description="Liet phim, cham touchpad")
            db.add_all([cat1, cat2, cat3])
            db.commit()
            print("[+] Da tao 3 ErrorCategories")

        # 3. Người dùng hệ thống (Users) - mỗi vai trò 1 tài khoản, mật khẩu đã băm
        user_mgr = db.query(User).filter_by(username="manager01").first()
        if not user_mgr:
            user_mgr = User(
                username="manager01",
                password_hash=hash_password(DEMO_PASSWORDS["manager01"]),
                full_name="Nguyen Quan Ly",
                role="MANAGER",
                service_center_id=sc.id,
                email="manager@baohanhai.vn",
                phone="0901111111"
            )
            user_rec = User(
                username="receptionist01",
                password_hash=hash_password(DEMO_PASSWORDS["receptionist01"]),
                full_name="Tran Tiep Nhan",
                role="RECEPTIONIST",
                service_center_id=sc.id,
                email="receptionist@baohanhai.vn",
                phone="0902222222"
            )
            user_tech = User(
                username="technician01",
                password_hash=hash_password(DEMO_PASSWORDS["technician01"]),
                full_name="Le Ky Thuat",
                role="TECHNICIAN",
                service_center_id=sc.id,
                email="technician@baohanhai.vn",
                phone="0903333333"
            )
            db.add_all([user_mgr, user_rec, user_tech])
            db.commit()
            print("[+] Da tao 3 Users (MANAGER, RECEPTIONIST, TECHNICIAN) voi mat khau da bam PBKDF2.")

        # 3b. Nâng cấp tài khoản cũ: bản ghi tạo trước Đợt 7 chỉ có placeholder
        #     "pbkdf2:sha256:dummyhash123" -> cấp lại mật khẩu demo để đăng nhập được.
        upgraded = 0
        for username, password, _full_name, _role in DEMO_ACCOUNTS:
            account = db.query(User).filter_by(username=username).first()
            if account and is_legacy_hash(account.password_hash):
                account.password_hash = hash_password(password)
                account.active = True
                upgraded += 1
        if upgraded:
            db.commit()
            print(f"[+] Da cap nhat mat khau (bam lai) cho {upgraded} tai khoan cu khong co hash hop le.")

        # 4. Khách hàng (Customers)
        c1 = db.query(Customer).filter_by(phone="0912345678").first()
        if not c1:
            c1 = Customer(full_name="Nguyen Van An", phone="0912345678", email="an.nguyen@gmail.com", address="So 10 Hai Ba Trung, HN")
            c2 = Customer(full_name="Tran Thi Binh", phone="0987654321", email="binh.tran@gmail.com", address="So 25 Dong Da, HN")
            c3 = Customer(full_name="Le Hoang Cuong", phone="0901234567", email="cuong.le@gmail.com", address="So 40 Thanh Xuan, HN")
            db.add_all([c1, c2, c3])
            db.commit()
            db.refresh(c1)
            db.refresh(c2)
            db.refresh(c3)
            print("[+] Da tao 3 Customers")
        else:
            c2 = db.query(Customer).filter_by(phone="0987654321").first()
            c3 = db.query(Customer).filter_by(phone="0901234567").first()

        # 5. Sản phẩm (Products)
        p1 = db.query(Product).filter_by(name="Laptop Asus ROG Strix G16").first()
        if not p1:
            p1 = Product(name="Laptop Asus ROG Strix G16", brand="Asus", category="Laptop", warranty_duration_months=24, description="Gaming Laptop RTX 4070")
            p2 = Product(name="Dien thoai Samsung Galaxy S24 Ultra", brand="Samsung", category="Smartphone", warranty_duration_months=12, description="Flagship AI Phone")
            p3 = Product(name="Man hinh Dell UltraSharp U2723QE", brand="Dell", category="Monitor", warranty_duration_months=36, description="4K IPS Black Monitor")
            db.add_all([p1, p2, p3])
            db.commit()
            db.refresh(p1)
            db.refresh(p2)
            db.refresh(p3)
            print("[+] Da tao 3 Products")
        else:
            p2 = db.query(Product).filter_by(name="Dien thoai Samsung Galaxy S24 Ultra").first()
            p3 = db.query(Product).filter_by(name="Man hinh Dell UltraSharp U2723QE").first()

        # 6. Sản phẩm theo serial (Product Instances)
        inst1 = db.query(ProductInstance).filter_by(serial_number="SN-ASUS-VALID-01").first()
        if not inst1:
            inst1 = ProductInstance(
                product_id=p1.id,
                customer_id=c1.id,
                serial_number="SN-ASUS-VALID-01",
                purchase_date=date(2026, 1, 15),
                warranty_end_date=date(2028, 1, 15),
                status="ACTIVE"
            )
            inst2 = ProductInstance(
                product_id=p2.id,
                customer_id=c2.id,
                serial_number="SN-SAMS-EXPIRED-02",
                purchase_date=date(2023, 1, 1),
                warranty_end_date=date(2024, 1, 1),
                status="EXPIRED"
            )
            inst3 = ProductInstance(
                product_id=p3.id,
                customer_id=c3.id,
                serial_number="SN-DELL-HAS-OPEN-03",
                purchase_date=date(2026, 2, 1),
                warranty_end_date=date(2029, 2, 1),
                status="ACTIVE"
            )
            inst4 = ProductInstance(
                product_id=p1.id,
                customer_id=c1.id,
                serial_number="SN-ASUS-OWNER-TEST-04",
                purchase_date=date(2026, 3, 1),
                warranty_end_date=date(2028, 3, 1),
                status="ACTIVE"
            )
            # Serial tu nhien (kieu ma nha san xuat) de minh hoa phieu dang "Cho tra may"
            inst5 = ProductInstance(
                product_id=p1.id,
                customer_id=c1.id,
                serial_number="SN-ASUS-2026-0001",
                purchase_date=date(2026, 5, 10),
                warranty_end_date=date(2028, 5, 10),
                status="ACTIVE"
            )
            db.add_all([inst1, inst2, inst3, inst4, inst5])
            db.commit()
            db.refresh(inst3)
            db.refresh(inst5)
            print("[+] Da tao 5 ProductInstances chuan bi cho cac kich ban kiem thu.")

            rec_user = db.query(User).filter_by(role="RECEPTIONIST").first()
            tech_user = db.query(User).filter_by(role="TECHNICIAN").first()
            existing_ticket = WarrantyTicket(
                ticket_code="TK-INIT-OPEN-001",
                product_instance_id=inst3.id,
                customer_id=c3.id,
                service_center_id=sc.id,
                created_by=rec_user.id if rec_user else 1,
                issue_description="Man hinh Dell bi chap chon cong Type-C",
                status="INSPECTING",
                # [Đợt hoàn thiện nghiệp vụ] Chẩn đoán sơ bộ của kỹ thuật viên (KHÔNG phải gợi ý AI)
                diagnosis_note="Da kiem tra cong Type-C: tiep xuc chap chon, nghi hong chan ket noi.",
                diagnosis_by=tech_user.id if tech_user else None,
                diagnosis_at=datetime(2026, 5, 12, 9, 30),
            )
            db.add(existing_ticket)
            db.commit()
            db.refresh(existing_ticket)

            history = TicketStatusHistory(
                ticket_id=existing_ticket.id,
                from_status="RECEIVED",
                to_status="INSPECTING",
                changed_by=rec_user.id if rec_user else 1,
                note="Chuyen sang kiem tra ky thuat (Da co san trong seed de test BR3)."
            )
            db.add(history)
            db.commit()
            print(f"[+] Da tao san Ticket dang mo: {existing_ticket.ticket_code} (Status: {existing_ticket.status})")

            # Phiếu mẫu thứ hai đang ở WAITING_RETURN: máy đã sửa xong, đang chờ khách tới nhận.
            # Dùng cho thẻ "Chờ trả máy" trên bảng điều khiển và minh họa vòng đời 6 trạng thái.
            waiting_ticket = WarrantyTicket(
                ticket_code="TK-20260510-0001",
                product_instance_id=inst5.id,
                customer_id=c1.id,
                service_center_id=sc.id,
                created_by=rec_user.id if rec_user else 1,
                issue_description="Laptop Asus khong len man hinh, den nguon nhay lien tuc",
                status="WAITING_RETURN",
                # Chẩn đoán + nội dung sửa chữa do KỸ THUẬT VIÊN ghi nhận (tách khỏi gợi ý của AI)
                diagnosis_note="Nguon khong on dinh: IC nguon bi chay, tu dien loc nguon phong ra.",
                diagnosis_by=tech_user.id if tech_user else None,
                diagnosis_at=datetime(2026, 5, 10, 15, 20),
                repair_content="Thay IC nguon va 2 tu dien loc; ve sinh tan nhiet, do lai dien ap 19V on dinh.",
                repair_parts="IC nguon RT8205, tu dien 470uF",
                repair_note="May chay thu 2 gio lien tuc, nhiet do CPU 65 do C - dat yeu cau.",
                repair_by=tech_user.id if tech_user else None,
                repair_at=datetime(2026, 5, 10, 17, 45),
            )
            db.add(waiting_ticket)
            db.commit()
            db.refresh(waiting_ticket)

            waiting_history = [
                TicketStatusHistory(
                    ticket_id=waiting_ticket.id, from_status=None, to_status="RECEIVED",
                    changed_by=rec_user.id if rec_user else 1,
                    note="Khoi tao phieu tiep nhan bao hanh (Dat toan bo BR1-BR4)."
                ),
                TicketStatusHistory(
                    ticket_id=waiting_ticket.id, from_status="RECEIVED", to_status="INSPECTING",
                    changed_by=tech_user.id if tech_user else 1,
                    note="Kiem tra bo mach nguon, xac dinh loi IC nguon."
                ),
                TicketStatusHistory(
                    ticket_id=waiting_ticket.id, from_status="INSPECTING", to_status="REPAIRING",
                    changed_by=tech_user.id if tech_user else 1,
                    note="Thay IC nguon va ve sinh tan nhiet."
                ),
                TicketStatusHistory(
                    ticket_id=waiting_ticket.id, from_status="REPAIRING", to_status="WAITING_RETURN",
                    changed_by=tech_user.id if tech_user else 1,
                    note="May da hoat dong on dinh, dang cho khach den nhan may."
                ),
            ]
            db.add_all(waiting_history)
            # Nhật ký sửa chữa (bảng repair_logs) - lịch sử máy đã được xử lý những gì, ai làm
            if tech_user:
                db.add(
                    RepairLog(
                        ticket_id=waiting_ticket.id,
                        technician_id=tech_user.id,
                        action_description=waiting_ticket.repair_content,
                        parts_used=waiting_ticket.repair_parts,
                        labor_hours=1.5,
                        logged_at=datetime(2026, 5, 10, 17, 45),
                    )
                )
            db.commit()
            print(f"[+] Da tao san Ticket cho tra may: {waiting_ticket.ticket_code} (Status: {waiting_ticket.status})")
            print("[+] Da ghi chan doan + noi dung sua chua + nhat ky repair_logs cho phieu mau.")

        print("\n=> DU LIEU KHOI TAO DA NAP THANH CONG!")
        print_demo_credentials()
    except Exception as e:
        db.rollback()
        print(f"[-] Loi nap du lieu: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    seed()
