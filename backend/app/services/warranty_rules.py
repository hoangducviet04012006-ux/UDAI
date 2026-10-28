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

# Danh sách trạng thái đang mở theo quy định mới:
# Một serial chỉ có 1 phiếu chưa đóng tại một thời điểm,
# bao gồm cả phiếu Hoàn tất/Từ chối đang chờ trả máy.
# Chỉ khi phiếu chuyển sang RETURNED (Đã trả máy) thì mới tính là đã đóng.
OPEN_TICKET_STATUSES = ["RECEIVED", "INSPECTING", "REPAIRING", "COMPLETED", "REJECTED"]

# Nhãn tiếng Việt của 6 trạng thái vòng đời phiếu
TICKET_STATUS_LABELS = {
    "RECEIVED": "Tiếp nhận",
    "INSPECTING": "Kiểm tra",
    "REPAIRING": "Sửa chữa",
    "COMPLETED": "Hoàn tất",
    "REJECTED": "Từ chối",
    "RETURNED": "Đã trả máy",
}

# Ma trận chuyển trạng thái hợp lệ theo yêu cầu nghiệp vụ chuẩn:
# Luồng sửa chữa: RECEIVED -> INSPECTING -> REPAIRING -> COMPLETED -> RETURNED
# Luồng từ chối : INSPECTING -> REJECTED -> RETURNED
# Không chuyển tắt, không chuyển ngược, không mở lại phiếu đã đóng (RETURNED là terminal state).
ALLOWED_TRANSITIONS = {
    "RECEIVED": ["INSPECTING"],
    "INSPECTING": ["REPAIRING", "REJECTED"],
    "REPAIRING": ["COMPLETED"],
    "COMPLETED": ["RETURNED"],
    "REJECTED": ["RETURNED"],
    "RETURNED": [],
}

# Tiến trình 5 bước luồng sửa chữa (hiển thị trên màn hình phiếu)
TICKET_STEPS: List[Dict[str, Any]] = [
    {"step": 1, "status": "RECEIVED", "label": "Tiếp nhận"},
    {"step": 2, "status": "INSPECTING", "label": "Kiểm tra"},
    {"step": 3, "status": "REPAIRING", "label": "Sửa chữa"},
    {"step": 4, "status": "COMPLETED", "label": "Hoàn tất"},
    {"step": 5, "status": "RETURNED", "label": "Đã trả máy"},
]

# Mô tả ngắn gọn cho từng trạng thái
TICKET_STATUS_HINTS: Dict[str, str] = {
    "RECEIVED": "Đã nhận máy và lập phiếu tại quầy. Cần phân công kỹ thuật viên để bắt đầu kiểm tra.",
    "INSPECTING": "Kỹ thuật viên đang kiểm tra, xác định lỗi và điều kiện bảo hành.",
    "REPAIRING": "Đang thực hiện sửa chữa thiết bị theo bảo hành.",
    "COMPLETED": "Đã sửa xong, đã kiểm tra kết quả đạt yêu cầu, đang chờ khách nhận máy.",
    "REJECTED": "Quản lý đã xác nhận từ chối bảo hành, có lý do, đang chờ trả máy cho khách.",
    "RETURNED": "Đã bàn giao máy cho khách và đóng phiếu bảo hành.",
}


class BusinessRuleError(HTTPException):
    """
    Lỗi nghiệp vụ trả ra API.
    - `detail`      : nội dung kỹ thuật (giữ định dạng để phục vụ kiểm thử).
    - `user_message`: câu tiếng Việt thân thiện cho nhân viên.
    - `error_code`  : mã nghiệp vụ ngắn.
    - `hint`        : việc cần làm tiếp theo.
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
TRANSITION_RULES: Dict[Tuple[str, str], Dict[str, Any]] = {
    ("RECEIVED", "INSPECTING"): {
        "target": "INSPECTING",
        "button_label": "Bắt đầu kiểm tra",
        "confirm_question": "Bắt đầu chuyển phiếu sang Kiểm tra?",
        "description": "Đưa máy vào kiểm tra. Bắt buộc phải có kỹ thuật viên phụ trách.",
        "permission": PERM_TICKET_UPDATE_STATUS,
        "style": "warning",
        "fields": ["technician_id", "note"],
        "requires_input": False,
        "note_label": "Ghi chú tiếp nhận (không bắt buộc)",
        "note_placeholder": "Ví dụ: Đã nhận máy tại quầy, chuyển kỹ thuật viên kiểm tra",
    },
    ("INSPECTING", "REPAIRING"): {
        "target": "REPAIRING",
        "button_label": "Bắt đầu sửa chữa",
        "confirm_question": "Chuyển phiếu sang Sửa chữa?",
        "description": "Bắt buộc có chẩn đoán và kết quả xác định đủ điều kiện bảo hành.",
        "permission": PERM_TICKET_UPDATE_STATUS,
        "style": "primary",
        "fields": ["diagnosis_note", "error_category_id", "is_warranty_eligible", "warranty_check_note", "note"],
        "requires_input": True,
        "note_label": "Ghi chú kỹ thuật (không bắt buộc)",
        "note_placeholder": "Ví dụ: Đủ điều kiện bảo hành, tiến hành thay linh kiện",
    },
    ("INSPECTING", "REJECTED"): {
        "target": "REJECTED",
        "button_label": "Xác nhận từ chối",
        "confirm_question": "Xác nhận từ chối bảo hành phiếu này?",
        "description": "Chỉ Quản lý xác nhận. Bắt buộc có lý do từ chối bảo hành.",
        "permission": PERM_TICKET_REJECT,
        "style": "danger",
        "fields": ["rejection_reason", "note"],
        "requires_input": True,
        "note_label": "Lý do từ chối bảo hành (bắt buộc)",
        "note_placeholder": "Ví dụ: Thiết bị vào nước, rơi vỡ, không thuộc phạm vi bảo hành",
    },
    ("REPAIRING", "COMPLETED"): {
        "target": "COMPLETED",
        "button_label": "Xác nhận hoàn tất",
        "confirm_question": "Xác nhận sửa xong và chuyển sang Hoàn tất (chờ trả máy)?",
        "description": "Bắt buộc có nội dung xử lý và kết quả kiểm tra sau sửa đạt yêu cầu.",
        "permission": PERM_TICKET_UPDATE_STATUS,
        "style": "primary",
        "fields": ["repair_content", "repair_parts", "repair_note", "repair_test_passed", "repair_test_note", "note"],
        "requires_input": True,
        "note_label": "Ghi chú bàn giao nội bộ (không bắt buộc)",
        "note_placeholder": "Ví dụ: Máy chạy thử ổn định 2 giờ, nhiệt độ tốt, sẵn sàng trả khách",
    },
    ("COMPLETED", "RETURNED"): {
        "target": "RETURNED",
        "button_label": "Xác nhận trả máy",
        "confirm_question": "Xác nhận đã bàn giao máy cho khách và đóng phiếu?",
        "description": "Bàn giao thiết bị đã sửa xong cho khách, lưu người trả và thời điểm trả.",
        "permission": PERM_TICKET_HANDOVER,
        "style": "success",
        "fields": ["handover_note", "note"],
        "requires_input": True,
        "note_label": "Ghi chú khi bàn giao (không bắt buộc)",
        "note_placeholder": "Ví dụ: Khách đã kiểm tra máy, nhận lại phiếu và linh kiện cũ",
    },
    ("REJECTED", "RETURNED"): {
        "target": "RETURNED",
        "button_label": "Xác nhận trả máy",
        "confirm_question": "Xác nhận đã bàn giao trả lại máy từ chối bảo hành cho khách và đóng phiếu?",
        "description": "Bàn giao trả lại máy từ chối cho khách, lưu người trả và thời điểm trả.",
        "permission": PERM_TICKET_HANDOVER,
        "style": "success",
        "fields": ["handover_note", "note"],
        "requires_input": True,
        "note_label": "Ghi chú khi bàn giao (không bắt buộc)",
        "note_placeholder": "Ví dụ: Đã giải thích lý do từ chối cho khách và bàn giao lại nguyên trạng máy",
    },
}


def transition_rule(current_status: str, new_status: str) -> Optional[Dict[str, Any]]:
    """Lấy mô tả hành động tương ứng một chuyển trạng thái (None nếu không có)."""
    return TRANSITION_RULES.get((current_status, new_status))


def available_transitions(current_status: str, has_permission_fn) -> List[Dict[str, Any]]:
    """
    Danh sách hành động mà người dùng được phép thực hiện ở trạng thái hiện tại.
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
    Nếu không tìm thấy -> Thông báo lỗi và không tạo phiếu.
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


def check_instance_warranty_status(instance: ProductInstance, check_date: Optional[date] = None) -> Tuple[bool, int]:
    """
    Kiểm tra tình trạng bảo hành của thiết bị tại thời điểm check_date:
    - Nếu thiếu ngày mua hoặc hạn bảo hành: raise BusinessRuleError (không tự lấy ngày tiếp nhận làm ngày mua).
    - Trả về (is_valid, days_diff):
      + is_valid=True: còn hạn (warranty_end_date >= check_date; ngày hết hạn vẫn được tính còn hạn), days_diff là số ngày còn lại.
      + is_valid=False: hết hạn (warranty_end_date < check_date), days_diff là số ngày đã quá hạn.
    """
    if check_date is None:
        check_date = date.today()

    if instance.purchase_date is None or instance.warranty_end_date is None:
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"[BR2 FAIL] Thiết bị '{instance.serial_number}' thiếu thông tin ngày mua / hạn bảo hành. Không thể tự lấy ngày tiếp nhận làm ngày mua.",
            user_message=(
                f"Thiết bị \"{instance.serial_number}\" chưa có thông tin ngày mua hợp lệ trong hồ sơ. "
                "Hệ thống không tự ý lấy ngày tiếp nhận làm ngày mua, vui lòng cập nhật hồ sơ mua hàng của thiết bị trước."
            ),
            error_code="BR2_MISSING_PURCHASE_DATE",
            hint="Kiểm tra hoá đơn hoặc giấy tờ mua hàng để cập nhật ngày mua chính xác.",
        )

    if instance.warranty_end_date < check_date:
        days_expired = (check_date - instance.warranty_end_date).days
        return False, days_expired
    days_remaining = (instance.warranty_end_date - check_date).days
    return True, days_remaining


def validate_br2_warranty_valid(instance: ProductInstance, check_date: Optional[date] = None) -> date:
    """
    Kiểm tra máy còn hạn bảo hành (raise lỗi nếu hết hạn).
    Dùng khi kiểm tra điều kiện sửa chữa theo diện bảo hành.
    """
    if check_date is None:
        check_date = date.today()
    is_valid, days_diff = check_instance_warranty_status(instance, check_date)
    if not is_valid:
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"[BR2 FAIL] Sản phẩm với serial '{instance.serial_number}' đã hết hạn bảo hành vào ngày "
                f"{instance.warranty_end_date.strftime('%d/%m/%Y')} (đã quá hạn {days_diff} ngày so với ngày "
                f"kiểm tra {check_date.strftime('%d/%m/%Y')}). Không được sửa chữa theo diện bảo hành."
            ),
            user_message=(
                f"Thiết bị có số sê-ri \"{instance.serial_number}\" đã hết hạn bảo hành từ ngày "
                f"{instance.warranty_end_date.strftime('%d/%m/%Y')} (quá hạn {days_diff} ngày), "
                "nên không đủ điều kiện sửa chữa bảo hành."
            ),
            error_code="BR2_WARRANTY_EXPIRED",
            hint="Chuyển hồ sơ sang luồng Từ chối bảo hành (INSPECTING -> REJECTED -> RETURNED).",
        )
    return check_date


def validate_br3_no_open_tickets(db: Session, product_instance_id: int):
    """
    BR3: Sản phẩm chỉ có một phiếu chưa đóng tại một thời điểm,
    bao gồm cả phiếu Hoàn tất/Từ chối đang chờ trả.
    Các trạng thái đang mở: RECEIVED, INSPECTING, REPAIRING, COMPLETED, REJECTED.
    Chỉ khi phiếu trước đó đã chuyển sang RETURNED (Đã trả máy) thì mới được tạo phiếu mới.
    """
    open_ticket = db.query(WarrantyTicket).filter(
        WarrantyTicket.product_instance_id == product_instance_id,
        WarrantyTicket.status.in_(OPEN_TICKET_STATUSES)
    ).first()

    if open_ticket:
        status_name = TICKET_STATUS_LABELS.get(open_ticket.status, open_ticket.status)
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"[BR3 FAIL] Sản phẩm đang có phiếu bảo hành chưa hoàn tất (Mã phiếu: '{open_ticket.ticket_code}', "
                f"Trạng thái hiện tại: '{open_ticket.status}'). Không tạo phiếu mới để tránh trùng lặp."
            ),
            user_message=(
                f"Thiết bị này đang có phiếu bảo hành chưa đóng: {open_ticket.ticket_code} ({status_name}). "
                "Mỗi thiết bị chỉ có một phiếu chưa đóng tại một thời điểm (kể cả phiếu đang chờ trả máy). "
                "Vui lòng xử lý hoặc hoàn tất trả máy cho phiếu cũ trước khi lập phiếu mới."
            ),
            error_code="BR3_OPEN_TICKET_EXISTS",
            hint=f"Mở phiếu {open_ticket.ticket_code} để tiếp tục xử lý thay vì tạo phiếu trùng.",
        )


def validate_br4_owner_verification(instance: ProductInstance, request_customer_id: int):
    """
    BR4: Khách hàng yêu cầu tiếp nhận phải trùng khớp với chủ sở hữu đã đăng ký.
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
                f"Khách hàng yêu cầu tiếp nhận không phải chủ sở hữu đã đăng ký của thiết bị "
                f"\"{instance.serial_number}\". Vui lòng kiểm tra lại thông tin chủ sở hữu trước khi lập phiếu bảo hành."
            ),
            error_code="BR4_OWNER_MISMATCH",
            hint="Đối chiếu lại thông tin chủ sở hữu thiết bị; chỉ chủ sở hữu đã đăng ký mới được tiếp nhận bảo hành.",
        )


def validate_state_transition(current_status: str, new_status: str, rejection_reason: Optional[str] = None):
    """
    Kiểm tra chuyển trạng thái theo State Machine chuẩn:
    - TIẾP NHẬN -> KIỂM TRA -> SỬA CHỮA -> HOÀN TẤT -> ĐÃ TRẢ MÁY
    - KIỂM TRA -> TỪ CHỐI -> ĐÃ TRẢ MÁY
    - Không chuyển tắt, không chuyển ngược, không mở lại phiếu đã đóng.
    """
    allowed = ALLOWED_TRANSITIONS.get(current_status, [])
    if new_status not in allowed:
        current_label = TICKET_STATUS_LABELS.get(current_status, current_status)
        new_label = TICKET_STATUS_LABELS.get(new_status, new_status)
        allowed_labels = ", ".join(
            f"{code} ({TICKET_STATUS_LABELS.get(code, code)})" for code in allowed
        ) or "Không có (phiếu đã đóng)"
        rule = transition_rule(current_status, new_status)
        
        if current_status == "REPAIRING" and new_status in ("RETURNED", "WAITING_RETURN"):
            user_message = (
                "Chưa thể trả máy. Thiết bị đang ở trạng thái Sửa chữa, "
                "cần xác nhận Hoàn tất trước khi bàn giao trả máy cho khách."
            )
            hint = "Bấm \"Xác nhận hoàn tất\" trước, sau đó bấm \"Xác nhận trả máy\"."
        elif current_status == "COMPLETED" and new_status == "REPAIRING":
            user_message = "Không cho phép chuyển ngược phiếu từ Hoàn tất về Sửa chữa."
            hint = "Quy trình không hỗ trợ chuyển ngược trạng thái."
        elif rule:
            user_message = f"Không thực hiện được thao tác \"{rule['button_label']}\" vì phiếu đang ở trạng thái \"{current_label}\"."
            hint = f"Trạng thái tiếp theo hợp lệ: {allowed_labels}."
        else:
            user_message = f"Phiếu đang ở trạng thái \"{current_label}\" nên không thể chuyển sang \"{new_label}\"."
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
            hint="Ví dụ: Thiết bị vào nước, rơi vỡ, hoặc không thuộc phạm vi bảo hành.",
        )


def validate_ticket_technician_assignment(ticket: WarrantyTicket, assigned_technician_id: Optional[int] = None):
    """
    Quy tắc: Trước khi chuyển sang Kiểm tra phải có kỹ thuật viên phụ trách.
    """
    effective_tech_id = assigned_technician_id or ticket.assigned_technician_id
    if not effective_tech_id:
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="[WORKFLOW REQUIRED] Phiếu chưa có kỹ thuật viên phụ trách. Bắt buộc phân công kỹ thuật viên trước khi chuyển sang Kiểm tra.",
            user_message="Phiếu chưa có kỹ thuật viên phụ trách. Vui lòng phân công kỹ thuật viên trước khi bắt đầu kiểm tra.",
            error_code="WORKFLOW_TECH_REQUIRED",
            hint="Chỉ định kỹ thuật viên phụ trách phiếu để tiếp tục.",
        )


def validate_inspecting_to_repairing(
    ticket: WarrantyTicket,
    diagnosis_note: Optional[str] = None,
    is_warranty_eligible: Optional[bool] = None,
):
    """
    Quy tắc: Kiểm tra -> Sửa chữa: phải có chẩn đoán và kết quả xác định đủ điều kiện bảo hành.
    """
    effective_diag = (diagnosis_note or "").strip() or (ticket.diagnosis_note or "").strip()
    if not effective_diag:
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="[WORKFLOW REQUIRED] Chuyển sang SỬA CHỮA bắt buộc phải có chẩn đoán của kỹ thuật viên.",
            user_message="Vui lòng ghi nhận kết luận chẩn đoán trước khi chuyển phiếu sang sửa chữa.",
            error_code="WORKFLOW_DIAGNOSIS_REQUIRED",
            hint="Ghi rõ hiện tượng hư hỏng và kết luận kỹ thuật.",
        )

    # [BR2]: Kiểm tra hạn bảo hành - Máy hết hạn KHÔNG được phép chuyển sang sửa chữa bảo hành
    inst = ticket.product_instance
    if inst:
        ref_date = ticket.created_at.date() if ticket.created_at else date.today()
        is_valid_warranty, days_diff = check_instance_warranty_status(inst, ref_date)
        if not is_valid_warranty:
            raise BusinessRuleError(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"[BR2 FAIL] Thiết bị '{inst.serial_number}' đã hết hạn bảo hành từ ngày "
                    f"{inst.warranty_end_date.strftime('%d/%m/%Y')} (quá hạn {days_diff} ngày). "
                    "Không được phép chuyển sang SỬA CHỮA bảo hành. Phiếu phải chuyển qua luồng Từ chối bảo hành (INSPECTING -> REJECTED -> RETURNED)."
                ),
                user_message=(
                    f"Thiết bị \"{inst.serial_number}\" đã hết hạn bảo hành từ ngày "
                    f"{inst.warranty_end_date.strftime('%d/%m/%Y')} nên không đủ điều kiện sửa chữa bảo hành. "
                    "Vui lòng đề xuất từ chối để Quản lý duyệt từ chối bảo hành."
                ),
                error_code="BR2_WARRANTY_EXPIRED",
                hint="Kỹ thuật viên ghi đề xuất từ chối để Quản lý duyệt từ chối bảo hành.",
            )

    # Xác định điều kiện bảo hành: phải là True
    effective_eligible = is_warranty_eligible if is_warranty_eligible is not None else ticket.is_warranty_eligible
    if effective_eligible is not True:
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="[WORKFLOW REQUIRED] Chuyển sang SỬA CHỮA bắt buộc phải có kết quả xác định đủ điều kiện bảo hành (is_warranty_eligible=True).",
            user_message="Thiết bị chưa được xác nhận đủ điều kiện bảo hành. Chỉ tiếp nhận sửa chữa khi đã xác định đủ điều kiện bảo hành.",
            error_code="WORKFLOW_WARRANTY_ELIGIBLE_REQUIRED",
            hint="Xác nhận đủ điều kiện bảo hành nếu lỗi thuộc diện được bảo hành, hoặc đề xuất từ chối nếu không thuộc phạm vi.",
        )


def validate_repairing_to_completed(
    ticket: WarrantyTicket,
    repair_content: Optional[str] = None,
    repair_test_passed: Optional[bool] = None,
    note: Optional[str] = None,
):
    """
    Quy tắc: Sửa chữa -> Hoàn tất: phải có nội dung xử lý và kết quả kiểm tra sau sửa đạt yêu cầu.
    """
    effective_content = (repair_content or "").strip() or (ticket.repair_content or "").strip() or (note or "").strip()
    if not effective_content:
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="[WORKFLOW REQUIRED] Chuyển sang HOÀN TẤT bắt buộc phải có nội dung xử lý sửa chữa.",
            user_message="Vui lòng ghi nhận nội dung đã sửa chữa / linh kiện đã thay trước khi chuyển sang Hoàn tất.",
            error_code="WORKFLOW_REPAIR_CONTENT_REQUIRED",
            hint="Ghi ngắn gọn việc đã sửa và linh kiện thay thế.",
        )

    effective_test_passed = repair_test_passed if repair_test_passed is not None else ticket.repair_test_passed
    if effective_test_passed is not True:
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="[WORKFLOW REQUIRED] Chuyển sang HOÀN TẤT bắt buộc phải có kết quả kiểm tra sau sửa đạt yêu cầu (repair_test_passed=True).",
            user_message="Chưa xác nhận kết quả kiểm tra sau sửa đạt yêu cầu. Vui lòng chạy thử và xác nhận đạt yêu cầu trước khi chuyển Hoàn tất.",
            error_code="WORKFLOW_REPAIR_TEST_REQUIRED",
            hint="Kiểm tra chạy thử thiết bị và tích chọn kết quả kiểm tra đạt yêu cầu.",
        )


def validate_to_returned(
    ticket: WarrantyTicket,
    actor: User,
    handover_note: Optional[str] = None,
    note: Optional[str] = None,
):
    """
    Quy tắc: Hoàn tất/Từ chối -> Đã trả máy: phải xác nhận bàn giao, lưu người trả và thời điểm trả.
    Chỉ Tiếp nhận hoặc Quản lý được xác nhận trả máy.
    """
    if actor.role == "TECHNICIAN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kỹ thuật viên không có quyền xác nhận trả máy cho khách. Việc này thuộc quầy tiếp nhận hoặc quản lý.",
        )

    effective_handover = (handover_note or "").strip() or (note or "").strip() or (ticket.handover_note or "").strip()
    if not effective_handover:
        raise BusinessRuleError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="[WORKFLOW REQUIRED] Xác nhận trả máy bắt buộc phải ghi nhận thông tin / ghi chú bàn giao cho khách.",
            user_message="Vui lòng ghi thông tin bàn giao (tình trạng máy khi trả, người nhận máy) trước khi đóng phiếu.",
            error_code="WORKFLOW_HANDOVER_REQUIRED",
            hint="Ví dụ: Khách đã kiểm tra máy, ký biên bản nhận lại máy.",
        )


def validate_ticket_actor_access(ticket: WarrantyTicket, actor: User, is_technical: bool = False):
    """
    Kiểm tra quyền theo từng phiếu:
    - Tiếp nhận: Không được làm thao tác kỹ thuật (chẩn đoán, sửa chữa, kết luận lỗi).
    - Kỹ thuật viên: Chỉ được thao tác trên phiếu được phân công cho mình.
    - Quản lý: Chỉ thao tác trong trung tâm bảo hành được phân công.
    """
    if actor.role == "RECEPTIONIST" and is_technical:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Nhân viên tiếp nhận '{actor.username}' không được phép thực hiện thao tác kỹ thuật (chẩn đoán, sửa chữa, kết luận lỗi).",
        )
    if actor.role == "TECHNICIAN":
        if ticket.assigned_technician_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Phiếu chưa có kỹ thuật viên phụ trách. Kỹ thuật viên '{actor.username}' chỉ được thao tác trên phiếu được giao cho mình.",
            )
        if ticket.assigned_technician_id != actor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Kỹ thuật viên '{actor.username}' không được thao tác trên phiếu của kỹ thuật viên khác (phiếu đang giao cho nhân viên ID {ticket.assigned_technician_id}).",
            )
    if actor.role == "MANAGER":
        if ticket.service_center_id and actor.service_center_id and ticket.service_center_id != actor.service_center_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Quản lý không thuộc trung tâm bảo hành tiếp nhận phiếu này.",
            )


def completion_blockers(db: Session, ticket: WarrantyTicket) -> List[str]:
    """Danh sách lý do vì sao phiếu chưa thể trả máy / đóng phiếu."""
    if ticket is None:
        return ["Không tìm thấy phiếu bảo hành."]

    blockers: List[str] = []
    status_label = TICKET_STATUS_LABELS.get(ticket.status, ticket.status)

    if ticket.status not in ("COMPLETED", "REJECTED"):
        blockers.append(
            f"Thiết bị đang ở trạng thái \"{status_label}\". Phiếu phải ở Hoàn tất hoặc Từ chối mới được xác nhận trả máy."
        )

    if ticket.status == "COMPLETED":
        if not ticket.repair_content and not ticket.repair_note:
            blockers.append("Chưa ghi nhận nội dung sửa chữa của thiết bị.")
        if ticket.repair_test_passed is not True:
            blockers.append("Chưa xác nhận kết quả kiểm tra sau sửa đạt yêu cầu.")

    return blockers


def completion_checklist(ticket: WarrantyTicket) -> List[Dict[str, Any]]:
    """Điều kiện trả máy thực tế để hiển thị trên màn hình phiếu (loại bỏ chi tiết kỹ thuật hệ thống)."""
    if ticket is None:
        return []
    is_ready_status = ticket.status in ("COMPLETED", "REJECTED")
    has_repair = bool(ticket.repair_content or ticket.repair_note)
    test_passed = ticket.repair_test_passed is True

    return [
        {"key": "assigned_tech", "label": "Đã có kỹ thuật viên phụ trách", "satisfied": ticket.assigned_technician_id is not None},
        {"key": "status_ready", "label": "Thiết bị ở trạng thái Hoàn tất hoặc Từ chối", "satisfied": is_ready_status},
        {"key": "repair_info", "label": "Đã ghi nhận nội dung sửa chữa (với sửa chữa)", "satisfied": has_repair or ticket.status == "REJECTED"},
        {"key": "test_passed", "label": "Đã kiểm tra sau sửa đạt yêu cầu (với sửa chữa)", "satisfied": test_passed or ticket.status == "REJECTED"},
    ]


def validate_service_center_exists(db: Session, service_center_id: int) -> ServiceCenter:
    center = db.query(ServiceCenter).filter(ServiceCenter.id == service_center_id).first()
    if not center:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy trung tâm bảo hành với ID: {service_center_id}."
        )
    return center


def validate_user_exists(db: Session, user_id: int, user_label: str = "nhân viên") -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy {user_label} với ID: {user_id}."
        )
    return user


def validate_error_category_exists(db: Session, category_id: int) -> ErrorCategory:
    category = db.query(ErrorCategory).filter(ErrorCategory.id == category_id).first()
    if not category:
        raise BusinessRuleError(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy nhãn loại lỗi với ID: {category_id}.",
            user_message="Không tìm thấy loại lỗi đã chọn. Vui lòng chọn lại loại lỗi trong danh sách.",
            error_code="ERROR_CATEGORY_NOT_FOUND",
            hint="Chọn một nhãn lỗi trong danh sách.",
        )
    return category


def add_months_to_date(source_date: date, months: int) -> date:
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
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
            traces.append(f"[Trace WARNING] Có sự chênh lệch giữa ngày đóng băng ({frozen_end_date}) và ngày tính lại ({calculated_end_date}).")
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

    effective_end_date = frozen_end_date if frozen_end_date else calculated_end_date
    delta_days = (effective_end_date - check_date).days
    is_valid = (effective_end_date >= check_date)

    traces.append(f"[Step 5] Đối chiếu BR2: effective_end_date ({effective_end_date}) >= check_date ({check_date}) -> {is_valid}")
    traces.append(f"[Step 6] Chênh lệch số ngày: {delta_days} ngày. (Dương/0: còn hạn, Âm: quá hạn)")

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
