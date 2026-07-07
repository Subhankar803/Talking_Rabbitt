/* ============================================================
   app.js — shared across every page: theme, active nav link,
   and the "current dataset" the whole app revolves around.
   ============================================================ */

const API_BASE = "/api";

function checkAuth() {
  const path = window.location.pathname;
  if (path === "/" || path === "/login" || path === "/sign_up") {
    return;
  }
  const user = localStorage.getItem("tr_user");
  if (!user) {
    window.location.href = "/";
  }
}
checkAuth();

const AppState = {
  getDataset() {
    const raw = localStorage.getItem("tr_dataset");
    return raw ? JSON.parse(raw) : null;
  },
  setDataset(dataset) {
    localStorage.setItem("tr_dataset", JSON.stringify(dataset));
    window.dispatchEvent(new CustomEvent("dataset-changed", { detail: dataset }));
  },
  clearDataset() {
    localStorage.removeItem("tr_dataset");
  },
};

function initTheme() {
  const saved = localStorage.getItem("tr_theme") || "dark";
  document.documentElement.setAttribute("data-theme", saved);
  document.querySelectorAll("[data-theme-btn]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.themeBtn === saved);
    btn.addEventListener("click", () => {
      document.documentElement.setAttribute("data-theme", btn.dataset.themeBtn);
      localStorage.setItem("tr_theme", btn.dataset.themeBtn);
      document.querySelectorAll("[data-theme-btn]").forEach((b) => b.classList.toggle("active", b === btn));
    });
  });
}

function initActiveNav() {
  const path = window.location.pathname === "/" ? "/" : window.location.pathname.replace(/\/$/, "");
  document.querySelectorAll(".nav-link").forEach((link) => {
    const href = link.getAttribute("href");
    if (href === path) link.classList.add("active");
  });
}

function renderDatasetPill() {
  const pillEls = document.querySelectorAll("[data-dataset-pill]");
  const dataset = AppState.getDataset();
  pillEls.forEach((el) => {
    el.innerHTML = dataset
      ? `<span class="dot"></span> ${dataset.original_name} <span class="mono" style="color:var(--text-muted)">· ${dataset.row_count} rows</span>`
      : `<span class="dot" style="background:var(--text-muted)"></span> No dataset loaded`;
  });
}

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

function requireDatasetOrRedirect() {
  const dataset = AppState.getDataset();
  if (!dataset) {
    const container = document.querySelector("[data-requires-dataset]");
    if (container) {
      container.innerHTML = `
        <div class="empty-state">
          <i class="ti ti-database-off"></i>
          <div>No dataset loaded yet.</div>
          <div style="margin-top:14px"><a class="btn btn-primary" href="/upload"><i class="ti ti-upload"></i> Upload a dataset</a></div>
        </div>`;
    }
    return null;
  }
  return dataset;
}

const NAV_ITEMS = [
  { href: "/home", icon: "ti-home", label: "Home" },
  { href: "/upload", icon: "ti-upload", label: "Upload data" },
  { href: "/dashboard", icon: "ti-chart-bar", label: "Dashboard" },
  { href: "/chat", icon: "ti-message-chatbot", label: "Ask Rabbitt" },
  { href: "/forecast", icon: "ti-trending-up", label: "Forecast" },
  { href: "/report", icon: "ti-report", label: "Executive report" },
];

function injectSidebar() {
  const mount = document.getElementById("sidebar-mount");
  if (!mount) return;

  const userRaw = localStorage.getItem("tr_user");
  const user = userRaw ? JSON.parse(userRaw) : null;
  const companyLabel = user && user.companyName ? user.companyName : "BI Assistant";

  mount.innerHTML = `
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M6 10c0-3 2-6 6-6s6 3 6 6v6a6 6 0 0 1-12 0v-6Z" stroke="#05140F" stroke-width="1.6"/>
            <path d="M8 6 6 2M16 6l2-4" stroke="#05140F" stroke-width="1.6" stroke-linecap="round"/>
            <circle cx="9.5" cy="11" r="1" fill="#05140F"/><circle cx="14.5" cy="11" r="1" fill="#05140F"/>
          </svg>
        </div>
        <div>
          <div class="brand-name">Talking Rabbitt</div>
          <div class="brand-tag">${companyLabel}</div>
        </div>
      </div>
      <nav class="nav-group">
        <span class="nav-label">Workspace</span>
        ${NAV_ITEMS.map((item) => `
          <a class="nav-link" href="${item.href}">
            <i class="ti ${item.icon}"></i> ${item.label}
          </a>`).join("")}
      </nav>
      <div class="sidebar-footer">
        <div class="theme-toggle" style="margin-bottom: 12px;">
          <span>Theme</span>
          <div>
            <button data-theme-btn="dark"><i class="ti ti-moon"></i></button>
            <button data-theme-btn="light"><i class="ti ti-sun"></i></button>
          </div>
        </div>
        <div class="user-profile" style="padding: 10px 0; border-top: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; margin-top: 8px;">
          <div style="display: flex; flex-direction: column; gap: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
            <span style="font-size: 12px; font-weight: 600; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${user ? user.fullName : "User"}</span>
            <span style="font-size: 10px; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${user ? user.email : ""}</span>
          </div>
          <button onclick="logout()" class="btn btn-outline" style="padding: 4px 8px; font-size: 11px; height: auto; background: transparent; border-color: var(--border); flex-shrink: 0; margin-left: 8px;">
            <i class="ti ti-logout" style="margin-right: 2px;"></i> Exit
          </button>
        </div>
      </div>
    </aside>`;
}

window.logout = function() {
  localStorage.removeItem("tr_user");
  window.location.href = "/";
};

document.addEventListener("DOMContentLoaded", () => {
  injectSidebar();
  initTheme();
  initActiveNav();
  renderDatasetPill();
  window.addEventListener("dataset-changed", renderDatasetPill);
});
