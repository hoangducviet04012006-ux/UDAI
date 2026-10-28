"""
=======================================================================
KIEM THU HOI QUY XAC THUC & PHAN QUYEN (AUTH & RBAC REGRESSION TEST)
=======================================================================
Kiem tra toan dien:
  1. Dang nhap dung mat khau cho ca 3 vai tro (MANAGER, RECEPTIONIST, TECHNICIAN).
  2. Xu ly dung khi nguoi dung copy-paste thua khoang trang dau/cuoi.
  3. Chan dung khi sai mat khau hoac tai khoan khong ton tai (401, thong bao trung tinh).
  4. Tu dong nang cap tai khoan CSDL cu luu hash gia (dummyhash123) sang PBKDF2 chuan.
  5. Bao toan mat khau nguoi dung da thay doi (khong tu dong reset mat khau hop le).
  6. Kiem tra phan quyen (RBAC) cua ca 3 vai tro:
     - Quan ly: toan quyen + quan tri tai khoan (user.manage) + tu choi bao hanh (ticket.reject).
     - Tiep nhan: tiep nhan may, cham soc khach, tra may; khong duoc quan tri tai khoan (403).
     - Ky thuat vien: chan doan, sua chua; khong duoc tao khach/tiep nhan/quan tri (403).

Luu y an toan:
  Su dung CSDL tam rieng biet (temporary SQLite DB) de KHONG anh huong hay reset
  file CSDL thuc te database/baohanh_ai.db.
"""
import os
import sys
import tempfile

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Su dung CSDL tam lap tuc truoc khi import app de cach ly hoan toan
temp_db = tempfile.NamedTemporaryFile(suffix="_auth_reg.db", delete=False)
temp_db.close()
temp_db_path = temp_db.name.replace("\\", "/")
os.environ["DATABASE_URL"] = f"sqlite:///{temp_db_path}"

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

from fastapi.testclient import TestClient
from app.main import app
from app.database import engine, Base, SessionLocal
from app.models import User, ServiceCenter
from app.services import auth_service
from app.services.auth_service import (
    hash_password,
    is_legacy_hash,
    verify_password,
    DEMO_CREDENTIALS,
    PERM_USER_MANAGE,
    PERM_TICKET_REJECT,
    PERM_TICKET_CREATE,
    PERM_TICKET_DIAGNOSE,
    PERM_TICKET_REPAIR,
    PERM_TICKET_HANDOVER,
)

client = TestClient(app)
checks = []


def record(name, condition, detail=""):
    checks.append((name, bool(condition), detail))
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}")
    if detail:
        print(f"         -> {detail}")


def setup_test_db():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        sc = ServiceCenter(name="TTBH Test", address="Ha Noi", phone="0243000000", email="test@bh.vn", active=True)
        db.add(sc)
        db.commit()
        db.refresh(sc)

        u1 = User(
            username="manager01",
            password_hash=hash_password("Manager@123"),
            full_name="Nguyen Quan Ly",
            role="MANAGER",
            service_center_id=sc.id,
            active=True,
        )
        u2 = User(
            username="receptionist01",
            password_hash=hash_password("Reception@123"),
            full_name="Tran Tiep Nhan",
            role="RECEPTIONIST",
            service_center_id=sc.id,
            active=True,
        )
        u3 = User(
            username="technician01",
            password_hash=hash_password("Technician@123"),
            full_name="Le Ky Thuat",
            role="TECHNICIAN",
            service_center_id=sc.id,
            active=True,
        )
        db.add_all([u1, u2, u3])
        db.commit()


def run_tests():
    print("=" * 75)
    print("KIEM THU HOI QUY XAC THUC & PHAN QUYEN (BAOHANHAI)")
    print(f"Moi truong: CSDL tam rieng biet ({temp_db_path})")
    print("=" * 75)

    setup_test_db()

    # 1. Dang nhap thanh cong ca 3 vai tro voi mat khau demo
    tokens = {}
    roles_info = {}
    for u, p, expected_role in [
        ("manager01", "Manager@123", "MANAGER"),
        ("receptionist01", "Reception@123", "RECEPTIONIST"),
        ("technician01", "Technician@123", "TECHNICIAN"),
    ]:
        res = client.post("/api/v1/auth/login", json={"username": u, "password": p})
        data = res.json() if res.status_code == 200 else {}
        ok = res.status_code == 200 and data.get("user", {}).get("role") == expected_role
        tokens[expected_role] = data.get("access_token")
        roles_info[expected_role] = data.get("user", {})
        record(f"Dang nhap dung mat khau: {u} ({expected_role})", ok, f"HTTP {res.status_code}, token co san")

    # 2. Khong strip mat khau: khoang trang trong mat khau duoc bao toan chinh xac
    res_trail = client.post("/api/v1/auth/login", json={"username": "manager01", "password": "Manager@123 "})
    record("Khong strip mat khau: 'Manager@123 ' bi chan 401 (khong tu cat khoang trang)", res_trail.status_code == 401)

    res_lead = client.post("/api/v1/auth/login", json={"username": "manager01", "password": " Manager@123"})
    record("Khong strip mat khau: ' Manager@123' bi chan 401 (khong tu cat khoang trang)", res_lead.status_code == 401)

    # 3. Sai mat khau & tai khoan khong ton tai tra 401 voi thong bao trung tinh
    res_bad_pw = client.post("/api/v1/auth/login", json={"username": "manager01", "password": "WrongPassword@123"})
    res_no_user = client.post("/api/v1/auth/login", json={"username": "khong_ton_tai", "password": "Manager@123"})
    ok_guards = (
        res_bad_pw.status_code == 401
        and res_no_user.status_code == 401
        and res_bad_pw.json().get("detail") == "Tên đăng nhập hoặc mật khẩu không đúng."
        and res_no_user.json().get("detail") == "Tên đăng nhập hoặc mật khẩu không đúng."
    )
    record("Sai mat khau & tai khoan khong ton tai tra cung HTTP 401 trung tinh", ok_guards)

    # 4. Tu dong nang cap tai khoan demo co hash gia cu (dummyhash123) khi dang nhap
    with SessionLocal() as db:
        legacy_u = User(
            username="legacy_mgr",
            password_hash="pbkdf2:sha256:dummyhash123",
            full_name="Legacy Manager",
            role="MANAGER",
            active=True,
        )
        db.add(legacy_u)
        db.commit()

        # Gia su demo_mgr co hash gia
        demo_legacy = db.query(User).filter(User.username == "manager01").first()
        demo_legacy.password_hash = "pbkdf2:sha256:dummyhash123"
        db.commit()

    # Khi DEMO_MODE tat: khong tu dong nang cap tai khoan demo
    demo_pw = auth_service.DEMO_CREDENTIALS.get("manager01", "123456")
    os.environ["DEMO_MODE"] = "false"
    res_no_demo = client.post("/api/v1/auth/login", json={"username": "manager01", "password": demo_pw})
    record("Khi DEMO_MODE tat: tai khoan hash gia bi chan 401 khong tu nang cap", res_no_demo.status_code == 401)

    # Khi DEMO_MODE bat ro rang: tu dong nang cap sang PBKDF2 hop le
    os.environ["DEMO_MODE"] = "true"
    res_migrated = client.post("/api/v1/auth/login", json={"username": "manager01", "password": demo_pw})
    ok_migrate = res_migrated.status_code == 200
    with SessionLocal() as db:
        updated_acc = db.query(User).filter(User.username == "manager01").first()
        is_still_legacy = is_legacy_hash(updated_acc.password_hash)
        is_pw_valid = verify_password(demo_pw, updated_acc.password_hash)
    record(
        "Khi DEMO_MODE bat: tai khoan demo hash gia duoc nang cap sang PBKDF2 hop le",
        ok_migrate and not is_still_legacy and is_pw_valid,
        f"Hash sau nang cap hop le PBKDF2: {not is_still_legacy}",
    )

    # Thu dang nhap sai mat khau vao tai khoan co hash gia -> phai that bai va KHONG duoc nang cap
    res_bad_legacy = client.post("/api/v1/auth/login", json={"username": "legacy_mgr", "password": "WrongPassword"})
    record("Tai khoan hash gia khi nhap sai mat khau bi chan 401", res_bad_legacy.status_code == 401)

    # 5. Bao toan mat khau nguoi dung da thay doi (khong bi ghi de)
    custom_pw = "CustomUserPassword#2026"
    with SessionLocal() as db:
        user_mgr = db.query(User).filter(User.username == "manager01").first()
        user_mgr.password_hash = hash_password(custom_pw)
        db.commit()

    # Goi ensure_demo_accounts_configured de xac nhan khong tu reset mat khau tuy bien
    with SessionLocal() as db:
        upgraded_count = auth_service.ensure_demo_accounts_configured(db)
        user_mgr = db.query(User).filter(User.username == "manager01").first()
        still_custom = verify_password(custom_pw, user_mgr.password_hash)
    record(
        "ensure_demo_accounts_configured KHONG ghi de mat khau hop le nguoi dung da doi",
        upgraded_count == 0 and still_custom,
        f"Mat khau tuy bien van con nguyen ven: {still_custom}",
    )

    # Tra ve mat khau demo de tiep tuc kiem tra phan quyen
    with SessionLocal() as db:
        user_mgr = db.query(User).filter(User.username == "manager01").first()
        user_mgr.password_hash = hash_password("Manager@123")
        db.commit()

    # 6. Kiem tra phan quyen (RBAC) cua ba vai tro
    mgr_headers = {"Authorization": f"Bearer {tokens['MANAGER']}"}
    rec_headers = {"Authorization": f"Bearer {tokens['RECEPTIONIST']}"}
    tech_headers = {"Authorization": f"Bearer {tokens['TECHNICIAN']}"}

    # a) Endpoint quan tri tai khoan (/api/v1/users/) chi cho phep QUAN LY
    res_users_mgr = client.get("/api/v1/users/", headers=mgr_headers)
    res_users_rec = client.get("/api/v1/users/", headers=rec_headers)
    res_users_tech = client.get("/api/v1/users/", headers=tech_headers)
    res_users_anon = client.get("/api/v1/users/")

    ok_rbac_users = (
        res_users_mgr.status_code == 200
        and res_users_rec.status_code == 403
        and res_users_tech.status_code == 403
        and res_users_anon.status_code == 401
    )
    record(
        "RBAC: /api/v1/users/ (Quan tri): Quan ly = 200, Tiep nhan = 403, Ky thuat = 403, An danh = 401",
        ok_rbac_users,
    )

    # b) Danh sach quyen trong session cua 3 vai tro:
    mgr_perms = set(roles_info["MANAGER"].get("permissions", []))
    rec_perms = set(roles_info["RECEPTIONIST"].get("permissions", []))
    tech_perms = set(roles_info["TECHNICIAN"].get("permissions", []))

    record("Quan ly co quyen user.manage va ticket.reject",
           PERM_USER_MANAGE in mgr_perms and PERM_TICKET_REJECT in mgr_perms)
    record("Tiep nhan co ticket.create, ticket.handover nhung KHONG co user.manage, ticket.reject",
           PERM_TICKET_CREATE in rec_perms and PERM_TICKET_HANDOVER in rec_perms
           and PERM_USER_MANAGE not in rec_perms and PERM_TICKET_REJECT not in rec_perms)
    record("Ky thuat co ticket.diagnose, ticket.repair nhung KHONG co ticket.create, ticket.reject",
           PERM_TICKET_DIAGNOSE in tech_perms and PERM_TICKET_REPAIR in tech_perms
           and PERM_TICKET_CREATE not in tech_perms and PERM_TICKET_REJECT not in tech_perms)

    # 7. Kiem tra hanh dong va quyen tren phieu chua phan cong / da phan cong KTV
    with SessionLocal() as db:
        from datetime import date
        from app.models import Customer, Product, ProductInstance, WarrantyTicket
        cust = Customer(full_name="Khach Test Unassigned", phone="0911223344", address="HN")
        prod = Product(name="Laptop Test", brand="Asus", category="Laptop", warranty_duration_months=24)
        db.add_all([cust, prod])
        db.commit()
        inst = ProductInstance(product_id=prod.id, customer_id=cust.id, serial_number="SN-TEST-UNASSIGN-01", purchase_date=date(2025, 1, 1), warranty_end_date=date(2027, 1, 1))
        db.add(inst)
        db.commit()
        t_unassigned = WarrantyTicket(
            ticket_code="TK-TEST-UNASSIGN-01",
            product_instance_id=inst.id,
            customer_id=cust.id,
            service_center_id=1,
            created_by=2, # receptionist01
            issue_description="May khong len nguon",
            status="RECEIVED",
            assigned_technician_id=None,
        )
        db.add(t_unassigned)
        db.commit()
        unassigned_id = t_unassigned.id

    # a) Quan ly thay hanh dong chinh la 'Phan cong KTV', mo form phan cong
    res_mgr_t = client.get(f"/api/v1/warranty-tickets/{unassigned_id}", headers=mgr_headers).json()
    mgr_primary = res_mgr_t.get("primary_action", {})
    mgr_actions = [a["target"] for a in res_mgr_t.get("available_actions", [])]
    record(
        "Phieu chua phan cong: Quan ly thay nut chinh 'Phan cong KTV', khong co 'INSPECTING'",
        mgr_primary.get("target") == "ASSIGN" and res_mgr_t.get("action_label") in ("Phân công kỹ thuật viên", "Phân công KTV") and "INSPECTING" not in mgr_actions
    )

    # b) Tiep nhan thay 'Cho quan ly phan cong', khong co nut bat dau kiem tra
    res_rec_t = client.get(f"/api/v1/warranty-tickets/{unassigned_id}", headers=rec_headers).json()
    record(
        "Phieu chua phan cong: Tiep nhan thay 'Chờ quản lý phân công', available_actions rong",
        res_rec_t.get("action_label") in ("Chờ phân công kỹ thuật viên", "Chờ quản lý phân công") and res_rec_t.get("available_actions") == []
    )

    # c) Ky thuat vien thay 'Chua phan cong KTV' va bi chan 403 khi co tinh kiem tra
    res_tech_t = client.get(f"/api/v1/warranty-tickets/{unassigned_id}", headers=tech_headers).json()
    record(
        "Phieu chua phan cong: Ky thuat vien thay 'Chưa phân công KTV', available_actions rong",
        res_tech_t.get("action_label") in ("Chờ phân công kỹ thuật viên", "Chưa phân công KTV") and res_tech_t.get("available_actions") == []
    )
    res_tech_patch = client.patch(
        f"/api/v1/warranty-tickets/{unassigned_id}/status",
        headers=tech_headers,
        json={"new_status": "INSPECTING", "changed_by": 3}
    )
    record(
        "KTV bi chan 403 khi thao tac tren phieu chua duoc phan cong cho minh",
        res_tech_patch.status_code == 403
    )

    # d) Quan ly phan cong KTV qua /assign -> KTV thay 'Bat dau kiem tra'
    res_assign = client.post(
        f"/api/v1/warranty-tickets/{unassigned_id}/assign",
        headers=mgr_headers,
        json={"technician_id": 3, "note": "Phan cong Le Ky Thuat kiem tra"}
    )
    res_tech_after = client.get(f"/api/v1/warranty-tickets/{unassigned_id}", headers=tech_headers).json()
    tech_after_targets = [a["target"] for a in res_tech_after.get("available_actions", [])]
    record(
        "Sau khi Quan ly phan cong: KTV duoc giao thay nut 'Bat dau kiem tra' (INSPECTING)",
        res_assign.status_code == 200 and "INSPECTING" in tech_after_targets
    )

    print("=" * 75)
    failed = [c for c in checks if not c[1]]
    total = len(checks)
    passed = total - len(failed)
    print(f"TONG KET KIEM THU HOI QUY: {passed}/{total} PASS (FAIL: {len(failed)})")
    print("=" * 75)

    try:
        os.remove(temp_db_path)
    except Exception:
        pass

    return len(failed) == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
