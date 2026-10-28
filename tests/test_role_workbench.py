"""
KIEM THU MAN HINH CONG VIEC THEO VAI TRO (6 TRANG THAI REFACTORED)

Cach chay:
    .\\dev.ps1 workbench           (hoac: py -3.12 tests\\test_role_workbench.py)

Bo kiem thu nay kiem tra: "sau khi dang nhap, moi vai tro co nhin thay dung viec cua minh khong?"
theo dung 6 trang thai nghiep vu chuan:
    RECEIVED -> INSPECTING -> REPAIRING -> COMPLETED -> RETURNED (Luong sua chua)
    INSPECTING -> REJECTED -> RETURNED (Luong tu choi)

    CASE A: Tiep nhan may moi  -> bang dieu khien cua Tiep nhan cap nhat ngay.
    CASE B: Ky thuat vien      -> thay phieu duoc giao, kiem tra, sua chua, chuyen hoan tat cho tra may.
    CASE C: Tra may           -> Tiep nhan thay "Cho tra may" va xac nhan tra may (dong phieu RETURNED).
    CASE D: Quan ly           -> thay toan bo tinh hinh + "viec can chu y" + lich su xu ly 5 buoc.
    CASE E: Phan quyen        -> thao tac ngoai quyen bi chan 403 o backend.
    CASE F: Menu theo vai tro -> /auth/me tra dung menu + nhom menu (backend quy dinh).
    CASE G: "Viec cua toi"    -> loc mine=1 chay o tang SQL, khop giua danh sach va so lieu.
    CASE H: Nut hanh dong     -> moi dong danh sach co nhan nut theo trang thai + quyen.

Luu y: File kiem thu nay chay tren CSDL tam thoi co lap (tempfile SQLite),
khong can thiep vao database/baohanh_ai.db.
"""
import sys
import os
import tempfile
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Cấu trúc dự án: tests/ ở gốc, code trong backend/
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db, Base
import app.database as app_db
from app.models import User
from app.services.schema_migration import ensure_schema_upgrades
from seed_data import DEMO_ACCOUNTS, seed

# Thiết lập CSDL tạm độc lập
TEMP_DB_FILE = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
temp_db_path = TEMP_DB_FILE.name
TEMP_DB_FILE.close()

TEST_DATABASE_URL = f"sqlite:///{temp_db_path}"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

app_db.engine = test_engine
app_db.SessionLocal = TestSessionLocal

def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

RESULTS = []  # [(case, tên kiểm tra, ok, ghi chú)]
WORKBOARD_URL = "/api/v1/warranty-tickets/workboard"


def print_separator(title=""):
    print("\n" + "=" * 78)
    if title:
        print(f"  {title}")
        print("=" * 78)


def record(case, name, ok, note=""):
    RESULTS.append((case, name, bool(ok), note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {case}: {name}")
    if note:
        print(f"          -> {note}")


def login_client(username, password):
    """Trả về TestClient đã gắn header Authorization của tài khoản vừa đăng nhập."""
    client = TestClient(app)
    res = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    if res.status_code != 200:
        raise RuntimeError(f"Dang nhap that bai ({username}): HTTP {res.status_code}")
    client.headers.update({"Authorization": f"Bearer {res.json()['access_token']}"})
    return client


def user_id_of(role):
    db = TestSessionLocal()
    try:
        user = db.query(User).filter(User.role == role).first()
        return user.id if user else None
    finally:
        db.close()


def group_by_key(workboard):
    return {group["key"]: group for group in workboard.get("groups", [])}


def codes_of(group):
    return [item["ticket_code"] for item in (group or {}).get("items", [])]


def new_device_and_ticket(manager, receptionist, serial, issue, customer_id=1, product_id=1):
    """Tạo thiết bị + phiếu mới ở trạng thái RECEIVED (dữ liệu thật)."""
    manager.post(
        "/api/v1/product-instances/",
        json={
            "serial_number": serial,
            "customer_id": customer_id,
            "product_id": product_id,
            "purchase_date": "2026-06-01",
            "warranty_duration_months": 24,
            "description": "Thiet bi phuc vu kiem thu man hinh cong viec theo vai tro",
        },
    )
    res = receptionist.post(
        "/api/v1/warranty-tickets/",
        json={
            "serial_number": serial,
            "customer_id": customer_id,
            "service_center_id": 1,
            "created_by": user_id_of("RECEPTIONIST"),
            "issue_description": issue,
        },
    )
    return res


def patch_status(client, ticket_id, payload):
    return client.patch(f"/api/v1/warranty-tickets/{ticket_id}/status", json=payload)


def run_all_tests():
    # Khởi tạo CSDL test độc lập
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    ensure_schema_upgrades(test_engine)
    init_db_session = TestSessionLocal()
    try:
        seed(session=init_db_session, target_engine=test_engine)
    finally:
        init_db_session.close()

    print_separator("BAOHANHAI - KIEM THU MAN HINH CONG VIEC THEO VAI TRO (6 TRANG THAI)")
    print(f"  Thoi diem chay: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("  Cau hoi kiem chung: sau khi dang nhap, moi vai tro co thay dung viec cua minh?")

    manager = login_client(*DEMO_ACCOUNTS[0][:2])
    receptionist = login_client(*DEMO_ACCOUNTS[1][:2])
    technician = login_client(*DEMO_ACCOUNTS[2][:2])
    clients = {"MANAGER": manager, "RECEPTIONIST": receptionist, "TECHNICIAN": technician}
    id_technician = user_id_of("TECHNICIAN")
    id_receptionist = user_id_of("RECEPTIONIST")
    id_manager = user_id_of("MANAGER")
    print(f"  Da dang nhap 3 vai tro | receptionist={id_receptionist} technician={id_technician}")

    # =================================================================
    # CASE F: MENU THEO VAI TRO (backend tra ve, khong phai giao dien tu doan)
    # =================================================================
    print_separator("CASE F: MENU THEO VAI TRO (/auth/me tra ve menus)")
    menus = {}
    for role, client in clients.items():
        menus[role] = client.get("/api/v1/auth/me").json().get("menus", [])

    def tabs(role, group=None):
        return [menu["tab"] for menu in menus[role] if group is None or menu["group"] == group]

    mgr_tabs, rec_tabs, tech_tabs = tabs("MANAGER"), tabs("RECEPTIONIST"), tabs("TECHNICIAN")
    tech_reference = tabs("TECHNICIAN", "reference")
    case_f_ok = (
        "accounts" in mgr_tabs
        and "accounts" not in rec_tabs
        and "accounts" not in tech_tabs
        and tech_tabs == ["dashboard", "tickets", "lookup", "ai"]
        and len(tech_reference) == 0
        and all(menu["permission"] for menu in menus["MANAGER"])
        and all(menu["label"] for menu in menus["TECHNICIAN"])
    )
    record(
        "CASE F",
        "Menu theo vai tro: Quan ly co Tai khoan; Ky thuat vien chi co dung 4 muc viec chinh",
        case_f_ok,
        f"MANAGER={mgr_tabs} | RECEPTIONIST={rec_tabs} | TECHNICIAN={tech_tabs}",
    )

    # =================================================================
    # KHOI TAO DU LIEU KIEM THU (2 thiet bi that + 2 phieu moi)
    # =================================================================
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    serial_a = f"SN-WB-A-{stamp}"
    serial_b = f"SN-WB-B-{stamp}"
    res_a = new_device_and_ticket(manager, receptionist, serial_a, "Laptop khong len nguon sau khi cam sac")
    res_b = new_device_and_ticket(manager, receptionist, serial_b, "Man hinh chap chon, loa bi re")
    if res_a.status_code != 201 or res_b.status_code != 201:
        record("SETUP", "Tao 2 thiet bi + 2 phieu de kiem thu", False,
               f"HTTP phieu A = {res_a.status_code}, phieu B = {res_b.status_code}")
        return False
    ticket_a = res_a.json()
    ticket_b = res_b.json()
    print(f"  Phieu kiem thu: {ticket_a['ticket_code']} | {ticket_b['ticket_code']}")

    # =================================================================
    # CASE A: TIEP NHAN MAY MOI -> BANG DIEU KHIEN CUA TIEP NHAN CAP NHAT
    # =================================================================
    print_separator("CASE A: TIEP NHAN MAY MOI -> 'VIEC CUA TOI' CAP NHAT NGAY")
    wb_rec_before = receptionist.get(WORKBOARD_URL).json()
    group_to_receive = group_by_key(wb_rec_before).get("to_receive", {})
    count_before = group_to_receive.get("count", 0)
    quick_keys = [action["key"] for action in wb_rec_before.get("quick_actions", [])]
    case_a_ok = (
        wb_rec_before.get("role") == "RECEPTIONIST"
        and bool(group_to_receive)
        and ticket_a["ticket_code"] in codes_of(group_to_receive)
        and count_before >= 1
        and "receive" in quick_keys
        and any("trả máy" in note for note in wb_rec_before.get("notes", []))
        and bool(wb_rec_before.get("cards"))
    )
    record(
        "CASE A",
        "Tiep nhan: dashboard hien 'Can tiep nhan' + nut 'Tiep nhan may moi' + phieu vua tao",
        case_a_ok,
        f"nhom 'Can tiep nhan' = {count_before} phieu | co phieu vua tao: "
        f"{ticket_a['ticket_code'] in codes_of(group_to_receive)} | thao tac nhanh = {quick_keys}",
    )

    # Thẻ "Tiếp nhận" và nhóm "Cần tiếp nhận" phải cùng số liệu (cùng nguồn dữ liệu)
    card_received = next(
        (card["count"] for card in wb_rec_before.get("cards", []) if card["key"] == "RECEIVED"), None
    )
    record(
        "CASE A2",
        "So lieu the 'Moi tiep nhan' khop voi nhom 'Can tiep nhan' (cung nguon du lieu)",
        card_received == count_before,
        f"the = {card_received} | nhom = {count_before}",
    )

    # =================================================================
    # CASE G: "VIEC CUA TOI" (mine=1) LOC O TANG SQL - KHOP DANH SACH & SO LIEU
    # =================================================================
    print_separator("CASE G: 'VIEC CUA TOI' (mine=1) - LOC THAT O BACKEND")
    # Quản lý phân công KTV cho phiếu B và KTV chuyển sang INSPECTING -> REPAIRING
    assign_b = manager.post(
        f"/api/v1/warranty-tickets/{ticket_b['id']}/assign",
        json={"technician_id": id_technician, "note": "Phan cong KTV kiem tra may B"}
    )
    patch_status(technician, ticket_b["id"], {
        "new_status": "INSPECTING", "changed_by": id_technician,
        "note": "Da nhan may B, bat dau kiem tra.",
    })
    patch_status(technician, ticket_b["id"], {
        "new_status": "REPAIRING", "changed_by": id_technician,
        "diagnosis_note": "Cap tin hieu man hinh bi long, loa phai bi re. Du dieu kien bao hanh.",
        "is_warranty_eligible": True,
        "error_category_id": 2,
    })
    tech_mine_list = technician.get(
        "/api/v1/warranty-tickets/", params={"mine": "1", "limit": 200}
    ).json()
    tech_mine_stats = technician.get(
        "/api/v1/warranty-tickets/stats/summary", params={"mine": 1}
    ).json()
    rec_mine_list = receptionist.get(
        "/api/v1/warranty-tickets/", params={"mine": "1", "limit": 200}
    ).json()
    tech_codes = [row["ticket_code"] for row in tech_mine_list]
    rec_codes = [row["ticket_code"] for row in rec_mine_list]
    sum_tech_mine = sum(
        tech_mine_stats.get(key, 0)
        for key in ["received", "inspecting", "repairing", "completed", "rejected", "returned"]
    )
    case_g_ok = (
        assign_b.status_code == 200
        and ticket_b["ticket_code"] in tech_codes
        and ticket_a["ticket_code"] not in tech_codes
        # Phiếu A do tiếp nhận lập và chưa ai xử lý thêm -> nằm trong "việc của tôi" của tiếp nhận
        and ticket_a["ticket_code"] in rec_codes
        and ticket_b["ticket_code"] not in rec_codes
        and len(tech_mine_list) == sum_tech_mine
        and tech_mine_stats.get("scope") == "MINE"
        # Phân trang vẫn đúng: lấy 1 dòng "việc của tôi" phải là phiếu của chính mình
        and all(
            row["handler_id"] == id_technician
            for row in technician.get(
                "/api/v1/warranty-tickets/", params={"mine": "1", "limit": 1}
            ).json()
        )
    )
    record(
        "CASE G",
        "Loc mine=1 o SQL: danh sach = phieu cua chinh minh, so lieu khop, phan trang dung",
        case_g_ok,
        f"ky thuat co {len(tech_mine_list)} phieu (tong so lieu mine = {sum_tech_mine}) | "
        f"phieu B thuoc ky thuat: {ticket_b['ticket_code'] in tech_codes} | "
        f"phieu A thuoc tiep nhan: {ticket_a['ticket_code'] in rec_codes} | "
        f"phieu B khong nam trong viec cua tiep nhan: {ticket_b['ticket_code'] not in rec_codes}",
    )

    # =================================================================
    # CASE B: KY THUAT VIEN - KIEM TRA -> SUA CHUA -> HOAN TAT CHO TRA MAY
    # =================================================================
    print_separator("CASE B: KY THUAT VIEN - KIEM TRA -> SUA CHUA -> HOAN TAT")
    # Quản lý phân công phiếu A cho KTV để KTV thấy trong công việc được giao
    manager.post(
        f"/api/v1/warranty-tickets/{ticket_a['id']}/assign",
        json={"technician_id": id_technician, "note": "Phan cong KTV kiem tra may A"}
    )
    wb_tech = technician.get(WORKBOARD_URL).json()
    tech_groups = group_by_key(wb_tech)
    assigned_received = tech_groups.get("assigned_received", {})
    item_a = next(
        (item for item in assigned_received.get("items", []) if item["ticket_code"] == ticket_a["ticket_code"]),
        {},
    )
    case_b1_ok = (
        wb_tech.get("role") == "TECHNICIAN"
        and wb_tech.get("title") == "Công việc kỹ thuật"
        and bool(assigned_received)
        and assigned_received.get("scope") == "MINE"
        and bool(item_a)
        and item_a.get("action_kind") == "transition"
        and item_a.get("primary_action", {}).get("target") == "INSPECTING"
        and "receive" not in [action["key"] for action in wb_tech.get("quick_actions", [])]
        and any("trả máy" in note for note in wb_tech.get("notes", []))
    )
    record(
        "CASE B1",
        "Ky thuat: nhom 'Phieu duoc giao' co phieu moi + nut theo vai tro, khong co tiep nhan may",
        case_b1_ok,
        f"nhom 'Phieu duoc giao' = {assigned_received.get('count')} | nhan nut theo vai tro = "
        f"'{assigned_received.get('action_label')}' | thao tac nhanh = "
        f"{[action['key'] for action in wb_tech.get('quick_actions', [])]}",
    )

    step_inspect = patch_status(technician, ticket_a["id"], {
        "new_status": "INSPECTING", "changed_by": id_technician,
        "note": "Da nhan may tu quay, bat dau kiem tra bo mach nguon.",
    })
    step_repair = patch_status(technician, ticket_a["id"], {
        "new_status": "REPAIRING", "changed_by": id_technician,
        "note": "Ket luan: IC nguon chay, du dieu kien bao hanh.",
        "diagnosis_note": "IC nguon RT8205 chay, tu dien loc nguon phong.",
        "is_warranty_eligible": True,
        "error_category_id": 1,
    })
    step_complete = patch_status(technician, ticket_a["id"], {
        "new_status": "COMPLETED", "changed_by": id_technician,
        "note": "Da sua xong, may dat yeu cau kiem tra sau sua, chuyen cho tra may.",
        "repair_content": "Thay IC nguon RT8205 va 2 tu dien loc, do lai dien ap 19V on dinh.",
        "repair_parts": "IC nguon RT8205, tu dien 470uF",
        "repair_test_passed": True,
        "repair_test_note": "Chay thu tai 100% lien tuc 30 phut khong sap nguon.",
    })
    wb_tech_after = technician.get(WORKBOARD_URL).json()
    tech_after_groups = group_by_key(wb_tech_after)
    completed_group = tech_after_groups.get("completed", {})
    my_tickets_codes = [row["ticket_code"] for row in wb_tech_after.get("my_tickets", [])]
    case_b2_ok = (
        step_inspect.status_code == 200
        and step_repair.status_code == 200
        and step_complete.status_code == 200
        and ticket_a["ticket_code"] in codes_of(completed_group)
        and completed_group.get("scope") == "MINE"
        and ticket_a["ticket_code"] in my_tickets_codes
        # Ở bước "hoàn tất (chờ trả máy)", kỹ thuật viên KHÔNG có nút xác nhận trả máy (RETURNED)
        and all(
            action.get("target") != "RETURNED"
            for item in completed_group.get("items", [])
            for action in item.get("available_actions", [])
        )
    )
    record(
        "CASE B2",
        "Ky thuat: kiem tra -> sua chua -> hoan tat cho tra may; khong tu y tra may cho khach",
        case_b2_ok,
        f"HTTP kiem tra={step_inspect.status_code} sua={step_repair.status_code} "
        f"hoan tat={step_complete.status_code} | nhom 'Da hoan tat' co phieu A: "
        f"{ticket_a['ticket_code'] in codes_of(completed_group)}",
    )

    # =================================================================
    # CASE C: TRA MAY - TIEP NHAN XAC NHAN DA TRA MAY (RETURNED)
    # =================================================================
    print_separator("CASE C: TRA MAY - TIEP NHAN XAC NHAN DA TRA MAY (RETURNED)")
    wb_rec_waiting = receptionist.get(WORKBOARD_URL).json()
    rec_completed_group = group_by_key(wb_rec_waiting).get("completed_return", {})
    item_waiting = next(
        (item for item in rec_completed_group.get("items", []) if item["ticket_code"] == ticket_a["ticket_code"]),
        {},
    )
    handover_res = patch_status(receptionist, ticket_a["id"], {
        "new_status": "RETURNED", "changed_by": id_receptionist,
        "handover_note": "Khach da kiem tra may va nhan lai cung phieu bao hanh.",
        "note": "Ban giao may tai quay, dong phieu bao hanh.",
    })
    wb_rec_done = receptionist.get(WORKBOARD_URL).json()
    rec_group_done = group_by_key(wb_rec_done).get("completed_return", {})
    case_c_ok = (
        ticket_a["ticket_code"] in codes_of(rec_completed_group)
        and item_waiting.get("primary_action", {}).get("target") == "RETURNED"
        and item_waiting.get("action_kind") == "transition"
        and handover_res.status_code == 200
        and ticket_a["ticket_code"] not in codes_of(rec_group_done)
    )
    record(
        "CASE C",
        "Tiep nhan: thay 'Cho tra may' -> xac nhan da tra may -> phieu roi khoi hang cho",
        case_c_ok,
        f"truoc khi tra co phieu A = {ticket_a['ticket_code'] in codes_of(rec_completed_group)} | "
        f"nut = {item_waiting.get('primary_action', {}).get('button_label')} | "
        f"HTTP tra may = {handover_res.status_code}",
    )

    # =================================================================
    # CASE D: QUAN LY - THAY TOAN BO TINH HINH + "VIEC CAN CHU Y" + LICH SU
    # =================================================================
    print_separator("CASE D: QUAN LY - TOAN BO TINH HINH + VIEC CAN CHU Y + LICH SU")
    wb_mgr = manager.get(WORKBOARD_URL).json()
    mgr_groups = group_by_key(wb_mgr)
    attention = wb_mgr.get("attention", [])
    attention_b = next((item for item in attention if item["ticket_code"] == ticket_b["ticket_code"]), {})
    detail_b = manager.get(f"/api/v1/warranty-tickets/{ticket_b['id']}").json()
    detail_a = manager.get(f"/api/v1/warranty-tickets/{ticket_a['id']}").json()
    card_keys = [card["key"] for card in wb_mgr.get("cards", [])]
    case_d_ok = (
        wb_mgr.get("role") == "MANAGER"
        and wb_mgr.get("title") == "Tổng quan trung tâm"
        and all(key in card_keys for key in ["TOTAL", "RECEIVED", "INSPECTING", "REPAIRING",
                                             "COMPLETED", "REJECTED", "RETURNED"])
        and set(mgr_groups.keys()) >= {"received", "inspecting", "repairing", "completed", "rejected", "returned"}
        # Phiếu B đang sửa chữa nhưng chưa ghi nội dung sửa chữa -> nằm trong "việc cần chú ý"
        and bool(attention_b)
        and "Chưa cập nhật nội dung" in attention_b.get("reason", "")
        and len(detail_a.get("history", [])) in (5, 6)
        and detail_b.get("status") == "REPAIRING"
        and bool(wb_mgr.get("active_tickets"))
    )
    record(
        "CASE D",
        "Quan ly: du the so lieu + nhom viec + 'viec can chu y' theo du lieu that + lich su phieu",
        case_d_ok,
        f"the = {card_keys} | so phieu can chu y = {len(attention)} | ly do phieu B = "
        f"\"{attention_b.get('reason', '(khong co)')}\" | lich su phieu A = "
        f"{len(detail_a.get('history', []))} buoc",
    )

    # =================================================================
    # CASE E: PHAN QUYEN - THAO TAC NGOAI QUYEN BI CHAN 403 O BACKEND
    # =================================================================
    print_separator("CASE E: PHAN QUYEN - NGOAI QUYEN BI CHAN 403 O BACKEND")
    tech_create = technician.post("/api/v1/warranty-tickets/", json={
        "serial_number": serial_b, "customer_id": 1, "service_center_id": 1,
        "created_by": id_technician, "issue_description": "Ky thuat vien tu tao phieu (phai bi chan)",
    })
    tech_handover = patch_status(technician, ticket_b["id"], {
        "new_status": "RETURNED", "changed_by": id_technician,
        "handover_note": "Ky thuat vien tu xac nhan tra may (phai bi chan).",
    })
    tech_users = technician.get("/api/v1/users/")
    rec_diagnose = receptionist.patch(f"/api/v1/warranty-tickets/{ticket_b['id']}/diagnosis", json={
        "actor_id": id_receptionist, "diagnosis_note": "Tiep nhan tu ghi chan doan (phai bi chan)",
    })
    rec_delete_customer = receptionist.delete("/api/v1/customers/1")
    wb_codes = {role: client.get(WORKBOARD_URL).status_code for role, client in clients.items()}
    case_e_ok = (
        tech_create.status_code == 403
        and tech_handover.status_code == 403
        and tech_users.status_code == 403
        and rec_diagnose.status_code == 403
        and rec_delete_customer.status_code == 403
        and all(code == 200 for code in wb_codes.values())
    )
    record(
        "CASE E",
        "Ngoai quyen -> 403 (tao phieu/tra may/quan tri/quan ly khach) va ca 3 vai tro van xem duoc dashboard",
        case_e_ok,
        f"ky thuat tao phieu={tech_create.status_code} | ky thuat tra may={tech_handover.status_code} | "
        f"ky thuat xem tai khoan={tech_users.status_code} | tiep nhan ghi chan doan={rec_diagnose.status_code} | "
        f"tiep nhan xoa khach={rec_delete_customer.status_code} | workboard={wb_codes}",
    )

    # =================================================================
    # CASE H: NUT HANH DONG + PHAM VI (scope) + NHOM NHIEU TRANG THAI
    # =================================================================
    print_separator("CASE H: NUT HANH DONG THEO TRANG THAI + QUYEN, PHAM VI, NHOM NHIEU BUOC")

    def row_of(client, ticket_id, status):
        rows = client.get(
            "/api/v1/warranty-tickets/", params={"status": status, "limit": 200}
        ).json()
        return next((row for row in rows if row["id"] == ticket_id), {})

    def targets(row):
        return sorted(action["target"] for action in row.get("available_actions", []))

    # (1) Phiếu đã bàn giao đóng phiếu -> mọi vai trò chỉ còn xem phiếu (không còn nút chuyển bước)
    row_done = row_of(technician, ticket_a["id"], "RETURNED")
    # (2) Nhóm "Đang xử lý kỹ thuật" của Tiếp nhận gộp 2 bước -> phải lọc được theo 2 trạng thái
    group_processing = group_by_key(receptionist.get(WORKBOARD_URL).json()).get("processing", {})
    multi = receptionist.get(
        "/api/v1/warranty-tickets/",
        params={"status": group_processing.get("status_filter", ""), "limit": 200},
    ).json()
    multi_statuses = {row["status"] for row in multi}

    # (3) Đưa phiếu B sang "COMPLETED" (hoàn tất, chờ trả) để so sánh quyền: KTV KHÔNG được trả máy
    move_completed = patch_status(technician, ticket_b["id"], {
        "new_status": "COMPLETED", "changed_by": id_technician,
        "note": "Da xu ly xong cap tin hieu man hinh va loa.",
        "repair_content": "Ep lai cap tin hieu man hinh, thay loa phai.",
        "repair_parts": "Loa phai 2W",
        "repair_test_passed": True,
        "repair_test_note": "Kiem tra hien thi sac net, loa to ro khong re.",
    })
    row_completed_tech = row_of(technician, ticket_b["id"], "COMPLETED")
    row_completed_rec = row_of(receptionist, ticket_b["id"], "COMPLETED")
    wb_scope_mine = technician.get(WORKBOARD_URL, params={"scope": "MINE"}).json()
    wb_scope_all = technician.get(WORKBOARD_URL, params={"scope": "ALL"}).json()
    mine_group_scopes = {group["scope"] for group in wb_scope_mine.get("groups", [])}
    all_group_scopes = {group["scope"] for group in wb_scope_all.get("groups", [])}
    case_h_ok = (
        # Phiếu kết thúc -> chỉ xem, không còn nút chuyển bước
        row_done.get("action_kind") == "read_only"
        and "Xem phiếu" in row_done.get("action_label", "")
        and row_done.get("available_actions") == []
        # Tại "COMPLETED": Kỹ thuật KHÔNG có nút RETURNED, Tiếp nhận có nút RETURNED
        and move_completed.status_code == 200
        and "RETURNED" not in targets(row_completed_tech)
        and "RETURNED" in targets(row_completed_rec)
        and row_completed_rec.get("primary_action", {}).get("target") == "RETURNED"
        and row_completed_rec.get("action_label") == "Xác nhận trả máy"
        # Nhóm nhiều bước + phạm vi MINE/ALL do backend quyết định
        and multi_statuses == {"INSPECTING", "REPAIRING"}
        and group_processing.get("status_filter") == "INSPECTING,REPAIRING"
        and mine_group_scopes == {"MINE"}
        and all_group_scopes == {"ALL"}
        and wb_scope_mine.get("scope") == "MINE"
        and wb_scope_all.get("scope") == "ALL"
    )
    record(
        "CASE H",
        "Nut hanh dong theo trang thai + quyen; nhom nhieu buoc va pham vi MINE/ALL do backend quyet dinh",
        case_h_ok,
        f"phieu hoan tat voi Ky thuat = '{row_done.get('action_label')}' ({row_done.get('action_kind')}) | "
        f"tai 'Hoan tat cho tra': Ky thuat {targets(row_completed_tech)} vs Tiep nhan {targets(row_completed_rec)} "
        f"(nut '{row_completed_rec.get('action_label')}') | nhom 'Dang xu ly' -> {sorted(multi_statuses)} | "
        f"scope MINE/ALL = {sorted(mine_group_scopes)}/{sorted(all_group_scopes)}",
    )

    # =================================================================
    # TONG KET
    # =================================================================
    print_separator("BANG TONG HOP KET QUA KIEM THU MAN HINH CONG VIEC")
    passed = sum(1 for _, _, ok, _ in RESULTS if ok)
    for case, name, ok, _note in RESULTS:
        print(f"  {case:<9} {name:<72} : [{'PASS' if ok else 'FAIL'}]")
    print(f"\n  => TONG KET: {passed}/{len(RESULTS)} PASS | FAIL: {len(RESULTS) - passed}")
    all_passed = passed == len(RESULTS)
    if all_passed:
        print("  >>> XAC NHAN: MOI VAI TRO THAY DUNG CONG VIEC CUA MINH! <<<")
    else:
        print("  >>> CANH BAO: CO KICH BAN CHUA DAT, XEM CHI TIET O TREN. <<<")
    print("=" * 78 + "\n")
    return all_passed


if __name__ == "__main__":
    sys.exit(0 if run_all_tests() else 1)
