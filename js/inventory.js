/* Account data: central AWS resource cache (M02 /api/m02/cache/*). Sync in the background, browse instantly. */
(function () {
  "use strict";
  const NX = window.NEXUS, UI = NX.ui, esc = NX.esc, $ = UI.$, $$ = UI.$$;
  const PAGE = 100;
  const S = { acct: "", summary: null, service: "", page: 0, total: 0, items: [], regions: [], picked: null, services: null, poll: null };

  // Columns shown per service (from the row summary). Everything else is in the detail view.
  const COLS = {
    ec2: ["type", "az", "private_ip", "public_ip", "imdsv2"], asg: ["min", "desired", "max", "instances"], ebs: ["size_gb", "type", "encrypted", "attached_to"],
    lambda: ["runtime", "memory_mb", "timeout_s", "modified"], eks: ["version", "nodegroups", "public_api", "vpc"], ecr: ["scan_on_push", "tag_mutability", "uri"],
    vpc: ["cidr", "subnets", "azs", "default"], subnet: ["vpc", "az", "cidr", "free_ips", "auto_public_ip"], sg: ["vpc", "inbound_rules", "open_ports"],
    elb: ["type", "scheme", "dns"], rds: ["engine", "class", "multi_az", "encrypted", "public", "backup_days"], rds_cluster: ["engine", "members", "encrypted", "backup_days"],
    dynamodb: ["keys", "billing", "items", "size_mb"], elasticache: ["engine", "node_type", "nodes", "encrypted"], sqs: ["fifo"], sns: ["arn"],
    acm: ["type", "in_use", "expires"], kms: ["aws_managed"], s3: ["bucket_region", "created"], iam_role: ["path", "last_used", "description"],
    route53: ["records", "comment"], cloudfront: ["domain", "aliases", "enabled"],
  };
  const label = (k) => k.replace(/_/g, " ");
  const fmt = (v) => {
    if (v === true) return '<span class="nx-badge b-success">yes</span>';
    if (v === false) return '<span class="nx-badge b-secondary">no</span>';
    if (v == null || v === "") return '<span class="nx-muted">-</span>';
    const t = String(v);
    return /^\d{4}-\d\d-\d\dT/.test(t) ? esc(t.slice(0, 16).replace("T", " ")) : esc(t.length > 80 ? t.slice(0, 77) + "…" : t);
  };
  const stateBadge = (s) => s ? `<span class="nx-badge b-${/running|active|available|in-use|ok|issued|deployed|public/i.test(s) ? "success" :
    /stop|fail|error|delet|open-to-internet|expired/i.test(s) ? "danger" : "secondary"}">${esc(s)}</span>` : "";
  const ago = (ts) => {
    if (!ts) return "never";
    const s = Math.max(0, (Date.now() - Date.parse(ts.replace(" ", "T") + "Z")) / 1000);
    return s < 90 ? "just now" : s < 3600 ? `${Math.round(s / 60)} min ago` : s < 86400 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} d ago`;
  };

  /* ---------------- summary ---------------- */
  async function loadSummary() {
    try { S.summary = await NX.api.get(`/api/m02/cache/summary?account=${encodeURIComponent(S.acct)}`); }
    catch (e) { $("#iv-services").innerHTML = `<div class="alert alert-danger small m-2">${esc(e.message)}</div>`; return; }
    const sm = S.summary, cfg = sm.config;
    if (!S.services) S.services = cfg ? cfg.services : sm.catalog.map(c => c.id);
    $("#iv-svc-n").textContent = `${S.services.length}/${sm.catalog.length}`;
    const errs = sm.services.reduce((n, s) => n + s.errors, 0);
    const last = sm.last_jobs[0];
    const k = (l, v, i, t, sub) => `<div class="col-6 col-xl-3"><div class="nx-card h-100"><div class="nx-card-body nx-kpi"><div class="nx-kpi-icon tone-${t}"><i class="bi ${i}"></i></div>
      <div><div class="nx-kpi-value" style="font-size:20px">${esc(v)}</div><div class="nx-kpi-label">${esc(l)}</div>${sub ? `<div class="small nx-muted">${esc(sub)}</div>` : ""}</div></div></div></div>`;
    $("#iv-kpis").innerHTML = k("Resources cached", sm.total.toLocaleString(), "bi-database", "primary", `${sm.services.filter(s => s.count).length} services`) +
      k("Regions", sm.regions.filter(r => r.region !== "global").length, "bi-globe", "info", sm.regions.slice(0, 3).map(r => `${r.region} ${r.n}`).join(" · ")) +
      k("Read errors", errs, "bi-exclamation-triangle", errs ? "warning" : "success", errs ? "see list above the table" : "all slices read") +
      k("Last sync", last ? ago(last.finished_at || last.started_at) : "never", "bi-clock-history", last && last.status === "completed" ? "success" : "secondary",
        last ? `${last.status.replace(/_/g, " ")} · ${last.trigger}` : "click Sync now");
    const auto = sm.interval_minutes ? `auto refresh every ${sm.interval_minutes >= 60 ? sm.interval_minutes / 60 + " h" : sm.interval_minutes + " min"}` : "auto refresh off";
    $("#iv-stamp").innerHTML = `${cfg && cfg.last_synced ? `synced ${esc(ago(cfg.last_synced))} (${esc(cfg.last_synced)} UTC)` : "not synced yet"}<br>
      <span class="nx-muted">${esc(auto)}</span>${NX.session.isAdmin() ? ` · <a href="#" id="iv-auto">change</a>` : ""}`;
    const a2 = $("#iv-auto"); if (a2) a2.onclick = (e) => { e.preventDefault(); openAuto(); };
    // service list grouped by category
    const cats = {};
    sm.catalog.forEach(c => (cats[c.category] = cats[c.category] || []).push(c));
    const byId = Object.fromEntries(sm.services.map(s => [s.service, s]));
    $("#iv-services").innerHTML = `<a href="#" class="d-flex justify-content-between px-2 py-1 rounded text-decoration-none ${!S.service ? "bg-primary text-white" : ""}" data-svc="">
        <span class="fw-semibold">All resources</span><span>${sm.total.toLocaleString()}</span></a>` +
      Object.entries(cats).map(([cat, list]) => `<div class="small text-uppercase nx-muted fw-semibold px-2 mt-2">${esc(cat)}</div>` + list.map(c => {
        const x = byId[c.id] || { count: 0, errors: 0 };
        return `<a href="#" class="d-flex justify-content-between px-2 py-1 rounded text-decoration-none small ${S.service === c.id ? "bg-primary text-white" : ""} ${!x.count && !x.errors ? "opacity-50" : ""}" data-svc="${esc(c.id)}">
          <span>${esc(c.label)}${x.errors ? ` <i class="bi bi-exclamation-triangle-fill text-warning" title="${x.errors} region(s) failed"></i>` : ""}</span><span>${x.count}</span></a>`;
      }).join("")).join("");
    $$("[data-svc]").forEach(a3 => a3.onclick = (e) => { e.preventDefault(); S.service = a3.dataset.svc; S.page = 0; $("#iv-state").value = ""; loadSummary(); loadRows(); });
    // filters
    const regSel = $("#iv-region"), cur = regSel.value;
    regSel.innerHTML = `<option value="">All regions</option>` + sm.regions.map(r => `<option value="${esc(r.region)}" ${r.region === cur ? "selected" : ""}>${esc(r.region)} (${r.n})</option>`).join("");
    const states = S.service && byId[S.service] ? Object.entries(byId[S.service].states || {}) : [];
    const stSel = $("#iv-state"), curSt = stSel.value;
    stSel.innerHTML = `<option value="">All states</option>` + states.filter(([s]) => s !== "-").map(([s, n]) => `<option value="${esc(s)}" ${s === curSt ? "selected" : ""}>${esc(s)} (${n})</option>`).join("");
    stSel.disabled = !states.length;
    // errors for current selection
    const errRows = sm.services.filter(s => !S.service || s.service === S.service).flatMap(s => Object.entries(s.regions).filter(([, v]) => v.status === "error").map(([r, v]) => ({ s, r, v })));
    $("#iv-errors").innerHTML = errRows.length ? `<div class="alert alert-warning py-2 small"><b>${errRows.length} part(s) could not be read</b> (last good data is kept):
      <ul class="mb-0">${errRows.slice(0, 8).map(e => `<li>${esc(e.s.label)} · ${esc(e.r)}: ${esc(e.v.error)}</li>`).join("")}${errRows.length > 8 ? `<li>and ${errRows.length - 8} more</li>` : ""}</ul></div>` : "";
    if (sm.running_job) watch(sm.running_job.id);
    if (!sm.total && !sm.running_job) {
      $("#iv-body").innerHTML = `<tr><td><div class="nx-empty"><i class="bi bi-cloud-download"></i>No cached data for this account yet. Choose regions and click <b>Sync now</b>.</div></td></tr>`;
      $("#iv-head").innerHTML = ""; $("#iv-info").textContent = ""; $("#iv-pages").innerHTML = "";
    }
  }

  /* ---------------- rows ---------------- */
  function query(extra) {
    const p = new URLSearchParams({ account: S.acct, limit: PAGE, offset: S.page * PAGE, ...extra });
    if (S.service) p.set("service", S.service);
    if ($("#iv-region").value) p.set("region", $("#iv-region").value);
    if ($("#iv-state").value) p.set("state", $("#iv-state").value);
    const q = $("#iv-q").value.trim();
    if (q.includes("=") && !q.includes(" ")) p.set("tag", q); else if (q) p.set("q", q);
    return p;
  }
  async function loadRows() {
    let r;
    try { r = await NX.api.get(`/api/m02/cache/resources?${query()}`); } catch (e) { $("#iv-body").innerHTML = `<tr><td>${esc(e.message)}</td></tr>`; return; }
    S.items = r.items; S.total = r.total;
    if (!r.total && S.summary && !S.summary.total) return;
    const cols = S.service ? (COLS[S.service] || []) : [];
    $("#iv-head").innerHTML = `<tr>${S.service ? "" : "<th>Service</th>"}<th>Name</th><th>ID</th><th>Region</th><th>State</th>${cols.map(c => `<th>${esc(label(c))}</th>`).join("")}${S.service ? "" : "<th>Details</th>"}<th>Fetched</th></tr>`;
    $("#iv-body").innerHTML = r.items.length ? r.items.map((it, i) => `<tr style="cursor:pointer" data-row="${i}">
      ${S.service ? "" : `<td class="small">${esc(it.service_label)}</td>`}
      <td class="fw-semibold small">${esc(it.name || "-")}</td><td class="nx-mono small" style="max-width:260px;overflow:hidden;text-overflow:ellipsis">${esc(it.resource_id)}</td>
      <td class="small">${esc(it.region)}</td><td>${stateBadge(it.state)}</td>
      ${cols.map(c => `<td class="small">${fmt(it.summary[c])}</td>`).join("")}
      ${S.service ? "" : `<td class="small nx-muted">${Object.entries(it.summary).filter(([, v]) => v !== null && v !== "" && typeof v !== "object").slice(0, 3).map(([k, v]) => `${esc(label(k))}: ${fmt(v)}`).join(" · ")}</td>`}
      <td class="small nx-muted">${esc(ago(it.fetched_at))}</td></tr>`).join("")
      : `<tr><td colspan="12"><div class="nx-empty"><i class="bi bi-search"></i>Nothing matches.</div></td></tr>`;
    $$("[data-row]").forEach(tr => tr.onclick = () => openDetail(S.items[+tr.dataset.row]));
    const pages = Math.max(1, Math.ceil(r.total / PAGE));
    $("#iv-info").textContent = `${r.total.toLocaleString()} resources${r.total > PAGE ? ` · page ${S.page + 1} of ${pages}` : ""}`;
    $("#iv-pages").innerHTML = pages > 1 ? `<button class="btn btn-sm btn-outline-secondary" data-pg="-1" ${S.page === 0 ? "disabled" : ""}><i class="bi bi-chevron-left"></i></button>
      <button class="btn btn-sm btn-outline-secondary" data-pg="1" ${S.page >= pages - 1 ? "disabled" : ""}><i class="bi bi-chevron-right"></i></button>` : "";
    $$("[data-pg]").forEach(b => b.onclick = () => { S.page += +b.dataset.pg; loadRows(); });
  }

  async function openDetail(it) {
    const m = UI.modal(`${it.service_label}: ${it.name || it.resource_id}`, `<div id="iv-d">Loading…</div>`, { size: "modal-xl" });
    try {
      const d = (await NX.api.get(`/api/m02/cache/resource?account=${encodeURIComponent(S.acct)}&region=${encodeURIComponent(it.region)}&service=${encodeURIComponent(it.service)}&id=${encodeURIComponent(it.resource_id)}`)).resource;
      const json = JSON.stringify(d.detail, null, 2);
      $("#iv-d", m.el).innerHTML = `<div class="d-flex flex-wrap gap-2 mb-3">${stateBadge(d.state)} <span class="nx-badge b-secondary">${esc(d.region)}</span>
          <span class="nx-badge b-secondary nx-mono">${esc(d.resource_id)}</span><span class="nx-badge b-secondary">fetched ${esc(d.fetched_at)} UTC</span></div>
        <div class="row g-3"><div class="col-lg-6"><h6 class="fw-bold">Summary</h6><table class="nx-table">${Object.entries(d.summary).map(([k, v]) => `<tr><td class="small nx-muted">${esc(label(k))}</td><td class="small">${fmt(v)}</td></tr>`).join("")}</table></div>
          <div class="col-lg-6"><h6 class="fw-bold">Tags (${Object.keys(d.tags).length})</h6>${Object.keys(d.tags).length ? `<table class="nx-table">${Object.entries(d.tags).map(([k, v]) => `<tr><td class="small nx-mono">${esc(k)}</td><td class="small">${esc(v)}</td>
            <td class="text-end"><button class="btn btn-sm btn-link p-0" data-tagq="${esc(k)}=${esc(v)}" title="Find everything with this tag"><i class="bi bi-search"></i></button></td></tr>`).join("")}</table>` : '<div class="small nx-muted">No tags.</div>'}</div></div>
        <h6 class="fw-bold mt-3 d-flex justify-content-between">Full API record <button class="btn btn-sm btn-outline-secondary" id="iv-copy"><i class="bi bi-clipboard me-1"></i>Copy JSON</button></h6>
        <pre class="nx-log" style="max-height:45vh">${esc(json)}</pre><div class="small nx-muted">Secret-bearing fields (e.g. Lambda environment variables, EC2 user data) are never stored.</div>`;
      $("#iv-copy", m.el).onclick = () => navigator.clipboard.writeText(json).then(() => NX.toast("Copied.", "success"));
      $$("[data-tagq]", m.el).forEach(b => b.onclick = () => { m.hide(); $("#iv-q").value = b.dataset.tagq; S.service = ""; S.page = 0; loadSummary(); loadRows(); });
    } catch (e) { $("#iv-d", m.el).innerHTML = `<div class="alert alert-danger small">${esc(e.message)}</div>`; }
  }

  /* ---------------- sync ---------------- */
  async function sync() {
    let regions = $("#iv-scope").value;
    if (regions === "pick") {
      if (!S.picked || !S.picked.length) return pickRegions();
      regions = S.picked;
    }
    $("#iv-sync").disabled = true;
    try {
      const r = await NX.api.post("/api/m02/cache/sync", { account: S.acct, regions, services: S.services });
      NX.toast(r.started ? `Sync started: ${r.job.total} reads across ${r.job.regions.length} region(s).` : "A sync is already running for this account.", "info");
      watch(r.job.id);
    } catch (e) { NX.toast(UI.errorText(e), "danger"); $("#iv-sync").disabled = false; }
  }
  function watch(jid) {
    if (S.poll) return;
    $("#iv-progress").classList.remove("d-none"); $("#iv-sync").disabled = true;
    const tick = async () => {
      let j; try { j = (await NX.api.get(`/api/m02/cache/jobs/${encodeURIComponent(jid)}`)).job; } catch (e) { return; }
      const pct = Math.round(j.done / Math.max(1, j.total) * 100);
      $("#iv-prog-bar").style.width = pct + "%";
      $("#iv-prog-label").textContent = `Syncing ${j.regions.length} region(s) · ${j.services.length} services${j.errors ? ` · ${j.errors} failed` : ""}`;
      $("#iv-prog-n").textContent = `${j.done}/${j.total} · ${j.resources.toLocaleString()} resources`;
      if (j.status !== "running") {
        clearInterval(S.poll); S.poll = null;
        $("#iv-progress").classList.add("d-none"); $("#iv-sync").disabled = false;
        NX.toast(`Sync ${j.status.replace(/_/g, " ")}: ${j.resources.toLocaleString()} resources${j.errors ? `, ${j.errors} part(s) failed` : ""}.`, j.errors ? "warning" : "success");
        await loadSummary(); loadRows();
      } else if (j.done % 5 === 0) { loadSummary(); }
    };
    S.poll = setInterval(tick, 1500); tick();
  }

  async function pickRegions() {
    const a = NX.awsAccounts.find(x => x.id === S.acct);
    let regs = [];
    try { regs = (await NX.api.get("/api/m02/regions?account=" + encodeURIComponent(S.acct))).regions.map(r => r.code); } catch (e) { regs = [a.region]; }
    const chosen = new Set(S.picked || [a.region]);
    const m = UI.modal("Regions to sync", `<div class="d-flex flex-wrap gap-1">${regs.map(r => `<input type="checkbox" class="btn-check" id="rg-${r}" value="${r}" ${chosen.has(r) ? "checked" : ""}>
      <label class="btn btn-sm btn-outline-primary" for="rg-${r}">${esc(r)}</label>`).join("")}</div>`, { size: "modal-lg", footer: '<button class="btn btn-primary" id="rg-ok">Use these regions</button>' });
    $("#rg-ok", m.el).onclick = () => { S.picked = $$("input:checked", m.el).map(i => i.value); m.hide(); if (S.picked.length) sync(); };
  }

  function pickServices() {
    const cat = S.summary.catalog, on = new Set(S.services);
    const m = UI.modal("Services to sync", `<div class="d-flex gap-2 mb-2"><button class="btn btn-sm btn-outline-secondary" id="sv-all">All</button><button class="btn btn-sm btn-outline-secondary" id="sv-none">None</button></div>
      <div class="row g-1">${cat.map(c => `<div class="col-md-6"><div class="form-check"><input class="form-check-input" type="checkbox" id="sv-${c.id}" value="${c.id}" ${on.has(c.id) ? "checked" : ""}>
        <label class="form-check-label small" for="sv-${c.id}">${esc(c.label)} <span class="nx-muted">(${esc(c.category)}${c.scope === "global" ? ", global" : ""})</span></label></div></div>`).join("")}</div>`,
      { size: "modal-lg", footer: '<button class="btn btn-primary" id="sv-ok">Save</button>' });
    $("#sv-all", m.el).onclick = () => $$("input[type=checkbox]", m.el).forEach(i => i.checked = true);
    $("#sv-none", m.el).onclick = () => $$("input[type=checkbox]", m.el).forEach(i => i.checked = false);
    $("#sv-ok", m.el).onclick = () => { S.services = $$("input:checked", m.el).map(i => i.value); $("#iv-svc-n").textContent = `${S.services.length}/${cat.length}`; m.hide(); };
  }

  function openAuto() {
    const cur = S.summary.interval_minutes, cfg = S.summary.config;
    const m = UI.modal("Automatic refresh", `<label class="form-label small fw-semibold">Re-sync connected accounts every</label>
      <select class="form-select mb-3" id="au-int">${[[0, "Off"], [15, "15 minutes"], [30, "30 minutes"], [60, "1 hour"], [180, "3 hours"], [360, "6 hours"], [720, "12 hours"], [1440, "24 hours"]]
        .map(([v, l]) => `<option value="${v}" ${v === cur ? "selected" : ""}>${l}</option>`).join("")}</select>
      ${cfg ? `<div class="form-check form-switch"><input class="form-check-input" type="checkbox" id="au-acct" ${cfg.auto_refresh ? "checked" : ""}><label class="form-check-label small" for="au-acct">Include this account</label></div>` : ""}
      <div class="small nx-muted mt-2">Each refresh repeats the regions and services of the account's last manual sync. Reads only; SSO profiles need a valid login on the portal host.</div>`,
      { footer: '<button class="btn btn-primary" id="au-ok">Save</button>' });
    $("#au-ok", m.el).onclick = async () => {
      try {
        await NX.api.call("PUT", "/api/m02/cache/settings", { interval_minutes: +$("#au-int", m.el).value, ...(cfg ? { account: S.acct, auto_refresh: $("#au-acct", m.el).checked } : {}) });
        m.hide(); NX.toast("Saved.", "success"); loadSummary();
      } catch (e) { NX.toast(UI.errorText(e), "danger"); }
    };
  }

  async function exportCsv() {
    const all = [];
    for (let off = 0; off < Math.min(S.total, 20000); off += 1000) {
      const p = query({ limit: 1000, offset: off });
      all.push(...(await NX.api.get(`/api/m02/cache/resources?${p}`)).items);
    }
    const keys = [...new Set(all.flatMap(i => Object.keys(i.summary)))];
    const rows = [["service", "name", "id", "region", "state", ...keys, "fetched_at"]].concat(all.map(i => [i.service, i.name, i.resource_id, i.region, i.state, ...keys.map(k => i.summary[k]), i.fetched_at]));
    const csv = rows.map(r => r.map(c => `"${String(c == null ? "" : typeof c === "object" ? JSON.stringify(c) : c).replace(/"/g, '""')}"`).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" })); a.download = `aws-${S.acct}-${S.service || "all"}.csv`; a.click();
  }

  async function init() {
    if (!$("#iv-body")) return;
    const accts = await NX.loadAccounts();
    if (!accts.length) { $("#iv-services").innerHTML = '<div class="small p-2">Connect an AWS account on the <a href="aws-accounts.html">AWS Accounts</a> page first.</div>'; $("#iv-sync").disabled = true; return; }
    S.acct = UI.qs("account") || NX.activeAccount.getId() || accts[0].id;
    $("#iv-acct").innerHTML = accts.map(a => `<option value="${esc(a.id)}" ${a.id === S.acct ? "selected" : ""}>${esc(a.alias)} (${esc(a.id)}) · ${esc(a.region)}${a.status === "connected" ? "" : " · " + esc(a.status)}</option>`).join("");
    $("#iv-acct").onchange = () => { S.acct = $("#iv-acct").value; S.service = ""; S.page = 0; S.services = null; S.picked = null; if (S.poll) { clearInterval(S.poll); S.poll = null; } loadSummary(); loadRows(); };
    $("#iv-scope").onchange = () => { if ($("#iv-scope").value === "pick") pickRegions(); };
    $("#iv-sync").onclick = sync; $("#iv-svc-btn").onclick = pickServices; $("#iv-csv").onclick = exportCsv;
    if (role() === "viewer") $("#iv-sync").disabled = true;
    let deb; $("#iv-q").oninput = () => { clearTimeout(deb); deb = setTimeout(() => { S.page = 0; loadRows(); }, 250); };
    $("#iv-region").onchange = () => { S.page = 0; loadRows(); };
    $("#iv-state").onchange = () => { S.page = 0; loadRows(); };
    await loadSummary(); loadRows();
  }
  const role = () => (NX.session.get() || {}).role;
  document.addEventListener("DOMContentLoaded", () => setTimeout(init, 0));
})();
