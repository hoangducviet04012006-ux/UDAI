from datetime import datetime, date
from sqlalchemy import (
    Column, BigInteger, Integer, String, Text, Boolean, Date, DateTime, Numeric,
    ForeignKey, CheckConstraint, UniqueConstraint
)
from sqlalchemy.types import JSON
from sqlalchemy.orm import relationship
from app.database import Base

# Kiểu dữ liệu ID đa hình: BigInteger trên PostgreSQL, Integer trên SQLite để kích hoạt AUTOINCREMENT
PK_ID = BigInteger().with_variant(Integer, "sqlite")

class ServiceCenter(Base):
    __tablename__ = "service_centers"

    id = Column(PK_ID, primary_key=True, index=True, autoincrement=True)
    name = Column(String(150), unique=True, nullable=False)
    address = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(100), unique=True, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    users = relationship("User", back_populates="service_center")
    warranty_tickets = relationship("WarrantyTicket", back_populates="service_center")


class ErrorCategory(Base):
    __tablename__ = "error_categories"

    id = Column(PK_ID, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    warranty_tickets = relationship("WarrantyTicket", back_populates="error_category")


class User(Base):
    __tablename__ = "users"

    id = Column(PK_ID, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False)  # MANAGER, RECEPTIONIST, TECHNICIAN
    service_center_id = Column(BigInteger, ForeignKey("service_centers.id", ondelete="SET NULL"), nullable=True)
    email = Column(String(100), unique=True, nullable=True)
    phone = Column(String(20), nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("role IN ('MANAGER', 'RECEPTIONIST', 'TECHNICIAN')", name="check_user_role"),
    )

    service_center = relationship("ServiceCenter", back_populates="users")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(PK_ID, primary_key=True, index=True, autoincrement=True)
    full_name = Column(String(100), nullable=False)
    phone = Column(String(20), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=True)
    address = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    product_instances = relationship("ProductInstance", back_populates="customer")
    warranty_tickets = relationship("WarrantyTicket", back_populates="customer")


class Product(Base):
    __tablename__ = "products"

    id = Column(PK_ID, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    brand = Column(String(50), nullable=True)
    category = Column(String(50), nullable=True)
    warranty_duration_months = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("warranty_duration_months > 0", name="check_warranty_duration_months"),
    )

    instances = relationship("ProductInstance", back_populates="product")


class ProductInstance(Base):
    __tablename__ = "product_instances"

    id = Column(PK_ID, primary_key=True, index=True, autoincrement=True)
    product_id = Column(BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    customer_id = Column(BigInteger, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False)
    serial_number = Column(String(100), unique=True, nullable=False, index=True)
    purchase_date = Column(Date, nullable=False)
    warranty_end_date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="ACTIVE")  # ACTIVE / EXPIRED
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'EXPIRED')", name="check_product_instance_status"),
    )

    product = relationship("Product", back_populates="instances")
    customer = relationship("Customer", back_populates="product_instances")
    warranty_tickets = relationship("WarrantyTicket", back_populates="product_instance")

    # ---- Convenience properties (phục vụ response CRUD & Debug KT2) ----
    @property
    def product_name(self):
        return self.product.name if self.product else None

    @property
    def product_brand(self):
        return self.product.brand if self.product else None

    @property
    def product_category(self):
        return self.product.category if self.product else None

    @property
    def description(self):
        return self.product.description if self.product else None

    @property
    def warranty_duration_months(self):
        return self.product.warranty_duration_months if self.product else None

    @property
    def customer_name(self):
        return self.customer.full_name if self.customer else None

    @property
    def customer_phone(self):
        return self.customer.phone if self.customer else None


class WarrantyTicket(Base):
    """Phiếu bảo hành.

    Vòng đời nghiệp vụ chuẩn:
    - Luồng sửa chữa:
      RECEIVED (Tiếp nhận) -> INSPECTING (Kiểm tra) -> REPAIRING (Sửa chữa)
      -> COMPLETED (Hoàn tất) -> RETURNED (Đã trả máy).
    - Luồng từ chối:
      INSPECTING (Kiểm tra) -> REJECTED (Từ chối) -> RETURNED (Đã trả máy).

    Ý nghĩa:
    - RECEIVED (Tiếp nhận): đã nhận máy và lập phiếu.
    - INSPECTING (Kiểm tra): kỹ thuật viên đang kiểm tra, xác định lỗi và điều kiện bảo hành.
    - REPAIRING (Sửa chữa): đang thực hiện sửa chữa.
    - COMPLETED (Hoàn tất): sửa xong, đã kiểm tra kết quả, đang chờ khách nhận.
    - REJECTED (Từ chối): quản lý xác nhận không tiếp nhận sửa theo bảo hành, có lý do, đang chờ trả máy.
    - RETURNED (Đã trả máy): đã bàn giao cho khách, đóng phiếu.
    """

    __tablename__ = "warranty_tickets"

    id = Column(PK_ID, primary_key=True, index=True, autoincrement=True)
    ticket_code = Column(String(30), unique=True, nullable=False, index=True)
    product_instance_id = Column(BigInteger, ForeignKey("product_instances.id", ondelete="RESTRICT"), nullable=False)
    customer_id = Column(BigInteger, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False)
    service_center_id = Column(BigInteger, ForeignKey("service_centers.id", ondelete="RESTRICT"), nullable=False)
    created_by = Column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    issue_description = Column(Text, nullable=False)
    device_condition = Column(Text, nullable=True)           # Ngoại quan / tình trạng máy khi nhận
    accessories_accompanying = Column(Text, nullable=True)   # Phụ kiện nhận kèm
    error_category_id = Column(BigInteger, ForeignKey("error_categories.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(20), nullable=False, default="RECEIVED")  # RECEIVED, INSPECTING, REPAIRING, COMPLETED, REJECTED, RETURNED
    
    # Phân công kỹ thuật viên phụ trách phiếu
    assigned_technician_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_at = Column(DateTime, nullable=True)

    # Chẩn đoán & xác định điều kiện bảo hành
    diagnosis_note = Column(Text, nullable=True)             # Kết luận chẩn đoán của kỹ thuật viên
    diagnosis_by = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    diagnosis_at = Column(DateTime, nullable=True)
    is_warranty_eligible = Column(Boolean, nullable=True)    # Kết quả xác định đủ điều kiện bảo hành
    warranty_check_note = Column(Text, nullable=True)        # Ghi chú xác định điều kiện bảo hành

    # Nghiệp vụ sửa chữa & kiểm tra sau sửa
    repair_content = Column(Text, nullable=True)             # Nội dung đã kiểm tra / đã sửa
    repair_parts = Column(Text, nullable=True)               # Linh kiện / thành phần đã thay
    repair_note = Column(Text, nullable=True)                # Ghi chú kỹ thuật khi sửa chữa
    repair_by = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    repair_at = Column(DateTime, nullable=True)              # Thời điểm hoàn thành sửa chữa
    repair_test_passed = Column(Boolean, nullable=True)      # Kết quả kiểm tra sau sửa đạt yêu cầu
    repair_test_note = Column(Text, nullable=True)           # Ghi chú kiểm tra sau sửa

    # Nhánh từ chối bảo hành
    rejection_reason = Column(Text, nullable=True)
    rejection_proposed_by = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejection_proposed_at = Column(DateTime, nullable=True)
    rejection_proposal_note = Column(Text, nullable=True)    # Đề xuất & bằng chứng kiểm tra của KTV
    rejection_reviewed_by = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejection_reviewed_at = Column(DateTime, nullable=True)
    rejection_review_status = Column(String(20), nullable=True)  # PENDING, APPROVED, DECLINED

    # Bàn giao trả máy & Đóng phiếu
    completed_at = Column(DateTime, nullable=True)           # Mốc hoàn tất sửa chữa (chờ trả máy)
    handed_over_by = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    handed_over_at = Column(DateTime, nullable=True)         # Thời điểm bàn giao trả máy cho khách
    handover_note = Column(Text, nullable=True)              # Ghi chú khi bàn giao máy cho khách
    resolution = Column(String(20), nullable=True)           # Kết quả lưu vết khi đóng: 'COMPLETED' (Sửa hoàn tất) hoặc 'REJECTED' (Từ chối)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("status IN ('RECEIVED', 'INSPECTING', 'REPAIRING', 'COMPLETED', 'REJECTED', 'RETURNED')", name="check_ticket_status"),
        CheckConstraint("rejection_review_status IS NULL OR rejection_review_status IN ('PENDING', 'APPROVED', 'DECLINED')", name="check_rejection_review_status"),
        CheckConstraint("resolution IS NULL OR resolution IN ('COMPLETED', 'REJECTED')", name="check_ticket_resolution"),
    )

    product_instance = relationship("ProductInstance", back_populates="warranty_tickets")
    customer = relationship("Customer", back_populates="warranty_tickets")
    service_center = relationship("ServiceCenter", back_populates="warranty_tickets")
    error_category = relationship("ErrorCategory", back_populates="warranty_tickets")
    creator = relationship("User", foreign_keys=[created_by])
    assigned_technician = relationship("User", foreign_keys=[assigned_technician_id])
    rejection_proposer = relationship("User", foreign_keys=[rejection_proposed_by])
    rejection_reviewer = relationship("User", foreign_keys=[rejection_reviewed_by])
    diagnosis_user = relationship("User", foreign_keys=[diagnosis_by])
    repair_user = relationship("User", foreign_keys=[repair_by])
    handover_user = relationship("User", foreign_keys=[handed_over_by])

    assignments = relationship("TechnicianAssignment", back_populates="ticket", cascade="all, delete-orphan")
    status_history = relationship("TicketStatusHistory", back_populates="ticket", cascade="all, delete-orphan", order_by="TicketStatusHistory.created_at")
    repair_logs = relationship("RepairLog", back_populates="ticket", cascade="all, delete-orphan")
    ai_results = relationship("AIResult", back_populates="ticket", cascade="all, delete-orphan")

    # ---- Convenience properties (hiển thị thông tin sản phẩm trong chi tiết phiếu KT2) ----
    @property
    def serial_number(self):
        return self.product_instance.serial_number if self.product_instance else None

    @property
    def product_name(self):
        if self.product_instance and self.product_instance.product:
            return self.product_instance.product.name
        return None

    @property
    def customer_name(self):
        return self.customer.full_name if self.customer else None

    @property
    def warranty_end_date(self):
        return self.product_instance.warranty_end_date if self.product_instance else None


class TechnicianAssignment(Base):
    __tablename__ = "technician_assignments"

    id = Column(PK_ID, primary_key=True, index=True, autoincrement=True)
    ticket_id = Column(BigInteger, ForeignKey("warranty_tickets.id", ondelete="CASCADE"), nullable=False)
    technician_id = Column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    assigned_by = Column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    ticket = relationship("WarrantyTicket", back_populates="assignments")
    technician = relationship("User", foreign_keys=[technician_id])
    assigner = relationship("User", foreign_keys=[assigned_by])


class TicketStatusHistory(Base):
    __tablename__ = "ticket_status_history"

    id = Column(PK_ID, primary_key=True, index=True, autoincrement=True)
    ticket_id = Column(BigInteger, ForeignKey("warranty_tickets.id", ondelete="CASCADE"), nullable=False)
    from_status = Column(String(20), nullable=True)
    to_status = Column(String(20), nullable=False)
    changed_by = Column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    ticket = relationship("WarrantyTicket", back_populates="status_history")
    user = relationship("User", foreign_keys=[changed_by])


class RepairLog(Base):
    __tablename__ = "repair_logs"

    id = Column(PK_ID, primary_key=True, index=True, autoincrement=True)
    ticket_id = Column(BigInteger, ForeignKey("warranty_tickets.id", ondelete="CASCADE"), nullable=False)
    technician_id = Column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    action_description = Column(Text, nullable=False)
    parts_used = Column(Text, nullable=True)
    labor_hours = Column(Numeric(5, 2), nullable=True)
    logged_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    ticket = relationship("WarrantyTicket", back_populates="repair_logs")
    technician = relationship("User", foreign_keys=[technician_id])


class AIResult(Base):
    __tablename__ = "ai_results"

    id = Column(PK_ID, primary_key=True, index=True, autoincrement=True)
    ticket_id = Column(BigInteger, ForeignKey("warranty_tickets.id", ondelete="CASCADE"), nullable=False)
    ai_function = Column(String(50), nullable=False)
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    confidence_score = Column(Numeric(5, 4), nullable=True)
    reviewed_by = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_status = Column(String(20), default="PENDING")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    ticket = relationship("WarrantyTicket", back_populates="ai_results")
    reviewer = relationship("User", foreign_keys=[reviewed_by])


# =====================================================================
# KT4 (P1) - SCHEMA CHATBOT: chuẩn bị nền tảng cho RAG + LangGraph Agent
# ---------------------------------------------------------------------
# 5 bảng MỚI, KHÔNG sửa/xoá bất kỳ cột nào của 11 bảng KT1 => giữ nguyên ERD:
#   12. kb_documents  - tài liệu tri thức (knowledge base) phục vụ RAG
#   13. kb_chunks     - các đoạn tài liệu đã chia nhỏ (+ vector fallback in-memory)
#   14. chat_sessions - phiên hội thoại của khách hàng/nhân viên
#   15. chat_messages - từng lượt tin nhắn (đã khử PII) + trích dẫn + guardrail
#   16. chat_handoffs - bàn giao nhân viên (human-in-the-loop)
#
# Lưu ý thiết kế:
#   * KHÔNG khai báo relationship() sang User/Customer/WarrantyTicket để không phải
#     sửa các class cũ (yêu cầu: không đụng nghiệp vụ KT1-KT3). Khoá ngoại vẫn được
#     khai báo đầy đủ nên ràng buộc toàn vẹn dữ liệu không thay đổi.
#   * chat_messages.content CHỈ lưu bản đã khử PII (sanitize_pii của KT3).
#   * Các cột JSON dùng để lưu vết: citations, tool_args, guardrail_flags, token_usage.
# =====================================================================


class TicketLookupCredential(Base):
    """One revocable customer capability per ticket; plaintext is never persisted."""
    __tablename__ = "ticket_lookup_credentials"
    ticket_id = Column(PK_ID, ForeignKey("warranty_tickets.id", ondelete="CASCADE"), primary_key=True)
    token_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False)


class KBDocument(Base):
    """Tài liệu tri thức của chatbot (tương ứng một file markdown trong database/knowledge)."""

    __tablename__ = "kb_documents"

    id = Column(PK_ID, primary_key=True, index=True, autoincrement=True)
    doc_code = Column(String(50), unique=True, nullable=False, index=True)  # BH-POLICY-01...
    title = Column(String(200), nullable=False)
    doc_type = Column(String(30), nullable=False)  # POLICY | FAQ | MANUAL | BR_RULE | PROCESS
    source_ref = Column(String(255), nullable=True)
    language = Column(String(10), default="vi")
    content = Column(Text, nullable=False)
    checksum = Column(String(64), nullable=False)  # sha256(content) -> chống nhúng lại chunk cũ
    version = Column(String(20), default="1.0")
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "doc_type IN ('POLICY', 'FAQ', 'MANUAL', 'BR_RULE', 'PROCESS')",
            name="check_kb_doc_type",
        ),
    )

    chunks = relationship("KBChunk", back_populates="document", cascade="all, delete-orphan")


class KBChunk(Base):
    """Đoạn tài liệu đã chia nhỏ - đơn vị truy hồi (retrieval unit) của RAG."""

    __tablename__ = "kb_chunks"

    id = Column(PK_ID, primary_key=True, index=True, autoincrement=True)
    document_id = Column(BigInteger, ForeignKey("kb_documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=True)
    embedding = Column(JSON, nullable=True)  # fallback khi vector store chạy in-memory
    chunk_metadata = Column(JSON, nullable=True)  # heading/section/source_ref để hiển thị trích dẫn
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_kb_chunk"),
    )

    document = relationship("KBDocument", back_populates="chunks")


class ChatSession(Base):
    """Phiên hội thoại với chatbot (có thể gắn với một khách hàng và/hoặc một phiếu bảo hành)."""

    __tablename__ = "chat_sessions"

    id = Column(PK_ID, primary_key=True, index=True, autoincrement=True)
    session_code = Column(String(30), unique=True, nullable=False, index=True)  # CS-YYYYMMDD-XXXX
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    customer_id = Column(BigInteger, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    ticket_id = Column(BigInteger, ForeignKey("warranty_tickets.id", ondelete="SET NULL"), nullable=True)
    channel = Column(String(20), nullable=False, default="WEB")
    status = Column(String(20), nullable=False, default="ACTIVE")  # ACTIVE | CLOSED | ESCALATED
    title = Column(String(200), nullable=True)
    locale = Column(String(10), default="vi")
    turn_count = Column(Integer, nullable=False, default=0)
    last_intent = Column(String(50), nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_message_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'CLOSED', 'ESCALATED')", name="check_chat_session_status"),
    )

    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.turn_index",
    )
    handoffs = relationship("ChatHandoff", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    """
    Một lượt tin nhắn trong phiên hội thoại.

    role = USER (khách) | ASSISTANT (chatbot) | SYSTEM (thông báo hệ thống) | TOOL (kết quả gọi công cụ).
    content CHỈ lưu bản đã khử PII; guardrail_flags lưu vết khử PII / chặn prompt injection.
    """

    __tablename__ = "chat_messages"

    id = Column(PK_ID, primary_key=True, index=True, autoincrement=True)
    session_id = Column(BigInteger, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    turn_index = Column(Integer, nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    intent = Column(String(50), nullable=True)
    tool_name = Column(String(50), nullable=True)
    tool_args = Column(JSON, nullable=True)
    retrieved_chunk_ids = Column(JSON, nullable=True)
    citations = Column(JSON, nullable=True)  # [{chunk_id, doc_code, title, snippet}]
    confidence = Column(Numeric(5, 4), nullable=True)
    guardrail_flags = Column(JSON, nullable=True)
    pii_redacted = Column(Boolean, nullable=False, default=False)
    provider = Column(String(50), nullable=True)
    prompt_version = Column(String(20), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    token_usage = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("role IN ('USER', 'ASSISTANT', 'SYSTEM', 'TOOL')", name="check_chat_message_role"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="check_chat_confidence",
        ),
        UniqueConstraint("session_id", "turn_index", name="uq_chat_turn"),
    )

    session = relationship("ChatSession", back_populates="messages")


class ChatHandoff(Base):
    """
    Yêu cầu bàn giao cho nhân viên (human-in-the-loop).

    Chatbot KHÔNG tự quyết định bảo hành: khi cần con người xử lý, hệ thống tạo bản ghi ở
    trạng thái OPEN và chỉ ĐỀ XUẤT nhãn lỗi (ai_suggested_category_id). Nhãn chỉ được ghi
    vào warranty_tickets.error_category_id khi MANAGER/RECEPTIONIST duyệt APPROVED (KT3).
    """

    __tablename__ = "chat_handoffs"

    id = Column(PK_ID, primary_key=True, index=True, autoincrement=True)
    session_id = Column(BigInteger, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    message_id = Column(BigInteger, ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True)
    ticket_id = Column(BigInteger, ForeignKey("warranty_tickets.id", ondelete="SET NULL"), nullable=True)
    reason = Column(String(200), nullable=False)
    priority = Column(String(10), nullable=False, default="NORMAL")  # LOW | NORMAL | HIGH
    ai_suggested_category_id = Column(
        BigInteger, ForeignKey("error_categories.id", ondelete="SET NULL"), nullable=True
    )
    ai_confidence = Column(Numeric(5, 4), nullable=True)
    status = Column(String(20), nullable=False, default="OPEN")  # OPEN | ASSIGNED | RESOLVED | CANCELLED
    assigned_to = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_by = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolution_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('OPEN', 'ASSIGNED', 'RESOLVED', 'CANCELLED')",
            name="check_chat_handoff_status",
        ),
        CheckConstraint("priority IN ('LOW', 'NORMAL', 'HIGH')", name="check_chat_handoff_priority"),
    )

    session = relationship("ChatSession", back_populates="handoffs")
