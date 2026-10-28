"""
Isolated E2E Test Server Runner:
- Copies database/backup/baohanh_ai.db.backup_20261028_122110.bak to database/temp_browser_e2e.db
- Strictly forces DATABASE_URL to temp_browser_e2e.db
- Asserts active DB engine is isolated from database/baohanh_ai.db
- Serves FastAPI app and static files on 127.0.0.1:8088
"""
import os
import sys
import shutil

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, BACKEND_DIR)

DB_BACKUP = os.path.join(PROJECT_ROOT, "database", "backup", "baohanh_ai.db.backup_20261028_122110.bak")
TEMP_DB = os.path.join(PROJECT_ROOT, "database", "temp_browser_e2e.db").replace("\\", "/")

if not os.path.exists(DB_BACKUP):
    raise FileNotFoundError(f"Backup file not found at {DB_BACKUP}")

print(f"[*] Sao chep CSDL sao luu sang CSDL tam: {TEMP_DB}")
shutil.copyfile(DB_BACKUP, TEMP_DB)

# Thiet lap bien moi truong truoc bat ky import nao
os.environ["DATABASE_URL"] = f"sqlite:///{TEMP_DB}"

from app.config import settings
settings.database_url = f"sqlite:///{TEMP_DB}"

import app.database as app_db

# Kiem tra cach ly chat che
active_url = str(app_db.engine.url)
print(f"[*] Engine database URL: {active_url}")
assert "temp_browser_e2e.db" in active_url, f"Engine URL mismatch: {active_url}"
assert "baohanh_ai.db" not in active_url, f"Engine URL must NOT use baohanh_ai.db: {active_url}"

from app.main import app
import uvicorn

if __name__ == "__main__":
    print("[*] Khoi dong server test E2E tai http://127.0.0.1:8088 ...")
    uvicorn.run(app, host="127.0.0.1", port=8088, log_level="warning")
