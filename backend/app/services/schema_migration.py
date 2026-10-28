"""
[Nghiệp vụ phiếu bảo hành tái cấu trúc] Nâng cấp cấu trúc bảng & Chuyển đổi dữ liệu cũ AN TOÀN.

Nguyên tắc:
1. Xác định đúng CSDL ứng dụng đang kết nối.
2. Thêm cột mới idempotent (không xoá/sửa cột cũ, cho phép NULL).
3. Nâng cấp CHECK constraint trên bảng warranty_tickets và ticket_status_history để hỗ trợ 6 trạng thái:
   RECEIVED, INSPECTING, REPAIRING, COMPLETED, REJECTED, RETURNED.
4. Ánh xạ dữ liệu cũ sang mới theo nguyên tắc:
   - WAITING_RETURN -> COMPLETED (sửa xong, chờ khách nhận).
   - COMPLETED cũ:
     + Có handed_over_at -> RETURNED (Đã trả máy), resolution = 'COMPLETED'.
     + Không có handed_over_at -> giữ COMPLETED (Hoàn tất, chờ khách nhận), KHÔNG suy đoán là đã trả máy!
   - REJECTED cũ:
     + Có handed_over_at -> RETURNED (Đã trả máy), resolution = 'REJECTED'.
     + Không có handed_over_at -> giữ REJECTED (Từ chối, chờ trả máy).
5. Quét kiểm tra trùng serial: nếu có > 1 phiếu chưa đóng trên cùng serial -> báo xung đột và giữ nguyên.
6. Tạo partial unique index ngăn chặn request đồng thời tạo trùng phiếu mở.
"""
import logging
from typing import Any, Dict, List, Tuple
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("baohanhai.schema_migration")

TABLE = "warranty_tickets"

# Danh sách cột nghiệp vụ cần có trên warranty_tickets
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
    ("handed_over_at", "TIMESTAMP"),
    ("handover_note", "TEXT"),
    # Cột nghiệp vụ tái cấu trúc mới
    ("assigned_technician_id", "BIGINT REFERENCES users(id) ON DELETE SET NULL"),
    ("assigned_at", "TIMESTAMP"),
    ("is_warranty_eligible", "BOOLEAN"),
    ("warranty_check_note", "TEXT"),
    ("repair_test_passed", "BOOLEAN"),
    ("repair_test_note", "TEXT"),
    ("rejection_proposal_note", "TEXT"),
    ("completed_at", "TIMESTAMP"),
    ("resolution", "VARCHAR(20)"),
    ("device_condition", "TEXT"),
    ("accessories_accompanying", "TEXT"),
]


def ensure_schema_upgrades(engine: Engine) -> List[str]:
    """
    Bổ sung các cột nghiệp vụ phiếu còn thiếu trong CSDL hiện tại.
    Chạy lại nhiều lần an toàn (idempotent).
    """
    added: List[str] = []
    try:
        inspector = inspect(engine)
        if TABLE not in inspector.get_table_names():
            return added
        existing = {col["name"] for col in inspector.get_columns(TABLE)}
    except Exception as exc:
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
        except Exception as exc:
            logger.warning("Không thêm được cột %s.%s: %s", TABLE, column_name, exc)

    # Nâng cấp Check Constraint cho SQLite / PostgreSQL nếu cần
    upgrade_check_constraints(engine)

    # Chuyển đổi dữ liệu cũ sang bộ trạng thái mới
    migrate_tickets_data(engine)

    # Tạo partial unique index ngăn chặn concurrency bug BR3
    ensure_concurrency_index(engine)

    return added


def upgrade_check_constraints(engine: Engine) -> None:
    """Nâng cấp ràng buộc CHECK trên warranty_tickets để chấp nhận 'RETURNED'."""
    dialect_name = engine.dialect.name
    try:
        if dialect_name == "sqlite":
            _upgrade_sqlite_constraints(engine)
        elif dialect_name == "postgresql":
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE warranty_tickets DROP CONSTRAINT IF EXISTS check_ticket_status;"))
                conn.execute(text(
                    "ALTER TABLE warranty_tickets ADD CONSTRAINT check_ticket_status "
                    "CHECK (status IN ('RECEIVED', 'INSPECTING', 'REPAIRING', 'COMPLETED', 'REJECTED', 'RETURNED', 'WAITING_RETURN'));"
                ))
                conn.execute(text(
                    "ALTER TABLE warranty_tickets DROP CONSTRAINT IF EXISTS check_ticket_resolution;"
                ))
                conn.execute(text(
                    "ALTER TABLE warranty_tickets ADD CONSTRAINT check_ticket_resolution "
                    "CHECK (resolution IS NULL OR resolution IN ('COMPLETED', 'REJECTED'));"
                ))
    except Exception as exc:
        logger.warning("Lưu ý khi nâng cấp check constraint: %s", exc)


def _upgrade_sqlite_constraints(engine: Engine) -> None:
    """Nâng cấp bảng SQLite thông qua sao chép nếu constraint cũ không có 'RETURNED'."""
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='warranty_tickets'")
            ).fetchone()
            if not row or not row[0]:
                return
            sql = row[0]
            # Nếu constraint cũ chưa có RETURNED
            if "'RETURNED'" in sql:
                return

        # Nâng cấp bảng bằng quy trình chuẩn SQLite (recreate table)
        logger.info("Đang nâng cấp CHECK constraint bảng warranty_tickets trên SQLite...")
        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF;"))
            conn.execute(text("ALTER TABLE warranty_tickets RENAME TO _old_warranty_tickets;"))
            
            # Tạo bảng mới với định nghĩa đầy đủ hỗ trợ cả trạng thái mới và cũ
            conn.execute(text("""
                CREATE TABLE warranty_tickets (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    ticket_code VARCHAR(30) UNIQUE NOT NULL,
                    product_instance_id BIGINT NOT NULL REFERENCES product_instances(id) ON DELETE RESTRICT,
                    customer_id BIGINT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
                    service_center_id BIGINT NOT NULL REFERENCES service_centers(id) ON DELETE RESTRICT,
                    created_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                    issue_description TEXT NOT NULL,
                    device_condition TEXT,
                    accessories_accompanying TEXT,
                    error_category_id BIGINT REFERENCES error_categories(id) ON DELETE SET NULL,
                    status VARCHAR(20) NOT NULL CHECK (status IN ('RECEIVED', 'INSPECTING', 'REPAIRING', 'COMPLETED', 'REJECTED', 'RETURNED', 'WAITING_RETURN')),
                    assigned_technician_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
                    assigned_at DATETIME,
                    diagnosis_note TEXT,
                    diagnosis_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
                    diagnosis_at DATETIME,
                    is_warranty_eligible BOOLEAN,
                    warranty_check_note TEXT,
                    repair_content TEXT,
                    repair_parts TEXT,
                    repair_note TEXT,
                    repair_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
                    repair_at DATETIME,
                    repair_test_passed BOOLEAN,
                    repair_test_note TEXT,
                    rejection_reason TEXT,
                    rejection_proposed_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
                    rejection_proposed_at DATETIME,
                    rejection_proposal_note TEXT,
                    rejection_reviewed_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
                    rejection_reviewed_at DATETIME,
                    rejection_review_status VARCHAR(20) CHECK (rejection_review_status IS NULL OR rejection_review_status IN ('PENDING', 'APPROVED', 'DECLINED')),
                    completed_at DATETIME,
                    handed_over_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
                    handed_over_at DATETIME,
                    handover_note TEXT,
                    resolution VARCHAR(20) CHECK (resolution IS NULL OR resolution IN ('COMPLETED', 'REJECTED')),
                    created_at DATETIME,
                    updated_at DATETIME
                );
            """))

            # Lấy danh sách cột từ bảng cũ để copy chính xác
            cols_info = conn.execute(text("PRAGMA table_info(_old_warranty_tickets)")).fetchall()
            old_col_names = [r[1] for r in cols_info]
            new_cols_info = conn.execute(text("PRAGMA table_info(warranty_tickets)")).fetchall()
            new_col_names = set(r[1] for r in new_cols_info)
            common_cols = [c for c in old_col_names if c in new_col_names]

            cols_str = ", ".join(common_cols)
            conn.execute(text(f"INSERT INTO warranty_tickets ({cols_str}) SELECT {cols_str} FROM _old_warranty_tickets;"))
            conn.execute(text("DROP TABLE _old_warranty_tickets;"))
            conn.execute(text("PRAGMA foreign_keys = ON;"))
            logger.info("Đã nâng cấp CHECK constraint bảng warranty_tickets trên SQLite thành công.")
    except Exception as exc:
        logger.error("Lỗi khi nâng cấp constraint SQLite: %s", exc)


def migrate_tickets_data(engine: Engine) -> Dict[str, Any]:
    """
    Chuyển đổi dữ liệu phiếu cũ sang bộ 6 trạng thái chuẩn.
    Bảo toàn tính toàn vẹn, không suy đoán dữ liệu thiếu bằng chứng.
    """
    report = {
        "waiting_to_completed": 0,
        "completed_to_returned": 0,
        "completed_retained": 0,
        "rejected_to_returned": 0,
        "rejected_retained": 0,
        "conflicts": [],
    }

    try:
        with engine.begin() as conn:
            # 1. WAITING_RETURN -> COMPLETED
            # Ý NGHĨA NGHIỆP VỤ: repair_at là mốc bắt đầu ghi nhận sửa chữa, KHÔNG PHẢI ngày hoàn tất.
            # Tuyệt đối không lấy ngày bắt đầu sửa làm ngày hoàn tất (không fallback sang repair_at, updated_at, created_at).
            # Chỉ điền completed_at nếu có bằng chứng xác thực từ lịch sử chuyển trạng thái
            # (bản ghi ticket_status_history với to_status IN ('WAITING_RETURN', 'COMPLETED')).
            # Nếu thiếu bằng chứng, giữ completed_at = NULL (trống) để thống kê xử lý dữ liệu thiếu rõ ràng.
            res = conn.execute(text("""
                UPDATE warranty_tickets
                SET status = 'COMPLETED',
                    completed_at = COALESCE(
                        completed_at,
                        (
                            SELECT h.created_at
                            FROM ticket_status_history h
                            WHERE h.ticket_id = warranty_tickets.id
                              AND h.to_status IN ('WAITING_RETURN', 'COMPLETED')
                            ORDER BY h.id ASC
                            LIMIT 1
                        )
                    )
                WHERE status = 'WAITING_RETURN'
            """))
            report["waiting_to_completed"] = res.rowcount

            # 1b. Khong tu y sua dep hay ghi de completed_at tren moi lan khoi dong
            pass

            # 2. COMPLETED cũ:
            # - Có bằng chứng bàn giao (handed_over_at IS NOT NULL) -> RETURNED
            res = conn.execute(text("""
                UPDATE warranty_tickets
                SET status = 'RETURNED',
                    resolution = 'COMPLETED'
                WHERE status = 'COMPLETED' AND handed_over_at IS NOT NULL
            """))
            report["completed_to_returned"] = res.rowcount

            # - Không có bằng chứng bàn giao (handed_over_at IS NULL): giữ COMPLETED (Hoàn tất, chờ trả máy)
            count_kept = conn.execute(text("""
                SELECT COUNT(*) FROM warranty_tickets WHERE status = 'COMPLETED' AND handed_over_at IS NULL
            """)).scalar()
            report["completed_retained"] = count_kept

            # 3. REJECTED cũ:
            # - Có handed_over_at -> RETURNED, resolution = 'REJECTED'
            res = conn.execute(text("""
                UPDATE warranty_tickets
                SET status = 'RETURNED',
                    resolution = 'REJECTED'
                WHERE status = 'REJECTED' AND handed_over_at IS NOT NULL
            """))
            report["rejected_to_returned"] = res.rowcount

            # - Không có handed_over_at -> giữ REJECTED (chờ trả máy)
            count_rej = conn.execute(text("""
                SELECT COUNT(*) FROM warranty_tickets WHERE status = 'REJECTED' AND handed_over_at IS NULL
            """)).scalar()
            report["rejected_retained"] = count_rej

            # 4. Cập nhật bảng ticket_status_history cho đồng bộ
            conn.execute(text("UPDATE ticket_status_history SET from_status = 'COMPLETED' WHERE from_status = 'WAITING_RETURN';"))
            conn.execute(text("UPDATE ticket_status_history SET to_status = 'COMPLETED' WHERE to_status = 'WAITING_RETURN';"))

            # 5. Kiểm tra xung đột: tìm các serial có nhiều hơn 1 phiếu chưa đóng
            conflict_rows = conn.execute(text("""
                SELECT t.product_instance_id, pi.serial_number, COUNT(t.id) as open_count, GROUP_CONCAT(t.ticket_code) as codes
                FROM warranty_tickets t
                JOIN product_instances pi ON t.product_instance_id = pi.id
                WHERE t.status != 'RETURNED'
                GROUP BY t.product_instance_id, pi.serial_number
                HAVING COUNT(t.id) > 1
            """)).fetchall()

            for r in conflict_rows:
                conflict_item = {
                    "product_instance_id": r[0],
                    "serial_number": r[1],
                    "open_count": r[2],
                    "ticket_codes": r[3],
                }
                report["conflicts"].append(conflict_item)
                logger.warning(
                    "[CONFLICT] Thiết bị %s (ID %s) có %s phiếu chưa đóng: %s. Giữ nguyên dữ liệu để quản lý xử lý.",
                    r[1], r[0], r[2], r[3]
                )

    except Exception as exc:
        logger.error("Lỗi trong quá trình migrate_tickets_data: %s", exc)

    return report


def ensure_concurrency_index(engine: Engine) -> None:
    """Tạo partial unique index chặn triệt để request đồng thời tạo 2 phiếu mở cho cùng 1 serial."""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_open_ticket_per_instance
                ON warranty_tickets(product_instance_id)
                WHERE status != 'RETURNED';
            """))
            logger.info("Đã đảm bảo partial unique index uq_open_ticket_per_instance.")
    except Exception as exc:
        # Nếu có conflict dữ liệu cũ thì không tạo được unique index, log cảnh báo để quản lý giải quyết xung đột
        logger.warning("Chưa thể tạo partial unique index do có dữ liệu xung đột: %s", exc)
