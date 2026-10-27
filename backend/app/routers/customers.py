"""
API Endpoint: /api/v1/customers (Khách hàng)

Đợt 7 - Phân quyền:
    * Xem khách hàng  : `customer.view` (mọi nhân viên đã đăng nhập).
    * Thêm khách hàng : `customer.create` (QUẢN LÝ, TIẾP NHẬN).
    * Sửa khách hàng  : `customer.update` (QUẢN LÝ, TIẾP NHẬN).
    * Xóa khách hàng  : `customer.delete` (chỉ QUẢN LÝ).
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ProductInstance, WarrantyTicket
from app.schemas import CustomerCreate, CustomerUpdate, CustomerResponse
from app.crud import customers as crud_customers
from app.services.auth_service import (
    PERM_CUSTOMER_CREATE,
    PERM_CUSTOMER_DELETE,
    PERM_CUSTOMER_UPDATE,
    PERM_CUSTOMER_VIEW,
    require_permissions,
)

router = APIRouter(prefix="/api/v1/customers", tags=["Customers (Khách hàng)"])

@router.post(
    "/",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Thêm khách hàng mới",
    dependencies=[Depends(require_permissions(PERM_CUSTOMER_CREATE))],
)
def create_customer(customer_in: CustomerCreate, db: Session = Depends(get_db)):
    existing = crud_customers.get_customer_by_phone(db, customer_in.phone)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Số điện thoại '{customer_in.phone}' đã được đăng ký cho khách hàng '{existing.full_name}'."
        )
    return crud_customers.create_customer(db, customer_in)

@router.get(
    "/",
    response_model=List[CustomerResponse],
    summary="Danh sách khách hàng",
    dependencies=[Depends(require_permissions(PERM_CUSTOMER_VIEW))],
)
def read_customers(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud_customers.get_customers(db, skip=skip, limit=limit)

@router.get(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Xem thông tin chi tiết khách hàng",
    dependencies=[Depends(require_permissions(PERM_CUSTOMER_VIEW))],
)
def read_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = crud_customers.get_customer(db, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy khách hàng.")
    return customer

@router.put(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Cập nhật thông tin khách hàng",
    dependencies=[Depends(require_permissions(PERM_CUSTOMER_UPDATE))],
)
def update_customer(customer_id: int, customer_in: CustomerUpdate, db: Session = Depends(get_db)):
    customer = crud_customers.update_customer(db, customer_id, customer_in)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy khách hàng để cập nhật.")
    return customer

@router.delete(
    "/{customer_id}",
    status_code=status.HTTP_200_OK,
    summary="Xóa khách hàng",
    dependencies=[Depends(require_permissions(PERM_CUSTOMER_DELETE))],
)
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    """
    [AUD-01] Xóa khách hàng an toàn:
    - Trước khi xóa, đếm số thiết bị (`product_instances`) và phiếu bảo hành
      (`warranty_tickets`) đang tham chiếu tới khách hàng này.
    - Nếu còn dữ liệu liên quan -> trả **409 Conflict** kèm thông báo tiếng Việt,
      KHÔNG xóa và KHÔNG cascade xóa thiết bị/phiếu (bảo toàn dữ liệu theo FK RESTRICT).
    - Nếu không còn tham chiếu -> xóa bình thường (200).
    """
    customer = crud_customers.get_customer(db, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy khách hàng để xóa.")

    instance_count = db.query(ProductInstance).filter(ProductInstance.customer_id == customer_id).count()
    ticket_count = db.query(WarrantyTicket).filter(WarrantyTicket.customer_id == customer_id).count()
    if instance_count > 0 or ticket_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Khách hàng đang có {instance_count} thiết bị / {ticket_count} phiếu bảo hành "
                "nên không thể xóa. Hãy xử lý dữ liệu liên quan trước."
            )
        )

    crud_customers.delete_customer(db, customer_id)
    return {"message": "Đã xóa khách hàng thành công.", "customer_id": customer_id}
