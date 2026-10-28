"""
=====================================================================
MÀN HÌNH CÔNG VIỆC THEO VAI TRÒ (Đợt "Mỗi vai trò thấy đúng việc của mình")
=====================================================================
Mục tiêu: sau khi đăng nhập, bảng điều khiển trả lời NGAY câu hỏi
"Hiện tại tôi cần làm gì?" mà nhân viên không phải mở từng menu để tìm việc.

Cách làm (backend là nguồn sự thật):
    * Mỗi vai trò có một "bố cục" riêng: tiêu đề, thẻ số liệu, nhóm công việc,
      thứ tự ưu tiên việc cần làm, và các thao tác nhanh.
    * Nhóm công việc trả KÈM danh sách phiếu (đã kèm hành động được phép theo
      quyền), nên bấm một ô là mở ngay việc - không phải tự đi tìm mã phiếu.
    * "Việc cần chú ý" của Quản lý chỉ dùng DỮ LIỆU THẬT của phiếu
      (thiếu kết luận chẩn đoán, thiếu nội dung sửa chữa, máy đã sửa xong chờ
      khách, số ngày kể từ lần cập nhật gần nhất). KHÔNG tự đặt ngưỡng
      "quá lâu" khi hệ thống chưa có quy tắc đó.
    * Quyền vẫn do backend kiểm tra (dependencies của router): mọi mục ở đây
      chỉ được trả khi tài khoản có quyền `ticket.view`.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.crud import warranty_tickets as crud_tickets
from app.models import Customer, ProductInstance, User, WarrantyTicket
from app.services import ticket_view
from app.services.auth_service import (
    PERM_TICKET_CREATE,
    PERM_TICKET_HANDOVER,
    PERM_USER_VIEW,
    ROLE_LABELS_VN,
    ROLE_MANAGER,
    ROLE_RECEPTIONIST,
    ROLE_TECHNICIAN,
    has_permission,
)
from app.services.warranty_rules import (
    OPEN_TICKET_STATUSES,
    TICKET_STATUS_LABELS,
)

# Giới hạn số dòng mỗi khối: bảng điều khiển chỉ cần việc cần làm NGAY,
# danh sách đầy đủ nằm ở màn "Phiếu bảo hành".
GROUP_ITEM_LIMIT = 6
FOCUS_LIMIT = 10
ATTENTION_LIMIT = 10
TABLE_LIMIT = 15

SCOPE_DEFAULT = "DEFAULT"
SCOPE_MINE = "MINE"
SCOPE_ALL = "ALL"
VALID_SCOPES = (SCOPE_DEFAULT, SCOPE_MINE, SCOPE_ALL)

# Màu trạng thái dùng NHẤT QUÁN ở mọi màn hình (khớp badge-* trong styles.css)
STATUS_TONES: Dict[str, str] = {
    "RECEIVED": "blue",
    "INSPECTING": "amber",
    "REPAIRING": "purple",
    "COMPLETED": "emerald",
    "REJECTED": "rose",
    "RETURNED": "slate",
}

# ------------------------------ Thẻ số liệu -------------------------------
CARD_DEFS: Dict[str, Dict[str, str]] = {
    "TOTAL": {
        "label": "Tổng phiếu",
        "description": "Tất cả phiếu bảo hành của trung tâm",
        "tone": "slate",
    },
    "RECEIVED": {
        "label": "Tiếp nhận",
        "description": "Máy vừa nhận tại quầy, chờ KTV kiểm tra",
        "tone": STATUS_TONES["RECEIVED"],
    },
    "INSPECTING": {
        "label": "Kiểm tra",
        "description": "KTV đang xác định nguyên nhân & điều kiện bảo hành",
        "tone": STATUS_TONES["INSPECTING"],
    },
    "REPAIRING": {
        "label": "Sửa chữa",
        "description": "Máy đang trong quá trình sửa chữa",
        "tone": STATUS_TONES["REPAIRING"],
    },
    "COMPLETED": {
        "label": "Hoàn tất",
        "description": "Đã sửa xong đạt yêu cầu, chờ khách nhận máy",
        "tone": STATUS_TONES["COMPLETED"],
    },
    "REJECTED": {
        "label": "Từ chối",
        "description": "Không đủ điều kiện bảo hành, chờ trả máy",
        "tone": STATUS_TONES["REJECTED"],
    },
    "RETURNED": {
        "label": "Đã trả máy",
        "description": "Đã bàn giao cho khách, đóng phiếu",
        "tone": STATUS_TONES["RETURNED"],
    },
    "CUSTOMERS": {
        "label": "Khách hàng",
        "description": "Khách hàng đang được quản lý",
        "tone": "cyan",
    },
    "DEVICES": {
        "label": "Thiết bị đã đăng ký",
        "description": "Thiết bị theo số sê-ri",
        "tone": "indigo",
    },
}

# ------------------------------ Nhóm công việc ----------------------------
# `scope`: ALL  = việc chung của trung tâm
#          MINE = việc mà chính người đang đăng nhập đang phụ trách
# `action_target` / `action_label`: câu chữ nút hành động theo VAI TRÒ
WORK_GROUPS: Dict[str, List[Dict[str, Any]]] = {
    ROLE_MANAGER: [
        {
            "key": "received",
            "label": "Tiếp nhận",
            "statuses": ["RECEIVED"],
            "scope": "ALL",
            "description": "Phiếu mới tại quầy, cần phân công KTV kiểm tra.",
            "action_target": "INSPECTING",
            "action_label": "Phân công / Kiểm tra",
        },
        {
            "key": "inspecting",
            "label": "Đang kiểm tra",
            "statuses": ["INSPECTING"],
            "scope": "ALL",
            "description": "KTV đang xác định lỗi & điều kiện bảo hành; duyệt từ chối nếu có đề xuất.",
            "action_target": None,
            "action_label": "Xem tiến độ",
        },
        {
            "key": "repairing",
            "label": "Đang sửa chữa",
            "statuses": ["REPAIRING"],
            "scope": "ALL",
            "description": "Máy đang sửa; theo dõi tiến độ và kiểm tra sau sửa.",
            "action_target": None,
            "action_label": "Xem tiến độ",
        },
        {
            "key": "completed",
            "label": "Hoàn tất (Chờ trả)",
            "statuses": ["COMPLETED"],
            "scope": "ALL",
            "description": "Máy đã sửa xong đạt yêu cầu, đang chờ khách tới nhận.",
            "action_target": "RETURNED",
            "action_label": "Xác nhận trả máy",
        },
        {
            "key": "rejected",
            "label": "Từ chối (Chờ trả)",
            "statuses": ["REJECTED"],
            "scope": "ALL",
            "description": "Không tiếp nhận bảo hành, đang chờ trả máy cho khách.",
            "action_target": "RETURNED",
            "action_label": "Xác nhận trả máy",
        },
        {
            "key": "returned",
            "label": "Đã trả máy",
            "statuses": ["RETURNED"],
            "scope": "ALL",
            "description": "Phiếu đã bàn giao xong cho khách, đã đóng.",
            "action_target": None,
            "action_label": "Xem phiếu",
        },
    ],
    ROLE_RECEPTIONIST: [
        {
            "key": "to_receive",
            "label": "Cần tiếp nhận",
            "statuses": ["RECEIVED"],
            "scope": "MINE",
            "description": "Máy vừa nhận tại quầy, chờ Quản lý phân công KTV kiểm tra.",
            "action_target": None,
            "action_label": "Xem phiếu",
        },
        {
            "key": "processing",
            "label": "Đang xử lý kỹ thuật",
            "statuses": ["INSPECTING", "REPAIRING"],
            "scope": "ALL",
            "description": "Máy đang được KTV kiểm tra/sửa — dùng khi khách hỏi thông tin.",
            "action_target": None,
            "action_label": "Xem tiến độ",
        },
        {
            "key": "completed_return",
            "label": "Chờ trả máy (Hoàn tất)",
            "statuses": ["COMPLETED"],
            "scope": "MINE",
            "description": "Máy sửa xong đạt yêu cầu, bàn giao cho khách và đóng phiếu.",
            "action_target": "RETURNED",
            "action_label": "Xác nhận trả máy",
        },
        {
            "key": "rejected_return",
            "label": "Chờ trả máy (Từ chối)",
            "statuses": ["REJECTED"],
            "scope": "MINE",
            "description": "Phiếu bị từ chối bảo hành, bàn giao trả máy lại cho khách.",
            "action_target": "RETURNED",
            "action_label": "Xác nhận trả máy",
        },
    ],
    ROLE_TECHNICIAN: [
        {
            "key": "assigned_received",
            "label": "Phiếu được giao",
            "statuses": ["RECEIVED"],
            "scope": "MINE",
            "description": "Máy được phân công cho bạn, bắt đầu kiểm tra.",
            "action_target": "INSPECTING",
            "action_label": "Bắt đầu kiểm tra",
        },
        {
            "key": "inspecting",
            "label": "Đang kiểm tra",
            "statuses": ["INSPECTING"],
            "scope": "MINE",
            "description": "Chẩn đoán lỗi & điều kiện bảo hành, hoặc đề xuất từ chối.",
            "action_target": "REPAIRING",
            "action_label": "Cập nhật kiểm tra",
        },
        {
            "key": "repairing",
            "label": "Đang sửa chữa",
            "statuses": ["REPAIRING"],
            "scope": "MINE",
            "description": "Ghi nội dung sửa, kiểm tra sau sửa đạt yêu cầu rồi xác nhận hoàn tất.",
            "action_target": "COMPLETED",
            "action_label": "Xác nhận hoàn tất",
        },
        {
            "key": "completed",
            "label": "Đã hoàn tất",
            "statuses": ["COMPLETED"],
            "scope": "MINE",
            "description": "Đã sửa xong đạt yêu cầu; quầy tiếp nhận sẽ bàn giao cho khách.",
            "action_target": None,
            "action_label": "Xem phiếu",
        },
        {
            "key": "rejected",
            "label": "Đã từ chối",
            "statuses": ["REJECTED"],
            "scope": "MINE",
            "description": "Phiếu đã từ chối bảo hành; quầy tiếp nhận sẽ bàn giao lại máy cho khách.",
            "action_target": None,
            "action_label": "Xem phiếu",
        },
    ],
}

# ---------------------- Bố cục bảng điều khiển theo vai trò ----------------
ROLE_LAYOUT: Dict[str, Dict[str, Any]] = {
    ROLE_MANAGER: {
        "title": "Tổng quan trung tâm",
        "subtitle": "Toàn bộ tình hình tiếp nhận và xử lý bảo hành trong ngày.",
        "cards": ["TOTAL", "IN_PROGRESS", "WAITING_RETURN", "RETURNED"],
        "focus_order": ["RECEIVED", "INSPECTING", "REPAIRING", "COMPLETED", "REJECTED"],
        "show_attention": True,
        "table_title": "Phiếu đang xử lý (toàn trung tâm)",
        "table_scope": SCOPE_ALL,
    },
    ROLE_RECEPTIONIST: {
        "title": "Việc tại quầy tiếp nhận",
        "subtitle": "Những phiếu cần bạn xử lý ngay: tiếp nhận máy và bàn giao trả máy cho khách.",
        "cards": ["TOTAL", "IN_PROGRESS", "WAITING_RETURN", "RETURNED"],
        "focus_order": ["COMPLETED", "REJECTED", "RECEIVED", "INSPECTING", "REPAIRING"],
        "show_attention": False,
        "table_title": "Phiếu tại quầy tiếp nhận",
        "table_scope": SCOPE_MINE,
    },
    ROLE_TECHNICIAN: {
        "title": "Công việc kỹ thuật",
        "subtitle": "Máy được phân công kiểm tra, đang sửa chữa và các phiếu cần cập nhật kết quả.",
        "cards": ["TOTAL", "IN_PROGRESS", "WAITING_RETURN", "RETURNED"],
        "focus_order": ["RECEIVED", "INSPECTING", "REPAIRING", "COMPLETED", "REJECTED"],
        "show_attention": False,
        "table_title": "Phiếu được giao cho tôi",
        "table_scope": SCOPE_MINE,
    },
}

# -------------------------------- Thao tác nhanh ---------------------------
QUICK_ACTIONS: Dict[str, List[Dict[str, Any]]] = {
    ROLE_MANAGER: [
        {
            "key": "all_tickets",
            "label": "Xem toàn bộ phiếu",
            "description": "Danh sách phiếu của cả trung tâm",
            "icon": "list-checks",
            "primary": True,
        },
        {
            "key": "lookup",
            "label": "Tra cứu bảo hành",
            "description": "Tra theo số sê-ri hoặc mã phiếu",
            "icon": "search-check",
        },
        {
            "key": "ai",
            "label": "Hỗ trợ xác định lỗi",
            "description": "Gợi ý loại lỗi cho một phiếu",
            "icon": "wand-2",
        },
        {
            "key": "accounts",
            "label": "Tài khoản nhân viên",
            "description": "Tài khoản và vai trò làm việc",
            "icon": "shield-user",
        },
    ],
    ROLE_RECEPTIONIST: [
        {
            "key": "receive",
            "label": "Tiếp nhận máy mới",
            "description": "Đăng ký máy (nếu chưa có) và tạo phiếu bảo hành",
            "icon": "package-plus",
            "primary": True,
        },
        {
            "key": "waiting_return",
            "label": "Danh sách chờ trả máy",
            "description": "Máy hoàn tất hoặc từ chối, cần bàn giao cho khách",
            "icon": "handshake",
        },
        {
            "key": "lookup",
            "label": "Tra cứu bảo hành",
            "description": "Khách gọi tới: tra theo số sê-ri hoặc mã phiếu",
            "icon": "search-check",
        },
    ],
    ROLE_TECHNICIAN: [
        {
            "key": "waiting_inspect",
            "label": "Phiếu được phân công",
            "description": "Máy được phân công cho bạn, bắt đầu kiểm tra",
            "icon": "stethoscope",
            "primary": True,
        },
        {
            "key": "ai",
            "label": "Hỗ trợ xác định lỗi",
            "description": "Hệ thống gợi ý loại lỗi để tham khảo",
            "icon": "wand-2",
        },
        {
            "key": "lookup",
            "label": "Tra cứu bảo hành",
            "description": "Tra theo số sê-ri hoặc mã phiếu",
            "icon": "search-check",
        },
    ],
}

# ------------------- Ghi chú nghiệp vụ theo vai trò (việc này của ai) ------
ROLE_NOTES: Dict[str, List[Dict[str, Any]]] = {
    ROLE_MANAGER: [
        "Chỉ Quản lý được duyệt xác nhận TỪ CHỐI bảo hành (kèm lý do bắt buộc).",
        "Có thể phân công kỹ thuật viên phụ trách phiếu bảo hành.",
        "Khối \"Việc cần chú ý\" chỉ liệt kê dữ liệu thật của phiếu, không tự đặt ngưỡng cảnh báo.",
    ],
    ROLE_RECEPTIONIST: [
        "Bước cuối (xác nhận trả máy) là việc tại quầy: Tiếp nhận hoặc Quản lý thực hiện.",
        "Máy đang kiểm tra/sửa chữa thuộc phòng kỹ thuật — Tiếp nhận theo dõi để trả lời khách.",
        "Không ghi chẩn đoán, nội dung sửa chữa hoặc tự duyệt từ chối.",
    ],
    ROLE_TECHNICIAN: [
        "Kỹ thuật viên chỉ thao tác trên các phiếu được phân công cho mình.",
        "Kiểm tra → Sửa chữa: Bắt buộc ghi chẩn đoán và xác định đủ điều kiện bảo hành.",
        "Sửa chữa → Hoàn tất: Bắt buộc ghi nội dung sửa và xác nhận kết quả kiểm tra đạt yêu cầu.",
        "Kỹ thuật viên không tự duyệt từ chối hoặc trả máy: nếu không đủ điều kiện, ghi đề xuất từ chối để Quản lý duyệt.",
    ],
}


# =====================================================================
# Truy vấn dùng chung
# =====================================================================
def _resolve_scope(requested: Optional[str]) -> str:
    """Chuẩn hoá tham số `scope` của API (giá trị lạ -> dùng mặc định theo vai trò)."""
    value = str(requested or SCOPE_DEFAULT).upper()
    return value if value in VALID_SCOPES else SCOPE_DEFAULT


def _query_tickets(
    db: Session,
    statuses: List[str],
    current_user: Optional[User] = None,
    scope: Optional[str] = None,
    mine_user_id: Optional[int] = None,
    limit: Optional[int] = None,
) -> List[WarrantyTicket]:
    """
    Lấy phiếu theo danh sách trạng thái; lọc ở tầng SQL theo đúng vai trò và trung tâm bảo hành
    để số liệu và danh sách luôn khớp nhau 100%.
    """
    query = db.query(WarrantyTicket).filter(WarrantyTicket.status.in_(list(statuses)))
    query = crud_tickets.apply_ticket_scope_filter(
        query,
        current_user=current_user,
        scope=scope,
        mine_user_id=mine_user_id,
    )
    query = query.order_by(WarrantyTicket.id.desc())
    if limit is not None:
        query = query.limit(int(limit))
    return query.all()


def _count_tickets(
    db: Session,
    statuses: List[str],
    current_user: Optional[User] = None,
    scope: Optional[str] = None,
    mine_user_id: Optional[int] = None,
) -> int:
    """Đếm phiếu theo trạng thái (cùng điều kiện lọc với `_query_tickets`)."""
    query = db.query(func.count(WarrantyTicket.id)).filter(
        WarrantyTicket.status.in_(list(statuses))
    )
    query = crud_tickets.apply_ticket_scope_filter(
        query,
        current_user=current_user,
        scope=scope,
        mine_user_id=mine_user_id,
    )
    return int(query.scalar() or 0)


def _status_scope_map(role: str) -> Dict[str, str]:
    """
    Phạm vi mặc định của từng trạng thái theo vai trò (dùng cho thẻ số liệu).

    Ví dụ kỹ thuật viên: phiếu "chờ kiểm tra" là việc chung của phòng kỹ thuật
    (máy đã tiếp nhận, chưa ai nhận), còn phiếu đang kiểm tra/sửa chữa là việc
    của chính người đang phụ trách.
    """
    mapping: Dict[str, str] = {}
    for group in WORK_GROUPS.get(role, []):
        for status in group["statuses"]:
            mapping.setdefault(status, group["scope"])
    return mapping


def _workflow_order(status: str, order: List[str]) -> int:
    """Vị trí ưu tiên của một trạng thái trong danh sách việc cần làm."""
    try:
        return order.index(status)
    except ValueError:
        return len(order)


def _sort_for_work(rows: List[Dict[str, Any]], order: List[str]) -> List[Dict[str, Any]]:
    """Sắp phiếu theo thứ tự nghiệp vụ của vai trò, cùng bước thì phiếu mới lên trước."""
    return sorted(rows, key=lambda row: (_workflow_order(row.get("status", ""), order), -int(row.get("id", 0))))


# =====================================================================
# KHỐI "VIỆC CẦN CHÚ Ý" (Quản lý)
# ---------------------------------------------------------------------
# Chỉ dùng dữ liệu THẬT của phiếu để giải thích vì sao cần chú ý:
#   * RECEIVED       : máy đã tiếp nhận nhưng chưa chuyển vào phòng kiểm tra
#   * INSPECTING     : chưa có kết luận chẩn đoán của kỹ thuật viên
#   * REPAIRING      : chưa cập nhật nội dung đã kiểm tra/sửa chữa
#   * WAITING_RETURN : máy đã sửa xong, đang chờ khách tới nhận
# Số ngày kể từ lần cập nhật gần nhất được nêu như DỮ LIỆU, không phải
# một ngưỡng "quá lâu" do hệ thống tự đặt.
# =====================================================================
def _attention_reasons(ticket: WarrantyTicket) -> List[str]:
    reasons: List[str] = []
    if ticket.status == "RECEIVED":
        if not ticket.assigned_technician_id:
            reasons.append("Máy đã tiếp nhận nhưng chưa phân công KTV phụ trách")
        else:
            reasons.append("Máy đã tiếp nhận, chưa bắt đầu kiểm tra")
    elif ticket.status == "INSPECTING":
        if (ticket.rejection_proposal_note or "").strip():
            reasons.append(f"KTV đề xuất từ chối: {ticket.rejection_proposal_note}")
        elif not (ticket.diagnosis_note or "").strip():
            reasons.append("Chưa có kết luận chẩn đoán của KTV")
        elif ticket.is_warranty_eligible is None:
            reasons.append("Chưa xác nhận điều kiện bảo hành")
    elif ticket.status == "REPAIRING":
        if not (ticket.repair_content or "").strip():
            reasons.append("Chưa cập nhật nội dung sửa chữa")
        elif not ticket.repair_test_passed:
            reasons.append("Chưa kiểm tra sau sửa đạt yêu cầu")
    elif ticket.status == "COMPLETED":
        reasons.append("Máy đã sửa xong đạt yêu cầu, đang chờ khách tới nhận")
    elif ticket.status == "REJECTED":
        reasons.append("Đã từ chối bảo hành, đang chờ trả lại máy cho khách")
    return reasons


def build_attention(
    db: Session,
    tickets: List[WarrantyTicket],
    current_user: User,
    order: List[str],
) -> List[Dict[str, Any]]:
    """Danh sách phiếu cần quản lý chú ý (kèm lý do + số ngày chưa cập nhật)."""
    if not tickets:
        return []
    summaries = {
        row["id"]: row
        for row in ticket_view.build_ticket_summaries(db, tickets, current_user=current_user)
    }
    now = datetime.utcnow()
    items: List[Dict[str, Any]] = []
    for ticket in tickets:
        reasons = _attention_reasons(ticket)
        if not reasons:
            continue
        history = list(ticket.status_history or [])
        last_at = history[-1].created_at if history else ticket.created_at
        days = (now - last_at).days if last_at else None
        if days and days > 0:
            reasons.append(f"đã {days} ngày kể từ lần cập nhật gần nhất")
        row = summaries.get(ticket.id, {})
        items.append(
            {
                "ticket_id": ticket.id,
                "ticket_code": ticket.ticket_code,
                "status": ticket.status,
                "status_label": TICKET_STATUS_LABELS.get(ticket.status, ticket.status),
                "reason": " • ".join(reasons),
                "days_since_update": days,
                "serial_number": row.get("serial_number"),
                "product_name": row.get("product_name"),
                "customer_name": row.get("customer_name"),
                "handler_name": row.get("handler_name"),
                "created_at": ticket.created_at,
            }
        )
    items.sort(
        key=lambda item: (
            _workflow_order(item["status"], order),
            -(item["days_since_update"] or 0),
            -int(item["ticket_id"]),
        )
    )
    return items[:ATTENTION_LIMIT]


def build_cards(
    role: str,
    counts_active: Dict[str, int],
    scope_label: str,
) -> List[Dict[str, Any]]:
    """
    4 thẻ số liệu chuẩn theo yêu cầu:
    - Tổng phiếu
    - Đang xử lý = Tiếp nhận + Kiểm tra + Sửa chữa
    - Chờ trả máy = Hoàn tất + Từ chối
    - Đã trả máy
    Trong cùng phạm vi, Tổng phiếu luôn bằng tổng 3 nhóm còn lại 100%.
    """
    rec = int(counts_active.get("RECEIVED", 0))
    insp = int(counts_active.get("INSPECTING", 0))
    rep = int(counts_active.get("REPAIRING", 0))
    comp = int(counts_active.get("COMPLETED", 0))
    rej = int(counts_active.get("REJECTED", 0))
    ret = int(counts_active.get("RETURNED", 0))

    in_progress = rec + insp + rep
    waiting_return = comp + rej
    returned = ret
    total = in_progress + waiting_return + returned

    return [
        {
            "key": "TOTAL",
            "label": "Tổng phiếu",
            "count": total,
            "description": f"Tất cả phiếu ({scope_label})",
            "tone": "indigo",
            "status": "ALL",
            "icon": "files",
        },
        {
            "key": "IN_PROGRESS",
            "label": "Đang xử lý",
            "count": in_progress,
            "description": f"Tiếp nhận: {rec} • Kiểm tra: {insp} • Sửa: {rep}",
            "tone": "blue",
            "status": "PROCESSING",
            "icon": "hammer",
        },
        {
            "key": "WAITING_RETURN",
            "label": "Chờ trả máy",
            "count": waiting_return,
            "description": f"Hoàn tất: {comp} • Từ chối: {rej}",
            "tone": "amber",
            "status": "WAITING_RETURN",
            "icon": "clock",
        },
        {
            "key": "RETURNED",
            "label": "Đã trả máy",
            "count": returned,
            "description": "Đã bàn giao cho khách và đóng phiếu",
            "tone": "emerald",
            "status": "RETURNED",
            "icon": "check-circle-2",
        },
    ]


def build_quick_actions(role: str, current_user: User) -> List[Dict[str, Any]]:
    """Thao tác nhanh theo vai trò (đã lọc theo quyền thật của tài khoản)."""
    actions: List[Dict[str, Any]] = []
    for action in QUICK_ACTIONS.get(role, []):
        if action["key"] == "receive" and not has_permission(current_user, PERM_TICKET_CREATE):
            continue
        if action["key"] == "accounts" and not has_permission(current_user, PERM_USER_VIEW):
            continue
        if action["key"] == "waiting_return" and not has_permission(current_user, PERM_TICKET_HANDOVER):
            continue
        actions.append(dict(action))
    return actions


def build_role_notes(role: str, current_user: User) -> List[str]:
    """Ghi chú nghiệp vụ: nói rõ việc nào của vai trò nào để nhân viên biết bàn cho ai."""
    notes = list(ROLE_NOTES.get(role, []))
    if role == ROLE_TECHNICIAN and not has_permission(current_user, PERM_TICKET_HANDOVER):
        notes.append("Bạn không có quyền xác nhận đã trả máy — bước này thuộc quầy tiếp nhận/quản lý.")
    if role == ROLE_RECEPTIONIST and has_permission(current_user, PERM_TICKET_CREATE):
        notes.append("Bạn có thể tiếp nhận máy mới trực tiếp từ bảng điều khiển (nút \"Tiếp nhận máy mới\").")
    return notes


def build_workboard(
    db: Session, current_user: User, scope: Optional[str] = None
) -> Dict[str, Any]:
    """
    Dựng toàn bộ dữ liệu bảng điều khiển cho vai trò của `current_user`.

    Chỉ ĐỌC dữ liệu, không thay đổi nghiệp vụ phiếu: mọi số liệu đều tính từ
    trạng thái + lịch sử thật trong CSDL theo đúng phân quyền vai trò và trung tâm.
    """
    role = current_user.role or ""
    layout = ROLE_LAYOUT.get(role, ROLE_LAYOUT[ROLE_RECEPTIONIST])
    resolved_scope = _resolve_scope(scope)
    focus_order = list(layout["focus_order"])

    # 1. Xác định phạm vi đang xem
    if resolved_scope == SCOPE_MINE:
        active_scope = SCOPE_MINE
    elif resolved_scope == SCOPE_ALL:
        active_scope = SCOPE_ALL
    else:  # DEFAULT
        active_scope = SCOPE_ALL if role == ROLE_MANAGER else SCOPE_MINE

    if active_scope == SCOPE_MINE:
        if role == ROLE_RECEPTIONIST:
            scope_label = "Việc tại quầy"
        elif role == ROLE_TECHNICIAN:
            scope_label = "Phiếu được giao cho tôi"
        else:
            scope_label = "Toàn trung tâm"
    else:
        scope_label = "Toàn trung tâm"

    counts_active = crud_tickets.count_tickets_by_status(
        db,
        current_user=current_user,
        scope=active_scope,
    )

    # 2. Nhóm công việc (theo đúng vai trò và phạm vi)
    groups: List[Dict[str, Any]] = []
    for definition in WORK_GROUPS.get(role, []):
        group_scope = definition["scope"] if resolved_scope == SCOPE_DEFAULT else resolved_scope
        statuses = list(definition["statuses"])
        group_tickets = _query_tickets(
            db,
            statuses,
            current_user=current_user,
            scope=group_scope,
            limit=GROUP_ITEM_LIMIT,
        )
        count = _count_tickets(
            db,
            statuses,
            current_user=current_user,
            scope=group_scope,
        )
        groups.append(
            {
                "key": definition["key"],
                "label": definition["label"],
                "description": definition["description"],
                "count": count,
                "status_filter": ",".join(statuses),
                "statuses": statuses,
                "scope": group_scope,
                "scope_label": (
                    "Việc tại quầy" if role == ROLE_RECEPTIONIST and group_scope == SCOPE_MINE
                    else ("Phiếu được giao" if role == ROLE_TECHNICIAN and group_scope == SCOPE_MINE else "Toàn trung tâm")
                ),
                "tone": STATUS_TONES.get(statuses[0], "slate"),
                "action_target": definition["action_target"],
                "action_label": definition["action_label"],
                "items": ticket_view.build_ticket_summaries(
                    db, group_tickets, current_user=current_user
                ),
            }
        )

    # 3. Việc cần làm ngay
    status_scopes = _status_scope_map(role)
    focus: List[Dict[str, Any]] = []
    for status_code in focus_order:
        resolved = (
            resolved_scope
            if resolved_scope != SCOPE_DEFAULT
            else status_scopes.get(status_code, SCOPE_ALL)
        )
        tickets = _query_tickets(
            db,
            [status_code],
            current_user=current_user,
            scope=resolved,
            limit=FOCUS_LIMIT,
        )
        focus.extend(
            ticket_view.build_ticket_summaries(db, tickets, current_user=current_user)
        )
    focus = _sort_for_work(focus, focus_order)[:FOCUS_LIMIT]

    # 4. Phiếu đang xử lý + phiếu của tôi (lấy trọn bộ để phân trang / lọc chính xác)
    my_raw_tickets = crud_tickets.get_warranty_tickets(
        db,
        current_user=current_user,
        scope=SCOPE_MINE,
        limit=100,
    )
    my_tickets = _sort_for_work(
        ticket_view.build_ticket_summaries(db, my_raw_tickets, current_user=current_user),
        focus_order,
    )

    all_raw_tickets = crud_tickets.get_warranty_tickets(
        db,
        current_user=current_user,
        scope=SCOPE_ALL,
        limit=100,
    )
    active_tickets = _sort_for_work(
        ticket_view.build_ticket_summaries(db, all_raw_tickets, current_user=current_user),
        focus_order,
    )

    # 5. Việc cần chú ý (Quản lý)
    attention: List[Dict[str, Any]] = []
    if layout["show_attention"]:
        attention = build_attention(
            db,
            _query_tickets(
                db,
                list(OPEN_TICKET_STATUSES),
                current_user=current_user,
                scope=SCOPE_ALL,
            ),
            current_user,
            focus_order,
        )

    cards = build_cards(role, counts_active, scope_label)

    rec = int(counts_active.get("RECEIVED", 0))
    insp = int(counts_active.get("INSPECTING", 0))
    rep = int(counts_active.get("REPAIRING", 0))
    comp = int(counts_active.get("COMPLETED", 0))
    rej = int(counts_active.get("REJECTED", 0))
    ret = int(counts_active.get("RETURNED", 0))

    in_progress = rec + insp + rep
    waiting_return = comp + rej
    returned = ret
    total_tickets = in_progress + waiting_return + returned

    totals = {
        **counts_active,
        "total_tickets": total_tickets,
        "in_progress": in_progress,
        "waiting_return": waiting_return,
        "returned": returned,
        "customers": int(db.query(func.count(Customer.id)).scalar() or 0),
        "devices": int(db.query(func.count(ProductInstance.id)).scalar() or 0),
    }

    return {
        "role": role,
        "role_label": ROLE_LABELS_VN.get(role, role),
        "title": layout["title"],
        "subtitle": layout["subtitle"],
        "scope": active_scope,
        "scope_label": scope_label,
        "generated_at": datetime.utcnow(),
        "cards": cards,
        "groups": groups,
        "focus": focus,
        "attention": attention,
        "active_tickets": active_tickets,
        "my_tickets": my_tickets,
        "table_title": layout["table_title"],
        "quick_actions": build_quick_actions(role, current_user),
        "totals": totals,
        "notes": build_role_notes(role, current_user),
    }
