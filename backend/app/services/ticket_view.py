"""
Tầng HIỂN THỊ NGHIỆP VỤ PHIẾU BẢO HÀNH (Chuẩn 6 trạng thái).

Luồng sửa chữa: Tiếp nhận -> Kiểm tra -> Sửa chữa -> Hoàn tất -> Đã trả máy.
Luồng từ chối : Tiếp nhận -> Kiểm tra -> Từ chối -> Đã trả máy.

Quyền thao tác per-ticket:
- Kỹ thuật viên chỉ có nút thao tác trên phiếu được phân công cho mình.
- Tiếp nhận xác nhận trả máy từ Hoàn tất hoặc Từ chối.
- Quản lý duyệt từ chối, phân công KTV.
"""
from datetime import date, datetime
from typing import Any, Callable, Dict, Iterable, List, Optional
from sqlalchemy.orm import Session

from app.models import AIResult, ErrorCategory, RepairLog, User, WarrantyTicket
from app.services.auth_service import (
    PERM_TICKET_DIAGNOSE,
    PERM_TICKET_HANDOVER,
    PERM_TICKET_REPAIR,
    PERM_TICKET_REJECT,
    PERM_TICKET_UPDATE_STATUS,
    ROLE_MANAGER,
    ROLE_RECEPTIONIST,
    ROLE_TECHNICIAN,
    has_permission,
)
from app.services.warranty_rules import (
    TICKET_STATUS_HINTS,
    TICKET_STATUS_LABELS,
    TICKET_STEPS,
    available_transitions,
    completion_blockers,
    completion_checklist,
)

# Trạng thái còn cho phép bổ sung thông tin chuyên môn
EDITABLE_WORKFLOW_STATUSES = ("RECEIVED", "INSPECTING", "REPAIRING")

AI_SUGGESTION_DISCLAIMER = (
    "AI chỉ gợi ý loại lỗi. Kết luận cuối cùng phải do nhân viên có quyền xác nhận."
)

READ_ONLY_ACTION_LABELS: Dict[str, str] = {
    "COMPLETED": "Xem chi tiết",
    "REJECTED": "Xem chi tiết",
    "RETURNED": "Xem chi tiết",
    "INSPECTING": "Xem chi tiết",
    "REPAIRING": "Xem chi tiết",
    "RECEIVED": "Xem chi tiết",
}
DEFAULT_READ_ONLY_LABEL = "Xem chi tiết"

PRIMARY_ACTION_PRIORITY = [
    "COMPLETED",
    "RETURNED",
    "REPAIRING",
    "INSPECTING",
    "REJECTED",
]

PERMISSION_LABELS: Dict[str, str] = {
    PERM_TICKET_UPDATE_STATUS: "cập nhật tình trạng phiếu",
    PERM_TICKET_REJECT: "xác nhận từ chối bảo hành (chỉ Quản lý)",
    PERM_TICKET_HANDOVER: "xác nhận đã trả máy cho khách (Tiếp nhận hoặc Quản lý)",
    PERM_TICKET_DIAGNOSE: "ghi nhận chẩn đoán (Kỹ thuật viên hoặc Quản lý)",
    PERM_TICKET_REPAIR: "ghi nhận nội dung sửa chữa (Kỹ thuật viên hoặc Quản lý)",
}


def format_duration(seconds: Optional[float]) -> str:
    """Định dạng thời lượng: dưới 1 giờ hiển thị phút, trên 1 giờ hiển thị giờ."""
    if seconds is None:
        return "Chưa đủ dữ liệu"
    if seconds < 0:
        return "Chưa đủ dữ liệu (mốc thời gian không hợp lệ)"
    mins = round(seconds / 60.0)
    if mins < 60:
        return f"{max(1, mins)} phút"
    h = mins // 60
    rem_mins = mins % 60
    if rem_mins > 0:
        return f"{h} giờ {rem_mins} phút"
    return f"{h} giờ"


def permission_notes(
    current_status: str,
    permission_check: Callable[[str], bool],
    is_assigned_to_actor: bool = True,
    actor_is_tech: bool = False,
) -> List[str]:
    notes: List[str] = []
    if actor_is_tech and not is_assigned_to_actor:
        notes.append("Phiếu này được phân công cho kỹ thuật viên khác. Bạn đang ở chế độ chỉ xem.")
    return notes


def _user_name_map(db: Session, user_ids: Iterable[Optional[int]]) -> Dict[int, str]:
    ids = {int(uid) for uid in user_ids if uid is not None}
    if not ids:
        return {}
    rows = db.query(User.id, User.full_name).filter(User.id.in_(ids)).all()
    return {row[0]: row[1] for row in rows}


def _category_name(db: Session, category_id: Optional[int]) -> Optional[str]:
    if category_id is None:
        return None
    row = db.query(ErrorCategory).filter(ErrorCategory.id == category_id).first()
    return row.name if row else None


def warranty_status_info(end_date: Optional[date], check_date: Optional[date] = None) -> Dict[str, Any]:
    if end_date is None:
        return {
            "status": "Không xác định",
            "message": "Thiết bị chưa có thông tin hạn bảo hành.",
            "days_remaining": None,
        }
    ref = check_date or date.today()
    days = (end_date - ref).days
    if days >= 0:
        msg = f"Còn hạn bảo hành tại ngày tiếp nhận (còn {days} ngày, hạn đến {end_date.strftime('%d/%m/%Y')})." if check_date else f"Còn bảo hành {days} ngày (hết hạn {end_date.strftime('%d/%m/%Y')})."
        return {
            "status": "Còn bảo hành",
            "message": msg,
            "days_remaining": days,
        }
    msg = f"Đã hết hạn bảo hành {abs(days)} ngày tại ngày tiếp nhận (hết hạn {end_date.strftime('%d/%m/%Y')})." if check_date else f"Đã hết hạn bảo hành {abs(days)} ngày (hết hạn {end_date.strftime('%d/%m/%Y')})."
    return {
        "status": "Đã hết hạn",
        "message": msg,
        "days_remaining": days,
    }


def latest_ai_result(db: Session, ticket_id: int) -> Optional[AIResult]:
    return (
        db.query(AIResult)
        .filter(AIResult.ticket_id == ticket_id, AIResult.ai_function == "ERROR_CLASSIFICATION")
        .order_by(AIResult.id.desc())
        .first()
    )


def build_ai_suggestion(db: Session, ticket_id: int) -> Dict[str, Any]:
    result = latest_ai_result(db, ticket_id)
    if result is None:
        return {
            "available": False,
            "message": "Chưa có gợi ý loại lỗi cho phiếu này.",
        }

    output = result.output_data or {}
    suggested_id = output.get("suggested_category_id")
    need_more = list(output.get("need_more_information") or [])
    if suggested_id is None:
        message = "Chưa đủ thông tin để gợi ý loại lỗi."
        if need_more:
            message += " Vui lòng hỏi thêm khách hàng: " + "; ".join(need_more)
        confidence = None
    else:
        message = (
            "Gợi ý loại lỗi từ hệ thống AI (tham khảo). "
            "Kỹ thuật viên phụ trách xác nhận loại lỗi chính thức."
        )
        confidence = float(result.confidence_score) if result.confidence_score is not None else None

    input_data = result.input_data or {}
    provider_name = input_data.get("provider", "mock")
    is_simulation = (provider_name == "mock")
    simulation_label = "Chế độ mô phỏng" if is_simulation else f"Mô hình AI: {provider_name}"

    return {
        "available": True,
        "ai_result_id": result.id,
        "suggested_category_id": suggested_id,
        "suggested_category_name": output.get("suggested_category_name") or _category_name(db, suggested_id),
        "confidence": confidence,
        "reason": output.get("reason"),
        "review_status": result.review_status,
        "provider": provider_name,
        "is_simulation": is_simulation,
        "simulation_label": simulation_label,
        "created_at": result.created_at,
        "need_more_information": need_more,
        "message": message,
    }


def build_history(db: Session, ticket: WarrantyTicket) -> List[Dict[str, Any]]:
    history = list(ticket.status_history or [])
    name_map = _user_name_map(db, [row.changed_by for row in history])
    return [
        {
            "id": row.id,
            "ticket_id": row.ticket_id,
            "from_status": row.from_status,
            "to_status": row.to_status,
            "from_label": TICKET_STATUS_LABELS.get(row.from_status) if row.from_status else None,
            "to_label": TICKET_STATUS_LABELS.get(row.to_status, row.to_status),
            "changed_by": row.changed_by,
            "changed_by_name": name_map.get(row.changed_by),
            "note": row.note,
            "created_at": row.created_at,
        }
        for row in history
    ]


ASSIGN_ACTION: Dict[str, Any] = {
    "target": "ASSIGN",
    "target_label": "Phân công kỹ thuật viên",
    "button_label": "Phân công kỹ thuật viên",
    "confirm_question": "Phân công kỹ thuật viên phụ trách phiếu?",
    "description": "Chỉ định kỹ thuật viên chịu trách nhiệm kiểm tra và sửa chữa thiết bị.",
    "style": "primary",
    "fields": ["technician_id", "note"],
    "requires_input": True,
    "requires_rejection_reason": False,
    "note_label": "Ghi chú phân công (không bắt buộc)",
    "note_placeholder": "Ví dụ: Giao KTV kiểm tra nguồn và mainboard",
    "permission": PERM_TICKET_UPDATE_STATUS,
}

REASSIGN_ACTION: Dict[str, Any] = {
    "target": "ASSIGN",
    "target_label": "Phân công lại KTV",
    "button_label": "Phân công lại KTV",
    "confirm_question": "Phân công lại kỹ thuật viên phụ trách phiếu?",
    "description": "Chỉ định kỹ thuật viên khác chịu trách nhiệm kiểm tra và sửa chữa thiết bị.",
    "style": "primary",
    "fields": ["technician_id", "note"],
    "requires_input": True,
    "requires_rejection_reason": False,
    "note_label": "Ghi chú phân công lại",
    "note_placeholder": "Ví dụ: Điều chuyển KTV xử lý phần cứng",
    "permission": PERM_TICKET_UPDATE_STATUS,
}


def build_row_action(
    ticket: WarrantyTicket,
    current_user: Optional[User] = None,
) -> Dict[str, Any]:
    """Nút hành động theo vai trò và kiểm tra quyền per-ticket."""
    if current_user is None:
        return {
            "available_actions": [],
            "primary_action": None,
            "action_label": READ_ONLY_ACTION_LABELS.get(ticket.status, DEFAULT_READ_ONLY_LABEL),
            "action_kind": "read_only",
        }

    # 1. Đã trả máy (RETURNED): chỉ xem chi tiết và lịch sử
    if ticket.status == "RETURNED":
        return {
            "available_actions": [],
            "primary_action": None,
            "action_label": "Xem chi tiết",
            "action_kind": "read_only",
        }

    # 2. Hoàn tất hoặc Từ chối (COMPLETED / REJECTED):
    # Người có quyền PERM_TICKET_HANDOVER (Tiếp nhận hoặc Quản lý) thấy "Xác nhận trả máy".
    # Kỹ thuật viên không có quyền trả máy -> chỉ xem phiếu.
    if ticket.status in ("COMPLETED", "REJECTED"):
        actions = available_transitions(ticket.status, lambda p: has_permission(current_user, p))
        primary = next((action for action in actions if action["target"] == "RETURNED"), None)
        if primary is not None:
            return {
                "available_actions": actions,
                "primary_action": primary,
                "action_label": primary["button_label"],
                "action_kind": "transition",
            }
        return {
            "available_actions": [],
            "primary_action": None,
            "action_label": "Xem chi tiết",
            "action_kind": "read_only",
        }

    # 3. Phiếu đang ở bước xử lý kỹ thuật (RECEIVED, INSPECTING, REPAIRING):
    is_unassigned = ticket.assigned_technician_id is None

    # 3A. Phiếu CHƯA có KTV phụ trách:
    if is_unassigned:
        if current_user.role == ROLE_MANAGER:
            return {
                "available_actions": [ASSIGN_ACTION],
                "primary_action": ASSIGN_ACTION,
                "action_label": "Phân công kỹ thuật viên",
                "action_kind": "transition",
            }
        elif current_user.role == ROLE_RECEPTIONIST:
            return {
                "available_actions": [],
                "primary_action": None,
                "action_label": "Xem chi tiết",
                "action_kind": "read_only",
            }
        else:
            return {
                "available_actions": [],
                "primary_action": None,
                "action_label": "Xem chi tiết",
                "action_kind": "read_only",
            }

    # 3B. Phiếu ĐÃ có KTV phụ trách:
    if current_user.role == ROLE_TECHNICIAN:
        # Kỹ thuật viên không được thao tác trên phiếu của người khác
        if ticket.assigned_technician_id != current_user.id:
            return {
                "available_actions": [],
                "primary_action": None,
                "action_label": "Xem chi tiết",
                "action_kind": "read_only",
            }
        # KTV được phân công: hiển thị hành động chuyển bước theo trạng thái
        actions = available_transitions(ticket.status, lambda p: has_permission(current_user, p))
        primary = None
        for target in PRIMARY_ACTION_PRIORITY:
            primary = next((action for action in actions if action["target"] == target), None)
            if primary is not None:
                break
        if primary is None and actions:
            primary = actions[0]
        return {
            "available_actions": actions,
            "primary_action": primary,
            "action_label": primary["button_label"] if primary else "Xem chi tiết",
            "action_kind": "transition" if primary else "read_only",
        }

    elif current_user.role == ROLE_RECEPTIONIST:
        # Tiếp nhận không kiểm tra / sửa chữa máy: chỉ xem chi tiết phiếu
        return {
            "available_actions": [],
            "primary_action": None,
            "action_label": "Xem chi tiết",
            "action_kind": "read_only",
        }

    else:
        # Quản lý (MANAGER) với phiếu đã có KTV:
        actions = available_transitions(ticket.status, lambda p: has_permission(current_user, p))
        primary = None
        for target in PRIMARY_ACTION_PRIORITY:
            primary = next((action for action in actions if action["target"] == target), None)
            if primary is not None:
                break
        if primary is None and actions:
            primary = actions[0]

        available = list(actions)
        if not any(a["target"] == "ASSIGN" for a in available):
            available.append(REASSIGN_ACTION)

        return {
            "available_actions": available,
            "primary_action": primary or REASSIGN_ACTION,
            "action_label": primary["button_label"] if primary else REASSIGN_ACTION["button_label"],
            "action_kind": "transition",
        }


def build_ticket_summary(
    db: Session,
    ticket: WarrantyTicket,
    name_map: Optional[Dict[int, str]] = None,
    category_map: Optional[Dict[int, str]] = None,
    current_user: Optional[User] = None,
) -> Dict[str, Any]:
    history = list(ticket.status_history or [])
    last_step = history[-1] if history else None
    handler_id = last_step.changed_by if last_step else ticket.created_by

    needed_user_ids = [ticket.created_by, handler_id, ticket.assigned_technician_id]
    if name_map is None:
        name_map = _user_name_map(db, needed_user_ids)
    if category_map is None:
        category_map = {}
        if ticket.error_category_id is not None:
            name = _category_name(db, ticket.error_category_id)
            if name:
                category_map[ticket.error_category_id] = name

    instance = ticket.product_instance
    product = instance.product if instance is not None and instance.product is not None else None
    customer = ticket.customer

    row_action = build_row_action(ticket, current_user)

    return {
        "id": ticket.id,
        "ticket_code": ticket.ticket_code,
        "product_instance_id": ticket.product_instance_id,
        "customer_id": ticket.customer_id,
        "service_center_id": ticket.service_center_id,
        "created_by": ticket.created_by,
        "issue_description": ticket.issue_description,
        "device_condition": getattr(ticket, "device_condition", None),
        "accessories_accompanying": getattr(ticket, "accessories_accompanying", None),
        "error_category_id": ticket.error_category_id,
        "status": ticket.status,
        "status_label": TICKET_STATUS_LABELS.get(ticket.status, ticket.status),
        "status_hint": TICKET_STATUS_HINTS.get(ticket.status, ""),
        "assigned_technician_id": ticket.assigned_technician_id,
        "assigned_technician_name": name_map.get(ticket.assigned_technician_id) if ticket.assigned_technician_id else None,
        "assigned_at": ticket.assigned_at,
        "is_warranty_eligible": ticket.is_warranty_eligible,
        "warranty_check_note": ticket.warranty_check_note,
        "repair_test_passed": ticket.repair_test_passed,
        "repair_test_note": ticket.repair_test_note,
        "rejection_reason": ticket.rejection_reason,
        "rejection_proposed_by": ticket.rejection_proposed_by,
        "rejection_proposed_at": ticket.rejection_proposed_at,
        "rejection_proposal_note": ticket.rejection_proposal_note,
        "rejection_reviewed_by": ticket.rejection_reviewed_by,
        "rejection_reviewed_at": ticket.rejection_reviewed_at,
        "rejection_review_status": ticket.rejection_review_status,
        "completed_at": ticket.completed_at,
        "handed_over_at": ticket.handed_over_at,
        "handed_over_by": ticket.handed_over_by,
        "handover_note": ticket.handover_note,
        "resolution": ticket.resolution,
        "serial_number": instance.serial_number if instance is not None else None,
        "product_name": product.name if product is not None else None,
        "product_brand": product.brand if product is not None else None,
        "customer_name": customer.full_name if customer is not None else None,
        "customer_phone": customer.phone if customer is not None else None,
        "warranty_end_date": instance.warranty_end_date if instance is not None else None,
        "error_category_name": category_map.get(ticket.error_category_id),
        "handler_id": handler_id,
        "handler_name": name_map.get(handler_id) if handler_id is not None else None,
        "available_actions": row_action["available_actions"],
        "primary_action": row_action["primary_action"],
        "action_label": row_action["action_label"],
        "action_kind": row_action["action_kind"],
        "status_history": build_history(db, ticket),
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
    }


def build_ticket_summaries(
    db: Session,
    tickets: List[WarrantyTicket],
    current_user: Optional[User] = None,
) -> List[Dict[str, Any]]:
    if not tickets:
        return []
    user_ids: List[Optional[int]] = [t.created_by for t in tickets]
    user_ids.extend(t.assigned_technician_id for t in tickets)
    user_ids.extend(row.changed_by for t in tickets for row in (t.status_history or []))
    name_map = _user_name_map(db, user_ids)

    category_ids = {t.error_category_id for t in tickets if t.error_category_id is not None}
    category_map: Dict[int, str] = {}
    if category_ids:
        rows = (
            db.query(ErrorCategory.id, ErrorCategory.name)
            .filter(ErrorCategory.id.in_(category_ids))
            .all()
        )
        category_map = {row[0]: row[1] for row in rows}

    return [
        build_ticket_summary(db, t, name_map, category_map, current_user=current_user)
        for t in tickets
    ]


def build_workflow_steps(db: Session, ticket: WarrantyTicket) -> List[Dict[str, Any]]:
    """Tiến trình hiển thị các bước (sửa chữa hoặc từ chối)."""
    history = list(ticket.status_history or [])
    name_map = _user_name_map(db, [row.changed_by for row in history])
    reached: Dict[str, Dict[str, Any]] = {}
    for row in history:
        reached[row.to_status] = {
            "at": row.created_at,
            "by_name": name_map.get(row.changed_by),
            "note": row.note,
            "from_label": TICKET_STATUS_LABELS.get(row.from_status) if row.from_status else None,
        }

    # Luồng từ chối
    is_rejected_flow = (ticket.status == "REJECTED" or ticket.resolution == "REJECTED")
    if is_rejected_flow:
        custom_steps = [
            {"step": 1, "status": "RECEIVED", "label": "Tiếp nhận"},
            {"step": 2, "status": "INSPECTING", "label": "Kiểm tra"},
            {"step": 3, "status": "REJECTED", "label": "Từ chối"},
            {"step": 4, "status": "RETURNED", "label": "Đã trả máy"},
        ]
        order = ["RECEIVED", "INSPECTING", "REJECTED", "RETURNED"]
    else:
        custom_steps = TICKET_STEPS
        order = [step["status"] for step in TICKET_STEPS]

    if ticket.status in order:
        current_index = order.index(ticket.status)
    else:
        current_index = 0

    steps: List[Dict[str, Any]] = []
    for index, step in enumerate(custom_steps):
        done = reached.get(step["status"])
        if index < current_index:
            state = "done"
        elif index == current_index:
            state = "current"
        else:
            state = "pending"
        steps.append(
            {
                "step": step["step"],
                "status": step["status"],
                "label": step["label"],
                "state": state,
                "at": done["at"] if done else None,
                "by_name": done["by_name"] if done else None,
                "note": done["note"] if done else None,
            }
        )
    return steps


def build_repair_logs(db: Session, ticket: WarrantyTicket) -> List[Dict[str, Any]]:
    logs = (
        db.query(RepairLog)
        .filter(RepairLog.ticket_id == ticket.id)
        .order_by(RepairLog.id.asc())
        .all()
    )
    name_map = _user_name_map(db, [log.technician_id for log in logs])
    return [
        {
            "id": log.id,
            "technician_id": log.technician_id,
            "technician_name": name_map.get(log.technician_id),
            "action_description": log.action_description,
            "parts_used": log.parts_used,
            "logged_at": log.logged_at,
        }
        for log in logs
    ]


def build_ticket_detail(
    db: Session, ticket: WarrantyTicket, current_user: Optional[User] = None
) -> Dict[str, Any]:
    """Màn hình chi tiết phiếu đầy đủ thông tin A-G, tính thời gian xử lý và chờ nhận."""
    if current_user is None:
        permission_check: Callable[[str], bool] = lambda _p: False
    else:
        permission_check = lambda p: has_permission(current_user, p)

    detail = build_ticket_summary(db, ticket, current_user=current_user)
    history = build_history(db, ticket)
    instance = ticket.product_instance
    product = instance.product if instance is not None and instance.product is not None else None
    customer = ticket.customer

    needed_ids = [
        ticket.created_by,
        ticket.diagnosis_by,
        ticket.repair_by,
        ticket.handed_over_by,
        ticket.assigned_technician_id,
        ticket.rejection_proposed_by,
        ticket.rejection_reviewed_by,
    ]
    name_map = _user_name_map(db, needed_ids)
    ref_intake_date = ticket.created_at.date() if ticket.created_at else date.today()
    warranty = warranty_status_info(instance.warranty_end_date if instance is not None else None, check_date=ref_intake_date)
    blockers = completion_blockers(db, ticket)

    # Tính thời gian xử lý kỹ thuật và thời gian chờ khách nhận máy
    processing_time_hours = None
    processing_time_display = "Chưa đủ dữ liệu"
    tech_finish_at = ticket.completed_at or ticket.rejection_reviewed_at
    if tech_finish_at and ticket.created_at:
        delta_sec = (tech_finish_at - ticket.created_at).total_seconds()
        if delta_sec >= 0:
            processing_time_hours = round(delta_sec / 3600.0, 1)
            processing_time_display = format_duration(delta_sec)
        else:
            processing_time_display = "Chưa đủ dữ liệu (mốc thời gian sai thứ tự)"

    waiting_time_hours = None
    waiting_time_display = "Chưa đủ dữ liệu"
    if tech_finish_at:
        if ticket.handed_over_at:
            delta_wait_sec = (ticket.handed_over_at - tech_finish_at).total_seconds()
            if delta_wait_sec >= 0:
                waiting_time_hours = round(delta_wait_sec / 3600.0, 1)
                waiting_time_display = format_duration(delta_wait_sec)
            else:
                waiting_time_display = "Chưa đủ dữ liệu (mốc thời gian sai thứ tự)"
        elif ticket.status in ("COMPLETED", "REJECTED"):
            delta_wait_sec = (datetime.utcnow() - tech_finish_at).total_seconds()
            if delta_wait_sec >= 0:
                waiting_time_hours = round(delta_wait_sec / 3600.0, 1)
                waiting_time_display = format_duration(delta_wait_sec)
            else:
                waiting_time_display = "Chưa đủ dữ liệu (mốc thời gian sai thứ tự)"

    is_assigned = True
    actor_is_tech = False
    if current_user:
        actor_is_tech = (current_user.role == "TECHNICIAN")
        if actor_is_tech and ticket.assigned_technician_id:
            is_assigned = (ticket.assigned_technician_id == current_user.id)

    row_action = build_row_action(ticket, current_user)

    detail.update(
        {
            "status_label": TICKET_STATUS_LABELS.get(ticket.status, ticket.status),
            "status_hint": TICKET_STATUS_HINTS.get(ticket.status, ""),
            "steps": build_workflow_steps(db, ticket),
            "history": history,
            "customer": (
                {
                    "id": customer.id,
                    "full_name": customer.full_name,
                    "phone": customer.phone,
                    "email": customer.email,
                }
                if customer is not None
                else None
            ),
            "intake": {
                "received_at": ticket.created_at,
                "received_by": ticket.created_by,
                "received_by_name": name_map.get(ticket.created_by),
                "issue_description": ticket.issue_description,
                "device_condition": getattr(ticket, "device_condition", None),
                "accessories_accompanying": getattr(ticket, "accessories_accompanying", None),
                "assigned_technician_id": ticket.assigned_technician_id,
                "assigned_technician_name": name_map.get(ticket.assigned_technician_id) if ticket.assigned_technician_id else None,
                "assigned_at": ticket.assigned_at,
            },
            "diagnosis": {
                "note": ticket.diagnosis_note,
                "error_category_id": ticket.error_category_id,
                "error_category_name": detail.get("error_category_name"),
                "confirmed_by": ticket.diagnosis_by,
                "confirmed_by_name": name_map.get(ticket.diagnosis_by) if ticket.diagnosis_by else None,
                "confirmed_at": ticket.diagnosis_at,
                "is_warranty_eligible": ticket.is_warranty_eligible,
                "warranty_check_note": ticket.warranty_check_note,
                "rejection_proposal_note": ticket.rejection_proposal_note,
                "rejection_proposed_by": ticket.rejection_proposed_by,
                "rejection_proposed_by_name": name_map.get(ticket.rejection_proposed_by) if ticket.rejection_proposed_by else None,
                "rejection_proposed_at": ticket.rejection_proposed_at,
            },
            "ai_suggestion": build_ai_suggestion(db, ticket.id),
            "device": (
                {
                    "id": instance.id,
                    "serial_number": instance.serial_number,
                    "product_name": product.name if product is not None else None,
                    "brand": product.brand if product is not None else None,
                    "category": product.category if product is not None else None,
                    "purchase_date": instance.purchase_date,
                    "warranty_end_date": instance.warranty_end_date,
                    "warranty_status": warranty["status"],
                    "warranty_status_message": warranty["message"],
                    "days_remaining": warranty["days_remaining"],
                }
                if instance is not None
                else None
            ),
            "repair": {
                "content": ticket.repair_content,
                "parts": ticket.repair_parts,
                "note": ticket.repair_note,
                "technician_id": ticket.repair_by,
                "technician_name": name_map.get(ticket.repair_by) if ticket.repair_by else None,
                "recorded_at": ticket.repair_at,
                "repair_test_passed": ticket.repair_test_passed,
                "repair_test_note": ticket.repair_test_note,
                "logs": build_repair_logs(db, ticket),
            },
            "handover": {
                "is_waiting_handover": ticket.status in ("COMPLETED", "REJECTED"),
                "is_waiting_return": ticket.status == "COMPLETED",
                "is_returned": ticket.status == "RETURNED",
                "status_message": (
                    "Thiết bị đã sửa xong, đang chờ khách nhận máy."
                    if ticket.status == "COMPLETED"
                    else (
                        "Thiết bị bị từ chối bảo hành, đang chờ trả máy cho khách."
                        if ticket.status == "REJECTED"
                        else (
                            "Thiết bị đã được bàn giao cho khách, phiếu đã đóng."
                            if ticket.status == "RETURNED"
                            else TICKET_STATUS_HINTS.get(ticket.status, "")
                        )
                    )
                ),
                "completed_at": ticket.completed_at,
                "repair_completed_at": ticket.completed_at,
                "repair_completed_by_name": name_map.get(ticket.repair_by) if ticket.repair_by else None,
                "returned_at": ticket.handed_over_at,
                "returned_by_name": name_map.get(ticket.handed_over_by) if ticket.handed_over_by else None,
                "note": ticket.handover_note,
                "resolution": ticket.resolution,
                "resolution_label": (
                    "Đã sửa xong hoàn tất"
                    if ticket.resolution == "COMPLETED"
                    else ("Từ chối bảo hành" if ticket.resolution == "REJECTED" else None)
                ),
                "processing_time_hours": processing_time_hours,
                "waiting_time_hours": waiting_time_hours,
                "processing_time_display": processing_time_display,
                "waiting_time_display": waiting_time_display,
            },
            "available_actions": row_action["available_actions"],
            "completion_checklist": completion_checklist(ticket),
            "can_complete": len(blockers) == 0,
            "completion_blockers": blockers,
            "can_edit_diagnosis": bool(permission_check(PERM_TICKET_DIAGNOSE))
            and ticket.status in EDITABLE_WORKFLOW_STATUSES
            and (not actor_is_tech or is_assigned),
            "can_edit_repair": bool(permission_check(PERM_TICKET_REPAIR))
            and ticket.status in EDITABLE_WORKFLOW_STATUSES
            and (not actor_is_tech or is_assigned),
            "permission_notes": permission_notes(ticket.status, permission_check, is_assigned, actor_is_tech),
        }
    )
    return detail


def build_role_workload(
    role: Optional[str], counts: Dict[str, int], mine: bool = False
) -> List[Dict[str, Any]]:
    """Danh sách việc cần làm theo vai trò."""
    if role == "TECHNICIAN":
        definitions = [
            ("RECEIVED", "Phiếu chờ kiểm tra", "Máy đã tiếp nhận tại quầy, cần kiểm tra."),
            ("INSPECTING", "Phiếu đang kiểm tra", "Cần ghi chẩn đoán và xác định điều kiện bảo hành."),
            ("REPAIRING", "Phiếu đang sửa chữa", "Sửa xong thì chuyển phiếu sang Hoàn tất."),
            ("COMPLETED", "Phiếu đã sửa xong", "Đã hoàn tất kiểm tra sau sửa, chờ khách tới nhận."),
        ]
    elif role == "RECEPTIONIST":
        definitions = [
            ("RECEIVED", "Phiếu chờ tiếp nhận", "Máy vừa tiếp nhận: phân công KTV và chuyển kiểm tra."),
            ("COMPLETED", "Phiếu chờ trả máy (Hoàn tất)", "Máy đã sửa xong: gọi khách nhận và xác nhận trả máy."),
            ("REJECTED", "Phiếu chờ trả máy (Từ chối)", "Máy từ chối bảo hành: bàn giao trả lại cho khách."),
            ("INSPECTING", "Phiếu đang kiểm tra", "Theo dõi tiến độ để trả lời khách."),
            ("RETURNED", "Phiếu đã đóng", "Đã bàn giao cho khách."),
        ]
    else:  # MANAGER
        definitions = [
            ("RECEIVED", "Mới tiếp nhận", "Phiếu mới cần phân công và chuyển kiểm tra."),
            ("INSPECTING", "Đang kiểm tra", "Kỹ thuật viên đang xác định nguyên nhân."),
            ("REPAIRING", "Đang sửa chữa", "Máy đang được sửa chữa."),
            ("COMPLETED", "Hoàn tất (Chờ trả máy)", "Đã sửa xong đạt yêu cầu, chờ khách tới nhận."),
            ("REJECTED", "Từ chối (Chờ trả máy)", "Đã từ chối bảo hành, chờ trả máy cho khách."),
            ("RETURNED", "Đã trả máy", "Đã bàn giao cho khách, phiếu đã đóng."),
        ]

    return [
        {
            "status": status_code,
            "label": label,
            "description": description,
            "count": int(counts.get(status_code, 0)),
            "scope": "MINE" if mine else "ALL",
            "status_filter": status_code,
        }
        for status_code, label, description in definitions
    ]
