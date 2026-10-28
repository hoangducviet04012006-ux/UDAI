const { spawn } = require('child_process');
const http = require('http');
const fs = require('fs');
const path = require('path');

const CHROME_PATH = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const EDGE_PATH = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const BROWSER_BIN = fs.existsSync(CHROME_PATH) ? CHROME_PATH : EDGE_PATH;
const BASE_URL = 'http://127.0.0.1:8088';
const OUT_DIR = path.resolve(__dirname, '../docs/evidence/redesign');

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function httpGetJson(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); } catch (e) { reject(e); }
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
  const cdpPort = 9226;
  const userDataDir = path.join(require('os').tmpdir(), 'chrome_cdp_real_after_' + Date.now());

  const chromeProc = spawn(BROWSER_BIN, [
    '--headless=new',
    `--remote-debugging-port=${cdpPort}`,
    `--user-data-dir=${userDataDir}`,
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    'about:blank'
  ]);

  for (let i = 0; i < 30; i++) {
    await sleep(400);
    try {
      const v = await httpGetJson(`http://127.0.0.1:${cdpPort}/json/version`);
      if (v && v.webSocketDebuggerUrl) break;
    } catch (_) {}
  }

  const targets = await httpGetJson(`http://127.0.0.1:${cdpPort}/json/list`);
  const pageTarget = targets.find((t) => t.type === 'page') || targets[0];
  const client = new CDPClient(pageTarget.webSocketDebuggerUrl);
  await client.connect();

  await client.send('Page.enable');
  await client.send('Runtime.enable');
  await client.send('DOM.enable');

  async function login(username, password = '123456') {
    await client.eval(`(() => {
      localStorage.clear();
      sessionStorage.clear();
      window.location.reload();
    })()`);
    await sleep(1000);
    await client.eval(`(() => {
      const u = document.getElementById('login-username');
      const p = document.getElementById('login-password');
      if (u) { u.value = '${username}'; u.dispatchEvent(new Event('input')); }
      if (p) { p.value = '${password}'; p.dispatchEvent(new Event('input')); }
      const f = document.getElementById('login-form');
      if (f) f.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
    })()`);
    await sleep(2200);
  }

  console.log('[CDP] Capturing REAL AFTER screenshots...');

  // ================= 1. VIEWPORT 1920x1080 (DESKTOP) =================
  await client.setViewport(1920, 1080);
  await client.send('Page.navigate', { url: BASE_URL });
  await sleep(1200);

  // 1.1 Overview (Manager) 1920x1080
  await login('manager01', '123456');
  await client.eval(`document.querySelector('.nav-tab-btn[data-tab="dashboard"]').click()`);
  await sleep(1500);
  await client.screenshot(path.join(OUT_DIR, 'after_01_overview_1920.png'));

  // 1.2 Accounts (Manager) 1920x1080
  await client.eval(`document.querySelector('.nav-tab-btn[data-tab="accounts"]').click()`);
  await sleep(1500);
  await client.screenshot(path.join(OUT_DIR, 'after_05_accounts_1920.png'));

  // 1.3 Tickets List (Receptionist) 1920x1080
  await login('receptionist01', '123456');
  await client.eval(`document.querySelector('.nav-tab-btn[data-tab="tickets"]').click()`);
  await sleep(1500);
  // Ensure reception panel is collapsed to show pure tickets list
  await client.eval(`(() => {
    const p = document.getElementById('reception-panel');
    if (p && !p.classList.contains('hidden')) document.getElementById('btn-toggle-reception')?.click();
  })()`);
  await sleep(600);
  await client.screenshot(path.join(OUT_DIR, 'after_02_tickets_1920.png'));

  // 1.4 Intake Wizard (Receptionist) 1920x1080
  await client.eval(`(() => {
    const p = document.getElementById('reception-panel');
    if (p && p.classList.contains('hidden')) document.getElementById('btn-toggle-reception')?.click();
  })()`);
  await sleep(1000);
  await client.screenshot(path.join(OUT_DIR, 'after_03_intake_1920.png'));

  // 1.5 Ticket Detail (Technician) 1920x1080
  await login('technician01', '123456');
  await client.eval(`document.querySelector('.nav-tab-btn[data-tab="tickets"]').click()`);
  await sleep(1500);
  await client.eval(`(() => {
    const btn = document.querySelector('#tickets-table-body button[onclick*="viewTicketDetail"]') || 
                document.querySelector('#tickets-table-body button[onclick*="openTicketModal"]') ||
                document.querySelector('#tickets-table-body tr button');
    if (btn) btn.click();
  })()`);
  await sleep(1500);
  await client.screenshot(path.join(OUT_DIR, 'after_04_ticket_detail_1920.png'));
  await client.eval(`(() => { window.closeTicketModal && window.closeTicketModal(); if (window.closeModal) window.closeModal('ticket-modal'); })()`);
  await sleep(600);

  // 1.6 Chatbot window open (1920x1080)
  await client.eval(`(() => {
    const launch = document.querySelector('.bh-launch') || document.getElementById('btn-bh-support');
    if (launch) launch.click();
  })()`);
  await sleep(1200);
  await client.screenshot(path.join(OUT_DIR, 'after_06_chatbot_1920.png'));

  // ================= 2. VIEWPORT 1366x768 (LAPTOP) =================
  console.log('[CDP] Capturing 1366x768 screenshots...');
  await client.setViewport(1366, 768);
  await sleep(600);
  await client.eval(`(() => {
    const panel = document.getElementById('bh-support');
    if (panel && !panel.hidden) panel.hidden = true;
    const launch = document.querySelector('.bh-launch');
    if (launch) launch.setAttribute('aria-expanded', 'false');
  })()`);
  await sleep(500);
  await client.screenshot(path.join(OUT_DIR, 'after_09_tickets_1366.png'));

  await login('manager01', '123456');
  await client.eval(`document.querySelector('.nav-tab-btn[data-tab="dashboard"]').click()`);
  await sleep(1200);
  await client.screenshot(path.join(OUT_DIR, 'after_08_overview_1366.png'));

  // ================= 3. VIEWPORT 390x844 (MOBILE PHONE) =================
  console.log('[CDP] Capturing 390x844 screenshots...');
  await client.setViewport(390, 844);
  await sleep(1000);
  await client.screenshot(path.join(OUT_DIR, 'after_10_overview_mobile_390.png'));

  // Open Chatbot on mobile
  await client.eval(`(() => {
    const launch = document.querySelector('.bh-launch') || document.getElementById('btn-bh-support');
    if (launch) launch.click();
  })()`);
  await sleep(1200);
  await client.screenshot(path.join(OUT_DIR, 'after_07_chatbot_mobile_390.png'));

  console.log('[CDP] ALL REAL AFTER SCREENSHOTS CAPTURED SUCCESSFULLY!');
  chromeProc.kill();
  process.exit(0);
}

run().catch((err) => {
  console.error('[CDP Error]', err);
  process.exit(1);
});
