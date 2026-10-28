"""
KIỂM THỬ NGHIỆP VỤ PHIẾU BẢO HÀNH (VÒNG ĐỜI 6 TRẠNG THÁI) - CASE 1..8
===================================================================
Quy trình nghiệp vụ chuẩn:
- Luồng sửa chữa: TIẾP NHẬN -> KIỂM TRA -> SỬA CHỮA -> HOÀN TẤT -> ĐÃ TRẢ MÁY.
- Luồng từ chối: KIỂM TRA -> TỪ CHỐI -> ĐÃ TRẢ MÁY.

Môi trường: Chạy trên CSDL tạm riêng biệt, không xóa hay ảnh hưởng đến CSDL chính.
"""
import os
import sys
import tempfile
from datetime import date, datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

temp_db_fd, temp_db_path = tempfile.mkstemp(prefix="test_wf_", suffix=".db")
os.close(temp_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{temp_db_path}"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

wf_engine = create_engine(f"sqlite:///{temp_db_path}", connect_args={"check_same_thread": False})
WfSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=wf_engine)

from app.database import get_db, Base
from app.main import app

def override_get_db():
    db = WfSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

from app.models import RepairLog, TicketStatusHistory, User, WarrantyTicket
from app.services.schema_migration import ensure_schema_upgrades
from seed_data import DEMO_ACCOUNTS, DEMO_PASSWORDS, seed

RESULTS = []

def print_separator(title=""):
    print("\n" + "=" * 78)
    if title:
        print(f"  {title}")
        print("=" * 78)

def record(case, name, ok, note=""):
    RESULTS.append((case, name, bool(ok), note))
    status_text = "PASS" if ok else "FAIL"
    line = f"  [{status_text}] {case}: {name}"
    print(line)
    if note:
        print(f"          -> {note}")

def login_client(username, password):
    client = TestClient(app)
    res = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    if res.status_code != 200:
        raise RuntimeError(f"Dang nhap that bai ({username}): HTTP {res.status_code}")
    token = res.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client

def find_user_id(role):
    db = WfSessionLocal()
    try:
        user = db.query(User).filter(User.role == role).first()
        return user.id if user else None
    finally:
        db.close()

def make_device_and_ticket(manager, receptionist, serial, issue, tech_id, customer_id=1, product_id=1):
    device = manager.post(
        "/api/v1/product-instances/",
        json={
            "serial_number": serial,
            "customer_id": customer_id,
            "product_id": product_id,
            "purchase_date": "2026-06-01",
            "warranty_duration_months": 24,
            "description": "Thiet bi phuc vu kiem thu vong doi phieu bao hanh",
        },
    )
    ticket = receptionist.post(
        "/api/v1/warranty-tickets/",
        json={
            "serial_number": serial,
            "customer_id": customer_id,
            "service_center_id": 1,
            "created_by": find_user_id("RECEPTIONIST"),
            "issue_description": issue,
        },
    )
    if ticket.status_code == 201 and tech_id:
        t_id = ticket.json()["id"]
        manager.post(
            f"/api/v1/warranty-tickets/{t_id}/assign",
            json={"technician_id": tech_id, "note": "Quan ly phan cong KTV kiem tra"},
        )
    return device, ticket

def patch_status(client, ticket_id, payload):
    return client.patch(f"/api/v1/warranty-tickets/{ticket_id}/status", json=payload)

def get_detail(client, ticket_id):
    return client.get(f"/api/v1/warranty-tickets/{ticket_id}")

def run_all_tests():
    Base.metadata.create_all(bind=wf_engine)
    ensure_schema_upgrades(wf_engine)

    # Nạp seed trên database tạm
    import seed_data
    old_engine = seed_data.engine
    old_session = seed_data.SessionLocal
    seed_data.engine = wf_engine
    seed_data.SessionLocal = WfSessionLocal
    try:
        seed()
    finally:
        seed_data.engine = old_engine
        seed_data.SessionLocal = old_session

    print_separator("BAOHANHAI - KIỂM THỬ VÒNG ĐỜI 6 TRẠNG THÁI (CASE 1..8)")
    print(f"  Thời điểm chạy: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("  Quy trình kiểm tra: Tiếp nhận -> Kiểm tra -> Sửa chữa -> Hoàn tất -> Đã trả máy")

    manager = login_client("manager01", DEMO_PASSWORDS["manager01"])
    receptionist = login_client("receptionist01", DEMO_PASSWORDS["receptionist01"])
    technician = login_client("technician01", DEMO_PASSWORDS["technician01"])
    id_manager = find_user_id("MANAGER")
    id_receptionist = find_user_id("RECEPTIONIST")
    id_technician = find_user_id("TECHNICIAN")

    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    serial_full = f"SN-WF-FULL-{stamp}"
    serial_block = f"SN-WF-BLOCK-{stamp}"

    device_full, ticket_full_res = make_device_and_ticket(
        manager, receptionist, serial_full, "Laptop khong len nguon, den nguon nhay lien tuc", id_technician
    )
    device_block, ticket_block_res = make_device_and_ticket(
        manager, receptionist, serial_block, "Man hinh chap chon khi cam sac", id_technician
    )
    if ticket_full_res.status_code != 201 or ticket_block_res.status_code != 201:
        record("SETUP", "Tao 2 thiet bi + 2 phieu de kiem thu", False)
        return False
    ticket_full = ticket_full_res.json()
    ticket_block = ticket_block_res.json()
    id_full, id_block = ticket_full["id"], ticket_block["id"]

    # =================================================================
    # CASE 1: TIẾP NHẬN -> KIỂM TRA -> SỬA CHỮA -> HOÀN TẤT -> ĐÃ TRẢ MÁY
    # =================================================================
    print_separator("CASE 1: LUỒNG SỬA CHỮA ĐẦY ĐỦ 5 BƯỚC ĐẾN TRẢ MÁY")
    step1 = patch_status(technician, id_full, {
        "new_status": "INSPECTING", "changed_by": id_technician,
        "note": "KTV nhan may, bat dau kiem tra bo mach nguon.",
    })
    step2 = patch_status(technician, id_full, {
        "new_status": "REPAIRING", "changed_by": id_technician,
        "note": "Da kiem tra, xac dinh loi IC nguon, du dieu kien bao hanh.",
        "diagnosis_note": "Mach nguon chay: IC nguon nong bat thuong, tu dien loc bi phong.",
        "is_warranty_eligible": True,
        "error_category_id": 1,
    })
    # Ghi nhận nội dung sửa chữa riêng
    repair_save = technician.patch(f"/api/v1/warranty-tickets/{id_full}/repair", json={
        "actor_id": id_technician,
        "repair_content": "Thay IC nguon va 2 tu dien loc nguon, ve sinh tan nhiet.",
        "repair_parts": "IC nguon RT8205, tu dien 470uF",
        "repair_note": "Chay thu 60 phut on dinh.",
    })
    step3 = patch_status(technician, id_full, {
        "new_status": "COMPLETED", "changed_by": id_technician,
        "note": "May da sua xong dat yeu cau, chuyen ra quay cho khach nhan.",
        "repair_content": "Thay IC nguon va 2 tu dien loc nguon, ve sinh tan nhiet.",
        "repair_parts": "IC nguon RT8205, tu dien 470uF",
        "repair_test_passed": True,
        "repair_test_note": "Test chay thu 60 phut on dinh dat yeu cau",
    })
    step4 = patch_status(receptionist, id_full, {
        "new_status": "RETURNED", "changed_by": id_receptionist,
        "handover_note": "Khach da kiem tra may va nhan lai kem phieu bao hanh.",
        "note": "Da ban giao may cho khach tai quay va dong phieu.",
    })
    detail_full = get_detail(receptionist, id_full).json()
    codes = [step1.status_code, step2.status_code, step3.status_code, step4.status_code]
    case1_ok = (
        codes == [200, 200, 200, 200]
        and detail_full["status"] == "RETURNED"
        and detail_full["resolution"] == "COMPLETED"
        and detail_full["handed_over_at"] is not None
        and len(detail_full["history"]) == 5
        and detail_full["device"]["serial_number"] == serial_full
        and bool(detail_full["customer"]["full_name"])
        and bool(detail_full["repair"]["content"])
        and len(detail_full["repair"]["logs"]) >= 1
        and detail_full["handover"]["returned_by_name"] is not None
    )
    record("CASE 1", "Luong day du 5 buoc -> RETURNED + luu resolution='COMPLETED'", case1_ok,
           f"HTTP: {codes} | trang thai cuoi: {detail_full['status']} | resolution: {detail_full.get('resolution')}")

    # =================================================================
    # CASE 2: SỬA CHỮA -> TRẢ MÁY (BỎ QUA HOÀN TẤT) PHẢI BỊ CHẶN
    # =================================================================
    print_separator("CASE 2: CHẶN CHUYỂN TẮT (REPAIRING -> RETURNED)")
    patch_status(technician, id_block, {
        "new_status": "INSPECTING", "changed_by": id_technician,
        "note": "Tiep nhan may, chuyen kiem tra.",
    })
    patch_status(technician, id_block, {
        "new_status": "REPAIRING", "changed_by": id_technician,
        "note": "Dang sua chua cum cong sac.",
        "diagnosis_note": "Chan ket noi cong sac bi long, can thay cum connector.",
        "is_warranty_eligible": True,
    })
    skip = patch_status(receptionist, id_block, {
        "new_status": "RETURNED", "changed_by": id_receptionist,
        "handover_note": "Co gang dong phieu som khi chua xong (phai bi chan).",
    })
    detail_block = get_detail(receptionist, id_block).json()
    body_skip = skip.json()
    case2_ok = (
        skip.status_code == 400
        and "STATE MACHINE ERROR" in str(body_skip.get("detail", ""))
        and detail_block["status"] == "REPAIRING"
        and detail_block["handed_over_at"] is None
    )
    record("CASE 2", "Sua chua -> Tra may bi chan (chuyen tat khong hop le)", case2_ok,
           f"HTTP {skip.status_code} | trang thai giu nguyen: {detail_block['status']}")

    # =================================================================
    # CASE 4: AI GỢI Ý LOẠI LỖI KHÔNG TỰ ĐỘNG THÀNH KẾT LUẬN CỦA PHIẾU
    # =================================================================
    print_separator("CASE 4: AI GỢI Ý LOẠI LỖI - PHIẾU KHÔNG TỰ ĐỘNG CÓ KẾT LUẬN")
    ai_classify = technician.post(f"/api/v1/ai/tickets/{id_block}/classify-error")
    detail_after_ai = get_detail(technician, id_block).json()
    ai_body = ai_classify.json() if ai_classify.status_code == 201 else {}
    case4a_ok = (
        ai_classify.status_code == 201
        and detail_after_ai["error_category_id"] is None
        and detail_after_ai["status"] == "REPAIRING"
        and detail_after_ai["ai_suggestion"]["available"] is True
        and detail_after_ai["diagnosis"]["error_category_id"] is None
    )
    record("CASE 4a", "AI goi y xong: phieu VAN chua co ket luan loai loi (AI chi de xuat)", case4a_ok)

    ai_result_id = ai_body.get("ai_result_id")
    approve = manager.patch(f"/api/v1/ai/results/{ai_result_id}/review",
                            json={"reviewed_by": id_manager, "decision": "APPROVED"})
    detail_after_review = get_detail(manager, id_block).json()
    case4b_ok = (
        approve.status_code == 200
        and detail_after_review["error_category_id"] is not None
        and detail_after_review["status"] == "REPAIRING"
        and detail_after_review["ai_suggestion"]["review_status"] == "APPROVED"
    )
    record("CASE 4b", "Chi khi NGUOI co quyen xac nhan thi nhan loi moi ghi vao phieu", case4b_ok)

    # =================================================================
    # CASE 3: THAO TÁC NGOÀI QUYỀN BỊ CHẶN THẬT Ở BACKEND (403)
    # =================================================================
    print_separator("CASE 3: THAO TÁC NGOÀI QUYỀN PHẢI BỊ CHẶN (403)")
    tech_create = technician.post("/api/v1/warranty-tickets/", json={
        "serial_number": serial_full, "customer_id": 1, "service_center_id": 1,
        "created_by": id_technician, "issue_description": "Ky thuat vien tu tao phieu (phai bi chan)",
    })
    rec_diagnose = receptionist.patch(f"/api/v1/warranty-tickets/{id_block}/diagnosis", json={
        "actor_id": id_receptionist,
        "diagnosis_note": "Nhan vien tiep nhan tu ghi chan doan (phai bi chan)",
    })
    case3_ok = (
        tech_create.status_code == 403
        and rec_diagnose.status_code == 403
    )
    record("CASE 3a", "Ky thuat vien tao phieu / Tiep nhan ghi chan doan -> bi chan 403", case3_ok)

    # Đưa phiếu sang COMPLETED (Hoàn tất, chờ trả máy)
    finish_repair = patch_status(technician, id_block, {
        "new_status": "COMPLETED", "changed_by": id_technician,
        "note": "Da sua xong connector, may san sang tra khach.",
        "repair_content": "Thay cum connector sac, do lai dien ap 5V on dinh.",
        "repair_parts": "Cum connector Type-C",
        "repair_test_passed": True,
        "repair_test_note": "Chay thu 30 phut sac binh thuong",
    })
    # KTV cố tình tự ý trả máy (RETURNED) -> Bị chặn 403
    tech_return = patch_status(technician, id_block, {
        "new_status": "RETURNED", "changed_by": id_technician,
        "handover_note": "Ky thuat vien tu xac nhan da tra may (phai bi chan).",
    })
    detail_waiting = get_detail(receptionist, id_block).json()
    case3b_ok = (
        finish_repair.status_code == 200
        and tech_return.status_code == 403
        and detail_waiting["status"] == "COMPLETED"
    )
    record("CASE 3b", "Ky thuat vien tu xac nhan TRA MAY (RETURNED) -> bi chan 403", case3b_ok)

    # =================================================================
    # CASE 5: "HOÀN TẤT (CHỜ TRẢ MÁY)" HIỂN THỊ ĐÚNG Ở DASHBOARD & CHI TIẾT
    # =================================================================
    print_separator("CASE 5: TRẠNG THÁI HOÀN TẤT (CHỜ TRẢ) HIỂN THỊ ĐÚNG")
    stats_all = manager.get("/api/v1/warranty-tickets/stats/summary").json()
    stats_mine = technician.get("/api/v1/warranty-tickets/stats/summary?mine=1").json()
    list_completed = receptionist.get(
        "/api/v1/warranty-tickets/", params={"status": "COMPLETED", "limit": 200}
    ).json()
    list_codes = [item["ticket_code"] for item in list_completed]
    case5_ok = (
        stats_all.get("completed", 0) >= 1
        and stats_mine.get("scope") == "MINE"
        and ticket_block["ticket_code"] in list_codes
        and detail_waiting["status"] == "COMPLETED"
        and "chờ khách nhận máy" in detail_waiting["handover"]["status_message"]
    )
    record("CASE 5", "Trang thai COMPLETED (Cho tra may) hien dung o bang dieu khien + danh sach + chi tiet", case5_ok)

    # =================================================================
    # CASE 6: TRẢ MÁY -> LỊCH SỬ ĐẦY ĐỦ VÀ ĐÓNG PHIẾU
    # =================================================================
    print_separator("CASE 6: TRẢ MÁY ĐÓNG PHIẾU - LỊCH SỬ ĐẦY ĐỦ CÁC BƯỚC")
    return_block = patch_status(receptionist, id_block, {
        "new_status": "RETURNED", "changed_by": id_receptionist,
        "handover_note": "Khach da nhan may, da kiem tra cong sac hoat dong tot.",
        "note": "Ban giao may cho khach tai quay.",
    })
    detail_done = get_detail(receptionist, id_block).json()
    history = detail_done["history"]
    case6_ok = (
        return_block.status_code == 200
        and detail_done["status"] == "RETURNED"
        and detail_done["resolution"] == "COMPLETED"
        and len(history) == 5
        and detail_done["handed_over_at"] is not None
        and detail_done["handover"]["note"] is not None
    )
    record("CASE 6", "Lich su 5 buoc day du: Tiep nhan -> Kiem tra -> Sua chua -> Hoan tat -> Da tra may", case6_ok)

    # =================================================================
    # CASE 7: TẢI LẠI TRANG -> DỮ LIỆU ĐỒNG BỘ VÀ KHỚP CSDL
    # =================================================================
    print_separator("CASE 7: TẢI LẠI TRANG - DỮ LIỆU VẪN CHÍNH XÁC (LẤY TỪ CSDL)")
    reload1 = get_detail(receptionist, id_block).json()
    reload2 = get_detail(manager, id_block).json()
    db = WfSessionLocal()
    try:
        row = db.query(WarrantyTicket).filter(WarrantyTicket.id == id_block).first()
        db_history = db.query(TicketStatusHistory).filter(TicketStatusHistory.ticket_id == id_block).count()
        db_repair_logs = db.query(RepairLog).filter(RepairLog.ticket_id == id_block).count()
        db_status = row.status
        db_resolution = row.resolution
        db_handed_over = row.handed_over_at is not None
    finally:
        db.close()
    case7_ok = (
        reload1["status"] == reload2["status"] == "RETURNED"
        and reload1["resolution"] == reload2["resolution"] == "COMPLETED"
        and db_status == "RETURNED"
        and db_resolution == "COMPLETED"
        and db_handed_over is True
        and db_history == 5
        and db_repair_logs >= 1
    )
    record("CASE 7", "Goi lai API nhieu lan + doi chieu CSDL: trang thai RETURNED va resolution='COMPLETED' dong bo", case7_ok)

    # =================================================================
    # CASE 8: PHÂN QUYỀN VÀ HÀNH ĐỘNG HIỂN THỊ THEO VAI TRÒ
    # =================================================================
    print_separator("CASE 8: 3 VAI TRÒ - QUYỀN THẬT + HÀNH ĐỘNG HIỂN THỊ ĐÚNG")
    role_expectations = {
        "MANAGER": {"ticket.reject": True, "ticket.handover": True, "ticket.diagnose": True, "ticket.repair": True},
        "RECEPTIONIST": {"ticket.reject": False, "ticket.handover": True, "ticket.diagnose": False, "ticket.repair": False},
        "TECHNICIAN": {"ticket.reject": False, "ticket.handover": False, "ticket.diagnose": True, "ticket.repair": True},
    }
    clients = {"MANAGER": manager, "RECEPTIONIST": receptionist, "TECHNICIAN": technician}
    role_ok = True
    for role, expectations in role_expectations.items():
        perms = clients[role].get("/api/v1/auth/me").json().get("permissions", [])
        for permission, expected in expectations.items():
            if (permission in perms) != expected:
                role_ok = False

    # Phiếu mẫu thứ 2 trong seed đang ở COMPLETED (chờ trả máy)
    seeded = receptionist.get("/api/v1/warranty-tickets/code/TK-20260510-0001").json()
    waiting_id = seeded.get("id")

    actions_by_role = {}
    for role, client in clients.items():
        detail = client.get(f"/api/v1/warranty-tickets/{waiting_id}").json()
        actions_by_role[role] = [action["target"] for action in detail.get("available_actions", [])]

    # Tại COMPLETED: KTV không được trả máy (RETURNED không có trong actions của KTV)
    # Tiếp nhận & Quản lý có nút xác nhận trả máy (RETURNED)
    actions_ok = (
        "RETURNED" not in actions_by_role["TECHNICIAN"]
        and "RETURNED" in actions_by_role["RECEPTIONIST"]
        and "RETURNED" in actions_by_role["MANAGER"]
    )
    case8_ok = role_ok and actions_ok
    record("CASE 8", "3 vai tro: quyen backend dung + nut RETURNED chi danh cho Tiep nhan/Quan ly", case8_ok)

    # =================================================================
    # TỔNG KẾT
    # =================================================================
    print_separator("BẢNG TỔNG HỢP KẾT QUẢ KIỂM THỬ")
    passed = sum(1 for _, _, ok, _ in RESULTS if ok)
    for case, name, ok, note in RESULTS:
        print(f"  {case:<9} {name:<64} : [{'PASS' if ok else 'FAIL'}]")
    print(f"\n  => TỔNG KẾT: {passed}/{len(RESULTS)} PASS | FAIL: {len(RESULTS) - passed}")

    # Dọn dẹp file db tạm
    try:
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)
    except Exception:
        pass

    return passed == len(RESULTS)

if __name__ == "__main__":
    sys.exit(0 if run_all_tests() else 1)
