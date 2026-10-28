"""
=======================================================================
API Endpoint KT3: /api/v1/ai
=======================================================================
AI-01 - Gợi ý phân loại lỗi bảo hành + Human-in-the-loop review.

Nguyên tắc:
    * AI chỉ ĐỀ XUẤT nhãn lỗi cho một phiếu bảo hành ĐÃ TỒN TẠI.
    * AI KHÔNG tự ghi error_category_id, KHÔNG đổi trạng thái phiếu,
      KHÔNG quyết định chấp nhận/từ chối bảo hành.
    * Chỉ khi MANAGER hoặc TECHNICIAN được giao phiếu duyệt APPROVED thì nhãn mới được ghi vào phiếu.

Đợt 7 - Phân quyền:
    * `ai.view`     : xem kết quả AI / cấu hình (mọi nhân viên đã đăng nhập).
    * `ai.classify` : gọi AI gợi ý nhãn lỗi (cả 3 vai trò).
    * `ai.review`   : xét duyệt APPROVED/REJECTED (QUẢN LÝ, KTV ĐƯỢC GIAO PHIẾU) - Tiếp nhận 403.
    * Người xét duyệt (`reviewed_by`) không được khai khống: nhân viên chỉ ghi danh
      chính mình, quản lý được xét duyệt thay cho bất kỳ nhân viên nào.
"""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import (
    AIClassificationResponse,
    AIHistorySummaryResponse,
    AIProgressNotificationResponse,
    AIResultResponse,
    AIReviewRequest,
    AIReviewResponse,
    AISuggestCategoryRequest,
)
from app.services import ai_error_classifier as ai_service
from app.services.auth_service import (
    PERM_AI_CLASSIFY,
    PERM_AI_REVIEW,
    PERM_AI_VIEW,
    PERM_STAFF_VIEW,
    ensure_actor_allowed,
    require_permissions,
)

router = APIRouter(prefix="/api/v1/ai", tags=["Chức năng AI Bảo hành (BaoHanhAI)"])


@router.post(
    "/tickets/{ticket_id}/classify-error",
    response_model=AIClassificationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[KT3] AI gợi ý phân loại lỗi cho phiếu bảo hành (lưu vào ai_results, review_status=PENDING)",
    dependencies=[Depends(require_permissions(PERM_AI_CLASSIFY))],
)
def classify_error_for_ticket(ticket_id: int, db: Session = Depends(get_db)):
    """
    Gọi AI-01 để gợi ý nhãn lỗi cho phiếu bảo hành:

    - Lấy `product_name` (ProductInstance -> Product), `issue_description` (WarrantyTicket)
      và danh sách nhãn active từ `error_categories`.
    - Loại bỏ PII (tên/điện thoại/email/địa chỉ khách hàng) trước khi lưu `input_data`.
    - Loại bỏ mọi chỉ dẫn can thiệp trong mô tả lỗi (prompt injection guardrail).
    - Kiểm tra hợp lệ đầu ra: nhãn phải tồn tại trong `error_categories`, confidence thuộc [0, 1],
      nhãn null => confidence <= 0.40, nhãn ngoài danh sách => null/null/0.0.
    - Lưu kết quả vào `ai_results` với `ai_function="ERROR_CLASSIFICATION"`,
      `review_status="PENDING"`.

    **KHÔNG** ghi `error_category_id` vào phiếu và **KHÔNG** đổi trạng thái phiếu.
    Trả 404 nếu phiếu không tồn tại; trả 422 nếu phiếu chưa có mô tả lỗi.
    """
    ai_result = ai_service.classify_ticket_error(db, ticket_id)
    return ai_service.classification_response_payload(ai_result)


@router.get(
    "/results/{result_id}",
    response_model=AIResultResponse,
    summary="[KT3] Xem chi tiết một kết quả AI trong bảng ai_results",
    dependencies=[Depends(require_permissions(PERM_AI_VIEW))],
)
def read_ai_result(result_id: int, db: Session = Depends(get_db)):
    """Trả về bản ghi `ai_results` đầy đủ (input_data đã loại PII, output_data đã kiểm tra hợp lệ)."""
    return ai_service.get_ai_result_or_404(db, result_id)


@router.patch(
    "/results/{result_id}/review",
    response_model=AIReviewResponse,
    summary="[KT3] KTV phụ trách hoặc QUẢN LÝ xét duyệt kết quả AI (APPROVED/REJECTED)",
)
def review_ai_result(
    result_id: int,
    review_in: AIReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(PERM_AI_REVIEW)),
):
    """
    Xét duyệt kết quả AI (human-in-the-loop):

    - Người xét duyệt phải tồn tại (404 nếu không có).
    - Chỉ `MANAGER` hoặc `TECHNICIAN` được giao phiếu được xét duyệt. Tiếp nhận và KTV khác -> 403.
    - `APPROVED`: cập nhật `review_status` và ghi nhãn lỗi đã duyệt vào `warranty_tickets.error_category_id`.
    - `REJECTED`: chỉ cập nhật `review_status`, không thay đổi `error_category_id`.
    - Phiếu đã ở COMPLETED, REJECTED, RETURNED -> 400 không cho xét duyệt.
    - Trạng thái phiếu bảo hành không bị thay đổi bởi thao tác này.
    """
    ensure_actor_allowed(db, current_user, review_in.reviewed_by, "người xét duyệt kết quả AI")
    return ai_service.review_ai_result(db, result_id, review_in)


@router.get(
    "/tickets/{ticket_id}/results",
    response_model=List[AIResultResponse],
    summary="[KT3] Danh sách kết quả AI của một phiếu (phục vụ giao diện demo)",
    dependencies=[Depends(require_permissions(PERM_AI_VIEW))],
)
def list_results_of_ticket(ticket_id: int, db: Session = Depends(get_db)):
    return ai_service.list_ai_results_for_ticket(db, ticket_id)


@router.get(
    "/config",
    summary="[KT3] Thông tin AI provider đang hoạt động (không tiết lộ API key)",
    dependencies=[Depends(require_permissions(PERM_AI_VIEW))],
)
def get_ai_config() -> Dict[str, Any]:
    return ai_service.describe_ai_provider_config()


@router.get(
    "/demo/users",
    summary="[KT3] Danh sách người dùng phục vụ chọn người xét duyệt trên giao diện demo",
    dependencies=[Depends(require_permissions(PERM_STAFF_VIEW))],
)
def list_demo_reviewers(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id.asc()).all()
    return [
        {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role,
            "can_review": user.role in ai_service.ALLOWED_REVIEW_ROLES and bool(user.active),
        }
        for user in users
    ]


# ---------------------------------------------------------------------
# CHỨC NĂNG AI 1 (BỔ SUNG): Gợi ý nhóm lỗi trực tiếp từ mô tả
# ---------------------------------------------------------------------
@router.post(
    "/suggest-category",
    summary="Chức năng AI 1: Gợi ý nhóm lỗi trực tiếp từ mô tả (khi tiếp nhận hoặc kiểm tra)",
    dependencies=[Depends(require_permissions(PERM_AI_CLASSIFY))],
)
def suggest_category_live(
    payload: AISuggestCategoryRequest,
    db: Session = Depends(get_db),
):
    """Gợi ý nhóm lỗi tức thời cho mô tả lỗi, khử PII và bảo đảm tính an toàn dữ liệu."""
    return ai_service.classify_raw_description(
        db, payload.product_name, payload.issue_description
    )


# ---------------------------------------------------------------------
# CHỨC NĂNG AI 2: Tóm tắt lịch sử bảo hành thiết bị / phiếu
# ---------------------------------------------------------------------
@router.post(
    "/devices/{device_id}/summarize-history",
    response_model=AIHistorySummaryResponse,
    summary="Chức năng AI 2: Tóm tắt lịch sử bảo hành theo thiết bị",
    dependencies=[Depends(require_permissions(PERM_AI_VIEW))],
)
def summarize_device_history(
    device_id: int,
    db: Session = Depends(get_db),
):
    """Tổng hợp tóm tắt lịch sử sửa chữa, các lỗi từng gặp và linh kiện đã thay cho thiết bị."""
    return ai_service.summarize_warranty_history(db, device_id=device_id)


@router.post(
    "/tickets/{ticket_id}/summarize-history",
    response_model=AIHistorySummaryResponse,
    summary="Chức năng AI 2: Tóm tắt lịch sử bảo hành theo phiếu",
    dependencies=[Depends(require_permissions(PERM_AI_VIEW))],
)
def summarize_ticket_history(
    ticket_id: int,
    db: Session = Depends(get_db),
):
    """Tổng hợp tóm tắt lịch sử bảo hành của thiết bị trong phiếu đang mở."""
    return ai_service.summarize_warranty_history(db, ticket_id=ticket_id)


# ---------------------------------------------------------------------
# CHỨC NĂNG AI 3: Soạn tin cập nhật tiến độ
# ---------------------------------------------------------------------
@router.post(
    "/tickets/{ticket_id}/draft-progress-notification",
    response_model=AIProgressNotificationResponse,
    summary="Chức năng AI 3: Soạn tin nhắn cập nhật tiến độ cho nhân viên xem, sửa và sao chép",
    dependencies=[Depends(require_permissions(PERM_AI_VIEW))],
)
def draft_ticket_notification(
    ticket_id: int,
    db: Session = Depends(get_db),
):
    """
    Soạn nội dung thông báo tiến độ xử lý bảo hành cho khách hàng.
    Không cam kết chi phí hoặc thời hạn kết thúc trong tương lai.
    Không tự động gửi ra ngoài; nhân viên xem, chỉnh sửa và sao chép để gửi.
    """
    return ai_service.draft_progress_notification(db, ticket_id=ticket_id)

