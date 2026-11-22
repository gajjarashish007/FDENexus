/* M02 Environments: list, create wizard (account -> region/AZ -> network -> review), details, decommission. */
(function () {
  "use strict";
  const NX = window.NEXUS, UI = NX.ui, esc = NX.esc, $ = UI.$, $$ = UI.$$;
  const STEPS = ["Account & tier", "Region & AZs", "Network", "Review"];
  const TIER_INFO = {
    sandbox: "Experiments. Small instance sizes only, auto-approved.", development: "Day-to-day development, auto-approved when policy passes.",
    staging: "Pre-production, reviewed by an approver.", production: "Customer traffic. Approver required, 2+ AZs, per-AZ NAT recommended."
  };
  const W = { step: 0, regions: [], regionSource: "", accounts: [], plan: null, preview: null, busy: false,
    f: { name: "", account_id: "", tier: "development", team: "", description: "", region: "", azs: [], cidr: "", nat_mode: "single", flow_logs: true, guardduty: false } };
  let ENVS = [];
  const me = () => NX.session.get() || {};

  /* ---------------- list ---------------- */
  async function loadList() {
    try { ENVS = (await NX.api.get("/api/m02/environments")).environments; }
    catch (e) { $("#ev-body-list").innerHTML = `<tr><td colspan="8">${esc(e.message)}</td></tr>`; return; }
    const live = ENVS.filter(e => e.status !== "retired");
    const k = (l, v, i, t) => `<div class="col-6 col-xl-3"><div class="nx-card h-100"><div class="nx-card-body nx-kpi"><div class="nx-kpi-icon tone-${t}"><i class="bi ${i}"></i></div>
      <div><div class="nx-kpi-value" style="font-size:20px">${esc(v)}</div><div class="nx-kpi-label">${esc(l)}</div></div></div></div></div>`;
    $("#ev-kpis").innerHTML = k("Environments", live.length, "bi-diagram-3", "primary") +
      k("Production", live.filter(e => e.tier === "production").length, "bi-shield-check", "danger") +
      k("Components", live.reduce((s, e) => s + e.component_count, 0), "bi-boxes", "info") +
      k("Est. monthly (fixed)", UI.money(live.reduce((s, e) => s + e.monthly, 0)), "bi-cash-coin", "success");
    const canDecom = ["admin", "operator"].includes(me().role);
    $("#ev-body-list").innerHTML = ENVS.length ? ENVS.map(e => `<tr>
      <td><a href="#" class="fw-semibold text-decoration-none" data-open="${esc(e.id)}">${esc(e.id)}</a>
        ${e.kind === "existing" ? '<span class="nx-badge b-info ms-1" title="Existing VPC in the account, not managed by the portal">existing</span>' : ""}<div class="small nx-muted">team ${esc(e.team)}</div></td>
      <td><span class="nx-badge b-${e.tier === "production" ? "danger" : e.tier === "staging" ? "warning" : "secondary"}">${esc(e.tier)}</span></td>
      <td class="small"><span class="nx-mono">${esc(e.account_id)}</span><div class="nx-muted">${esc(e.region)} · ${e.azs.length} AZ</div></td>
      <td class="small nx-mono">${esc(e.cidr || "")}${e.vpc_id ? `<div class="nx-muted">${esc(e.vpc_id)}</div>` : e.kind === "existing" ? '<div class="nx-muted">no VPC</div>' : ""}</td><td>${e.component_count}</td><td>${UI.money(e.monthly)}</td><td>${UI.envBadge(e.status)}</td>
      <td class="text-end" style="white-space:nowrap">
        <button class="btn btn-sm btn-outline-secondary" data-open="${esc(e.id)}" title="Details"><i class="bi bi-eye"></i></button>
        ${["active", "provisioning"].includes(e.status) ? `<a class="btn btn-sm btn-outline-primary" href="launch.html?env=${encodeURIComponent(e.id)}" title="Launch into this environment"><i class="bi bi-rocket-takeoff"></i></a>` : ""}
        ${canDecom && e.status === "active" && e.kind !== "existing" ? `<button class="btn btn-sm btn-outline-danger" data-decom="${esc(e.id)}" title="Decommission"><i class="bi bi-trash"></i></button>` : ""}
        ${canDecom && e.status === "active" && e.kind === "existing" ? (e.component_count
          ? `<button class="btn btn-sm btn-outline-danger" data-decom="${esc(e.id)}" title="Remove what the portal launched here"><i class="bi bi-trash"></i></button>`
          : `<button class="btn btn-sm btn-outline-secondary" data-forget="${esc(e.id)}" title="Remove from portal (AWS untouched)"><i class="bi bi-x-lg"></i></button>`) : ""}
      </td></tr>`).join("") : `<tr><td colspan="8"><div class="nx-empty"><i class="bi bi-diagram-3"></i>No environments yet. Click “New environment”.</div></td></tr>`;
    $$("[data-open]").forEach(b => b.onclick = (ev) => { ev.preventDefault(); openEnv(b.dataset.open); });
    $$("[data-decom]").forEach(b => b.onclick = () => decommissionEnv(b.dataset.decom));
    $$("[data-forget]").forEach(b => b.onclick = async () => {
      if (!confirm(`Remove ${b.dataset.forget} from the portal? Nothing in AWS is changed.`)) return;
      try { await NX.api.call("DELETE", "/api/m02/environments/" + encodeURIComponent(b.dataset.forget)); NX.toast("Removed from the portal.", "success"); loadList(); }
      catch (e) { NX.toast(UI.errorText(e), "danger"); }
    });
    const open = UI.qs("env"); if (open && ENVS.find(e => e.id === open)) openEnv(open);
  }

  /* ---------------- details ---------------- */
  async function openEnv(id) {
    let e;
    try { e = (await NX.api.get("/api/m02/environments/" + encodeURIComponent(id))).environment; } catch (er) { return NX.toast(er.message, "danger"); }
    const canDecom = ["admin", "operator"].includes(me().role);
    const comps = e.components.length ? `<table class="nx-table"><thead><tr><th>Component</th><th>Type</th><th>Est. monthly</th><th>Last change</th><th></th></tr></thead><tbody>
      ${e.components.map(c => `<tr><td class="nx-mono small">${esc(c.instance)}</td><td>${esc(c.component)}</td><td>${UI.money(c.monthly)}</td>
        <td>${c.change ? `<a href="changes.html?id=${esc(c.change)}" class="nx-id">${esc(c.change)}</a> ${UI.changeBadge(c.status)}` : ""}</td>
        <td class="text-end">${canDecom && !["vpc", "account-baseline"].includes(c.component) ? `<button class="btn btn-sm btn-outline-danger" data-rm="${esc(c.instance)}">Remove</button>` : ""}</td></tr>`).join("")}</tbody></table>`
      : '<div class="small nx-muted">Nothing deployed yet.</div>';
    const versions = e.versions.length ? e.versions.map(v => `<div class="nx-sum-row"><span>v${v.version} · <a class="nx-id" href="changes.html?id=${esc(v.change_id)}">${esc(v.change_id)}</a> <span class="nx-muted small">${esc(v.created_at)}</span></span>
      <span class="small">${v.components.length} components ${canDecom && v.version !== e.versions[0].version ? `<button class="btn btn-sm btn-link p-0 ms-2" data-rb="${v.version}">Roll back to this</button>` : ""}</span></div>`).join("") : '<div class="small nx-muted">No versions yet.</div>';
    const m = UI.modal(`Environment ${e.id}`, `
      <div class="d-flex flex-wrap gap-2 mb-3">${UI.envBadge(e.status)} <span class="nx-badge b-secondary">${esc(e.tier)}</span>
        <span class="nx-badge b-secondary">${esc(e.region)}</span><span class="nx-badge b-secondary nx-mono">${esc(e.account_id)}</span>
        <span class="nx-badge b-secondary nx-mono">${esc(e.cidr)}</span><span class="nx-badge b-primary">${UI.money(e.monthly)}/mo</span></div>
      <div class="small nx-muted mb-3">AZs: ${e.azs.map(esc).join(", ") || "-"} · ${e.kind === "existing" ? "imported" : "created"} by ${esc(e.created_by)} ${esc(e.created_at)}</div>
      ${e.kind === "existing" ? `<div class="alert alert-info py-2 small">Existing ${e.vpc_id ? "VPC <span class='nx-mono'>" + esc(e.vpc_id) + "</span>" : "account (no VPC chosen)"}: the portal never changes or deletes it. Only resources launched from the portal are managed here.</div>
        ${e.subnets.length ? `<table class="nx-table mb-3"><thead><tr><th>Subnet</th><th>AZ</th><th>CIDR</th><th>Type</th></tr></thead><tbody>${e.subnets.map(s => `<tr><td class="nx-mono small">${esc(s.id)} ${esc(s.name || "")}</td><td>${esc(s.az)}</td><td class="nx-mono small">${esc(s.cidr)}</td><td>${s.public ? '<span class="nx-badge b-warning">public</span>' : '<span class="nx-badge b-secondary">private</span>'}</td></tr>`).join("")}</tbody></table>` : ""}` : ""}
      ${e.pending.length ? `<div class="alert alert-warning py-2 small">${e.pending.length} change(s) in flight: ${e.pending.map(p => `<a href="changes.html?id=${esc(p.id)}">${esc(p.id)}</a> (${esc(p.status)})`).join(", ")}</div>` : ""}
      <h6 class="fw-bold">Components</h6>${comps}
      <h6 class="fw-bold mt-4">Stack versions</h6>${versions}
      <div class="mt-3"><a href="changes.html?stack=${encodeURIComponent(e.id)}" class="small">View generated Atmos stack</a></div>`,
      { size: "modal-xl", footer: ["active", "provisioning"].includes(e.status) ? `<a class="btn btn-primary" href="launch.html?env=${encodeURIComponent(e.id)}"><i class="bi bi-rocket-takeoff me-1"></i>Launch into ${esc(e.id)}</a>` : "" });
    $$("[data-rm]", m.el).forEach(b => b.onclick = async () => {
      if (!confirm(`Remove ${b.dataset.rm} from ${e.id}? The resource is destroyed after approval.`)) return;
      try { const r = await NX.api.post(`/api/m02/environments/${encodeURIComponent(e.id)}/decommission`, { instance: b.dataset.rm });
        NX.toast(`${r.change.id}: ${r.change.status}`, "success"); m.hide(); loadList(); } catch (er) { NX.toast(UI.errorText(er), "danger"); }
    });
    $$("[data-rb]", m.el).forEach(b => b.onclick = async () => {
      try { const r = await NX.api.post(`/api/m03/stacks/${encodeURIComponent(e.id)}/rollback`, { version: +b.dataset.rb });
        NX.toast(`Rollback proposed as ${r.change.id} (${r.change.status}).`, "success"); m.hide(); loadList(); } catch (er) { NX.toast(UI.errorText(er), "danger"); }
    });
  }

  async function decommissionEnv(id) {
    const typed = prompt(`This destroys every resource in ${id} after approval.\nType the environment name to confirm:`);
    if (typed === null) return;
    try { const r = await NX.api.post(`/api/m02/environments/${encodeURIComponent(id)}/decommission`, { confirm: typed.trim() });
      NX.toast(`${r.change.id}: ${r.change.status.replace("_", " ")}`, "warning"); loadList(); } catch (e) { NX.toast(UI.errorText(e), "danger"); }
  }

  /* ---------------- create wizard ---------------- */
  function stepAccount() {
    const f = W.f, accts = W.accounts.filter(a => a.status === "connected");
    if (!accts.length) return `<div class="nx-empty"><i class="bi bi-cloud-plus"></i>Connect an AWS account first on the <a href="aws-accounts.html">AWS Accounts</a> page.</div>`;
    const prodOk = ["admin", "operator"].includes(me().role);
    return `<div class="row g-3">
      <div class="col-md-6"><label class="form-label small fw-semibold" for="w-name">Environment name *</label>
        <input class="form-control" id="w-name" value="${esc(f.name)}" placeholder="dev-payments" maxlength="32"><div class="form-text">Becomes the Atmos stack name.</div></div>
      <div class="col-md-6"><label class="form-label small fw-semibold" for="w-team">Owning team *</label><input class="form-control" id="w-team" value="${esc(f.team)}" placeholder="payments"></div>
      <div class="col-12"><label class="form-label small fw-semibold">AWS account</label><div class="row g-2">${accts.map(a => `<div class="col-md-6 col-xl-4">
        <div class="nx-choice ${f.account_id === a.id ? "selected" : ""}" data-acct="${esc(a.id)}" tabindex="0" role="button">
          <div class="fw-semibold">${esc(a.alias)}</div><div class="small nx-muted nx-mono">${esc(a.id)} · home ${esc(a.region)}</div>
          <div class="small nx-muted">${a.method === "assume-role" ? "AssumeRole" : "Instance role"} · ${esc(a.env)}</div></div></div>`).join("")}</div></div>
      <div class="col-12"><label class="form-label small fw-semibold">Tier</label><div class="row g-2">${["sandbox", "development", "staging", "production"].map(t => `<div class="col-6 col-xl-3">
        <div class="nx-choice ${f.tier === t ? "selected" : ""} ${t === "production" && !prodOk ? "opacity-50" : ""}" data-tier="${t}" tabindex="0" role="button">
          <div class="fw-semibold text-capitalize">${t}</div><div class="small nx-muted">${TIER_INFO[t]}</div></div></div>`).join("")}</div>
        ${!prodOk ? '<div class="form-text">Production environments can be requested by admins and operators.</div>' : ""}</div>
      <div class="col-12"><label class="form-label small fw-semibold" for="w-desc">Description</label><input class="form-control" id="w-desc" value="${esc(f.description)}" maxlength="300"></div></div>`;
  }
  function stepRegion() {
    const f = W.f, r = W.regions.find(x => x.code === f.region);
    return `<div class="alert alert-info py-2 small"><i class="bi bi-info-circle me-1"></i>${esc(W.regionSource)}</div>
      <label class="form-label small fw-semibold" for="w-region">Region</label>
      <select class="form-select mb-3" id="w-region"><option value="">Choose a region…</option>${W.regions.map(x => `<option value="${x.code}" ${x.code === f.region ? "selected" : ""}>${esc(x.name)} · ${x.code} (${x.azs.length} AZs)</option>`).join("")}</select>
      ${r ? `<label class="form-label small fw-semibold d-block">Availability zones <span class="nx-muted fw-normal">(${f.azs.length} selected${f.tier === "production" ? ", production needs 2+" : ""})</span></label>
        <div>${r.azs.map(z => `<span class="nx-az ${f.azs.includes(z.name) ? "on" : ""}" data-az="${esc(z.name)}" tabindex="0" role="button"><i class="bi bi-${f.azs.includes(z.name) ? "check-circle-fill" : "circle"}"></i>${esc(z.name)}${z.zone_id ? ` <span class="nx-muted small">${esc(z.zone_id)}</span>` : ""}</span>`).join("")}</div>
        <div class="form-text">Pick 2-3 AZs for resilience. Each AZ gets one public and one private subnet.</div>` : ""}`;
  }
  function stepNetwork() {
    const f = W.f, p = W.plan;
    const nat = [["none", "No NAT", "Private subnets have no internet egress. $0."], ["single", "Single NAT", "One NAT gateway, about $33/mo. Single-AZ dependency."],
      ["per-az", "NAT per AZ", `${f.azs.length} NAT gateways, about $${(32.85 * f.azs.length).toFixed(0)}/mo. Survives an AZ outage.`]];
    let map = "";
    if (p && !p.error) {
      const colors = ["#2563eb", "#0891b2", "#7c3aed", "#0d9488", "#4f46e5", "#0284c7"];
      const pre = (c) => +c.split("/")[1], base = pre(p.cidr), w = (c) => Math.pow(2, base - pre(c)) * 100;
      map = `<div class="small fw-semibold mt-3 mb-1">Address plan</div><div class="nx-subnet-map">
        ${p.public.map((c, i) => `<div style="width:${w(c)}%;background:${colors[i % 6]};opacity:.65" title="public ${c}">pub ${c}</div>`).join("")}
        <div style="width:${w(p.reserved_for_growth)}%;background:#94a3b8" title="reserved ${p.reserved_for_growth}">reserved</div>
        ${p.private.map((c, i) => `<div style="width:${w(c)}%;background:${colors[i % 6]}" title="private ${c}">priv ${c}</div>`).join("")}</div>
        <div class="small nx-muted mt-1">${p.public.length} public subnets (${p.public_hosts} IPs each) · ${p.private.length} private subnets (${p.private_hosts} IPs each) · ${esc(p.reserved_for_growth)} kept free for growth.</div>
        ${p.conflicts.length ? `<div class="alert alert-danger py-2 small mt-2">${p.conflicts.map(esc).join("<br>")}</div>` : ""}`;
    } else if (p && p.error) map = `<div class="alert alert-danger py-2 small mt-2">${esc(p.error)}</div>`;
    return `<div class="row g-3"><div class="col-md-6"><label class="form-label small fw-semibold" for="w-cidr">VPC CIDR</label>
        <div class="input-group"><input class="form-control nx-mono" id="w-cidr" value="${esc(f.cidr)}" placeholder="10.20.0.0/16">
        <button class="btn btn-outline-secondary" id="w-suggest" type="button">Suggest free range</button></div>
        <div class="form-text">Private range, /16 to /24, must not overlap other environments in the account.</div></div>
      <div class="col-md-6"><div class="form-check form-switch mt-md-4"><input class="form-check-input" type="checkbox" id="w-flow" ${f.flow_logs ? "checked" : ""}><label class="form-check-label small fw-semibold" for="w-flow">VPC flow logs</label></div>
        <div class="form-check form-switch"><input class="form-check-input" type="checkbox" id="w-gd" ${f.guardduty ? "checked" : ""}><label class="form-check-label small fw-semibold" for="w-gd">Enable GuardDuty here (leave off if your organization manages it)</label></div></div>
      <div class="col-12">${map}</div>
      <div class="col-12"><label class="form-label small fw-semibold">Internet egress for private subnets</label><div class="row g-2">${nat.map(([v, l, d]) => `<div class="col-md-4">
        <div class="nx-choice ${f.nat_mode === v ? "selected" : ""}" data-nat="${v}" tabindex="0" role="button"><div class="fw-semibold">${l}</div><div class="small nx-muted">${d}</div></div></div>`).join("")}</div></div></div>`;
  }
  function stepReview() {
    if (!W.preview) return `<div class="nx-empty"><i class="bi bi-hourglass-split"></i>Running policy, cost and Atmos validation…</div>`;
    return UI.reviewHtml(W.preview);
  }

  function drawWizard() {
    UI.steps($("#ev-steps"), STEPS, W.step, (i) => { W.step = i; W.preview = null; drawWizard(); });
    $("#ev-body").innerHTML = [stepAccount, stepRegion, stepNetwork, stepReview][W.step]();
    const f = W.f, bindIn = (id, k) => { const n = $(id); if (n) n.oninput = () => { f[k] = n.value.trim(); }; };
    bindIn("#w-name", "name"); bindIn("#w-team", "team"); bindIn("#w-desc", "description");
    $$("[data-acct]").forEach(c => c.onclick = () => { f.account_id = c.dataset.acct; f.region = ""; f.azs = []; W.regions = []; drawWizard(); });
    $$("[data-tier]").forEach(c => c.onclick = () => { f.tier = c.dataset.tier; if (f.tier === "production" && f.nat_mode === "single") f.nat_mode = "per-az"; drawWizard(); });
    const reg = $("#w-region");
    if (reg) reg.onchange = () => { f.region = reg.value; const r = W.regions.find(x => x.code === f.region); f.azs = r ? r.azs.slice(0, Math.min(3, r.azs.length)).map(z => z.name) : []; drawWizard(); };
    $$("[data-az]").forEach(c => c.onclick = () => { const z = c.dataset.az; f.azs = f.azs.includes(z) ? f.azs.filter(x => x !== z) : [...f.azs, z].sort(); drawWizard(); });
    const cidr = $("#w-cidr");
    if (cidr) { cidr.onchange = () => { f.cidr = cidr.value.trim(); loadPlan(); }; }
    const sug = $("#w-suggest");
    if (sug) sug.onclick = async () => { try { f.cidr = (await NX.api.get("/api/m02/cidr-suggest?account=" + encodeURIComponent(f.account_id))).cidr; loadPlan(); } catch (e) { NX.toast(e.message, "danger"); } };
    const flow = $("#w-flow"); if (flow) flow.onchange = () => { f.flow_logs = flow.checked; };
    const gd = $("#w-gd"); if (gd) gd.onchange = () => { f.guardduty = gd.checked; };
    $$("[data-nat]").forEach(c => c.onclick = () => { f.nat_mode = c.dataset.nat; drawWizard(); });
    $("#ev-back").disabled = W.step === 0 || W.busy;
    const next = $("#ev-next");
    next.disabled = W.busy || (W.step === 3 && (!W.preview || W.preview.status === "blocked"));
    next.innerHTML = W.step === 3 ? '<i class="bi bi-send me-1"></i>Submit environment' : 'Next<i class="bi bi-arrow-right ms-1"></i>';
  }

  async function loadPlan() {
    const f = W.f;
    if (!f.cidr) { W.plan = null; return drawWizard(); }
    try { W.plan = await NX.api.get(`/api/m02/cidr-plan?cidr=${encodeURIComponent(f.cidr)}&azs=${f.azs.length}&account=${encodeURIComponent(f.account_id)}`); }
    catch (e) { W.plan = { error: e.message }; }
    drawWizard();
  }

  async function loadRegions() {
    try { const r = await NX.api.get("/api/m02/regions?account=" + encodeURIComponent(W.f.account_id));
      W.regions = r.regions; W.regionSource = r.warning || "Regions and AZs read from the AWS account.";
      const home = (W.accounts.find(a => a.id === W.f.account_id) || {}).region;
      if (!W.f.region && home && W.regions.find(x => x.code === home)) { W.f.region = home; W.f.azs = W.regions.find(x => x.code === home).azs.slice(0, 3).map(z => z.name); }
    } catch (e) { NX.toast(e.message, "danger"); }
  }

  function validateStep() {
    const f = W.f;
    if (W.step === 0) {
      if (!/^[a-z][a-z0-9-]{2,31}$/.test(f.name)) return "Name: 3-32 chars, starts with a letter, lowercase, digits, hyphens.";
      if (!f.team) return "Enter the owning team.";
      if (!f.account_id) return "Pick an AWS account.";
      if (f.tier === "production" && !["admin", "operator"].includes(me().role)) return "Only admins and operators can request production.";
    }
    if (W.step === 1) {
      if (!f.region) return "Pick a region.";
      if (!f.azs.length) return "Pick at least one availability zone.";
      if (f.tier === "production" && f.azs.length < 2) return "Production needs 2 or more AZs.";
    }
    if (W.step === 2) {
      if (!W.plan || W.plan.error) return "Enter a valid VPC CIDR.";
      if (W.plan.conflicts && W.plan.conflicts.length) return "The CIDR overlaps another environment.";
    }
    return "";
  }

  async function next() {
    const er = validateStep(); if (er) return NX.toast(er, "warning");
    if (W.step === 0) { W.busy = true; await loadRegions(); W.busy = false; W.step = 1; return drawWizard(); }
    if (W.step === 1) { W.step = 2; if (!W.f.cidr) { try { W.f.cidr = (await NX.api.get("/api/m02/cidr-suggest?account=" + encodeURIComponent(W.f.account_id))).cidr; } catch (e) { /* user types */ } } return loadPlan(); }
    if (W.step === 2) {
      W.step = 3; W.preview = null; drawWizard();
      try { W.preview = (await NX.api.post("/api/m02/environments/preview", W.f)).preview; } catch (e) { W.step = 2; NX.toast(UI.errorText(e), "danger"); }
      return drawWizard();
    }
    W.busy = true; drawWizard();
    try {
      const r = await NX.api.post("/api/m02/environments", W.f);
      NX.toast(`${r.environment}: change ${r.change.id} ${r.change.status.replace("_", " ")}`, r.change.status === "blocked" ? "danger" : "success");
      closeWizard(); loadList();
    } catch (e) { NX.toast(UI.errorText(e), "danger"); }
    W.busy = false; if (!$("#ev-wizard").classList.contains("d-none")) drawWizard();
  }

  function openWizard() {
    W.step = 0; W.preview = null; W.plan = null;
    W.f = { name: "", account_id: (NX.activeAccount.get() || {}).id || "", tier: "development", team: "", description: "", region: "", azs: [], cidr: "", nat_mode: "single", flow_logs: true, guardduty: false };
    $("#ev-wizard").classList.remove("d-none"); $("#ev-new").disabled = true; drawWizard();
    $("#ev-wizard").scrollIntoView({ behavior: "smooth" });
  }
  function closeWizard() { $("#ev-wizard").classList.add("d-none"); $("#ev-new").disabled = false; }

  /* ---------------- account provisioning (AWS Organizations) ---------------- */
  function openProvision() {
    const accts = W.accounts.filter(a => a.status === "connected");
    const m = UI.modal("Provision a new AWS account", `
      <p class="small nx-muted">Creates a member account with AWS Organizations from the management account. It is a reviewed change like any other. After apply, register the account on the AWS Accounts page.</p>
      <div class="row g-3">
        <div class="col-md-6"><label class="form-label small fw-semibold">Account name</label><input class="form-control" id="pa-name" placeholder="payments-prod"></div>
        <div class="col-md-6"><label class="form-label small fw-semibold">Root email (unique)</label><input class="form-control" id="pa-email" type="email" placeholder="aws+payments-prod@example.com"></div>
        <div class="col-md-6"><label class="form-label small fw-semibold">Parent OU or root id</label><input class="form-control nx-mono" id="pa-parent" placeholder="ou-ab12-cd34ef56"></div>
        <div class="col-md-6"><label class="form-label small fw-semibold">Management account</label>
          <select class="form-select" id="pa-mgmt">${accts.map(a => `<option value="${esc(a.id)}">${esc(a.alias)} (${esc(a.id)})</option>`).join("")}</select></div>
        <div class="col-12"><div class="form-check"><input class="form-check-input" type="checkbox" id="pa-close"><label class="form-check-label small" for="pa-close">Close the account if this change is later destroyed</label></div></div>
      </div><div class="alert alert-danger py-2 small mt-3 d-none" id="pa-err"></div>`,
      { footer: '<button class="btn btn-primary" id="pa-go">Submit change</button>' });
    $("#pa-go", m.el).onclick = async () => {
      try {
        const r = await NX.api.post("/api/m02/accounts/provision", { account_name: $("#pa-name", m.el).value.trim(), account_email: $("#pa-email", m.el).value.trim(),
          parent_id: $("#pa-parent", m.el).value.trim(), management_account_id: $("#pa-mgmt", m.el).value, close_on_deletion: $("#pa-close", m.el).checked });
        m.hide(); NX.toast(`${r.change.id}: ${r.change.status.replace("_", " ")}. ${r.next}`, "success");
      } catch (e) { const er = $("#pa-err", m.el); er.textContent = UI.errorText(e); er.classList.remove("d-none"); }
    };
  }

  /* ---------------- import an existing VPC / account ---------------- */
  async function openImport() {
    const accts = W.accounts.filter(a => a.status === "connected");
    if (!accts.length) return NX.toast("Connect and test an AWS account first.", "warning");
    const m = UI.modal("Use an existing VPC", `
      <p class="small nx-muted">Register a VPC that already exists in your account as an environment. The portal reads it live and launches new resources into its subnets with Terraform. The VPC itself is never changed or deleted by the portal.</p>
      <div class="row g-3">
        <div class="col-md-6"><label class="form-label small fw-semibold">AWS account</label><select class="form-select" id="im-acct">${accts.map(a => `<option value="${esc(a.id)}" data-region="${esc(a.region)}">${esc(a.alias)} (${esc(a.id)})</option>`).join("")}</select></div>
        <div class="col-md-6"><label class="form-label small fw-semibold">Region</label><select class="form-select" id="im-region"></select></div>
        <div class="col-12"><label class="form-label small fw-semibold d-flex justify-content-between">VPC <button class="btn btn-sm btn-link p-0" id="im-reload" type="button">Reload</button></label><div id="im-vpcs" class="small nx-muted">Loading…</div></div>
        <div class="col-md-4"><label class="form-label small fw-semibold">Environment name</label><input class="form-control" id="im-name" placeholder="legacy-eu" maxlength="32"></div>
        <div class="col-md-4"><label class="form-label small fw-semibold">Tier</label><select class="form-select" id="im-tier">${["sandbox", "development", "staging", "production"].map(t => `<option ${t === "development" ? "selected" : ""}>${t}</option>`).join("")}</select></div>
        <div class="col-md-4"><label class="form-label small fw-semibold">Owning team</label><input class="form-control" id="im-team"></div>
      </div><div class="alert alert-danger py-2 small mt-3 d-none" id="im-err"></div>`,
      { size: "modal-xl", footer: '<button class="btn btn-primary" id="im-go">Add environment</button>' });
    let vpcId = "";
    const loadRegions = async () => {
      const a = accts.find(x => x.id === $("#im-acct", m.el).value);
      let regs = []; try { regs = (await NX.api.get("/api/m02/regions?account=" + encodeURIComponent(a.id))).regions; } catch (e) { /* below */ }
      if (!regs.find(r => r.code === a.region)) regs.unshift({ code: a.region, name: a.region });
      $("#im-region", m.el).innerHTML = regs.map(r => `<option value="${esc(r.code)}" ${r.code === a.region ? "selected" : ""}>${esc(r.name)} · ${esc(r.code)}</option>`).join("");
    };
    const loadVpcs = async () => {
      vpcId = ""; const host = $("#im-vpcs", m.el); host.textContent = "Reading VPCs from AWS…";
      try {
        const r = await NX.api.get(`/api/m02/live/vpcs?account=${encodeURIComponent($("#im-acct", m.el).value)}&region=${encodeURIComponent($("#im-region", m.el).value)}`);
        host.innerHTML = `<div class="row g-2">${r.vpcs.map(v => `<div class="col-md-6"><div class="nx-choice" data-vpc="${esc(v.id)}" tabindex="0" role="button">
            <div class="d-flex justify-content-between"><span class="fw-semibold">${esc(v.name || v.id)}</span><span>${v.default ? '<span class="nx-badge b-secondary">default</span>' : ""}${v.managed_by_fde ? ' <span class="nx-badge b-primary">FDE</span>' : ""}</span></div>
            <div class="small nx-muted nx-mono">${esc(v.id)} · ${esc(v.cidr)}</div>
            <div class="small">${v.subnets.filter(s => s.public).length} public · ${v.subnets.filter(s => !s.public).length} private subnets · ${v.azs.length} AZs</div></div></div>`).join("")}
          <div class="col-md-6"><div class="nx-choice" data-vpc="" tabindex="0" role="button"><div class="fw-semibold">No VPC</div><div class="small nx-muted">Only for S3, DynamoDB, DNS and certificates.</div></div></div></div>`;
        $$("[data-vpc]", m.el).forEach(c => c.onclick = () => { vpcId = c.dataset.vpc; $$("[data-vpc]", m.el).forEach(x => x.classList.toggle("selected", x === c));
          const v = r.vpcs.find(x => x.id === vpcId); if (v && !$("#im-name", m.el).value) $("#im-name", m.el).value = (v.name || "existing").toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^[^a-z]+/, "").slice(0, 32); });
      } catch (e) { host.innerHTML = `<div class="alert alert-danger py-2 small mb-0">${esc(UI.errorText(e))}</div>`; }
    };
    $("#im-acct", m.el).onchange = async () => { await loadRegions(); loadVpcs(); };
    $("#im-region", m.el).onchange = loadVpcs; $("#im-reload", m.el).onclick = loadVpcs;
    $("#im-go", m.el).onclick = async () => {
      try {
        const r = await NX.api.post("/api/m02/environments/import", { name: $("#im-name", m.el).value.trim(), account_id: $("#im-acct", m.el).value,
          region: $("#im-region", m.el).value, vpc_id: vpcId, tier: $("#im-tier", m.el).value, team: $("#im-team", m.el).value.trim() });
        m.hide(); NX.toast(`${r.environment.id} added. Launch resources into it now.`, "success"); loadList();
      } catch (e) { const er = $("#im-err", m.el); er.textContent = UI.errorText(e); er.classList.remove("d-none"); }
    };
    await loadRegions(); loadVpcs();
  }

  async function init() {
    if (!$("#ev-body-list")) return;
    W.accounts = await NX.loadAccounts();
    $("#ev-new").onclick = openWizard; $("#ev-cancel").onclick = closeWizard;
    $("#ev-import").onclick = openImport;
    if (location.hash === "#import") setTimeout(openImport, 300);
    $("#ev-back").onclick = () => { if (W.step > 0) { W.step--; W.preview = null; drawWizard(); } };
    $("#ev-next").onclick = next;
    if (NX.session.isAdmin()) { $("#ev-provision").classList.remove("d-none"); $("#ev-provision").onclick = openProvision; }
    if (location.hash === "#provision" && NX.session.isAdmin()) openProvision();
    if (me().role === "viewer") { $("#ev-new").disabled = true; $("#ev-import").disabled = true; }
    loadList();
  }
  document.addEventListener("DOMContentLoaded", () => setTimeout(init, 0));
})();
