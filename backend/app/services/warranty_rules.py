from datetime import date, datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import (
    Customer,
    ErrorCategory,
    Product,
    ProductInstance,
    ServiceCenter,
    User,
    WarrantyTicket,
)
# Mã quyền dùng cho ma trận hành động trên phiếu (nguồn sự thật: app.services.auth_service)
from app.services.auth_service import (
    PERM_TICKET_HANDOVER,
    PERM_TICKET_REJECT,
    PERM_TICKET_UPDATE_STATUS,
)

# Danh sách trạng thái đang mở theo Whitelist BR3
# (phiếu đang mở = phiếu chưa trả máy xong cho khách, gồm cả WAITING_RETURN)
OPEN_TICKET_STATUSES = ["RECEIVED", "INSPECTING", "REPAIRING", "WAITING_RETURN"]

# Nhãn tiếng Việt của 6 trạng thái vòng đời phiếu (dùng thống nhất ở tài liệu & thông báo)
TICKET_STATUS_LABELS = {
    "RECEIVED": "Mới tiếp nhận",
    "INSPECTING": "Đang kiểm tra",
    "REPAIRING": "Đang sửa chữa",
    "WAITING_RETURN": "Chờ trả máy",
    "COMPLETED": "Đã hoàn tất",
    "REJECTED": "Từ chối bảo hành",
}

# Ma trận chuyển trạng thái hợp lệ theo thiết kế KT1/KT2 (mở rộng đợt hoàn thiện)
# Vòng đời thực tế của một phiếu bảo hành:
#   RECEIVED -> INSPECTING -> REPAIRING -> WAITING_RETURN -> COMPLETED
# Bắt buộc đi qua WAITING_RETURN: máy sửa xong vẫn phải "chờ trả máy" (đợi khách
# tới nhận) rồi mới được đóng phiếu ở trạng thái COMPLETED.
ALLOWED_TRANSITIONS = {
    "RECEIVED": ["INSPECTING"],
    "INSPECTING": ["REPAIRING", "REJECTED"],
    "REPAIRING": ["WAITING_RETURN", "INSPECTING"],
    "WAITING_RETURN": ["COMPLETED", "REPAIRING"],
    "COMPLETED": [],
    "REJECTED": []
}


# =====================================================================
# [Đợt hoàn thiện nghiệp vụ] Hành động theo từng bước - nguồn sự thật DUY NHẤT
# ---------------------------------------------------------------------
# Mỗi chuyển trạng thái được mô tả bằng 1 bản ghi: nhãn nút người dùng thấy,
# câu hỏi xác nhận, quyền cần có, và các thông tin nghiệp vụ cần ghi nhận.
# Giao diện CHỈ hiển thị những gì backend trả về (`available_actions`) nên
# không thể có nút "nhảy cóc" trạng thái.
# =====================================================================
STEP_STATUSES = ["RECEIVED", "INSPECTING", "REPAIRING", "WAITING_RETURN", "COMPLETED"]

# Nhãn 5 bước xử lý thực tế (dùng cho thanh tiến trình ở màn hình phiếu)
TICKET_STEPS: List[Dict[str, Any]] = [
    {"step": 1, "status": "RECEIVED", "label": "Tiếp nhận"},
    {"step": 2, "status": "INSPECTING", "label": "Kiểm tra"},
    {"step": 3, "status": "REPAIRING", "label": "Sửa chữa"},
    {"step": 4, "status": "WAITING_RETURN", "label": "Chờ trả máy"},
    {"step": 5, "status": "COMPLETED", "label": "Hoàn tất"},
]

# Câu mô tả NGẮN, KHÔNG mã kỹ thuật: nhân viên nhìn là biết phiếu đang ở đâu
# và bước tiếp theo phải làm gì.
TICKET_STATUS_HINTS: Dict[str, str] = {
    "RECEIVED": "Máy đã được tiếp nhận tại quầy. Bước tiếp theo: chuyển máy vào phòng kiểm tra.",
    "INSPECTING": "Kỹ thuật viên đang kiểm tra máy và cần ghi nhận kết luận chẩn đoán.",
    "REPAIRING": "Máy đang được sửa chữa. Khi sửa xong, chuyển phiếu sang mục Chờ trả máy.",
    "WAITING_RETURN": "Thiết bị đã sửa xong và đang chờ khách nhận máy.",
    "COMPLETED": "Phiếu đã hoàn tất và thiết bị đã được bàn giao cho khách.",
    "REJECTED": "Phiếu đã bị từ chối bảo hành (không thuộc phạm vi bảo hành).",
}


class BusinessRuleError(HTTPException):
    """
    Lỗi nghiệp vụ trả ra API.

    - `detail`      : nội dung kỹ thuật (giữ nguyên định dạng cũ để không phá các
                      minh chứng kiểm thử KT2/KT3 đang trích trường này).
    - `user_message`: câu tiếng Việt thân thiện cho nhân viên; giao diện hiển thị
                      trường này TRƯỚC TIÊN nên người dùng không thấy mã kỹ thuật.
    - `error_code`  : mã nghiệp vụ ngắn (BR1..BR5, STATE_MACHINE, WORKFLOW_...).
    - `hint`        : việc cần làm tiếp theo (nếu có).
    """

    def __init__(
        self,
        status_code: int,
        detail: str,
        user_message: str,
        error_code: str = "BUSINESS_RULE",
        hint: Optional[str] = None,
    ):
        super().__init__(status_code=status_code, detail=detail)
        self.user_message = user_message
        self.error_code = error_code
        self.hint = hint


# Ma trận HÀNH ĐỘNG trên phiếu: nhãn nút + quyền + thông tin cần ghi nhận.
# `fields`  : các trường nghiệp vụ giao diện cần hỏi người dùng khi xác nhận.
# `requires_input`: phải có ít nhất một nội dung (ghi chú hoặc trường nghiệp vụ)
#             mới cho chuyển bước -> chặn thao tác "bấm cho xong".
TRANSITION_RULES: Dict[Tuple[str, str], Dict[str, Any]] = {
    ("RECEIVED", "INSPECTING"): {
        "target": "INSPECTING",
        "button_label": "Chuyển sang kiểm tra",
        "confirm_question": "Chuyển phiếu sang Đang kiểm tra?",
        "description": "Đưa máy vào phòng kiểm tra để xác định nguyên nhân.",
        "permission": PERM_TICKET_UPDATE_STATUS,
        "style": "warning",
        "fields": ["note"],
        "requires_input": False,
        "note_label": "Ghi chú tiếp nhận (không bắt buộc)",
        "note_placeholder": "Ví dụ: Đã nhận máy tại quầy, chuyển kỹ thuật kiểm tra",
    },
    ("INSPECTING", "REPAIRING"): {
        "target": "REPAIRING",
        "button_label": "Bắt đầu sửa chữa",
        "confirm_question": "Chuyển phiếu sang Đang sửa chữa?",
        "description": "Kỹ thuật viên đã có kết luận chẩn đoán và bắt đầu sửa chữa.",
        "permission": PERM_TICKET_UPDATE_STATUS,
        "style": "primary",
        "fields": ["diagnosis_note", "error_category_id", "note"],
        "requires_input": True,
        "note_label": "Ghi chú kỹ thuật (không bắt buộc)",
        "note_placeholder": "Ví dụ: Thay IC nguồn, vệ sinh tản nhiệt",
    },
    ("REPAIRING", "WAITING_RETURN"): {
        "target": "WAITING_RETURN",
        "button_label": "Sửa xong – Chờ trả máy",
        "confirm_question": "Chuyển phiếu sang Chờ trả máy?",
        "description": "Máy đã sửa xong và được đưa ra quầy chờ khách tới nhận.",
        "permission": PERM_TICKET_UPDATE_STATUS,
        "style": "primary",
        "fields": ["repair_content", "repair_parts", "repair_note", "note"],
        "requires_input": True,
        "note_label": "Ghi chú bàn giao nội bộ (không bắt buộc)",
        "note_placeholder": "Ví dụ: Máy chạy ổn định sau 2 giờ chạy thử",
    },
}


# Bổ sung 4 hành động còn lại của vòng đời phiếu (trả máy, sửa lại, kiểm tra lại, từ chối)
TRANSITION_RULES.update(
    {
        ("WAITING_RETURN", "COMPLETED"): {
            "target": "COMPLETED",
            "button_label": "Xác nhận đã trả máy",
            "confirm_question": "Xác nhận đã trả máy cho khách và hoàn tất phiếu?",
            "description": "Máy đã được bàn giao cho khách; phiếu được đóng lại.",
            "permission": PERM_TICKET_HANDOVER,
            "style": "success",
            "fields": ["handover_note", "note"],
            "requires_input": True,
            "note_label": "Ghi chú khi bàn giao (không bắt buộc)",
            "note_placeholder": "Ví dụ: Khách đã kiểm tra máy và nhận lại kèm phiếu bảo hành",
        },
        ("WAITING_RETURN", "REPAIRING"): {
            "target": "REPAIRING",
            "button_label": "Khách báo còn lỗi – Sửa lại",
            "confirm_question": "Chuyển phiếu về Đang sửa chữa?",
            "description": "Khách kiểm tra và báo máy còn lỗi; máy được đưa lại xưởng.",
            "permission": PERM_TICKET_UPDATE_STATUS,
            "style": "warning",
            "fields": ["note"],
            "requires_input": True,
            "note_label": "Lý do sửa lại (bắt buộc)",
            "note_placeholder": "Ví dụ: Khách báo máy vẫn chập chờn sau khi nhận",
        },
        ("REPAIRING", "INSPECTING"): {
            "target": "INSPECTING",
            "button_label": "Cần kiểm tra lại",
            "confirm_question": "Chuyển phiếu về Đang kiểm tra?",
            "description": "Cần kiểm tra lại trước khi tiếp tục sửa chữa.",
            "permission": PERM_TICKET_UPDATE_STATUS,
            "style": "warning",
            "fields": ["diagnosis_note", "note"],
            "requires_input": True,
            "note_label": "Lý do kiểm tra lại (bắt buộc)",
            "note_placeholder": "Ví dụ: Nghi ngờ lỗi phát sinh ở bo mạch",
        },
        ("INSPECTING", "REJECTED"): {
            "target": "REJECTED",
            "button_label": "Từ chối bảo hành",
            "confirm_question": "Từ chối bảo hành phiếu này?",
            "description": "Thiết bị không thuộc phạm vi bảo hành; quyết định thuộc Quản lý.",
            "permission": PERM_TICKET_REJECT,
            "style": "danger",
            "fields": ["rejection_reason", "note"],
            "requires_input": True,
            "note_label": "Lý do từ chối bảo hành (bắt buộc)",
            "note_placeholder": "Ví dụ: Thiết bị vào nước, không thuộc phạm vi bảo hành",
        },
    }
)


def transition_rule(current_status: str, new_status: str) -> Optional[Dict[str, Any]]:
    """Lấy mô tả hành động tương ứng một chuyển trạng thái (None nếu không có)."""
    return TRANSITION_RULES.get((current_status, new_status))


def available_transitions(current_status: str, has_permission_fn) -> List[Dict[str, Any]]:
    """
    Danh sách hành động mà NGƯỜI ĐANG ĐĂNG NHẬP được phép thực hiện ở trạng thái hiện tại.

    `has_permission_fn(permission_code) -> bool` do tầng router truyền vào; nhờ vậy
    giao diện chỉ hiển thị nút có quyền và backend vẫn là nơi chặn thật.
    """
    actions: List[Dict[str, Any]] = []
    for (source_status, target_status), rule in TRANSITION_RULES.items():
        if source_status != current_status:
            continue
        if not has_permission_fn(rule["permission"]):
            continue
        actions.append(
            {
                "target": target_status,
                "target_label": TICKET_STATUS_LABELS.get(target_status, target_status),
                "button_label": rule["button_label"],
                "confirm_question": rule["confirm_question"],
                "description": rule["description"],
                "style": rule["style"],
                "fields": list(rule["fields"]),
                "requires_input": bool(rule["requires_input"]),
                "requires_rejection_reason": target_status == "REJECTED",
                "note_label": rule.get("note_label", "Ghi chú xử lý"),
                "note_placeholder": rule.get("note_placeholder", ""),
                "permission": rule["permission"],
            }
        )
    return actions


def validate_br1_serial_exists(db: Session, serial_number: str) -> ProductInstance:
    """
    BR1: Serial sản phẩm phải tồn tại trong hệ thống.
    Nếu không tìm thấy -> Thông báo lỗi và không tạo phiếu (không tạo REJECTED).
    """
    instance = db.query(ProductInstance).filter(ProductInstance.serial_number == serial_number).first()
    if not instance:
        raise BusinessRuleError(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"[BR1 FAIL] Không tìm thấy sản phẩm với số serial '{serial_number}' trong hệ thống. Không tạo phiếu bảo hành.",
            user_message=(
                f"Không tìm thấy thiết bị có số sê-ri \"{serial_number}\" trong hệ thống nên chưa thể lập phiếu bảo hành. "
                "Vui lòng kiểm tra lại số sê-ri trên tem máy, hoặc đăng ký thiết bị mới cho khách trước."
            ),
            error_code="BR1_SERIAL_NOT_FOUND",
            hint="Kiểm tra lại số sê-ri hoặc đăng ký thiết bị mới cho khách hàng.",
        )
    return instance


def validate_br2_warranty_valid(instance: ProductInstance, check_date: Optional[date] = None) -> date:
    """
    BR2: Sản phẩm phải còn thời hạn bảo hành tại thời điểm tiếp nhận.
    Quy tắc: warranty_end_date >= check_date (tính bao gồm cả ngày kết thúc).
    Nếu hết hạn -> Thông báo lỗi và không tạo phiếu.
    """
    if check_date is None:
        check_date = date.today()

    if instance.warranty_end_date < check_date:
        days_expired = (check_date - instance.warranty_end_date).days
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"[BR2 FAIL] Sản phẩm với serial '{instance.serial_number}' đã hết hạn bảo hành vào ngày "
                f"{instance.warranty_end_date.strftime('%d/%m/%Y')} (đã quá hạn {days_expired} ngày so với ngày "
                f"kiểm tra {check_date.strftime('%d/%m/%Y')}). Không tạo phiếu bảo hành."
            ),
            user_message=(
                f"Thiết bị có số sê-ri \"{instance.serial_number}\" đã hết hạn bảo hành từ ngày "
                f"{instance.warranty_end_date.strftime('%d/%m/%Y')} (quá hạn {days_expired} ngày), "
                "nên không đủ điều kiện tiếp nhận bảo hành."
            ),
            error_code="BR2_WARRANTY_EXPIRED",
            hint="Thông báo cho khách về tình trạng hết hạn bảo hành; nếu khách đồng ý có thể nhận sửa chữa tính phí (ngoài phạm vi phiếu bảo hành).",
        )
    return check_date


def validate_br3_no_open_tickets(db: Session, product_instance_id: int):
    """
    BR3: Sản phẩm không được có phiếu bảo hành đang xử lý.
    Các trạng thái đang mở theo whitelist: RECEIVED, INSPECTING, REPAIRING, WAITING_RETURN.
    Nếu có -> Dừng và không tạo phiếu trùng.
    """
    open_ticket = db.query(WarrantyTicket).filter(
        WarrantyTicket.product_instance_id == product_instance_id,
        WarrantyTicket.status.in_(OPEN_TICKET_STATUSES)
    ).first()

    if open_ticket:
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"[BR3 FAIL] Sản phẩm đang có phiếu bảo hành chưa hoàn tất (Mã phiếu: '{open_ticket.ticket_code}', "
                f"Trạng thái hiện tại: '{open_ticket.status}'). Không tạo phiếu mới để tránh trùng lặp."
            ),
            user_message=(
                f"Thiết bị này đang có phiếu bảo hành chưa hoàn tất: {open_ticket.ticket_code} "
                f"({TICKET_STATUS_LABELS.get(open_ticket.status, open_ticket.status)}). "
                "Mỗi thiết bị chỉ có một phiếu đang xử lý, vui lòng tiếp tục xử lý phiếu cũ thay vì lập phiếu mới."
            ),
            error_code="BR3_OPEN_TICKET_EXISTS",
            hint=f"Mở phiếu {open_ticket.ticket_code} để cập nhật tình trạng thay vì tạo phiếu trùng.",
        )


def validate_br4_owner_verification(instance: ProductInstance, request_customer_id: int):
    """
    BR4: Khách hàng/chủ sở hữu phải được xác minh phù hợp với thông tin sản phẩm.
    Nếu khách hàng yêu cầu tiếp nhận không phải là chủ sở hữu đã đăng ký -> Dừng để xác minh.
    """
    if instance.customer_id != request_customer_id:
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"[BR4 FAIL] Xác minh chủ sở hữu không khớp: Khách hàng gửi yêu cầu (ID: {request_customer_id}) "
                f"không trùng khớp với chủ sở hữu đã đăng ký của serial '{instance.serial_number}' (ID: {instance.customer_id}). "
                f"Không tạo phiếu bảo hành."
            ),
            user_message=(
                f"Khách hàng đang yêu cầu tiếp nhận không phải chủ sở hữu đã đăng ký của thiết bị "
                f"\"{instance.serial_number}\". Vui lòng kiểm tra lại thông tin chủ sở hữu (giấy tờ mua hàng) "
                "trước khi lập phiếu bảo hành."
            ),
            error_code="BR4_OWNER_MISMATCH",
            hint="Đối chiếu lại thông tin chủ sở hữu thiết bị; chỉ chủ sở hữu đã đăng ký mới được tiếp nhận bảo hành.",
        )


def validate_state_transition(current_status: str, new_status: str, rejection_reason: Optional[str] = None):
    """
    Kiểm tra tính hợp lệ của việc chuyển trạng thái theo State Machine (6 trạng thái):
    - RECEIVED -> INSPECTING
    - INSPECTING -> REPAIRING hoặc REJECTED
    - REPAIRING -> WAITING_RETURN (sửa xong, chờ trả máy) hoặc INSPECTING
    - WAITING_RETURN -> COMPLETED (đã trả máy cho khách) hoặc REPAIRING (khách báo còn lỗi)
    - COMPLETED / REJECTED là terminal state
    - Không cho phép REPAIRING -> COMPLETED trực tiếp (bắt buộc đi qua WAITING_RETURN)
      hoặc bất kỳ chuyển trạng thái nào ngoài ma trận.
    Thông báo lỗi trả kèm nhãn tiếng Việt của trạng thái để người dùng dễ đọc.
    """
    allowed = ALLOWED_TRANSITIONS.get(current_status, [])
    if new_status not in allowed:
        current_label = TICKET_STATUS_LABELS.get(current_status, current_status)
        new_label = TICKET_STATUS_LABELS.get(new_status, new_status)
        allowed_labels = ", ".join(
            code + " (" + TICKET_STATUS_LABELS.get(code, code) + ")" for code in allowed
        ) or "Không có (đây là trạng thái kết thúc)"
        rule = transition_rule(current_status, new_status)
        if current_status == "REPAIRING" and new_status == "COMPLETED":
            user_message = (
                "Chưa thể hoàn tất phiếu. Thiết bị vẫn đang ở trạng thái sửa chữa, "
                "cần chuyển sang \"Chờ trả máy\" sau khi sửa xong, rồi mới xác nhận đã trả máy cho khách."
            )
            hint = "Bấm \"Sửa xong – Chờ trả máy\" trước, sau đó bấm \"Xác nhận đã trả máy\"."
        elif rule:
            user_message = (
                f"Không thực hiện được thao tác \"{rule['button_label']}\" vì phiếu đang ở trạng thái "
                f"\"{current_label}\"."
            )
            hint = f"Trạng thái tiếp theo hợp lệ: {allowed_labels}."
        else:
            user_message = (
                f"Phiếu đang ở trạng thái \"{current_label}\" nên không thể chuyển sang \"{new_label}\"."
            )
            hint = f"Trạng thái tiếp theo hợp lệ: {allowed_labels}."
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"[STATE MACHINE ERROR] Không được phép chuyển trạng thái từ '{current_status}' ({current_label}) "
                f"sang '{new_status}' ({new_label}). "
                f"Các trạng thái hợp lệ tiếp theo: {allowed_labels}."
            ),
            user_message=user_message,
            error_code="STATE_MACHINE_ERROR",
            hint=hint,
        )

    if new_status == "REJECTED" and (not rejection_reason or not rejection_reason.strip()):
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="[BR5 REQUIRED] Khi chuyển phiếu sang trạng thái REJECTED, bắt buộc phải cung cấp lý do từ chối (rejection_reason).",
            user_message="Vui lòng ghi rõ lý do từ chối bảo hành trước khi xác nhận.",
            error_code="BR5_REJECTION_REASON_REQUIRED",
            hint="Ví dụ: Thiết bị vào nước, rơi vỡ, hoặc đã hết hạn bảo hành do khách cung cấp sai ngày mua.",
        )


# =====================================================================
# [Đợt hoàn thiện nghiệp vụ] Điều kiện GHI NHẬN THÔNG TIN & ĐIỀU KIỆN HOÀN TẤT
# ---------------------------------------------------------------------
# Mục tiêu: không cho nhân viên "bấm cho xong" - mỗi bước sửa chữa/trả máy phải
# kèm thông tin xử lý thật, và phiếu chỉ được đóng khi đã sửa xong + đã trả máy.
# Các quy tắc này KHÔNG thay đổi BR1-BR5 cũng không thay đổi ma trận
# ALLOWED_TRANSITIONS (vẫn phải đi qua WAITING_RETURN trước COMPLETED).
# =====================================================================
MIN_HISTORY_STEPS_BEFORE_COMPLETE = 4  # Tiếp nhận -> Kiểm tra -> Sửa chữa -> Chờ trả máy


def workflow_input_recorded(note: Optional[str], *values: Optional[str]) -> bool:
    """True nếu có ít nhất một nội dung nghiệp vụ thật được ghi nhận."""
    for candidate in (note,) + values:
        if candidate and str(candidate).strip():
            return True
    return False


def validate_transition_input(
    current_status: str,
    new_status: str,
    note: Optional[str] = None,
    diagnosis_note: Optional[str] = None,
    repair_content: Optional[str] = None,
    repair_parts: Optional[str] = None,
    repair_note: Optional[str] = None,
    handover_note: Optional[str] = None,
) -> None:
    """
    Bắt buộc mỗi bước nghiệp vụ phải kèm thông tin xử lý (ghi chú hoặc dữ liệu chuyên môn).

    Không áp dụng cho bước từ chối bảo hành vì lý do từ chối đã bắt buộc ở BR5.
    """
    rule = transition_rule(current_status, new_status)
    if not rule or not rule.get("requires_input") or new_status == "REJECTED":
        return

    if workflow_input_recorded(
        note, diagnosis_note, repair_content, repair_parts, repair_note, handover_note
    ):
        return

    message_by_target = {
        "INSPECTING": "Vui lòng ghi lại lý do cần kiểm tra lại trước khi chuyển bước.",
        "REPAIRING": (
            "Vui lòng ghi kết luận chẩn đoán (hoặc ghi chú kỹ thuật) trước khi chuyển phiếu "
            "sang \"Đang sửa chữa\"."
        ),
        "WAITING_RETURN": (
            "Vui lòng ghi nội dung đã sửa chữa (hoặc ghi chú kỹ thuật) trước khi chuyển phiếu "
            "sang \"Chờ trả máy\" để biết máy đã được xử lý những gì."
        ),
        "COMPLETED": (
            "Vui lòng ghi thông tin bàn giao (người nhận máy / tình trạng máy khi trả) "
            "trước khi hoàn tất phiếu."
        ),
    }
    raise BusinessRuleError(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"[WORKFLOW INPUT REQUIRED] Chuyển trạng thái {current_status} -> {new_status} "
            "thiếu thông tin xử lý (note/diagnosis_note/repair_content/handover_note)."
        ),
        user_message=message_by_target.get(
            new_status, "Vui lòng ghi thông tin xử lý trước khi chuyển bước tiếp theo."
        ),
        error_code="WORKFLOW_INPUT_REQUIRED",
        hint=rule.get("note_placeholder") or "Ghi ngắn gọn việc đã làm để người sau tiếp tục xử lý.",
    )


def completion_blockers(db: Session, ticket: WarrantyTicket) -> List[str]:
    """
    Danh sách lý do TIẾNG VIỆT vì sao phiếu chưa thể hoàn tất (rỗng = được phép hoàn tất).

    Kiểm tra theo đúng yêu cầu nghiệp vụ: phiếu tồn tại -> thiết bị tồn tại ->
    khách hàng tồn tại -> đang ở "Chờ trả máy" -> đã ghi nhận thông tin sửa chữa ->
    lịch sử có đủ các bước xử lý.
    """
    if ticket is None:
        return ["Không tìm thấy phiếu bảo hành."]

    blockers: List[str] = []
    status_label = TICKET_STATUS_LABELS.get(ticket.status, ticket.status)

    if ticket.product_instance is None:
        blockers.append("Không tìm thấy thiết bị của phiếu nên không thể xác nhận đã trả máy.")

    if ticket.customer is None:
        blockers.append("Không tìm thấy khách hàng của phiếu nên không thể xác nhận đã trả máy.")

    if ticket.status != "WAITING_RETURN":
        blockers.append(
            f"Thiết bị đang ở trạng thái \"{status_label}\" nên chưa thể hoàn tất. "
            "Hãy sửa xong và chuyển phiếu sang \"Chờ trả máy\" trước khi trả máy cho khách."
        )

    history = list(ticket.status_history or [])
    if len(history) < MIN_HISTORY_STEPS_BEFORE_COMPLETE:
        blockers.append(
            "Phiếu chưa ghi nhận đủ các bước xử lý (Tiếp nhận → Kiểm tra → Sửa chữa → Chờ trả máy)."
        )

    if not _has_repair_info(ticket):
        blockers.append(
            "Chưa có thông tin sửa chữa (nội dung đã sửa hoặc ghi chú kỹ thuật) nên chưa thể hoàn tất phiếu."
        )

    return blockers


def _has_repair_info(ticket: WarrantyTicket) -> bool:
    """Đã có thông tin sửa chữa chưa (dữ liệu cột hoặc ghi chú ở bước chuyển sang Chờ trả máy)."""
    repair_history_note = next(
        (
            row.note
            for row in reversed(list(ticket.status_history or []))
            if row.to_status == "WAITING_RETURN" and row.note
        ),
        None,
    )
    return (
        workflow_input_recorded(ticket.repair_content, ticket.repair_note, repair_history_note)
        or ticket.repair_at is not None
    )


def completion_checklist(ticket: WarrantyTicket) -> List[Dict[str, Any]]:
    """Điều kiện hoàn tất kèm trạng thái đạt/chưa đạt để hiển thị trên màn hình phiếu."""
    if ticket is None:
        return []
    history = list(ticket.status_history or [])
    return [
        {
            "key": "ticket_exists",
            "label": "Phiếu bảo hành tồn tại",
            "satisfied": True,
        },
        {
            "key": "device_exists",
            "label": "Thiết bị của phiếu tồn tại",
            "satisfied": ticket.product_instance is not None,
        },
        {
            "key": "customer_exists",
            "label": "Khách hàng của phiếu tồn tại",
            "satisfied": ticket.customer is not None,
        },
        {
            "key": "status_waiting_return",
            "label": "Thiết bị đang ở trạng thái \"Chờ trả máy\"",
            "satisfied": ticket.status == "WAITING_RETURN",
        },
        {
            "key": "repair_info",
            "label": "Đã ghi nhận thông tin sửa chữa",
            "satisfied": _has_repair_info(ticket),
        },
        {
            "key": "history_steps",
            "label": "Lịch sử đã có đủ các bước xử lý",
            "satisfied": len(history) >= MIN_HISTORY_STEPS_BEFORE_COMPLETE,
        },
    ]


def validate_ticket_completion(db: Session, ticket: WarrantyTicket) -> None:
    """Chặn hoàn tất phiếu khi chưa đủ điều kiện; thông báo lỗi bằng tiếng Việt dễ hiểu."""
    blockers = completion_blockers(db, ticket)
    if not blockers:
        return
    raise BusinessRuleError(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="[WORKFLOW COMPLETE BLOCKED] " + " | ".join(blockers),
        user_message=blockers[0],
        error_code="WORKFLOW_COMPLETE_BLOCKED",
        hint="Hoàn tất các bước còn thiếu rồi xác nhận lại.",
    )


# =====================================================================
# [AUD-06] Kiểm tra sự tồn tại của các đối tượng được tham chiếu qua FK.
# ---------------------------------------------------------------------
# Trước đây API chấp nhận `service_center_id` / `created_by` / `changed_by`
# không tồn tại (ví dụ 999999) và ghi thẳng vào CSDL. Hai hàm dưới đây chỉ
# kiểm tra SỰ TỒN TẠI, KHÔNG thay đổi BR1-BR4, State Machine hay AI-01.
# =====================================================================
def validate_service_center_exists(db: Session, service_center_id: int) -> ServiceCenter:
    """Kiểm tra trung tâm bảo hành tồn tại (404 nếu không có)."""
    center = db.query(ServiceCenter).filter(ServiceCenter.id == service_center_id).first()
    if not center:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy trung tâm bảo hành với ID: {service_center_id}."
        )
    return center


def validate_user_exists(db: Session, user_id: int, user_label: str = "nhân viên") -> User:
    """Kiểm tra người dùng hệ thống tồn tại (404 nếu không có)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy {user_label} với ID: {user_id}."
        )
    return user


def validate_error_category_exists(db: Session, category_id: int) -> ErrorCategory:
    """
    Kiểm tra nhãn loại lỗi tồn tại trước khi ghi vào phiếu.

    Dùng cho cả 2 đường: kỹ thuật viên kết luận loại lỗi, và nhân viên xét duyệt
    gợi ý của AI (AI không tự ghi nhãn - xem KT3 phần human-in-the-loop).
    """
    category = db.query(ErrorCategory).filter(ErrorCategory.id == category_id).first()
    if not category:
        raise BusinessRuleError(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy nhãn loại lỗi với ID: {category_id}.",
            user_message=(
                "Không tìm thấy loại lỗi đã chọn. Vui lòng chọn lại loại lỗi trong danh sách."
            ),
            error_code="ERROR_CATEGORY_NOT_FOUND",
            hint="Chọn một nhãn lỗi đang hiển thị trong mục \"Loại lỗi\" của phiếu.",
        )
    return category


def add_months_to_date(source_date: date, months: int) -> date:
    """
    Hàm tính ngày hết hạn bảo hành chuẩn xác theo lịch (tránh sai số do lấy 30 ngày/tháng).
    """
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    # Xử lý trường hợp ngày cuối tháng (ví dụ 31/01 + 1 tháng -> 28/02)
    import calendar
    max_day_in_month = calendar.monthrange(year, month)[1]
    day = min(source_date.day, max_day_in_month)
    return date(year, month, day)


def detailed_debug_warranty(
    db: Session,
    serial_number: Optional[str] = None,
    purchase_date: Optional[date] = None,
    warranty_duration_months: Optional[int] = None,
    check_date: Optional[date] = None
) -> Dict[str, Any]:
    """
    Chức năng Debug kiểm tra hạn bảo hành chuyên sâu phục vụ yêu cầu KT2:
    - Phân tích ngày mua, thời gian bảo hành, ngày hết hạn tính toán vs ngày hết hạn đóng băng.
    - Kiểm tra các lỗi phổ biến: Lỗi Timezone, Lỗi so sánh >= hay >, Lỗi ngày cuối tháng/năm nhuận.
    """
    traces = []
    if check_date is None:
        check_date = date.today()
    traces.append(f"[Step 1] Khởi tạo ngày kiểm tra đối chiếu: {check_date.strftime('%Y-%m-%d')}")

    product_name = None
    frozen_end_date = None
    calculated_end_date = None

    if serial_number:
        traces.append(f"[Step 2] Tìm kiếm thông tin theo serial '{serial_number}' trong cơ sở dữ liệu...")
        instance = db.query(ProductInstance).filter(ProductInstance.serial_number == serial_number).first()
        if not instance:
            traces.append(f"[Trace ERROR] Không tìm thấy serial '{serial_number}' trong bảng product_instances.")
            return {
                "serial_number": serial_number,
                "product_name": None,
                "purchase_date": None,
                "warranty_duration_months": None,
                "calculated_end_date": None,
                "frozen_end_date": None,
                "check_date": check_date,
                "is_valid": False,
                "days_remaining": 0,
                "status_message": "SERIAL_NOT_FOUND",
                "debug_traces": traces
            }

        product = db.query(Product).filter(Product.id == instance.product_id).first()
        product_name = product.name if product else "Unknown"
        purchase_date = instance.purchase_date
        warranty_duration_months = product.warranty_duration_months if product else 12
        frozen_end_date = instance.warranty_end_date
        calculated_end_date = add_months_to_date(purchase_date, warranty_duration_months)
        traces.append(f"[Step 3] Tìm thấy sản phẩm: '{product_name}', Ngày mua: {purchase_date}, Hạn BH mặc định: {warranty_duration_months} tháng.")
        traces.append(f"[Step 4] Ngày kết thúc BH đóng băng trong DB: {frozen_end_date}. Ngày kết thúc BH tính toán lại: {calculated_end_date}.")
        
        if frozen_end_date != calculated_end_date:
            traces.append(f"[Trace WARNING] Có sự chênh lệch giữa ngày đóng băng ({frozen_end_date}) và ngày tính lại ({calculated_end_date}) do gia hạn hoặc điều chỉnh hợp đồng.")
    else:
        traces.append("[Step 2] Chế độ kiểm tra độc lập (Standalone simulation không dùng serial DB).")
        if not purchase_date or not warranty_duration_months:
            traces.append("[Trace ERROR] Thiếu thông tin purchase_date hoặc warranty_duration_months.")
            return {
                "serial_number": None,
                "product_name": None,
                "purchase_date": purchase_date,
                "warranty_duration_months": warranty_duration_months,
                "calculated_end_date": None,
                "frozen_end_date": None,
                "check_date": check_date,
                "is_valid": False,
                "days_remaining": 0,
                "status_message": "MISSING_INPUT_PARAMETERS",
                "debug_traces": traces
            }
        calculated_end_date = add_months_to_date(purchase_date, warranty_duration_months)
        frozen_end_date = calculated_end_date
        traces.append(f"[Step 3] Ngày mua: {purchase_date}, Thời hạn: {warranty_duration_months} tháng -> Ngày hết hạn: {calculated_end_date}.")

    # So sánh điều kiện bảo hành BR2
    effective_end_date = frozen_end_date if frozen_end_date else calculated_end_date
    delta_days = (effective_end_date - check_date).days
    is_valid = (effective_end_date >= check_date)

    traces.append(f"[Step 5] Đối chiếu BR2: effective_end_date ({effective_end_date}) >= check_date ({check_date}) -> {is_valid}")
    traces.append(f"[Step 6] Chênh lệch số ngày: {delta_days} ngày. (Dương: còn hạn, Âm: quá hạn)")

    if is_valid:
        status_msg = f"CÒN HẠN BẢO HÀNH (Còn {delta_days} ngày)"
        traces.append(f"[Result PASS] Điều kiện BR2 ĐẠT. Sản phẩm còn thời hạn bảo hành hợp lệ.")
    else:
        status_msg = f"HẾT HẠN BẢO HÀNH (Quá hạn {abs(delta_days)} ngày)"
        traces.append(f"[Result FAIL] Điều kiện BR2 KHÔNG ĐẠT. Sản phẩm đã quá hạn bảo hành.")

    return {
        "serial_number": serial_number,
        "product_name": product_name,
        "purchase_date": purchase_date,
        "warranty_duration_months": warranty_duration_months,
        "calculated_end_date": calculated_end_date,
        "frozen_end_date": frozen_end_date,
        "check_date": check_date,
        "is_valid": is_valid,
        "days_remaining": delta_days,
        "status_message": status_msg,
        "debug_traces": traces
    }
