/* FDE Nexus: per-page behavior. One file, each page calls the init it needs.
   All interactions are simulated (filter, sort, paginate, modals, run buttons). */
(function () {
  "use strict";
  const NX = window.NEXUS;
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => [...(r || document).querySelectorAll(s)];
  const esc = NX.esc;
  const qparam = (k) => new URLSearchParams(location.search).get(k) || "";

  /* ============================ OVERVIEW (live) ============================ */
  function initOverview() {
    const kpiHost = $("#nx-kpis");
    if (!kpiHost) return;
    const kpi = (label, value, icon, tone) => `
      <div class="col-6 col-md-4 col-xl"><div class="nx-card h-100"><div class="nx-card-body nx-kpi">
        <div class="nx-kpi-icon tone-${tone}"><i class="bi ${icon}"></i></div>
        <div><div class="nx-kpi-value">${esc(value)}</div><div class="nx-kpi-label">${esc(label)}</div></div>
      </div></div></div>`;

    // module list from the module manifests (only modules enabled for the dashboard)
    const mh = $("#nx-module-health");
    if (mh) NX.api.get("/api/modules").then(r => {
      const tone = { live: "success", partial: "warning", planned: "secondary" };
      mh.innerHTML = r.modules.map(m => `
        <a class="d-flex align-items-center gap-2 py-2 text-decoration-none border-bottom nx-mod-row" href="service-details.html?id=${m.id}" style="color:inherit">
          <span class="nx-kpi-icon tone-${tone[m.maturity]}" style="width:34px;height:34px;font-size:16px"><i class="bi ${esc(m.icon)}"></i></span>
          <span class="flex-grow-1"><span class="nx-mono small nx-muted">${m.id}</span><br><span class="fw-semibold small">${esc(m.name)}</span></span>
          <span class="small nx-muted me-2">${m.counts.live}/${m.capabilities.length}</span>${NX.ui.capBadge(m.maturity)}
        </a>`).join("");
    }).catch(e => { mh.innerHTML = emptyHtml(e.message); });

    (async () => {
      let ov, hs, notes = [];
      try {
        [ov, hs] = await Promise.all([NX.api.get("/api/overview"), NX.api.get("/api/health-summary")]);
        notes = (await NX.api.get("/api/notifications")).notifications || [];
      } catch (e) { kpiHost.innerHTML = `<div class="col-12">${emptyHtml(e.message)}</div>`; return; }
      await NX.loadAccounts();
      const k = ov.kpis, rc = hs.requests || {};
      kpiHost.innerHTML = kpi("My requests", k.my_requests, "bi-inbox", "primary") +
        kpi("Pending approvals", k.pending_approvals, "bi-hourglass-split", "warning") +
        kpi("Resources", k.resources, "bi-boxes", "info") +
        kpi("Catalog items", k.catalog_items, "bi-grid", "success") +
        kpi("AWS accounts", (NX.awsAccounts || []).length, "bi-cloud", "secondary");

      const at = $("#nx-activity");
      if (at) at.innerHTML = (ov.recent_activity || []).length ? ov.recent_activity.map(a => `
        <li class="t-${a.level === "warn" ? "warning" : "info"}">
          <div class="nx-tl-title small">${esc(a.action)} <span class="nx-muted">&middot; ${esc(a.target || "")}</span></div>
          <div class="nx-tl-meta">${esc(a.actor || "system")} &middot; ${esc(a.ts)}</div></li>`).join("") : `<li class="nx-muted small">No activity yet.</li>`;

      const al = $("#nx-alerts");
      if (al) al.innerHTML = notes.length ? notes.slice(0, 6).map(n => `
        <div class="nx-alert a-${n.level === "danger" ? "danger" : n.level === "warning" ? "warning" : n.level === "success" ? "success" : "info"}">
          <i class="bi bi-bell nx-alert-icon"></i>
          <div><div class="nx-alert-title">${esc(n.title)}</div><div class="nx-alert-text">${esc(n.body || "")}</div></div>
          <span class="nx-alert-time">${esc((n.created_at || "").slice(5, 16))}</span></div>`).join("") : emptyHtml("No notifications.");

      const bars = $("#nx-bars");
      if (bars) {
        const data = [["Pending", rc.pending || 0, false], ["Approved", (rc.approved || 0) + (rc.deploying || 0), true], ["Deployed", rc.deployed || 0, true],
          ["Rejected", rc.rejected || 0, false], ["Failed", rc.failed || 0, false]];
        const max = Math.max(...data.map(d => d[1]), 1);
        bars.innerHTML = data.map(d => `<div class="nx-bar-col"><span class="small fw-bold">${d[1]}</span>
          <div class="nx-bar ${d[2] ? "alt" : ""}" style="height:${Math.round(d[1] / max * 100)}%"></div><span class="nx-bar-label">${d[0]}</span></div>`).join("");
      }
      const donut = $("#nx-donut");
      if (donut) {
        const r = hs.resources || {}, total = r.total || 0, pct = total ? Math.round((r.healthy || 0) / total * 100) : 0;
        donut.style.background = total ? `conic-gradient(var(--nx-primary) ${pct * 3.6}deg, var(--nx-border) 0)` : "var(--nx-border)";
        donut.innerHTML = `<div class="nx-donut-hole"><div><div class="nx-donut-value">${total ? pct + "%" : "n/a"}</div><div class="nx-donut-sub">${total ? "healthy" : "no resources"}</div></div></div>`;
      }
    })();
  }

  /* ============================ AWS ACCOUNTS (persisted by the M01 backend) ============================ */
  function initAwsAccounts() {
    const host = $("#nx-aws");
    if (!host) return;
    const isAdmin = NX.session.isAdmin();
    async function draw() {
      host.innerHTML = `<div class="nx-empty"><i class="bi bi-hourglass-split"></i>Loading accounts…</div>`;
      const accts = await NX.loadAccounts();
      const activeId = NX.activeAccount.getId();
      let sugg = {};
      if (isAdmin) { try { sugg = (await NX.api.get("/api/aws-accounts/suggestions")).suggestions; } catch (e) { /* optional */ } }
      S_SUGG = sugg;
      const connected = accts.filter(a => a.status === "connected").length;
      host.innerHTML = `
        <div class="row g-3 mb-3">
          ${awsKpi("Accounts registered", accts.length, "bi-cloud", "primary")}
          ${awsKpi("Connected", connected, "bi-check-circle", "success")}
          ${awsKpi("Needs attention", accts.length - connected, "bi-exclamation-triangle", "warning")}
          ${awsKpi("Active account", (NX.activeAccount.get() || {}).alias || "None", "bi-star", "info")}
        </div>
        <div class="nx-card"><div class="nx-table-wrap">
          <table class="nx-table"><thead><tr>
            <th>Account</th><th>ID</th><th>Connection</th><th>Region</th><th>Env</th><th>Status / last test</th><th class="text-end">Actions</th>
          </tr></thead><tbody>${accts.length ? accts.map(a => accountRow(a, activeId, isAdmin)).join("")
            : `<tr><td colspan="7"><div class="nx-empty"><i class="bi bi-cloud-plus"></i>No AWS accounts connected. ${isAdmin ? "Use “Connect account” to add one." : "Ask an admin to connect one."}</div></td></tr>`}</tbody></table>
        </div></div>`;
      $$("[data-activate]").forEach(b => b.onclick = async () => {
        try { await NX.activeAccount.set(b.dataset.activate); NX.toast("Active account updated.", "success"); draw(); }
        catch (e) { NX.toast(e.message, "danger"); }
      });
      $$("[data-test]").forEach(b => b.onclick = () => testConnection(b.dataset.test, draw));
      $$("[data-view-acct]").forEach(b => b.onclick = () => viewAccount(b.dataset.viewAcct));
      $$("[data-useprof]").forEach(b => b.onclick = async () => {
        const [id, prof] = b.dataset.useprof.split("|"), a = NX.awsAccounts.find(x => x.id === id);
        b.disabled = true; b.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Testing';
        try {
          const r = await NX.api.call("PUT", `/api/aws-accounts/${encodeURIComponent(id)}`, { alias: a.alias, name: a.name, method: "profile", profile: prof, region: a.region, env: a.env });
          NX.toast(`${a.alias}: ${r.account.note}`, r.account.status === "connected" ? "success" : "danger");
        } catch (e) { NX.toast(UI_ERR(e), "danger"); }
        draw();
      });
      $$("[data-edit-acct]").forEach(b => b.onclick = () => openConnectModal(draw, NX.awsAccounts.find(x => x.id === b.dataset.editAcct)));
      $$("[data-del-acct]").forEach(b => b.onclick = async () => {
        if (!window.confirm(`Remove AWS account ${b.dataset.delAcct} from the portal?`)) return;
        try { await NX.api.call("DELETE", `/api/aws-accounts/${encodeURIComponent(b.dataset.delAcct)}`); NX.toast("Account removed.", "success"); draw(); }
        catch (e) { NX.toast(e.message, "danger"); }
      });
    }
    draw();
    const all = $("#nx-aws-testall");
    if (all) all.onclick = async () => {
      all.disabled = true; all.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Testing all';
      try {
        const r = await NX.api.post("/api/aws-accounts/test-all");
        const ok = r.results.filter(x => x.status === "connected").length;
        NX.toast(r.results.length ? `${ok} of ${r.results.length} accounts connected${r.simulated ? " (simulation mode: no AWS calls)" : ""}.` : "No accounts to test.", ok === r.results.length ? "success" : "warning");
      } catch (e) { NX.toast(e.message, "danger"); }
      all.disabled = false; all.innerHTML = '<i class="bi bi-plug me-1"></i>Test all connections';
      draw();
    };
    const add = $("#nx-aws-connect");
    if (add) { add.disabled = !isAdmin; add.title = isAdmin ? "" : "Admin only"; add.onclick = () => openConnectModal(draw); }
  }

  let S_SUGG = {};
  const UI_ERR = (e) => e.message + (e.details && e.details.length ? ": " + e.details.join(" ") : "");
  function awsKpi(label, value, icon, tone) {
    return `<div class="col-6 col-xl-3"><div class="nx-card h-100"><div class="nx-card-body nx-kpi">
      <div class="nx-kpi-icon tone-${tone}"><i class="bi ${icon}"></i></div>
      <div><div class="nx-kpi-value" style="font-size:20px">${esc(value)}</div><div class="nx-kpi-label">${esc(label)}</div></div>
    </div></div></div>`;
  }
  function accountRow(a, activeId, isAdmin) {
    const method = a.method === "instance-role" ? '<span class="nx-badge b-secondary">Host credentials</span>'
      : a.method === "profile" ? `<span class="nx-badge b-info">Profile</span><div class="small nx-muted nx-mono">${esc(a.profile || "")}</div>`
      : '<span class="nx-badge b-primary">AssumeRole</span>';
    const st = a.status === "connected" ? NX.badge("connected")
      : a.status === "failed" ? NX.badge("failed", "Failed") : NX.badge("unverified", "Unverified");
    return `<tr>
      <td><div class="fw-semibold">${esc(a.name)}</div><div class="small nx-muted nx-mono">${esc(a.alias)}</div></td>
      <td class="nx-mono small">${esc(a.id)}</td>
      <td>${method}${a.role_arn ? `<div class="small nx-muted nx-mono" style="max-width:260px;overflow:hidden;text-overflow:ellipsis">${esc(a.role_arn)}</div>` : ""}</td>
      <td class="small">${esc(a.region)}</td>
      <td><span class="nx-badge b-secondary">${esc(a.env)}</span></td>
      <td>${st}<div class="small nx-muted" title="${esc(a.note || "")}">${esc(a.last_checked || "never tested")}</div>
        ${a.status === "failed" ? `<div class="small text-danger" style="max-width:240px;white-space:normal">${esc((a.note || "").slice(0, 160))}</div>` : ""}
        ${(S_SUGG[a.id] || []).map(p => `<button class="btn btn-sm btn-success mt-1 me-1" data-useprof="${esc(a.id)}|${esc(p)}"><i class="bi bi-magic me-1"></i>Use profile ${esc(p)}</button>`).join("")}</td>
      <td class="text-end" style="white-space:nowrap">
        <button class="btn btn-sm btn-outline-secondary" data-view-acct="${esc(a.id)}" title="Details"><i class="bi bi-eye"></i></button>
        <button class="btn btn-sm btn-outline-primary" data-test="${esc(a.id)}" title="Test connection"><i class="bi bi-plug me-1"></i>Test</button>
        <a class="btn btn-sm btn-outline-secondary" href="inventory.html?account=${encodeURIComponent(a.id)}" title="Live inventory"><i class="bi bi-database-check"></i></a>
        ${isAdmin ? `<button class="btn btn-sm btn-outline-secondary" data-edit-acct="${esc(a.id)}" title="Edit"><i class="bi bi-pencil"></i></button>` : ""}
        ${a.status === "connected" ? (a.id === activeId
          ? '<button class="btn btn-sm btn-primary" disabled>Active</button>'
          : `<button class="btn btn-sm btn-outline-primary" data-activate="${esc(a.id)}">Set active</button>`) : ""}
        ${isAdmin ? `<button class="btn btn-sm btn-outline-danger" data-del-acct="${esc(a.id)}" title="Remove"><i class="bi bi-trash"></i></button>` : ""}
      </td></tr>`;
  }
  async function testConnection(id, done) {
    const a = NX.awsAccounts.find(x => x.id === id);
    const btn = document.querySelector(`[data-test="${id}"]`);
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Testing'; }
    try {
      const r = (await NX.api.post(`/api/aws-accounts/${encodeURIComponent(id)}/test`)).account;
      NX.toast(`${r.alias}: ${r.note}`, r.status === "connected" ? "success" : "danger");
    } catch (e) { NX.toast(`${a ? a.alias : id}: ${e.message}`, "danger"); }
    if (done) done();
  }

  function viewAccount(id) {
    const a = NX.awsAccounts.find(x => x.id === id);
    if (!a) return;
    const modal = buildModal("acct-view", `${a.name} (${a.id})`, `
      <div class="row g-3">
        ${["alias","id","region","env"].map(k => `<div class="col-6"><div class="small nx-muted">${k}</div><div class="fw-semibold">${esc(a[k])}</div></div>`).join("")}
        <div class="col-6"><div class="small nx-muted">connection</div><div class="fw-semibold">${esc(a.method)}</div></div>
        <div class="col-6"><div class="small nx-muted">status</div><div class="fw-semibold">${esc(a.status)}</div></div>
        <div class="col-6"><div class="small nx-muted">last checked</div><div class="fw-semibold">${esc(a.last_checked || "never")}</div></div>
        <div class="col-6"><div class="small nx-muted">added by</div><div class="fw-semibold">${esc(a.created_by || "")}</div></div>
      </div>
      ${a.role_arn ? `<hr class="nx-hr"><div class="small nx-muted">Role ARN</div><div class="nx-mono small">${esc(a.role_arn)}</div>` : ""}
      ${a.external_id ? `<div class="small nx-muted mt-2">External ID</div><div class="nx-mono small">${esc(a.external_id)}</div>` : ""}
      ${a.note ? `<hr class="nx-hr"><div class="small">${esc(a.note)}</div>` : ""}
      <hr class="nx-hr">
      <div class="small nx-muted">${a.method === "instance-role"
        ? "Uses the portal host's default AWS credentials directly (instance role or AWS_PROFILE). No assume-role step."
        : a.method === "profile" ? `Uses the <span class='nx-mono'>${esc(a.profile)}</span> profile from the portal host's ~/.aws/config (SSO sessions must be renewed with aws sso login).`
        : "The portal host calls <span class='nx-mono'>sts:AssumeRole</span> on this role and uses the temporary credentials for this account's API calls."}</div>`, null);
    modal._show();
  }
  async function openConnectModal(onDone, existing) {
    const ex = existing || null;
    let profiles = [];
    try { profiles = (await NX.api.get("/api/aws-accounts/profiles")).profiles; } catch (e) { /* admins only */ }
    const regions = NX.awsRegions.includes((ex || {}).region) || !ex ? NX.awsRegions : [ex.region, ...NX.awsRegions];
    const sel = (v, cur) => v === cur ? "selected" : "";
    const modal = buildModal("acct-connect", ex ? `Edit ${ex.alias} (${ex.id})` : "Connect an AWS account", `
      <p class="nx-muted small">The portal only stores how to reach the account, never long-lived keys. Use <b>Test connection</b> before saving.</p>
      <div class="row g-3">
        <div class="col-6"><label class="form-label small fw-semibold">Account ID</label><input class="form-control" id="ca-id" placeholder="123456789012" maxlength="12" value="${esc((ex || {}).id || "")}" ${ex ? "disabled" : ""}></div>
        <div class="col-6"><label class="form-label small fw-semibold">Alias</label><input class="form-control" id="ca-alias" placeholder="payments-prod" value="${esc((ex || {}).alias || "")}"></div>
        <div class="col-12"><label class="form-label small fw-semibold">Connection method</label>
          <select class="form-select" id="ca-method">
            <option value="profile" ${sel("profile", (ex || {}).method)}>Local AWS profile on the portal host (SSO / ~/.aws/config)</option>
            <option value="assume-role" ${sel("assume-role", (ex || { method: "assume-role" }).method)}>Cross-account IAM role (AssumeRole)</option>
            <option value="instance-role" ${sel("instance-role", (ex || {}).method)}>Host credentials (instance role / AWS_PROFILE)</option></select>
          <div class="form-text" id="ca-method-help"></div></div>
        <div class="col-12" id="ca-profile-wrap"><label class="form-label small fw-semibold">Profile</label>
          ${profiles.length ? `<select class="form-select" id="ca-profile">${profiles.map(p => `<option ${sel(p, (ex || {}).profile)}>${esc(p)}</option>`).join("")}</select>`
            : `<input class="form-control" id="ca-profile" placeholder="profile name" value="${esc((ex || {}).profile || "")}">`}
          <div class="form-text">Names read from the portal host's <span class="nx-mono">~/.aws/config</span>. For SSO profiles run <span class="nx-mono">aws sso login --profile &lt;name&gt;</span> on that host when the session expires.</div></div>
        <div class="col-12" id="ca-role-wrap"><label class="form-label small fw-semibold">Role ARN</label>
          <input class="form-control nx-mono" id="ca-role" placeholder="arn:aws:iam::123456789012:role/FDENexusCrossAccountRole" value="${esc((ex || {}).role_arn || "")}"></div>
        <div class="col-6" id="ca-ext-wrap"><label class="form-label small fw-semibold">External ID (optional)</label><input class="form-control" id="ca-ext" value="${esc((ex || {}).external_id || "")}"></div>
        <div class="col-6"><label class="form-label small fw-semibold">Default region</label>
          <select class="form-select" id="ca-region">${regions.map(r => `<option ${sel(r, (ex || {}).region)}>${r}</option>`).join("")}</select></div>
        <div class="col-12"><label class="form-label small fw-semibold">Environment</label>
          <select class="form-select" id="ca-env">${["non-production", "production", "sandbox", "shared"].map(v => `<option ${sel(v, (ex || {}).env)}>${v}</option>`).join("")}</select></div>
      </div>
      <div class="alert py-2 small mt-3 mb-0 d-none" id="ca-test-out"></div>
      <div class="alert alert-danger py-2 small mt-3 mb-0 d-none" id="ca-err"></div>
      <button class="btn btn-outline-primary mt-3" id="ca-test" type="button"><i class="bi bi-plug me-1"></i>Test connection (without saving)</button>`, ex ? "Save" : "Connect");
    const methodSel = $("#ca-method");
    const HELP = { "profile": "Best on a laptop or admin host with AWS SSO: the portal uses that profile's credentials for this account.",
      "assume-role": "Best on a server: the portal's own identity assumes a role in this account. The role's trust policy must allow it.",
      "instance-role": "Uses the portal host's default credentials directly (EC2 instance profile, or start the portal with AWS_PROFILE=...)." };
    const sync = () => {
      const m = methodSel.value;
      $("#ca-role-wrap").style.display = m === "assume-role" ? "" : "none";
      $("#ca-ext-wrap").style.display = m === "assume-role" ? "" : "none";
      $("#ca-profile-wrap").style.display = m === "profile" ? "" : "none";
      $("#ca-method-help").textContent = HELP[m];
    };
    methodSel.onchange = sync; sync();
    const body = () => ({ id: $("#ca-id").value.trim(), alias: $("#ca-alias").value.trim(), method: methodSel.value,
      role_arn: $("#ca-role").value.trim(), external_id: $("#ca-ext").value.trim(), profile: ($("#ca-profile").value || "").trim(),
      region: $("#ca-region").value, env: $("#ca-env").value });
    $("#ca-test").onclick = async () => {
      const out = $("#ca-test-out"), b = $("#ca-test");
      b.disabled = true; b.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Testing';
      try { const r = await NX.api.post("/api/aws-accounts/test-config", body());
        out.className = `alert alert-${r.status === "connected" ? "success" : "danger"} py-2 small mt-3 mb-0`;
        out.textContent = (r.status === "connected" ? "Connected. " : "Failed. ") + r.note;
        (r.suggested_profiles || []).forEach(p => {
          const btn = document.createElement("button"); btn.type = "button"; btn.className = "btn btn-sm btn-success mt-2 me-1 d-block";
          btn.textContent = `Use profile ${p} instead`;
          btn.onclick = () => { methodSel.value = "profile"; sync(); const pf = $("#ca-profile"); pf.value = p; $("#ca-test").click(); };
          out.appendChild(btn);
        }); }
      catch (e) { out.className = "alert alert-danger py-2 small mt-3 mb-0"; out.textContent = e.message; }
      b.disabled = false; b.innerHTML = '<i class="bi bi-plug me-1"></i>Test connection (without saving)';
    };
    modal._confirm.onclick = async () => {
      const err = $("#ca-err");
      modal._confirm.disabled = true;
      try {
        const r = ex ? await NX.api.call("PUT", `/api/aws-accounts/${encodeURIComponent(ex.id)}`, body()) : await NX.api.post("/api/aws-accounts", body());
        modal._hide();
        NX.toast(`${r.account.alias}: ${r.account.note}`, r.account.status === "connected" ? "success" : "danger");
        if (onDone) onDone();
      } catch (e) { err.textContent = e.message; err.classList.remove("d-none"); }
      modal._confirm.disabled = false;
    };
    modal._show();
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
    const search = $("#nx-mod-search"), groupSel = $("#nx-mod-group"), statusSel = $("#nx-mod-status");
    const admin = NX.session.isAdmin();
    let mods = [];
    const pre = qparam("q"); if (pre) search.value = pre;
    const showAll = $("#nx-mod-all");
    if (showAll) showAll.closest(".form-check").classList.toggle("d-none", !admin);

    async function load() {
      try { mods = (await NX.api.get("/api/modules" + (admin && showAll && showAll.checked ? "?all=1" : ""))).modules; }
      catch (e) { host.innerHTML = `<div class="col-12">${emptyHtml(e.message)}</div>`; return; }
      const groups = [...new Set(mods.map(m => m.group))].sort();
      const cur = groupSel.value;
      groupSel.innerHTML = `<option value="">All groups</option>` + groups.map(g => `<option ${g === cur ? "selected" : ""}>${esc(g)}</option>`).join("");
      render();
    }
    const tone = { live: "success", partial: "warning", planned: "secondary" };
    function render() {
      const q = search.value.trim().toLowerCase(), g = groupSel.value, s = statusSel.value;
      const list = mods.filter(m => (!q || (m.id + " " + m.name + " " + m.description + " " + m.capabilities.map(c => c.name).join(" ")).toLowerCase().includes(q)) &&
        (!g || m.group === g) && (!s || m.maturity === s));
      $("#nx-mod-count").textContent = `${list.length} of ${mods.length} modules`;
      host.innerHTML = list.length ? list.map(m => {
        const n = m.capabilities.length, c = m.counts;
        return `<div class="col-12 col-md-6 col-xl-4"><div class="nx-card nx-module h-100 ${m.enabled ? "" : "opacity-75"}" data-go="${m.id}">
          <div class="nx-card-body">
            <div class="d-flex align-items-start gap-3">
              <div class="nx-mod-icon tone-${tone[m.maturity]}"><i class="bi ${esc(m.icon)}"></i></div>
              <div class="flex-grow-1"><div class="d-flex justify-content-between align-items-center">
                <span class="nx-mod-id">${m.id}</span><span>${NX.ui ? NX.ui.capBadge(m.maturity) : esc(m.maturity)}${m.enabled ? "" : ' <span class="nx-badge b-secondary">hidden</span>'}</span></div>
                <div class="nx-mod-name">${esc(m.name)}</div></div>
            </div>
            <p class="nx-mod-desc">${esc(m.description)}</p>
            <div class="progress mb-1" style="height:8px" title="${c.live} live, ${c.partial} partial, ${c.planned} planned">
              <div class="progress-bar bg-success" style="width:${c.live / n * 100}%"></div>
              <div class="progress-bar bg-warning" style="width:${c.partial / n * 100}%"></div></div>
            <div class="small nx-muted">${c.live} live · ${c.partial} partial · ${c.planned} planned of ${n} capabilities</div>
            <hr class="nx-hr">
            <div class="d-flex justify-content-between align-items-center small nx-muted">
              <span><i class="bi bi-person me-1"></i>${esc(m.owner)}</span>
              ${admin && m.id !== "M01" ? `<div class="form-check form-switch mb-0" title="Show on dashboard"><input class="form-check-input" type="checkbox" data-toggle="${m.id}" ${m.enabled ? "checked" : ""}></div>`
                : `<span class="nx-badge b-secondary">${esc(m.phase)}</span>`}
            </div></div></div></div>`;
      }).join("") : `<div class="col-12"><div class="nx-card">${emptyHtml("No modules match your filters.")}</div></div>`;
      $$("[data-go]").forEach(card => card.onclick = (e) => { if (!e.target.closest(".form-check")) location.href = "service-details.html?id=" + card.dataset.go; });
      $$("[data-toggle]").forEach(t => t.onchange = async () => {
        try { await NX.api.call("PUT", "/api/modules/" + t.dataset.toggle, { enabled: t.checked });
          NX.toast(`${t.dataset.toggle} ${t.checked ? "shown on" : "hidden from"} the dashboard.`, "success"); load(); }
        catch (e) { NX.toast(e.message, "danger"); t.checked = !t.checked; }
      });
    }
    [search, groupSel, statusSel].forEach(c => c.addEventListener("input", render));
    if (showAll) showAll.onchange = load;
    load();
  }

  /* ============================ SERVICE DETAILS (manifest driven) ============================ */
  function initServiceDetails() {
    const root = $("#nx-detail");
    if (!root) return;
    const id = (qparam("id") || "M01").toUpperCase();
    (async () => {
      let m;
      try { m = (await NX.api.get("/api/modules/" + encodeURIComponent(id))).module; }
      catch (e) { $("#nx-detail-head").innerHTML = emptyHtml(e.message); return; }
      $("#nx-detail-breadcrumb").textContent = m.name;
      const UI = NX.ui, c = m.counts, ws = m.ui && m.ui.workspace;
      $("#nx-detail-head").innerHTML = `
        <div class="d-flex align-items-start gap-3 flex-wrap">
          <div class="nx-mod-icon tone-${{ live: "success", partial: "warning", planned: "secondary" }[m.maturity]}" style="width:56px;height:56px;font-size:28px"><i class="bi ${esc(m.icon)}"></i></div>
          <div class="flex-grow-1">
            <div class="d-flex align-items-center gap-2 flex-wrap"><span class="nx-mod-id">${m.id}</span>${UI.capBadge(m.maturity)}
              <span class="nx-badge b-secondary">Phase ${esc(m.phase)}</span>${m.enabled ? "" : '<span class="nx-badge b-secondary">hidden from dashboard</span>'}</div>
            <h2 class="h5 mt-1 mb-1">${esc(m.name)}</h2>
            <p class="nx-muted mb-1">${esc(m.description)}</p>
            <div class="small nx-muted">${c.live} live · ${c.partial} partial · ${c.planned} planned · folder <span class="nx-mono">modules/${esc(m.slug)}</span></div>
          </div>
          <div class="text-end">
            <div class="small nx-muted">Owner</div><div class="fw-semibold">${esc(m.owner)}</div>
            <div class="mt-2 d-flex gap-2 justify-content-end">
              ${ws ? `<a class="btn btn-sm btn-primary" href="${esc(ws)}"><i class="bi bi-box-arrow-up-right me-1"></i>Open workspace</a>` : ""}
              <button class="btn btn-sm btn-outline-primary" id="nx-configure"><i class="bi bi-sliders me-1"></i>Configure</button></div>
          </div>
        </div>`;
      $("#nx-configure").onclick = () => {
        if (m.id === "M01") return openM01Config();
        if (m.id === "M03" || m.id === "M02") return (location.href = "changes.html#settings");
        NX.toast(`${m.id} has no settings yet: its capabilities are still planned. Build it from modules/${m.slug}/README.md.`, "info");
      };

      // Capabilities: status + what it does + where to use it
      const design = m.design ? `<div class="nx-card mt-3"><div class="nx-card-body"><div class="fw-bold mb-2">Design inputs</div>
        ${Object.entries(m.design).map(([k, v]) => `<div class="mb-2"><div class="small fw-semibold text-capitalize">${esc(k.replace(/_/g, " "))}</div>
          <div class="small">${Array.isArray(v) ? v.map(x => `<span class="nx-cap">${esc(x)}</span>`).join(" ")
            : typeof v === "object" ? Object.entries(v).map(([a, b]) => `<div><b>${esc(a)}</b>: ${esc(b.join(", "))}</div>`).join("") : esc(v)}</div></div>`).join("")}</div></div>` : "";
      $("#pane-capabilities").innerHTML = `<div class="nx-card"><div class="nx-card-body">
        <div class="small nx-muted mb-2"><b>live</b> works end to end in the portal · <b>partial</b> some of it works (see note) · <b>planned</b> not built yet</div>
        ${m.capabilities.map(cp => `<div class="nx-cap-row">
          <div style="min-width:78px">${UI.capBadge(cp.status)}</div>
          <div class="flex-grow-1"><div class="fw-semibold small">${esc(cp.name)}${cp.provided_by ? ` <span class="nx-muted fw-normal">via ${esc(cp.provided_by)}</span>` : ""}</div>
            <div class="small nx-muted">${esc(cp.summary)}</div></div>
          ${cp.where ? `<a class="btn btn-sm btn-outline-secondary" href="${esc(cp.where)}">Open</a>` : ""}</div>`).join("")}</div></div>${design}`;

      // M01 keeps its live catalog / inventory tabs; other modules show activity only
      const tabs = $$("#nx-detail .nx-tabs button");
      if (m.id === "M01") {
        tabs.find(b => b.dataset.tab === "operations").textContent = "Catalog";
        tabs.find(b => b.dataset.tab === "findings").textContent = "Unhealthy resources";
        wireTabs(); loadM01Live();
        return;
      }
      tabs.filter(b => ["operations", "findings"].includes(b.dataset.tab)).forEach(b => b.remove());
      wireTabs();
      const pat = { M02: /environment|aws_account|iac_|ec2_/, M03: /iac_|m03_/ }[m.id];
      if (!pat) { $("#pane-activity").innerHTML = emptyHtml("No activity: this module has no backend yet."); return; }
      try {
        const logs = ((await NX.api.get("/api/audit?limit=300")).logs || []).filter(a => pat.test(a.action));
        $("#pane-activity").innerHTML = logs.length ? `<ul class="nx-timeline">${logs.map(a => `<li class="t-${a.level === "warn" ? "warning" : "info"}">
          <div class="nx-tl-title small">${esc(a.action)} <span class="nx-muted">&middot; ${esc(a.target || "")}</span></div>
          <div class="nx-tl-meta">${esc(a.actor || "system")} &middot; ${esc(a.details || "")} &middot; ${esc(a.ts)}</div></li>`).join("")}</ul>` : emptyHtml("No activity yet.");
      } catch (e) { $("#pane-activity").innerHTML = emptyHtml(e.message); }
    })();
  }

  /* M01 tabs are filled from the live backend instead of sample data. */
  async function loadM01Live() {
    const set = (id, html) => { const n = $(id); if (n) n.innerHTML = html; };
    const loading = emptyHtml("Loading…");
    ["#pane-operations", "#pane-findings", "#pane-activity"].forEach(i => set(i, loading));
    try {
      const [cat, res, aud] = await Promise.all([
        NX.api.get("/api/catalog"), NX.api.get("/api/resources"), NX.api.get("/api/audit?limit=50")]);
      const items = cat.items || [];
      set("#pane-operations", items.length ? tableHtml(
        ["Catalog item", "Category", "Risk", "Approval", "Est. cost / time"],
        items.map(i => [`<span class="nx-id">${esc(i.id)}</span><div class="small">${esc(i.name)}</div>`, esc(i.category),
          NX.riskBadge(i.risk_tier), i.approval_required ? "Required" : "Auto", esc((i.est_cost || "-") + " · " + (i.est_time || "-"))])
      ) : emptyHtml("The service catalog is empty."));
      const bad = (res.resources || []).filter(r => r.status !== "healthy");
      set("#pane-findings", bad.length ? tableHtml(
        ["Resource", "Type", "Environment", "Status"],
        bad.map(r => [`<span class="nx-id">${esc(r.id)}</span><div class="small">${esc(r.name)}</div>`, esc(r.type), esc(r.environment), esc(r.status)])
      ) : emptyHtml("No unhealthy resources."));
      const logs = aud.logs || [];
      set("#pane-activity", logs.length
        ? `<ul class="nx-timeline">${logs.map(a => `<li class="t-${a.level === "warn" ? "warning" : "info"}">
            <div class="nx-tl-title small">${esc(a.action)} <span class="nx-muted">&middot; ${esc(a.target || "")}</span></div>
            <div class="nx-tl-meta">${esc(a.actor || "system")} &middot; ${esc(a.ts)}</div></li>`).join("")}</ul>`
        : emptyHtml("No activity recorded yet."));
    } catch (e) {
      ["#pane-operations", "#pane-findings", "#pane-activity"].forEach(i => set(i, emptyHtml(e.message)));
    }
  }

  async function openM01Config() {
    if (!NX.session.isAdmin()) return NX.toast("Only an administrator can change module configuration.", "warning");
    let cfg;
    try { cfg = await NX.api.get("/api/config"); } catch (e) { return NX.toast(e.message, "danger"); }
    const rt = cfg.runtime || {};
    const modal = buildModal("m01-config", "Configure M01", `
      <div class="small nx-muted mb-2">Runtime (set by environment variables on the host)</div>
      <div class="d-flex flex-wrap gap-2 mb-3">
        <span class="nx-badge b-${rt.live_reads ? "success" : "secondary"}">${rt.live_reads ? "Live data from AWS" : "Offline (no AWS reads)"}</span>
        <span class="nx-badge b-${rt.demo_mode ? "warning" : "success"}">${rt.demo_mode ? "Changes simulated" : "Live changes"}</span>
        <span class="nx-badge b-secondary">Default region ${esc(rt.region)}</span>
        <span class="nx-badge b-secondary">Session ${esc(rt.jwt_expiry_hours)}h</span>
      </div>
      <div class="small nx-muted mb-2">The default region comes from <b>${esc(rt.region_source || "")}</b> and is used only when an AWS account has no region.
        Each connected account and each environment uses its own region${NX.activeAccount.get() ? ` (active account ${esc(NX.activeAccount.get().alias)}: <b>${esc(NX.activeAccount.get().region)}</b>)` : ""}.</div>
      <table class="nx-table mb-3"><thead><tr><th>Environment variable</th><th>Current value</th><th>Effect</th></tr></thead><tbody>
        <tr><td class="nx-mono small">M01_DEMO</td><td class="nx-mono small">${esc((rt.env || {}).M01_DEMO)}</td><td class="small">1 = simulate AWS changes, 0 = live (./start-portal.sh --prod)</td></tr>
        <tr><td class="nx-mono small">M01_LIVE_READS</td><td class="nx-mono small">${esc((rt.env || {}).M01_LIVE_READS)}</td><td class="small">1 = read real data from connected accounts (read-only), 0 = fully offline</td></tr>
        <tr><td class="nx-mono small">AWS_PROFILE</td><td class="nx-mono small">${esc((rt.env || {}).AWS_PROFILE || "(not set)")}</td><td class="small">Host credentials used by the "Host credentials" method and as the base for AssumeRole</td></tr>
        <tr><td class="nx-mono small">AWS_REGION</td><td class="nx-mono small">${esc(rt.region)}</td><td class="small">Fallback region for accounts without one</td></tr>
        <tr><td class="nx-mono small">JWT_EXPIRY_HOURS</td><td class="nx-mono small">${esc(rt.jwt_expiry_hours)}</td><td class="small">Sign-in session length</td></tr>
        <tr><td class="nx-mono small">GITLAB_TOKEN</td><td class="small">set on host only</td><td class="small">Lets M03 open merge requests (settings in IaC Changes)</td></tr>
      </tbody></table>
      <div class="small nx-muted mb-3">Set these before starting the portal, e.g. <span class="nx-mono">AWS_REGION=eu-west-1 M01_DEMO=0 ./start-portal.sh --prod</span>. They cannot change while it runs.</div>
      <div class="small fw-semibold mb-2">Service catalog</div>
      <table class="nx-table"><thead><tr><th>Item</th><th>Risk</th><th>Requires approval</th><th>Enabled</th></tr></thead><tbody>
      ${(cfg.catalog || []).map(i => `<tr><td>${esc(i.name)}</td><td>${NX.riskBadge(i.risk_tier)}</td>
        <td><div class="form-check form-switch"><input class="form-check-input" type="checkbox" data-appr="${esc(i.id)}" ${i.approval_required ? "checked" : ""}></div></td>
        <td><div class="form-check form-switch"><input class="form-check-input" type="checkbox" data-en="${esc(i.id)}" ${i.enabled ? "checked" : ""}></div></td></tr>`).join("")}
      </tbody></table>
      <div class="small nx-muted mt-2">Requests for production are always approval-gated regardless of this setting.</div>`, "Save");
    modal._confirm.onclick = async () => {
      modal._confirm.disabled = true;
      try {
        for (const i of cfg.catalog || []) {
          const appr = modal._el.querySelector(`[data-appr="${i.id}"]`).checked, en = modal._el.querySelector(`[data-en="${i.id}"]`).checked;
          if (appr !== !!i.approval_required || en !== !!i.enabled)
            await NX.api.call("PUT", `/api/catalog/${encodeURIComponent(i.id)}`, { approval_required: appr, enabled: en });
        }
        modal._hide(); NX.toast("Configuration saved.", "success"); loadM01Live();
      } catch (e) { NX.toast(e.message, "danger"); }
      modal._confirm.disabled = false;
    };
    modal._show();
  }

  /* ============================ REQUESTS (live: M01 backend) ============================ */
  function normReq(r) {
    return { id: r.id, item: r.item_name, team: r.team || "", requester: r.requester || "",
      risk: r.risk_tier, status: r.status, cost: r.est_cost || "",
      submitted: (r.created_at || "").replace("T", " ").slice(0, 16), env: r.environment || "", raw: r };
  }

  function initRequests() {
    const tbody = $("#nx-req-body");
    if (!tbody) return;
    const search = $("#nx-req-search"), riskSel = $("#nx-req-risk"), statusSel = $("#nx-req-status");
    const ses = NX.session.get() || {};
    const canDecide = ["admin", "approver", "operator", "security"].includes(ses.role);
    let sortKey = "submitted", sortDir = -1, page = 1;
    const pageSize = 10;
    let data = [];

    function setBody(html) { tbody.innerHTML = `<tr><td colspan="8">${html}</td></tr>`; }

    async function load() {
      setBody(`<div class="nx-empty"><i class="bi bi-hourglass-split"></i>Loading requests…</div>`);
      try {
        const r = await NX.api.get("/api/requests");
        data = (r.requests || []).map(normReq);
        render();
      } catch (e) {
        setBody(`<div class="nx-empty"><i class="bi bi-exclamation-triangle"></i>${esc(e.message)}</div>`);
      }
    }

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
          <td><span class="nx-id">${esc(r.id)}</span></td>
          <td>${esc(r.item)}<div class="small nx-muted">${esc(r.env)}</div></td>
          <td>${esc(r.team)}</td>
          <td>${NX.riskBadge(r.risk)}</td>
          <td>${esc(r.cost)}</td>
          <td>${NX.badge(r.status)}</td>
          <td class="small nx-muted">${esc(r.submitted)}</td>
          <td class="text-end">
            <button class="btn btn-sm btn-outline-secondary" data-view="${esc(r.id)}" title="View"><i class="bi bi-eye"></i></button>
            ${r.status === "pending" && canDecide ? `<button class="btn btn-sm btn-outline-success" data-approve="${esc(r.id)}" title="Approve"><i class="bi bi-check-lg"></i></button>
            <button class="btn btn-sm btn-outline-danger" data-reject="${esc(r.id)}" title="Reject"><i class="bi bi-x-lg"></i></button>` : ""}
          </td>
        </tr>`).join("")
        : `<tr><td colspan="8"><div class="nx-empty"><i class="bi bi-inbox"></i>${data.length ? "No requests match your filters." : "No requests yet. Use “New request” to create the first one."}</div></td></tr>`;
      $("#nx-req-info").textContent = `Showing ${slice.length} of ${list.length} requests`;
      $("#nx-req-pages").innerHTML = pagerButtons(page, pages);
      wirePager($("#nx-req-pages"), (p) => { page = p; render(); });
      $$("[data-view]").forEach(b => b.onclick = () => openRequestModal(b.dataset.view));
      $$("[data-approve]").forEach(b => b.onclick = () => decide(b.dataset.approve, "approve"));
      $$("[data-reject]").forEach(b => b.onclick = () => decide(b.dataset.reject, "reject"));
    }

    async function decide(id, action) {
      let reason = "";
      if (action === "reject") { reason = window.prompt("Reason for rejection (optional):") ; if (reason === null) return; }
      try {
        await NX.api.post(`/api/requests/${encodeURIComponent(id)}/${action}`, { reason });
        NX.toast(`${id} ${action === "approve" ? "approved" : "rejected"}.`, action === "approve" ? "success" : "danger");
        load();
      } catch (e) { NX.toast(e.message, "danger"); }
    }

    [search, riskSel, statusSel].forEach(c => c.addEventListener("input", () => { page = 1; render(); }));

    // ----- new request: form is generated from the catalog item's input_schema
    const nb = $("#nx-new-request");
    if (nb) nb.onclick = async () => {
      let items = [];
      try { items = (await NX.api.get("/api/catalog")).items || []; }
      catch (e) { return NX.toast(e.message, "danger"); }
      if (!items.length) return NX.toast("The catalog is empty.", "warning");
      const modal = buildModal("new-req", "New self-service request", `
        <div class="mb-3"><label class="form-label small fw-semibold" for="f-item">Catalog item</label>
          <select class="form-select" id="f-item">${items.map(i => `<option value="${esc(i.id)}">${esc(i.name)}</option>`).join("")}</select>
          <div class="small nx-muted mt-1" id="f-item-desc"></div></div>
        <div class="row g-3" id="f-fields"></div>
        <div class="alert alert-danger py-2 small mt-3 mb-0 d-none" id="f-err"></div>`, "Submit request");

      const sel = modal._el.querySelector("#f-item");
      function drawFields() {
        const item = items.find(i => i.id === sel.value);
        modal._el.querySelector("#f-item-desc").textContent =
          `${item.description || ""} Risk ${item.risk_tier}, ${item.approval_required ? "needs approval" : "auto-approved"}, ${item.est_cost || "cost n/a"}, ${item.est_time || ""}`;
        modal._el.querySelector("#f-fields").innerHTML = (item.input_schema || []).map(f => {
          const id = "fld-" + f.name, req = f.required ? "required" : "";
          const label = `<label class="form-label small fw-semibold" for="${id}">${esc(f.label || f.name)}${f.required ? " *" : ""}</label>`;
          let input;
          if (f.type === "select") {
            input = `<select class="form-select" id="${id}" data-name="${esc(f.name)}" ${req}>${(f.options || []).map(o => `<option>${esc(o)}</option>`).join("")}</select>`;
          } else {
            input = `<input class="form-control" id="${id}" data-name="${esc(f.name)}" data-type="${esc(f.type || "text")}"
              type="${f.type === "number" ? "number" : "text"}" value="${esc(f.default != null ? f.default : "")}"
              placeholder="${esc(f.placeholder || "")}" ${req}>`;
          }
          return `<div class="col-12 col-md-6">${label}${input}</div>`;
        }).join("");
      }
      sel.addEventListener("change", drawFields);
      drawFields();

      modal._confirm.onclick = async () => {
        const inputs = {};
        modal._el.querySelectorAll("#f-fields [data-name]").forEach(c => {
          let v = c.value;
          if (c.dataset.type === "number" && v !== "") v = Number(v);
          if (v !== "") inputs[c.dataset.name] = v;
        });
        const err = modal._el.querySelector("#f-err");
        modal._confirm.disabled = true;
        try {
          const r = await NX.api.post("/api/requests", { itemId: sel.value, inputs });
          modal._hide();
          NX.toast(`${r.request.id} submitted (${r.request.status}).`, "success");
          load();
        } catch (e) {
          const d = e.details;
          err.textContent = e.message + (d ? ": " + (Array.isArray(d) ? d.join("; ") : JSON.stringify(d)) : "");
          err.classList.remove("d-none");
        }
        modal._confirm.disabled = false;
      };
      modal._show();
    };

    load();
  }

  async function openRequestModal(id) {
    let res, manifest = "";
    try {
      res = await NX.api.get(`/api/requests/${encodeURIComponent(id)}`);
      try { manifest = (await NX.api.get(`/api/requests/${encodeURIComponent(id)}/manifest`)).manifest || ""; } catch (e) { /* optional */ }
    } catch (e) { return NX.toast(e.message, "danger"); }
    const rr = normReq(res.request), approvals = res.approvals || [];
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
      <div class="small fw-semibold mb-2">Approvals</div>
      ${approvals.length ? approvals.map(a => `<div class="small mb-1">${esc(a.approver || a.approver_name || "")} · ${NX.badge(a.decision)} ${a.reason ? "· " + esc(a.reason) : ""}</div>`).join("")
        : `<div class="small nx-muted">No decisions recorded.</div>`}
      ${manifest ? `<hr class="nx-hr"><div class="small fw-semibold mb-2">Generated manifest</div><pre class="small p-2 border rounded" style="max-height:240px;overflow:auto">${esc(manifest)}</pre>` : ""}`, null);
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
    let logs = [];
    function render() {
      const q = search.value.trim().toLowerCase(), t = toneSel.value;
      const list = logs.filter(a => (!q || ((a.actor || "") + a.action + (a.target || "") + (a.details || "")).toLowerCase().includes(q)) &&
        (!t || (t === "warning" ? a.level === "warn" : t === "info" ? a.level === "info" : false)));
      $("#nx-act-info").textContent = `${list.length} events`;
      tbody.innerHTML = list.length ? list.map(a => `
        <tr><td class="small nx-mono nx-muted">${esc(a.ts)}</td><td>${esc(a.actor || "system")}</td>
          <td class="nx-mono small">${esc(a.action)}</td><td>${esc(a.target || "")}${a.details ? `<div class="small nx-muted">${esc(a.details)}</div>` : ""}</td>
          <td>${NX.badge(a.level === "warn" ? "warning" : "ready", a.level === "warn" ? "Warning" : "Info")}</td>
          <td><span class="nx-id">M01</span></td></tr>`).join("")
        : `<tr><td colspan="6"><div class="nx-empty"><i class="bi bi-clock-history"></i>No events.</div></td></tr>`;
    }
    [search, toneSel].forEach(c => c.addEventListener("input", render));
    NX.api.get("/api/audit?limit=500").then(r => { logs = r.logs || []; render(); })
      .catch(e => { tbody.innerHTML = `<tr><td colspan="6"><div class="nx-empty"><i class="bi bi-exclamation-triangle"></i>${esc(e.message)}</div></td></tr>`; });
    const exp = $("#nx-act-export");
    if (exp) exp.onclick = () => {
      const rows = [["time", "actor", "action", "target", "level", "details"]].concat(logs.map(a => [a.ts, a.actor, a.action, a.target, a.level, a.details]));
      const csv = rows.map(r => r.map(c => '"' + String(c == null ? "" : c).replace(/"/g, '""') + '"').join(",")).join("\n");
      const link = document.createElement("a");
      link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" })); link.download = "fde-nexus-audit.csv"; link.click();
    };
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
    $$("[data-int]").forEach(b => b.onclick = () => NX.toast("Integrations are planned for a later module.", "info"));

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

  let adminUsers = [];
  async function renderUsers() {
    const body = $("#nx-users-body");
    const search = $("#nx-user-search"), roleSel = $("#nx-user-role");
    if (roleSel && !roleSel.dataset.filled) {
      roleSel.innerHTML = `<option value="">All roles</option>` + NX.roles.map(r => `<option value="${r.id}">${esc(r.name)}</option>`).join("");
      roleSel.dataset.filled = "1";
    }
    const me = (NX.session.get() || {}).name;
    function draw() {
      const q = (search.value || "").toLowerCase(), rf = roleSel.value;
      const list = adminUsers.filter(u => (!q || (u.username + u.email + (u.team || "")).toLowerCase().includes(q)) && (!rf || u.role === rf));
      $("#nx-users-info").textContent = `${list.length} of ${adminUsers.length} users`;
      body.innerHTML = list.length ? list.map(u => {
        const self = u.username === me;
        const st = u.status === "approved" ? NX.badge("ready", "Active") : u.status === "pending" ? NX.badge("warning", "Pending approval")
          : NX.badge("rejected", u.status === "disabled" ? "Disabled" : "Rejected");
        const actions = u.status === "pending"
          ? `<button class="btn btn-sm btn-success" data-u-approve="${u.id}">Approve</button> <button class="btn btn-sm btn-outline-danger" data-u-reject="${u.id}">Reject</button>`
          : `<select class="nx-access-sel" data-role-for="${u.id}" ${self ? "disabled" : ""}>${NX.roles.map(r => `<option value="${r.id}" ${r.id === u.role ? "selected" : ""}>${esc(r.name)}</option>`).join("")}</select>
             ${self ? "" : `<button class="btn btn-sm btn-outline-${u.status === "approved" ? "warning" : "success"}" data-u-toggle="${u.id}" data-to="${u.status === "approved" ? "disable" : "enable"}">${u.status === "approved" ? "Disable" : "Enable"}</button>`}`;
        return `<tr>
          <td><div class="d-flex align-items-center gap-2"><span class="nx-avatar" style="width:30px;height:30px;font-size:11px">${esc(u.username.slice(0, 2).toUpperCase())}</span>
            <div><div class="fw-semibold small">${esc(u.username)}${self ? " (you)" : ""}</div><div class="small nx-muted">${esc(u.email)}</div></div></div></td>
          <td>${esc(u.team || "")}</td><td><span class="nx-badge b-primary">${esc((NX.roles.find(r => r.id === u.role) || {}).name || u.role)}</span></td>
          <td>${u.mfa ? NX.badge("pass", "MFA on") : NX.badge("warning", "No MFA")}</td><td>${st}</td>
          <td class="small nx-muted">${esc(u.last_login || "never")}</td><td class="text-end" style="white-space:nowrap">${actions}</td></tr>`;
      }).join("") : `<tr><td colspan="7"><div class="nx-empty"><i class="bi bi-people"></i>No users match.</div></td></tr>`;
      const act = async (fn, msg) => { try { await fn(); NX.toast(msg, "success"); await reload(); } catch (e) { NX.toast(e.message, "danger"); } };
      $$("[data-role-for]").forEach(s => s.onchange = () => act(() => NX.api.post(`/api/users/${s.dataset.roleFor}/role`, { role: s.value }), "Role updated."));
      $$("[data-u-toggle]").forEach(b => b.onclick = () => act(() => NX.api.post(`/api/users/${b.dataset.uToggle}/${b.dataset.to}`), "User updated."));
      $$("[data-u-approve]").forEach(b => b.onclick = () => act(() => NX.api.post(`/api/users/${b.dataset.uApprove}/approve`), "User approved."));
      $$("[data-u-reject]").forEach(b => b.onclick = () => act(() => NX.api.post(`/api/users/${b.dataset.uReject}/reject`), "Signup rejected."));
    }
    async function reload() {
      try { adminUsers = (await NX.api.get("/api/users")).users || []; draw(); renderRolesTab(); }
      catch (e) { body.innerHTML = `<tr><td colspan="7"><div class="nx-empty"><i class="bi bi-exclamation-triangle"></i>${esc(e.message)}</div></td></tr>`; }
    }
    if (!renderUsers.bound) { [search, roleSel].forEach(c => c.addEventListener("input", draw)); renderUsers.bound = true; }
    renderUsers.reload = reload;
    await reload();
  }
  function openAddUser() {
    const modal = buildModal("add-user", "Add user", `
      <p class="nx-muted small">Creates an active account. Share the password through a secure channel; the user can sign in immediately.</p>
      <div class="mb-3"><label class="form-label small fw-semibold">Username</label><input class="form-control" id="au-name" autocomplete="off"></div>
      <div class="mb-3"><label class="form-label small fw-semibold">Email</label><input class="form-control" id="au-email" type="email" autocomplete="off"></div>
      <div class="row g-3">
        <div class="col-6"><label class="form-label small fw-semibold">Initial password (8+ chars)</label><input class="form-control" id="au-pass" type="password" autocomplete="new-password"></div>
        <div class="col-6"><label class="form-label small fw-semibold">Role</label>
          <select class="form-select" id="au-role">${NX.roles.map(r => `<option value="${r.id}" ${r.id === "developer" ? "selected" : ""}>${esc(r.name)}</option>`).join("")}</select></div>
      </div>
      <div class="alert alert-danger py-2 small mt-3 mb-0 d-none" id="au-err"></div>`, "Add user");
    modal._confirm.onclick = async () => {
      try {
        await NX.api.post("/api/users", { username: $("#au-name").value.trim(), email: $("#au-email").value.trim(), password: $("#au-pass").value, role: $("#au-role").value });
        modal._hide(); NX.toast("User created.", "success"); if (renderUsers.reload) renderUsers.reload();
      } catch (e) { const er = $("#au-err"); er.textContent = e.message; er.classList.remove("d-none"); }
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
    // Mirrors the rules the backend enforces (api.py). Read-only.
    const A = "admin", O = "operator", P = "approver", S = "security", D = "developer", V = "viewer";
    const rows = [
      ["Browse catalog, search, view own requests", [A, O, P, S, D, V]],
      ["Submit requests and launch instances", [A, O, P, S, D]],
      ["Start, stop and reboot instances", [A, O, P, S, D]],
      ["Approve or reject other people's requests", [A, O, P, S]],
      ["View all requests", [A, O, P, S]],
      ["Terminate instances", [A, O]],
      ["Connect or remove AWS accounts", [A]],
      ["Manage users and roles", [A]],
      ["Configure catalog (approval, enable)", [A]],
      ["View the full audit log", [A]]
    ];
    host.innerHTML = `<div class="nx-table-wrap"><table class="nx-table nx-matrix"><thead><tr>
      <th>Capability</th>${NX.roles.map(r => `<th class="text-center">${esc(r.name)}</th>`).join("")}</tr></thead><tbody>
      ${rows.map(([cap, roles]) => `<tr><td>${esc(cap)}</td>${NX.roles.map(r => `<td class="text-center">${roles.includes(r.id)
        ? '<i class="bi bi-check-circle-fill text-success"></i>' : '<i class="bi bi-dash text-muted"></i>'}</td>`).join("")}</tr>`).join("")}
      </tbody></table></div><p class="small nx-muted mt-2 mb-0">Read-only view of the rules enforced by the backend. Requesters can never approve their own request.</p>`;
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
      "aws-accounts.html": initAwsAccounts,
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
