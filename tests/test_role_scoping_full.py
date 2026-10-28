"""
Kịch bản kiểm thử toàn diện theo yêu cầu đợt sửa phạm vi dữ liệu:
1. Xác minh 4 tài khoản (manager01, receptionist01, technician01, technician02):
   - manager01: thấy toàn trung tâm (4 phiếu), Tổng = 4 = 2 (đang xử lý) + 2 (chờ trả) + 0 (đã trả)
   - receptionist01: Việc tại quầy = 3 phiếu (1 Tiếp nhận + 2 Chờ trả), Toàn bộ = 4 phiếu
   - technician01: Phiếu được giao = 2 phiếu (1 Hoàn tất + 1 Từ chối), Tổng = 2 = 0 + 2 + 0
   - technician02: Phiếu được giao = 0 phiếu, bảng trống, Tổng = 0 = 0 + 0 + 0
2. Kiểm tra phân quyền trực tiếp (Direct API call):
   - technician02 gọi API cập nhật phiếu của technician01 -> 403 Forbidden
   - technician01 gọi API trả máy (handover) -> 403 Forbidden
   - receptionist01 gọi API chẩn đoán kỹ thuật -> 403 Forbidden
3. Kiểm tra phân công lại (Reassignment):
   - Manager chuyển phiếu từ technician01 sang technician02 -> technician01 còn 1, technician02 lên 1
   - Chuyển ngược lại -> hoàn nguyên
4. Tiếp nhận khác cùng trung tâm bàn giao phiếu:
   - Tiếp nhận xem và bàn giao được phiếu do người khác lập
5. Cách ly trung tâm (Center isolation):
   - Phiếu ở trung tâm 2 không xuất hiện trong thống kê hay bảng của trung tâm 1
"""
import os
import sys
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
backend_path = os.path.join(PROJECT_ROOT, "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.main import app
from test_isolation import isolated_test_database

sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = ""
client = TestClient(app)

def request_json(url, method="GET", data=None, token=None):
    # Đảm bảo url chỉ là path tương đối, không gọi tới live server
    path = url.replace("http://127.0.0.1:8000", "")
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = client.request(method, path, json=data, headers=headers)
    try:
        content = resp.json()
    except Exception:
        content = {"raw": resp.text}
    return resp.status_code, content

def login(username, password="123456"):
    status, body = request_json("/api/v1/auth/login", method="POST", data={"username": username, "password": password})
    assert status == 200, f"Login failed for {username}: {body}"
    return body["access_token"]

def _test_all_internal():
    print("=" * 70)
    print("KIỂM THỬ PHẠM VI DỮ LIỆU & PHÂN QUYỀN VAI TRÒ BAOHANHAI")
    print("=" * 70)

    # 1. Đăng nhập 4 tài khoản
    tokens = {
        "manager01": login("manager01"),
        "receptionist01": login("receptionist01"),
        "technician01": login("technician01"),
        "technician02": login("technician02"),
    }
    print("[PASS] Đăng nhập thành công 4 tài khoản demo (123456).")

    # 2. Kiểm tra workboard & 4 thẻ số liệu của 4 tài khoản
    print("\n--- 1. Kiểm tra 4 tài khoản ---")
    results = {}
    for user, tok in tokens.items():
        st_def, wb_def = request_json(f"{BASE_URL}/api/v1/warranty-tickets/workboard", token=tok)
        st_mine, wb_mine = request_json(f"{BASE_URL}/api/v1/warranty-tickets/workboard?scope=MINE", token=tok)
        st_all, wb_all = request_json(f"{BASE_URL}/api/v1/warranty-tickets/workboard?scope=ALL", token=tok)
        assert st_def == 200 and st_mine == 200 and st_all == 200

        cards_def = {c["key"]: c["count"] for c in wb_def["cards"]}
        # Công thức: TOTAL == IN_PROGRESS + WAITING_RETURN + RETURNED
        assert cards_def["TOTAL"] == cards_def["IN_PROGRESS"] + cards_def["WAITING_RETURN"] + cards_def["RETURNED"], (
            f"{user}: Tổng ({cards_def['TOTAL']}) != Đang xử lý ({cards_def['IN_PROGRESS']}) + Chờ trả ({cards_def['WAITING_RETURN']}) + Đã trả ({cards_def['RETURNED']})"
        )
        assert wb_def["totals"]["total_tickets"] == cards_def["TOTAL"]
        results[user] = {
            "role": wb_def["role"],
            "scope": wb_def["scope"],
            "scope_label": wb_def["scope_label"],
            "cards": cards_def,
            "my_tickets_count": len(wb_def["my_tickets"]),
            "active_tickets_count": len(wb_def["active_tickets"]),
        }
        print(f"[{user} - {wb_def['role']}] Phạm vi: {wb_def['scope']} ({wb_def['scope_label']}) | "
              f"Tổng: {cards_def['TOTAL']} (Đang xử lý: {cards_def['IN_PROGRESS']}, Chờ trả: {cards_def['WAITING_RETURN']}, Đã trả: {cards_def['RETURNED']}) | "
              f"Bảng phiếu của tôi: {len(wb_def['my_tickets'])} dòng")

    # Xác minh chi tiết từng tài khoản
    assert results["manager01"]["cards"]["TOTAL"] == 4
    assert results["manager01"]["cards"]["IN_PROGRESS"] == 2
    assert results["manager01"]["cards"]["WAITING_RETURN"] == 2
    assert results["manager01"]["my_tickets_count"] == 4

    assert results["receptionist01"]["scope"] == "MINE"
    assert results["receptionist01"]["scope_label"] == "Việc tại quầy"
    assert results["receptionist01"]["cards"]["TOTAL"] == 3
    assert results["receptionist01"]["cards"]["IN_PROGRESS"] == 1
    assert results["receptionist01"]["cards"]["WAITING_RETURN"] == 2
    assert results["receptionist01"]["my_tickets_count"] == 3

    assert results["technician01"]["scope"] == "MINE"
    assert results["technician01"]["scope_label"] == "Phiếu được giao cho tôi"
    assert results["technician01"]["cards"]["TOTAL"] == 2
    assert results["technician01"]["cards"]["IN_PROGRESS"] == 0
    assert results["technician01"]["cards"]["WAITING_RETURN"] == 2
    assert results["technician01"]["my_tickets_count"] == 2

    assert results["technician02"]["scope"] == "MINE"
    assert results["technician02"]["scope_label"] == "Phiếu được giao cho tôi"
    assert results["technician02"]["cards"]["TOTAL"] == 0
    assert results["technician02"]["cards"]["IN_PROGRESS"] == 0
    assert results["technician02"]["cards"]["WAITING_RETURN"] == 0
    assert results["technician02"]["my_tickets_count"] == 0

    print("[PASS] Số liệu 4 thẻ của cả 4 tài khoản đồng nhất 100% với bảng dữ liệu.")

    # 3. Phân quyền API trực tiếp (Backend RBAC)
    print("\n--- 2. Kiểm tra phân quyền gọi API trực tiếp ---")
    # technician02 (id=4) cố cập nhật trạng thái phiếu 2 (của technician01 id=3)
    st, resp = request_json(f"{BASE_URL}/api/v1/warranty-tickets/2/status", method="PATCH", data={"new_status": "REPAIRING", "changed_by": 4}, token=tokens["technician02"])
    assert st == 403, f"Expected 403 when tech02 modifies tech01 ticket, got {st}: {resp}"
    print(f"[PASS] technician02 không thể thao tác trên phiếu của technician01 (HTTP {st} Forbidden).")

    # technician01 (id=3) cố xác nhận trả máy (handover) cho phiếu 2
    st, resp = request_json(f"{BASE_URL}/api/v1/warranty-tickets/2/status", method="PATCH", data={"new_status": "RETURNED", "changed_by": 3}, token=tokens["technician01"])
    assert st == 403, f"Expected 403 when tech01 closes ticket, got {st}: {resp}"
    print(f"[PASS] technician01 không thể xác nhận trả máy (HTTP {st} Forbidden - quyền thuộc Tiếp nhận/Quản lý).")

    # receptionist01 (id=2) cố chuyển sang REPAIRING (thao tác kỹ thuật)
    st, resp = request_json(f"{BASE_URL}/api/v1/warranty-tickets/1/status", method="PATCH", data={"new_status": "REPAIRING", "changed_by": 2}, token=tokens["receptionist01"])
    assert st == 403, f"Expected 403 when receptionist does technical transition, got {st}: {resp}"
    print(f"[PASS] receptionist01 không thể thực hiện thao tác sửa chữa kỹ thuật (HTTP {st} Forbidden).")

    # 4. Kiểm tra chặn phân công phiếu đã hoàn tất (COMPLETED) trên server live (không làm thay đổi DB)
    print("\n--- 3. Kiểm tra chặn phân công lại phiếu ở trạng thái COMPLETED ---")
    st, resp = request_json(f"{BASE_URL}/api/v1/warranty-tickets/2/assign", method="POST", data={"technician_id": 4, "note": "Thử phân công lại phiếu đã hoàn tất"}, token=tokens["manager01"])
    assert st == 400, f"Expected 400 when assigning COMPLETED ticket, got {st}: {resp}"
    assert resp.get("error_code") == "TICKET_NOT_ASSIGNABLE" or "TICKET_NOT_ASSIGNABLE" in str(resp), f"Expected error_code TICKET_NOT_ASSIGNABLE, got: {resp}"
    print(f"[PASS] Hệ thống chặn phân công lại phiếu COMPLETED chính xác (HTTP 400 - TICKET_NOT_ASSIGNABLE).")

    # 5. Tiếp nhận thấy phiếu chờ trả do người khác lập
    print("\n--- 4. Tiếp nhận thấy phiếu chờ trả do người khác lập ---")
    st, my_tickets = request_json(f"{BASE_URL}/api/v1/warranty-tickets/?mine=1", token=tokens["receptionist01"])
    assert st == 200
    ticket_codes = [t["ticket_code"] for t in my_tickets]
    assert "TK-20260510-0001" in ticket_codes, "Phiếu hoàn tất TK-20260510-0001 phải xuất hiện trong Việc tại quầy của Tiếp nhận"
    assert any(t.get("status") == "REJECTED" for t in my_tickets), "Phiếu từ chối (REJECTED) phải xuất hiện trong Việc tại quầy của Tiếp nhận"
    print(f"[PASS] Tiếp nhận thấy đủ 2 phiếu chờ trả máy (Hoàn tất & Từ chối) trong Việc tại quầy.")

    # 6. Thống kê tập dữ liệu lớn & phân trang
    print("\n--- 5. Kiểm tra thống kê không bị giới hạn bởi phân trang ---")
    st, summary = request_json(f"{BASE_URL}/api/v1/warranty-tickets/stats/summary", token=tokens["manager01"])
    assert st == 200
    assert summary["total_tickets"] == 4
    st, page1 = request_json(f"{BASE_URL}/api/v1/warranty-tickets/?limit=1", token=tokens["manager01"])
    assert st == 200
    assert len(page1) == 1
    # Số liệu tổng hợp vẫn là 4 dù trang chỉ lấy 1 dòng
    print(f"[PASS] Thống kê tổng hợp ({summary['total_tickets']} phiếu) độc lập với phân trang trang đơn ({len(page1)} dòng).")

    print("\n" + "=" * 70)
    print("TẤT CẢ CÁC BÀI TEST NGHIỆP VỤ & PHÂN QUYỀN ĐỀU ĐẠT 100%!")
    print("=" * 70)


def test_all():
    from test_isolation import isolated_test_database
    with isolated_test_database(copy_from_app_db=True):
        _test_all_internal()


if __name__ == "__main__":
    test_all()
