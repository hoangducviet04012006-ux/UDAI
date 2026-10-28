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
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Customer, Product, ProductInstance, User, WarrantyTicket
from app.schemas import (
    RejectionReviewRequest,
    TicketDiagnosisUpdate,
    TicketRepairUpdate,
    WarrantyTicketAssign,
    WarrantyTicketCreate,
    WarrantyTicketDetailResponse,
    WarrantyTicketProposal,
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
    validate_ticket_actor_access,
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
    ROLE_MANAGER,
    ROLE_RECEPTIONIST,
    ROLE_TECHNICIAN,
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
    - **BR2**: Sản phẩm còn hạn bảo hành (warranty_end_date >= check_date; không tự lấy ngày tiếp nhận làm ngày mua).
    - **BR3**: Không có phiếu bảo hành đang mở (RECEIVED, INSPECTING, REPAIRING, COMPLETED, REJECTED).
    - **BR4**: Xác minh đúng khách hàng / chủ sở hữu sản phẩm.
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
        description="true = chỉ tính phiếu trong phạm vi việc của tôi / việc tại quầy / phiếu được giao",
    ),
    scope: Optional[str] = Query(None, description="MINE hoặc ALL"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(PERM_TICKET_VIEW)),
):
    """
    Số liệu cho bảng điều khiển:
    - Thống kê 6 trạng thái: RECEIVED, INSPECTING, REPAIRING, COMPLETED, REJECTED, RETURNED.
    - Cùng phạm vi tài khoản, vai trò và trung tâm bảo hành được phép.
    - Đảm bảo Tổng phiếu = sum(các nhóm) nhất quán 100%.
    """
    effective_scope = "MINE" if mine or (scope and scope.upper() == "MINE") else ("ALL" if scope and scope.upper() == "ALL" else ("MINE" if current_user.role != ROLE_MANAGER and mine else "ALL"))
    if effective_scope == "MINE":
        if current_user.role == ROLE_TECHNICIAN:
            scope_label = "Phiếu được giao"
        elif current_user.role == ROLE_RECEPTIONIST:
            scope_label = "Việc tại quầy"
        else:
            scope_label = "Toàn trung tâm"
    else:
        scope_label = "Toàn trung tâm"

    counts = crud_tickets.count_tickets_by_status(
        db, current_user=current_user, scope=effective_scope
    )
    total_tickets = sum(counts.values())
    total_products = db.query(Product).count()
    total_customers = db.query(Customer).count()
    total_instances = db.query(ProductInstance).count()

    # Tính tổng số phiếu từ chối
    rej_query = db.query(WarrantyTicket).filter(
        or_(
            WarrantyTicket.status == "REJECTED",
            (WarrantyTicket.status == "RETURNED") & (WarrantyTicket.resolution == "REJECTED"),
        )
    )
    rej_query = crud_tickets.apply_ticket_scope_filter(
        rej_query, current_user=current_user, scope=effective_scope
    )
    total_rejections = rej_query.count()
    rejection_rate_percent = (
        round((total_rejections / total_tickets) * 100.0, 1) if total_tickets > 0 else 0.0
    )

    tickets_query = crud_tickets.apply_ticket_scope_filter(
        db.query(WarrantyTicket), current_user=current_user, scope=effective_scope
    )
    all_tickets = tickets_query.all()
    now = datetime.utcnow()

    proc_times: List[float] = []
    wait_times: List[float] = []

    for t in all_tickets:
        end_tech = t.completed_at or t.rejection_reviewed_at
        if end_tech and t.created_at:
            h_proc = (end_tech - t.created_at).total_seconds() / 3600.0
            if h_proc >= 0:
                proc_times.append(h_proc)

        if end_tech:
            if t.status == "RETURNED" and t.handed_over_at:
                h_wait = (t.handed_over_at - end_tech).total_seconds() / 3600.0
                if h_wait >= 0:
                    wait_times.append(h_wait)
            elif t.status in ("COMPLETED", "REJECTED"):
                h_wait = (now - end_tech).total_seconds() / 3600.0
                if h_wait >= 0:
                    wait_times.append(h_wait)

    avg_processing_hours = (
        round(sum(proc_times) / len(proc_times), 1) if proc_times else 0.0
    )
    avg_waiting_hours = (
        round(sum(wait_times) / len(wait_times), 1) if wait_times else 0.0
    )

    missing_time_count = 0
    for t in all_tickets:
        if t.status in ("COMPLETED", "REJECTED", "RETURNED"):
            end_tech_check = t.completed_at or t.rejection_reviewed_at
            if not end_tech_check or not t.created_at or (end_tech_check - t.created_at).total_seconds() < 0:
                missing_time_count += 1

    return {
        "scope": effective_scope,
        "scope_label": scope_label,
        "total_tickets": total_tickets,
        "received": counts.get("RECEIVED", 0),
        "inspecting": counts.get("INSPECTING", 0),
        "repairing": counts.get("REPAIRING", 0),
        "completed": counts.get("COMPLETED", 0),
        "rejected": counts.get("REJECTED", 0),
        "returned": counts.get("RETURNED", 0),
        "total_rejections": total_rejections,
        "rejection_rate_percent": rejection_rate_percent,
        "avg_processing_time_hours": avg_processing_hours,
        "avg_waiting_time_hours": avg_waiting_hours,
        "missing_time_tickets_count": missing_time_count,
        "valid_time_tickets_count": len(proc_times),
        "metrics_explanation": {
            "rejection_rate": "Tỷ lệ từ chối (%) = (Số phiếu REJECTED + số phiếu RETURNED có resolution='REJECTED') / Tổng phiếu * 100. Đảm bảo giữ nguyên kết quả từ chối sau khi đã đóng phiếu.",
            "processing_time": "Thời gian xử lý kỹ thuật: Tính từ thời điểm tiếp nhận (created_at) đến khi hoàn tất sửa chữa / duyệt từ chối (completed_at). Các phiếu thiếu bằng chứng mốc thời gian được giữ trống (NULL) và loại khỏi mẫu tính để tránh sai lệch số liệu.",
            "waiting_time": "Thời gian chờ nhận máy: Tính từ khi hoàn tất kỹ thuật đến khi bàn giao đóng phiếu (handed_over_at) hoặc thời điểm hiện tại đối với phiếu đang chờ khách.",
            "data_integrity": f"Có {missing_time_count} phiếu kết thúc nhưng thiếu mốc thời gian hoàn tất kỹ thuật được xác thực. Hệ thống giữ nguyên trạng thái dữ liệu thiếu, không gán ép thời gian bắt đầu sửa.",
        },
        "total_products": total_products,
        "total_customers": total_customers,
        "total_instances": total_instances,
        "workload": ticket_view.build_role_workload(
            current_user.role, counts, mine=(effective_scope == "MINE")
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
            "Lọc theo trạng thái: RECEIVED, INSPECTING, REPAIRING, COMPLETED, REJECTED, RETURNED. "
            "Có thể truyền nhiều trạng thái cách nhau bởi dấu phẩy (ví dụ: INSPECTING,REPAIRING)."
        ),
    ),
    q: Optional[str] = Query(None, description="Tìm theo mã phiếu / số sê-ri / tên khách hàng / số điện thoại"),
    mine: bool = Query(False, description="true = lọc theo vai trò (Phiếu được giao / Việc tại quầy)"),
    scope: Optional[str] = Query(None, description="MINE hoặc ALL"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(PERM_TICKET_VIEW)),
):
    """
    Mỗi dòng trả về thông tin nhân viên phụ trách, loại lỗi, số điện thoại khách hàng
    và NÚT HÀNH ĐỘNG theo quyền của người đang đăng nhập (`action_label`,
    `action_kind`, `primary_action`) để danh sách đủ dữ liệu làm việc.

    Bộ lọc phạm vi chạy ở tầng CSDL (theo vai trò và trung tâm bảo hành) nên số liệu và
    danh sách luôn khớp nhau dù có phân trang.
    """
    tickets = crud_tickets.get_warranty_tickets(
        db,
        skip=skip,
        limit=limit,
        status_filter=status,
        keyword=q,
        current_user=current_user,
        scope=scope,
        mine=mine,
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

@router.post(
    "/{ticket_id}/assign",
    response_model=WarrantyTicketDetailResponse,
    summary="Phân công hoặc phân công lại kỹ thuật viên phụ trách phiếu (Chỉ Quản lý)",
)
def assign_technician(
    ticket_id: int,
    payload: WarrantyTicketAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(PERM_TICKET_UPDATE_STATUS)),
):
    """Phân công hoặc phân công lại KTV phụ trách: CHỈ QUẢN LÝ thực hiện."""
    if current_user.role != ROLE_MANAGER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ Quản lý mới có quyền phân công hoặc phân công lại kỹ thuật viên phụ trách phiếu.",
        )
    crud_tickets.assign_technician_to_ticket(
        db, ticket_id, payload.technician_id, current_user.id, payload.note
    )
    ticket = crud_tickets.get_warranty_ticket(db, ticket_id)
    return ticket_view.build_ticket_detail(db, ticket, current_user)


@router.post(
    "/{ticket_id}/propose-rejection",
    response_model=WarrantyTicketDetailResponse,
    summary="Kỹ thuật viên đề xuất từ chối bảo hành kèm bằng chứng kiểm tra",
)
def propose_rejection(
    ticket_id: int,
    payload: WarrantyTicketProposal,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(PERM_TICKET_DIAGNOSE)),
):
    """KTV phụ trách ghi nhận đề xuất từ chối để Quản lý xem xét duyệt."""
    ticket = crud_tickets.get_warranty_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phiếu bảo hành.")
    validate_ticket_actor_access(ticket, current_user)
    crud_tickets.propose_ticket_rejection(
        db, ticket_id, payload.proposal_note, current_user
    )
    updated = crud_tickets.get_warranty_ticket(db, ticket_id)
    return ticket_view.build_ticket_detail(db, updated, current_user)


@router.post(
    "/{ticket_id}/review-rejection-proposal",
    response_model=WarrantyTicketDetailResponse,
    summary="Quản lý xét duyệt đề xuất từ chối của KTV (APPROVED hoặc DECLINED)",
)
def review_rejection_proposal(
    ticket_id: int,
    payload: RejectionReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(PERM_TICKET_REJECT)),
):
    """Quản lý xét duyệt đề xuất từ chối: APPROVED (chuyển sang REJECTED) hoặc DECLINED (giữ ở INSPECTING)."""
    crud_tickets.review_ticket_rejection_proposal(
        db, ticket_id, payload.decision, payload.note, current_user
    )
    updated = crud_tickets.get_warranty_ticket(db, ticket_id)
    return ticket_view.build_ticket_detail(db, updated, current_user)


@router.patch("/{ticket_id}/status", response_model=WarrantyTicketDetailResponse, summary="Cập nhật trạng thái phiếu theo quy trình (State Machine + thông tin xử lý)")
def update_status(
    ticket_id: int,
    status_update: WarrantyTicketStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(PERM_TICKET_UPDATE_STATUS)),
):
    """
    Cập nhật trạng thái phiếu theo đúng luồng chuẩn:
    - Luồng sửa chữa: RECEIVED -> INSPECTING -> REPAIRING -> COMPLETED -> RETURNED.
    - Luồng từ chối: INSPECTING -> REJECTED -> RETURNED.

    Phân quyền per-ticket:
    - Kỹ thuật viên chỉ thao tác trên phiếu được phân công cho mình; không được duyệt từ chối hoặc trả máy.
    - Nhân viên tiếp nhận không ghi chẩn đoán, không sửa chữa, không duyệt từ chối; chỉ xác nhận trả máy từ COMPLETED hoặc REJECTED.
    - Quản lý duyệt từ chối (bắt buộc lý do).
    - Cập nhật phiếu và lịch sử trong cùng giao dịch.
    """
    ticket = crud_tickets.get_warranty_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy phiếu bảo hành có ID: {ticket_id}",
        )

    target_status = str(status_update.new_status).upper()
    is_technical = target_status in ("INSPECTING", "REPAIRING", "COMPLETED", "REJECTED")
    # 1. Kiểm tra quyền thao tác trên phiếu này (per-ticket access)
    validate_ticket_actor_access(ticket, current_user, is_technical=is_technical)

    if ticket.status == target_status:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"CONCURRENCY_CONFLICT: Phiếu đã ở trạng thái '{target_status}'. Thao tác có thể đã được xử lý đồng thời bởi yêu cầu khác."
        )
    rule = transition_rule(ticket.status, target_status)

    # 1b. Phân công KTV: Chỉ Quản lý mới có quyền phân công/đổi KTV
    if status_update.technician_id is not None and current_user.role != ROLE_MANAGER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ Quản lý mới có quyền phân công hoặc đổi kỹ thuật viên phụ trách phiếu.",
        )

    # 2. Kiểm tra vai trò Tiếp nhận không được làm việc kỹ thuật hoặc duyệt từ chối
    if current_user.role == ROLE_RECEPTIONIST and target_status in ("REPAIRING", "COMPLETED", "REJECTED"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Nhân viên tiếp nhận không được ghi kết quả kiểm tra/sửa chữa hoặc tự duyệt từ chối. "
                "Thao tác này thuộc phòng kỹ thuật / quản lý."
            ),
        )

    # 3. Bước duyệt từ chối bảo hành: chỉ QUẢN LÝ
    if target_status == "REJECTED" and not has_permission(current_user, PERM_TICKET_REJECT):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Chỉ quản lý được xác nhận TỪ CHỐI bảo hành. "
                "Kỹ thuật viên vui lòng ghi đề xuất từ chối để quản lý xem xét."
            ),
        )

    # 4. Bước xác nhận trả máy (RETURNED): TIẾP NHẬN hoặc QUẢN LÝ
    if target_status == "RETURNED" and not has_permission(current_user, PERM_TICKET_HANDOVER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Chỉ nhân viên tiếp nhận hoặc quản lý được xác nhận ĐÃ TRẢ MÁY cho khách. "
                "Kỹ thuật viên vui lòng chuyển máy ra quầy để bàn giao."
            ),
        )

    # 5. Các bước còn lại: dùng đúng quyền khai báo trong ma trận hành động
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

    crud_tickets.update_ticket_status(db, ticket_id, status_update, actor=current_user)
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
    Kiểm tra quyền per-ticket: KTV chỉ thao tác phiếu được phân công.
    """
    ticket = crud_tickets.get_warranty_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phiếu bảo hành.")
    validate_ticket_actor_access(ticket, current_user, is_technical=True)
    ensure_actor_allowed(db, current_user, payload.actor_id, "người ghi nhận chẩn đoán")
    crud_tickets.save_ticket_diagnosis(db, ticket_id, payload)
    updated = crud_tickets.get_warranty_ticket(db, ticket_id)
    return ticket_view.build_ticket_detail(db, updated, current_user)

@router.patch("/{ticket_id}/repair", response_model=WarrantyTicketDetailResponse, summary="Ghi nhận NỘI DUNG SỬA CHỮA (đã sửa + linh kiện thay thế) của kỹ thuật viên")
def update_repair(
    ticket_id: int,
    payload: TicketRepairUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(PERM_TICKET_REPAIR)),
):
    """
    Lưu nội dung đã kiểm tra/đã sửa chữa, linh kiện thay thế và ghi chú kỹ thuật.
    Kiểm tra quyền per-ticket: KTV chỉ thao tác phiếu được phân công.
    """
    ticket = crud_tickets.get_warranty_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phiếu bảo hành.")
    validate_ticket_actor_access(ticket, current_user, is_technical=True)
    ensure_actor_allowed(db, current_user, payload.actor_id, "người ghi nhận sửa chữa")
    crud_tickets.save_ticket_repair(db, ticket_id, payload)
    updated = crud_tickets.get_warranty_ticket(db, ticket_id)
    return ticket_view.build_ticket_detail(db, updated, current_user)
