"""
BaoHanhAI - Trinh khoi dong ung dung tich hop (Application Launcher)
Tu dong kiem tra CSDL, chay migration an toan, kiem tra cong va mo trinh duyet.
"""
import sys
import os
import time
import socket
import threading
import webbrowser
import urllib.request
import json

# Cau hinh console UTF-8 tren Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))
os.chdir(PROJECT_ROOT)

HOST = "127.0.0.1"
PORT = 8000
HEALTH_URL = f"http://{HOST}:{PORT}/health"
APP_URL = f"http://{HOST}:{PORT}/"

def is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0

def check_app_healthy(timeout: float = 1.0) -> bool:
    try:
        req = urllib.request.Request(HEALTH_URL, headers={"User-Agent": "BaoHanhAI-Launcher"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("status") == "healthy"
    except Exception:
        return False
    return False

def open_browser_when_ready():
    start_time = time.time()
    while time.time() - start_time < 15:
        if check_app_healthy(timeout=0.5):
            print("\n" + "=" * 65)
            print(f" [OK] He thong BaoHanhAI da san sang tai: {APP_URL}")
            print(" Dang mo trinh duyet...")
            print("=" * 65)
            try:
                webbrowser.open(APP_URL)
            except Exception:
                pass
            return
        time.sleep(0.3)

def prepare_database():
    """
    Kiem tra CSDL:
    - Neu database moi chua co bang nao: tao bang va nap du lieu mau 1 lan.
    - Neu database da co san: chi chay migration an toan, KHONG reset, KHONG seed lai, KHONG doi mat khau.
    """
    from app.database import engine, SessionLocal, Base
    from app.services.schema_migration import ensure_schema_upgrades
    from app.services.support_schema import backup_before_support_schema
    from sqlalchemy import inspect

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    if not existing_tables or "warranty_tickets" not in existing_tables:
        print("[*] Khoi tao co so du lieu moi va nap du lieu mau khoi tao...")
        Base.metadata.create_all(bind=engine)
        ensure_schema_upgrades(engine)
        from tests.seed_data import seed
        seed()
        print("[+] Da khoi tao CSDL moi va nap du lieu mau thanh cong.")
    else:
        # Database co san -> chi chay migration an toan
        backup_before_support_schema(engine)
        print("[*] Phat hien CSDL hien co, dang chay migration an toan...")
        added = ensure_schema_upgrades(engine)
        if added:
            print(f"[+] Da bo sung cac cot nghiep vu con thieu: {', '.join(added)}")
        else:
            print("[+] Cau truc CSDL da dong bo va day du.")

def main():
    print("=" * 65)
    print("   HE THONG QUAN LY BAO HANH SAN PHAM TICH HOP AI (BAOHANHAI)   ")
    print("=" * 65)

    # 1. Kiem tra cong 8000
    if is_port_in_use(HOST, PORT):
        if check_app_healthy(timeout=1.0):
            print(f"\n[*] Ung dung BaoHanhAI dang hoat dong tai {APP_URL}")
            print("    Dang mo trinh duyet web...")
            webbrowser.open(APP_URL)
            print("\n[OK] Da mo ung dung trong trinh duyet.")
            sys.exit(0)
        else:
            print(f"\n[CANH BAO] Cong {PORT} dang bi mot ung dung khac chiem giu!")
            print(f"He thong khong tu y tat tien trinh khac.")
            print(f"Vui long dong ung dung dang dung cong {PORT} hoac doi cong trong cau hinh.")
            sys.exit(1)

    # 2. Chuan bi CSDL
    try:
        prepare_database()
    except Exception as exc:
        print(f"\n[-] Loi kiem tra/chuan bi CSDL: {exc}")
        sys.exit(1)

    # 3. Hen gio mo trinh duyet khi server khoi dong xong
    threading.Thread(target=open_browser_when_ready, daemon=True).start()

    # 4. In huong dan dang nhap
    print("\n[*] TAI KHOAN DEMO KHOI TAO:")
    print("    - Quan ly       : manager01      | Mat khau: 123456 (Hoang Duc Viet)")
    print("    - Tiep nhan     : receptionist01 | Mat khau: 123456 (Nguyen Thu Ha)")
    print("    - Ky thuat vien : technician01   | Mat khau: 123456 (Tran Minh Tuan)")
    print("    - Ky thuat vien : technician02   | Mat khau: 123456 (Le Quoc Huy)")
    print("\n[*] Dang khoi dong may chu web tai: " + APP_URL)
    print("    (Nhan Ctrl+C de dung may chu)\n")

    # 5. Khoi dong uvicorn
    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True, log_level="info")

if __name__ == "__main__":
    main()
