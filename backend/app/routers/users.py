"""
=======================================================================
Đợt 7 - Router Quản trị tài khoản nhân viên (chỉ QUẢN LÝ được dùng)
=======================================================================
    * GET    /api/v1/users            - danh sách tài khoản
    * POST   /api/v1/users            - tạo tài khoản nhân viên
    * PATCH  /api/v1/users/{user_id}  - cập nhật (họ tên, vai trò, trạng thái, đổi mật khẩu)

Ràng buộc an toàn:
    * Mọi API ở đây yêu cầu quyền `user.view` / `user.manage` - chỉ vai trò QUẢN LÝ có.
    * Không trả về mật khẩu/hash trong bất kỳ phản hồi nào.
    * Quản lý KHÔNG thể tự vô hiệu hoá hay tự hạ vai trò của chính mình (tránh tự khoá hệ thống).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import schemas
from app.database import get_db
from app.models import ServiceCenter, User
from app.services.auth_service import (
    PERM_USER_MANAGE,
    PERM_USER_VIEW,
    hash_password,
    require_permissions,
    role_label_vn,
)

router = APIRouter(prefix="/api/v1/users", tags=["Users (Tài khoản nhân viên)"])


def _serialize(user: User) -> schemas.StaffUserResponse:
    """Chuyển bản ghi người dùng sang dữ liệu trả ra ngoài (đã bổ sung nhãn vai trò tiếng Việt)."""
    return schemas.StaffUserResponse(
        id=int(user.id),
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        role_label=role_label_vn(user.role),
        email=user.email,
        phone=user.phone,
        service_center_id=user.service_center_id,
        active=bool(user.active),
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _assert_service_center(db: Session, service_center_id: Optional[int]) -> None:
    if service_center_id is None:
        return
    if not db.query(ServiceCenter).filter(ServiceCenter.id == service_center_id).first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy trung tâm bảo hành được chọn.",
        )


@router.get(
    "",
    response_model=schemas.StaffUserListResponse,
    summary="Danh sách tài khoản nhân viên",
    dependencies=[Depends(require_permissions(PERM_USER_VIEW))],
    include_in_schema=False,
)
@router.get(
    "/",
    response_model=schemas.StaffUserListResponse,
    summary="Danh sách tài khoản nhân viên",
    dependencies=[Depends(require_permissions(PERM_USER_VIEW))],
)
def list_users(
    search: Optional[str] = Query(None, description="Tìm theo tên đăng nhập, họ tên, email, SĐT"),
    role: Optional[str] = Query(None, description="Lọc theo vai trò"),
    active: Optional[bool] = Query(None, description="Lọc theo trạng thái hoạt động"),
    db: Session = Depends(get_db),
):
    query = db.query(User)
    if search:
        s = f"%{search.strip().lower()}%"
        query = query.filter(
            func.lower(User.username).like(s)
            | func.lower(User.full_name).like(s)
            | func.lower(func.coalesce(User.email, "")).like(s)
            | func.lower(func.coalesce(User.phone, "")).like(s)
        )
    if role and role != "ALL":
        query = query.filter(User.role == role)
    if active is not None:
        query = query.filter(User.active == active)
    users = query.order_by(User.role.asc(), User.username.asc()).all()
    return schemas.StaffUserListResponse(total=len(users), items=[_serialize(u) for u in users])


@router.post(
    "",
    response_model=schemas.StaffUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo tài khoản nhân viên",
    dependencies=[Depends(require_permissions(PERM_USER_MANAGE))],
    include_in_schema=False,
)
@router.post(
    "/",
    response_model=schemas.StaffUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo tài khoản nhân viên",
    dependencies=[Depends(require_permissions(PERM_USER_MANAGE))],
)
def create_user(payload: schemas.StaffUserCreate, db: Session = Depends(get_db)):
    username = payload.username.strip()
    if db.query(User).filter(func.lower(User.username) == username.lower()).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tên đăng nhập \"{username}\" đã được sử dụng.",
        )
    if payload.email and db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email này đã được dùng cho một tài khoản khác.",
        )
    _assert_service_center(db, payload.service_center_id)

    user = User(
        username=username,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role=payload.role,
        email=payload.email,
        phone=payload.phone,
        service_center_id=payload.service_center_id,
        active=payload.active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _serialize(user)


@router.patch(
    "/{user_id}",
    response_model=schemas.StaffUserResponse,
    summary="Cập nhật tài khoản nhân viên",
    dependencies=[Depends(require_permissions(PERM_USER_MANAGE))],
)
def update_user(
    user_id: int,
    payload: schemas.StaffUserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(PERM_USER_MANAGE)),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tài khoản cần cập nhật."
        )

    is_self = int(user.id) == int(current_user.id)
    if is_self and payload.active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bạn không thể tự vô hiệu hoá tài khoản đang đăng nhập.",
        )
    if is_self and payload.role and payload.role != current_user.role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bạn không thể tự đổi vai trò của tài khoản đang đăng nhập.",
        )
    if payload.email and db.query(User).filter(User.email == payload.email, User.id != user.id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email này đã được dùng cho một tài khoản khác.",
        )
    if payload.service_center_id is not None:
        _assert_service_center(db, payload.service_center_id)

    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
    if payload.role is not None:
        user.role = payload.role
    if payload.email is not None:
        user.email = payload.email or None
    if payload.phone is not None:
        user.phone = payload.phone or None
    if payload.service_center_id is not None:
        user.service_center_id = payload.service_center_id
    if payload.active is not None:
        user.active = payload.active
    if payload.new_password:
        user.password_hash = hash_password(payload.new_password)

    db.commit()
    db.refresh(user)
    return _serialize(user)
