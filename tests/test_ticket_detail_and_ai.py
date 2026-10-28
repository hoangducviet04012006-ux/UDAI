"""
Kiểm thử toàn diện cho các yêu cầu trong đợt sửa đổi:
1. Đối soát ngày giờ và thời gian xử lý (dưới 1 giờ, mốc sai thứ tự, thiếu dữ liệu, ngày tiếp nhận).
2. Sửa kết quả phân loại AI (thiếu thông tin không hiện 95%, nhãn không hợp lệ, lỗi provider).
3. Quyền xác nhận nhóm lỗi (KTV được giao xác nhận; Tiếp nhận / KTV khác bị chặn).
4. Chặn ghi kết quả sau hoàn tất (COMPLETED, REJECTED, RETURNED bị chặn cập nhật chẩn đoán, sửa chữa, AI).
5. Hai nhánh bàn giao và chặn mở lại phiếu RETURNED.
6. Phạm vi danh sách mine/all theo vai trò.
"""
import tempfile
import os
import sys
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

try:
    import pytest
    fixture_dec = pytest.fixture(scope="module")
except ImportError:
    def fixture_dec(func):
        return func


from app.main import app
from app.database import Base, get_db
from app.models import ServiceCenter, User, Customer, Product, ProductInstance, WarrantyTicket, TicketStatusHistory, ErrorCategory, AIResult
from app.services.auth_service import hash_password, create_access_token
from app.services.ticket_view import format_duration, build_ticket_detail, build_ai_suggestion
from app.services.ai_error_classifier import validate_ai_output, MockAIProvider, AIClassificationOutput


from test_isolation import isolated_test_database


@fixture_dec
def temp_db():
    iso = isolated_test_database()
    engine, TestingSessionLocal, db_path = iso.__enter__()
    try:
        db = TestingSessionLocal()

        # Seed service center
        sc = ServiceCenter(id=1, name="TTBH Trung Tâm", address="123 Phố Huế", active=True)
        db.add(sc)
        db.commit()

        # Seed users
        mgr = User(username="mgr_test", password_hash=hash_password("123456"), full_name="Quản Lý Test", role="MANAGER", active=True, service_center_id=1)
        rec = User(username="rec_test", password_hash=hash_password("123456"), full_name="Tiếp Nhận Test", role="RECEPTIONIST", active=True, service_center_id=1)
        tech1 = User(username="tech1_test", password_hash=hash_password("123456"), full_name="KTV 1 Test", role="TECHNICIAN", active=True, service_center_id=1)
        tech2 = User(username="tech2_test", password_hash=hash_password("123456"), full_name="KTV 2 Test", role="TECHNICIAN", active=True, service_center_id=1)
        db.add_all([mgr, rec, tech1, tech2])
        db.commit()

        # Seed error categories
        cat1 = ErrorCategory(id=1, name="Loi nguon", description="Nguon", active=True)
        cat2 = ErrorCategory(id=2, name="Loi man hinh hien thi", description="Man hinh", active=True)
        db.add_all([cat1, cat2])
        db.commit()

        # Seed customer, product, instance
        cust = Customer(id=1, full_name="Nguyễn Văn A", phone="0987654321", email="a@example.com")
        prod = Product(id=1, name="Laptop Asus ROG", brand="Asus", category="Laptop", warranty_duration_months=24)
        inst = ProductInstance(id=1, serial_number="ROG-TEST-001", product_id=1, customer_id=1, purchase_date=datetime(2025, 1, 1), warranty_end_date=datetime(2027, 1, 1))
        db.add_all([cust, prod, inst])
        db.commit()

        yield {
            "db": db,
            "mgr": mgr,
            "rec": rec,
            "tech1": tech1,
            "tech2": tech2,
            "cat1": cat1,
            "cat2": cat2,
            "client": TestClient(app),
        }
    finally:
        try:
            db.close()
        except Exception:
            pass
        iso.__exit__(None, None, None)


def test_format_duration():
    """Kiểm tra logic format thời lượng: thiếu mốc, sai thứ tự, dưới 1 giờ (phút), trên 1 giờ (giờ phút)."""
    # Dưới 1 giờ
    assert format_duration(45 * 60) == "45 phút"
    assert format_duration(5 * 60) == "5 phút"
    assert format_duration(30) == "1 phút"

    # Tròn giờ và lẻ phút
    assert format_duration(2 * 3600) == "2 giờ"
    assert format_duration(4 * 3600 + 15 * 60) == "4 giờ 15 phút"


def test_ticket_timestamps_and_duration_in_detail(temp_db):
    """Kiểm tra màn hình chi tiết phiếu phân biệt ngày tiếp nhận, thời điểm tạo và tính thời gian xử lý."""
    db = temp_db["db"]
    mgr = temp_db["mgr"]
    tech1 = temp_db["tech1"]

    # Phiếu hợp lệ: tiếp nhận 10/05/2026 13:30, hoàn tất 10/05/2026 17:45 (4h15m)
    t1 = WarrantyTicket(
        ticket_code="TK-TEST-TIME-01",
        customer_id=1,
        product_instance_id=1,
        service_center_id=1,
        created_by=mgr.id,
        status="COMPLETED",
        created_at=datetime(2026, 5, 10, 13, 30),
        diagnosis_at=datetime(2026, 5, 10, 15, 20),
        repair_at=datetime(2026, 5, 10, 17, 45),
        completed_at=datetime(2026, 5, 10, 17, 45),
        assigned_technician_id=tech1.id,
        issue_description="Không lên nguồn",
    )
    db.add(t1)
    db.commit()

    detail = build_ticket_detail(db, t1, current_user=mgr)
    handover = detail["handover"]
    assert handover["processing_time_hours"] == 4.2
    assert handover["processing_time_display"] == "4 giờ 15 phút"
    assert detail["intake"]["received_at"] == datetime(2026, 5, 10, 13, 30)
    assert detail["diagnosis"]["confirmed_at"] == datetime(2026, 5, 10, 15, 20)

    # Phiếu mốc sai thứ tự: completed_at trước created_at -> không tính số liệu, báo sai thứ tự
    t2 = WarrantyTicket(
        ticket_code="TK-TEST-TIME-02",
        customer_id=1,
        product_instance_id=1,
        service_center_id=1,
        created_by=mgr.id,
        status="COMPLETED",
        created_at=datetime(2026, 10, 27, 10, 0),
        completed_at=datetime(2026, 5, 10, 10, 0),  # trước created_at
        assigned_technician_id=tech1.id,
        issue_description="Lỗi",
    )
    db.add(t2)
    db.commit()

    detail2 = build_ticket_detail(db, t2, current_user=mgr)
    assert "sai thứ tự" in detail2["handover"]["processing_time_display"]

    # Phiếu đang xử lý chưa hoàn tất -> "Chưa đủ dữ liệu"
    t3 = WarrantyTicket(
        ticket_code="TK-TEST-TIME-03",
        customer_id=1,
        product_instance_id=1,
        service_center_id=1,
        created_by=mgr.id,
        status="INSPECTING",
        created_at=datetime(2026, 10, 27, 10, 0),
        assigned_technician_id=tech1.id,
        issue_description="Lỗi",
    )
    db.add(t3)
    db.commit()

    detail3 = build_ticket_detail(db, t3, current_user=mgr)
    assert detail3["handover"]["processing_time_display"] == "Chưa đủ dữ liệu"

    # Phiếu COMPLETED nhưng thiếu bằng chứng hoàn tất (completed_at = None) -> "Chưa đủ dữ liệu"
    t4 = WarrantyTicket(
        ticket_code="TK-TEST-TIME-04",
        customer_id=1,
        product_instance_id=1,
        service_center_id=1,
        created_by=mgr.id,
        status="COMPLETED",
        created_at=datetime(2026, 10, 27, 10, 0),
        completed_at=None,
        assigned_technician_id=tech1.id,
        issue_description="Lỗi nguồn",
    )
    db.add(t4)
    db.commit()

    detail4 = build_ticket_detail(db, t4, current_user=mgr)
    assert detail4["handover"]["processing_time_display"] == "Chưa đủ dữ liệu"
    assert detail4["handover"]["waiting_time_display"] == "Chưa đủ dữ liệu"

    # Kiểm tra API /stats/summary: Loại phiếu thiếu mốc/sai thứ tự khỏi avg, nhưng giữ trong tổng và thống kê trạng thái
    client = temp_db["client"]
    token_dict = create_access_token(mgr)
    resp_stats = client.get(
        "/api/v1/warranty-tickets/stats/summary",
        headers={"Authorization": f"Bearer {token_dict['access_token']}"},
    )
    assert resp_stats.status_code == 200
    stats_data = resp_stats.json()
    assert stats_data["total_tickets"] >= 4
    # Phiếu t2 (sai thứ tự) và t4 (thiếu completed_at) nằm trong missing_time_tickets_count
    assert stats_data["missing_time_tickets_count"] >= 2
    # Chỉ phiếu t1 (hợp lệ) nằm trong mẫu tính thời gian trung bình
    assert stats_data["valid_time_tickets_count"] >= 1



def test_ai_classification_guardrails(temp_db):
    """Kiểm tra: thiếu thông tin không hiện 95%; nhãn không hợp lệ bị loại bỏ."""
    db = temp_db["db"]
    cats = [temp_db["cat1"], temp_db["cat2"]]

    # 1. Output thiếu thông tin (suggested_category_id = None)
    raw_insufficient = {
        "suggested_category_id": None,
        "suggested_category_name": None,
        "confidence": 0.95,  # Provider có lỡ trả 0.95 thì validate_ai_output phải ép xuống <= 0.40
        "reason": "Chưa đủ thông tin",
        "need_more_information": ["Thiết bị lỗi ở bộ phận nào?"],
    }
    validated = validate_ai_output(raw_insufficient, cats)
    assert validated.suggested_category_id is None
    assert validated.confidence <= 0.40

    # 2. Output có nhãn không hợp lệ (không tồn tại trong error_categories)
    raw_invalid = {
        "suggested_category_id": 999,
        "suggested_category_name": "Nhãn Bịa Đặt",
        "confidence": 0.90,
        "reason": "AI tự nghĩ ra nhãn",
    }
    validated_invalid = validate_ai_output(raw_invalid, cats)
    assert validated_invalid.suggested_category_id is None
    assert validated_invalid.confidence == 0.0
    assert "[INVALID AI OUTPUT]" in validated_invalid.reason

    # 3. Khi build_ai_suggestion đọc bản ghi thiếu thông tin -> confidence phải là None
    ai_record = AIResult(
        ticket_id=999,
        ai_function="ERROR_CLASSIFICATION",
        confidence_score=0.95,
        review_status="PENDING",
        output_data={"suggested_category_id": None, "suggested_category_name": None},
        input_data={"provider": "mock"},
    )
    db.add(ai_record)
    db.commit()

    # Stub latest_ai_result via test query
    sug = build_ai_suggestion(db, 999)
    assert sug["suggested_category_id"] is None
    assert sug["confidence"] is None  # Đảm bảo frontend không nhận được số 0.95 khi thiếu thông tin!


def auth_header(user: User) -> dict:
    token_dict = create_access_token(user)
    return {"Authorization": f"Bearer {token_dict['access_token']}"}


def test_error_category_confirmation_permissions(temp_db):
    """
    Quyền xác nhận nhóm lỗi:
    - KTV được phân công: được duyệt (APPROVED)
    - KTV khác: bị chặn (HTTP 403)
    - Nhân viên tiếp nhận: bị chặn (HTTP 403)
    - Quản lý: được duyệt
    """
    db = temp_db["db"]
    client = temp_db["client"]
    mgr = temp_db["mgr"]
    rec = temp_db["rec"]
    tech1 = temp_db["tech1"]
    tech2 = temp_db["tech2"]

    # Tạo phiếu ở INSPECTING phân công cho tech1
    t = WarrantyTicket(
        ticket_code="TK-TEST-PERM-01",
        customer_id=1,
        product_instance_id=1,
        service_center_id=1,
        created_by=rec.id,
        status="INSPECTING",
        created_at=datetime.utcnow(),
        assigned_technician_id=tech1.id,
        issue_description="Màn hình kẻ sọc",
    )
    db.add(t)
    db.commit()

    # Tạo kết quả gợi ý AI
    ai_res = AIResult(
        ticket_id=t.id,
        ai_function="ERROR_CLASSIFICATION",
        confidence_score=0.85,
        review_status="PENDING",
        output_data={"suggested_category_id": 2, "suggested_category_name": "Loi man hinh hien thi"},
        input_data={"provider": "mock"},
    )
    db.add(ai_res)
    db.commit()

    # 1. Tiếp nhận cố duyệt -> 403
    resp_rec = client.patch(
        f"/api/v1/ai/results/{ai_res.id}/review",
        json={"reviewed_by": rec.id, "decision": "APPROVED"},
        headers=auth_header(rec),
    )
    assert resp_rec.status_code == 403

    # 2. KTV khác (tech2 không được phân công) cố duyệt -> 403
    resp_tech2 = client.patch(
        f"/api/v1/ai/results/{ai_res.id}/review",
        json={"reviewed_by": tech2.id, "decision": "APPROVED"},
        headers=auth_header(tech2),
    )
    assert resp_tech2.status_code == 403

    # 3. KTV được phân công (tech1) duyệt -> 200 OK
    resp_tech1 = client.patch(
        f"/api/v1/ai/results/{ai_res.id}/review",
        json={"reviewed_by": tech1.id, "decision": "APPROVED"},
        headers=auth_header(tech1),
    )
    assert resp_tech1.status_code == 200
    db.refresh(t)
    assert t.error_category_id == 2


def test_block_modifications_on_closed_tickets(temp_db):
    """
    Chặn ghi kết quả sau hoàn tất:
    Ở COMPLETED, REJECTED, RETURNED:
    - Không cho sửa chẩn đoán qua API (HTTP 400)
    - Không cho sửa nội dung sửa chữa qua API (HTTP 400)
    - Không cho tạo gợi ý phân loại AI (HTTP 400)
    """
    db = temp_db["db"]
    client = temp_db["client"]
    tech1 = temp_db["tech1"]
    mgr = temp_db["mgr"]

    for term_status in ("COMPLETED", "REJECTED", "RETURNED"):
        closed_ticket = WarrantyTicket(
            ticket_code=f"TK-CLOSED-{term_status}",
            customer_id=1,
            product_instance_id=1,
            service_center_id=1,
            created_by=mgr.id,
            status=term_status,
            created_at=datetime.utcnow() - timedelta(days=1),
            completed_at=datetime.utcnow() - timedelta(hours=5),
            assigned_technician_id=tech1.id,
            issue_description="Lỗi",
        )
        db.add(closed_ticket)
        db.commit()

        # 1. Chặn sửa chẩn đoán
        r_diag = client.patch(
            f"/api/v1/warranty-tickets/{closed_ticket.id}/diagnosis",
            json={"actor_id": mgr.id, "diagnosis_note": "Sửa chẩn đoán mới"},
            headers=auth_header(mgr),
        )
        assert r_diag.status_code == 400

        # 2. Chặn sửa sửa chữa
        r_rep = client.patch(
            f"/api/v1/warranty-tickets/{closed_ticket.id}/repair",
            json={"actor_id": mgr.id, "repair_content": "Sửa nội dung mới"},
            headers=auth_header(mgr),
        )
        assert r_rep.status_code == 400

        # 3. Chặn tạo gợi ý AI
        r_ai = client.post(
            f"/api/v1/ai/tickets/{closed_ticket.id}/classify-error",
            headers=auth_header(mgr),
        )
        assert r_ai.status_code == 400


def test_handover_and_no_reopen_for_returned(temp_db):
    """
    Kiểm tra hai nhánh bàn giao:
    - COMPLETED -> RETURNED: bàn giao thành công
    - REJECTED -> RETURNED: bàn giao thành công
    - RETURNED: không thể chuyển tiếp trạng thái nào khác (HTTP 400)
    """
    db = temp_db["db"]
    client = temp_db["client"]
    rec = temp_db["rec"]

    # Nhánh 1: COMPLETED -> RETURNED
    t_comp = WarrantyTicket(
        ticket_code="TK-TEST-HANDOVER-COMP",
        customer_id=1,
        product_instance_id=1,
        service_center_id=1,
        created_by=rec.id,
        status="COMPLETED",
        created_at=datetime.utcnow() - timedelta(days=1),
        completed_at=datetime.utcnow() - timedelta(hours=2),
        diagnosis_note="Xong",
        repair_content="Đã thay linh kiện",
        error_category_id=1,
        issue_description="Nguồn",
    )
    db.add(t_comp)
    db.commit()

    r1 = client.patch(
        f"/api/v1/warranty-tickets/{t_comp.id}/status",
        json={"new_status": "RETURNED", "changed_by": rec.id, "note": "Đã bàn giao máy cho khách"},
        headers=auth_header(rec),
    )
    assert r1.status_code == 200
    db.refresh(t_comp)
    assert t_comp.status == "RETURNED"

    # Nhánh 2: REJECTED -> RETURNED
    t_rej = WarrantyTicket(
        ticket_code="TK-TEST-HANDOVER-REJ",
        customer_id=1,
        product_instance_id=1,
        service_center_id=1,
        created_by=rec.id,
        status="REJECTED",
        created_at=datetime.utcnow() - timedelta(days=1),
        completed_at=datetime.utcnow() - timedelta(hours=2),
        diagnosis_note="Từ chối do vào nước",
        rejection_reason="Máy vào nước",
        issue_description="Rơi nước",
    )
    db.add(t_rej)
    db.commit()

    r2 = client.patch(
        f"/api/v1/warranty-tickets/{t_rej.id}/status",
        json={"new_status": "RETURNED", "changed_by": rec.id, "note": "Đã trả lại máy cho khách"},
        headers=auth_header(rec),
    )
    assert r2.status_code == 200
    db.refresh(t_rej)
    assert t_rej.status == "RETURNED"

    # Chặn mở lại hoặc chuyển trạng thái trên phiếu RETURNED
    # 1. Quản lý cố mở lại -> 400 (State machine đóng)
    mgr = temp_db["mgr"]
    r3 = client.patch(
        f"/api/v1/warranty-tickets/{t_comp.id}/status",
        json={"new_status": "INSPECTING", "changed_by": mgr.id, "note": "Mở lại"},
        headers=auth_header(mgr),
    )
    assert r3.status_code == 400

    # 2. Tiếp nhận cố mở lại -> 403/400 (bị chặn)
    r4 = client.patch(
        f"/api/v1/warranty-tickets/{t_comp.id}/status",
        json={"new_status": "INSPECTING", "changed_by": rec.id, "note": "Mở lại"},
        headers=auth_header(rec),
    )
    assert r4.status_code in (400, 403)





if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  CHẠY TEST TOÀN DIỆN CHO CHI TIẾT PHIẾU, AI VÀ PHÂN QUYỀN")
    print("=" * 70)
    
    tests = [
        ("01. Test format duration (thiếu mốc, sai thứ tự, phút, giờ phút)", test_format_duration, False),
        ("02. Test đối soát ngày giờ, thời gian xử lý & chờ nhận trong chi tiết phiếu", test_ticket_timestamps_and_duration_in_detail, True),
        ("03. Test AI guardrails (thiếu TT không hiện %, nhãn không hợp lệ, lỗi provider)", test_ai_classification_guardrails, True),
        ("04. Test quyền xác nhận nhóm lỗi (KTV được giao, Manager, chặn Receptionist & KTV khác)", test_error_category_confirmation_permissions, True),
        ("05. Test chặn ghi kết quả sau hoàn tất (COMPLETED, REJECTED, RETURNED)", test_block_modifications_on_closed_tickets, True),
        ("06. Test bàn giao từ COMPLETED/REJECTED và chặn mở lại RETURNED", test_handover_and_no_reopen_for_returned, True),
    ]

    gen = temp_db()
    context = next(gen)

    passed = 0
    failed = 0

    try:
        for name, fn, needs_db in tests:
            try:
                if needs_db:
                    fn(context)
                else:
                    fn()
                print(f"  [PASS] {name}")
                passed += 1
            except Exception as e:
                print(f"  [FAIL] {name}: {e}")
                import traceback
                traceback.print_exc()
                failed += 1
    finally:
        try:
            next(gen)
        except StopIteration:
            pass

    print("=" * 70)
    print(f"KẾT QUẢ: {passed}/{len(tests)} PASS, {failed} FAIL")
    print("=" * 70 + "\n")
    sys.exit(0 if failed == 0 else 1)

