"""
API Endpoint: /api/v1/products (Danh mục máy / model sản phẩm)

Đợt 7 - Phân quyền:
    * Xem danh mục  : quyền `product.view` (mọi nhân viên đã đăng nhập).
    * Thêm/sửa/xóa  : quyền `product.manage` (chỉ QUẢN LÝ).
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Product, ProductInstance
from app.schemas import ProductCreate, ProductUpdate, ProductResponse
from app.crud import products as crud_products
from app.services.auth_service import (
    PERM_PRODUCT_MANAGE,
    PERM_PRODUCT_VIEW,
    require_permissions,
)

router = APIRouter(prefix="/api/v1/products", tags=["Products (Sản phẩm)"])

@router.post(
    "/",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo mới sản phẩm",
    dependencies=[Depends(require_permissions(PERM_PRODUCT_MANAGE))],
)
def create_product(product_in: ProductCreate, db: Session = Depends(get_db)):
    return crud_products.create_product(db, product_in)

@router.get(
    "/",
    response_model=List[ProductResponse],
    summary="Lấy danh sách sản phẩm (model)",
    dependencies=[Depends(require_permissions(PERM_PRODUCT_VIEW))],
)
def read_products(
    search: Optional[str] = Query(None, description="Tìm kiếm theo tên / thương hiệu"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    from sqlalchemy import or_
    q = db.query(Product)
    if search and search.strip():
        keyword = f"%{search.strip()}%"
        q = q.filter(or_(Product.name.ilike(keyword), Product.brand.ilike(keyword), Product.category.ilike(keyword)))
    return q.order_by(Product.id).offset(skip).limit(limit).all()

@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Xem chi tiết sản phẩm",
    dependencies=[Depends(require_permissions(PERM_PRODUCT_VIEW))],
)
def read_product(product_id: int, db: Session = Depends(get_db)):
    product = crud_products.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy sản phẩm.")
    return product

@router.put(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Cập nhật sản phẩm",
    dependencies=[Depends(require_permissions(PERM_PRODUCT_MANAGE))],
)
def update_product(product_id: int, product_in: ProductUpdate, db: Session = Depends(get_db)):
    product = crud_products.update_product(db, product_id, product_in)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy sản phẩm để cập nhật.")
    return product

@router.delete(
    "/{product_id}",
    status_code=status.HTTP_200_OK,
    summary="Xóa sản phẩm (model)",
    dependencies=[Depends(require_permissions(PERM_PRODUCT_MANAGE))],
)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = crud_products.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy sản phẩm để xóa.")

    # Chặn xóa model khi vẫn còn sản phẩm theo serial đang tham chiếu (FK RESTRICT)
    instance_count = db.query(ProductInstance).filter(ProductInstance.product_id == product_id).count()
    if instance_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Không thể xóa model sản phẩm (ID: {product_id}) vì vẫn còn {instance_count} sản phẩm theo serial "
                "đang tham chiếu. Hãy xóa/vô hiệu hóa các sản phẩm serial đó trước."
            )
        )

    success = crud_products.delete_product(db, product_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy sản phẩm để xóa.")
    return {"message": "Đã xóa sản phẩm thành công.", "product_id": product_id}
