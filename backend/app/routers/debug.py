"""
API Endpoint: /api/v1/debug (Công cụ debug nghiệp vụ KT2)

Đợt 7 - Phân quyền: công cụ debug dùng chung dữ liệu nghiệp vụ bảo hành nên
yêu cầu đăng nhập và quyền `ticket.view` (mọi nhân viên đã đăng nhập).
"""
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import DebugWarrantyCheckRequest, DebugWarrantyCheckResponse
from app.services.warranty_rules import detailed_debug_warranty
from app.services.auth_service import PERM_TICKET_VIEW, require_permissions

router = APIRouter(prefix="/api/v1/debug", tags=["Debug KT2 (Kiểm tra Hạn Bảo hành)"])

@router.post(
    "/check-warranty",
    response_model=DebugWarrantyCheckResponse,
    summary="[KT2 DEBUG] Kiểm tra và Debug điều kiện Hạn Bảo hành (BR2)",
    dependencies=[Depends(require_permissions(PERM_TICKET_VIEW))],
)
def debug_warranty_endpoint(
    request: DebugWarrantyCheckRequest,
    db: Session = Depends(get_db)
):
    """
    Chức năng debug kiểm tra hạn bảo hành (Nội dung KT2 nhắc riêng):
    - Kiểm tra và trace chi tiết từng bước xác định ngày mua, hạn bảo hành.
    - So sánh ngày kết thúc đóng băng vs ngày tính toán thực tế.
    - Tính toán số ngày còn lại (hoặc quá hạn) theo ngày đối chiếu.
    - Ghi nhận trace log chi tiết để phục vụ báo cáo và phân tích lỗi.
    """
    result = detailed_debug_warranty(
        db=db,
        serial_number=request.serial_number,
        purchase_date=request.purchase_date,
        warranty_duration_months=request.warranty_duration_months,
        check_date=request.check_date
    )
    return result

@router.get(
    "/check-serial/{serial_number}",
    response_model=DebugWarrantyCheckResponse,
    summary="[KT2 DEBUG] Tra cứu và kiểm tra hạn nhanh theo Serial",
    dependencies=[Depends(require_permissions(PERM_TICKET_VIEW))],
)
def debug_by_serial(
    serial_number: str,
    check_date: Optional[date] = Query(None, description="Ngày đối chiếu kiểm tra (mặc định hôm nay)"),
    db: Session = Depends(get_db)
):
    return detailed_debug_warranty(
        db=db,
        serial_number=serial_number,
        check_date=check_date
    )
