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
  const cdpPort = 9224;
  const userDataDir = path.join(require('os').tmpdir(), 'chrome_cdp_shot_' + Date.now());

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

  async function login(username, password) {
    await client.eval(`
      localStorage.clear();
      sessionStorage.clear();
      window.location.reload();
    `);
    await sleep(800);
    await client.eval(`
      document.getElementById('login-username').value = '${username}';
      document.getElementById('login-password').value = '${password}';
      document.getElementById('login-form').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
    `);
    await sleep(1500);
  }

  console.log('[CDP] Capturing BEFORE screenshots...');

  // 1. Overview (Manager) 1920x1080
  await client.setViewport(1920, 1080);
  await client.send('Page.navigate', { url: BASE_URL });
  await sleep(1000);
  await login('manager01', 'Admin@123');
  await sleep(1200);
  await client.eval(`document.querySelector('.nav-tab-btn[data-tab="dashboard"]').click()`);
  await sleep(1000);
  await client.screenshot(path.join(OUT_DIR, 'before_01_overview.png'));

  // 2. Accounts (Manager) 1920x1080
  await client.eval(`document.querySelector('.nav-tab-btn[data-tab="accounts"]').click()`);
  await sleep(1000);
  await client.screenshot(path.join(OUT_DIR, 'before_05_accounts.png'));

  // 3. Tickets List (Receptionist) 1920x1080
  await login('receptionist01', 'Tiepnhan@123');
  await sleep(1200);
  await client.eval(`document.querySelector('.nav-tab-btn[data-tab="tickets"]').click()`);
  await sleep(1000);
  // Ensure reception panel is hidden for pure ticket list view
  await client.eval(`(() => {
    const p = document.getElementById('reception-panel');
    if (p && !p.classList.contains('hidden')) document.getElementById('btn-toggle-reception')?.click();
  })()`);
  await sleep(500);
  await client.screenshot(path.join(OUT_DIR, 'before_02_tickets.png'));

  // 4. Intake Wizard (Receptionist) 1920x1080
  await client.eval(`(() => {
    const p = document.getElementById('reception-panel');
    if (p && p.classList.contains('hidden')) document.getElementById('btn-toggle-reception')?.click();
  })()`);
  await sleep(800);
  await client.screenshot(path.join(OUT_DIR, 'before_03_intake.png'));

  // 5. Ticket Detail (Technician) 1920x1080
  await login('technician01', 'Kythuat@123');
  await sleep(1200);
  await client.eval(`document.querySelector('.nav-tab-btn[data-tab="tickets"]').click()`);
  await sleep(1000);
  // Click on the first view ticket detail button
  await client.eval(`(() => {
    const btn = document.querySelector('#tickets-table-body button[onclick*="viewTicketDetail"]') || document.querySelector('#tickets-table-body tr button');
    if (btn) btn.click();
  })()`);
  await sleep(1200);
  await client.screenshot(path.join(OUT_DIR, 'before_04_ticket_detail.png'));
  // Close modal
  await client.eval(`(() => { window.closeTicketModal && window.closeTicketModal(); })()`);
  await sleep(500);

  // 6. Chatbot window open (1920x1080)
  await client.eval(`(() => {
    const launch = document.querySelector('.bh-launch') || document.getElementById('btn-bh-support');
    if (launch) launch.click();
  })()`);
  await sleep(1000);
  await client.screenshot(path.join(OUT_DIR, 'before_06_chatbot.png'));

  // 7. Chatbot mobile viewport (390x844)
  await client.setViewport(390, 844);
  await sleep(800);
  await client.screenshot(path.join(OUT_DIR, 'before_07_chatbot_mobile_390.png'));

  console.log('[CDP] ALL BEFORE SCREENSHOTS CAPTURED SUCCESSFULLY!');
  chromeProc.kill();
  process.exit(0);
}

run().catch((err) => {
  console.error('[CDP Error]', err);
  process.exit(1);
});
