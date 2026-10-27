"""
Tầng HIỂN THỊ NGHIỆP VỤ PHIẾU (một màn hình xử lý cho mọi vai trò).

Module này chỉ ĐỌC dữ liệu và dựng payload cho giao diện:
    * Khối A-G: khách hàng, thiết bị, tiếp nhận, chẩn đoán, gợi ý AI, sửa chữa, trả máy, lịch sử.
    * `available_actions`: các nút hành động mà NGƯỜI ĐANG ĐĂNG NHẬP được phép bấm.
    * `completion_checklist` / `completion_blockers`: điều kiện hoàn tất phiếu.

Mọi nhãn trạng thái trả ra đều là TIẾNG VIỆT (không trả mã enum cho giao diện
hiển thị), nhưng vẫn giữ trường mã (`status`) để frontend đối chiếu logic.
"""
from datetime import date
from typing import Any, Callable, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from app.models import AIResult, ErrorCategory, RepairLog, User, WarrantyTicket
from app.services.auth_service import (
    PERM_TICKET_DIAGNOSE,
    PERM_TICKET_HANDOVER,
    PERM_TICKET_REPAIR,
    PERM_TICKET_REJECT,
    PERM_TICKET_UPDATE_STATUS,
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

# Trạng thái còn cho phép bổ sung thông tin chuyên môn (chưa kết thúc vòng đời phiếu)
EDITABLE_WORKFLOW_STATUSES = ("RECEIVED", "INSPECTING", "REPAIRING", "WAITING_RETURN")

AI_SUGGESTION_DISCLAIMER = (
    "AI chỉ gợi ý loại lỗi. Kết luận cuối cùng phải do nhân viên có quyền xác nhận."
)

# Nhãn nút khi vai trò hiện tại KHÔNG có bước chuyển nào (chỉ được xem phiếu).
# Câu chữ nói rõ việc tiếp theo nằm ở đâu để nhân viên biết bàn cho ai.
READ_ONLY_ACTION_LABELS: Dict[str, str] = {
    "WAITING_RETURN": "Xem thông tin trả máy",
    "COMPLETED": "Xem phiếu",
    "REJECTED": "Xem phiếu",
}
DEFAULT_READ_ONLY_LABEL = "Xem phiếu"

# Thứ tự ưu tiên chọn HÀNH ĐỘNG CHÍNH của một dòng danh sách:
# bước tiến của quy trình trước (sửa xong -> trả máy -> kiểm tra -> ...),
# cuối cùng mới tới các bước "lùi" (sửa lại / kiểm tra lại / từ chối).
PRIMARY_ACTION_PRIORITY = [
    "WAITING_RETURN",
    "COMPLETED",
    "REPAIRING",
    "INSPECTING",
    "REJECTED",
]

# Nhãn tiếng Việt của từng mã quyền (dùng cho câu giải thích khi thiếu quyền)
PERMISSION_LABELS: Dict[str, str] = {
    PERM_TICKET_UPDATE_STATUS: "cập nhật tình trạng phiếu",
    PERM_TICKET_REJECT: "xác nhận từ chối bảo hành (chỉ Quản lý)",
    PERM_TICKET_HANDOVER: "xác nhận đã trả máy cho khách (Tiếp nhận hoặc Quản lý)",
    PERM_TICKET_DIAGNOSE: "ghi nhận chẩn đoán (Kỹ thuật viên hoặc Quản lý)",
    PERM_TICKET_REPAIR: "ghi nhận nội dung sửa chữa (Kỹ thuật viên hoặc Quản lý)",
}


def permission_notes(current_status: str, permission_check: Callable[[str], bool]) -> List[str]:
    """
    Giải thích vì sao một số bước KHÔNG hiện nút với vai trò hiện tại.

    Nhờ vậy nhân viên hiểu ngay "việc này của ai" thay vì thấy màn hình trống.
    """
    notes: List[str] = []
    for action in available_transitions(current_status, lambda _permission: True):
        if permission_check(action["permission"]):
            continue
        needed = PERMISSION_LABELS.get(action["permission"], action["permission"])
        notes.append(
            f"Thao tác \"{action['button_label']}\" cần quyền {needed}, "
            "nên không hiển thị với vai trò đang đăng nhập."
        )
    return notes


def _user_name_map(db: Session, user_ids: Iterable[Optional[int]]) -> Dict[int, str]:
    """Bảng tra ID nhân viên -> họ tên (một truy vấn duy nhất)."""
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


def warranty_status_info(end_date: Optional[date]) -> Dict[str, Any]:
    """Tình trạng bảo hành bằng tiếng Việt: nhãn + câu mô tả + số ngày còn lại."""
    if end_date is None:
        return {
            "status": "Không xác định",
            "message": "Thiết bị chưa có thông tin hạn bảo hành.",
            "days_remaining": None,
        }
    days = (end_date - date.today()).days
    if days >= 0:
        return {
            "status": "Còn bảo hành",
            "message": f"Còn bảo hành {days} ngày (hết hạn {end_date.strftime('%d/%m/%Y')}).",
            "days_remaining": days,
        }
    return {
        "status": "Đã hết hạn",
        "message": f"Đã hết hạn bảo hành {abs(days)} ngày (hết hạn {end_date.strftime('%d/%m/%Y')}).",
        "days_remaining": days,
    }


def latest_ai_result(db: Session, ticket_id: int) -> Optional[AIResult]:
    """Kết quả AI-01 mới nhất của phiếu (chỉ để GỢI Ý, không phải kết luận của phiếu)."""
    return (
        db.query(AIResult)
        .filter(AIResult.ticket_id == ticket_id)
        .order_by(AIResult.id.desc())
        .first()
    )


def build_ai_suggestion(db: Session, ticket_id: int) -> Dict[str, Any]:
    """Khối 'Gợi ý loại lỗi' của phiếu (tách biệt hoàn toàn với kết luận của kỹ thuật viên)."""
    result = latest_ai_result(db, ticket_id)
    if result is None:
        return {
            "available": False,
            "message": (
                "Chưa có gợi ý loại lỗi cho phiếu này. Nếu cần, bấm \"Gợi ý loại lỗi\" "
                "để hệ thống tham khảo mô tả lỗi của khách."
            ),
        }

    output = result.output_data or {}
    suggested_id = output.get("suggested_category_id")
    need_more = list(output.get("need_more_information") or [])
    if suggested_id is None:
        message = "Chưa đủ thông tin để gợi ý loại lỗi."
        if need_more:
            message += " Vui lòng hỏi thêm khách hàng: " + "; ".join(need_more)
        else:
            message += " Vui lòng hỏi thêm khách hàng về hiện tượng lỗi cụ thể."
    else:
        message = (
            "Đây là GỢI Ý của hệ thống, không phải kết luận của phiếu. "
            "Kỹ thuật viên cần kiểm tra và tự xác nhận loại lỗi."
        )

    return {
        "available": True,
        "ai_result_id": result.id,
        "suggested_category_id": suggested_id,
        "suggested_category_name": output.get("suggested_category_name")
        or _category_name(db, suggested_id),
        "confidence": float(result.confidence_score) if result.confidence_score is not None else None,
        "reason": output.get("reason"),
        "review_status": result.review_status,
        "provider": (result.input_data or {}).get("provider"),
        "created_at": result.created_at,
        "need_more_information": need_more,
        "message": message,
    }


def build_history(db: Session, ticket: WarrantyTicket) -> List[Dict[str, Any]]:
    """Lịch sử xử lý: trạng thái, thời gian, người thực hiện, ghi chú."""
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



def build_row_action(status: str, permission_check: Callable[[str], bool]) -> Dict[str, Any]:
    """
    Nút hành động của MỘT DÒNG danh sách phiếu (trạng thái + quyền quyết định).

    Nguyên tắc nghiệp vụ: mỗi dòng chỉ có MỘT hành động chính, và hành động đó
    luôn nằm trong danh sách backend cho phép -> giao diện không thể hiển thị
    thao tác mà backend sẽ chặn (403).

    Trả về: available_actions, primary_action, action_label, action_kind.
    """
    actions = available_transitions(status, permission_check)
    primary: Optional[Dict[str, Any]] = None
    # Ưu tiên bước tiến của quy trình (sửa xong -> trả máy -> kiểm tra -> ...)
    for target in PRIMARY_ACTION_PRIORITY:
        primary = next((action for action in actions if action["target"] == target), None)
        if primary is not None:
            break
    if primary is None and actions:
        primary = actions[0]

    return {
        "available_actions": actions,
        "primary_action": primary,
        "action_label": primary["button_label"] if primary else READ_ONLY_ACTION_LABELS.get(
            status, DEFAULT_READ_ONLY_LABEL
        ),
        "action_kind": "transition" if primary else "read_only",
    }


def build_ticket_summary(
    db: Session,
    ticket: WarrantyTicket,
    name_map: Optional[Dict[int, str]] = None,
    category_map: Optional[Dict[int, str]] = None,
    current_user: Optional[User] = None,
) -> Dict[str, Any]:
    """
    Dữ liệu 1 dòng của DANH SÁCH phiếu (bảng phiếu, dashboard, kết quả tra cứu).

    Nếu truyền `current_user`, mỗi dòng kèm LUÔN nút hành động mà vai trò đó
    được phép bấm (xem `build_row_action`) để danh sách không hiển thị
    thao tác ngoài quyền.
    """
    history = list(ticket.status_history or [])
    last_step = history[-1] if history else None
    handler_id = last_step.changed_by if last_step else ticket.created_by
    if name_map is None:
        name_map = _user_name_map(db, [ticket.created_by, handler_id])
    if category_map is None:
        category_map = {}
        if ticket.error_category_id is not None:
            name = _category_name(db, ticket.error_category_id)
            if name:
                category_map[ticket.error_category_id] = name

    instance = ticket.product_instance
    product = instance.product if instance is not None and instance.product is not None else None
    customer = ticket.customer

    if current_user is not None:
        permission_check = lambda permission: has_permission(current_user, permission)  # noqa: E731
        row_action = build_row_action(ticket.status, permission_check)
    else:
        row_action = {
            "available_actions": [],
            "primary_action": None,
            "action_label": READ_ONLY_ACTION_LABELS.get(ticket.status, DEFAULT_READ_ONLY_LABEL),
            "action_kind": "read_only",
        }

    return {
        "id": ticket.id,
        "ticket_code": ticket.ticket_code,
        "product_instance_id": ticket.product_instance_id,
        "customer_id": ticket.customer_id,
        "service_center_id": ticket.service_center_id,
        "created_by": ticket.created_by,
        "issue_description": ticket.issue_description,
        "error_category_id": ticket.error_category_id,
        "status": ticket.status,
        "status_label": TICKET_STATUS_LABELS.get(ticket.status, ticket.status),
        "status_hint": TICKET_STATUS_HINTS.get(ticket.status, ""),
        "rejection_reason": ticket.rejection_reason,
        "rejection_proposed_by": ticket.rejection_proposed_by,
        "rejection_proposed_at": ticket.rejection_proposed_at,
        "rejection_reviewed_by": ticket.rejection_reviewed_by,
        "rejection_reviewed_at": ticket.rejection_reviewed_at,
        "rejection_review_status": ticket.rejection_review_status,
        "handed_over_at": ticket.handed_over_at,
        "serial_number": instance.serial_number if instance is not None else None,
        "product_name": product.name if product is not None else None,
        "product_brand": product.brand if product is not None else None,
        "customer_name": customer.full_name if customer is not None else None,
        "customer_phone": customer.phone if customer is not None else None,
        "warranty_end_date": instance.warranty_end_date if instance is not None else None,
        "error_category_name": category_map.get(ticket.error_category_id),
        "handler_id": handler_id,
        "handler_name": name_map.get(handler_id) if handler_id is not None else None,
        # [Đợt màn hình công việc theo vai trò] Hành động chính của dòng theo quyền
        "available_actions": row_action["available_actions"],
        "primary_action": row_action["primary_action"],
        "action_label": row_action["action_label"],
        "action_kind": row_action["action_kind"],
        # Danh sách vẫn trả lịch sử để không phá giao diện cũ; màn hình chi tiết có lịch sử đầy đủ.
        "status_history": build_history(db, ticket),
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
    }


def build_ticket_summaries(
    db: Session,
    tickets: List[WarrantyTicket],
    current_user: Optional[User] = None,
) -> List[Dict[str, Any]]:
    """
    Dựng danh sách phiếu với 1 truy vấn tên nhân viên + 1 truy vấn nhãn lỗi (hiệu năng).

    `current_user` (nếu có) quyết định nút hành động kèm theo mỗi dòng.
    """
    if not tickets:
        return []
    user_ids: List[Optional[int]] = [t.created_by for t in tickets]
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
    """Tiến trình 5 bước kèm thời gian/người thực hiện/ghi chú của từng bước đã đi qua."""
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

    order = [step["status"] for step in TICKET_STEPS]
    if ticket.status == "REJECTED":
        current_index = 1
    elif ticket.status in order:
        current_index = order.index(ticket.status)
    else:
        current_index = 0

    steps: List[Dict[str, Any]] = []
    for index, step in enumerate(TICKET_STEPS):
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
    """Nhật ký sửa chữa (bảng repair_logs) - dùng lại bảng có sẵn của KT1."""
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
    """
    Dựng payload màn hình xử lý phiếu: đủ khối A-G + hành động được phép + điều kiện hoàn tất.

    `current_user` = None nghĩa là không xác định người xem -> không trả hành động nào
    (an toàn mặc định: không hiển thị nút khi không rõ quyền).
    """
    if current_user is None:
        permission_check: Callable[[str], bool] = lambda _permission: False
    else:
        permission_check = lambda permission: has_permission(current_user, permission)

    detail = build_ticket_summary(db, ticket)
    history = build_history(db, ticket)
    instance = ticket.product_instance
    product = instance.product if instance is not None and instance.product is not None else None
    customer = ticket.customer
    name_map = _user_name_map(
        db, [ticket.created_by, ticket.diagnosis_by, ticket.repair_by, ticket.handed_over_by]
    )

    warranty = warranty_status_info(instance.warranty_end_date if instance is not None else None)
    repair_history_note = next(
        (
            row["note"]
            for row in reversed(history)
            if row["to_status"] == "WAITING_RETURN" and row["note"]
        ),
        None,
    )
    repair_completed_row = next(
        (row for row in reversed(history) if row["to_status"] == "WAITING_RETURN"), None
    )
    blockers = completion_blockers(db, ticket)

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
            },
            "diagnosis": {
                "note": ticket.diagnosis_note,
                "error_category_id": ticket.error_category_id,
                "error_category_name": detail.get("error_category_name"),
                "confirmed_by": ticket.diagnosis_by,
                "confirmed_by_name": name_map.get(ticket.diagnosis_by)
                if ticket.diagnosis_by
                else None,
                "confirmed_at": ticket.diagnosis_at,
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
                "note": ticket.repair_note or repair_history_note,
                "technician_id": ticket.repair_by
                or (repair_completed_row or {}).get("changed_by"),
                "technician_name": name_map.get(ticket.repair_by)
                or (repair_completed_row or {}).get("changed_by_name"),
                "recorded_at": ticket.repair_at
                or (repair_completed_row["created_at"] if repair_completed_row else None),
                "logs": build_repair_logs(db, ticket),
            },
            "handover": {
                "is_waiting_return": ticket.status == "WAITING_RETURN",
                "status_message": (
                    "Thiết bị đã sửa xong và đang chờ khách nhận máy."
                    if ticket.status == "WAITING_RETURN"
                    else TICKET_STATUS_HINTS.get(ticket.status, "")
                ),
                "repair_completed_at": ticket.repair_at
                or (repair_completed_row["created_at"] if repair_completed_row else None),
                "repair_completed_by_name": (repair_completed_row or {}).get("changed_by_name"),


                "returned_at": ticket.handed_over_at,
                "returned_by_name": name_map.get(ticket.handed_over_by)
                if ticket.handed_over_by
                else None,
                "note": ticket.handover_note,
            },
            "available_actions": available_transitions(ticket.status, permission_check),
            "completion_checklist": completion_checklist(ticket),
            "can_complete": len(blockers) == 0,
            "completion_blockers": blockers,
            "can_edit_diagnosis": bool(permission_check(PERM_TICKET_DIAGNOSE))
            and ticket.status in EDITABLE_WORKFLOW_STATUSES,
            "can_edit_repair": bool(permission_check(PERM_TICKET_REPAIR))
            and ticket.status in EDITABLE_WORKFLOW_STATUSES,
            "permission_notes": permission_notes(ticket.status, permission_check),
        }
    )
    return detail


def build_role_workload(
    role: Optional[str], counts: Dict[str, int], mine: bool = False
) -> List[Dict[str, Any]]:
    """
    Danh sách việc cần làm NGAY, chọn theo vai trò đang đăng nhập.

    Giao diện dùng danh sách này để vẽ khối "Việc cần làm" thay vì đổ toàn bộ số liệu
    thống kê cho mọi vai trò (nhân viên không cần thấy số liệu của người khác).
    """
    if role == "TECHNICIAN":
        definitions = [
            ("INSPECTING", "Phiếu đang kiểm tra", "Máy đang trên bàn kiểm tra: cần ghi kết luận chẩn đoán."),
            ("REPAIRING", "Phiếu đang sửa chữa", "Sửa xong thì chuyển phiếu sang \"Chờ trả máy\"."),
            ("WAITING_RETURN", "Phiếu đã sửa xong", "Máy đã xong: chuyển ra quầy để trả khách."),
        ]
    elif role == "RECEPTIONIST":
        definitions = [
            ("RECEIVED", "Phiếu chờ tiếp nhận", "Máy vừa tiếp nhận: chuyển vào phòng kiểm tra."),
            ("WAITING_RETURN", "Phiếu chờ trả máy", "Gọi khách tới nhận máy và xác nhận đã trả máy."),
            ("INSPECTING", "Phiếu đang kiểm tra", "Theo dõi để trả lời khách khi họ gọi hỏi."),
        ]
    else:
        definitions = [
            ("RECEIVED", "Mới tiếp nhận", "Phiếu mới cần chuyển kỹ thuật kiểm tra."),
            ("INSPECTING", "Đang kiểm tra", "Kỹ thuật viên đang xác định nguyên nhân."),
            ("REPAIRING", "Đang sửa chữa", "Máy đang được sửa chữa."),
            ("WAITING_RETURN", "Chờ trả máy", "Đã sửa xong, chờ khách tới nhận."),
            ("COMPLETED", "Đã hoàn tất", "Đã bàn giao máy cho khách."),
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
