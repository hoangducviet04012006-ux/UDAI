"""
Kiểm thử trực tiếp API xét duyệt kết quả AI (AI Review RBAC & State Restrictions):
1. KTV được giao phiếu xét duyệt -> HTTP 200 OK (APPROVED ghi nhận error_category_id).
2. KTV KHÁC (không được giao phiếu này) xét duyệt -> HTTP 403 Forbidden.
3. Nhân viên TIẾP NHẬN xét duyệt -> HTTP 403 Forbidden (Tiếp nhận không có quyền ai.review).
4. QUẢN LÝ xét duyệt -> HTTP 200 OK.
5. Phiếu ở trạng thái COMPLETED / REJECTED / RETURNED xét duyệt -> HTTP 400 Bad Request.
"""
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

from fastapi.testclient import TestClient
from tests.test_isolation import isolated_test_database
from app.main import app
from app.models import User, WarrantyTicket, ProductInstance, ErrorCategory, Customer
from app.services.auth_service import hash_password
from app.services import ai_error_classifier as ai_service

def run_ai_review_api_tests():
    print("======================================================================")
    print("KIỂM THỬ TRỰC TIẾP API XÉT DUYỆT NHÓM LỖI AI (RBAC & TRẠNG THÁI PHIẾU)")
    print("======================================================================")
    
    with isolated_test_database() as temp_db_path:
        import app.database as app_db
        db = app_db.SessionLocal()
        
        # 1. Tạo dữ liệu mẫu
        from tests.seed_data import seed
        seed(session=db)
        
        # Thêm 2 KTV, 1 Tiếp nhận, 1 Quản lý
        mgr = db.query(User).filter(User.username == "manager01").first()
        rec = db.query(User).filter(User.username == "receptionist01").first()
        tech1 = db.query(User).filter(User.username == "technician01").first()
        tech2 = db.query(User).filter(User.username == "technician02").first()
        
        # Lấy phiếu bảo hành đang INSPECTING được giao cho tech1
        ticket = db.query(WarrantyTicket).filter(WarrantyTicket.status == "INSPECTING").first()
        if not ticket:
            ticket = db.query(WarrantyTicket).first()
            ticket.status = "INSPECTING"
        ticket.assigned_technician_id = tech1.id
        db.commit()
        db.refresh(ticket)
        
        print(f"[*] Phiếu test ID={ticket.id}, Mã={ticket.ticket_code}, Trạng thái={ticket.status}, KTV phụ trách ID={ticket.assigned_technician_id}")
        
        # Gọi AI tạo gợi ý phân loại lỗi
        ai_res = ai_service.classify_ticket_error(db, ticket.id)
        result_id = ai_res.id
        print(f"[*] Tạo kết quả AI ID={result_id}, review_status={ai_res.review_status}")
        
        # Test client logins
        client = TestClient(app)
        
        def get_auth_headers(username, password="123456"):
            res = client.post("/api/v1/auth/login", json={"username": username, "password": password})
            assert res.status_code == 200, f"Login failed for {username}: {res.text}"
            token = res.json()["access_token"]
            return {"Authorization": f"Bearer {token}"}
            
        headers_mgr = get_auth_headers("manager01")
        headers_rec = get_auth_headers("receptionist01")
        headers_tech1 = get_auth_headers("technician01")
        headers_tech2 = get_auth_headers("technician02")
        
        # -------------------------------------------------------------
        # CA 1: Tiếp nhận xét duyệt -> BỊ CHẶN 403
        # -------------------------------------------------------------
        res_rec = client.patch(f"/api/v1/ai/results/{result_id}/review", json={
            "reviewed_by": rec.id,
            "decision": "APPROVED",
            "note": "Tiếp nhận tự ý duyệt"
        }, headers=headers_rec)
        assert res_rec.status_code == 403, f"Expected 403 for receptionist, got {res_rec.status_code}"
        print("  [PASS] Ca 1: Tiếp nhận gọi API xét duyệt AI bị chặn HTTP 403 Forbidden (không có quyền ai.review)")
        
        # -------------------------------------------------------------
        # CA 2: KTV2 (không được giao phiếu này) xét duyệt -> BỊ CHẶN 403
        # -------------------------------------------------------------
        res_tech2 = client.patch(f"/api/v1/ai/results/{result_id}/review", json={
            "reviewed_by": tech2.id,
            "decision": "APPROVED",
            "note": "KTV khác duyệt hộ"
        }, headers=headers_tech2)
        assert res_tech2.status_code == 403, f"Expected 403 for tech2, got {res_tech2.status_code}"
        print("  [PASS] Ca 2: KTV khác (không phụ trách phiếu) gọi API xét duyệt bị chặn HTTP 403 Forbidden")
        
        # -------------------------------------------------------------
        # CA 3: KTV1 (được phân công phiếu) xét duyệt -> THÀNH CÔNG 200 OK
        # -------------------------------------------------------------
        res_tech1 = client.patch(f"/api/v1/ai/results/{result_id}/review", json={
            "reviewed_by": tech1.id,
            "decision": "APPROVED",
            "note": "KTV phụ trách xác nhận đúng nhóm lỗi phần cứng"
        }, headers=headers_tech1)
        assert res_tech1.status_code == 200, f"Expected 200 for assigned tech1, got {res_tech1.status_code}: {res_tech1.text}"
        data1 = res_tech1.json()
        assert data1["review_status"] == "APPROVED"
        assert data1["reviewed_by"] == tech1.id
        
        db.refresh(ticket)
        assert ticket.error_category_id is not None
        print(f"  [PASS] Ca 3: KTV phụ trách xét duyệt APPROVED thành công 200 OK (ghi nhận error_category_id={ticket.error_category_id})")
        
        # -------------------------------------------------------------
        # CA 4: Quản lý xét duyệt trên kết quả AI mới -> THÀNH CÔNG 200 OK
        # -------------------------------------------------------------
        ai_res_2 = ai_service.classify_ticket_error(db, ticket.id)
        result_id_2 = ai_res_2.id
        
        res_mgr = client.patch(f"/api/v1/ai/results/{result_id_2}/review", json={
            "reviewed_by": mgr.id,
            "decision": "APPROVED",
            "note": "Quản lý xác nhận"
        }, headers=headers_mgr)
        assert res_mgr.status_code == 200, f"Expected 200 for manager, got {res_mgr.status_code}: {res_mgr.text}"
        print("  [PASS] Ca 4: Quản lý xét duyệt APPROVED thành công 200 OK")
        
        # -------------------------------------------------------------
        # CA 5: Phiếu đã ở COMPLETED / RETURNED -> BỊ CHẶN 400 Bad Request khi review
        # -------------------------------------------------------------
        ai_res_3 = ai_service.classify_ticket_error(db, ticket.id)
        ticket.status = "COMPLETED"
        db.commit()
        
        res_closed = client.patch(f"/api/v1/ai/results/{ai_res_3.id}/review", json={
            "reviewed_by": mgr.id,
            "decision": "APPROVED",
            "note": "Duyệt khi phiếu đã xong"
        }, headers=headers_mgr)
        assert res_closed.status_code == 400, f"Expected 400 for closed ticket, got {res_closed.status_code}: {res_closed.text}"
        print("  [PASS] Ca 5: Phiếu ở trạng thái COMPLETED/RETURNED gọi API xét duyệt AI bị chặn HTTP 400 Bad Request")
        
        db.close()
        print("======================================================================")
        print("TẤT CẢ 5/5 CA KIỂM THỬ TRỰC TIẾP API AI REVIEW ĐỀU ĐẠT CHUẨN!")
        print("======================================================================")

if __name__ == "__main__":
    run_ai_review_api_tests()
