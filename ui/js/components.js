/* FDE Nexus: shared UI shell and render helpers.
   Injects the sidebar + header into every page and provides small helpers
   (badges, toasts, theme). No network calls. */
(function () {
  "use strict";
  const NX = window.NEXUS;

  /* ---- small helpers ---- */
  const el = (sel, root) => (root || document).querySelector(sel);
  NX.esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  /* status badge from statusMeta key */
  NX.badge = function (key, textOverride) {
    const m = NX.statusMeta[key] || { label: key, tone: "secondary", icon: "bi-dot" };
    return `<span class="nx-badge b-${m.tone}"><i class="bi ${m.icon}"></i>${NX.esc(textOverride || m.label)}</span>`;
  };
  /* risk tier badge */
  NX.riskBadge = function (tier) {
    const r = NX.riskTiers[tier] || { label: tier, tone: "secondary" };
    return `<span class="nx-badge b-${r.tone}">${NX.esc(r.label)}</span>`;
  };

  /* navigation definition shared across pages.
     adminOnly items appear only when the signed-in demo role is admin/superadmin. */
  const NAV = [
    { section: "Operate" },
    { href: "index.html", icon: "bi-speedometer2", label: "Overview" },
    { href: "services.html", icon: "bi-grid-3x3-gap", label: "Modules & Services", count: 16 },
    { href: "requests.html", icon: "bi-inbox", label: "Requests & Approvals", count: 4 },
    { href: "operations.html", icon: "bi-gear-wide-connected", label: "Operations Registry" },
    { section: "Self-service" },
    { href: "requirements.html", icon: "bi-chat-left-text", label: "Describe → YAML" },
    { href: "builder.html", icon: "bi-ui-checks-grid", label: "Infrastructure Builder" },
    { section: "Engineer" },
    { href: "troubleshooting.html", icon: "bi-bug", label: "EKS Troubleshooting" },
    { href: "validation.html", icon: "bi-check2-square", label: "Checks & Validation" },
    { href: "stack.html", icon: "bi-boxes", label: "Tech Stack" },
    { section: "Insight" },
    { href: "reports.html", icon: "bi-bar-chart-line", label: "Reports" },
    { href: "activity.html", icon: "bi-clock-history", label: "Activity & Audit Log" },
    { section: "Platform" },
    { href: "admin.html", icon: "bi-shield-lock", label: "Admin Panel", adminOnly: true },
    { href: "settings.html", icon: "bi-sliders", label: "Settings" },
    { href: "help.html", icon: "bi-question-circle", label: "Help & Docs" }
  ];

  /* ---- demo session (frontend only) ---- */
  NX.session = {
    get() { try { return JSON.parse(localStorage.getItem("nx-session") || "null"); } catch (e) { return null; } },
    set(s) { localStorage.setItem("nx-session", JSON.stringify(s)); },
    clear() { localStorage.removeItem("nx-session"); },
    isAdmin() { const s = this.get(); return s && (s.role === "admin" || s.role === "superadmin"); }
  };
  NX.requireAuth = function () {
    // Pages (except the login page) require a demo session; otherwise redirect to login.
    if (document.body.getAttribute("data-public") === "1") return true;
    if (!NX.session.get()) { location.replace("login.html"); return false; }
    return true;
  };

  /* ---- shell injection ---- */
  function buildShell() {
    const app = el("#nx-app");
    if (!app) return;
    // gate every app page behind the demo login
    if (!NX.requireAuth()) return;
    const page = app.getAttribute("data-page") || "";
    const title = app.getAttribute("data-title") || "FDE Nexus";
    const isAdmin = NX.session.isAdmin();

    const navHtml = NAV.filter(item => !item.adminOnly || isAdmin).map(item => {
      if (item.section) return `<div class="nx-section">${item.section}</div>`;
      const active = item.href === page ? "active" : "";
      const count = item.count != null ? `<span class="nx-count">${item.count}</span>` : "";
      return `<a class="nav-link ${active}" href="${item.href}">
                <i class="bi ${item.icon}"></i><span class="nav-link-text">${item.label}</span>${count}
              </a>`;
    }).join("");

    const sidebar = `
      <aside class="nx-sidebar" id="nx-sidebar">
        <a class="nx-brand" href="index.html" aria-label="FDE Nexus home">
          <span class="nx-logo">N</span>
          <span class="nx-brand-text"><b>FDE Nexus</b><small>CLOUD ENGINEERING</small></span>
        </a>
        <nav class="nx-nav" aria-label="Primary">${navHtml}</nav>
        <div class="nx-sidebar-foot">Static demo UI &middot; v0.1<br>Spec author: Ashish Gajjar</div>
      </aside>`;

    const header = `
      <header class="nx-header">
        <button class="nx-toggle" id="nx-toggle" aria-label="Toggle navigation"><i class="bi bi-list"></i></button>
        <h1 class="nx-page-title">${NX.esc(title)}</h1>
        <div class="nx-search">
          <div class="input-group input-group-sm">
            <span class="input-group-text bg-transparent border-end-0"><i class="bi bi-search"></i></span>
            <input id="nx-global-search" type="search" class="form-control border-start-0" placeholder="Search modules, requests, operations…" aria-label="Global search">
          </div>
        </div>
        <div class="nx-header-actions">
          <button class="nx-iconbtn" id="nx-theme-btn" title="Toggle theme" aria-label="Toggle light or dark theme"><i class="bi bi-moon-stars"></i></button>
          <button class="nx-iconbtn" id="nx-alerts-btn" title="Notifications" aria-label="Notifications"><i class="bi bi-bell"></i><span class="nx-dot"></span></button>
          <div class="dropdown">
            <button class="nx-avatar border-0" id="nx-user-btn" data-bs-toggle="dropdown" aria-expanded="false" title="Account">${NX.esc(initials())}</button>
            <ul class="dropdown-menu dropdown-menu-end" aria-labelledby="nx-user-btn">
              <li class="dropdown-header" id="nx-user-head"></li>
              <li><hr class="dropdown-divider"></li>
              <li><a class="dropdown-item" href="settings.html"><i class="bi bi-sliders me-2"></i>Settings</a></li>
              ${isAdmin ? '<li><a class="dropdown-item" href="admin.html"><i class="bi bi-shield-lock me-2"></i>Admin Panel</a></li>' : ''}
              <li><button class="dropdown-item" id="nx-logout"><i class="bi bi-box-arrow-right me-2"></i>Sign out</button></li>
            </ul>
          </div>
        </div>
      </header>`;

    const bannerHidden = app.getAttribute("data-no-banner") === "1";
    const banner = bannerHidden ? "" : `
      <div class="nx-demo-banner" role="note">
        <i class="bi bi-info-circle-fill"></i>
        <span><strong>Demo interface.</strong> No backend, no AWS calls, no real data. Every action is a simulation using mock data.</span>
      </div>`;

    // wrap existing page content
    const content = app.innerHTML;
    app.innerHTML = `${sidebar}
      <div class="nx-main">
        ${header}
        <div class="nx-content">
          ${banner}
          ${content}
        </div>
      </div>
      <div class="nx-backdrop" id="nx-backdrop"></div>`;

    wireShell(page);
  }

  function initials() {
    const s = NX.session.get();
    if (!s || !s.name) return "AG";
    return s.name.split(/\s+/).map(w => w[0]).join("").slice(0, 2).toUpperCase();
  }

  function wireShell(page) {
    const app = el("#nx-app");
    const isMobile = () => window.matchMedia("(max-width: 992px)").matches;

    // populate user dropdown header and wire logout
    const s = NX.session.get();
    const head = el("#nx-user-head");
    if (head && s) head.innerHTML = `<strong>${NX.esc(s.name)}</strong><br><span class="small text-muted">${NX.esc(s.role)}</span>`;
    const lo = el("#nx-logout");
    if (lo) lo.addEventListener("click", () => { NX.session.clear(); location.href = "login.html"; });

    el("#nx-toggle").addEventListener("click", () => {
      if (isMobile()) app.classList.toggle("nx-sidebar-open");
      else {
        app.classList.toggle("nx-collapsed");
        localStorage.setItem("nx-collapsed", app.classList.contains("nx-collapsed") ? "1" : "0");
      }
    });
    if (localStorage.getItem("nx-collapsed") === "1" && !isMobile()) app.classList.add("nx-collapsed");
    el("#nx-backdrop").addEventListener("click", () => app.classList.remove("nx-sidebar-open"));

    // theme
    applyTheme(localStorage.getItem("nx-theme") || "light");
    el("#nx-theme-btn").addEventListener("click", () => {
      const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      applyTheme(next); localStorage.setItem("nx-theme", next);
      NX.toast("Theme switched to " + next + " (demo preference).", "info");
    });

    // alerts dropdown -> offcanvas
    el("#nx-alerts-btn").addEventListener("click", showAlertsPanel);

    // global search routes to services with query (demo)
    const gs = el("#nx-global-search");
    gs.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && gs.value.trim()) {
        location.href = "services.html?q=" + encodeURIComponent(gs.value.trim());
      }
    });
  }

  function applyTheme(mode) {
    document.documentElement.setAttribute("data-theme", mode);
    const i = el("#nx-theme-btn i");
    if (i) i.className = mode === "dark" ? "bi bi-sun" : "bi bi-moon-stars";
  }

  /* ---- toasts ---- */
  NX.toast = function (msg, tone) {
    tone = tone || "primary";
    let host = el("#nx-toast-host");
    if (!host) {
      host = document.createElement("div");
      host.id = "nx-toast-host";
      host.className = "toast-container position-fixed bottom-0 end-0 p-3";
      host.style.zIndex = "1200";
      document.body.appendChild(host);
    }
    const icon = { primary: "bi-info-circle", success: "bi-check-circle", warning: "bi-exclamation-triangle", danger: "bi-x-circle", info: "bi-info-circle" }[tone] || "bi-info-circle";
    const node = document.createElement("div");
    node.className = "toast align-items-center border-0 mb-2";
    node.setAttribute("role", "status");
    node.innerHTML = `<div class="d-flex">
        <div class="toast-body d-flex align-items-center gap-2">
          <i class="bi ${icon} text-${tone === 'primary' ? 'primary' : tone}"></i>
          <span>${NX.esc(msg)}</span>
        </div>
        <button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
      </div>`;
    host.appendChild(node);
    const t = new bootstrap.Toast(node, { delay: 3200 });
    t.show();
    node.addEventListener("hidden.bs.toast", () => node.remove());
  };

  /* ---- alerts offcanvas ---- */
  function showAlertsPanel() {
    let oc = el("#nx-alerts-oc");
    if (!oc) {
      oc = document.createElement("div");
      oc.className = "offcanvas offcanvas-end";
      oc.id = "nx-alerts-oc";
      oc.tabIndex = -1;
      oc.innerHTML = `
        <div class="offcanvas-header border-bottom">
          <h5 class="offcanvas-title"><i class="bi bi-bell me-2"></i>Notifications</h5>
          <button type="button" class="btn-close" data-bs-dismiss="offcanvas" aria-label="Close"></button>
        </div>
        <div class="offcanvas-body">
          ${NX.alerts.map(a => `
            <div class="nx-alert a-${a.level}">
              <i class="bi ${a.icon} nx-alert-icon"></i>
              <div>
                <div class="nx-alert-title">${NX.esc(a.title)}</div>
                <div class="nx-alert-text">${NX.esc(a.text)}</div>
              </div>
              <span class="nx-alert-time">${NX.esc(a.time)}</span>
            </div>`).join("")}
          <p class="nx-muted small mt-3 mb-0">Demo notifications. No action is performed.</p>
        </div>`;
      document.body.appendChild(oc);
    }
    bootstrap.Offcanvas.getOrCreateInstance(oc).show();
  }

  /* run once DOM ready */
  document.addEventListener("DOMContentLoaded", buildShell);
})();
