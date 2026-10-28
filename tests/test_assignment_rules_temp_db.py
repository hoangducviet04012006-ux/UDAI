"""
KIỂM THỬ QUY TẮC PHÂN CÔNG KỸ THUẬT VIÊN TRÊN DATABASE TẠM THỜI (TEMP DB)
==========================================================================
Mục tiêu kiểm thử:
1. Chặn phân công / phân công lại trên 3 trạng thái không được phép:
   - COMPLETED (Hoàn tất)
   - REJECTED (Từ chối)
   - RETURNED (Đã trả máy)
2. Cho phép phân công / phân công lại trên 3 trạng thái xử lý kỹ thuật:
   - RECEIVED (Tiếp nhận)
   - INSPECTING (Kiểm tra)
   - REPAIRING (Sửa chữa)
3. Kiểm tra tính năng Workboard (mine tickets & cards) dịch chuyển chính xác
   khi phiếu được phân công lại giữa technician01 và technician02.
4. Bắt buộc có lý do khi phân công lại (REASSIGN_REASON_REQUIRED).
5. Phân quyền: Chỉ Quản lý (MANAGER) mới được gọi API phân công (KTV & Tiếp nhận bị 403).

Toàn bộ test chạy trên file database sao chép tạm thời, KHÔNG chạm vào database đang chạy!
"""
import os
import shutil
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

from fastapi.testclient import TestClient
from app.database import get_db
from app.main import app
from app.models import WarrantyTicket, TicketStatusHistory, TechnicianAssignment
from test_isolation import isolated_test_database

client = TestClient(app)

def login(username, password="123456"):
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    return resp.json()["access_token"]

def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}

def run_tests():
    print("=" * 75)
    print("BẮT ĐẦU KIỂM THỬ QUY TẮC PHÂN CÔNG KỸ THUẬT VIÊN TRÊN DATABASE TẠM")
    import app.database as app_db
    print(f"Temporary DB: {app_db.engine.url}")
    print("=" * 75)

    tokens = {
        "manager01": login("manager01"),
        "receptionist01": login("receptionist01"),
        "technician01": login("technician01"),
        "technician02": login("technician02"),
    }

    # Chuẩn bị dữ liệu mẫu trên temp DB:
    # Đảm bảo có đủ 6 trạng thái để test:
    # Phiếu 1: INSPECTING (assigned to technician01)
    # Phiếu 2: COMPLETED (assigned to technician01)
    # Phiếu 3: REJECTED (assigned to technician01)
    # Phiếu 4: RECEIVED (unassigned)
    # Tạo thêm Phiếu 5: REPAIRING (assigned to technician01)
    # Tạo thêm Phiếu 6: RETURNED (assigned to technician01)
    import app.database as app_db
    db = app_db.SessionLocal()
    try:
        # Kiểm tra phiếu 1
        t1 = db.query(WarrantyTicket).filter(WarrantyTicket.id == 1).first()
        t1.status = "INSPECTING"
        t1.assigned_technician_id = 3

        # Phiếu 2: COMPLETED
        t2 = db.query(WarrantyTicket).filter(WarrantyTicket.id == 2).first()
        t2.status = "COMPLETED"
        t2.assigned_technician_id = 3

        # Phiếu 3: REJECTED
        t3 = db.query(WarrantyTicket).filter(WarrantyTicket.id == 3).first()
        t3.status = "REJECTED"
        t3.assigned_technician_id = 3

        # Phiếu 4: RECEIVED
        t4 = db.query(WarrantyTicket).filter(WarrantyTicket.id == 4).first()
        t4.status = "RECEIVED"
        t4.assigned_technician_id = None

        # Tạo phiếu 5: REPAIRING
        t5 = WarrantyTicket(
            ticket_code="TK-TEST-REPAIRING-05",
            customer_id=1,
            product_instance_id=1,
            issue_description="Lỗi màn hình",
            service_center_id=1,
            created_by=2,
            status="REPAIRING",
            assigned_technician_id=3,
        )
        db.add(t5)

        # Tạo phiếu 6: RETURNED
        t6 = WarrantyTicket(
            ticket_code="TK-TEST-RETURNED-06",
            customer_id=1,
            product_instance_id=1,
            issue_description="Lỗi phím",
            service_center_id=1,
            created_by=2,
            status="RETURNED",
            assigned_technician_id=3,
        )
        db.add(t6)
        db.commit()
        db.refresh(t5)
        db.refresh(t6)
        t5_id = t5.id
        t6_id = t6.id
    finally:
        db.close()

    print("\n--- 1. KIỂM THỬ CHẶN PHÂN CÔNG Ở 3 TRẠNG THÁI: COMPLETED, REJECTED, RETURNED ---")
    # 1.1 Phiếu COMPLETED (id=2)
    resp = client.post(
        "/api/v1/warranty-tickets/2/assign",
        json={"technician_id": 4, "note": "Thử phân công phiếu đã hoàn tất"},
        headers=auth_headers(tokens["manager01"]),
    )
    assert resp.status_code == 400, f"Expected 400 for COMPLETED ticket, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data.get("error_code") == "TICKET_NOT_ASSIGNABLE", f"Wrong error_code: {data}"
    print(f"[PASS] Phiếu COMPLETED: Bị chặn phân công chính xác với HTTP 400 ({data.get('error_code')})")

    # 1.2 Phiếu REJECTED (id=3)
    resp = client.post(
        "/api/v1/warranty-tickets/3/assign",
        json={"technician_id": 4, "note": "Thử phân công phiếu đã từ chối"},
        headers=auth_headers(tokens["manager01"]),
    )
    assert resp.status_code == 400, f"Expected 400 for REJECTED ticket, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data.get("error_code") == "TICKET_NOT_ASSIGNABLE", f"Wrong error_code: {data}"
    print(f"[PASS] Phiếu REJECTED: Bị chặn phân công chính xác với HTTP 400 ({data.get('error_code')})")

    # 1.3 Phiếu RETURNED (id=t6_id)
    resp = client.post(
        f"/api/v1/warranty-tickets/{t6_id}/assign",
        json={"technician_id": 4, "note": "Thử phân công phiếu đã trả máy"},
        headers=auth_headers(tokens["manager01"]),
    )
    assert resp.status_code == 400, f"Expected 400 for RETURNED ticket, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data.get("error_code") == "TICKET_NOT_ASSIGNABLE", f"Wrong error_code: {data}"
    print(f"[PASS] Phiếu RETURNED: Bị chặn phân công chính xác với HTTP 400 ({data.get('error_code')})")

    print("\n--- 2. KIỂM THỬ CHO PHÉP PHÂN CÔNG / PHÂN CÔNG LẠI Ở 3 TRẠNG THÁI: RECEIVED, INSPECTING, REPAIRING ---")
    # 2.1 Phiếu RECEIVED (id=4): Phân công lần đầu cho technician01 (user_id=3)
    resp = client.post(
        "/api/v1/warranty-tickets/4/assign",
        json={"technician_id": 3, "note": "Phân công ban đầu cho Tuấn"},
        headers=auth_headers(tokens["manager01"]),
    )
    assert resp.status_code == 200, f"Expected 200 for RECEIVED ticket assign, got {resp.status_code}: {resp.text}"
    assert resp.json()["assigned_technician_id"] == 3
    print("[PASS] Phiếu RECEIVED: Phân công ban đầu thành công (HTTP 200).")

    # Phân công lại phiếu 4 từ technician01 (id=3) sang technician02 (id=4)
    resp = client.post(
        "/api/v1/warranty-tickets/4/assign",
        json={"technician_id": 4, "note": "Chuyển việc cho Huy xử lý"},
        headers=auth_headers(tokens["manager01"]),
    )
    assert resp.status_code == 200, f"Expected 200 for RECEIVED ticket reassign, got {resp.status_code}: {resp.text}"
    assert resp.json()["assigned_technician_id"] == 4
    print("[PASS] Phiếu RECEIVED: Phân công lại thành công từ Tuấn sang Huy (HTTP 200).")

    # 2.2 Phiếu INSPECTING (id=1): Phân công lại từ technician01 sang technician02
    resp = client.post(
        "/api/v1/warranty-tickets/1/assign",
        json={"technician_id": 4, "note": "Phân công lại kiểm tra cho Huy"},
        headers=auth_headers(tokens["manager01"]),
    )
    assert resp.status_code == 200, f"Expected 200 for INSPECTING ticket reassign, got {resp.status_code}: {resp.text}"
    assert resp.json()["assigned_technician_id"] == 4
    print("[PASS] Phiếu INSPECTING: Phân công lại thành công cho Huy (HTTP 200).")

    # 2.3 Phiếu REPAIRING (id=t5_id): Phân công lại từ technician01 sang technician02
    resp = client.post(
        f"/api/v1/warranty-tickets/{t5_id}/assign",
        json={"technician_id": 4, "note": "Phân công lại sửa chữa cho Huy"},
        headers=auth_headers(tokens["manager01"]),
    )
    assert resp.status_code == 200, f"Expected 200 for REPAIRING ticket reassign, got {resp.status_code}: {resp.text}"
    assert resp.json()["assigned_technician_id"] == 4
    print("[PASS] Phiếu REPAIRING: Phân công lại thành công cho Huy (HTTP 200).")

    print("\n--- 3. KIỂM THỬ WORKBOARD PHẢN ÁNH CHÍNH XÁC SAU PHÂN CÔNG LẠI ---")
    # Lấy workboard scope=MINE của technician02
    resp_t2 = client.get("/api/v1/warranty-tickets/workboard?scope=MINE", headers=auth_headers(tokens["technician02"]))
    assert resp_t2.status_code == 200
    wb_t2 = resp_t2.json()
    cards_t2 = {c["key"]: c["count"] for c in wb_t2["cards"]}
    # technician02 nhận 3 phiếu (phiếu 4 RECEIVED, phiếu 1 INSPECTING, phiếu 5 REPAIRING)
    assert cards_t2["TOTAL"] == 3, f"technician02 should have 3 tickets, got {cards_t2['TOTAL']}"
    assert cards_t2["IN_PROGRESS"] == 3
    assert len(wb_t2["my_tickets"]) == 3
    print(f"[PASS] technician02 workboard phản ánh chính xác: Tổng {cards_t2['TOTAL']} phiếu, Đang xử lý {cards_t2['IN_PROGRESS']} phiếu, Bảng có {len(wb_t2['my_tickets'])} dòng.")

    print("\n--- 4. KIỂM THỬ YÊU CẦU LÝ DO KHI PHÂN CÔNG LẠI (REASSIGN_REASON_REQUIRED) ---")
    # Phân công lại phiếu 1 mà không truyền note
    resp = client.post(
        "/api/v1/warranty-tickets/1/assign",
        json={"technician_id": 3, "note": ""},
        headers=auth_headers(tokens["manager01"]),
    )
    assert resp.status_code == 400
    assert resp.json().get("error_code") == "REASSIGN_REASON_REQUIRED"
    print(f"[PASS] Phân công lại thiếu lý do bị chặn chính xác với HTTP 400 (REASSIGN_REASON_REQUIRED).")

    print("\n--- 5. KIỂM THỬ PHÂN QUYỀN VAI TRÒ (CHỈ MANAGER MỚI ĐƯỢC PHÂN CÔNG) ---")
    # Tiếp nhận thử phân công phiếu 4
    resp = client.post(
        "/api/v1/warranty-tickets/4/assign",
        json={"technician_id": 3, "note": "Tiếp nhận tự phân công"},
        headers=auth_headers(tokens["receptionist01"]),
    )
    assert resp.status_code == 403, f"Expected 403 for receptionist, got {resp.status_code}"
    print("[PASS] Tiếp nhận gọi API phân công bị chặn với HTTP 403 Forbidden.")

    # Kỹ thuật viên thử phân công phiếu 4
    resp = client.post(
        "/api/v1/warranty-tickets/4/assign",
        json={"technician_id": 3, "note": "KTV tự phân công"},
        headers=auth_headers(tokens["technician01"]),
    )
    assert resp.status_code == 403, f"Expected 403 for technician, got {resp.status_code}"
    print("[PASS] Kỹ thuật viên gọi API phân công bị chặn với HTTP 403 Forbidden.")

    print("\n" + "=" * 75)
    print("TẤT CẢ KIỂM THỬ QUY TẮC PHÂN CÔNG TRÊN TEMP DB ĐẠT 100%!")
    print("=" * 75)

if __name__ == "__main__":
    with isolated_test_database(copy_from_app_db=True):
        run_tests()
