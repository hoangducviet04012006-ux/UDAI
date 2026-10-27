"""
=======================================================================
Đợt 7 - Xác thực (Authentication) & Phân quyền theo vai trò (RBAC)
=======================================================================
Mục tiêu: mọi API nghiệp vụ chỉ phục vụ người dùng ĐÃ ĐĂNG NHẬP và CÓ QUYỀN.
Ẩn/hiện menu trên giao diện chỉ là trải nghiệm; quyết định cuối cùng luôn ở backend.

Nguyên tắc bắt buộc (đã kiểm chứng bằng tests/test_auth_rbac.py):
    * Mật khẩu KHÔNG lưu dạng thô: chỉ lưu PBKDF2-HMAC-SHA256 + salt ngẫu nhiên
      (dùng thư viện chuẩn `hashlib`, không thêm dependency mới).
    * Token có chữ ký HMAC-SHA256 và hạn dùng; token KHÔNG chứa mật khẩu/hash.
    * Vai trò (role) LUÔN lấy từ token đã xác thực + bản ghi `users` trong CSDL,
      KHÔNG bao giờ lấy từ payload do frontend gửi lên.
    * 401 = chưa đăng nhập / token sai hoặc hết hạn / tài khoản bị vô hiệu hoá.
      403 = đã đăng nhập nhưng không đủ quyền với thao tác đang gọi.
    * Không tiết lộ chi tiết hệ thống (SQL, stack trace, hash, danh sách user) trong lỗi.

Định dạng token:  v1.<base64url(payload)>.<base64url(hmac_sha256)>
payload = {"sub": user_id, "usr": username, "rol": role, "iat": ..., "exp": ..., "jti": ...}
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User

# =====================================================================
# 1. Vai trò & nhãn tiếng Việt (dùng cho thông báo lỗi/thông tin phiên)
# =====================================================================
ROLE_MANAGER = "MANAGER"
ROLE_RECEPTIONIST = "RECEPTIONIST"
ROLE_TECHNICIAN = "TECHNICIAN"
ALL_ROLES: Tuple[str, ...] = (ROLE_MANAGER, ROLE_RECEPTIONIST, ROLE_TECHNICIAN)

ROLE_LABELS_VN: Dict[str, str] = {
    ROLE_MANAGER: "Quản lý",
    ROLE_RECEPTIONIST: "Nhân viên tiếp nhận",
    ROLE_TECHNICIAN: "Kỹ thuật viên",
}


def role_label_vn(role: Optional[str]) -> str:
    """Nhãn tiếng Việt của vai trò (dùng cho giao diện và thông báo)."""
    return ROLE_LABELS_VN.get(role or "", "Không xác định")


# =====================================================================
# 2. Danh mục quyền (permission) theo NGHIỆP VỤ, không theo tên API
# ---------------------------------------------------------------------
# Mỗi quyền gắn với một việc thật của trung tâm bảo hành, ví dụ:
#   ticket.create  = "Tiếp nhận máy và lập phiếu bảo hành"
#   ai.review      = "Xác nhận loại lỗi do AI gợi ý (human-in-the-loop)"
#   ticket.reject  = "Xác nhận TỪ CHỐI bảo hành" (quyết định thuộc quản lý)
# =====================================================================
PERM_DASHBOARD_VIEW = "dashboard.view"
PERM_LOOKUP_VIEW = "lookup.view"
PERM_TICKET_VIEW = "ticket.view"
PERM_TICKET_CREATE = "ticket.create"
PERM_TICKET_UPDATE_STATUS = "ticket.update_status"
PERM_TICKET_REJECT = "ticket.reject"
# --- Đợt hoàn thiện nghiệp vụ: tách quyền theo từng bước xử lý phiếu ---
# ticket.diagnose : ghi nhận CHẨN ĐOÁN (kết luận lỗi) - việc của kỹ thuật viên.
# ticket.repair   : ghi nhận NỘI DUNG SỬA CHỮA / linh kiện thay thế.
# ticket.handover : xác nhận ĐÃ TRẢ MÁY cho khách và đóng phiếu (việc ở quầy).
PERM_TICKET_DIAGNOSE = "ticket.diagnose"
PERM_TICKET_REPAIR = "ticket.repair"
PERM_TICKET_HANDOVER = "ticket.handover"
PERM_AI_VIEW = "ai.view"
PERM_AI_CLASSIFY = "ai.classify"
PERM_AI_REVIEW = "ai.review"
PERM_CUSTOMER_VIEW = "customer.view"
PERM_CUSTOMER_CREATE = "customer.create"
PERM_CUSTOMER_UPDATE = "customer.update"
PERM_CUSTOMER_DELETE = "customer.delete"
PERM_PRODUCT_VIEW = "product.view"
PERM_PRODUCT_MANAGE = "product.manage"
PERM_DEVICE_VIEW = "device.view"
PERM_DEVICE_MANAGE = "device.manage"
PERM_STAFF_VIEW = "staff.view"
PERM_USER_VIEW = "user.view"
PERM_USER_MANAGE = "user.manage"

# Quyền dùng chung cho CẢ 3 vai trò (mọi nhân viên đã đăng nhập đều cần để làm việc)
_COMMON_PERMISSIONS = frozenset(
    {
        PERM_DASHBOARD_VIEW,
        PERM_LOOKUP_VIEW,
        PERM_TICKET_VIEW,
        PERM_AI_VIEW,
        PERM_AI_CLASSIFY,
        PERM_CUSTOMER_VIEW,
        PERM_PRODUCT_VIEW,
        PERM_DEVICE_VIEW,
        PERM_STAFF_VIEW,
    }
)

ROLE_PERMISSIONS: Dict[str, frozenset] = {
    # QUẢN LÝ: toàn quyền nghiệp vụ + quản trị tài khoản nhân viên.
    ROLE_MANAGER: _COMMON_PERMISSIONS
    | frozenset(
        {
            PERM_TICKET_CREATE,
            PERM_TICKET_UPDATE_STATUS,
            PERM_TICKET_REJECT,
            PERM_TICKET_DIAGNOSE,
            PERM_TICKET_REPAIR,
            PERM_TICKET_HANDOVER,
            PERM_AI_REVIEW,
            PERM_CUSTOMER_CREATE,
            PERM_CUSTOMER_UPDATE,
            PERM_CUSTOMER_DELETE,
            PERM_PRODUCT_MANAGE,
            PERM_DEVICE_MANAGE,
            PERM_USER_VIEW,
            PERM_USER_MANAGE,
        }
    ),
    # NHÂN VIÊN TIẾP NHẬN: tiếp nhận máy, lập phiếu, chăm sóc khách, xác nhận gợi ý AI,
    # và xác nhận trả máy cho khách (việc tại quầy). KHÔNG ghi chẩn đoán/sửa chữa của kỹ thuật.
    ROLE_RECEPTIONIST: _COMMON_PERMISSIONS
    | frozenset(
        {
            PERM_TICKET_CREATE,
            PERM_TICKET_UPDATE_STATUS,
            PERM_TICKET_HANDOVER,
            PERM_AI_REVIEW,
            PERM_CUSTOMER_CREATE,
            PERM_CUSTOMER_UPDATE,
            PERM_DEVICE_MANAGE,
        }
    ),
    # KỸ THUẬT VIÊN: xử lý máy (kiểm tra -> chẩn đoán -> sửa chữa -> chờ trả máy);
    # KHÔNG tiếp nhận/xóa dữ liệu, KHÔNG quyết định từ chối bảo hành, KHÔNG trả máy cho khách.
    ROLE_TECHNICIAN: _COMMON_PERMISSIONS
    | frozenset({PERM_TICKET_UPDATE_STATUS, PERM_TICKET_DIAGNOSE, PERM_TICKET_REPAIR}),
}

# Vai trò được xác nhận kết quả AI (human-in-the-loop) - dùng chung với KT3.
ALLOWED_REVIEW_ROLES: Tuple[str, ...] = (ROLE_MANAGER, ROLE_RECEPTIONIST)


def permissions_for_role(role: Optional[str]) -> List[str]:
    """Danh sách quyền của một vai trò (rỗng nếu vai trò không hợp lệ)."""
    return sorted(ROLE_PERMISSIONS.get(role or "", frozenset()))


def has_permission(user: Optional[User], permission: str) -> bool:
    """True nếu tài khoản đang hoạt động và vai trò của tài khoản có quyền này."""
    if not user or not getattr(user, "active", False):
        return False
    return permission in ROLE_PERMISSIONS.get(user.role or "", frozenset())


# =====================================================================
# 3b. MENU THEO VAI TRÒ (Đợt "Màn hình công việc theo vai trò")
# ---------------------------------------------------------------------
# Menu KHÔNG do giao diện tự quyết: backend trả về đúng những mục mà vai trò
# đang đăng nhập cần cho ca làm việc, kèm nhóm hiển thị:
#   * work      - việc hằng ngày (Tổng quan, Phiếu bảo hành, Tra cứu, Hỗ trợ xác định lỗi)
#   * reference - sổ/danh mục tra cứu nội bộ (Khách hàng, Danh mục máy, Máy đã đăng ký)
#   * admin     - quản trị tài khoản nhân viên (chỉ Quản lý)
# Kỹ thuật viên VẪN có quyền đọc sổ khách hàng / danh mục máy / máy đã đăng ký
# (đã kiểm chứng ở tests/test_auth_rbac.py), nhưng các mục đó được xếp vào nhóm
# "Tra cứu nội bộ" để menu chính chỉ còn việc phục vụ trực tiếp kỹ thuật.
# Việc ẩn/hiện menu chỉ là trải nghiệm: mọi quyền vẫn được backend kiểm tra (403).
# =====================================================================
MENU_WORK = "work"
MENU_REFERENCE = "reference"
MENU_ADMIN = "admin"

MENU_GROUP_LABELS_VN: Dict[str, str] = {
    MENU_REFERENCE: "Tra cứu nội bộ",
    MENU_ADMIN: "Quản trị",
}

# Danh mục mục menu của hệ thống (một màn hình = một mục).
MENU_DEFINITIONS: List[Dict[str, str]] = [
    {
        "tab": "dashboard",
        "label": "Tổng quan",
        "icon": "layout-dashboard",
        "permission": PERM_DASHBOARD_VIEW,
        "group": MENU_WORK,
        "hint": "Việc cần làm hôm nay: số lượng theo từng bước và phiếu cần xử lý ngay",
    },
    {
        "tab": "tickets",
        "label": "Phiếu bảo hành",
        "icon": "file-text",
        "permission": PERM_TICKET_VIEW,
        "group": MENU_WORK,
        "hint": "Tiếp nhận máy mới, tra cứu phiếu và cập nhật tiến độ xử lý",
    },
    {
        "tab": "lookup",
        "label": "Tra cứu bảo hành",
        "icon": "search-check",
        "permission": PERM_LOOKUP_VIEW,
        "group": MENU_WORK,
        "hint": "Khách gọi tới: tra theo số sê-ri hoặc mã phiếu",
    },
    {
        "tab": "ai",
        "label": "Hỗ trợ xác định lỗi",
        "icon": "wand-2",
        "permission": PERM_AI_VIEW,
        "group": MENU_WORK,
        "hint": "Hệ thống gợi ý loại lỗi; nhân viên có quyền xác nhận trước khi ghi vào phiếu",
    },
    {
        "tab": "customers",
        "label": "Khách hàng",
        "icon": "users",
        "permission": PERM_CUSTOMER_VIEW,
        "group": MENU_WORK,
        "hint": "Sổ khách hàng: xem ai đang gửi máy, sửa thông tin liên hệ",
    },
    {
        "tab": "products",
        "label": "Danh mục máy",
        "icon": "package",
        "permission": PERM_PRODUCT_VIEW,
        "group": MENU_WORK,
        "hint": "Danh mục dòng máy và thời hạn bảo hành mặc định",
    },
    {
        "tab": "devices",
        "label": "Máy đã đăng ký",
        "icon": "hard-drive",
        "permission": PERM_DEVICE_VIEW,
        "group": MENU_WORK,
        "hint": "Máy theo số sê-ri: chủ sở hữu, hạn bảo hành, phiếu đã có",
    },
    {
        "tab": "accounts",
        "label": "Tài khoản nhân viên",
        "icon": "shield-user",
        "permission": PERM_USER_VIEW,
        "group": MENU_ADMIN,
        "hint": "Danh sách tài khoản và vai trò làm việc (chỉ Quản lý)",
    },
]

# Với vai trò nào thì (những) màn hình nào được xếp lại vào nhóm nào.
MENU_GROUP_OVERRIDES: Dict[str, Dict[str, str]] = {
    ROLE_TECHNICIAN: {
        "customers": MENU_REFERENCE,
        "products": MENU_REFERENCE,
        "devices": MENU_REFERENCE,
    },
}


def navigation_for_role(role: Optional[str]) -> List[Dict[str, str]]:
    """
    Menu của một vai trò (đã lọc theo quyền) - giao diện vẽ lại đúng danh sách này.

    Trả về mỗi mục: tab, label, icon, group, group_label, hint, permission.
    """
    granted = ROLE_PERMISSIONS.get(role or "", frozenset())
    items: List[Dict[str, str]] = []
    for menu in MENU_DEFINITIONS:
        if menu["permission"] not in granted:
            continue
        group = MENU_GROUP_OVERRIDES.get(role or "", {}).get(menu["tab"], menu["group"])
        items.append(
            {
                "tab": menu["tab"],
                "label": menu["label"],
                "icon": menu["icon"],
                "group": group,
                "group_label": MENU_GROUP_LABELS_VN.get(group, ""),
                "hint": menu["hint"],
                "permission": menu["permission"],
            }
        )
    return items


# =====================================================================
# 3. Băm & kiểm tra mật khẩu (PBKDF2-HMAC-SHA256, thư viện chuẩn)
# ---------------------------------------------------------------------
# Định dạng lưu trong users.password_hash:
#   pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
# => Có salt riêng cho từng tài khoản, không thể so sánh hash giữa các user,
#    không thể đảo ngược, không lưu mật khẩu gốc ở bất kỳ đâu.
# =====================================================================
PASSWORD_HASH_PREFIX = "pbkdf2_sha256"
# Giá trị placeholder cũ trong tests/seed_data.py (không phải hash thật) - cần nâng cấp.
LEGACY_PASSWORD_HASH_PLACEHOLDER = "pbkdf2:sha256:dummyhash123"

MIN_PASSWORD_LENGTH = 8


def hash_password(password: str, iterations: Optional[int] = None) -> str:
    """Băm mật khẩu thành chuỗi an toàn để lưu CSDL (KHÔNG lưu mật khẩu thô)."""
    raw = (password or "").encode("utf-8")
    rounds = int(iterations or settings.auth_pbkdf2_iterations)
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", raw, bytes.fromhex(salt), rounds, dklen=32)
    return f"{PASSWORD_HASH_PREFIX}${rounds}${salt}${digest.hex()}"


def is_legacy_hash(stored_hash: Optional[str]) -> bool:
    """True nếu giá trị đang lưu không phải hash PBKDF2 hợp lệ (ví dụ placeholder cũ)."""
    if not stored_hash:
        return True
    parts = stored_hash.split("$")
    if len(parts) != 4 or parts[0] != PASSWORD_HASH_PREFIX:
        return True
    try:
        int(parts[1])
        bytes.fromhex(parts[2])
        bytes.fromhex(parts[3])
    except ValueError:
        return True
    return False


def verify_password(password: str, stored_hash: Optional[str]) -> bool:
    """So khớp mật khẩu với hash đã lưu bằng phép so sánh chống dò thời gian."""
    if not password or is_legacy_hash(stored_hash):
        return False
    _, rounds_txt, salt_hex, digest_hex = (stored_hash or "").split("$")
    try:
        expected = bytes.fromhex(digest_hex)
        rounds = int(rounds_txt)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), rounds, dklen=len(expected)
    )
    return hmac.compare_digest(candidate, expected)


# =====================================================================
# 4. Token phiên đăng nhập (HMAC-SHA256, có hạn dùng, thu hồi được khi đăng xuất)
# ---------------------------------------------------------------------
# Lưu ý kiến trúc: KHÔNG cần thêm bảng CSDL (giữ nguyên 16 bảng hiện có).
# Danh sách token đã thu hồi (logout) lưu trong bộ nhớ tiến trình - đủ cho mô hình
# chạy 1 tiến trình của đồ án; nếu triển khai nhiều worker thì chuyển sang Redis/DB.
# =====================================================================
TOKEN_PREFIX = "v1"
_BEARER_SCHEME = "bearer"

bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    description="Dán token nhận được từ POST /api/v1/auth/login (không cần gõ chữ 'Bearer').",
)

_REVOKED_TOKENS: Dict[str, int] = {}  # jti -> thời điểm hết hạn (epoch seconds)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(payload_b64: str) -> str:
    signature = hmac.new(
        settings.auth_secret_key.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).digest()
    return _b64url_encode(signature)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_access_token(user: User, ttl_minutes: Optional[int] = None) -> Dict[str, Any]:
    """Sinh token cho phiên đăng nhập (chỉ chứa định danh + vai trò, KHÔNG chứa mật khẩu)."""
    now = int(time.time())
    ttl = int(ttl_minutes or settings.auth_token_ttl_minutes)
    payload = {
        "sub": int(user.id),
        "usr": user.username,
        "rol": user.role,
        "iat": now,
        "exp": now + ttl * 60,
        "jti": secrets.token_hex(8),
    }
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return {
        "access_token": f"{TOKEN_PREFIX}.{payload_b64}.{_sign(payload_b64)}",
        "token_type": _BEARER_SCHEME,
        "expires_in": ttl * 60,
        "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(payload["exp"])),
    }


def _cleanup_revoked_tokens() -> None:
    now = int(time.time())
    for jti, exp in list(_REVOKED_TOKENS.items()):
        if exp <= now:
            _REVOKED_TOKENS.pop(jti, None)


def decode_access_token(token: Optional[str]) -> Dict[str, Any]:
    """Kiểm tra chữ ký + hạn dùng + trạng thái thu hồi của token. Sai -> HTTP 401."""
    if not token:
        raise _unauthorized("Bạn cần đăng nhập để sử dụng chức năng này.")
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != TOKEN_PREFIX:
        raise _unauthorized("Phiên đăng nhập không hợp lệ. Vui lòng đăng nhập lại.")
    payload_b64, signature = parts[1], parts[2]
    if not hmac.compare_digest(_sign(payload_b64), signature):
        raise _unauthorized("Phiên đăng nhập không hợp lệ. Vui lòng đăng nhập lại.")
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise _unauthorized("Phiên đăng nhập không hợp lệ. Vui lòng đăng nhập lại.")

    if int(payload.get("exp") or 0) <= int(time.time()):
        raise _unauthorized("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.")

    _cleanup_revoked_tokens()
    if payload.get("jti") in _REVOKED_TOKENS:
        raise _unauthorized("Phiên đăng nhập đã được đăng xuất. Vui lòng đăng nhập lại.")
    return payload


def revoke_token(token: Optional[str]) -> bool:
    """Thu hồi token khi người dùng đăng xuất (idempotent, không lộ thông tin)."""
    if not token:
        return False
    try:
        payload = decode_access_token(token)
    except HTTPException:
        return False
    _REVOKED_TOKENS[str(payload.get("jti"))] = int(payload.get("exp") or 0)
    return True


def reset_revoked_tokens() -> None:
    """Xoá danh sách token đã thu hồi (dùng cho kiểm thử tự động)."""
    _REVOKED_TOKENS.clear()


# =====================================================================
# 5. Nạp tài khoản từ token (dependency dùng chung cho MỌI API nghiệp vụ)
# =====================================================================
def load_user_from_token(token: Optional[str], db: Session) -> User:
    """
    Giải mã token -> nạp bản ghi người dùng MỚI NHẤT từ CSDL.

    Vai trò luôn đọc từ CSDL (nguồn duy nhất đáng tin): nếu quản lý đổi vai trò
    hoặc vô hiệu hoá tài khoản thì token cũ mất hiệu lực ngay, không cần đợi hết hạn.
    """
    payload = decode_access_token(token)
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user:
        raise _unauthorized("Phiên đăng nhập không còn hiệu lực. Vui lòng đăng nhập lại.")
    if not user.active:
        raise _unauthorized("Tài khoản đã bị vô hiệu hoá. Vui lòng liên hệ quản lý.")
    return user


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Dependency: trả về tài khoản đang đăng nhập, hoặc ném 401 nếu chưa đăng nhập."""
    token = credentials.credentials if credentials else None
    return load_user_from_token(token, db)


def get_raw_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[str]:
    """Dependency phụ: trả về token thô (dùng cho API đăng xuất)."""
    return credentials.credentials if credentials else None


def require_permissions(*required: str):
    """
    Dependency factory: bắt buộc đăng nhập VÀ có đủ mọi quyền trong `required`.

    Dùng cho các endpoint nhạy cảm:
        @router.post("/", dependencies=[Depends(require_permissions(PERM_X))])
    hoặc khi cần chính tài khoản đó:
        def handler(current_user: User = Depends(require_permissions(PERM_X))):
    """

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        granted = ROLE_PERMISSIONS.get(current_user.role or "", frozenset())
        missing = [perm for perm in required if perm not in granted]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Tài khoản \"{current_user.username}\" ({role_label_vn(current_user.role)}) "
                    "không có quyền thực hiện thao tác này."
                ),
            )
        return current_user

    return dependency


def require_roles(*roles: str):
    """Dependency factory: chỉ cho phép các vai trò liệt kê (ngoài danh sách -> 403)."""

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Thao tác này chỉ dành cho: "
                    f"{', '.join(role_label_vn(role) for role in roles)}."
                ),
            )
        return current_user

    return dependency


# Alias tương thích tên gọi quen thuộc khi đọc code.
require_authenticated = get_current_user


# =====================================================================
# 6. Đăng nhập & quy tắc "người thực hiện" (chống khai khống nhân viên)
# =====================================================================
def authenticate(db: Session, username: str, password: str) -> Tuple[Optional[User], str]:
    """
    Kiểm tra thông tin đăng nhập.

    Trả về (user, "") nếu hợp lệ; ngược lại (None, lý do) - lý do chỉ dùng cho log nội bộ,
    KHÔNG trả ra ngoài (tránh dò tài khoản tồn tại hay không).
    """
    username = (username or "").strip()
    if not username or not password:
        return None, "missing_credentials"
    user = db.query(User).filter(func.lower(User.username) == username.lower()).first()
    if not user:
        return None, "user_not_found"
    if is_legacy_hash(user.password_hash):
        return None, "password_not_configured"
    if not verify_password(password, user.password_hash):
        return None, "bad_password"
    if not user.active:
        return None, "inactive_user"
    return user, ""


def ensure_actor_allowed(
    db: Session, current_user: User, actor_id: Optional[int], action_label: str
) -> Optional[User]:
    """
    Chống "khai khống" người thực hiện: nhân viên chỉ được ghi danh mình,
    quản lý được ghi danh bất kỳ ai.

    Trả về bản ghi nhân viên sẽ được lưu vào phiếu (None = không ghi nhận ai).
    """
    if current_user.role == ROLE_MANAGER:
        if actor_id is None:
            return None
        target = db.query(User).filter(User.id == actor_id).first()
        if not target:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy nhân viên được chỉ định cho thao tác này.",
            )
        return target
    if actor_id is None:
        return None
    if int(actor_id) == int(current_user.id):
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            f"Bạn chỉ có thể ghi nhận chính mình là người thực hiện "
            f"({action_label}). Vui lòng nhờ quản lý nếu cần ghi nhận người khác."
        ),
    )
