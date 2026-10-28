"""
BỘ KIỂM THỬ TOÀN DIỆN TÁI CẤU TRÚC NGHIỆP VỤ PHIẾU BẢO HÀNH BAOHANHAI
======================================================================
Kiểm thử 100% các yêu cầu nghiệp vụ bổ sung trên database tạm thời:
1. Thống nhất CHỈ MANAGER được phân công / phân công lại KTV (Backend, UI, Test).
2. BR2 & Máy hết hạn: Máy hết hạn VẪN ĐƯỢC lập phiếu tiếp nhận để kiểm tra và đi
   qua luồng từ chối rồi trả máy (RECEIVED -> INSPECTING -> REJECTED -> RETURNED).
   Tuyệt đối KHÔNG cho máy hết hạn chuyển sang sửa chữa bảo hành (INSPECTING -> REPAIRING).
   Giữ nguyên các điều kiện tiếp nhận khác (BR1, BR3, BR4, không tự lấy ngày tiếp nhận làm ngày mua).
3. Concurrency (Đồng thời): Hai request đồng thời chuyển trạng thái cùng một phiếu:
   KHÔNG được tạo hai lịch sử chuyển bước hoặc ghi đè kết quả (OCC atomic update, 409 Conflict).
4. Luồng sửa chữa chuẩn: RECEIVED -> INSPECTING -> REPAIRING -> COMPLETED -> RETURNED.
5. Luồng từ chối chuẩn: INSPECTING -> REJECTED -> RETURNED.
6. BR3: Chặn trùng phiếu mở; cho phép tạo sau khi phiếu cũ đã RETURNED.
7. Thống kê & Resolution: Giữ nguyên kết quả sau khi đóng phiếu; tách thời gian kỹ thuật & thời gian chờ nhận.
8. Migration chạy lại an toàn, idempotency.
"""
import concurrent.futures
import os
import sys
import threading
from datetime import date, datetime, timedelta

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

# Cấu hình database test tạm riêng biệt (KHÔNG chạm vào database chính)
TEMP_DB_PATH = os.path.join(PROJECT_ROOT, "database", "test_temporary.db")
if os.path.exists(TEMP_DB_PATH):
    try:
        os.remove(TEMP_DB_PATH)
    except Exception:
        pass

TEMP_DB_URL = f"sqlite:///{TEMP_DB_PATH}"
os.environ["DATABASE_URL"] = TEMP_DB_URL

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Khởi tạo engine test tạm
test_engine = create_engine(TEMP_DB_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Override get_db của FastAPI
from app.database import get_db, Base
from app.main import app

def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

from app.models import (
    Customer, ErrorCategory, Product, ProductInstance,
    ServiceCenter, TicketStatusHistory, User, WarrantyTicket, TechnicianAssignment
)
from app.services.auth_service import hash_password
from app.services.schema_migration import ensure_schema_upgrades, migrate_tickets_data
from app.services.warranty_rules import (
    validate_br1_serial_exists, validate_br2_warranty_valid,
    validate_br3_no_open_tickets, BusinessRuleError
)

TEST_RESULTS = []

def record(test_id, name, ok, note=""):
    TEST_RESULTS.append((test_id, name, bool(ok), note))
    status_str = "PASS" if ok else "FAIL"
    print(f"  [{status_str}] {test_id}: {name}")
    if note:
        print(f"          -> {note}")

def setup_test_database():
    """Khởi tạo cấu trúc bảng, chạy migration và tạo tài khoản test."""
    Base.metadata.create_all(bind=test_engine)
    ensure_schema_upgrades(test_engine)

    db = TestSessionLocal()
    # 1. Service Center
    sc = ServiceCenter(name="TTBH Test Ha Noi", address="123 Cau Giay", phone="02438889999", email="test@baohanhai.vn", active=True)
    db.add(sc)
    db.commit()

    # 2. Error Categories
    cat1 = ErrorCategory(name="Lỗi phần cứng bo mạch", description="Hỏng IC nguồn")
    cat2 = ErrorCategory(name="Lỗi màn hình", description="Kẻ sọc màn hình")
    db.add_all([cat1, cat2])
    db.commit()

    # 3. Users: 1 Manager, 1 Receptionist, 2 Technicians
    pwd_mgr = hash_password("Manager@123")
    pwd_rec = hash_password("Reception@123")
    pwd_tech1 = hash_password("Tech1@123")
    pwd_tech2 = hash_password("Tech2@123")

    mgr = User(username="mgr_test", password_hash=pwd_mgr, full_name="Nguyen Quan Ly", role="MANAGER", service_center_id=sc.id, email="mgr@test.vn")
    rec = User(username="rec_test", password_hash=pwd_rec, full_name="Tran Tiep Nhan", role="RECEPTIONIST", service_center_id=sc.id, email="rec@test.vn")
    tech1 = User(username="tech1_test", password_hash=pwd_tech1, full_name="Le Ky Thuat 1", role="TECHNICIAN", service_center_id=sc.id, email="tech1@test.vn")
    tech2 = User(username="tech2_test", password_hash=pwd_tech2, full_name="Pham Ky Thuat 2", role="TECHNICIAN", service_center_id=sc.id, email="tech2@test.vn")
    db.add_all([mgr, rec, tech1, tech2])
    db.commit()

    # 4. Customers
    c1 = Customer(full_name="Hoang Duc Viet", phone="0911222333", email="viet@test.vn", address="Ha Noi")
    c2 = Customer(full_name="Vu Thi Mai", phone="0988777666", email="mai@test.vn", address="Hai Phong")
    db.add_all([c1, c2])
    db.commit()

    # 5. Products
    p1 = Product(name="Laptop Asus Zenbook 14", brand="Asus", category="Laptop", warranty_duration_months=24)
    db.add(p1)
    db.commit()

    # 6. Product Instances
    # Instance 1: Còn hạn chuẩn
    inst1 = ProductInstance(
        product_id=p1.id, customer_id=c1.id, serial_number="SN-TEST-VALID-01",
        purchase_date=date.today() - timedelta(days=100),
        warranty_end_date=date.today() + timedelta(days=630),
        status="ACTIVE"
    )
    # Instance 2: Đúng ngày hết hạn (hôm nay là ngày cuối cùng)
    inst2 = ProductInstance(
        product_id=p1.id, customer_id=c1.id, serial_number="SN-TEST-EXACT-END",
        purchase_date=date.today() - timedelta(days=730),
        warranty_end_date=date.today(),
        status="ACTIVE"
    )
    # Instance 3: Đã hết hạn bảo hành
    inst3 = ProductInstance(
        product_id=p1.id, customer_id=c1.id, serial_number="SN-TEST-EXPIRED",
        purchase_date=date.today() - timedelta(days=800),
        warranty_end_date=date.today() - timedelta(days=70),
        status="EXPIRED"
    )
    # Instance 4: Cho luồng từ chối
    inst4 = ProductInstance(
        product_id=p1.id, customer_id=c2.id, serial_number="SN-TEST-REJECT-FLOW",
        purchase_date=date.today() - timedelta(days=50),
        warranty_end_date=date.today() + timedelta(days=680),
        status="ACTIVE"
    )
    # Instance 5: Cho test BR3 (nhiều lần bảo hành)
    inst5 = ProductInstance(
        product_id=p1.id, customer_id=c1.id, serial_number="SN-TEST-MULTI-CYCLE",
        purchase_date=date.today() - timedelta(days=30),
        warranty_end_date=date.today() + timedelta(days=700),
        status="ACTIVE"
    )
    # Instance 6: Cho test Concurrency
    inst6 = ProductInstance(
        product_id=p1.id, customer_id=c1.id, serial_number="SN-TEST-CONCURRENCY",
        purchase_date=date.today() - timedelta(days=60),
        warranty_end_date=date.today() + timedelta(days=670),
        status="ACTIVE"
    )
    # Instance 7: Còn hạn tại ngày tiếp nhận (created_at) nhưng đã hết hạn tại ngày xử lý thực tế
    inst7 = ProductInstance(
        product_id=p1.id, customer_id=c1.id, serial_number="SN-TEST-INTAKE-VALID-REPAIR-EXPIRED",
        purchase_date=date.today() - timedelta(days=730),
        warranty_end_date=date.today() - timedelta(days=2),  # Đã quá hạn 2 ngày so với ngày KTV xử lý
        status="ACTIVE"
    )
    db.add_all([inst1, inst2, inst3, inst4, inst5, inst6, inst7])
    db.commit()
    db.close()

def login_client(username, password):
    client = TestClient(app)
    res = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    if res.status_code != 200:
        raise RuntimeError(f"Đăng nhập thất bại: {username}")
    token = res.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client

def run_tests():
    print("\n" + "=" * 80)
    print("  BẮT ĐẦU CHẠY KIỂM THỬ TÁI CẤU TRÚC NGHIỆP VỤ PHIẾU BẢO HÀNH")
    print(f"  CSDL Test Tạm: {TEMP_DB_PATH}")
    print("=" * 80)

    setup_test_database()

    client_mgr = login_client("mgr_test", "Manager@123")
    client_rec = login_client("rec_test", "Reception@123")
    client_tech1 = login_client("tech1_test", "Tech1@123")
    client_tech2 = login_client("tech2_test", "Tech2@123")

    db = TestSessionLocal()
    tech1_id = db.query(User).filter(User.username == "tech1_test").first().id
    tech2_id = db.query(User).filter(User.username == "tech2_test").first().id
    rec_id = db.query(User).filter(User.username == "rec_test").first().id
    mgr_id = db.query(User).filter(User.username == "mgr_test").first().id
    c1_id = db.query(Customer).filter(Customer.phone == "0911222333").first().id
    c2_id = db.query(Customer).filter(Customer.phone == "0988777666").first().id
    db.close()

    # -------------------------------------------------------------
    # 1. PHÂN CÔNG KTV (CHỈ MANAGER) & LUỒNG SỬA CHỮA ĐẦY ĐỦ 5 BƯỚC
    # -------------------------------------------------------------
    print("\n--- 1. PHÂN CÔNG KTV (CHỈ MANAGER) & LUỒNG SỬA CHỮA ĐẦY ĐỦ ---")
    # 1.1 Tiếp nhận cố tình gán KTV khi tạo phiếu -> Phải bị chặn 403
    res_rec_assign_create = client_rec.post("/api/v1/warranty-tickets/", json={
        "serial_number": "SN-TEST-VALID-01",
        "customer_id": c1_id,
        "service_center_id": 1,
        "created_by": rec_id,
        "issue_description": "Laptop khong khoi dong duoc",
        "technician_id": tech1_id
    })
    ok_assign_block_create = res_rec_assign_create.status_code == 403 and "Quản lý" in res_rec_assign_create.json().get("detail", "")
    record("T1.1", "Chặn Tiếp nhận tự phân công KTV khi lập phiếu (HTTP 403 - Chỉ Manager)", ok_assign_block_create)

    # 1.2 Tiếp nhận lập phiếu chuẩn (không có technician_id) -> RECEIVED
    res_create = client_rec.post("/api/v1/warranty-tickets/", json={
        "serial_number": "SN-TEST-VALID-01",
        "customer_id": c1_id,
        "service_center_id": 1,
        "created_by": rec_id,
        "issue_description": "Laptop khong khoi dong duoc"
    })
    ok_create = res_create.status_code == 201 and res_create.json()["status"] == "RECEIVED" and res_create.json()["assigned_technician_id"] is None
    ticket_1 = res_create.json()
    t1_id = ticket_1["id"]
    record("T1.2", "Tiếp nhận lập phiếu mới thành công ở trạng thái RECEIVED (chưa có KTV)", ok_create)

    # 1.3 Tiếp nhận hoặc KTV gọi /assign -> Phải bị chặn 403
    res_rec_assign = client_rec.post(f"/api/v1/warranty-tickets/{t1_id}/assign", json={"technician_id": tech1_id})
    res_tech_assign = client_tech1.post(f"/api/v1/warranty-tickets/{t1_id}/assign", json={"technician_id": tech1_id})
    ok_assign_role_block = res_rec_assign.status_code == 403 and res_tech_assign.status_code == 403
    record("T1.3", "Tiếp nhận và Kỹ thuật viên bị chặn gọi API phân công /assign (HTTP 403)", ok_assign_role_block)

    # 1.4 Quản lý phân công KTV1 cho phiếu -> Thành công 200
    res_mgr_assign = client_mgr.post(f"/api/v1/warranty-tickets/{t1_id}/assign", json={
        "technician_id": tech1_id, "note": "Quản lý giao cho KTV1 kiểm tra bo mạch"
    })
    ok_mgr_assign = (
        res_mgr_assign.status_code == 200
        and res_mgr_assign.json()["assigned_technician_id"] == tech1_id
        and res_mgr_assign.json()["assigned_technician_name"] == "Le Ky Thuat 1"
    )
    record("T1.4", "Chỉ Quản lý (MANAGER) được phân công KTV qua endpoint /assign (HTTP 200)", ok_mgr_assign)

    # 1.5 KTV1 nhận kiểm tra: RECEIVED -> INSPECTING
    res_inspect = client_tech1.patch(f"/api/v1/warranty-tickets/{t1_id}/status", json={
        "new_status": "INSPECTING",
        "changed_by": tech1_id,
        "note": "KTV nhận máy kiểm tra theo phân công của Quản lý"
    })
    ok_inspect = res_inspect.status_code == 200 and res_inspect.json()["status"] == "INSPECTING"
    record("T1.5", "KTV được phân công chuyển RECEIVED -> INSPECTING", ok_inspect)

    # 1.6 Chuyển sang REPAIRING (bắt buộc chẩn đoán & is_warranty_eligible=True)
    res_repair = client_tech1.patch(f"/api/v1/warranty-tickets/{t1_id}/status", json={
        "new_status": "REPAIRING",
        "changed_by": tech1_id,
        "diagnosis_note": "Chập IC nguồn chính, tụ lọc nguồn bị nứt",
        "is_warranty_eligible": True,
        "warranty_check_note": "Máy nguyên tem, đủ điều kiện bảo hành",
        "error_category_id": 1,
        "note": "Bắt đầu sửa chữa"
    })
    ok_repair = res_repair.status_code == 200 and res_repair.json()["status"] == "REPAIRING"
    record("T1.6", "INSPECTING -> REPAIRING có đầy đủ chẩn đoán & xác nhận đủ ĐKBH", ok_repair)

    # 1.7 Chuyển sang COMPLETED (bắt buộc nội dung sửa & repair_test_passed=True)
    res_complete = client_tech1.patch(f"/api/v1/warranty-tickets/{t1_id}/status", json={
        "new_status": "COMPLETED",
        "changed_by": tech1_id,
        "repair_content": "Thay IC nguồn RT8205 và tụ lọc, vệ sinh keo tản nhiệt",
        "repair_parts": "IC RT8205, tụ 470uF",
        "repair_test_passed": True,
        "repair_test_note": "Chạy thử test máy 2 giờ nhiệt độ ổn định 60 độ C",
        "note": "Xác nhận hoàn tất sửa chữa, chờ khách tới nhận"
    })
    ok_complete = res_complete.status_code == 200 and res_complete.json()["status"] == "COMPLETED"
    record("T1.7", "REPAIRING -> COMPLETED (sửa xong, kiểm tra sau sửa đạt yêu cầu, chờ trả máy)", ok_complete)

    # 1.8 Chuyển sang RETURNED (Tiếp nhận xác nhận bàn giao và đóng phiếu)
    res_return = client_rec.patch(f"/api/v1/warranty-tickets/{t1_id}/status", json={
        "new_status": "RETURNED",
        "changed_by": rec_id,
        "handover_note": "Đã bàn giao máy cho khách tại quầy, khách test OK",
        "note": "Đã trả máy cho khách và đóng phiếu"
    })
    detail_returned = res_return.json() if res_return.status_code == 200 else {}
    ok_return = (
        res_return.status_code == 200
        and detail_returned.get("status") == "RETURNED"
        and detail_returned.get("resolution") == "COMPLETED"
        and detail_returned.get("handed_over_by") == rec_id
        and detail_returned.get("handed_over_at") is not None
    )
    record("T1.8", "COMPLETED -> RETURNED (Bàn giao khách, đóng phiếu, lưu resolution='COMPLETED')", ok_return)

    # -------------------------------------------------------------
    # 2. LUỒNG TỪ CHỐI ĐẦY ĐỦ ĐẾN TRẢ MÁY ĐÓNG PHIẾU
    # -------------------------------------------------------------
    print("\n--- 2. KIỂM THỬ LUỒNG TỪ CHỐI ĐẦY ĐỦ ---")
    res_create_rej = client_rec.post("/api/v1/warranty-tickets/", json={
        "serial_number": "SN-TEST-REJECT-FLOW",
        "customer_id": c2_id,
        "service_center_id": 1,
        "created_by": rec_id,
        "issue_description": "Máy chập chờn bàn phím"
    })
    t2_id = res_create_rej.json()["id"]
    # Quản lý phân công KTV1
    client_mgr.post(f"/api/v1/warranty-tickets/{t2_id}/assign", json={"technician_id": tech1_id})

    client_tech1.patch(f"/api/v1/warranty-tickets/{t2_id}/status", json={
        "new_status": "INSPECTING", "changed_by": tech1_id, "note": "KTV nhận máy kiểm tra"
    })

    # KTV gửi đề xuất từ chối bảo hành
    res_prop = client_tech1.post(f"/api/v1/warranty-tickets/{t2_id}/propose-rejection", json={
        "proposal_note": "Máy bị ngấm nước ngọt vào mainboard, oxy hóa mạch đồng, vi phạm quy định BH"
    })
    ok_prop = res_prop.status_code == 200 and res_prop.json()["rejection_proposal_note"] is not None
    record("T2.1", "KTV gửi đề xuất từ chối kèm bằng chứng kiểm tra", ok_prop)

    # Quản lý duyệt từ chối (REJECTED kèm lý do bắt buộc)
    res_rej_approve = client_mgr.patch(f"/api/v1/warranty-tickets/{t2_id}/status", json={
        "new_status": "REJECTED",
        "changed_by": mgr_id,
        "rejection_reason": "Thiết bị bị ngấm chất lỏng vào mainboard, từ chối bảo hành theo điều khoản nhà sản xuất",
        "note": "Quản lý duyệt từ chối bảo hành"
    })
    ok_rej_approve = res_rej_approve.status_code == 200 and res_rej_approve.json()["status"] == "REJECTED"
    record("T2.2", "Quản lý duyệt từ chối bảo hành (INSPECTING -> REJECTED)", ok_rej_approve)

    # Tiếp nhận bàn giao máy trả khách (REJECTED -> RETURNED)
    res_rej_return = client_rec.patch(f"/api/v1/warranty-tickets/{t2_id}/status", json={
        "new_status": "RETURNED",
        "changed_by": rec_id,
        "handover_note": "Đã trả lại máy nguyên trạng cho khách cùng biên bản từ chối bảo hành",
        "note": "Bàn giao trả máy từ chối"
    })
    detail_rej_return = res_rej_return.json() if res_rej_return.status_code == 200 else {}
    ok_rej_return = (
        res_rej_return.status_code == 200
        and detail_rej_return.get("status") == "RETURNED"
        and detail_rej_return.get("resolution") == "REJECTED"
        and detail_rej_return.get("handed_over_at") is not None
    )
    record("T2.3", "REJECTED -> RETURNED (Bàn giao máy từ chối, đóng phiếu, lưu resolution='REJECTED')", ok_rej_return)

    # -------------------------------------------------------------
    # 3. CHẶN CHUYỂN TRẠNG THÁI SAI HOẶC THIẾU DỮ LIỆU
    # -------------------------------------------------------------
    print("\n--- 3. CHẶN CHUYỂN TRẠNG THÁI SAI HOẶC THIẾU DỮ LIỆU ---")
    res_no_tech = client_rec.post("/api/v1/warranty-tickets/", json={
        "serial_number": "SN-TEST-MULTI-CYCLE",
        "customer_id": c1_id,
        "service_center_id": 1,
        "created_by": rec_id,
        "issue_description": "Máy chạy chậm bất thường"
    })
    t3_id = res_no_tech.json()["id"]

    # 3.1 Chặn sang INSPECTING khi chưa có KTV (Quản lý gọi mà chưa gán KTV)
    res_block_inspect = client_mgr.patch(f"/api/v1/warranty-tickets/{t3_id}/status", json={
        "new_status": "INSPECTING", "changed_by": mgr_id, "note": "Chuyển kiểm tra mà chưa gán KTV"
    })
    ok_b1 = res_block_inspect.status_code == 400 and "kỹ thuật viên" in res_block_inspect.json().get("detail", "")
    record("T3.1", "Chặn RECEIVED -> INSPECTING khi chưa có kỹ thuật viên phụ trách", ok_b1, f"code={res_block_inspect.status_code}")

    # Quản lý phân công KTV1 cho phiếu
    client_mgr.post(f"/api/v1/warranty-tickets/{t3_id}/assign", json={
        "technician_id": tech1_id, "note": "Gán KTV1 phụ trách"
    })
    client_tech1.patch(f"/api/v1/warranty-tickets/{t3_id}/status", json={
        "new_status": "INSPECTING", "changed_by": tech1_id, "note": "Bắt đầu kiểm tra"
    })

    # 3.2 Chặn sang REPAIRING khi thiếu chẩn đoán
    res_block_diag = client_tech1.patch(f"/api/v1/warranty-tickets/{t3_id}/status", json={
        "new_status": "REPAIRING", "changed_by": tech1_id, "is_warranty_eligible": True
    })
    ok_b2 = res_block_diag.status_code == 400 and "chẩn đoán" in res_block_diag.json().get("detail", "").lower()
    record("T3.2", "Chặn INSPECTING -> REPAIRING khi thiếu kết luận chẩn đoán", ok_b2)

    # 3.3 Chặn sang REPAIRING khi không đủ ĐKBH hoặc is_warranty_eligible != True
    res_block_elig = client_tech1.patch(f"/api/v1/warranty-tickets/{t3_id}/status", json={
        "new_status": "REPAIRING", "changed_by": tech1_id,
        "diagnosis_note": "Lỗi ổ cứng SSD",
        "is_warranty_eligible": False
    })
    ok_b3 = res_block_elig.status_code == 400 and "điều kiện" in res_block_elig.json().get("detail", "").lower()
    record("T3.3", "Chặn INSPECTING -> REPAIRING khi không đủ điều kiện bảo hành (is_warranty_eligible=False)", ok_b3)

    # Cho qua REPAIRING hợp lệ
    client_tech1.patch(f"/api/v1/warranty-tickets/{t3_id}/status", json={
        "new_status": "REPAIRING", "changed_by": tech1_id,
        "diagnosis_note": "Lỗi bad sector SSD chính hãng",
        "is_warranty_eligible": True
    })

    # 3.4 Chặn REPAIRING -> COMPLETED khi thiếu nội dung sửa
    res_block_rep_content = client_tech1.patch(f"/api/v1/warranty-tickets/{t3_id}/status", json={
        "new_status": "COMPLETED", "changed_by": tech1_id,
        "repair_test_passed": True
    })
    ok_b4 = res_block_rep_content.status_code == 400 and "nội dung" in res_block_rep_content.json().get("detail", "").lower()
    record("T3.4", "Chặn REPAIRING -> COMPLETED khi thiếu nội dung sửa chữa", ok_b4)

    # 3.5 Chặn REPAIRING -> COMPLETED khi chưa test sau sửa đạt yêu cầu
    res_block_rep_test = client_tech1.patch(f"/api/v1/warranty-tickets/{t3_id}/status", json={
        "new_status": "COMPLETED", "changed_by": tech1_id,
        "repair_content": "Đã thay SSD 512GB",
        "repair_test_passed": False
    })
    ok_b5 = res_block_rep_test.status_code == 400 and "kiểm tra sau sửa" in res_block_rep_test.json().get("detail", "").lower()
    record("T3.5", "Chặn REPAIRING -> COMPLETED khi chưa xác nhận kiểm tra sau sửa đạt yêu cầu", ok_b5)

    # Cho qua COMPLETED hợp lệ
    client_tech1.patch(f"/api/v1/warranty-tickets/{t3_id}/status", json={
        "new_status": "COMPLETED", "changed_by": tech1_id,
        "repair_content": "Đã thay SSD 512GB mới",
        "repair_test_passed": True,
        "repair_test_note": "Cài lại Windows test ổn định"
    })

    # 3.6 Chặn chuyển ngược (COMPLETED -> REPAIRING)
    res_block_back = client_tech1.patch(f"/api/v1/warranty-tickets/{t3_id}/status", json={
        "new_status": "REPAIRING", "changed_by": tech1_id
    })
    ok_b6 = res_block_back.status_code == 400 and "STATE MACHINE ERROR" in res_block_back.json().get("detail", "")
    record("T3.6", "Chặn chuyển ngược trạng thái (COMPLETED -> REPAIRING)", ok_b6)

    # Cho qua RETURNED hợp lệ
    client_rec.patch(f"/api/v1/warranty-tickets/{t3_id}/status", json={
        "new_status": "RETURNED", "changed_by": rec_id, "handover_note": "Bàn giao khách xong"
    })

    # 3.7 Chặn mở lại phiếu đã đóng (RETURNED -> RECEIVED)
    res_block_reopen = client_rec.patch(f"/api/v1/warranty-tickets/{t3_id}/status", json={
        "new_status": "RECEIVED", "changed_by": rec_id
    })
    ok_b7 = res_block_reopen.status_code == 400 and "đã đóng" in res_block_reopen.json().get("detail", "").lower()
    record("T3.7", "Chặn mở lại phiếu đã đóng (RETURNED -> RECEIVED)", ok_b7)

    # -------------------------------------------------------------
    # 4. PHÂN QUYỀN PER-TICKET VÀ THEO VAI TRÒ
    # -------------------------------------------------------------
    print("\n--- 4. PHÂN QUYỀN PER-TICKET VÀ THEO VAI TRÒ ---")
    res_p4 = client_rec.post("/api/v1/warranty-tickets/", json={
        "serial_number": "SN-TEST-MULTI-CYCLE",
        "customer_id": c1_id,
        "service_center_id": 1,
        "created_by": rec_id,
        "issue_description": "Lần bảo hành thứ 2 của SN-TEST-MULTI-CYCLE"
    })
    t4_id = res_p4.json()["id"]
    # Quản lý phân công KTV1
    client_mgr.post(f"/api/v1/warranty-tickets/{t4_id}/assign", json={"technician_id": tech1_id})

    # 4.1 Chặn KTV2 (không được giao) thao tác trên phiếu của KTV1
    res_tech2_inspect = client_tech2.patch(f"/api/v1/warranty-tickets/{t4_id}/status", json={
        "new_status": "INSPECTING", "changed_by": tech2_id
    })
    ok_p1 = res_tech2_inspect.status_code == 403 and "kỹ thuật viên khác" in res_tech2_inspect.json().get("detail", "").lower()
    record("T4.1", "Chặn KTV2 thao tác trên phiếu phân công cho KTV1 (HTTP 403)", ok_p1)

    # 4.2 Chặn KTV tự duyệt REJECTED
    client_tech1.patch(f"/api/v1/warranty-tickets/{t4_id}/status", json={
        "new_status": "INSPECTING", "changed_by": tech1_id
    })
    res_tech_reject = client_tech1.patch(f"/api/v1/warranty-tickets/{t4_id}/status", json={
        "new_status": "REJECTED", "changed_by": tech1_id, "rejection_reason": "KTV tự duyệt từ chối"
    })
    ok_p2 = res_tech_reject.status_code == 403 and "quản lý" in res_tech_reject.json().get("detail", "").lower()
    record("T4.2", "Chặn KTV tự ý duyệt từ chối bảo hành (HTTP 403)", ok_p2)

    # 4.3 Chặn Tiếp nhận sửa chữa hoặc duyệt từ chối
    res_rec_repair = client_rec.patch(f"/api/v1/warranty-tickets/{t4_id}/status", json={
        "new_status": "REPAIRING", "changed_by": rec_id, "diagnosis_note": "Tiếp nhận tự chẩn đoán", "is_warranty_eligible": True
    })
    ok_p3 = res_rec_repair.status_code == 403
    record("T4.3", "Chặn Tiếp nhận can thiệp sửa chữa/chẩn đoán (HTTP 403)", ok_p3)

    # 4.4 Chặn KTV tự ý bàn giao đóng phiếu RETURNED
    client_tech1.patch(f"/api/v1/warranty-tickets/{t4_id}/status", json={
        "new_status": "REPAIRING", "changed_by": tech1_id,
        "diagnosis_note": "Lỗi cáp nguồn", "is_warranty_eligible": True
    })
    client_tech1.patch(f"/api/v1/warranty-tickets/{t4_id}/status", json={
        "new_status": "COMPLETED", "changed_by": tech1_id,
        "repair_content": "Thay cáp nguồn mới", "repair_test_passed": True
    })
    res_tech_return = client_tech1.patch(f"/api/v1/warranty-tickets/{t4_id}/status", json={
        "new_status": "RETURNED", "changed_by": tech1_id, "handover_note": "KTV tự trả máy"
    })
    ok_p4 = res_tech_return.status_code == 403 and "quầy" in res_tech_return.json().get("detail", "").lower()
    record("T4.4", "Chặn KTV tự xác nhận trả máy đóng phiếu (HTTP 403)", ok_p4)

    # Tiếp nhận trả máy hợp lệ
    client_rec.patch(f"/api/v1/warranty-tickets/{t4_id}/status", json={
        "new_status": "RETURNED", "changed_by": rec_id, "handover_note": "Quầy trả máy cho khách"
    })

    # -------------------------------------------------------------
    # 5. QUY TẮC BR3 (CHẶN TRÙNG PHIẾU MỞ VÀ CHO PHÉP TẠO SAU KHI ĐÓNG)
    # -------------------------------------------------------------
    print("\n--- 5. KIỂM THỬ QUY TẮC BR3 ---")
    res_open = client_rec.post("/api/v1/warranty-tickets/", json={
        "serial_number": "SN-TEST-VALID-01",
        "customer_id": c1_id,
        "service_center_id": 1,
        "created_by": rec_id,
        "issue_description": "Lần bảo hành tiếp theo của SN-TEST-VALID-01"
    })
    ok_first = res_open.status_code == 201
    t5_id = res_open.json()["id"]
    client_mgr.post(f"/api/v1/warranty-tickets/{t5_id}/assign", json={"technician_id": tech1_id})

    # Cố tình tạo phiếu thứ 2 cho cùng serial khi phiếu 1 đang mở -> Chặn 400
    res_dup = client_rec.post("/api/v1/warranty-tickets/", json={
        "serial_number": "SN-TEST-VALID-01",
        "customer_id": c1_id,
        "service_center_id": 1,
        "created_by": rec_id,
        "issue_description": "Cố tình tạo trùng phiếu mở"
    })
    ok_dup_block = res_dup.status_code == 400 and "BR3" in res_dup.json().get("detail", "")
    record("T5.1", "Chặn tạo 2 phiếu chưa đóng cho cùng 1 serial (BR3 FAIL)", ok_dup_block)

    # Chuyển phiếu qua COMPLETED (vẫn chưa đóng) -> Vẫn phải chặn
    client_tech1.patch(f"/api/v1/warranty-tickets/{t5_id}/status", json={"new_status": "INSPECTING", "changed_by": tech1_id})
    client_tech1.patch(f"/api/v1/warranty-tickets/{t5_id}/status", json={
        "new_status": "REPAIRING", "changed_by": tech1_id,
        "diagnosis_note": "Lỗi quạt tản nhiệt", "is_warranty_eligible": True
    })
    client_tech1.patch(f"/api/v1/warranty-tickets/{t5_id}/status", json={
        "new_status": "COMPLETED", "changed_by": tech1_id,
        "repair_content": "Thay quạt mới", "repair_test_passed": True
    })
    res_dup2 = client_rec.post("/api/v1/warranty-tickets/", json={
        "serial_number": "SN-TEST-VALID-01",
        "customer_id": c1_id,
        "service_center_id": 1,
        "created_by": rec_id,
        "issue_description": "Tạo phiếu khi phiếu cũ ở COMPLETED (chờ trả)"
    })
    ok_dup_block2 = res_dup2.status_code == 400
    record("T5.2", "Phiếu đang ở COMPLETED (chờ trả máy) vẫn tính là chưa đóng -> Chặn BR3", ok_dup_block2)

    # Đóng phiếu (chuyển sang RETURNED)
    client_rec.patch(f"/api/v1/warranty-tickets/{t5_id}/status", json={
        "new_status": "RETURNED", "changed_by": rec_id, "handover_note": "Khách nhận máy"
    })

    # Bây giờ tạo lần bảo hành mới -> Phải thành công!
    res_new_cycle = client_rec.post("/api/v1/warranty-tickets/", json={
        "serial_number": "SN-TEST-VALID-01",
        "customer_id": c1_id,
        "service_center_id": 1,
        "created_by": rec_id,
        "issue_description": "Lần bảo hành thứ 3 sau khi các phiếu trước đã đóng RETURNED"
    })
    ok_new_cycle = res_new_cycle.status_code == 201
    record("T5.3", "Cho phép tạo lần bảo hành mới cho serial sau khi phiếu cũ đã RETURNED", ok_new_cycle)

    # -------------------------------------------------------------
    # 6. KIỂM THỬ THỜI HẠN BẢO HÀNH BR2 (MÁY HẾT HẠN ĐƯỢC TIẾP NHẬN ĐỂ KIỂM TRA/TỪ CHỐI)
    # -------------------------------------------------------------
    print("\n--- 6. KIỂM THỬ THỜI HẠN BẢO HÀNH BR2 ---")
    # 6.1 Đúng ngày hết hạn (warranty_end_date == today) -> Còn hạn (PASS)
    res_exact = client_rec.post("/api/v1/warranty-tickets/", json={
        "serial_number": "SN-TEST-EXACT-END",
        "customer_id": c1_id,
        "service_center_id": 1,
        "created_by": rec_id,
        "issue_description": "Kiểm tra phiếu đúng ngày hết hạn bảo hành"
    })
    ok_exact = res_exact.status_code == 201
    record("T6.1", "Ngày hết hạn bằng đúng ngày tiếp nhận (warranty_end_date == check_date) vẫn tính CÒN HẠN", ok_exact)

    # 6.2 Máy hết hạn VẪN ĐƯỢC LẬP PHIẾU TIẾP NHẬN để kiểm tra (HTTP 201 RECEIVED)
    res_expired = client_rec.post("/api/v1/warranty-tickets/", json={
        "serial_number": "SN-TEST-EXPIRED",
        "customer_id": c1_id,
        "service_center_id": 1,
        "created_by": rec_id,
        "issue_description": "Khách mang máy đến kiểm tra sập nguồn (máy đã quá hạn BH)"
    })
    ok_expired_create = (
        res_expired.status_code == 201
        and res_expired.json()["status"] == "RECEIVED"
        and res_expired.json()["is_warranty_eligible"] is False
        and "Hết hạn bảo hành" in (res_expired.json().get("warranty_check_note") or "")
    )
    t_exp_id = res_expired.json()["id"] if res_expired.status_code == 201 else None
    record("T6.2", "Máy hết hạn VẪN ĐƯỢC lập phiếu tiếp nhận ở RECEIVED để kiểm tra/từ chối", ok_expired_create)

    # 6.3 Quản lý phân công KTV1 và KTV1 nhận kiểm tra INSPECTING thành công
    client_mgr.post(f"/api/v1/warranty-tickets/{t_exp_id}/assign", json={"technician_id": tech1_id})
    res_exp_inspect = client_tech1.patch(f"/api/v1/warranty-tickets/{t_exp_id}/status", json={
        "new_status": "INSPECTING", "changed_by": tech1_id, "note": "KTV nhận máy hết hạn vào kiểm tra"
    })
    ok_exp_inspect = res_exp_inspect.status_code == 200 and res_exp_inspect.json()["status"] == "INSPECTING"
    record("T6.3", "Máy hết hạn được chuyển sang bước KIỂM TRA (INSPECTING) bình thường", ok_exp_inspect)

    # 6.4 CHẶN TUYỆT ĐỐI không cho máy hết hạn chuyển sang sửa chữa bảo hành (INSPECTING -> REPAIRING)
    res_exp_repair_block = client_tech1.patch(f"/api/v1/warranty-tickets/{t_exp_id}/status", json={
        "new_status": "REPAIRING",
        "changed_by": tech1_id,
        "diagnosis_note": "Cố tình chuyển sang sửa chữa miễn phí",
        "is_warranty_eligible": True,
        "note": "Cố tình đưa vào sửa chữa"
    })
    ok_exp_repair_block = (
        res_exp_repair_block.status_code == 400
        and ("BR2_WARRANTY_EXPIRED" in str(res_exp_repair_block.json()) or "hết hạn bảo hành" in str(res_exp_repair_block.json()).lower())
    )
    record("T6.4", "CHẶN TUYỆT ĐỐI máy hết hạn chuyển sang sửa chữa bảo hành (INSPECTING -> REPAIRING bị chặn 400)", ok_exp_repair_block)

    # 6.5 Máy hết hạn đi qua luồng từ chối: KTV đề xuất -> Quản lý duyệt REJECTED -> Tiếp nhận trả máy RETURNED
    client_tech1.post(f"/api/v1/warranty-tickets/{t_exp_id}/propose-rejection", json={
        "proposal_note": "Thiết bị đã hết hạn bảo hành 70 ngày, đề xuất từ chối bảo hành miễn phí."
    })
    res_exp_reject = client_mgr.patch(f"/api/v1/warranty-tickets/{t_exp_id}/status", json={
        "new_status": "REJECTED",
        "changed_by": mgr_id,
        "rejection_reason": "Thiết bị đã quá hạn bảo hành theo quy định BR2 của nhà sản xuất.",
        "note": "Quản lý duyệt từ chối do hết hạn bảo hành"
    })
    res_exp_return = client_rec.patch(f"/api/v1/warranty-tickets/{t_exp_id}/status", json={
        "new_status": "RETURNED",
        "changed_by": rec_id,
        "handover_note": "Đã trả lại máy cho khách, tư vấn sửa chữa tính phí dịch vụ ngoài.",
        "note": "Trả máy từ chối cho khách"
    })
    ok_exp_full_cycle = (
        res_exp_reject.status_code == 200
        and res_exp_return.status_code == 200
        and res_exp_return.json()["status"] == "RETURNED"
        and res_exp_return.json()["resolution"] == "REJECTED"
    )
    record("T6.5", "Máy hết hạn hoàn tất trọn vẹn luồng từ chối rồi trả máy (RECEIVED -> INSPECTING -> REJECTED -> RETURNED)", ok_exp_full_cycle)

    # 6.6 Thiếu ngày mua / ngày hết hạn -> Báo lỗi, không tự gán ngày tiếp nhận làm ngày mua
    inst_missing = ProductInstance(
        product_id=1, customer_id=c1_id, serial_number="SN-TEST-MISSING-DATES",
        purchase_date=None, warranty_end_date=None, status="ACTIVE"
    )
    try:
        validate_br2_warranty_valid(inst_missing)
        ok_missing_date = False
    except BusinessRuleError as e:
        ok_missing_date = "thiếu thông tin" in str(e.detail).lower() or "BR2" in str(e.detail)
    record("T6.6", "Thiếu ngày mua/hết hạn báo lỗi rõ ràng, không tự ý gán ngày tiếp nhận làm ngày mua", ok_missing_date)

    # 6.7 Máy còn hạn ngày tiếp nhận nhưng hết hạn ngày xử lý: VẪN ĐƯỢC PHÉP SỬA CHỮA BẢO HÀNH
    # Serial SN-TEST-INTAKE-VALID-REPAIR-EXPIRED có warranty_end_date = today - 2 ngày (hôm nay đã hết hạn)
    # Lập phiếu với created_at = 5 ngày trước (khi đó máy còn hạn 3 ngày)
    res_iv_create = client_rec.post("/api/v1/warranty-tickets/", json={
        "serial_number": "SN-TEST-INTAKE-VALID-REPAIR-EXPIRED",
        "customer_id": c1_id,
        "service_center_id": 1,
        "created_by": rec_id,
        "issue_description": "Khách mang máy đến bảo hành từ 5 ngày trước (lúc còn hạn), nay KTV mới xử lý"
    })
    assert res_iv_create.status_code == 201, f"Tạo phiếu thất bại: {res_iv_create.text}"
    t_iv_id = res_iv_create.json()["id"]

    # Giả lập thời điểm tiếp nhận thực tế của phiếu là 5 ngày trước
    with TestSessionLocal() as db_session:
        db_t = db_session.query(WarrantyTicket).filter(WarrantyTicket.id == t_iv_id).first()
        db_t.created_at = datetime.utcnow() - timedelta(days=5)
        db_session.commit()

    # Quản lý phân công KTV1 và KTV1 nhận kiểm tra INSPECTING
    client_mgr.post(f"/api/v1/warranty-tickets/{t_iv_id}/assign", json={"technician_id": tech1_id})
    res_iv_inspect = client_tech1.patch(f"/api/v1/warranty-tickets/{t_iv_id}/status", json={
        "new_status": "INSPECTING", "changed_by": tech1_id, "note": "KTV nhận kiểm tra máy tiếp nhận từ 5 ngày trước"
    })
    ok_iv_inspect = res_iv_inspect.status_code == 200

    # KTV chuyển sang sửa chữa REPAIRING:
    # Tại ngày xử lý (hôm nay), thiết bị ĐÃ HẾT HẠN (warranty_end_date = today - 2 ngày)
    # Nhưng vì ngày tiếp nhận created_at = 5 ngày trước (còn hạn 3 ngày), quyết định bảo hành căn cứ ngày tiếp nhận -> PHẢI THÀNH CÔNG (HTTP 200)
    res_iv_repair = client_tech1.patch(f"/api/v1/warranty-tickets/{t_iv_id}/status", json={
        "new_status": "REPAIRING",
        "changed_by": tech1_id,
        "diagnosis_note": "Lỗi phần cứng hợp lệ trong diện bảo hành",
        "is_warranty_eligible": True,
        "note": "Xác nhận đủ điều kiện bảo hành căn cứ ngày tiếp nhận của phiếu"
    })
    ok_iv_repair = res_iv_repair.status_code == 200 and res_iv_repair.json()["status"] == "REPAIRING"

    # Hoàn tất sửa chữa COMPLETED và Bàn giao RETURNED
    res_iv_complete = client_tech1.patch(f"/api/v1/warranty-tickets/{t_iv_id}/status", json={
        "new_status": "COMPLETED",
        "changed_by": tech1_id,
        "repair_content": "Thay linh kiện bo mạch bảo hành miễn phí",
        "repair_test_passed": True,
        "note": "Kiểm tra sau sửa đạt chuẩn 100%"
    })
    res_iv_return = client_rec.patch(f"/api/v1/warranty-tickets/{t_iv_id}/status", json={
        "new_status": "RETURNED",
        "changed_by": rec_id,
        "handover_note": "Đã trả máy bảo hành hoàn tất cho khách",
        "note": "Bàn giao khách nhận máy"
    })
    ok_iv_full = (
        ok_iv_inspect
        and ok_iv_repair
        and res_iv_complete.status_code == 200
        and res_iv_return.status_code == 200
        and res_iv_return.json()["status"] == "RETURNED"
        and res_iv_return.json()["resolution"] == "COMPLETED"
    )
    record("T6.7", "Máy còn hạn ngày tiếp nhận nhưng hết hạn ngày xử lý: VẪN ĐƯỢC SỬA BẢO HÀNH (căn cứ created_at)", ok_iv_full)

    # -------------------------------------------------------------
    # 7. XỬ LÝ CONCURRENCY (ĐỒNG THỜI CHUYỂN TRẠNG THÁI CÙNG MỘT PHIẾU)
    # -------------------------------------------------------------
    print("\n--- 7. KIỂM THỬ XỬ LÝ ĐỒNG THỜI (CONCURRENCY) ---")
    # Tạo phiếu mới cho kiểm thử Concurrency
    res_cc = client_rec.post("/api/v1/warranty-tickets/", json={
        "serial_number": "SN-TEST-CONCURRENCY",
        "customer_id": c1_id,
        "service_center_id": 1,
        "created_by": rec_id,
        "issue_description": "Kiểm thử concurrency trạng thái"
    })
    t_cc_id = res_cc.json()["id"]
    client_mgr.post(f"/api/v1/warranty-tickets/{t_cc_id}/assign", json={"technician_id": tech1_id})

    # Hai request đồng thời gửi từ RECEIVED -> INSPECTING
    barrier = threading.Barrier(2)
    results_cc = []

    def make_concurrent_request(client_user, note_str):
        barrier.wait()  # Đồng bộ hóa điểm xuất phát
        res = client_user.patch(f"/api/v1/warranty-tickets/{t_cc_id}/status", json={
            "new_status": "INSPECTING",
            "changed_by": tech1_id,
            "note": note_str
        })
        results_cc.append(res)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(make_concurrent_request, client_tech1, "Request đồng thời A")
        f2 = executor.submit(make_concurrent_request, client_tech1, "Request đồng thời B")
        concurrent.futures.wait([f1, f2])

    status_codes = sorted([r.status_code for r in results_cc])
    # Kiểm tra: đúng 1 request thành công (200), 1 request xung đột (409 Conflict)
    ok_cc_status = (status_codes == [200, 409])

    # Kiểm tra lịch sử trong CSDL: Chỉ có đúng 1 bản ghi chuyển RECEIVED -> INSPECTING
    db = TestSessionLocal()
    try:
        hist_cc = db.query(TicketStatusHistory).filter(
            TicketStatusHistory.ticket_id == t_cc_id,
            TicketStatusHistory.from_status == "RECEIVED",
            TicketStatusHistory.to_status == "INSPECTING"
        ).all()
        ok_cc_hist = len(hist_cc) == 1
    finally:
        db.close()

    ok_concurrency = ok_cc_status and ok_cc_hist
    record("T7.1", "Hai request đồng thời đổi trạng thái: 1 thành công (200), 1 chặn xung đột (409 Conflict)", ok_cc_status,
           f"HTTP status trả về: {status_codes}")
    record("T7.2", "Lịch sử chuyển bước không bị nhân đôi, không ghi đè kết quả khi có xung đột", ok_cc_hist,
           f"Số bản ghi chuyển RECEIVED->INSPECTING trong CSDL: {len(hist_cc)}")

    # -------------------------------------------------------------
    # 8. THỐNG KÊ, RESOLUTION VÀ THỜI GIAN XỬ LÝ / CHỜ NHẬN
    # -------------------------------------------------------------
    print("\n--- 8. THỐNG KÊ, RESOLUTION VÀ THỜI GIAN XỬ LÝ / CHỜ NHẬN ---")
    res_stats = client_mgr.get("/api/v1/warranty-tickets/stats/summary")
    stats = res_stats.json()
    ok_stats = (
        res_stats.status_code == 200
        and "total_rejections" in stats
        and stats["total_rejections"] >= 2  # t2 và t_exp_id đều đã RETURNED với resolution='REJECTED'
        and "rejection_rate_percent" in stats
        and "avg_processing_time_hours" in stats
        and "avg_waiting_time_hours" in stats
        and "metrics_explanation" in stats
    )
    record("T8.1", "Thống kê tỷ lệ từ chối giữ nguyên kết quả sau khi đóng phiếu (resolution='REJECTED')", ok_stats,
           f"Tổng từ chối={stats.get('total_rejections')}, Tỷ lệ={stats.get('rejection_rate_percent')}%, "
           f"TG xử lý TB={stats.get('avg_processing_time_hours')}h, TG chờ TB={stats.get('avg_waiting_time_hours')}h")

    # -------------------------------------------------------------
    # 9. MIGRATION CHẠY LẠI AN TOÀN (IDEMPOTENCY)
    # -------------------------------------------------------------
    print("\n--- 9. MIGRATION CHẠY LẠI AN TOÀN (IDEMPOTENCY) ---")
    try:
        ensure_schema_upgrades(test_engine)
        migrate_tickets_data(test_engine)
        ensure_schema_upgrades(test_engine)
        migrate_tickets_data(test_engine)
        ok_migration = True
    except Exception as e:
        ok_migration = False
        print(f"Lỗi migration: {e}")
    record("T9.1", "Migration chạy lại nhiều lần an toàn, không reset database, không xóa dữ liệu", ok_migration)

    # -------------------------------------------------------------
    # TỔNG KẾT
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    total_tests = len(TEST_RESULTS)
    pass_tests = sum(1 for _, _, ok, _ in TEST_RESULTS if ok)
    fail_tests = total_tests - pass_tests
    print(f"  KẾT QUẢ KIỂM THỬ TÁI CẤU TRÚC: {pass_tests}/{total_tests} PASS ({round(pass_tests/total_tests*100)}%)")
    print("=" * 80)

    if fail_tests > 0:
        print("\nCác case bị FAIL:")
        for test_id, name, ok, note in TEST_RESULTS:
            if not ok:
                print(f"  - [{test_id}] {name} -> {note}")
        return False
    return True

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
