from datetime import datetime, date
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field, EmailStr

# ----------------- Product Schemas -----------------
class ProductBase(BaseModel):
    name: str = Field(..., max_length=100, description="Tên model sản phẩm")
    brand: Optional[str] = Field(None, max_length=50, description="Thương hiệu")
    category: Optional[str] = Field(None, max_length=50, description="Ngành hàng/chủng loại")
    warranty_duration_months: int = Field(..., gt=0, description="Thời hạn bảo hành mặc định (tháng)")
    description: Optional[str] = Field(None, description="Mô tả sản phẩm")

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    warranty_duration_months: Optional[int] = Field(None, gt=0)
    description: Optional[str] = None

class ProductResponse(ProductBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ----------------- Customer Schemas -----------------
class CustomerBase(BaseModel):
    full_name: str = Field(..., max_length=100, description="Họ và tên khách hàng")
    phone: str = Field(..., max_length=20, description="Số điện thoại liên hệ")
    email: Optional[str] = Field(None, max_length=100, description="Email khách hàng")
    address: Optional[str] = Field(None, max_length=255, description="Địa chỉ")

class CustomerCreate(CustomerBase):
    pass

class CustomerUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None

class CustomerResponse(CustomerBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ----------------- Product Instance Schemas -----------------
class ProductInstanceBase(BaseModel):
    product_id: int
    customer_id: int
    serial_number: str
    purchase_date: date
    warranty_end_date: date
    status: str = "ACTIVE"

class ProductInstanceCreate(ProductInstanceBase):
    pass

class ProductInstanceResponse(ProductInstanceBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ----------------- Serial Product (Sản phẩm theo Serial) Schemas -----------------
# Đây là nhóm schema phục vụ CRUD "Sản phẩm có Serial" theo yêu cầu KT2:
# Tên sản phẩm + Serial + Ngày mua + Ngày hết hạn bảo hành + Thông tin mô tả.
class SerialProductCreate(BaseModel):
    serial_number: str = Field(..., max_length=100, description="Số serial của sản phẩm (bắt buộc, duy nhất)")
    customer_id: int = Field(..., gt=0, description="ID khách hàng / chủ sở hữu sản phẩm")
    purchase_date: date = Field(..., description="Ngày mua sản phẩm")
    product_id: Optional[int] = Field(None, gt=0, description="ID model sản phẩm nếu đã tồn tại trong bảng products")
    product_name: Optional[str] = Field(None, max_length=100, description="Tên sản phẩm (dùng khi chưa có product_id)")
    brand: Optional[str] = Field(None, max_length=50, description="Thương hiệu (chỉ dùng khi tạo mới model)")
    category: Optional[str] = Field(None, max_length=50, description="Ngành hàng (chỉ dùng khi tạo mới model)")
    warranty_duration_months: Optional[int] = Field(None, gt=0, description="Thời hạn bảo hành (tháng); mặc định lấy theo model")
    warranty_end_date: Optional[date] = Field(None, description="Ngày hết hạn bảo hành; nếu bỏ trống hệ thống tự tính = ngày mua + số tháng")
    description: Optional[str] = Field(None, description="Thông tin mô tả sản phẩm")
    status: str = Field("ACTIVE", pattern="^(ACTIVE|EXPIRED)$", description="Trạng thái: ACTIVE hoặc EXPIRED")

    class Config:
        from_attributes = True


class SerialProductUpdate(BaseModel):
    serial_number: Optional[str] = Field(None, max_length=100, description="Số serial mới")
    customer_id: Optional[int] = Field(None, gt=0, description="ID khách hàng mới")
    product_id: Optional[int] = Field(None, gt=0, description="ID model sản phẩm mới")
    purchase_date: Optional[date] = Field(None, description="Ngày mua mới")
    warranty_duration_months: Optional[int] = Field(None, gt=0, description="Thời hạn bảo hành (tháng) dùng để tính lại ngày hết hạn")
    warranty_end_date: Optional[date] = Field(None, description="Ngày hết hạn bảo hành (nếu cập nhật trực tiếp)")
    status: Optional[str] = Field(None, pattern="^(ACTIVE|EXPIRED)$")
    product_name: Optional[str] = Field(None, max_length=100)
    brand: Optional[str] = Field(None, max_length=50)
    category: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None, description="Cập nhật thông tin mô tả sản phẩm")


class SerialProductResponse(BaseModel):
    id: int
    product_id: int
    product_name: Optional[str]
    product_brand: Optional[str]
    product_category: Optional[str]
    description: Optional[str]
    customer_id: int
    customer_name: Optional[str]
    customer_phone: Optional[str]
    serial_number: str
    purchase_date: date
    warranty_end_date: date
    warranty_duration_months: Optional[int]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ----------------- Ticket Status History Schemas -----------------
class TicketStatusHistoryResponse(BaseModel):
    id: int
    ticket_id: int
    from_status: Optional[str]
    to_status: str
    changed_by: int
    note: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ----------------- Warranty Ticket Schemas -----------------
class WarrantyTicketCreate(BaseModel):
    serial_number: str = Field(..., description="Số serial của sản phẩm cần tiếp nhận (BR1)")
    customer_id: int = Field(..., description="ID khách hàng yêu cầu tiếp nhận (BR4)")
    service_center_id: int = Field(..., description="Trung tâm bảo hành tiếp nhận")
    created_by: int = Field(..., description="ID nhân viên tiếp nhận (RECEPTIONIST/MANAGER)")
    issue_description: str = Field(..., description="Mô tả lỗi của khách hàng")
    device_condition: Optional[str] = Field(None, description="Tình trạng ngoại quan khi tiếp nhận máy")
    accessories_accompanying: Optional[str] = Field(None, description="Phụ kiện nhận kèm theo máy")
    error_category_id: Optional[int] = Field(None, description="Danh mục lỗi (tùy chọn sau khi AI gợi ý/nhân viên review)")
    technician_id: Optional[int] = Field(None, description="ID kỹ thuật viên phụ trách (tùy chọn gán ngay khi lập phiếu)")

class WarrantyTicketAssign(BaseModel):
    technician_id: int = Field(..., gt=0, description="ID kỹ thuật viên được phân công phụ trách")
    note: Optional[str] = Field(None, description="Ghi chú phân công")

class WarrantyTicketProposal(BaseModel):
    proposal_note: str = Field(..., min_length=3, description="Đề xuất từ chối và bằng chứng kiểm tra của kỹ thuật viên")

class RejectionReviewRequest(BaseModel):
    decision: str = Field(..., pattern="^(APPROVED|DECLINED)$", description="APPROVED hoặc DECLINED")
    note: str = Field(..., min_length=3, description="Lý do chính thức hoặc ghi chú quyết định của Quản lý")

class WarrantyTicketStatusUpdate(BaseModel):
    new_status: str = Field(..., description="Trạng thái chuyển tiếp hợp lệ: INSPECTING, REPAIRING, COMPLETED, REJECTED, RETURNED")
    changed_by: int = Field(..., description="ID người thực hiện cập nhật")
    note: Optional[str] = Field(None, description="Ghi chú kèm theo việc cập nhật trạng thái")
    rejection_reason: Optional[str] = Field(None, description="Lý do từ chối (bắt buộc nếu chuyển sang REJECTED)")
    technician_id: Optional[int] = Field(None, description="Chỉ định KTV khi chuyển sang INSPECTING (nếu chưa có)")
    diagnosis_note: Optional[str] = Field(None, description="Kết luận chẩn đoán của kỹ thuật viên")
    error_category_id: Optional[int] = Field(None, description="Loại lỗi do kỹ thuật viên xác nhận")
    is_warranty_eligible: Optional[bool] = Field(None, description="Xác định đủ điều kiện bảo hành (True/False)")
    warranty_check_note: Optional[str] = Field(None, description="Ghi chú xác định điều kiện bảo hành")
    repair_content: Optional[str] = Field(None, description="Nội dung đã kiểm tra / đã sửa chữa")
    repair_parts: Optional[str] = Field(None, description="Linh kiện / thành phần đã thay thế")
    repair_note: Optional[str] = Field(None, description="Ghi chú kỹ thuật khi sửa chữa")
    repair_test_passed: Optional[bool] = Field(None, description="Kết quả kiểm tra sau sửa đạt yêu cầu (True/False)")
    repair_test_note: Optional[str] = Field(None, description="Ghi chú kiểm tra sau sửa")
    rejection_proposal_note: Optional[str] = Field(None, description="Đề xuất và bằng chứng kiểm tra của KTV")
    handover_note: Optional[str] = Field(None, description="Ghi chú khi bàn giao máy cho khách")

class TicketActionOption(BaseModel):
    """Một nút hành động mà backend CHO PHÉP người đang đăng nhập thực hiện."""

    target: str
    target_label: str
    button_label: str
    confirm_question: str
    description: str
    style: str = Field(..., description="primary / warning / success / danger")
    fields: List[str] = Field(default_factory=list, description="Các trường nghiệp vụ cần hỏi thêm")
    requires_input: bool = False
    requires_rejection_reason: bool = False
    note_label: str = "Ghi chú xử lý"
    note_placeholder: str = ""
    permission: str


class WarrantyTicketResponse(BaseModel):
    id: int
    ticket_code: str
    product_instance_id: int
    customer_id: int
    service_center_id: int
    created_by: int
    issue_description: str
    device_condition: Optional[str] = None
    accessories_accompanying: Optional[str] = None
    error_category_id: Optional[int]
    status: str
    # Phân công kỹ thuật viên phụ trách
    assigned_technician_id: Optional[int] = None
    assigned_technician_name: Optional[str] = None
    assigned_at: Optional[datetime] = None
    # Nhãn tiếng Việt + câu mô tả trạng thái (giao diện KHÔNG hiển thị mã enum cho nhân viên)
    status_label: Optional[str] = None
    status_hint: Optional[str] = None
    # Điều kiện bảo hành & kiểm tra sau sửa
    is_warranty_eligible: Optional[bool] = None
    warranty_check_note: Optional[str] = None
    repair_test_passed: Optional[bool] = None
    repair_test_note: Optional[str] = None
    # Nhánh từ chối
    rejection_reason: Optional[str]
    rejection_proposed_by: Optional[int]
    rejection_proposed_at: Optional[datetime]
    rejection_proposal_note: Optional[str] = None
    rejection_reviewed_by: Optional[int]
    rejection_reviewed_at: Optional[datetime]
    rejection_review_status: Optional[str]
    # Bàn giao & Đóng phiếu
    completed_at: Optional[datetime] = None
    handed_over_at: Optional[datetime]
    handed_over_by: Optional[int] = None
    handover_note: Optional[str] = None
    resolution: Optional[str] = None  # 'COMPLETED' (Sửa hoàn tất) hoặc 'REJECTED' (Từ chối)
    # Thông tin sản phẩm đính kèm phiếu
    serial_number: Optional[str] = None
    product_name: Optional[str] = None
    customer_name: Optional[str] = None
    warranty_end_date: Optional[date] = None
    customer_phone: Optional[str] = None
    error_category_name: Optional[str] = None
    handler_id: Optional[int] = None
    handler_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    status_history: List[TicketStatusHistoryResponse] = []
    available_actions: List[TicketActionOption] = Field(
        default_factory=list, description="Các bước chuyển trạng thái mà vai trò hiện tại được phép"
    )
    primary_action: Optional[TicketActionOption] = Field(
        None, description="Hành động chính (nút duy nhất) của dòng, null nếu chỉ được xem"
    )
    action_label: str = Field(
        "Xem phiếu", description="Nhãn nút hành động chính của dòng (kèm câu chữ cho trường hợp chỉ xem)"
    )
    action_kind: str = Field(
        "read_only",
        pattern="^(transition|read_only)$",
        description="transition = bấm là chuyển bước; read_only = chỉ mở phiếu xem",
    )

    class Config:
        from_attributes = True


# ----------------- Debug Warranty Check Schemas (KT2) -----------------
class DebugWarrantyCheckRequest(BaseModel):
    serial_number: Optional[str] = Field(None, description="Số serial cần kiểm tra trong DB")
    purchase_date: Optional[date] = Field(None, description="Ngày mua (dùng kiểm tra chay)")
    warranty_duration_months: Optional[int] = Field(None, gt=0, description="Thời gian bảo hành (tháng)")
    check_date: Optional[date] = Field(None, description="Ngày đối chiếu kiểm tra (mặc định hôm nay)")

class DebugWarrantyCheckResponse(BaseModel):
    serial_number: Optional[str]
    product_name: Optional[str]
    purchase_date: Optional[date]
    warranty_duration_months: Optional[int]
    calculated_end_date: Optional[date]
    frozen_end_date: Optional[date]
    check_date: date
    is_valid: bool
    days_remaining: int
    status_message: str
    debug_traces: List[str]


# =====================================================================
# KT3 - AI-01: Gợi ý phân loại lỗi bảo hành (Error Classification)
# AI chỉ ĐỀ XUẤT, nhân viên (RECEPTIONIST/MANAGER) xét duyệt thủ công.
# =====================================================================

class AIClassificationOutput(BaseModel):
    """
    Đầu ra chuẩn của AI-01 (đúng cấu trúc JSON mà AI được yêu cầu trả về).
    - suggested_category_id = null khi AI không đủ căn cứ (guardrail).
    - confidence luôn nằm trong [0, 1] và <= 0.40 khi không có nhãn.
    """
    suggested_category_id: Optional[int] = Field(
        None, description="ID nhãn lỗi trong bảng error_categories; null nếu AI không đủ căn cứ"
    )
    suggested_category_name: Optional[str] = Field(
        None, max_length=100, description="Tên nhãn lỗi, phải khớp với suggested_category_id"
    )
    confidence: float = Field(
        0.0, ge=0.0, le=1.0, description="Độ tin cậy của AI trong khoảng 0 - 1"
    )
    reason: str = Field("", description="Giải thích ngắn gọn của AI (hoặc lý do đầu ra không hợp lệ)")
    need_more_information: List[str] = Field(
        default_factory=list, description="Danh sách thông tin cần hỏi thêm khi dữ liệu chưa đủ"
    )


class AIClassificationResponse(AIClassificationOutput):
    """Kết quả trả về của POST /api/v1/ai/tickets/{ticket_id}/classify-error (đã lưu vào ai_results)."""
    ai_result_id: int
    ticket_id: int
    ai_function: str = Field("ERROR_CLASSIFICATION", description="Mã chức năng AI")
    review_status: str = Field("PENDING", pattern="^(PENDING|APPROVED|REJECTED)$")
    provider: Optional[str] = Field(None, description="Provider AI đã dùng (mock/rule-based/openai...)")
    created_at: Optional[datetime] = Field(None, description="Thời điểm lưu kết quả AI")

    class Config:
        from_attributes = True


class AIResultResponse(BaseModel):
    """Bản ghi lưu vết trong bảng ai_results (GET /api/v1/ai/results/{result_id})."""
    id: int
    ticket_id: int
    ai_function: str
    input_data: Optional[Dict[str, Any]] = Field(None, description="Dữ liệu đầu vào đã loại bỏ PII")
    output_data: Optional[Dict[str, Any]] = Field(None, description="Đầu ra AI đã được kiểm tra hợp lệ")
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    reviewed_by: Optional[int] = None
    review_status: str = Field("PENDING", pattern="^(PENDING|APPROVED|REJECTED)$")
    created_at: datetime

    class Config:
        from_attributes = True


class AIReviewRequest(BaseModel):
    """Yêu cầu xét duyệt kết quả AI (human-in-the-loop)."""
    reviewed_by: int = Field(..., gt=0, description="ID người xét duyệt (MANAGER hoặc RECEPTIONIST)")
    decision: str = Field(..., pattern="^(APPROVED|REJECTED)$", description="APPROVED hoặc REJECTED")


class AIReviewResponse(BaseModel):
    """Kết quả xét duyệt. Chỉ khi APPROVED mới ghi nhãn vào warranty_tickets.error_category_id."""
    ai_result_id: int
    ticket_id: int
    ai_function: str
    review_status: str = Field(..., pattern="^(PENDING|APPROVED|REJECTED)$")
    reviewed_by: int
    reviewer_role: str
    decision: str = Field(..., pattern="^(APPROVED|REJECTED)$")
    applied_error_category_id: Optional[int] = Field(
        None, description="Nhãn lỗi được ghi vào phiếu (chỉ khi APPROVED); null khi REJECTED"
    )
    ticket_error_category_id: Optional[int] = Field(None, description="Nhãn lỗi hiện tại của phiếu sau xét duyệt")
    ticket_status: str = Field(..., description="Trạng thái phiếu (KHÔNG thay đổi bởi AI/review)")
    message: str


class AISuggestCategoryRequest(BaseModel):
    """Yêu cầu gợi ý loại lỗi trực tiếp từ mô tả (phục vụ lúc tiếp nhận máy mới hoặc kiểm tra)."""
    product_name: Optional[str] = Field(None, description="Tên dòng máy")
    issue_description: str = Field(..., min_length=3, description="Mô tả tình trạng lỗi của thiết bị")


class AIHistorySummaryResponse(BaseModel):
    """Kết quả tóm tắt lịch sử bảo hành của thiết bị/phiếu bằng AI."""
    device_id: Optional[int] = None
    serial_number: Optional[str] = None
    product_name: Optional[str] = None
    total_tickets: int = 0
    warranty_status: str
    summary: str
    history_highlights: List[str] = Field(default_factory=list)
    recommendation: Optional[str] = None
    provider_info: Dict[str, Any] = Field(default_factory=dict)


class AIProgressNotificationResponse(BaseModel):
    """Bản thảo tin nhắn cập nhật tiến độ do AI soạn để nhân viên xem, sửa và sao chép."""
    ticket_id: int
    ticket_code: str
    customer_name: Optional[str] = None
    device_name: Optional[str] = None
    current_status: str
    status_label: str
    draft_message: str
    provider_info: Dict[str, Any] = Field(default_factory=dict)


# =====================================================================
# Đợt 7 - Xác thực (Auth) & Phân quyền theo vai trò (RBAC)
# ---------------------------------------------------------------------
# Lưu ý: các schema trả về TUYỆT ĐỐI không chứa password_hash / mật khẩu.
# =====================================================================
class LoginRequest(BaseModel):
    username: str = Field(
        ..., min_length=1, max_length=50, description="Tên đăng nhập (ví dụ: manager)"
    )
    password: str = Field(
        ..., min_length=1, max_length=128, description="Mật khẩu làm việc (không lưu dạng thô)"
    )


class SessionMenuEntry(BaseModel):
    """Một mục menu mà vai trò hiện tại được phép thấy (backend là nguồn sự thật)."""

    tab: str = Field(..., description="Mã màn hình: dashboard / tickets / lookup / ...")
    label: str = Field(..., description="Nhãn tiếng Việt hiển thị trên menu")
    icon: str = Field("circle", description="Tên biểu tượng (lucide)")
    group: str = Field("work", pattern="^(work|reference|admin)$")
    group_label: str = Field("", description="Nhãn nhóm menu (ví dụ: Tra cứu nội bộ)")
    hint: str = Field("", description="Câu mô tả ngắn hiện khi rê chuột")
    permission: str = Field(..., description="Quyền tối thiểu để thấy mục menu này")


class UserSessionInfo(BaseModel):
    """Thông tin phiên làm việc hiện tại (trả cho giao diện để hiển thị + ẩn/hiện menu)."""

    id: int
    username: str
    full_name: str
    role: str = Field(..., description="MANAGER / RECEPTIONIST / TECHNICIAN")
    role_label: str = Field(..., description="Nhãn tiếng Việt của vai trò")
    service_center_id: Optional[int] = Field(None, description="Trung tâm bảo hành trực thuộc")
    permissions: List[str] = Field(
        default_factory=list,
        description="Danh sách quyền nghiệp vụ - giao diện dùng để ẩn/hiện chức năng",
    )
    menus: List[SessionMenuEntry] = Field(
        default_factory=list,
        description=(
            "Menu dành cho vai trò này (backend quyết định): nhóm 'work' là việc hằng ngày, "
            "nhóm 'reference' là sổ/danh mục tra cứu nội bộ"
        ),
    )


class LoginResponse(BaseModel):
    access_token: str = Field(..., description="Token phiên đăng nhập (gửi kèm header Authorization)")
    token_type: str = Field("bearer", description="Kiểu token")
    expires_in: int = Field(..., description="Số giây token còn hiệu lực")
    expires_at: str = Field(..., description="Thời điểm hết hạn (UTC, ISO 8601)")
    user: UserSessionInfo
    message: str = Field(..., description="Thông báo thân thiện hiển thị cho người dùng")


class LogoutResponse(BaseModel):
    success: bool = True
    message: str


class StaffUserCreate(BaseModel):
    """Quản lý tạo tài khoản nhân viên mới."""

    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(..., min_length=6, max_length=128, description="Mật khẩu tối thiểu 6 ký tự")
    full_name: str = Field(..., min_length=1, max_length=100)
    role: str = Field(..., pattern=r"^(MANAGER|RECEPTIONIST|TECHNICIAN)$")
    email: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    service_center_id: Optional[int] = Field(None, gt=0)
    active: bool = True


class StaffUserUpdate(BaseModel):
    """Quản lý cập nhật tài khoản. `new_password` để trống nếu không đổi mật khẩu."""

    full_name: Optional[str] = Field(None, min_length=1, max_length=100)
    role: Optional[str] = Field(None, pattern=r"^(MANAGER|RECEPTIONIST|TECHNICIAN)$")
    email: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    service_center_id: Optional[int] = Field(None, gt=0)
    active: Optional[bool] = None
    new_password: Optional[str] = Field(None, min_length=6, max_length=128)


class StaffUserResponse(BaseModel):
    """Thông tin tài khoản nhân viên trả ra ngoài (KHÔNG có mật khẩu/hash)."""

    id: int
    username: str
    full_name: str
    role: str
    role_label: str
    email: Optional[str] = None
    phone: Optional[str] = None
    service_center_id: Optional[int] = None
    active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class StaffUserListResponse(BaseModel):
    total: int
    items: List[StaffUserResponse]


# =====================================================================
# [Đợt hoàn thiện nghiệp vụ phiếu] Cập nhật thông tin xử lý theo từng bước
# ---------------------------------------------------------------------
# Quy ước 3 nguồn thông tin KHÔNG trộn lẫn (xem models.WarrantyTicket):
#   - Khách hàng mô tả       : issue_description (chỉ ghi lúc tiếp nhận)
#   - AI gợi ý               : ai_results (chỉ để tham khảo, KHÔNG tự ghi vào phiếu)
#   - Kỹ thuật viên kết luận : diagnosis_note / repair_content (người có quyền ghi)
# =====================================================================

class TicketDiagnosisUpdate(BaseModel):
    """Ghi nhận CHẨN ĐOÁN của kỹ thuật viên (người xác nhận = actor_id)."""

    actor_id: int = Field(..., gt=0, description="ID nhân viên ghi nhận chẩn đoán")
    diagnosis_note: str = Field(
        ..., min_length=3, description="Kết luận chẩn đoán của kỹ thuật viên (bắt buộc)"
    )
    error_category_id: Optional[int] = Field(
        None, gt=0, description="Loại lỗi do kỹ thuật viên xác nhận (không phải gợi ý của AI)"
    )
    is_warranty_eligible: Optional[bool] = Field(None, description="Xác nhận đủ điều kiện bảo hành")
    warranty_check_note: Optional[str] = Field(None, description="Ghi chú xác định điều kiện bảo hành")
    note: Optional[str] = Field(None, description="Ghi chú thêm (tùy chọn)")


class TicketRepairUpdate(BaseModel):
    """Ghi nhận NỘI DUNG SỬA CHỮA (đã kiểm tra / đã sửa / linh kiện thay thế)."""

    actor_id: int = Field(..., gt=0, description="ID nhân viên thực hiện sửa chữa")
    repair_content: Optional[str] = Field(None, description="Nội dung đã kiểm tra và đã sửa")
    repair_parts: Optional[str] = Field(None, description="Linh kiện / thành phần đã thay thế")
    repair_note: Optional[str] = Field(None, description="Ghi chú kỹ thuật")
    repair_test_passed: Optional[bool] = Field(None, description="Kết quả kiểm tra sau sửa đạt yêu cầu")
    repair_test_note: Optional[str] = Field(None, description="Ghi chú kiểm tra sau sửa")
    note: Optional[str] = Field(None, description="Ghi chú thêm (tùy chọn)")


# ----------------- Chi tiết phiếu: các khối thông tin A - G -----------------
class TicketCustomerInfo(BaseModel):
    """A. THÔNG TIN KHÁCH HÀNG"""

    id: int
    full_name: str
    phone: Optional[str] = None
    email: Optional[str] = None


class TicketDeviceInfo(BaseModel):
    """B. THÔNG TIN THIẾT BỊ"""

    id: int
    serial_number: str
    product_name: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    purchase_date: Optional[date] = None
    warranty_end_date: Optional[date] = None
    warranty_status: str = Field(..., description="Còn bảo hành / Đã hết hạn")
    warranty_status_message: str = Field(..., description="Câu mô tả tình trạng bảo hành bằng tiếng Việt")
    days_remaining: Optional[int] = None


class TicketIntakeInfo(BaseModel):
    """C. TIẾP NHẬN"""

    received_at: datetime
    received_by: Optional[int] = None
    received_by_name: Optional[str] = None
    issue_description: str = Field(..., description="Mô tả tình trạng/lỗi do KHÁCH HÀNG cung cấp")
    device_condition: Optional[str] = None
    accessories_accompanying: Optional[str] = None
    assigned_technician_id: Optional[int] = None
    assigned_technician_name: Optional[str] = None
    assigned_at: Optional[datetime] = None


class TicketDiagnosisInfo(BaseModel):
    """D. CHẨN ĐOÁN (kết luận của kỹ thuật viên - khác với gợi ý của AI)"""

    note: Optional[str] = None
    error_category_id: Optional[int] = None
    error_category_name: Optional[str] = None
    confirmed_by: Optional[int] = None
    confirmed_by_name: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    is_warranty_eligible: Optional[bool] = None
    warranty_check_note: Optional[str] = None
    rejection_proposal_note: Optional[str] = None
    rejection_proposed_by: Optional[int] = None
    rejection_proposed_by_name: Optional[str] = None
    rejection_proposed_at: Optional[datetime] = None


class TicketAiSuggestionInfo(BaseModel):
    available: bool = False
    ai_result_id: Optional[int] = None
    suggested_category_id: Optional[int] = None
    suggested_category_name: Optional[str] = None
    confidence: Optional[float] = None
    reason: Optional[str] = None
    review_status: Optional[str] = None
    provider: Optional[str] = None
    created_at: Optional[datetime] = None
    need_more_information: List[str] = Field(default_factory=list)
    message: str = Field(
        "AI chỉ gợi ý loại lỗi; nhân viên có quyền phải xác nhận trước khi ghi vào phiếu."
    )


class TicketRepairLogEntry(BaseModel):
    id: int
    technician_id: int
    technician_name: Optional[str] = None
    action_description: str
    parts_used: Optional[str] = None
    logged_at: datetime


class TicketRepairInfo(BaseModel):
    """E. SỬA CHỮA"""

    content: Optional[str] = None
    parts: Optional[str] = None
    note: Optional[str] = None
    technician_id: Optional[int] = None
    technician_name: Optional[str] = None
    recorded_at: Optional[datetime] = None
    repair_test_passed: Optional[bool] = None
    repair_test_note: Optional[str] = None
    logs: List[TicketRepairLogEntry] = Field(default_factory=list)


class TicketHandoverInfo(BaseModel):
    """F. TRẢ MÁY"""

    is_waiting_handover: bool = False
    is_waiting_return: bool = False  # Giữ để tương thích
    is_returned: bool = False
    status_message: str = ""
    completed_at: Optional[datetime] = None
    repair_completed_at: Optional[datetime] = None
    repair_completed_by_name: Optional[str] = None
    returned_at: Optional[datetime] = None
    returned_by_name: Optional[str] = None
    note: Optional[str] = None
    resolution: Optional[str] = None
    resolution_label: Optional[str] = None
    processing_time_hours: Optional[float] = None  # Thời gian xử lý kỹ thuật đến khi xong/từ chối
    waiting_time_hours: Optional[float] = None     # Thời gian chờ khách nhận máy
    processing_time_display: Optional[str] = None
    waiting_time_display: Optional[str] = None


class TicketHistoryEntry(BaseModel):
    """G. LỊCH SỬ - mỗi bước có trạng thái, thời gian, người thực hiện, ghi chú."""

    id: int
    from_status: Optional[str] = None
    to_status: str
    from_label: Optional[str] = None
    to_label: str
    changed_by: int
    changed_by_name: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime


class TicketCompletionCheck(BaseModel):
    key: str
    label: str
    satisfied: bool


class WarrantyTicketDetailResponse(WarrantyTicketResponse):
    """
    Chi tiết phiếu cho MÀN HÌNH XỬ LÝ: mọi việc của phiếu nằm trong một màn hình.
    Bao gồm đủ các khối A-G và danh sách hành động được phép (theo quyền).
    """

    status_label: str
    status_hint: str
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    customer: Optional[TicketCustomerInfo] = None
    device: Optional[TicketDeviceInfo] = None
    intake: Optional[TicketIntakeInfo] = None
    diagnosis: TicketDiagnosisInfo = Field(default_factory=TicketDiagnosisInfo)
    ai_suggestion: TicketAiSuggestionInfo = Field(default_factory=TicketAiSuggestionInfo)
    repair: TicketRepairInfo = Field(default_factory=TicketRepairInfo)
    handover: TicketHandoverInfo = Field(default_factory=TicketHandoverInfo)
    history: List[TicketHistoryEntry] = Field(default_factory=list)
    available_actions: List[TicketActionOption] = Field(default_factory=list)
    completion_checklist: List[TicketCompletionCheck] = Field(default_factory=list)
    can_complete: bool = False
    completion_blockers: List[str] = Field(default_factory=list)
    can_edit_diagnosis: bool = False
    can_edit_repair: bool = False
    permission_notes: List[str] = Field(
        default_factory=list,
        description="Giải thích các bước không hiển thị nút vì vai trò hiện tại thiếu quyền",
    )

    class Config:
        from_attributes = True


# =====================================================================
# [Đợt màn hình công việc theo vai trò] Bảng điều khiển trả lời câu hỏi
# "Hiện tại tôi cần làm gì?" — dữ liệu do backend tính theo VAI TRÒ
# ---------------------------------------------------------------------
# Giao diện chỉ vẽ lại những gì backend trả về: số liệu, nhóm việc,
# danh sách phiếu kèm hành động được phép, và các việc cần chú ý.
# =====================================================================
class WorkboardCard(BaseModel):
    """Một thẻ số liệu trên bảng điều khiển (có nhãn tiếng Việt + tông màu thống nhất)."""

    key: str = Field(..., description="Mã số liệu: total / received / inspecting / ... / customers / devices")
    label: str = Field(..., description="Nhãn hiển thị (tiếng Việt)")
    count: int = 0
    description: str = ""
    tone: str = Field("slate", description="Tông màu: blue / amber / purple / cyan / emerald / rose / slate")
    status: Optional[str] = Field(None, description="Trạng thái phiếu tương ứng (nếu là thẻ theo trạng thái)")


class WorkboardGroup(BaseModel):
    """Một nhóm công việc: có bao nhiêu việc và những phiếu nào cần xử lý ngay."""

    key: str
    label: str
    description: str = ""
    count: int = 0
    status_filter: Optional[str] = Field(
        None, description="Mã trạng thái để mở danh sách phiếu đã lọc sẵn theo nhóm này"
    )
    statuses: List[str] = Field(default_factory=list)
    scope: str = Field("ALL", pattern="^(ALL|MINE)$")
    scope_label: str = Field("Toàn trung tâm", description="Phạm vi số liệu: toàn trung tâm / việc của tôi")
    tone: str = "slate"
    action_target: Optional[str] = Field(None, description="Trạng thái đích của nút hành động chính trong nhóm")
    action_label: str = Field("", description="Câu chữ nút hành động theo vai trò (ví dụ: Bắt đầu kiểm tra)")
    items: List[WarrantyTicketResponse] = Field(default_factory=list)


class WorkboardAttentionItem(BaseModel):
    """Một phiếu cần quản lý chú ý, kèm LÝ DO lấy từ dữ liệu thật của phiếu."""

    ticket_id: int
    ticket_code: str
    status: str
    status_label: str
    reason: str
    days_since_update: Optional[int] = Field(
        None, description="Số ngày kể từ lần cập nhật trạng thái gần nhất (dữ liệu thật, không phán xét)"
    )
    serial_number: Optional[str] = None
    product_name: Optional[str] = None
    customer_name: Optional[str] = None
    handler_name: Optional[str] = None
    created_at: Optional[datetime] = None


class WorkboardQuickAction(BaseModel):
    """Thao tác nhanh trên bảng điều khiển (nhãn do backend đặt theo vai trò)."""

    key: str
    label: str
    description: str = ""
    icon: str = "arrow-right"
    primary: bool = False


class WorkboardResponse(BaseModel):
    """Toàn bộ dữ liệu bảng điều khiển theo vai trò trong MỘT lần gọi API."""

    role: str
    role_label: str
    title: str = Field(..., description="Tiêu đề bảng điều khiển (ví dụ: Công việc kỹ thuật)")
    subtitle: str = ""
    scope: str = Field("DEFAULT", description="DEFAULT (theo vai trò) / MINE / ALL")
    scope_label: str = "Theo vai trò"
    generated_at: datetime
    cards: List[WorkboardCard] = Field(default_factory=list)
    groups: List[WorkboardGroup] = Field(default_factory=list)
    focus: List[WarrantyTicketResponse] = Field(
        default_factory=list, description="Việc cần làm ngay, đã sắp theo thứ tự nghiệp vụ"
    )
    attention: List[WorkboardAttentionItem] = Field(default_factory=list)
    active_tickets: List[WarrantyTicketResponse] = Field(
        default_factory=list, description="Phiếu đang xử lý (chưa hoàn tất/từ chối)"
    )
    table_title: str = Field("Phiếu đang xử lý", description="Tiêu đề bảng phiếu trên bảng điều khiển")
    my_tickets: List[WarrantyTicketResponse] = Field(
        default_factory=list, description="Phiếu mà chính tài khoản này đang phụ trách"
    )
    quick_actions: List[WorkboardQuickAction] = Field(default_factory=list)
    totals: Dict[str, Any] = Field(default_factory=dict)
    notes: List[str] = Field(
        default_factory=list, description="Ghi chú nghiệp vụ theo vai trò (việc này của ai, vì sao)"
    )
