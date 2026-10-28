"""
KIỂM CHỨNG TÍNH BẤT BIẾN KHI CHẠY LẠI MIGRATION (IDEMPOTENCY PROOF)
===================================================================
Mục tiêu kiểm chứng (Yêu cầu 3):
1. Chạy trên CSDL tạm có CẢ dữ liệu cũ và dữ liệu mới.
2. Chạy migration lần 1: Nâng cấp schema và chuẩn hóa dữ liệu cũ.
3. Chụp snapshot toàn bộ trạng thái, kết quả, mốc thời gian và lịch sử.
4. Chạy migration lần 2.
5. Chứng minh lần chạy thứ 2:
   - KHÔNG đổi trạng thái (status).
   - KHÔNG đổi kết quả (resolution, is_warranty_eligible, rejection_reason).
   - KHÔNG đổi các mốc thời điểm (*_at).
   - KHÔNG làm thay đổi hoặc sinh thêm bản ghi lịch sử chuyển bước (ticket_status_history).
"""
import os
import sys
import tempfile
from datetime import datetime, date

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (
    Customer, ErrorCategory, Product, ProductInstance,
    ServiceCenter, TicketStatusHistory, User, WarrantyTicket
)
from app.services.schema_migration import ensure_schema_upgrades, migrate_tickets_data

def build_snapshot(engine):
    """Chụp snapshot toàn diện của các bảng liên quan đến phiếu bảo hành."""
    with engine.connect() as conn:
        # 1. Bảng warranty_tickets
        tickets_rows = conn.execute(text("""
            SELECT id, ticket_code, status, resolution, is_warranty_eligible, 
                   rejection_reason, diagnosis_note, repair_content, handover_note,
                   created_at, diagnosis_at, repair_at, 
                   completed_at, handed_over_at, assigned_technician_id, assigned_at
            FROM warranty_tickets
            ORDER BY id ASC
        """)).fetchall()

        tickets_data = []
        for r in tickets_rows:
            tickets_data.append({
                "id": r[0],
                "ticket_code": r[1],
                "status": r[2],
                "resolution": r[3],
                "is_warranty_eligible": r[4],
                "rejection_reason": r[5],
                "diagnosis_note": r[6],
                "repair_content": r[7],
                "handover_note": r[8],
                "created_at": str(r[9]) if r[9] else None,
                "diagnosis_at": str(r[10]) if r[10] else None,
                "repair_at": str(r[11]) if r[11] else None,
                "completed_at": str(r[12]) if r[12] else None,
                "handed_over_at": str(r[13]) if r[13] else None,
                "assigned_technician_id": r[14],
                "assigned_at": str(r[15]) if r[15] else None,
            })

        # 2. Bảng ticket_status_history
        hist_rows = conn.execute(text("""
            SELECT id, ticket_id, from_status, to_status, changed_by, note, created_at
            FROM ticket_status_history
            ORDER BY id ASC
        """)).fetchall()

        hist_data = []
        for h in hist_rows:
            hist_data.append({
                "id": h[0],
                "ticket_id": h[1],
                "from_status": h[2],
                "to_status": h[3],
                "changed_by": h[4],
                "note": h[5],
                "created_at": str(h[6]) if h[6] else None,
            })

    return {
        "tickets": tickets_data,
        "history": hist_data,
        "ticket_count": len(tickets_data),
        "history_count": len(hist_data),
    }

def run_migration_proof():
    print("=" * 80)
    print("  KIỂM CHỨNG TÍNH BẤT BIẾN CỦA MIGRATION TRÊN DỮ LIỆU CŨ VÀ MỚI (YÊU CẦU 3)")
    print("=" * 80)

    temp_fd, temp_path = tempfile.mkstemp(prefix="migration_proof_", suffix=".db")
    os.close(temp_fd)
    engine = create_engine(f"sqlite:///{temp_path}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine)

    try:
        # 1. Tạo schema ban đầu
        Base.metadata.create_all(bind=engine)
        ensure_schema_upgrades(engine)

        db = Session()
        sc = ServiceCenter(name="TTBH Proof", address="123 Proof", phone="0123456789", active=True)
        db.add(sc)
        db.commit()

        u_mgr = User(username="mgr_p", password_hash="hash", full_name="QL Proof", role="MANAGER", service_center_id=sc.id)
        u_rec = User(username="rec_p", password_hash="hash", full_name="TN Proof", role="RECEPTIONIST", service_center_id=sc.id)
        u_tech = User(username="tech_p", password_hash="hash", full_name="KTV Proof", role="TECHNICIAN", service_center_id=sc.id)
        db.add_all([u_mgr, u_rec, u_tech])
        db.commit()

        cust = Customer(full_name="Khach Hang Proof", phone="0999888777", email="proof@baohanh.vn")
        db.add(cust)
        db.commit()

        prod = Product(name="Laptop Proof", brand="ProofBrand", category="Laptop", warranty_duration_months=24)
        db.add(prod)
        db.commit()

        inst1 = ProductInstance(product_id=prod.id, customer_id=cust.id, serial_number="SN-OLD-01", purchase_date=date(2025, 1, 1), warranty_end_date=date(2027, 1, 1), status="ACTIVE")
        inst2 = ProductInstance(product_id=prod.id, customer_id=cust.id, serial_number="SN-OLD-02", purchase_date=date(2025, 1, 1), warranty_end_date=date(2027, 1, 1), status="ACTIVE")
        inst3 = ProductInstance(product_id=prod.id, customer_id=cust.id, serial_number="SN-OLD-03", purchase_date=date(2025, 1, 1), warranty_end_date=date(2027, 1, 1), status="ACTIVE")
        inst4 = ProductInstance(product_id=prod.id, customer_id=cust.id, serial_number="SN-NEW-01", purchase_date=date(2025, 1, 1), warranty_end_date=date(2027, 1, 1), status="ACTIVE")
        inst5 = ProductInstance(product_id=prod.id, customer_id=cust.id, serial_number="SN-NEW-02", purchase_date=date(2025, 1, 1), warranty_end_date=date(2027, 1, 1), status="ACTIVE")
        inst6 = ProductInstance(product_id=prod.id, customer_id=cust.id, serial_number="SN-OLD-06", purchase_date=date(2025, 1, 1), warranty_end_date=date(2027, 1, 1), status="ACTIVE")
        inst7 = ProductInstance(product_id=prod.id, customer_id=cust.id, serial_number="SN-OLD-07", purchase_date=date(2025, 1, 1), warranty_end_date=date(2027, 1, 1), status="ACTIVE")
        db.add_all([inst1, inst2, inst3, inst4, inst5, inst6, inst7])
        db.commit()

        # 2. Tạo DỮ LIỆU CŨ và MỚI bằng raw SQL (đáp ứng đúng dữ liệu trước và sau tái cấu trúc)
        with engine.begin() as conn:
            conn.execute(text("PRAGMA ignore_check_constraints = ON;"))
            # Phiếu cũ 1: WAITING_RETURN có lịch sử chuyển bước -> Phải sang COMPLETED, completed_at lấy từ lịch sử
            conn.execute(text("""
                INSERT INTO warranty_tickets (
                    ticket_code, product_instance_id, customer_id, service_center_id, created_by,
                    issue_description, status, created_at, repair_at
                ) VALUES (
                    'TK-OLD-WAITING-01', 1, 1, 1, 2, 'Lỗi cũ 1 có lịch sử', 'WAITING_RETURN',
                    '2026-01-10 08:00:00', '2026-01-11 14:00:00'
                )
            """))
            # Phiếu cũ 1b: WAITING_RETURN THIẾU bằng chứng lịch sử -> Phải sang COMPLETED, completed_at giữ NULL
            conn.execute(text("""
                INSERT INTO warranty_tickets (
                    ticket_code, product_instance_id, customer_id, service_center_id, created_by,
                    issue_description, status, created_at, repair_at
                ) VALUES (
                    'TK-OLD-WAITING-NOHIST', 6, 1, 1, 2, 'Lỗi cũ thiếu lịch sử', 'WAITING_RETURN',
                    '2026-01-10 08:00:00', '2026-01-11 14:30:00'
                )
            """))
            # Phiếu cũ 1c: Đã migration trước đó bị điền ép completed_at = repair_at không có lịch sử -> Phải làm sạch về NULL
            conn.execute(text("""
                INSERT INTO warranty_tickets (
                    ticket_code, product_instance_id, customer_id, service_center_id, created_by,
                    issue_description, status, created_at, repair_at, completed_at
                ) VALUES (
                    'TK-OLD-MIGRATED-FAKE', 7, 1, 1, 2, 'Phiếu migration cũ bị ép completed_at', 'COMPLETED',
                    '2026-01-10 08:00:00', '2026-01-11 12:00:00', '2026-01-11 12:00:00'
                )
            """))
            # Phiếu cũ 2: COMPLETED cũ có handed_over_at -> Phải chuyển sang RETURNED, resolution='COMPLETED'
            conn.execute(text("""
                INSERT INTO warranty_tickets (
                    ticket_code, product_instance_id, customer_id, service_center_id, created_by,
                    issue_description, status, created_at, handed_over_at
                ) VALUES (
                    'TK-OLD-COMPLETED-02', 2, 1, 1, 2, 'Lỗi cũ 2 đã trả máy', 'COMPLETED',
                    '2026-01-12 09:00:00', '2026-01-13 16:00:00'
                )
            """))
            # Phiếu cũ 3: REJECTED cũ có handed_over_at -> Phải chuyển sang RETURNED, resolution='REJECTED'
            conn.execute(text("""
                INSERT INTO warranty_tickets (
                    ticket_code, product_instance_id, customer_id, service_center_id, created_by,
                    issue_description, status, rejection_reason, created_at, handed_over_at
                ) VALUES (
                    'TK-OLD-REJECT-03', 3, 1, 1, 2, 'Lỗi cũ 3 từ chối đã trả máy', 'REJECTED',
                    'Hết hạn bảo hành', '2026-01-14 09:00:00', '2026-01-15 11:00:00'
                )
            """))
            # Phiếu mới 1: Đã chuẩn hóa RETURNED với resolution='COMPLETED'
            conn.execute(text("""
                INSERT INTO warranty_tickets (
                    ticket_code, product_instance_id, customer_id, service_center_id, created_by,
                    issue_description, status, resolution, is_warranty_eligible, diagnosis_note,
                    repair_content, handover_note, created_at, diagnosis_at, repair_at, completed_at,
                    handed_over_at, assigned_technician_id, assigned_at
                ) VALUES (
                    'TK-NEW-RETURNED-01', 4, 1, 1, 2, 'Lỗi mới sửa xong', 'RETURNED', 'COMPLETED', 1,
                    'Lỗi IC', 'Đã thay IC', 'Khách đã nhận', '2026-05-01 10:00:00', '2026-05-01 11:00:00',
                    '2026-05-01 14:00:00', '2026-05-02 09:00:00', '2026-05-02 16:00:00', 3, '2026-05-01 10:30:00'
                )
            """))
            # Phiếu mới 2: Đang ở INSPECTING
            conn.execute(text("""
                INSERT INTO warranty_tickets (
                    ticket_code, product_instance_id, customer_id, service_center_id, created_by,
                    issue_description, status, created_at, assigned_technician_id, assigned_at
                ) VALUES (
                    'TK-NEW-INSPECTING-02', 5, 1, 1, 2, 'Lỗi mới đang kiểm tra', 'INSPECTING',
                    '2026-05-03 08:00:00', 3, '2026-05-03 08:30:00'
                )
            """))
            # Lịch sử cũ có chứa WAITING_RETURN cho Phiếu 1 -> Phải được đổi sang COMPLETED
            conn.execute(text("""
                INSERT INTO ticket_status_history (ticket_id, from_status, to_status, changed_by, note, created_at)
                VALUES (1, 'REPAIRING', 'WAITING_RETURN', 3, 'Xong chuyển chờ trả', '2026-01-11 15:00:00')
            """))
            # Lịch sử mới
            conn.execute(text("""
                INSERT INTO ticket_status_history (ticket_id, from_status, to_status, changed_by, note, created_at)
                VALUES (4, 'RECEIVED', 'INSPECTING', 3, 'KTV nhận máy', '2026-05-01 11:00:00')
            """))
            conn.execute(text("PRAGMA ignore_check_constraints = OFF;"))

        print("[+] Đã khởi tạo CSDL tạm thành công:")
        print("    - 5 phiếu dữ liệu kiểu CŨ (WAITING_RETURN có lịch sử, WAITING_RETURN thiếu lịch sử, COMPLETED gán ép, COMPLETED trả máy, REJECTED trả máy)")
        print("    - 2 phiếu dữ liệu kiểu MỚI (RETURNED và INSPECTING)")
        print("    - Lịch sử trạng thái cũ và mới")

        # -------------------------------------------------------------
        # BƯỚC 1: CHẠY MIGRATION LẦN 1
        # -------------------------------------------------------------
        print("\n--- CHẠY MIGRATION LẦN 1 ---")
        ensure_schema_upgrades(engine)
        migrate_tickets_data(engine)
        print("[+] Migration lần 1 hoàn tất.")

        # CHỤP SNAPSHOT 1
        snapshot_1 = build_snapshot(engine)
        print(f"[+] Snapshot 1: {snapshot_1['ticket_count']} phiếu, {snapshot_1['history_count']} bản ghi lịch sử.")
        
        t_old1_s1 = next(t for t in snapshot_1["tickets"] if t["ticket_code"] == "TK-OLD-WAITING-01")
        print(f"    - Phiếu cũ TK-OLD-WAITING-01 sau lần 1: status={t_old1_s1['status']}, completed_at={t_old1_s1['completed_at']}")
        assert t_old1_s1["status"] == "COMPLETED", "Phiếu cũ WAITING_RETURN phải được map sang COMPLETED"
        assert t_old1_s1["completed_at"] == "2026-01-11 15:00:00", "completed_at phải được lấy từ bằng chứng lịch sử (15:00), không lấy ngày bắt đầu sửa repair_at (14:00)"

        t_nohist_s1 = next(t for t in snapshot_1["tickets"] if t["ticket_code"] == "TK-OLD-WAITING-NOHIST")
        print(f"    - Phiếu cũ thiếu lịch sử TK-OLD-WAITING-NOHIST: status={t_nohist_s1['status']}, completed_at={t_nohist_s1['completed_at']}")
        assert t_nohist_s1["status"] == "COMPLETED", "Phiếu phải chuyển sang COMPLETED"
        assert t_nohist_s1["completed_at"] is None, "Phiếu thiếu bằng chứng lịch sử PHẢI giữ completed_at = NULL, không được bịa thời gian hay lấy repair_at"

        t_fake_s1 = next(t for t in snapshot_1["tickets"] if t["ticket_code"] == "TK-OLD-MIGRATED-FAKE")
        print(f"    - Phiếu migration cũ TK-OLD-MIGRATED-FAKE: status={t_fake_s1['status']}, completed_at={t_fake_s1['completed_at']}")
        assert t_fake_s1["completed_at"] is None, "Phiếu đã migration trước đó bị điền ép từ repair_at phải được làm sạch về NULL"

        t_old2_s1 = next(t for t in snapshot_1["tickets"] if t["ticket_code"] == "TK-OLD-COMPLETED-02")
        print(f"    - Phiếu cũ TK-OLD-COMPLETED-02 sau lần 1: status={t_old2_s1['status']}, resolution={t_old2_s1['resolution']}")
        assert t_old2_s1["status"] == "RETURNED", "Phiếu COMPLETED cũ có handed_over_at phải sang RETURNED"
        assert t_old2_s1["resolution"] == "COMPLETED", "resolution phải là COMPLETED"

        t_old3_s1 = next(t for t in snapshot_1["tickets"] if t["ticket_code"] == "TK-OLD-REJECT-03")
        print(f"    - Phiếu cũ TK-OLD-REJECT-03 sau lần 1: status={t_old3_s1['status']}, resolution={t_old3_s1['resolution']}")
        assert t_old3_s1["status"] == "RETURNED", "Phiếu REJECTED cũ có handed_over_at phải sang RETURNED"
        assert t_old3_s1["resolution"] == "REJECTED", "resolution phải là REJECTED"

        t_new1_s1 = next(t for t in snapshot_1["tickets"] if t["ticket_code"] == "TK-NEW-RETURNED-01")
        print(f"    - Phiếu mới TK-NEW-RETURNED-01 sau lần 1: status={t_new1_s1['status']}, resolution={t_new1_s1['resolution']}, handed_over_at={t_new1_s1['handed_over_at']}")

        # -------------------------------------------------------------
        # BƯỚC 2: CHẠY MIGRATION LẦN 2
        # -------------------------------------------------------------
        print("\n--- CHẠY MIGRATION LẦN 2 TRÊN CÙNG DATABASE ---")
        ensure_schema_upgrades(engine)
        migrate_tickets_data(engine)
        print("[+] Migration lần 2 hoàn tất.")

        # CHỤP SNAPSHOT 2
        snapshot_2 = build_snapshot(engine)
        print(f"[+] Snapshot 2: {snapshot_2['ticket_count']} phiếu, {snapshot_2['history_count']} bản ghi lịch sử.")

        # -------------------------------------------------------------
        # BƯỚC 3: SO SÁNH ĐỐI CHIẾU TUYỆT ĐỐI (SNAPSHOT 1 vs SNAPSHOT 2)
        # -------------------------------------------------------------
        print("\n--- KẾT QUẢ SO SÁNH ĐỐI CHIẾU SNAPSHOT 1 VÀ SNAPSHOT 2 ---")
        
        # 1. So sánh số lượng phiếu và số lượng lịch sử
        count_match = (snapshot_1["ticket_count"] == snapshot_2["ticket_count"]) and (snapshot_1["history_count"] == snapshot_2["history_count"])
        print(f"  [1] Số lượng phiếu và bản ghi lịch sử: {'100% KHỚP' if count_match else 'KHÁC NHAU'}")
        print(f"      - Phiếu: {snapshot_1['ticket_count']} == {snapshot_2['ticket_count']}")
        print(f"      - Lịch sử: {snapshot_1['history_count']} == {snapshot_2['history_count']}")

        # 2. So sánh trạng thái (status) của từng phiếu
        status_mismatches = []
        for t1, t2 in zip(snapshot_1["tickets"], snapshot_2["tickets"]):
            if t1["status"] != t2["status"]:
                status_mismatches.append((t1["ticket_code"], t1["status"], t2["status"]))
        print(f"  [2] Trạng thái (status) của toàn bộ phiếu: {'100% KHÔNG ĐỔI' if not status_mismatches else 'CÓ LỖI'}")

        # 3. So sánh kết quả (resolution, is_warranty_eligible, rejection_reason)
        resolution_mismatches = []
        for t1, t2 in zip(snapshot_1["tickets"], snapshot_2["tickets"]):
            diffs = []
            if t1["resolution"] != t2["resolution"]:
                diffs.append(f"resolution: {t1['resolution']} != {t2['resolution']}")
            if t1["is_warranty_eligible"] != t2["is_warranty_eligible"]:
                diffs.append(f"is_warranty_eligible: {t1['is_warranty_eligible']} != {t2['is_warranty_eligible']}")
            if t1["rejection_reason"] != t2["rejection_reason"]:
                diffs.append(f"rejection_reason: {t1['rejection_reason']} != {t2['rejection_reason']}")
            if diffs:
                resolution_mismatches.append((t1["ticket_code"], diffs))
        print(f"  [3] Kết quả xử lý (resolution & rejection): {'100% KHÔNG ĐỔI' if not resolution_mismatches else 'CÓ LỖI'}")

        # 4. So sánh toàn bộ các mốc thời điểm (*_at)
        time_mismatches = []
        for t1, t2 in zip(snapshot_1["tickets"], snapshot_2["tickets"]):
            diff_times = []
            time_keys = ["created_at", "diagnosis_at", "repair_at", "completed_at", "handed_over_at", "assigned_at"]
            for k in time_keys:
                if t1[k] != t2[k]:
                    diff_times.append(f"{k}: {t1[k]} != {t2[k]}")
            if diff_times:
                time_mismatches.append((t1["ticket_code"], diff_times))
        print(f"  [4] Toàn bộ thời điểm (created_at, completed_at, handed_over_at...): {'100% KHÔNG ĐỔI' if not time_mismatches else 'CÓ LỖI'}")

        # 5. So sánh từng bản ghi lịch sử (ticket_status_history)
        history_mismatches = []
        for h1, h2 in zip(snapshot_1["history"], snapshot_2["history"]):
            if h1 != h2:
                history_mismatches.append((h1["id"], h1, h2))
        print(f"  [5] Toàn bộ bản ghi lịch sử chuyển bước: {'100% NGUYÊN VẸN (KHÔNG ĐỔI, KHÔNG SINH THÊM)' if not history_mismatches else 'CÓ LỖI'}")

        all_passed = (
            count_match
            and not status_mismatches
            and not resolution_mismatches
            and not time_mismatches
            and not history_mismatches
        )

        print("\n" + "=" * 80)
        if all_passed:
            print("  >>> XÁC NHẬN MINH CHỨNG: MIGRATION ĐẠT TÍNH CHẤT IDEMPOTENCY TUYỆT ĐỐI! <<<")
            print("      Lần chạy thứ hai không làm thay đổi bất kỳ trạng thái, kết quả, thời điểm")
            print("      hoặc lịch sử đã chuyển đổi của cả dữ liệu cũ và dữ liệu mới.")
            print("=" * 80)
            return True
        else:
            print("  >>> THẤT BẠI: Phát hiện sai lệch giữa hai lần chạy migration! <<<")
            print("=" * 80)
            return False

    finally:
        try:
            os.remove(temp_path)
        except Exception:
            pass

if __name__ == "__main__":
    ok = run_migration_proof()
    sys.exit(0 if ok else 1)
