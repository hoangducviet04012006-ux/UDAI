/* =====================================================================
   BaoHanhAI - Giao diện quản lý bảo hành (Đợt 2)
   ---------------------------------------------------------------------
   Nguyên tắc:
   - Mọi dữ liệu nghiệp vụ đều lấy từ API thật, không hard-code/mock.
   - Mọi lỗi API (400/403/404/409/422/500) hiển thị đúng bản chất bằng tiếng Việt.
   - Mọi thao tác thêm/sửa/xóa/đổi trạng thái đều gọi API rồi nạp lại dữ liệu.
   - [Đợt 7] Người dùng phải đăng nhập; giao diện gửi token kèm mọi API và
     ẩn/hiện menu + thao tác theo quyền của vai trò (quyền do backend trả về).
   ===================================================================== */

const API_BASE = "";

/* --------------------------- Trạng thái dùng chung --------------------------- */
const state = {
  currentTab: "dashboard",
  customers: [],
  products: [],
  devices: [],
  tickets: [],
  categories: [],
  users: [],
  statusChart: null,
  // Bảng điều khiển theo vai trò: dữ liệu backend trả về (workboard) + cách xem đang chọn
  workboard: null,
  dashView: null,
  dashActiveRows: [],
  dashAttention: [],
  dashIsAttention: false,
  dashUseMine: false,
  dashFilterStatus: "ALL",
  dashSearchQuery: "",
  selectedTicket: null,
  selectedDeviceId: null,
  currentAiResult: null,
  wizard: { device: null },
  actionHandler: null,
  // Danh sách id các trường nghiệp vụ đang hiển thị trong hộp thoại xác nhận
  actionFields: [],
  // Phiên làm việc hiện tại: token + thông tin nhân viên (vai trò & danh sách quyền).
  session: { token: "", user: null },
  sessionEpoch: 0,
};

/* --------------------------- Gọi API có xử lý lỗi --------------------------- */
/**
 * Gọi API và luôn trả về { ok, status, data }. Không ném ngoại lệ ra ngoài để
 * tầng giao diện luôn hiển thị được thông báo lỗi rõ ràng.
 *
 * [Đợt 7] Nếu đã đăng nhập, mọi yêu cầu đều tự động gắn header
 * `Authorization: Bearer <token>` để backend nhận diện nhân viên và vai trò.
 * Riêng yêu cầu đăng nhập truyền `{ skipAuth: true }` cho nên không gắn token
 * (tránh trường hợp token cũ/hết hạn làm hỏng thao tác đăng nhập).
 */
async function apiFetch(path, options = {}) {
  const { skipAuth = false, ...rest } = options;
  const opts = { headers: {}, ...rest };
  if (opts.body !== undefined && typeof opts.body !== "string") {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.body);
  }
  if (!skipAuth && state.session.token) {
    opts.headers["Authorization"] = "Bearer " + state.session.token;
  }
  try {
    const res = await fetch(API_BASE + path, opts);
    const text = await res.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch (e) {
      data = { detail: text || "" };
    }
    // Token hết hạn hoặc bị thu hồi: đưa người dùng về màn hình đăng nhập.
    if (res.status === 401 && !skipAuth) {
      handleSessionExpired();
    }
    return { ok: res.ok, status: res.status, data };
  } catch (e) {
    return { ok: false, status: 0, data: { detail: "Không kết nối được hệ thống." } };
  }
}

/* Tên trường kỹ thuật trong thông báo của hệ thống -> nhãn người dùng hiểu được */
const FIELD_LABELS = {
  full_name: "Họ và tên",
  phone: "Số điện thoại",
  email: "Email",
  address: "Địa chỉ",
  name: "Tên",
  brand: "Thương hiệu",
  category: "Nhóm sản phẩm",
  warranty_duration_months: "Thời hạn bảo hành",
  serial_number: "Số sê-ri",
  customer_id: "Khách hàng",
  product_id: "Dòng máy",
  purchase_date: "Ngày mua",
  issue_description: "Mô tả tình trạng lỗi",
  service_center_id: "Trung tâm bảo hành",
  created_by: "Người tiếp nhận",
  new_status: "Trạng thái mới",
  changed_by: "Người thực hiện",
  note: "Ghi chú",
  decision: "Lựa chọn xác nhận",
  reviewed_by: "Người xác nhận",
  status: "Tình trạng theo dõi của máy",
  description: "Mô tả",
};

/* Câu báo lỗi tiếng Anh của hệ thống -> câu tiếng Việt tương ứng */
const SERVER_MESSAGE_LABELS = [
  [/field required/i, "là trường bắt buộc"],
  [/input should be a valid integer/i, "phải là số nguyên"],
  [/input should be a valid number/i, "phải là số"],
  [/input should be a valid date/i, "phải là ngày hợp lệ"],
  [/valid email/i, "phải là email hợp lệ"],
  [/should have at most (\d+) characters?/i, "không được vượt quá $1 ký tự"],
  [/should have at least (\d+) characters?/i, "phải có ít nhất $1 ký tự"],
  [/should be greater than or equal to (\d+)/i, "phải lớn hơn hoặc bằng $1"],
  [/should be greater than (\d+)/i, "phải lớn hơn $1"],
  [/should be less than or equal to (\d+)/i, "phải nhỏ hơn hoặc bằng $1"],
  [/should be less than (\d+)/i, "phải nhỏ hơn $1"],
  [/string should match pattern/i, "không đúng định dạng"],
  [/input should be/i, "giá trị không hợp lệ"],
];

/** Ghép nhãn tiếng Việt của trường với câu giải thích tiếng Việt (bỏ mã trường kỹ thuật). */
function friendlyFieldMessage(field, message) {
  const label = FIELD_LABELS[field] || "";
  let msg = String(message || "").trim();
  SERVER_MESSAGE_LABELS.forEach(([pattern, replacement]) => {
    msg = msg.replace(pattern, replacement);
  });
  if (!label) return msg;
  return msg ? `${label}: ${msg}` : label;
}

/** Chuyển thông báo lỗi dữ liệu nhập (422) thành câu tiếng Việt dễ hiểu. */
function validationMessage(detail) {
  if (!Array.isArray(detail)) return typeof detail === "string" ? detail : "";
  return detail
    .map((item) => {
      const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : "";
      return friendlyFieldMessage(field, item.msg);
    })
    .join("; ");
}

/**
 * Chuyển lỗi HTTP thành thông báo tiếng Việt theo đúng bản chất lỗi.
 * Không gộp mọi lỗi thành "Lỗi kết nối máy chủ".
 *
 * [Đợt hoàn thiện nghiệp vụ] Backend trả kèm `message` (câu tiếng Việt đã được
 * viết sẵn cho nhân viên) và `hint` (việc cần làm tiếp). Giao diện ưu tiên 2
 * trường này để KHÔNG hiển thị mã kỹ thuật như [BR3 FAIL] hay STATE MACHINE ERROR.
 */
function errorMessage(status, data) {
  const detail = data && data.detail ? data.detail : "";
  const friendly = data && data.message ? String(data.message) : "";
  const hint = data && data.hint ? String(data.hint) : "";
  const clean = humanizeText(detail);
  if (friendly) return hint ? `${friendly} ${hint}` : friendly;
  if (status === 0) return "Không kết nối được hệ thống. Vui lòng kiểm tra kết nối mạng rồi thử lại.";
  if (status === 400) return clean || "Yêu cầu không hợp lệ.";
  if (status === 401) return clean || "Phiên làm việc đã hết hạn. Vui lòng đăng nhập lại.";
  if (status === 403) return clean || "Tài khoản này không có quyền thực hiện thao tác.";
  if (status === 404) return clean || "Không tìm thấy dữ liệu yêu cầu.";
  if (status === 409) return clean || "Dữ liệu đang được sử dụng ở nơi khác nên không thể thực hiện.";
  if (status === 422) {
    const v = validationMessage(detail);
    return "Thông tin nhập chưa hợp lệ." + (v ? " Vui lòng kiểm tra: " + humanizeText(v) : "");
  }
  if (status >= 500) return "Hệ thống đang gặp sự cố, vui lòng thử lại sau ít phút.";
  return clean || "Đã xảy ra lỗi không xác định.";
}

/* --------------------------- Tiện ích giao diện --------------------------- */
function $(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function showToast(message, type = "info", duration = 4500) {
  const container = $("toast-container");
  if (!container) return;
  const icons = { success: "check-circle", error: "alert-octagon", warning: "alert-triangle", info: "info" };
  const colors = {
    success: "bg-emerald-50 border-emerald-300 text-emerald-900 shadow-md",
    error: "bg-rose-50 border-rose-300 text-rose-900 shadow-md",
    warning: "bg-amber-50 border-amber-300 text-amber-900 shadow-md",
    info: "bg-indigo-50 border-indigo-200 text-indigo-950 shadow-md",
  };
  const iconColors = {
    success: "text-emerald-600",
    error: "text-rose-600",
    warning: "text-amber-600",
    info: "text-indigo-600",
  };
  const toast = document.createElement("div");
  toast.className = `toast flex items-start gap-3 p-4 rounded-xl border ${colors[type] || colors.info}`;
  toast.innerHTML = `
    <i data-lucide="${icons[type] || "info"}" class="w-5 h-5 mt-0.5 shrink-0 ${iconColors[type] || "text-indigo-600"}"></i>
    <div class="flex-1 text-sm font-semibold leading-relaxed">${message}</div>
    <button class="text-slate-400 hover:text-slate-700 ml-2 text-base font-bold leading-none" onclick="this.parentElement.remove()">&times;</button>`;
  container.appendChild(toast);
  refreshIcons();
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(-10px)";
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

function refreshIcons() {
  if (window.lucide) {
    try { lucide.createIcons(); } catch (e) { /* CDN chưa sẵn sàng */ }
  }
}

/** Hiển thị thông báo lỗi từ kết quả apiFetch. */
function toastError(result, fallbackPrefix = "") {
  const msg = errorMessage(result.status, result.data);
  showToast((fallbackPrefix ? fallbackPrefix + " " : "") + msg, "error", 8000);
}

function setTableMessage(tbodyId, colspan, text) {
  const tbody = $(tbodyId);
  if (!tbody) return;
  tbody.innerHTML = `<tr><td class="table-msg" colspan="${colspan}">${text}</td></tr>`;
}

function setTableLoading(tbodyId, colspan, text = "Đang tải dữ liệu...") {
  setTableMessage(tbodyId, colspan, `<span class="inline-flex items-center gap-2"><i data-lucide="loader" class="w-4 h-4 animate-spin"></i>${text}</span>`);
  refreshIcons();
}

function fmtDate(iso) {
  if (!iso) return "–";
  const p = String(iso).split("T")[0].split("-");
  if (p.length !== 3) return String(iso);
  return `${p[2]}/${p[1]}/${p[0]}`;
}

function fmtDateTime(iso) {
  if (!iso) return "–";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso);
  return d.toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function todayISO() {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

/** Cộng số tháng vào ngày ISO (xử lý đúng ngày cuối tháng). */
function addMonthsISO(dateStr, months) {
  const parts = String(dateStr).split("-");
  if (parts.length !== 3) return "";
  const y = parseInt(parts[0], 10);
  const m = parseInt(parts[1], 10) - 1;
  const d = parseInt(parts[2], 10);
  const target = new Date(y, m + months, 1);
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
  const t = new Date(target.getFullYear(), target.getMonth(), Math.min(d, lastDay));
  return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")}`;
}

/* --------------------------- Hiển thị tiếng Việt cho người dùng ---------------------------
   LƯU Ý KIẾN TRÚC: đây thuần là "lớp hiển thị" (display layer).
   - KHÔNG đổi dữ liệu backend/DB/API; mã kỹ thuật vẫn giữ nguyên trong CSDL & response.
   - Chỉ dịch/mã hoá lại chuỗi TRƯỚC KHI in ra giao diện cho người dùng phổ thông.
   ------------------------------------------------------------------------- */

/* Vai trò hệ thống -> cách gọi nghiệp vụ */
const ROLE_LABELS = {
  MANAGER: "Quản lý",
  RECEPTIONIST: "Nhân viên tiếp nhận",
  TECHNICIAN: "Kỹ thuật viên",
};

/* Trạng thái thiết bị -> tiếng Việt */
const DEVICE_STATUS_LABELS = {
  ACTIVE: "Đang hoạt động",
  EXPIRED: "Ngừng theo dõi",
};

/* Một số chuỗi dữ liệu mẫu (seed) đang lưu không dấu; hiển thị lại cho tự nhiên.
   Đây chỉ là bản dịch hiển thị của ĐÚNG nội dung đó, không tạo dữ liệu mới. */
const DISPLAY_TEXT_MAP = {
  "Nguyen Van An": "Nguyễn Văn An",
  "Tran Thi Binh": "Trần Thị Bình",
  "Le Hoang Cuong": "Lê Hoàng Cường",
  "Vuong Thi Thu": "Vương Thị Thu",
  "Nguyen Quan Ly": "Nguyễn Quản Lý",
  "Tran Tiep Nhan": "Trần Tiếp Nhận",
  "Le Ky Thuat": "Lê Kỹ Thuật",
  "Dien thoai Samsung Galaxy S24 Ultra": "Điện thoại Samsung Galaxy S24 Ultra",
  "Man hinh Dell UltraSharp U2723QE": "Màn hình Dell UltraSharp U2723QE",
  "Loi phan cung bo mach / nguon": "Lỗi phần cứng – Bo mạch / nguồn",
  "Loi man hinh hien thi": "Lỗi màn hình hiển thị",
  "Loi ban phim & Touchpad": "Lỗi bàn phím & Touchpad",
  "Thiet bi khong len nguon hoac sap nguon dot ngot": "Thiết bị không lên nguồn hoặc sập nguồn đột ngột",
  "Man hinh ke soc, diem chet hoac chop nhay": "Màn hình kẻ sọc, điểm chết hoặc chớp nháy",
  "Liet phim, cham touchpad": "Liệt phím, chạm touchpad không nhạy",
  "Chuyen sang kiem tra ky thuat (Da co san trong seed de test BR3).":
    "Chuyển sang bước kiểm tra kỹ thuật.",
  "Khởi tạo phiếu tiếp nhận bảo hành (Đạt toàn bộ BR1-BR4).":
    "Khởi tạo phiếu tiếp nhận bảo hành (đạt toàn bộ điều kiện bảo hành).",
  "Ky thuat vien da tiep nhan may vao phong kiem tra": "Kỹ thuật viên đã tiếp nhận máy vào phòng kiểm tra",
  "Xac dinh loi chip nguon, tien hanh sua chua thay the linh kien":
    "Xác định lỗi chip nguồn, tiến hành sửa chữa thay thế linh kiện",
  "Da thay the linh kien thanh cong, may hoat dong binh thuong":
    "Đã thay thế linh kiện thành công, máy hoạt động bình thường",
};

/* Nhóm lỗi kỹ thuật của bộ phân loại -> tên hiển thị */
const ERROR_GROUP_LABELS = {
  POWER_MAINBOARD: "nguồn / bo mạch",
  POWER_FAILURE: "thiết bị không lên nguồn",
  HARDWARE_ERROR: "lỗi phần cứng",
  SOFTWARE_ERROR: "lỗi phần mềm",
  NETWORK_ERROR: "lỗi kết nối mạng",
  KEYBOARD_TOUCHPAD: "bàn phím & touchpad",
  DISPLAY: "màn hình hiển thị",
  POWER: "nguồn / bo mạch",
  KEYBOARD: "bàn phím",
  TOUCHPAD: "touchpad",
  UNKNOWN: "chưa xác định",
};

function roleLabel(role) {
  return ROLE_LABELS[role] || "Nhân viên";
}

function deviceStatusLabel(code) {
  return DEVICE_STATUS_LABELS[code] || "Không xác định";
}

/** Tra bản dịch hiển thị cho một chuỗi dữ liệu (nếu có), ngược lại giữ nguyên.
 *  Không áp dụng khôi phục dấu ở đây để tên khách hàng/tên sản phẩm do người dùng nhập luôn nguyên vẹn. */
function displayText(value) {
  if (value === null || value === undefined) return value;
  const raw = String(value);
  return DISPLAY_TEXT_MAP[raw] || DISPLAY_TEXT_MAP[raw.trim()] || raw;
}

/** Bỏ các thẻ kỹ thuật mà backend gắn vào thông báo: [BR2 FAIL], [AI-01], BR1-BR4, enum... */
function stripTechTags(text) {
  if (!text) return "";
  let out = String(text);
  out = out.replace(/\[(BR[1-5]|STATE MACHINE|AI-01|GUARDRAIL|INVALID AI OUTPUT|VALIDATION|REVIEW|AUD-\d+|CHẶN STATE MACHINE)[^\]]*\]/gi, " ");
  out = out.replace(/\(FK RESTRICT\)/gi, " ");
  out = out.replace(/\(Đạt toàn bộ BR1-BR4\)/gi, "(đạt toàn bộ điều kiện bảo hành)");
  out = out.replace(/\(Da co san trong seed de test BR3\)/gi, "");
  out = out.replace(/\bBR[1-5]\b/gi, "");
  out = out.replace(/\b(WORKFLOW_STATE_CLOSED|INVALID_TRANSITION|RBAC_FORBIDDEN)\b/gi, "");
  out = out.replace(/\s{2,}/g, " ").trim();
  out = out.replace(/\s+([.,;:])/g, "$1");
  return out.replace(/^[-–•:\s]+/, "");
}

/* Mã trạng thái xuất hiện BÊN TRONG câu thông báo -> tiếng Việt */
const INLINE_CODE_MAP = {
  "RECEIVED": "Tiếp nhận",
  "INSPECTING": "Kiểm tra",
  "REPAIRING": "Sửa chữa",
  "COMPLETED": "Hoàn tất",
  "REJECTED": "Từ chối",
  "RETURNED": "Đã trả máy",
  "ACTIVE": "Đang hoạt động",
  "EXPIRED": "Ngừng theo dõi",
  "APPROVED": "Đã xác nhận",
  "PENDING": "Chờ xác nhận",
};

/* Cụm từ khoá kỹ thuật hay xuất hiện trong lý do gợi ý -> tiếng Việt */
const KEYWORD_DISPLAY_MAP = {
  "man hinh": "màn hình",
  "ke soc": "kẻ sọc",
  "diem chet": "điểm chết",
  "chop nhay": "chớp nháy",
  "nhap nhay": "nhấp nháy",
  "ban phim": "bàn phím",
  "nguon": "nguồn",
  "bo mach": "bo mạch",
  "khong len": "không lên",
  "soc": "sọc",
  "liet phim": "liệt phím",
};


/* Cụm từ tiếng Việt không dấu hay gặp trong mô tả lỗi/dữ liệu mẫu -> hiển thị lại có dấu.
   Ưu tiên cụm từ để tránh nhầm với tên riêng (ví dụ "Van" trong tên người). */
const PHRASE_ACCENT_MAP = {
  "man hinh": "màn hình",
  "ban phim": "bàn phím",
  "bo mach": "bo mạch",
  "khoi dong": "khởi động",
  "den nguon": "đèn nguồn",
  "nhan nut": "nhấn nút",
  "chap nhan": "chấp nhận",
  "tiep nhan": "tiếp nhận",
  "sua chua": "sửa chữa",
  "hien thi": "hiển thị",
  "tu dong": "tự động",
  "thiet bi": "thiết bị",
  "kiem tra": "kiểm tra",
  "bao hanh": "bảo hành",
  "phieu bao hanh": "phiếu bảo hành",
  "khach hang": "khách hàng",
  "san pham": "sản phẩm",
  "linh kien": "linh kiện",
  "ky thuat": "kỹ thuật",
  "bo qua": "bỏ qua",
  "quy tac": "quy tắc",
  "xu ly": "xử lý",
  "tien hanh": "tiến hành",
  "thay the": "thay thế",
  "lien tuc": "liên tục",
  "van de": "vấn đề",
  "khong len": "không lên",
  "khong khoi dong": "không khởi động",
  "chap chon": "chập chờn",
  "nhap nhay": "nhấp nháy",
  "chop nhay": "chớp nháy",
  "ke soc": "kẻ sọc",
  "diem chet": "điểm chết",
  "de kiem thu": "để kiểm thử",
  "duoc tao": "được tạo",
};

/* Từ đơn tiếng Việt không dấu -> có dấu (chỉ những từ KHÔNG trùng với tên riêng thường gặp). */
const WORD_ACCENT_MAP = {
  hinh: "hình", soc: "sọc", diem: "điểm", chet: "chết", chop: "chớp", nhay: "nháy",
  nhap: "nhấp", phim: "phím", nguon: "nguồn", mach: "mạch", khong: "không", len: "lên",
  bat: "bật", khoi: "khởi", dong: "động", den: "đèn", tat: "tắt", nut: "nút",
  may: "máy", bi: "bị", chap: "chập", chon: "chờn", cong: "cổng", sac: "sạc",
  kiem: "kiểm", thuat: "thuật", thiet: "thiết", phieu: "phiếu", khach: "khách",
  ngay: "ngày", loi: "lỗi", binh: "bình", thuong: "thường", hoat: "hoạt",
  dinh: "định", xac: "xác", man: "màn", nhung: "nhưng", cham: "chạm", dang: "đang",
  sap: "sập", dot: "đột", duoc: "được", toan: "toàn", xoa: "xóa", hong: "hỏng",
  yeu: "yếu", xong: "xong", luon: "luôn",
};

/**
 * Khôi phục dấu tiếng Việt cho phần dữ liệu mẫu lưu không dấu (chỉ để HIỂN THỊ).
 * - Từ thường: "man hinh" -> "màn hình".
 * - Từ viết hoa đầu câu: "Man hinh" -> "Màn hình".
 * - KHÔNG đụng tới số sê-ri, mã viết hoa toàn bộ (SN, DELL…) hay tên riêng không có trong bảng.
 */
function accentRestore(text) {
  if (!text) return text;
  let out = String(text);
  Object.keys(PHRASE_ACCENT_MAP).forEach((phrase) => {
    out = out.split(phrase).join(PHRASE_ACCENT_MAP[phrase]);
  });
  return out.replace(/(^|[^0-9A-Za-zÀ-ỹ]+)([A-Za-z]{2,})(?![0-9A-Za-zÀ-ỹ])/g, (all, separator, word) => {
    const lower = word.toLowerCase();
    const mapped = WORD_ACCENT_MAP[lower];
    if (!mapped) return all;
    if (word === lower) return separator + mapped;
    const titleCase = lower.charAt(0).toUpperCase() + lower.slice(1);
    if (word === titleCase) return separator + mapped.charAt(0).toUpperCase() + mapped.slice(1);
    return all;
  });
}

/**
 * Chuyển lý do/thông báo kỹ thuật thành câu tiếng Việt dễ hiểu cho nhân viên bảo hành.
 * Chỉ thay đổi phần HIỂN THỊ, không ảnh hưởng dữ liệu lưu trong CSDL.
 * Thứ tự xử lý: bỏ thẻ kỹ thuật -> thay chuỗi dữ liệu đã biết -> thay mã trạng thái/nhóm lỗi/từ khoá.
 */
function humanizeText(text) {
  let out = stripTechTags(text);
  if (!out) return "";

  // 1) Các chuỗi dữ liệu đã biết (gồm tên seed không dấu) - khớp NGUYÊN VĂN trước
  Object.keys(DISPLAY_TEXT_MAP).forEach((key) => {
    if (out.indexOf(key) !== -1) out = out.split(key).join(DISPLAY_TEXT_MAP[key]);
  });

  // 2) Mã trạng thái: ưu tiên dạng được trích dẫn 'INSPECTING', sau đó dạng đứng riêng.
  //    Dùng ranh giới an toàn (không khớp trong 'SN-SAMS-EXPIRED-02').
  Object.keys(INLINE_CODE_MAP).forEach((key) => {
    out = out.split("'" + key + "'").join("'" + INLINE_CODE_MAP[key] + "'");
    out = out.replace(new RegExp("(^|[^\\w-])" + key + "(?![\\w-])", "g"), "$1" + INLINE_CODE_MAP[key]);
  });

  // 3) Nhóm lỗi kỹ thuật của bộ phân loại (DISPLAY, POWER_MAINBOARD...)
  Object.keys(ERROR_GROUP_LABELS).forEach((key) => {
    out = out.split("'" + key + "'").join("'" + ERROR_GROUP_LABELS[key] + "'");
    out = out.replace(new RegExp("(^|[^\\w-])" + key + "(?![\\w-])", "g"), "$1" + ERROR_GROUP_LABELS[key]);
  });

  // 4) Từ khoá kỹ thuật còn lại trong lý do gợi ý (chỉ khớp chữ thường)
  Object.keys(KEYWORD_DISPLAY_MAP).forEach((key) => {
    out = out.replace(new RegExp("(^|[^\\w-])" + key + "(?![\\wàáâãèéêìíòóôõùúýăđĩũơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ])", "g"),
      "$1" + KEYWORD_DISPLAY_MAP[key]);
  });

  const words = {
    confidence: "mức độ chắc chắn",
    provider: "nguồn gợi ý",
    prompt: "nội dung yêu cầu",
    issue_description: "mô tả lỗi",
    error_category_id: "loại lỗi",
    "error_categories": "danh mục loại lỗi",
    "product_instance": "thiết bị",
    "warranty_ticket": "phiếu bảo hành",
    "ai_results": "kết quả gợi ý",
    "state transition": "chuyển trạng thái",
    "test": "kiểm thử",
    "PII": "thông tin cá nhân",
    "fixture": "dữ liệu kiểm thử",
    "Nhãn lỗi": "Loại lỗi",
    "nhãn lỗi": "loại lỗi",
    "Nhãn": "Loại lỗi",
    "nhãn": "loại lỗi",
  };
  Object.keys(words).forEach((key) => {
    out = out.split(key).join(words[key]);
  });
  return accentRestore(out.replace(/\s{2,}/g, " ").replace(/\s+([.,;:])/g, "$1").trim());
}

/** Diễn giải một bước trace đối chiếu bảo hành của backend cho dễ đọc. */
function humanizeTraceStep(step) {
  let out = String(step);
  out = out.replace(/\[Step (\d+)\]/g, "[Bước $1]");
  out = out.replace(/\[Trace (WARNING|ERROR)\]/g, "[Ghi chú]");
  out = out.replace(/\[Result (PASS|FAIL)\]/g, "[Kết quả]");
  const words = {
    serial_number: "số sê-ri",
    product_name: "tên sản phẩm",
    purchase_date: "ngày mua",
    warranty_duration_months: "thời hạn bảo hành (tháng)",
    warranty_end_date: "ngày hết hạn bảo hành",
    calculated_end_date: "ngày hết hạn tính lại",
    frozen_end_date: "ngày hết hạn trong hồ sơ",
    effective_end_date: "ngày hết hạn áp dụng",
    check_date: "ngày kiểm tra",
    delta_days: "số ngày chênh lệch",
    is_valid: "kết luận còn hạn",
    "Hạn BH": "hạn bảo hành",
    "Standalone simulation": "mô phỏng độc lập",
    DB: "dữ liệu trong hệ thống",
  };
  Object.keys(words).forEach((key) => {
    out = out.split(key).join(words[key]);
  });
  out = out.replace(/BR[1-5]/g, "quy tắc bảo hành");
  out = out.replace(/->/g, "→");
  out = out.replace(/\bTrue\b/g, "Đạt");
  out = out.replace(/\bFalse\b/g, "Không đạt");
  out = out.replace(/\bPASS\b/g, "Đạt");
  out = out.replace(/\bFAIL\b/g, "Không đạt");
  out = out.split("Điều kiện quy tắc bảo hành").join("Điều kiện bảo hành");
  out = out.split("Đối chiếu quy tắc bảo hành").join("Đối chiếu điều kiện bảo hành");
  return out.replace(/\s{2,}/g, " ").replace(/\s+([.,;:])/g, "$1").trim();
}

/** 0.93 -> "93%" cho dễ hiểu. */
function confidencePercent(value) {
  const num = Number(value || 0);
  return Math.round(num * 100) + "%";
}


/* --------------------------- Trạng thái phiếu (song ngữ) --------------------------- */
/* 6 trạng thái vòng đời phiếu:
   - Luồng sửa chữa: TIẾP NHẬN -> KIỂM TRA -> SỬA CHỮA -> HOÀN TẤT -> ĐÃ TRẢ MÁY
   - Luồng từ chối: KIỂM TRA -> TỪ CHỐI -> ĐÃ TRẢ MÁY */
const STATUS_LABELS = {
  RECEIVED: "Tiếp nhận",
  INSPECTING: "Kiểm tra",
  REPAIRING: "Sửa chữa",
  COMPLETED: "Hoàn tất",
  REJECTED: "Từ chối",
  RETURNED: "Đã trả máy",
};
const STATUS_COLORS = ["#3B82F6", "#F59E0B", "#A855F7", "#10B981", "#EF4444", "#64748B"];
const STATUS_ORDER = ["RECEIVED", "INSPECTING", "REPAIRING", "COMPLETED", "REJECTED", "RETURNED"];

function statusLabel(code) {
  return STATUS_LABELS[code] || "Không xác định";
}

function statusBadge(code) {
  return `<span class="px-2.5 py-1 text-xs font-semibold rounded-full badge-${String(code || "").toLowerCase()}">${statusLabel(code)}</span>`;
}

function reviewLabel(code) {
  if (code === "APPROVED") return "Đã xác nhận";
  if (code === "REJECTED") return "Không dùng gợi ý này";
  if (code === "PENDING") return "Chờ xác nhận";
  return code ? "Không xác định" : "–";
}

function userName(userId) {
  if (userId === null || userId === undefined) return "–";
  const u = state.users.find((x) => x.id === userId);
  return u ? `${displayText(u.full_name)} – ${roleLabel(u.role)}` : "Nhân viên (chưa rõ tên)";
}

function userShortName(userId) {
  if (userId === null || userId === undefined) return "–";
  const u = state.users.find((x) => x.id === userId);
  if (u) return displayText(u.full_name);
  const full = userName(userId);
  return full.split(" – ")[0] || "–";
}

/**
 * KTV phụ trách: phân biệt người tiếp nhận (created_by) với KTV được phân công.
 * Chưa phân công KTV thì hiển thị "Chưa phân công".
 */
function ticketTechnicianName(t) {
  if (!t) return "Chưa phân công";
  // 1. Cột phân công KTV từ backend API
  if (t.assigned_technician_name) {
    const n = displayText(t.assigned_technician_name);
    if (n && n !== "–" && n !== "Chưa rõ") return n;
  }
  if (t.assigned_technician_id) {
    const n = userShortName(t.assigned_technician_id);
    if (n && n !== "–" && n !== "Chưa rõ") return n;
  }
  // 2. KTV thực hiện sửa chữa
  if (t.repair_by) {
    const n = userShortName(t.repair_by);
    if (n && n !== "–" && n !== "Chưa rõ") return n;
  }
  // 3. KTV thực hiện chẩn đoán
  if (t.diagnosis_by) {
    const n = userShortName(t.diagnosis_by);
    if (n && n !== "–" && n !== "Chưa rõ") return n;
  }
  // 4. Lịch sử chuyển trạng thái: tìm bước INSPECTING/REPAIRING do KTV thực hiện (không phải receptionist)
  const history = Array.isArray(t.status_history) ? t.status_history : (Array.isArray(t.history) ? t.history : []);
  for (let i = history.length - 1; i >= 0; i--) {
    const s = history[i];
    if (["INSPECTING", "REPAIRING"].includes(s.to_status) && s.changed_by && s.changed_by !== t.created_by) {
      const n = s.changed_by_name ? displayText(s.changed_by_name) : userShortName(s.changed_by);
      if (n && n !== "–" && n !== "Chưa rõ") return n;
    }
  }
  // Nếu phiếu mới tiếp nhận (RECEIVED), chắc chắn chưa phân công KTV
  if (t.status === "RECEIVED") return "Chưa phân công";

  // Nếu có handler_name và không phải người tiếp nhận
  if (t.handler_name) {
    const h = displayText(t.handler_name);
    const creator = userShortName(t.created_by);
    if (h && h !== creator && h !== "–" && !h.toLowerCase().includes("tiếp nhận")) return h;
  }
  return "Chưa phân công";
}

function formatTechnicianCell(name) {
  if (!name || name === "Chưa phân công") {
    return `<span class="text-slate-400 italic">Chưa phân công</span>`;
  }
  return `<span class="font-medium text-slate-800">${escapeHtml(name)}</span>`;
}

function categoryName(categoryId) {
  if (categoryId === null || categoryId === undefined) return "Chưa xác định";
  const c = state.categories.find((x) => x.id === categoryId);
  return c ? displayText(c.name) : "Loại lỗi khác";
}

/* --------------------------- Validation --------------------------- */
function setFieldError(fieldId, message) {
  const box = $("err-" + fieldId);
  if (box) {
    box.textContent = message;
    box.classList.toggle("hidden", !message);
  }
}

function clearFieldErrors(ids) {
  ids.forEach((id) => setFieldError(id, ""));
}

const PHONE_REGEX = /^(0|\+84)\d{8,10}$/;
const EMAIL_REGEX = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;

function validateCustomerForm(data) {
  const errors = {};
  if (!data.full_name) errors["cust-name"] = "Vui lòng nhập họ và tên khách hàng.";
  else if (data.full_name.length < 2) errors["cust-name"] = "Họ và tên quá ngắn.";
  if (!data.phone) errors["cust-phone"] = "Vui lòng nhập số điện thoại.";
  else if (!PHONE_REGEX.test(data.phone.replace(/[\s.-]/g, ""))) errors["cust-phone"] = "Số điện thoại không hợp lệ (ví dụ: 0912345678).";
  if (data.email && !EMAIL_REGEX.test(data.email)) errors["cust-email"] = "Email không hợp lệ (ví dụ: an.nguyen@gmail.com).";
  return errors;
}

/* --------------------------- Modal dùng chung --------------------------- */
function openModal(id) {
  const el = $(id);
  if (el) el.style.display = "flex";
  refreshIcons();
}

function closeModal(id) {
  const el = $(id);
  if (el) el.style.display = "none";
  if (id === "ticket-modal") {
    state.selectedTicket = null;
    state.currentAiResult = null;
  }
  if (id === "device-detail-modal") state.selectedDeviceId = null;
}

/* --------------------------- HỘP THOẠI XÁC NHẬN (đa trường) --------------------------- */
/*
 * Modal xác nhận thao tác (thay cho confirm()/prompt() của trình duyệt).
 * [Đợt hoàn thiện nghiệp vụ] Hộp thoại dùng chung cho mọi thao tác.
 * Mỗi bước chuyển trạng thái cần hỏi đúng những thông tin nghiệp vụ của bước đó
 * (kết luận chẩn đoán / nội dung đã sửa / linh kiện / ghi chú bàn giao), nên hàm
 * này hỗ trợ NHIỀU trường thay vì chỉ một ô ghi chú.
 *
 * options:
 *   title, message, selectLabel, selectOptions, selectDefault,
 *   fields: [{ id, label, placeholder, required, defaultValue, type: "textarea"|"text",
 *              options: [{value,label}] }]
 *   confirmLabel, danger, onConfirm({ actorId, values })
 */
function showActionModal(options) {
  const {
    title = "Xác nhận thao tác",
    message = "",
    selectLabel = "",
    selectOptions = null,
    selectDefault = "",
    fields = [],
    confirmLabel = "Xác nhận",
    danger = false,
  } = options;

  $("action-modal-title").textContent = title;
  $("action-modal-message").innerHTML = message;

  // Chọn "người thực hiện" (chỉ những người mà tài khoản hiện tại được ghi nhận)
  const selectWrap = $("action-modal-select-wrap");
  const select = $("action-modal-select");
  if (selectOptions && selectOptions.length) {
    selectWrap.classList.remove("hidden");
    $("action-modal-select-label").textContent = selectLabel || "Người thực hiện";
    select.innerHTML = selectOptions
      .map((opt) => `<option value="${opt.value}">${escapeHtml(opt.label)}</option>`)
      .join("");
    select.value = String(selectDefault || selectOptions[0].value);
  } else {
    selectWrap.classList.add("hidden");
    select.innerHTML = "";
  }

  // Các trường nghiệp vụ của bước đang thực hiện
  const box = $("action-modal-fields");
  box.innerHTML = fields
    .map((field) => {
      const isSelect = Array.isArray(field.options) && field.options.length > 0;
      const label = escapeHtml(field.label || "Nội dung") + (field.required ? ' <span class="text-rose-400">*</span>' : "");
      const requiredAttr = field.required ? ' data-required="1"' : "";
      const inputHtml = isSelect
        ? `<select class="w-full glass-input px-3 py-2 rounded-xl text-sm" id="action-field-${field.id}"${requiredAttr}>
             ${field.options.map((o) => `<option value="${escapeHtml(String(o.value))}">${escapeHtml(o.label)}</option>`).join("")}
           </select>`
        : field.type === "text"
          ? `<input type="text" class="w-full glass-input px-3 py-2 rounded-xl text-sm" id="action-field-${field.id}"${requiredAttr}
               placeholder="${escapeHtml(field.placeholder || "")}" value="${escapeHtml(field.defaultValue || "")}">`
          : `<textarea rows="3" class="w-full glass-input px-3 py-2 rounded-xl text-sm" id="action-field-${field.id}"${requiredAttr}
               placeholder="${escapeHtml(field.placeholder || "")}">${escapeHtml(field.defaultValue || "")}</textarea>`;
      return `<div>
        <label class="form-label" for="action-field-${field.id}">${label}</label>
        ${inputHtml}
        ${field.hint ? `<div class="text-xs text-slate-500 mt-1">${escapeHtml(field.hint)}</div>` : ""}
        <span class="form-error hidden" id="err-action-field-${field.id}"></span>
      </div>`;
    })
    .join("");
  state.actionFields = fields.map((field) => field.id);

  const confirmBtn = $("action-modal-confirm");
  confirmBtn.textContent = confirmLabel;
  confirmBtn.className = danger ? "btn btn-danger" : "btn btn-primary";

  state.actionHandler = options.onConfirm;
  openModal("action-modal");
  const firstField = fields.length ? $("action-field-" + fields[0].id) : null;
  setTimeout(() => (firstField || confirmBtn).focus(), 50);
}

/** Danh sách lựa chọn "Người thực hiện" cho hộp thoại xác nhận (chỉ người mà tài khoản hiện tại được ghi nhận). */
function staffSelectOptions(preferredRole = "RECEPTIONIST") {
  const users = assignableStaff();
  const options = users.map((u) => ({
    value: u.id,
    label: `${displayText(u.full_name)} – ${roleLabel(u.role)}`,
  }));
  const preferred = defaultActor(users, preferredRole);
  return { options, defaultId: preferred ? preferred.id : "" };
}

/** Lấy người thực hiện đã chọn trong hộp thoại xác nhận. */
function selectedStaffId(fallbackRole = "RECEPTIONIST") {
  const select = $("action-modal-select");
  const value = select && select.value ? parseInt(select.value, 10) : NaN;
  if (!isNaN(value)) return value;
  const { defaultId } = staffSelectOptions(fallbackRole);
  return defaultId ? parseInt(defaultId, 10) : NaN;
}

function closeActionModal() {
  $("action-modal").style.display = "none";
  state.actionHandler = null;
  state.actionFields = [];
  const btn = $("action-modal-confirm");
  if (btn) btn.disabled = false;
}

/** Gom giá trị các trường nghiệp vụ đang hiển thị trong hộp thoại. */
function collectActionFieldValues() {
  const values = {};
  (state.actionFields || []).forEach((fieldId) => {
    const el = $("action-field-" + fieldId);
    if (el) values[fieldId] = (el.value || "").trim();
  });
  return values;
}

async function confirmActionModal() {
  const values = collectActionFieldValues();
  let invalid = null;
  (state.actionFields || []).forEach((fieldId) => {
    const el = $("action-field-" + fieldId);
    const errorBox = $("err-action-field-" + fieldId);
    const required = el && el.getAttribute("data-required") === "1";
    if (errorBox) {
      errorBox.textContent = "";
      errorBox.classList.add("hidden");
    }
    if (required && !values[fieldId]) {
      invalid = fieldId;
      if (errorBox) {
        errorBox.textContent = "Vui lòng nhập nội dung này trước khi xác nhận.";
        errorBox.classList.remove("hidden");
      }
    }
  });
  if (invalid) return;

  const btn = $("action-modal-confirm");
  const origHtml = btn ? btn.innerHTML : "Xác nhận";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="inline-flex items-center gap-1.5"><i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i> Đang xử lý...</span>`;
    refreshIcons();
  }

  const handler = state.actionHandler;
  const actorId = selectedStaffId("TECHNICIAN");
  try {
    if (typeof handler === "function") {
      await handler({ actorId, values });
    }
    closeActionModal();
  } catch (err) {
    console.error(err);
    showToast("Đã có lỗi xảy ra khi thực hiện thao tác.", "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origHtml;
      refreshIcons();
    }
  }
}

/* --------------------------- Điều hướng tab --------------------------- */
/* Danh sách màn hình của ứng dụng (thứ tự này không quyết định menu; menu do HTML + data-perm quyết định). */
const TABS = ["dashboard", "lookup", "customers", "products", "devices", "tickets", "ai", "accounts"];

/* Sidebar toggle helpers */
function toggleSidebar(force) {
  const shell = $("app-shell");
  const backdrop = $("sidebar-backdrop");
  if (!shell) return;
  const isOpen = shell.classList.contains("sidebar-open");
  const next = force !== undefined ? force : !isOpen;
  shell.classList.toggle("sidebar-open", next);
  if (backdrop) backdrop.classList.toggle("hidden", !next);
}

function toggleSidebarCollapse() {
  const shell = $("app-shell");
  if (!shell) return;
  shell.classList.toggle("sidebar-collapsed");
  const icon = $("sidebar-collapse-icon");
  if (icon) {
    const isCollapsed = shell.classList.contains("sidebar-collapsed");
    icon.setAttribute("data-lucide", isCollapsed ? "panel-left-open" : "panel-left-close");
    refreshIcons();
  }
}

function setupTabs() {
  document.querySelectorAll(".nav-tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.getAttribute("data-tab");
      // Bỏ qua các nút nhóm / dropdown toggle hoặc phần tử không gắn tab chuyển trang
      if (!tab) return;
      switchTab(tab);
      closeNavMore();
    });
  });
  // Bấm ra ngoài menu phụ "Tra cứu nội bộ" thì đóng lại
  document.addEventListener("click", (event) => {
    const wrap = $("nav-more");
    if (!wrap || wrap.classList.contains("hidden")) return;
    if (!wrap.contains(event.target)) closeNavMore();
  });
}

function switchTab(tabId) {
  if (!tabId || typeof tabId !== "string") return;
  if (!TABS.includes(tabId)) {
    console.warn(`[switchTab] Bỏ qua tab không hợp lệ: "${tabId}"`);
    return;
  }
  // Không cho mở màn hình mà vai trò hiện tại không có quyền (backend vẫn là nơi chặn thật).
  if (TAB_PERMISSIONS[tabId] && !hasPerm(TAB_PERMISSIONS[tabId])) {
    const fallback = firstAllowedTab();
    if (tabId === fallback) return;
    tabId = fallback;
  }
  state.currentTab = tabId;

  const TAB_TITLES = {
    dashboard: "Tổng quan",
    tickets: "Phiếu bảo hành",
    lookup: "Tra cứu bảo hành",
    ai: "Hỗ trợ xác định lỗi",
    customers: "Khách hàng",
    products: "Danh mục máy",
    devices: "Máy đã đăng ký",
    accounts: "Tài khoản nhân viên",
  };
  const topTitle = $("topbar-page-title");
  if (topTitle) topTitle.textContent = TAB_TITLES[tabId] || "BaoHanhAI";
  toggleSidebar(false);

  document.querySelectorAll(".nav-tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.getAttribute("data-tab") === tabId);
  });
  document.querySelectorAll(".tab-content-panel").forEach((panel) => {
    panel.classList.toggle("hidden", panel.id !== "tab-" + tabId);
  });

  if (tabId === "dashboard") loadDashboard();
  if (tabId === "lookup") refreshLookupSamples();
  if (tabId === "customers") loadCustomers();
  if (tabId === "products") loadProducts();
  if (tabId === "devices") loadDevices();
  if (tabId === "tickets") {
    const role = state.session.user ? state.session.user.role : "";
    if (role === "TECHNICIAN" && !state._preserveTicketScope) {
      ticketOnlyMine = true;
    }
    state._preserveTicketScope = false;
    loadWizardOptions();
    loadTickets();
  }
  if (tabId === "ai") { populateAiTicketSelect(); }
  if (tabId === "accounts") loadAccounts();

  refreshIcons();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function goToTickets() {
  switchTab("tickets");
  setTimeout(() => {
    const el = $("wiz-serial");
    if (el) el.focus();
  }, 300);
}

function goToAiTab() {
  const ticketId = state.selectedTicket ? state.selectedTicket.id : null;
  closeModal("ticket-modal");
  switchTab("ai");
  if (ticketId) {
    const sel = $("ai-ticket-select");
    if (sel) {
      sel.value = String(ticketId);
      onAiTicketChange();
    }
  }
}

function toggleReceptionPanel() {
  const body = $("reception-body");
  if (body) body.classList.toggle("hidden");
}

/* --------------------------- Dữ liệu tham chiếu --------------------------- */
/** Nạp danh mục lỗi + người dùng hệ thống (dùng chung cho nhiều màn hình). */
async function loadReferenceData() {
  const [meta, users] = await Promise.all([
    apiFetch("/api/v1/warranty-tickets/meta/demo-data"),
    apiFetch("/api/v1/ai/demo/users"),
  ]);
  if (meta.ok && meta.data) state.categories = meta.data.error_categories || [];
  if (users.ok && Array.isArray(users.data)) state.users = users.data;

  const catSelect = $("wiz-category-select");
  if (catSelect && state.categories.length) {
    const current = catSelect.value;
    catSelect.innerHTML = '<option value="">-- Chưa xác định (để hệ thống gợi ý) --</option>' +
      state.categories.map((c) => `<option value="${c.id}">${escapeHtml(displayText(c.name))}</option>`).join("");
    if (current) catSelect.value = current;
  }

  // "Người tiếp nhận" của phiếu: quản lý chọn được bất kỳ ai, nhân viên chỉ ghi nhận chính mình
  // (backend là nơi chặn thật — xem auth_service.ensure_actor_allowed).
  const staff = assignableStaff();
  const options = staff
    .map((u) => `<option value="${u.id}">${escapeHtml(displayText(u.full_name))} – ${escapeHtml(roleLabel(u.role))}</option>`)
    .join("");
  const createdBy = $("wiz-created-by");
  if (createdBy) {
    const current = createdBy.value;
    createdBy.innerHTML = options;
    const actor = defaultActor(staff, "RECEPTIONIST");
    createdBy.value = current || (actor ? String(actor.id) : "");
  }

  const reviewer = $("ai-reviewer-select");
  if (reviewer) {
    reviewer.innerHTML = staff
      .map((u) => `<option value="${u.id}">${escapeHtml(displayText(u.full_name))} (${escapeHtml(roleLabel(u.role))})${staffCanReview(u) ? "" : " – không có quyền xác nhận"}</option>`)
      .join("");
    const actor = defaultActor(staff, "TECHNICIAN");
    if (actor) reviewer.value = String(actor.id);
  }
}

/* --------------------------- TRẠNG THÁI BẢO HÀNH (chỉ để hiển thị) ---------------------------
   QUAN TRỌNG: đây là phần hiển thị. Quyết định bảo hành vẫn do backend (`warranty_end_date >= check_date`).
   ------------------------------------------------------------------------- */
function warrantyInfoFor(endDateISO) {
  if (!endDateISO) return { label: "Không xác định", textClass: "text-slate-600", dot: "⚪", days: null };
  const end = new Date(String(endDateISO) + "T00:00:00");
  if (isNaN(end.getTime())) return { label: "Không xác định", textClass: "text-slate-600", dot: "⚪", days: null };
  const today = new Date(todayISO() + "T00:00:00");
  const days = Math.round((end - today) / 86400000);
  if (days >= 0) return { label: "Còn bảo hành", textClass: "text-emerald-700", dot: "●", days };
  return { label: "Đã hết hạn", textClass: "text-rose-700", dot: "●", days };
}

function warrantyStatusHtml(endDateISO) {
  const w = warrantyInfoFor(endDateISO);
  const detail = w.days === null ? "" : (w.days >= 0 ? `còn ${w.days} ngày` : `quá hạn ${Math.abs(w.days)} ngày`);
  return `<span class="inline-flex items-center gap-1.5 font-semibold ${w.textClass}"><span class="text-xs leading-none">${w.dot}</span> ${w.label}</span>` +
    (detail ? `<span class="text-slate-500 font-normal"> (${detail})</span>` : "");
}

/* --------------------------- MÀN HÌNH: TỔNG QUAN ---------------------------
   [Đợt màn hình công việc theo vai trò] Bảng điều khiển trả lời câu hỏi
   "Hiện tại tôi cần làm gì?" cho TỪNG vai trò. Toàn bộ nội dung (tiêu đề, thẻ
   số liệu, nhóm việc, việc cần chú ý, nút hành động) do backend trả về qua
   GET /api/v1/warranty-tickets/workboard — giao diện không tự suy diễn.
   ------------------------------------------------------------------------- */

/** Màu chữ theo "tông" mà backend gán cho thẻ số liệu (mỗi trạng thái 1 màu cố định). */
const TONE_TEXT = {
  blue: "text-blue-700",
  amber: "text-amber-700",
  purple: "text-purple-700",
  cyan: "text-cyan-700",
  emerald: "text-emerald-700",
  rose: "text-rose-700",
  indigo: "text-indigo-700",
  slate: "text-slate-700",
};

function toneText(tone) {
  return TONE_TEXT[tone] || TONE_TEXT.slate;
}

function num(value) {
  return value === undefined || value === null ? "–" : value;
}

/** Đầu trang: tiêu đề + vai trò + phạm vi số liệu (backend đặt theo tài khoản). */
function renderDashHeader(wb) {
  const title = $("dash-title");
  if (title) title.textContent = "Tổng quan";
  const subtitle = $("dash-subtitle");
  if (subtitle) {
    const scopeText = wb.scope_label || (wb.scope && wb.scope !== "DEFAULT" ? wb.scope : "Toàn trung tâm");
    subtitle.textContent = `Phạm vi dữ liệu: ${scopeText}`;
  }
  const roleChip = $("dash-role-chip");
  if (roleChip) {
    roleChip.textContent = "";
    roleChip.classList.add("hidden");
  }
  const scopeChip = $("dash-scope-chip");
  if (scopeChip) {
    const show = wb.scope && wb.scope !== "DEFAULT";
    scopeChip.textContent = wb.scope_label || wb.scope;
    scopeChip.classList.toggle("hidden", !show);
  }
}

/** Khi bấm thẻ số liệu trên bảng điều khiển: lọc đúng nhóm trạng thái của bảng và cuộn xuống */
function onDashCardClick(status) {
  if (!status) return;
  if (status === "ALL") {
    setDashFilterStatus("ALL");
  } else if (status === "PROCESSING" || status.includes("RECEIVED") || status.includes("INSPECTING") || status.includes("REPAIRING")) {
    setDashFilterStatus("PROCESSING");
  } else if (status === "WAITING_RETURN" || status.includes("COMPLETED") || status.includes("REJECTED")) {
    setDashFilterStatus("WAITING_RETURN");
  } else if (status === "RETURNED") {
    setDashFilterStatus("RETURNED");
  } else {
    setDashFilterStatus(status);
  }
  const tableEl = $("dash-active-title");
  if (tableEl) {
    tableEl.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

/** Xây dựng đúng 4 thẻ số liệu chuẩn theo yêu cầu: Tổng phiếu, Đang xử lý, Chờ trả máy, Đã trả máy */
function buildDashboardFourCards(wb, view) {
  if (!wb) return [];
  // Nếu backend đã trả sẵn đúng 4 thẻ chuẩn
  if (Array.isArray(wb.cards) && wb.cards.length === 4) {
    return wb.cards;
  }
  const totals = wb.totals || {};
  const isMine = view === "mine" || (view !== "all" && wb.role !== "MANAGER" && wb.scope === "MINE");
  const scopeLabel = wb.scope_label || (isMine ? (wb.role === "RECEPTIONIST" ? "Việc tại quầy" : "Phiếu được giao") : "Toàn trung tâm");

  const rec = Number(totals.received || totals.RECEIVED || 0);
  const insp = Number(totals.inspecting || totals.INSPECTING || 0);
  const rep = Number(totals.repairing || totals.REPAIRING || 0);
  const comp = Number(totals.completed || totals.COMPLETED || 0);
  const rej = Number(totals.rejected || totals.REJECTED || 0);
  const ret = Number(totals.returned || totals.RETURNED || 0);

  const inProgress = rec + insp + rep;
  const waitingReturn = comp + rej;
  const returned = ret;
  const total = inProgress + waitingReturn + returned;

  return [
    {
      key: "TOTAL",
      label: "Tổng phiếu",
      count: total,
      description: `Tất cả phiếu (${scopeLabel})`,
      tone: "indigo",
      status: "ALL",
      icon: "files",
    },
    {
      key: "IN_PROGRESS",
      label: "Đang xử lý",
      count: inProgress,
      description: `Tiếp nhận: ${rec} • Kiểm tra: ${insp} • Sửa: ${rep}`,
      tone: "blue",
      status: "PROCESSING",
      icon: "hammer",
    },
    {
      key: "WAITING_RETURN",
      label: "Chờ trả máy",
      count: waitingReturn,
      description: `Hoàn tất: ${comp} • Từ chối: ${rej}`,
      tone: "amber",
      status: "WAITING_RETURN",
      icon: "clock",
    },
    {
      key: "RETURNED",
      label: "Đã trả máy",
      count: returned,
      description: "Đã bàn giao cho khách và đóng phiếu",
      tone: "emerald",
      status: "RETURNED",
      icon: "check-circle-2",
    },
  ];
}

/** Thẻ số liệu theo vai trò: số nổi bật, nhãn ngắn, viền trung tính gọn gàng */
function renderDashCards(cards) {
  const box = $("dash-cards");
  if (!box) return;
  const items = Array.isArray(cards) ? cards : [];
  if (!items.length) {
    box.innerHTML = '<div class="text-sm text-slate-500 col-span-full">Chưa có số liệu.</div>';
    return;
  }

  const iconStyles = {
    RETURNED: "bg-emerald-50 text-emerald-600 border-emerald-100",
    WAITING_RETURN: "bg-cyan-50 text-cyan-600 border-cyan-100",
    "COMPLETED,REJECTED": "bg-cyan-50 text-cyan-600 border-cyan-100",
    PROCESSING: "bg-amber-50 text-amber-600 border-amber-100",
    "RECEIVED,INSPECTING,REPAIRING": "bg-amber-50 text-amber-600 border-amber-100",
    RECEIVED: "bg-indigo-50 text-indigo-600 border-indigo-100",
  };

  box.innerHTML = items
    .map((card) => {
      const clickable = card.status ? `onclick="onDashCardClick('${card.status}')" role="button" tabindex="0"` : "";
      const iconName = card.icon || (card.status === "RETURNED" ? "check-circle-2" : (card.status === "WAITING_RETURN" || card.status === "COMPLETED,REJECTED" ? "clock" : (card.status === "PROCESSING" || card.status === "RECEIVED,INSPECTING,REPAIRING" ? "wrench" : "circle-dot")));
      const iconCls = iconStyles[card.status] || "bg-indigo-50 text-indigo-600 border-indigo-100";
      return `<div class="bg-white rounded-xl p-4 sm:p-5 border border-slate-200 shadow-sm hover:border-indigo-300 hover:shadow-md transition-all dash-card cursor-pointer group" ${clickable} title="Bấm để lọc bảng phiếu bên dưới">
        <div class="flex items-center justify-between mb-3">
          <span class="text-xs font-bold text-slate-500 uppercase tracking-wider group-hover:text-indigo-600 transition-colors">${escapeHtml(card.label)}</span>
          <div class="w-8 h-8 rounded-lg flex items-center justify-center border ${iconCls} transition-transform group-hover:scale-105">
            <i data-lucide="${iconName}" class="w-4 h-4"></i>
          </div>
        </div>
        <div class="text-3xl font-extrabold text-slate-900 tracking-tight leading-none">${num(card.count)}</div>
        <div class="text-xs text-slate-500 mt-2.5 font-normal truncate">${escapeHtml(card.description || "")}</div>
      </div>`;
    })
    .join("");
  refreshIcons();
}

/** Thao tác nhanh theo vai trò (nhãn + mức ưu tiên do backend quyết định). */
function renderDashQuickActions(wb) {
  const box = $("dash-quick-actions");
  if (!box) return;
  const actions = Array.isArray(wb.quick_actions) ? wb.quick_actions : [];
  const hint = $("dash-quick-hint");
  if (hint) {
    hint.textContent = `Thao tác chính của ${wb.role_label || roleLabel(wb.role)} trong một ca làm việc.`;
  }
  if (!actions.length) {
    box.innerHTML = '<div class="text-xs text-slate-500">Không có thao tác nhanh cho vai trò này.</div>';
    return;
  }
  box.innerHTML = actions
    .map((action) => `<button class="btn ${action.primary ? "btn-primary" : "btn-secondary"} justify-center btn-stack text-left"
        onclick="dashQuickAction('${action.key}')" title="${escapeHtml(action.description || action.label)}">
        <span class="inline-flex items-center gap-1.5"><i data-lucide="${escapeHtml(action.icon || "arrow-right")}" class="w-4 h-4"></i> ${escapeHtml(action.label)}</span>
        <span class="text-xs font-normal opacity-90">${escapeHtml(action.description || "")}</span>
      </button>`)
    .join("");
  refreshIcons();
}

/** Ghi chú nghiệp vụ theo vai trò: việc nào của ai (tránh nhân viên tự đoán). */
function renderDashNotes(wb) {
  const box = $("dash-notes");
  if (!box) return;
  const notes = Array.isArray(wb.notes) ? wb.notes : [];
  box.innerHTML = notes.map((text) => `<div class="flex items-start gap-1.5"><span class="text-slate-500">•</span><span>${escapeHtml(text)}</span></div>`).join("");
}

/** Tra cứu nhanh từ Tổng quan: chuyển sang màn Tra cứu bảo hành và chạy luôn. */
function dashLookup() {
  const box = $("dash-lookup-input");
  const keyword = box ? (box.value || "").trim() : "";
  if (!keyword) {
    showToast("Vui lòng nhập số sê-ri hoặc mã phiếu cần tra cứu.", "warning");
    return;
  }
  switchTab("lookup");
  $("lookup-input").value = keyword;
  runLookup();
}

/**
 * Tải bảng điều khiển theo VAI TRÒ của tài khoản đang đăng nhập.
 * `scope`: null = theo vai trò (mặc định), "MINE" = việc của tôi, "ALL" = toàn trung tâm.
 * Mọi số liệu đều do backend tính (bao gồm cả việc lọc "việc của tôi").
 */
async function loadDashboard(showSuccessMessage = false, scope = null) {
  const currentEpoch = state.sessionEpoch;
  const effectiveScope = scope !== null ? scope : (state.dashView === "mine" ? "MINE" : (state.dashView === "all" ? "ALL" : null));
  const query = effectiveScope ? `?scope=${encodeURIComponent(effectiveScope)}` : "";
  const res = await apiFetch(`/api/v1/warranty-tickets/workboard${query}`);
  if (currentEpoch !== state.sessionEpoch) return;
  if (!res.ok) {
    toastError(res, "Không tải được bảng điều khiển công việc.");
    return;
  }
  const wb = res.data || {};
  state.workboard = wb;

  renderDashHeader(wb);
  renderDashQuickActions(wb);
  const fourCards = buildDashboardFourCards(wb, state.dashView);
  renderDashCards(fourCards);
  renderWorkGroups(wb.groups);
  renderDashFocus(wb);
  renderDashAttention(wb);
  renderDashNotes(wb);
  renderDashViewButtons(wb);
  renderDashTable(wb, state.dashView);

  // Cập nhật số liệu phụ Khách hàng & Thiết bị
  const custCountEl = $("dash-cust-count");
  if (custCountEl && wb.totals) custCountEl.textContent = num(wb.totals.customers);
  const devCountEl = $("dash-device-count");
  if (devCountEl && wb.totals) devCountEl.textContent = num(wb.totals.devices);

  // Quản lý xem thêm biểu đồ phân bổ + các chip lọc nhanh theo trạng thái
  const chartPanel = $("dash-chart-panel");
  if (chartPanel) {
    const showChart = wb.role === "MANAGER";
    chartPanel.classList.toggle("hidden", !showChart);
    if (showChart) {
      renderStatusChart(wb.totals || {});
      renderStatusChips(wb.totals || {});
    }
  }

  if (showSuccessMessage) showToast("Đã cập nhật số liệu mới nhất.", "success", 3000);
}

/**
 * Đổi cách xem trên bảng "Phiếu đang xử lý".
 * - "mine"/"all": tải lại từ backend với phạm vi tương ứng (không lọc giả ở giao diện).
 * - "attention": xem danh sách phiếu cần chú ý (Quản lý) do backend tính sẵn.
 */
async function setDashView(view) {
  state.dashView = view || null;
  if (view !== "attention") {
    await loadDashboard(false, view === "mine" ? "MINE" : (view === "all" ? "ALL" : null));
    return;
  }
  const wb = state.workboard;
  if (!wb) return;
  renderDashViewButtons(wb);
  renderDashTable(wb, view);
}

/** Nút chuyển cách xem theo vai trò: Quản lý (Toàn trung tâm / Việc cần chú ý), Tiếp nhận (Việc tại quầy / Toàn bộ phiếu), KTV (Phiếu được giao / Toàn bộ phiếu). */
function renderDashViewButtons(wb) {
  const box = $("dash-view-buttons");
  if (!box) return;
  const role = wb.role || (state.session.user && state.session.user.role) || "";
  const view = state.dashView;
  let defs = [];
  if (role === "MANAGER") {
    defs = [
      { key: "all", label: "Toàn trung tâm", icon: "layout-list" },
      { key: "attention", label: "Việc cần chú ý", icon: "alert-triangle" },
    ];
  } else if (role === "RECEPTIONIST") {
    defs = [
      { key: "mine", label: "Việc tại quầy", icon: "user-check" },
      { key: "all", label: "Toàn bộ phiếu", icon: "layout-list" },
    ];
  } else if (role === "TECHNICIAN") {
    defs = [
      { key: "mine", label: "Phiếu được giao", icon: "user-check" },
      { key: "all", label: "Toàn bộ phiếu", icon: "layout-list" },
    ];
  } else {
    defs = [
      { key: "mine", label: "Việc của tôi", icon: "user-check" },
      { key: "all", label: "Toàn bộ phiếu", icon: "layout-list" },
    ];
  }
  const defaultKey = role === "MANAGER" ? "all" : "mine";
  const activeKey = view === "attention" ? "attention" : (view === "all" || view === "mine" ? view : defaultKey);
  box.innerHTML = defs
    .map((def) => `<button class="btn ${def.key === activeKey ? "btn-primary" : "btn-secondary"} btn-sm" onclick="setDashView('${def.key}')">
        <i data-lucide="${def.icon}" class="w-3.5 h-3.5"></i> ${def.label}</button>`)
    .join("");
  refreshIcons();
}

/** Mở màn "Phiếu bảo hành" với bộ lọc trạng thái (dùng từ bảng điều khiển), giữ nguyên phạm vi người dùng đang chọn. */
function openTicketsFiltered(status) {
  state._preserveTicketScope = true;
  ticketOnlyMine = state.dashUseMine;
  switchTab("tickets");
  applyStatusFilter(status || "ALL");
}

/**
 * Thao tác nhanh trên bảng điều khiển (mã do backend trả về, giao diện chỉ ánh xạ sang màn hình).
 */
function dashQuickAction(key) {
  switch (key) {
    case "receive":
      switchTab("tickets");
      setTimeout(() => {
        const el = $("wiz-serial");
        if (el) {
          el.focus();
          el.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }, 300);
      return;
    case "waiting_return":
      openTicketsFiltered("COMPLETED,REJECTED");
      return;
    case "waiting_inspect":
      openTicketsFiltered("RECEIVED");
      return;
    case "lookup":
      switchTab("lookup");
      setTimeout(() => {
        const el = $("lookup-input");
        if (el) el.focus();
      }, 300);
      return;
    case "all_tickets":
      openTicketsFiltered("ALL");
      return;
    case "ai":
      switchTab("ai");
      return;
    case "accounts":
      switchTab("accounts");
      return;
    default:
      showToast("Thao tác này chưa được gắn với màn hình nào.", "warning");
  }
}

/* ------------------- KHỐI NHÓM CÔNG VIỆC / VIỆC CẦN LÀM ------------------- */

/**
 * Nhãn nút cho một phiếu trong nhóm: ưu tiên câu chữ theo NGHIỆP VỤ của vai trò
 * (ví dụ kỹ thuật viên: "Bắt đầu kiểm tra") khi hành động được phép đúng như nhóm mong đợi.
 */
function groupActionLabel(group, row) {
  if (row.primary_action && row.primary_action.target === "ASSIGN") {
    return row.primary_action.button_label || "Phân công KTV";
  }
  const target = row.primary_action ? row.primary_action.target : null;
  if (group.action_label && (!group.action_target || group.action_target === target)) {
    return group.action_label;
  }
  return row.action_label || "Xem phiếu";
}

/** True nếu bấm nút trong nhóm sẽ chuyển trạng thái (ngược lại chỉ mở phiếu xem). */
function groupActionIsTransition(group, row) {
  return row.action_kind === "transition" && !!row.primary_action &&
    (!group.action_target || group.action_target === row.primary_action.target || row.primary_action.target === "ASSIGN");
}

/** Nhóm công việc: số lượng + danh sách phiếu cần xử lý ngay (mỗi phiếu 1 nút hành động). */
function renderWorkGroups(groups) {
  const box = $("dash-workload");
  if (!box) return;
  const items = Array.isArray(groups) ? groups : [];
  const hint = $("dash-workload-hint");
  const title = $("dash-workload-title");
  if (title) {
    title.innerHTML = '<i data-lucide="list-checks" class="w-4 h-4 text-indigo-600"></i> Công việc theo bước';
  }
  if (!items.length) {
    box.innerHTML = '<div class="text-sm text-slate-500">Vai trò này chưa có nhóm công việc nào.</div>';
    if (hint) hint.textContent = "";
    return;
  }
  box.innerHTML = items
    .map((group) => {
      const rows = Array.isArray(group.items) ? group.items : [];
      const head = `<button type="button" class="w-full text-left" onclick="openTicketsFiltered('${escapeHtml(group.status_filter || "")}')"
              title="Mở danh sách phiếu ở bước này">
          <div class="flex items-center justify-between gap-2">
            <span class="text-sm font-bold text-slate-800">${escapeHtml(group.label)}</span>
            <span class="text-lg font-bold font-mono ${group.count > 0 ? toneText(group.tone) : "text-slate-400"}">${group.count}</span>
          </div>
          <div class="text-xs text-slate-500 mt-1">${escapeHtml(group.description || "")}</div>
          <div class="text-xs text-slate-400 mt-1">Phạm vi: ${escapeHtml(group.scope_label || "")}</div>
        </button>`;
      const rowHtml = rows.length
        ? rows
            .map((row) => {
              const isTransition = groupActionIsTransition(group, row);
              const target = isTransition && row.primary_action ? row.primary_action.target : null;
              return `<div class="dash-work-item">
                <div class="min-w-0">
                  <div class="font-semibold text-slate-900 truncate">${escapeHtml(row.ticket_code)}</div>
                  <div class="text-xs text-slate-500 truncate">${escapeHtml(displayText(row.customer_name) || "–")} &bull; ${escapeHtml(displayText(row.product_name) || row.serial_number || "")}</div>
                </div>
                <button class="btn ${isTransition ? "btn-primary" : "btn-secondary"} btn-sm shrink-0"
                        onclick="handleTicketAction(${row.id}, ${target ? `'${target}'` : "null"})">
                  ${escapeHtml(groupActionLabel(group, row))}
                </button>
              </div>`;
            })
            .join("")
        : '<div class="text-xs text-slate-500">Không còn phiếu nào ở bước này.</div>';
      return `<div class="p-3.5 rounded-xl border border-slate-200 bg-slate-50 flex flex-col gap-2">${head}${rowHtml}</div>`;
    })
    .join("");
  if (hint) {
    hint.textContent = "Bấm số lượng để mở danh sách phiếu của bước đó; bấm nút trên từng phiếu để xử lý ngay.";
  }
  refreshIcons();
}

/** "Việc cần làm ngay": danh sách phiếu đã sắp theo thứ tự nghiệp vụ của vai trò. */
function renderDashFocus(wb) {
  const box = $("dash-focus");
  if (!box) return;
  const rows = Array.isArray(wb.focus) ? wb.focus : [];
  const hint = $("dash-focus-hint");
  if (hint) hint.textContent = `Thứ tự ưu tiên của ${wb.role_label || roleLabel(wb.role)} • ${rows.length} phiếu`;
  if (!rows.length) {
    box.innerHTML = '<div class="text-sm text-emerald-700 font-medium">Bạn không còn phiếu nào đang chờ xử lý.</div>';
    return;
  }
  box.innerHTML = rows
    .map((row, index) => {
      const isTransition = row.action_kind === "transition" && row.primary_action;
      const target = isTransition && row.primary_action ? row.primary_action.target : null;
      return `<div class="dash-focus-row">
        <span class="dash-focus-index">${index + 1}</span>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="font-semibold text-slate-900">${escapeHtml(row.ticket_code)}</span>
            ${statusBadge(row.status)}
            <span class="text-xs text-slate-500">${escapeHtml(row.serial_number || "–")}</span>
            <span class="text-xs text-slate-700 font-medium">${escapeHtml(displayText(row.product_name) || "")}</span>
          </div>
          <div class="text-xs text-slate-600 mt-1 truncate">
            ${escapeHtml(displayText(row.customer_name) || "–")} &bull; ${escapeHtml(row.customer_phone || "")} &bull; KTV: <span class="font-medium text-slate-800">${escapeHtml(ticketTechnicianName(row))}</span>
          </div>
        </div>
        <button class="btn ${isTransition ? "btn-primary" : "btn-secondary"} btn-sm shrink-0"
                onclick="handleTicketAction(${row.id}, ${target ? `'${target}'` : "null"})">
          ${escapeHtml(row.action_label || "Xem phiếu")}
        </button>
      </div>`;
    })
    .join("");
}

/** "Việc cần chú ý" (chỉ Quản lý): phiếu cần để mắt + lý do lấy từ dữ liệu thật. */
function renderDashAttention(wb) {
  const panel = $("dash-attention-panel");
  const box = $("dash-attention");
  const rows = Array.isArray(wb.attention) ? wb.attention : [];
  const show = wb.role === "MANAGER";
  if (panel) panel.classList.toggle("hidden", !show);
  if (!box) return;
  if (!show) {
    box.innerHTML = "";
    return;
  }
  if (!rows.length) {
    box.innerHTML = '<div class="text-sm text-emerald-700 font-medium">Không có phiếu nào cần chú ý.</div>';
    return;
  }
  box.innerHTML = rows
    .map(
      (row) => `<button type="button" class="dash-attention-row" onclick="openTicketModal(${row.ticket_id})">
        <div class="flex items-center justify-between gap-2">
          <span class="font-semibold text-slate-900">${escapeHtml(row.ticket_code)}</span>
          ${statusBadge(row.status)}
        </div>
        <div class="text-slate-800 font-semibold mt-1">${escapeHtml(displayText(row.customer_name) || "–")} &bull; ${escapeHtml(displayText(row.product_name) || row.serial_number || "")}</div>
        <div class="text-amber-800 font-medium text-xs mt-1">${escapeHtml(row.reason)}</div>
      </button>`
    )
    .join("");
}

/** Áp bộ lọc trạng thái cho danh sách phiếu (đổi màu nút lọc + tải lại dữ liệu). */
function applyStatusFilter(status) {
  const value = status || "ALL";
  document.querySelectorAll(".filter-status-btn").forEach((btn) => {
    btn.classList.remove("btn-primary");
    btn.classList.add("btn-secondary");
  });
  const activeBtn = document.querySelector(`.filter-status-btn[data-status="${value}"]`);
  if (activeBtn) {
    activeBtn.classList.remove("btn-secondary");
    activeBtn.classList.add("btn-primary");
  }
  loadTickets(value);
}

/** Mở modal chi tiết thiết bị theo ID hoặc Serial. */
async function openDeviceBySerialOrId(instanceId, serial) {
  if (instanceId) {
    if (!state.devices.length) await loadDevices();
    const d = state.devices.find((x) => x.id === instanceId);
    if (d) return openDeviceDetailModal(instanceId);
  }
  if (serial) {
    if (!state.devices.length) await loadDevices();
    let d = state.devices.find((x) => x.serial_number === serial);
    if (!d) {
      const res = await apiFetch(`/api/v1/product-instances/search?query=${encodeURIComponent(serial)}`);
      if (res.ok && Array.isArray(res.data) && res.data.length) {
        d = res.data[0];
        state.devices.push(d);
      }
    }
    if (d) return openDeviceDetailModal(d.id);
  }
  showToast("Không tìm thấy thông tin thiết bị.", "warning");
}

/** Nút hành động phụ của một dòng (chỉ hiện khi thực sự có bước khác được phép). */
function rowExtraActionsHtml(row) {
  const extras = (Array.isArray(row.available_actions) ? row.available_actions : []).filter(
    (action) => !row.primary_action || action.target !== row.primary_action.target
  );
  if (!extras.length) return "";
  return `<details class="row-more">
      <summary class="row-more-summary" title="Xem các thao tác khác">
        <i data-lucide="more-horizontal" class="w-4 h-4"></i>
        <span>Thao tác khác</span>
      </summary>
      <div class="row-more-menu">
        ${extras
          .map(
            (action) =>
              `<button class="btn btn-secondary btn-sm w-full justify-start text-xs" onclick="handleTicketAction(${row.id}, '${action.target}')">
                <i data-lucide="arrow-right" class="w-3.5 h-3.5"></i>
                <span>${escapeHtml(action.button_label)}</span>
              </button>`
          )
          .join("")}
      </div>
    </details>`;
}

/** Hiển thị đúng 1 thông điệp ngắn gọn trong cột "Việc cần làm" (phân biệt màu trung tính / vàng / đỏ). */
function renderNextActionCell(row, attentionReason) {
  // 1. Màu đỏ: lỗi thao tác hoặc vấn đề thực sự cần xử lý ngay (KTV đề xuất từ chối)
  if (row.rejection_proposal_note || (attentionReason && attentionReason.includes("đề xuất từ chối"))) {
    return `<div class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-rose-50 text-rose-800 border border-rose-200 text-xs font-semibold">
        <i data-lucide="alert-circle" class="w-3.5 h-3.5 text-rose-600 shrink-0"></i>
        <span>KTV đề xuất từ chối bảo hành</span>
      </div>`;
  }

  // 2. Màu vàng: thiếu phân công, thiếu kết quả kiểm tra hoặc dữ liệu cần bổ sung
  if (!row.assigned_technician_id) {
    return `<div class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-amber-50 text-amber-900 border border-amber-200 text-xs font-semibold">
        <i data-lucide="alert-triangle" class="w-3.5 h-3.5 text-amber-600 shrink-0"></i>
        <span>Chưa phân công KTV</span>
      </div>`;
  }

  if (row.status === "INSPECTING") {
    const hasDiag = Boolean((row.diagnosis_note || "").trim());
    const hasElig = row.is_warranty_eligible !== null && row.is_warranty_eligible !== undefined;
    if (!hasDiag || !hasElig) {
      return `<div class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-amber-50 text-amber-900 border border-amber-200 text-xs font-semibold">
          <i data-lucide="help-circle" class="w-3.5 h-3.5 text-amber-600 shrink-0"></i>
          <span>Cần ghi nhận chẩn đoán & ĐKBH</span>
        </div>`;
    }
    return `<div class="inline-flex items-center gap-1.5 text-slate-700 text-sm font-medium">
        <i data-lucide="check" class="w-4 h-4 text-emerald-600 shrink-0"></i>
        <span>Đã có chẩn đoán, chuẩn bị sửa</span>
      </div>`;
  }

  if (row.status === "REPAIRING") {
    const hasRepair = Boolean((row.repair_content || "").trim());
    const hasPass = row.repair_test_passed === true;
    if (!hasRepair || !hasPass) {
      return `<div class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-amber-50 text-amber-900 border border-amber-200 text-xs font-semibold">
          <i data-lucide="wrench" class="w-3.5 h-3.5 text-amber-600 shrink-0"></i>
          <span>Cần ghi nội dung sửa & kiểm tra</span>
        </div>`;
    }
    return `<div class="inline-flex items-center gap-1.5 text-slate-700 text-sm font-medium">
        <i data-lucide="check" class="w-4 h-4 text-emerald-600 shrink-0"></i>
        <span>Đã sửa xong, chuẩn bị hoàn tất</span>
      </div>`;
  }

  // 3. Màu trung tính: thông tin tiến độ bình thường (không coi mọi phiếu chờ trả là cảnh báo)
  if (row.status === "COMPLETED") {
    return `<div class="inline-flex items-center gap-1.5 text-slate-700 text-sm font-medium">
        <i data-lucide="clock" class="w-4 h-4 text-slate-500 shrink-0"></i>
        <span>Đang chờ khách nhận máy</span>
      </div>`;
  }

  if (row.status === "REJECTED") {
    return `<div class="inline-flex items-center gap-1.5 text-slate-700 text-sm font-medium">
        <i data-lucide="clock" class="w-4 h-4 text-slate-500 shrink-0"></i>
        <span>Đang chờ trả lại máy cho khách</span>
      </div>`;
  }

  if (row.status === "RECEIVED") {
    return `<div class="inline-flex items-center gap-1.5 text-slate-700 text-sm font-medium">
        <i data-lucide="user-check" class="w-4 h-4 text-slate-500 shrink-0"></i>
        <span>Đã giao KTV, chờ bắt đầu kiểm tra</span>
      </div>`;
  }

  if (row.status === "RETURNED") {
    return `<div class="inline-flex items-center gap-1.5 text-slate-500 text-sm">
        <i data-lucide="check-circle-2" class="w-4 h-4 text-slate-400 shrink-0"></i>
        <span>Phiếu đã đóng</span>
      </div>`;
  }

  return `<div class="text-slate-600 text-sm font-medium">${escapeHtml(statusLabel(row.status))}</div>`;
}

/** Bảng "Phiếu cần xử lý" / "Danh sách phiếu" / "Việc cần chú ý" - mỗi dòng 1 hành động chính theo quyền. */
function renderDashTable(wb, view) {
  const tbody = $("dash-active-body");
  if (!tbody) return;
  const isAttention = view === "attention";
  const lastCol = $("dash-active-last-col");
  if (lastCol) lastCol.textContent = isAttention ? "Lý do cần chú ý" : "Việc cần làm";

  const useMine = !isAttention && (view === "mine" || (view !== "all" && wb.role !== "MANAGER"));
  const rows = isAttention
    ? (Array.isArray(wb.attention) ? wb.attention : []).map((item) => ({
        ...item,
        id: item.ticket_id,
        _reason: item.reason,
      }))
    : (useMine ? wb.my_tickets || [] : wb.active_tickets || []);

  state.dashActiveRows = rows;
  state.dashAttention = Array.isArray(wb.attention) ? wb.attention : [];
  state.dashIsAttention = isAttention;
  state.dashUseMine = useMine;

  renderFilteredDashTable();
}

function setDashFilterStatus(status) {
  state.dashFilterStatus = status || "ALL";
  document.querySelectorAll(".dash-filter-btn").forEach((btn) => {
    const active = btn.getAttribute("data-dash-filter") === state.dashFilterStatus;
    btn.classList.toggle("btn-primary", active);
    btn.classList.toggle("btn-secondary", !active);
  });
  renderFilteredDashTable();
}

function filterDashTable() {
  const input = $("dash-table-search");
  state.dashSearchQuery = input ? input.value : "";
  renderFilteredDashTable();
}

function renderFilteredDashTable() {
  const tbody = $("dash-active-body");
  if (!tbody) return;
  const rows = state.dashActiveRows || [];
  const isAttention = state.dashIsAttention;
  const useMine = state.dashUseMine;
  const wb = state.workboard || {};
  const role = (state.session.user && state.session.user.role) || wb.role || "";

  const attentionList = state.dashAttention || [];
  const attentionMap = new Map();
  attentionList.forEach((a) => {
    attentionMap.set(a.ticket_id || a.id, a.reason);
  });

  const query = (state.dashSearchQuery || "").toLowerCase().trim();
  const filterStatus = state.dashFilterStatus || "ALL";

  // Cập nhật tiêu đề bảng theo bộ lọc và phạm vi
  const title = $("dash-active-title");
  if (title) {
    const scopeLabel = wb.scope_label || (useMine ? (role === "RECEPTIONIST" ? "Việc tại quầy" : "Phiếu được giao") : "Toàn trung tâm");
    if (isAttention) {
      title.innerHTML = `<i data-lucide="alert-triangle" class="w-5 h-5 text-amber-500"></i> Việc cần chú ý (${escapeHtml(scopeLabel)})`;
    } else if (filterStatus === "ALL" || filterStatus === "RETURNED") {
      title.innerHTML = `<i data-lucide="clipboard-list" class="w-5 h-5 text-indigo-600"></i> Danh sách phiếu (${escapeHtml(scopeLabel)})`;
    } else {
      title.innerHTML = `<i data-lucide="clipboard-list" class="w-5 h-5 text-indigo-600"></i> ${escapeHtml(
        useMine ? (role === "RECEPTIONIST" ? "Phiếu tại quầy tiếp nhận" : "Phiếu được giao cho tôi") : (wb.table_title || "Phiếu cần xử lý")
      )} (${escapeHtml(scopeLabel)})`;
    }
  }

  let filtered = rows;
  if (!isAttention) {
    if (filterStatus === "PROCESSING") {
      filtered = filtered.filter((r) => ["RECEIVED", "INSPECTING", "REPAIRING"].includes(r.status));
    } else if (filterStatus === "WAITING_RETURN") {
      filtered = filtered.filter((r) => ["COMPLETED", "REJECTED"].includes(r.status));
    } else if (filterStatus !== "ALL") {
      filtered = filtered.filter((r) => r.status === filterStatus);
    }
  }

  if (query) {
    filtered = filtered.filter((r) => {
      const code = String(r.ticket_code || "").toLowerCase();
      const serial = String(r.serial_number || "").toLowerCase();
      const cust = String(r.customer_name || "").toLowerCase();
      const phone = String(r.customer_phone || "").toLowerCase();
      const prod = String(r.product_name || "").toLowerCase();
      return (
        code.includes(query) ||
        serial.includes(query) ||
        cust.includes(query) ||
        phone.includes(query) ||
        prod.includes(query)
      );
    });
  }

  // Cập nhật số kết quả phù hợp trên thanh lọc
  const filterCountEl = $("dash-filter-count");
  if (filterCountEl) {
    filterCountEl.classList.remove("hidden");
    if (filtered.length !== rows.length) {
      filterCountEl.textContent = `Hiển thị ${num(filtered.length)} / ${num(rows.length)} phiếu (đang lọc)`;
    } else {
      filterCountEl.textContent = `Hiển thị ${num(rows.length)} / ${num(rows.length)} phiếu`;
    }
  }

  if (!filtered.length) {
    let emptyMsg = "Hiện không có phiếu nào cần xử lý.";
    if (query || filterStatus !== "ALL") {
      emptyMsg = "Không tìm thấy phiếu nào phù hợp với bộ lọc.";
    } else if (isAttention) {
      emptyMsg = "Không có phiếu nào cần chú ý.";
    } else if (role === "TECHNICIAN" && useMine) {
      emptyMsg = 'Bạn chưa được phân công phiếu nào. Bấm "Toàn bộ phiếu" để xem tất cả.';
    } else if (role === "RECEPTIONIST" && useMine) {
      emptyMsg = 'Hiện tại không có phiếu nào cần xử lý tại quầy. Bấm "Toàn bộ phiếu" để xem tất cả.';
    } else if (useMine) {
      emptyMsg = 'Bạn hiện không có phiếu nào đang xử lý. Bấm "Toàn bộ phiếu" để xem tất cả.';
    } else {
      emptyMsg = "Hiện không có phiếu nào cần xử lý trong trung tâm.";
    }
    setTableMessage("dash-active-body", 7, emptyMsg);
    return;
  }

  tbody.innerHTML = filtered
    .map((row) => {
      const isTransition = row.action_kind === "transition" && row.primary_action;
      const target = isTransition ? row.primary_action.target : null;
      const buttonLabel = row.primary_action ? row.primary_action.button_label : (row.action_label || "Xem chi tiết");

      return `<tr class="table-row">
        <td class="table-td">
          <button type="button" class="font-semibold text-slate-900 hover:text-indigo-600 transition-colors text-left text-sm"
                  onclick="openTicketModal(${row.id})" title="Bấm để xem chi tiết phiếu">
            ${escapeHtml(row.ticket_code)}
          </button>
          <div class="text-xs text-slate-400 mt-0.5">${fmtDateTime(row.created_at)}</div>
        </td>
        <td class="table-td">
          <div class="font-semibold text-slate-900">${escapeHtml(displayText(row.customer_name) || "–")}</div>
          <div class="text-xs text-slate-500 mt-0.5">${escapeHtml(row.customer_phone || "")}</div>
        </td>
        <td class="table-td">
          <div class="text-slate-800 font-medium text-sm leading-snug">${escapeHtml(displayText(row.product_name) || "–")}</div>
          <div class="mt-0.5">
            <button type="button" class="text-xs text-slate-500 hover:text-indigo-600 transition-colors text-left inline-block font-normal"
                    onclick="openDeviceBySerialOrId(${row.product_instance_id || "null"}, '${escapeHtml(row.serial_number || "")}')" title="Bấm để xem thông tin thiết bị">
              ${escapeHtml(row.serial_number || "–")}
            </button>
          </div>
        </td>
        <td class="table-td">${statusBadge(row.status)}</td>
        <td class="table-td text-sm">
          <div class="flex items-center gap-1.5">
            <i data-lucide="user" class="w-3.5 h-3.5 text-slate-400 shrink-0"></i>
            ${formatTechnicianCell(ticketTechnicianName(row))}
          </div>
        </td>
        <td class="table-td">
          ${renderNextActionCell(row, attentionMap.get(row.id))}
        </td>
        <td class="table-td text-right">
          <div class="flex flex-col items-end gap-1.5">
            <button class="btn ${isTransition ? "btn-primary" : "btn-secondary"} btn-sm"
                    onclick="handleTicketAction(${row.id}, ${target ? `'${target}'` : "null"})">
              <i data-lucide="${target === "ASSIGN" ? "user-plus" : (isTransition ? "arrow-right-circle" : "eye")}" class="w-4 h-4"></i>
              <span>${escapeHtml(buttonLabel)}</span>
            </button>
            ${rowExtraActionsHtml(row)}
          </div>
        </td>
      </tr>`;
    })
    .join("");
  refreshIcons();
}

/**
 * Bấm nút hành động của một phiếu (từ bảng điều khiển hoặc danh sách):
 * Nếu là phân công KTV -> mở form phân công ngay;
 * nếu là chuyển bước -> mở modal phiếu kèm hộp thoại xác nhận.
 */
function handleTicketAction(ticketId, targetStatus) {
  if (targetStatus === "ASSIGN") {
    openAssignModal(ticketId);
    return;
  }
  openTicketModal(ticketId, targetStatus ? { autoAction: targetStatus } : {});
}

/** Biểu đồ phân bổ trạng thái - dữ liệu thật từ API thống kê. */
function renderStatusChart(stats) {
  const canvas = $("statusDonutChart");
  if (!canvas || typeof Chart === "undefined") return;
  const data = STATUS_ORDER.map((code) => stats[code.toLowerCase()] || 0);
  const labels = STATUS_ORDER.map((code) => statusLabel(code));

  if (state.statusChart) {
    state.statusChart.data.labels = labels;
    state.statusChart.data.datasets[0].data = data;
    state.statusChart.update();
    return;
  }
  state.statusChart = new Chart(canvas, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{ data, backgroundColor: STATUS_COLORS, borderColor: "#0f172a", borderWidth: 3, hoverOffset: 4 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom", labels: { color: "#94A3B8", font: { family: "Plus Jakarta Sans", size: 11 }, padding: 12 } },
      },
      cutout: "68%",
    },
  });
}

function renderStatusChips(stats) {
  const box = $("dash-status-chips");
  if (!box) return;
  box.innerHTML = STATUS_ORDER.map((code, i) => {
    const value = stats[code.toLowerCase()] || 0;
    return `<span class="chip"><span class="w-2 h-2 rounded-full" style="background:${STATUS_COLORS[i]}"></span>${statusLabel(code)}: <strong class="font-mono text-white">${value}</strong></span>`;
  }).join("");
}

/* --------------------------- MÀN HÌNH: TRA CỨU BẢO HÀNH --------------------------- */
/**
 * Nút chọn nhanh một thiết bị (dùng chung cho màn Tra cứu và wizard tiếp nhận).
 * Hiển thị theo cách người dùng nhận ra thiết bị: sản phẩm + khách hàng + tình trạng bảo hành;
 * số sê-ri vẫn hiện ở dòng nhỏ để đối chiếu với tem trên máy.
 */
function deviceSampleButtonHtml(d, handlerName) {
  const w = warrantyInfoFor(d.warranty_end_date);
  return `<button type="button" class="btn btn-secondary btn-sm btn-stack text-left" onclick="${handlerName}('${escapeHtml(d.serial_number)}')">
      <span class="font-semibold text-slate-900 text-sm">${escapeHtml(displayText(d.product_name) || "Thiết bị")}</span>
      <span class="text-xs text-slate-600">${escapeHtml(displayText(d.customer_name) || "Chưa rõ khách hàng")} &bull; <span class="${w.textClass} font-semibold">${w.dot} ${w.label}</span></span>
      <span class="text-xs text-slate-500 font-mono">Số sê-ri: ${escapeHtml(d.serial_number)}</span>
    </button>`;
}

/** Nút chọn nhanh thiết bị để tra cứu (lấy từ API, không hard-code). */
async function refreshLookupSamples() {
  const box = $("lookup-samples");
  if (!box) return;
  if (!state.devices.length) {
    const res = await apiFetch("/api/v1/product-instances/?limit=8");
    if (res.ok) state.devices = res.data || [];
  }
  const samples = state.devices.slice(0, 4);
  box.innerHTML = samples.length
    ? samples.map((d) => deviceSampleButtonHtml(d, "useLookupSample")).join("")
    : '<span class="text-xs text-slate-500">Chưa có thiết bị nào trong hệ thống.</span>';
  refreshIcons();
}

function useLookupSample(serial) {
  $("lookup-input").value = serial;
  runLookup();
}

function clearLookup() {
  $("lookup-input").value = "";
  $("lookup-result").innerHTML = "";
}

/** Tra cứu: nhận cả SỐ SÊ-RI và MÃ PHIẾU (mã phiếu bắt đầu bằng TK-). */
async function runLookup() {
  const box = $("lookup-result");
  const keyword = ($("lookup-input").value || "").trim();
  if (!keyword) {
    showToast("Vui lòng nhập số sê-ri hoặc mã phiếu cần tra cứu.", "warning");
    return;
  }
  box.innerHTML = '<div class="glass-panel p-5 text-sm text-slate-500">Đang tra cứu...</div>';
  await ensureCountData();   // có sẵn thiết bị + phiếu để card kết quả hiện đúng lịch sử phiếu
  if (/^TK-/i.test(keyword)) {
    await lookupTicketByCode(keyword.toUpperCase());
  } else {
    await lookupDeviceBySerial(keyword);
  }
  refreshIcons();
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/** Tra cứu theo số sê-ri -> card thông tin bảo hành. */
async function lookupDeviceBySerial(serial) {
  const box = $("lookup-result");
  const res = await apiFetch(`/api/v1/product-instances/by-serial/${encodeURIComponent(serial)}`);
  if (res.status === 404) {
    box.innerHTML = lookupNotFoundCard(serial,
      "Số sê-ri này chưa được đăng ký. Nếu đây là máy mới, hãy dùng nút <strong>Tiếp nhận thiết bị</strong> ở Tổng quan để đăng ký thiết bị và tạo phiếu bảo hành.");
    return;
  }
  if (!res.ok) {
    box.innerHTML = lookupNotFoundCard(serial, escapeHtml(errorMessage(res.status, res.data)));
    return;
  }
  const d = res.data;
  const tickets = state.tickets.filter((t) => t.serial_number === d.serial_number);
  box.innerHTML = deviceWarrantyCardHtml(d, warrantyInfoFor(d.warranty_end_date), tickets);
}

/** Card "Thông tin bảo hành" (dùng chung cho màn Tra cứu). */
function deviceWarrantyCardHtml(d, w, tickets) {
  const warrantyBoxClass = w.days !== null && w.days >= 0 ? "bg-emerald-50 border-emerald-200" : "bg-rose-50 border-rose-200";
  const warrantyDetail = w.days === null
    ? "Chưa có ngày hết hạn"
    : (w.days >= 0 ? `Hạn đến: ${fmtDate(d.warranty_end_date)} (còn ${w.days} ngày)` : `Đã hết hạn ngày ${fmtDate(d.warranty_end_date)} (quá ${Math.abs(w.days)} ngày)`);
  const serialArg = escapeHtml(d.serial_number);

  return `
    <div class="glass-panel p-5">
      <div class="flex flex-wrap items-center justify-between gap-2 mb-4">
        <h3 class="section-title"><i data-lucide="shield-check" class="w-4 h-4 text-emerald-600"></i> Thông tin bảo hành</h3>
        <button class="btn btn-secondary btn-sm" onclick="openDeviceDetailModal(${d.id})"><i data-lucide="info" class="w-3.5 h-3.5"></i> Xem chi tiết thiết bị</button>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-xs mb-4">
        <div class="p-3 bg-slate-50 rounded-xl border border-slate-200">
          <div class="text-slate-500 font-semibold mb-1">Sản phẩm</div>
          <div class="font-bold text-slate-900">${escapeHtml(displayText(d.product_name) || "–")}</div>
          <div class="text-slate-500 mt-1">Hãng: <span class="text-slate-800">${escapeHtml(displayText(d.product_brand) || "–")}</span></div>
        </div>
        <div class="p-3 bg-slate-50 rounded-xl border border-slate-200">
          <div class="text-slate-500 font-semibold mb-1">Số sê-ri</div>
          <div class="font-mono font-bold text-indigo-700">${escapeHtml(d.serial_number)}</div>
        </div>
        <div class="p-3 bg-slate-50 rounded-xl border border-slate-200">
          <div class="text-slate-500 font-semibold mb-1">Khách hàng</div>
          <div class="font-bold text-slate-900">${escapeHtml(displayText(d.customer_name) || "–")}</div>
          <div class="text-slate-600 mt-1 font-mono">${escapeHtml(d.customer_phone || "")}</div>
        </div>
        <div class="p-3 bg-slate-50 rounded-xl border border-slate-200">
          <div class="text-slate-500 font-semibold mb-1">Ngày mua</div>
          <div class="font-mono text-slate-800">${fmtDate(d.purchase_date)}</div>
        </div>
        <div class="p-3 bg-slate-50 rounded-xl border border-slate-200">
          <div class="text-slate-500 font-semibold mb-1">Hạn bảo hành</div>
          <div class="font-mono text-slate-800">${fmtDate(d.warranty_end_date)}</div>
        </div>
        <div class="p-3 rounded-xl border ${warrantyBoxClass}">
          <div class="text-slate-500 font-semibold mb-1">Trạng thái bảo hành</div>
          <div class="text-base font-bold ${w.textClass}">${w.dot} ${w.label.toUpperCase()}</div>
          <div class="text-slate-600 mt-1 font-medium">${warrantyDetail}</div>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        ${hasPerm("ticket.create") ? `<button class="btn btn-primary" onclick="startTicketForSerial('${serialArg}')"><i data-lucide="file-plus-2" class="w-4 h-4"></i> Tạo phiếu bảo hành cho thiết bị này</button>` : ""}
        <button class="btn btn-secondary" onclick="runLookupCheck('${serialArg}')"><i data-lucide="search-check" class="w-4 h-4"></i> Đối chiếu điều kiện bảo hành</button>
        <span class="text-xs text-slate-500">${tickets.length ? `Thiết bị đã có ${tickets.length} phiếu bảo hành` : "Thiết bị chưa có phiếu bảo hành nào"}</span>
      </div>

      <div id="lookup-check-result" class="mt-3"></div>
      ${tickets.length ? `
      <div class="mt-3 pt-3 border-t border-slate-200">
        <div class="text-xs text-slate-600 font-semibold mb-2">Phiếu bảo hành của thiết bị:</div>
        <div class="flex flex-wrap gap-2">
          ${tickets.map((t) => `<button class="btn btn-secondary btn-sm" onclick="openTicketModal(${t.id})"><span class="font-mono font-bold text-indigo-700">${escapeHtml(t.ticket_code)}</span> ${statusBadge(t.status)}</button>`).join("")}
        </div>
      </div>` : ""}
    </div>`;
}

/** Thẻ thông báo khi không tìm thấy dữ liệu tra cứu. */
function lookupNotFoundCard(keyword, hint) {
  return `
    <div class="glass-panel p-5 border border-amber-300 bg-amber-50/50">
      <div class="text-sm font-bold text-amber-900 mb-1">Không tìm thấy "${escapeHtml(keyword)}" trong hệ thống</div>
      <p class="text-xs text-slate-600">${hint}</p>
    </div>`;
}

/** Tra cứu theo mã phiếu -> card tình trạng phiếu + thiết bị. */
async function lookupTicketByCode(code) {
  const box = $("lookup-result");
  const res = await apiFetch(`/api/v1/warranty-tickets/code/${encodeURIComponent(code)}`);
  if (res.status === 404) {
    box.innerHTML = lookupNotFoundCard(code,
      "Mã phiếu không đúng hoặc phiếu không tồn tại. Mã phiếu có dạng <span class=\"font-mono\">TK-YYYYMMDD-XXXX</span>.");
    return;
  }
  if (!res.ok) {
    box.innerHTML = lookupNotFoundCard(code, escapeHtml(errorMessage(res.status, res.data)));
    return;
  }
  const t = res.data;
  const w = warrantyInfoFor(t.warranty_end_date);
  const handler = ticketTechnicianName(t);
  box.innerHTML = `
    <div class="glass-panel p-5">
      <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h3 class="section-title"><i data-lucide="file-text" class="w-4 h-4 text-indigo-600"></i> Phiếu bảo hành <span class="font-mono ml-1 text-indigo-700">${escapeHtml(t.ticket_code)}</span></h3>
        <button class="btn btn-primary btn-sm" onclick="openTicketModal(${t.id})"><i data-lucide="arrow-up-right" class="w-3.5 h-3.5"></i> Mở phiếu để xử lý</button>
      </div>

      ${ticketProgressHtml(t.status)}

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-xs mt-4">
        <div class="p-3 bg-slate-50 rounded-xl border border-slate-200">
          <div class="text-slate-500 font-semibold mb-1">Khách hàng</div>
          <div class="font-bold text-slate-900">${escapeHtml(displayText(t.customer_name) || "–")}</div>
        </div>
        <div class="p-3 bg-slate-50 rounded-xl border border-slate-200">
          <div class="text-slate-500 font-semibold mb-1">Thiết bị (số sê-ri)</div>
          <div class="font-mono font-bold text-indigo-700">${escapeHtml(t.serial_number || "–")}</div>
          <div class="text-slate-600 mt-1 font-medium">${escapeHtml(displayText(t.product_name) || "")}</div>
        </div>
        <div class="p-3 bg-slate-50 rounded-xl border border-slate-200">
          <div class="text-slate-500 font-semibold mb-1">Tình trạng bảo hành của thiết bị</div>
          <div class="${w.textClass} font-bold">${w.dot} ${w.label}</div>
          <div class="text-slate-600 mt-1">Hạn: <span class="font-mono font-medium">${fmtDate(t.warranty_end_date)}</span></div>
        </div>
        <div class="p-3 bg-slate-50 rounded-xl border border-slate-200">
          <div class="text-slate-500 font-semibold mb-1">Ngày tiếp nhận</div>
          <div class="font-mono text-slate-800 font-medium">${fmtDateTime(t.created_at)}</div>
        </div>
        <div class="p-3 bg-slate-50 rounded-xl border border-slate-200">
          <div class="text-slate-500 font-semibold mb-1">KTV phụ trách</div>
          <div class="text-slate-900 font-medium">${formatTechnicianCell(handler)}</div>
        </div>
        <div class="p-3 bg-slate-50 rounded-xl border border-slate-200">
          <div class="text-slate-500 font-semibold mb-1">Loại lỗi</div>
          <div class="text-slate-900 font-medium">${escapeHtml(categoryName(t.error_category_id))}</div>
        </div>
      </div>

      <div class="mt-3">
        <div class="text-xs font-bold text-slate-700 mb-1">Nội dung sự cố khách báo</div>
        <div class="text-sm text-slate-800 p-3 bg-slate-50 rounded-xl border border-slate-200 leading-relaxed">${escapeHtml(humanizeText(t.issue_description) || "–")}</div>
      </div>
    </div>`;
}

/** Đối chiếu điều kiện bảo hành theo đúng nghiệp vụ backend (chỉ hiển thị kết luận). */
async function runLookupCheck(serial) {
  const box = $("lookup-check-result");
  if (!box) return;
  box.innerHTML = '<span class="text-xs text-slate-500">Đang đối chiếu...</span>';
  const res = await apiFetch("/api/v1/debug/check-warranty", {
    method: "POST",
    body: { serial_number: serial, check_date: todayISO() },
  });
  if (!res.ok) {
    box.innerHTML = `<span class="text-xs text-rose-700">${escapeHtml(errorMessage(res.status, res.data))}</span>`;
    return;
  }
  const data = res.data;
  const valid = data.is_valid === true;
  const traces = Array.isArray(data.debug_traces) ? data.debug_traces : [];
  box.innerHTML = `
    <div class="p-3 rounded-xl border text-xs ${valid ? "bg-emerald-50 border-emerald-200 text-emerald-900" : "bg-rose-50 border-rose-200 text-rose-900"}">
      <div class="font-bold">${valid ? "Đủ điều kiện bảo hành" : "Không đủ điều kiện bảo hành"}</div>
      <div class="mt-1 text-xs">Đối chiếu ngày ${fmtDate(data.check_date)}: ${escapeHtml(humanizeText(data.status_message))}</div>
    </div>
    ${traces.length ? `
    <details class="mt-2 rounded-xl border border-slate-200 bg-slate-50">
      <summary class="px-3 py-2 text-xs font-semibold text-slate-600 cursor-pointer">Thông tin đối chiếu chi tiết (chỉ cần khi trao đổi với bộ phận kỹ thuật)</summary>
      <div class="px-3 pb-3 font-mono text-xs text-slate-600 space-y-0.5">
        ${traces.map((s) => `<div>${escapeHtml(humanizeTraceStep(s))}</div>`).join("")}
      </div>
    </details>` : ""}`;
}

/** Từ màn Tra cứu: bắt đầu tạo phiếu cho thiết bị này (mở wizard ở bước 1 và tra sẵn). */
function startTicketForSerial(serial) {
  switchTab("tickets");
  setTimeout(() => {
    const input = $("wiz-serial");
    if (input) {
      input.value = serial;
      wizardLookupSerial();
    }
  }, 300);
}


/* --------------------------- MÀN HÌNH: KHÁCH HÀNG --------------------------- */
async function loadCustomers() {
  setTableLoading("customers-table-body", 7);
  const res = await apiFetch("/api/v1/customers/");
  if (!res.ok) {
    setTableMessage("customers-table-body", 7, "Không tải được danh sách khách hàng.");
    toastError(res, "Không tải được danh sách khách hàng.");
    return;
  }
  state.customers = Array.isArray(res.data) ? res.data : [];
  await ensureCountData();
  renderCustomers(state.customers);
}

function renderCustomers(items) {
  const tbody = $("customers-table-body");
  if (!tbody) return;
  if (!items.length) {
    setTableMessage("customers-table-body", 7, "Chưa có khách hàng nào trong hệ thống.");
    return;
  }
  tbody.innerHTML = items.map((c) => {
    const deviceCount = countDevicesOfCustomer(c.id);
    const ticketCount = countTicketsOfCustomer(c.id);
    return `
    <tr class="table-row">
      <td class="table-td font-bold text-slate-900">${escapeHtml(displayText(c.full_name))}</td>
      <td class="table-td font-mono font-bold text-indigo-700">${escapeHtml(c.phone)}</td>
      <td class="table-td text-slate-600">${escapeHtml(c.email || "–")}</td>
      <td class="table-td text-slate-600">${escapeHtml(c.address || "–")}</td>
      <td class="table-td text-center font-mono font-bold text-slate-800">${deviceCount}</td>
      <td class="table-td text-center font-mono font-bold text-indigo-700">${ticketCount}</td>
      <td class="table-td text-right whitespace-nowrap">
        <button class="btn btn-secondary btn-sm" onclick="openCustomerDetailModal(${c.id})"><i data-lucide="info" class="w-3.5 h-3.5"></i> Chi tiết</button>
        ${hasPerm("customer.update") ? `<button class="btn btn-secondary btn-sm ml-1" onclick="openCustomerModal(${c.id})"><i data-lucide="pencil" class="w-3.5 h-3.5"></i> Sửa</button>` : ""}
        ${hasPerm("customer.delete") ? `<button class="btn btn-danger btn-sm ml-1" onclick="deleteCustomer(${c.id})"><i data-lucide="trash-2" class="w-3.5 h-3.5"></i> Xóa</button>` : ""}
      </td>
    </tr>`;
  }).join("");
  refreshIcons();
}

/** Số thiết bị của một khách hàng — đếm từ dữ liệu API đã tải (không hard-code). */
function countDevicesOfCustomer(customerId) {
  return state.devices.filter((d) => d.customer_id === customerId).length;
}

/** Số phiếu bảo hành của một khách hàng — đếm từ dữ liệu API đã tải. */
function countTicketsOfCustomer(customerId) {
  return state.tickets.filter((t) => t.customer_id === customerId).length;
}

/** Số thiết bị đang quản lý theo một sản phẩm — đếm từ dữ liệu API đã tải. */
function countDevicesOfProduct(productId) {
  return state.devices.filter((d) => d.product_id === productId).length;
}

/**
 * Bảo đảm đã có danh sách thiết bị + phiếu để hiển thị số lượng ở bảng Khách hàng/Sản phẩm.
 * Dùng đúng API đang có, không tạo dữ liệu mới.
 */
async function ensureCountData() {
  if (!state.devices.length) {
    const resDevices = await apiFetch("/api/v1/product-instances/");
    if (resDevices.ok) state.devices = resDevices.data || [];
  }
  if (!state.tickets.length) {
    const resTickets = await apiFetch("/api/v1/warranty-tickets/");
    if (resTickets.ok) state.tickets = resTickets.data || [];
  }
}

function searchCustomers() {
  const keyword = ($("customer-search-input").value || "").trim().toLowerCase();
  if (!keyword) {
    renderCustomers(state.customers);
    return;
  }
  const filtered = state.customers.filter((c) =>
    (c.full_name || "").toLowerCase().includes(keyword) || (c.phone || "").includes(keyword));
  if (!filtered.length) {
    setTableMessage("customers-table-body", 7, `Không tìm thấy khách hàng nào khớp với "${escapeHtml(keyword)}".`);
    return;
  }
  renderCustomers(filtered);
}

/** Modal chi tiết khách hàng: thông tin + thiết bị + phiếu bảo hành của khách. */
async function openCustomerDetailModal(customerId) {
  const c = state.customers.find((x) => x.id === customerId);
  if (!c) {
    showToast("Không tìm thấy khách hàng này. Hãy làm mới danh sách.", "warning");
    return;
  }
  await ensureCountData();
  const devices = state.devices.filter((d) => d.customer_id === customerId);
  const tickets = state.tickets.filter((t) => t.customer_id === customerId);

  $("customer-detail-title").textContent = `Chi tiết khách hàng: ${displayText(c.full_name)}`;
  const infoCell = (label, value, mono = false) => `
    <div class="p-3 bg-slate-50 rounded-xl border border-slate-200">
      <div class="text-xs text-slate-500 font-semibold mb-1">${label}</div>
      <div class="font-bold text-slate-900${mono ? " font-mono text-indigo-700" : ""}">${value}</div>
    </div>`;

  const deviceRows = devices.length
    ? devices.map((d) => `
      <tr class="table-row">
        <td class="table-td font-mono font-bold text-indigo-700">${escapeHtml(d.serial_number)}</td>
        <td class="table-td text-slate-900 font-medium">${escapeHtml(displayText(d.product_name) || "–")}</td>
        <td class="table-td text-slate-600 font-mono text-xs">${fmtDate(d.warranty_end_date)}</td>
        <td class="table-td">${warrantyStatusHtml(d.warranty_end_date)}</td>
        <td class="table-td text-right whitespace-nowrap">
          <button class="btn btn-secondary btn-sm" onclick="closeModal('customer-detail-modal'); openDeviceDetailModal(${d.id})"><i data-lucide="info" class="w-3.5 h-3.5"></i> Chi tiết thiết bị</button>
        </td>
      </tr>`).join("")
    : '<tr><td class="table-msg" colspan="5">Khách hàng chưa có thiết bị nào.</td></tr>';

  const ticketRows = tickets.length
    ? tickets.map((t) => `
      <tr class="table-row">
        <td class="table-td font-mono font-bold text-indigo-700">${escapeHtml(t.ticket_code)}</td>
        <td class="table-td">${statusBadge(t.status)}</td>
        <td class="table-td text-slate-900 font-medium">${escapeHtml(displayText(t.product_name) || "–")}</td>
        <td class="table-td text-slate-600 font-mono text-xs">${fmtDate(t.received_date)}</td>
        <td class="table-td text-right whitespace-nowrap">
          <button class="btn btn-secondary btn-sm" onclick="closeModal('customer-detail-modal'); openTicketModal(${t.id})"><i data-lucide="file-text" class="w-3.5 h-3.5"></i> Xem phiếu</button>
        </td>
      </tr>`).join("")
    : '<tr><td class="table-msg" colspan="5">Khách hàng chưa có phiếu bảo hành nào.</td></tr>';

  $("customer-detail-body").innerHTML = `
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
      ${infoCell("Số điện thoại", escapeHtml(c.phone), true)}
      ${infoCell("Email", escapeHtml(c.email || "–"))}
      ${infoCell("Số thiết bị", String(devices.length), true)}
      ${infoCell("Số phiếu bảo hành", String(tickets.length), true)}
    </div>
    <div class="p-3 bg-slate-50 rounded-xl border border-slate-200">
      <div class="text-xs text-slate-500 font-semibold mb-1">Địa chỉ</div>
      <div class="font-medium text-slate-800">${escapeHtml(c.address || "–")}</div>
    </div>

    <div>
      <div class="text-xs font-bold text-slate-700 mb-2 flex items-center gap-1.5"><i data-lucide="hard-drive" class="w-3.5 h-3.5 text-indigo-600"></i> Thiết bị của khách (${devices.length})</div>
      <div class="overflow-x-auto rounded-xl border border-slate-200">
        <table class="w-full min-w-[620px]">
          <thead><tr>
            <th class="table-th">Số sê-ri</th><th class="table-th">Sản phẩm</th><th class="table-th">Hạn bảo hành</th><th class="table-th">Tình trạng</th><th class="table-th text-right">Thao tác</th>
          </tr></thead>
          <tbody>${deviceRows}</tbody>
        </table>
      </div>
    </div>

    <div>
      <div class="text-xs font-bold text-slate-700 mb-2 flex items-center gap-1.5"><i data-lucide="file-text" class="w-3.5 h-3.5 text-indigo-600"></i> Phiếu bảo hành của khách (${tickets.length})</div>
      <div class="overflow-x-auto rounded-xl border border-slate-200">
        <table class="w-full min-w-[620px]">
          <thead><tr>
            <th class="table-th">Mã phiếu</th><th class="table-th">Trạng thái</th><th class="table-th">Sản phẩm</th><th class="table-th">Ngày tiếp nhận</th><th class="table-th text-right">Thao tác</th>
          </tr></thead>
          <tbody>${ticketRows}</tbody>
        </table>
      </div>
    </div>`;
  openModal("customer-detail-modal");
}

function openCustomerModal(customerId = null) {
  clearFieldErrors(["cust-name", "cust-phone", "cust-email"]);
  $("cust-id").value = "";
  $("cust-name").value = "";
  $("cust-phone").value = "";
  $("cust-email").value = "";
  $("cust-address").value = "";

  if (customerId) {
    const c = state.customers.find((x) => x.id === customerId);
    if (!c) {
      showToast("Không tìm thấy khách hàng cần sửa. Hãy làm mới danh sách.", "warning");
      return;
    }
    $("customer-modal-title").textContent = `Sửa khách hàng: ${displayText(c.full_name)}`;
    $("cust-id").value = c.id;
    $("cust-name").value = c.full_name || "";
    $("cust-phone").value = c.phone || "";
    $("cust-email").value = c.email || "";
    $("cust-address").value = c.address || "";
  } else {
    $("customer-modal-title").textContent = "Thêm khách hàng";
  }
  openModal("customer-modal");
}

async function submitCustomerForm(event) {
  event.preventDefault();
  const submitBtn = event.target ? event.target.querySelector("button[type=submit]") : null;
  const id = $("cust-id").value;
  const payload = {
    full_name: ($("cust-name").value || "").trim(),
    phone: ($("cust-phone").value || "").trim(),
    email: ($("cust-email").value || "").trim() || null,
    address: ($("cust-address").value || "").trim() || null,
  };

  clearFieldErrors(["cust-name", "cust-phone", "cust-email"]);
  const errors = validateCustomerForm(payload);
  if (Object.keys(errors).length) {
    Object.entries(errors).forEach(([field, msg]) => setFieldError(field, msg));
    showToast("Vui lòng kiểm tra lại thông tin khách hàng.", "warning");
    return;
  }

  if (submitBtn) submitBtn.disabled = true;
  try {
    const res = id
      ? await apiFetch(`/api/v1/customers/${id}`, { method: "PUT", body: payload })
      : await apiFetch("/api/v1/customers/", { method: "POST", body: payload });

    if (!res.ok) {
      toastError(res, id ? "Không cập nhật được khách hàng." : "Không thêm được khách hàng.");
      return;
    }
    closeModal("customer-modal");
    const shownName = displayText(payload.full_name);
    showToast(id ? `Đã cập nhật khách hàng "${escapeHtml(shownName)}".` : `Đã thêm khách hàng "${escapeHtml(shownName)}".`, "success");
    await loadCustomers();
    await loadReferenceData();
    await loadDashboard();
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

function deleteCustomer(customerId) {
  if (!hasPerm("customer.delete")) {
    showToast("Chỉ quản lý được xóa khách hàng.", "warning");
    return;
  }
  const c = state.customers.find((x) => x.id === customerId);
  const name = c ? displayText(c.full_name) : "khách hàng này";
  showActionModal({
    title: "Xóa khách hàng",
    message: `Bạn có chắc muốn xóa khách hàng <strong>${escapeHtml(name)}</strong>?<br>
      <span class="text-xs text-slate-400">Lưu ý: khách hàng còn thiết bị hoặc phiếu bảo hành sẽ không xóa được. Khi đó hệ thống sẽ báo rõ số lượng còn lại để bạn xử lý trước.</span>`,
    confirmLabel: "Xóa khách hàng",
    danger: true,
    onConfirm: async () => {
      const res = await apiFetch(`/api/v1/customers/${customerId}`, { method: "DELETE" });
      if (!res.ok) {
        toastError(res, "Không thể xóa khách hàng.");
        return;
      }
      showToast(`Đã xóa khách hàng "${name}".`, "success");
      await loadCustomers();
      await loadReferenceData();
      await loadDashboard();
    },
  });
}

/* --------------------------- MÀN HÌNH: DANH MỤC MÁY --------------------------- */
async function loadProducts() {
  setTableLoading("products-table-body", 6);
  const res = await apiFetch("/api/v1/products/");
  if (!res.ok) {
    setTableMessage("products-table-body", 6, "Không tải được danh mục máy.");
    toastError(res, "Không tải được danh mục máy.");
    return;
  }
  state.products = Array.isArray(res.data) ? res.data : [];
  await ensureCountData();
  renderProducts(state.products);
  populateProductDatalist();
}

function renderProducts(items) {
  const tbody = $("products-table-body");
  if (!tbody) return;
  if (!items.length) {
    setTableMessage("products-table-body", 6, "Chưa có dòng máy nào trong danh mục.");
    return;
  }
  tbody.innerHTML = items.map((p) => `
    <tr class="table-row">
      <td class="table-td font-bold text-slate-900">${escapeHtml(displayText(p.name))}</td>
      <td class="table-td text-slate-700 font-medium">${escapeHtml(displayText(p.brand) || "–")}</td>
      <td class="table-td text-slate-700">${escapeHtml(p.category || "–")}</td>
      <td class="table-td text-emerald-700 font-semibold">${p.warranty_duration_months} tháng</td>
      <td class="table-td text-center font-mono font-bold text-slate-800">${countDevicesOfProduct(p.id)}</td>
      <td class="table-td text-right whitespace-nowrap">
        ${hasPerm("product.manage") ? `<button class="btn btn-secondary btn-sm" onclick="openProductModal(${p.id})"><i data-lucide="pencil" class="w-3.5 h-3.5"></i> Sửa</button>
        <button class="btn btn-danger btn-sm ml-1" onclick="deleteProduct(${p.id})"><i data-lucide="trash-2" class="w-3.5 h-3.5"></i> Xóa</button>` : `<span class="text-xs text-slate-500">Chỉ xem danh mục</span>`}
      </td>
    </tr>`).join("");
  refreshIcons();
}

function searchProducts() {
  const keyword = ($("product-search-input").value || "").trim().toLowerCase();
  if (!keyword) {
    renderProducts(state.products);
    return;
  }
  const filtered = state.products.filter((p) =>
    (p.name || "").toLowerCase().includes(keyword) ||
    (p.brand || "").toLowerCase().includes(keyword) ||
    (p.category || "").toLowerCase().includes(keyword));
  if (!filtered.length) {
    setTableMessage("products-table-body", 6, `Không tìm thấy dòng máy nào khớp với "${escapeHtml(keyword)}".`);
    return;
  }
  renderProducts(filtered);
}

function populateProductDatalist() {
  const dl = $("list-product-names");
  if (!dl) return;
  // value = tên gốc trong CSDL (để khi lưu vẫn khớp đúng sản phẩm), label = tên hiển thị tiếng Việt
  dl.innerHTML = state.products
    .map((p) => `<option value="${escapeHtml(p.name)}" label="${escapeHtml(displayText(p.name))}"></option>`)
    .join("");
}

function openProductModal(productId = null) {
  clearFieldErrors(["prod-name", "prod-months"]);
  $("prod-id").value = "";
  $("prod-name").value = "";
  $("prod-brand").value = "";
  $("prod-category").value = "";
  $("prod-months").value = "12";
  $("prod-description").value = "";

  if (productId) {
    const p = state.products.find((x) => x.id === productId);
    if (!p) {
      showToast("Không tìm thấy dòng máy cần sửa. Hãy làm mới danh sách.", "warning");
      return;
    }
    $("product-modal-title").textContent = `Sửa dòng máy: ${displayText(p.name)}`;
    $("prod-id").value = p.id;
    $("prod-name").value = p.name || "";
    $("prod-brand").value = p.brand || "";
    $("prod-category").value = p.category || "";
    $("prod-months").value = p.warranty_duration_months || 12;
    $("prod-description").value = p.description || "";
  } else {
    $("product-modal-title").textContent = "Thêm dòng máy";
  }
  openModal("product-modal");
}

async function submitProductForm(event) {
  event.preventDefault();
  const submitBtn = event.target ? event.target.querySelector("button[type=submit]") : null;
  const id = $("prod-id").value;
  const months = parseInt($("prod-months").value, 10);
  const payload = {
    name: ($("prod-name").value || "").trim(),
    brand: ($("prod-brand").value || "").trim() || null,
    category: ($("prod-category").value || "").trim() || null,
    warranty_duration_months: months,
    description: ($("prod-description").value || "").trim() || null,
  };

  clearFieldErrors(["prod-name", "prod-months"]);
  let hasError = false;
  if (!payload.name) { setFieldError("prod-name", "Vui lòng nhập tên máy (dòng máy)."); hasError = true; }
  if (!months || months < 1 || months > 120) { setFieldError("prod-months", "Thời hạn bảo hành phải từ 1 đến 120 tháng."); hasError = true; }
  if (hasError) {
    showToast("Vui lòng kiểm tra lại thông tin dòng máy.", "warning");
    return;
  }

  if (submitBtn) submitBtn.disabled = true;
  try {
    const res = id
      ? await apiFetch(`/api/v1/products/${id}`, { method: "PUT", body: payload })
      : await apiFetch("/api/v1/products/", { method: "POST", body: payload });

    if (!res.ok) {
      toastError(res, id ? "Không cập nhật được dòng máy." : "Không thêm được dòng máy.");
      return;
    }
    closeModal("product-modal");
    const shownProduct = displayText(payload.name);
    showToast(id ? `Đã cập nhật dòng máy "${escapeHtml(shownProduct)}".` : `Đã thêm dòng máy "${escapeHtml(shownProduct)}".`, "success");
    await loadProducts();
    await loadDashboard();
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

function deleteProduct(productId) {
  if (!hasPerm("product.manage")) {
    showToast("Chỉ quản lý được xóa dòng máy.", "warning");
    return;
  }
  const p = state.products.find((x) => x.id === productId);
  const name = p ? displayText(p.name) : "dòng máy này";
  showActionModal({
    title: "Xóa dòng máy",
    message: `Bạn có chắc muốn xóa dòng máy <strong>${escapeHtml(name)}</strong>?<br>
      <span class="text-xs text-slate-400">Lưu ý: dòng máy đang có máy đăng ký theo số sê-ri sẽ không xóa được. Hãy xử lý các máy đó trước.</span>`,
    confirmLabel: "Xóa dòng máy",
    danger: true,
    onConfirm: async () => {
      const res = await apiFetch(`/api/v1/products/${productId}`, { method: "DELETE" });
      if (!res.ok) {
        toastError(res, "Không thể xóa dòng máy.");
        return;
      }
      showToast(`Đã xóa dòng máy "${name}".`, "success");
      await loadProducts();
      await loadDashboard();
    },
  });
}

/* --------------------------- MÀN HÌNH: THIẾT BỊ --------------------------- */
async function loadDevices(searchText = "") {
  setTableLoading("devices-table-body", 8);
  let path = "/api/v1/product-instances/?limit=200";
  if (searchText) path += `&search=${encodeURIComponent(searchText)}`;
  const res = await apiFetch(path);
  if (!res.ok) {
    setTableMessage("devices-table-body", 8, "Không tải được danh sách thiết bị.");
    toastError(res, "Không tải được danh sách thiết bị.");
    return;
  }
  state.devices = Array.isArray(res.data) ? res.data : [];
  renderDevices(state.devices);
  populateDeviceCustomerSelect();
}

function renderDevices(items) {
  const tbody = $("devices-table-body");
  if (!tbody) return;
  if (!items.length) {
    setTableMessage("devices-table-body", 8, "Chưa có thiết bị nào được đăng ký.");
    return;
  }
  tbody.innerHTML = items.map((d) => {
    const w = warrantyInfoFor(d.warranty_end_date);
    const expired = w.days !== null && w.days < 0;
    const isActive = d.status === "ACTIVE";
    const recordChip = `<span class="px-2 py-0.5 rounded-full text-xs font-bold ${isActive ? "bg-emerald-50 text-emerald-800 border border-emerald-200" : "bg-rose-50 text-rose-800 border border-rose-200"}">${escapeHtml(deviceStatusLabel(d.status))}</span>`;
    return `
    <tr class="table-row">
      <td class="table-td font-mono font-bold text-indigo-700">${escapeHtml(d.serial_number)}</td>
      <td class="table-td text-slate-900 font-bold">${escapeHtml(displayText(d.product_name) || "–")}<br><span class="text-xs text-slate-500 font-normal">${escapeHtml(displayText(d.product_brand) || "")}</span></td>
      <td class="table-td text-slate-800 font-medium">${escapeHtml(displayText(d.customer_name) || "–")}<br><span class="text-xs text-slate-500 font-mono font-normal">${escapeHtml(d.customer_phone || "")}</span></td>
      <td class="table-td text-slate-600 font-mono text-xs">${fmtDate(d.purchase_date)}</td>
      <td class="table-td font-mono ${expired ? "text-rose-700 font-semibold" : "text-emerald-700 font-semibold"}">${fmtDate(d.warranty_end_date)}</td>
      <td class="table-td">${warrantyStatusHtml(d.warranty_end_date)}</td>
      <td class="table-td">${recordChip}</td>
      <td class="table-td text-right whitespace-nowrap">
        <button class="btn btn-secondary btn-sm" onclick="openDeviceDetailModal(${d.id})"><i data-lucide="info" class="w-3.5 h-3.5"></i> Chi tiết</button>
        ${hasPerm("device.manage") ? `<button class="btn btn-secondary btn-sm ml-1" onclick="openDeviceModal(${d.id})"><i data-lucide="pencil" class="w-3.5 h-3.5"></i> Sửa</button>
        <button class="btn btn-danger btn-sm ml-1" onclick="deleteDevice(${d.id})"><i data-lucide="trash-2" class="w-3.5 h-3.5"></i> Xóa</button>` : ""}
      </td>
    </tr>`;
  }).join("");
  refreshIcons();
}

function searchDevices() {
  const keyword = ($("device-search-input").value || "").trim();
  loadDevices(keyword);
}

/* --------- CHI TIẾT THIẾT BỊ: thông tin + tình trạng bảo hành + phiếu của thiết bị --------- */
async function openDeviceDetailModal(deviceId) {
  if (!state.devices.length || !state.tickets.length) await ensureCountData();
  const d = state.devices.find((x) => x.id === deviceId);
  if (!d) {
    showToast("Không tìm thấy thiết bị. Hãy làm mới danh sách.", "warning");
    return;
  }
  state.selectedDeviceId = deviceId;
  const w = warrantyInfoFor(d.warranty_end_date);
  const tickets = state.tickets.filter((t) => t.serial_number === d.serial_number);
  const warrantyDetail = w.days === null
    ? ""
    : (w.days >= 0 ? `(còn ${w.days} ngày, hạn đến ${fmtDate(d.warranty_end_date)})` : `(đã hết hạn ngày ${fmtDate(d.warranty_end_date)}, quá ${Math.abs(w.days)} ngày)`);

  $("dev-detail-serial").textContent = d.serial_number;
  $("dev-detail-status").innerHTML = `<span class="text-sm font-bold ${w.textClass}">${w.dot} ${w.label.toUpperCase()}</span>
    <span class="text-xs text-slate-500 ml-2 font-medium">${warrantyDetail}</span>`;

  $("dev-detail-info").innerHTML = `
    <div class="p-3 bg-slate-50 rounded-xl border border-slate-200">
      <div class="text-xs text-slate-500 font-semibold mb-1">Dòng máy</div>
      <div class="font-bold text-slate-900">${escapeHtml(displayText(d.product_name) || "–")}</div>
      <div class="text-slate-500 mt-1">Hãng: <span class="text-slate-800 font-medium">${escapeHtml(displayText(d.product_brand) || "–")}</span></div>
    </div>
    <div class="p-3 bg-slate-50 rounded-xl border border-slate-200">
      <div class="text-xs text-slate-500 font-semibold mb-1">Chủ sở hữu</div>
      <div class="font-bold text-slate-900">${escapeHtml(displayText(d.customer_name) || "–")}</div>
      <div class="text-slate-600 mt-1 font-mono">${escapeHtml(d.customer_phone || "")}</div>
    </div>
    <div class="p-3 bg-slate-50 rounded-xl border border-slate-200">
      <div class="text-xs text-slate-500 font-semibold mb-1">Ngày mua</div>
      <div class="font-mono text-slate-800">${fmtDate(d.purchase_date)}</div>
    </div>
    <div class="p-3 bg-slate-50 rounded-xl border border-slate-200">
      <div class="text-xs text-slate-500 font-semibold mb-1">Tình trạng theo dõi</div>
      <div class="text-slate-800 font-medium">${escapeHtml(deviceStatusLabel(d.status))}</div>
    </div>`;

  const checkBox = $("dev-detail-check");
  checkBox.className = "hidden mb-4";
  checkBox.innerHTML = "";

  $("dev-detail-tickets").innerHTML = tickets.length
    ? tickets.map((t) => `
      <div class="flex flex-wrap items-center justify-between gap-2 p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs">
        <div class="flex items-center gap-2">
          <span class="font-mono font-bold text-indigo-700">${escapeHtml(t.ticket_code)}</span>
          ${statusBadge(t.status)}
          <span class="text-slate-600 font-mono">${fmtDateTime(t.created_at)}</span>
        </div>
        <button class="btn btn-secondary btn-sm" onclick="closeModal('device-detail-modal'); openTicketModal(${t.id})"><i data-lucide="arrow-up-right" class="w-3.5 h-3.5"></i> Mở phiếu</button>
      </div>`).join("")
    : '<div class="text-xs text-slate-500">Thiết bị này chưa có phiếu bảo hành nào.</div>';

  openModal("device-detail-modal");
}

function editDeviceFromDetail() {
  const id = state.selectedDeviceId;
  closeModal("device-detail-modal");
  if (id) openDeviceModal(id);
}

function createTicketForDevice() {
  const d = state.devices.find((x) => x.id === state.selectedDeviceId);
  closeModal("device-detail-modal");
  if (d) startTicketForSerial(d.serial_number);
}

/** Kiểm tra bảo hành ngay trong chi tiết thiết bị (gọi đúng API backend). */
async function runDeviceWarrantyCheck() {
  const d = state.devices.find((x) => x.id === state.selectedDeviceId);
  if (!d) return;
  const box = $("dev-detail-check");
  box.className = "mb-4";
  box.innerHTML = '<span class="text-xs text-slate-500">Đang đối chiếu điều kiện bảo hành...</span>';
  const res = await apiFetch("/api/v1/debug/check-warranty", {
    method: "POST",
    body: { serial_number: d.serial_number, check_date: todayISO() },
  });
  if (!res.ok) {
    box.innerHTML = `<span class="text-xs text-rose-700">${escapeHtml(errorMessage(res.status, res.data))}</span>`;
    return;
  }
  const data = res.data;
  const valid = data.is_valid === true;
  const traces = Array.isArray(data.debug_traces) ? data.debug_traces : [];
  box.innerHTML = `
    <div class="p-3 rounded-xl border text-xs ${valid ? "bg-emerald-50 border-emerald-200 text-emerald-900" : "bg-rose-50 border-rose-200 text-rose-900"}">
      <div class="font-bold">${valid ? "Đủ điều kiện bảo hành" : "Không đủ điều kiện bảo hành"}</div>
      <div class="mt-1 text-xs">Đối chiếu ngày ${fmtDate(data.check_date)}: ${escapeHtml(humanizeText(data.status_message))}</div>
    </div>
    ${traces.length ? `
    <details class="mt-2 rounded-xl border border-slate-200 bg-slate-50">
      <summary class="px-3 py-2 text-xs font-semibold text-slate-600 cursor-pointer">Thông tin đối chiếu chi tiết (chỉ cần khi trao đổi với bộ phận kỹ thuật)</summary>
      <div class="px-3 pb-3 font-mono text-xs text-slate-600 space-y-0.5">
        ${traces.map((s) => `<div>${escapeHtml(humanizeTraceStep(s))}</div>`).join("")}
      </div>
    </details>` : ""}`;
  refreshIcons();
}

/** Tiến trình xử lý phiếu (5 bước) - dùng ở modal phiếu và màn Tra cứu. */
function ticketProgressHtml(status) {
  const steps = [
    { code: "RECEIVED", label: "Tiếp nhận" },
    { code: "INSPECTING", label: "Kiểm tra" },
    { code: "REPAIRING", label: "Sửa chữa" },
    { code: "COMPLETED", label: "Hoàn tất" },
    { code: "RETURNED", label: "Đã trả máy" },
  ];
  if (status === "REJECTED") {
    return `<div class="flex flex-wrap items-center gap-1.5">
      <span class="px-2.5 py-1 rounded-lg border bg-emerald-50 border-emerald-300 text-emerald-800 font-medium">1. Tiếp nhận</span>
      <i data-lucide="chevron-right" class="w-3.5 h-3.5 text-slate-400"></i>
      <span class="px-2.5 py-1 rounded-lg border bg-emerald-50 border-emerald-300 text-emerald-800 font-medium">2. Kiểm tra</span>
      <i data-lucide="chevron-right" class="w-3.5 h-3.5 text-slate-400"></i>
      <span class="px-2.5 py-1 rounded-lg border bg-rose-50 border-rose-300 text-rose-800 font-bold">Từ chối (chờ trả)</span>
      <i data-lucide="chevron-right" class="w-3.5 h-3.5 text-slate-400"></i>
      <span class="px-2.5 py-1 rounded-lg border border-slate-200 text-slate-400 bg-white">Đã trả máy</span>
    </div>`;
  }
  const currentIdx = Math.max(0, steps.findIndex((s) => s.code === status));
  return `<div class="flex flex-wrap items-center gap-1.5">
    ${steps.map((s, i) => {
      const done = i < currentIdx;
      const current = i === currentIdx;
      const cls = current
        ? "bg-indigo-50 border-indigo-300 text-indigo-700 font-bold"
        : (done ? "bg-emerald-50 border-emerald-300 text-emerald-800 font-medium" : "border-slate-200 text-slate-400 bg-white");
      return `<span class="px-2.5 py-1 rounded-lg border ${cls}">${i + 1}. ${s.label}${current ? " (hiện tại)" : ""}</span>`;
    }).join('<i data-lucide="chevron-right" class="w-3.5 h-3.5 text-slate-400"></i>')}
  </div>`;
}

function populateDeviceCustomerSelect() {
  const sel = $("dev-customer-id");
  if (!sel) return;
  const current = sel.value;
  sel.innerHTML = '<option value="">-- Chọn khách hàng --</option>' +
    state.customers.map((c) => `<option value="${c.id}">${escapeHtml(c.full_name)} – ${escapeHtml(c.phone)}</option>`).join("");
  if (current) sel.value = current;
}

function recalcDeviceEndDate() {
  const endInput = $("dev-end-date");
  const purchase = $("dev-purchase-date").value;
  const monthsRaw = ($("dev-months").value || "").trim();
  if (!purchase || !monthsRaw) { endInput.value = ""; return; }
  const months = parseInt(monthsRaw, 10);
  endInput.value = months > 0 ? addMonthsISO(purchase, months) : "";
}

async function openDeviceModal(deviceId = null) {
  if (!state.customers.length) {
    const res = await apiFetch("/api/v1/customers/");
    if (res.ok) state.customers = res.data || [];
  }
  if (!state.products.length) {
    const res = await apiFetch("/api/v1/products/");
    if (res.ok) state.products = res.data || [];
  }
  populateDeviceCustomerSelect();
  populateProductDatalist();

  clearFieldErrors(["dev-serial", "dev-customer", "dev-product", "dev-purchase", "dev-months"]);
  $("dev-id").value = "";
  $("dev-serial").value = "";
  $("dev-customer-id").value = "";
  $("dev-product-name").value = "";
  $("dev-brand").value = "";
  $("dev-category").value = "";
  $("dev-purchase-date").value = "";
  $("dev-months").value = "";
  $("dev-end-date").value = "";
  $("dev-status").value = "ACTIVE";
  $("dev-description").value = "";

  if (deviceId) {
    const d = state.devices.find((x) => x.id === deviceId);
    if (!d) {
      showToast("Không tìm thấy thiết bị cần sửa. Hãy làm mới danh sách.", "warning");
      return;
    }
    $("device-modal-title").textContent = `Sửa thiết bị ${d.serial_number}`;
    $("dev-id").value = d.id;
    $("dev-serial").value = d.serial_number || "";
    $("dev-customer-id").value = d.customer_id;
    $("dev-product-name").value = d.product_name || "";
    $("dev-brand").value = d.product_brand || "";
    $("dev-category").value = d.product_category || "";
    $("dev-purchase-date").value = d.purchase_date || "";
    $("dev-months").value = d.warranty_duration_months || "";
    $("dev-end-date").value = d.warranty_end_date || "";
    $("dev-status").value = d.status || "ACTIVE";
    $("dev-description").value = d.description || "";
  } else {
    $("device-modal-title").textContent = "Thêm thiết bị";
  }
  openModal("device-modal");
}

async function submitDeviceForm(event) {
  event.preventDefault();
  const submitBtn = event.target ? event.target.querySelector("button[type=submit]") : null;
  const id = $("dev-id").value;
  const serial = ($("dev-serial").value || "").trim();
  const customerId = parseInt($("dev-customer-id").value, 10);
  const productName = ($("dev-product-name").value || "").trim();
  const purchaseDate = $("dev-purchase-date").value;
  const monthsRaw = ($("dev-months").value || "").trim();
  const months = monthsRaw ? parseInt(monthsRaw, 10) : null;

  clearFieldErrors(["dev-serial", "dev-customer", "dev-product", "dev-purchase", "dev-months"]);
  let hasError = false;
  if (!serial) { setFieldError("dev-serial", "Vui lòng nhập số sê-ri của thiết bị."); hasError = true; }
  if (!customerId) { setFieldError("dev-customer", "Vui lòng chọn khách hàng (chủ sở hữu)."); hasError = true; }
  if (!productName) { setFieldError("dev-product", "Vui lòng chọn hoặc nhập tên sản phẩm."); hasError = true; }
  if (!purchaseDate) { setFieldError("dev-purchase", "Vui lòng chọn ngày mua."); hasError = true; }
  if (months !== null && (isNaN(months) || months < 1 || months > 120)) {
    setFieldError("dev-months", "Thời hạn bảo hành phải từ 1 đến 120 tháng.");
    hasError = true;
  }
  if (hasError) {
    showToast("Vui lòng kiểm tra lại thông tin thiết bị.", "warning");
    return;
  }

  const payload = {
    serial_number: serial,
    customer_id: customerId,
    purchase_date: purchaseDate,
    status: $("dev-status").value,
    description: ($("dev-description").value || "").trim() || null,
  };
  if (months) payload.warranty_duration_months = months;

  // Gắn sản phẩm: tìm chính xác theo tên trong danh mục đã có, nếu chưa có thì tạo mới theo tên.
  const matched = state.products.find((p) => (p.name || "").trim().toLowerCase() === productName.toLowerCase());
  if (matched) {
    payload.product_id = matched.id;
  } else {
    payload.product_name = productName;
    const brand = ($("dev-brand").value || "").trim();
    const category = ($("dev-category").value || "").trim();
    if (brand) payload.brand = brand;
    if (category) payload.category = category;
  }

  if (submitBtn) submitBtn.disabled = true;
  try {
    const res = id
      ? await apiFetch(`/api/v1/product-instances/${id}`, { method: "PUT", body: payload })
      : await apiFetch("/api/v1/product-instances/", { method: "POST", body: payload });

    if (!res.ok) {
      toastError(res, id ? "Không cập nhật được thiết bị." : "Không thêm được thiết bị.");
      return;
    }
    closeModal("device-modal");
    showToast(id ? `Đã cập nhật thiết bị "${serial}".` : `Đã thêm thiết bị "${serial}".`, "success");
    await loadDevices();
    await loadReferenceData();
    await loadDashboard();
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

function deleteDevice(deviceId) {
  if (!hasPerm("device.manage")) {
    showToast("Vai trò hiện tại không có quyền xóa thiết bị.", "warning");
    return;
  }
  const d = state.devices.find((x) => x.id === deviceId);
  const serial = d ? d.serial_number : "thiết bị này";
  showActionModal({
    title: "Xóa thiết bị",
    message: `Bạn có chắc muốn xóa thiết bị <strong class="font-mono">${escapeHtml(serial)}</strong>?<br>
      <span class="text-xs text-slate-400">Lưu ý: thiết bị đang có phiếu bảo hành sẽ không xóa được.</span>`,
    confirmLabel: "Xóa thiết bị",
    danger: true,
    onConfirm: async () => {
      const res = await apiFetch(`/api/v1/product-instances/${deviceId}`, { method: "DELETE" });
      if (!res.ok) {
        toastError(res, "Không thể xóa thiết bị.");
        return;
      }
      showToast(`Đã xóa thiết bị "${serial}".`, "success");
      await loadDevices();
      await loadDashboard();
    },
  });
}

/* --------------------------- MÀN HÌNH: PHIẾU BẢO HÀNH --------------------------- */
/* ---------------------------------------------------------------------------
   WIZARD "TIẾP NHẬN MÁY MỚI" (2 bước)
   Bước 1: tra số sê-ri -> có trong hệ thống thì dùng ngay, chưa có thì đăng ký thiết bị mới.
   Bước 2: xem lại thông tin thiết bị + nhập mô tả lỗi -> tạo phiếu bảo hành.
   LƯU Ý: điều kiện bảo hành vẫn do backend quyết định khi tạo phiếu; giao diện chỉ hiển thị.
   --------------------------------------------------------------------------- */
function wizardShowStep(step) {
  const step1 = $("wizard-step1");
  const step2 = $("wizard-step2");
  if (!step1 || !step2) return;
  step1.classList.toggle("hidden", step !== 1);
  step2.classList.toggle("hidden", step !== 2);
  refreshIcons();
}

function wizardToggleNewDevice(show) {
  const box = $("wiz-new-device");
  if (box) box.classList.toggle("hidden", !show);
  refreshIcons();
}

/** Nạp khách hàng / sản phẩm / người dùng / danh mục lỗi + danh sách chọn nhanh cho wizard. */
async function loadWizardOptions() {
  if (!state.customers.length) await loadCustomers();
  if (!state.products.length) {
    const resProducts = await apiFetch("/api/v1/products/");
    if (resProducts.ok) state.products = resProducts.data || [];
  }
  if (!state.categories.length || !state.users.length) await loadReferenceData();

  const sel = $("wiz-customer-id");
  if (sel) {
    const current = sel.value;
    sel.innerHTML = '<option value="">-- Chọn khách hàng --</option>' +
      state.customers.map((c) => `<option value="${c.id}">${escapeHtml(c.full_name)} – ${escapeHtml(c.phone)}</option>`).join("");
    if (current) sel.value = current;
  }

  populateProductDatalist();
  await refreshWizardSamples();
}

/** Danh sách "chọn nhanh" các thiết bị đang có để tiếp nhận. */
async function refreshWizardSamples() {
  const box = $("wiz-samples");
  if (!box) return;
  if (!state.devices.length) {
    const res = await apiFetch("/api/v1/product-instances/?limit=8");
    if (res.ok) state.devices = res.data || [];
  }
  box.innerHTML = state.devices.length
    ? state.devices.slice(0, 4).map((d) => deviceSampleButtonHtml(d, "wizardUseSample")).join("")
    : '<span class="text-xs text-slate-500">Chưa có thiết bị nào trong hệ thống.</span>';
  refreshIcons();
}

/** Chọn nhanh một thiết bị đang có -> tra luôn ở bước 1. */
function wizardUseSample(serial) {
  const input = $("wiz-serial");
  if (input) input.value = serial;
  wizardLookupSerial();
}

/** Đưa wizard về trạng thái ban đầu (bước 1, trống). */
function wizardReset() {
  state.wizard = { device: null };
  clearFieldErrors(["wiz-serial", "wiz-customer", "wiz-product", "wiz-purchase", "wiz-desc", "wiz-created-by"]);
  const ids = ["wiz-serial", "wiz-desc", "wiz-product-name", "wiz-brand", "wiz-category", "wiz-purchase-date", "wiz-months"];
  ids.forEach((id) => { if ($(id)) $(id).value = ""; });
  if ($("wiz-customer-id")) $("wiz-customer-id").value = "";
  if ($("wiz-category-select")) $("wiz-category-select").value = "";
  if ($("wiz-device-result")) $("wiz-device-result").innerHTML = "";
  if ($("wiz-end-date")) $("wiz-end-date").textContent = "";
  if ($("wiz-preview")) $("wiz-preview").innerHTML = "";
  const createdBy = $("wiz-created-by");
  if (createdBy && state.users.length) {
    const actor = defaultActor(assignableStaff(), "RECEPTIONIST");
    if (actor) createdBy.value = String(actor.id);
  }
  wizardToggleNewDevice(false);
  wizardShowStep(1);
}

/** Dự báo hạn bảo hành ở bước 1 (chỉ để nhìn trước; backend vẫn là nơi quyết định). */
function recalcWizardEndDate() {
  const label = $("wiz-end-date");
  if (!label) return;
  const purchase = ($("wiz-purchase-date").value || "").trim();
  const monthsRaw = ($("wiz-months").value || "").trim();
  if (!purchase || !monthsRaw) {
    label.textContent = "Bỏ trống thời hạn: hệ thống lấy theo hạn bảo hành của sản phẩm.";
    return;
  }
  const months = parseInt(monthsRaw, 10);
  label.textContent = months > 0 ? `Hạn bảo hành dự kiến: ${fmtDate(addMonthsISO(purchase, months))}` : "";
}

/** Bước 1 (nhánh "máy mới"): kiểm tra dữ liệu rồi tạo thiết bị, sau đó sang bước 2. */
async function wizardSaveDevice() {
  const serial = ($("wiz-serial").value || "").trim();
  const customerId = parseInt($("wiz-customer-id").value, 10);
  const productName = ($("wiz-product-name").value || "").trim();
  const purchaseDate = ($("wiz-purchase-date").value || "").trim();
  const monthsRaw = ($("wiz-months").value || "").trim();
  const months = monthsRaw ? parseInt(monthsRaw, 10) : null;

  clearFieldErrors(["wiz-serial", "wiz-customer", "wiz-product", "wiz-purchase"]);
  let hasError = false;
  if (!serial) { setFieldError("wiz-serial", "Vui lòng nhập số sê-ri thiết bị."); hasError = true; }
  if (!customerId) { setFieldError("wiz-customer", "Vui lòng chọn khách hàng (chủ sở hữu thiết bị)."); hasError = true; }
  if (!productName) { setFieldError("wiz-product", "Vui lòng chọn hoặc nhập tên sản phẩm."); hasError = true; }
  if (!purchaseDate) { setFieldError("wiz-purchase", "Vui lòng chọn ngày mua."); hasError = true; }
  if (months !== null && (isNaN(months) || months < 1 || months > 120)) {
    showToast("Thời hạn bảo hành phải từ 1 đến 120 tháng.", "warning");
    hasError = true;
  }
  if (hasError) {
    showToast("Vui lòng kiểm tra lại thông tin thiết bị.", "warning");
    return;
  }

  const payload = {
    serial_number: serial,
    customer_id: customerId,
    purchase_date: purchaseDate,
    status: "ACTIVE",
  };
  if (months) payload.warranty_duration_months = months;

  // Gắn sản phẩm: khớp chính xác theo tên trong danh mục, chưa có thì tạo mới theo tên.
  const matched = state.products.find((p) => (p.name || "").trim().toLowerCase() === productName.toLowerCase());
  if (matched) {
    payload.product_id = matched.id;
  } else {
    payload.product_name = productName;
    const brand = ($("wiz-brand").value || "").trim();
    const category = ($("wiz-category").value || "").trim();
    if (brand) payload.brand = brand;
    if (category) payload.category = category;
  }

  const res = await apiFetch("/api/v1/product-instances/", { method: "POST", body: payload });
  if (!res.ok) {
    toastError(res, "Không đăng ký được thiết bị.");
    return;
  }

  // Đọc lại theo số sê-ri để có đủ thông tin hiển thị (khách hàng, sản phẩm, hạn bảo hành).
  const fresh = await apiFetch(`/api/v1/product-instances/by-serial/${encodeURIComponent(serial)}`);
  state.wizard.device = fresh.ok ? fresh.data : (res.data || {});
  $("wiz-device-result").innerHTML = wizardDeviceFoundHtml(state.wizard.device);
  wizardToggleNewDevice(false);
  showToast(`Đã đăng ký thiết bị <strong class="font-mono">${escapeHtml(serial)}</strong>. Tiếp tục tạo phiếu bảo hành.`, "success", 6000);

  await loadWizardOptions();
  await loadDashboard();
  wizardGoToStep2();
}

/**
 * Kiểm tra điều kiện bảo hành trước khi tạo phiếu.
 * KHÔNG truyền check_date => backend dùng đúng ngày hôm nay, khớp với điều kiện khi lưu phiếu.
 */
/**
 * BƯỚC 1: tra số sê-ri thiết bị.
 * - Có trong hệ thống -> hiện card thông tin + nút sang bước 2.
 * - Chưa có -> mở form đăng ký thiết bị mới ngay bên dưới.
 * KHÔNG truyền ngày kiểm tra: backend luôn dùng đúng ngày hôm nay khi tạo phiếu.
 */
async function wizardLookupSerial() {
  const serialInput = $("wiz-serial");
  const box = $("wiz-device-result");
  if (!serialInput || !box) return;
  const serial = (serialInput.value || "").trim();

  setFieldError("wiz-serial", "");
  state.wizard.device = null;
  wizardToggleNewDevice(false);

  if (!serial) {
    box.innerHTML = "";
    setFieldError("wiz-serial", "Vui lòng nhập số sê-ri thiết bị.");
    return;
  }

  box.innerHTML = '<span class="text-xs text-slate-400 inline-flex items-center gap-2"><i data-lucide="loader" class="w-4 h-4 animate-spin"></i>Đang tra số sê-ri...</span>';
  refreshIcons();

  const res = await apiFetch(`/api/v1/product-instances/by-serial/${encodeURIComponent(serial)}`);
  if (res.status === 404) {
    box.innerHTML = `
      <div class="p-3.5 rounded-xl border border-amber-200 bg-amber-50 text-xs text-amber-900">
        <div class="font-bold text-amber-900 flex items-center gap-1.5">
          <i data-lucide="info" class="w-4 h-4 text-amber-600"></i> Số sê-ri <span class="font-mono font-bold">${escapeHtml(serial)}</span> chưa có trong hệ thống
        </div>
        <p class="text-amber-800 mt-1">Vui lòng điền thông tin bên dưới để đăng ký thiết bị mới, sau đó tiếp tục tạo phiếu bảo hành.</p>
      </div>`;
    if ($("wiz-purchase-date")) $("wiz-purchase-date").value = "";
    recalcWizardEndDate();
    wizardToggleNewDevice(true);
    refreshIcons();
    return;
  }
  if (!res.ok) {
    box.innerHTML = `<div class="p-3.5 rounded-xl border border-rose-200 bg-rose-50 text-xs text-rose-800">${escapeHtml(errorMessage(res.status, res.data))}</div>`;
    return;
  }

  state.wizard.device = res.data;
  box.innerHTML = wizardDeviceFoundHtml(res.data);
  refreshIcons();
}

/** Card thiết bị đã tìm thấy ở bước 1 (kèm tình trạng bảo hành và cảnh báo phiếu đang mở nếu có). */
function wizardDeviceFoundHtml(d) {
  if (!d || !d.serial_number) return "";
  const w = warrantyInfoFor(d.warranty_end_date);
  const note = w.days !== null && w.days < 0
    ? `<div class="p-3 rounded-xl border border-rose-200 bg-rose-50 text-xs text-rose-800 mt-2">
         Thiết bị đã hết hạn bảo hành (hạn ${fmtDate(d.warranty_end_date)}). Vẫn tạo được phiếu nhưng phiếu sẽ được xử lý như trường hợp ngoài bảo hành.
       </div>`
    : "";

  const openStatuses = ["RECEIVED", "INSPECTING", "REPAIRING", "COMPLETED", "REJECTED"];
  const openTicket = (state.tickets || []).find((t) => (t.serial_number === d.serial_number || t.product_instance_id === d.id) && openStatuses.includes(t.status));
  let openWarning = "";
  if (openTicket) {
    openWarning = `
      <div class="p-3.5 rounded-xl border border-amber-300 bg-amber-50 text-xs text-amber-900 mt-2 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <span class="font-bold text-amber-900">Cảnh báo phiếu đang mở:</span> Thiết bị này đang có phiếu <span class="font-mono font-bold">${escapeHtml(openTicket.ticket_code)}</span> (${escapeHtml(statusLabel(openTicket.status))}) chưa kết thúc.
        </div>
        <button type="button" class="btn btn-secondary btn-xs shrink-0 text-amber-900 border-amber-300 hover:bg-amber-100" onclick="openTicketModal(${openTicket.id})">
          <i data-lucide="eye" class="w-3.5 h-3.5"></i> Xem phiếu đang xử lý
        </button>
      </div>`;
  }

  return `
    <div class="p-4 rounded-xl border border-emerald-200 bg-emerald-50/60">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="text-xs">
          <div class="font-bold text-emerald-900 flex items-center gap-1.5">
            <i data-lucide="check-circle-2" class="w-4 h-4 text-emerald-600"></i> Đã tìm thấy thiết bị <span class="font-mono text-emerald-950 font-bold">${escapeHtml(d.serial_number)}</span>
          </div>
          <div class="text-slate-600 mt-1">
            <span class="font-medium text-slate-900">${escapeHtml(displayText(d.product_name) || "–")}</span>
            &bull; Khách hàng: <span class="font-medium text-slate-800">${escapeHtml(displayText(d.customer_name) || "–")}</span>
            ${d.customer_phone ? `&bull; <span class="font-mono text-slate-700">${escapeHtml(d.customer_phone)}</span>` : ""}
            &bull; ${warrantyStatusHtml(d.warranty_end_date)}
          </div>
        </div>
        <div class="flex flex-wrap gap-2">
          <button type="button" class="btn btn-secondary btn-sm" onclick="openDeviceDetailModal(${d.id})"><i data-lucide="info" class="w-3.5 h-3.5"></i> Xem chi tiết</button>
          <button type="button" class="btn btn-primary btn-sm" onclick="wizardGoToStep2()"><i data-lucide="arrow-right" class="w-3.5 h-3.5"></i> Tiếp tục bước 2</button>
        </div>
      </div>
    </div>${openWarning}${note}`;
}

/** BƯỚC 2: xem lại thiết bị đã chọn rồi mở form mô tả lỗi. */
async function wizardGoToStep2() {
  const d = state.wizard.device;
  if (!d) {
    showToast("Vui lòng chọn hoặc đăng ký thiết bị ở bước 1.", "warning");
    wizardShowStep(1);
    return;
  }
  if (!state.tickets.length) await ensureCountData();
  const preview = $("wiz-preview");
  if (preview) preview.innerHTML = wizardPreviewHtml(d) + wizardOpenTicketWarningHtml(d);
  wizardShowStep(2);
  const desc = $("wiz-desc");
  if (desc) setTimeout(() => desc.focus(), 120);
}

/**
 * Nhắc trước khi tạo phiếu: thiết bị đang có phiếu chưa kết thúc.
 * Chỉ là nhắc để tránh phải nhập lại; việc chặn vẫn do hệ thống quyết định.
 */
function wizardOpenTicketWarningHtml(d) {
  const openStatuses = ["RECEIVED", "INSPECTING", "REPAIRING", "COMPLETED", "REJECTED"];
  const open = state.tickets.find((t) => t.serial_number === d.serial_number && openStatuses.includes(t.status));
  if (!open) return "";
  return `
    <div class="p-3.5 rounded-xl border border-amber-200 bg-amber-50 text-xs sm:col-span-2 lg:col-span-4">
      <div class="font-bold text-amber-900">Thiết bị này đang có phiếu chưa kết thúc</div>
      <p class="text-amber-800 mt-1">
        Phiếu <strong class="font-mono text-amber-950 font-bold">${escapeHtml(open.ticket_code)}</strong> (${escapeHtml(statusLabel(open.status))}) vẫn đang được xử lý.
        Mỗi thiết bị chỉ có một phiếu đang xử lý, nên hãy xử lý phiếu cũ trước nếu khách không báo lỗi mới.
      </p>
      <button type="button" class="btn btn-secondary btn-sm mt-2" onclick="closeReceptionAndOpenTicket(${open.id})">
        <i data-lucide="eye" class="w-3.5 h-3.5"></i> Xem phiếu đang xử lý
      </button>
    </div>`;
}

/** Mở phiếu đang xử lý của thiết bị từ bước 2 của wizard. */
function closeReceptionAndOpenTicket(ticketId) {
  openTicketModal(ticketId);
}

/** Tóm tắt thiết bị ở bước 2 để nhân viên đối chiếu trước khi tạo phiếu. */
function wizardPreviewHtml(d) {
  const cell = (label, value) => `
    <div class="p-3 bg-slate-50 rounded-xl border border-slate-200">
      <div class="text-xs text-slate-500 font-semibold mb-1">${label}</div>
      <div class="font-bold text-slate-900">${value}</div>
    </div>`;
  return [
    cell("Thiết bị", `${escapeHtml(displayText(d.product_name) || "–")}<div class="font-mono text-indigo-700 font-bold text-xs mt-0.5">${escapeHtml(d.serial_number)}</div>`),
    cell("Khách hàng", `${escapeHtml(displayText(d.customer_name) || "–")}<div class="font-mono text-slate-600 text-xs mt-0.5">${escapeHtml(d.customer_phone || "")}</div>`),
    cell("Ngày mua", `<span class="font-mono text-slate-800">${fmtDate(d.purchase_date)}</span>`),
    cell("Tình trạng bảo hành", warrantyStatusHtml(d.warranty_end_date)),
  ].join("");
}

function wizardBackToStep1() {
  wizardShowStep(1);
}

/** Gợi ý nhóm lỗi trực tiếp (AI Chức năng 1) trong màn hình tiếp nhận */
async function wizardSuggestCategory() {
  const d = state.wizard.device;
  const productName = d ? (d.product_name || "") : ($("wiz-product-name") ? $("wiz-product-name").value : "");
  const desc = ($("wiz-desc") ? $("wiz-desc").value : "").trim();
  if (!desc) {
    showToast("Vui lòng nhập mô tả tình trạng lỗi trước khi yêu cầu AI gợi ý.", "warning");
    if ($("wiz-desc")) $("wiz-desc").focus();
    return;
  }
  const btn = $("btn-wiz-ai-suggest");
  const origHtml = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i data-lucide="loader" class="w-4 h-4 animate-spin text-purple-600"></i> Đang phân tích...';
    refreshIcons();
  }

  try {
    const res = await apiFetch("/api/v1/ai/suggest-category", {
      method: "POST",
      body: {
        product_name: productName || null,
        issue_description: desc,
      },
    });
    if (!res.ok) {
      toastError(res, "Không thể lấy gợi ý loại lỗi từ AI.");
      return;
    }
    const data = res.data || {};
    const hintBox = $("wiz-ai-hint");
    const hintText = $("wiz-ai-hint-text");
    if (data.suggested_category_id) {
      const select = $("wiz-category-select");
      if (select) select.value = String(data.suggested_category_id);
      if (hintBox && hintText) {
        hintBox.classList.remove("hidden");
        const confStr = data.confidence ? ` (độ chắc chắn: ${Math.round(data.confidence * 100)}%)` : "";
        hintText.innerHTML = `<strong>Gợi ý:</strong> ${escapeHtml(data.suggested_category_name || "")}${confStr}. ${escapeHtml(data.reason || "")}<br><span class="text-slate-500 italic mt-0.5 block">Nội dung được AI gợi ý, cần kiểm tra trước khi sử dụng.</span>`;
      }
      showToast(`AI gợi ý nhóm lỗi: <strong>${escapeHtml(data.suggested_category_name || "")}</strong>`, "success");
    } else {
      if (hintBox && hintText) {
        hintBox.classList.remove("hidden");
        let extra = "";
        if (Array.isArray(data.need_more_information) && data.need_more_information.length) {
          extra = "<br><strong>Cần hỏi thêm khách:</strong> " + data.need_more_information.map(escapeHtml).join("; ");
        }
        hintText.innerHTML = `Mô tả hiện tại chưa đủ để AI phân loại lỗi chắc chắn. ${escapeHtml(data.reason || "")}${extra}<br><span class="text-slate-500 italic mt-0.5 block">Nội dung được AI gợi ý, cần kiểm tra trước khi sử dụng.</span>`;
      }
      showToast("Chưa đủ thông tin để AI gợi ý nhóm lỗi chính xác.", "info");
    }
    refreshIcons();
  } catch (err) {
    showToast("Lỗi khi kết nối dịch vụ AI.", "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origHtml;
      refreshIcons();
    }
  }
}

/** BƯỚC 2 (hoàn tất): tạo phiếu bảo hành cho thiết bị đã chọn ở bước 1. */
async function wizardSubmitTicket() {
  const submitBtn = $("btn-wizard-submit");
  const d = state.wizard.device;
  if (!d) {
    showToast("Thiếu thông tin thiết bị, hãy chọn lại ở bước 1.", "warning");
    wizardShowStep(1);
    return;
  }
  const description = ($("wiz-desc").value || "").trim();
  const createdBy = parseInt($("wiz-created-by").value, 10);
  const categoryRaw = $("wiz-category-select").value;
  const condition = ($("wiz-condition") ? $("wiz-condition").value : "").trim();
  const accessories = ($("wiz-accessories") ? $("wiz-accessories").value : "").trim();

  clearFieldErrors(["wiz-desc", "wiz-created-by"]);
  let hasError = false;
  if (!description) { setFieldError("wiz-desc", "Vui lòng nhập mô tả tình trạng lỗi."); hasError = true; }
  else if (description.length < 5) { setFieldError("wiz-desc", "Mô tả lỗi quá ngắn, hãy ghi rõ tình trạng thiết bị."); hasError = true; }
  if (!createdBy) { setFieldError("wiz-created-by", "Vui lòng chọn người tiếp nhận."); hasError = true; }
  if (hasError) {
    showToast("Vui lòng kiểm tra lại thông tin phiếu bảo hành.", "warning");
    return;
  }

  const payload = {
    serial_number: d.serial_number,
    customer_id: d.customer_id,
    service_center_id: 1,
    created_by: createdBy,
    issue_description: description,
    device_condition: condition || null,
    accessories_accompanying: accessories || null,
  };
  // Chỉ gửi nhãn lỗi khi nhân viên chủ động chọn; mặc định để trống cho luồng AI gợi ý.
  if (categoryRaw) payload.error_category_id = parseInt(categoryRaw, 10);

  if (submitBtn) submitBtn.disabled = true;
  try {
    const res = await apiFetch("/api/v1/warranty-tickets/", { method: "POST", body: payload });
    if (!res.ok) {
      toastError(res, "Không tạo được phiếu bảo hành.");
      return;
    }
    const ticket = res.data || {};
    showToast(`Đã tạo phiếu bảo hành <strong class="font-mono">${escapeHtml(ticket.ticket_code)}</strong> ở trạng thái "Đã tiếp nhận".`, "success", 7000);
    wizardReset();
    await loadTickets();
    await loadDashboard();
    if (ticket.id) openTicketModal(ticket.id);
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

/* --------------------------- DANH SÁCH PHIẾU --------------------------- */
let ticketStatusFilter = "ALL";
/** Bộ lọc "Phiếu của tôi": true = chỉ lấy phiếu mà tài khoản hiện tại là người xử lý gần nhất. */
let ticketOnlyMine = false;

async function loadTickets(statusFilter = null) {
  const currentEpoch = state.sessionEpoch;
  if (statusFilter !== null) ticketStatusFilter = statusFilter;
  setTableLoading("tickets-table-body", 8);

  // Bộ lọc do BACKEND thực hiện (trạng thái + việc của tôi + từ khoá) để số liệu luôn chính xác
  const params = new URLSearchParams();
  params.set("limit", "200");
  if (ticketStatusFilter && ticketStatusFilter !== "ALL") params.set("status", ticketStatusFilter);
  if (ticketOnlyMine) params.set("mine", "1");
  const keyword = ticketSearchKeyword();
  if (keyword) params.set("q", keyword);

  const res = await apiFetch(`/api/v1/warranty-tickets/?${params.toString()}`);
  if (currentEpoch !== state.sessionEpoch) return;
  if (!res.ok) {
    if (!state.tickets || !state.tickets.length) {
      setTableMessage("tickets-table-body", 8, "Không tải được danh sách phiếu bảo hành.");
    }
    toastError(res, "Không tải được danh sách phiếu bảo hành.");
    return;
  }
  state.tickets = Array.isArray(res.data) ? res.data : [];
  renderTickets(state.tickets);
  populateAiTicketSelect();
  updateTicketScopeButtons();
}

/** Từ khoá đang nhập ở ô tìm kiếm của danh sách phiếu (rỗng nếu chưa nhập). */
function ticketSearchKeyword() {
  const box = $("ticket-search-input");
  return box ? (box.value || "").trim() : "";
}

/** Thiết lập phạm vi danh sách phiếu: mine = true (việc của tôi/phiếu được giao) hoặc false (toàn trung tâm). */
function setTicketScope(mine) {
  ticketOnlyMine = !!mine;
  updateTicketScopeButtons();
  loadTickets();
}

/** Bật/tắt bộ lọc phạm vi trên danh sách phiếu. */
function toggleMyTickets() {
  setTicketScope(!ticketOnlyMine);
}

/** Đổi màu và nhãn nút lọc theo vai trò (Việc tại quầy / Phiếu được giao). */
function updateTicketScopeButtons() {
  const btnMine = $("btn-scope-mine");
  const btnAll = $("btn-scope-all");
  const lblMine = $("label-scope-mine");
  const lblAll = $("label-scope-all");
  if (!btnMine || !btnAll) return;

  const role = state.session.user ? state.session.user.role : "";
  if (role === "TECHNICIAN") {
    if (lblMine) lblMine.textContent = "Phiếu được giao";
    if (lblAll) lblAll.textContent = "Toàn trung tâm — chỉ xem";
  } else if (role === "RECEPTIONIST") {
    if (lblMine) lblMine.textContent = "Việc tại quầy";
    if (lblAll) lblAll.textContent = "Toàn bộ phiếu";
  } else {
    if (lblMine) lblMine.textContent = "Việc của tôi";
    if (lblAll) lblAll.textContent = "Toàn trung tâm";
  }

  btnMine.className = `btn btn-sm ${ticketOnlyMine ? "btn-primary font-bold shadow-sm" : "btn-secondary text-slate-600"} rounded-lg transition-all`;
  btnAll.className = `btn btn-sm ${!ticketOnlyMine ? "btn-primary font-bold shadow-sm" : "btn-secondary text-slate-600"} rounded-lg transition-all`;
  refreshIcons();
}

/** Phiếu đang xử lý (chưa kết thúc) luôn được ưu tiên hiển thị trước. */
function sortTicketsForWork(items) {
  const order = { RECEIVED: 0, INSPECTING: 1, REPAIRING: 2, COMPLETED: 3, REJECTED: 4, RETURNED: 5 };
  return items.slice().sort((a, b) => {
    const oa = order[a.status] === undefined ? 9 : order[a.status];
    const ob = order[b.status] === undefined ? 9 : order[b.status];
    if (oa !== ob) return oa - ob;
    return b.id - a.id;
  });
}

/** Nhân viên phụ trách / KTV phụ trách. */
function ticketHandlerName(t) {
  return ticketTechnicianName(t);
}

/**
 * Tìm phiếu theo mã phiếu / số sê-ri / tên khách hàng / số điện thoại.
 *
 * Việc tìm kiếm do BACKEND thực hiện (`?q=...`) nên kết quả không bị giới hạn
 * theo số dòng đã tải về; gõ liên tục thì chờ 350ms mới gọi API (tránh spam).
 */
let ticketSearchTimer = null;
function filterTickets() {
  if (ticketSearchTimer) clearTimeout(ticketSearchTimer);
  ticketSearchTimer = setTimeout(() => {
    ticketSearchTimer = null;
    loadTickets();
  }, 350);
}

/** Nút "Tra cứu mã phiếu": tìm đúng theo mã, nếu không phải mã phiếu thì lọc theo từ khoá. */
async function searchTicketByCode() {
  const keyword = ticketSearchKeyword();
  if (!keyword) {
    showToast("Vui lòng nhập mã phiếu, số sê-ri hoặc tên khách hàng cần tìm.", "warning");
    return;
  }
  if (!/^TK-/i.test(keyword)) {
    await loadTickets();
    return;
  }
  const res = await apiFetch(`/api/v1/warranty-tickets/code/${encodeURIComponent(keyword.toUpperCase())}`);
  if (!res.ok) {
    toastError(res, "Không tra cứu được phiếu bảo hành.");
    return;
  }
  openTicketModal(res.data.id);
}

/**
 * Danh sách phiếu: đúng 8 cột đồng bộ với header:
 * Mã phiếu | Khách hàng | Thiết bị / Số sê-ri | Trạng thái | KTV phụ trách | Ngày tiếp nhận | Loại lỗi | Thao tác
 */
function renderTickets(tickets) {
  const tbody = $("tickets-table-body");
  if (!tbody) return;
  if (!tickets.length) {
    const role = state.session.user ? state.session.user.role : "";
    let emptyMsg = "Chưa có phiếu bảo hành nào phù hợp.";
    if (ticketSearchKeyword()) {
      emptyMsg = `Không tìm thấy phiếu nào khớp với từ khóa "${ticketSearchKeyword()}".`;
    } else if (ticketStatusFilter && ticketStatusFilter !== "ALL") {
      const stName = statusLabel(ticketStatusFilter);
      emptyMsg = ticketOnlyMine
        ? (role === "TECHNICIAN" ? `Bạn không có phiếu nào ở bước "${stName}".` : `Không có phiếu nào ở bước "${stName}" trong danh sách của bạn.`)
        : `Không có phiếu nào ở bước "${stName}" trong toàn trung tâm.`;
    } else if (ticketOnlyMine) {
      if (role === "TECHNICIAN") {
        emptyMsg = 'Bạn chưa được phân công phiếu nào. Chọn "Toàn trung tâm — chỉ xem" để xem phiếu của trung tâm.';
      } else if (role === "RECEPTIONIST") {
        emptyMsg = 'Hiện không có phiếu nào cần xử lý tại quầy. Chọn "Toàn bộ phiếu" để xem toàn trung tâm.';
      } else {
        emptyMsg = 'Bạn hiện không có phiếu nào đang phụ trách.';
      }
    } else {
      emptyMsg = "Trung tâm hiện chưa có phiếu bảo hành nào.";
    }
    setTableMessage("tickets-table-body", 8, emptyMsg);
    return;
  }
  tbody.innerHTML = sortTicketsForWork(tickets).map((t) => {
    const isTransition = t.action_kind === "transition" && t.primary_action;
    const target = isTransition ? t.primary_action.target : null;
    return `<tr class="table-row">
      <td class="table-td">
        <button type="button" class="font-semibold text-slate-900 hover:text-indigo-600 transition-colors text-left text-sm"
                onclick="openTicketModal(${t.id})" title="Bấm để xem chi tiết phiếu">
          ${escapeHtml(t.ticket_code)}
        </button>
      </td>
      <td class="table-td">
        <div class="font-semibold text-slate-900">${escapeHtml(displayText(t.customer_name) || "–")}</div>
        <div class="text-xs text-slate-500 mt-0.5">${escapeHtml(t.customer_phone || "")}</div>
      </td>
      <td class="table-td">
        <div class="text-slate-800 font-medium">${escapeHtml(displayText(t.product_name) || "–")}</div>
        <div class="mt-0.5">
          <button type="button" class="text-xs text-slate-500 hover:text-indigo-600 transition-colors text-left inline-block font-normal"
                  onclick="openDeviceBySerialOrId(${t.product_instance_id || "null"}, '${escapeHtml(t.serial_number || "")}')" title="Bấm để xem thông tin thiết bị">
            ${escapeHtml(t.serial_number || "–")}
          </button>
        </div>
      </td>
      <td class="table-td">${statusBadge(t.status)}</td>
      <td class="table-td text-sm">
        <div class="flex items-center gap-1.5">
          <i data-lucide="user" class="w-3.5 h-3.5 text-slate-400 shrink-0"></i>
          ${formatTechnicianCell(ticketTechnicianName(t))}
        </div>
      </td>
      <td class="table-td text-sm font-mono text-slate-600">${fmtDateTime(t.created_at)}</td>
      <td class="table-td text-sm text-slate-700">${escapeHtml(t.error_category_name || categoryName(t.error_category_id))}</td>
      <td class="table-td text-right">
        <div class="flex flex-col items-end gap-1.5">
          <button class="btn ${isTransition ? "btn-primary" : "btn-secondary"} btn-sm"
                  onclick="handleTicketAction(${t.id}, ${target ? `'${target}'` : "null"})">
            <i data-lucide="${target === "ASSIGN" ? "user-plus" : (isTransition ? "arrow-right-circle" : "eye")}" class="w-4 h-4"></i>
            <span>${escapeHtml(t.action_label || "Xem phiếu")}</span>
          </button>
          ${rowExtraActionsHtml(t)}
        </div>
      </td>
    </tr>`;
  }).join("");
  refreshIcons();
}

/* --------------------------- MÀN HÌNH XỬ LÝ PHIẾU --------------------------- */
/**
 * Mở phiếu và xử lý TOÀN BỘ nghiệp vụ trong MỘT màn hình: khách hàng, thiết bị,
 * tiếp nhận, chẩn đoán, sửa chữa, trả máy, lịch sử, gợi ý của hệ thống và các nút
 * hành động mà tài khoản hiện tại ĐƯỢC PHÉP bấm.
 *
 * `options.autoAction` = trạng thái đích: khi mở từ nút hành động trên danh sách
 * hoặc bảng điều khiển, hộp thoại xác nhận của đúng bước đó được mở luôn
 * (nhưng vẫn kiểm tra lại với `available_actions` do backend trả về).
 *
 * Mọi dữ liệu (kể cả nhãn trạng thái và danh sách hành động) đều lấy từ backend;
 * giao diện không tự suy diễn trạng thái để tránh hiển thị sai.
 */
async function openTicketModal(ticketId, options = {}) {
  const res = await apiFetch(`/api/v1/warranty-tickets/${ticketId}`);
  if (!res.ok) {
    toastError(res, "Không mở được chi tiết phiếu bảo hành.");
    return;
  }
  const t = res.data;
  state.selectedTicket = t;
  state.currentAiResult = null;

  renderTicketWorkspace(t);
  await refreshModalAiPanel(t);
  openModal("ticket-modal");
  refreshIcons();

  if (options.autoAction) {
    const allowed = (Array.isArray(t.available_actions) ? t.available_actions : []).some(
      (action) => action.target === options.autoAction
    );
    if (allowed) startTransition(options.autoAction);
    else showToast("Bước xử lý này không còn khả dụng. Vui lòng xem lại phiếu.", "warning");
  }
}

/** Thanh tiến trình 5 bước kèm người thực hiện + thời gian của bước đã đi qua. */
function renderStepsHtml(t) {
  const steps = Array.isArray(t.steps) && t.steps.length
    ? t.steps
    : [
        { step: 1, status: "RECEIVED", label: "Tiếp nhận", state: "current" },
        { step: 2, status: "INSPECTING", label: "Kiểm tra", state: "pending" },
        { step: 3, status: "REPAIRING", label: "Sửa chữa", state: "pending" },
        { step: 4, status: "COMPLETED", label: "Hoàn tất", state: "pending" },
        { step: 5, status: "RETURNED", label: "Đã trả máy", state: "pending" },
      ];
  const chips = steps.map((step) => {
    const cls = step.state === "current"
      ? "bg-indigo-50 border-indigo-300 text-indigo-700 font-bold"
      : (step.state === "done"
        ? "bg-emerald-50 border-emerald-300 text-emerald-800 font-medium"
        : "border-slate-200 text-slate-400 bg-white");
    const who = step.by_name ? ` – ${displayText(step.by_name)}` : "";
    const when = step.at ? ` (${fmtDateTime(step.at)})` : "";
    return `<span class="px-2.5 py-1 rounded-lg border ${cls}" title="${escapeHtml(who + when)}">${step.step}. ${escapeHtml(step.label)}${step.state === "current" ? " (đang ở đây)" : ""}</span>`;
  });
  const rejected = t.status === "REJECTED"
    ? '<span class="px-2.5 py-1 rounded-lg border bg-rose-50 border-rose-300 text-rose-800 font-semibold">Từ chối (chờ trả máy)</span>'
    : "";
  return chips.join('<i data-lucide="chevron-right" class="w-3.5 h-3.5 text-slate-400"></i>') + rejected;
}

/** Danh sách điều kiện trả máy (đủ/chưa đủ) - do backend trả về. */
function renderCompletionChecklist(t) {
  const list = $("ws-completion-list");
  if (!list) return;
  const checks = Array.isArray(t.completion_checklist) ? t.completion_checklist : [];
  list.innerHTML = checks
    .map((item) => `<div class="flex items-start gap-1.5 ${item.satisfied ? "text-emerald-700 font-medium" : "text-slate-500"}">
        <span>${item.satisfied ? "✔" : "○"}</span><span>${escapeHtml(item.label)}</span>
      </div>`)
    .join("");
  const blockers = Array.isArray(t.completion_blockers) ? t.completion_blockers : [];
  const box = $("ws-completion-blockers");
  if (box) {
    box.innerHTML = blockers.length
      ? '<div class="font-semibold mb-0.5 text-rose-800">Chưa đủ điều kiện:</div>' +
        blockers.map((text) => `<div class="text-rose-700">• ${escapeHtml(text)}</div>`).join("")
      : (t.status === "COMPLETED" || t.status === "REJECTED" ? "Đủ điều kiện để xác nhận đã trả máy cho khách và đóng phiếu." : "");
  }
  const details = $("ws-completion-details");
  if (details) {
    const isTech = state.session.user && state.session.user.role === "TECHNICIAN";
    details.open = !isTech;
  }
}

/** Lịch sử xử lý: trạng thái, thời gian, người thực hiện, ghi chú. */
function renderTicketTimeline(t) {
  const box = $("modal-ticket-timeline");
  const history = Array.isArray(t.history) && t.history.length
    ? t.history
    : (Array.isArray(t.status_history) ? t.status_history : []);
  if (!history.length) {
    box.innerHTML = '<div class="text-xs text-slate-500">Chưa có lịch sử xử lý.</div>';
    return;
  }
  box.innerHTML = history.map((h, idx) => {
    const fromLabel = h.from_label || (h.from_status ? statusLabel(h.from_status) : "");
    const toLabel = h.to_label || statusLabel(h.to_status);
    const actor = h.changed_by_name ? displayText(h.changed_by_name) : userShortName(h.changed_by);
    const cleanNote = stripTechTags(humanizeText(h.note)) || "Không có ghi chú";
    return `
    <div class="flex items-start gap-3">
      <div class="w-6 h-6 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 flex items-center justify-center text-xs font-bold shrink-0">${idx + 1}</div>
      <div class="flex-1 text-xs">
        <div class="font-bold text-slate-900 flex items-center justify-between gap-2">
          <span>${escapeHtml(fromLabel ? fromLabel + " → " : "")}${escapeHtml(toLabel)}</span>
          <span class="text-slate-500 font-mono font-normal">${fmtDateTime(h.created_at)}</span>
        </div>
        <div class="text-slate-600 mt-0.5">${escapeHtml(cleanNote)}</div>
        <div class="text-slate-500 mt-0.5 font-medium">Người thực hiện: <span class="text-slate-700">${escapeHtml(actor)}</span></div>
      </div>
    </div>`;
  }).join("");
}

/** Vẽ màn hình phiếu: khối A-G + nút hành động + điều kiện hoàn tất. */
function renderTicketWorkspace(t) {
  const customer = t.customer || {};
  const device = t.device || {};
  const intake = t.intake || {};
  const repair = t.repair || {};
  const handover = t.handover || {};

  $("modal-ticket-code").textContent = t.ticket_code || "–";
  const badge = $("modal-ticket-badge");
  badge.className = `px-3 py-1 text-xs font-semibold rounded-full badge-${String(t.status).toLowerCase()}`;
  badge.textContent = t.status_label || statusLabel(t.status);
  $("modal-status-hint").textContent = t.status_hint || "";
  const handlerChip = $("modal-handler-chip");
  if (handlerChip) handlerChip.textContent = `KTV phụ trách: ${ticketTechnicianName(t)}`;
  $("modal-ticket-progress").innerHTML = renderStepsHtml(t);

  // A. Khách hàng
  $("modal-customer").textContent = displayText(customer.full_name || t.customer_name) || "–";
  $("modal-customer-phone").textContent = customer.phone || t.customer_phone || "–";
  $("modal-customer-email").textContent = customer.email || "–";

  // B. Thiết bị
  const productLine = [device.brand, device.category].filter((v) => v && String(v).trim()).join(" • ");
  $("modal-serial").textContent = device.serial_number || t.serial_number || "–";
  $("modal-product").innerHTML = escapeHtml(displayText(device.product_name || t.product_name) || "–") +
    (productLine ? ` <span class="text-slate-500">(${escapeHtml(productLine)})</span>` : "");
  $("modal-purchase-date").textContent = device.purchase_date ? fmtDate(device.purchase_date) : "–";
  $("modal-warranty-end").textContent = device.warranty_end_date
    ? fmtDate(device.warranty_end_date)
    : fmtDate(t.warranty_end_date);
  $("modal-warranty-status").innerHTML = device.warranty_status_message
    ? `<span class="font-bold ${device.warranty_status === "Đã hết hạn" ? "text-rose-700" : "text-emerald-700"}">${escapeHtml(device.warranty_status)}</span>
       <span class="text-slate-600 font-medium"> – ${escapeHtml(device.warranty_status_message)}</span>`
    : warrantyStatusHtml(t.warranty_end_date);

  // Tiếp nhận máy (ngoại quan, phụ kiện)
  $("modal-ticket-created").textContent = fmtDateTime(intake.received_at || t.created_at);
  $("modal-created-by").textContent = intake.received_by_name || userName(t.created_by);
  if ($("modal-ticket-desc")) {
    $("modal-ticket-desc").textContent = humanizeText(intake.issue_description || t.issue_description) || "";
  }
  if ($("modal-device-condition")) {
    $("modal-device-condition").textContent = intake.device_condition || t.device_condition || "Thân máy nguyên vẹn, không ghi nhận trầy xước đặc biệt.";
  }
  if ($("modal-accessories")) {
    $("modal-accessories").textContent = intake.accessories_accompanying || t.accessories_accompanying || "Không kèm phụ kiện.";
  }

  // Khối "Kiểm tra và chẩn đoán": mô tả khách + gợi ý AI + kết luận KTV
  if ($("ws-support-customer")) {
    $("ws-support-customer").textContent =
      humanizeText((intake && intake.issue_description) || t.issue_description) ||
      "Khách hàng chưa cung cấp mô tả tình trạng lỗi.";
  }
  renderAiSuggestionBox(t);
  renderDiagnosisOfficial(t);

  // E. Sửa chữa
  renderRepairSection(t);
  // F. Trả máy
  renderHandoverSection(t);

  // Điều kiện hoàn tất + lý do từ chối (nếu có)
  renderCompletionChecklist(t);

  // Đề xuất từ chối bảo hành (chờ Quản lý duyệt)
  const proposalBox = $("modal-rejection-proposal-box");
  if (proposalBox) {
    if (t.status === "INSPECTING" && t.rejection_proposal_note) {
      proposalBox.classList.remove("hidden");
      const noteEl = $("modal-rejection-proposal-note");
      if (noteEl) noteEl.textContent = humanizeText(t.rejection_proposal_note);
      const actionEl = $("modal-rejection-proposal-actions");
      if (actionEl) {
        if (isManager() || hasPerm("ticket.reject")) {
          actionEl.innerHTML = `
            <button type="button" class="btn btn-danger btn-sm" onclick="reviewRejectionProposal(${t.id}, 'APPROVED')">
              <i data-lucide="check-circle" class="w-3.5 h-3.5"></i> Duyệt từ chối
            </button>
            <button type="button" class="btn btn-secondary btn-sm" onclick="reviewRejectionProposal(${t.id}, 'DECLINED')">
              <i data-lucide="x-circle" class="w-3.5 h-3.5"></i> Không đồng ý (Tiếp tục xử lý)
            </button>`;
        } else {
          actionEl.innerHTML = `<span class="text-xs text-amber-800 italic flex items-center gap-1.5"><i data-lucide="clock" class="w-3.5 h-3.5"></i> Đã gửi đề xuất từ chối, đang chờ Quản lý xem xét phê duyệt.</span>`;
        }
      }
    } else {
      proposalBox.classList.add("hidden");
    }
  }

  const rejectionBox = $("modal-rejection-box");
  if (t.status === "REJECTED" && t.rejection_reason) {
    rejectionBox.classList.remove("hidden");
    $("modal-rejection-reason").textContent = humanizeText(t.rejection_reason);
  } else {
    rejectionBox.classList.add("hidden");
  }

  renderTicketTimeline(t);
  renderStateActions(t);
  refreshIcons();
}

/** Khối gợi ý loại lỗi tham khảo (AI) - thu gọn khi đã có kết luận chính thức. */
function renderAiSuggestionBox(t) {
  const container = $("ws-ai-suggestion-box");
  if (!container) return;
  const ai = t.ai_suggestion || {};
  const diagnosis = t.diagnosis || {};
  const hasConclusion = Boolean(diagnosis.error_category_name || diagnosis.note);
  const isOpen = !hasConclusion;

  if (!ai.available) {
    container.innerHTML = `
      <div class="p-3 rounded-lg border border-slate-200 bg-white text-xs text-slate-500 flex items-center justify-between">
        <span>Chưa có gợi ý loại lỗi từ hệ thống AI.</span>
      </div>`;
    return;
  }

  const isSim = ai.is_simulation;
  const simBadge = isSim
    ? `<span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-100 text-amber-800 border border-amber-200">Chế độ mô phỏng</span>`
    : `<span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-indigo-100 text-indigo-800 border border-indigo-200">${escapeHtml(ai.simulation_label || "AI Engine")}</span>`;

  const hasValidLabel = Boolean(ai.suggested_category_id && ai.suggested_category_name);
  const labelText = hasValidLabel
    ? displayText(ai.suggested_category_name)
    : "Chưa xác định nhóm lỗi";

  // Khi thiếu thông tin hoặc không xác định được nhóm lỗi: KHÔNG hiển thị phần trăm độ chắc chắn
  const confText = (hasValidLabel && ai.confidence !== null && ai.confidence !== undefined)
    ? ` • <span class="font-mono font-bold ${confidenceColor(ai.confidence)}">Mức độ chắc chắn: ${confidencePercent(ai.confidence)}</span>`
    : "";

  let questionsHtml = "";
  if (Array.isArray(ai.need_more_information) && ai.need_more_information.length) {
    questionsHtml = `
      <div class="mt-2.5 p-2.5 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-900">
        <div class="font-bold mb-1 flex items-center gap-1">
          <i data-lucide="help-circle" class="w-3.5 h-3.5 text-amber-700"></i> Câu hỏi bổ sung cho khách hàng:
        </div>
        <ul class="list-disc pl-4 space-y-0.5">
          ${ai.need_more_information.map((q) => `<li>${escapeHtml(humanizeText(q))}</li>`).join("")}
        </ul>
      </div>`;
  }

  const userRole = state.session.user ? state.session.user.role : "";
  const isAssignedTech = userRole === "TECHNICIAN" && t.assigned_technician_id === (state.session.user && state.session.user.id);
  const isTerminal = ["COMPLETED", "REJECTED", "RETURNED"].includes(t.status);
  const canConfirmAi = (isAssignedTech || userRole === "MANAGER") && !isTerminal && hasValidLabel && ai.review_status === "PENDING";

  const actionButtons = canConfirmAi
    ? `<div class="mt-2.5 pt-2 border-t border-purple-100 flex items-center gap-2">
        <button type="button" class="btn btn-sm btn-success" onclick="confirmAiCategoryFromSection(${ai.ai_result_id})">
          <i data-lucide="check" class="w-3.5 h-3.5"></i> Xác nhận nhóm lỗi này
        </button>
        <button type="button" class="btn btn-sm btn-secondary" onclick="openDiagnosisModal()">
          <i data-lucide="edit" class="w-3.5 h-3.5"></i> Chọn nhóm lỗi khác
        </button>
      </div>`
    : "";

  const reviewBadge = ai.review_status === "APPROVED"
    ? '<span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">Đã xác nhận vào phiếu</span>'
    : (ai.review_status === "REJECTED"
        ? '<span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-100 text-rose-800 border border-rose-200">Không dùng gợi ý</span>'
        : '<span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-purple-100 text-purple-800 border border-purple-200">Chờ xác nhận</span>');

  container.innerHTML = `
    <details class="group rounded-lg border border-purple-200 bg-purple-50/40" ${isOpen ? "open" : ""}>
      <summary class="p-3 cursor-pointer select-none flex items-center justify-between text-xs">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="font-bold text-purple-900 flex items-center gap-1.5">
            <i data-lucide="wand-2" class="w-3.5 h-3.5 text-purple-600"></i> Gợi ý tham khảo (AI)
          </span>
          ${simBadge}
          <strong class="${hasValidLabel ? "text-purple-800" : "text-amber-800"}">${escapeHtml(labelText)}</strong>
          ${confText}
          ${reviewBadge}
        </div>
        <i data-lucide="chevron-down" class="w-4 h-4 text-purple-600 group-open:rotate-180 transition-transform"></i>
      </summary>
      <div class="px-3 pb-3 pt-1 text-xs border-t border-purple-100 text-slate-700">
        <div class="text-slate-600 mt-1">${escapeHtml(aiReasonText(ai))}</div>
        ${questionsHtml}
        ${actionButtons}
        <div class="text-[11px] text-slate-500 mt-2 italic">
          Gợi ý AI chỉ mang tính tham khảo. Kết luận chính thức do kỹ thuật viên phụ trách hoặc quản lý xác nhận.
        </div>
      </div>
    </details>`;
}

/** Khối kết luận chính thức của kỹ thuật viên. */
function renderDiagnosisOfficial(t) {
  const diagnosis = t.diagnosis || {};
  const meta = [];
  if (diagnosis.error_category_name) {
    meta.push(`Nhóm lỗi chính thức: <strong class="text-slate-900">${escapeHtml(displayText(diagnosis.error_category_name))}</strong>`);
  } else {
    meta.push(`Nhóm lỗi: <span class="text-amber-800 font-medium">Chưa xác nhận</span>`);
  }
  if (diagnosis.confirmed_by_name) {
    meta.push(`Người xác nhận: <strong class="text-slate-800">${escapeHtml(displayText(diagnosis.confirmed_by_name))}</strong>`);
  }
  if (diagnosis.confirmed_at) {
    meta.push(`Thời điểm: <span class="font-mono text-slate-700">${fmtDateTime(diagnosis.confirmed_at)}</span>`);
  }

  const badgeBox = $("ws-official-badge");
  if (badgeBox) {
    badgeBox.innerHTML = diagnosis.error_category_name
      ? '<span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">Đã có kết luận kỹ thuật</span>'
      : '<span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-100 text-amber-800 border border-amber-200">Chờ kỹ thuật viên kết luận</span>';
  }

  $("ws-diagnosis-body").innerHTML = humanizeText(diagnosis.note)
    ? escapeHtml(humanizeText(diagnosis.note))
    : '<span class="text-amber-800 font-medium">Chưa có ghi chép chẩn đoán. Kỹ thuật viên phụ trách cần kiểm tra máy và ghi nhận kết luận.</span>';
  $("ws-diagnosis-meta").innerHTML = meta.join(" &bull; ");

  const btn = $("btn-edit-diagnosis");
  if (btn) btn.classList.toggle("hidden", !t.can_edit_diagnosis);

  const btnAiSuggest = $("btn-ai-suggest-ticket");
  const isTerminal = ["COMPLETED", "REJECTED", "RETURNED"].includes(t.status);
  if (btnAiSuggest) {
    btnAiSuggest.classList.toggle("hidden", isTerminal || !hasPerm("ai.classify"));
  }
}

/** Xác nhận gợi ý loại lỗi trực tiếp từ khu vực Kiểm tra và chẩn đoán. */
async function confirmAiCategoryFromSection(resultId) {
  if (!state.selectedTicket) return;
  const t = state.selectedTicket;
  const user = state.session.user;
  if (!user) {
    showToast("Vui lòng đăng nhập lại.", "warning");
    return;
  }
  const res = await apiFetch(`/api/v1/ai/results/${resultId}/review`, {
    method: "PATCH",
    body: { reviewed_by: user.id, decision: "APPROVED" },
  });
  if (!res.ok) {
    toastError(res, "Không xác nhận được nhóm lỗi.");
    return;
  }
  showToast("Đã xác nhận nhóm lỗi kỹ thuật thành công.", "success");
  await openTicketModal(t.id);
  await loadTickets();
  await loadDashboard();
}

/** E. Khối sửa chữa: nội dung đã kiểm tra/đã sửa, linh kiện thay thế, nhật ký sửa chữa. */
function renderRepairSection(t) {
  const repair = t.repair || {};
  $("ws-repair-body").innerHTML = humanizeText(repair.content)
    ? escapeHtml(humanizeText(repair.content))
    : '<span class="text-slate-500">Chưa ghi nhận nội dung đã kiểm tra / đã sửa chữa.</span>';

  const meta = [];
  if (repair.technician_name) meta.push(`Người thực hiện: <span class="text-slate-800 font-medium">${escapeHtml(displayText(repair.technician_name))}</span>`);
  if (repair.recorded_at) meta.push(`Thời điểm: <span class="font-mono text-slate-700">${fmtDateTime(repair.recorded_at)}</span>`);
  if (repair.note) meta.push(`Ghi chú: ${escapeHtml(humanizeText(repair.note))}`);
  $("ws-repair-parts").innerHTML =
    (repair.parts
      ? `Linh kiện/thành phần thay thế: <span class="text-slate-900 font-medium">${escapeHtml(humanizeText(repair.parts))}</span><br>`
      : "") + meta.join(" &bull; ");

  const logs = Array.isArray(repair.logs) ? repair.logs : [];
  $("ws-repair-logs").innerHTML = logs.length
    ? `<div class="text-xs text-slate-600 font-bold mb-1">Nhật ký sửa chữa (${logs.length} lần):</div>` +
      logs.map((log) => `<div class="text-xs text-slate-600">• <span class="font-mono text-slate-700">${fmtDateTime(log.logged_at)}</span>
        – <strong class="text-slate-800">${escapeHtml(displayText(log.technician_name) || "")}</strong>: ${escapeHtml(humanizeText(log.action_description) || "")}
        ${log.parts_used ? `<span class="text-slate-500">(linh kiện: ${escapeHtml(humanizeText(log.parts_used))})</span>` : ""}</div>`).join("")
    : "";

  const btn = $("btn-edit-repair");
  if (btn) btn.classList.toggle("hidden", !t.can_edit_repair);
}

/** F. Khối trả máy: nổi bật khi máy đang "Chờ trả máy" để nhân viên biết cần bàn giao. */
function renderHandoverSection(t) {
  const handover = t.handover || {};
  const box = $("ws-handover-box");
  const isWaiting = t.status === "COMPLETED" || t.status === "REJECTED";
  const isClosed = t.status === "RETURNED";
  box.className = "p-3.5 rounded-xl border " + (
    isWaiting
      ? "border-cyan-200 bg-cyan-50"
      : (isClosed ? "border-emerald-200 bg-emerald-50" : "border-slate-200 bg-slate-50")
  );

  const lines = [
    `<div class="font-bold ${isWaiting ? "text-cyan-900" : (isClosed ? "text-emerald-900" : "text-slate-900")}">${escapeHtml(handover.status_message || statusLabel(t.status))}</div>`,
  ];
  if (t.resolution) {
    const resLabel = t.resolution === "COMPLETED" ? "Sửa chữa hoàn tất" : (t.resolution === "REJECTED" ? "Từ chối bảo hành" : t.resolution);
    lines.push(`<div class="text-xs text-slate-600 mt-1">Kết quả đóng phiếu: <span class="font-bold text-slate-900">${escapeHtml(resLabel)}</span></div>`);
  }
  if (handover.processing_time_display) {
    lines.push(`<div class="text-xs text-slate-600 mt-1">Thời gian xử lý kỹ thuật: <span class="font-mono text-slate-900 font-semibold">${escapeHtml(handover.processing_time_display)}</span></div>`);
  } else if (handover.processing_time_hours !== null && handover.processing_time_hours !== undefined) {
    lines.push(`<div class="text-xs text-slate-600 mt-1">Thời gian xử lý kỹ thuật: <span class="font-mono text-slate-900 font-semibold">${handover.processing_time_hours} giờ</span></div>`);
  }
  if (handover.waiting_time_display) {
    lines.push(`<div class="text-xs text-slate-600 mt-0.5">Thời gian chờ nhận máy: <span class="font-mono text-slate-900 font-semibold">${escapeHtml(handover.waiting_time_display)}</span></div>`);
  } else if (handover.waiting_time_hours !== null && handover.waiting_time_hours !== undefined) {
    lines.push(`<div class="text-xs text-slate-600 mt-0.5">Thời gian chờ nhận máy: <span class="font-mono text-slate-900 font-semibold">${handover.waiting_time_hours} giờ</span></div>`);
  }
  if (handover.repair_completed_at) {
    lines.push(`<div class="text-slate-500 mt-1 text-xs">Hoàn thành sửa chữa: <span class="font-mono text-slate-700">${fmtDateTime(handover.repair_completed_at)}</span>${
      handover.repair_completed_by_name
        ? ` – <span class="text-slate-800 font-medium">${escapeHtml(displayText(handover.repair_completed_by_name))}</span>`
        : ""}</div>`);
  }
  if (t.handed_over_at) {
    lines.push(`<div class="text-slate-500 mt-1 text-xs">Đã trả máy lúc: <span class="font-mono text-slate-700">${fmtDateTime(t.handed_over_at)}</span>${
      handover.returned_by_name
        ? ` – <span class="text-slate-800 font-medium">${escapeHtml(displayText(handover.returned_by_name))}</span>`
        : ""}</div>`);
  }
  if (handover.note) {
    lines.push(`<div class="text-slate-600 mt-1 text-xs">Ghi chú bàn giao: <span class="text-slate-900 font-medium">${escapeHtml(humanizeText(handover.note))}</span></div>`);
  }
  $("ws-handover-body").innerHTML = lines.join("");
}

/** Nút chuyển trạng thái: CHỈ hiện những hành động mà BACKEND cho phép vai trò hiện tại. */
function renderStateActions(t) {
  const box = $("modal-state-actions");
  if (!box) return;
  const notesBox = $("modal-permission-notes");
  const actions = Array.isArray(t.available_actions) ? t.available_actions : [];
  const userRole = state.session.user ? state.session.user.role : null;

  if (notesBox) {
    notesBox.innerHTML = "";
  }

  // KTV xem phiếu Hoàn tất: chỉ ghi ngắn: "Đã hoàn tất sửa chữa. Chờ quầy tiếp nhận bàn giao."
  if (userRole === "TECHNICIAN" && t.status === "COMPLETED") {
    box.innerHTML = `<div class="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 font-semibold flex items-center gap-2">
      <i data-lucide="check-circle" class="w-4 h-4 text-emerald-600 shrink-0"></i>
      <span>Đã hoàn tất sửa chữa. Chờ quầy tiếp nhận bàn giao.</span>
    </div>`;
    refreshIcons();
    return;
  }

  const buttons = [];

  // Nút phân công / phân công lại KTV: CHỈ QUẢN LÝ được thực hiện (khi phiếu đang ở RECEIVED, INSPECTING, REPAIRING)
  const assignableStatuses = ["RECEIVED", "INSPECTING", "REPAIRING"];
  if (isManager() && assignableStatuses.includes(t.status)) {
    const assignText = t.assigned_technician_id ? "Phân công lại KTV" : "Phân công KTV";
    buttons.push(`<button class="btn btn-secondary" onclick="openAssignModal(${t.id})">
      <i data-lucide="user-plus" class="w-4 h-4"></i> ${assignText}</button>`);
  }

  // Các nút hành động chính từ backend
  actions.forEach((action) => {
    buttons.push(`<button class="btn btn-${escapeHtml(action.style || "primary")}" onclick="startTransition('${action.target}')">
      <i data-lucide="arrow-right-circle" class="w-4 h-4"></i> ${escapeHtml(action.button_label)}</button>`);
  });

  // Nút Đề xuất từ chối: KTV được phân công hoặc Quản lý khi phiếu ở INSPECTING và chưa có đề xuất
  const isAssignedTech = userRole === "TECHNICIAN" && t.assigned_technician_id === (state.session.user && state.session.user.id);
  if (t.status === "INSPECTING" && (isAssignedTech || userRole === "MANAGER") && !t.rejection_proposal_note) {
    buttons.push(`<button class="btn btn-danger" onclick="openProposeRejectionModal(${t.id})">
      <i data-lucide="file-warning" class="w-4 h-4"></i> Đề xuất từ chối</button>`);
  }

  if (!buttons.length) {
    const done = t.status === "RETURNED";
    const isUnassigned = !t.assigned_technician_id;
    if (isUnassigned && t.status === "RECEIVED" && userRole === "RECEPTIONIST") {
      box.innerHTML = `<div class="p-3 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-800 font-medium flex items-center gap-2">
        <i data-lucide="clock" class="w-4 h-4 text-amber-600 shrink-0"></i>
        <span>Phiếu chưa phân công kỹ thuật viên. Đang chờ Quản lý phân công.</span>
      </div>`;
    } else {
      box.innerHTML = done
        ? `<div class="text-xs text-slate-500 font-medium flex items-center gap-1.5"><i data-lucide="check" class="w-4 h-4 text-emerald-600"></i> Phiếu đã bàn giao máy cho khách và đóng thành công.</div>`
        : '<div class="text-xs text-slate-500">Không có thao tác khả dụng ở bước hiện tại.</div>';
    }
    refreshIcons();
    return;
  }
  box.innerHTML = buttons.join("");
  refreshIcons();
}

/** Tìm mô tả hành động (do backend trả về) theo trạng thái đích. */
function findAction(targetStatus) {
  const t = state.selectedTicket;
  const actions = t && Array.isArray(t.available_actions) ? t.available_actions : [];
  return actions.find((action) => action.target === targetStatus) || null;
}

/** Câu mô tả ngắn về thiết bị + phiếu để hiển thị trong hộp thoại xác nhận. */
function ticketConfirmSummary(t) {
  const serial = t.serial_number || (t.device && t.device.serial_number) || "–";
  const product = displayText(t.product_name || (t.device && t.device.product_name)) || "Thiết bị";
  return `Thiết bị: <strong>${escapeHtml(product)}</strong> (số sê-ri <span class="font-mono">${escapeHtml(serial)}</span>)<br>
    Phiếu: <strong class="font-mono">${escapeHtml(t.ticket_code)}</strong>
    &bull; Khách hàng: <strong>${escapeHtml(displayText(t.customer_name) || "–")}</strong>`;
}

/** Danh mục lỗi để kỹ thuật viên chọn khi ghi nhận chẩn đoán (không phải chọn hộ AI). */
function categorySelectOptions(selectedId) {
  const options = state.categories.map((c) => ({ value: c.id, label: displayText(c.name) }));
  options.unshift({ value: "", label: "-- Chưa xác định loại lỗi --" });
  return { options, selected: selectedId ? String(selectedId) : "" };
}

/** Bắt đầu chuyển trạng thái: hộp thoại xác nhận + hỏi đúng thông tin nghiệp vụ của bước. */
function startTransition(targetStatus) {
  const t = state.selectedTicket;
  if (!t) return;
  const action = findAction(targetStatus);
  if (!action) {
    showToast("Bước này không khả dụng cho vai trò hiện tại.", "warning");
    return;
  }
  if (!hasPerm("ticket.update_status")) {
    showToast("Vai trò hiện tại không có quyền cập nhật tình trạng phiếu.", "warning");
    return;
  }

  const isReject = targetStatus === "REJECTED";
  const staff = staffSelectOptions(targetStatus === "RETURNED" ? "RECEPTIONIST" : "TECHNICIAN");
  const fieldSpecs = Array.isArray(action.fields) ? action.fields : [];
  const categories = categorySelectOptions(t.error_category_id);
  const fields = [];

  // 1. Phân công kỹ thuật viên (nếu bước chuyển sang INSPECTING yêu cầu)
  if (fieldSpecs.includes("technician_id")) {
    const techUsers = (state.users || []).filter((u) => u.role === "TECHNICIAN");
    fields.push({
      id: "technician_id",
      label: "Kỹ thuật viên phụ trách",
      options: techUsers.map((u) => ({ value: u.id, label: `${displayText(u.full_name)} (${u.username})` })),
      defaultValue: t.assigned_technician_id ? String(t.assigned_technician_id) : (techUsers.length ? String(techUsers[0].id) : ""),
      required: true,
      hint: "Bắt buộc có kỹ thuật viên phụ trách trước khi chuyển sang Kiểm tra.",
    });
  }

  // 2. Chẩn đoán & xác định đủ điều kiện bảo hành (INSPECTING -> REPAIRING)
  if (fieldSpecs.includes("diagnosis_note")) {
    fields.push({
      id: "diagnosis_note",
      label: "Kết luận chẩn đoán của kỹ thuật viên",
      placeholder: "Ví dụ: IC nguồn bị chập, tụ lọc nguồn phồng",
      defaultValue: t.diagnosis && t.diagnosis.note ? t.diagnosis.note : "",
      required: true,
      hint: "Đây là kết luận của kỹ thuật viên, KHÔNG phải gợi ý của hệ thống.",
    });
  }
  if (fieldSpecs.includes("error_category_id") && state.categories.length) {
    fields.push({
      id: "error_category_id",
      label: "Loại lỗi theo kết luận kỹ thuật",
      options: categories.options,
      defaultValue: categories.selected,
    });
  }
  if (fieldSpecs.includes("is_warranty_eligible")) {
    fields.push({
      id: "is_warranty_eligible",
      label: "Xác định điều kiện bảo hành",
      options: [
        { value: "true", label: "✔ Đủ điều kiện bảo hành" },
        { value: "false", label: "✖ Không đủ điều kiện bảo hành" },
      ],
      defaultValue: t.is_warranty_eligible === false ? "false" : "true",
      required: true,
      hint: "Bắt buộc xác định đủ điều kiện bảo hành để chuyển sang Sửa chữa.",
    });
  }
  if (fieldSpecs.includes("warranty_check_note")) {
    fields.push({
      id: "warranty_check_note",
      label: "Ghi chú điều kiện bảo hành (không bắt buộc)",
      placeholder: "Ví dụ: Máy còn nguyên tem, không có dấu hiệu va đập hay vào nước",
      defaultValue: t.warranty_check_note || "",
    });
  }

  // 3. Sửa chữa & Kiểm tra sau sửa (REPAIRING -> COMPLETED)
  if (fieldSpecs.includes("repair_content")) {
    fields.push({
      id: "repair_content",
      label: "Nội dung đã kiểm tra / đã sửa chữa",
      placeholder: "Ví dụ: Thay IC nguồn RT8205, vệ sinh tản nhiệt, chạy thử 2 giờ",
      defaultValue: t.repair && t.repair.content ? t.repair.content : "",
      required: true,
    });
  }
  if (fieldSpecs.includes("repair_parts")) {
    fields.push({
      id: "repair_parts",
      label: "Linh kiện / thành phần đã thay (không bắt buộc)",
      placeholder: "Ví dụ: IC nguồn RT8205, tụ 470uF",
      defaultValue: t.repair && t.repair.parts ? t.repair.parts : "",
    });
  }
  if (fieldSpecs.includes("repair_test_passed")) {
    fields.push({
      id: "repair_test_passed",
      label: "Kết quả kiểm tra sau sửa",
      options: [
        { value: "true", label: "✔ Đạt yêu cầu (Máy hoạt động ổn định)" },
        { value: "false", label: "✖ Chưa đạt yêu cầu" },
      ],
      defaultValue: t.repair_test_passed === false ? "false" : "true",
      required: true,
      hint: "Bắt buộc kiểm tra sau sửa đạt yêu cầu mới được xác nhận Hoàn tất.",
    });
  }
  if (fieldSpecs.includes("repair_test_note")) {
    fields.push({
      id: "repair_test_note",
      label: "Ghi chú kiểm tra sau sửa (không bắt buộc)",
      placeholder: "Ví dụ: Đã test chạy thử 2 giờ, nhiệt độ ổn định",
      defaultValue: t.repair_test_note || "",
    });
  }

  // 4. Lý do từ chối (INSPECTING -> REJECTED)
  if (fieldSpecs.includes("rejection_reason")) {
    fields.push({
      id: "rejection_reason",
      label: "Lý do từ chối bảo hành (bắt buộc)",
      placeholder: "Ví dụ: Thiết bị vào nước, chập cháy linh kiện, không thuộc phạm vi bảo hành",
      required: true,
    });
  }

  // 5. Bàn giao trả máy (COMPLETED / REJECTED -> RETURNED)
  if (fieldSpecs.includes("handover_note")) {
    fields.push({
      id: "handover_note",
      label: "Thông tin bàn giao trả máy cho khách (bắt buộc)",
      placeholder: "Ví dụ: Khách đã kiểm tra máy, ký nhận bàn giao và nhận lại phiếu bảo hành",
      defaultValue: t.handover && t.handover.note ? t.handover.note : "",
      required: true,
    });
  }

  fields.push({
    id: "note",
    label: action.note_label || "Ghi chú xử lý (không bắt buộc)",
    placeholder: action.note_placeholder || "",
    defaultValue: "",
  });

  showActionModal({
    title: action.confirm_question || `Chuyển sang "${action.target_label}"`,
    message: `${ticketConfirmSummary(t)}<br><span class="text-xs text-slate-400">${escapeHtml(action.description || "")}</span>`,
    selectLabel: "Người thực hiện",
    selectOptions: staff.options,
    selectDefault: staff.defaultId,
    fields,
    confirmLabel: action.button_label || "Xác nhận",
    danger: isReject,
    onConfirm: ({ actorId, values }) => executeTransition(t.id, targetStatus, values, actorId),
  });
}

/** Gửi yêu cầu chuyển trạng thái kèm thông tin nghiệp vụ đã nhập. */
async function executeTransition(ticketId, targetStatus, values, changedBy) {
  if (!changedBy) {
    showToast("Không xác định được người thực hiện. Vui lòng tải lại trang.", "warning");
    return;
  }
  const action = findAction(targetStatus);
  const payload = {
    new_status: targetStatus,
    changed_by: changedBy,
    note: values.note || `Chuyển sang ${(action && action.target_label) || statusLabel(targetStatus)}`,
  };

  // Chuẩn hóa kiểu dữ liệu
  if (values.technician_id) payload.technician_id = parseInt(values.technician_id, 10);
  if (values.error_category_id) payload.error_category_id = parseInt(values.error_category_id, 10);
  if (values.is_warranty_eligible !== undefined && values.is_warranty_eligible !== "") {
    payload.is_warranty_eligible = values.is_warranty_eligible === "true";
  }
  if (values.repair_test_passed !== undefined && values.repair_test_passed !== "") {
    payload.repair_test_passed = values.repair_test_passed === "true";
  }
  [
    "diagnosis_note",
    "warranty_check_note",
    "repair_content",
    "repair_parts",
    "repair_note",
    "repair_test_note",
    "rejection_reason",
    "handover_note",
    "rejection_proposal_note",
  ].forEach((key) => {
    if (values[key]) payload[key] = values[key];
  });

  const res = await apiFetch(`/api/v1/warranty-tickets/${ticketId}/status`, { method: "PATCH", body: payload });
  if (!res.ok) {
    toastError(res, "Không chuyển được trạng thái phiếu.");
    return;
  }
  showToast(`Đã chuyển phiếu sang trạng thái "${(action && action.target_label) || statusLabel(targetStatus)}".`, "success");
  if (state.selectedTicket && state.selectedTicket.id === ticketId) {
    await openTicketModal(ticketId);
  }
  await loadTickets();
  await loadDashboard();
}

/** Mở modal phân công kỹ thuật viên phụ trách phiếu. */
async function openAssignModal(ticketId) {
  if (!isManager()) {
    showToast("Chỉ Quản lý mới có quyền phân công hoặc phân công lại kỹ thuật viên.", "warning");
    return;
  }
  let t = state.selectedTicket && state.selectedTicket.id === ticketId ? state.selectedTicket : null;
  if (!t) {
    t = (state.tickets || []).find((item) => item.id === ticketId);
  }
  if (!t) {
    const res = await apiFetch(`/api/v1/warranty-tickets/${ticketId}`);
    if (res.ok && res.data) t = res.data;
  }
  if (!t) {
    showToast("Không tìm thấy thông tin phiếu bảo hành.", "warning");
    return;
  }
  const assignableStatuses = ["RECEIVED", "INSPECTING", "REPAIRING"];
  if (!assignableStatuses.includes(t.status)) {
    showToast(
      `Không thể phân công kỹ thuật viên cho phiếu ở trạng thái ${displayText(t.status_label || statusLabel(t.status))}. Chỉ phân công khi phiếu đang Tiếp nhận, Kiểm tra hoặc Sửa chữa.`,
      "warning"
    );
    return;
  }
  if (!state.users || !state.users.length) {
    await loadReferenceData();
  }
  const techUsers = (state.users || []).filter((u) => u.role === "TECHNICIAN");
  if (!techUsers.length) {
    showToast("Không có tài khoản kỹ thuật viên nào trong hệ thống.", "warning");
    return;
  }

  const isReassign = Boolean(t.assigned_technician_id);
  showActionModal({
    title: isReassign ? "Phân công lại kỹ thuật viên" : "Phân công kỹ thuật viên",
    message: `${ticketConfirmSummary(t)}<br><span class="text-xs text-slate-500">Chỉ định kỹ thuật viên chịu trách nhiệm kiểm tra và sửa chữa thiết bị này (Thẩm quyền của Quản lý).</span>`,
    selectLabel: "Quản lý phân công",
    selectOptions: staffSelectOptions("MANAGER").options,
    selectDefault: staffSelectOptions("MANAGER").defaultId,
    fields: [
      {
        id: "technician_id",
        label: "Kỹ thuật viên phụ trách",
        options: techUsers.map((u) => ({ value: u.id, label: `${displayText(u.full_name)} (${u.username})` })),
        defaultValue: t.assigned_technician_id ? String(t.assigned_technician_id) : String(techUsers[0].id),
        required: true,
      },
      {
        id: "note",
        label: "Ghi chú phân công",
        placeholder: "Ví dụ: Khách cần lấy gấp trước chiều mai...",
        defaultValue: "",
      },
    ],
    confirmLabel: "Xác nhận phân công",
    onConfirm: async ({ actorId, values }) => {
      const techId = parseInt(values.technician_id, 10);
      const res = await apiFetch(`/api/v1/warranty-tickets/${t.id}/assign`, {
        method: "POST",
        body: { technician_id: techId, note: values.note || null },
      });
      if (!res.ok) {
        toastError(res, "Không phân công được kỹ thuật viên.");
        return;
      }
      showToast("Đã phân công kỹ thuật viên phụ trách thành công.", "success");
      if (state.selectedTicket && state.selectedTicket.id === t.id) {
        await openTicketModal(t.id);
      }
      await loadTickets();
      await loadDashboard();
    },
  });
}

/** Mở modal để KTV ghi đề xuất từ chối bảo hành. */
async function openProposeRejectionModal(ticketId) {
  let t = state.selectedTicket && state.selectedTicket.id === ticketId ? state.selectedTicket : null;
  if (!t) {
    t = (state.tickets || []).find((item) => item.id === ticketId);
  }
  if (!t) {
    const res = await apiFetch(`/api/v1/warranty-tickets/${ticketId}`);
    if (res.ok && res.data) t = res.data;
  }
  if (!t) return;

  showActionModal({
    title: "Đề xuất từ chối bảo hành",
    message: `${ticketConfirmSummary(t)}<br><span class="text-xs text-slate-500">Ghi lại đề xuất và bằng chứng kiểm tra để Quản lý xem xét duyệt từ chối.</span>`,
    selectLabel: "Kỹ thuật viên đề xuất",
    selectOptions: staffSelectOptions("TECHNICIAN").options,
    selectDefault: staffSelectOptions("TECHNICIAN").defaultId,
    fields: [
      {
        id: "proposal_note",
        label: "Lý do đề xuất & Bằng chứng kiểm tra (bắt buộc)",
        placeholder: "Ví dụ: Mainboard bị rỉ sét do ngấm nước, tem bảo hành rách, có dấu hiệu sửa chữa bên ngoài...",
        required: true,
      },
    ],
    confirmLabel: "Gửi đề xuất",
    danger: true,
    onConfirm: async ({ actorId, values }) => {
      const res = await apiFetch(`/api/v1/warranty-tickets/${t.id}/propose-rejection`, {
        method: "POST",
        body: { proposal_note: values.proposal_note },
      });
      if (!res.ok) {
        toastError(res, "Không gửi được đề xuất từ chối.");
        return;
      }
      showToast("Đã gửi đề xuất từ chối bảo hành cho Quản lý.", "success");
      if (state.selectedTicket && state.selectedTicket.id === t.id) {
        await openTicketModal(t.id);
      }
      await loadTickets();
      await loadDashboard();
    },
  });
}

/** Ghi nhận CHẨN ĐOÁN của kỹ thuật viên mà không đổi trạng thái phiếu. */
function openDiagnosisModal() {
  const t = state.selectedTicket;
  if (!t) return;
  if (!t.can_edit_diagnosis) {
    showToast("Chỉ kỹ thuật viên hoặc quản lý được ghi nhận chẩn đoán.", "warning");
    return;
  }
  const categories = categorySelectOptions(t.error_category_id);
  const staff = staffSelectOptions("TECHNICIAN");
  showActionModal({
    title: "Ghi nhận chẩn đoán",
    message: `${ticketConfirmSummary(t)}<br><span class="text-xs text-slate-400">Kết luận này do kỹ thuật viên kiểm tra máy, không phải gợi ý của hệ thống.</span>`,
    selectLabel: "Kỹ thuật viên kết luận",
    selectOptions: staff.options,
    selectDefault: staff.defaultId,
    fields: [
      {
        id: "diagnosis_note",
        label: "Kết luận chẩn đoán",
        placeholder: "Ví dụ: IC nguồn bị chập, tụ lọc nguồn phồng",
        defaultValue: t.diagnosis && t.diagnosis.note ? t.diagnosis.note : "",
        required: true,
      },
      {
        id: "error_category_id",
        label: "Loại lỗi theo kết luận kỹ thuật",
        options: categories.options,
        defaultValue: categories.selected,
      },
      { id: "note", label: "Ghi chú thêm (không bắt buộc)", placeholder: "" },
    ],
    confirmLabel: "Lưu chẩn đoán",
    onConfirm: ({ actorId, values }) => saveDiagnosis(t.id, actorId, values),
  });
}

/** Ghi nhận NỘI DUNG SỬA CHỮA (đã sửa + linh kiện) mà không đổi trạng thái phiếu. */
function openRepairModal() {
  const t = state.selectedTicket;
  if (!t) return;
  if (!t.can_edit_repair) {
    showToast("Chỉ kỹ thuật viên hoặc quản lý được ghi nhận nội dung sửa chữa.", "warning");
    return;
  }
  const staff = staffSelectOptions("TECHNICIAN");
  showActionModal({
    title: "Ghi nhận nội dung sửa chữa",
    message: `${ticketConfirmSummary(t)}<br><span class="text-xs text-slate-400">Thông tin này là việc đã làm thực tế, dùng để tra cứu khi khách hỏi lại.</span>`,
    selectLabel: "Kỹ thuật viên thực hiện",
    selectOptions: staff.options,
    selectDefault: staff.defaultId,
    fields: [
      {
        id: "repair_content",
        label: "Nội dung đã kiểm tra / đã sửa chữa",
        placeholder: "Ví dụ: Thay IC nguồn, vệ sinh tản nhiệt, chạy thử 2 giờ",
        defaultValue: t.repair && t.repair.content ? t.repair.content : "",
        required: true,
      },
      {
        id: "repair_parts",
        label: "Linh kiện / thành phần đã thay (không bắt buộc)",
        placeholder: "Ví dụ: IC nguồn RT8205, tụ 470uF",
        defaultValue: t.repair && t.repair.parts ? t.repair.parts : "",
      },
      {
        id: "repair_note",
        label: "Ghi chú kỹ thuật (không bắt buộc)",
        placeholder: "Ví dụ: Máy chạy ổn định sau 2 giờ chạy thử",
      },
    ],
    confirmLabel: "Lưu nội dung sửa chữa",
    onConfirm: ({ actorId, values }) => saveRepair(t.id, actorId, values),
  });
}

/** Lưu chẩn đoán rồi vẽ lại màn hình phiếu (không đổi trạng thái). */
async function saveDiagnosis(ticketId, actorId, values) {
  if (!actorId) {
    showToast("Không xác định được người ghi nhận. Vui lòng tải lại trang.", "warning");
    return;
  }
  const body = { actor_id: actorId, diagnosis_note: values.diagnosis_note };
  if (values.error_category_id) body.error_category_id = parseInt(values.error_category_id, 10);
  if (values.note) body.note = values.note;
  const res = await apiFetch(`/api/v1/warranty-tickets/${ticketId}/diagnosis`, { method: "PATCH", body });
  if (!res.ok) {
    toastError(res, "Không lưu được chẩn đoán.");
    return;
  }
  showToast("Đã lưu kết luận chẩn đoán cho phiếu.", "success");
  await openTicketModal(ticketId);
  await loadTickets();
}

/** Lưu nội dung sửa chữa rồi vẽ lại màn hình phiếu (không đổi trạng thái). */
async function saveRepair(ticketId, actorId, values) {
  if (!actorId) {
    showToast("Không xác định được người ghi nhận. Vui lòng tải lại trang.", "warning");
    return;
  }
  const body = {
    actor_id: actorId,
    repair_content: values.repair_content || "",
    repair_parts: values.repair_parts || "",
    repair_note: values.repair_note || "",
  };
  const res = await apiFetch(`/api/v1/warranty-tickets/${ticketId}/repair`, { method: "PATCH", body });
  if (!res.ok) {
    toastError(res, "Không lưu được nội dung sửa chữa.");
    return;
  }
  showToast("Đã lưu nội dung sửa chữa cho phiếu.", "success");
  await openTicketModal(ticketId);
  await loadTickets();
}

/* --------------------------- MÀN HÌNH: GỢI Ý LOẠI LỖI --------------------------- */
function populateAiTicketSelect() {
  const sel = $("ai-ticket-select");
  if (!sel) return;
  const activeTickets = state.tickets.filter((t) => !["COMPLETED", "REJECTED", "RETURNED"].includes(t.status));
  if (!activeTickets.length) {
    sel.innerHTML = '<option value="">-- Không có phiếu nào đang chờ xử lý lỗi --</option>';
    return;
  }
  const current = sel.value;
  sel.innerHTML = activeTickets.map((t) => {
    const label = `${t.ticket_code} – ${t.serial_number || "không rõ số sê-ri"} (${statusLabel(t.status)})` +
      (t.error_category_id ? " – đã có loại lỗi" : " – chưa xác định loại lỗi");
    return `<option value="${t.id}">${escapeHtml(label)}</option>`;
  }).join("");
  if (current && activeTickets.some((t) => String(t.id) === current)) {
    sel.value = current;
  } else {
    const firstUnlabeled = activeTickets.find((t) => !t.error_category_id);
    sel.value = String((firstUnlabeled || activeTickets[0]).id);
  }
}

async function onAiTicketChange() {
  const sel = $("ai-ticket-select");
  const ticketId = sel && sel.value ? parseInt(sel.value, 10) : null;
  state.currentAiResult = null;
  if (!ticketId) {
    $("ai-result-box").innerHTML = "Chưa có phiếu bảo hành nào để gợi ý loại lỗi.";
    setTableMessage("ai-history-body", 5, "Chưa chọn phiếu bảo hành.");
    return;
  }
  const ticket = state.tickets.find((t) => t.id === ticketId);
  await loadAiHistory(ticketId);
  const res = await apiFetch(`/api/v1/ai/tickets/${ticketId}/results`);
  if (res.ok && Array.isArray(res.data) && res.data.length) {
    state.currentAiResult = normalizeAiResult(res.data[0]);
  }
  renderAiResultBox(ticket || null);
}

/** Chuẩn hóa kết quả gợi ý loại lỗi vừa chạy (POST classify) về cùng cấu trúc nội bộ. */
function normalizeFreshAiResult(data) {
  const out = data && typeof data === "object" ? data : {};
  return {
    ai_result_id: out.ai_result_id,
    ticket_id: out.ticket_id,
    suggested_category_id: out.suggested_category_id === undefined ? null : out.suggested_category_id,
    suggested_category_name: out.suggested_category_name || null,
    raw_reason: out.reason || "",
    confidence: out.confidence === null || out.confidence === undefined ? 0 : Number(out.confidence),
    need_more_information: Array.isArray(out.need_more_information) ? out.need_more_information : [],
    review_status: out.review_status,
    provider: (out.input_data && out.input_data.provider) || out.provider || null,
    created_at: out.created_at,
  };
}

/** Chuẩn hóa bản ghi ai_results (lịch sử) về cùng cấu trúc với response gợi ý loại lỗi. */
function normalizeAiResult(record) {
  const out = record.output_data && typeof record.output_data === "object" ? record.output_data : {};
  return {
    ai_result_id: record.id,
    ticket_id: record.ticket_id,
    suggested_category_id: out.suggested_category_id === undefined ? null : out.suggested_category_id,
    suggested_category_name: out.suggested_category_name || null,
    raw_reason: out.reason || "",
    confidence: record.confidence_score === null || record.confidence_score === undefined ? 0 : Number(record.confidence_score),
    reason: out.reason || "",
    need_more_information: Array.isArray(out.need_more_information) ? out.need_more_information : [],
    review_status: record.review_status,
    provider: (record.input_data && record.input_data.provider) || null,
    created_at: record.created_at,
  };
}

function confidenceColor(value) {
  if (value > 0.7) return "text-emerald-700 font-bold";
  if (value > 0.4) return "text-amber-700 font-bold";
  return "text-rose-700 font-bold";
}

/** Kết quả gợi ý có kèm loại lỗi nằm trong danh mục thật của hệ thống hay không. */
function aiLabelIsUsable(result) {
  if (!result) return false;
  const id = result.suggested_category_id;
  if (id === null || id === undefined) return false;
  return state.categories.some((c) => c.id === id);
}

/** Kết quả có phải do hệ thống chặn nội dung can thiệp trong mô tả lỗi hay không. */
function aiResultIsBlocked(result) {
  return !!result && String(result.raw_reason || "").indexOf("GUARDRAIL") !== -1;
}

/** Cách gọi loại lỗi được gợi ý, đã lọc các kết quả không hợp lệ. */
function aiSuggestionText(result) {
  if (!result) return "Chưa xác định";
  if (result.suggested_category_id === null || result.suggested_category_id === undefined) return "Chưa xác định";
  if (!aiLabelIsUsable(result)) return "Không xác định";
  return displayText(result.suggested_category_name) || categoryName(result.suggested_category_id);
}

/** Lời giải thích dễ hiểu cho nhân viên tiếp nhận. */
function aiReasonText(result) {
  if (!result) return "";
  if (aiResultIsBlocked(result)) {
    return "Mô tả lỗi của phiếu có phần nội dung không phải tình trạng của thiết bị nên hệ thống đã bỏ qua phần đó và chưa gợi ý được loại lỗi. Hãy hỏi khách mô tả cụ thể hơn (máy có lên nguồn không, màn hình hiện gì, có tiếng kêu bất thường không...).";
  }
  return humanizeText(result.raw_reason) || "Không có giải thích.";
}

function renderAiResultBox(ticket) {
  const box = $("ai-result-box");
  if (!box) return;
  const hasLabel = ticket && ticket.error_category_id;
  const currentLine = `<div class="pb-2 mb-2 border-b border-slate-200 text-slate-700">
      Loại lỗi đã ghi trên phiếu: <strong class="${hasLabel ? "text-emerald-700 font-bold" : "text-amber-700 font-bold"}">${escapeHtml(ticket ? categoryName(ticket.error_category_id) : "–")}</strong>
      <span class="text-slate-500 text-xs font-normal">(chỉ được ghi sau khi kỹ thuật viên/quản lý xác nhận)</span>
    </div>`;

  const r = state.currentAiResult;
  if (!r) {
    box.innerHTML = currentLine + '<div class="text-slate-500">Chưa có kết quả gợi ý cho phiếu này. Bấm "Gợi ý loại lỗi" để hệ thống đọc mô tả sự cố của khách.</div>';
    return;
  }

  const needMore = r.need_more_information || [];
  const needMoreHtml = needMore.length
    ? `<div class="mt-2 p-2.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-900">
         <div class="font-semibold mb-1">Nên hỏi thêm khách hàng để xác định chính xác hơn:</div>
         <ul class="list-disc ml-4 space-y-0.5">${needMore.map((q) => `<li>${escapeHtml(humanizeText(q))}</li>`).join("")}</ul>
       </div>`
    : "";

  const statusClass = r.review_status === "APPROVED"
    ? "bg-emerald-100 text-emerald-800 border border-emerald-300"
    : (r.review_status === "REJECTED"
      ? "bg-rose-100 text-rose-800 border border-rose-300"
      : "bg-slate-100 text-slate-700 border border-slate-300");

  const footerNote = r.review_status === "PENDING"
    ? "Kết quả này chỉ là gợi ý. Chọn người xác nhận rồi bấm Xác nhận / Không dùng gợi ý."
    : "Kết quả đã được xác nhận, không thể xác nhận lại.";

  const canUseLabel = aiLabelIsUsable(r);
  const warning = (r.suggested_category_id !== null && r.suggested_category_id !== undefined && !canUseLabel)
    ? '<div class="text-xs text-amber-800 font-medium mt-1">Kết quả gợi ý này không khớp danh mục loại lỗi nên hệ thống không ghi vào phiếu. Hãy bấm <strong>Gợi ý loại lỗi</strong> lại sau khi bổ sung mô tả lỗi.</div>'
    : "";

  const isSim = r.provider === "mock" || r.provider === null;
  const simBadge = isSim
    ? '<span class="px-2 py-0.5 rounded text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-200">Chế độ mô phỏng</span>'
    : '<span class="px-2 py-0.5 rounded text-xs font-semibold bg-indigo-100 text-indigo-800 border border-indigo-200">Mô hình AI</span>';

  const showConfidence = canUseLabel && r.confidence !== null && r.confidence !== undefined;
  const confidenceLine = showConfidence
    ? `<div class="text-slate-600">Mức độ chắc chắn: <strong class="font-mono ${confidenceColor(r.confidence)}">${confidencePercent(r.confidence)}</strong>
         &bull; Thời điểm gợi ý: <span class="font-mono text-slate-700">${fmtDateTime(r.created_at)}</span></div>`
    : `<div class="text-amber-800 text-xs font-medium">Chưa đủ thông tin để xác định nhóm lỗi hoặc độ chắc chắn.
         &bull; Thời điểm: <span class="font-mono text-slate-700">${fmtDateTime(r.created_at)}</span></div>`;

  box.innerHTML = currentLine +
    `<div class="flex flex-wrap items-center gap-2">
       <span class="text-slate-600">Loại lỗi được gợi ý:</span>
       <strong class="${canUseLabel ? "text-purple-700 font-bold" : "text-amber-800 font-bold"}">${escapeHtml(aiSuggestionText(r))}</strong>
       ${simBadge}
       <span class="px-2 py-0.5 rounded-full text-xs font-bold ${statusClass}">${escapeHtml(reviewLabel(r.review_status))}</span>
     </div>
     ${confidenceLine}
     <div class="text-slate-800"><span class="text-slate-600">Giải thích:</span> ${escapeHtml(aiReasonText(r))}</div>
     ${warning}
     ${needMoreHtml}
     <div class="text-xs text-slate-500 mt-1">${footerNote}</div>`;
}

async function loadAiHistory(ticketId) {
  setTableLoading("ai-history-body", 5);
  const res = await apiFetch(`/api/v1/ai/tickets/${ticketId}/results`);
  if (!res.ok) {
    setTableMessage("ai-history-body", 5, "Không tải được lịch sử gợi ý loại lỗi của phiếu.");
    return;
  }
  const items = Array.isArray(res.data) ? res.data : [];
  if (!items.length) {
    setTableMessage("ai-history-body", 5, "Phiếu này chưa có kết quả gợi ý nào.");
    return;
  }
  $("ai-history-body").innerHTML = items.map((rec) => {
    const n = normalizeAiResult(rec);
    const labelCls = aiLabelIsUsable(n) ? "text-purple-700 font-semibold" : "text-amber-700 font-semibold";
    return `
    <tr class="table-row">
      <td class="table-td text-slate-600 font-mono">${fmtDateTime(n.created_at)}</td>
      <td class="table-td ${labelCls}">${escapeHtml(aiSuggestionText(n))}</td>
      <td class="table-td font-mono font-medium">${aiLabelIsUsable(n) ? confidencePercent(n.confidence) : "–"}</td>
      <td class="table-td">${escapeHtml(reviewLabel(n.review_status))}</td>
      <td class="table-td text-slate-600">${rec.reviewed_by ? escapeHtml(userName(rec.reviewed_by)) : "–"}</td>
    </tr>`;
  }).join("");
}

/** Gọi API gợi ý loại lỗi cho phiếu đang chọn. */
async function runAiClassify() {
  if (!hasPerm("ai.classify")) {
    showToast("Vai trò hiện tại không có quyền gợi ý loại lỗi.", "warning");
    return;
  }
  const sel = $("ai-ticket-select");
  const ticketId = sel && sel.value ? parseInt(sel.value, 10) : null;
  if (!ticketId) {
    showToast("Chưa có phiếu bảo hành nào để gợi ý loại lỗi.", "warning");
    return;
  }
  const btn = $("btn-ai-classify");
  const originalHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<i data-lucide="loader" class="w-4 h-4 animate-spin"></i> Đang gợi ý loại lỗi...';
  refreshIcons();

  const res = await apiFetch(`/api/v1/ai/tickets/${ticketId}/classify-error`, { method: "POST" });
  if (res.ok) {
    state.currentAiResult = normalizeFreshAiResult(res.data);
    const label = aiSuggestionText(state.currentAiResult);
    const confMsg = state.currentAiResult.suggested_category_id ? ` (mức độ chắc chắn ${confidencePercent(state.currentAiResult.confidence)})` : "";
    showToast(`Đã gợi ý xong. Loại lỗi được gợi ý: <strong>${escapeHtml(label)}</strong>${confMsg} – đang chờ kỹ thuật viên xác nhận.`, "success", 8000);
    renderAiResultBox(state.tickets.find((t) => t.id === ticketId) || null);
    await loadAiHistory(ticketId);
    await loadTickets();
  } else {
    toastError(res, "Không gợi ý được loại lỗi cho phiếu này.");
  }

  btn.disabled = false;
  btn.innerHTML = originalHtml;
  refreshIcons();
}

/** Nhân viên xác nhận hoặc không dùng kết quả gợi ý (human-in-the-loop). */
async function submitAiReview(decision) {
  if (!hasPerm("ai.review")) {
    showToast("Chỉ kỹ thuật viên phụ trách hoặc quản lý được xác nhận gợi ý loại lỗi.", "warning");
    return;
  }
  if (!state.currentAiResult) {
    showToast("Chưa có kết quả gợi ý nào để xác nhận.", "warning");
    return;
  }
  if (state.currentAiResult.review_status !== "PENDING") {
    showToast("Kết quả này đã được xác nhận trước đó.", "warning");
    return;
  }
  const reviewedBy = parseInt($("ai-reviewer-select").value, 10);
  if (!reviewedBy) {
    showToast("Vui lòng chọn người xác nhận.", "warning");
    return;
  }
  const ticketId = state.currentAiResult.ticket_id;
  const res = await apiFetch(`/api/v1/ai/results/${state.currentAiResult.ai_result_id}/review`, {
    method: "PATCH",
    body: { reviewed_by: reviewedBy, decision },
  });
  if (!res.ok) {
    toastError(res, decision === "APPROVED" ? "Không xác nhận được loại lỗi." : "Không cập nhật được kết quả gợi ý.");
    return;
  }
  showToast(
    decision === "APPROVED"
      ? `Đã xác nhận loại lỗi và ghi vào phiếu${ticketCodeHtml(ticketId)}.`
      : `Đã bỏ qua kết quả gợi ý cho phiếu${ticketCodeHtml(ticketId)}. Phiếu vẫn giữ nguyên loại lỗi cũ.`,
    decision === "APPROVED" ? "success" : "warning",
    8000
  );

  await loadTickets();
  if (ticketId) {
    const sel = $("ai-ticket-select");
    if (sel) sel.value = String(ticketId);
    state.currentAiResult = null;
    const results = await apiFetch(`/api/v1/ai/tickets/${ticketId}/results`);
    if (results.ok && Array.isArray(results.data) && results.data.length) {
      state.currentAiResult = normalizeAiResult(results.data[0]);
    }
    await loadAiHistory(ticketId);
    renderAiResultBox(state.tickets.find((t) => t.id === ticketId) || null);
  }
  await loadDashboard();
  // Nếu modal chi tiết phiếu đang mở đúng phiếu này thì nạp lại số liệu mới.
  if (state.selectedTicket && state.selectedTicket.id === ticketId && $("ticket-modal").style.display === "flex") {
    await openTicketModal(ticketId);
  }
}

/** Khối gợi ý loại lỗi hiển thị trong chi tiết phiếu (có thể gợi ý/xác nhận ngay). */
async function refreshModalAiPanel(t) {
  const box = $("modal-ai-body");
  const summary = $("modal-ai-summary");
  if (!box) return;
  box.innerHTML = '<span class="text-slate-400">Đang tải kết quả gợi ý...</span>';
  const res = await apiFetch(`/api/v1/ai/tickets/${t.id}/results`);
  const items = res.ok && Array.isArray(res.data) ? res.data : [];
  if (items.length) state.currentAiResult = normalizeAiResult(items[0]);

  const latest = items.length ? normalizeAiResult(items[0]) : null;
  if (summary) {
    if (!latest) {
      summary.className = "px-2.5 py-1 text-xs rounded-full border border-slate-300 text-slate-600 bg-slate-50";
      summary.textContent = "Chưa có gợi ý loại lỗi";
    } else if (latest.review_status === "APPROVED") {
      summary.className = "px-2.5 py-1 text-xs rounded-full border border-emerald-300 bg-emerald-50 text-emerald-800 font-semibold";
      summary.textContent = "Đã xác nhận loại lỗi";
    } else if (latest.review_status === "REJECTED") {
      summary.className = "px-2.5 py-1 text-xs rounded-full border border-rose-300 bg-rose-50 text-rose-800 font-semibold";
      summary.textContent = "Không dùng gợi ý của hệ thống";
    } else {
      summary.className = "px-2.5 py-1 text-xs rounded-full border border-amber-300 bg-amber-50 text-amber-800 font-semibold";
      summary.textContent = "Gợi ý loại lỗi: chờ xác nhận";
    }
  }

  let html = `<div class="mb-2 text-slate-700">Loại lỗi đã ghi trên phiếu: <strong class="${t.error_category_id ? "text-emerald-700 font-bold" : "text-amber-700 font-bold"}">${escapeHtml(categoryName(t.error_category_id))}</strong></div>`;
  if (!latest) {
    html += `<div class="text-slate-500 mb-2">Chưa có kết quả gợi ý cho phiếu này.</div>`;
  } else {
    const statusCls = latest.review_status === "APPROVED" ? "text-emerald-700 font-semibold" : (latest.review_status === "REJECTED" ? "text-rose-700 font-semibold" : "text-amber-700 font-semibold");
    const labelCls = aiLabelIsUsable(latest) ? "text-purple-700 font-bold" : "text-amber-700 font-bold";
    html += `<div class="mb-1 text-slate-700">Loại lỗi được gợi ý: <strong class="${labelCls}">${escapeHtml(aiSuggestionText(latest))}</strong>
        &bull; Mức độ chắc chắn: <span class="font-mono ${confidenceColor(latest.confidence)}">${confidencePercent(latest.confidence)}</span></div>
      <div class="text-slate-600">Trạng thái xác nhận: <strong class="${statusCls}">${escapeHtml(reviewLabel(latest.review_status))}</strong>
        &bull; Thời điểm: <span class="font-mono text-slate-700">${fmtDateTime(latest.created_at)}</span></div>
      <div class="text-slate-600 mt-1">Số lần đã gợi ý: <span class="font-mono font-medium text-slate-800">${items.length}</span></div>`;
  }
  const users = assignableStaff();
  const reviewerOptions = users
    .map((u) => `<option value="${u.id}">${escapeHtml(displayText(u.full_name))} (${escapeHtml(roleLabel(u.role))})${staffCanReview(u) ? "" : " – không có quyền xác nhận"}</option>`)
    .join("");
  const defaultReviewer = defaultActor(users, "RECEPTIONIST");
  const canConfirm = latest && latest.review_status === "PENDING";
  // Quyền xác nhận gợi ý AI (ai.review): chỉ hiện khối duyệt cho vai trò được phép.
  const canReviewAi = hasPerm("ai.review");
  const canClassifyAi = hasPerm("ai.classify");

  if (canReviewAi) {
    html += `
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-3 items-end">
        <div class="sm:col-span-2">
          <label class="form-label" for="modal-ai-reviewer">Người xác nhận</label>
          <select id="modal-ai-reviewer" class="w-full glass-input px-3 py-2 rounded-xl text-sm">${reviewerOptions}</select>
        </div>
        <div class="flex gap-2">
          <button class="btn btn-success flex-1 justify-center${canConfirm ? "" : " opacity-50"}" ${canConfirm ? "" : "disabled"} onclick="submitAiReviewModal('APPROVED')"><i data-lucide="check-circle" class="w-3.5 h-3.5"></i> Xác nhận</button>
          <button class="btn btn-danger flex-1 justify-center${canConfirm ? "" : " opacity-50"}" ${canConfirm ? "" : "disabled"} onclick="submitAiReviewModal('REJECTED')"><i data-lucide="x-circle" class="w-3.5 h-3.5"></i> Không dùng</button>
        </div>
      </div>`;
  } else {
    html += `<div class="text-xs text-slate-500 mt-3">Vai trò hiện tại chỉ xem được gợi ý loại lỗi; việc xác nhận do nhân viên tiếp nhận hoặc quản lý thực hiện.</div>`;
  }
  html += `
    <div class="flex flex-wrap gap-2 mt-2">
      ${canClassifyAi ? `<button class="btn btn-primary btn-sm" onclick="classifyCurrentTicket()"><i data-lucide="wand-2" class="w-3.5 h-3.5"></i> Gợi ý loại lỗi cho phiếu này</button>` : ""}
      <button class="btn btn-secondary btn-sm" onclick="goToAiTab()"><i data-lucide="arrow-up-right" class="w-3.5 h-3.5"></i> Xem đầy đủ ở màn hình xác định lỗi</button>
    </div>
    ${canReviewAi && !canConfirm ? '<div class="text-xs text-amber-800 font-medium mt-2">Hai nút <strong>Xác nhận</strong> / <strong>Không dùng</strong> chỉ bật khi phiếu có kết quả gợi ý đang chờ duyệt — hãy bấm <strong>Gợi ý loại lỗi cho phiếu này</strong> trước.</div>' : ""}`;
  box.innerHTML = html;
  if ($("modal-ai-reviewer") && defaultReviewer) $("modal-ai-reviewer").value = String(defaultReviewer.id);
  refreshIcons();
}

/** Mã phiếu để hiển thị trong thông báo (không lộ mã nội bộ khi chưa có mã phiếu). */
function ticketCodeFromList(ticketId) {
  const t = state.tickets.find((x) => x.id === ticketId);
  return t && t.ticket_code ? t.ticket_code : "";
}

/** Chuỗi hiển thị mã phiếu kèm nhấn mạnh (rỗng nếu chưa có). */
function ticketCodeHtml(ticketId) {
  const code = ticketCodeFromList(ticketId);
  return code ? ` <strong class="font-mono">${escapeHtml(code)}</strong>` : "";
}

/** Xác nhận / không dùng gợi ý loại lỗi ngay trong chi tiết phiếu. */
async function submitAiReviewModal(decision) {
  if (!hasPerm("ai.review")) {
    showToast("Chỉ kỹ thuật viên phụ trách hoặc quản lý được xác nhận gợi ý loại lỗi.", "warning");
    return;
  }
  if (!state.currentAiResult) {
    showToast("Chưa có kết quả gợi ý nào để xác nhận.", "warning");
    return;
  }
  const select = $("modal-ai-reviewer");
  const reviewedBy = select ? parseInt(select.value, 10) : NaN;
  if (!reviewedBy) {
    showToast("Vui lòng chọn người xác nhận.", "warning");
    return;
  }
  const ticketId = state.currentAiResult.ticket_id;
  const res = await apiFetch(`/api/v1/ai/results/${state.currentAiResult.ai_result_id}/review`, {
    method: "PATCH",
    body: { reviewed_by: reviewedBy, decision },
  });
  if (!res.ok) {
    toastError(res, decision === "APPROVED" ? "Không xác nhận được loại lỗi." : "Không cập nhật được kết quả gợi ý.");
    return;
  }
  showToast(
    decision === "APPROVED"
      ? `Đã xác nhận loại lỗi và ghi vào phiếu${ticketCodeHtml(ticketId)}.`
      : `Đã bỏ qua kết quả gợi ý cho phiếu${ticketCodeHtml(ticketId)}.`,
    decision === "APPROVED" ? "success" : "warning",
    8000
  );
  await loadTickets();
  if ($("ticket-modal").style.display === "flex") await openTicketModal(ticketId);
  await loadDashboard();
}

/** Gợi ý loại lỗi ngay cho phiếu đang mở (không rời khỏi phiếu). */
async function classifyCurrentTicket() {
  const t = state.selectedTicket;
  if (!t) return;
  if (["COMPLETED", "REJECTED", "RETURNED"].includes(t.status)) {
    showToast("Phiếu đã ở trạng thái kết thúc, không thể tạo gợi ý loại lỗi.", "warning");
    return;
  }
  const res = await apiFetch(`/api/v1/ai/tickets/${t.id}/classify-error`, { method: "POST" });
  if (!res.ok) {
    toastError(res, "Không gợi ý được loại lỗi cho phiếu này.");
    return;
  }
  const fresh = normalizeFreshAiResult(res.data);
  const label = aiSuggestionText(fresh);
  const confMsg = fresh.suggested_category_id ? ` (mức độ chắc chắn ${confidencePercent(res.data.confidence)})` : "";
  showToast(`Đã gợi ý xong. Loại lỗi được gợi ý: <strong>${escapeHtml(label)}</strong>${confMsg}.`, "success", 8000);
  await openTicketModal(t.id);
  await loadTickets();
}

/* =====================================================================
   [Đợt 7] ĐĂNG NHẬP & PHÂN QUYỀN TRÊN GIAO DIỆN
   ---------------------------------------------------------------------
   - Token được lưu ở localStorage và gửi kèm mọi API (xem apiFetch).
   - Vai trò + danh sách quyền LUÔN lấy từ backend (`/api/v1/auth/me`) —
     giao diện không tự quyết định quyền.
   - Ẩn/hiện menu chỉ là trải nghiệm: backend vẫn là nơi chặn thật (401/403).
   ===================================================================== */
const TOKEN_STORAGE_KEY = "baohanhai.access_token";

/* Quyền tối thiểu để mở từng màn hình (khớp `data-perm` trên menu). */
const TAB_PERMISSIONS = {
  dashboard: "dashboard.view",
  tickets: "ticket.view",
  lookup: "lookup.view",
  ai: "ai.view",
  customers: "customer.view",
  products: "product.view",
  devices: "device.view",
  accounts: "user.view",
};

/** Đổi trạng thái phiên -> CSS quyết định hiển thị màn hình đăng nhập hay ứng dụng. */
function setAuthState(mode) {
  document.documentElement.setAttribute("data-auth", mode);
}

function storeToken(token) {
  try {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } catch (e) {
    /* Trình duyệt chặn localStorage: vẫn làm việc được trong phiên hiện tại. */
  }
}

function readStoredToken() {
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY) || "";
  } catch (e) {
    return "";
  }
}

function clearStoredToken() {
  try {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch (e) {
    /* bỏ qua */
  }
}

/** True nếu vai trò đang đăng nhập có quyền này (danh sách quyền do backend trả về). */
function hasPerm(permission) {
  const user = state.session.user;
  if (!user || !Array.isArray(user.permissions)) return false;
  return user.permissions.indexOf(permission) !== -1;
}

const hasPermission = hasPerm;

function isManager() {
  return !!state.session.user && state.session.user.role === "MANAGER";
}

/** Ẩn/hiện mọi phần tử có khai báo `data-perm` theo quyền của vai trò đang đăng nhập.
 * Lưu ý: KHÔNG áp dụng cho các nút menu chính trên sidebar (.nav-tab-btn)
 * vì menu điều hướng sidebar do renderNavigation quyết định theo cấu hình vai trò. */
function applyPermissions() {
  document.querySelectorAll("[data-perm]:not(.nav-tab-btn)").forEach((el) => {
    el.style.display = hasPerm(el.getAttribute("data-perm")) ? "" : "none";
  });
}

/* ------------------------------------------------------------------
   MENU THEO VAI TRÒ (backend quyết định)
   Backend trả `menus` kèm mỗi phiên đăng nhập:
     - group "work"      : việc hằng ngày -> hiện trên menu chính
     - group "reference" : sổ/danh mục tra cứu nội bộ -> gom vào "Tra cứu nội bộ"
     - group "admin"     : quản trị tài khoản nhân viên (chỉ Quản lý)
   Giao diện chỉ VẼ LẠI danh sách đó; quyền vẫn do backend kiểm tra (403).
   ------------------------------------------------------------------ */
function toggleNavMore(force) {
  const panel = $("nav-more-panel");
  const toggleBtn = $("nav-more-toggle");
  if (!panel) return;
  const isCurrentlyHidden = panel.classList.contains("hidden");
  const willOpen = force !== undefined ? force : isCurrentlyHidden;
  panel.classList.toggle("hidden", !willOpen);
  if (toggleBtn) {
    toggleBtn.setAttribute("aria-expanded", willOpen ? "true" : "false");
  }
}

function closeNavMore() {
  toggleNavMore(false);
}

/** Lấy danh sách tab hợp lệ theo vai trò của người dùng hiện tại */
function getEffectiveAllowedTabs(user) {
  if (!user) return ["dashboard"];
  const role = user.role || "";
  if (role === "TECHNICIAN") {
    return ["dashboard", "tickets", "lookup", "ai"];
  }
  if (Array.isArray(user.menus) && user.menus.length > 0) {
    return user.menus.map((m) => m.tab);
  }
  if (role === "RECEPTIONIST") {
    return ["dashboard", "tickets", "lookup", "ai", "customers", "products", "devices"];
  }
  return ["dashboard", "tickets", "lookup", "ai", "customers", "products", "devices", "accounts"];
}

/** Vẽ menu theo vai trò; gom nhóm "reference" vào dropdown nếu có; ẩn nhóm rỗng & tiêu đề Sổ & Quản trị. */
function renderNavigation(menus) {
  let list = Array.isArray(menus) ? menus : [];
  const user = state.session.user;
  const role = user ? user.role : "";

  // BẢO VỆ TẠI NGUỒN GIAO DIỆN THEO VAI TRÒ:
  // Nếu là Kỹ thuật viên (TECHNICIAN), menu hiển thị CHỈ ĐƯỢC PHÉP gồm đúng 4 mục:
  // 1. Tổng quan, 2. Phiếu bảo hành, 3. Tra cứu bảo hành, 4. Hỗ trợ xác định lỗi.
  // Tuyệt đối không giữ nhóm "reference" ("Tra cứu nội bộ") hay các mục danh mục sổ sách.
  if (role === "TECHNICIAN") {
    const TECH_ALLOWED_TABS = ["dashboard", "tickets", "lookup", "ai"];
    list = list.filter((m) => TECH_ALLOWED_TABS.includes(m.tab) && m.group !== "reference");
  }

  const moreWrap = $("nav-more");
  const morePanel = $("nav-more-panel");
  const adminSection = $("nav-section-admin");
  const adminNav = $("nav-section-admin-items") || (adminSection ? adminSection.querySelector("nav") : null);

  // Phục hồi các nút đã từng được chuyển vào dropdown panel về lại container gốc
  if (morePanel && adminNav) {
    const movedBtns = Array.from(morePanel.querySelectorAll(".nav-tab-btn[data-tab]"));
    movedBtns.forEach((btn) => {
      if (moreWrap) {
        adminNav.insertBefore(btn, moreWrap);
      } else {
        adminNav.appendChild(btn);
      }
    });
    morePanel.innerHTML = "";
  }

  const allowedTabs = list.map((menu) => menu.tab);

  // 1. Mục menu không thuộc vai trò này -> ẩn hoàn toàn (cả class hidden và inline style)
  document.querySelectorAll(".nav-tab-btn[data-tab]").forEach((btn) => {
    const tab = btn.getAttribute("data-tab");
    const isAllowed = allowedTabs.includes(tab);
    btn.classList.toggle("hidden", !isAllowed);
    btn.style.display = isAllowed ? "" : "none";
    if (!isAllowed) {
      btn.classList.remove("active");
    }
  });

  // 2. Gom nhóm reference vào dropdown "Tra cứu nội bộ" nếu có mục reference
  const reference = list.filter((menu) => menu.group === "reference");
  if (moreWrap && morePanel) {
    const hasReference = reference.length > 0;
    moreWrap.classList.toggle("hidden", !hasReference);
    moreWrap.style.display = hasReference ? "" : "none";
    if (!hasReference) {
      closeNavMore();
    } else {
      reference.forEach((menu) => {
        const btn = document.querySelector(`nav .nav-tab-btn[data-tab="${menu.tab}"]`);
        if (!btn) return;
        btn.classList.remove("hidden");
        btn.style.display = "";
        btn.setAttribute("title", menu.hint || menu.label);
        morePanel.appendChild(btn);
      });
    }
  }

  // 3. Ẩn tiêu đề "Sổ & Quản trị" và cả khối section nếu không còn mục nào hiển thị bên dưới
  if (adminSection) {
    const visibleAdminItems = adminSection.querySelectorAll(
      ".nav-tab-btn[data-tab]:not(.hidden), #nav-more:not(.hidden)"
    );
    const hasVisible = visibleAdminItems.length > 0 && Array.from(visibleAdminItems).some(
      (el) => el.style.display !== "none"
    );
    adminSection.classList.toggle("hidden", !hasVisible);
    adminSection.style.display = hasVisible ? "" : "none";
  }

  // 4. Màn hình nhỏ (nếu có): nhãn nhóm
  const mobileNav = document.querySelector(".nav-tab-mobile");
  if (mobileNav) {
    const oldLabel = mobileNav.querySelector(".nav-group-label");
    if (oldLabel) oldLabel.remove();
    const first = reference[0];
    if (first) {
      const mobileBtn = mobileNav.querySelector(`.nav-tab-btn[data-tab="${first.tab}"]`);
      if (mobileBtn) {
        const label = document.createElement("span");
        label.className = "nav-group-label";
        label.textContent = first.group_label || "Tra cứu nội bộ";
        mobileNav.insertBefore(label, mobileBtn);
      }
    }
  }
  refreshIcons();
}

/** Tab mặc định nên mở: tab đầu tiên trong menu mà vai trò hiện tại được phép xem. */
function firstAllowedTab() {
  const user = state.session && state.session.user;
  const allowed = getEffectiveAllowedTabs(user);
  return allowed[0] || "dashboard";
}

/** Cập nhật thẻ phiên làm việc trên thanh điều hướng + áp quyền cho toàn bộ giao diện. */
function applySessionUi() {
  const user = state.session.user;
  const chip = $("session-chip");
  if (user) {
    if ($("session-name")) $("session-name").textContent = displayText(user.full_name);
    if ($("session-role")) $("session-role").textContent = `${roleLabel(user.role)} \u2022 @${user.username}`;
    if (chip) chip.style.display = "flex";
    // Menu do BACKEND trả về theo vai trò (nhóm "work" / "reference" / "admin")
    renderNavigation(user.menus);

    // NẾU TAB HIỆN TẠI KHÔNG CÒN TRONG MENU CỦA VAI TRÒ NÀY -> CHUYỂN VỀ TỔNG QUAN
    const allowed = getEffectiveAllowedTabs(user);
    if (!allowed.includes(state.currentTab)) {
      switchTab("dashboard");
    }
  } else {
    if (chip) chip.style.display = "none";
    renderNavigation([]);
    switchTab("dashboard");
  }
  applyPermissions();
}

/** Nhân viên được phép ghi nhận là "người thực hiện": quản lý chọn bất kỳ ai, nhân viên chỉ chính mình. */
function assignableStaff() {
  const me = state.session.user;
  if (!me) return state.users;
  if (isManager()) return state.users.length ? state.users : [me];
  const mine = state.users.filter((u) => u.id === me.id);
  return mine.length ? mine : [me];
}

/** Người được chọn sẵn: chính mình (nhân viên) hoặc nhân viên tiếp nhận (quản lý). */
function defaultActor(staff, preferredRole = "RECEPTIONIST") {
  const me = state.session.user;
  if (me && !isManager()) {
    const mine = staff.find((u) => u.id === me.id);
    if (mine) return mine;
  }
  return staff.find((u) => u.role === preferredRole) || staff[0] || null;
}

/** Cờ "được xác nhận kết quả gợi ý AI" — ưu tiên cờ thật từ backend, nếu thiếu thì suy ra từ vai trò. */
function staffCanReview(user) {
  if (!user) return false;
  if (typeof user.can_review === "boolean") return user.can_review;
  return user.role === "MANAGER" || user.role === "TECHNICIAN";
}

function setLoginMessage(text, type = "error") {
  const box = $("login-message");
  if (!box) return;
  box.textContent = text || "";
  box.className = text
    ? "text-sm rounded-xl px-3 py-2 border font-medium " + (type === "success"
        ? "border-emerald-300 bg-emerald-50 text-emerald-800"
        : "border-rose-300 bg-rose-50 text-rose-800")
    : "hidden";
}

/** Nạp dữ liệu nghiệp vụ ban đầu cho vai trò vừa đăng nhập. */
async function loadWorkspaceData() {
  await loadReferenceData();
  await loadCustomers();
  await loadProducts();
  await loadDevices();
  await loadTickets();
}

/** Sau khi đăng nhập (hoặc khôi phục phiên): nạp dữ liệu rồi mở giao diện ứng dụng. */
async function enterWorkspace() {
  applySessionUi();
  setAuthState("authed");
  await loadWorkspaceData();
  const user = state.session.user;
  const allowed = getEffectiveAllowedTabs(user);
  let tab = state.currentTab;
  if (!allowed.includes(tab) || !hasPerm(TAB_PERMISSIONS[tab])) {
    tab = firstAllowedTab();
  }
  switchTab(tab);
  refreshIcons();
}

/** Gửi thông tin đăng nhập lên backend và mở giao diện khi thành công. */
async function submitLogin(event) {
  if (event) event.preventDefault();
  const username = ($("login-username").value || "").trim();
  const password = ($("login-password").value || "").trim();
  const btn = $("login-submit");
  if (!username || !password) {
    setLoginMessage("Vui lòng nhập tên đăng nhập và mật khẩu.");
    return;
  }
  setLoginMessage("");
  btn.disabled = true;
  btn.innerHTML = '<i data-lucide="loader-circle" class="w-4 h-4 animate-spin"></i> Đang kiểm tra...';
  refreshIcons();

  const res = await apiFetch("/api/v1/auth/login", {
    method: "POST",
    skipAuth: true,
    body: { username, password },
  });

  btn.disabled = false;
  btn.innerHTML = '<i data-lucide="log-in" class="w-4 h-4"></i> Đăng nhập';
  refreshIcons();

  if (!res.ok || !res.data || !res.data.access_token) {
    setLoginMessage(
      res.status === 401 ? "Tên đăng nhập hoặc mật khẩu không đúng." : errorMessage(res.status, res.data)
    );
    $("login-password").value = "";
    $("login-password").focus();
    return;
  }

  clearSessionData();
  state.session.token = res.data.access_token;
  state.session.user = res.data.user || null;
  storeToken(state.session.token);
  showToast(escapeHtml(res.data.message || "Đăng nhập thành công."), "success", 5000);
  await enterWorkspace();
}

/** Khôi phục phiên đăng nhập cũ (F5): token còn hiệu lực thì vào thẳng ứng dụng. */
async function restoreSession() {
  const token = readStoredToken();
  if (!token) return false;
  state.session.token = token;
  const res = await apiFetch("/api/v1/auth/me");
  if (!res.ok || !res.data || !res.data.role) {
    state.session.token = "";
    state.session.user = null;
    clearStoredToken();
    return false;
  }
  state.session.user = res.data;
  return true;
}

function clearSessionData() {
  window.BaoHanhSupport?.reset();
  state.sessionEpoch++;
  state.selectedTicket = null;
  state.currentAiResult = null;
  state.workboard = null;
  state.tickets = [];
  state.customers = [];
  state.products = [];
  state.devices = [];
  state.users = [];
  state.dashActiveRows = [];
  state.dashAttention = [];
  state.dashView = null;
  state.dashFilterStatus = "ALL";
  state.dashSearchQuery = "";
  state.currentTab = "dashboard";
  setTableMessage("dash-active-body", 7, "Đang tải dữ liệu...");
  setTableMessage("tickets-table-body", 8, "Đang tải dữ liệu...");
}

/** Token hết hạn/bị thu hồi giữa phiên làm việc -> quay về màn hình đăng nhập. */
function handleSessionExpired() {
  if (!state.session.token) return;
  state.session.token = "";
  state.session.user = null;
  clearStoredToken();
  clearSessionData();
  applySessionUi();
  setAuthState("guest");
  setLoginMessage("Phiên làm việc đã hết hạn. Vui lòng đăng nhập lại.");
  refreshIcons();
}

/** Đăng xuất: thu hồi token ở backend rồi xoá phiên ở trình duyệt. */
async function logout() {
  if (!state.session.token) return;
  const res = await apiFetch("/api/v1/auth/logout", { method: "POST" });
  state.session.token = "";
  state.session.user = null;
  clearStoredToken();
  clearSessionData();
  applySessionUi();
  setAuthState("guest");
  $("login-password").value = "";
  setLoginMessage(
    res.ok
      ? "Đã đăng xuất. Đăng nhập lại để tiếp tục làm việc."
      : "Đã thoát khỏi phiên làm việc trên trình duyệt này.",
    res.ok ? "success" : "error"
  );
  setTimeout(() => $("login-username").focus(), 50);
  refreshIcons();
}

/* --------------------------- MÀN HÌNH: TÀI KHOẢN NHÂN VIÊN --------------------------- */
/**
 * Danh sách tài khoản nhân viên (chỉ Quản lý — quyền `user.view`).
 * Không hiển thị mật khẩu/hash; dữ liệu lấy từ `GET /api/v1/users`.
 */
async function loadAccounts() {
  setTableLoading("accounts-table-body", 8);
  const res = await apiFetch("/api/v1/users");
  if (!res.ok) {
    if (res.status === 403) {
      setTableMessage("accounts-table-body", 8, "Chỉ Quản lý xem được danh sách tài khoản nhân viên.");
    } else {
      setTableMessage("accounts-table-body", 8, `Lỗi tải danh sách tài khoản: ${escapeHtml(errorMessage(res.status, res.data))}`);
    }
    const badge = $("account-count-badge");
    if (badge) badge.textContent = "";
    return;
  }
  const payload = res.data || {};
  const rows = Array.isArray(payload) ? payload : Array.isArray(payload.items) ? payload.items : [];
  state.accounts = rows;
  filterAccounts();
}

/** Lọc và hiển thị danh sách tài khoản theo từ khóa, vai trò và trạng thái. */
function filterAccounts() {
  const allRows = state.accounts || [];
  const searchInput = $("account-search-input");
  const roleSelect = $("account-role-filter");
  const statusSelect = $("account-status-filter");
  const badge = $("account-count-badge");

  const query = (searchInput ? searchInput.value : "").trim().toLowerCase();
  const roleFilter = roleSelect ? roleSelect.value : "ALL";
  const statusFilter = statusSelect ? statusSelect.value : "ALL";

  if (!allRows.length) {
    setTableMessage("accounts-table-body", 8, "Hệ thống chưa có tài khoản nhân viên nào.");
    if (badge) badge.textContent = "0 tài khoản";
    return;
  }

  const filtered = allRows.filter((u) => {
    if (roleFilter !== "ALL" && u.role !== roleFilter) return false;
    const active = u.active !== false;
    if (statusFilter === "ACTIVE" && !active) return false;
    if (statusFilter === "LOCKED" && active) return false;
    if (query) {
      const uname = (u.username || "").toLowerCase();
      const fname = (u.full_name || "").toLowerCase();
      const email = (u.email || "").toLowerCase();
      const phone = (u.phone || "").toLowerCase();
      if (!uname.includes(query) && !fname.includes(query) && !email.includes(query) && !phone.includes(query)) {
        return false;
      }
    }
    return true;
  });

  if (badge) {
    badge.textContent = `Hiển thị ${filtered.length}/${allRows.length} tài khoản`;
  }

  if (!filtered.length) {
    setTableMessage("accounts-table-body", 8, "Không tìm thấy tài khoản nào phù hợp với bộ lọc.");
    return;
  }

  const canManage = hasPerm("user.manage");
  const currentUserId = state.session.user ? state.session.user.id : null;
  const tbody = $("accounts-table-body");
  if (!tbody) return;

  tbody.innerHTML = filtered
    .map((u) => {
      const active = u.active !== false;
      let actionBtn = "";
      if (canManage) {
        if (Number(u.id) === Number(currentUserId)) {
          actionBtn = '<span class="text-xs text-slate-400 italic">Đang đăng nhập</span>';
        } else if (active) {
          actionBtn = `<button type="button" class="btn btn-secondary btn-xs text-rose-600 border-rose-200 hover:bg-rose-50" onclick="toggleUserActive(${u.id}, false)"><i data-lucide="lock" class="w-3 h-3"></i> Khoá</button>`;
        } else {
          actionBtn = `<button type="button" class="btn btn-secondary btn-xs text-emerald-600 border-emerald-200 hover:bg-emerald-50" onclick="toggleUserActive(${u.id}, true)"><i data-lucide="unlock" class="w-3 h-3"></i> Mở khoá</button>`;
        }
      }
      return `<tr class="table-row">
        <td class="table-td font-mono text-xs font-semibold">${escapeHtml(u.username)}</td>
        <td class="table-td font-medium">${escapeHtml(displayText(u.full_name))}</td>
        <td class="table-td">${escapeHtml(roleLabel(u.role))}</td>
        <td class="table-td">${escapeHtml(displayText(u.email))}</td>
        <td class="table-td font-mono text-xs">${escapeHtml(displayText(u.phone))}</td>
        <td class="table-td">${u.service_center_id === null || u.service_center_id === undefined ? "Toàn hệ thống" : "Trung tâm #" + escapeHtml(u.service_center_id)}</td>
        <td class="table-td">${active
          ? '<span class="px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300">Đang làm việc</span>'
          : '<span class="px-2.5 py-1 text-xs font-semibold rounded-full bg-rose-100 text-rose-800 border border-rose-300">Đã khoá</span>'}</td>
        <td class="table-td text-right">${actionBtn}</td>
      </tr>`;
    })
    .join("");
  refreshIcons();
}

/** Quản lý: Khoá / Mở khoá tài khoản nhân viên */
async function toggleUserActive(userId, active) {
  const actionText = active ? "mở khoá" : "khoá";
  const ok = confirm(`Bạn có chắc chắn muốn ${actionText} tài khoản này?`);
  if (!ok) return;

  const res = await apiFetch(`/api/v1/users/${userId}`, {
    method: "PATCH",
    body: { active: active },
  });
  if (!res.ok) {
    toastError(res, `Không thể ${actionText} tài khoản.`);
    return;
  }
  showToast(`Đã ${actionText} tài khoản thành công.`, "success");
  await loadAccounts();
}

/** Quản lý xét duyệt đề xuất từ chối của KTV: APPROVED hoặc DECLINED */
async function reviewRejectionProposal(ticketId, decision) {
  const isApprove = decision === "APPROVED";
  const actionText = isApprove ? "duyệt từ chối" : "không đồng ý từ chối";
  const promptMessage = isApprove
    ? "Xác nhận DUYỆT từ chối bảo hành theo đề xuất của KTV.\nPhiếu sẽ chuyển sang trạng thái TỪ CHỐI (REJECTED).\nNhập lý do/ghi chú duyệt:"
    : "Xác nhận KHÔNG ĐỒNG Ý từ chối bảo hành.\nPhiếu sẽ giữ ở bước Đang kiểm tra (INSPECTING) để KTV tiếp tục xử lý.\nNhập chỉ đạo/lý do cho KTV:";

  const noteInput = prompt(promptMessage, isApprove ? "Đã duyệt đề xuất từ chối bảo hành." : "Không đồng ý từ chối, yêu cầu tiếp tục xử lý.");
  if (noteInput === null) return; // Người dùng ấn Hủy

  const res = await apiFetch(`/api/v1/warranty-tickets/${ticketId}/review-rejection-proposal`, {
    method: "POST",
    body: {
      decision: decision,
      note: noteInput.trim() || (isApprove ? "Đã duyệt đề xuất từ chối bảo hành." : "Không đồng ý từ chối, yêu cầu tiếp tục xử lý."),
    },
  });

  if (!res.ok) {
    toastError(res, `Không thể ${actionText}.`);
    return;
  }

  showToast(isApprove ? "Đã duyệt từ chối bảo hành thành công." : "Đã từ chối đề xuất, yêu cầu KTV tiếp tục xử lý.", "success");
  await openTicketModal(ticketId);
  await loadTickets();
  await loadDashboard();
}

/** Quản lý: Mở modal thêm tài khoản mới */
function openAddUserModal() {
  const form = $("user-form");
  if (form) form.reset();
  clearFieldErrors(["usr-username", "usr-password", "usr-fullname"]);
  openModal("user-modal");
}

/** Quản lý: Submit thêm tài khoản mới */
async function submitUserForm(e) {
  e.preventDefault();
  const submitBtn = e.target ? e.target.querySelector("button[type=submit]") : null;
  const username = ($("usr-username").value || "").trim();
  const password = $("usr-password").value || "";
  const fullName = ($("usr-fullname").value || "").trim();
  const role = $("usr-role").value;
  const phone = ($("usr-phone").value || "").trim() || null;
  const email = ($("usr-email").value || "").trim() || null;

  clearFieldErrors(["usr-username", "usr-password", "usr-fullname"]);
  let hasError = false;
  if (!username) { setFieldError("usr-username", "Vui lòng nhập tên đăng nhập."); hasError = true; }
  if (!password) { setFieldError("usr-password", "Vui lòng nhập mật khẩu."); hasError = true; }
  else if (password.length < 6) { setFieldError("usr-password", "Mật khẩu phải có tối thiểu 6 ký tự."); hasError = true; }
  if (!fullName) { setFieldError("usr-fullname", "Vui lòng nhập họ và tên."); hasError = true; }

  if (hasError) return;

  if (submitBtn) submitBtn.disabled = true;
  try {
    const res = await apiFetch("/api/v1/users/", {
      method: "POST",
      body: {
        username: username,
        password: password,
        full_name: fullName,
        role: role,
        phone: phone,
        email: email,
        service_center_id: 1,
        active: true,
      },
    });
    if (!res.ok) {
      toastError(res, "Không thể tạo tài khoản.");
      return;
    }
    showToast(`Đã tạo tài khoản <strong>${escapeHtml(username)}</strong> thành công.`, "success");
    closeModal("user-modal");
    await loadAccounts();
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

/** AI Chức năng 1: Gợi ý loại lỗi trong màn hình Tiếp nhận máy */
async function wizardSuggestCategory() {
  const descEl = $("wiz-desc");
  const desc = (descEl ? descEl.value : "").trim();
  if (desc.length < 3) {
    showToast("Vui lòng nhập mô tả lỗi (tối thiểu 3 ký tự) để AI gợi ý nhóm lỗi.", "warning");
    if (descEl) descEl.focus();
    return;
  }
  const btn = $("btn-wiz-ai-suggest");
  const hintBox = $("wiz-ai-hint");
  const hintText = $("wiz-ai-hint-text");
  if (btn) btn.disabled = true;
  if (hintBox) hintBox.classList.remove("hidden");
  if (hintText) hintText.innerHTML = '<span class="flex items-center gap-1.5"><i data-lucide="loader" class="w-3.5 h-3.5 animate-spin"></i> Đang phân tích mô tả lỗi...</span>';
  refreshIcons();

  let prodName = "";
  if (state.wizardDevice && state.wizardDevice.product_name) {
    prodName = state.wizardDevice.product_name;
  } else if ($("wiz-product-name") && $("wiz-product-name").value) {
    prodName = $("wiz-product-name").value.trim();
  }

  const res = await apiFetch("/api/v1/ai/suggest-category", {
    method: "POST",
    body: {
      product_name: prodName,
      issue_description: desc,
    },
  });
  if (btn) btn.disabled = false;

  if (!res.ok) {
    if (hintBox) hintBox.classList.add("hidden");
    toastError(res, "Không thể gợi ý loại lỗi.");
    return;
  }

  const d = res.data || {};
  const pInfo = d.provider_info || {};
  const simBadge = pInfo.simulation_label ? `<span class="badge-simulation ml-1 text-[11px] px-1.5 py-0.5 rounded bg-slate-200 text-slate-700 font-semibold">${escapeHtml(pInfo.simulation_label)}</span>` : "";

  if (d.suggested_category_id && $("wiz-category-select")) {
    $("wiz-category-select").value = String(d.suggested_category_id);
  }

  if (hintText) {
    const catName = d.suggested_category_name ? `<strong>${escapeHtml(d.suggested_category_name)}</strong>` : "Chưa xác định nhóm cụ thể";
    hintText.innerHTML = `${catName} (Độ tin cậy: ${confidencePercent(d.confidence)}) ${simBadge} &ndash; ${escapeHtml(d.reason || "")}`;
  }
  refreshIcons();
}

/** AI Chức năng 2: Tóm tắt lịch sử bảo hành theo phiếu */
async function showTicketAiHistory(ticketId = null) {
  const tid = ticketId || (state.selectedTicket ? state.selectedTicket.id : null);
  if (!tid) return;
  openModal("ai-summary-modal");
  const content = $("ai-summary-content");
  if (content) content.innerHTML = '<div class="flex items-center gap-2 text-purple-700 py-3"><i data-lucide="loader" class="w-4 h-4 animate-spin"></i> Đang tổng hợp lịch sử bảo hành...</div>';
  refreshIcons();

  const res = await apiFetch(`/api/v1/ai/tickets/${tid}/summarize-history`, { method: "POST" });
  if (!res.ok) {
    if (content) content.innerHTML = `<span class="text-rose-600">${escapeHtml(errorMessage(res.status, res.data))}</span>`;
    return;
  }
  const d = res.data || {};
  const pInfo = d.provider_info || {};
  const simBadge = pInfo.simulation_label ? `<span class="badge-simulation text-[11px] px-2 py-0.5 rounded bg-slate-200 text-slate-700 font-semibold">${escapeHtml(pInfo.simulation_label)}</span>` : "";
  let repeatBadge = "";
  if (d.is_repeated_fault) {
    repeatBadge = '<div class="p-2.5 rounded-lg bg-amber-50 border border-amber-300 text-amber-900 font-semibold text-xs flex items-center gap-1.5 mb-2"><i data-lucide="alert-triangle" class="w-4 h-4 text-amber-600"></i> Cảnh báo: Thiết bị có dấu hiệu lỗi lặp lại nhiều lần.</div>';
  }
  let catsHtml = "";
  if (Array.isArray(d.fault_categories) && d.fault_categories.length) {
    catsHtml = `<div><strong>Các nhóm lỗi đã ghi nhận:</strong> ${escapeHtml(d.fault_categories.join(", "))}</div>`;
  }
  let partsHtml = "";
  if (Array.isArray(d.repair_parts) && d.repair_parts.length) {
    partsHtml = `<div><strong>Linh kiện từng thay thế:</strong> ${escapeHtml(d.repair_parts.join(", "))}</div>`;
  }

  if (content) {
    content.innerHTML = `
      <div class="flex items-center justify-between mb-2 pb-2 border-b border-slate-200">
        <span class="text-xs text-slate-500 font-semibold uppercase tracking-wider">Tóm tắt lịch sử bảo hành</span>
        ${simBadge}
      </div>
      ${repeatBadge}
      <div class="text-slate-900 font-medium leading-relaxed">${escapeHtml(d.summary || "Chưa có thông tin.")}</div>
      ${d.recommendation ? `<div class="mt-2.5 p-2.5 rounded-lg bg-indigo-50/60 border border-indigo-100 text-xs text-indigo-900"><strong>Khuyến nghị:</strong> ${escapeHtml(d.recommendation)}</div>` : ""}
      <div class="pt-3 mt-3 border-t border-slate-200 text-xs text-slate-600 space-y-1">
        <div><strong>Tổng số lần gửi bảo hành:</strong> ${d.total_tickets || d.ticket_count || 1} lần</div>
        ${catsHtml}
        ${partsHtml}
      </div>
    `;
    refreshIcons();
  }
}

/** AI Chức năng 2: Tóm tắt lịch sử bảo hành theo thiết bị */
async function showDeviceAiHistory(deviceId = null) {
  const did = deviceId || state.selectedDeviceId || (state.selectedDevice ? state.selectedDevice.id : null);
  if (!did) return;
  openModal("ai-summary-modal");
  const content = $("ai-summary-content");
  if (content) content.innerHTML = '<div class="flex items-center gap-2 text-purple-700 py-3"><i data-lucide="loader" class="w-4 h-4 animate-spin"></i> Đang tổng hợp lịch sử bảo hành...</div>';
  refreshIcons();

  const res = await apiFetch(`/api/v1/ai/devices/${did}/summarize-history`, { method: "POST" });
  if (!res.ok) {
    if (content) content.innerHTML = `<span class="text-rose-600">${escapeHtml(errorMessage(res.status, res.data))}</span>`;
    return;
  }
  const d = res.data || {};
  const pInfo = d.provider_info || {};
  const simBadge = pInfo.simulation_label ? `<span class="badge-simulation text-[11px] px-2 py-0.5 rounded bg-slate-200 text-slate-700 font-semibold">${escapeHtml(pInfo.simulation_label)}</span>` : "";
  let repeatBadge = "";
  if (d.is_repeated_fault) {
    repeatBadge = '<div class="p-2.5 rounded-lg bg-amber-50 border border-amber-300 text-amber-900 font-semibold text-xs flex items-center gap-1.5 mb-2"><i data-lucide="alert-triangle" class="w-4 h-4 text-amber-600"></i> Cảnh báo: Thiết bị có dấu hiệu lỗi lặp lại nhiều lần.</div>';
  }
  let catsHtml = "";
  if (Array.isArray(d.fault_categories) && d.fault_categories.length) {
    catsHtml = `<div><strong>Các nhóm lỗi đã ghi nhận:</strong> ${escapeHtml(d.fault_categories.join(", "))}</div>`;
  }
  let partsHtml = "";
  if (Array.isArray(d.repair_parts) && d.repair_parts.length) {
    partsHtml = `<div><strong>Linh kiện từng thay thế:</strong> ${escapeHtml(d.repair_parts.join(", "))}</div>`;
  }

  if (content) {
    content.innerHTML = `
      <div class="flex items-center justify-between mb-2 pb-2 border-b border-slate-200">
        <span class="text-xs text-slate-500 font-semibold uppercase tracking-wider">Tóm tắt lịch sử bảo hành</span>
        ${simBadge}
      </div>
      ${repeatBadge}
      <div class="text-slate-900 font-medium leading-relaxed">${escapeHtml(d.summary || "Chưa có thông tin.")}</div>
      ${d.recommendation ? `<div class="mt-2.5 p-2.5 rounded-lg bg-indigo-50/60 border border-indigo-100 text-xs text-indigo-900"><strong>Khuyến nghị:</strong> ${escapeHtml(d.recommendation)}</div>` : ""}
      <div class="pt-3 mt-3 border-t border-slate-200 text-xs text-slate-600 space-y-1">
        <div><strong>Tổng số lần gửi bảo hành:</strong> ${d.total_tickets || d.ticket_count || 1} lần</div>
        ${catsHtml}
        ${partsHtml}
      </div>
    `;
    refreshIcons();
  }
}

/** AI Chức năng 3: Soạn tin cập nhật tiến độ cho nhân viên xem, sửa và sao chép */
async function showTicketAiNotification(ticketId = null) {
  const tid = ticketId || (state.selectedTicket ? state.selectedTicket.id : null);
  if (!tid) return;
  openModal("ai-notification-modal");
  const area = $("ai-noti-textarea");
  const recipient = $("ai-noti-recipient");
  const statusEl = $("ai-noti-copy-status");
  if (statusEl) statusEl.textContent = "";
  if (area) area.value = "Đang soạn nội dung tin nhắn cập nhật tiến độ...";

  const t = state.selectedTicket;
  if (recipient) {
    const custName = t && t.customer ? t.customer.full_name : (t ? t.customer_name : "");
    const custPhone = t && t.customer ? t.customer.phone : (t ? t.customer_phone : "");
    recipient.textContent = `${displayText(custName)} (${custPhone || "Không có SĐT"})`;
  }

  const res = await apiFetch(`/api/v1/ai/tickets/${tid}/draft-progress-notification`, { method: "POST" });
  if (!res.ok) {
    if (area) area.value = "Không thể tạo nội dung tin nhắn: " + errorMessage(res.status, res.data);
    return;
  }
  const d = res.data || {};
  const pInfo = d.provider_info || {};
  const simBadge = pInfo.simulation_label ? `<span class="badge-simulation text-[11px] px-2 py-0.5 rounded bg-slate-200 text-slate-700 font-semibold">${escapeHtml(pInfo.simulation_label)}</span>` : "";
  if (statusEl) statusEl.innerHTML = simBadge;
  if (area) area.value = d.draft_message || d.suggested_message || "";
}

/** Sao chép nội dung tin nhắn tiến độ vào clipboard */
async function copyNotificationText() {
  const area = $("ai-noti-textarea");
  const statusEl = $("ai-noti-copy-status");
  if (!area || !area.value.trim()) return;
  try {
    await navigator.clipboard.writeText(area.value.trim());
    if (statusEl) statusEl.textContent = "✔ Đã sao chép tin nhắn vào bộ nhớ tạm!";
    showToast("Đã sao chép tin nhắn thông báo vào bộ nhớ tạm.", "success");
  } catch (err) {
    area.select();
    document.execCommand("copy");
    if (statusEl) statusEl.textContent = "✔ Đã sao chép tin nhắn!";
    showToast("Đã sao chép tin nhắn.", "success");
  }
}

/* --------------------------- KHỞI TẠO --------------------------- */
function bindEvents() {
  setupTabs();
  setupAuthEvents();

  $("btn-goto-tickets").addEventListener("click", goToTickets);
  $("customer-form").addEventListener("submit", submitCustomerForm);
  $("product-form").addEventListener("submit", submitProductForm);
  $("device-form").addEventListener("submit", submitDeviceForm);
  const userForm = $("user-form");
  if (userForm) userForm.addEventListener("submit", submitUserForm);
  $("action-modal-confirm").addEventListener("click", confirmActionModal);

  // Wizard "Tiếp nhận máy mới": tra số sê-ri + tính trước hạn bảo hành
  const wizSerial = $("wiz-serial");
  if (wizSerial) {
    wizSerial.addEventListener("blur", () => {
      if (wizSerial.value.trim() && !state.wizard.device) wizardLookupSerial();
    });
  }
  $("wiz-purchase-date").addEventListener("change", recalcWizardEndDate);
  $("wiz-months").addEventListener("input", recalcWizardEndDate);
  $("wiz-customer-id").addEventListener("change", () => setFieldError("wiz-customer", ""));
  $("wiz-product-name").addEventListener("change", () => setFieldError("wiz-product", ""));
  $("wiz-desc").addEventListener("input", () => setFieldError("wiz-desc", ""));
  $("wiz-created-by").addEventListener("change", () => setFieldError("wiz-created-by", ""));
  $("ai-ticket-select").addEventListener("change", onAiTicketChange);
  $("dev-purchase-date").addEventListener("change", recalcDeviceEndDate);
  $("dev-months").addEventListener("input", recalcDeviceEndDate);

  // Bộ lọc trạng thái phiếu
  document.querySelectorAll(".filter-status-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".filter-status-btn").forEach((b) => {
        b.classList.remove("btn-primary");
        b.classList.add("btn-secondary");
      });
      btn.classList.remove("btn-secondary");
      btn.classList.add("btn-primary");
      loadTickets(btn.getAttribute("data-status"));
    });
  });

  // Đóng modal bằng phím Esc
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    ["ticket-modal", "customer-modal", "product-modal", "device-modal", "action-modal"].forEach((id) => {
      const el = $(id);
      if (el && el.style.display === "flex") {
        if (id === "action-modal") closeActionModal();
        else closeModal(id);
      }
    });
  });
}

function setupAuthEvents() {
  const form = $("login-form");
  if (form) {
    form.addEventListener("submit", submitLogin);
    form.addEventListener("input", () => setLoginMessage(""));
  }
  // Bấm vào tài khoản demo để tự điền nhanh
  document.querySelectorAll(".login-demo-item").forEach((item) => {
    item.addEventListener("click", () => {
      const u = item.getAttribute("data-demo-user");
      const p = item.getAttribute("data-demo-pass");
      if (u && p) {
        if ($("login-username")) $("login-username").value = u;
        if ($("login-password")) $("login-password").value = p;
        setLoginMessage("");
        const submitBtn = $("login-submit");
        if (submitBtn) submitBtn.focus();
      }
    });
  });
  const logoutBtn = $("btn-logout");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", () =>
      showActionModal({
        title: "Đăng xuất",
        message: "Bạn có chắc muốn thoát phiên làm việc hiện tại? Phiên đăng nhập sẽ bị thu hồi trên hệ thống.",
        confirmLabel: "Đăng xuất",
        danger: true,
        onConfirm: () => logout(),
      })
    );
  }
}

async function init() {
  refreshIcons();
  bindEvents();

  // Chưa/f5 lại trang: thử khôi phục phiên cũ, nếu không có thì hiện màn hình đăng nhập.
  const restored = await restoreSession();
  if (!restored) {
    setAuthState("guest");
    const userInput = $("login-username");
    if (userInput) userInput.focus();
    refreshIcons();
    return;
  }

  await enterWorkspace();
}

document.addEventListener("DOMContentLoaded", init);















