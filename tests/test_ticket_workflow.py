"""
KIEM THU NGHIEP VU PHIEU BAO HANH (Dot hoan thien Prompt 1) - 8 KICH BAN CASE 1..8

Cach chay:
    .\\dev.ps1 workflow            (hoac: py -3.12 tests\\test_ticket_workflow.py)

Bo kiem thu nay tap trung vao VONG DOI PHIEU BAO HANH (khac voi bo minh chung
KT2/KT3 tap trung vao quy tac BR1-BR4 va AI-01):
    CASE 1: Tiep nhan -> Kiem tra -> Sua chua -> Cho tra may -> Hoan tat thanh cong.
    CASE 2: Sua chua -> Hoan tat bi chan (khong duoc bo qua buoc "cho tra may").
    CASE 3: Thao tac ngoai quyen bi chan that o backend (403).
    CASE 4: AI goi y loi KHONG tu dong tro thanh ket luan cua phieu.
    CASE 5: "Cho tra may" hien dung tren bang dieu khien + danh sach + chi tiet phieu.
    CASE 6: Hoan tat -> lich su phai co day du cac buoc (trang thai, thoi gian, nguoi thuc hien).
    CASE 7: Tai lai trang (goi lai API) -> trang thai + lich su van chinh xac.
    CASE 8: Dang nhap 3 vai tro -> quyen va hanh dong hien thi dung theo vai tro.

Luu y: file nay tu lam moi CSDL (drop_all + create_all + seed) truoc khi kiem thu.
"""
import sys
import os
from datetime import date, datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Cấu trúc dự án: tests/ ở gốc, code trong backend/
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, engine, Base
from app.models import RepairLog, TicketStatusHistory, User, WarrantyTicket
from app.services.schema_migration import ensure_schema_upgrades
from seed_data import DEMO_ACCOUNTS, seed

RESULTS = []  # [(case, ten_kich_ban, ok, ghi_chu)]


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
    """Tra ve TestClient da gan header Authorization cua tai khoan vua dang nhap."""
    client = TestClient(app)
    res = client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    if res.status_code != 200:
        raise RuntimeError(f"Dang nhap that bai ({username}): HTTP {res.status_code}")
    token = res.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def find_user_id(role):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.role == role).first()
        return user.id if user else None
    finally:
        db.close()


def make_device_and_ticket(manager, receptionist, serial, issue, customer_id=1, product_id=1):
    """Tao 1 thiet bi moi + 1 phieu moi o trang thai RECEIVED (dung nguon du lieu that)."""
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
    return device, ticket



def patch_status(client, ticket_id, payload):
    return client.patch(f"/api/v1/warranty-tickets/{ticket_id}/status", json=payload)


def get_detail(client, ticket_id):
    return client.get(f"/api/v1/warranty-tickets/{ticket_id}")


def run_all_tests():
    # Làm mới CSDL để kết quả kiểm thử luôn chuẩn khi chạy lại
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    ensure_schema_upgrades(engine)
    seed()

    print_separator("BAOHANHAI - KIEM THU NGHIEP VU PHIEU BAO HANH (CASE 1..8)")
    print(f"  Thoi diem chay: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("  Quy trinh kiem tra: Tiep nhan -> Kiem tra -> Sua chua -> Cho tra may -> Hoan tat")

    manager = login_client(*DEMO_ACCOUNTS[0][:2])
    receptionist = login_client(*DEMO_ACCOUNTS[1][:2])
    technician = login_client(*DEMO_ACCOUNTS[2][:2])
    id_manager = find_user_id("MANAGER")
    id_receptionist = find_user_id("RECEPTIONIST")
    id_technician = find_user_id("TECHNICIAN")
    print(f"  Da dang nhap 3 vai tro | manager={id_manager} receptionist={id_receptionist} "
          f"technician={id_technician}")

    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    serial_full = f"SN-WF-FULL-{stamp}"
    serial_block = f"SN-WF-BLOCK-{stamp}"

    device_full, ticket_full_res = make_device_and_ticket(
        manager, receptionist, serial_full, "Laptop khong len nguon, den nguon nhay lien tuc"
    )
    device_block, ticket_block_res = make_device_and_ticket(
        manager, receptionist, serial_block, "Man hinh chap chon khi cam sac"
    )
    if ticket_full_res.status_code != 201 or ticket_block_res.status_code != 201:
        record("SETUP", "Tao 2 thiet bi + 2 phieu de kiem thu", False,
               f"HTTP phieu 1 = {ticket_full_res.status_code}, phieu 2 = {ticket_block_res.status_code}")
        return False
    ticket_full = ticket_full_res.json()
    ticket_block = ticket_block_res.json()
    id_full, id_block = ticket_full["id"], ticket_block["id"]
    print(f"  Phieu kiem thu: {ticket_full['ticket_code']} (id={id_full}) | "
          f"{ticket_block['ticket_code']} (id={id_block})")


    # =================================================================
    # CASE 1: TIEP NHAN -> KIEM TRA -> SUA CHUA -> CHO TRA MAY -> HOAN TAT
    # =================================================================
    print_separator("CASE 1: LUONG PHIEU DAY DU (5 BUOC) PHAI THANH CONG")
    step1 = patch_status(receptionist, id_full, {
        "new_status": "INSPECTING", "changed_by": id_receptionist,
        "note": "Da tiep nhan may tai quay, chuyen ky thuat kiem tra.",
    })
    step2 = patch_status(technician, id_full, {
        "new_status": "REPAIRING", "changed_by": id_technician,
        "note": "Da kiem tra, xac dinh loi mach nguon.",
        "diagnosis_note": "Mach nguon chay: IC nguon nong bat thuong, tu dien loc bi phong.",
        "error_category_id": 1,
    })
    # Ghi nhan noi dung sua chua rieng (khong doi trang thai) - dung thao tac cua ky thuat vien
    repair_save = technician.patch(f"/api/v1/warranty-tickets/{id_full}/repair", json={
        "actor_id": id_technician,
        "repair_content": "Thay IC nguon va 2 tu dien loc nguon, ve sinh tan nhiet.",
        "repair_parts": "IC nguon RT8205, tu dien 470uF",
        "repair_note": "Chay thu 60 phut on dinh.",
    })
    step3 = patch_status(technician, id_full, {
        "new_status": "WAITING_RETURN", "changed_by": id_technician,
        "note": "May da sua xong, da dua ra quay cho khach den nhan.",
        "repair_content": "Thay IC nguon va 2 tu dien loc nguon, ve sinh tan nhiet.",
        "repair_parts": "IC nguon RT8205, tu dien 470uF",
    })
    step4 = patch_status(receptionist, id_full, {
        "new_status": "COMPLETED", "changed_by": id_receptionist,
        "handover_note": "Khach da kiem tra may va nhan lai kem phieu bao hanh.",
        "note": "Da ban giao may cho khach tai quay.",
    })
    detail_full = get_detail(receptionist, id_full).json()
    codes = [step1.status_code, step2.status_code, step3.status_code, step4.status_code]
    case1_ok = (
        codes == [200, 200, 200, 200]
        and detail_full["status"] == "COMPLETED"
        and detail_full["handed_over_at"] is not None
        and len(detail_full["history"]) == 5
        and detail_full["device"]["serial_number"] == serial_full
        and bool(detail_full["customer"]["full_name"])
        and bool(detail_full["repair"]["content"])
        and len(detail_full["repair"]["logs"]) >= 1
        and detail_full["handover"]["returned_by_name"] is not None
    )
    record("CASE 1", "Luong day du 5 buoc -> COMPLETED + luu day du thong tin xu ly", case1_ok,
           f"HTTP: {codes} | trang thai cuoi: {detail_full['status']} | "
           f"lich su: {len(detail_full['history'])} buoc | "
           f"nguoi tra may: {detail_full['handover']['returned_by_name']} | "
           f"nhat ky sua chua: {len(detail_full['repair']['logs'])} dong")


    # =================================================================
    # CASE 2: SUA CHUA -> HOAN TAT (BO QUA CHO TRA MAY) PHAI BI CHAN
    # =================================================================
    print_separator("CASE 2: SUA CHUA -> HOAN TAT PHAI BI CHAN (BAT BUOC QUA CHO TRA MAY)")
    patch_status(receptionist, id_block, {
        "new_status": "INSPECTING", "changed_by": id_receptionist,
        "note": "Tiep nhan may, chuyen kiem tra.",
    })
    patch_status(technician, id_block, {
        "new_status": "REPAIRING", "changed_by": id_technician,
        "note": "Dang sua chua cum cong sac.",
        "diagnosis_note": "Chan ket noi cong sac bi long, can thay cum connector.",
    })
    skip = patch_status(receptionist, id_block, {
        "new_status": "COMPLETED", "changed_by": id_receptionist,
        "handover_note": "Co gang dong phieu som (phai bi chan).",
    })
    detail_block = get_detail(receptionist, id_block).json()
    body_skip = skip.json()
    case2_ok = (
        skip.status_code == 400
        and "STATE MACHINE ERROR" in str(body_skip.get("detail", ""))
        and "Chưa thể hoàn tất phiếu" in str(body_skip.get("message", ""))
        and "[" not in str(body_skip.get("message", ""))
        and detail_block["status"] == "REPAIRING"
        and detail_block["handed_over_at"] is None
    )
    record("CASE 2", "Sua chua -> Hoan tat bi chan, thong bao tieng Viet khong lo ma ky thuat", case2_ok,
           f"HTTP {skip.status_code} | message = \"{body_skip.get('message')}\" | "
           f"trang thai giu nguyen: {detail_block['status']}")

    # =================================================================
    # CASE 4: AI GOI Y LOAI LOI KHONG TU DONG THANH KET LUAN CUA PHIEU
    # =================================================================
    print_separator("CASE 4: AI GOI Y LOAI LOI - PHIEU KHONG TU DONG CO KET LUAN")
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
    record("CASE 4a", "AI goi y xong: phieu VAN chua co ket luan loai loi (AI chi de xuat)", case4a_ok,
           f"HTTP {ai_classify.status_code} | AI de xuat: "
           f"{ai_body.get('suggested_category_name')} "
           f"({round(float(ai_body.get('confidence') or 0) * 100)}%) | "
           f"error_category_id cua phieu: {detail_after_ai['error_category_id']}")

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
    record("CASE 4b", "Chi khi NGUOI co quyen xac nhan thi nhan loi moi ghi vao phieu (trang thai khong doi)",
           case4b_ok,
           f"HTTP {approve.status_code} | nhan loi sau xac nhan: "
           f"{detail_after_review['diagnosis']['error_category_name']} | "
           f"trang thai: {detail_after_review['status']}")


    # =================================================================
    # CASE 3: THAO TAC NGOAI QUYEN BI CHAN THAT O BACKEND (403)
    # =================================================================
    print_separator("CASE 3: THAO TAC NGOAI QUYEN PHAI BI CHAN (403)")
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
    record("CASE 3a", "Ky thuat vien tao phieu / Tiep nhan ghi chan doan -> bi chan 403", case3_ok,
           f"technician POST /tickets/ = {tech_create.status_code} | "
           f"receptionist PATCH /diagnosis = {rec_diagnose.status_code}")

    # Dua phieu block sang "Cho tra may" de kiem tra tiep quyen tra may + hien thi
    finish_repair = patch_status(technician, id_block, {
        "new_status": "WAITING_RETURN", "changed_by": id_technician,
        "note": "Da sua xong connector, may san sang tra khach.",
        "repair_content": "Thay cum connector sac, do lai dien ap 5V on dinh.",
        "repair_parts": "Cum connector Type-C",
    })
    tech_complete = patch_status(technician, id_block, {
        "new_status": "COMPLETED", "changed_by": id_technician,
        "handover_note": "Ky thuat vien tu xac nhan da tra may (phai bi chan).",
    })
    detail_waiting = get_detail(receptionist, id_block).json()
    case3b_ok = (
        finish_repair.status_code == 200
        and tech_complete.status_code == 403
        and detail_waiting["status"] == "WAITING_RETURN"
    )
    record("CASE 3b", "Ky thuat vien tu xac nhan DA TRA MAY -> bi chan 403 (chi Tiep nhan/Quan ly)",
           case3b_ok,
           f"chuyen sang Cho tra may = {finish_repair.status_code} | "
           f"technician PATCH COMPLETED = {tech_complete.status_code} | "
           f"trang thai: {detail_waiting['status']}")

    # =================================================================
    # CASE 5: "CHO TRA MAY" HIEN DUNG TREN BANG DIEU KHIEN + DANH SACH + CHI TIET
    # =================================================================
    print_separator("CASE 5: TRANG THAI CHO TRA MAY HIEN DUNG O 3 NOI")
    stats_all = manager.get("/api/v1/warranty-tickets/stats/summary").json()
    stats_mine = technician.get("/api/v1/warranty-tickets/stats/summary?mine=1").json()
    list_waiting = receptionist.get(
        "/api/v1/warranty-tickets/", params={"status": "WAITING_RETURN", "limit": 200}
    ).json()
    list_codes = [item["ticket_code"] for item in list_waiting]
    list_row = next(
        (item for item in list_waiting if item["ticket_code"] == ticket_block["ticket_code"]), {}
    )
    waiting_workload = [
        item for item in stats_mine.get("workload", []) if item.get("status") == "WAITING_RETURN"
    ]
    case5_ok = (
        stats_all.get("waiting_return", 0) >= 1
        and stats_mine.get("scope") == "MINE"
        and bool(waiting_workload)
        and waiting_workload[0]["count"] >= 1
        and ticket_block["ticket_code"] in list_codes
        and detail_waiting["handover"]["is_waiting_return"] is True
        and "chờ khách nhận máy" in detail_waiting["handover"]["status_message"]
        # Mỗi dòng danh sách phải đủ dữ liệu làm việc: người phụ trách + số điện thoại khách
        and bool(list_row.get("handler_name"))
        and bool(list_row.get("customer_phone"))
        and list_row.get("status_label") == "Chờ trả máy"
    )
    record("CASE 5", "Cho tra may hien o bang dieu khien + danh sach + chi tiet phieu", case5_ok,
           f"tong cho tra may (toan he thong) = {stats_all.get('waiting_return')} | "
           f"viec cua ky thuat vien (cho tra may) = "
           f"{waiting_workload[0]['count'] if waiting_workload else 0} | "
           f"dong danh sach: {list_row.get('ticket_code')} - {list_row.get('status_label')} - "
           f"phu trach: {list_row.get('handler_name')} - SDT: {list_row.get('customer_phone')}")



    # =================================================================
    # CASE 6: HOAN TAT -> LICH SU PHAI CO DAY DU CAC BUOC
    # =================================================================
    print_separator("CASE 6: HOAN TAT PHIEU - LICH SU DAY DU CAC BUOC")
    complete_block = patch_status(receptionist, id_block, {
        "new_status": "COMPLETED", "changed_by": id_receptionist,
        "handover_note": "Khach da nhan may, da kiem tra cong sac hoat dong tot.",
        "note": "Ban giao may cho khach tai quay.",
    })
    detail_done = get_detail(receptionist, id_block).json()
    history = detail_done["history"]
    history_labels = [row["to_label"] for row in history]
    history_actors_ok = all(row["changed_by_name"] for row in history)
    history_times_ok = all(row["created_at"] for row in history)
    case6_ok = (
        complete_block.status_code == 200
        and detail_done["status"] == "COMPLETED"
        and len(history) == 5
        and history_labels == ["Mới tiếp nhận", "Đang kiểm tra", "Đang sửa chữa", "Chờ trả máy", "Đã hoàn tất"]
        and history_actors_ok
        and history_times_ok
        and detail_done["handover"]["returned_at"] is not None
        and detail_done["handover"]["note"] is not None
    )
    record("CASE 6", "Lich su 5 buoc: trang thai + thoi gian + nguoi thuc hien + ghi chu", case6_ok,
           f"HTTP {complete_block.status_code} | cac buoc: {' -> '.join(history_labels)} | "
           f"nguoi thuc hien day du: {history_actors_ok}")

    # =================================================================
    # CASE 7: TAI LAI TRANG (GOI LAI API) -> TRANG THAI + LICH SU VAN CHINH XAC
    # =================================================================
    print_separator("CASE 7: TAI LAI TRANG - DU LIEU VAN CHINH XAC (LAY TU CSDL)")
    reload1 = get_detail(receptionist, id_block).json()
    reload2 = get_detail(manager, id_block).json()
    db = SessionLocal()
    try:
        row = db.query(WarrantyTicket).filter(WarrantyTicket.id == id_block).first()
        db_history = db.query(TicketStatusHistory).filter(
            TicketStatusHistory.ticket_id == id_block
        ).count()
        db_repair_logs = db.query(RepairLog).filter(RepairLog.ticket_id == id_block).count()
        db_status = row.status
        db_handed_over = row.handed_over_at is not None
        db_handover_note = row.handover_note
        db_handed_over_by = row.handed_over_by
    finally:
        db.close()
    case7_ok = (
        reload1["status"] == reload2["status"] == "COMPLETED"
        and len(reload1["history"]) == len(reload2["history"]) == 5
        and db_status == "COMPLETED"
        and db_handed_over is True
        and bool(db_handover_note)
        and db_handed_over_by == id_receptionist
        and db_history == 5
        and db_repair_logs >= 1
        and reload1["repair"]["content"] == reload2["repair"]["content"]
    )
    record("CASE 7", "Goi lai API nhieu lan + doi chieu CSDL: trang thai, lich su, ban giao khop", case7_ok,
           f"trang thai DB: {db_status} | so dong lich su DB: {db_history} | "
           f"handed_over_by: {db_handed_over_by} | nhat ky sua chua DB: {db_repair_logs}")

    # =================================================================
    # CASE 8: DANG NHAP 3 VAI TRO - QUYEN VA HANH DONG HIEN THI DUNG
    # =================================================================
    print_separator("CASE 8: 3 VAI TRO - QUYEN THAT + HANH DONG HIEN THI DUNG")
    # Phieu dang o "Cho tra may" de so sanh hanh dong hien thi theo vai tro
    waiting_ticket = receptionist.get(
        "/api/v1/warranty-tickets/", params={"status": "WAITING_RETURN", "limit": 50}
    ).json()
    waiting_id = waiting_ticket[0]["id"] if waiting_ticket else None
    if waiting_id is None:
        # Khong con phieu cho tra may nao -> dung phieu seed co san trong CSDL
        seeded = receptionist.get("/api/v1/warranty-tickets/code/TK-20260510-0001")
        waiting_id = seeded.json().get("id") if seeded.status_code == 200 else None
        if waiting_id is not None:
            seeded_detail = seeded.json()
            print(f"  [i] Dung phieu mau san co: {seeded_detail['ticket_code']} "
                  f"({seeded_detail['status_label']})")

    role_expectations = {
        "MANAGER": {"ticket.reject": True, "ticket.handover": True,
                    "ticket.diagnose": True, "ticket.repair": True},
        "RECEPTIONIST": {"ticket.reject": False, "ticket.handover": True,
                         "ticket.diagnose": False, "ticket.repair": False},
        "TECHNICIAN": {"ticket.reject": False, "ticket.handover": False,
                       "ticket.diagnose": True, "ticket.repair": True},
    }
    clients = {"MANAGER": manager, "RECEPTIONIST": receptionist, "TECHNICIAN": technician}
    role_ok = True
    notes = []
    for role, expectations in role_expectations.items():
        client = clients[role]
        me = client.get("/api/v1/auth/me").json()
        perms = me.get("permissions", [])
        for permission, expected in expectations.items():
            actual = permission in perms
            if actual != expected:
                role_ok = False
                notes.append(f"{role}.{permission}: mong doi {expected} - thuc te {actual}")
        notes.append(f"{role}: {len(perms)} quyen")

    actions_by_role = {}
    for role, client in clients.items():
        detail = client.get(f"/api/v1/warranty-tickets/{waiting_id}").json()
        actions_by_role[role] = {
            "targets": [action["target"] for action in detail.get("available_actions", [])],
            "labels": [action["button_label"] for action in detail.get("available_actions", [])],
            "notes": detail.get("permission_notes", []),
            "can_complete": detail.get("can_complete"),
        }

    tech_targets = actions_by_role["TECHNICIAN"]["targets"]
    rec_targets = actions_by_role["RECEPTIONIST"]["targets"]
    mgr_targets = actions_by_role["MANAGER"]["targets"]
    actions_ok = (
        "COMPLETED" not in tech_targets
        and "COMPLETED" in rec_targets
        and "COMPLETED" in mgr_targets
        and "REPAIRING" in tech_targets
        and any("trả máy" in note for note in actions_by_role["TECHNICIAN"]["notes"])
    )
    case8_ok = role_ok and actions_ok and waiting_id is not None
    record("CASE 8", "3 vai tro: quyen backend dung + nut hanh doi hien thi theo quyen", case8_ok,
           f"{' | '.join(notes)} | hanh dong tai phieu cho tra may: "
           f"TECHNICIAN={tech_targets or ['(khong co)']} RECEPTIONIST={rec_targets} MANAGER={mgr_targets}")
    print(f"          -> Nut hien thi voi Tiep nhan: {actions_by_role['RECEPTIONIST']['labels']}")
    print(f"          -> Ghi chu voi Ky thuat vien: {actions_by_role['TECHNICIAN']['notes']}")

    # =================================================================
    # TONG KET
    # =================================================================
    print_separator("BANG TONG HOP KET QUA KIEM THU NGHIEP VU PHIEU BAO HANH")
    passed = sum(1 for _, _, ok, _ in RESULTS if ok)
    for case, name, ok, note in RESULTS:
        print(f"  {case:<9} {name:<64} : [{'PASS' if ok else 'FAIL'}]")
    print(f"\n  => TONG KET: {passed}/{len(RESULTS)} PASS | FAIL: {len(RESULTS) - passed}")
    all_passed = passed == len(RESULTS)
    if all_passed:
        print("  >>> XAC NHAN: NGHIEP VU PHIEU BAO HANH HOAT DONG DUNG THEO QUY TRINH! <<<")
    else:
        print("  >>> CANH BAO: CO KICH BAN CHUA DAT, XEM CHI TIET O TREN. <<<")
    print("=" * 78 + "\n")
    return all_passed


if __name__ == "__main__":
    # Exit code: 0 = toan bo CASE PASS, 1 = co CASE FAIL
    sys.exit(0 if run_all_tests() else 1)
