from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models import Customer
from app.schemas import CustomerCreate, CustomerUpdate

def get_customer(db: Session, customer_id: int) -> Optional[Customer]:
    return db.query(Customer).filter(Customer.id == customer_id).first()

def get_customer_by_phone(db: Session, phone: str) -> Optional[Customer]:
    return db.query(Customer).filter(Customer.phone == phone).first()

def get_customers(db: Session, skip: int = 0, limit: int = 100) -> List[Customer]:
    return db.query(Customer).offset(skip).limit(limit).all()

def create_customer(db: Session, customer_in: CustomerCreate) -> Customer:
    db_customer = Customer(
        full_name=customer_in.full_name,
        phone=customer_in.phone,
        email=customer_in.email,
        address=customer_in.address
    )
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer

def update_customer(db: Session, customer_id: int, customer_in: CustomerUpdate) -> Optional[Customer]:
    db_customer = get_customer(db, customer_id)
    if not db_customer:
        return None
    update_data = customer_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_customer, field, value)
    db.commit()
    db.refresh(db_customer)
    return db_customer

def delete_customer(db: Session, customer_id: int) -> bool:
    """
    [AUD-01] Xóa khách hàng.
    - Trả ``False`` nếu khách hàng không tồn tại (router sẽ trả 404).
    - Nếu CSDL từ chối vì còn dữ liệu tham chiếu (FK RESTRICT / NOT NULL),
      rollback giao dịch và trả **409 Conflict** thay vì để lỗi 500 thoát ra.
    - KHÔNG cascade xóa thiết bị/phiếu bảo hành.
    """
    db_customer = get_customer(db, customer_id)
    if not db_customer:
        return False
    try:
        db.delete(db_customer)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Khách hàng đang được dữ liệu khác tham chiếu nên không thể xóa. "
                "Hãy xử lý dữ liệu liên quan trước."
            )
        )
    return True
