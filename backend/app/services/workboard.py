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

from sqlalchemy import func
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
    "WAITING_RETURN": "cyan",
    "COMPLETED": "emerald",
    "REJECTED": "rose",
}

# ------------------------------ Thẻ số liệu -------------------------------
CARD_DEFS: Dict[str, Dict[str, str]] = {
    "TOTAL": {
        "label": "Tổng phiếu",
        "description": "Tất cả phiếu bảo hành của trung tâm",
        "tone": "slate",
    },
    "RECEIVED": {
        "label": "Mới tiếp nhận",
        "description": "Máy vừa nhận tại quầy, chưa chuyển kiểm tra",
        "tone": STATUS_TONES["RECEIVED"],
    },
    "INSPECTING": {
        "label": "Đang kiểm tra",
        "description": "Kỹ thuật viên đang xác định nguyên nhân",
        "tone": STATUS_TONES["INSPECTING"],
    },
    "REPAIRING": {
        "label": "Đang sửa chữa",
        "description": "Máy đang nằm trên bàn sửa chữa",
        "tone": STATUS_TONES["REPAIRING"],
    },
    "WAITING_RETURN": {
        "label": "Chờ trả máy",
        "description": "Đã sửa xong, chờ khách tới nhận",
        "tone": STATUS_TONES["WAITING_RETURN"],
    },
    "COMPLETED": {
        "label": "Đã hoàn tất",
        "description": "Đã bàn giao máy cho khách",
        "tone": STATUS_TONES["COMPLETED"],
    },
    "REJECTED": {
        "label": "Từ chối bảo hành",
        "description": "Không thuộc phạm vi bảo hành",
        "tone": STATUS_TONES["REJECTED"],
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
# `scope`: ALL  = việc chung của trung tâm (máy đang chờ ở quầy/bàn kỹ thuật,
#                bất kỳ ai đúng vai trò đều có thể nhận)
#          MINE = việc mà chính người đang đăng nhập đang phụ trách
# `action_target` / `action_label`: câu chữ nút hành động theo VAI TRÒ cho các
# phiếu trong nhóm (hành động thật vẫn do backend kiểm tra quyền khi gọi API).
WORK_GROUPS: Dict[str, List[Dict[str, Any]]] = {
    ROLE_MANAGER: [
        {
            "key": "received",
            "label": "Mới tiếp nhận",
            "statuses": ["RECEIVED"],
            "scope": "ALL",
            "description": "Phiếu mới tại quầy, cần chuyển kỹ thuật kiểm tra.",
            "action_target": "INSPECTING",
            "action_label": "Chuyển sang kiểm tra",
        },
        {
            "key": "inspecting",
            "label": "Đang kiểm tra",
            "statuses": ["INSPECTING"],
            "scope": "ALL",
            "description": "Kỹ thuật viên đang xác định nguyên nhân lỗi.",
            "action_target": None,
            "action_label": "Xem tiến độ",
        },
        {
            "key": "repairing",
            "label": "Đang sửa chữa",
            "statuses": ["REPAIRING"],
            "scope": "ALL",
            "description": "Máy đang sửa; theo dõi tiến độ và linh kiện thay thế.",
            "action_target": None,
            "action_label": "Xem tiến độ",
        },
        {
            "key": "waiting_return",
            "label": "Chờ trả máy",
            "statuses": ["WAITING_RETURN"],
            "scope": "ALL",
            "description": "Máy đã sửa xong, đang chờ khách tới nhận.",
            "action_target": "COMPLETED",
            "action_label": "Xác nhận đã trả máy",
        },
        {
            "key": "completed",
            "label": "Đã hoàn tất",
            "statuses": ["COMPLETED"],
            "scope": "ALL",
            "description": "Phiếu đã bàn giao xong cho khách.",
            "action_target": None,
            "action_label": "Xem phiếu",
        },
    ],
    ROLE_RECEPTIONIST: [
        {
            "key": "to_receive",
            "label": "Cần tiếp nhận",
            "statuses": ["RECEIVED"],
            "scope": "ALL",
            "description": "Máy đang ở quầy: chuyển vào phòng kiểm tra.",
            "action_target": "INSPECTING",
            "action_label": "Chuyển vào phòng kiểm tra",
        },
        {
            "key": "processing",
            "label": "Đang xử lý",
            "statuses": ["INSPECTING", "REPAIRING"],
            "scope": "ALL",
            "description": "Máy đang được kỹ thuật kiểm tra/sửa — dùng khi khách gọi hỏi.",
            "action_target": None,
            "action_label": "Xem tiến độ để trả lời khách",
        },
        {
            "key": "waiting_return",
            "label": "Chờ trả máy",
            "statuses": ["WAITING_RETURN"],
            "scope": "ALL",
            "description": "Gọi khách tới nhận máy rồi xác nhận đã trả máy.",
            "action_target": "COMPLETED",
            "action_label": "Xác nhận đã trả máy",
        },
    ],
    ROLE_TECHNICIAN: [
        {
            "key": "waiting_inspect",
            "label": "Chờ kiểm tra",
            "statuses": ["RECEIVED"],
            "scope": "ALL",
            "description": "Máy đã tiếp nhận tại quầy, cần đưa vào bàn kiểm tra.",
            "action_target": "INSPECTING",
            "action_label": "Bắt đầu kiểm tra",
        },
        {
            "key": "inspecting",
            "label": "Đang kiểm tra",
            "statuses": ["INSPECTING"],
            "scope": "MINE",
            "description": "Ghi kết luận chẩn đoán rồi chuyển sang sửa chữa.",
            "action_target": "REPAIRING",
            "action_label": "Cập nhật kết quả kiểm tra",
        },
        {
            "key": "repairing",
            "label": "Đang sửa chữa",
            "statuses": ["REPAIRING"],
            "scope": "MINE",
            "description": "Sửa xong thì chuyển phiếu sang \"Chờ trả máy\".",
            "action_target": "WAITING_RETURN",
            "action_label": "Cập nhật sửa chữa",
        },
        {
            "key": "waiting_profile",
            "label": "Chờ hoàn thiện hồ sơ",
            "statuses": ["WAITING_RETURN"],
            "scope": "MINE",
            "description": "Đã sửa xong — máy chờ khách nhận, quầy sẽ bàn giao.",
            "action_target": None,
            "action_label": "Xem thông tin trả máy",
        },
    ],
}

# ---------------------- Bố cục bảng điều khiển theo vai trò ----------------
# `focus_order`: thứ tự "Việc cần làm" theo nghiệp vụ của từng vai trò.
# `show_attention`: chỉ Quản lý có khối "Việc cần chú ý".
ROLE_LAYOUT: Dict[str, Dict[str, Any]] = {
    ROLE_MANAGER: {
        "title": "Tổng quan trung tâm",
        "subtitle": "Toàn bộ tình hình tiếp nhận và xử lý bảo hành trong ngày.",
        "cards": [
            "TOTAL",
            "RECEIVED",
            "INSPECTING",
            "REPAIRING",
            "WAITING_RETURN",
            "COMPLETED",
            "REJECTED",
            "CUSTOMERS",
            "DEVICES",
        ],
        "focus_order": ["RECEIVED", "REPAIRING", "WAITING_RETURN", "INSPECTING"],
        "show_attention": True,
        "table_title": "Phiếu đang xử lý (toàn hệ thống)",
        "table_scope": SCOPE_ALL,
    },
    ROLE_RECEPTIONIST: {
        "title": "Việc tại quầy tiếp nhận",
        "subtitle": "Những phiếu cần bạn xử lý ngay: tiếp nhận máy và trả máy cho khách.",
        "cards": ["RECEIVED", "INSPECTING", "REPAIRING", "WAITING_RETURN", "COMPLETED"],
        "focus_order": ["RECEIVED", "WAITING_RETURN", "INSPECTING", "REPAIRING"],
        "show_attention": False,
        "table_title": "Phiếu tôi đang phụ trách",
        "table_scope": SCOPE_DEFAULT,
    },
    ROLE_TECHNICIAN: {
        "title": "Công việc kỹ thuật",
        "subtitle": "Máy cần kiểm tra, đang sửa chữa và các phiếu cần cập nhật kết quả.",
        "cards": ["RECEIVED", "INSPECTING", "REPAIRING", "WAITING_RETURN"],
        "focus_order": ["RECEIVED", "REPAIRING", "INSPECTING", "WAITING_RETURN"],
        "show_attention": False,
        "table_title": "Phiếu tôi đang xử lý",
        "table_scope": SCOPE_DEFAULT,
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
            "description": "Máy đã sửa xong, cần gọi khách tới nhận",
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
            "label": "Phiếu chờ kiểm tra",
            "description": "Máy vừa tiếp nhận, cần bắt đầu kiểm tra",
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
ROLE_NOTES: Dict[str, List[str]] = {
    ROLE_MANAGER: [
        "Chỉ Quản lý được xác nhận TỪ CHỐI bảo hành (quyết định thuộc quản lý).",
        "Khối \"Việc cần chú ý\" chỉ liệt kê dữ liệu thật của phiếu, không tự đặt ngưỡng cảnh báo.",
    ],
    ROLE_RECEPTIONIST: [
        "Bước cuối (xác nhận đã trả máy) là việc tại quầy: bạn hoặc quản lý thực hiện.",
        "Máy đang kiểm tra/sửa chữa thuộc phòng kỹ thuật — bạn theo dõi để trả lời khách.",
    ],
    ROLE_TECHNICIAN: [
        "Kỹ thuật viên không tự xác nhận trả máy: khi sửa xong hãy chuyển phiếu sang \"Chờ trả máy\" để quầy bàn giao.",
        "Kết luận chẩn đoán do bạn ghi; gợi ý của hệ thống chỉ là thông tin tham khảo.",
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
    mine_user_id: Optional[int] = None,
    limit: Optional[int] = None,
) -> List[WarrantyTicket]:
    """
    Lấy phiếu theo danh sách trạng thái; `mine_user_id` lọc ở tầng SQL
    (người xử lý gần nhất) để số liệu và danh sách luôn khớp nhau.
    """
    query = db.query(WarrantyTicket).filter(WarrantyTicket.status.in_(list(statuses)))
    if mine_user_id is not None:
        handler = crud_tickets.last_handler_subquery(db)
        query = query.outerjoin(handler, handler.c.ticket_id == WarrantyTicket.id).filter(
            func.coalesce(handler.c.changed_by, WarrantyTicket.created_by) == mine_user_id
        )
    query = query.order_by(WarrantyTicket.id.desc())
    if limit is not None:
        query = query.limit(int(limit))
    return query.all()


def _count_tickets(db: Session, statuses: List[str], mine_user_id: Optional[int] = None) -> int:
    """Đếm phiếu theo trạng thái (cùng điều kiện lọc với `_query_tickets`)."""
    query = db.query(func.count(WarrantyTicket.id)).filter(
        WarrantyTicket.status.in_(list(statuses))
    )
    if mine_user_id is not None:
        handler = crud_tickets.last_handler_subquery(db)
        query = query.outerjoin(handler, handler.c.ticket_id == WarrantyTicket.id).filter(
            func.coalesce(handler.c.changed_by, WarrantyTicket.created_by) == mine_user_id
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
        reasons.append("Máy đã tiếp nhận nhưng chưa chuyển vào phòng kiểm tra")
    elif ticket.status == "INSPECTING":
        if not (ticket.diagnosis_note or "").strip():
            reasons.append("Chưa có kết luận chẩn đoán của kỹ thuật viên")
    elif ticket.status == "REPAIRING":
        if not (ticket.repair_content or "").strip():
            reasons.append("Chưa cập nhật nội dung đã kiểm tra / đã sửa chữa")
    elif ticket.status == "WAITING_RETURN":
        reasons.append("Máy đã sửa xong, đang chờ khách tới nhận")
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
    db: Session,
    role: str,
    counts_all: Dict[str, int],
    counts_mine: Dict[str, int],
    scope: str,
) -> List[Dict[str, Any]]:
    """
    Thẻ số liệu của bảng điều khiển theo vai trò.

    `scope = DEFAULT`: dùng phạm vi khai báo cho từng nhóm việc (việc chung của
    trung tâm hay việc của chính tôi). `scope = MINE/ALL`: áp cho mọi thẻ.
    """
    layout = ROLE_LAYOUT.get(role, ROLE_LAYOUT[ROLE_RECEPTIONIST])
    status_scopes = _status_scope_map(role)
    cards: List[Dict[str, Any]] = []
    for key in layout["cards"]:
        definition = CARD_DEFS.get(key)
        if definition is None:
            continue
        if key == "TOTAL":
            count = sum(counts_all.values())
        elif key == "CUSTOMERS":
            count = int(db.query(func.count(Customer.id)).scalar() or 0)
        elif key == "DEVICES":
            count = int(db.query(func.count(ProductInstance.id)).scalar() or 0)
        else:
            resolved = scope if scope != SCOPE_DEFAULT else status_scopes.get(key, SCOPE_ALL)
            source = counts_mine if resolved == SCOPE_MINE else counts_all
            count = int(source.get(key, 0))
        cards.append(
            {
                "key": key,
                "label": definition["label"],
                "count": count,
                "description": definition["description"],
                "tone": definition["tone"],
                "status": None if key in ("TOTAL", "CUSTOMERS", "DEVICES") else key,
            }
        )
    return cards


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
    trạng thái + lịch sử thật trong CSDL.
    """
    role = current_user.role or ""
    layout = ROLE_LAYOUT.get(role, ROLE_LAYOUT[ROLE_RECEPTIONIST])
    resolved_scope = _resolve_scope(scope)
    focus_order = list(layout["focus_order"])

    counts_all = crud_tickets.count_tickets_by_status(db)
    counts_mine = crud_tickets.count_tickets_by_status(db, mine_user_id=current_user.id)

    # ---------------- 1. Nhóm công việc (kèm phiếu cần xử lý) ----------------
    groups: List[Dict[str, Any]] = []
    for definition in WORK_GROUPS.get(role, []):
        group_scope = definition["scope"] if resolved_scope == SCOPE_DEFAULT else resolved_scope
        mine_user_id = current_user.id if group_scope == SCOPE_MINE else None
        statuses = list(definition["statuses"])
        count = _count_tickets(db, statuses, mine_user_id=mine_user_id)
        tickets = _query_tickets(
            db, statuses, mine_user_id=mine_user_id, limit=GROUP_ITEM_LIMIT
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
                "scope_label": "Việc của tôi" if group_scope == SCOPE_MINE else "Toàn trung tâm",
                "tone": STATUS_TONES.get(statuses[0], "slate"),
                "action_target": definition["action_target"],
                "action_label": definition["action_label"],
                "items": ticket_view.build_ticket_summaries(
                    db, tickets, current_user=current_user
                ),
            }
        )

    # ------------------------- 2. Việc cần làm ngay -------------------------
    status_scopes = _status_scope_map(role)
    focus: List[Dict[str, Any]] = []
    for status_code in focus_order:
        resolved = (
            resolved_scope
            if resolved_scope != SCOPE_DEFAULT
            else status_scopes.get(status_code, SCOPE_ALL)
        )
        mine_user_id = current_user.id if resolved == SCOPE_MINE else None
        tickets = _query_tickets(db, [status_code], mine_user_id=mine_user_id, limit=FOCUS_LIMIT)
        focus.extend(
            ticket_view.build_ticket_summaries(db, tickets, current_user=current_user)
        )
    focus = _sort_for_work(focus, focus_order)[:FOCUS_LIMIT]

    # ---------------- 3. Phiếu đang xử lý + phiếu của tôi -------------------
    active_tickets = _sort_for_work(
        ticket_view.build_ticket_summaries(
            db,
            _query_tickets(db, list(OPEN_TICKET_STATUSES), limit=TABLE_LIMIT * 2),
            current_user=current_user,
        ),
        focus_order,
    )[:TABLE_LIMIT]
    my_tickets = _sort_for_work(
        ticket_view.build_ticket_summaries(
            db,
            _query_tickets(
                db,
                list(OPEN_TICKET_STATUSES),
                mine_user_id=current_user.id,
                limit=TABLE_LIMIT * 2,
            ),
            current_user=current_user,
        ),
        focus_order,
    )[:TABLE_LIMIT]

    # --------------------- 4. Việc cần chú ý (Quản lý) ----------------------
    attention: List[Dict[str, Any]] = []
    if layout["show_attention"]:
        attention = build_attention(
            db,
            _query_tickets(db, list(OPEN_TICKET_STATUSES)),
            current_user,
            focus_order,
        )

    totals = dict(counts_all)
    totals["total_tickets"] = sum(counts_all.values())
    totals["my_total_tickets"] = sum(counts_mine.values())
    totals["customers"] = int(db.query(func.count(Customer.id)).scalar() or 0)
    totals["devices"] = int(db.query(func.count(ProductInstance.id)).scalar() or 0)

    return {
        "role": role,
        "role_label": ROLE_LABELS_VN.get(role, role),
        "title": layout["title"],
        "subtitle": layout["subtitle"],
        "scope": resolved_scope,
        "scope_label": {
            SCOPE_MINE: "Việc của tôi",
            SCOPE_ALL: "Toàn bộ phiếu",
        }.get(resolved_scope, "Theo vai trò"),
        "generated_at": datetime.utcnow(),
        "cards": build_cards(db, role, counts_all, counts_mine, resolved_scope),
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
