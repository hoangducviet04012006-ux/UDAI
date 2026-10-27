/*
 * Smoke test giao diện (chạy bằng Node, KHÔNG cần trình duyệt):
 *   node tests/smoke_frontend.js      (hoặc: .\dev.ps1 ui)
 *
 * Nạp frontend/app.js trong môi trường DOM giả tối thiểu rồi gọi thử các hàm
 * hiển thị quan trọng của MÀN HÌNH PHIẾU để phát hiện lỗi cú pháp / lỗi tham
 * chiếu sau khi sửa nghiệp vụ phiếu bảo hành:
 *   - nhãn trạng thái tiếng Việt (không lộ enum),
 *   - thông báo lỗi ưu tiên `message` tiếng Việt của backend (không lộ mã kỹ thuật),
 *   - thanh tiến trình 5 bước, hộp thoại xác nhận (thiết bị + phiếu + khách hàng),
 *   - khối "Việc cần làm" theo vai trò, điều kiện hoàn tất, lịch sử xử lý,
 *   - nút hành động chỉ vẽ theo `available_actions` do backend trả về.
 *
 * LƯU Ý: đây là kiểm tra lớp HIỂN THỊ; việc chặn thật vẫn do backend
 * (xem tests/test_ticket_workflow.py cho phần nghiệp vụ/API).
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

function makeEl() {
  return {
    style: {},
    dataset: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    setAttribute() {},
    getAttribute() { return null; },
    removeAttribute() {},
    focus() {},
    scrollIntoView() {},
    remove() {},
    appendChild() {},
    addEventListener() {},
    querySelectorAll() { return []; },
    querySelector() { return null; },
    innerHTML: "",
    textContent: "",
    value: "",
    placeholder: "",
    className: "",
    children: [],
  };
}

const elements = {};
const getEl = (id) => {
  if (!elements[id]) elements[id] = makeEl();
  return elements[id];
};

const sandbox = {
  console,
  setTimeout,
  clearTimeout,
  URLSearchParams,
  fetch: async () => ({ ok: true, status: 200, text: async () => "{}" }),
  window: { localStorage: { getItem: () => null, setItem() {}, removeItem() {} } },
  document: {
    getElementById: getEl,
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener() {},
    documentElement: { setAttribute() {} },
    createElement: makeEl,
    body: makeEl(),
  },
};
sandbox.globalThis = sandbox;

// Đường dẫn tính theo vị trí file test để chạy được từ mọi thư mục
const appJsPath = path.join(__dirname, "..", "frontend", "app.js");
const source = fs.readFileSync(appJsPath, "utf8");
vm.createContext(sandbox);
vm.runInContext(source, sandbox, { filename: "app.js" });

const checks = [];
function check(name, condition, extra) {
  checks.push([name, !!condition, extra || ""]);
}

// 1. Nhãn trạng thái hiển thị tiếng Việt, không lộ enum
check("statusLabel(WAITING_RETURN) = 'Chờ trả máy'",
  sandbox.statusLabel("WAITING_RETURN") === "Chờ trả máy", sandbox.statusLabel("WAITING_RETURN"));

// 2. Thông báo lỗi ưu tiên `message` tiếng Việt của backend (không lộ mã kỹ thuật)
const errMsg = sandbox.errorMessage(400, {
  detail: "[STATE MACHINE ERROR] Không được phép chuyển trạng thái từ 'REPAIRING' ...",
  message: "Chưa thể hoàn tất phiếu. Thiết bị vẫn đang ở trạng thái sửa chữa.",
  hint: "Bấm \"Sửa xong – Chờ trả máy\" trước.",
});
check("errorMessage dùng message tiếng Việt của backend",
  errMsg.indexOf("Chưa thể hoàn tất phiếu") === 0 && errMsg.indexOf("STATE MACHINE") === -1, errMsg);

// 3. Thanh tiến trình 5 bước vẽ từ dữ liệu backend
const stepsHtml = sandbox.renderStepsHtml({
  status: "WAITING_RETURN",
  steps: [
    { step: 1, status: "RECEIVED", label: "Tiếp nhận", state: "done", by_name: "Tran Tiep Nhan", at: "2026-05-10T08:00:00" },
    { step: 2, status: "INSPECTING", label: "Kiểm tra", state: "done", by_name: "Le Ky Thuat", at: "2026-05-10T09:00:00" },
    { step: 3, status: "REPAIRING", label: "Sửa chữa", state: "done", by_name: "Le Ky Thuat", at: "2026-05-10T10:00:00" },
    { step: 4, status: "WAITING_RETURN", label: "Chờ trả máy", state: "current", by_name: "Le Ky Thuat", at: "2026-05-10T11:00:00" },
    { step: 5, status: "COMPLETED", label: "Hoàn tất", state: "pending" },
  ],
});
check("renderStepsHtml có đủ 5 bước và đánh dấu bước hiện tại",
  stepsHtml.indexOf("Chờ trả máy") !== -1 && stepsHtml.indexOf("đang ở đây") !== -1,
  stepsHtml.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 120));

// 4. Hộp thoại xác nhận hiển thị đúng thiết bị + phiếu + khách hàng
const summary = sandbox.ticketConfirmSummary({
  ticket_code: "TK-20260510-0001",
  serial_number: "SN-ASUS-2026-0001",
  product_name: "Laptop Asus ROG Strix G16",
  customer_name: "Nguyen Van An",
});
check("ticketConfirmSummary có thiết bị + phiếu + khách hàng",
  summary.indexOf("TK-20260510-0001") !== -1 && summary.indexOf("SN-ASUS-2026-0001") !== -1,
  summary.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 120));


// 5. Khối nhóm công việc theo vai trò: mỗi phiếu có 1 nút hành động do backend chỉ định
sandbox.renderWorkGroups([
  {
    key: "waiting_return",
    label: "Chờ trả máy",
    description: "Gọi khách tới nhận máy rồi xác nhận đã trả máy.",
    count: 2,
    status_filter: "WAITING_RETURN",
    statuses: ["WAITING_RETURN"],
    scope: "ALL",
    scope_label: "Toàn trung tâm",
    tone: "cyan",
    action_target: "COMPLETED",
    action_label: "Xác nhận đã trả máy",
    items: [
      {
        id: 7,
        ticket_code: "TK-20260510-0001",
        status: "WAITING_RETURN",
        status_label: "Chờ trả máy",
        customer_name: "Nguyen Van An",
        product_name: "Laptop Asus ROG Strix G16",
        serial_number: "SN-ASUS-2026-0001",
        created_at: "2026-05-10T08:00:00",
        action_kind: "transition",
        action_label: "Xác nhận đã trả máy",
        primary_action: { target: "COMPLETED", button_label: "Xác nhận đã trả máy" },
        available_actions: [{ target: "COMPLETED", button_label: "Xác nhận đã trả máy" }],
      },
    ],
  },
]);
const workloadHtml = getEl("dash-workload").innerHTML;
check("renderWorkGroups vẽ nhóm việc + nút hành động theo vai trò",
  workloadHtml.indexOf("Chờ trả máy") !== -1 &&
  workloadHtml.indexOf("Xác nhận đã trả máy") !== -1 &&
  workloadHtml.indexOf("Toàn trung tâm") !== -1,
  workloadHtml.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 160));

// 5b. Nhãn nút theo nghiệp vụ của vai trò (kỹ thuật viên: "Bắt đầu kiểm tra")
sandbox.renderWorkGroups([
  {
    key: "waiting_inspect",
    label: "Chờ kiểm tra",
    description: "Máy đã tiếp nhận tại quầy, cần đưa vào bàn kiểm tra.",
    count: 1,
    status_filter: "RECEIVED",
    scope: "ALL",
    scope_label: "Toàn trung tâm",
    tone: "blue",
    action_target: "INSPECTING",
    action_label: "Bắt đầu kiểm tra",
    items: [
      {
        id: 11,
        ticket_code: "TK-TEST-0011",
        status: "RECEIVED",
        customer_name: "Tran Thi Binh",
        serial_number: "SN-ASUS-VALID-01",
        created_at: "2026-05-11T08:00:00",
        action_kind: "transition",
        action_label: "Chuyển sang kiểm tra",
        primary_action: { target: "INSPECTING", button_label: "Chuyển sang kiểm tra" },
        available_actions: [{ target: "INSPECTING", button_label: "Chuyển sang kiểm tra" }],
      },
    ],
  },
]);
check("Nhãn nút trong nhóm dùng câu chữ của vai trò (Bắt đầu kiểm tra)",
  getEl("dash-workload").innerHTML.indexOf("Bắt đầu kiểm tra") !== -1,
  getEl("dash-workload").innerHTML.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 160));

// 5c. Thẻ số liệu theo vai trò (nhãn + số do backend trả về)
sandbox.renderDashCards([
  { key: "RECEIVED", label: "Mới tiếp nhận", count: 3, description: "Máy vừa nhận tại quầy", tone: "blue", status: "RECEIVED" },
  { key: "WAITING_RETURN", label: "Chờ trả máy", count: 2, description: "Đã sửa xong", tone: "cyan", status: "WAITING_RETURN" },
]);
const cardsHtml = getEl("dash-cards").innerHTML;
check("renderDashCards vẽ thẻ số liệu theo vai trò + bấm được",
  cardsHtml.indexOf("Mới tiếp nhận") !== -1 && cardsHtml.indexOf("3") !== -1 &&
  cardsHtml.indexOf("openTicketsFiltered('RECEIVED')") !== -1,
  cardsHtml.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 140));

// 5d. Bảng điều khiển: mỗi dòng phiếu có đúng 1 hành động chính theo trạng thái + quyền
sandbox.renderDashTable(
  {
    role: "TECHNICIAN",
    table_title: "Phiếu tôi đang xử lý",
    my_tickets: [
      {
        id: 21,
        ticket_code: "TK-TEST-0021",
        status: "REPAIRING",
        customer_name: "Le Hoang Cuong",
        customer_phone: "0901234567",
        serial_number: "SN-DELL-01",
        product_name: "Man hinh Dell UltraSharp U2723QE",
        handler_name: "Le Ky Thuat",
        created_at: "2026-05-12T09:00:00",
        action_kind: "transition",
        action_label: "Sửa xong – Chờ trả máy",
        primary_action: { target: "WAITING_RETURN", button_label: "Sửa xong – Chờ trả máy" },
        available_actions: [{ target: "WAITING_RETURN", button_label: "Sửa xong – Chờ trả máy" }],
      },
    ],
    active_tickets: [],
    attention: [],
  },
  "mine"
);
const dashTable = getEl("dash-active-body").innerHTML;
check("renderDashTable: bảng điều khiển có nút hành động chính của phiếu",
  dashTable.indexOf("Sửa xong – Chờ trả máy") !== -1 && dashTable.indexOf("TK-TEST-0021") !== -1,
  dashTable.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 160));

// 5e. Khối "Việc cần chú ý" chỉ hiện với Quản lý và nêu LÝ DO thật của phiếu
sandbox.renderDashAttention({
  role: "MANAGER",
  attention: [
    {
      ticket_id: 31,
      ticket_code: "TK-TEST-0031",
      status: "REPAIRING",
      status_label: "Đang sửa chữa",
      reason: "Chưa cập nhật nội dung đã kiểm tra / đã sửa chữa",
      customer_name: "Nguyen Van An",
      product_name: "Laptop Asus ROG Strix G16",
    },
  ],
});
check("renderDashAttention nêu lý do cần chú ý của phiếu (Quản lý)",
  getEl("dash-attention").innerHTML.indexOf("Chưa cập nhật nội dung") !== -1,
  getEl("dash-attention").innerHTML.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 140));

// 6. Danh sách điều kiện hoàn tất hiển thị đủ/chưa đủ
sandbox.renderCompletionChecklist({
  status: "REPAIRING",
  completion_checklist: [
    { key: "device_exists", label: "Thiết bị của phiếu tồn tại", satisfied: true },
    { key: "status_waiting_return", label: "Thiết bị đang ở trạng thái Chờ trả máy", satisfied: false },
  ],
  completion_blockers: ["Thiết bị đang ở trạng thái Đang sửa chữa nên chưa thể hoàn tất."],
});
const checklist = getEl("ws-completion-list").innerHTML;
check("renderCompletionChecklist hiện điều kiện đủ/chưa đủ",
  checklist.indexOf("✔") !== -1 && checklist.indexOf("○") !== -1,
  checklist.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim());

// 7. Lịch sử xử lý có người thực hiện + thời gian + ghi chú
sandbox.renderTicketTimeline({
  history: [{
    id: 1, from_status: null, to_status: "RECEIVED", from_label: null, to_label: "Mới tiếp nhận",
    changed_by: 2, changed_by_name: "Tran Tiep Nhan", note: "Khởi tạo phiếu tiếp nhận",
    created_at: "2026-05-10T08:00:00",
  }],
});
const timeline = getEl("modal-ticket-timeline").innerHTML;
check("renderTicketTimeline có người thực hiện + thời gian + ghi chú",
  timeline.indexOf("Người thực hiện") !== -1 && timeline.indexOf("Mới tiếp nhận") !== -1 &&
  timeline.indexOf("Khởi tạo phiếu tiếp nhận") !== -1 && timeline.indexOf("08:00") !== -1,
  timeline.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 140));

// 8. Nút hành động chỉ hiện theo danh sách backend trả về (available_actions)
sandbox.renderStateActions({
  status: "WAITING_RETURN",
  status_label: "Chờ trả máy",
  available_actions: [{
    target: "COMPLETED", target_label: "Đã hoàn tất", button_label: "Xác nhận đã trả máy",
    confirm_question: "?", description: "Bàn giao máy", style: "success", fields: ["handover_note"],
    requires_input: true, requires_rejection_reason: false, note_label: "Ghi chú",
    note_placeholder: "", permission: "ticket.handover",
  }],
  permission_notes: ["Thao tác Khách báo còn lỗi cần quyền khác."],
});
const actionsHtml = getEl("modal-state-actions").innerHTML;
check("renderStateActions chỉ vẽ nút mà backend cho phép",
  actionsHtml.indexOf("Xác nhận đã trả máy") !== -1 && actionsHtml.indexOf("Từ chối bảo hành") === -1,
  actionsHtml.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim());

console.log("=".repeat(70));
console.log("SMOKE TEST GIAO DIEN (khong can trinh duyet)");
console.log("=".repeat(70));
let failed = 0;
checks.forEach(([name, ok, extra], index) => {
  if (!ok) failed += 1;
  console.log(`  ${String(index + 1).padStart(2, "0")}. [${ok ? "PASS" : "FAIL"}] ${name}`);
  if (extra) console.log(`      -> ${extra}`);
});
console.log(`\n  => ${checks.length - failed}/${checks.length} PASS | FAIL: ${failed}`);
process.exit(failed === 0 ? 0 : 1);
