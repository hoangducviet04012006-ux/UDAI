"""
=======================================================================
Đợt 7 - Router Xác thực (Authentication)
=======================================================================
Cung cấp 3 API cho vòng đời phiên làm việc:
    * POST /api/v1/auth/login  - đăng nhập, nhận token
    * GET  /api/v1/auth/me     - thông tin phiên hiện tại (vai trò + quyền)
    * POST /api/v1/auth/logout - đăng xuất, thu hồi token

Nguyên tắc bảo mật:
    * Sai tài khoản hay sai mật khẩu đều trả CÙNG một thông báo 401 (không cho dò tài khoản).
    * Không log và không trả lại mật khẩu/hash dưới bất kỳ hình thức nào.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import schemas
from app.database import get_db
from app.models import User
from app.services import auth_service
from app.services.auth_service import (
    get_current_user,
    get_raw_token,
    navigation_for_role,
    permissions_for_role,
    role_label_vn,
)

logger = logging.getLogger("baohanhai.auth")

router = APIRouter(prefix="/api/v1/auth", tags=["Auth (Đăng nhập & Phân quyền)"])


def build_session_info(user: User) -> schemas.UserSessionInfo:
    """
    Gói thông tin phiên làm việc (vai trò + danh sách quyền + menu) để giao diện sử dụng.

    `menus` do backend tính theo vai trò: giao diện chỉ vẽ lại đúng các mục menu
    mà vai trò này thực sự cần cho ca làm việc (nhóm "work" / "reference" / "admin").
    """
    return schemas.UserSessionInfo(
        id=int(user.id),
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        role_label=role_label_vn(user.role),
        service_center_id=user.service_center_id,
        permissions=permissions_for_role(user.role),
        menus=[schemas.SessionMenuEntry(**item) for item in navigation_for_role(user.role)],
    )


@router.post(
    "/login",
    response_model=schemas.LoginResponse,
    summary="Đăng nhập",
    description=(
        "Xác thực tên đăng nhập + mật khẩu và trả về token phiên làm việc.\n\n"
        "Giao diện gửi token kèm header `Authorization: Bearer <access_token>` cho mọi API nghiệp vụ."
    ),
)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user, reason = auth_service.authenticate(db, payload.username, payload.password)
    if not user:
        # Ghi log nội bộ (KHÔNG ghi mật khẩu) để phục vụ truy vết, nhưng trả lỗi trung tính.
        logger.warning("Đăng nhập thất bại (lý do: %s).", reason)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tên đăng nhập hoặc mật khẩu không đúng.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_info = auth_service.create_access_token(user)
    logger.info("Đăng nhập thành công (vai trò: %s).", role_label_vn(user.role))
    return schemas.LoginResponse(
        access_token=token_info["access_token"],
        token_type=token_info["token_type"],
        expires_in=token_info["expires_in"],
        expires_at=token_info["expires_at"],
        user=build_session_info(user),
        message=f"Xin chào {user.full_name} - {role_label_vn(user.role)}.",
    )


@router.get(
    "/me",
    response_model=schemas.UserSessionInfo,
    summary="Thông tin phiên đăng nhập hiện tại",
    description=(
        "Trả về tài khoản, vai trò và danh sách quyền đang có hiệu lực.\n\n"
        "Giao diện dùng thông tin này để hiển thị tên người dùng và ẩn/hiện menu theo vai trò.\n"
        "Vai trò luôn đọc từ CSDL nên đổi vai trò/vô hiệu hoá tài khoản có hiệu lực ngay."
    ),
)
def read_current_session(current_user: User = Depends(get_current_user)):
    return build_session_info(current_user)


@router.post(
    "/logout",
    response_model=schemas.LogoutResponse,
    summary="Đăng xuất",
    description="Thu hồi token hiện tại; token này không thể dùng lại cho các API nghiệp vụ.",
)
def logout(
    token: str = Depends(get_raw_token),
    current_user: User = Depends(get_current_user),
):
    auth_service.revoke_token(token)
    logger.info("Người dùng đã đăng xuất (vai trò: %s).", role_label_vn(current_user.role))
    return schemas.LogoutResponse(
        success=True, message="Đã đăng xuất. Vui lòng đăng nhập lại để tiếp tục làm việc."
    )
