import random
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Customer,
    ErrorCategory,
    ProductInstance,
    RepairLog,
    TechnicianAssignment,
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
    OPEN_TICKET_STATUSES,
    TICKET_STATUS_LABELS,
    BusinessRuleError,
    check_instance_warranty_status,
    validate_br1_serial_exists,
    validate_br2_warranty_valid,
    validate_br3_no_open_tickets,
    validate_br4_owner_verification,
    validate_error_category_exists,
    validate_inspecting_to_repairing,
    validate_repairing_to_completed,
    validate_service_center_exists,
    validate_state_transition,
    validate_ticket_actor_access,
    validate_ticket_technician_assignment,
    validate_to_returned,
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
    - BR1: Serial phải tồn tại trong bảng product_instances.
    - BR2: Sản phẩm phải còn hạn bảo hành (warranty_end_date >= today; không tự lấy ngày tiếp nhận làm ngày mua).
    - BR3: Một serial chỉ có 1 phiếu chưa đóng tại một thời điểm (kể cả phiếu đang chờ trả máy).
    - BR4: Khách hàng yêu cầu phải trùng khớp với chủ sở hữu của serial.
    Xử lý an toàn request đồng thời bằng partial unique index và database transaction.
    """
    # 1. BR1: Serial tồn tại
    instance = validate_br1_serial_exists(db, ticket_in.serial_number)

    # 2. BR2: Kiểm tra hạn bảo hành (không tự lấy ngày tiếp nhận làm ngày mua khi thiếu dữ liệu).
    # Quy tắc: Máy hết hạn VẪN ĐƯỢC lập phiếu tiếp nhận để kiểm tra và đi qua luồng từ chối rồi trả máy.
    # Không cho máy hết hạn chuyển sang sửa chữa bảo hành (chặn tại bước INSPECTING -> REPAIRING).
    is_valid_warranty, days_diff = check_instance_warranty_status(instance)
    warranty_note = None
    if not is_valid_warranty:
        warranty_note = (
            f"Hết hạn bảo hành từ ngày {instance.warranty_end_date.strftime('%d/%m/%Y')} (quá hạn {days_diff} ngày). "
            "Tiếp nhận để kiểm tra và xử lý theo luồng từ chối/tính phí."
        )

    # 3. BR3: Không có phiếu đang mở
    validate_br3_no_open_tickets(db, instance.id)

    # 4. BR4: Xác minh đúng chủ sở hữu
    validate_br4_owner_verification(instance, ticket_in.customer_id)

    # 5. Kiểm tra các tham chiếu tồn tại
    validate_service_center_exists(db, ticket_in.service_center_id)
    creator = validate_user_exists(db, ticket_in.created_by, "nhân viên tiếp nhận")

    # Kiểm tra KTV phân công: CHỈ Quản lý mới được phân công KTV ngay khi lập phiếu
    assigned_tech = None
    if ticket_in.technician_id:
        if creator.role != "MANAGER":
            raise BusinessRuleError(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Chỉ Quản lý mới có quyền phân công kỹ thuật viên phụ trách phiếu.",
                user_message="Nhân viên tiếp nhận không được tự phân công KTV. Phiếu sẽ được chuyển cho Quản lý phân công.",
                error_code="RBAC_ASSIGN_FORBIDDEN",
            )
        assigned_tech = validate_user_exists(db, ticket_in.technician_id, "kỹ thuật viên phụ trách")

    ticket_code = generate_ticket_code()
    while db.query(WarrantyTicket).filter(WarrantyTicket.ticket_code == ticket_code).first():
        ticket_code = generate_ticket_code()

    now = datetime.utcnow()
    new_ticket = WarrantyTicket(
        ticket_code=ticket_code,
        product_instance_id=instance.id,
        customer_id=ticket_in.customer_id,
        service_center_id=ticket_in.service_center_id,
        created_by=ticket_in.created_by,
        issue_description=ticket_in.issue_description,
        device_condition=getattr(ticket_in, "device_condition", None),
        accessories_accompanying=getattr(ticket_in, "accessories_accompanying", None),
        error_category_id=ticket_in.error_category_id,
        status="RECEIVED",
        assigned_technician_id=assigned_tech.id if assigned_tech else None,
        assigned_at=now if assigned_tech else None,
        is_warranty_eligible=False if not is_valid_warranty else None,
        warranty_check_note=warranty_note,
    )

    db.add(new_ticket)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        # Bắt trường hợp race condition tạo trùng phiếu mở cho cùng 1 serial
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"[BR3 FAIL] Xung đột đồng thời: Thiết bị '{ticket_in.serial_number}' đã có phiếu bảo hành đang mở.",
            user_message=f"Thiết bị '{ticket_in.serial_number}' đang có phiếu bảo hành chưa đóng trong hệ thống.",
            error_code="BR3_OPEN_TICKET_EXISTS",
            hint="Vui lòng kiểm tra lại danh sách phiếu đang mở của thiết bị này.",
        ) from exc

    # Ghi log lịch sử khởi tạo trạng thái
    if not is_valid_warranty:
        initial_note = f"Khởi tạo phiếu tiếp nhận bảo hành (Thiết bị đã hết hạn bảo hành {days_diff} ngày, tiếp nhận để kiểm tra/từ chối)."
    else:
        initial_note = "Khởi tạo phiếu tiếp nhận bảo hành (Đạt toàn bộ BR1-BR4)."
    if assigned_tech:
        initial_note += f" Phân công kỹ thuật viên: {assigned_tech.full_name}."
        # Lưu vào bảng technician_assignments
        db.add(
            TechnicianAssignment(
                ticket_id=new_ticket.id,
                technician_id=assigned_tech.id,
                assigned_by=creator.id,
                assigned_at=now,
            )
        )

    initial_history = TicketStatusHistory(
        ticket_id=new_ticket.id,
        from_status=None,
        to_status="RECEIVED",
        changed_by=ticket_in.created_by,
        note=initial_note,
        created_at=now,
    )
    db.add(initial_history)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"[BR3 FAIL] Thiết bị '{ticket_in.serial_number}' đã có phiếu bảo hành đang xử lý.",
            user_message="Thiết bị này đang có một phiếu bảo hành chưa đóng.",
            error_code="BR3_OPEN_TICKET_EXISTS",
        ) from exc

    db.refresh(new_ticket)
    return new_ticket


def get_warranty_ticket(db: Session, ticket_id: int) -> Optional[WarrantyTicket]:
    return db.query(WarrantyTicket).filter(WarrantyTicket.id == ticket_id).first()


def get_warranty_ticket_by_code(db: Session, ticket_code: str) -> Optional[WarrantyTicket]:
    return db.query(WarrantyTicket).filter(WarrantyTicket.ticket_code == ticket_code).first()


def assign_technician_to_ticket(
    db: Session,
    ticket_id: int,
    technician_id: int,
    assigned_by: int,
    note: Optional[str] = None,
) -> WarrantyTicket:
    """Phân công hoặc phân công lại kỹ thuật viên phụ trách phiếu bảo hành."""
    ticket = _get_ticket_or_404(db, ticket_id)
    tech = validate_user_exists(db, technician_id, "kỹ thuật viên")
    assigner = validate_user_exists(db, assigned_by, "người phân công")

    # Quy tắc nghiệp vụ: Chỉ phân công / phân công lại khi phiếu ở RECEIVED, INSPECTING, REPAIRING.
    # Tuyệt đối không cho phép phân công khi phiếu đã ở COMPLETED, REJECTED hoặc RETURNED.
    ASSIGNABLE_STATUSES = ("RECEIVED", "INSPECTING", "REPAIRING")
    if ticket.status not in ASSIGNABLE_STATUSES:
        status_labels = {
            "COMPLETED": "Hoàn tất sửa chữa",
            "REJECTED": "Từ chối bảo hành",
            "RETURNED": "Đã trả máy",
        }
        lbl = status_labels.get(ticket.status, ticket.status)
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"[TICKET_NOT_ASSIGNABLE] Không thể phân công hoặc phân công lại kỹ thuật viên cho phiếu ở trạng thái {ticket.status} ({lbl}). "
                f"Chỉ được phân công khi phiếu đang ở trạng thái Tiếp nhận (RECEIVED), Kiểm tra (INSPECTING) hoặc Sửa chữa (REPAIRING)."
            ),
            user_message=f"Phiếu đang ở trạng thái '{lbl}', không thể phân công hoặc thay đổi kỹ thuật viên phụ trách.",
            error_code="TICKET_NOT_ASSIGNABLE",
        )

    if not tech.active:
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kỹ thuật viên đang bị khoá hoặc đã ngừng hoạt động.",
            user_message="Kỹ thuật viên này đang bị khoá hoặc đã ngừng hoạt động. Vui lòng chọn kỹ thuật viên khác.",
            error_code="TECHNICIAN_INACTIVE",
        )
    if tech.role != "TECHNICIAN":
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Người được phân công phải có vai trò Kỹ thuật viên (TECHNICIAN).",
            user_message="Chỉ được phân công cho nhân viên có vai trò Kỹ thuật viên.",
            error_code="INVALID_TECHNICIAN_ROLE",
        )
    if ticket.service_center_id and tech.service_center_id and tech.service_center_id != ticket.service_center_id:
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kỹ thuật viên không thuộc trung tâm bảo hành tiếp nhận phiếu.",
            user_message="Kỹ thuật viên này không thuộc trung tâm bảo hành tiếp nhận phiếu.",
            error_code="SERVICE_CENTER_MISMATCH",
        )

    is_reassign = ticket.assigned_technician_id is not None and ticket.assigned_technician_id != tech.id
    if is_reassign and (not note or not note.strip()):
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="[REASSIGN_REASON_REQUIRED] Phân công lại kỹ thuật viên bắt buộc phải có lý do.",
            user_message="Khi phân công lại kỹ thuật viên, bắt buộc phải có lý do.",
            error_code="REASSIGN_REASON_REQUIRED",
        )

    now = datetime.utcnow()
    ticket.assigned_technician_id = tech.id
    ticket.assigned_at = now

    # Lưu vào technician_assignments
    db.add(
        TechnicianAssignment(
            ticket_id=ticket.id,
            technician_id=tech.id,
            assigned_by=assigner.id,
            assigned_at=now,
        )
    )

    # Lưu lịch sử phân công lại vào TicketStatusHistory nếu là phân công lại
    if is_reassign:
        hist_note = f"Phân công lại KTV: {tech.full_name}. Lý do: {note.strip()}"
        db.add(
            TicketStatusHistory(
                ticket_id=ticket.id,
                from_status=ticket.status,
                to_status=ticket.status,
                changed_by=assigner.id,
                note=hist_note,
                created_at=now,
            )
        )

    db.commit()
    db.refresh(ticket)
    return ticket


def propose_ticket_rejection(
    db: Session,
    ticket_id: int,
    proposal_note: str,
    actor: User,
) -> WarrantyTicket:
    """Kỹ thuật viên ghi đề xuất từ chối bảo hành kèm bằng chứng kiểm tra."""
    ticket = _get_ticket_or_404(db, ticket_id)
    validate_ticket_actor_access(ticket, actor, is_technical=True)

    if ticket.status != "INSPECTING":
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chỉ được đề xuất từ chối khi phiếu đang ở trạng thái Kiểm tra (hiện tại: {ticket.status}).",
            user_message="Chỉ có thể gửi đề xuất từ chối khi máy đang ở bước Kiểm tra.",
            error_code="WORKFLOW_INVALID_STATE",
        )

    now = datetime.utcnow()
    ticket.rejection_proposed_by = actor.id
    ticket.rejection_proposed_at = now
    ticket.rejection_proposal_note = proposal_note.strip()
    ticket.rejection_review_status = "PENDING"

    db.add(
        TicketStatusHistory(
            ticket_id=ticket.id,
            from_status="INSPECTING",
            to_status="INSPECTING",
            changed_by=actor.id,
            note=f"Kỹ thuật viên đề xuất từ chối bảo hành: {proposal_note.strip()}",
            created_at=now,
        )
    )

    db.commit()
    db.refresh(ticket)
    return ticket


def review_ticket_rejection_proposal(
    db: Session,
    ticket_id: int,
    decision: str,
    note: str,
    actor: User,
) -> WarrantyTicket:
    """Quản lý xét duyệt đề xuất từ chối của KTV: APPROVED hoặc DECLINED."""
    ticket = _get_ticket_or_404(db, ticket_id)
    if actor.role != "MANAGER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ Quản lý mới có quyền xét duyệt đề xuất từ chối bảo hành.",
        )
    if ticket.status != "INSPECTING":
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chỉ xét duyệt đề xuất từ chối khi phiếu đang ở bước Kiểm tra.",
            user_message="Phiếu không ở trạng thái Kiểm tra để xét duyệt đề xuất từ chối.",
            error_code="WORKFLOW_INVALID_STATE",
        )
    now = datetime.utcnow()
    decision_upper = decision.strip().upper()
    if decision_upper == "APPROVED":
        ticket.status = "REJECTED"
        ticket.rejection_reason = note.strip()
        ticket.rejection_reviewed_by = actor.id
        ticket.rejection_reviewed_at = now
        ticket.rejection_review_status = "APPROVED"
        db.add(
            TicketStatusHistory(
                ticket_id=ticket.id,
                from_status="INSPECTING",
                to_status="REJECTED",
                changed_by=actor.id,
                note=f"Quản lý duyệt từ chối bảo hành. Lý do chính thức: {note.strip()}",
                created_at=now,
            )
        )
    elif decision_upper == "DECLINED":
        ticket.rejection_review_status = "DECLINED"
        ticket.rejection_reviewed_by = actor.id
        ticket.rejection_reviewed_at = now
        db.add(
            TicketStatusHistory(
                ticket_id=ticket.id,
                from_status="INSPECTING",
                to_status="INSPECTING",
                changed_by=actor.id,
                note=f"Quản lý không đồng ý đề xuất từ chối: {note.strip()}",
                created_at=now,
            )
        )
    else:
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quyết định xét duyệt phải là APPROVED hoặc DECLINED.",
            user_message="Quyết định xét duyệt không hợp lệ.",
            error_code="INVALID_DECISION",
        )
    db.commit()
    db.refresh(ticket)
    return ticket


def update_ticket_status(
    db: Session,
    ticket_id: int,
    status_update: WarrantyTicketStatusUpdate,
    actor: Optional[User] = None,
) -> WarrantyTicket:
    """
    Cập nhật trạng thái phiếu theo đúng vòng đời nghiệp vụ và phân quyền:
    - Kiểm tra quyền thao tác per-ticket (KTV chỉ thao tác phiếu được phân công).
    - Kiểm tra State Machine hợp lệ (không chuyển tắt, không chuyển ngược, không mở lại phiếu đã đóng).
    - Kiểm tra điều kiện bắt buộc của từng bước:
      + RECEIVED -> INSPECTING: phải có KTV phụ trách.
      + INSPECTING -> REPAIRING: phải có chẩn đoán & xác định đủ ĐKBH (is_warranty_eligible=True).
      + REPAIRING -> COMPLETED: phải có nội dung xử lý & kiểm tra sau sửa đạt yêu cầu (repair_test_passed=True).
      + INSPECTING -> REJECTED: chỉ Quản lý duyệt, bắt buộc lý do từ chối.
      + COMPLETED / REJECTED -> RETURNED: chỉ Tiếp nhận hoặc Quản lý, bắt buộc xác nhận bàn giao, lưu người trả & thời điểm trả.
    - Cập nhật phiếu và ghi log lịch sử trong CÙNG giao dịch.
    """
    ticket = _get_ticket_or_404(db, ticket_id)
    acting_user = actor or validate_user_exists(db, status_update.changed_by, "nhân viên thực hiện")

    # Kiểm tra quyền per-ticket: KTV không được sửa phiếu của KTV khác
    validate_ticket_actor_access(ticket, acting_user)

    from_status = ticket.status
    to_status = str(status_update.new_status).upper()

    # 1. Xác thực State Machine
    validate_state_transition(from_status, to_status, status_update.rejection_reason)

    now = datetime.utcnow()

    # 2. Kiểm tra điều kiện từng bước cụ thể
    if to_status == "INSPECTING":
        # Nếu có truyền technician_id thì gán KTV phụ trách
        if status_update.technician_id:
            tech = validate_user_exists(db, status_update.technician_id, "kỹ thuật viên")
            ticket.assigned_technician_id = tech.id
            ticket.assigned_at = now
            db.add(
                TechnicianAssignment(
                    ticket_id=ticket.id,
                    technician_id=tech.id,
                    assigned_by=acting_user.id,
                    assigned_at=now,
                )
            )
        # Bắt buộc phải có kỹ thuật viên phụ trách
        validate_ticket_technician_assignment(ticket, status_update.technician_id)

    elif to_status == "REPAIRING":
        # Bắt buộc phiếu phải có kỹ thuật viên phụ trách
        validate_ticket_technician_assignment(ticket)

        # Cập nhật chẩn đoán / loại lỗi / điều kiện bảo hành nếu có trong payload
        if status_update.diagnosis_note:
            ticket.diagnosis_note = status_update.diagnosis_note.strip()
            ticket.diagnosis_by = acting_user.id
            ticket.diagnosis_at = now
        if status_update.error_category_id:
            validate_error_category_exists(db, status_update.error_category_id)
            ticket.error_category_id = status_update.error_category_id
        if status_update.is_warranty_eligible is not None:
            ticket.is_warranty_eligible = status_update.is_warranty_eligible
        if status_update.warranty_check_note:
            ticket.warranty_check_note = status_update.warranty_check_note.strip()

        # Kiểm tra điều kiện bắt buộc để sang REPAIRING
        validate_inspecting_to_repairing(
            ticket,
            diagnosis_note=status_update.diagnosis_note,
            is_warranty_eligible=status_update.is_warranty_eligible,
        )

    elif to_status == "REJECTED":
        # Chỉ Quản lý duyệt từ chối bảo hành
        if acting_user.role != "MANAGER":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Chỉ quản lý được xác nhận TỪ CHỐI bảo hành. Vui lòng chuyển hồ sơ cho quản lý quyết định.",
            )
        ticket.rejection_reason = status_update.rejection_reason.strip()
        ticket.rejection_reviewed_by = acting_user.id
        ticket.rejection_reviewed_at = now
        ticket.rejection_review_status = "APPROVED"

    elif to_status == "COMPLETED":
        # Bắt buộc phiếu phải có kỹ thuật viên phụ trách
        validate_ticket_technician_assignment(ticket)

        # Cập nhật thông tin sửa chữa & kiểm tra sau sửa nếu có
        if status_update.repair_content:
            ticket.repair_content = status_update.repair_content.strip()
        if status_update.repair_parts:
            ticket.repair_parts = status_update.repair_parts.strip()
        if status_update.repair_note:
            ticket.repair_note = status_update.repair_note.strip()
        if status_update.repair_test_passed is not None:
            ticket.repair_test_passed = status_update.repair_test_passed
        if status_update.repair_test_note:
            ticket.repair_test_note = status_update.repair_test_note.strip()

        # Kiểm tra điều kiện bắt buộc để sang COMPLETED
        validate_repairing_to_completed(
            ticket,
            repair_content=status_update.repair_content,
            repair_test_passed=status_update.repair_test_passed,
            note=status_update.note,
        )

        ticket.completed_at = now
        ticket.repair_at = now
        ticket.repair_by = acting_user.id

        # Ghi log sửa chữa
        rep_desc = ticket.repair_content or ticket.repair_note or status_update.note or "Sửa chữa hoàn tất"
        db.add(
            RepairLog(
                ticket_id=ticket.id,
                technician_id=acting_user.id,
                action_description=rep_desc,
                parts_used=ticket.repair_parts or None,
            )
        )

    elif to_status == "RETURNED":
        # Xác nhận trả máy và đóng phiếu
        validate_to_returned(ticket, acting_user, status_update.handover_note, status_update.note)
        ticket.handed_over_by = acting_user.id
        ticket.handed_over_at = now
        ticket.handover_note = (status_update.handover_note or status_update.note or "").strip() or None
        
        # Lưu kết quả đóng phiếu (resolution): giữ nguyên kết quả trước đó là sửa hoàn tất hay từ chối
        ticket.resolution = from_status  # "COMPLETED" hoặc "REJECTED"

    # Cập nhật trạng thái phiếu có kiểm tra xung đột đồng thời (Optimistic Concurrency Control)
    # Bắt buộc trạng thái trong CSDL tại thời điểm ghi phải đúng bằng from_status
    updated_rows = (
        db.query(WarrantyTicket)
        .filter(WarrantyTicket.id == ticket.id, WarrantyTicket.status == from_status)
        .update({WarrantyTicket.status: to_status}, synchronize_session=False)
    )

    if updated_rows == 0:
        db.rollback()
        current_actual = db.query(WarrantyTicket).filter(WarrantyTicket.id == ticket.id).first()
        actual_st = current_actual.status if current_actual else "UNKNOWN"
        raise BusinessRuleError(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"[CONCURRENCY CONFLICT] Trạng thái phiếu '{ticket.ticket_code}' đã bị thay đổi đồng thời bởi một giao dịch khác "
                f"(trạng thái hiện tại: '{actual_st}'). Thao tác chuyển từ '{from_status}' sang '{to_status}' bị hủy để chống ghi đè."
            ),
            user_message=(
                f"Phiếu vừa được cập nhật sang \"{TICKET_STATUS_LABELS.get(actual_st, actual_st)}\" bởi thao tác khác. "
                "Vui lòng tải lại trang để xem tiến độ mới nhất."
            ),
            error_code="CONCURRENCY_CONFLICT",
            hint="Tải lại trang trước khi thực hiện thao tác tiếp theo.",
        )

    ticket.status = to_status

    # Ghi log lịch sử trạng thái trong CÙNG giao dịch
    history_note = (status_update.note or "").strip() or f"Chuyển trạng thái từ {TICKET_STATUS_LABELS.get(from_status, from_status)} sang {TICKET_STATUS_LABELS.get(to_status, to_status)}"
    history_entry = TicketStatusHistory(
        ticket_id=ticket.id,
        from_status=from_status,
        to_status=to_status,
        changed_by=acting_user.id,
        note=history_note,
        created_at=now,
    )
    db.add(history_entry)

    db.commit()
    db.refresh(ticket)
    return ticket


def save_ticket_diagnosis(
    db: Session,
    ticket_id: int,
    payload: TicketDiagnosisUpdate,
    actor: Optional[User] = None,
) -> WarrantyTicket:
    """Ghi nhận chẩn đoán & điều kiện bảo hành của kỹ thuật viên mà không đổi trạng thái."""
    ticket = _get_ticket_or_404(db, ticket_id)
    acting_user = actor or validate_user_exists(db, payload.actor_id, "nhân viên ghi nhận chẩn đoán")
    validate_ticket_actor_access(ticket, acting_user, is_technical=True)

    if ticket.status in ("COMPLETED", "RETURNED", "REJECTED"):
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"[WORKFLOW STATE ERROR] Phiếu đang ở trạng thái {ticket.status} nên không thể ghi chẩn đoán.",
            user_message=f"Phiếu đã ở trạng thái \"{TICKET_STATUS_LABELS.get(ticket.status, ticket.status)}\" nên không thể sửa chẩn đoán.",
            error_code="WORKFLOW_STATE_CLOSED",
        )

    if payload.error_category_id is not None:
        validate_error_category_exists(db, payload.error_category_id)
        ticket.error_category_id = payload.error_category_id

    ticket.diagnosis_note = payload.diagnosis_note.strip()
    ticket.diagnosis_by = acting_user.id
    ticket.diagnosis_at = datetime.utcnow()
    if payload.is_warranty_eligible is not None:
        ticket.is_warranty_eligible = payload.is_warranty_eligible
    if payload.warranty_check_note:
        ticket.warranty_check_note = payload.warranty_check_note.strip()

    db.commit()
    db.refresh(ticket)
    return ticket


def save_ticket_repair(
    db: Session,
    ticket_id: int,
    payload: TicketRepairUpdate,
    actor: Optional[User] = None,
) -> WarrantyTicket:
    """Ghi nhận nội dung sửa chữa & kiểm tra sau sửa của kỹ thuật viên mà không đổi trạng thái."""
    ticket = _get_ticket_or_404(db, ticket_id)
    acting_user = actor or validate_user_exists(db, payload.actor_id, "nhân viên sửa chữa")
    validate_ticket_actor_access(ticket, acting_user, is_technical=True)

    if ticket.status in ("COMPLETED", "RETURNED", "REJECTED"):
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"[WORKFLOW STATE ERROR] Phiếu đang ở trạng thái {ticket.status} nên không thể ghi nội dung sửa chữa.",
            user_message=f"Phiếu đã ở trạng thái \"{TICKET_STATUS_LABELS.get(ticket.status, ticket.status)}\" nên không thể ghi sửa chữa.",
            error_code="WORKFLOW_STATE_CLOSED",
        )

    content = (payload.repair_content or "").strip()
    note = (payload.repair_note or "").strip()
    parts = (payload.repair_parts or "").strip()
    if not (content or note):
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="[WORKFLOW INPUT REQUIRED] Thiếu repair_content/repair_note khi lưu nội dung sửa chữa.",
            user_message="Vui lòng ghi nội dung đã kiểm tra/đã sửa chữa (hoặc ghi chú kỹ thuật) trước khi lưu.",
            error_code="WORKFLOW_INPUT_REQUIRED",
        )

    now = datetime.utcnow()
    ticket.repair_content = content or ticket.repair_content
    ticket.repair_note = note or ticket.repair_note
    ticket.repair_parts = parts or ticket.repair_parts
    ticket.repair_by = acting_user.id
    ticket.repair_at = now
    if payload.repair_test_passed is not None:
        ticket.repair_test_passed = payload.repair_test_passed
    if payload.repair_test_note:
        ticket.repair_test_note = payload.repair_test_note.strip()

    db.add(
        RepairLog(
            ticket_id=ticket.id,
            technician_id=acting_user.id,
            action_description=content or note,
            parts_used=parts or None,
            logged_at=now,
        )
    )
    db.commit()
    db.refresh(ticket)
    return ticket


def apply_ticket_scope_filter(
    query,
    current_user: Optional[User] = None,
    scope: Optional[str] = None,
    mine: bool = False,
    mine_user_id: Optional[int] = None,
    service_center_id: Optional[int] = None,
):
    """
    Áp dụng bộ lọc phạm vi chuẩn theo vai trò và trung tâm:
    - Quản lý: Xem toàn bộ phiếu trong trung tâm bảo hành của mình.
    - Tiếp nhận: 'Việc tại quầy' (mine=True / scope='MINE') gồm các phiếu trong trung tâm
      ở trạng thái Tiếp nhận (RECEIVED), Hoàn tất (COMPLETED), hoặc Từ chối (REJECTED).
    - Kỹ thuật viên: 'Phiếu được giao' (mine=True / scope='MINE') CHỈ lấy phiếu có
      assigned_technician_id == user.id (không phụ thuộc người tạo hay lịch sử).
    - Giới hạn theo trung tâm (service_center_id) để không lộ chéo dữ liệu trung tâm khác.
    """
    # 1. Giới hạn trung tâm bảo hành
    center_id = None
    if current_user and getattr(current_user, "service_center_id", None):
        center_id = current_user.service_center_id
    elif service_center_id:
        center_id = service_center_id

    if center_id:
        query = query.filter(WarrantyTicket.service_center_id == center_id)

    # 2. Giới hạn phạm vi theo vai trò
    is_mine = mine or (scope and str(scope).upper() == "MINE")

    if is_mine:
        if current_user:
            if current_user.role == "TECHNICIAN":
                query = query.filter(WarrantyTicket.assigned_technician_id == current_user.id)
            elif current_user.role == "RECEPTIONIST":
                query = query.filter(WarrantyTicket.status.in_(["RECEIVED", "COMPLETED", "REJECTED"]))
            else:
                # Quản lý giữ nguyên phạm vi toàn trung tâm
                pass
        elif mine_user_id is not None:
            query = query.filter(WarrantyTicket.assigned_technician_id == mine_user_id)
    elif mine_user_id is not None and not (scope and str(scope).upper() == "ALL"):
        query = query.filter(WarrantyTicket.assigned_technician_id == mine_user_id)

    return query


def get_warranty_tickets(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    status_filter: Optional[str] = None,
    keyword: Optional[str] = None,
    current_user: Optional[User] = None,
    scope: Optional[str] = None,
    mine: bool = False,
    mine_user_id: Optional[int] = None,
    service_center_id: Optional[int] = None,
) -> List[WarrantyTicket]:
    """
    Danh sách phiếu bảo hành.
    - Lọc theo vai trò (Phiếu được giao cho KTV / Việc tại quầy cho Tiếp nhận / Toàn trung tâm cho Quản lý).
    - Giới hạn trong trung tâm bảo hành của tài khoản đăng nhập.
    - `keyword`: tìm theo mã phiếu, số sê-ri, tên khách hàng, số điện thoại.
    """
    query = (
        db.query(WarrantyTicket)
        .outerjoin(ProductInstance, WarrantyTicket.product_instance_id == ProductInstance.id)
        .outerjoin(Customer, WarrantyTicket.customer_id == Customer.id)
    )

    query = apply_ticket_scope_filter(
        query,
        current_user=current_user,
        scope=scope,
        mine=mine,
        mine_user_id=mine_user_id,
        service_center_id=service_center_id,
    )

    if status_filter:
        values = [v.strip().upper() for v in str(status_filter).split(",") if v.strip()]
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
    db: Session,
    current_user: Optional[User] = None,
    scope: Optional[str] = None,
    mine: bool = False,
    mine_user_id: Optional[int] = None,
    service_center_id: Optional[int] = None,
) -> Dict[str, int]:
    """
    Đếm phiếu theo từng trạng thái tuân thủ đúng phạm vi vai trò và trung tâm bảo hành.
    Luôn trả về đủ 6 trạng thái để Tổng phiếu = sum(các nhóm) nhất quán 100%.
    """
    query = db.query(WarrantyTicket.status, func.count(WarrantyTicket.id))
    query = apply_ticket_scope_filter(
        query,
        current_user=current_user,
        scope=scope,
        mine=mine,
        mine_user_id=mine_user_id,
        service_center_id=service_center_id,
    )
    counts = dict(query.group_by(WarrantyTicket.status).all())
    all_statuses = ["RECEIVED", "INSPECTING", "REPAIRING", "COMPLETED", "REJECTED", "RETURNED"]
    return {st: int(counts.get(st, 0)) for st in all_statuses}


def last_handler_subquery(db: Session):
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


def _get_ticket_or_404(db: Session, ticket_id: int) -> WarrantyTicket:
    ticket = get_warranty_ticket(db, ticket_id)
    if not ticket:
        raise BusinessRuleError(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy phiếu bảo hành có ID: {ticket_id}",
            user_message="Không tìm thấy phiếu bảo hành này.",
            error_code="TICKET_NOT_FOUND",
        )
    return ticket
