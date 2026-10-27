import random
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import (
    Customer,
    ErrorCategory,
    ProductInstance,
    RepairLog,
    TicketStatusHistory,
    User,
    WarrantyTicket,
)
from app.schemas import (
    TicketDiagnosisUpdate,
    TicketRepairUpdate,
    WarrantyTicketCreate,
    WarrantyTicketStatusUpdate,
)
from app.services.warranty_rules import (
    TICKET_STATUS_LABELS,
    BusinessRuleError,
    validate_br1_serial_exists,
    validate_br2_warranty_valid,
    validate_br3_no_open_tickets,
    validate_br4_owner_verification,
    validate_error_category_exists,
    validate_state_transition,
    validate_service_center_exists,
    validate_ticket_completion,
    validate_transition_input,
    validate_user_exists,
)

def generate_ticket_code() -> str:
    """Sinh mã phiếu định dạng TK-YYYYMMDD-XXXX"""
    today_str = datetime.now().strftime("%Y%m%d")
    rand_suffix = f"{random.randint(1000, 9999)}"
    return f"TK-{today_str}-{rand_suffix}"

def create_warranty_ticket_with_rules(db: Session, ticket_in: WarrantyTicketCreate) -> WarrantyTicket:
    """
    Tạo phiếu bảo hành tuân thủ nghiêm ngặt 4 quy tắc BR1 - BR4:
    - BR1: Serial phải tồn tại trong bảng product_instances
    - BR2: Sản phẩm phải còn hạn bảo hành (warranty_end_date >= today)
    - BR3: Không có phiếu nào đang mở (RECEIVED, INSPECTING, REPAIRING, WAITING_RETURN)
    - BR4: Khách hàng yêu cầu phải trùng khớp với chủ sở hữu của serial
    """
    # 1. Kiểm tra BR1: Serial tồn tại
    instance = validate_br1_serial_exists(db, ticket_in.serial_number)

    # 2. Kiểm tra BR2: Còn hạn bảo hành
    validate_br2_warranty_valid(instance)

    # 3. Kiểm tra BR3: Không có phiếu đang mở
    validate_br3_no_open_tickets(db, instance.id)

    # 4. Kiểm tra BR4: Xác minh đúng chủ sở hữu
    validate_br4_owner_verification(instance, ticket_in.customer_id)

    # 5. [AUD-06] Kiểm tra sự tồn tại của các tham chiếu FK trước khi ghi CSDL
    #    (đặt SAU BR1-BR4 để không làm thay đổi hành vi của 4 quy tắc nghiệp vụ)
    validate_service_center_exists(db, ticket_in.service_center_id)
    validate_user_exists(db, ticket_in.created_by, "nhân viên tiếp nhận")

    # Nếu tất cả 4 rules đều PASS, tiến hành tạo phiếu ở trạng thái RECEIVED
    ticket_code = generate_ticket_code()
    
    # Đảm bảo mã phiếu là duy nhất
    while db.query(WarrantyTicket).filter(WarrantyTicket.ticket_code == ticket_code).first():
        ticket_code = generate_ticket_code()

    new_ticket = WarrantyTicket(
        ticket_code=ticket_code,
        product_instance_id=instance.id,
        customer_id=ticket_in.customer_id,
        service_center_id=ticket_in.service_center_id,
        created_by=ticket_in.created_by,
        issue_description=ticket_in.issue_description,
        error_category_id=ticket_in.error_category_id,
        status="RECEIVED"
    )

    db.add(new_ticket)
    db.flush()  # Sinh new_ticket.id trước khi ghi log lịch sử

    # Ghi log lịch sử khởi tạo trạng thái
    initial_history = TicketStatusHistory(
        ticket_id=new_ticket.id,
        from_status=None,
        to_status="RECEIVED",
        changed_by=ticket_in.created_by,
        note="Khởi tạo phiếu tiếp nhận bảo hành (Đạt toàn bộ BR1-BR4)."
    )
    db.add(initial_history)

    db.commit()
    db.refresh(new_ticket)
    return new_ticket

def get_warranty_ticket(db: Session, ticket_id: int) -> Optional[WarrantyTicket]:
    return db.query(WarrantyTicket).filter(WarrantyTicket.id == ticket_id).first()

def get_warranty_ticket_by_code(db: Session, ticket_code: str) -> Optional[WarrantyTicket]:
    return db.query(WarrantyTicket).filter(WarrantyTicket.ticket_code == ticket_code).first()

def last_handler_subquery(db: Session):
    """
    Bảng tra "người phụ trách hiện tại" của từng phiếu = người thực hiện
    BƯỚC XỬ LÝ GẦN NHẤT (dòng lịch sử trạng thái mới nhất).

    Dùng cho bộ lọc `mine=1` ("Việc của tôi"): nhờ làm ở tầng SQL nên phân trang
    và số liệu thống kê luôn tính trên ĐÚNG tập phiếu đang làm việc, không bị
    cắt bớt sau khi đã giới hạn số dòng.
    """
    latest = (
        db.query(
            TicketStatusHistory.ticket_id.label("ticket_id"),
            func.max(TicketStatusHistory.id).label("last_id"),
        )
        .group_by(TicketStatusHistory.ticket_id)
        .subquery()
    )
    return (
        db.query(
            TicketStatusHistory.ticket_id.label("ticket_id"),
            TicketStatusHistory.changed_by.label("changed_by"),
        )
        .join(latest, TicketStatusHistory.id == latest.c.last_id)
        .subquery()
    )


def get_warranty_tickets(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    status_filter: Optional[str] = None,
    keyword: Optional[str] = None,
    mine_user_id: Optional[int] = None,
) -> List[WarrantyTicket]:
    """
    Danh sách phiếu bảo hành.

    `keyword` tìm theo: mã phiếu, số sê-ri, tên khách hàng, số điện thoại khách hàng
    (đúng nhu cầu "khách gọi tới, nhân viên tra một ô là ra việc").
    `mine_user_id`: chỉ lấy phiếu mà nhân viên này là người xử lý gần nhất (SQL).
    """
    query = (
        db.query(WarrantyTicket)
        .outerjoin(ProductInstance, WarrantyTicket.product_instance_id == ProductInstance.id)
        .outerjoin(Customer, WarrantyTicket.customer_id == Customer.id)
    )
    if mine_user_id is not None:
        handler = last_handler_subquery(db)
        query = query.outerjoin(handler, handler.c.ticket_id == WarrantyTicket.id).filter(
            func.coalesce(handler.c.changed_by, WarrantyTicket.created_by) == mine_user_id
        )
    if status_filter:
        # Hỗ trợ cả một trạng thái ("REPAIRING") và nhiều trạng thái cách nhau bởi dấu phẩy
        # ("INSPECTING,REPAIRING") để nhóm việc "Đang xử lý" trên bảng điều khiển mở đúng danh sách.
        values = [value.strip() for value in str(status_filter).split(",") if value.strip()]
        if len(values) == 1:
            query = query.filter(WarrantyTicket.status == values[0])
        elif values:
            query = query.filter(WarrantyTicket.status.in_(values))

    if keyword and keyword.strip():
        like = f"%{keyword.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(WarrantyTicket.ticket_code).like(like),
                func.lower(func.coalesce(ProductInstance.serial_number, "")).like(like),
                func.lower(func.coalesce(Customer.full_name, "")).like(like),
                func.lower(func.coalesce(Customer.phone, "")).like(like),
            )
        )

    return query.order_by(WarrantyTicket.id.desc()).offset(skip).limit(limit).all()


def count_tickets_by_status(
    db: Session, mine_user_id: Optional[int] = None
) -> Dict[str, int]:
    """
    Đếm phiếu theo trạng thái.

    - `mine_user_id = None`: đếm toàn hệ thống (tổng quan cho Quản lý).
    - `mine_user_id = <id>`: chỉ đếm phiếu mà nhân viên đó là NGƯỜI XỬ LÝ GẦN NHẤT
      (dùng cho khối "Việc của tôi" trên bảng điều khiển). Phép lọc chạy ở SQL
      nên số liệu khớp với danh sách phiếu của chính bộ lọc đó.
    """
    if mine_user_id is None:
        counts = dict(
            db.query(WarrantyTicket.status, func.count(WarrantyTicket.id))
            .group_by(WarrantyTicket.status)
            .all()
        )
        return {str(k): int(v) for k, v in counts.items()}

    handler = last_handler_subquery(db)
    counts = dict(
        db.query(WarrantyTicket.status, func.count(WarrantyTicket.id))
        .outerjoin(handler, handler.c.ticket_id == WarrantyTicket.id)
        .filter(func.coalesce(handler.c.changed_by, WarrantyTicket.created_by) == mine_user_id)
        .group_by(WarrantyTicket.status)
        .all()
    )
    return {str(k): int(v) for k, v in counts.items()}

def _get_ticket_or_404(db: Session, ticket_id: int) -> WarrantyTicket:
    """Lấy phiếu hoặc báo lỗi tiếng Việt dễ hiểu (không lộ chi tiết kỹ thuật)."""
    ticket = get_warranty_ticket(db, ticket_id)
    if not ticket:
        raise BusinessRuleError(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy phiếu bảo hành có ID: {ticket_id}",
            user_message="Không tìm thấy phiếu bảo hành này. Có thể phiếu đã bị xoá.",
            error_code="TICKET_NOT_FOUND",
            hint="Tải lại danh sách phiếu rồi mở lại phiếu cần xử lý.",
        )
    return ticket


def _apply_workflow_fields(
    db: Session,
    ticket: WarrantyTicket,
    payload: WarrantyTicketStatusUpdate,
    actor: User,
    now: datetime,
    from_status: str,
    to_status: str,
) -> None:
    """
    Ghi nhận thông tin nghiệp vụ đi kèm một bước chuyển trạng thái.

    Quy ước:
      - CHẨN ĐOÁN (diagnosis_*) do người thực hiện bước này ghi -> lưu người + thời gian.
      - SỬA CHỮA (repair_*) ghi khi sửa xong; bước sang WAITING_RETURN chốt mốc sửa xong.
      - BÀN GIAO (handover_note + handed_over_by/at) ghi khi hoàn tất phiếu.
    """
    if payload.diagnosis_note and payload.diagnosis_note.strip():
        ticket.diagnosis_note = payload.diagnosis_note.strip()
        ticket.diagnosis_by = actor.id
        ticket.diagnosis_at = now

    if payload.error_category_id is not None:
        # Loại lỗi do NGƯỜI xác nhận (không phải AI tự ghi) -> lưu cả người + thời điểm.
        validate_error_category_exists(db, payload.error_category_id)
        ticket.error_category_id = payload.error_category_id
        ticket.diagnosis_by = actor.id
        ticket.diagnosis_at = ticket.diagnosis_at or now

    if payload.repair_content and payload.repair_content.strip():
        ticket.repair_content = payload.repair_content.strip()
    if payload.repair_parts and payload.repair_parts.strip():
        ticket.repair_parts = payload.repair_parts.strip()
    if payload.repair_note and payload.repair_note.strip():
        ticket.repair_note = payload.repair_note.strip()

    if to_status == "WAITING_RETURN":
        # Bước này chính là "sửa xong" -> chốt mốc hoàn thành sửa chữa + người thực hiện.
        ticket.repair_at = now
        ticket.repair_by = actor.id
        # Ghi thêm nhật ký sửa chữa (bảng repair_logs có sẵn từ KT1) để tra cứu về sau.
        description = (
            (payload.repair_content or "").strip()
            or (payload.repair_note or "").strip()
            or (payload.note or "").strip()
        )
        if description:
            db.add(
                RepairLog(
                    ticket_id=ticket.id,
                    technician_id=actor.id,
                    action_description=description,
                    parts_used=(payload.repair_parts or "").strip() or None,
                )
            )

    if to_status == "COMPLETED":
        ticket.handover_note = (
            (payload.handover_note or "").strip() or (payload.note or "").strip() or None
        )
        ticket.handed_over_by = actor.id


def update_ticket_status(
    db: Session,
    ticket_id: int,
    status_update: WarrantyTicketStatusUpdate
) -> WarrantyTicket:
    """
    Cập nhật trạng thái phiếu theo đúng quy trình nghiệp vụ:

    1. Phiếu phải tồn tại; người thực hiện phải là nhân viên có thật trong hệ thống.
    2. Chuyển trạng thái phải nằm trong ma trận ALLOWED_TRANSITIONS
       (bắt buộc đi qua WAITING_RETURN trước khi COMPLETED).
    3. Mỗi bước nghiệp vụ phải kèm thông tin xử lý (không cho "bấm cho xong").
    4. Hoàn tất phiếu phải đủ điều kiện (thiết bị + khách hàng + đã sửa xong + đủ lịch sử).
    5. Lưu vết đầy đủ: từ/đến trạng thái, người thực hiện, thời gian, ghi chú.

    Đầu vào có thể kèm dữ liệu chuyên môn: diagnosis_note, error_category_id,
    repair_content, repair_parts, repair_note, handover_note.
    """
    ticket = _get_ticket_or_404(db, ticket_id)

    # [AUD-06] `changed_by` phải là nhân viên tồn tại trước khi ghi lịch sử trạng thái.
    actor = validate_user_exists(db, status_update.changed_by, "nhân viên thực hiện")

    from_status = ticket.status
    to_status = status_update.new_status

    # 2. Xác thực transition hợp lệ theo State Machine 6 trạng thái
    validate_state_transition(from_status, to_status, status_update.rejection_reason)

    # 3. Bắt buộc có thông tin xử lý cho các bước nghiệp vụ (sửa chữa / hoàn tất / ...)
    validate_transition_input(
        from_status,
        to_status,
        note=status_update.note,
        diagnosis_note=status_update.diagnosis_note,
        repair_content=status_update.repair_content,
        repair_parts=status_update.repair_parts,
        repair_note=status_update.repair_note,
        handover_note=status_update.handover_note,
    )

    # 4. Chỉ cho hoàn tất khi đã sửa xong và máy thực sự đang chờ trả cho khách
    if to_status == "COMPLETED":
        validate_ticket_completion(db, ticket)

    now = datetime.utcnow()

    # Ghi nhận dữ liệu chuyên môn kèm bước chuyển (nếu người dùng có nhập)
    _apply_workflow_fields(db, ticket, status_update, actor, now, from_status, to_status)

    # Cập nhật trạng thái phiếu
    ticket.status = to_status

    if to_status == "REJECTED":
        ticket.rejection_reason = status_update.rejection_reason
        ticket.rejection_reviewed_by = status_update.changed_by
        ticket.rejection_reviewed_at = now
        ticket.rejection_review_status = "APPROVED"
    elif to_status == "COMPLETED":
        ticket.handed_over_at = now

    # Ghi log lịch sử trạng thái (người thực hiện + thời gian + ghi chú)
    history_entry = TicketStatusHistory(
        ticket_id=ticket.id,
        from_status=from_status,
        to_status=to_status,
        changed_by=status_update.changed_by,
        note=status_update.note or f"Chuyển trạng thái từ {from_status} sang {to_status}"
    )
    db.add(history_entry)

    db.commit()
    db.refresh(ticket)
    return ticket



def save_ticket_diagnosis(
    db: Session, ticket_id: int, payload: TicketDiagnosisUpdate
) -> WarrantyTicket:
    """
    Ghi nhận CHẨN ĐOÁN của kỹ thuật viên mà KHÔNG đổi trạng thái phiếu.

    Đây là kết luận của NGƯỜI. Gợi ý của AI nằm riêng ở bảng ai_results và chỉ được
    ghi vào phiếu sau khi người có quyền xác nhận (KT3 - human in the loop).
    """
    ticket = _get_ticket_or_404(db, ticket_id)
    if ticket.status in ("COMPLETED", "REJECTED"):
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"[WORKFLOW STATE ERROR] Phiếu đang ở trạng thái {ticket.status} "
                "nên không thể ghi chẩn đoán."
            ),
            user_message=(
                f"Phiếu đã ở trạng thái \"{TICKET_STATUS_LABELS.get(ticket.status, ticket.status)}\" "
                "nên không thể ghi thêm chẩn đoán."
            ),
            error_code="WORKFLOW_STATE_CLOSED",
            hint="Trao đổi với quản lý nếu thiết bị phải xử lý lại.",
        )

    actor = validate_user_exists(db, payload.actor_id, "nhân viên ghi nhận chẩn đoán")
    if payload.error_category_id is not None:
        validate_error_category_exists(db, payload.error_category_id)
        ticket.error_category_id = payload.error_category_id

    ticket.diagnosis_note = payload.diagnosis_note.strip()
    ticket.diagnosis_by = actor.id
    ticket.diagnosis_at = datetime.utcnow()

    db.commit()
    db.refresh(ticket)
    return ticket


def save_ticket_repair(
    db: Session, ticket_id: int, payload: TicketRepairUpdate
) -> WarrantyTicket:
    """
    Ghi nhận NỘI DUNG SỬA CHỮA (đã kiểm tra / đã sửa / linh kiện thay thế) mà không đổi trạng thái.

    Bắt buộc có nội dung sửa chữa hoặc ghi chú kỹ thuật để phiếu không bị rỗng thông tin.
    """
    ticket = _get_ticket_or_404(db, ticket_id)
    if ticket.status in ("COMPLETED", "REJECTED"):
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"[WORKFLOW STATE ERROR] Phiếu đang ở trạng thái {ticket.status} "
                "nên không thể ghi nội dung sửa chữa."
            ),
            user_message=(
                f"Phiếu đã ở trạng thái \"{TICKET_STATUS_LABELS.get(ticket.status, ticket.status)}\" "
                "nên không thể ghi thêm nội dung sửa chữa."
            ),
            error_code="WORKFLOW_STATE_CLOSED",
            hint="Trao đổi với quản lý nếu thiết bị phải sửa lại.",
        )

    content = (payload.repair_content or "").strip()
    note = (payload.repair_note or "").strip()
    parts = (payload.repair_parts or "").strip()
    if not (content or note):
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "[WORKFLOW INPUT REQUIRED] Thiếu repair_content/repair_note "
                "khi lưu nội dung sửa chữa."
            ),
            user_message=(
                "Vui lòng ghi nội dung đã kiểm tra/đã sửa chữa (hoặc ghi chú kỹ thuật) "
                "trước khi lưu."
            ),
            error_code="WORKFLOW_INPUT_REQUIRED",
            hint="Ví dụ: Đã thay IC nguồn, vệ sinh tản nhiệt, chạy thử 2 giờ ổn định.",
        )

    actor = validate_user_exists(db, payload.actor_id, "nhân viên sửa chữa")
    ticket.repair_content = content or ticket.repair_content
    ticket.repair_note = note or ticket.repair_note
    ticket.repair_parts = parts or ticket.repair_parts
    ticket.repair_by = actor.id
    ticket.repair_at = datetime.utcnow()

    db.add(
        RepairLog(
            ticket_id=ticket.id,
            technician_id=actor.id,
            action_description=content or note,
            parts_used=parts or None,
        )
    )
    db.commit()
    db.refresh(ticket)
    return ticket
