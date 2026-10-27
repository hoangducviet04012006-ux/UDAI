"""
API Endpoint: /api/v1/warranty-tickets (Phiếu bảo hành)

Đợt hoàn thiện nghiệp vụ (Prompt 1) - PHIẾU BẢO HÀNH LÀ TRUNG TÂM:
    * `GET /{id}` trả về ĐẦY ĐỦ thông tin để xử lý trong MỘT màn hình:
      khách hàng, thiết bị, tiếp nhận, chẩn đoán, gợi ý AI, sửa chữa, trả máy,
      lịch sử và danh sách hành động mà người đang đăng nhập ĐƯỢC PHÉP thực hiện.
    * `GET /` hỗ trợ tìm kiếm theo mã phiếu / số sê-ri / tên khách / số điện thoại
      và lọc `mine=1` (phiếu của chính tôi) để nhân viên thấy ngay việc cần làm.
    * `PATCH /{id}/status` đi theo State Machine, bắt buộc kèm thông tin xử lý và
      chặn hoàn tất khi chưa đủ điều kiện (đã sửa xong + đang chờ trả máy).
    * `PATCH /{id}/diagnosis` / `PATCH /{id}/repair`: ghi nhận dữ liệu chuyên môn
      (kết luận của kỹ thuật viên) mà KHÔNG đổi trạng thái phiếu.

Đợt 7 - Phân quyền:
    * Xem / tra cứu / thống kê : `ticket.view` (mọi nhân viên đã đăng nhập).
    * Tiếp nhận lập phiếu      : `ticket.create` (QUẢN LÝ, TIẾP NHẬN).
    * Cập nhật trạng thái      : `ticket.update_status` (cả 3 vai trò theo luồng).
    * Ghi chẩn đoán / sửa chữa : `ticket.diagnose` / `ticket.repair` (KỸ THUẬT VIÊN, QUẢN LÝ).
    * Xác nhận đã trả máy      : `ticket.handover` (TIẾP NHẬN, QUẢN LÝ).
    * Chuyển sang REJECTED     : `ticket.reject` (chỉ QUẢN LÝ).
    * Người thực hiện (`created_by` / `changed_by` / `actor_id`) không được "khai khống":
      nhân viên chỉ ghi danh chính mình, quản lý được ghi danh bất kỳ ai.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import (
    TicketDiagnosisUpdate,
    TicketRepairUpdate,
    WarrantyTicketCreate,
    WarrantyTicketDetailResponse,
    WarrantyTicketResponse,
    WarrantyTicketStatusUpdate,
    WorkboardResponse,
)
from app.crud import warranty_tickets as crud_tickets
from app.services import ticket_view, workboard
from app.services.warranty_rules import (
    TICKET_STATUS_HINTS,
    TICKET_STATUS_LABELS,
    TICKET_STEPS,
    available_transitions,
    transition_rule,
)
from app.services.auth_service import (
    PERM_TICKET_CREATE,
    PERM_TICKET_DIAGNOSE,
    PERM_TICKET_HANDOVER,
    PERM_TICKET_REJECT,
    PERM_TICKET_REPAIR,
    PERM_TICKET_UPDATE_STATUS,
    PERM_TICKET_VIEW,
    ROLE_LABELS_VN,
    ensure_actor_allowed,
    has_permission,
    require_permissions,
)

router = APIRouter(prefix="/api/v1/warranty-tickets", tags=["Warranty Tickets (Phiếu bảo hành)"])

@router.post(
    "/",
    response_model=WarrantyTicketDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Tiếp nhận & Tạo phiếu bảo hành mới (Kiểm tra BR1 - BR4)",
)
def create_ticket(
    ticket_in: WarrantyTicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(PERM_TICKET_CREATE)),
):
    """
    Tạo phiếu bảo hành sau khi vượt qua toàn bộ 4 điều kiện nghiệp vụ:
    - **BR1**: Serial phải tồn tại trong hệ thống.
    - **BR2**: Sản phẩm còn hạn bảo hành (warranty_end_date >= check_date).
    - **BR3**: Không có phiếu bảo hành đang mở (RECEIVED, INSPECTING, REPAIRING, WAITING_RETURN).
    - **BR4**: Xác minh đúng khách hàng / chủ sở hữu sản phẩm.

    Đợt 7: chỉ QUẢN LÝ / TIẾP NHẬN có quyền `ticket.create`; người lập phiếu
    (`created_by`) không được khai khống (nhân viên chỉ ghi danh chính mình).

    Trả về CHI TIẾT PHIẾU vừa tạo (cùng cấu trúc với màn hình xử lý phiếu) để
    giao diện mở ngay phiếu cho nhân viên mà không cần gọi thêm API.
    """
    if ticket_in.created_by is not None:
        ensure_actor_allowed(db, current_user, ticket_in.created_by, "người lập phiếu bảo hành")
    ticket = crud_tickets.create_warranty_ticket_with_rules(db, ticket_in)
    return ticket_view.build_ticket_detail(db, ticket, current_user)

@router.get(
    "/stats/summary",
    summary="Thống kê phiếu theo trạng thái (toàn hệ thống hoặc theo nhân viên đang đăng nhập)",
    dependencies=[Depends(require_permissions(PERM_TICKET_VIEW))],
)
def get_tickets_summary(
    mine: bool = Query(
        False,
        description="true = chỉ tính phiếu mà tài khoản đang đăng nhập là người xử lý gần nhất",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(PERM_TICKET_VIEW)),
):
    """
    Số liệu cho bảng điều khiển.

    Ngoài số đếm theo trạng thái, endpoint trả thêm `workload` = danh sách việc cần làm
    THEO VAI TRÒ (kỹ thuật viên / tiếp nhận / quản lý) để giao diện hiển thị đúng việc
    của người đang đăng nhập thay vì bắt họ tự đoán.
    """
    scope_user_id = current_user.id if mine else None
    from app.models import Customer, Product, ProductInstance
    
    counts = crud_tickets.count_tickets_by_status(db, mine_user_id=scope_user_id)
    total_tickets = sum(counts.values())
    total_products = db.query(Product).count()
    total_customers = db.query(Customer).count()
    total_instances = db.query(ProductInstance).count()
    
    return {
        "scope": "MINE" if mine else "ALL",
        "scope_label": "Việc của tôi" if mine else "Toàn hệ thống",
        "total_tickets": total_tickets,
        "received": counts.get("RECEIVED", 0),
        "inspecting": counts.get("INSPECTING", 0),
        "repairing": counts.get("REPAIRING", 0),
        "waiting_return": counts.get("WAITING_RETURN", 0),
        "completed": counts.get("COMPLETED", 0),
        "rejected": counts.get("REJECTED", 0),
        "total_products": total_products,
        "total_customers": total_customers,
        "total_instances": total_instances,
        "workload": ticket_view.build_role_workload(
            current_user.role, counts, mine=bool(mine)
        ),
    }

@router.get(
    "/meta/workflow",
    summary="Mô tả quy trình phiếu bảo hành (5 bước + hành động theo quyền người đang đăng nhập)",
    dependencies=[Depends(require_permissions(PERM_TICKET_VIEW))],
)
def get_workflow_meta(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(PERM_TICKET_VIEW)),
):
    """
    Mô tả quy trình để giao diện hiển thị cho nhân viên KHÔNG cần biết API:
    nhãn 5 bước, câu mô tả trạng thái, và ma trận hành động theo từng trạng thái
    (đã lọc theo quyền của tài khoản đang đăng nhập).
    """
    matrix = {
        status_code: available_transitions(
            status_code, lambda permission: has_permission(current_user, permission)
        )
        for status_code in TICKET_STATUS_LABELS
    }
    return {
        "steps": TICKET_STEPS,
        "status_labels": TICKET_STATUS_LABELS,
        "status_hints": TICKET_STATUS_HINTS,
        "actions_by_status": matrix,
        "role": current_user.role,
        "role_label": ROLE_LABELS_VN.get(current_user.role, current_user.role),
    }

@router.get(
    "/meta/demo-data",
    summary="Lấy danh mục lỗi và serial mẫu phục vụ demo",
    dependencies=[Depends(require_permissions(PERM_TICKET_VIEW))],
)
def get_demo_meta(db: Session = Depends(get_db)):
    from app.models import ErrorCategory, ProductInstance, Product, Customer
    cats = db.query(ErrorCategory).all()
    instances = db.query(ProductInstance).join(Product).join(Customer).all()
    
    return {
        "error_categories": [{"id": c.id, "name": c.name, "description": c.description} for c in cats],
        "demo_instances": [
            {
                "serial_number": inst.serial_number,
                "product_name": inst.product.name if inst.product else "",
                "customer_name": inst.customer.full_name if inst.customer else "",
                "customer_id": inst.customer_id,
                "purchase_date": str(inst.purchase_date),
                "warranty_end_date": str(inst.warranty_end_date)
            }
            for inst in instances
        ]
    }

@router.get(
    "/workboard",
    response_model=WorkboardResponse,
    summary="Bảng điều khiển công việc THEO VAI TRÒ (Quản lý / Tiếp nhận / Kỹ thuật viên)",
)
def get_workboard(
    scope: Optional[str] = Query(
        None,
        description=(
            "Phạm vi số liệu: để trống = theo vai trò (mặc định), "
            "MINE = việc của tôi, ALL = toàn trung tâm"
        ),
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(PERM_TICKET_VIEW)),
):
    """
    Trả về ĐÚNG những gì vai trò đang đăng nhập cần cho ca làm việc:

    - `title` / `subtitle` / `cards`: tiêu đề và số liệu của vai trò đó.
    - `groups`: nhóm công việc (số lượng + danh sách phiếu cần xử lý ngay, mỗi
      phiếu đã kèm nút hành động mà tài khoản này ĐƯỢC PHÉP bấm).
    - `focus`: "Việc cần làm", đã sắp theo thứ tự nghiệp vụ của vai trò.
    - `attention`: "Việc cần chú ý" (chỉ Quản lý) kèm lý do lấy từ dữ liệu thật.
    - `my_tickets` / `active_tickets`: phiếu của tôi và phiếu đang xử lý toàn trung tâm.

    Quyền vẫn do backend kiểm tra: thiếu `ticket.view` sẽ bị chặn 403 trước khi tới đây.
    """
    return workboard.build_workboard(db, current_user, scope=scope)


@router.get(
    "/",
    response_model=List[WarrantyTicketResponse],
    summary="Danh sách phiếu bảo hành (lọc trạng thái / từ khoá / việc của tôi)",
    dependencies=[Depends(require_permissions(PERM_TICKET_VIEW))],
)
def read_tickets(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = Query(
        None,
        description=(
            "Lọc theo trạng thái: RECEIVED, INSPECTING, REPAIRING, WAITING_RETURN, COMPLETED, REJECTED. "
            "Có thể truyền nhiều trạng thái cách nhau bởi dấu phẩy (ví dụ: INSPECTING,REPAIRING)."
        ),
    ),
    q: Optional[str] = Query(None, description="Tìm theo mã phiếu / số sê-ri / tên khách hàng / số điện thoại"),
    mine: bool = Query(False, description="true = chỉ lấy phiếu mà tài khoản đang đăng nhập là người xử lý gần nhất"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(PERM_TICKET_VIEW)),
):
    """
    Mỗi dòng trả về thông tin nhân viên phụ trách, loại lỗi, số điện thoại khách hàng
    và NÚT HÀNH ĐỘNG theo quyền của người đang đăng nhập (`action_label`,
    `action_kind`, `primary_action`) để danh sách đủ dữ liệu làm việc.

    Bộ lọc `mine=1` chạy ở tầng CSDL (người xử lý gần nhất) nên số liệu và
    danh sách luôn khớp nhau dù có phân trang.
    """
    tickets = crud_tickets.get_warranty_tickets(
        db,
        skip=skip,
        limit=limit,
        status_filter=status,
        keyword=q,
        mine_user_id=current_user.id if mine else None,
    )
    return ticket_view.build_ticket_summaries(db, tickets, current_user=current_user)

@router.get(
    "/{ticket_id}",
    response_model=WarrantyTicketDetailResponse,
    summary="Màn hình xử lý phiếu: khách hàng, thiết bị, chẩn đoán, sửa chữa, trả máy, lịch sử, hành động được phép",
    dependencies=[Depends(require_permissions(PERM_TICKET_VIEW))],
)
def read_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(PERM_TICKET_VIEW)),
):
    ticket = crud_tickets.get_warranty_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phiếu bảo hành.")
    return ticket_view.build_ticket_detail(db, ticket, current_user)

@router.get(
    "/code/{ticket_code}",
    response_model=WarrantyTicketDetailResponse,
    summary="Tra cứu phiếu theo mã (trả về đủ dữ liệu màn hình xử lý)",
    dependencies=[Depends(require_permissions(PERM_TICKET_VIEW))],
)
def read_ticket_by_code(
    ticket_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(PERM_TICKET_VIEW)),
):
    ticket = crud_tickets.get_warranty_ticket_by_code(db, ticket_code)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy phiếu có mã: {ticket_code}")
    return ticket_view.build_ticket_detail(db, ticket, current_user)

@router.patch("/{ticket_id}/status", response_model=WarrantyTicketDetailResponse, summary="Cập nhật trạng thái phiếu theo quy trình (State Machine + thông tin xử lý)")
def update_status(
    ticket_id: int,
    status_update: WarrantyTicketStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(PERM_TICKET_UPDATE_STATUS)),
):
    """
    Cập nhật trạng thái phiếu theo đúng vòng đời nghiệp vụ (6 trạng thái):
    - `RECEIVED` (Mới tiếp nhận) -> `INSPECTING`
    - `INSPECTING` (Đang kiểm tra) -> `REPAIRING` hoặc `REJECTED` (bắt buộc lý do từ chối)
    - `REPAIRING` (Đang sửa chữa) -> `WAITING_RETURN` (sửa xong, chờ trả máy) hoặc `INSPECTING`
    - `WAITING_RETURN` (Chờ trả máy) -> `COMPLETED` (đã trả máy) hoặc `REPAIRING` (khách báo còn lỗi)
    - `REPAIRING` -> `COMPLETED` bị chặn (`[STATE MACHINE ERROR]`) vì bắt buộc qua "Chờ trả máy".

    Kiểm tra nghiệp vụ trước khi ghi CSDL:
    1. Phiếu tồn tại; người thực hiện là nhân viên có thật.
    2. Chuyển trạng thái nằm trong ma trận cho phép.
    3. Bước nghiệp vụ phải kèm thông tin xử lý (chẩn đoán / nội dung sửa chữa / ghi chú bàn giao).
    4. `WAITING_RETURN -> COMPLETED` chỉ thành công khi đủ điều kiện (thiết bị + khách hàng
       tồn tại, đã có thông tin sửa chữa, lịch sử đủ các bước).

    Phân quyền theo từng bước (backend chặn thật, không chỉ ẩn nút):
    - `ticket.update_status`: điều kiện chung để cập nhật trạng thái.
    - `ticket.handover`    : riêng bước "Xác nhận đã trả máy" (TIẾP NHẬN / QUẢN LÝ).
    - `ticket.reject`      : riêng bước "Từ chối bảo hành" (chỉ QUẢN LÝ).

    Trả về CHI TIẾT PHIẾU đã cập nhật (đủ dữ liệu để giao diện vẽ lại ngay một lần gọi).
    """
    ticket = crud_tickets.get_warranty_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy phiếu bảo hành có ID: {ticket_id}",
        )

    target_status = str(status_update.new_status).upper()
    rule = transition_rule(ticket.status, target_status)

    # Bước đặc biệt: từ chối bảo hành là quyết định của QUẢN LÝ
    if target_status == "REJECTED" and not has_permission(current_user, PERM_TICKET_REJECT):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Chỉ quản lý được xác nhận TỪ CHỐI bảo hành. "
                "Vui lòng chuyển hồ sơ cho quản lý quyết định."
            ),
        )

    # Bước đặc biệt: xác nhận đã trả máy = việc ở quầy (TIẾP NHẬN / QUẢN LÝ)
    if target_status == "COMPLETED" and not has_permission(current_user, PERM_TICKET_HANDOVER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Chỉ nhân viên tiếp nhận hoặc quản lý được xác nhận ĐÃ TRẢ MÁY cho khách. "
                "Kỹ thuật viên vui lòng chuyển máy ra quầy để bàn giao."
            ),
        )

    # Các bước còn lại: dùng đúng quyền khai báo trong ma trận hành động
    if rule and not has_permission(current_user, rule["permission"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Tài khoản \"{current_user.username}\" không có quyền thực hiện thao tác "
                f"\"{rule['button_label']}\"."
            ),
        )

    if status_update.changed_by is not None:
        ensure_actor_allowed(db, current_user, status_update.changed_by, "người cập nhật trạng thái")

    crud_tickets.update_ticket_status(db, ticket_id, status_update)
    updated = crud_tickets.get_warranty_ticket(db, ticket_id)
    return ticket_view.build_ticket_detail(db, updated, current_user)

@router.patch("/{ticket_id}/diagnosis", response_model=WarrantyTicketDetailResponse, summary="Ghi nhận CHẨN ĐOÁN của kỹ thuật viên (không đổi trạng thái phiếu)")
def update_diagnosis(
    ticket_id: int,
    payload: TicketDiagnosisUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(PERM_TICKET_DIAGNOSE)),
):
    """
    Lưu kết luận chẩn đoán của người có chuyên môn mà KHÔNG đổi trạng thái phiếu.

    Đây là "KỸ THUẬT VIÊN KẾT LUẬN" - hoàn toàn tách biệt với "AI GỢI Ý"
    (AI chỉ đề xuất và không tự ghi nhãn lỗi vào phiếu - KT3).
    """
    ensure_actor_allowed(db, current_user, payload.actor_id, "người ghi nhận chẩn đoán")
    crud_tickets.save_ticket_diagnosis(db, ticket_id, payload)
    ticket = crud_tickets.get_warranty_ticket(db, ticket_id)
    return ticket_view.build_ticket_detail(db, ticket, current_user)

@router.patch("/{ticket_id}/repair", response_model=WarrantyTicketDetailResponse, summary="Ghi nhận NỘI DUNG SỬA CHỮA (đã sửa + linh kiện thay thế) của kỹ thuật viên")
def update_repair(
    ticket_id: int,
    payload: TicketRepairUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(PERM_TICKET_REPAIR)),
):
    """
    Lưu nội dung đã kiểm tra/đã sửa chữa, linh kiện thay thế và ghi chú kỹ thuật.

    Mỗi lần lưu cũng ghi thêm một dòng vào bảng `repair_logs` để có nhật ký sửa chữa
    theo thời gian (ai làm, khi nào, thay linh kiện gì).
    """
    ensure_actor_allowed(db, current_user, payload.actor_id, "người ghi nhận sửa chữa")
    crud_tickets.save_ticket_repair(db, ticket_id, payload)
    ticket = crud_tickets.get_warranty_ticket(db, ticket_id)
    return ticket_view.build_ticket_detail(db, ticket, current_user)
