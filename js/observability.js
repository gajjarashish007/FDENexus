/* M11 Observability & SRE workspace. */
(function () {
  "use strict";
  const NX = window.NEXUS, UI = NX.ui, esc = NX.esc, $ = UI.$, $$ = UI.$$;
  const S = { tab: "overview", ov: null };
  const me = () => NX.session.get() || {};
  const loading = () => '<div class="nx-empty"><i class="bi bi-hourglass-split"></i>Loading…</div>';
  const fail = (e) => `<div class="alert alert-danger small">${esc(UI.errorText(e))}</div>`;
  const tbl = (head, rows, empty) => rows.length ? `<div class="nx-card"><div class="nx-table-wrap"><table class="nx-table"><thead><tr>${head.map(h => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div></div>`
    : `<div class="nx-card"><div class="nx-empty"><i class="bi bi-inbox"></i>${esc(empty)}</div></div>`;
  const sevBadge = (s) => ({ critical: "danger", high: "warning", medium: "info", low: "secondary", info: "secondary" }[s] || "secondary");
  const statusBadge = (s) => `<span class="nx-badge b-${{ open: "danger", investigating: "warning", identified: "primary", monitoring: "info", resolved: "success" }[s] || "secondary"}">${esc(s)}</span>`;
  const acctSel = (id) => `<select class="form-select" id="${id}" style="max-width:320px">${(NX.awsAccounts || []).map(a => `<option value="${esc(a.id)}" ${a.id === NX.activeAccount.getId() ? "selected" : ""}>${esc(a.alias)} (${esc(a.id)})</option>`).join("")}</select>`;

  async function overview() {
    S.ov = await NX.api.get("/api/m11/overview");
    const o = S.ov, k = (l, v, i, t, sub) => `<div class="col-6 col-xl-2"><div class="nx-card h-100"><div class="nx-card-body nx-kpi"><div class="nx-kpi-icon tone-${t}"><i class="bi ${i}"></i></div>
      <div><div class="nx-kpi-value" style="font-size:20px">${esc(v)}</div><div class="nx-kpi-label">${esc(l)}</div>${sub ? `<div class="small nx-muted">${esc(sub)}</div>` : ""}</div></div></div></div>`;
    const h = o.services_by_health || {};
    $("#obs-kpis").innerHTML = k("Services", o.services, "bi-diagram-3", "primary", `${h.healthy || 0} healthy`) +
      k("Incidents", o.incidents_open, "bi-exclamation-octagon", o.incidents_open ? "danger" : "success", `by severity`) +
      k("Alerts firing", o.alerts_firing, "bi-bell", o.alerts_firing ? "warning" : "success") +
      k("SLOs burning", o.slos_burning, "bi-speedometer2", o.slos_burning ? "danger" : "success", `of ${o.slos_total}`) +
      k("Healthy", h.healthy || 0, "bi-check-circle", "success") +
      k("Degraded", h.degraded || 0, "bi-exclamation-circle", h.degraded ? "warning" : "secondary");
  }

  async function drawServices() {
    const r = await NX.api.get("/api/m11/services");
    const healthIcon = { healthy: "check-circle text-success", degraded: "exclamation-circle text-warning", down: "x-circle text-danger", unknown: "question-circle text-secondary" };
    $("#obs-pane").innerHTML = tbl(["Service", "Tier", "Team", "Health", "SLO", "Error budget", ""], r.services.map(s => `<tr>
      <td><div class="fw-semibold small">${esc(s.name)}</div><div class="nx-mono nx-muted">${esc(s.id)}</div></td>
      <td class="small">${esc(s.tier || "-")}</td>
      <td class="small">${esc(s.team || "-")}</td>
      <td><i class="bi bi-${healthIcon[s.health] || healthIcon.unknown}"></i></td>
      <td class="small">${s.slo_target ? `${esc(s.slo_target)}%` : "-"}</td>
      <td class="small">${s.error_budget_remaining !== undefined ? `${esc(s.error_budget_remaining)}%` : "-"}</td>
      <td><button class="btn btn-sm btn-outline-secondary" data-svc="${esc(s.id)}"><i class="bi bi-eye"></i></button></td></tr>`), "No services. Add one to track SLOs.");
    $$("[data-svc]").forEach(b => b.onclick = async () => {
      const s = await NX.api.get(`/api/m11/services/${b.dataset.svc}`);
      UI.modal(`Service ${s.service.name}`, `<div class="small"><div><b>Tier:</b> ${esc(s.service.tier || "-")}</div><div><b>Team:</b> ${esc(s.service.team || "-")}</div><div><b>Owner:</b> ${esc(s.service.owner || "-")}</div><div><b>SLO:</b> ${s.service.slo_target ? esc(s.service.slo_target) + "%" : "not set"}</div></div>`, { footer: '<button class="btn btn-primary" id="svc-edit">Edit</button>' });
    });
  }

  async function drawIncidents() {
    const r = await NX.api.get("/api/m11/incidents?limit=100");
    $("#obs-pane").innerHTML = `<div class="d-flex justify-content-end mb-2"><button class="btn btn-sm btn-danger" id="inc-new"><i class="bi bi-plus-lg me-1"></i>New incident</button></div>` +
      tbl(["Incident", "Service", "Severity", "Status", "Created", "Duration", ""], r.incidents.map(i => `<tr>
        <td><div class="fw-semibold small">${esc(i.title)}</div><div class="nx-mono nx-muted">${esc(i.id)}</div></td>
        <td class="small">${esc(i.service_id || "-")}</td>
        <td><span class="nx-badge b-${sevBadge(i.severity)}">${esc(i.severity)}</span></td>
        <td>${statusBadge(i.status)}</td>
        <td class="small">${esc(i.created_at)}</td>
        <td class="small">${i.duration_minutes ? esc(i.duration_minutes) + " min" : "-"}</td>
        <td style="white-space:nowrap">
          ${i.status === "open" ? `<button class="btn btn-sm btn-outline-primary" data-ack="${esc(i.id)}">Ack</button>` : ""}
          ${i.status !== "resolved" ? `<button class="btn btn-sm btn-outline-success" data-res="${esc(i.id)}">Resolve</button>` : ""}
        </td></tr>`), "No incidents. Good news!");
    $("#inc-new").onclick = async () => {
      const m = UI.modal("New incident", `<div class="row g-3">
        <div class="col-12"><label class="form-label small fw-semibold">Title</label><input class="form-control" id="inc-title" placeholder="API latency spike"></div>
        <div class="col-md-6"><label class="form-label small fw-semibold">Severity</label><select class="form-select" id="inc-sev">${["critical", "high", "medium", "low", "info"].map(s => `<option>${s}</option>`).join("")}</select></div>
        <div class="col-md-6"><label class="form-label small fw-semibold">Service</label><input class="form-control" id="inc-svc" placeholder="SVC-xxxx"></div>
      </div>`, { footer: '<button class="btn btn-danger" id="inc-go">Create</button>' });
      $("#inc-go", m.el).onclick = async () => {
        try { await NX.api.post("/api/m11/incidents", { title: $("#inc-title", m.el).value, severity: $("#inc-sev", m.el).value, service_id: $("#inc-svc", m.el).value }); m.hide(); NX.toast("Incident created.", "success"); drawIncidents(); }
        catch (e) { NX.toast(UI.errorText(e), "danger"); }
      };
    };
    $$("[data-ack]").forEach(b => b.onclick = async () => {
      try { await NX.api.post(`/api/m11/incidents/${b.dataset.ack}/acknowledge`); NX.toast("Acknowledged.", "success"); drawIncidents(); }
      catch (e) { NX.toast(UI.errorText(e), "danger"); }
    });
    $$("[data-res]").forEach(b => b.onclick = async () => {
      const rca = prompt("Root cause analysis (optional):");
      try { await NX.api.post(`/api/m11/incidents/${b.dataset.res}/resolve`, { rca }); NX.toast("Resolved.", "success"); drawIncidents(); }
      catch (e) { NX.toast(UI.errorText(e), "danger"); }
    });
  }

  async function drawAlerts() {
    const r = await NX.api.get("/api/m11/alerts?limit=100");
    $("#obs-pane").innerHTML = tbl(["Alert", "Source", "Severity", "Status", "Created", ""], r.alerts.map(a => `<tr>
      <td><div class="fw-semibold small">${esc(a.name)}</div><div class="nx-mono nx-muted">${esc(a.id)}</div></td>
      <td class="small">${esc(a.source)}</td>
      <td><span class="nx-badge b-${sevBadge(a.severity)}">${esc(a.severity)}</span></td>
      <td>${statusBadge(a.status)}</td>
      <td class="small">${esc(a.created_at)}</td>
      <td>
        ${a.status === "firing" ? `<button class="btn btn-sm btn-outline-primary" data-aack="${esc(a.id)}">Ack</button>` : ""}
        ${a.status !== "resolved" ? `<button class="btn btn-sm btn-outline-success" data-ares="${esc(a.id)}">Resolve</button>` : ""}
      </td></tr>`), "No active alerts.");
    $$("[data-aack]").forEach(b => b.onclick = async () => {
      try { await NX.api.post(`/api/m11/alerts/${b.dataset.aack}/acknowledge`); NX.toast("Acknowledged.", "success"); drawAlerts(); }
      catch (e) { NX.toast(UI.errorText(e), "danger"); }
    });
    $$("[data-ares]").forEach(b => b.onclick = async () => {
      try { await NX.api.post(`/api/m11/alerts/${b.dataset.ares}/resolve`); NX.toast("Resolved.", "success"); drawAlerts(); }
      catch (e) { NX.toast(UI.errorText(e), "danger"); }
    });
  }

  async function drawSlos() {
    const r = await NX.api.get("/api/m11/slos");
    $("#obs-pane").innerHTML = tbl(["SLO", "Service", "Target", "Current", "Error budget", ""], r.slos.map(s => `<tr>
      <td><div class="fw-semibold small">${esc(s.name)}</div><div class="nx-mono nx-muted">${esc(s.id)}</div></td>
      <td class="small">${esc(s.service_id || "-")}</td>
      <td class="small">${esc(s.target)}%</td>
      <td class="small">${s.current ? esc(s.current) + "%" : "-"}</td>
      <td class="small ${s.error_budget_remaining !== undefined && s.error_budget_remaining < 0 ? "text-danger" : ""}">${s.error_budget_remaining !== undefined ? esc(s.error_budget_remaining) + "%" : "-"}</td>
      <td><button class="btn btn-sm btn-outline-secondary" data-slo="${esc(s.id)}"><i class="bi bi-pencil"></i></button></td></tr>`), "No SLOs defined.");
  }

  async function drawCloudWatch() {
    $("#obs-pane").innerHTML = `<div class="nx-card"><div class="nx-card-body">
      <div class="row g-3 mb-3">
        <div class="col-md-4">${acctSel("cw-acct")}</div>
        <div class="col-md-4"><input class="form-control" id="cw-ns" placeholder="Namespace (AWS/EC2)" value="AWS/EC2"></div>
        <div class="col-md-4"><input class="form-control" id="cw-metric" placeholder="Metric (CPUUtilization)" value="CPUUtilization"></div>
      </div>
      <button class="btn btn-outline-primary" id="cw-go"><i class="bi bi-graph-up me-1"></i>Fetch</button>
      <div id="cw-out" class="mt-3"></div>
    </div></div>`;
    $("#cw-go").onclick = async () => {
      try {
        const acct = $("#cw-acct").value, ns = $("#cw-ns").value || "AWS/EC2", metric = $("#cw-metric").value || "CPUUtilization";
        const r = await NX.api.get(`/api/m11/cloudwatch/metrics?account=${acct}&namespace=${ns}&metric=${metric}&hours=6`);
        const rows = (r.datapoints || []).map(d => `<tr><td>${esc(d.Timestamp)}</td><td>${esc(d.Average?.toFixed(2) || "-")}</td><td>${esc(d.Maximum?.toFixed(2) || "-")}</td><td>${esc(d.Minimum?.toFixed(2) || "-")}</td></tr>`).join("");
        $("#cw-out").innerHTML = `<div class="nx-table-wrap"><table class="nx-table"><thead><tr><th>Time</th><th>Avg</th><th>Max</th><th>Min</th></tr></thead><tbody>${rows || "<tr><td colspan='4' class='nx-muted'>No data</td></tr>"}</tbody></table></div>`;
      } catch (e) { NX.toast(UI.errorText(e), "danger"); }
    };
  }

  async function setTab(t) {
    S.tab = t; $$("#obs-tabs [data-tab]").forEach(b => b.classList.toggle("active", b.dataset.tab === t));
    $("#obs-pane").innerHTML = loading();
    try { await ({ overview, services: drawServices, incidents: drawIncidents, alerts: drawAlerts, slos: drawSlos, cloudwatch: drawCloudWatch }[t])(); } catch (e) { $("#obs-pane").innerHTML = fail(e); }
  }

  async function init() {
    if (!$("#obs-pane")) return;
    try { await overview(); } catch (e) { $("#obs-pane").innerHTML = fail(e); return; }
    $$("#obs-tabs [data-tab]").forEach(b => b.onclick = () => setTab(b.dataset.tab));
    setTab("overview");
  }
  document.addEventListener("DOMContentLoaded", () => setTimeout(init, 0));
})();
