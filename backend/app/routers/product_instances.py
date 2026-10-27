"""
API Endpoint: /api/v1/product-instances
CRUD "Sản phẩm theo Serial" — bổ sung hoàn chỉnh yêu cầu KT2:
Danh sách / Xem chi tiết / Tìm kiếm theo Serial / Thêm / Sửa / Xóa (vô hiệu hoá an toàn).

Đợt 7 - Phân quyền:
    * Xem thiết bị              : `device.view` (mọi nhân viên đã đăng nhập).
    * Đăng ký / sửa / xóa thiết bị : `device.manage` (QUẢN LÝ, TIẾP NHẬN).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import SerialProductCreate, SerialProductUpdate, SerialProductResponse
from app.crud import product_instances as crud_instances
from app.services.auth_service import (
    PERM_DEVICE_MANAGE,
    PERM_DEVICE_VIEW,
    require_permissions,
)

router = APIRouter(prefix="/api/v1/product-instances", tags=["Products (Sản phẩm theo Serial - CRUD KT2)"])


@router.post(
    "/",
    response_model=SerialProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[KT2] Tạo sản phẩm theo Serial (Tên + Serial + Ngày mua + Hạn BH + Mô tả)",
    dependencies=[Depends(require_permissions(PERM_DEVICE_MANAGE))],
)
def create_serial_product(payload: SerialProductCreate, db: Session = Depends(get_db)):
    """Đăng ký một sản phẩm cụ thể theo serial. Hệ thống tự tính ngày hết hạn bảo hành nếu bỏ trống."""
    return crud_instances.create_product_instance(db, payload)


@router.get(
    "/",
    response_model=List[SerialProductResponse],
    summary="[KT2] Danh sách sản phẩm theo Serial (tìm kiếm Serial / Tên sản phẩm)",
    dependencies=[Depends(require_permissions(PERM_DEVICE_VIEW))],
)
def list_serial_products(
    search: Optional[str] = Query(None, description="Tìm kiếm theo Serial Number hoặc Tên sản phẩm"),
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    return crud_instances.list_product_instances(db, search=search, skip=skip, limit=limit)


@router.get(
    "/by-serial/{serial_number}",
    response_model=SerialProductResponse,
    summary="[KT2] Tra cứu sản phẩm chính xác theo Serial Number",
    dependencies=[Depends(require_permissions(PERM_DEVICE_VIEW))],
)
def read_serial_product_by_serial(serial_number: str, db: Session = Depends(get_db)):
    instance = crud_instances.get_by_serial(db, serial_number)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy sản phẩm có Serial: '{serial_number}'."
        )
    return instance


@router.get(
    "/{instance_id}",
    response_model=SerialProductResponse,
    summary="[KT2] Xem chi tiết sản phẩm theo Serial",
    dependencies=[Depends(require_permissions(PERM_DEVICE_VIEW))],
)
def read_serial_product(instance_id: int, db: Session = Depends(get_db)):
    instance = crud_instances.get_product_instance(db, instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy sản phẩm có ID: {instance_id}."
        )
    return instance


@router.put(
    "/{instance_id}",
    response_model=SerialProductResponse,
    summary="[KT2] Cập nhật sản phẩm theo Serial (Tên / Thời hạn BH / Mô tả)",
    dependencies=[Depends(require_permissions(PERM_DEVICE_MANAGE))],
)
def update_serial_product(instance_id: int, payload: SerialProductUpdate, db: Session = Depends(get_db)):
    instance = crud_instances.update_product_instance(db, instance_id, payload)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy sản phẩm có ID: {instance_id} để cập nhật."
        )
    return instance


@router.delete(
    "/{instance_id}",
    status_code=status.HTTP_200_OK,
    summary="[KT2] Xóa / vô hiệu hoá sản phẩm theo Serial",
    dependencies=[Depends(require_permissions(PERM_DEVICE_MANAGE))],
)
def delete_serial_product(instance_id: int, db: Session = Depends(get_db)):
    result = crud_instances.delete_product_instance(db, instance_id)
    if result == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy sản phẩm có ID: {instance_id} để xóa."
        )
    if result == "has_tickets":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Sản phẩm (ID: {instance_id}) đang được tham chiếu bởi phiếu bảo hành "
                "nên không thể xóa để bảo toàn tính toàn vẹn dữ liệu (FK RESTRICT). "
                "Hãy hoàn tất/từ chối các phiếu liên quan trước."
            )
        )
    return {"message": "Đã xóa sản phẩm theo serial thành công.", "product_instance_id": instance_id}
