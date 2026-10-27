"""
=======================================================================
Đợt 7 - MINH CHỨNG: ĐĂNG NHẬP THẬT & PHÂN QUYỀN THEO VAI TRÒ (RBAC)
=======================================================================
File này kiểm chứng ĐỘC LẬP phần bảo mật (đăng nhập + phân quyền), tách khỏi
24 minh chứng nghiệp vụ KT2/KT3 trong tests/test_scenarios.py (không sửa, không
làm nhiễu nội dung minh chứng KT2/KT3).

Nội dung kiểm chứng:
    01. Đăng nhập thành công cả 3 vai trò -> 200 + token + danh sách quyền.
    02. Sai mật khẩu / tài khoản không tồn tại -> 401 và THÔNG BÁO GIỐNG NHAU
        (không cho dò tài khoản - user enumeration).
    03. Mọi API nghiệp vụ khi KHÔNG có token -> 401 (không có "cửa hậu").
    04. Token bị sửa chữ ký / tự chế độ vai trò MANAGER -> 401.
    05. Token hết hạn -> 401.
    06. GET /auth/me trả đúng danh tính, vai trò và quyền lấy từ CSDL.
    07. Đăng xuất thu hồi token ngay lập tức (token cũ -> 401).
    08. Tài khoản bị vô hiệu hoá -> 401 (cả đăng nhập mới và token đang dùng).
    09. Ma trận RBAC: vai trò gọi API ngoài quyền -> 403 (ẩn menu KHÔNG đủ).
    10. Không thể "khai khống" người thực hiện (created_by / changed_by).
    11. Chỉ QUẢN LÝ được xác nhận TỪ CHỐI bảo hành (REJECTED).
    12. Mật khẩu chỉ lưu dạng băm PBKDF2-HMAC-SHA256 + salt riêng, không lưu thô.
    13. Vai trò LUÔN lấy từ CSDL: đổi vai trò trong CSDL có hiệu lực ngay với
        token đang dùng (token/giao diện KHÔNG thể quyết định quyền).

Cách chạy:
    py -3.12 tests\\test_auth_rbac.py     (từ thư mục gốc dự án)
Exit code: 0 = toàn bộ PASS, 1 = có mục FAIL.
"""
import sys
import os
import json

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Cấu trúc dự án: tests/ ở gốc, code trong backend/
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

from fastapi.testclient import TestClient

from app.main import app
from app.database import engine, Base, SessionLocal
from app.models import User, WarrantyTicket, TicketStatusHistory
from app.services import auth_service
from seed_data import seed, DEMO_ACCOUNTS, DEMO_PASSWORDS

ROLE_CLIENT = {}   # role -> TestClient đã đăng nhập
ROLE_TOKEN = {}    # role -> access_token


def print_separator(title=""):
    print("\n" + "=" * 75)
    if title:
        print(f"  {title.upper()}")
        print("=" * 75)


def record(results, name, ok, detail=""):
    """Ghi nhận kết quả 1 mục minh chứng và in ra màn hình."""
    results.append((name, "PASS" if ok else "FAIL"))
    print(f"[=> {name}]: {'DAT (PASS)' if ok else 'THAT BAI (FAIL)'}")
    if detail:
        print(f"    {detail}")


def login_client(username, password):
    """Tạo TestClient riêng và đăng nhập; trả về (client, response)."""
    session = TestClient(app)
    res = session.post("/api/v1/auth/login", json={"username": username, "password": password})
    if res.status_code == 200:
        session.headers.update({"Authorization": f"Bearer {res.json()['access_token']}"})
    return session, res


def user_id(db, username):
    """ID thật của tài khoản trong CSDL (không hard-code để tránh sai lệch)."""
    row = db.query(User).filter(User.username == username).first()
    return int(row.id) if row else None


def run_all_tests():
    # CSDL luôn được làm mới để kết quả tái lập 100%
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed()

    results = []
    db = SessionLocal()

    id_manager = user_id(db, "manager01")
    id_receptionist = user_id(db, "receptionist01")
    id_technician = user_id(db, "technician01")

    print_separator("BAOHANHAI - MINH CHUNG DANG NHAP & PHAN QUYEN (DOT 7)")
    print(f"[*] ID tai khoan trong CSDL: manager01={id_manager} | "
          f"receptionist01={id_receptionist} | technician01={id_technician}")

    # =================================================================
    # 01. ĐĂNG NHẬP THÀNH CÔNG CẢ 3 VAI TRÒ
    # =================================================================
    print_separator("01. DANG NHAP THANH CONG 3 VAI TRO (MANAGER / RECEPTIONIST / TECHNICIAN)")
    ok_login = True
    for username, password, full_name, role in DEMO_ACCOUNTS:
        session, res = login_client(username, password)
        body = res.json() if res.status_code == 200 else {}
        info = body.get("user", {})
        perms = info.get("permissions", [])
        ok_role = info.get("role") == role and len(perms) > 0
        # Phản hồi KHÔNG được chứa mật khẩu thô hay hash
        ok_secret = (password not in res.text) and ("pbkdf2" not in res.text) \
            and ("password_hash" not in res.text)
        # Token dùng được ngay cho API nghiệp vụ
        ok_use = session.get("/api/v1/auth/me").status_code == 200
        ok_login = ok_login and res.status_code == 200 and ok_role and ok_secret and ok_use
        ROLE_CLIENT[role] = session
        ROLE_TOKEN[role] = body.get("access_token", "")
        print(f"    - {role:<13} | HTTP {res.status_code} | vai tro: {info.get('role_label')} | "
              f"so quyen: {len(perms):2d} | token dung duoc: {ok_use} | "
              f"khong lo mat khau/hash: {ok_secret}")
    record(results, "01. Dang nhap thanh cong ca 3 vai tro + nhan token + danh sach quyen", ok_login)

    # =================================================================
    # 02. SAI MẬT KHẨU / TÀI KHOẢN KHÔNG TỒN TẠI -> 401 (THÔNG BÁO GIỐNG NHAU)
    # =================================================================
    print_separator("02. SAI MAT KHAU / TAI KHOAN KHONG TON TAI -> 401 (KHONG CHO DO TAI KHOAN)")
    _, bad_password = login_client("manager01", "sai-mat-khau-123")
    _, unknown_user = login_client("khong-ton-tai-9999", "Manager@123")
    _, empty_login = login_client("", "")
    detail_set = {bad_password.json().get("detail"), unknown_user.json().get("detail")}
    ok_login_guard = (
        bad_password.status_code == 401
        and unknown_user.status_code == 401
        and empty_login.status_code in (401, 422)
        and len(detail_set) == 1
        and "manager" not in unknown_user.text.lower()
    )
    print(f"    - Sai mat khau            -> HTTP {bad_password.status_code} | "
          f"detail: {bad_password.json().get('detail')}")
    print(f"    - Tai khoan khong ton tai -> HTTP {unknown_user.status_code} | "
          f"detail: {unknown_user.json().get('detail')}")
    print(f"    - Bo trong ten/mat khau   -> HTTP {empty_login.status_code} "
          f"(422 = chan ngay o buoc kiem tra du lieu, khong the dang nhap)")
    print("    => Hai truong hop tra CUNG mot thong bao (khong tiet lo tai khoan nao ton tai).")
    record(results, "02. Sai mat khau & tai khoan khong ton tai -> 401, thong bao trung tinh",
           ok_login_guard)

    # =================================================================
    # 03. KHÔNG CÓ TOKEN -> 401 CHO MỌI API NGHIỆP VỤ
    # =================================================================
    print_separator("03. KHONG CO TOKEN -> 401 VOI MOI API NGHIEP VU (KHONG CO CUA HAU)")
    anonymous = TestClient(app)
    protected_calls = [
        ("GET", "/api/v1/products/", None),
        ("POST", "/api/v1/products/", {"name": "X", "brand": "Y", "category": "Z"}),
        ("GET", "/api/v1/customers/", None),
        ("POST", "/api/v1/customers/", {"full_name": "X", "phone": "0900000000"}),
        ("GET", "/api/v1/product-instances/", None),
        ("GET", "/api/v1/warranty-tickets/", None),
        ("GET", "/api/v1/warranty-tickets/stats/summary", None),
        ("POST", "/api/v1/warranty-tickets/", {"serial_number": "SN-ASUS-VALID-01",
                                               "customer_id": 1, "service_center_id": 1,
                                               "created_by": 2, "issue_description": "test"}),
        ("PATCH", "/api/v1/warranty-tickets/1/status",
         {"new_status": "INSPECTING", "changed_by": 3}),
        ("POST", "/api/v1/ai/tickets/1/classify-error", None),
        ("GET", "/api/v1/ai/results/1", None),
        ("PATCH", "/api/v1/ai/results/1/review", {"reviewed_by": 1, "decision": "APPROVED"}),
        ("GET", "/api/v1/ai/demo/users", None),
        ("POST", "/api/v1/debug/check-warranty", {"serial_number": "SN-ASUS-VALID-01"}),
        ("GET", "/api/v1/users/", None),
        ("GET", "/api/v1/auth/me", None),
    ]
    not_401 = []
    for method, url, payload in protected_calls:
        res = anonymous.request(method, url, json=payload)
        mark = "OK" if res.status_code == 401 else "!!"
        print(f"    [{mark}] {method:<6} {url:<46} -> HTTP {res.status_code}")
        if res.status_code != 401:
            not_401.append(f"{method} {url}")
    record(results, "03. Khong co token -> 401 cho toan bo API nghiep vu (16 API)", not not_401,
           detail="" if not not_401 else f"API khong tra 401: {not_401}")

    # =================================================================
    # 04. TOKEN GIẢ / BỊ SỬA ĐỔI -> 401
    # =================================================================
    print_separator("04. TOKEN BI SUA DOI / TU CHE DO VAI TRO -> 401")
    manager_token = ROLE_TOKEN["MANAGER"]
    tech_token = ROLE_TOKEN["TECHNICIAN"]
    t_prefix, t_payload, t_sign = tech_token.split(".")

    # (a) Sửa 1 ký tự của chữ ký
    bad_sig = ("b" if t_sign[0] != "b" else "c") + t_sign[1:]
    tampered = TestClient(app)
    tampered.headers.update({"Authorization": f"Bearer {t_prefix}.{t_payload}.{bad_sig}"})

    # (b) Tự chế payload đòi vai trò MANAGER nhưng giữ chữ ký cũ của kỹ thuật viên
    forged_payload = json.loads(auth_service._b64url_decode(t_payload).decode("utf-8"))
    forged_payload["rol"] = "MANAGER"
    forged_b64 = auth_service._b64url_encode(
        json.dumps(forged_payload, separators=(",", ":")).encode("utf-8")
    )
    forged = TestClient(app)
    forged.headers.update({"Authorization": f"Bearer {t_prefix}.{forged_b64}.{t_sign}"})

    # (c) Token rác không đúng định dạng
    garbage = TestClient(app)
    garbage.headers.update({"Authorization": "Bearer token.rac.khong.hop.le"})

    forgery_cases = [
        ("Sua chu ky token", tampered),
        ("Tu che payload vai tro MANAGER", forged),
        ("Token rac sai dinh dang", garbage),
    ]
    ok_forgery = True
    for label, session in forgery_cases:
        me_code = session.get("/api/v1/auth/me").status_code
        users_code = session.get("/api/v1/users/").status_code
        ok_forgery = ok_forgery and me_code == 401 and users_code == 401
        print(f"    - {label:<32} | /auth/me -> {me_code} | /users/ -> {users_code}")
    ok_original_ok = ROLE_CLIENT["TECHNICIAN"].get("/api/v1/auth/me").status_code == 200
    ok_forgery = ok_forgery and ok_original_ok
    print(f"    - Token goc van hop le            | /auth/me -> "
          f"{ROLE_CLIENT['TECHNICIAN'].get('/api/v1/auth/me').status_code}")
    record(results, "04. Token gia / sua chu ky / tu che vai tro -> 401 (khong the nang quyen)",
           ok_forgery)

    # =================================================================
    # 05. TOKEN HẾT HẠN -> 401
    # =================================================================
    print_separator("05. TOKEN HET HAN -> 401")
    manager_user = db.query(User).filter(User.id == id_manager).first()
    expired_token = auth_service.create_access_token(manager_user, ttl_minutes=-60)["access_token"]
    expired = TestClient(app)
    expired.headers.update({"Authorization": f"Bearer {expired_token}"})
    expired_me = expired.get("/api/v1/auth/me")
    expired_products = expired.get("/api/v1/products/")
    manager_products = ROLE_CLIENT["MANAGER"].get("/api/v1/products/")
    print(f"    - /auth/me   (token het han 60 phut) -> HTTP {expired_me.status_code} | "
          f"detail: {expired_me.json().get('detail')}")
    print(f"    - /products/ (token het han 60 phut) -> HTTP {expired_products.status_code}")
    print(f"    - Token con han ({manager_token[:18]}...)          -> HTTP "
          f"{manager_products.status_code}")
    ok_expired = (
        expired_me.status_code == 401
        and expired_products.status_code == 401
        and manager_products.status_code == 200
    )
    record(results, "05. Token het han -> 401 (ke ca khi chu ky dung)", ok_expired)

    # =================================================================
    # 06. GET /auth/me -> ĐÚNG DANH TÍNH + VAI TRÒ + QUYỀN (TỪ CSDL)
    # =================================================================
    print_separator("06. GET /auth/me -> DUNG DANH TINH, VAI TRO VA QUYEN TU CSDL")
    me = ROLE_CLIENT["RECEPTIONIST"].get("/api/v1/auth/me").json()
    expected_perms = auth_service.permissions_for_role("RECEPTIONIST")
    db_receptionist = db.query(User).filter(User.id == id_receptionist).first()
    ok_me = (
        me.get("id") == id_receptionist
        and me.get("username") == db_receptionist.username
        and me.get("full_name") == db_receptionist.full_name
        and me.get("role") == "RECEPTIONIST"
        and me.get("role_label") == "Nhân viên tiếp nhận"
        and sorted(me.get("permissions", [])) == expected_perms
    )
    print(f"    - id/username/full_name : {me.get('id')} / {me.get('username')} / "
          f"{me.get('full_name')}")
    print(f"    - vai tro               : {me.get('role')} ({me.get('role_label')})")
    print(f"    - so quyen              : {len(me.get('permissions', []))} quyen"
          f" | khop ROLE_PERMISSIONS: {sorted(me.get('permissions', [])) == expected_perms}")
    print("    - khong co quyen dac biet: "
          f"ticket.reject={'ticket.reject' in me.get('permissions', [])} | "
          f"user.manage={'user.manage' in me.get('permissions', [])} | "
          f"product.manage={'product.manage' in me.get('permissions', [])}")
    record(results, "06. GET /auth/me tra dung danh tinh/vai tro/quyen cua phien hien tai", ok_me)

    # =================================================================
    # 07. ĐĂNG XUẤT THU HỒI TOKEN NGAY LẬP TỨC
    # =================================================================
    print_separator("07. DANG XUAT THU HOI TOKEN NGAY LAP TUC")
    temp_session, _ = login_client("technician01", DEMO_PASSWORDS["technician01"])
    temp_token = temp_session.headers["Authorization"].replace("Bearer ", "")
    before_logout = temp_session.get("/api/v1/auth/me").status_code
    logout_res = temp_session.post("/api/v1/auth/logout")
    after_logout_me = temp_session.get("/api/v1/auth/me").status_code
    after_logout_products = temp_session.get("/api/v1/products/").status_code

    # Token cũ nhét vào client khác vẫn bị chặn (thu hồi theo token, không theo client)
    revenge = TestClient(app)
    revenge.headers.update({"Authorization": f"Bearer {temp_token}"})
    revenge_code = revenge.get("/api/v1/auth/me").status_code
    # Tài khoản khác đang làm việc KHÔNG bị ảnh hưởng
    other_still_ok = ROLE_CLIENT["MANAGER"].get("/api/v1/auth/me").status_code == 200

    print(f"    - Truoc khi dang xuat : /auth/me -> {before_logout}")
    print(f"    - POST /auth/logout   : HTTP {logout_res.status_code} | "
          f"message: {logout_res.json().get('message')}")
    print(f"    - Sau khi dang xuat   : /auth/me -> {after_logout_me} | /products/ -> "
          f"{after_logout_products} | token cu o client khac -> {revenge_code}")
    print(f"    - Phien cua quan ly khac van lam viec binh thuong: {other_still_ok}")
    ok_logout = (
        before_logout == 200
        and logout_res.status_code == 200
        and after_logout_me == 401
        and after_logout_products == 401
        and revenge_code == 401
        and other_still_ok
    )
    record(results, "07. Dang xuat thu hoi token ngay (token cu -> 401, phien khac khong anh huong)",
           ok_logout)

    # =================================================================
    # 08. TÀI KHOẢN BỊ VÔ HIỆU HOÁ -> 401
    # =================================================================
    print_separator("08. TAI KHOAN BI VO HIEU HOA -> 401 (TOKEN DANG DUNG MAT HIEU LUC NGAY)")
    active_session, _ = login_client("receptionist01", DEMO_PASSWORDS["receptionist01"])
    before_disable = active_session.get("/api/v1/auth/me").status_code
    db_receptionist.active = False
    db.commit()
    after_disable = active_session.get("/api/v1/auth/me").status_code
    relogin_disabled = TestClient(app).post(
        "/api/v1/auth/login",
        json={"username": "receptionist01", "password": DEMO_PASSWORDS["receptionist01"]},
    ).status_code
    # Khôi phục trạng thái ban đầu để các mục minh chứng sau chạy bình thường
    db_receptionist.active = True
    db.commit()
    restored = TestClient(app).post(
        "/api/v1/auth/login",
        json={"username": "receptionist01", "password": DEMO_PASSWORDS["receptionist01"]},
    ).status_code
    print(f"    - Truoc khi vo hieu hoa: /auth/me -> {before_disable}")
    print(f"    - Sau khi vo hieu hoa  : /auth/me (token cu) -> {after_disable} | "
          f"dang nhap lai -> {relogin_disabled}")
    print(f"    - Khoi phuc tai khoan  : dang nhap lai -> {restored}")
    ok_inactive = (
        before_disable == 200
        and after_disable == 401
        and relogin_disabled == 401
        and restored == 200
    )
    record(results, "08. Tai khoan bi vo hieu hoa -> 401 ngay ca khi token con han", ok_inactive)

    # =================================================================
    # 09. MA TRẬN RBAC: VAI TRÒ GỌI API NGOÀI QUYỀN -> 403
    #     (chứng minh "ẩn menu trên giao diện KHÔNG đủ": gọi thẳng API vẫn bị chặn)
    # =================================================================
    print_separator("09. MA TRAN RBAC: GOI THANG API NGOAI QUYEN -> 403")
    product_payload = {"name": "San pham thu RBAC", "brand": "Test", "category": "Laptop",
                       "warranty_duration_months": 12, "description": "Kiem chung phan quyen"}
    customer_payload = {"full_name": "Khach Thu RBAC", "phone": "0999888777",
                        "email": "rbac@example.com", "address": "Ha Noi"}
    instance_payload = {"serial_number": "SN-RBAC-BYPASS-99", "customer_id": 1, "product_id": 1,
                        "purchase_date": "2026-06-01", "warranty_duration_months": 24}
    ticket_payload = {"serial_number": "SN-ASUS-OWNER-TEST-04", "customer_id": 1,
                      "service_center_id": 1, "created_by": id_receptionist,
                      "issue_description": "Kiem chung phan quyen RBAC"}
    new_user_payload = {"username": "ke-gia-danh", "password": "GiaDanh@123",
                        "full_name": "Ke Gian Danh", "role": "MANAGER"}

    forbidden_matrix = {
        "TECHNICIAN": [
            ("POST", "/api/v1/products/", product_payload),
            ("PUT", "/api/v1/products/1", product_payload),
            ("DELETE", "/api/v1/products/1", None),
            ("POST", "/api/v1/customers/", customer_payload),
            ("PUT", "/api/v1/customers/1", customer_payload),
            ("DELETE", "/api/v1/customers/1", None),
            ("POST", "/api/v1/product-instances/", instance_payload),
            ("DELETE", "/api/v1/product-instances/1", None),
            ("POST", "/api/v1/warranty-tickets/", ticket_payload),
            ("PATCH", "/api/v1/ai/results/1/review",
             {"reviewed_by": id_technician, "decision": "APPROVED"}),
            ("GET", "/api/v1/users/", None),
            ("POST", "/api/v1/users/", new_user_payload),
            ("PATCH", f"/api/v1/users/{id_technician}", {"role": "MANAGER"}),
        ],
        "RECEPTIONIST": [
            ("POST", "/api/v1/products/", product_payload),
            ("PUT", "/api/v1/products/1", product_payload),
            ("DELETE", "/api/v1/products/1", None),
            ("DELETE", "/api/v1/customers/1", None),
            ("GET", "/api/v1/users/", None),
            ("POST", "/api/v1/users/", new_user_payload),
            ("PATCH", f"/api/v1/users/{id_receptionist}", {"role": "MANAGER"}),
        ],
    }
    allowed_matrix = {
        "TECHNICIAN": [
            ("GET", "/api/v1/products/", None),
            ("GET", "/api/v1/customers/", None),
            ("GET", "/api/v1/product-instances/", None),
            ("GET", "/api/v1/warranty-tickets/", None),
            ("GET", "/api/v1/warranty-tickets/meta/demo-data", None),
            ("GET", "/api/v1/ai/config", None),
            ("GET", "/api/v1/ai/demo/users", None),
            ("POST", "/api/v1/ai/tickets/999999/classify-error", None),
            ("PATCH", "/api/v1/warranty-tickets/999999/status",
             {"new_status": "REPAIRING", "changed_by": id_technician}),
        ],
        "RECEPTIONIST": [
            ("GET", "/api/v1/products/", None),
            ("GET", "/api/v1/customers/", None),
            ("GET", "/api/v1/warranty-tickets/", None),
            ("GET", "/api/v1/ai/config", None),
        ],
        "MANAGER": [
            ("GET", "/api/v1/users/", None),
            ("GET", "/api/v1/ai/config", None),
        ],
    }

    ok_matrix = True
    for role_name, calls in forbidden_matrix.items():
        session = ROLE_CLIENT[role_name]
        blocked = 0
        for method, url, payload in calls:
            code = session.request(method, url, json=payload).status_code
            blocked += 1 if code == 403 else 0
            if code != 403:
                ok_matrix = False
                print(f"    [!!] {role_name:<13} {method:<6} {url:<42} -> HTTP {code} (DANG LE 403)")
        print(f"    - {role_name:<13} ngoai quyen: {blocked}/{len(calls)} bi chan 403")

    for role_name, calls in allowed_matrix.items():
        session = ROLE_CLIENT[role_name]
        passed = 0
        for method, url, payload in calls:
            code = session.request(method, url, json=payload).status_code
            ok_code = code not in (401, 403) and code < 500
            passed += 1 if ok_code else 0
            if not ok_code:
                ok_matrix = False
                print(f"    [!!] {role_name:<13} {method:<6} {url:<42} -> HTTP {code} "
                      f"(KHONG duoc 401/403)")
        print(f"    - {role_name:<13} trong quyen: {passed}/{len(calls)} duoc phep (khong 401/403)")
    record(results, "09. Ma tran RBAC: ngoai quyen -> 403, trong quyen -> duoc phep", ok_matrix)

    # =================================================================
    # 10 + 11. NHÂN VIÊN CHỈ ĐƯỢC GHI DANH CHÍNH MÌNH &
    #          CHỈ QUẢN LÝ ĐƯỢC XÁC NHẬN TỪ CHỐI BẢO HÀNH
    # =================================================================
    print_separator("10+11. NGUOI THUC HIEN & QUYEN TU CHOI BAO HANH (REJECTED)")
    manager = ROLE_CLIENT["MANAGER"]
    receptionist = ROLE_CLIENT["RECEPTIONIST"]
    technician = ROLE_CLIENT["TECHNICIAN"]

    new_instance = manager.post("/api/v1/product-instances/", json={
        "serial_number": "SN-RBAC-ACTOR-01", "customer_id": 1, "product_id": 1,
        "purchase_date": "2026-06-01", "warranty_duration_months": 24,
        "description": "Thiet bi phuc vu minh chung phan quyen Dot 7",
    })
    new_ticket = manager.post("/api/v1/warranty-tickets/", json={
        "serial_number": "SN-RBAC-ACTOR-01", "customer_id": 1, "service_center_id": 1,
        "created_by": id_receptionist, "issue_description": "Kiem chung nguoi thuc hien",
    })
    ticket_id = new_ticket.json().get("id") if new_ticket.status_code == 201 else None
    created_by_receptionist = new_ticket.json().get("created_by") if ticket_id else None
    print(f"    - Quan ly tao thiet bi (HTTP {new_instance.status_code}) + phieu "
          f"{new_ticket.json().get('ticket_code')} ghi danh tiep nhan "
          f"(created_by={created_by_receptionist}) -> HTTP {new_ticket.status_code}")

    # (a) Kỹ thuật viên tự ghi danh mình -> hợp lệ
    self_update = technician.patch(f"/api/v1/warranty-tickets/{ticket_id}/status", json={
        "new_status": "INSPECTING", "changed_by": id_technician,
        "note": "Ky thuat vien tiep nhan may (ghi danh chinh minh)",
    })
    # (b) Kỹ thuật viên ghi danh người khác -> 403
    fake_update = technician.patch(f"/api/v1/warranty-tickets/{ticket_id}/status", json={
        "new_status": "REPAIRING", "changed_by": id_receptionist,
        "note": "Khai khong nguoi thuc hien",
    })
    db.rollback()
    row_after_fake = db.query(WarrantyTicket).filter(WarrantyTicket.id == ticket_id).first()
    # Chụp ngay giá trị nguyên thuỷ: đối tượng ORM có thể bị làm mới (hết hạn) về sau
    status_after_fake = row_after_fake.status
    history_count_after_fake = len(db.query(TicketStatusHistory).filter(
        TicketStatusHistory.ticket_id == ticket_id).all())
    print(f"    [a] Ky thuat vien ghi danh CHINH MINH (changed_by={id_technician}) -> "
          f"HTTP {self_update.status_code}")
    print(f"    [b] Ky thuat vien ghi danh NGUOI KHAC (changed_by={id_receptionist}) -> "
          f"HTTP {fake_update.status_code} | trang thai khong doi: {status_after_fake}")

    # (c) Nhân viên tiếp nhận ghi danh người khác khi tạo phiếu -> 403
    fake_create = receptionist.post("/api/v1/warranty-tickets/", json={
        "serial_number": "SN-ASUS-OWNER-TEST-04", "customer_id": 1, "service_center_id": 1,
        "created_by": id_technician, "issue_description": "Khai khong nguoi tiep nhan",
    })
    # (d) Nhân viên tiếp nhận ghi danh chính mình -> tạo phiếu thành công
    real_create = receptionist.post("/api/v1/warranty-tickets/", json={
        "serial_number": "SN-ASUS-OWNER-TEST-04", "customer_id": 1, "service_center_id": 1,
        "created_by": id_receptionist,
        "issue_description": "Tiep nhan hop le (ghi danh chinh minh)",
    })
    print(f"    [c] Tiep nhan ghi danh NGUOI KHAC (created_by={id_technician}) -> "
          f"HTTP {fake_create.status_code} | detail: {fake_create.json().get('detail')}")
    print(f"    [d] Tiep nhan ghi danh CHINH MINH (created_by={id_receptionist}) -> "
          f"HTTP {real_create.status_code} | phieu {real_create.json().get('ticket_code')}")

    # (e) Kỹ thuật viên xác nhận TỪ CHỐI bảo hành -> 403 (thiếu quyền ticket.reject)
    tech_reject = technician.patch(f"/api/v1/warranty-tickets/{ticket_id}/status", json={
        "new_status": "REJECTED", "changed_by": id_technician,
        "rejection_reason": "Khong thuoc pham vi bao hanh (y dinh tu choi cua ky thuat vien)",
    })
    # (f) Nhân viên tiếp nhận cũng không được từ chối
    rec_reject = receptionist.patch(f"/api/v1/warranty-tickets/{ticket_id}/status", json={
        "new_status": "REJECTED", "changed_by": id_receptionist,
        "rejection_reason": "Khong thuoc pham vi bao hanh (y dinh tu choi cua tiep nhan)",
    })
    db.rollback()
    row_after_reject_attempts = db.query(WarrantyTicket).filter(
        WarrantyTicket.id == ticket_id).first()
    status_after_reject_attempts = row_after_reject_attempts.status
    reason_after_reject_attempts = row_after_reject_attempts.rejection_reason
    history_count_after_reject_attempts = len(db.query(TicketStatusHistory).filter(
        TicketStatusHistory.ticket_id == ticket_id).all())
    print(f"    [e] Ky thuat vien tu choi bao hanh -> HTTP {tech_reject.status_code} | "
          f"detail: {tech_reject.json().get('detail')}")
    print(f"    [f] Tiep nhan tu choi bao hanh    -> HTTP {rec_reject.status_code}")
    print(f"    => Phieu van giu nguyen trang thai: {status_after_reject_attempts} | "
          f"chua co ly do tu choi: {reason_after_reject_attempts is None} | "
          f"so lan doi trang thai: {history_count_after_reject_attempts}")

    # (g) Quản lý xác nhận từ chối -> thành công, lưu đủ lý do + lịch sử
    manager_reject = manager.patch(f"/api/v1/warranty-tickets/{ticket_id}/status", json={
        "new_status": "REJECTED", "changed_by": id_manager,
        "rejection_reason": "Thiet bi da bi thao roi, khong thuoc pham vi bao hanh.",
    })
    db.rollback()
    row_after_manager = db.query(WarrantyTicket).filter(WarrantyTicket.id == ticket_id).first()
    status_after_manager = row_after_manager.status
    reason_after_manager = row_after_manager.rejection_reason
    history_rows = db.query(TicketStatusHistory).filter(
        TicketStatusHistory.ticket_id == ticket_id).all()
    # Chuyển ngay sang dữ liệu nguyên thuỷ (tuple) để không phụ thuộc vòng đời đối tượng ORM
    history_plain = [(h.from_status, h.to_status, int(h.changed_by)) for h in history_rows]
    reject_history = [h for h in history_plain if h[1] == "REJECTED"]
    print(f"    [g] Quan ly xac nhan TU CHOI -> HTTP {manager_reject.status_code} | trang thai: "
          f"{status_after_manager} | ly do da luu: {bool(reason_after_manager)}")
    print(f"        Lich su trang thai: {history_plain}")
    print(f"        So ban ghi lich su: {len(history_plain)} | so lan TU CHOI: "
          f"{len(reject_history)} (nguoi thuc hien: {reject_history[0][2] if reject_history else '-'})")

    ok_actor = (
        new_instance.status_code == 201
        and new_ticket.status_code == 201
        and int(created_by_receptionist) == id_receptionist
        and self_update.status_code == 200
        and fake_update.status_code == 403
        and status_after_fake == "INSPECTING"
        and history_count_after_fake == 2
        and fake_create.status_code == 403
        and real_create.status_code == 201
        and int(real_create.json().get("created_by")) == id_receptionist
    )
    record(results, "10. Nhan vien chi duoc ghi danh CHINH MINH; quan ly duoc ghi danh thay",
           ok_actor)

    ok_reject = (
        tech_reject.status_code == 403
        and rec_reject.status_code == 403
        and status_after_reject_attempts == "INSPECTING"
        and reason_after_reject_attempts is None
        and history_count_after_reject_attempts == 2
        and manager_reject.status_code == 200
        and status_after_manager == "REJECTED"
        and bool(reason_after_manager)
        and len(reject_history) == 1
        and reject_history[0][0] == "INSPECTING"
        and reject_history[0][2] == id_manager
    )
    record(results, "11. Chi QUAN LY duoc xac nhan TU CHOI bao hanh (REJECTED) + luu lich su",
           ok_reject)

    # =================================================================
    # 12. MẬT KHẨU CHỈ LƯU DẠNG BĂM PBKDF2 + SALT RIÊNG
    # =================================================================
    print_separator("12. MAT KHAU CHI LUU DANG BAM PBKDF2 + SALT RIENG (KHONG LUU THO)")
    db.rollback()
    all_users = db.query(User).all()
    hashes_ok = True
    raw_leak = []
    matched_user = None
    for u in all_users:
        stored = u.password_hash or ""
        if not stored.startswith("pbkdf2_sha256$") or len(stored.split("$")) != 4:
            hashes_ok = False
        if any(raw in stored for raw in DEMO_PASSWORDS.values()):
            raw_leak.append(u.username)
        if u.username in DEMO_PASSWORDS and auth_service.verify_password(
            DEMO_PASSWORDS[u.username], stored
        ):
            matched_user = u.username
    distinct_hashes = {u.password_hash for u in all_users}
    first_hash = all_users[0].password_hash
    same_password_twice = auth_service.hash_password("Manager@123")
    same_password_again = auth_service.hash_password("Manager@123")
    wrong_password_rejected = not auth_service.verify_password("sai-mat-khau", first_hash)
    print(f"    - So tai khoan kiem tra: {len(all_users)} | tat ca dung dinh dang "
          f"pbkdf2_sha256$iter$salt$hash: {hashes_ok}")
    print(f"    - So hash khac nhau: {len(distinct_hashes)}/{len(all_users)} "
          f"(salt rieng cho tung tai khoan)")
    print(f"    - Mat khau tho xuat hien trong CSDL: {raw_leak if raw_leak else 'KHONG'}")
    print(f"    - Cung mat khau bam 2 lan cho 2 ket qua khac nhau: "
          f"{same_password_twice != same_password_again}")
    print(f"    - Vi du hash: {first_hash[:46]}...")
    print(f"    - Dang nhap dung mat khau duoc xac thuc: {matched_user} | "
          f"mat khau sai bi tu choi: {wrong_password_rejected}")
    ok_hash = (
        hashes_ok
        and not raw_leak
        and len(distinct_hashes) == len(all_users)
        and same_password_twice != same_password_again
        and matched_user is not None
        and wrong_password_rejected
    )
    record(results, "12. Mat khau luu dang bam PBKDF2-HMAC-SHA256 + salt rieng (khong luu tho)",
           ok_hash)

    # =================================================================
    # 13. VAI TRÒ LUÔN LẤY TỪ CSDL (TOKEN/FRONTEND KHÔNG QUYẾT ĐỊNH ĐƯỢC QUYỀN)
    # =================================================================
    print_separator("13. VAI TRO LUON LAY TU CSDL (DOI VAI TRO CO HIEU LUC NGAY)")
    token_payload = json.loads(auth_service._b64url_decode(tech_token.split(".")[1]).decode("utf-8"))
    token_role_claim = token_payload.get("rol")
    before_promote = technician.get("/api/v1/users/").status_code

    db.rollback()
    db_technician = db.query(User).filter(User.id == id_technician).first()
    db_technician.role = "MANAGER"          # Quản lý thăng cấp cho nhân viên này
    db.commit()
    after_promote_users = technician.get("/api/v1/users/").status_code
    me_after_promote = technician.get("/api/v1/auth/me").json()

    db.rollback()
    db_technician = db.query(User).filter(User.id == id_technician).first()
    db_technician.role = "TECHNICIAN"       # Hạ quyền trở lại như ban đầu
    db.commit()
    after_demote_users = technician.get("/api/v1/users/").status_code

    print(f"    - Token phat hanh khi vai tro la: {token_role_claim} (payload token KHONG doi)")
    print(f"    - Truoc khi thang cap: GET /users/ -> {before_promote} "
          f"(403 = dung quyen ky thuat vien)")
    print(f"    - Sau khi thang cap trong CSDL: GET /users/ -> {after_promote_users} | "
          f"vai tro /auth/me: {me_after_promote.get('role')} ({me_after_promote.get('role_label')})"
          f" | so quyen: {len(me_after_promote.get('permissions', []))}")
    print(f"    - Sau khi ha quyen tro lai: GET /users/ -> {after_demote_users} (403 tro lai)")
    ok_role_from_db = (
        token_role_claim == "TECHNICIAN"
        and before_promote == 403
        and after_promote_users == 200
        and me_after_promote.get("role") == "MANAGER"
        and len(me_after_promote.get("permissions", [])) > 0
        and after_demote_users == 403
    )
    record(results, "13. Quyen luon doc tu CSDL: doi vai tro co hieu luc ngay voi token dang dung",
           ok_role_from_db)

    # =================================================================
    # TỔNG HỢP
    # =================================================================
    db.close()
    print_separator("BANG TONG HOP MINH CHUNG DANG NHAP & PHAN QUYEN")
    passed = sum(1 for _, status_str in results if status_str == "PASS")
    for name, status_str in results:
        print(f"  {name:<78} : [{status_str}]")
    print(f"\n  => TONG KET: {passed}/{len(results)} PASS | FAIL: {len(results) - passed}")
    print_separator()
    all_passed = passed == len(results)
    if all_passed:
        print("  >>> XAC NHAN: 100% MINH CHUNG DANG NHAP & PHAN QUYEN (RBAC) DEU DAT (PASS)! <<<")
    else:
        print("  >>> CANH BAO: CO MUC MINH CHUNG CHUA DAT, KIEM TRA LAI CHI TIET. <<<")
    print("=" * 75 + "\n")
    return all_passed


if __name__ == "__main__":
    # Exit code: 0 = toàn bộ PASS, 1 = có mục FAIL
    sys.exit(0 if run_all_tests() else 1)
