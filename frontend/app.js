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
  selectedTicket: null,
  selectedDeviceId: null,
  currentAiResult: null,
  wizard: { device: null },
  actionHandler: null,
  // Danh sách id các trường nghiệp vụ đang hiển thị trong hộp thoại xác nhận
  actionFields: [],
  // Phiên làm việc hiện tại: token + thông tin nhân viên (vai trò & danh sách quyền).
  session: { token: "", user: null },
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
    success: "bg-emerald-950/90 border-emerald-500/50 text-emerald-100",
    error: "bg-rose-950/90 border-rose-500/50 text-rose-100",
    warning: "bg-amber-950/90 border-amber-500/50 text-amber-100",
    info: "bg-slate-900/95 border-slate-700 text-slate-200",
  };
  const toast = document.createElement("div");
  toast.className = `toast flex items-start gap-3 p-4 rounded-xl border shadow-2xl max-w-md ${colors[type] || colors.info}`;
  toast.innerHTML = `
    <i data-lucide="${icons[type] || "info"}" class="w-5 h-5 mt-0.5 shrink-0"></i>
    <div class="flex-1 text-sm font-medium leading-relaxed">${message}</div>
    <button class="text-slate-400 hover:text-white ml-2 text-xs" onclick="this.parentElement.remove()">&times;</button>`;
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

/** Bỏ các thẻ kỹ thuật mà backend gắn vào thông báo: [BR2 FAIL], [AI-01]... */
function stripTechTags(text) {
  if (!text) return "";
  let out = String(text);
  out = out.replace(/\[(BR[1-5]|STATE MACHINE|AI-01|GUARDRAIL|INVALID AI OUTPUT|VALIDATION|REVIEW|AUD-\d+|CHẶN STATE MACHINE)[^\]]*\]/gi, " ");
  out = out.replace(/\(FK RESTRICT\)/gi, " ");
  out = out.replace(/\s{2,}/g, " ").trim();
  out = out.replace(/\s+([.,;:])/g, "$1");
  return out.replace(/^[-–•:\s]+/, "");
}

/* Mã trạng thái xuất hiện BÊN TRONG câu thông báo -> tiếng Việt */
const INLINE_CODE_MAP = {
  "RECEIVED": "Mới tiếp nhận",
  "INSPECTING": "Đang kiểm tra",
  "REPAIRING": "Đang sửa chữa",
  "WAITING_RETURN": "Chờ trả máy",
  "COMPLETED": "Đã hoàn tất",
  "REJECTED": "Từ chối bảo hành",
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
/* 6 trạng thái vòng đời phiếu - khớp ALLOWED_TRANSITIONS ở backend
   (app/services/warranty_rules.py). Bắt buộc đi qua WAITING_RETURN trước khi hoàn tất. */
const STATUS_LABELS = {
  RECEIVED: "Mới tiếp nhận",
  INSPECTING: "Đang kiểm tra",
  REPAIRING: "Đang sửa chữa",
  WAITING_RETURN: "Chờ trả máy",
  COMPLETED: "Đã hoàn tất",
  REJECTED: "Từ chối bảo hành",
};
const STATUS_COLORS = ["#3B82F6", "#F59E0B", "#A855F7", "#06B6D4", "#10B981", "#EF4444"];
const STATUS_ORDER = ["RECEIVED", "INSPECTING", "REPAIRING", "WAITING_RETURN", "COMPLETED", "REJECTED"];

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
        ${field.hint ? `<div class="text-[11px] text-slate-500 mt-1">${escapeHtml(field.hint)}</div>` : ""}
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

function confirmActionModal() {
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

  const handler = state.actionHandler;
  const actorId = selectedStaffId("TECHNICIAN");
  closeActionModal();
  if (typeof handler === "function") handler({ actorId, values });
}

/* --------------------------- Điều hướng tab --------------------------- */
/* Danh sách màn hình của ứng dụng (thứ tự này không quyết định menu; menu do HTML + data-perm quyết định). */
const TABS = ["dashboard", "lookup", "customers", "products", "devices", "tickets", "ai", "accounts"];

function setupTabs() {
  document.querySelectorAll(".nav-tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      switchTab(btn.getAttribute("data-tab"));
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
  if (!TABS.includes(tabId)) tabId = "dashboard";
  // Không cho mở màn hình mà vai trò hiện tại không có quyền (backend vẫn là nơi chặn thật).
  if (TAB_PERMISSIONS[tabId] && !hasPerm(TAB_PERMISSIONS[tabId])) tabId = firstAllowedTab();
  state.currentTab = tabId;

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
  if (tabId === "tickets") { loadWizardOptions(); loadTickets(); }
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
    const actor = defaultActor(staff, "RECEPTIONIST");
    if (actor) reviewer.value = String(actor.id);
  }
}

/* --------------------------- TRẠNG THÁI BẢO HÀNH (chỉ để hiển thị) ---------------------------
   QUAN TRỌNG: đây là phần hiển thị. Quyết định bảo hành vẫn do backend (`warranty_end_date >= check_date`).
   ------------------------------------------------------------------------- */
function warrantyInfoFor(endDateISO) {
  if (!endDateISO) return { label: "Không xác định", textClass: "text-slate-300", dot: "⚪", days: null };
  const end = new Date(String(endDateISO) + "T00:00:00");
  if (isNaN(end.getTime())) return { label: "Không xác định", textClass: "text-slate-300", dot: "⚪", days: null };
  const today = new Date(todayISO() + "T00:00:00");
  const days = Math.round((end - today) / 86400000);
  if (days >= 0) return { label: "Còn bảo hành", textClass: "text-emerald-300", dot: "🟢", days };
  return { label: "Đã hết hạn", textClass: "text-rose-300", dot: "🔴", days };
}

function warrantyStatusHtml(endDateISO) {
  const w = warrantyInfoFor(endDateISO);
  const detail = w.days === null ? "" : (w.days >= 0 ? `còn ${w.days} ngày` : `quá hạn ${Math.abs(w.days)} ngày`);
  return `<span class="font-semibold ${w.textClass}">${w.dot} ${w.label}</span>` +
    (detail ? `<span class="text-slate-400"> (${detail})</span>` : "");
}

/* --------------------------- MÀN HÌNH: TỔNG QUAN ---------------------------
   [Đợt màn hình công việc theo vai trò] Bảng điều khiển trả lời câu hỏi
   "Hiện tại tôi cần làm gì?" cho TỪNG vai trò. Toàn bộ nội dung (tiêu đề, thẻ
   số liệu, nhóm việc, việc cần chú ý, nút hành động) do backend trả về qua
   GET /api/v1/warranty-tickets/workboard — giao diện không tự suy diễn.
   ------------------------------------------------------------------------- */

/** Màu chữ theo "tông" mà backend gán cho thẻ số liệu (mỗi trạng thái 1 màu cố định). */
const TONE_TEXT = {
  blue: "text-blue-400",
  amber: "text-amber-400",
  purple: "text-purple-400",
  cyan: "text-cyan-400",
  emerald: "text-emerald-400",
  rose: "text-rose-400",
  indigo: "text-indigo-400",
  slate: "text-slate-200",
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
  if (title) title.textContent = wb.title || "Tổng quan";
  const subtitle = $("dash-subtitle");
  if (subtitle) subtitle.textContent = wb.subtitle || "";
  const roleChip = $("dash-role-chip");
  if (roleChip) roleChip.textContent = `${wb.role_label || roleLabel(wb.role)} • ${state.session.user ? "@" + state.session.user.username : ""}`;
  const scopeChip = $("dash-scope-chip");
  if (scopeChip) {
    const show = wb.scope && wb.scope !== "DEFAULT";
    scopeChip.textContent = `Phạm vi: ${wb.scope_label || wb.scope}`;
    scopeChip.classList.toggle("hidden", !show);
  }
}

/** Thẻ số liệu theo vai trò; bấm thẻ có trạng thái thì mở danh sách phiếu đã lọc. */
function renderDashCards(cards) {
  const box = $("dash-cards");
  if (!box) return;
  const items = Array.isArray(cards) ? cards : [];
  if (!items.length) {
    box.innerHTML = '<div class="text-xs text-slate-500 col-span-full">Chưa có số liệu.</div>';
    return;
  }
  box.innerHTML = items
    .map((card) => {
      const clickable = card.status ? `onclick="openTicketsFiltered('${card.status}')" role="button" tabindex="0"` : "";
      return `<div class="glass-panel glass-panel-hover rounded-xl p-4 border border-slate-800 dash-card" ${clickable}>
        <div class="flex items-center justify-between text-xs mb-2 ${toneText(card.tone)}"><span>${escapeHtml(card.label)}</span><i data-lucide="circle-dot" class="w-4 h-4"></i></div>
        <div class="text-2xl font-bold font-mono ${toneText(card.tone)}">${num(card.count)}</div>
        <div class="text-[11px] text-slate-500 mt-1">${escapeHtml(card.description || "")}</div>
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
        <span class="text-[10px] font-normal opacity-80">${escapeHtml(action.description || "")}</span>
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
  const query = scope ? `?scope=${encodeURIComponent(scope)}` : "";
  const res = await apiFetch(`/api/v1/warranty-tickets/workboard${query}`);
  if (!res.ok) {
    toastError(res, "Không tải được bảng điều khiển công việc.");
    return;
  }
  const wb = res.data || {};
  state.workboard = wb;

  renderDashHeader(wb);
  renderDashQuickActions(wb);
  renderDashCards(wb.cards);
  renderWorkGroups(wb.groups);
  renderDashFocus(wb);
  renderDashAttention(wb);
  renderDashNotes(wb);
  renderDashViewButtons(wb);
  renderDashTable(wb, state.dashView);

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

/** Nút chuyển cách xem: Quản lý xem toàn hệ thống / việc cần chú ý; nhân viên xem việc của tôi / toàn bộ. */
function renderDashViewButtons(wb) {
  const box = $("dash-view-buttons");
  if (!box) return;
  const role = wb.role || "";
  const view = state.dashView;
  const defs = role === "MANAGER"
    ? [
        { key: "all", label: "Toàn bộ hệ thống", icon: "layout-list" },
        { key: "attention", label: "Việc cần chú ý", icon: "alert-triangle" },
      ]
    : [
        { key: "mine", label: "Việc của tôi", icon: "user-check" },
        { key: "all", label: "Toàn bộ phiếu", icon: "layout-list" },
      ];
  const defaultKey = role === "MANAGER" ? "all" : "mine";
  const activeKey = view === "attention" ? "attention" : (view === "all" || view === "mine" ? view : defaultKey);
  box.innerHTML = defs
    .map((def) => `<button class="btn ${def.key === activeKey ? "btn-primary" : "btn-secondary"} btn-sm" onclick="setDashView('${def.key}')">
        <i data-lucide="${def.icon}" class="w-3.5 h-3.5"></i> ${def.label}</button>`)
    .join("") +
    `<button class="btn btn-secondary btn-sm" onclick="openTicketsFiltered('')"><i data-lucide="arrow-right" class="w-3.5 h-3.5"></i> Xem tất cả phiếu</button>`;
  refreshIcons();
}

/** Mở màn "Phiếu bảo hành" với bộ lọc trạng thái (dùng từ bảng điều khiển). */
function openTicketsFiltered(status) {
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
      openTicketsFiltered("WAITING_RETURN");
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
  const target = row.primary_action ? row.primary_action.target : null;
  if (group.action_label && (!group.action_target || group.action_target === target)) {
    return group.action_label;
  }
  return row.action_label || "Xem phiếu";
}

/** True nếu bấm nút trong nhóm sẽ chuyển trạng thái (ngược lại chỉ mở phiếu xem). */
function groupActionIsTransition(group, row) {
  return row.action_kind === "transition" && !!row.primary_action &&
    (!group.action_target || group.action_target === row.primary_action.target);
}

/** Nhóm công việc: số lượng + danh sách phiếu cần xử lý ngay (mỗi phiếu 1 nút hành động). */
function renderWorkGroups(groups) {
  const box = $("dash-workload");
  if (!box) return;
  const items = Array.isArray(groups) ? groups : [];
  const hint = $("dash-workload-hint");
  const title = $("dash-workload-title");
  if (title) {
    title.innerHTML = '<i data-lucide="list-checks" class="w-4 h-4 text-amber-400"></i> Công việc theo bước';
  }
  if (!items.length) {
    box.innerHTML = '<div class="text-xs text-slate-500">Vai trò này chưa có nhóm công việc nào.</div>';
    if (hint) hint.textContent = "";
    return;
  }
  box.innerHTML = items
    .map((group) => {
      const rows = Array.isArray(group.items) ? group.items : [];
      const head = `<button type="button" class="w-full text-left" onclick="openTicketsFiltered('${escapeHtml(group.status_filter || "")}')"
              title="Mở danh sách phiếu ở bước này">
          <div class="flex items-center justify-between gap-2">
            <span class="text-xs font-semibold text-slate-200">${escapeHtml(group.label)}</span>
            <span class="text-lg font-bold font-mono ${group.count > 0 ? toneText(group.tone) : "text-slate-600"}">${group.count}</span>
          </div>
          <div class="text-[11px] text-slate-500 mt-1">${escapeHtml(group.description || "")}</div>
          <div class="text-[10px] text-slate-600 mt-1">Phạm vi: ${escapeHtml(group.scope_label || "")}</div>
        </button>`;
      const rowHtml = rows.length
        ? rows
            .map((row) => {
              const isTransition = groupActionIsTransition(group, row);
              const target = isTransition && row.primary_action ? row.primary_action.target : null;
              return `<div class="dash-work-item">
                <div class="min-w-0">
                  <div class="font-mono text-indigo-300 truncate">${escapeHtml(row.ticket_code)}</div>
                  <div class="text-slate-400 truncate">${escapeHtml(displayText(row.customer_name) || "–")} &bull; ${escapeHtml(displayText(row.product_name) || row.serial_number || "")}</div>
                </div>
                <button class="btn ${isTransition ? "btn-primary" : "btn-secondary"} btn-sm shrink-0"
                        onclick="handleTicketAction(${row.id}, ${target ? `'${target}'` : "null"})">
                  ${escapeHtml(groupActionLabel(group, row))}
                </button>
              </div>`;
            })
            .join("")
        : '<div class="text-[11px] text-slate-500">Không còn phiếu nào ở bước này.</div>';
      return `<div class="p-3 rounded-xl border border-slate-800 bg-slate-900/70 flex flex-col gap-2">${head}${rowHtml}</div>`;
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
    box.innerHTML = '<div class="text-xs text-emerald-300/90">Bạn không còn phiếu nào đang chờ xử lý.</div>';
    return;
  }
  box.innerHTML = rows
    .map((row, index) => {
      const isTransition = row.action_kind === "transition" && row.primary_action;
      const target = isTransition ? row.primary_action.target : null;
      return `<div class="dash-focus-row">
        <span class="dash-focus-index">${index + 1}</span>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="font-mono font-semibold text-indigo-300">${escapeHtml(row.ticket_code)}</span>
            ${statusBadge(row.status)}
            <span class="text-[11px] text-slate-500 font-mono">${escapeHtml(row.serial_number || "–")}</span>
            <span class="text-[11px] text-slate-400">${escapeHtml(displayText(row.product_name) || "")}</span>
          </div>
          <div class="text-[11px] text-slate-400 mt-0.5 truncate">
            ${escapeHtml(displayText(row.customer_name) || "–")} &bull; ${escapeHtml(row.customer_phone || "")} &bull; phụ trách: ${escapeHtml(ticketHandlerName(row))}
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
    box.innerHTML = '<div class="text-xs text-emerald-300/90">Không có phiếu nào cần chú ý.</div>';
    return;
  }
  box.innerHTML = rows
    .map(
      (row) => `<button type="button" class="dash-attention-row" onclick="openTicketModal(${row.ticket_id})">
        <div class="flex items-center justify-between gap-2">
          <span class="font-mono text-indigo-300">${escapeHtml(row.ticket_code)}</span>
          ${statusBadge(row.status)}
        </div>
        <div class="text-slate-200 mt-1">${escapeHtml(displayText(row.customer_name) || "–")} &bull; ${escapeHtml(displayText(row.product_name) || row.serial_number || "")}</div>
        <div class="text-amber-200/90 mt-1">${escapeHtml(row.reason)}</div>
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

/** Nút hành động phụ của một dòng (chỉ hiện khi thực sự có bước khác được phép). */
function rowExtraActionsHtml(row) {
  const extras = (Array.isArray(row.available_actions) ? row.available_actions : []).filter(
    (action) => !row.primary_action || action.target !== row.primary_action.target
  );
  if (!extras.length) return "";
  return `<details class="row-more">
      <summary class="row-more-summary">Thêm</summary>
      <div class="row-more-menu">
        ${extras
          .map(
            (action) =>
              `<button class="btn btn-secondary btn-sm w-full justify-start" onclick="handleTicketAction(${row.id}, '${action.target}')">${escapeHtml(action.button_label)}</button>`
          )
          .join("")}
      </div>
    </details>`;
}

/** Bảng "Phiếu đang xử lý" / "Việc cần chú ý" - mỗi dòng 1 hành động chính theo quyền. */
function renderDashTable(wb, view) {
  const tbody = $("dash-active-body");
  if (!tbody) return;
  const isAttention = view === "attention";
  const lastCol = $("dash-active-last-col");
  if (lastCol) lastCol.textContent = isAttention ? "Lý do cần chú ý" : "Loại lỗi";

  const useMine = !isAttention && (view === "mine" || (view !== "all" && wb.role !== "MANAGER"));
  const title = $("dash-active-title");
  if (title) {
    title.innerHTML = isAttention
      ? '<i data-lucide="alert-triangle" class="w-4 h-4 text-amber-400"></i> Việc cần chú ý'
      : `<i data-lucide="hammer" class="w-4 h-4 text-cyan-400"></i> ${escapeHtml(
          useMine ? "Phiếu tôi đang xử lý" : (wb.table_title || "Phiếu đang xử lý")
        )}`;
  }

  const rows = isAttention
    ? (Array.isArray(wb.attention) ? wb.attention : []).map((item) => ({
        ...item,
        id: item.ticket_id,
        _reason: item.reason,
      }))
    : (useMine ? wb.my_tickets || [] : wb.active_tickets || []);

  if (!rows.length) {
    setTableMessage(
      "dash-active-body",
      8,
      isAttention
        ? "Không có phiếu nào cần chú ý."
        : useMine
          ? 'Bạn hiện không có phiếu nào đang xử lý. Bấm "Toàn bộ phiếu" để xem tất cả.'
          : "Hiện không có phiếu nào đang xử lý."
    );
    return;
  }

  tbody.innerHTML = rows
    .map((row) => {
      const isTransition = row.action_kind === "transition" && row.primary_action;
      const target = isTransition ? row.primary_action.target : null;
      const lastCell = isAttention
        ? `<span class="text-amber-200/90">${escapeHtml(row._reason || "")}</span>`
        : escapeHtml(row.error_category_name || categoryName(row.error_category_id));
      return `<tr class="table-row">
      <td class="table-td font-mono font-semibold text-indigo-300">${escapeHtml(row.ticket_code)}</td>
      <td class="table-td font-mono text-cyan-300">${escapeHtml(row.serial_number || "–")}<br><span class="text-[11px] text-slate-500">${escapeHtml(displayText(row.product_name) || "")}</span></td>
      <td class="table-td text-slate-200">${escapeHtml(displayText(row.customer_name) || "–")}<br><span class="text-[11px] text-slate-500 font-mono">${escapeHtml(row.customer_phone || "")}</span></td>
      <td class="table-td">${statusBadge(row.status)}</td>
      <td class="table-td text-slate-300 text-xs">${escapeHtml(ticketHandlerName(row))}</td>
      <td class="table-td text-slate-400">${fmtDateTime(row.created_at)}</td>
      <td class="table-td text-slate-400 text-xs">${lastCell}</td>
      <td class="table-td text-right">
        <div class="flex flex-col items-end gap-1">
          <button class="btn ${isTransition ? "btn-primary" : "btn-secondary"} btn-sm"
                  onclick="handleTicketAction(${row.id}, ${target ? `'${target}'` : "null"})">
            <i data-lucide="${isTransition ? "arrow-right-circle" : "eye"}" class="w-3.5 h-3.5"></i> ${escapeHtml(row.action_label || "Xem phiếu")}
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
 * mở thẳng màn hình phiếu; nếu là bước chuyển trạng thái thì mở luôn hộp thoại xác nhận.
 */
function handleTicketAction(ticketId, targetStatus) {
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
      <span class="font-semibold text-slate-100">${escapeHtml(displayText(d.product_name) || "Thiết bị")}</span>
      <span class="text-[10px] text-slate-400">${escapeHtml(displayText(d.customer_name) || "Chưa rõ khách hàng")} &bull; <span class="${w.textClass} font-semibold">${w.dot} ${w.label}</span></span>
      <span class="text-[10px] text-slate-500 font-mono">Số sê-ri: ${escapeHtml(d.serial_number)}</span>
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
    : '<span class="text-[11px] text-slate-500">Chưa có thiết bị nào trong hệ thống.</span>';
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
  box.innerHTML = '<div class="glass-panel rounded-2xl p-5 border border-slate-800 text-xs text-slate-400">Đang tra cứu...</div>';
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
  const warrantyBoxClass = w.days !== null && w.days >= 0 ? "bg-emerald-950/40 border-emerald-600/40" : "bg-rose-950/40 border-rose-600/40";
  const warrantyDetail = w.days === null
    ? "Chưa có ngày hết hạn"
    : (w.days >= 0 ? `Hạn đến: ${fmtDate(d.warranty_end_date)} (còn ${w.days} ngày)` : `Đã hết hạn ngày ${fmtDate(d.warranty_end_date)} (quá ${Math.abs(w.days)} ngày)`);
  const serialArg = escapeHtml(d.serial_number);

  return `
    <div class="glass-panel rounded-2xl p-5 border border-slate-800">
      <div class="flex flex-wrap items-center justify-between gap-2 mb-4">
        <h3 class="section-title"><i data-lucide="shield-check" class="w-4 h-4 text-emerald-400"></i> Thông tin bảo hành</h3>
        <button class="btn btn-secondary btn-sm" onclick="openDeviceDetailModal(${d.id})"><i data-lucide="info" class="w-3.5 h-3.5"></i> Xem chi tiết thiết bị</button>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-xs mb-4">
        <div class="p-3 bg-slate-900/70 rounded-xl border border-slate-800">
          <div class="text-slate-400 mb-1">Sản phẩm</div>
          <div class="font-semibold text-slate-100">${escapeHtml(displayText(d.product_name) || "–")}</div>
          <div class="text-slate-400 mt-1">Hãng: <span class="text-slate-200">${escapeHtml(displayText(d.product_brand) || "–")}</span></div>
        </div>
        <div class="p-3 bg-slate-900/70 rounded-xl border border-slate-800">
          <div class="text-slate-400 mb-1">Số sê-ri</div>
          <div class="font-mono font-semibold text-cyan-300">${escapeHtml(d.serial_number)}</div>
        </div>
        <div class="p-3 bg-slate-900/70 rounded-xl border border-slate-800">
          <div class="text-slate-400 mb-1">Khách hàng</div>
          <div class="font-semibold text-slate-200">${escapeHtml(displayText(d.customer_name) || "–")}</div>
          <div class="text-slate-400 mt-1 font-mono">${escapeHtml(d.customer_phone || "")}</div>
        </div>
        <div class="p-3 bg-slate-900/70 rounded-xl border border-slate-800">
          <div class="text-slate-400 mb-1">Ngày mua</div>
          <div class="font-mono text-slate-200">${fmtDate(d.purchase_date)}</div>
        </div>
        <div class="p-3 bg-slate-900/70 rounded-xl border border-slate-800">
          <div class="text-slate-400 mb-1">Hạn bảo hành</div>
          <div class="font-mono text-slate-200">${fmtDate(d.warranty_end_date)}</div>
        </div>
        <div class="p-3 rounded-xl border ${warrantyBoxClass}">
          <div class="text-slate-400 mb-1">Trạng thái bảo hành</div>
          <div class="text-base font-bold ${w.textClass}">${w.dot} ${w.label.toUpperCase()}</div>
          <div class="text-slate-400 mt-1">${warrantyDetail}</div>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        ${hasPerm("ticket.create") ? `<button class="btn btn-primary" onclick="startTicketForSerial('${serialArg}')"><i data-lucide="file-plus-2" class="w-4 h-4"></i> Tạo phiếu bảo hành cho thiết bị này</button>` : ""}
        <button class="btn btn-secondary" onclick="runLookupCheck('${serialArg}')"><i data-lucide="search-check" class="w-4 h-4"></i> Đối chiếu điều kiện bảo hành</button>
        <span class="text-[11px] text-slate-500">${tickets.length ? `Thiết bị đã có ${tickets.length} phiếu bảo hành` : "Thiết bị chưa có phiếu bảo hành nào"}</span>
      </div>

      <div id="lookup-check-result" class="mt-3"></div>
      ${tickets.length ? `
      <div class="mt-3 pt-3 border-t border-slate-800">
        <div class="text-[11px] text-slate-400 mb-2">Phiếu bảo hành của thiết bị:</div>
        <div class="flex flex-wrap gap-2">
          ${tickets.map((t) => `<button class="btn btn-secondary btn-sm" onclick="openTicketModal(${t.id})"><span class="font-mono">${escapeHtml(t.ticket_code)}</span> ${statusBadge(t.status)}</button>`).join("")}
        </div>
      </div>` : ""}
    </div>`;
}

/** Thẻ thông báo khi không tìm thấy dữ liệu tra cứu. */
function lookupNotFoundCard(keyword, hint) {
  return `
    <div class="glass-panel rounded-2xl p-5 border border-amber-900/60">
      <div class="text-sm font-semibold text-amber-200 mb-1">Không tìm thấy "${escapeHtml(keyword)}" trong hệ thống</div>
      <p class="text-xs text-slate-400">${hint}</p>
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
  const handler = ticketHandlerName(t);
  box.innerHTML = `
    <div class="glass-panel rounded-2xl p-5 border border-slate-800">
      <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h3 class="section-title"><i data-lucide="file-text" class="w-4 h-4 text-indigo-400"></i> Phiếu bảo hành <span class="font-mono ml-1">${escapeHtml(t.ticket_code)}</span></h3>
        <button class="btn btn-primary btn-sm" onclick="openTicketModal(${t.id})"><i data-lucide="arrow-up-right" class="w-3.5 h-3.5"></i> Mở phiếu để xử lý</button>
      </div>

      ${ticketProgressHtml(t.status)}

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-xs mt-4">
        <div class="p-3 bg-slate-900/70 rounded-xl border border-slate-800">
          <div class="text-slate-400 mb-1">Khách hàng</div>
          <div class="font-semibold text-slate-200">${escapeHtml(displayText(t.customer_name) || "–")}</div>
        </div>
        <div class="p-3 bg-slate-900/70 rounded-xl border border-slate-800">
          <div class="text-slate-400 mb-1">Thiết bị (số sê-ri)</div>
          <div class="font-mono font-semibold text-cyan-300">${escapeHtml(t.serial_number || "–")}</div>
          <div class="text-slate-400 mt-1">${escapeHtml(displayText(t.product_name) || "")}</div>
        </div>
        <div class="p-3 bg-slate-900/70 rounded-xl border border-slate-800">
          <div class="text-slate-400 mb-1">Tình trạng bảo hành của thiết bị</div>
          <div class="${w.textClass} font-semibold">${w.dot} ${w.label}</div>
          <div class="text-slate-400 mt-1">Hạn: <span class="font-mono">${fmtDate(t.warranty_end_date)}</span></div>
        </div>
        <div class="p-3 bg-slate-900/70 rounded-xl border border-slate-800">
          <div class="text-slate-400 mb-1">Ngày tiếp nhận</div>
          <div class="font-mono text-slate-200">${fmtDateTime(t.created_at)}</div>
        </div>
        <div class="p-3 bg-slate-900/70 rounded-xl border border-slate-800">
          <div class="text-slate-400 mb-1">Nhân viên phụ trách</div>
          <div class="text-slate-200">${escapeHtml(handler)}</div>
        </div>
        <div class="p-3 bg-slate-900/70 rounded-xl border border-slate-800">
          <div class="text-slate-400 mb-1">Loại lỗi</div>
          <div class="text-slate-200">${escapeHtml(categoryName(t.error_category_id))}</div>
        </div>
      </div>

      <div class="mt-3">
        <div class="text-xs font-semibold text-slate-300 mb-1">Nội dung sự cố khách báo</div>
        <div class="text-sm text-slate-200 p-3 bg-slate-900/70 rounded-xl border border-slate-800">${escapeHtml(humanizeText(t.issue_description) || "–")}</div>
      </div>
    </div>`;
}

/** Đối chiếu điều kiện bảo hành theo đúng nghiệp vụ backend (chỉ hiển thị kết luận). */
async function runLookupCheck(serial) {
  const box = $("lookup-check-result");
  if (!box) return;
  box.innerHTML = '<span class="text-xs text-slate-400">Đang đối chiếu...</span>';
  const res = await apiFetch("/api/v1/debug/check-warranty", {
    method: "POST",
    body: { serial_number: serial, check_date: todayISO() },
  });
  if (!res.ok) {
    box.innerHTML = `<span class="text-xs text-rose-300">${escapeHtml(errorMessage(res.status, res.data))}</span>`;
    return;
  }
  const data = res.data;
  const valid = data.is_valid === true;
  const traces = Array.isArray(data.debug_traces) ? data.debug_traces : [];
  box.innerHTML = `
    <div class="p-3 rounded-xl border text-xs ${valid ? "bg-emerald-950/30 border-emerald-600/40 text-emerald-200" : "bg-rose-950/30 border-rose-600/40 text-rose-200"}">
      <div class="font-bold">${valid ? "Đủ điều kiện bảo hành" : "Không đủ điều kiện bảo hành"}</div>
      <div class="mt-1 text-[11px]">Đối chiếu ngày ${fmtDate(data.check_date)}: ${escapeHtml(humanizeText(data.status_message))}</div>
    </div>
    ${traces.length ? `
    <details class="mt-2 rounded-xl border border-slate-800 bg-black/60">
      <summary class="px-3 py-2 text-[11px] font-semibold text-slate-400">Thông tin đối chiếu chi tiết (chỉ cần khi trao đổi với bộ phận kỹ thuật)</summary>
      <div class="px-3 pb-3 font-mono text-[11px] text-slate-400 space-y-0.5">
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
    setTableMessage("customers-table-body", 6, "Không tải được danh sách khách hàng.");
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
      <td class="table-td font-semibold text-slate-100">${escapeHtml(displayText(c.full_name))}</td>
      <td class="table-td font-mono text-indigo-300">${escapeHtml(c.phone)}</td>
      <td class="table-td text-slate-400">${escapeHtml(c.email || "–")}</td>
      <td class="table-td text-slate-400">${escapeHtml(c.address || "–")}</td>
      <td class="table-td text-center font-mono text-cyan-300">${deviceCount}</td>
      <td class="table-td text-center font-mono text-fuchsia-300">${ticketCount}</td>
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
    <div class="p-3 bg-slate-900/70 rounded-xl border border-slate-800">
      <div class="text-slate-400 mb-1">${label}</div>
      <div class="font-semibold text-slate-100${mono ? " font-mono" : ""}">${value}</div>
    </div>`;

  const deviceRows = devices.length
    ? devices.map((d) => `
      <tr class="table-row">
        <td class="table-td font-mono text-cyan-300">${escapeHtml(d.serial_number)}</td>
        <td class="table-td text-slate-200">${escapeHtml(displayText(d.product_name) || "–")}</td>
        <td class="table-td text-slate-400 font-mono">${fmtDate(d.warranty_end_date)}</td>
        <td class="table-td">${warrantyStatusHtml(d.warranty_end_date)}</td>
        <td class="table-td text-right whitespace-nowrap">
          <button class="btn btn-secondary btn-sm" onclick="closeModal('customer-detail-modal'); openDeviceDetailModal(${d.id})"><i data-lucide="info" class="w-3.5 h-3.5"></i> Chi tiết thiết bị</button>
        </td>
      </tr>`).join("")
    : '<tr><td class="table-msg" colspan="5">Khách hàng chưa có thiết bị nào.</td></tr>';

  const ticketRows = tickets.length
    ? tickets.map((t) => `
      <tr class="table-row">
        <td class="table-td font-mono text-indigo-300">${escapeHtml(t.ticket_code)}</td>
        <td class="table-td">${statusBadge(t.status)}</td>
        <td class="table-td text-slate-400">${escapeHtml(displayText(t.product_name) || "–")}</td>
        <td class="table-td text-slate-400 font-mono">${fmtDate(t.received_date)}</td>
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
    <div class="p-3 bg-slate-900/70 rounded-xl border border-slate-800">
      <div class="text-slate-400 mb-1">Địa chỉ</div>
      <div class="text-slate-200">${escapeHtml(c.address || "–")}</div>
    </div>

    <div>
      <div class="text-xs font-semibold text-slate-200 mb-2 flex items-center gap-1.5"><i data-lucide="hard-drive" class="w-3.5 h-3.5 text-cyan-400"></i> Thiết bị của khách (${devices.length})</div>
      <div class="overflow-x-auto rounded-xl border border-slate-800">
        <table class="w-full min-w-[620px]">
          <thead><tr>
            <th class="table-th">Số sê-ri</th><th class="table-th">Sản phẩm</th><th class="table-th">Hạn bảo hành</th><th class="table-th">Tình trạng</th><th class="table-th text-right">Thao tác</th>
          </tr></thead>
          <tbody>${deviceRows}</tbody>
        </table>
      </div>
    </div>

    <div>
      <div class="text-xs font-semibold text-slate-200 mb-2 flex items-center gap-1.5"><i data-lucide="file-text" class="w-3.5 h-3.5 text-indigo-400"></i> Phiếu bảo hành của khách (${tickets.length})</div>
      <div class="overflow-x-auto rounded-xl border border-slate-800">
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
      <td class="table-td font-semibold text-slate-100">${escapeHtml(displayText(p.name))}</td>
      <td class="table-td text-slate-300">${escapeHtml(displayText(p.brand) || "–")}</td>
      <td class="table-td text-slate-300">${escapeHtml(p.category || "–")}</td>
      <td class="table-td text-emerald-300">${p.warranty_duration_months} tháng</td>
      <td class="table-td text-center font-mono text-cyan-300">${countDevicesOfProduct(p.id)}</td>
      <td class="table-td text-right whitespace-nowrap">
        ${hasPerm("product.manage") ? `<button class="btn btn-secondary btn-sm" onclick="openProductModal(${p.id})"><i data-lucide="pencil" class="w-3.5 h-3.5"></i> Sửa</button>
        <button class="btn btn-danger btn-sm ml-1" onclick="deleteProduct(${p.id})"><i data-lucide="trash-2" class="w-3.5 h-3.5"></i> Xóa</button>` : `<span class="text-[11px] text-slate-500">Chỉ xem danh mục</span>`}
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
    const recordChip = `<span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${isActive ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/40" : "bg-rose-500/15 text-rose-300 border border-rose-500/40"}">${escapeHtml(deviceStatusLabel(d.status))}</span>`;
    return `
    <tr class="table-row">
      <td class="table-td font-mono text-cyan-300">${escapeHtml(d.serial_number)}</td>
      <td class="table-td text-slate-100">${escapeHtml(displayText(d.product_name) || "–")}<br><span class="text-[11px] text-slate-500">${escapeHtml(displayText(d.product_brand) || "")}</span></td>
      <td class="table-td text-slate-300">${escapeHtml(displayText(d.customer_name) || "–")}<br><span class="text-[11px] text-slate-500 font-mono">${escapeHtml(d.customer_phone || "")}</span></td>
      <td class="table-td text-slate-400">${fmtDate(d.purchase_date)}</td>
      <td class="table-td font-mono ${expired ? "text-rose-300" : "text-emerald-300"}">${fmtDate(d.warranty_end_date)}</td>
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
    <span class="text-xs text-slate-400 ml-2">${warrantyDetail}</span>`;

  $("dev-detail-info").innerHTML = `
    <div class="p-3 bg-slate-900/70 rounded-xl border border-slate-800">
      <div class="text-slate-400 mb-1">Dòng máy</div>
      <div class="font-semibold text-slate-100">${escapeHtml(displayText(d.product_name) || "–")}</div>
      <div class="text-slate-400 mt-1">Hãng: <span class="text-slate-200">${escapeHtml(displayText(d.product_brand) || "–")}</span></div>
    </div>
    <div class="p-3 bg-slate-900/70 rounded-xl border border-slate-800">
      <div class="text-slate-400 mb-1">Chủ sở hữu</div>
      <div class="font-semibold text-slate-200">${escapeHtml(displayText(d.customer_name) || "–")}</div>
      <div class="text-slate-400 mt-1 font-mono">${escapeHtml(d.customer_phone || "")}</div>
    </div>
    <div class="p-3 bg-slate-900/70 rounded-xl border border-slate-800">
      <div class="text-slate-400 mb-1">Ngày mua</div>
      <div class="font-mono text-slate-200">${fmtDate(d.purchase_date)}</div>
    </div>
    <div class="p-3 bg-slate-900/70 rounded-xl border border-slate-800">
      <div class="text-slate-400 mb-1">Tình trạng theo dõi</div>
      <div class="text-slate-200">${escapeHtml(deviceStatusLabel(d.status))}</div>
    </div>`;

  const checkBox = $("dev-detail-check");
  checkBox.className = "hidden mb-4";
  checkBox.innerHTML = "";

  $("dev-detail-tickets").innerHTML = tickets.length
    ? tickets.map((t) => `
      <div class="flex flex-wrap items-center justify-between gap-2 p-2.5 bg-slate-900/70 rounded-xl border border-slate-800 text-xs">
        <div class="flex items-center gap-2">
          <span class="font-mono text-indigo-300">${escapeHtml(t.ticket_code)}</span>
          ${statusBadge(t.status)}
          <span class="text-slate-400">${fmtDateTime(t.created_at)}</span>
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
  box.innerHTML = '<span class="text-xs text-slate-400">Đang đối chiếu điều kiện bảo hành...</span>';
  const res = await apiFetch("/api/v1/debug/check-warranty", {
    method: "POST",
    body: { serial_number: d.serial_number, check_date: todayISO() },
  });
  if (!res.ok) {
    box.innerHTML = `<span class="text-xs text-rose-300">${escapeHtml(errorMessage(res.status, res.data))}</span>`;
    return;
  }
  const data = res.data;
  const valid = data.is_valid === true;
  const traces = Array.isArray(data.debug_traces) ? data.debug_traces : [];
  box.innerHTML = `
    <div class="p-3 rounded-xl border text-xs ${valid ? "bg-emerald-950/30 border-emerald-600/40 text-emerald-200" : "bg-rose-950/30 border-rose-600/40 text-rose-200"}">
      <div class="font-bold">${valid ? "Đủ điều kiện bảo hành" : "Không đủ điều kiện bảo hành"}</div>
      <div class="mt-1 text-[11px]">Đối chiếu ngày ${fmtDate(data.check_date)}: ${escapeHtml(humanizeText(data.status_message))}</div>
    </div>
    ${traces.length ? `
    <details class="mt-2 rounded-xl border border-slate-800 bg-black/60">
      <summary class="px-3 py-2 text-[11px] font-semibold text-slate-400">Thông tin đối chiếu chi tiết (chỉ cần khi trao đổi với bộ phận kỹ thuật)</summary>
      <div class="px-3 pb-3 font-mono text-[11px] text-slate-400 space-y-0.5">
        ${traces.map((s) => `<div>${escapeHtml(humanizeTraceStep(s))}</div>`).join("")}
      </div>
    </details>` : ""}`;
  refreshIcons();
}

/** Tiến trình xử lý phiếu (4 bước) - dùng ở modal phiếu và màn Tra cứu. */
function ticketProgressHtml(status) {
  const steps = [
    { code: "RECEIVED", label: "Tiếp nhận" },
    { code: "INSPECTING", label: "Kiểm tra" },
    { code: "REPAIRING", label: "Sửa chữa" },
    { code: "WAITING_RETURN", label: "Chờ trả máy" },
    { code: "COMPLETED", label: "Hoàn tất" },
  ];
  if (status === "REJECTED") {
    const idx = 1;
    return `<div class="flex flex-wrap items-center gap-1.5">
      ${steps.map((s, i) => `
        <span class="px-2.5 py-1 rounded-lg border ${i <= idx ? "bg-slate-800 border-slate-600 text-slate-200" : "border-slate-800 text-slate-500"}">
          ${i + 1}. ${s.label}
        </span>`).join('<i data-lucide="chevron-right" class="w-3.5 h-3.5 text-slate-600"></i>')}
      <span class="px-2.5 py-1 rounded-lg border bg-rose-950/50 border-rose-600/50 text-rose-200 font-semibold">Từ chối bảo hành</span>
    </div>`;
  }
  const currentIdx = Math.max(0, steps.findIndex((s) => s.code === status));
  return `<div class="flex flex-wrap items-center gap-1.5">
    ${steps.map((s, i) => {
      const done = i < currentIdx;
      const current = i === currentIdx;
      const cls = current
        ? "bg-indigo-600/30 border-indigo-400 text-indigo-100 font-semibold"
        : (done ? "bg-emerald-950/40 border-emerald-700/60 text-emerald-200" : "border-slate-800 text-slate-500");
      return `<span class="px-2.5 py-1 rounded-lg border ${cls}">${i + 1}. ${s.label}${current ? " (hiện tại)" : ""}</span>`;
    }).join('<i data-lucide="chevron-right" class="w-3.5 h-3.5 text-slate-600"></i>')}
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
  await loadProducts();
  await loadDashboard();
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
    : '<span class="text-[11px] text-slate-500">Chưa có thiết bị nào trong hệ thống.</span>';
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
      <div class="p-3 rounded-xl border border-amber-800/70 bg-amber-950/20 text-xs">
        <div class="font-semibold text-amber-200">Số sê-ri <span class="font-mono">${escapeHtml(serial)}</span> chưa có trong hệ thống</div>
        <p class="text-slate-400 mt-1">Điền thông tin bên dưới để đăng ký thiết bị mới, sau đó tiếp tục tạo phiếu bảo hành.</p>
      </div>`;
    if ($("wiz-purchase-date") && !$("wiz-purchase-date").value) $("wiz-purchase-date").value = todayISO();
    recalcWizardEndDate();
    wizardToggleNewDevice(true);
    refreshIcons();
    return;
  }
  if (!res.ok) {
    box.innerHTML = `<div class="p-3 rounded-xl border border-rose-800/70 bg-rose-950/20 text-xs text-rose-200">${escapeHtml(errorMessage(res.status, res.data))}</div>`;
    return;
  }

  state.wizard.device = res.data;
  box.innerHTML = wizardDeviceFoundHtml(res.data);
  refreshIcons();
}

/** Card thiết bị đã tìm thấy ở bước 1 (kèm tình trạng bảo hành để nhìn trước). */
function wizardDeviceFoundHtml(d) {
  if (!d || !d.serial_number) return "";
  const w = warrantyInfoFor(d.warranty_end_date);
  const note = w.days !== null && w.days < 0
    ? `<div class="p-3 rounded-xl border border-rose-800/70 bg-rose-950/20 text-xs text-rose-200 mt-2">
         Thiết bị đã hết hạn bảo hành (hạn ${fmtDate(d.warranty_end_date)}). Vẫn tạo được phiếu nhưng phiếu sẽ được xử lý như trường hợp ngoài bảo hành.
       </div>`
    : "";
  return `
    <div class="p-3 rounded-xl border border-emerald-800/60 bg-emerald-950/20">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="text-xs">
          <div class="font-semibold text-emerald-100">Đã tìm thấy thiết bị <span class="font-mono">${escapeHtml(d.serial_number)}</span></div>
          <div class="text-slate-300 mt-1">
            ${escapeHtml(displayText(d.product_name) || "–")}
            &bull; Khách hàng: ${escapeHtml(displayText(d.customer_name) || "–")}
            ${d.customer_phone ? `&bull; <span class="font-mono">${escapeHtml(d.customer_phone)}</span>` : ""}
            &bull; ${warrantyStatusHtml(d.warranty_end_date)}
          </div>
        </div>
        <div class="flex flex-wrap gap-2">
          <button type="button" class="btn btn-secondary btn-sm" onclick="openDeviceDetailModal(${d.id})"><i data-lucide="info" class="w-3.5 h-3.5"></i> Xem chi tiết</button>
          <button type="button" class="btn btn-primary btn-sm" onclick="wizardGoToStep2()"><i data-lucide="arrow-right" class="w-3.5 h-3.5"></i> Tiếp tục bước 2</button>
        </div>
      </div>
    </div>${note}`;
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
  const openStatuses = ["RECEIVED", "INSPECTING", "REPAIRING", "WAITING_RETURN"];
  const open = state.tickets.find((t) => t.serial_number === d.serial_number && openStatuses.includes(t.status));
  if (!open) return "";
  return `
    <div class="p-3 rounded-xl border border-amber-700/60 bg-amber-950/30 text-xs sm:col-span-2 lg:col-span-4">
      <div class="font-semibold text-amber-200">Thiết bị này đang có phiếu chưa kết thúc</div>
      <p class="text-slate-300 mt-1">
        Phiếu <strong class="font-mono">${escapeHtml(open.ticket_code)}</strong> (${escapeHtml(statusLabel(open.status))}) vẫn đang được xử lý.
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
    <div class="p-3 bg-slate-900/70 rounded-xl border border-slate-800">
      <div class="text-slate-400 mb-1">${label}</div>
      <div class="font-semibold text-slate-100">${value}</div>
    </div>`;
  return [
    cell("Thiết bị", `${escapeHtml(displayText(d.product_name) || "–")}<div class="font-mono text-cyan-300 text-[11px] mt-0.5">${escapeHtml(d.serial_number)}</div>`),
    cell("Khách hàng", `${escapeHtml(displayText(d.customer_name) || "–")}<div class="font-mono text-slate-400 text-[11px] mt-0.5">${escapeHtml(d.customer_phone || "")}</div>`),
    cell("Ngày mua", `<span class="font-mono">${fmtDate(d.purchase_date)}</span>`),
    cell("Tình trạng bảo hành", warrantyStatusHtml(d.warranty_end_date)),
  ].join("");
}

function wizardBackToStep1() {
  wizardShowStep(1);
}

/** BƯỚC 2 (hoàn tất): tạo phiếu bảo hành cho thiết bị đã chọn ở bước 1. */
async function wizardSubmitTicket() {
  const d = state.wizard.device;
  if (!d) {
    showToast("Thiếu thông tin thiết bị, hãy chọn lại ở bước 1.", "warning");
    wizardShowStep(1);
    return;
  }
  const description = ($("wiz-desc").value || "").trim();
  const createdBy = parseInt($("wiz-created-by").value, 10);
  const categoryRaw = $("wiz-category-select").value;

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
  };
  // Chỉ gửi nhãn lỗi khi nhân viên chủ động chọn; mặc định để trống cho luồng AI gợi ý.
  if (categoryRaw) payload.error_category_id = parseInt(categoryRaw, 10);

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
}

/* --------------------------- DANH SÁCH PHIẾU --------------------------- */
let ticketStatusFilter = "ALL";
/** Bộ lọc "Phiếu của tôi": true = chỉ lấy phiếu mà tài khoản hiện tại là người xử lý gần nhất. */
let ticketOnlyMine = false;

async function loadTickets(statusFilter = null) {
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
  if (!res.ok) {
    setTableMessage("tickets-table-body", 8, "Không tải được danh sách phiếu bảo hành.");
    toastError(res, "Không tải được danh sách phiếu bảo hành.");
    return;
  }
  state.tickets = Array.isArray(res.data) ? res.data : [];
  renderTickets(state.tickets);
  populateAiTicketSelect();
  updateMyTicketFilterButton();
}

/** Từ khoá đang nhập ở ô tìm kiếm của danh sách phiếu (rỗng nếu chưa nhập). */
function ticketSearchKeyword() {
  const box = $("ticket-search-input");
  return box ? (box.value || "").trim() : "";
}

/** Bật/tắt bộ lọc "Phiếu của tôi" (việc do chính nhân viên đang đăng nhập phụ trách). */
function toggleMyTickets() {
  ticketOnlyMine = !ticketOnlyMine;
  updateMyTicketFilterButton();
  showToast(
    ticketOnlyMine
      ? "Đang xem các phiếu bạn đang phụ trách."
      : "Đang xem phiếu của toàn bộ trung tâm.",
    "info",
    2500
  );
  loadTickets();
}

/** Đổi màu nút "Phiếu của tôi" để nhân viên biết bộ lọc đang bật. */
function updateMyTicketFilterButton() {
  const btn = $("ticket-my-filter");
  if (!btn) return;
  btn.classList.toggle("btn-primary", ticketOnlyMine);
  btn.classList.toggle("btn-secondary", !ticketOnlyMine);
}

/** Phiếu đang xử lý (chưa kết thúc) luôn được ưu tiên hiển thị trước. */
function sortTicketsForWork(items) {
  const order = { RECEIVED: 0, INSPECTING: 1, REPAIRING: 2, WAITING_RETURN: 3, COMPLETED: 4, REJECTED: 5 };
  return items.slice().sort((a, b) => {
    const oa = order[a.status] === undefined ? 9 : order[a.status];
    const ob = order[b.status] === undefined ? 9 : order[b.status];
    if (oa !== ob) return oa - ob;
    return b.id - a.id;
  });
}

/** Nhân viên phụ trách = người thực hiện ở bước xử lý gần nhất (backend đã tính sẵn). */
function ticketHandlerName(t) {
  if (t && t.handler_name) return displayText(t.handler_name);
  const history = Array.isArray(t.status_history) ? t.status_history : [];
  const last = history.length ? history[history.length - 1] : null;
  const userId = last ? last.changed_by : t.created_by;
  return userName(userId);
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
 * Danh sách phiếu: mỗi dòng có ĐÚNG MỘT hành động chính theo trạng thái + quyền
 * (nhãn và loại hành động do backend trả về), các bước phụ nằm trong menu "Thêm".
 */
function renderTickets(tickets) {
  const tbody = $("tickets-table-body");
  if (!tbody) return;
  if (!tickets.length) {
    setTableMessage(
      "tickets-table-body",
      8,
      ticketOnlyMine
        ? "Bạn hiện không có phiếu nào đang phụ trách. Bấm \"Phiếu của tôi\" lần nữa để xem toàn bộ."
        : "Chưa có phiếu bảo hành nào phù hợp."
    );
    return;
  }
  tbody.innerHTML = sortTicketsForWork(tickets).map((t) => {
    const isTransition = t.action_kind === "transition" && t.primary_action;
    const target = isTransition ? t.primary_action.target : null;
    return `<tr class="table-row">
      <td class="table-td font-mono font-semibold text-indigo-300">${escapeHtml(t.ticket_code)}</td>
      <td class="table-td font-mono text-cyan-300">${escapeHtml(t.serial_number || "–")}<br><span class="text-[11px] text-slate-500">${escapeHtml(displayText(t.product_name) || "")}</span></td>
      <td class="table-td text-slate-200">${escapeHtml(displayText(t.customer_name) || "–")}
        <br><span class="text-[11px] text-slate-500 font-mono">${escapeHtml(t.customer_phone || "")}</span></td>
      <td class="table-td">${statusBadge(t.status)}</td>
      <td class="table-td text-slate-400">${fmtDateTime(t.created_at)}</td>
      <td class="table-td text-slate-300 text-xs">${escapeHtml(ticketHandlerName(t))}</td>
      <td class="table-td text-slate-400">${escapeHtml(t.error_category_name || categoryName(t.error_category_id))}</td>
      <td class="table-td text-right">
        <div class="flex flex-col items-end gap-1">
          <button class="btn ${isTransition ? "btn-primary" : "btn-secondary"} btn-sm"
                  onclick="handleTicketAction(${t.id}, ${target ? `'${target}'` : "null"})">
            <i data-lucide="${isTransition ? "arrow-right-circle" : "eye"}" class="w-3.5 h-3.5"></i> ${escapeHtml(t.action_label || "Xem phiếu")}
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
        { step: 4, status: "WAITING_RETURN", label: "Chờ trả máy", state: "pending" },
        { step: 5, status: "COMPLETED", label: "Hoàn tất", state: "pending" },
      ];
  const chips = steps.map((step) => {
    const cls = step.state === "current"
      ? "bg-indigo-600/30 border-indigo-400 text-indigo-100 font-semibold"
      : (step.state === "done"
        ? "bg-emerald-950/40 border-emerald-700/60 text-emerald-200"
        : "border-slate-800 text-slate-500");
    const who = step.by_name ? ` – ${displayText(step.by_name)}` : "";
    const when = step.at ? ` (${fmtDateTime(step.at)})` : "";
    return `<span class="px-2.5 py-1 rounded-lg border ${cls}" title="${escapeHtml(who + when)}">${step.step}. ${escapeHtml(step.label)}${step.state === "current" ? " (đang ở đây)" : ""}</span>`;
  });
  const rejected = t.status === "REJECTED"
    ? '<span class="px-2.5 py-1 rounded-lg border bg-rose-950/50 border-rose-600/50 text-rose-200 font-semibold">Từ chối bảo hành</span>'
    : "";
  return chips.join('<i data-lucide="chevron-right" class="w-3.5 h-3.5 text-slate-600"></i>') + rejected;
}

/** Danh sách điều kiện hoàn tất (đủ/chưa đủ) - do backend trả về. */
function renderCompletionChecklist(t) {
  const list = $("ws-completion-list");
  if (!list) return;
  const checks = Array.isArray(t.completion_checklist) ? t.completion_checklist : [];
  list.innerHTML = checks
    .map((item) => `<div class="flex items-start gap-1.5 ${item.satisfied ? "text-emerald-300" : "text-slate-400"}">
        <span>${item.satisfied ? "✔" : "○"}</span><span>${escapeHtml(item.label)}</span>
      </div>`)
    .join("");
  const blockers = Array.isArray(t.completion_blockers) ? t.completion_blockers : [];
  const box = $("ws-completion-blockers");
  if (box) {
    box.innerHTML = blockers.length
      ? '<div class="font-semibold mb-0.5">Chưa thể hoàn tất:</div>' +
        blockers.map((text) => `<div>• ${escapeHtml(text)}</div>`).join("")
      : (t.status === "WAITING_RETURN" ? "Đủ điều kiện để xác nhận đã trả máy và hoàn tất phiếu." : "");
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
    const actor = h.changed_by_name ? displayText(h.changed_by_name) : userName(h.changed_by);
    return `
    <div class="flex items-start gap-3">
      <div class="w-6 h-6 rounded-full bg-indigo-600/30 border border-indigo-400 text-indigo-200 flex items-center justify-center text-[11px] font-bold shrink-0">${idx + 1}</div>
      <div class="flex-1 text-xs">
        <div class="font-semibold text-slate-100 flex items-center justify-between gap-2">
          <span>${escapeHtml(fromLabel ? fromLabel + " → " : "")}${escapeHtml(toLabel)}</span>
          <span class="text-slate-500 font-mono">${fmtDateTime(h.created_at)}</span>
        </div>
        <div class="text-slate-400 mt-0.5">${escapeHtml(humanizeText(h.note) || "Không có ghi chú")}</div>
        <div class="text-slate-500 mt-0.5">Người thực hiện: ${escapeHtml(actor)}</div>
      </div>
    </div>`;
  }).join("");
}

/** Vẽ màn hình phiếu: khối A-G + nút hành động + điều kiện hoàn tất. */
function renderTicketWorkspace(t) {
  const customer = t.customer || {};
  const device = t.device || {};
  const intake = t.intake || {};
  const diagnosis = t.diagnosis || {};
  const repair = t.repair || {};
  const handover = t.handover || {};

  $("modal-ticket-code").textContent = t.ticket_code || "–";
  const badge = $("modal-ticket-badge");
  badge.className = `px-3 py-1 text-xs font-semibold rounded-full badge-${String(t.status).toLowerCase()}`;
  badge.textContent = t.status_label || statusLabel(t.status);
  $("modal-status-hint").textContent = t.status_hint || "";
  const handlerChip = $("modal-handler-chip");
  if (handlerChip) handlerChip.textContent = `Nhân viên phụ trách: ${t.handler_name || userName(t.created_by)}`;
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
    ? `<span class="font-semibold ${device.warranty_status === "Đã hết hạn" ? "text-rose-300" : "text-emerald-300"}">${escapeHtml(device.warranty_status)}</span>
       <span class="text-slate-400"> – ${escapeHtml(device.warranty_status_message)}</span>`
    : warrantyStatusHtml(t.warranty_end_date);

  // C. Tiếp nhận (mô tả của KHÁCH HÀNG - không trộn với kết luận của kỹ thuật viên)
  $("modal-ticket-created").textContent = fmtDateTime(intake.received_at || t.created_at);
  $("modal-created-by").textContent = intake.received_by_name || userName(t.created_by);
  $("modal-ticket-desc").textContent =
    humanizeText(intake.issue_description || t.issue_description) ||
    "Khách hàng chưa cung cấp mô tả tình trạng lỗi.";
  // Khối "Hỗ trợ chẩn đoán": 3 phần tách biệt (khách mô tả / hệ thống gợi ý / kỹ thuật viên kết luận)
  renderDiagnosisSupport(t);

  // D. Chẩn đoán - kết luận của kỹ thuật viên (AI chỉ gợi ý, ở khối riêng)
  renderDiagnosisSection(t);
  // E. Sửa chữa
  renderRepairSection(t);
  // F. Trả máy
  renderHandoverSection(t);

  // Điều kiện hoàn tất + lý do từ chối (nếu có)
  renderCompletionChecklist(t);
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

/**
 * Khối "Hỗ trợ chẩn đoán": 3 phần TÁCH BIỆT theo đúng nghiệp vụ
 *   1. Khách hàng mô tả (dữ liệu tiếp nhận)
 *   2. Hệ thống gợi ý loại lỗi (chỉ tham khảo, không phải kết luận)
 *   3. Kết luận của kỹ thuật viên (người có quyền xác nhận)
 * Không gọi gợi ý của hệ thống là "kết luận" và không tự ghi vào phiếu.
 */
function renderDiagnosisSupport(t) {
  const customerBox = $("ws-support-customer");
  if (customerBox) {
    customerBox.textContent =
      humanizeText((t.intake && t.intake.issue_description) || t.issue_description) ||
      "Khách hàng chưa cung cấp mô tả tình trạng lỗi.";
  }

  const aiBox = $("ws-support-ai");
  if (aiBox) {
    const ai = t.ai_suggestion || {};
    if (!ai.available) {
      aiBox.innerHTML = '<span class="text-slate-400">Chưa có gợi ý cho phiếu này.</span>';
    } else {
      const label = ai.suggested_category_name
        ? displayText(ai.suggested_category_name)
        : "chưa đủ thông tin để gợi ý";
      const conf = ai.confidence !== null && ai.confidence !== undefined
        ? ` (mức độ chắc chắn ${confidencePercent(ai.confidence)})`
        : "";
      aiBox.innerHTML = `<span class="font-semibold text-fuchsia-200">${escapeHtml(label)}</span>${escapeHtml(conf)}
        <div class="text-[11px] text-slate-500 mt-1">Chỉ là gợi ý để tham khảo, không phải kết luận của phiếu.</div>`;
    }
  }

  const conclusionBox = $("ws-support-conclusion");
  if (conclusionBox) {
    const diagnosis = t.diagnosis || {};
    const lines = [];
    if (diagnosis.error_category_name) {
      lines.push(`Loại lỗi: <span class="font-semibold text-slate-100">${escapeHtml(displayText(diagnosis.error_category_name))}</span>`);
    }
    if (diagnosis.note) {
      lines.push(escapeHtml(humanizeText(diagnosis.note)));
    }
    if (diagnosis.confirmed_by_name) {
      lines.push(`<span class="text-[11px] text-slate-500">Ghi nhận bởi ${escapeHtml(displayText(diagnosis.confirmed_by_name))}${diagnosis.confirmed_at ? " • " + fmtDateTime(diagnosis.confirmed_at) : ""}</span>`);
    }
    conclusionBox.innerHTML = lines.length
      ? lines.join("<br>")
      : '<span class="text-slate-400">Kỹ thuật viên chưa ghi kết luận cho phiếu này.</span>';
  }
}

/** D. Khối chẩn đoán: kết luận của kỹ thuật viên (KHÁC với gợi ý của AI). */
function renderDiagnosisSection(t) {
  const diagnosis = t.diagnosis || {};
  const meta = [];
  if (diagnosis.error_category_name) {
    meta.push(`Loại lỗi: <strong class="text-slate-200">${escapeHtml(diagnosis.error_category_name)}</strong>`);
  }
  if (diagnosis.confirmed_by_name) {
    meta.push(`Người xác nhận: <span class="text-slate-300">${escapeHtml(displayText(diagnosis.confirmed_by_name))}</span>`);
  }
  if (diagnosis.confirmed_at) {
    meta.push(`Thời điểm: <span class="font-mono text-slate-300">${fmtDateTime(diagnosis.confirmed_at)}</span>`);
  }
  $("ws-diagnosis-body").innerHTML = humanizeText(diagnosis.note)
    ? escapeHtml(humanizeText(diagnosis.note))
    : '<span class="text-amber-300/90">Chưa có kết luận chẩn đoán. Kỹ thuật viên cần kiểm tra máy và ghi nhận.</span>';
  $("ws-diagnosis-meta").innerHTML = meta.join(" &bull; ");
  const btn = $("btn-edit-diagnosis");
  if (btn) btn.classList.toggle("hidden", !t.can_edit_diagnosis);
}

/** E. Khối sửa chữa: nội dung đã kiểm tra/đã sửa, linh kiện thay thế, nhật ký sửa chữa. */
function renderRepairSection(t) {
  const repair = t.repair || {};
  $("ws-repair-body").innerHTML = humanizeText(repair.content)
    ? escapeHtml(humanizeText(repair.content))
    : '<span class="text-slate-400">Chưa ghi nhận nội dung đã kiểm tra / đã sửa chữa.</span>';

  const meta = [];
  if (repair.technician_name) meta.push(`Người thực hiện: ${escapeHtml(displayText(repair.technician_name))}`);
  if (repair.recorded_at) meta.push(`Thời điểm: <span class="font-mono">${fmtDateTime(repair.recorded_at)}</span>`);
  if (repair.note) meta.push(`Ghi chú: ${escapeHtml(humanizeText(repair.note))}`);
  $("ws-repair-parts").innerHTML =
    (repair.parts
      ? `Linh kiện/thành phần thay thế: <span class="text-slate-200">${escapeHtml(humanizeText(repair.parts))}</span><br>`
      : "") + meta.join(" &bull; ");

  const logs = Array.isArray(repair.logs) ? repair.logs : [];
  $("ws-repair-logs").innerHTML = logs.length
    ? `<div class="text-[11px] text-slate-500 mb-0.5">Nhật ký sửa chữa (${logs.length} lần):</div>` +
      logs.map((log) => `<div class="text-[11px] text-slate-400">• <span class="font-mono">${fmtDateTime(log.logged_at)}</span>
        – ${escapeHtml(displayText(log.technician_name) || "")}: ${escapeHtml(humanizeText(log.action_description) || "")}
        ${log.parts_used ? `<span class="text-slate-500">(linh kiện: ${escapeHtml(humanizeText(log.parts_used))})</span>` : ""}</div>`).join("")
    : "";

  const btn = $("btn-edit-repair");
  if (btn) btn.classList.toggle("hidden", !t.can_edit_repair);
}

/** F. Khối trả máy: nổi bật khi máy đang "Chờ trả máy" để nhân viên biết cần bàn giao. */
function renderHandoverSection(t) {
  const handover = t.handover || {};
  const box = $("ws-handover-box");
  const isWaiting = !!handover.is_waiting_return || t.status === "WAITING_RETURN";
  box.className = "p-3 rounded-xl border " + (
    isWaiting
      ? "border-cyan-600/50 bg-cyan-950/30"
      : (t.status === "COMPLETED" ? "border-emerald-700/50 bg-emerald-950/20" : "border-slate-800 bg-slate-900/70")
  );

  const lines = [
    `<div class="font-semibold ${isWaiting ? "text-cyan-200" : "text-slate-200"}">${escapeHtml(handover.status_message || statusLabel(t.status))}</div>`,
  ];
  if (handover.repair_completed_at) {
    lines.push(`<div class="text-slate-400 mt-1">Hoàn thành sửa chữa: <span class="font-mono text-slate-200">${fmtDateTime(handover.repair_completed_at)}</span>${
      handover.repair_completed_by_name
        ? ` – <span class="text-slate-200">${escapeHtml(displayText(handover.repair_completed_by_name))}</span>`
        : ""}</div>`);
  }
  if (t.handed_over_at) {
    lines.push(`<div class="text-slate-400 mt-1">Đã trả máy lúc: <span class="font-mono text-slate-200">${fmtDateTime(t.handed_over_at)}</span>${
      handover.returned_by_name
        ? ` – <span class="text-slate-200">${escapeHtml(displayText(handover.returned_by_name))}</span>`
        : ""}</div>`);
  }
  if (handover.note) {
    lines.push(`<div class="text-slate-400 mt-1">Ghi chú bàn giao: <span class="text-slate-200">${escapeHtml(humanizeText(handover.note))}</span></div>`);
  }
  $("ws-handover-body").innerHTML = lines.join("");
}

/** Nút chuyển trạng thái: CHỈ hiện những hành động mà BACKEND cho phép vai trò hiện tại. */
function renderStateActions(t) {
  const box = $("modal-state-actions");
  if (!box) return;
  const notesBox = $("modal-permission-notes");
  const actions = Array.isArray(t.available_actions) ? t.available_actions : [];
  const notes = Array.isArray(t.permission_notes) ? t.permission_notes : [];

  if (notesBox) {
    notesBox.innerHTML = notes.map((text) => `<div>• ${escapeHtml(humanizeText(text))}</div>`).join("");
  }

  if (!actions.length) {
    const done = t.status === "COMPLETED" || t.status === "REJECTED";
    box.innerHTML = done
      ? `<div class="text-xs text-slate-400">Phiếu đã ở trạng thái kết thúc (${escapeHtml(t.status_label || statusLabel(t.status))}), không thể chuyển thêm.</div>`
      : '<div class="text-xs text-slate-400">Vai trò hiện tại không có thao tác nào phù hợp với bước này. Xem ghi chú bên dưới để biết việc này của ai.</div>';
    return;
  }
  box.innerHTML = actions
    .map((action) => `<button class="btn btn-${escapeHtml(action.style || "primary")}" onclick="startTransition('${action.target}')">
        <i data-lucide="arrow-right-circle" class="w-4 h-4"></i> ${escapeHtml(action.button_label)}</button>`)
    .join("");
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
  const staff = staffSelectOptions("TECHNICIAN");
  const fieldSpecs = Array.isArray(action.fields) ? action.fields : [];
  const categories = categorySelectOptions(t.error_category_id);
  const fields = [];

  if (fieldSpecs.includes("diagnosis_note")) {
    fields.push({
      id: "diagnosis_note",
      label: "Kết luận chẩn đoán của kỹ thuật viên",
      placeholder: "Ví dụ: IC nguồn bị chập, tụ lọc nguồn phồng",
      defaultValue: t.diagnosis && t.diagnosis.note ? t.diagnosis.note : "",
      required: true,
      hint: "Đây là kết luận của người kiểm tra, KHÔNG phải gợi ý của hệ thống.",
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
  if (fieldSpecs.includes("repair_content")) {
    fields.push({
      id: "repair_content",
      label: "Nội dung đã kiểm tra / đã sửa chữa",
      placeholder: "Ví dụ: Thay IC nguồn, vệ sinh tản nhiệt, chạy thử 2 giờ",
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
  if (fieldSpecs.includes("repair_note")) {
    fields.push({
      id: "repair_note",
      label: "Ghi chú kỹ thuật (không bắt buộc)",
      placeholder: "Ví dụ: Máy chạy ổn định sau 2 giờ chạy thử",
      defaultValue: "",
    });
  }
  if (fieldSpecs.includes("handover_note")) {
    fields.push({
      id: "handover_note",
      label: "Thông tin bàn giao cho khách",
      placeholder: "Ví dụ: Khách đã kiểm tra máy và nhận lại kèm phiếu bảo hành",
      defaultValue: t.handover && t.handover.note ? t.handover.note : "",
      required: true,
    });
  }
  if (fieldSpecs.includes("rejection_reason")) {
    fields.push({
      id: "rejection_reason",
      label: "Lý do từ chối bảo hành",
      placeholder: "Ví dụ: Thiết bị vào nước, không thuộc phạm vi bảo hành",
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
  ["diagnosis_note", "repair_content", "repair_parts", "repair_note", "handover_note", "rejection_reason"].forEach((key) => {
    if (values[key]) payload[key] = values[key];
  });
  if (values.error_category_id) payload.error_category_id = parseInt(values.error_category_id, 10);

  const res = await apiFetch(`/api/v1/warranty-tickets/${ticketId}/status`, { method: "PATCH", body: payload });
  if (!res.ok) {
    toastError(res, "Không chuyển được trạng thái phiếu.");
    return;
  }
  showToast(`Đã chuyển phiếu sang trạng thái "${(action && action.target_label) || statusLabel(targetStatus)}".`, "success");
  await openTicketModal(ticketId);
  await loadTickets();
  await loadDashboard();
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
  if (!state.tickets.length) {
    sel.innerHTML = '<option value="">-- Chưa có phiếu bảo hành nào --</option>';
    return;
  }
  const current = sel.value;
  sel.innerHTML = state.tickets.map((t) => {
    const label = `${t.ticket_code} – ${t.serial_number || "không rõ số sê-ri"} (${statusLabel(t.status)})` +
      (t.error_category_id ? " – đã có loại lỗi" : " – chưa xác định loại lỗi");
    return `<option value="${t.id}">${escapeHtml(label)}</option>`;
  }).join("");
  if (current && state.tickets.some((t) => String(t.id) === current)) {
    sel.value = current;
  } else {
    const firstUnlabeled = state.tickets.find((t) => !t.error_category_id);
    sel.value = String((firstUnlabeled || state.tickets[0]).id);
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
  if (value > 0.7) return "text-emerald-300";
  if (value > 0.4) return "text-amber-300";
  return "text-rose-300";
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
  const currentLine = `<div class="pb-2 mb-2 border-b border-slate-800">
      Loại lỗi đã ghi trên phiếu: <strong class="${hasLabel ? "text-emerald-300" : "text-amber-300"}">${escapeHtml(ticket ? categoryName(ticket.error_category_id) : "–")}</strong>
      <span class="text-slate-500">(chỉ được ghi sau khi nhân viên xác nhận)</span>
    </div>`;

  const r = state.currentAiResult;
  if (!r) {
    box.innerHTML = currentLine + '<div class="text-slate-400">Chưa có kết quả gợi ý cho phiếu này. Bấm "Gợi ý loại lỗi" để hệ thống đọc mô tả sự cố của khách.</div>';
    return;
  }

  const needMore = r.need_more_information || [];
  const needMoreHtml = needMore.length
    ? `<div class="mt-2 p-2 rounded-lg bg-amber-950/30 border border-amber-800/40 text-amber-100">
         <div class="font-semibold mb-1">Nên hỏi thêm khách hàng để xác định chính xác hơn:</div>
         <ul class="list-disc ml-4 space-y-0.5">${needMore.map((q) => `<li>${escapeHtml(humanizeText(q))}</li>`).join("")}</ul>
       </div>`
    : "";

  const statusClass = r.review_status === "APPROVED"
    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
    : (r.review_status === "REJECTED"
      ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
      : "bg-slate-800 text-slate-300 border border-slate-700");

  const footerNote = r.review_status === "PENDING"
    ? "Kết quả này chỉ là gợi ý. Chọn người xác nhận rồi bấm Xác nhận / Không dùng gợi ý."
    : "Kết quả đã được xác nhận, không thể xác nhận lại.";

  const canUseLabel = aiLabelIsUsable(r);
  const warning = (r.suggested_category_id !== null && r.suggested_category_id !== undefined && !canUseLabel)
    ? '<div class="text-[11px] text-amber-300/90 mt-1">Kết quả gợi ý này không khớp danh mục loại lỗi nên hệ thống không ghi vào phiếu. Hãy bấm <strong>Gợi ý loại lỗi</strong> lại sau khi bổ sung mô tả lỗi.</div>'
    : "";

  box.innerHTML = currentLine +
    `<div class="flex flex-wrap items-center gap-2">
       <span class="text-slate-400">Loại lỗi được gợi ý:</span>
       <strong class="${canUseLabel ? "text-fuchsia-300" : "text-amber-300"}">${escapeHtml(aiSuggestionText(r))}</strong>
       <span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${statusClass}">${escapeHtml(reviewLabel(r.review_status))}</span>
     </div>
     <div class="text-slate-400">Mức độ chắc chắn: <strong class="font-mono ${confidenceColor(r.confidence)}">${confidencePercent(r.confidence)}</strong>
       &bull; Thời điểm gợi ý: <span class="font-mono text-slate-300">${fmtDateTime(r.created_at)}</span></div>
     <div class="text-slate-300"><span class="text-slate-400">Giải thích:</span> ${escapeHtml(aiReasonText(r))}</div>
     ${warning}
     ${needMoreHtml}
     <div class="text-[11px] text-slate-500 mt-1">${footerNote}</div>`;
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
    const labelCls = aiLabelIsUsable(n) ? "text-fuchsia-300" : "text-amber-300";
    return `
    <tr class="table-row">
      <td class="table-td text-slate-400 font-mono">${fmtDateTime(n.created_at)}</td>
      <td class="table-td ${labelCls}">${escapeHtml(aiSuggestionText(n))}</td>
      <td class="table-td font-mono">${confidencePercent(n.confidence)}</td>
      <td class="table-td">${escapeHtml(reviewLabel(n.review_status))}</td>
      <td class="table-td text-slate-400">${rec.reviewed_by ? escapeHtml(userName(rec.reviewed_by)) : "–"}</td>
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
    showToast(`Đã gợi ý xong. Loại lỗi được gợi ý: <strong>${escapeHtml(label)}</strong> (mức độ chắc chắn ${confidencePercent(state.currentAiResult.confidence)}) – đang chờ nhân viên xác nhận.`, "success", 8000);
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
    showToast("Chỉ nhân viên tiếp nhận hoặc quản lý được xác nhận gợi ý loại lỗi.", "warning");
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
      summary.className = "px-2.5 py-1 text-[11px] rounded-full border border-slate-700 text-slate-400";
      summary.textContent = "Chưa có gợi ý loại lỗi";
    } else if (latest.review_status === "APPROVED") {
      summary.className = "px-2.5 py-1 text-[11px] rounded-full border border-emerald-600/50 bg-emerald-950/40 text-emerald-200";
      summary.textContent = "Đã xác nhận loại lỗi";
    } else if (latest.review_status === "REJECTED") {
      summary.className = "px-2.5 py-1 text-[11px] rounded-full border border-rose-600/50 bg-rose-950/40 text-rose-200";
      summary.textContent = "Không dùng gợi ý của hệ thống";
    } else {
      summary.className = "px-2.5 py-1 text-[11px] rounded-full border border-amber-600/50 bg-amber-950/40 text-amber-200";
      summary.textContent = "Gợi ý loại lỗi: chờ xác nhận";
    }
  }

  let html = `<div class="mb-2">Loại lỗi đã ghi trên phiếu: <strong class="${t.error_category_id ? "text-emerald-300" : "text-amber-300"}">${escapeHtml(categoryName(t.error_category_id))}</strong></div>`;
  if (!latest) {
    html += `<div class="text-slate-400 mb-2">Chưa có kết quả gợi ý cho phiếu này.</div>`;
  } else {
    const statusCls = latest.review_status === "APPROVED" ? "text-emerald-300" : (latest.review_status === "REJECTED" ? "text-rose-300" : "text-amber-300");
    const labelCls = aiLabelIsUsable(latest) ? "text-fuchsia-300" : "text-amber-300";
    html += `<div class="mb-1">Loại lỗi được gợi ý: <strong class="${labelCls}">${escapeHtml(aiSuggestionText(latest))}</strong>
        &bull; Mức độ chắc chắn: <span class="font-mono ${confidenceColor(latest.confidence)}">${confidencePercent(latest.confidence)}</span></div>
      <div class="text-slate-400">Trạng thái xác nhận: <strong class="${statusCls}">${escapeHtml(reviewLabel(latest.review_status))}</strong>
        &bull; Thời điểm: <span class="font-mono">${fmtDateTime(latest.created_at)}</span></div>
      <div class="text-slate-400 mt-1">Số lần đã gợi ý: <span class="font-mono text-slate-200">${items.length}</span></div>`;
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
    html += `<div class="text-[11px] text-slate-400 mt-3">Vai trò hiện tại chỉ xem được gợi ý loại lỗi; việc xác nhận do nhân viên tiếp nhận hoặc quản lý thực hiện.</div>`;
  }
  html += `
    <div class="flex flex-wrap gap-2 mt-2">
      ${canClassifyAi ? `<button class="btn btn-primary btn-sm" onclick="classifyCurrentTicket()"><i data-lucide="wand-2" class="w-3.5 h-3.5"></i> Gợi ý loại lỗi cho phiếu này</button>` : ""}
      <button class="btn btn-secondary btn-sm" onclick="goToAiTab()"><i data-lucide="arrow-up-right" class="w-3.5 h-3.5"></i> Xem đầy đủ ở màn hình xác định lỗi</button>
    </div>
    ${canReviewAi && !canConfirm ? '<div class="text-[11px] text-amber-300/90 mt-2">Hai nút <strong>Xác nhận</strong> / <strong>Không dùng</strong> chỉ bật khi phiếu có kết quả gợi ý đang chờ duyệt — hãy bấm <strong>Gợi ý loại lỗi cho phiếu này</strong> trước.</div>' : ""}`;
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
    showToast("Chỉ nhân viên tiếp nhận hoặc quản lý được xác nhận gợi ý loại lỗi.", "warning");
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
  const res = await apiFetch(`/api/v1/ai/tickets/${t.id}/classify-error`, { method: "POST" });
  if (!res.ok) {
    toastError(res, "Không gợi ý được loại lỗi cho phiếu này.");
    return;
  }
  const label = aiSuggestionText(normalizeFreshAiResult(res.data));
  showToast(`Đã gợi ý xong. Loại lỗi được gợi ý: <strong>${escapeHtml(label)}</strong> (mức độ chắc chắn ${confidencePercent(res.data.confidence)}).`, "success", 8000);
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

function isManager() {
  return !!state.session.user && state.session.user.role === "MANAGER";
}

/** Ẩn/hiện mọi phần tử có khai báo `data-perm` theo quyền của vai trò đang đăng nhập. */
function applyPermissions() {
  document.querySelectorAll("[data-perm]").forEach((el) => {
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
function toggleNavMore() {
  const panel = $("nav-more-panel");
  if (!panel) return;
  panel.classList.toggle("hidden");
}

function closeNavMore() {
  const panel = $("nav-more-panel");
  if (panel) panel.classList.add("hidden");
}

/** Vẽ menu theo vai trò; nhóm "reference" được gom vào menu phụ "Tra cứu nội bộ". */
function renderNavigation(menus) {
  const list = Array.isArray(menus) ? menus : [];
  const moreWrap = $("nav-more");
  const morePanel = $("nav-more-panel");
  const allowedTabs = list.map((menu) => menu.tab);

  // 1. Mục menu không thuộc vai trò này -> ẩn (danh sách đã được backend lọc theo quyền)
  document.querySelectorAll(".nav-tab-btn").forEach((btn) => {
    const tab = btn.getAttribute("data-tab");
    if (!tab) return; // nút "Tra cứu nội bộ" không gắn với màn hình nào
    btn.classList.toggle("hidden", allowedTabs.indexOf(tab) === -1);
  });

  if (!moreWrap || !morePanel) return;
  morePanel.innerHTML = "";
  const reference = list.filter((menu) => menu.group === "reference");
  moreWrap.classList.toggle("hidden", reference.length === 0);

  // 2. Mục nhóm "reference" -> chuyển vào menu phụ (vẫn dùng đúng nút gốc nên giữ nguyên sự kiện)
  reference.forEach((menu) => {
    const btn = document.querySelector(`nav .nav-tab-btn[data-tab="${menu.tab}"]`);
    if (!btn) return;
    btn.classList.remove("hidden");
    btn.setAttribute("title", menu.hint || menu.label);
    morePanel.appendChild(btn);
  });

  // 3. Màn hình nhỏ: chèn nhãn nhóm trước mục tra cứu nội bộ để nhân viên biết đây là nhóm phụ
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

/** Tab mặc định nên mở: tab đầu tiên mà vai trò hiện tại được phép xem. */
function firstAllowedTab() {
  const order = ["dashboard", "tickets", "lookup", "ai", "customers", "products", "devices", "accounts"];
  return order.find((tab) => hasPerm(TAB_PERMISSIONS[tab])) || "dashboard";
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
  } else if (chip) {
    chip.style.display = "none";
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
  return user.role === "MANAGER" || user.role === "RECEPTIONIST";
}

function setLoginMessage(text, type = "error") {
  const box = $("login-message");
  if (!box) return;
  box.textContent = text || "";
  box.className = text
    ? "text-xs rounded-xl px-3 py-2 border " + (type === "success"
        ? "border-emerald-600/50 bg-emerald-950/40 text-emerald-200"
        : "border-rose-600/50 bg-rose-950/40 text-rose-200")
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
  const tab = hasPerm(TAB_PERMISSIONS[state.currentTab]) ? state.currentTab : firstAllowedTab();
  switchTab(tab);
  refreshIcons();
}

/** Gửi thông tin đăng nhập lên backend và mở giao diện khi thành công. */
async function submitLogin(event) {
  if (event) event.preventDefault();
  const username = ($("login-username").value || "").trim();
  const password = $("login-password").value || "";
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

/** Token hết hạn/bị thu hồi giữa phiên làm việc -> quay về màn hình đăng nhập. */
function handleSessionExpired() {
  if (!state.session.token) return;
  state.session.token = "";
  state.session.user = null;
  clearStoredToken();
  state.selectedTicket = null;
  state.currentAiResult = null;
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
  state.selectedTicket = null;
  state.currentAiResult = null;
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
  const res = await apiFetch("/api/v1/users/");
  if (!res.ok) {
    if (res.status === 403) {
      setTableMessage("accounts-table-body", 7, "Chỉ Quản lý xem được danh sách tài khoản nhân viên.");
    } else {
      setTableMessage("accounts-table-body", 7, escapeHtml(errorMessage(res.status, res.data)));
    }
    return;
  }
  const payload = res.data || {};
  const rows = Array.isArray(payload) ? payload : Array.isArray(payload.items) ? payload.items : [];
  if (!rows.length) {
    setTableMessage("accounts-table-body", 7, "Hệ thống chưa có tài khoản nhân viên nào.");
    return;
  }
  const tbody = $("accounts-table-body");
  tbody.innerHTML = rows
    .map((u) => {
      const active = u.active !== false;
      return `<tr class="table-row">
        <td class="table-td font-mono text-xs">${escapeHtml(u.username)}</td>
        <td class="table-td font-medium">${escapeHtml(displayText(u.full_name))}</td>
        <td class="table-td">${escapeHtml(roleLabel(u.role))}</td>
        <td class="table-td">${escapeHtml(displayText(u.email))}</td>
        <td class="table-td font-mono text-xs">${escapeHtml(displayText(u.phone))}</td>
        <td class="table-td">${u.service_center_id === null || u.service_center_id === undefined ? "Toàn hệ thống" : "Trung tâm #" + escapeHtml(u.service_center_id)}</td>
        <td class="table-td">${active
          ? '<span class="px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-950/60 text-emerald-200 border border-emerald-800/60">Đang làm việc</span>'
          : '<span class="px-2.5 py-1 text-xs font-semibold rounded-full bg-rose-950/60 text-rose-200 border border-rose-800/60">Đã khoá</span>'}</td>
      </tr>`;
    })
    .join("");
  refreshIcons();
}

/* --------------------------- KHỞI TẠO --------------------------- */
function bindEvents() {
  setupTabs();
  setupAuthEvents();

  $("btn-goto-tickets").addEventListener("click", goToTickets);
  $("customer-form").addEventListener("submit", submitCustomerForm);
  $("product-form").addEventListener("submit", submitProductForm);
  $("device-form").addEventListener("submit", submitDeviceForm);
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















