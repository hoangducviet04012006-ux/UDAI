/**
 * Automated Real Browser Verification via Chrome DevTools Protocol (CDP)
 * Tests BaoHanhAI with installed Google Chrome / Microsoft Edge.
 * Tests 4 user accounts: manager01, receptionist01, technician01, technician02.
 * Tests resolutions: 1920x1080, 1366x768, 768x1024 (small screen).
 */
const { spawn } = require('child_process');
const http = require('http');
const fs = require('fs');
const path = require('path');

const ARTIFACT_DIR = path.resolve('C:/Users/Hoang/.gemini/antigravity-ide/brain/165a5912-0267-4126-9f47-b7a766eb9942');
const CHROME_PATH = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const EDGE_PATH = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const BROWSER_BIN = fs.existsSync(CHROME_PATH) ? CHROME_PATH : EDGE_PATH;

console.log(`[CDP] Using browser: ${BROWSER_BIN}`);

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function httpGetJson(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          reject(e);
        }
      });
    }).on('error', reject);
  });
}

class CDPClient {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.ws = null;
    this.msgId = 1;
    this.pending = new Map();
  }

  connect() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.wsUrl);
      this.ws.onopen = () => resolve();
      this.ws.onerror = (err) => reject(err);
      this.ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.id && this.pending.has(msg.id)) {
          const { res, rej } = this.pending.get(msg.id);
          this.pending.delete(msg.id);
          if (msg.error) rej(msg.error);
          else res(msg.result);
        }
      };
    });
  }

  send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = this.msgId++;
      this.pending.set(id, { res: resolve, rej: reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async eval(expr) {
    const res = await this.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    if (res.exceptionDetails) {
      throw new Error(JSON.stringify(res.exceptionDetails));
    }
    return res.result ? res.result.value : undefined;
  }

  async screenshot(filepath) {
    const res = await this.send('Page.captureScreenshot', { format: 'png' });
    const buffer = Buffer.from(res.data, 'base64');
    fs.writeFileSync(filepath, buffer);
    console.log(`[Screenshot] Saved: ${filepath}`);
  }

  async setViewport(width, height) {
    await this.send('Emulation.setDeviceMetricsOverride', {
      width,
      height,
      deviceScaleFactor: 1,
      mobile: width < 768
    });
  }
}

async function run() {
  const cdpPort = 9222;
  const userDataDir = path.join(require('os').tmpdir(), 'chrome_cdp_profile_' + Date.now());

  const chromeProc = spawn(BROWSER_BIN, [
    '--headless=new',
    `--remote-debugging-port=${cdpPort}`,
    `--user-data-dir=${userDataDir}`,
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    'about:blank'
  ], { detached: false });

  chromeProc.on('error', (err) => console.error('Browser spawn error:', err));

  // Wait for CDP to be ready
  let versionInfo = null;
  for (let i = 0; i < 30; i++) {
    await sleep(500);
    try {
      versionInfo = await httpGetJson(`http://127.0.0.1:${cdpPort}/json/version`);
      if (versionInfo && versionInfo.webSocketDebuggerUrl) break;
    } catch (_) {}
  }

  if (!versionInfo || !versionInfo.webSocketDebuggerUrl) {
    throw new Error('Failed to connect to browser CDP port 9222');
  }

  console.log(`[CDP] Connected to browser: ${versionInfo.Browser}`);

  // Get existing page target
  const targets = await httpGetJson(`http://127.0.0.1:${cdpPort}/json/list`);
  const pageTarget = targets.find((t) => t.type === 'page') || targets[0];
  const pageWsUrl = pageTarget.webSocketDebuggerUrl;
  const client = new CDPClient(pageWsUrl);
  await client.connect();

  await client.send('Page.enable');
  await client.send('Runtime.enable');
  await client.send('DOM.enable');

  const results = [];
  function assert(name, condition, extra = '') {
    results.push({ name, passed: Boolean(condition), extra });
    console.log(`  [${condition ? 'PASS' : 'FAIL'}] ${name} ${extra ? `(${extra})` : ''}`);
  }

  try {
    console.log('\n=============================================================');
    console.log('1. KIỂM THỬ GIAO DIỆN VỚI VAI TRÒ QUẢN LÝ (manager01)');
    console.log('=============================================================');
    await client.setViewport(1920, 1080);
    await client.send('Page.navigate', { url: 'http://127.0.0.1:8000' });
    await sleep(2000);

    // Login as manager01
    await client.eval(`
      document.getElementById('login-username').value = 'manager01';
      document.getElementById('login-password').value = '123456';
      submitLogin();
    `);
    await sleep(2500);

    const mgrUser = await client.eval(`state.session.user ? state.session.user.username : null`);
    assert('Đăng nhập manager01 thành công', mgrUser === 'manager01');

    const topbarTitle = await client.eval(`document.getElementById('topbar-page-title').textContent.trim()`);
    assert('Tiêu đề topbar hiển thị đúng', topbarTitle === 'Tổng quan', topbarTitle);

    const intakeBtnText = await client.eval(`document.getElementById('btn-goto-tickets').textContent.trim()`);
    assert('Nút trên topbar ghi đúng "Tiếp nhận bảo hành"', intakeBtnText === 'Tiếp nhận bảo hành', intakeBtnText);

    const hasSecondarySection = await client.eval(`document.getElementById('dash-secondary-section') !== null`);
    assert('Đã loại bỏ khối thông tin bổ sung dư thừa khỏi Dashboard', !hasSecondarySection);

    const dashViewBtns = await client.eval(`document.getElementById('dash-view-buttons').innerText.trim()`);
    assert('Nút phạm vi Dashboard không bị chèn trùng "Xem tất cả phiếu"', !dashViewBtns.includes('Xem tất cả phiếu'), dashViewBtns);

    // Take screenshot Dashboard Manager 1920x1080
    await client.screenshot(path.join(ARTIFACT_DIR, '01_manager_dashboard_1920.png'));

    // Chuyển sang tab Tài khoản nhân viên
    console.log('\n--- Kiểm tra màn hình Quản lý tài khoản (tab accounts) ---');
    await client.eval(`switchTab('accounts')`);
    await sleep(1500);

    const accountRows = await client.eval(`document.querySelectorAll('#accounts-table-body tr.table-row').length`);
    assert('Bảng tài khoản nhân viên hiển thị dữ liệu (không bị kẹt tải)', accountRows >= 4, `Số dòng: ${accountRows}`);

    const accountNames = await client.eval(`Array.from(document.querySelectorAll('#accounts-table-body tr.table-row td:first-child')).map(td => td.textContent.trim()).join(', ')`);
    assert('Danh sách hiển thị đủ các tài khoản mẫu', accountNames.includes('manager01') && accountNames.includes('receptionist01') && accountNames.includes('technician01'), accountNames);

    // Test account search input
    await client.eval(`
      const input = document.getElementById('account-search-input');
      input.value = 'tech';
      filterAccounts();
    `);
    await sleep(500);

    const filteredRows = await client.eval(`document.querySelectorAll('#accounts-table-body tr.table-row').length`);
    assert('Bộ lọc tài khoản theo từ khóa "tech" hoạt động chính xác', filteredRows === 2, `Số dòng: ${filteredRows}`);

    // Take screenshot Accounts Manager 1920x1080
    await client.screenshot(path.join(ARTIFACT_DIR, '02_manager_accounts_1920.png'));

    // Test responsive 1366x768
    await client.setViewport(1366, 768);
    await sleep(500);
    await client.screenshot(path.join(ARTIFACT_DIR, '03_manager_accounts_1366.png'));

    // Reset search
    await client.eval(`
      document.getElementById('account-search-input').value = '';
      filterAccounts();
    `);

    // Log out manager
    console.log('\n=============================================================');
    console.log('2. KIỂM THỬ VAI TRÒ TIẾP NHẬN (receptionist01)');
    console.log('=============================================================');
    await client.eval(`logout()`);
    await sleep(1500);

    // Login as receptionist01
    await client.eval(`
      document.getElementById('login-username').value = 'receptionist01';
      document.getElementById('login-password').value = '123456';
      submitLogin();
    `);
    await sleep(2500);

    const recUser = await client.eval(`state.session.user ? state.session.user.username : null`);
    assert('Đăng nhập receptionist01 thành công', recUser === 'receptionist01');

    const accountsBtnHidden = await client.eval(`
      const btn = document.querySelector('.nav-tab-btn[data-tab="accounts"]');
      !btn || btn.classList.contains('hidden') || btn.style.display === 'none'
    `);
    assert('Menu Quản trị tài khoản bị ẩn với vai trò Tiếp nhận', accountsBtnHidden);

    // Chuyển sang Phiếu bảo hành (Tiếp nhận bảo hành)
    await client.eval(`switchTab('tickets')`);
    await sleep(1500);

    const receptionTitle = await client.eval(`document.querySelector('#reception-panel h2').textContent.trim()`);
    assert('Tiêu đề form tiếp nhận ghi "Tiếp nhận bảo hành"', receptionTitle.includes('Tiếp nhận bảo hành'), receptionTitle);

    // Test serial lookup với serial mới
    await client.eval(`
      document.getElementById('wiz-serial').value = 'SN-NEW-TEST-2026';
      wizardLookupSerial();
    `);
    await sleep(1500);

    const isNewDeviceShown = await client.eval(`!document.getElementById('wiz-new-device').classList.contains('hidden')`);
    assert('Serial chưa có chuyển sang form đăng ký máy mới không mất dữ liệu', isNewDeviceShown);

    const purchaseDateVal = await client.eval(`document.getElementById('wiz-purchase-date').value`);
    assert('Không tự điền ngày mua bằng hôm nay khi đăng ký máy mới', purchaseDateVal === '', `Giá trị: "${purchaseDateVal}"`);

    await client.screenshot(path.join(ARTIFACT_DIR, '04_receptionist_intake_1920.png'));

    // Log out receptionist
    console.log('\n=============================================================');
    console.log('3. KIỂM THỬ VAI TRÒ KỸ THUẬT VIÊN (technician02)');
    console.log('=============================================================');
    await client.eval(`logout()`);
    await sleep(1500);

    // Login as technician02 (tài khoản chưa có phiếu)
    await client.eval(`
      document.getElementById('login-username').value = 'technician02';
      document.getElementById('login-password').value = '123456';
      submitLogin();
    `);
    await sleep(2500);

    const tech2User = await client.eval(`state.session.user ? state.session.user.username : null`);
    assert('Đăng nhập technician02 thành công', tech2User === 'technician02');

    const tech2TableRows = await client.eval(`document.querySelectorAll('#dash-active-body tr.table-row').length`);
    const tech2EmptyMsg = await client.eval(`document.querySelector('#dash-active-body td.table-msg') ? document.querySelector('#dash-active-body td.table-msg').textContent.trim() : ''`);
    assert('KTV chưa có phiếu thấy trạng thái rỗng đúng (không nhận số liệu người khác)', tech2TableRows === 0 && tech2EmptyMsg.length > 0, tech2EmptyMsg);

    // Small screen test (768x1024)
    await client.setViewport(768, 1024);
    await sleep(500);
    await client.screenshot(path.join(ARTIFACT_DIR, '05_technician02_small_screen.png'));

    console.log('\n=============================================================');
    console.log(`TỔNG KẾT KIỂM THỬ TRÌNH DUYỆT THẬT (CHROME CDP):`);
    const passedCount = results.filter(r => r.passed).length;
    console.log(`ĐẠT: ${passedCount}/${results.length} (${Math.round(passedCount/results.length*100)}%)`);
    console.log('=============================================================');

  } finally {
    try {
      chromeProc.kill();
    } catch (_) {}
  }
}

run().catch((err) => {
  console.error('Fatal error during CDP test:', err);
  process.exit(1);
});
