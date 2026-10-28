"""
Kiểm thử chuyên sâu: Đơn giản hóa menu Kỹ thuật viên & Sửa lỗi điều hướng 'Tra cứu nội bộ'
Sử dụng CSDL SQLite tạm thời cô lập (tempfile), tuyệt đối không đụng database chính.
"""
import sys
import os
import tempfile
import json

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

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
from app.services import auth_service
from seed_data import DEMO_ACCOUNTS, DEMO_PASSWORDS, seed

from test_isolation import isolated_test_database, assert_not_application_database

def run_tests():
    with isolated_test_database() as (test_engine, TestSessionLocal, temp_db_path):
        assert_not_application_database(temp_db_path)
        db = TestSessionLocal()
        seed(session=db, target_engine=test_engine)

    # Tạo thêm 1 tài khoản KTV mới để chứng minh tính tổng quát theo vai trò (không hardcode username)
    new_tech = User(
        username="ktv_moitao",
        full_name="Kỹ Thuật Viên Mới Tạo",
        role=auth_service.ROLE_TECHNICIAN,
        password_hash=auth_service.hash_password("123456"),
        active=True,
    )
    db.add(new_tech)
    db.commit()

    client = TestClient(app)
    results = []

    def log_test(title, passed, detail=""):
        status = "PASS" if passed else "FAIL"
        results.append((title, status))
        print(f"[{status}] {title}")
        if detail:
            print(f"       -> {detail}")

    print("\n" + "=" * 75)
    print("  KIEM THU MENU THEO VAI TRO VA DIEU HUONG (TEMP DATABASE)")
    print("=" * 75)

    # 1. Kiểm tra menu technician01
    res1 = client.post("/api/v1/auth/login", json={"username": "technician01", "password": "123456"})
    menus_t1 = [m["tab"] for m in res1.json()["user"]["menus"]]
    groups_t1 = [m["group"] for m in res1.json()["user"]["menus"]]
    log_test(
        "KTV technician01 có đúng 4 mục (Tổng quan, Phiếu, Tra cứu, AI) & không có reference",
        menus_t1 == ["dashboard", "tickets", "lookup", "ai"] and "reference" not in groups_t1,
        f"menus={menus_t1}, groups={set(groups_t1)}"
    )

    # 2. Kiểm tra menu technician02
    res2 = client.post("/api/v1/auth/login", json={"username": "technician02", "password": "123456"})
    menus_t2 = [m["tab"] for m in res2.json()["user"]["menus"]]
    log_test(
        "KTV technician02 có đúng 4 mục theo vai trò",
        menus_t2 == ["dashboard", "tickets", "lookup", "ai"],
        f"menus={menus_t2}"
    )

    # 3. Kiểm tra tài khoản KTV tạo mới (ktv_moitao)
    res3 = client.post("/api/v1/auth/login", json={"username": "ktv_moitao", "password": "123456"})
    menus_t3 = [m["tab"] for m in res3.json()["user"]["menus"]]
    log_test(
        "Tài khoản KTV mới tạo 'ktv_moitao' tự động áp dụng đúng 4 mục (không hardcode)",
        menus_t3 == ["dashboard", "tickets", "lookup", "ai"],
        f"menus={menus_t3}"
    )

    # 4. Kiểm tra menu Tiếp nhận (receptionist01): giữ nguyên các mục Khách hàng, Danh mục máy, Máy đã đăng ký
    res_rec = client.post("/api/v1/auth/login", json={"username": "receptionist01", "password": "123456"})
    menus_rec = [m["tab"] for m in res_rec.json()["user"]["menus"]]
    rec_expected = ["dashboard", "tickets", "lookup", "ai", "customers", "products", "devices"]
    log_test(
        "Tiếp nhận giữ nguyên 7 mục (có Khách hàng, Danh mục máy, Máy đã đăng ký)",
        menus_rec == rec_expected,
        f"menus={menus_rec}"
    )

    # 5. Kiểm tra menu Quản lý (manager01): đủ 8 mục bao gồm Tài khoản nhân viên
    res_mgr = client.post("/api/v1/auth/login", json={"username": "manager01", "password": "123456"})
    menus_mgr = [m["tab"] for m in res_mgr.json()["user"]["menus"]]
    mgr_expected = ["dashboard", "tickets", "lookup", "ai", "customers", "products", "devices", "accounts"]
    log_test(
        "Quản lý giữ nguyên đầy đủ 8 mục (có thêm Tài khoản nhân viên)",
        menus_mgr == mgr_expected,
        f"menus={menus_mgr}"
    )

    # 6. Kiểm tra quyền backend của KTV: không bị thu hồi quyền đọc khách, thiết bị, serial
    token_ktv = res1.json()["access_token"]
    headers_ktv = {"Authorization": f"Bearer {token_ktv}"}
    
    # KTV đọc chi tiết thiết bị
    res_dev = client.get("/api/v1/product-instances/1", headers=headers_ktv)
    # KTV tra cứu bảo hành theo serial
    res_lookup = client.get("/api/v1/product-instances/by-serial/SN-ASUS-2026-0001", headers=headers_ktv)
    # KTV đọc chi tiết phiếu
    res_ticket = client.get("/api/v1/warranty-tickets/1", headers=headers_ktv)

    log_test(
        "KTV đọc chi tiết thiết bị, serial, tra cứu và chi tiết phiếu thành công (HTTP 200, không bị 403)",
        res_dev.status_code == 200 and res_lookup.status_code == 200 and res_ticket.status_code == 200,
        f"dev={res_dev.status_code}, lookup={res_lookup.status_code}, ticket={res_ticket.status_code}"
    )

    # KTV không có quyền quản lý tài khoản nhân viên
    res_acc = client.get("/api/v1/users/", headers=headers_ktv)
    log_test(
        "KTV truy cập ngoài quyền (quản trị tài khoản) bị chặn 403",
        res_acc.status_code == 403,
        f"status={res_acc.status_code}"
    )

    print("\n" + "=" * 75)
    total = len(results)
    passed = sum(1 for _, s in results if s == "PASS")
    print(f"  TONG KET BACKEND: {passed}/{total} PASS")
    print("=" * 75)
    return passed == total

if __name__ == "__main__":
    ok = run_tests()
    # Dọn dẹp temp db
    try:
        os.remove(temp_db_path)
    except Exception:
        pass
    sys.exit(0 if ok else 1)
