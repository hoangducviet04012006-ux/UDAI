from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

db_url = settings.database_url
connect_args = {}
if db_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    db_url,
    connect_args=connect_args,
    echo=False
)

# =====================================================================
# [AUD-10] Bật thực thi khoá ngoại (FOREIGN KEY) cho SQLite.
# ---------------------------------------------------------------------
# SQLite mặc định KHÔNG thực thi FK nên dữ liệu có FK "ảo" vẫn lọt vào DB
# (audit đã chứng minh: service_center_id / created_by / changed_by = 999999).
# Pragma được set cho MỖI connection mới của SQLite.
# - Chỉ áp dụng khi DATABASE_URL là SQLite => KHÔNG ảnh hưởng PostgreSQL.
# - KHÔNG thay đổi schema, KHÔNG xoá/sửa bất kỳ FK nào đang khai báo.
# =====================================================================
if db_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
