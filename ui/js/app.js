/* FDE Nexus: per-page behavior. One file, each page calls the init it needs.
   All interactions are simulated (filter, sort, paginate, modals, run buttons). */
(function () {
  "use strict";
  const NX = window.NEXUS;
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => [...(r || document).querySelectorAll(s)];
  const esc = NX.esc;
  const qparam = (k) => new URLSearchParams(location.search).get(k) || "";

  /* ============================ OVERVIEW ============================ */
  function initOverview() {
    // KPIs
    const kpiHost = $("#nx-kpis");
    if (kpiHost) {
      kpiHost.innerHTML = NX.kpis.map(k => `
        <div class="col-6 col-md-4 col-xl-2">
          <div class="nx-card h-100"><div class="nx-card-body nx-kpi">
            <div class="nx-kpi-icon tone-${k.tone}"><i class="bi ${k.icon}"></i></div>
            <div>
              <div class="nx-kpi-value">${esc(k.value)}</div>
              <div class="nx-kpi-label">${esc(k.label)}</div>
              <div class="nx-delta ${k.trend}"><i class="bi bi-arrow-${k.trend}-short"></i>${esc(k.delta)}</div>
            </div>
          </div></div>
        </div>`).join("");
    }

    // module health list
    const mh = $("#nx-module-health");
    if (mh) {
      mh.innerHTML = NX.modules.map(m => `
        <a class="d-flex align-items-center gap-2 py-2 text-decoration-none border-bottom nx-mod-row"
           href="service-details.html?id=${m.id}" style="color:inherit">
          <span class="nx-kpi-icon tone-${NX.statusMeta[m.status].tone}" style="width:34px;height:34px;font-size:16px"><i class="bi ${m.icon}"></i></span>
          <span class="flex-grow-1"><span class="nx-mono small nx-muted">${m.id}</span><br><span class="fw-semibold small">${esc(m.name)}</span></span>
          ${NX.badge(m.status)}
        </a>`).join("");
    }

    // activity timeline (recent 6)
    const at = $("#nx-activity");
    if (at) {
      at.innerHTML = NX.activity.slice(0, 6).map(a => `
        <li class="t-${a.tone}">
          <div class="nx-tl-title small">${esc(a.action)} <span class="nx-muted">&middot; ${esc(a.target)}</span></div>
          <div class="nx-tl-meta">${esc(a.actor)} &middot; ${esc(a.decision)} &middot; ${esc(a.ts)}</div>
        </li>`).join("");
    }

    // alerts
    const al = $("#nx-alerts");
    if (al) {
      al.innerHTML = NX.alerts.map(a => `
        <div class="nx-alert a-${a.level}">
          <i class="bi ${a.icon} nx-alert-icon"></i>
          <div><div class="nx-alert-title">${esc(a.title)}</div><div class="nx-alert-text">${esc(a.text)}</div></div>
          <span class="nx-alert-time">${esc(a.time)}</span>
        </div>`).join("");
    }

    // requests-by-status bars
    const bars = $("#nx-bars");
    if (bars) {
      const counts = { approved: 0, pending: 0, rejected: 0 };
      NX.requests.forEach(r => counts[r.status]++);
      const max = Math.max(...Object.values(counts), 1);
      const data = [
        { label: "Approved", v: counts.approved, alt: true },
        { label: "Pending", v: counts.pending, alt: false },
        { label: "Rejected", v: counts.rejected, alt: false }
      ];
      bars.innerHTML = data.map(d => `
        <div class="nx-bar-col">
          <span class="small fw-bold">${d.v}</span>
          <div class="nx-bar ${d.alt ? 'alt' : ''}" style="height:${Math.round(d.v / max * 100)}%"></div>
          <span class="nx-bar-label">${d.label}</span>
        </div>`).join("");
    }

    // donut: compliance
    const donut = $("#nx-donut");
    if (donut) {
      const pct = 92;
      donut.style.background = `conic-gradient(var(--nx-primary) ${pct * 3.6}deg, var(--nx-border) 0)`;
      donut.innerHTML = `<div class="nx-donut-hole"><div><div class="nx-donut-value">${pct}%</div><div class="nx-donut-sub">compliant</div></div></div>`;
    }
  }

  /* ============================ APPLICATIONS (your real tools) ============================ */
  function initTools() {
    const host = $("#nx-tools");
    if (!host) return;
    host.innerHTML = NX.tools.map(t => `
      <div class="col-12 col-xl-4">
        <div class="nx-card h-100"><div class="nx-card-body d-flex flex-column">
          <div class="d-flex align-items-start gap-3">
            <div class="nx-mod-icon tone-${NX.statusMeta[t.status].tone}" style="width:48px;height:48px;font-size:24px"><i class="bi ${t.icon}"></i></div>
            <div class="flex-grow-1">
              <div class="d-flex justify-content-between align-items-center">
                <span class="nx-mod-id">${esc(t.id)}</span>${NX.badge(t.status)}
              </div>
              <div class="nx-mod-name">${esc(t.name)}</div>
            </div>
          </div>
          <p class="nx-mod-desc">${esc(t.tagline)}</p>
          <div class="small nx-muted mb-2"><i class="bi bi-folder me-1"></i><span class="nx-mono">${esc(t.folder)}</span> &middot; port ${esc(t.port)}</div>
          <div class="nx-caps mb-2">${t.stack.map(s => `<span class="nx-cap">${esc(s)}</span>`).join(" ")}</div>
          <div class="small mb-2"><span class="fw-semibold">Role:</span> <span class="nx-muted">${esc(t.role)}</span></div>
          <details class="mb-2"><summary class="small fw-semibold cursor-pointer">Features (${t.features.length})</summary>
            <ul class="small nx-muted mt-2 mb-0">${t.features.map(f => `<li>${esc(f)}</li>`).join("")}</ul></details>
          <div class="mt-auto">
            <div class="small nx-muted mb-2">Maps to: ${t.maps_to.map(m => `<a class="nx-id text-decoration-none" href="service-details.html?id=${m}">${m}</a>`).join(" ")}</div>
            <button class="btn btn-sm btn-primary" data-open-tool="${t.id}"><i class="bi bi-box-arrow-up-right me-1"></i>Open (demo)</button>
          </div>
        </div></div>
      </div>`).join("");
    $$("[data-open-tool]").forEach(b => b.onclick = () => {
      const t = NX.tools.find(x => x.id === b.dataset.openTool);
      NX.toast(`${t.name} would open at ${t.entry} (demo, not launched here).`, "info");
    });
  }

  /* ============================ EKS TROUBLESHOOTING ============================ */
  function initTroubleshooting() {
    const host = $("#nx-ts");
    if (!host) return;
    const sevSel = $("#nx-ts-sev"), search = $("#nx-ts-search");
    function render() {
      const s = sevSel.value, q = search.value.trim().toLowerCase();
      const list = NX.troubleshooting.filter(t =>
        (!s || t.severity === s) &&
        (!q || (t.symptom + t.signal + t.cluster + t.likely).toLowerCase().includes(q)));
      $("#nx-ts-info").textContent = `${list.length} scenarios`;
      host.innerHTML = list.length ? list.map(t => `
        <div class="col-12 col-xl-6">
          <div class="nx-card h-100"><div class="nx-card-body">
            <div class="d-flex justify-content-between align-items-start gap-2">
              <div><span class="nx-id">${t.id}</span> <span class="fw-semibold">${esc(t.symptom)}</span></div>
              ${NX.badge(t.severity)}
            </div>
            <div class="small nx-muted mt-1"><i class="bi bi-boxes me-1"></i>${esc(t.cluster)} &middot; <span class="nx-mono">${esc(t.signal)}</span></div>
            <div class="small mt-2"><span class="fw-semibold">Likely cause:</span> ${esc(t.likely)}</div>
            <div class="small fw-semibold mt-2">Checks</div>
            <ul class="small nx-muted mb-2">${t.checks.map(c => `<li class="nx-mono">${esc(c)}</li>`).join("")}</ul>
            <div class="small"><span class="fw-semibold">Suggested action:</span> ${esc(t.action)}</div>
            <div class="mt-3"><button class="btn btn-sm btn-outline-primary" data-diag="${t.id}"><i class="bi bi-search me-1"></i>Run diagnostics (demo)</button></div>
          </div></div>
        </div>`).join("")
        : `<div class="col-12"><div class="nx-card"><div class="nx-empty"><i class="bi bi-bug"></i>No scenarios match.</div></div></div>`;
      $$("[data-diag]").forEach(b => b.onclick = () => runDiagnostics(b.dataset.diag));
    }
    [sevSel, search].forEach(c => c.addEventListener("input", render));
    render();
  }
  function runDiagnostics(id) {
    const t = NX.troubleshooting.find(x => x.id === id); if (!t) return;
    const modal = buildModal("ts-diag", `Diagnostics · ${t.symptom}`, `
      <div class="small nx-muted mb-2">${esc(t.cluster)} &middot; <span class="nx-mono">${esc(t.signal)}</span></div>
      <div class="nx-runlog" id="nx-ts-log">Ready. Read-only diagnostics. Press "Run".</div>
      <p class="small nx-muted mt-2 mb-0">Diagnostics are read-only. Any fix is a separate, human-approved action.</p>`,
      "Run diagnostics");
    modal._confirm.onclick = () => {
      modal._confirm.disabled = true;
      const log = $("#nx-ts-log"); log.textContent = "";
      const lines = ["$ eksense diagnose " + id].concat(t.checks.map(c => "[check] " + c + " ... ok"))
        .concat(["[finding] " + t.likely, "[suggest] " + t.action, "Done. (Simulation. No cluster changed.)"]);
      let i = 0;
      const tick = () => {
        if (i >= lines.length) { modal._confirm.disabled = false; NX.toast(`${id} diagnostics complete (simulated).`, "success"); return; }
        log.textContent += (i ? "\n" : "") + lines[i++]; log.scrollTop = log.scrollHeight; setTimeout(tick, 420);
      };
      tick();
    };
    modal._show();
  }

  /* ============================ TECH STACK ============================ */
  function initStack() {
    const host = $("#nx-stack");
    if (!host) return;
    const kinds = [...new Set(NX.stack.map(s => s.kind))];
    const sel = $("#nx-stack-kind");
    sel.innerHTML = `<option value="">All categories</option>` + kinds.map(k => `<option>${k}</option>`).join("");
    function render() {
      const k = sel.value;
      const list = NX.stack.filter(s => !k || s.kind === k);
      host.innerHTML = list.map(s => `
        <div class="col-12 col-md-6 col-xl-4">
          <div class="nx-card h-100"><div class="nx-card-body d-flex align-items-start gap-3">
            <div class="nx-kpi-icon tone-primary" style="width:42px;height:42px;font-size:20px"><i class="bi ${s.icon}"></i></div>
            <div><div class="fw-semibold">${esc(s.name)}</div>
              <span class="nx-badge b-secondary">${esc(s.kind)}</span>
              <span class="nx-badge b-info">${esc(s.license)}</span>
              <div class="small nx-muted mt-2">${esc(s.note)}</div></div>
          </div></div>
        </div>`).join("");
    }
    sel.addEventListener("input", render);
    render();
  }

  /* ============================ SERVICES (modules) ============================ */
  function initServices() {
    const host = $("#nx-modules");
    if (!host) return;
    const search = $("#nx-mod-search");
    const groupSel = $("#nx-mod-group");
    const statusSel = $("#nx-mod-status");

    // populate group filter
    const groups = [...new Set(NX.modules.map(m => m.group))].sort();
    groupSel.innerHTML = `<option value="">All groups</option>` + groups.map(g => `<option>${g}</option>`).join("");

    const pre = qparam("q");
    if (pre) search.value = pre;

    function render() {
      const q = search.value.trim().toLowerCase();
      const g = groupSel.value, s = statusSel.value;
      const list = NX.modules.filter(m =>
        (!q || (m.id + " " + m.name + " " + m.desc + " " + m.caps.join(" ")).toLowerCase().includes(q)) &&
        (!g || m.group === g) && (!s || m.status === s));
      $("#nx-mod-count").textContent = list.length + " of " + NX.modules.length + " modules";
      if (!list.length) {
        host.innerHTML = `<div class="col-12"><div class="nx-card"><div class="nx-empty">
          <i class="bi bi-search"></i>No modules match your filters.<br>
          <button class="btn btn-sm btn-outline-secondary mt-3" id="nx-mod-clear">Clear filters</button></div></div></div>`;
        $("#nx-mod-clear").onclick = () => { search.value = ""; groupSel.value = ""; statusSel.value = ""; render(); };
        return;
      }
      host.innerHTML = list.map(m => `
        <div class="col-12 col-md-6 col-xl-4">
          <div class="nx-card nx-module h-100" onclick="location.href='service-details.html?id=${m.id}'">
            <div class="nx-card-body">
              <div class="d-flex align-items-start gap-3">
                <div class="nx-mod-icon tone-${NX.statusMeta[m.status].tone}"><i class="bi ${m.icon}"></i></div>
                <div class="flex-grow-1">
                  <div class="d-flex justify-content-between align-items-center">
                    <span class="nx-mod-id">${m.id}</span>${NX.badge(m.status)}
                  </div>
                  <div class="nx-mod-name">${esc(m.name)}</div>
                </div>
              </div>
              <p class="nx-mod-desc">${esc(m.desc)}</p>
              <div class="nx-caps">${m.caps.slice(0, 4).map(c => `<span class="nx-cap">${esc(c)}</span>`).join("")}
                ${m.caps.length > 4 ? `<span class="nx-cap">+${m.caps.length - 4}</span>` : ""}</div>
              <hr class="nx-hr">
              <div class="d-flex justify-content-between align-items-center small nx-muted">
                <span><i class="bi bi-person me-1"></i>${esc(m.owner)}</span>
                <span class="nx-badge b-secondary">${esc(m.phase)}</span>
              </div>
            </div>
          </div>
        </div>`).join("");
    }
    [search, groupSel, statusSel].forEach(c => c.addEventListener("input", render));
    render();
  }

  /* ============================ SERVICE DETAILS ============================ */
  function initServiceDetails() {
    const root = $("#nx-detail");
    if (!root) return;
    const id = qparam("id") || "M01";
    const m = NX.modules.find(x => x.id === id) || NX.modules[0];

    $("#nx-detail-title").textContent = m.id + " " + m.name;
    $("#nx-detail-breadcrumb").textContent = m.name;

    const ops = NX.operations.filter(o => o.module === m.id);
    const finds = NX.findings.filter(f => f.module === m.id);
    const acts = NX.activity.filter(a => a.module === m.id);

    $("#nx-detail-head").innerHTML = `
      <div class="d-flex align-items-start gap-3 flex-wrap">
        <div class="nx-mod-icon tone-${NX.statusMeta[m.status].tone}" style="width:56px;height:56px;font-size:28px"><i class="bi ${m.icon}"></i></div>
        <div class="flex-grow-1">
          <div class="d-flex align-items-center gap-2 flex-wrap">
            <span class="nx-mod-id">${m.id}</span>${NX.badge(m.status)}<span class="nx-badge b-secondary">Phase ${esc(m.phase)}</span>
          </div>
          <h2 class="h5 mt-1 mb-1">${esc(m.name)}</h2>
          <p class="nx-muted mb-0">${esc(m.desc)}</p>
        </div>
        <div class="text-end">
          <div class="small nx-muted">Owner</div><div class="fw-semibold">${esc(m.owner)}</div>
          <button class="btn btn-sm btn-primary mt-2" id="nx-configure"><i class="bi bi-sliders me-1"></i>Configure</button>
        </div>
      </div>`;
    $("#nx-configure").onclick = () => NX.toast("Configuration is read-only in this demo.", "info");

    // tab contents
    $("#pane-capabilities").innerHTML = `<div class="row g-3">${m.caps.map(c => `
      <div class="col-12 col-md-6 col-xl-4"><div class="nx-card h-100"><div class="nx-card-body d-flex align-items-center gap-2">
        <i class="bi bi-check-circle-fill text-success"></i><span class="fw-semibold small">${esc(c)}</span></div></div></div>`).join("")}</div>`;

    $("#pane-operations").innerHTML = ops.length ? tableHtml(
      ["Operation", "Trigger", "Risk", "Approval", "SLO"],
      ops.map(o => [`<span class="nx-id">${o.id}</span><div class="small">${esc(o.name)}</div>`, esc(o.trigger), NX.riskBadge(o.risk), esc(o.approval), esc(o.slo)])
    ) : emptyHtml("No operations registered for this module in the demo data.");

    $("#pane-findings").innerHTML = finds.length ? tableHtml(
      ["Finding", "Severity", "Asset", "Status", "SLA"],
      finds.map(f => [`<span class="nx-id">${f.id}</span><div class="small">${esc(f.title)}</div>`, NX.badge(f.severity), esc(f.asset), NX.badge(f.status), esc(f.sla)])
    ) : emptyHtml("No open findings for this module. 🎉");

    $("#pane-activity").innerHTML = acts.length
      ? `<ul class="nx-timeline">${acts.map(a => `<li class="t-${a.tone}">
          <div class="nx-tl-title small">${esc(a.action)} <span class="nx-muted">&middot; ${esc(a.target)}</span></div>
          <div class="nx-tl-meta">${esc(a.actor)} &middot; ${esc(a.decision)} &middot; ${esc(a.ts)}</div></li>`).join("")}</ul>`
      : emptyHtml("No recent activity recorded for this module.");

    wireTabs();
  }

  /* ============================ REQUESTS ============================ */
  function initRequests() {
    const tbody = $("#nx-req-body");
    if (!tbody) return;
    const search = $("#nx-req-search"), riskSel = $("#nx-req-risk"), statusSel = $("#nx-req-status");
    let sortKey = "submitted", sortDir = -1, page = 1;
    const pageSize = 6;
    let data = NX.requests.slice();

    $$("#nx-req-table th.sortable").forEach(th => th.addEventListener("click", () => {
      const k = th.dataset.key;
      if (sortKey === k) sortDir *= -1; else { sortKey = k; sortDir = 1; }
      $$("#nx-req-table th.sortable .bi").forEach(i => i.className = "bi bi-arrow-down-up");
      th.querySelector(".bi").className = "bi bi-arrow-" + (sortDir > 0 ? "up" : "down");
      render();
    }));

    function filtered() {
      const q = search.value.trim().toLowerCase(), r = riskSel.value, s = statusSel.value;
      return data.filter(x =>
        (!q || (x.id + x.item + x.team + x.requester).toLowerCase().includes(q)) &&
        (!r || x.risk === r) && (!s || x.status === s))
        .sort((a, b) => (a[sortKey] > b[sortKey] ? 1 : a[sortKey] < b[sortKey] ? -1 : 0) * sortDir);
    }
    function render() {
      const list = filtered();
      const pages = Math.max(1, Math.ceil(list.length / pageSize));
      if (page > pages) page = pages;
      const slice = list.slice((page - 1) * pageSize, page * pageSize);
      tbody.innerHTML = slice.length ? slice.map(r => `
        <tr>
          <td><span class="nx-id">${r.id}</span></td>
          <td>${esc(r.item)}<div class="small nx-muted">${esc(r.env)}</div></td>
          <td>${esc(r.team)}</td>
          <td>${NX.riskBadge(r.risk)}</td>
          <td>${esc(r.cost)}</td>
          <td>${NX.badge(r.status)}</td>
          <td class="small nx-muted">${esc(r.submitted)}</td>
          <td class="text-end">
            <button class="btn btn-sm btn-outline-secondary" data-view="${r.id}"><i class="bi bi-eye"></i></button>
            ${r.status === "pending" ? `<button class="btn btn-sm btn-outline-success" data-approve="${r.id}"><i class="bi bi-check-lg"></i></button>
            <button class="btn btn-sm btn-outline-danger" data-reject="${r.id}"><i class="bi bi-x-lg"></i></button>` : ""}
          </td>
        </tr>`).join("")
        : `<tr><td colspan="8"><div class="nx-empty"><i class="bi bi-inbox"></i>No requests match your filters.</div></td></tr>`;
      $("#nx-req-info").textContent = `Showing ${slice.length} of ${list.length} requests`;
      $("#nx-req-pages").innerHTML = pagerButtons(page, pages);
      wirePager($("#nx-req-pages"), (p) => { page = p; render(); });
      wireReqActions();
    }
    function wireReqActions() {
      $$("[data-view]").forEach(b => b.onclick = () => openRequestModal(b.dataset.view));
      $$("[data-approve]").forEach(b => b.onclick = () => decide(b.dataset.approve, "approved"));
      $$("[data-reject]").forEach(b => b.onclick = () => decide(b.dataset.reject, "rejected"));
    }
    function decide(id, status) {
      const r = data.find(x => x.id === id); if (!r) return;
      r.status = status;
      NX.toast(`${id} ${status} (simulated). No real change was made.`, status === "approved" ? "success" : "danger");
      render();
    }
    [search, riskSel, statusSel].forEach(c => c.addEventListener("input", () => { page = 1; render(); }));
    render();

    // "new request" demo modal
    const nb = $("#nx-new-request");
    if (nb) nb.onclick = () => {
      const modal = buildModal("new-req", "New self-service request", `
        <p class="nx-muted small">Guided request form (demo). Submitting creates a mock pending request.</p>
        <div class="mb-3"><label class="form-label small fw-semibold">Catalog item</label>
          <select class="form-select" id="f-item">
            <option>Standard environment baseline</option><option>Kubernetes namespace</option>
            <option>VPC and networking</option><option>PostgreSQL (non-production)</option></select></div>
        <div class="row g-3">
          <div class="col-6"><label class="form-label small fw-semibold">Team</label><input class="form-control" id="f-team" value="Payments"></div>
          <div class="col-6"><label class="form-label small fw-semibold">Environment</label>
            <select class="form-select" id="f-env"><option>sandbox</option><option>non-production</option><option>staging</option><option>production</option></select></div>
        </div>
        <div class="alert alert-info mt-3 mb-0 py-2 small"><i class="bi bi-shield-check me-1"></i>A policy gate, security scan and cost estimate would run before approval.</div>`,
        "Submit request");
      modal._confirm.onclick = () => {
        const id = "REQ-" + (2042 + Math.floor(Math.random() * 50));
        data.unshift({ id, item: $("#f-item").value, team: $("#f-team").value, requester: "demo.user",
          risk: $("#f-env").value === "production" ? "R3" : "R2", status: "pending", cost: "$—/mo",
          submitted: new Date().toISOString().slice(0, 16).replace("T", " "), env: $("#f-env").value });
        modal._hide(); page = 1; render();
        NX.toast(`${id} submitted (simulated).`, "success");
      };
      modal._show();
    };
  }

  function openRequestModal(id) {
    const r = NX.requests.find(x => x.id === id) || window.NEXUS.requests.find(x => x.id === id);
    const all = (window.__reqData || NX.requests);
    const rr = all.find(x => x.id === id) || r;
    if (!rr) return;
    const modal = buildModal("req-view", `Request ${rr.id}`, `
      <div class="row g-3">
        <div class="col-6"><div class="small nx-muted">Catalog item</div><div class="fw-semibold">${esc(rr.item)}</div></div>
        <div class="col-6"><div class="small nx-muted">Team</div><div class="fw-semibold">${esc(rr.team)}</div></div>
        <div class="col-6"><div class="small nx-muted">Requester</div><div class="fw-semibold">${esc(rr.requester)}</div></div>
        <div class="col-6"><div class="small nx-muted">Environment</div><div class="fw-semibold">${esc(rr.env)}</div></div>
        <div class="col-6"><div class="small nx-muted">Risk tier</div>${NX.riskBadge(rr.risk)}</div>
        <div class="col-6"><div class="small nx-muted">Status</div>${NX.badge(rr.status)}</div>
        <div class="col-6"><div class="small nx-muted">Estimated cost</div><div class="fw-semibold">${esc(rr.cost)}</div></div>
        <div class="col-6"><div class="small nx-muted">Submitted</div><div class="fw-semibold">${esc(rr.submitted)}</div></div>
      </div>
      <hr class="nx-hr">
      <div class="small fw-semibold mb-2">Pre-checks</div>
      <div class="d-flex flex-wrap gap-2">
        ${NX.badge("pass", "Policy gate")} ${NX.badge("warning", "Security: 1 medium")} ${NX.badge("pass", "Cost within budget")}
      </div>`, null);
    modal._show();
  }

  /* ============================ OPERATIONS ============================ */
  function initOperations() {
    const tbody = $("#nx-op-body");
    if (!tbody) return;
    const search = $("#nx-op-search"), riskSel = $("#nx-op-risk");
    function render() {
      const q = search.value.trim().toLowerCase(), r = riskSel.value;
      const list = NX.operations.filter(o =>
        (!q || (o.id + o.name + o.module + o.owner).toLowerCase().includes(q)) && (!r || o.risk === r));
      $("#nx-op-info").textContent = `${list.length} of ${NX.operations.length} operations`;
      tbody.innerHTML = list.length ? list.map(o => `
        <tr>
          <td><span class="nx-id">${o.id}</span></td>
          <td>${esc(o.name)}</td>
          <td><a href="service-details.html?id=${o.module}" class="nx-id text-decoration-none">${o.module}</a></td>
          <td class="small">${esc(o.trigger)}</td>
          <td>${NX.riskBadge(o.risk)}</td>
          <td class="small">${esc(o.approval)}</td>
          <td class="text-end"><button class="btn btn-sm ${o.risk === 'R0' || o.risk === 'R1' ? 'btn-primary' : 'btn-outline-primary'}" data-run="${o.id}"><i class="bi bi-play-fill me-1"></i>Run</button></td>
        </tr>`).join("")
        : `<tr><td colspan="7"><div class="nx-empty"><i class="bi bi-gear"></i>No operations match.</div></td></tr>`;
      $$("[data-run]").forEach(b => b.onclick = () => runOperation(b.dataset.run));
    }
    [search, riskSel].forEach(c => c.addEventListener("input", render));
    render();
  }

  function runOperation(id) {
    const o = NX.operations.find(x => x.id === id); if (!o) return;
    const needsApproval = o.risk === "R2" || o.risk === "R3";
    const modal = buildModal("op-run", `Run ${o.id}`, `
      <div class="mb-2"><span class="fw-semibold">${esc(o.name)}</span></div>
      <div class="d-flex flex-wrap gap-2 mb-3">${NX.riskBadge(o.risk)}<span class="nx-badge b-secondary">Module ${o.module}</span><span class="nx-badge b-secondary">Owner: ${esc(o.owner)}</span></div>
      ${needsApproval ? `<div class="alert alert-warning py-2 small mb-3"><i class="bi bi-person-check me-1"></i>This is a ${o.risk} operation. In production it would require explicit human approval before running.</div>` : `<div class="alert alert-success py-2 small mb-3"><i class="bi bi-check-circle me-1"></i>${o.risk} operation: may run automatically within policy.</div>`}
      <div class="nx-runlog" id="nx-run-log">Ready. Press "${needsApproval ? 'Approve & simulate' : 'Simulate run'}".</div>`,
      needsApproval ? "Approve & simulate" : "Simulate run");
    modal._confirm.onclick = () => {
      modal._confirm.disabled = true;
      const log = $("#nx-run-log"); log.textContent = "";
      const steps = [
        `$ operation ${o.id} requested`,
        `[precheck] validating inputs and scope ....... ok`,
        `[policy]   evaluating against active bundle ... allow`,
        needsApproval ? `[approval] recorded (simulated)` : `[policy]   pre-approved tier`,
        `[lock]     idempotency key acquired`,
        `[execute]  running in isolated worker ........ ok`,
        `[verify]   post-conditions ................... pass`,
        `[audit]    evidence recorded`,
        `Done. (This is a simulation. No real resources changed.)`
      ];
      let i = 0;
      const tick = () => {
        if (i >= steps.length) { modal._confirm.disabled = false; NX.toast(`${o.id} completed (simulated).`, "success"); return; }
        log.textContent += (i ? "\n" : "") + steps[i++]; log.scrollTop = log.scrollHeight;
        setTimeout(tick, 420);
      };
      tick();
    };
    modal._show();
  }

  /* ============================ VALIDATION / CHECKS ============================ */
  function initValidation() {
    const host = $("#nx-checks");
    if (!host) return;
    const typeSel = $("#nx-chk-type");
    const types = [...new Set(NX.checks.map(c => c.type))];
    typeSel.innerHTML = `<option value="">All types</option>` + types.map(t => `<option>${t}</option>`).join("");

    function render() {
      const t = typeSel.value;
      const list = NX.checks.filter(c => !t || c.type === t);
      // summary
      const sum = { pass: 0, warning: 0, fail: 0 };
      list.forEach(c => sum[c.status]++);
      $("#nx-chk-summary").innerHTML = `
        ${summaryTile("Passed", sum.pass, "success", "bi-check-circle")}
        ${summaryTile("Warnings", sum.warning, "warning", "bi-exclamation-triangle")}
        ${summaryTile("Failed", sum.fail, "danger", "bi-x-circle")}`;
      host.innerHTML = list.map(c => `
        <div class="col-12 col-xl-6">
          <div class="nx-card h-100"><div class="nx-card-body">
            <div class="d-flex justify-content-between align-items-start gap-2">
              <div><span class="nx-id">${c.id}</span> <span class="nx-badge b-secondary">${esc(c.type)}</span>
                <div class="fw-semibold mt-1">${esc(c.name)}</div></div>
              ${NX.badge(c.status)}
            </div>
            <div class="small nx-muted mt-2"><i class="bi bi-bullseye me-1"></i>${esc(c.target)}</div>
            <div class="small mt-1">${esc(c.detail)}</div>
            <div class="mt-3"><button class="btn btn-sm btn-outline-primary" data-run-check="${c.id}"><i class="bi bi-arrow-repeat me-1"></i>Re-run check</button></div>
          </div></div>
        </div>`).join("");
      $$("[data-run-check]").forEach(b => b.onclick = () => simulateCheck(b));
    }
    typeSel.addEventListener("input", render);
    render();

    const runAll = $("#nx-run-all");
    if (runAll) runAll.onclick = () => {
      runAll.disabled = true;
      runAll.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span>Running checks…`;
      setTimeout(() => {
        runAll.disabled = false;
        runAll.innerHTML = `<i class="bi bi-play-circle me-1"></i>Run all checks`;
        NX.toast("All checks completed (simulated).", "success");
      }, 1800);
    };
  }
  function simulateCheck(btn) {
    const old = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span>Running…`;
    setTimeout(() => { btn.disabled = false; btn.innerHTML = old; NX.toast("Check re-run (simulated).", "info"); }, 1300);
  }

  /* ============================ REPORTS ============================ */
  function initReports() {
    const host = $("#nx-reports");
    if (!host) return;
    host.innerHTML = NX.reports.map(r => `
      <div class="col-12 col-md-6 col-xl-4">
        <div class="nx-card h-100"><div class="nx-card-body">
          <div class="d-flex justify-content-between align-items-start">
            <span class="nx-badge b-secondary">${esc(r.type)}</span>${NX.badge(r.status)}
          </div>
          <div class="fw-bold mt-2">${esc(r.name)}</div>
          <div class="small nx-muted">${esc(r.id)} &middot; ${esc(r.period)}</div>
          <hr class="nx-hr">
          <div class="d-flex justify-content-between small">
            <span class="nx-muted">Coverage</span><span class="fw-semibold">${esc(r.coverage)}</span>
          </div>
          <div class="d-flex justify-content-between small mt-1">
            <span class="nx-muted">Owner</span><span class="fw-semibold">${esc(r.owner)}</span>
          </div>
          <div class="mt-3 d-flex gap-2">
            <button class="btn btn-sm btn-primary flex-grow-1" data-dl="${r.id}"><i class="bi bi-download me-1"></i>Download</button>
            <button class="btn btn-sm btn-outline-secondary" data-prev="${r.id}"><i class="bi bi-eye"></i></button>
          </div>
        </div></div>
      </div>`).join("");
    $$("[data-dl]").forEach(b => b.onclick = () => NX.toast(`Preparing ${b.dataset.dl} (simulated download).`, "info"));
    $$("[data-prev]").forEach(b => b.onclick = () => NX.toast(`Preview for ${b.dataset.prev} is not available in the demo.`, "warning"));
  }

  /* ============================ ACTIVITY ============================ */
  function initActivity() {
    const tbody = $("#nx-act-body");
    if (!tbody) return;
    const search = $("#nx-act-search"), toneSel = $("#nx-act-tone");
    function render() {
      const q = search.value.trim().toLowerCase(), t = toneSel.value;
      const list = NX.activity.filter(a =>
        (!q || (a.actor + a.action + a.target + a.module).toLowerCase().includes(q)) &&
        (!t || a.tone === t));
      $("#nx-act-info").textContent = `${list.length} events`;
      tbody.innerHTML = list.length ? list.map(a => `
        <tr>
          <td class="small nx-mono nx-muted">${esc(a.ts)}</td>
          <td>${esc(a.actor)}</td>
          <td class="nx-mono small">${esc(a.action)}</td>
          <td>${esc(a.target)}</td>
          <td>${NX.badge(a.tone === 'success' ? 'ready' : a.tone === 'danger' ? 'fail' : a.tone === 'warning' ? 'warning' : 'generating', a.decision)}</td>
          <td><a class="nx-id text-decoration-none" href="service-details.html?id=${a.module}">${a.module}</a></td>
        </tr>`).join("")
        : `<tr><td colspan="6"><div class="nx-empty"><i class="bi bi-clock-history"></i>No events match.</div></td></tr>`;
    }
    [search, toneSel].forEach(c => c.addEventListener("input", render));
    render();
    const exp = $("#nx-act-export");
    if (exp) exp.onclick = () => NX.toast("Audit export requested (simulated). Evidence is read-only.", "info");
  }

  /* ============================ SETTINGS ============================ */
  function initSettings() {
    wireTabs();
    const ladder = $("#nx-autonomy");
    if (ladder) ladder.innerHTML = NX.autonomy.map((a, i) => `
      <div class="d-flex align-items-start gap-3 py-2 border-bottom">
        <span class="nx-badge b-${i < 3 ? 'success' : i === 3 ? 'warning' : 'danger'}">${a.level}</span>
        <div><div class="fw-semibold small">${esc(a.name)}</div><div class="nx-muted small">${esc(a.behavior)}</div></div>
      </div>`).join("");

    const integ = $("#nx-integrations");
    if (integ) integ.innerHTML = NX.integrations.map(x => `
      <div class="col-12 col-md-6">
        <div class="nx-card"><div class="nx-card-body d-flex align-items-center gap-3">
          <div class="nx-kpi-icon tone-${NX.statusMeta[x.status].tone}" style="width:40px;height:40px;font-size:18px"><i class="bi ${x.icon}"></i></div>
          <div class="flex-grow-1"><div class="fw-semibold small">${esc(x.name)}</div>${NX.badge(x.status)}</div>
          <button class="btn btn-sm btn-outline-secondary" data-int="${esc(x.name)}">Manage</button>
        </div></div>
      </div>`).join("");
    $$("[data-int]").forEach(b => b.onclick = () => NX.toast(`Integration settings are read-only in this demo.`, "info"));

    $$("#nx-app [data-demo-save]").forEach(b => b.onclick = (e) => { e.preventDefault(); NX.toast("Preferences saved (demo only).", "success"); });
  }

  /* ============================ ADMIN PANEL ============================ */
  function initAdmin() {
    if (!$("#nx-admin")) return;
    // guard: non-admins get a notice instead of the panel
    if (!NX.session.isAdmin()) {
      $("#nx-admin").innerHTML = `<div class="nx-card"><div class="nx-empty">
        <i class="bi bi-shield-lock"></i>Admin Panel requires an admin role.<br>
        <span class="small">Sign out and sign in again as <strong>Admin</strong> or <strong>Super Admin</strong> to explore it.</span>
        <div class="mt-3"><a class="btn btn-sm btn-outline-secondary" href="index.html">Back to overview</a></div></div></div>`;
      return;
    }
    wireTabs();
    renderUsers();
    renderRolesTab();
    renderAccessMatrix();
    const addBtn = $("#nx-add-user");
    if (addBtn) addBtn.onclick = openAddUser;
  }

  let adminUsers = null;
  function renderUsers() {
    adminUsers = adminUsers || NX.users.map(u => ({ ...u }));
    const body = $("#nx-users-body");
    const search = $("#nx-user-search"), roleSel = $("#nx-user-role");
    if (roleSel && !roleSel.dataset.filled) {
      roleSel.innerHTML = `<option value="">All roles</option>` + NX.roles.map(r => `<option value="${r.id}">${esc(r.name)}</option>`).join("");
      roleSel.dataset.filled = "1";
    }
    function draw() {
      const q = (search.value || "").toLowerCase(), rf = roleSel.value;
      const list = adminUsers.filter(u => (!q || (u.name + u.email + u.team).toLowerCase().includes(q)) && (!rf || u.role === rf));
      $("#nx-users-info").textContent = `${list.length} of ${adminUsers.length} users`;
      body.innerHTML = list.length ? list.map(u => {
        const roleName = (NX.roles.find(r => r.id === u.role) || {}).name || u.role;
        return `<tr>
          <td><div class="d-flex align-items-center gap-2"><span class="nx-avatar" style="width:30px;height:30px;font-size:11px">${esc(u.name.split(" ").map(w=>w[0]).join("").slice(0,2))}</span>
            <div><div class="fw-semibold small">${esc(u.name)}</div><div class="small nx-muted">${esc(u.email)}</div></div></div></td>
          <td>${esc(u.team)}</td>
          <td><span class="nx-badge b-primary">${esc(roleName)}</span></td>
          <td>${u.mfa ? NX.badge("pass","MFA on") : NX.badge("warning","No MFA")}</td>
          <td>${u.status === "active" ? NX.badge("ready","Active") : NX.badge("rejected","Suspended")}</td>
          <td class="small nx-muted">${esc(u.last)}</td>
          <td class="text-end">
            <select class="nx-access-sel" data-role-for="${u.id}">${NX.roles.map(r => `<option value="${r.id}" ${r.id===u.role?"selected":""}>${esc(r.name)}</option>`).join("")}</select>
            <button class="btn btn-sm btn-outline-${u.status==="active"?"warning":"success"}" data-toggle-user="${u.id}">${u.status==="active"?"Suspend":"Activate"}</button>
          </td>
        </tr>`;
      }).join("") : `<tr><td colspan="7"><div class="nx-empty"><i class="bi bi-people"></i>No users match.</div></td></tr>`;
      $$("[data-role-for]").forEach(s => s.onchange = () => {
        const u = adminUsers.find(x => x.id === s.dataset.roleFor); u.role = s.value;
        NX.toast(`${u.name} role changed to ${s.options[s.selectedIndex].text} (demo).`, "success"); draw();
      });
      $$("[data-toggle-user]").forEach(b => b.onclick = () => {
        const u = adminUsers.find(x => x.id === b.dataset.toggleUser);
        u.status = u.status === "active" ? "suspended" : "active";
        NX.toast(`${u.name} ${u.status} (demo).`, u.status === "active" ? "success" : "warning"); draw();
      });
    }
    [search, roleSel].forEach(c => c.addEventListener("input", draw));
    draw();
  }
  function openAddUser() {
    const modal = buildModal("add-user", "Add user", `
      <p class="nx-muted small">Create a user record (demo only; no invite is sent).</p>
      <div class="mb-3"><label class="form-label small fw-semibold">Full name</label><input class="form-control" id="au-name" placeholder="Jane Doe"></div>
      <div class="mb-3"><label class="form-label small fw-semibold">Email</label><input class="form-control" id="au-email" type="email" placeholder="jane.doe@example.com"></div>
      <div class="row g-3">
        <div class="col-6"><label class="form-label small fw-semibold">Team</label><input class="form-control" id="au-team" value="Platform"></div>
        <div class="col-6"><label class="form-label small fw-semibold">Role</label>
          <select class="form-select" id="au-role">${NX.roles.map(r => `<option value="${r.id}">${esc(r.name)}</option>`).join("")}</select></div>
      </div>
      <div class="form-check mt-3"><input class="form-check-input" type="checkbox" id="au-mfa" checked><label class="form-check-label small" for="au-mfa">Require MFA</label></div>`,
      "Add user");
    modal._confirm.onclick = () => {
      const name = ($("#au-name").value || "").trim(); if (!name) { NX.toast("Enter a name.", "warning"); return; }
      adminUsers.unshift({ id: "u-" + Math.floor(Math.random()*900+100), name, email: ($("#au-email").value||"").trim()||"user@example.com",
        role: $("#au-role").value, team: $("#au-team").value || "Platform", status: "active", mfa: $("#au-mfa").checked, last: "just now" });
      modal._hide(); renderUsers(); NX.toast(`${name} added (demo).`, "success");
    };
    modal._show();
  }
  function renderRolesTab() {
    const host = $("#nx-roles");
    if (!host) return;
    host.innerHTML = NX.roles.map(r => `
      <div class="col-12 col-md-6 col-xl-4"><div class="nx-card h-100"><div class="nx-card-body">
        <div class="d-flex justify-content-between align-items-center"><span class="fw-bold">${esc(r.name)}</span>
          <span class="nx-badge b-secondary">${adminUsers ? adminUsers.filter(u=>u.role===r.id).length : NX.users.filter(u=>u.role===r.id).length} users</span></div>
        <div class="small nx-muted mt-1">${esc(r.desc)}</div>
      </div></div></div>`).join("");
  }
  function renderAccessMatrix() {
    const host = $("#nx-access");
    if (!host) return;
    const levels = Object.keys(NX.accessLevelMeta);
    host.innerHTML = `<div class="nx-table-wrap"><table class="nx-table nx-matrix"><thead><tr>
      <th>Resource / service</th>${NX.roles.map(r => `<th>${esc(r.name)}</th>`).join("")}</tr></thead><tbody>
      ${NX.accessResources.map(res => `<tr><td>${esc(res)}</td>${NX.roles.map(r => {
        const lvl = (NX.accessMatrix[r.id] || {})[res] || "none";
        return `<td><select class="nx-access-sel" data-res="${esc(res)}" data-role="${r.id}">${levels.map(l =>
          `<option value="${l}" ${l===lvl?"selected":""}>${NX.accessLevelMeta[l].label}</option>`).join("")}</select></td>`;
      }).join("")}</tr>`).join("")}
      </tbody></table></div>`;
    $$("[data-res][data-role]", host).forEach(s => s.onchange = () => {
      NX.accessMatrix[s.dataset.role] = NX.accessMatrix[s.dataset.role] || {};
      NX.accessMatrix[s.dataset.role][s.dataset.res] = s.value;
      NX.toast(`Access updated: ${s.dataset.role} · ${s.dataset.res} → ${s.options[s.selectedIndex].text} (demo).`, "info");
    });
  }

  /* ============================ DESCRIBE -> YAML ============================ */
  function initRequirements() {
    const input = $("#nx-req-input");
    if (!input) return;
    // example chips
    $("#nx-req-chips").innerHTML = NX.requirementExamples.map((x, i) =>
      `<button class="btn btn-sm btn-outline-secondary" data-ex="${i}">${esc(x.slice(0, 48))}…</button>`).join("");
    $$("[data-ex]").forEach(b => b.onclick = () => { input.value = NX.requirementExamples[+b.dataset.ex]; });

    $("#nx-req-generate").onclick = () => {
      const text = input.value.trim();
      if (!text) { NX.toast("Describe what you need first.", "warning"); return; }
      const btn = $("#nx-req-generate"); btn.disabled = true;
      btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span>Generating…`;
      setTimeout(() => {
        btn.disabled = false; btn.innerHTML = `<i class="bi bi-magic me-1"></i>Generate YAML`;
        const parsed = parseRequirement(text);
        $("#nx-req-yaml").innerHTML = highlightYaml(parsed.yaml);
        $("#nx-req-understood").innerHTML = parsed.understood.map(u => `<li>${esc(u)}</li>`).join("");
        $("#nx-req-result").style.display = "";
        setFlow("nx-req-flow", 2);
        NX.toast("YAML generated from your requirement (simulated).", "success");
      }, 900);
    };
    wireYamlActions("nx-req", "nx-req-flow");
  }

  // very small keyword parser so the demo feels real without a backend
  function parseRequirement(text) {
    const t = text.toLowerCase();
    const num = (re, def) => { const m = text.match(re); return m ? m[1] : def; };
    const understood = [];
    let yaml = "", kind = "namespace";
    if (/helm|chart|deploy .* chart|release/.test(t)) kind = "helm";
    else if (/database|postgres|mysql|rds/.test(t)) kind = "database";
    else if (/environment|account|vpc|standard env/.test(t)) kind = "environment";
    else if (/namespace|quota|network policy/.test(t)) kind = "namespace";

    if (kind === "namespace") {
      const ns = (text.match(/namespace (?:called |named )?["']?([a-z0-9-]+)/i) || [])[1] || "team-staging";
      const cpu = num(/(\d+)\s*(?:v?cpu|cores?)/i, "8");
      const mem = num(/(\d+)\s*gi\w* (?:memory|ram)?/i, "16");
      understood.push(`Kind: Kubernetes Namespace (${ns})`, `Resource quota: ${cpu} CPU / ${mem}Gi memory`, "Network policy: default-deny");
      yaml = nsYaml({ name: ns, cpu, mem, netpol: /network policy|default.?deny/.test(t) });
    } else if (kind === "helm") {
      const chart = (text.match(/\b([a-z0-9-]+) helm chart|chart ([a-z0-9-]+)/i) || [])[1] || "web";
      const ver = num(/version\s*v?([0-9.]+)/i, "1.0.0");
      const ns = (text.match(/\bto the ([a-z0-9-]+) namespace|namespace ([a-z0-9-]+)/i) || [])[1] || "default";
      const rep = num(/(\d+)\s*replicas?/i, "2");
      const host = (text.match(/host ([a-z0-9.-]+\.[a-z]{2,})/i) || [])[1] || "app.example.com";
      const img = (text.match(/image ([a-z0-9./:-]+)/i) || [])[1] || (chart + ":" + ver);
      understood.push(`Kind: Helm release (${chart} ${ver})`, `Namespace: ${ns}`, `Replicas: ${rep}`, `Image: ${img}`, `Ingress host: ${host}`);
      yaml = helmYaml({ release: chart, chart, repo: "https://charts.example.com", version: ver, namespace: ns, replicas: rep, image: img, host });
    } else if (kind === "database") {
      const eng = /mysql/.test(t) ? "mysql" : "postgres";
      understood.push(`Kind: Database (${eng})`, "Multi-AZ: yes", "Backups: 7 days with PITR");
      yaml = dbYaml({ engine: eng, team: (text.match(/for ([a-z]+)/i) || [])[1] || "app", multiaz: true, backups: 7 });
    } else {
      const team = (text.match(/for the ([a-z]+) team|for ([a-z]+)/i) || [])[1] || "Platform";
      const region = (text.match(/\b(us-[a-z]+-\d|eu-[a-z]+-\d|ap-[a-z]+-\d)\b/i) || [])[1] || "us-east-2";
      understood.push(`Kind: Standard environment (Atmos)`, `Team: ${team}`, `Region: ${region}`, "Logging and budgets: enabled");
      yaml = envYaml({ team, region });
    }
    return { yaml, understood };
  }

  /* ============================ INFRASTRUCTURE BUILDER ============================ */
  function initBuilder() {
    const kindSel = $("#nx-b-kind");
    if (!kindSel) return;
    kindSel.innerHTML = NX.builderKinds.map(k => `<option value="${k.id}">${esc(k.name)}</option>`).join("");
    kindSel.addEventListener("change", () => { renderBuilderForm(kindSel.value); regen(); });
    $("#nx-b-form").addEventListener("input", regen);
    renderBuilderForm(kindSel.value);
    regen();
    wireYamlActions("nx-b", "nx-b-flow");

    function regen() {
      const vals = {};
      $$("#nx-b-form [data-field]").forEach(f => vals[f.dataset.field] = (f.type === "checkbox" ? f.checked : f.value));
      let yaml = "";
      switch (kindSel.value) {
        case "namespace": yaml = nsYaml({ name: vals.name || "team-staging", cpu: vals.cpu || "8", mem: vals.mem || "16", netpol: vals.netpol }); break;
        case "helm": yaml = helmYaml({ release: vals.release || "web", chart: vals.chart || "web", repo: vals.repo || "https://charts.example.com",
          version: vals.version || "1.0.0", namespace: vals.namespace || "default", replicas: vals.replicas || "2", image: vals.image || "web:1.0.0",
          host: vals.host, cpuReq: vals.cpuReq, memReq: vals.memReq, cpuLim: vals.cpuLim, memLim: vals.memLim, svcType: vals.svcType,
          hpaMin: vals.hpaMin, hpaMax: vals.hpaMax, sa: vals.sa }); break;
        case "environment": yaml = envYaml({ team: vals.team || "Platform", region: vals.region || "us-east-2", env: vals.env || "non-production", budget: vals.budget || "500" }); break;
        case "database": yaml = dbYaml({ engine: vals.engine || "postgres", team: vals.team || "app", size: vals.size || "db.r6g.large", storage: vals.storage || "100", multiaz: vals.multiaz, backups: vals.backups || "7" }); break;
      }
      $("#nx-b-yaml").innerHTML = highlightYaml(yaml);
      setFlow("nx-b-flow", 1);
    }
  }

  function renderBuilderForm(kind) {
    const f = $("#nx-b-form");
    const row = (html) => `<div class="row g-2 mb-1">${html}</div>`;
    const col = (label, field, input, hint) => `<div class="col-md-6"><label class="form-label">${label}</label>${input}
      ${hint ? `<div class="form-text nx-muted">${hint}</div>` : ""}</div>`;
    const txt = (field, val, ph) => `<input class="form-control form-control-sm" data-field="${field}" value="${val != null ? esc(val) : ""}" placeholder="${ph || ""}">`;
    const sel = (field, opts, val) => `<select class="form-select form-select-sm" data-field="${field}">${opts.map(o => `<option ${o===val?"selected":""}>${o}</option>`).join("")}</select>`;
    const chk = (field, label, on) => `<div class="form-check mt-1"><input class="form-check-input" type="checkbox" data-field="${field}" ${on?"checked":""} id="f-${field}"><label class="form-check-label small" for="f-${field}">${label}</label></div>`;

    if (kind === "namespace") {
      f.innerHTML =
        row(col("Namespace name", "name", txt("name", "payments-staging")) + col("Team label", "team", txt("team", "payments"))) +
        row(col("CPU quota (cores)", "cpu", txt("cpu", "8")) + col("Memory quota (Gi)", "mem", txt("mem", "16"))) +
        chk("netpol", "Apply default-deny network policy", true);
    } else if (kind === "helm") {
      f.innerHTML =
        `<div class="fw-semibold small mt-1 mb-2"><i class="bi bi-box-seam me-1"></i>Helm chart</div>` +
        row(col("Chart repository", "repo", txt("repo", "https://charts.example.com"), "Helm repo URL") +
            col("Chart name", "chart", txt("chart", "web"))) +
        row(col("Chart version", "version", txt("version", "1.6.2")) + col("Release name", "release", txt("release", "web"))) +
        row(col("Namespace", "namespace", txt("namespace", "shop")) + col("Image (repo:tag)", "image", txt("image", "web:1.6.2"))) +
        `<div class="fw-semibold small mt-3 mb-2"><i class="bi bi-sliders me-1"></i>Values</div>` +
        row(col("Replicas", "replicas", txt("replicas", "3")) + col("Service type", "svcType", sel("svcType", ["ClusterIP","NodePort","LoadBalancer"], "ClusterIP"))) +
        row(col("CPU request", "cpuReq", txt("cpuReq", "250m")) + col("Memory request", "memReq", txt("memReq", "256Mi"))) +
        row(col("CPU limit", "cpuLim", txt("cpuLim", "500m")) + col("Memory limit", "memLim", txt("memLim", "512Mi"))) +
        row(col("Ingress host", "host", txt("host", "shop.example.com")) + col("Service account (IRSA)", "sa", txt("sa", "web-sa"))) +
        `<div class="fw-semibold small mt-3 mb-2"><i class="bi bi-arrows-expand me-1"></i>Autoscaling</div>` +
        row(col("HPA min replicas", "hpaMin", txt("hpaMin", "3")) + col("HPA max replicas", "hpaMax", txt("hpaMax", "10")));
    } else if (kind === "environment") {
      f.innerHTML =
        row(col("Team", "team", txt("team", "Search")) + col("Environment", "env", sel("env", ["sandbox","non-production","staging","production"], "non-production"))) +
        row(col("Region", "region", sel("region", ["us-east-1","us-east-2","us-west-2","eu-west-1","ap-south-1"], "us-east-2")) + col("Monthly budget (USD)", "budget", txt("budget", "500")));
    } else if (kind === "database") {
      f.innerHTML =
        row(col("Engine", "engine", sel("engine", ["postgres","mysql"], "postgres")) + col("Team / owner", "team", txt("team", "orders"))) +
        row(col("Instance class", "size", txt("size", "db.r6g.large")) + col("Storage (GiB)", "storage", txt("storage", "100"))) +
        row(col("Backup retention (days)", "backups", txt("backups", "7")) + `<div class="col-md-6 d-flex align-items-end">${chk("multiaz", "Multi-AZ high availability", true)}</div>`);
    }
  }

  /* ---- YAML generators (plain text; highlighted on render) ---- */
  function nsYaml(o) {
    return `# Generated by FDE Nexus (demo). Review before use.
apiVersion: v1
kind: Namespace
metadata:
  name: ${o.name}
  labels:
    team: ${o.team || o.name.split("-")[0]}
    managed-by: fde-nexus
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: ${o.name}-quota
  namespace: ${o.name}
spec:
  hard:
    requests.cpu: "${o.cpu}"
    requests.memory: ${o.mem}Gi
    limits.cpu: "${o.cpu}"
    limits.memory: ${o.mem}Gi
${o.netpol ? `---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
  namespace: ${o.name}
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
` : ""}`;
  }
  function helmYaml(o) {
    return `# Generated by FDE Nexus (demo). Review before use.
# Argo CD Application wrapping a Helm chart.
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ${o.release}
  namespace: argocd
spec:
  project: default
  source:
    repoURL: ${o.repo}
    chart: ${o.chart}
    targetRevision: ${o.version}
    helm:
      releaseName: ${o.release}
      values: |
        replicaCount: ${o.replicas}
        image:
          repository: ${(o.image || "web:1.0.0").split(":")[0]}
          tag: "${(o.image || "web:1.0.0").split(":")[1] || "latest"}"
        serviceAccount:
          create: true
          name: ${o.sa || o.release + "-sa"}
        service:
          type: ${o.svcType || "ClusterIP"}
          port: 80
        resources:
          requests:
            cpu: ${o.cpuReq || "250m"}
            memory: ${o.memReq || "256Mi"}
          limits:
            cpu: ${o.cpuLim || "500m"}
            memory: ${o.memLim || "512Mi"}
        ingress:
          enabled: ${o.host ? "true" : "false"}
          host: ${o.host || "app.example.com"}
        autoscaling:
          enabled: true
          minReplicas: ${o.hpaMin || o.replicas}
          maxReplicas: ${o.hpaMax || 10}
  destination:
    server: https://kubernetes.default.svc
    namespace: ${o.namespace}
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions: [CreateNamespace=true]
`;
  }
  function envYaml(o) {
    return `# Generated by FDE Nexus (demo). Atmos stack configuration.
# Review before use. Deployed via Atmos + Terraform.
import:
  - catalog/standard-environment
vars:
  team: ${o.team}
  environment: ${o.env || "non-production"}
  region: ${o.region}
  tags:
    team: ${o.team}
    managed-by: fde-nexus
    cost-center: ${(o.team || "team").toLowerCase()}-cc
components:
  terraform:
    vpc:
      vars:
        cidr_block: 10.0.0.0/16
        availability_zones: 3
    logging:
      vars: { enabled: true }
    budgets:
      vars:
        monthly_limit_usd: ${o.budget || 500}
        alert_thresholds: [50, 80, 100]
`;
  }
  function dbYaml(o) {
    return `# Generated by FDE Nexus (demo). Terraform-ready values.
# Review before use.
database:
  engine: ${o.engine}
  owner_team: ${o.team}
  instance_class: ${o.size || "db.r6g.large"}
  allocated_storage_gib: ${o.storage || 100}
  multi_az: ${o.multiaz ? "true" : "false"}
  storage_encrypted: true
  kms_key: customer-managed
  backup:
    retention_days: ${o.backups}
    point_in_time_recovery: true
  tags:
    owner: ${o.team}
    managed-by: fde-nexus
`;
  }

  /* ---- shared YAML helpers: highlight, flow, copy / PR / Slack ---- */
  function highlightYaml(text) {
    return esc(text).split("\n").map(line => {
      if (/^\s*#/.test(line)) return `<span class="c">${line}</span>`;
      if (/^\s*---\s*$/.test(line)) return `<span class="d">${line}</span>`;
      const m = line.match(/^(\s*[-\w.]+:)(.*)$/);
      if (m) return `<span class="k">${m[1]}</span><span class="v">${m[2]}</span>`;
      return line;
    }).join("\n");
  }
  function setFlow(id, step) {
    const host = $("#" + id); if (!host) return;
    $$(".step", host).forEach((s, i) => s.classList.toggle("done", i < step));
  }
  function wireYamlActions(prefix, flowId) {
    const copy = $("#" + prefix + "-copy");
    if (copy) copy.onclick = () => {
      const txt = $("#" + prefix + "-yaml").innerText;
      (navigator.clipboard ? navigator.clipboard.writeText(txt) : Promise.reject()).then(
        () => NX.toast("YAML copied to clipboard.", "success"),
        () => NX.toast("Copy not available in this browser.", "warning"));
    };
    const pr = $("#" + prefix + "-pr");
    if (pr) pr.onclick = () => {
      const n = 100 + Math.floor(Math.random() * 800);
      setFlow(flowId, 4);
      const modal = buildModal(prefix + "-pr", "Pull request created (simulated)", `
        <div class="d-flex align-items-center gap-2 mb-2"><i class="bi bi-github" style="font-size:22px"></i>
          <span class="fw-semibold">infra-repo #${n}</span>${NX.badge("ready","Open")}</div>
        <p class="small mb-2">A branch <span class="nx-mono">nexus/generated-${n}</span> was pushed and a pull request opened with the generated manifest.</p>
        <div class="nx-slack"><div class="small nx-muted mb-1"><i class="bi bi-github me-1"></i>GitHub Actions</div>
          <div class="nx-slack-msg"><span class="nx-mono">plan</span> ✓ · <span class="nx-mono">policy</span> ✓ · <span class="nx-mono">security scan</span> ⚠ 1 medium · awaiting review</div></div>
        <p class="small nx-muted mt-2 mb-0">Simulated. No branch or PR is really created.</p>`, null);
      modal._show();
      NX.toast(`PR #${n} opened (simulated).`, "success");
    };
    const slack = $("#" + prefix + "-slack");
    if (slack) slack.onclick = () => {
      setFlow(flowId, 3);
      const modal = buildModal(prefix + "-slack", "Sent to Slack (simulated)", `
        <div class="nx-slack">
          <div class="small nx-muted mb-2"><i class="bi bi-slack me-1"></i>#cloud-requests</div>
          <div class="nx-slack-msg mb-2"><span class="nx-slack-user">you</span>: requesting the generated infrastructure, please review.</div>
          <div class="nx-slack-msg"><span class="nx-slack-user">nexus-bot</span>: Got it. I validated the manifest and opened a draft PR. React with ✅ to approve, or reply <span class="nx-mono">/changes</span>.</div>
        </div>
        <p class="small nx-muted mt-2 mb-0">Simulated. No message is sent to Slack.</p>`, "Open the PR");
      modal._confirm.onclick = () => { modal._hide(); if (pr) pr.click(); };
      modal._show();
    };
  }

  /* ============================ shared bits ============================ */
  function tableHtml(headers, rows) {
    return `<div class="nx-table-wrap"><table class="nx-table"><thead><tr>${headers.map(h => `<th>${h}</th>`).join("")}</tr></thead>
      <tbody>${rows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  }
  function emptyHtml(msg) { return `<div class="nx-empty"><i class="bi bi-inbox"></i>${esc(msg)}</div>`; }
  function summaryTile(label, value, tone, icon) {
    return `<div class="col-4"><div class="nx-card"><div class="nx-card-body nx-kpi">
      <div class="nx-kpi-icon tone-${tone}"><i class="bi ${icon}"></i></div>
      <div><div class="nx-kpi-value">${value}</div><div class="nx-kpi-label">${label}</div></div></div></div></div>`;
  }
  function pagerButtons(page, pages) {
    let html = `<button class="btn btn-sm btn-outline-secondary" data-p="${page - 1}" ${page <= 1 ? "disabled" : ""}><i class="bi bi-chevron-left"></i></button>`;
    for (let p = 1; p <= pages; p++) html += `<button class="btn btn-sm ${p === page ? "btn-primary" : "btn-outline-secondary"}" data-p="${p}">${p}</button>`;
    html += `<button class="btn btn-sm btn-outline-secondary" data-p="${page + 1}" ${page >= pages ? "disabled" : ""}><i class="bi bi-chevron-right"></i></button>`;
    return html;
  }
  function wirePager(host, cb) { $$("[data-p]", host).forEach(b => b.onclick = () => { if (!b.disabled) cb(+b.dataset.p); }); }

  function wireTabs() {
    $$(".nx-tabs").forEach(group => {
      const buttons = $$("button", group);
      buttons.forEach(btn => btn.onclick = () => {
        buttons.forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        const target = btn.dataset.tab;
        $$(".nx-tabpane").forEach(p => {
          if (p.dataset.pane === target || p.id === "pane-" + target) p.classList.toggle("active", true);
          else if (p.dataset.group === group.dataset.group) p.classList.remove("active");
        });
        // simpler: toggle by id match within same container
        const container = group.closest(".nx-card, .nx-tab-host, body");
        $$(".nx-tabpane", container).forEach(p => p.classList.toggle("active", p.id === "pane-" + target || p.dataset.pane === target));
      });
    });
  }

  /* Bootstrap modal builder */
  function buildModal(id, title, bodyHtml, confirmLabel) {
    let host = document.getElementById("nx-modal-" + id);
    if (host) host.remove();
    host = document.createElement("div");
    host.className = "modal fade"; host.id = "nx-modal-" + id; host.tabIndex = -1;
    host.innerHTML = `<div class="modal-dialog modal-dialog-centered">
      <div class="modal-content">
        <div class="modal-header"><h5 class="modal-title">${esc(title)}</h5>
          <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div>
        <div class="modal-body">${bodyHtml}</div>
        <div class="modal-footer">
          <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Close</button>
          ${confirmLabel ? `<button type="button" class="btn btn-primary" id="nx-modal-confirm-${id}">${esc(confirmLabel)}</button>` : ""}
        </div>
      </div></div>`;
    document.body.appendChild(host);
    const inst = bootstrap.Modal.getOrCreateInstance(host);
    host.addEventListener("hidden.bs.modal", () => host.remove());
    return { _el: host, _show: () => inst.show(), _hide: () => inst.hide(), _confirm: document.getElementById("nx-modal-confirm-" + id) };
  }

  /* ---- router: call the init for the current page ---- */
  document.addEventListener("DOMContentLoaded", () => {
    const page = (document.getElementById("nx-app") || {}).getAttribute
      ? document.getElementById("nx-app").getAttribute("data-page") : "";
    const map = {
      "index.html": initOverview,
      "applications.html": initTools,
      "troubleshooting.html": initTroubleshooting,
      "stack.html": initStack,
      "requirements.html": initRequirements,
      "builder.html": initBuilder,
      "admin.html": initAdmin,
      "services.html": initServices,
      "service-details.html": initServiceDetails,
      "requests.html": initRequests,
      "operations.html": initOperations,
      "validation.html": initValidation,
      "reports.html": initReports,
      "activity.html": initActivity,
      "settings.html": initSettings
    };
    // run after components.js has injected the shell
    setTimeout(() => { (map[page] || function () {})(); }, 0);
  });
})();
