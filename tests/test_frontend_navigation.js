/*
 * Kiểm thử chi tiết DOM và luồng điều hướng giao diện (chạy bằng Node.js, không cần mở trình duyệt):
 *   node tests/test_frontend_navigation.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

function createMockElement(tagName, id = "", classes = []) {
  const classListSet = new Set(classes);
  const attributes = {};
  const listeners = {};
  const children = [];

  const el = {
    tagName: tagName.toUpperCase(),
    id,
    style: {},
    dataset: {},
    children,
    parentNode: null,
    innerHTML: "",
    textContent: "",
    className: classes.join(" "),
    classList: {
      add(...cls) {
        cls.forEach(c => classListSet.add(c));
        el.className = Array.from(classListSet).join(" ");
      },
      remove(...cls) {
        cls.forEach(c => classListSet.delete(c));
        el.className = Array.from(classListSet).join(" ");
      },
      toggle(cls, force) {
        const next = force !== undefined ? !!force : !classListSet.has(cls);
        if (next) classListSet.add(cls);
        else classListSet.delete(cls);
        el.className = Array.from(classListSet).join(" ");
        return next;
      },
      contains(cls) {
        return classListSet.has(cls);
      },
    },
    setAttribute(k, v) {
      attributes[k] = String(v);
    },
    getAttribute(k) {
      return attributes[k] !== undefined ? attributes[k] : null;
    },
    hasAttribute(k) {
      return attributes[k] !== undefined;
    },
    removeAttribute(k) {
      delete attributes[k];
    },
    addEventListener(evt, fn) {
      if (!listeners[evt]) listeners[evt] = [];
      listeners[evt].push(fn);
    },
    click() {
      if (listeners["click"]) {
        listeners["click"].forEach(fn => fn({ target: el, preventDefault() {} }));
      }
    },
    appendChild(child) {
      if (child.parentNode) {
        child.parentNode.removeChild(child);
      }
      child.parentNode = el;
      children.push(child);
      return child;
    },
    insertBefore(newChild, refChild) {
      if (newChild.parentNode) {
        newChild.parentNode.removeChild(newChild);
      }
      newChild.parentNode = el;
      const idx = children.indexOf(refChild);
      if (idx !== -1) {
        children.splice(idx, 0, newChild);
      } else {
        children.push(newChild);
      }
      return newChild;
    },
    removeChild(child) {
      const idx = children.indexOf(child);
      if (idx !== -1) {
        children.splice(idx, 1);
        child.parentNode = null;
      }
      return child;
    },
    remove() {
      if (el.parentNode) {
        el.parentNode.removeChild(el);
      }
    },
    querySelector(selector) {
      return el.querySelectorAll(selector)[0] || null;
    },
    querySelectorAll(selector) {
      const matched = [];
      function traverse(curr) {
        for (const child of curr.children) {
          if (matchesSelector(child, selector)) {
            matched.push(child);
          }
          traverse(child);
        }
      }
      traverse(el);
      return matched;
    },
  };
  return el;
}

function matchesSelector(el, sel) {
  // Đơn giản hóa selector parser cho mock
  const parts = sel.split(",").map(s => s.trim());
  return parts.some(part => {
    // #id
    if (part.startsWith("#")) {
      const rest = part.slice(1);
      if (rest.includes(":not(.hidden)")) {
        const id = rest.replace(":not(.hidden)", "");
        return el.id === id && !el.classList.contains("hidden");
      }
      return el.id === rest;
    }
    // .class
    if (part === ".nav-tab-btn") {
      return el.classList.contains("nav-tab-btn");
    }
    if (part === ".nav-tab-btn[data-tab]") {
      return el.classList.contains("nav-tab-btn") && el.hasAttribute("data-tab");
    }
    if (part === ".nav-tab-btn[data-tab]:not(.hidden)") {
      return el.classList.contains("nav-tab-btn") && el.hasAttribute("data-tab") && !el.classList.contains("hidden");
    }
    if (part === "#nav-more:not(.hidden)") {
      return el.id === "nav-more" && !el.classList.contains("hidden");
    }
    if (part === "nav") {
      return el.tagName === "NAV";
    }
    if (part.startsWith(".nav-tab-btn[data-tab=")) {
      const match = part.match(/data-tab="([^"]+)"/);
      return el.classList.contains("nav-tab-btn") && match && el.getAttribute("data-tab") === match[1];
    }
    if (part.startsWith("nav .nav-tab-btn[data-tab=")) {
      const match = part.match(/data-tab="([^"]+)"/);
      return el.classList.contains("nav-tab-btn") && match && el.getAttribute("data-tab") === match[1];
    }
    return false;
  });
}

// Xây dựng cây DOM giả lập đúng như frontend/index.html
const rootDoc = createMockElement("html");
const body = createMockElement("body");
rootDoc.appendChild(body);

const elementsById = {};
function registerEl(el) {
  if (el.id) elementsById[el.id] = el;
  return el;
}

const topbarTitle = registerEl(createMockElement("h1", "topbar-page-title"));
body.appendChild(topbarTitle);

const appShell = registerEl(createMockElement("div", "app-shell"));
body.appendChild(appShell);

const navSectionWork = registerEl(createMockElement("div", "nav-section-work"));
const navWork = createMockElement("nav");
navSectionWork.appendChild(navWork);
body.appendChild(navSectionWork);

const btnDashboard = registerEl(createMockElement("button", "", ["nav-tab-btn"]));
btnDashboard.setAttribute("data-tab", "dashboard");
navWork.appendChild(btnDashboard);

const btnTickets = registerEl(createMockElement("button", "", ["nav-tab-btn"]));
btnTickets.setAttribute("data-tab", "tickets");
navWork.appendChild(btnTickets);

const btnLookup = registerEl(createMockElement("button", "", ["nav-tab-btn"]));
btnLookup.setAttribute("data-tab", "lookup");
navWork.appendChild(btnLookup);

const btnAi = registerEl(createMockElement("button", "", ["nav-tab-btn"]));
btnAi.setAttribute("data-tab", "ai");
navWork.appendChild(btnAi);

const navSectionAdmin = registerEl(createMockElement("div", "nav-section-admin"));
const navSectionAdminItems = registerEl(createMockElement("nav", "nav-section-admin-items"));
navSectionAdmin.appendChild(navSectionAdminItems);
body.appendChild(navSectionAdmin);

const btnCustomers = registerEl(createMockElement("button", "", ["nav-tab-btn"]));
btnCustomers.setAttribute("data-tab", "customers");
navSectionAdminItems.appendChild(btnCustomers);

const btnProducts = registerEl(createMockElement("button", "", ["nav-tab-btn"]));
btnProducts.setAttribute("data-tab", "products");
navSectionAdminItems.appendChild(btnProducts);

const btnDevices = registerEl(createMockElement("button", "", ["nav-tab-btn"]));
btnDevices.setAttribute("data-tab", "devices");
navSectionAdminItems.appendChild(btnDevices);

const btnAccounts = registerEl(createMockElement("button", "", ["nav-tab-btn"]));
btnAccounts.setAttribute("data-tab", "accounts");
navSectionAdminItems.appendChild(btnAccounts);

const navMore = registerEl(createMockElement("div", "nav-more", ["hidden"]));
const navMoreToggle = registerEl(createMockElement("button", "nav-more-toggle", ["nav-tab-btn"]));
navMoreToggle.setAttribute("aria-expanded", "false");
const navMorePanel = registerEl(createMockElement("div", "nav-more-panel", ["hidden"]));
navMore.appendChild(navMoreToggle);
navMore.appendChild(navMorePanel);
navSectionAdminItems.appendChild(navMore);

const sessionChip = registerEl(createMockElement("div", "session-chip"));
body.appendChild(sessionChip);

const allNavBtns = [
  btnDashboard, btnTickets, btnLookup, btnAi,
  btnCustomers, btnProducts, btnDevices, btnAccounts,
  navMoreToggle
];

const mockDocument = {
  documentElement: rootDoc,
  body,
  getElementById: (id) => elementsById[id] || null,
  querySelector: (sel) => body.querySelector(sel),
  querySelectorAll: (sel) => {
    if (sel === ".nav-tab-btn") return allNavBtns;
    return body.querySelectorAll(sel);
  },
  addEventListener: () => {},
};

const sandbox = {
  console,
  setTimeout: (fn) => fn(),
  clearTimeout: () => {},
  window: {
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    scrollTo: () => {},
  },
  document: mockDocument,
  fetch: async () => ({ ok: true, status: 200, json: async () => ({}) }),
};
sandbox.globalThis = sandbox;

const appJsPath = path.join(__dirname, "..", "frontend", "app.js");
const appJsCode = fs.readFileSync(appJsPath, "utf8");
vm.createContext(sandbox);
vm.runInContext(appJsCode, sandbox, { filename: "app.js" });
vm.runInContext("globalThis.state = state;", sandbox);

const tests = [];
function test(name, pass, detail = "") {
  tests.push({ name, pass: !!pass, detail });
  console.log(`[${pass ? "PASS" : "FAIL"}] ${name}`);
  if (detail) console.log(`       -> ${detail}`);
}

console.log("\n" + "=".repeat(75));
console.log("  KIEM THU GIAO DIEN & DIEU HUONG (MOCK DOM APP.JS)");
console.log("=".repeat(75));

// Khởi tạo tab listeners
sandbox.setupTabs();

// Menu và permissions KTV do backend trả về
const ktvMenus = [
  { tab: "dashboard", label: "Tổng quan", group: "work" },
  { tab: "tickets", label: "Phiếu bảo hành", group: "work" },
  { tab: "lookup", label: "Tra cứu bảo hành", group: "work" },
  { tab: "ai", label: "Hỗ trợ xác định lỗi", group: "work" },
];
const ktvPermissions = [
  "dashboard.view",
  "ticket.view",
  "lookup.view",
  "ai.view",
  "customer.view",
  "product.view",
  "device.view",
];

sandbox.state.session.user = {
  role: "TECHNICIAN",
  menus: ktvMenus,
  permissions: ktvPermissions,
};

// 1. Render menu KTV
sandbox.renderNavigation(ktvMenus);

test("KTV: Đúng 4 nút menu hiển thị (dashboard, tickets, lookup, ai)",
  !btnDashboard.classList.contains("hidden") &&
  !btnTickets.classList.contains("hidden") &&
  !btnLookup.classList.contains("hidden") &&
  !btnAi.classList.contains("hidden")
);

test("KTV: Các nút khách hàng, danh mục máy, máy đăng ký, tài khoản bị ẩn",
  btnCustomers.classList.contains("hidden") &&
  btnProducts.classList.contains("hidden") &&
  btnDevices.classList.contains("hidden") &&
  btnAccounts.classList.contains("hidden")
);

test("KTV: Khối Sổ & Quản trị (nav-section-admin) bị ẩn hoàn toàn (không khoảng trắng thừa)",
  navSectionAdmin.classList.contains("hidden")
);

test("KTV: Khối dropdown 'Tra cứu nội bộ' (nav-more) bị ẩn hoàn toàn",
  navMore.classList.contains("hidden")
);

// 2. Chuyển tab trong 4 mục của KTV
sandbox.switchTab("tickets");
test("Chuyển tab 'tickets' thành công, cập nhật tiêu đề topbar",
  sandbox.state.currentTab === "tickets" && topbarTitle.textContent === "Phiếu bảo hành" && btnTickets.classList.contains("active")
);

sandbox.switchTab("lookup");
test("Chuyển tab 'lookup' thành công, cập nhật tiêu đề topbar",
  sandbox.state.currentTab === "lookup" && topbarTitle.textContent === "Tra cứu bảo hành" && btnLookup.classList.contains("active")
);

sandbox.switchTab("ai");
test("Chuyển tab 'ai' thành công, cập nhật tiêu đề topbar",
  sandbox.state.currentTab === "ai" && topbarTitle.textContent === "Hỗ trợ xác định lỗi" && btnAi.classList.contains("active")
);

sandbox.switchTab("dashboard");
test("Chuyển tab 'dashboard' thành công, cập nhật tiêu đề topbar",
  sandbox.state.currentTab === "dashboard" && topbarTitle.textContent === "Tổng quan" && btnDashboard.classList.contains("active")
);

// 3. Click nút dropdown 'Tra cứu nội bộ' (navMoreToggle) không được đưa về Tổng quan
sandbox.switchTab("tickets"); // đang ở tickets
navMoreToggle.click(); // bấm nút toggle
test("Bấm nút 'Tra cứu nội bộ' (nav-more-toggle) KHÔNG bị đưa về Tổng quan (vẫn ở tickets)",
  sandbox.state.currentTab === "tickets" && topbarTitle.textContent === "Phiếu bảo hành"
);

// 4. Kiểm tra aria-expanded khi mở/đóng dropdown
sandbox.toggleNavMore(true);
test("Mở dropdown cập nhật aria-expanded='true'",
  navMoreToggle.getAttribute("aria-expanded") === "true" && !navMorePanel.classList.contains("hidden")
);

sandbox.closeNavMore();
test("Đóng dropdown cập nhật aria-expanded='false'",
  navMoreToggle.getAttribute("aria-expanded") === "false" && navMorePanel.classList.contains("hidden")
);

// 5. switchTab với tabId không hợp lệ (null, undefined, rỗng, lạ) không reset về dashboard
sandbox.switchTab("tickets");
sandbox.switchTab(null);
sandbox.switchTab("");
sandbox.switchTab("unknown_tab");
test("switchTab với tabId không hợp lệ giữ nguyên màn hình hiện tại (không âm thầm nhảy về Tổng quan)",
  sandbox.state.currentTab === "tickets"
);

// 6. Chuyển vai trò: Quản lý -> Đăng xuất -> Kỹ thuật viên
const managerMenus = [
  { tab: "dashboard", label: "Tổng quan", group: "work" },
  { tab: "tickets", label: "Phiếu bảo hành", group: "work" },
  { tab: "lookup", label: "Tra cứu bảo hành", group: "work" },
  { tab: "ai", label: "Hỗ trợ xác định lỗi", group: "work" },
  { tab: "customers", label: "Khách hàng", group: "work" },
  { tab: "products", label: "Danh mục máy", group: "work" },
  { tab: "devices", label: "Máy đã đăng ký", group: "work" },
  { tab: "accounts", label: "Tài khoản nhân viên", group: "admin" },
];
const managerPermissions = [
  "dashboard.view", "ticket.view", "lookup.view", "ai.view",
  "customer.view", "product.view", "device.view", "user.view"
];

// Quản lý đăng nhập
sandbox.state.session.user = { role: "MANAGER", menus: managerMenus, permissions: managerPermissions };
sandbox.renderNavigation(managerMenus);

test("Quản lý: Sổ & Quản trị hiển thị đầy đủ (không bị hidden)",
  !navSectionAdmin.classList.contains("hidden") &&
  !btnAccounts.classList.contains("hidden") &&
  !btnCustomers.classList.contains("hidden")
);

// Quản lý đang mở tab accounts rồi đăng xuất
sandbox.switchTab("accounts");
sandbox.state.session.user = null;
sandbox.clearSessionData();
sandbox.applySessionUi();

test("Đăng xuất: currentTab reset về dashboard, các nút menu bị dọn sạch",
  sandbox.state.currentTab === "dashboard" &&
  btnAccounts.classList.contains("hidden")
);

// KTV đăng nhập sau đó
sandbox.state.session.user = { role: "TECHNICIAN", menus: ktvMenus, permissions: ktvPermissions };
sandbox.applySessionUi();

test("KTV đăng nhập lại: Menu sạch sẽ, chỉ có 4 mục, không sót tàn dư của Quản lý",
  !btnDashboard.classList.contains("hidden") &&
  !btnTickets.classList.contains("hidden") &&
  !btnLookup.classList.contains("hidden") &&
  !btnAi.classList.contains("hidden") &&
  btnAccounts.classList.contains("hidden") &&
  navSectionAdmin.classList.contains("hidden")
);

console.log("\n" + "=".repeat(75));
const total = tests.length;
const passed = tests.filter(t => t.pass).length;
console.log(`  TONG KET FRONTEND: ${passed}/${total} PASS`);
console.log("=".repeat(75));

process.exit(passed === total ? 0 : 1);
