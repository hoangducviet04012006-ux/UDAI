"""
[Đợt hoàn thiện nghiệp vụ phiếu] Nâng cấp cấu trúc bảng KHÔNG MẤT DỮ LIỆU.

Vấn đề: `Base.metadata.create_all()` chỉ tạo bảng còn THIẾU, không thêm cột vào
bảng đã tồn tại. Hai tệp CSDL demo/sản phẩm vì vậy có thể đang thiếu các cột
nghiệp vụ mới của phiếu bảo hành (chẩn đoán / sửa chữa / bàn giao).

Giải pháp: quét cột thực tế của `warranty_tickets` rồi chỉ chạy
`ALTER TABLE ... ADD COLUMN` cho các cột còn thiếu.

Nguyên tắc an toàn:
    * CHỈ THÊM cột - KHÔNG sửa, KHÔNG xoá, KHÔNG đổi kiểu cột cũ.
    * Mọi cột mới đều cho phép NULL -> các dòng dữ liệu hiện có vẫn hợp lệ.
    * Chạy lại nhiều lần không gây lỗi (idempotent).
    * Không hỗ trợ MySQL (đồ án dùng SQLite mặc định, PostgreSQL là tùy chọn).
"""
import logging
from typing import List, Tuple

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("baohanhai.schema_migration")

TABLE = "warranty_tickets"

# (tên cột, định nghĩa kiểu) - cú pháp dùng chung cho cả SQLite và PostgreSQL.
# SQLite cho phép mệnh đề REFERENCES + ON DELETE ngay sau khi ADD COLUMN.
WORKFLOW_COLUMNS: List[Tuple[str, str]] = [
    ("diagnosis_note", "TEXT"),
    ("diagnosis_by", "BIGINT REFERENCES users(id) ON DELETE SET NULL"),
    ("diagnosis_at", "TIMESTAMP"),
    ("repair_content", "TEXT"),
    ("repair_parts", "TEXT"),
    ("repair_note", "TEXT"),
    ("repair_by", "BIGINT REFERENCES users(id) ON DELETE SET NULL"),
    ("repair_at", "TIMESTAMP"),
    ("handed_over_by", "BIGINT REFERENCES users(id) ON DELETE SET NULL"),
    ("handover_note", "TEXT"),
]


def ensure_schema_upgrades(engine: Engine) -> List[str]:
    """
    Bổ sung các cột nghiệp vụ phiếu còn thiếu trong CSDL hiện tại.

    Trả về danh sách tên cột vừa được thêm (rỗng = CSDL đã đầy đủ).
    Không bao giờ ném ngoại lệ ra ngoài: ứng dụng vẫn khởi động được kể cả khi
    CSDL đang ở chế độ chỉ đọc (khi đó chỉ ghi log cảnh báo).
    """
    added: List[str] = []
    try:
        inspector = inspect(engine)
        if TABLE not in inspector.get_table_names():
            # Bảng chưa tồn tại (create_all sẽ tạo đủ cột) -> không cần nâng cấp.
            return added
        existing = {col["name"] for col in inspector.get_columns(TABLE)}
    except Exception as exc:  # pragma: no cover - phòng khi CSDL không truy cập được
        logger.warning("Không đọc được cấu trúc bảng %s: %s", TABLE, exc)
        return added

    for column_name, column_type in WORKFLOW_COLUMNS:
        if column_name in existing:
            continue
        statement = f"ALTER TABLE {TABLE} ADD COLUMN {column_name} {column_type}"
        try:
            with engine.begin() as connection:
                connection.execute(text(statement))
            added.append(column_name)
            logger.info("Đã thêm cột %s.%s", TABLE, column_name)
        except Exception as exc:  # pragma: no cover
            logger.warning("Không thêm được cột %s.%s: %s", TABLE, column_name, exc)

    return added
