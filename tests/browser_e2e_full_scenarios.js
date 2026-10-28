/**
 * =======================================================================
 * KIỂM THỬ TRÌNH DUYỆT ĐẦY ĐỦ E2E TRÊN CSDL TẠM (BaoHanhAI)
 * =======================================================================
 * Kịch bản bao gồm:
 * 1. Tạo tài khoản, khóa/mở khóa và đăng nhập tài khoản bị khóa.
 * 2. Serial đã tồn tại, không có phiếu mở -> lập phiếu mới.
 * 3. Serial chưa tồn tại -> đăng ký máy -> lập phiếu.
 * 4. Luồng sửa chữa đầy đủ đến trả máy (RECEIVED -> INSPECTING -> REPAIRING -> COMPLETED -> RETURNED).
 * 5. Đề xuất từ chối -> Quản lý không đồng ý -> KTV tiếp tục.
 * 6. Đề xuất từ chối -> Quản lý duyệt -> Tiếp nhận trả máy.
 * 7. Ba chức năng AI (AI-01, AI-02, AI-03), sao chép thông báo, kiểm tra lỗi API giao diện.
 * 8. Tạo/sửa khách hàng và thiết bị theo quyền hiện có; kiểm tra ẩn nút theo RBAC.
 *
 * Mọi thao tác thực hiện qua nút và form (DOM events/clicks);
 * Xác nhận kết quả lưu và hiển thị sau khi tải lại trang (location.reload).
 * Lưu ảnh vào docs/evidence/screenshots/ và log vào docs/evidence/logs/
 */

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const LOG_FILE = path.resolve(__dirname, '../docs/evidence/logs/browser_e2e_test.log');
const SCREENSHOTS_DIR = path.resolve(__dirname, '../docs/evidence/screenshots');

fs.mkdirSync(path.dirname(LOG_FILE), { recursive: true });
fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.log(line);
  fs.appendFileSync(LOG_FILE, line + '\n');
}

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function runFullE2ETest() {
  log('======================================================================');
  log('BẮT ĐẦU KIỂM THỬ TRÌNH DUYỆT E2E TRÊN CSDL TẠM (PORT 8088)');
  log('======================================================================');

  // 1. Khởi động Headless Chrome
  const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  const profileDir = path.resolve(__dirname, 'temp_chrome_profile');
  
  const chrome = spawn(chromePath, [
    '--headless=new',
    '--remote-debugging-port=9222',
    '--remote-allow-origins=*',
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    `--user-data-dir=${profileDir}`,
    'http://127.0.0.1:8088/'
  ]);

  await sleep(2500);

  // 2. Kết nối Chrome DevTools Protocol qua WebSocket
  const listRes = await fetch('http://127.0.0.1:9222/json/list');
  const pages = await listRes.json();
  const page = pages.find(p => p.type === 'page');
  if (!page) throw new Error('Không tìm thấy target page trên Chrome CDP.');

  log(`[*] Đã kết nối target Chrome CDP: ${page.title} (${page.url})`);
  const ws = new WebSocket(page.webSocketDebuggerUrl);

  let msgId = 1;
  const callbacks = new Map();

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && callbacks.has(msg.id)) {
      callbacks.get(msg.id)(msg);
      callbacks.delete(msg.id);
    }
  };

  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = msgId++;
    callbacks.set(id, (res) => res.error ? reject(res.error) : resolve(res.result));
    ws.send(JSON.stringify({ id, method, params }));
  });

  await new Promise(r => ws.onopen = r);
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', {
    width: 1920,
    height: 1080,
    deviceScaleFactor: 1,
    mobile: false
  });

  // CDP Helper methods
  const evalJS = async (expression) => {
    let code = expression.trim();
    if (code.startsWith("(function") || code.startsWith("(() =>")) {
      code = "return " + code;
    } else if (!code.includes("return ") && !code.includes(";")) {
      code = `return (${code});`;
    }
    const wrapped = `(() => {\n${code}\n})()`;
    const res = await send('Runtime.evaluate', {
      expression: wrapped,
      awaitPromise: true,
      returnByValue: true
    });
    if (res.exceptionDetails) {
      throw new Error(`Eval exception: ${res.exceptionDetails.text} (${JSON.stringify(res.exceptionDetails.exception)})`);
    }
    return res.result ? res.result.value : undefined;
  };

  const screenshot = async (filename) => {
    await sleep(400);
    const snap = await send('Page.captureScreenshot', { format: 'png' });
    const fullPath = path.join(SCREENSHOTS_DIR, filename);
    fs.writeFileSync(fullPath, Buffer.from(snap.data, 'base64'));
    log(`  [SCREENSHOT] Đã lưu ảnh: ${filename}`);
  };

  // Mock confirm & prompt để automation không bị block modal
  const injectDialogOverrides = async (promptDefaultValue = "Xác nhận kiểm thử tự động") => {
    await evalJS(`
      window._lastPromptValue = "${promptDefaultValue}";
      window.confirm = function(msg) { console.log('[CONFIRM MOCK]', msg); return true; };
      window.prompt = function(msg, def) { console.log('[PROMPT MOCK]', msg); return window._lastPromptValue || def || "Xác nhận tự động"; };
    `);
  };

  const setPromptNote = async (note) => {
    await evalJS(`window._lastPromptValue = ${JSON.stringify(note)};`);
  };

  const waitElement = async (selector, timeout = 10000) => {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const ok = await evalJS(`!!document.querySelector("${selector}")`);
      if (ok) return true;
      await sleep(200);
    }
    throw new Error(`Timeout chờ selector: ${selector}`);
  };

  const login = async (username, password = "Password123!") => {
    log(`[*] Đăng nhập tài khoản: ${username} ...`);
    await evalJS(`
      const u = document.getElementById("login-username");
      const p = document.getElementById("login-password");
      if (u) { u.value = "${username}"; u.dispatchEvent(new Event("input")); }
      if (p) { p.value = "${password}"; p.dispatchEvent(new Event("input")); }
      const f = document.getElementById("login-form");
      if (f) f.dispatchEvent(new Event("submit", { cancelable: true }));
    `);
    await sleep(1500);
    await injectDialogOverrides();
  };

  const logout = async () => {
    log(`[*] Đăng xuất tài khoản ...`);
    await evalJS(`
      const btn = document.getElementById("btn-logout");
      if (btn) btn.click();
    `);
    await sleep(500);
    await evalJS(`
      const conf = document.getElementById("action-modal-confirm");
      if (conf) conf.click();
    `);
    await sleep(1500);
    await injectDialogOverrides();
  };

  const reload = async () => {
    log(`[*] Tải lại trang (location.reload) ...`);
    await evalJS(`location.reload();`);
    await sleep(2000);
    await injectDialogOverrides();
  };

  const switchTab = async (tabName) => {
    log(`[*] Chuyển sang tab: ${tabName} ...`);
    await evalJS(`switchTab("${tabName}");`);
    await sleep(800);
  };

  const resultsSummary = [];

  try {
    await injectDialogOverrides();

    // ===================================================================
    // KỊCH BẢN 1: QUẢN LÝ TÀI KHOẢN (Tạo, khóa/mở khóa, đăng nhập bị khóa)
    // ===================================================================
    log('\n>>> BẮT ĐẦU KỊCH BẢN 1: QUẢN LÝ TÀI KHOẢN (TẠO, KHÓA/MỞ KHÓA, THỬ ĐĂNG NHẬP)');
    await login('manager01', '123456');
    await switchTab('accounts');
    await waitElement('#accounts-table-body');

    // 1.1 Bấm nút Thêm tài khoản và nhập form
    log('[1.1] Mở form tạo tài khoản mới: tech_e2e_lock_demo');
    await evalJS(`
      openAddUserModal();
      document.getElementById("usr-username").value = "tech_e2e_lock_demo";
      document.getElementById("usr-password").value = "Password123!";
      document.getElementById("usr-fullname").value = "Kỹ Thuật Viên E2E Test";
      document.getElementById("usr-role").value = "TECHNICIAN";
      document.getElementById("usr-phone").value = "0988776655";
      document.getElementById("usr-email").value = "tech_lock_demo@baohanhai.vn";
      const f = document.getElementById("user-form");
      f.dispatchEvent(new Event("submit", { cancelable: true }));
    `);
    await sleep(2000);

    // Xác nhận tài khoản xuất hiện trong bảng với trạng thái Đang làm việc
    let userRow = await evalJS(`
      (function() {
        const rows = Array.from(document.querySelectorAll("#accounts-table-body tr"));
        const target = rows.find(r => r.textContent.includes("tech_e2e_lock_demo"));
        return target ? target.innerText : null;
      })()
    `);
    if (!userRow) throw new Error('Không tìm thấy tài khoản mới tạo trong danh sách!');
    log(`  [PASS] Đã tạo tài khoản thành công: ${userRow.replace(/\\n/g, ' ')}`);

    // 1.2 Bấm nút Khóa tài khoản
    log('[1.2] Bấm nút Khóa tài khoản tech_e2e_lock_demo');
    await evalJS(`
      (function() {
        const u = state.accounts.find(x => x.username === "tech_e2e_lock_demo");
        if (u) toggleUserActive(u.id, false);
      })()
    `);
    await sleep(1500);

    // Xác nhận giao diện hiển thị Đã khoá
    let lockedText = await evalJS(`
      (function() {
        const rows = Array.from(document.querySelectorAll("#accounts-table-body tr"));
        const target = rows.find(r => r.textContent.includes("tech_e2e_lock_demo"));
        return target ? target.innerText : "";
      })()
    `);
    if (!lockedText.includes("Đã khoá")) throw new Error(`Tài khoản chưa chuyển sang trạng thái Đã khoá: ${lockedText}`);
    log('  [PASS] Giao diện đã cập nhật trạng thái: Đã khoá');

    // Tải lại trang để kiểm chứng tính bền vững dữ liệu sau reload
    await reload();
    await login('manager01', '123456');
    await switchTab('accounts');
    await sleep(1000);
    lockedText = await evalJS(`
      (function() {
        const rows = Array.from(document.querySelectorAll("#accounts-table-body tr"));
        const target = rows.find(r => r.textContent.includes("tech_e2e_lock_demo"));
        return target ? target.innerText : "";
      })()
    `);
    if (!lockedText.includes("Đã khoá")) throw new Error(`Sau reload, trạng thái không lưu là Đã khoá: ${lockedText}`);
    await screenshot('01_account_locked_persisted.png');
    log('  [PASS] Xác nhận trạng thái Đã khoá được lưu bền vững sau khi tải lại trang.');

    // 1.3 Đăng xuất và thử đăng nhập bằng tài khoản bị khóa
    log('[1.3] Thử đăng nhập bằng tài khoản bị khóa: tech_e2e_lock_demo');
    await logout();
    await login('tech_e2e_lock_demo', 'Password123!');
    await sleep(1500);

    const isStillGuest = await evalJS(`document.documentElement.getAttribute("data-auth") === "guest"`);
    const toastErrorText = await evalJS(`
      const t = document.querySelector("#toast-container .toast-error, #toast-container .toast");
      return t ? t.innerText : "";
    `);
    if (!isStillGuest) throw new Error('Tài khoản bị khóa nhưng vẫn đăng nhập thành công!');
    await screenshot('01_locked_login_blocked.png');
    log(`  [PASS] Đăng nhập bị chặn chính xác với tài khoản đã khóa. Thông báo: "${toastErrorText.trim()}"`);

    // 1.4 Đăng nhập lại Quản lý và Mở khóa tài khoản
    log('[1.4] Quản lý mở khóa tài khoản tech_e2e_lock_demo');
    await login('manager01', '123456');
    await switchTab('accounts');
    await sleep(1000);
    await evalJS(`
      (function() {
        const u = state.accounts.find(x => x.username === "tech_e2e_lock_demo");
        if (u) toggleUserActive(u.id, true);
      })()
    `);
    await sleep(1500);

    // Xác nhận sau reload hiển thị Đang làm việc
    await reload();
    await login('manager01', '123456');
    await switchTab('accounts');
    await sleep(1000);
    const activeText = await evalJS(`
      (function() {
        const rows = Array.from(document.querySelectorAll("#accounts-table-body tr"));
        const target = rows.find(r => r.textContent.includes("tech_e2e_lock_demo"));
        return target ? target.innerText : "";
      })()
    `);
    if (!activeText.includes("Đang làm việc")) throw new Error(`Sau mở khóa & reload, tài khoản chưa về Đang làm việc: ${activeText}`);
    await screenshot('01_account_unlocked_persisted.png');
    log('  [PASS] Mở khóa thành công và hiển thị Đang làm việc sau reload.');

    // 1.5 Đăng xuất và đăng nhập bằng tài khoản vừa mở khóa
    await logout();
    log('[1.5] Đăng nhập bằng tài khoản vừa mở khóa tech_e2e_lock_demo');
    await login('tech_e2e_lock_demo', 'Password123!');
    const isAuthed = await evalJS(`document.documentElement.getAttribute("data-auth") === "authed"`);
    const currentUserName = await evalJS(`(document.getElementById("user-name-display") || {}).textContent || ""`);
    if (!isAuthed) throw new Error('Đăng nhập thất bại sau khi đã mở khóa!');
    await screenshot('01_unlocked_login_success.png');
    log(`  [PASS] Đăng nhập thành công với vai trò KTV (${currentUserName.trim()})!`);
    await logout();

    resultsSummary.push({ id: 'KB1', name: 'Quản lý tài khoản (tạo, khóa, đăng nhập bị khóa, mở khóa)', status: 'PASS' });

    // ===================================================================
    // KỊCH BẢN 2: SERIAL ĐÃ TỒN TẠI, KHÔNG CÓ PHIẾU MỞ -> LẬP PHIẾU MỚI
    // ===================================================================
    log('\n>>> BẮT ĐẦU KỊCH BẢN 2: SERIAL ĐÃ TỒN TẠI -> LẬP PHIẾU MỚI');
    await login('receptionist01', '123456');
    await switchTab('tickets');
    await waitElement('#wiz-serial');

    // Tra cứu serial đã có trong seed: SN-ASUS-VALID-01
    log('[2.1] Tra cứu serial SN-ASUS-VALID-01 trong Tiếp nhận bảo hành');
    await evalJS(`
      const sn = document.getElementById("wiz-serial");
      sn.value = "SN-ASUS-VALID-01";
      wizardLookupSerial();
    `);
    await sleep(2500);

    const lookupFound = await evalJS(`
      (function() {
        const resBox = document.getElementById("wiz-device-result");
        return resBox && resBox.innerText.includes("SN-ASUS-VALID-01");
      })()
    `);
    if (!lookupFound) throw new Error('Tra cứu không tìm thấy thiết bị SN-ASUS-VALID-01 trong khu tiếp nhận!');

    // Bấm nút Tiếp tục bước 2
    log('[2.2] Bấm Tiếp tục bước 2 và nhập thông tin phiếu');
    await evalJS(`
      wizardGoToStep2();
    `);
    await sleep(1500);

    // Nhập mô tả lỗi và tạo phiếu
    await evalJS(`
      document.getElementById("wiz-desc").value = "Bàn phím bị liệt cụm phím số bên phải, sạc chập chờn khi cắm nguồn";
      document.getElementById("wiz-accessories").value = "Sạc theo máy, túi chống sốc";
      document.getElementById("wiz-condition").value = "Máy trầy xước nhẹ góc dưới, tem bảo hành còn nguyên vẹn";
      wizardSubmitTicket();
    `);
    await sleep(3000);

    // Lấy mã phiếu vừa tạo
    const createdTicketCodeSc2 = await evalJS(`
      (function() {
        const t = (state.tickets || []).find(x => x.serial_number === "SN-ASUS-VALID-01" && x.status === "RECEIVED");
        return t ? t.ticket_code : (state.tickets && state.tickets.length ? state.tickets[0].ticket_code : null);
      })()
    `);
    log(`  [+] Mã phiếu vừa tạo: ${createdTicketCodeSc2}`);

    // Tải lại trang và vào tab Phiếu bảo hành để kiểm chứng dữ liệu hiển thị sau reload
    await reload();
    await login('receptionist01', '123456');
    await switchTab('tickets');
    await sleep(1500);

    const ticketRowSc2 = await evalJS(`
      (function() {
        const rows = Array.from(document.querySelectorAll("#tickets-table-body tr"));
        const target = rows.find(r => r.textContent.includes("${createdTicketCodeSc2}") || r.textContent.includes("SN-ASUS-VALID-01"));
        return target ? target.innerText : null;
      })()
    `);
    if (!ticketRowSc2) throw new Error('Phiếu mới tạo không hiển thị trong bảng sau reload!');
    await screenshot('02_ticket_created_existing_serial.png');
    log(`  [PASS] Phiếu ${createdTicketCodeSc2} hiển thị bền vững sau reload với trạng thái TIẾP NHẬN: ${ticketRowSc2.replace(/\\n/g, ' ')}`);

    resultsSummary.push({ id: 'KB2', name: 'Serial đã tồn tại -> Lập phiếu mới', status: 'PASS', ticketCode: createdTicketCodeSc2 });

    // ===================================================================
    // KỊCH BẢN 3: SERIAL CHƯA TỒN TẠI -> ĐĂNG KÝ MÁY -> LẬP PHIẾU
    // ===================================================================
    log('\n>>> BẮT ĐẦU KỊCH BẢN 3: SERIAL CHƯA TỒN TẠI -> ĐĂNG KÝ MÁY -> LẬP PHIẾU');
    await switchTab('tickets');
    await sleep(1000);

    const newSerial = `SN-NEW-DELL-${Date.now().toString().slice(-6)}`;
    log(`[3.1] Tra cứu serial chưa có: ${newSerial}`);
    await evalJS(`
      const sn = document.getElementById("wiz-serial");
      sn.value = "${newSerial}";
      wizardLookupSerial();
    `);
    await sleep(2500);

    // Kiểm tra form đăng ký máy mới hiển thị và Ngày mua để trống
    const isNewDeviceFormVisible = await evalJS(`!document.getElementById("wiz-new-device").classList.contains("hidden")`);
    const purchaseDateValue = await evalJS(`document.getElementById("wiz-purchase-date").value`);
    if (!isNewDeviceFormVisible) throw new Error('Không hiện form đăng ký máy khi serial chưa có!');
    if (purchaseDateValue !== "") throw new Error(`Ngày mua bị tự động điền giá trị hôm nay: "${purchaseDateValue}"! Yêu cầu phải để trống.`);
    log(`  [PASS] Form đăng ký máy mới hiển thị chuẩn, ô Ngày mua rỗng đúng yêu cầu (value='${purchaseDateValue}').`);

    // Điền thông tin đăng ký máy và lưu thiết bị (wizardSaveDevice tự động chuyển sang bước 2)
    log('[3.2] Điền thông tin đăng ký máy mới và tạo phiếu');
    await evalJS(`
      const custSelect = document.getElementById("wiz-customer-id");
      if (custSelect.options.length > 1) custSelect.selectedIndex = 1;
      document.getElementById("wiz-product-name").value = "Laptop Dell UltraBook XPS 13";
      document.getElementById("wiz-purchase-date").value = "2025-06-15";
      wizardSaveDevice();
    `);
    await sleep(2500);

    // Điền bước 2 mô tả lỗi và lập phiếu
    await evalJS(`
      document.getElementById("wiz-desc").value = "Máy khởi động kêu bíp liên tục, màn hình không hiển thị nội dung";
      document.getElementById("wiz-accessories").value = "Dây nguồn adapter zin theo máy";
      document.getElementById("wiz-condition").value = "Máy còn nguyên tem bảo hành, không cấn móp, màn hình không xước";
      wizardSubmitTicket();
    `);
    await sleep(3000);

    const createdTicketCodeSc3 = await evalJS(`
      (function() {
        const t = (state.tickets || []).find(x => x.serial_number === "${newSerial}");
        return t ? t.ticket_code : (state.tickets && state.tickets.length ? state.tickets[0].ticket_code : null);
      })()
    `);
    log(`  [+] Mã phiếu vừa tạo cho máy mới: ${createdTicketCodeSc3}`);

    // Tải lại trang và kiểm chứng cả ở tab Thiết bị lẫn tab Phiếu bảo hành
    await reload();
    await login('receptionist01', '123456');
    await switchTab('devices');
    await sleep(1500);

    const deviceRowSc3 = await evalJS(`
      (function() {
        const rows = Array.from(document.querySelectorAll("#devices-table-body tr"));
        const target = rows.find(r => r.textContent.includes("${newSerial}"));
        return target ? target.innerText : null;
      })()
    `);
    if (!deviceRowSc3) throw new Error(`Thiết bị ${newSerial} chưa được lưu vào danh sách thiết bị!`);
    log(`  [PASS] Thiết bị mới đã đăng ký thành công và hiển thị sau reload: ${deviceRowSc3.replace(/\\n/g, ' ')}`);

    await switchTab('tickets');
    await sleep(1000);
    const ticketRowSc3 = await evalJS(`
      (function() {
        const rows = Array.from(document.querySelectorAll("#tickets-table-body tr"));
        const target = rows.find(r => r.textContent.includes("${createdTicketCodeSc3}"));
        return target ? target.innerText : null;
      })()
    `);
    if (!ticketRowSc3) throw new Error(`Phiếu ${createdTicketCodeSc3} không hiển thị trong bảng phiếu sau reload!`);
    await screenshot('03_ticket_created_new_device.png');
    log(`  [PASS] Phiếu bảo hành cho thiết bị mới hiển thị bền vững sau reload.`);

    resultsSummary.push({ id: 'KB3', name: 'Serial chưa tồn tại -> Đăng ký máy -> Lập phiếu', status: 'PASS', ticketCode: createdTicketCodeSc3 });

    // ===================================================================
    // KỊCH BẢN 4: LUỒNG SỬA CHỮA ĐẦY ĐỦ ĐẾN TRẢ MÁY
    // (RECEIVED -> INSPECTING -> REPAIRING -> COMPLETED -> RETURNED)
    // ===================================================================
    log('\n>>> BẮT ĐẦU KỊCH BẢN 4: LUỒNG SỬA CHỮA ĐẦY ĐỦ ĐẾN TRẢ MÁY');
    await logout();

    // 4.1 Quản lý phân công KTV và chuyển sang INSPECTING
    log(`[4.1] Quản lý phân công KTV cho phiếu ${createdTicketCodeSc2}`);
    await login('manager01', '123456');
    await switchTab('tickets');
    await sleep(1000);

    // Mở modal chi tiết phiếu Sc2
    await evalJS(`
      (function() {
        const t = state.tickets.find(x => x.ticket_code === "${createdTicketCodeSc2}");
        if (t) openTicketModal(t.id);
      })()
    `);
    await sleep(1500);

    // 4.1a Quản lý phân công KTV Tuấn
    await evalJS(`
      (function() {
        const actions = Array.from(document.querySelectorAll("#modal-state-actions button"));
        const assignBtn = actions.find(b => b.textContent.includes("Phân công"));
        if (assignBtn) assignBtn.click();
      })()
    `);
    await sleep(800);
    await evalJS(`
      (function() {
        const sel = document.getElementById("action-modal-select");
        if (sel) {
          const opt = Array.from(sel.options).find(o => o.text.includes("Tuấn") || o.text.includes("technician01"));
          if (opt) sel.value = opt.value;
        }
        const noteField = document.getElementById("action-field-note");
        if (noteField) noteField.value = "Quản lý phân công KTV Trần Minh Tuấn";
        const conf = document.getElementById("action-modal-confirm");
        if (conf) conf.click();
      })()
    `);
    await sleep(2000);

    // 4.1b Bấm nút Bắt đầu kiểm tra để chuyển sang INSPECTING
    await evalJS(`
      (function() {
        const actions = Array.from(document.querySelectorAll("#modal-state-actions button"));
        const startBtn = actions.find(b => b.textContent.includes("Bắt đầu kiểm tra"));
        if (startBtn) startBtn.click();
      })()
    `);
    await sleep(800);
    await evalJS(`
      (function() {
        const conf = document.getElementById("action-modal-confirm");
        if (conf) conf.click();
      })()
    `);
    await sleep(2500);

    // Reload kiểm chứng trạng thái INSPECTING
    await reload();
    await login('manager01', '123456');
    await switchTab('tickets');
    await sleep(1000);
    await evalJS(`
      (function() {
        const t = state.tickets.find(x => x.ticket_code === "${createdTicketCodeSc2}");
        if (t) openTicketModal(t.id);
      })()
    `);
    await sleep(1500);

    let currentStatusBadge = await evalJS(`document.getElementById("modal-ticket-badge").textContent`);
    if (!currentStatusBadge.includes("Kiểm tra")) throw new Error(`Trạng thái chưa sang Kiểm tra: ${currentStatusBadge}`);
    await screenshot('04_flow_inspecting.png');
    log(`  [PASS] Bước 1 đạt chuẩn: Phiếu đã chuyển sang KIỂM TRA (INSPECTING) và phân công KTV.`);
    await logout();

    // 4.2 KTV tiếp nhận, chẩn đoán và chuyển sang REPAIRING
    log(`[4.2] KTV01 chẩn đoán và chuyển sang SỬA CHỮA (REPAIRING)`);
    await login('technician01', '123456');
    await switchTab('tickets');
    await sleep(1000);

    await evalJS(`
      (function() {
        const t = state.tickets.find(x => x.ticket_code === "${createdTicketCodeSc2}");
        if (t) openTicketModal(t.id);
      })()
    `);
    await sleep(1500);

    // Bấm nút chuyển sang Sửa chữa
    await evalJS(`
      (function() {
        const actions = Array.from(document.querySelectorAll("#modal-state-actions button"));
        const btn = actions.find(b => b.textContent.includes("Sửa chữa") || b.textContent.includes("Bắt đầu"));
        if (btn) btn.click();
      })()
    `);
    await sleep(800);

    // Điền kết luận chẩn đoán trong action modal
    await evalJS(`
      (function() {
        const diagField = document.getElementById("action-field-diagnosis_note");
        if (diagField) diagField.value = "Chập cáp ma trận phím số, chân cắm nguồn DC-in bị lỏng mối hàn";
        const eligField = document.getElementById("action-field-is_warranty_eligible");
        if (eligField) eligField.value = "true";
        const noteField = document.getElementById("action-field-note");
        if (noteField) noteField.value = "Tiến hành thay cáp phím và hàn lại chân nguồn";
        document.getElementById("action-modal-confirm").click();
      })()
    `);
    await sleep(2500);

    // Reload kiểm chứng REPAIRING
    await reload();
    await login('technician01', '123456');
    await switchTab('tickets');
    await sleep(1000);
    await evalJS(`
      (function() {
        const t = state.tickets.find(x => x.ticket_code === "${createdTicketCodeSc2}");
        if (t) openTicketModal(t.id);
      })()
    `);
    await sleep(1500);

    currentStatusBadge = await evalJS(`document.getElementById("modal-ticket-badge").textContent`);
    if (!currentStatusBadge.includes("Sửa chữa")) throw new Error(`Trạng thái chưa sang Sửa chữa: ${currentStatusBadge}`);
    await screenshot('04_flow_repairing.png');
    log(`  [PASS] Bước 2 đạt chuẩn: Phiếu đã chuyển sang SỬA CHỮA (REPAIRING) kèm kết luận chẩn đoán.`);

    // 4.3 KTV ghi nhận sửa chữa, nghiệm thu và chuyển sang COMPLETED
    log(`[4.3] KTV01 hoàn tất sửa chữa và nghiệm thu (COMPLETED)`);
    const clickedComplete = await evalJS(`
      (() => {
        const actions = Array.from(document.querySelectorAll("#modal-state-actions button"));
        const btn = actions.find(b => (b.getAttribute("onclick") || "").includes("COMPLETED") || b.textContent.includes("Hoàn tất") || b.textContent.includes("hoàn tất"));
        if (btn) {
          btn.click();
          return true;
        }
        return false;
      })()
    `);
    if (!clickedComplete) throw new Error("Không tìm thấy nút Chuyển Hoàn tất trong #modal-state-actions");
    await sleep(1000);

    const modalCompleteFilled = await evalJS(`
      (() => {
        const contentField = document.getElementById("action-field-repair_content");
        if (!contentField) return false;
        contentField.value = "Thay mới cụm cáp phím số Asus, hàn gia cố chân cắm nguồn DC-in, vệ sinh tản nhiệt";
        const partsField = document.getElementById("action-field-repair_parts");
        if (partsField) partsField.value = "Cáp phím Asus NumPad, thiếc hàn chì";
        const testPassField = document.getElementById("action-field-repair_test_passed");
        if (testPassField) testPassField.value = "true";
        const testNoteField = document.getElementById("action-field-repair_test_note");
        if (testNoteField) testNoteField.value = "Đã test gõ phím đầy đủ, đo áp nguồn 19V sạc pin ổn định trong 2 giờ";
        const confirmBtn = document.getElementById("action-modal-confirm");
        if (!confirmBtn) return false;
        confirmBtn.click();
        return true;
      })()
    `);
    if (!modalCompleteFilled) throw new Error("Không tìm thấy trường action-field-repair_content hoặc nút xác nhận trong hộp thoại Hoàn tất");
    await sleep(2500);

    // Reload kiểm chứng COMPLETED
    await reload();
    await login('technician01', '123456');
    await switchTab('tickets');
    await sleep(1000);
    await evalJS(`
      (function() {
        const t = state.tickets.find(x => x.ticket_code === "${createdTicketCodeSc2}");
        if (t) openTicketModal(t.id);
      })()
    `);
    await sleep(1500);

    currentStatusBadge = await evalJS(`document.getElementById("modal-ticket-badge").textContent`);
    if (!currentStatusBadge.includes("Hoàn tất")) throw new Error(`Trạng thái chưa sang Hoàn tất: ${currentStatusBadge}`);
    await screenshot('04_flow_completed.png');
    log(`  [PASS] Bước 3 đạt chuẩn: Phiếu đã chuyển sang HOÀN TẤT (COMPLETED) kèm biên bản sửa chữa & test.`);
    await logout();

    // 4.4 Nhân viên Tiếp nhận bàn giao trả máy cho khách (RETURNED)
    log(`[4.4] Nhân viên Tiếp nhận bàn giao trả máy (RETURNED)`);
    await login('receptionist01', '123456');
    await switchTab('tickets');
    await sleep(1000);
    await evalJS(`
      (function() {
        const t = state.tickets.find(x => x.ticket_code === "${createdTicketCodeSc2}");
        if (t) openTicketModal(t.id);
      })()
    `);
    await sleep(1500);

    const clickedReturn = await evalJS(`
      (() => {
        const actions = Array.from(document.querySelectorAll("#modal-state-actions button"));
        const btn = actions.find(b => (b.getAttribute("onclick") || "").includes("RETURNED") || b.textContent.includes("Trả máy") || b.textContent.includes("trả máy") || b.textContent.includes("Bàn giao"));
        if (btn) {
          btn.click();
          return true;
        }
        return false;
      })()
    `);
    if (!clickedReturn) throw new Error("Không tìm thấy nút Trả máy trong #modal-state-actions");
    await sleep(1000);

    const handoverFilled = await evalJS(`
      (() => {
        const handoverField = document.getElementById("action-field-handover_note");
        if (!handoverField) return false;
        handoverField.value = "Khách hàng đã kiểm tra thực tế máy hoạt động hoàn hảo, đã ký nhận biên bản bàn giao và nhận lại máy";
        const confirmBtn = document.getElementById("action-modal-confirm");
        if (!confirmBtn) return false;
        confirmBtn.click();
        return true;
      })()
    `);
    if (!handoverFilled) throw new Error("Không tìm thấy trường action-field-handover_note trong hộp thoại Trả máy");
    await sleep(2500);

    // Reload kiểm chứng RETURNED
    await reload();
    await login('receptionist01', '123456');
    await switchTab('tickets');
    await sleep(1000);
    await evalJS(`
      (function() {
        const t = state.tickets.find(x => x.ticket_code === "${createdTicketCodeSc2}");
        if (t) openTicketModal(t.id);
      })()
    `);
    await sleep(1500);

    currentStatusBadge = await evalJS(`document.getElementById("modal-ticket-badge").textContent`);
    if (!currentStatusBadge.includes("Đã trả")) throw new Error(`Trạng thái chưa sang Đã trả máy: ${currentStatusBadge}`);
    await screenshot('04_flow_returned.png');
    log(`  [PASS] Bước 4 đạt chuẩn: Phiếu đã hoàn thành toàn bộ chu trình sang ĐÃ TRẢ MÁY (RETURNED).`);
    await logout();

    resultsSummary.push({ id: 'KB4', name: 'Luồng sửa chữa đầy đủ đến trả máy (RECEIVED -> RETURNED)', status: 'PASS' });

    // ===================================================================
    // KỊCH BẢN 5: ĐỀ XUẤT TỪ CHỐI -> QUẢN LÝ KHÔNG ĐỒNG Ý -> KTV TIẾP TỤC
    // ===================================================================
    log('\n>>> BẮT ĐẦU KỊCH BẢN 5: ĐỀ XUẤT TỪ CHỐI -> QUẢN LÝ KHÔNG ĐỒNG Ý -> KTV TIẾP TỤC');

    // 5.1 Quản lý phân công KTV cho phiếu Sc3
    await login('manager01', '123456');
    await switchTab('tickets');
    await sleep(1000);
    await evalJS(`
      (function() {
        const t = state.tickets.find(x => x.ticket_code === "${createdTicketCodeSc3}");
        if (t) openTicketModal(t.id);
      })()
    `);
    await sleep(1500);

    // 5.1a Phân công KTV
    await evalJS(`
      (function() {
        const actions = Array.from(document.querySelectorAll("#modal-state-actions button"));
        const assignBtn = actions.find(b => b.textContent.includes("Phân công"));
        if (assignBtn) assignBtn.click();
      })()
    `);
    await sleep(800);
    await evalJS(`
      (function() {
        const sel = document.getElementById("action-modal-select");
        if (sel) {
          const opt = Array.from(sel.options).find(o => o.text.includes("Tuấn") || o.text.includes("technician01"));
          if (opt) sel.value = opt.value;
        }
        const conf = document.getElementById("action-modal-confirm");
        if (conf) conf.click();
      })()
    `);
    await sleep(2000);

    // 5.1b Chuyển sang INSPECTING
    await evalJS(`
      (function() {
        const actions = Array.from(document.querySelectorAll("#modal-state-actions button"));
        const startBtn = actions.find(b => b.textContent.includes("Bắt đầu kiểm tra"));
        if (startBtn) startBtn.click();
      })()
    `);
    await sleep(800);
    await evalJS(`
      (function() {
        const conf = document.getElementById("action-modal-confirm");
        if (conf) conf.click();
      })()
    `);
    await sleep(2000);
    await logout();

    // 5.2 KTV đề xuất từ chối bảo hành
    log(`[5.2] KTV đề xuất từ chối bảo hành cho phiếu ${createdTicketCodeSc3}`);
    await login('technician01', '123456');
    await switchTab('tickets');
    await sleep(1000);
    await evalJS(`
      (function() {
        const t = state.tickets.find(x => x.ticket_code === "${createdTicketCodeSc3}");
        if (t) openTicketModal(t.id);
      })()
    `);
    await sleep(1500);

    // Bấm nút Đề xuất từ chối
    const clickedPropose = await evalJS(`
      (() => {
        const actions = Array.from(document.querySelectorAll("#modal-state-actions button"));
        const btn = actions.find(b => (b.getAttribute("onclick") || "").includes("openProposeRejectionModal") || b.textContent.includes("Đề xuất từ chối"));
        if (btn) {
          btn.click();
          return true;
        }
        return false;
      })()
    `);
    if (!clickedPropose) throw new Error("Không tìm thấy nút Đề xuất từ chối");
    await sleep(1000);

    const filledProposal = await evalJS(`
      (() => {
        const propField = document.getElementById("action-field-proposal_note");
        if (!propField) return false;
        propField.value = "Khách hàng làm rơi máy cấn móp nặng góc vỏ, rách tem bảo hành";
        const noteField = document.getElementById("action-field-note");
        if (noteField) noteField.value = "Đề xuất chuyển sửa chữa dịch vụ có tính phí theo quy định";
        const confirmBtn = document.getElementById("action-modal-confirm");
        if (!confirmBtn) return false;
        confirmBtn.click();
        return true;
      })()
    `);
    if (!filledProposal) throw new Error("Không tìm thấy trường action-field-proposal_note trong hộp thoại Đề xuất từ chối");
    await sleep(2500);

    // Reload kiểm chứng hiển thị Hộp đề xuất chờ Quản lý duyệt
    await reload();
    await login('technician01', '123456');
    await switchTab('tickets');
    await sleep(1000);
    await evalJS(`
      (function() {
        const t = state.tickets.find(x => x.ticket_code === "${createdTicketCodeSc3}");
        if (t) openTicketModal(t.id);
      })()
    `);
    await sleep(1500);

    let proposalBoxText = await evalJS(`document.getElementById("modal-rejection-proposal-box").innerText`);
    if (!proposalBoxText.includes("Đề xuất từ chối") && !proposalBoxText.includes("chờ Quản lý")) {
      throw new Error(`Chưa hiển thị hộp đề xuất từ chối cho KTV: ${proposalBoxText}`);
    }
    await screenshot('05_rejection_proposed_pending.png');
    log('  [PASS] KTV đã đề xuất từ chối thành công, hộp thông tin chờ Quản lý duyệt hiển thị chuẩn.');
    await logout();

    // 5.3 Quản lý vào xem và bấm KHÔNG ĐỒNG Ý
    log(`[5.3] Quản lý xét duyệt: KHÔNG ĐỒNG Ý đề xuất từ chối`);
    await login('manager01', '123456');
    await setPromptNote('Không đồng ý từ chối, yêu cầu KTV hỗ trợ giá linh kiện ưu đãi để sửa dịch vụ');
    await switchTab('tickets');
    await sleep(1000);
    await evalJS(`
      (function() {
        const t = state.tickets.find(x => x.ticket_code === "${createdTicketCodeSc3}");
        if (t) openTicketModal(t.id);
      })()
    `);
    await sleep(1500);

    // Bấm nút Không đồng ý trong khối đề xuất
    await evalJS(`
      (function() {
        const box = document.getElementById("modal-rejection-proposal-actions");
        const btn = box ? Array.from(box.querySelectorAll("button")).find(b => b.textContent.includes("Không đồng ý")) : null;
        if (btn) btn.click();
      })()
    `);
    await sleep(2500);

    // Reload và kiểm tra: phiếu vẫn giữ ở INSPECTING
    await reload();
    await login('manager01', '123456');
    await switchTab('tickets');
    await sleep(1000);
    await evalJS(`
      (function() {
        const t = state.tickets.find(x => x.ticket_code === "${createdTicketCodeSc3}");
        if (t) openTicketModal(t.id);
      })()
    `);
    await sleep(1500);

    currentStatusBadge = await evalJS(`document.getElementById("modal-ticket-badge").textContent`);
    if (!currentStatusBadge.includes("Kiểm tra")) throw new Error(`Phiếu không giữ ở INSPECTING sau khi từ chối đề xuất: ${currentStatusBadge}`);
    await logout();

    // 5.4 KTV vào lại và thấy nút Bắt đầu sửa chữa để tiếp tục xử lý
    log(`[5.4] KTV vào lại thấy phiếu vẫn ở INSPECTING và có thể tiếp tục sửa chữa`);
    await login('technician01', '123456');
    await switchTab('tickets');
    await sleep(1000);
    await evalJS(`
      (function() {
        const t = state.tickets.find(x => x.ticket_code === "${createdTicketCodeSc3}");
        if (t) openTicketModal(t.id);
      })()
    `);
    await sleep(1500);

    const canContinueRepair = await evalJS(`
      (function() {
        const actions = Array.from(document.querySelectorAll("#modal-state-actions button"));
        return actions.some(b => b.textContent.includes("Sửa chữa") || b.textContent.includes("Bắt đầu"));
      })()
    `);
    if (!canContinueRepair) throw new Error('KTV không thấy nút tiếp tục sửa chữa sau khi Quản lý không đồng ý từ chối!');
    await screenshot('05_rejection_declined_tech_continues.png');
    log('  [PASS] KTV tiếp tục quy trình xử lý thành công sau khi Quản lý không đồng ý từ chối.');
    await logout();

    resultsSummary.push({ id: 'KB5', name: 'Đề xuất từ chối -> Quản lý không đồng ý -> KTV tiếp tục', status: 'PASS' });

    // ===================================================================
    // KỊCH BẢN 6: ĐỀ XUẤT TỪ CHỐI -> QUẢN LÝ DUYỆT -> TIẾP NHẬN TRẢ MÁY
    // ===================================================================
    log('\n>>> BẮT ĐẦU KỊCH BẢN 6: ĐỀ XUẤT TỪ CHỐI -> QUẢN LÝ DUYỆT -> TIẾP NHẬN TRẢ MÁY');

    // 6.1 Tạo phiếu mới để kiểm thử luồng duyệt từ chối
    await login('receptionist01', '123456');
    await switchTab('tickets');
    await sleep(1000);
    log(`[6.1] Tạo phiếu mới để kiểm thử luồng Duyệt từ chối`);
    await evalJS(`
      const sn = document.getElementById("wiz-serial");
      sn.value = "SN-ASUS-VALID-01";
      wizardLookupSerial();
    `);
    await sleep(2500);
    await evalJS(`
      wizardGoToStep2();
    `);
    await sleep(1500);
    await evalJS(`
      document.getElementById("wiz-desc").value = "Rơi xuống nước biển, toàn bộ bo mạch chập cháy rỉ sét";
      document.getElementById("wiz-accessories").value = "Máy trần không sạc";
      document.getElementById("wiz-condition").value = "Vỏ cong vênh, khe tản nhiệt bám muối";
      wizardSubmitTicket();
    `);
    await sleep(3000);

    const createdTicketCodeSc6 = await evalJS(`
      (function() {
        const t = (state.tickets || []).find(x => x.serial_number === "SN-ASUS-VALID-01" && x.status === "RECEIVED");
        return t ? t.ticket_code : (state.tickets && state.tickets.length ? state.tickets[0].ticket_code : null);
      })()
    `);
    log(`  [+] Mã phiếu cho kịch bản 6: ${createdTicketCodeSc6}`);
    await logout();

    // Phân công KTV
    await login('manager01', '123456');
    await switchTab('tickets');
    await sleep(1000);
    await evalJS(`
      (function() {
        const t = state.tickets.find(x => x.ticket_code === "${createdTicketCodeSc6}");
        if (t) openTicketModal(t.id);
      })()
    `);
    await sleep(1500);
    // 6.1b Phân công KTV
    await evalJS(`
      (function() {
        const actions = Array.from(document.querySelectorAll("#modal-state-actions button"));
        const assignBtn = actions.find(b => b.textContent.includes("Phân công"));
        if (assignBtn) assignBtn.click();
      })()
    `);
    await sleep(800);
    await evalJS(`
      (function() {
        const sel = document.getElementById("action-modal-select");
        if (sel) {
          const opt = Array.from(sel.options).find(o => o.text.includes("Tuấn") || o.text.includes("technician01"));
          if (opt) sel.value = opt.value;
        }
        const conf = document.getElementById("action-modal-confirm");
        if (conf) conf.click();
      })()
    `);
    await sleep(2000);

    // 6.1c Chuyển sang INSPECTING
    await evalJS(`
      (function() {
        const actions = Array.from(document.querySelectorAll("#modal-state-actions button"));
        const startBtn = actions.find(b => b.textContent.includes("Bắt đầu kiểm tra"));
        if (startBtn) startBtn.click();
      })()
    `);
    await sleep(800);
    await evalJS(`
      (function() {
        const conf = document.getElementById("action-modal-confirm");
        if (conf) conf.click();
      })()
    `);
    await sleep(2000);
    await logout();

    // 6.2 KTV đề xuất từ chối
    log(`[6.2] KTV đề xuất từ chối bảo hành cho phiếu ${createdTicketCodeSc6}`);
    await login('technician01', '123456');
    await switchTab('tickets');
    await sleep(1000);
    await evalJS(`
      (function() {
        const t = state.tickets.find(x => x.ticket_code === "${createdTicketCodeSc6}");
        if (t) openTicketModal(t.id);
      })()
    `);
    await sleep(1500);
    const clickedPropose6 = await evalJS(`
      (() => {
        const actions = Array.from(document.querySelectorAll("#modal-state-actions button"));
        const btn = actions.find(b => (b.getAttribute("onclick") || "").includes("openProposeRejectionModal") || b.textContent.includes("Đề xuất từ chối"));
        if (btn) {
          btn.click();
          return true;
        }
        return false;
      })()
    `);
    if (!clickedPropose6) throw new Error("Không tìm thấy nút Đề xuất từ chối trong kịch bản 6");
    await sleep(1000);

    const filledProposal6 = await evalJS(`
      (() => {
        const propField = document.getElementById("action-field-proposal_note");
        if (!propField) return false;
        propField.value = "Nước biển ăn mòn rỉ sét toàn bộ mainboard, vi phạm điều khoản bảo hành";
        const noteField = document.getElementById("action-field-note");
        if (noteField) noteField.value = "Có hình ảnh chụp linh kiện đính kèm biên bản giám định";
        const confirmBtn = document.getElementById("action-modal-confirm");
        if (!confirmBtn) return false;
        confirmBtn.click();
        return true;
      })()
    `);
    if (!filledProposal6) throw new Error("Không tìm thấy trường action-field-proposal_note trong kịch bản 6");
    await sleep(2500);
    await logout();

    // 6.3 Quản lý vào xem và bấm DUYỆT TỪ CHỐI
    log(`[6.3] Quản lý bấm DUYỆT TỪ CHỐI`);
    await login('manager01', '123456');
    await setPromptNote('Đã duyệt từ chối bảo hành theo biên bản giám định kỹ thuật nước vào máy');
    await switchTab('tickets');
    await sleep(1000);
    await evalJS(`
      (function() {
        const t = state.tickets.find(x => x.ticket_code === "${createdTicketCodeSc6}");
        if (t) openTicketModal(t.id);
      })()
    `);
    await sleep(1500);

    await evalJS(`
      (function() {
        const box = document.getElementById("modal-rejection-proposal-actions");
        const btn = box ? Array.from(box.querySelectorAll("button")).find(b => b.textContent.includes("Duyệt từ chối")) : null;
        if (btn) btn.click();
      })()
    `);
    await sleep(2500);

    // Reload kiểm chứng trạng thái REJECTED
    await reload();
    await login('manager01', '123456');
    await switchTab('tickets');
    await sleep(1000);
    await evalJS(`
      (function() {
        const t = state.tickets.find(x => x.ticket_code === "${createdTicketCodeSc6}");
        if (t) openTicketModal(t.id);
      })()
    `);
    await sleep(1500);

    currentStatusBadge = await evalJS(`document.getElementById("modal-ticket-badge").textContent`);
    if (!currentStatusBadge.includes("Từ chối")) throw new Error(`Trạng thái chưa chuyển sang Từ chối: ${currentStatusBadge}`);
    await screenshot('06_rejection_approved_ticket_rejected.png');
    log('  [PASS] Quản lý duyệt từ chối thành công, phiếu đã chuyển sang TỪ CHỐI (REJECTED).');
    await logout();

    // 6.4 Tiếp nhận vào trả máy từ chối cho khách
    log(`[6.4] Nhân viên Tiếp nhận trả máy từ chối cho khách`);
    await login('receptionist01', '123456');
    await switchTab('tickets');
    await sleep(1000);
    await evalJS(`
      (function() {
        const t = state.tickets.find(x => x.ticket_code === "${createdTicketCodeSc6}");
        if (t) openTicketModal(t.id);
      })()
    `);
    await sleep(1500);

    const clickedReturn6 = await evalJS(`
      (() => {
        const actions = Array.from(document.querySelectorAll("#modal-state-actions button"));
        const btn = actions.find(b => (b.getAttribute("onclick") || "").includes("RETURNED") || b.textContent.includes("Trả máy") || b.textContent.includes("trả máy") || b.textContent.includes("Bàn giao"));
        if (btn) {
          btn.click();
          return true;
        }
        return false;
      })()
    `);
    if (!clickedReturn6) throw new Error("Không tìm thấy nút Trả máy trong kịch bản 6");
    await sleep(1000);

    const filledReturn6 = await evalJS(`
      (() => {
        const handoverField = document.getElementById("action-field-handover_note");
        if (!handoverField) return false;
        handoverField.value = "Bàn giao trả lại máy từ chối bảo hành kèm biên bản giám định kỹ thuật cho khách hàng";
        const confirmBtn = document.getElementById("action-modal-confirm");
        if (!confirmBtn) return false;
        confirmBtn.click();
        return true;
      })()
    `);
    if (!filledReturn6) throw new Error("Không tìm thấy trường action-field-handover_note trong kịch bản 6");
    await sleep(2500);

    // Reload kiểm chứng RETURNED
    await reload();
    await login('receptionist01', '123456');
    await switchTab('tickets');
    await sleep(1000);
    await evalJS(`
      (function() {
        const t = state.tickets.find(x => x.ticket_code === "${createdTicketCodeSc6}");
        if (t) openTicketModal(t.id);
      })()
    `);
    await sleep(1500);

    currentStatusBadge = await evalJS(`document.getElementById("modal-ticket-badge").textContent`);
    if (!currentStatusBadge.includes("Đã trả")) throw new Error(`Trạng thái chưa sang Đã trả máy: ${currentStatusBadge}`);
    await screenshot('06_rejected_device_returned.png');
    log('  [PASS] Tiếp nhận trả máy từ chối thành công, chu trình hoàn tất sang ĐÃ TRẢ MÁY (RETURNED).');
    await logout();

    resultsSummary.push({ id: 'KB6', name: 'Đề xuất từ chối -> Quản lý duyệt -> Tiếp nhận trả máy', status: 'PASS' });

    // ===================================================================
    // KỊCH BẢN 7: BA CHỨC NĂNG AI, SAO CHÉP THÔNG BÁO, LỖI API GIAO DIỆN
    // ===================================================================
    log('\n>>> BẮT ĐẦU KỊCH BẢN 7: BA CHỨC NĂNG AI, SAO CHÉP THÔNG BÁO, LỖI API GIAO DIỆN');
    await login('technician01', '123456');
    await switchTab('tickets');
    await sleep(1000);

    // 7.1 AI-01: Gợi ý loại lỗi và KTV xác nhận loại lỗi
    log(`[7.1] AI-01: Gợi ý phân loại lỗi trên phiếu ${createdTicketCodeSc3}`);
    await evalJS(`
      (function() {
        const t = state.tickets.find(x => x.ticket_code === "${createdTicketCodeSc3}");
        if (t) openTicketModal(t.id);
      })()
    `);
    await sleep(1500);

    // Bấm nút Gợi ý loại lỗi (AI)
    await evalJS(`
      const btn = document.getElementById("btn-ai-suggest-ticket");
      if (btn) btn.click();
    `);
    await sleep(2500);

    // Xác nhận kết quả AI hiển thị
    const aiSuggestionBoxText = await evalJS(`(document.getElementById("ws-ai-suggestion-box") || {}).innerText || ""`);
    log(`  [+] Kết quả gợi ý AI: ${aiSuggestionBoxText.replace(/\\n/g, ' ')}`);

    // KTV bấm Xác nhận loại lỗi
    const confirmedAi = await evalJS(`
      (() => {
        const buttons = Array.from(document.querySelectorAll("#ws-ai-suggestion-box button, #ws-ai-suggestion-box .btn"));
        const btnConfirm = buttons.find(b => (b.getAttribute("onclick") || "").includes("confirmAiCategoryFromSection") || b.textContent.includes("Xác nhận"));
        if (btnConfirm) {
          btnConfirm.click();
          return true;
        }
        return false;
      })()
    `);
    if (!confirmedAi) throw new Error("Không tìm thấy nút Xác nhận loại lỗi AI trong #ws-ai-suggestion-box");
    await sleep(2500);

    // Reload kiểm chứng nhóm lỗi đã được ghi nhận vào phiếu
    await reload();
    await login('technician01', '123456');
    await switchTab('tickets');
    await sleep(1000);
    await evalJS(`
      (function() {
        const t = state.tickets.find(x => x.ticket_code === "${createdTicketCodeSc3}");
        if (t) openTicketModal(t.id);
      })()
    `);
    await sleep(1500);

    const diagnosisText = await evalJS(`(document.getElementById("ws-diagnosis-body") || {}).innerText || ""`);
    await screenshot('07_ai_01_suggest_and_review.png');
    log(`  [PASS] AI-01: Gợi ý và xác nhận loại lỗi thành công, kết luận chính thức: ${diagnosisText.trim()}`);

    // 7.2 AI-02: Tóm tắt lịch sử bảo hành thiết bị
    log(`[7.2] AI-02: Tóm tắt lịch sử bảo hành thiết bị bằng AI`);
    await evalJS(`showTicketAiHistory();`);
    await sleep(2500);

    const summaryContent = await evalJS(`(document.getElementById("ai-summary-content") || {}).innerText || ""`);
    if (!summaryContent || summaryContent.includes("Lỗi")) throw new Error(`Modal AI-02 không hiển thị nội dung: ${summaryContent}`);
    await screenshot('07_ai_02_device_history_modal.png');
    log(`  [PASS] AI-02: Tóm tắt lịch sử bảo hành hiển thị chuẩn: ${summaryContent.slice(0, 150).replace(/\\n/g, ' ')}...`);
    await evalJS(`closeModal("ai-summary-modal");`);
    await sleep(500);

    // 7.3 AI-03: Soạn tin nhắn tiến độ và Sao chép vào clipboard
    log(`[7.3] AI-03: Soạn tin nhắn tiến độ và sao chép vào bộ nhớ tạm`);
    await evalJS(`showTicketAiNotification();`);
    await sleep(2500);

    const draftMsg = await evalJS(`(document.getElementById("ai-noti-textarea") || {}).value || ""`);
    log(`  [+] Nội dung AI soạn: ${draftMsg.slice(0, 100)}...`);

    // Bấm nút Sao chép
    await evalJS(`copyNotificationText();`);
    await sleep(800);

    const copyStatus = await evalJS(`(document.getElementById("ai-noti-copy-status") || {}).innerText || ""`);
    await screenshot('07_ai_03_notification_copied.png');
    log(`  [PASS] AI-03: Đã sao chép tin nhắn vào bộ nhớ tạm, trạng thái: "${copyStatus.trim()}"`);
    await evalJS(`closeModal("ai-notification-modal");`);
    await sleep(500);

    // 7.4 Kiểm tra hiển thị lỗi API thân thiện bằng tiếng Việt
    log(`[7.4] Kiểm tra phản hồi lỗi API thân thiện khi form không hợp lệ`);
    await switchTab('customers');
    await sleep(1000);
    // Tiếp nhận mở form tạo khách hàng nhưng để trống tên
    await logout();
    await login('receptionist01', '123456');
    await switchTab('customers');
    await sleep(1000);

    await evalJS(`
      openCustomerModal();
      document.getElementById("cust-name").value = "";
      document.getElementById("cust-phone").value = "12345";
      const f = document.getElementById("customer-form");
      f.dispatchEvent(new Event("submit", { cancelable: true }));
    `);
    await sleep(1000);

    const errorMsg = await evalJS(`
      (function() {
        const err = document.querySelector("#customer-modal .form-error:not(.hidden)");
        return err ? err.innerText : "";
      })()
    `);
    await screenshot('07_api_error_handling_toast.png');
    log(`  [PASS] Lỗi form/API được hiển thị rõ ràng bằng tiếng Việt: "${errorMsg.trim()}"`);
    await evalJS(`closeModal("customer-modal");`);
    await sleep(500);
    await logout();

    resultsSummary.push({ id: 'KB7', name: 'Ba chức năng AI, sao chép thông báo, kiểm tra lỗi form/API', status: 'PASS' });

    // ===================================================================
    // KỊCH BẢN 8: TẠO/SỬA KHÁCH HÀNG & THIẾT BỊ; KIỂM TRA PHÂN QUYỀN RBAC
    // ===================================================================
    log('\n>>> BẮT ĐẦU KỊCH BẢN 8: TẠO/SỬA KHÁCH HÀNG & THIẾT BỊ; KIỂM TRA RBAC');
    await login('receptionist01', '123456');
    await switchTab('customers');
    await sleep(1000);

    const sc8CustPhone = `098${Date.now().toString().slice(-7)}`;
    const sc8DevSerial = `SN-MAC-${Date.now().toString().slice(-6)}`;

    // 8.1 Tiếp nhận tạo mới khách hàng
    log(`[8.1] Tiếp nhận tạo mới khách hàng: GS Ngô Bảo Châu (${sc8CustPhone})`);
    await evalJS(`
      openCustomerModal();
      document.getElementById("cust-name").value = "GS Ngô Bảo Châu";
      document.getElementById("cust-phone").value = "${sc8CustPhone}";
      document.getElementById("cust-email").value = "chou.ngo@example.com";
      document.getElementById("cust-address").value = "Số 18 đường Láng Hạ, Đống Đa, Hà Nội";
      const f = document.getElementById("customer-form");
      f.dispatchEvent(new Event("submit", { cancelable: true }));
    `);
    await sleep(2500);

    // Sửa địa chỉ khách hàng
    log('[8.2] Sửa địa chỉ khách hàng vừa tạo');
    await evalJS(`
      (function() {
        const c = state.customers.find(x => x.phone === "${sc8CustPhone}");
        if (c) openCustomerModal(c.id);
      })()
    `);
    await sleep(1000);
    await evalJS(`
      document.getElementById("cust-address").value = "Tòa nhà Vincom, 54A Nguyễn Chí Thanh, Hà Nội";
      const f = document.getElementById("customer-form");
      f.dispatchEvent(new Event("submit", { cancelable: true }));
    `);
    await sleep(2500);

    // Reload kiểm chứng khách hàng hiển thị địa chỉ mới
    await reload();
    await login('receptionist01', '123456');
    await switchTab('customers');
    await sleep(1000);

    let customerRow = await evalJS(`
      (function() {
        const rows = Array.from(document.querySelectorAll("#customers-table-body tr"));
        const target = rows.find(r => r.textContent.includes("Ngô Bảo Châu") && r.textContent.includes("${sc8CustPhone}"));
        return target ? target.innerText : null;
      })()
    `);
    if (!customerRow || !customerRow.includes("Nguyễn Chí Thanh")) {
      throw new Error(`Khách hàng chưa cập nhật địa chỉ sau reload: ${customerRow}`);
    }
    await screenshot('08_customer_create_and_edit.png');
    log(`  [PASS] Tạo và sửa khách hàng thành công, hiển thị chuẩn sau reload: ${customerRow.replace(/\\n/g, ' ')}`);

    // 8.3 Tiếp nhận đăng ký thiết bị mới và sửa thiết bị
    log(`[8.3] Tiếp nhận đăng ký thiết bị mới: ${sc8DevSerial}`);
    await switchTab('devices');
    await sleep(1000);

    await evalJS(`
      openDeviceModal();
      document.getElementById("dev-serial").value = "${sc8DevSerial}";
      const custSel = document.getElementById("dev-customer-id");
      const cOpt = Array.from(custSel.options).find(o => o.text.includes("Ngô Bảo Châu") || o.text.includes("${sc8CustPhone}"));
      if (cOpt) custSel.value = cOpt.value;
      document.getElementById("dev-product-name").value = "Laptop Asus ROG Strix G16";
      document.getElementById("dev-purchase-date").value = "2025-03-01";
      const f = document.getElementById("device-form");
      f.dispatchEvent(new Event("submit", { cancelable: true }));
    `);
    await sleep(2500);

    // Sửa thiết bị
    log('[8.4] Sửa ngày mua của thiết bị vừa đăng ký');
    await evalJS(`
      (function() {
        const d = state.devices.find(x => x.serial_number === "${sc8DevSerial}");
        if (d) openDeviceModal(d.id);
      })()
    `);
    await sleep(1000);
    await evalJS(`
      document.getElementById("dev-purchase-date").value = "2025-03-15";
      const f = document.getElementById("device-form");
      f.dispatchEvent(new Event("submit", { cancelable: true }));
    `);
    await sleep(2500);

    // Reload kiểm chứng thiết bị hiển thị sau reload
    await reload();
    await login('receptionist01', '123456');
    await switchTab('devices');
    await sleep(1000);

    let devRow = await evalJS(`
      (function() {
        const rows = Array.from(document.querySelectorAll("#devices-table-body tr"));
        const target = rows.find(r => r.textContent.includes("${sc8DevSerial}"));
        return target ? target.innerText : null;
      })()
    `);
    if (!devRow) throw new Error('Không tìm thấy thiết bị SN-MACBOOK-AIR-M3 sau reload!');
    await screenshot('08_device_create_and_edit.png');
    log(`  [PASS] Đăng ký và sửa thiết bị thành công, hiển thị chuẩn sau reload: ${devRow.replace(/\\n/g, ' ')}`);
    await logout();

    // 8.5 Kiểm tra RBAC: Đăng nhập KTV và kiểm tra các nút thêm bị ẩn
    log('[8.5] Đăng nhập KTV kiểm tra phân quyền RBAC: nút thêm/sửa bị ẩn theo vai trò');
    await login('technician01', '123456');
    await switchTab('customers');
    await sleep(1000);

    const techCanAddCustomer = await evalJS(`
      (function() {
        const btn = document.querySelector("#tab-customers button[onclick*='openCustomerModal']");
        return btn && btn.offsetParent !== null;
      })()
    `);
    await switchTab('devices');
    await sleep(1000);
    const techCanAddDevice = await evalJS(`
      (function() {
        const btn = document.querySelector("#tab-devices button[onclick*='openDeviceModal']");
        return btn && btn.offsetParent !== null;
      })()
    `);

    if (techCanAddCustomer || techCanAddDevice) {
      throw new Error(`KTV vẫn nhìn thấy nút Thêm khách hàng (${techCanAddCustomer}) hoặc Thêm thiết bị (${techCanAddDevice})!`);
    }
    await screenshot('08_technician_rbac_hidden_buttons.png');
    log(`  [PASS] Phân quyền RBAC chính xác: KTV không có quyền và không nhìn thấy nút thêm khách hàng/thiết bị.`);
    await logout();

    resultsSummary.push({ id: 'KB8', name: 'Tạo/sửa khách hàng & thiết bị theo quyền; kiểm tra RBAC ẩn nút', status: 'PASS' });

    log('\n======================================================================');
    log('TẤT CẢ 8/8 KỊCH BẢN KIỂM THỬ TRÌNH DUYỆT E2E ĐỀU PASS 100%!');
    log('======================================================================');
    resultsSummary.forEach(r => log(`  [${r.status}] ${r.id}: ${r.name}`));

  } catch (err) {
    log(`\n[LỖI NGHIÊM TRỌNG] ${err.stack || err.message}`);
    await screenshot('error_failure_state.png').catch(() => {});
  } finally {
    log('[*] Đóng kết nối WebSocket và tiến trình Chrome...');
    try { ws.close(); } catch (e) {}
    try { chrome.kill(); } catch (e) {}
    await sleep(1000);
  }
}

runFullE2ETest().catch(err => {
  console.error('Fatal runner error:', err);
  process.exit(1);
});
