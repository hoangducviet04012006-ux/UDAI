"""
Mô-đun tiện ích cách ly CSDL hoàn toàn cho các bài kiểm thử (Test Database Isolation).
=====================================================================================
Mục tiêu nghiệp vụ & an toàn:
1. Chặn đứng việc kiểm thử ghi vào CSDL ứng dụng (database/baohanh_ai.db).
2. Tự động phát hiện và TỪ CHỐI CHẠY nếu database đích trùng với database ứng dụng.
3. Điều hướng toàn bộ các tham chiếu đã import engine/SessionLocal trong sys.modules.
4. Chuyển hướng Lifespan của FastAPI app sang CSDL tạm.
5. Cung cấp công cụ chụp và so sánh Snapshot toàn diện (kèm kiểm tra SQLite journal/WAL).
"""
import os
import sys
import shutil
import sqlite3
import hashlib
import json
import tempfile
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Tuple
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
backend_path = os.path.join(PROJECT_ROOT, "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

import app.database as app_db
import app.main as app_main
from app.database import Base, get_db
from app.config import settings

APPLICATION_DB_PATH = os.path.normcase(os.path.abspath(os.path.join(PROJECT_ROOT, "database", "baohanh_ai.db")))


def normalize_sqlite_path(path_or_url: str) -> str:
    """Chuẩn hóa URL hoặc đường dẫn SQLite thành đường dẫn tuyệt đối chuẩn."""
    if not path_or_url:
        return ""
    clean = str(path_or_url).strip()
    if clean.startswith("sqlite:///"):
        clean = clean[10:]
    elif clean.startswith("sqlite://"):
        clean = clean[9:]
    clean = clean.split("?")[0]
    if clean in (":memory:", ""):
        return ":memory:"
    return os.path.normcase(os.path.abspath(clean))


def assert_not_application_database(path_or_url: str) -> None:
    """
    RÀNG BUỘC AN TOÀN: Test phải TỪ CHỐI CHẠY nếu database đích trùng database ứng dụng.
    """
    normalized = normalize_sqlite_path(path_or_url)
    if normalized == APPLICATION_DB_PATH:
        raise RuntimeError(
            f"\n{'='*75}\n"
            f"[BẢO VỆ CSDL ỨNG DỤNG - TEST BỊ TỪ CHỐI CHẠY!]\n"
            f"Phát hiện test đang cố gắng kết nối hoặc ghi vào CSDL thật của ứng dụng:\n"
            f"  Đích kết nối: {normalized}\n"
            f"  CSDL ứng dụng: {APPLICATION_DB_PATH}\n"
            f"Quy tắc an toàn: Mọi kiểm thử BẮT BUỘC phải chạy trên CSDL tạm riêng biệt.\n"
            f"{'='*75}\n"
        )


def _patch_sys_modules(old_engine, old_session_local, new_engine, new_session_local) -> List[Tuple[Any, str, Any]]:
    """
    Quét toàn bộ sys.modules để thay thế các biến engine / SessionLocal đã import theo cú pháp:
    `from app.database import engine, SessionLocal`
    Trả về danh sách các vị trí đã thay đổi để hoàn nguyên khi test kết thúc.
    """
    restorations = []
    for mod_name, mod in list(sys.modules.items()):
        if not mod:
            continue
        # Chỉ quét các module thuộc dự án (app, tests, seed_data)
        if mod_name.startswith("app") or mod_name.startswith("tests") or mod_name == "seed_data":
            try:
                mod_dict = getattr(mod, "__dict__", None)
                if not isinstance(mod_dict, dict):
                    continue
                for attr_name in ("engine", "test_engine", "wf_engine"):
                    if attr_name in mod_dict and mod_dict[attr_name] is old_engine:
                        mod_dict[attr_name] = new_engine
                        restorations.append((mod_dict, attr_name, old_engine))
                for attr_name in ("SessionLocal", "TestingSessionLocal", "TestSessionLocal", "WfSessionLocal", "Kt3SessionLocal"):
                    if attr_name in mod_dict and mod_dict[attr_name] is old_session_local:
                        mod_dict[attr_name] = new_session_local
                        restorations.append((mod_dict, attr_name, old_session_local))
            except Exception:
                pass
    return restorations


@contextmanager
def isolated_test_database(
    db_path: str = None,
    copy_from_app_db: bool = False
) -> Generator[Tuple[any, any, str], None, None]:
    """
    Context manager cách ly 100% CSDL cho bài kiểm thử:
    - db_path: Đường dẫn CSDL tạm thời (nếu None -> tạo file tạm trong tempdir).
    - copy_from_app_db: Nếu True -> sao chép dữ liệu hiện có từ baohanh_ai.db sang file tạm.
    """
    temp_dir = None
    if db_path is None:
        temp_dir = tempfile.mkdtemp(prefix="baohanh_test_iso_")
        target_path = os.path.join(temp_dir, "isolated_test.db")
    else:
        target_path = os.path.abspath(db_path)

    # 1. KIỂM TRA BẢO VỆ CSDL THẬT
    assert_not_application_database(target_path)

    # 2. Chuẩn bị file
    if copy_from_app_db:
        if os.path.exists(target_path):
            try:
                os.remove(target_path)
            except Exception:
                pass
        shutil.copy2(APPLICATION_DB_PATH, target_path)

    target_url = f"sqlite:///{target_path.replace(chr(92), '/')}"

    # 3. Tạo test engine & SessionLocal
    test_engine = create_engine(target_url, connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # 4. Lưu lại cấu hình gốc
    orig_engine = app_db.engine
    orig_session_local = app_db.SessionLocal
    orig_settings_url = settings.database_url
    orig_env_url = os.environ.get("DATABASE_URL")

    # 5. Áp dụng chuyển hướng toàn diện
    os.environ["DATABASE_URL"] = target_url
    try:
        settings.database_url = target_url
    except Exception:
        pass

    app_db.engine = test_engine
    app_db.SessionLocal = TestSessionLocal

    # Quét và điều hướng tất cả tham chiếu đã import sẵn
    restorations = _patch_sys_modules(orig_engine, orig_session_local, test_engine, TestSessionLocal)

    def _override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app_main.app.dependency_overrides[get_db] = _override_get_db

    # Khởi tạo bảng nếu là database mới
    if not copy_from_app_db:
        Base.metadata.create_all(bind=test_engine)

    try:
        yield test_engine, TestSessionLocal, target_path
    finally:
        # 6. Hoàn trả nguyên trạng
        app_main.app.dependency_overrides.pop(get_db, None)
        app_db.engine = orig_engine
        app_db.SessionLocal = orig_session_local

        # Hoàn trả các module trong sys.modules
        for target_dict, attr, old_val in restorations:
            try:
                target_dict[attr] = old_val
            except Exception:
                pass

        try:
            settings.database_url = orig_settings_url
        except Exception:
            pass

        if orig_env_url is not None:
            os.environ["DATABASE_URL"] = orig_env_url
        else:
            os.environ.pop("DATABASE_URL", None)

        test_engine.dispose()
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass


# =====================================================================
# CÔNG CỤ CHỤP VÀ SO SÁNH SNAPSHOT DATABASE (KIỂM CHỨNG TOÀN VẸN)
# =====================================================================
def take_database_snapshot(db_path: str = None) -> Dict[str, Any]:
    """
    Chụp toàn bộ cấu trúc và dữ liệu của file CSDL SQLite:
    - Trạng thái file, kích thước, SHA256 file
    - Trạng thái WAL / journal
    - Toàn bộ bảng, số dòng và nội dung từng bảng
    """
    path = db_path or APPLICATION_DB_PATH
    if not os.path.exists(path):
        return {"exists": False, "path": path}

    # Đọc file hash
    with open(path, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()

    wal_path = path + "-wal"
    shm_path = path + "-shm"
    journal_path = path + "-journal"

    wal_info = {
        "wal_exists": os.path.exists(wal_path),
        "wal_size": os.path.getsize(wal_path) if os.path.exists(wal_path) else 0,
        "shm_exists": os.path.exists(shm_path),
        "journal_exists": os.path.exists(journal_path),
    }

    conn = sqlite3.connect(path)
    c = conn.cursor()
    journal_mode = c.execute("PRAGMA journal_mode").fetchone()[0]

    # Danh sách bảng
    tables = [row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    
    table_data = {}
    table_counts = {}
    for tbl in tables:
        rows = c.execute(f"SELECT * FROM [{tbl}] ORDER BY 1").fetchall()
        table_counts[tbl] = len(rows)
        # Chuyển rows thành chuỗi hash để so sánh
        rows_str = json.dumps([[str(col) for col in row] for row in rows], sort_keys=True)
        table_data[tbl] = {
            "count": len(rows),
            "hash": hashlib.sha256(rows_str.encode("utf-8")).hexdigest(),
            "sample": rows[:5]
        }

    conn.close()

    return {
        "exists": True,
        "path": path,
        "size": os.path.getsize(path),
        "file_sha256": file_hash,
        "journal_mode": journal_mode,
        "wal_info": wal_info,
        "tables": tables,
        "table_counts": table_counts,
        "table_data": table_data,
    }


def compare_database_snapshots(before: Dict[str, Any], after: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    So sánh hai snapshot của CSDL.
    Trả về: (is_identical, diff_explanations)
    """
    diffs = []
    if not before.get("exists") or not after.get("exists"):
        return False, ["Một trong hai snapshot không tồn tại file."]

    if before["file_sha256"] != after["file_sha256"]:
        diffs.append(f"File SHA256 thay đổi: {before['file_sha256'][:10]}... -> {after['file_sha256'][:10]}...")

    if before["size"] != after["size"]:
        diffs.append(f"File size thay đổi: {before['size']} -> {after['size']} bytes")

    # Kiểm tra WAL / journal
    for k in ("wal_exists", "wal_size", "shm_exists", "journal_exists"):
        if before["wal_info"][k] != after["wal_info"][k]:
            diffs.append(f"Trạng thái WAL/journal thay đổi: {k} ({before['wal_info'][k]} -> {after['wal_info'][k]})")

    # So sánh bảng & dữ liệu
    before_tables = set(before["tables"])
    after_tables = set(after["tables"])
    if before_tables != after_tables:
        diffs.append(f"Danh sách bảng thay đổi: thêm {after_tables - before_tables}, mất {before_tables - after_tables}")

    for tbl in before_tables.intersection(after_tables):
        b_cnt = before["table_counts"].get(tbl, 0)
        a_cnt = after["table_counts"].get(tbl, 0)
        if b_cnt != a_cnt:
            diffs.append(f"Bảng [{tbl}]: số dòng thay đổi {b_cnt} -> {a_cnt}")
        elif before["table_data"][tbl]["hash"] != after["table_data"][tbl]["hash"]:
            diffs.append(f"Bảng [{tbl}]: nội dung dữ liệu thay đổi (hash khác nhau dù cùng {b_cnt} dòng)")

    return (len(diffs) == 0), diffs
