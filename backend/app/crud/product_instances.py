"""
CRUD Sản phẩm theo Serial (bảng product_instances) — Bổ sung đầy đủ yêu cầu KT2:
"CRUD sản phẩm: Tên sản phẩm + Serial + Ngày mua + Ngày hết hạn bảo hành + Mô tả".

Vì ERD tách thành 2 lớp:
- products          : model/catalog (tên, thương hiệu, mô tả, thời hạn BH mặc định)
- product_instances : thiết bị cụ thể theo serial (ngày mua, ngày hết hạn đóng băng)

Module này cung cấp CRUD trên product_instances và tự động đồng bộ các trường tên/mô tả
sang model products tương ứng khi cần.
"""
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Product, Customer, ProductInstance, WarrantyTicket
from app.schemas import SerialProductCreate, SerialProductUpdate
from app.services.warranty_rules import add_months_to_date


def get_product_instance(db: Session, instance_id: int) -> Optional[ProductInstance]:
    return db.query(ProductInstance).filter(ProductInstance.id == instance_id).first()


def get_by_serial(db: Session, serial_number: str) -> Optional[ProductInstance]:
    return db.query(ProductInstance).filter(ProductInstance.serial_number == serial_number).first()


def list_product_instances(
    db: Session,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 200
) -> List[ProductInstance]:
    """
    Liệt kê sản phẩm theo serial. Hỗ trợ tìm kiếm:
    - Theo Serial Number (so khớp một phần)
    - Theo Tên sản phẩm (model)
    """
    query = db.query(ProductInstance).join(Product).join(Customer)
    if search and search.strip():
        keyword = f"%{search.strip()}%"
        query = query.filter(
            or_(
                ProductInstance.serial_number.ilike(keyword),
                Product.name.ilike(keyword),
                Product.brand.ilike(keyword),
            )
        )
    return query.order_by(ProductInstance.id.desc()).offset(skip).limit(limit).all()


def _resolve_product(
    db: Session,
    product_id: Optional[int],
    product_name: Optional[str],
    brand: Optional[str],
    category: Optional[str],
    warranty_duration_months: Optional[int],
    description: Optional[str],
    creating: bool,
) -> Product:
    """Tìm model products theo product_id hoặc product_name; tạo mới nếu cần."""
    product = None
    if product_id is not None:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy model sản phẩm (products) có ID: {product_id}."
            )
        if warranty_duration_months:
            product.warranty_duration_months = warranty_duration_months
        if description:
            product.description = description
    elif product_name:
        product = db.query(Product).filter(Product.name == product_name.strip()).first()
        if not product:
            if not creating:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Không tìm thấy model sản phẩm '{product_name}'. Vui lòng chọn model đang có hoặc tạo sản phẩm mới."
                )
            months = warranty_duration_months or 12
            product = Product(
                name=product_name.strip(),
                brand=brand,
                category=category,
                warranty_duration_months=months,
                description=description,
            )
            db.add(product)
            db.flush()
        else:
            if warranty_duration_months:
                product.warranty_duration_months = warranty_duration_months
            if description:
                product.description = description
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vui lòng cung cấp 'product_id' hoặc 'product_name' để khai báo sản phẩm theo serial."
        )
    return product


def create_product_instance(db: Session, data: SerialProductCreate) -> ProductInstance:
    """Tạo một sản phẩm theo serial (đăng ký máy mới, đóng băng hạn bảo hành)."""
    serial_clean = data.serial_number.strip()
    existing = db.query(ProductInstance).filter(ProductInstance.serial_number == serial_clean).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Serial '{serial_clean}' đã tồn tại trong hệ thống. Không thể tạo trùng."
        )

    customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy khách hàng có ID: {data.customer_id}."
        )

    product = _resolve_product(
        db=db,
        product_id=data.product_id,
        product_name=data.product_name,
        brand=data.brand,
        category=data.category,
        warranty_duration_months=data.warranty_duration_months,
        description=data.description,
        creating=True,
    )

    # Tính ngày hết hạn bảo hành nếu người dùng không nhập trực tiếp
    months = data.warranty_duration_months or product.warranty_duration_months
    if data.warranty_end_date is not None:
        warranty_end = data.warranty_end_date
    else:
        warranty_end = add_months_to_date(data.purchase_date, months)

    if warranty_end < data.purchase_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ngày hết hạn bảo hành không được nhỏ hơn ngày mua."
        )

    instance = ProductInstance(
        product_id=product.id,
        customer_id=data.customer_id,
        serial_number=serial_clean,
        purchase_date=data.purchase_date,
        warranty_end_date=warranty_end,
        status=data.status,
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return instance


def update_product_instance(
    db: Session,
    instance_id: int,
    data: SerialProductUpdate,
) -> Optional[ProductInstance]:
    """Cập nhật thông tin sản phẩm theo serial (tên, hạn BH, mô tả, chủ sở hữu...)."""
    instance = get_product_instance(db, instance_id)
    if not instance:
        return None

    update_data = data.model_dump(exclude_unset=True)

    # ---- Xử lý đổi model sản phẩm / tên sản phẩm / mô tả / thời hạn BH ----
    product_changed = False
    if update_data.get("product_id") is not None:
        product = _resolve_product(db, update_data["product_id"], None, None, None, None, None, creating=False)
        instance.product_id = product.id
        product_changed = True
    elif update_data.get("product_name") or update_data.get("description") is not None:
        product = _resolve_product(
            db=db,
            product_id=instance.product_id,
            product_name=update_data.get("product_name"),
            brand=update_data.get("brand"),
            category=update_data.get("category"),
            warranty_duration_months=update_data.get("warranty_duration_months"),
            description=update_data.get("description"),
            creating=False,
        )
        if update_data.get("product_name"):
            product.name = update_data["product_name"].strip()
        if update_data.get("brand") is not None:
            product.brand = update_data["brand"]
        if update_data.get("category") is not None:
            product.category = update_data["category"]
        instance.product_id = product.id
        product_changed = True

    # ---- Cập nhật các cột trực tiếp của product_instances ----
    if update_data.get("customer_id") is not None:
        customer = db.query(Customer).filter(Customer.id == update_data["customer_id"]).first()
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy khách hàng có ID: {update_data['customer_id']}."
            )
        instance.customer_id = update_data["customer_id"]

    if update_data.get("serial_number") is not None:
        new_serial = update_data["serial_number"].strip()
        conflict = db.query(ProductInstance).filter(
            ProductInstance.serial_number == new_serial,
            ProductInstance.id != instance.id,
        ).first()
        if conflict:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Serial '{new_serial}' đã được dùng cho sản phẩm khác. Không thể cập nhật."
            )
        instance.serial_number = new_serial

    if update_data.get("purchase_date") is not None:
        instance.purchase_date = update_data["purchase_date"]
    if update_data.get("status") is not None:
        instance.status = update_data["status"]

    # ---- Tính lại ngày hết hạn nếu thay đổi ngày mua / hạn BH mà không nhập trực tiếp ngày kết thúc ----
    explicit_end = update_data.get("warranty_end_date")
    months_changed = update_data.get("warranty_duration_months") is not None
    purchase_changed = "purchase_date" in update_data and update_data.get("purchase_date") is not None

    if explicit_end is not None:
        instance.warranty_end_date = explicit_end
    elif months_changed or purchase_changed or product_changed:
        effective_product = db.query(Product).filter(Product.id == instance.product_id).first()
        base_months = update_data.get("warranty_duration_months")
        if base_months is None:
            base_months = effective_product.warranty_duration_months if effective_product else 12
        instance.warranty_end_date = add_months_to_date(instance.purchase_date, base_months)
        if update_data.get("warranty_duration_months") is not None and effective_product is not None:
            effective_product.warranty_duration_months = update_data["warranty_duration_months"]

    if instance.warranty_end_date < instance.purchase_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ngày hết hạn bảo hành không được nhỏ hơn ngày mua."
        )

    db.commit()
    db.refresh(instance)
    return instance


def delete_product_instance(db: Session, instance_id: int) -> str:
    """
    Xóa (hoặc chặn xóa an toàn) một sản phẩm theo serial.
    Trả về:
      - "deleted"     : xóa thành công
      - "has_tickets" : sản phẩm đang có phiếu bảo hành -> không xóa được (toàn vẹn dữ liệu)
      - "not_found"   : không tồn tại
    """
    instance = get_product_instance(db, instance_id)
    if not instance:
        return "not_found"

    ticket_count = db.query(WarrantyTicket).filter(WarrantyTicket.product_instance_id == instance_id).count()
    if ticket_count > 0:
        return "has_tickets"

    db.delete(instance)
    db.commit()
    return "deleted"

