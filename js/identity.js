/* M07 Identity & access workspace. */
(function () {
  "use strict";
  const NX = window.NEXUS, UI = NX.ui, esc = NX.esc, $ = UI.$, $$ = UI.$$;
  const S = { tab: "users", ov: null };
  const me = () => NX.session.get() || {};
  const isAdmin = () => (S.ov && S.ov.me && (S.ov.me.base_role || S.ov.me.role) === "admin");
  const isSec = () => isAdmin() || (S.ov && S.ov.me && (S.ov.me.base_role || S.ov.me.role) === "security");
  const ROLES = ["viewer", "developer", "approver", "operator", "security", "admin"];
  const loading = () => '<div class="nx-empty"><i class="bi bi-hourglass-split"></i>Loading…</div>';
  const fail = (e) => `<div class="alert alert-danger small">${esc(UI.errorText(e))}</div>`;
  const tbl = (head, rows, empty) => rows.length ? `<div class="nx-card"><div class="nx-table-wrap"><table class="nx-table"><thead><tr>${head.map(h => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div></div>`
    : `<div class="nx-card"><div class="nx-empty"><i class="bi bi-inbox"></i>${esc(empty)}</div></div>`;
  const yes = (v, t = "yes", f = "no") => v ? `<span class="nx-badge b-success">${t}</span>` : `<span class="nx-badge b-secondary">${f}</span>`;
  const acctSel = (id) => `<select class="form-select" id="${id}" style="max-width:320px">${(NX.awsAccounts || []).map(a => `<option value="${esc(a.id)}" ${a.id === NX.activeAccount.getId() ? "selected" : ""}>${esc(a.alias)} (${esc(a.id)})</option>`).join("")}</select>`;

  async function overview() {
    S.ov = await NX.api.get("/api/m07/overview");
    const o = S.ov, k = (l, v, i, t, sub) => `<div class="col-6 col-xl-2"><div class="nx-card h-100"><div class="nx-card-body nx-kpi"><div class="nx-kpi-icon tone-${t}"><i class="bi ${i}"></i></div>
      <div><div class="nx-kpi-value" style="font-size:20px">${esc(v)}</div><div class="nx-kpi-label">${esc(l)}</div>${sub ? `<div class="small nx-muted">${esc(sub)}</div>` : ""}</div></div></div></div>`;
    const miss = o.mfa_coverage.required_missing;
    $("#id-kpis").innerHTML = k("Active users", o.users, "bi-people", "primary") +
      k("MFA enrolled", `${o.mfa_coverage.enrolled}/${o.users}`, "bi-phone", miss.length ? "warning" : "success", miss.length ? `${miss.length} required missing` : "policy met") +
      k("Active sessions", o.active_sessions, "bi-display", "info") + k("Elevation", `${o.active_jit} active`, "bi-shield-plus", o.pending_jit ? "warning" : "secondary", `${o.pending_jit} pending`) +
      k("Open reviews", o.open_reviews, "bi-clipboard-check", o.open_reviews ? "warning" : "secondary") + k("Service tokens", o.service_tokens, "bi-key", "secondary", o.sso.enabled ? "SSO on" : "SSO off");
    $("#id-jit-n").textContent = o.pending_jit || "";
    const m = o.me;
    const banner = [];
    if (m.jit) banner.push(`<div class="alert alert-warning py-2 small"><i class="bi bi-shield-plus me-1"></i>You are temporarily <b>${esc(m.jit.role)}</b> (normally ${esc(m.base_role)}) until ${esc(m.jit.expires_at)} UTC.</div>`);
    if (m.mfa_required && !m.mfa_enabled) banner.push(`<div class="alert alert-danger py-2 small"><i class="bi bi-phone me-1"></i>Your role requires MFA. <a href="settings.html#security">Set it up in Settings</a>.</div>`);
    $("#id-kpis").insertAdjacentHTML("afterend", `<div id="id-banner">${banner.join("")}</div>`);
    const old = document.querySelectorAll("#id-banner"); if (old.length > 1) old[0].remove();
    $$("#id-tabs [data-tab]").forEach(b => { const t = b.dataset.tab; if (["reviews", "tokens", "sso", "rules"].includes(t) && !isSec()) b.parentElement.classList.add("d-none"); });
  }

  /* ---------------- users ---------------- */
  async function drawUsers() {
    if (!isSec()) { $("#id-pane").innerHTML = '<div class="nx-card"><div class="nx-card-body small">Your own sign-in methods and sessions are under <a href="settings.html#security">Settings</a>. Ask for more access with <b>Request elevated access</b>.</div></div>'; return; }
    const r = await NX.api.get("/api/m07/users"), req = new Set(r.mfa_required_roles);
    $("#id-pane").innerHTML = tbl(["User", "Role", "Status", "Sign-in", "MFA", "Sessions", "Access expires", "Last login", ""], r.users.map(u => `<tr>
      <td><div class="fw-semibold small">${esc(u.username)}</div><div class="small nx-muted">${esc(u.email)} · ${esc(u.team || "")}</div></td>
      <td><span class="nx-badge b-primary">${esc(u.role)}</span>${u.jit ? `<div class="small text-warning">temp ${esc(u.jit.role_to)} until ${esc(u.jit.expires_at)}</div>` : ""}</td>
      <td>${u.status === "approved" ? '<span class="nx-badge b-success">active</span>' : `<span class="nx-badge b-secondary">${esc(u.status)}</span>`}</td>
      <td class="small">${u.sources.map(esc).join(", ")}</td>
      <td>${u.mfa_enabled ? '<span class="nx-badge b-success">on</span>' : req.has(u.role) ? '<span class="nx-badge b-danger">required, off</span>' : '<span class="nx-badge b-secondary">off</span>'}</td>
      <td>${u.active_sessions}</td><td class="small">${u.expires_at ? `${esc(u.expires_at.slice(0, 10))}<div class="nx-muted">${esc(u.expiry_reason || "")}</div>` : '<span class="nx-muted">never</span>'}</td>
      <td class="small nx-muted">${esc(u.last_login || "never")}</td>
      <td class="text-end" style="white-space:nowrap">${isAdmin() && u.username !== me().name ? `
        <button class="btn btn-sm btn-outline-secondary" data-exp="${u.id}" data-cur="${esc((u.expires_at || "").slice(0, 10))}" title="Set access expiry"><i class="bi bi-calendar-x"></i></button>
        ${u.mfa_enabled ? `<button class="btn btn-sm btn-outline-warning" data-mfareset="${u.id}" title="Reset MFA (lost phone)"><i class="bi bi-phone-flip"></i></button>` : ""}` : ""}
        ${u.active_sessions ? `<button class="btn btn-sm btn-outline-danger" data-kill="${u.id}" title="Sign out everywhere"><i class="bi bi-box-arrow-right"></i></button>` : ""}</td></tr>`), "No users.") +
      `<div class="small nx-muted mt-2">Create, approve, disable users and change base roles in the <a href="admin.html">Admin panel</a>. Users from SSO or SCIM show their source.</div>`;
    $$("[data-exp]").forEach(b => b.onclick = async () => {
      const v = prompt("Access expires on (YYYY-MM-DD). Empty = never expires:", b.dataset.cur || "");
      if (v === null) return;
      const reason = v ? prompt("Reason (e.g. contractor end date):", "") : "";
      try { await NX.api.call("PUT", `/api/m07/users/${b.dataset.exp}/expiry`, { expires_at: v.trim(), reason }); NX.toast("Saved.", "success"); drawUsers(); }
      catch (e) { NX.toast(UI.errorText(e), "danger"); }
    });
    $$("[data-mfareset]").forEach(b => b.onclick = async () => {
      if (!confirm("Remove this user's MFA device? They must enroll again at next sign-in.")) return;
      try { await NX.api.post(`/api/m07/users/${b.dataset.mfareset}/mfa/reset`); NX.toast("MFA reset.", "success"); drawUsers(); } catch (e) { NX.toast(UI.errorText(e), "danger"); }
    });
    $$("[data-kill]").forEach(b => b.onclick = async () => {
      if (!confirm("Sign this user out of every session?")) return;
      try { await NX.api.post("/api/m07/sessions/revoke", { user_id: +b.dataset.kill }); NX.toast("Signed out.", "success"); drawUsers(); } catch (e) { NX.toast(UI.errorText(e), "danger"); }
    });
  }

  /* ---------------- just-in-time elevation ---------------- */
  async function drawJit() {
    const r = await NX.api.get("/api/m07/jit");
    const tone = { pending: "warning", active: "danger", expired: "secondary", revoked: "secondary", rejected: "secondary" };
    $("#id-pane").innerHTML = `<div class="small nx-muted mb-2">Temporary roles end automatically. Admins approve; nobody approves their own request.</div>` +
      tbl(["Request", "User", "From → to", "Duration", "Reason", "Status", "Approver", ""], r.requests.map(j => `<tr>
        <td class="nx-mono small">${esc(j.id)}<div class="nx-muted">${esc(j.requested_at)}</div></td><td>${esc(j.username)}</td>
        <td class="small">${esc(j.role_from)} → <b>${esc(j.role_to)}</b></td><td class="small">${j.hours} h${j.expires_at ? `<div class="nx-muted">until ${esc(j.expires_at)}</div>` : ""}</td>
        <td class="small" style="max-width:280px">${esc(j.reason)}</td><td><span class="nx-badge b-${tone[j.status] || "secondary"}">${esc(j.status)}</span></td><td class="small">${esc(j.approver || "")}</td>
        <td class="text-end" style="white-space:nowrap">
          ${j.status === "pending" && isAdmin() && j.username !== me().name ? `<button class="btn btn-sm btn-success" data-jit="${esc(j.id)}/approve">Approve</button> <button class="btn btn-sm btn-outline-danger" data-jit="${esc(j.id)}/reject">Reject</button>` : ""}
          ${["pending", "active"].includes(j.status) && (j.username === me().name || isSec()) ? `<button class="btn btn-sm btn-outline-secondary" data-jit="${esc(j.id)}/revoke">${j.status === "active" ? "End now" : "Cancel"}</button>` : ""}</td></tr>`), "No elevation requests.");
    $$("[data-jit]").forEach(b => b.onclick = async () => {
      const [id, act] = b.dataset.jit.split("/");
      try { await NX.api.post(`/api/m07/jit/${id}/${act}`); NX.toast(`${id}: ${act} done.`, "success"); await overview(); drawJit(); } catch (e) { NX.toast(UI.errorText(e), "danger"); }
    });
  }
  function openElevate() {
    const cur = (S.ov && (S.ov.me.base_role || S.ov.me.role)) || me().role;
    const rank = { viewer: 1, developer: 2, approver: 3, operator: 3, security: 3, admin: 9 };
    const opts = ROLES.filter(r => rank[r] > rank[cur]);
    if (!opts.length) return NX.toast("You already have the highest role.", "info");
    const m = UI.modal("Request elevated access", `<p class="small nx-muted">Temporary, approved by an administrator, ends automatically, and every action is recorded.</p>
      <div class="row g-3"><div class="col-md-6"><label class="form-label small fw-semibold">Role</label><select class="form-select" id="je-role">${opts.map(r => `<option>${r}</option>`).join("")}</select></div>
      <div class="col-md-6"><label class="form-label small fw-semibold">For</label><select class="form-select" id="je-h">${[0.5, 1, 2, 4, 8].map(h => `<option value="${h}" ${h === 1 ? "selected" : ""}>${h < 1 ? "30 minutes" : h + " hour" + (h > 1 ? "s" : "")}</option>`).join("")}</select></div>
      <div class="col-12"><label class="form-label small fw-semibold">Reason</label><input class="form-control" id="je-r" placeholder="INC-1234: restart payments deployment in production"></div></div>
      <div class="alert alert-danger py-2 small mt-3 d-none" id="je-err"></div>`, { footer: '<button class="btn btn-primary" id="je-go">Request</button>' });
    $("#je-go", m.el).onclick = async () => {
      try { await NX.api.post("/api/m07/jit", { role: $("#je-role", m.el).value, hours: +$("#je-h", m.el).value, reason: $("#je-r", m.el).value });
        m.hide(); NX.toast("Request sent to administrators.", "success"); await overview(); setTab("jit"); }
      catch (e) { const x = $("#je-err", m.el); x.textContent = UI.errorText(e); x.classList.remove("d-none"); }
    };
  }

  /* ---------------- access reviews ---------------- */
  async function drawReviews() {
    const r = await NX.api.get("/api/m07/reviews");
    $("#id-pane").innerHTML = `<div class="d-flex justify-content-end mb-2"><button class="btn btn-sm btn-primary" id="rv-new"><i class="bi bi-plus-lg me-1"></i>Start a review</button></div>` +
      tbl(["Review", "Scope", "Progress", "Revoke", "Due", "Status", ""], r.reviews.map(v => `<tr><td class="fw-semibold small">${esc(v.name)}<div class="nx-mono nx-muted">${esc(v.id)}</div></td>
        <td>${esc(v.scope)}</td><td>${v.decided}/${v.total}</td><td>${v.revoke}</td><td class="small">${esc((v.due_at || "").slice(0, 10))}</td>
        <td><span class="nx-badge b-${v.status === "open" ? "warning" : "secondary"}">${esc(v.status)}</span></td>
        <td class="text-end"><button class="btn btn-sm btn-outline-primary" data-rv="${esc(v.id)}">${v.status === "open" ? "Review" : "View"}</button></td></tr>`), "No access reviews yet.");
    $("#rv-new").onclick = async () => {
      const scope = prompt("Scope: all, privileged (approver/operator/security/admin), or a role name:", "privileged");
      if (!scope) return;
      try { const x = await NX.api.post("/api/m07/reviews", { scope: scope.trim(), due_days: 14 }); openReview(x.review); } catch (e) { NX.toast(UI.errorText(e), "danger"); }
    };
    $$("[data-rv]").forEach(b => b.onclick = () => openReview(b.dataset.rv));
  }
  async function openReview(id) {
    const r = await NX.api.get(`/api/m07/reviews/${id}`), open = r.review.status === "open";
    const m = UI.modal(`${r.review.name} (${id})`, `<p class="small nx-muted">Certify each person still needs their access. Revoked users are disabled and signed out when the review closes.</p>` +
      `<table class="nx-table"><thead><tr><th>User</th><th>Role</th><th>Team</th><th>Last login</th><th>Decision</th></tr></thead><tbody>${r.items.map(i => `<tr>
        <td class="small"><b>${esc(i.username)}</b><div class="nx-muted">${esc(i.email)}</div></td><td>${esc(i.role)}</td><td class="small">${esc(i.team || "")}</td><td class="small">${esc(i.last_login || "never")}</td>
        <td>${open && i.username !== me().name ? `<div class="btn-group btn-group-sm"><input type="radio" class="btn-check" name="d${i.user_id}" id="k${i.user_id}" ${i.decision === "keep" ? "checked" : ""} data-dec="${i.user_id}/keep"><label class="btn btn-outline-success" for="k${i.user_id}">Keep</label>
          <input type="radio" class="btn-check" name="d${i.user_id}" id="r${i.user_id}" ${i.decision === "revoke" ? "checked" : ""} data-dec="${i.user_id}/revoke"><label class="btn btn-outline-danger" for="r${i.user_id}">Revoke</label></div>`
          : i.decision ? `<span class="nx-badge b-${i.decision === "keep" ? "success" : "danger"}">${esc(i.decision)}</span> <span class="small nx-muted">${esc(i.decided_by || "")}</span>` : '<span class="small nx-muted">another reviewer</span>'}</td></tr>`).join("")}</tbody></table>`,
      { size: "modal-xl", footer: open ? '<button class="btn btn-danger" id="rv-close">Close review and apply</button>' : "" });
    $$("[data-dec]", m.el).forEach(i => i.onchange = async () => { const [uid, dec] = i.dataset.dec.split("/");
      try { await NX.api.post(`/api/m07/reviews/${id}/decide`, { user_id: +uid, decision: dec }); } catch (e) { NX.toast(UI.errorText(e), "danger"); } });
    const c = $("#rv-close", m.el);
    if (c) c.onclick = async () => {
      try { const x = await NX.api.post(`/api/m07/reviews/${id}/close`, {}); m.hide(); NX.toast(`Closed. Revoked: ${x.revoked.join(", ") || "none"}.`, "success"); drawReviews(); }
      catch (e) { if (/still need/.test(e.message) && confirm(e.message + " Close anyway (undecided users keep access)?")) { const x = await NX.api.post(`/api/m07/reviews/${id}/close`, { force: true }); m.hide(); NX.toast(`Closed. Revoked: ${x.revoked.join(", ") || "none"}.`, "success"); drawReviews(); } else NX.toast(UI.errorText(e), "danger"); }
    };
  }

  /* ---------------- sessions ---------------- */
  async function drawSessions() {
    const r = await NX.api.get("/api/m07/sessions" + (isSec() ? "?all=1" : ""));
    $("#id-pane").innerHTML = tbl(["User", "Method", "Started", "Last activity", "From", "Status", ""], r.sessions.map(s => `<tr>
      <td>${esc(s.username)}${s.current ? ' <span class="nx-badge b-primary">this session</span>' : ""}${s.elevated ? ' <span class="nx-badge b-warning">elevated</span>' : ""}</td>
      <td><span class="nx-badge b-${s.method === "mfa" || s.method === "sso" ? "success" : "secondary"}">${esc(s.method)}</span></td>
      <td class="small">${esc(s.created_at)}</td><td class="small">${esc(s.last_seen || "")}</td>
      <td class="small"><span class="nx-mono">${esc(s.ip || "")}</span><div class="nx-muted text-truncate" style="max-width:240px">${esc(s.user_agent || "")}</div></td>
      <td>${s.active ? '<span class="nx-badge b-success">active</span>' : `<span class="nx-badge b-secondary">${s.revoked_at ? "signed out" : "expired"}</span>${s.revoked_by ? `<div class="small nx-muted">${esc(s.revoked_by)}</div>` : ""}`}</td>
      <td class="text-end">${s.active && !s.current ? `<button class="btn btn-sm btn-outline-danger" data-sess="${esc(s.id)}">Sign out</button>` : ""}</td></tr>`), "No sessions.");
    $$("[data-sess]").forEach(b => b.onclick = async () => { try { await NX.api.post("/api/m07/sessions/revoke", { id: b.dataset.sess }); drawSessions(); } catch (e) { NX.toast(UI.errorText(e), "danger"); } });
  }

  /* ---------------- service identities ---------------- */
  async function drawTokens() {
    const r = await NX.api.get("/api/m07/tokens");
    $("#id-pane").innerHTML = `<div class="d-flex justify-content-between align-items-center mb-2"><div class="small nx-muted">API tokens for automation (CI pipelines, scripts). Never admin, always expire, stored only as a hash. Use as <span class="nx-mono">Authorization: Bearer fdx_…</span>.</div>
      <button class="btn btn-sm btn-primary" id="tk-new"><i class="bi bi-plus-lg me-1"></i>New token</button></div>` +
      tbl(["Name", "Role", "Prefix", "Created", "Expires", "Last used", "Status", ""], r.tokens.map(t => `<tr><td class="fw-semibold small">${esc(t.name)}</td><td>${esc(t.role)}</td>
        <td class="nx-mono small">${esc(t.prefix)}…</td><td class="small">${esc(t.created_at)}<div class="nx-muted">${esc(t.created_by)}</div></td><td class="small">${esc(t.expires_at || "")}</td>
        <td class="small">${esc(t.last_used || "never")}</td><td>${t.revoked_at ? '<span class="nx-badge b-secondary">revoked</span>' : '<span class="nx-badge b-success">active</span>'}</td>
        <td class="text-end">${t.revoked_at ? "" : `<button class="btn btn-sm btn-outline-danger" data-tkr="${esc(t.id)}">Revoke</button>`}</td></tr>`), "No service tokens.");
    $("#tk-new").onclick = () => {
      const m = UI.modal("New service token", `<div class="row g-3"><div class="col-md-5"><label class="form-label small fw-semibold">Name</label><input class="form-control" id="tk-n" placeholder="gitlab-ci"></div>
        <div class="col-md-4"><label class="form-label small fw-semibold">Role</label><select class="form-select" id="tk-r"><option>viewer</option><option selected>developer</option><option>operator</option></select></div>
        <div class="col-md-3"><label class="form-label small fw-semibold">Days</label><input class="form-control" type="number" id="tk-d" value="90" min="1" max="365"></div></div><div id="tk-out" class="mt-3"></div>`,
        { footer: '<button class="btn btn-primary" id="tk-go">Create</button>' });
      $("#tk-go", m.el).onclick = async () => {
        try { const x = await NX.api.post("/api/m07/tokens", { name: $("#tk-n", m.el).value.trim(), role: $("#tk-r", m.el).value, days: +$("#tk-d", m.el).value });
          $("#tk-out", m.el).innerHTML = `<div class="alert alert-warning small mb-0"><b>Copy this token now.</b> It is not shown again.<pre class="nx-log mt-2 mb-0">${esc(x.token)}</pre></div>`; $("#tk-go", m.el).remove(); drawTokens(); }
        catch (e) { $("#tk-out", m.el).innerHTML = fail(e); }
      };
    };
    $$("[data-tkr]").forEach(b => b.onclick = async () => { if (!confirm("Revoke this token? Anything using it stops working.")) return; await NX.api.post(`/api/m07/tokens/${b.dataset.tkr}/revoke`); drawTokens(); });
  }

  /* ---------------- AWS IAM roles ---------------- */
  async function drawAws() {
    if (!(NX.awsAccounts || []).length) await NX.loadAccounts();
    $("#id-pane").innerHTML = `<div class="d-flex gap-2 mb-2 align-items-center">${acctSel("aw-acct")}<input class="form-control" id="aw-q" placeholder="Filter roles…" style="max-width:260px">
      <select class="form-select" id="aw-f" style="max-width:220px"><option value="">All roles</option><option value="flag">Only roles with findings</option><option value="unused">Unused or never used</option><option value="cross">Cross-account trust</option></select>
      <span class="small nx-muted ms-auto" id="aw-n"></span></div><div id="aw-body">${loading()}</div>`;
    let roles = [];
    const draw = () => {
      const q = $("#aw-q").value.toLowerCase(), f = $("#aw-f").value;
      const list = roles.filter(r => (!q || (r.name + r.principals.join(" ")).toLowerCase().includes(q)) && (!f || (f === "flag" ? r.flags.length : f === "unused" ? r.flags.some(x => /unused|never/.test(x)) : r.flags.some(x => /cross-account|anyone/.test(x)))));
      $("#aw-n").textContent = `${list.length} of ${roles.length} roles`;
      $("#aw-body").innerHTML = tbl(["Role", "Type", "Trusted by", "Last used", "Findings", ""], list.slice(0, 500).map((r, i) => `<tr>
        <td class="small fw-semibold">${esc(r.name)}<div class="nx-muted">${esc(r.path || "")}</div></td><td><span class="nx-badge b-secondary">${esc(r.kind)}</span></td>
        <td class="small nx-mono" style="max-width:320px">${r.principals.map(esc).join("<br>")}</td><td class="small">${esc(r.last_used ? r.last_used.slice(0, 10) : "never")}</td>
        <td>${r.flags.map(x => `<span class="nx-badge b-${/anyone|without external/.test(x) ? "danger" : "warning"} me-1">${esc(x)}</span>`).join("")}</td>
        <td class="text-end"><button class="btn btn-sm btn-outline-secondary" data-awr="${esc(r.name)}">Policies</button></td></tr>`), "No IAM roles in the cache. Sync IAM roles on the Account data page.");
      $$("[data-awr]").forEach(b => b.onclick = async () => {
        const m = UI.modal(`IAM role ${b.dataset.awr}`, loading(), { size: "modal-lg" });
        try { const x = await NX.api.get(`/api/m07/iam/roles/${encodeURIComponent(b.dataset.awr)}?account=${encodeURIComponent($("#aw-acct").value)}`);
          $(".modal-body", m.el).innerHTML = `${x.privileged.length ? `<div class="alert alert-danger py-2 small">Broad permissions: ${x.privileged.map(esc).join(", ")}</div>` : ""}
            <h6 class="fw-bold">Attached policies</h6>${x.attached.map(p => `<div class="small nx-mono">${esc(p.PolicyArn)}</div>`).join("") || '<div class="small nx-muted">None</div>'}
            <h6 class="fw-bold mt-3">Inline policies</h6>${x.inline.map(p => `<div class="small nx-mono">${esc(p)}</div>`).join("") || '<div class="small nx-muted">None</div>'}
            <div class="small nx-muted mt-3">Read live from IAM. Change roles through Terraform (IaC Changes), not by hand.</div>`; }
        catch (e) { $(".modal-body", m.el).innerHTML = fail(e); }
      });
    };
    const load = async () => { $("#aw-body").innerHTML = loading(); try { roles = (await NX.api.get(`/api/m07/iam/roles?account=${encodeURIComponent($("#aw-acct").value)}`)).roles; draw(); } catch (e) { $("#aw-body").innerHTML = fail(e); } };
    $("#aw-acct").onchange = load; $("#aw-q").oninput = draw; $("#aw-f").onchange = draw; load();
  }

  async function drawWorkload() {
    if (!(NX.awsAccounts || []).length) await NX.loadAccounts();
    $("#id-pane").innerHTML = `<div class="d-flex gap-2 mb-2">${acctSel("wl-acct")}<button class="btn btn-outline-primary" id="wl-go">Read clusters</button></div><div id="wl-body"><div class="small nx-muted">Reads EKS Pod Identity associations and OIDC (IRSA) issuers live for every EKS cluster in the account data cache.</div></div>`;
    $("#wl-go").onclick = async () => {
      $("#wl-body").innerHTML = loading();
      try {
        const r = await NX.api.get(`/api/m07/workload?account=${encodeURIComponent($("#wl-acct").value)}`);
        $("#wl-body").innerHTML = r.clusters.map(c => `<div class="nx-card mb-2"><div class="nx-card-body"><div class="d-flex justify-content-between"><span class="fw-semibold">${esc(c.cluster)}</span><span class="small nx-muted">${esc(c.region)} · ${esc(c.access_mode || "")}</span></div>
          ${c.error ? `<div class="small text-danger">${esc(c.error)}</div>` : `<div class="small nx-muted mb-1">IRSA issuer: <span class="nx-mono">${esc(c.oidc_issuer || "none")}</span></div>
          ${c.pod_identity.length ? `<table class="nx-table"><thead><tr><th>Namespace</th><th>Service account</th><th>IAM role</th></tr></thead><tbody>${c.pod_identity.map(p => `<tr><td>${esc(p.namespace)}</td><td class="nx-mono small">${esc(p.service_account)}</td><td class="nx-mono small">${esc(p.role)}</td></tr>`).join("")}</tbody></table>` : '<div class="small nx-muted">No Pod Identity associations.</div>'}`}</div></div>`).join("") +
          `<div class="nx-card"><div class="nx-card-body"><div class="fw-semibold small mb-1">IAM roles trusted by an EKS OIDC provider (IRSA): ${r.irsa_roles.length}</div><div class="small nx-mono">${r.irsa_roles.slice(0, 60).map(esc).join(", ")}</div></div></div>`;
      } catch (e) { $("#wl-body").innerHTML = fail(e); }
    };
  }

  /* ---------------- SSO & SCIM ---------------- */
  async function drawSso() {
    const o = S.ov.sso;
    $("#id-pane").innerHTML = `<div class="row g-3"><div class="col-xl-7"><div class="nx-card"><div class="nx-card-body">
      <h2 class="h6 fw-bold">Single sign-on (OpenID Connect)</h2><p class="small nx-muted">Works with Okta, Microsoft Entra ID, Google, Keycloak, Auth0 and AWS IAM Identity Center apps. Authorization code flow with PKCE; the ID token signature, audience, issuer and nonce are verified.</p>
      <div class="row g-2">
        <div class="col-md-8"><label class="form-label small fw-semibold">Issuer URL</label><input class="form-control" id="ss-iss" value="${esc(o.issuer)}" placeholder="https://yourorg.okta.com"></div>
        <div class="col-md-4"><label class="form-label small fw-semibold">Button label</label><input class="form-control" id="ss-lbl" value="${esc(o.label)}"></div>
        <div class="col-md-6"><label class="form-label small fw-semibold">Client ID</label><input class="form-control" id="ss-cid" value="${esc(o.client_id)}"></div>
        <div class="col-md-6"><label class="form-label small fw-semibold">Redirect URI (register this in the IdP)</label><input class="form-control nx-mono" id="ss-red" value="${esc(o.redirect_uri || location.origin + "/api/m07/sso/callback")}"></div>
        <div class="col-md-6"><label class="form-label small fw-semibold">Groups claim</label><input class="form-control" id="ss-gc" value="${esc(o.groups_claim)}"></div>
        <div class="col-md-6"><label class="form-label small fw-semibold">Default role</label><select class="form-select" id="ss-dr">${ROLES.filter(r => r !== "admin").map(r => `<option ${r === o.default_role ? "selected" : ""}>${r}</option>`).join("")}</select></div>
        <div class="col-12"><label class="form-label small fw-semibold">Group → role mapping (one per line: group = role)</label><textarea class="form-control nx-mono" rows="4" id="ss-map">${esc(Object.entries(o.role_map).map(([g, r]) => `${g} = ${r}`).join("\n"))}</textarea></div>
        <div class="col-md-6"><div class="form-check form-switch"><input class="form-check-input" type="checkbox" id="ss-ap" ${o.auto_provision ? "checked" : ""}><label class="form-check-label small" for="ss-ap">Create portal accounts on first SSO sign-in</label></div></div>
        <div class="col-md-6"><div class="form-check form-switch"><input class="form-check-input" type="checkbox" id="ss-en" ${o.enabled ? "checked" : ""}><label class="form-check-label small" for="ss-en">Show the SSO button on the login page</label></div></div>
        <div class="col-12 small">Client secret: ${o.secret_present ? '<span class="nx-badge b-success">M07_OIDC_CLIENT_SECRET set</span>' : '<span class="nx-badge b-warning">not set (public PKCE clients do not need one)</span>'} <span class="nx-muted">Set it on the host before starting the portal; it is never stored.</span></div>
      </div>${isAdmin() ? '<button class="btn btn-primary mt-3" id="ss-save">Save</button>' : ""}<div id="ss-out" class="mt-2"></div></div></div></div>
      <div class="col-xl-5"><div class="nx-card"><div class="nx-card-body"><h2 class="h6 fw-bold">SCIM 2.0 provisioning</h2>
        <p class="small nx-muted">Let your IdP create and deactivate portal users automatically. Deactivation signs the user out everywhere. Administrator accounts are never changed by SCIM.</p>
        <div class="small">Base URL: <span class="nx-mono">${esc(location.origin)}/scim/v2</span></div>
        ${isAdmin() ? '<button class="btn btn-outline-primary mt-3" id="sc-tok">Generate SCIM token</button>' : ""}<div id="sc-out" class="mt-2"></div>
        <hr class="nx-hr"><h2 class="h6 fw-bold">SAML 2.0</h2><div class="small nx-muted">Not supported. Use the IdP's OIDC app type (all major IdPs offer it).</div></div></div></div></div>`;
    const sv = $("#ss-save");
    if (sv) sv.onclick = async () => {
      const map = {};
      $("#ss-map").value.split("\n").map(l => l.trim()).filter(Boolean).forEach(l => { const [g, r] = l.split("=").map(x => x.trim()); if (g && r) map[g] = r; });
      try { await NX.api.call("PUT", "/api/m07/sso", { enabled: $("#ss-en").checked, label: $("#ss-lbl").value, issuer: $("#ss-iss").value, client_id: $("#ss-cid").value,
          redirect_uri: $("#ss-red").value, groups_claim: $("#ss-gc").value, default_role: $("#ss-dr").value, role_map: map, auto_provision: $("#ss-ap").checked });
        $("#ss-out").innerHTML = '<div class="alert alert-success py-2 small mb-0">Saved. The IdP discovery document was read successfully.</div>'; await overview(); }
      catch (e) { $("#ss-out").innerHTML = fail(e); }
    };
    const st = $("#sc-tok");
    if (st) st.onclick = async () => {
      if (!confirm("Generate a new SCIM token? The previous one stops working.")) return;
      try { const x = await NX.api.post("/api/m07/scim/token"); $("#sc-out").innerHTML = `<div class="alert alert-warning small mb-0"><b>Copy now, shown once:</b><pre class="nx-log mt-2 mb-0">${esc(x.token)}</pre></div>`; }
      catch (e) { $("#sc-out").innerHTML = fail(e); }
    };
  }

  /* ---------------- policies ---------------- */
  async function drawRules() {
    const s = S.ov.settings, adm = isAdmin() ? "" : "disabled";
    $("#id-pane").innerHTML = `<div class="row g-3"><div class="col-xl-6"><div class="nx-card"><div class="nx-card-body">
      <h2 class="h6 fw-bold">Sign-in policy</h2>
      <label class="form-label small fw-semibold">Roles that must use MFA</label><div class="d-flex flex-wrap gap-1 mb-3">${ROLES.map(r => `<input type="checkbox" class="btn-check" id="mr-${r}" value="${r}" ${s.mfa_required_roles.includes(r) ? "checked" : ""} ${adm}><label class="btn btn-sm btn-outline-primary" for="mr-${r}">${r}</label>`).join("")}</div>
      <label class="form-label small fw-semibold">Sign out after inactivity (minutes, 0 = never)</label><input class="form-control mb-3" type="number" id="pl-idle" value="${s.session_idle_minutes}" min="0" max="1440" ${adm}>
      <label class="form-label small fw-semibold">Longest elevation (hours)</label><input class="form-control" type="number" id="pl-jit" value="${s.max_jit_hours}" min="1" max="24" ${adm}>
    </div></div></div><div class="col-xl-6"><div class="nx-card"><div class="nx-card-body">
      <h2 class="h6 fw-bold">Attribute rules (ABAC)</h2>
      <div class="form-check form-switch mb-2"><input class="form-check-input" type="checkbox" id="ab-team" ${s.abac_team_scope ? "checked" : ""} ${adm}><label class="form-check-label small" for="ab-team"><b>Team ownership:</b> developers and viewers change only environments owned by their team (user.team = environment.team)</label></div>
      <div class="form-check form-switch"><input class="form-check-input" type="checkbox" id="ab-mfa" ${s.abac_prod_requires_mfa ? "checked" : ""} ${adm}><label class="form-check-label small" for="ab-mfa"><b>Strong sign-in for production:</b> production changes need a session signed in with MFA or SSO</label></div>
      <div class="small nx-muted mt-2">Rules are enforced by the backend for every infrastructure request, on top of roles. Admins are exempt.</div>
    </div></div></div></div>${isAdmin() ? '<button class="btn btn-primary mt-3" id="pl-save">Save policies</button>' : ""}`;
    const b = $("#pl-save");
    if (b) b.onclick = async () => {
      try { await NX.api.call("PUT", "/api/m07/settings", { mfa_required_roles: $$("[id^=mr-]:checked").map(i => i.value), session_idle_minutes: +$("#pl-idle").value,
          max_jit_hours: +$("#pl-jit").value, abac_team_scope: $("#ab-team").checked, abac_prod_requires_mfa: $("#ab-mfa").checked });
        NX.toast("Policies saved.", "success"); await overview(); }
      catch (e) { NX.toast(UI.errorText(e), "danger"); }
    };
  }

  const TABS = { users: drawUsers, jit: drawJit, reviews: drawReviews, sessions: drawSessions, tokens: drawTokens, aws: drawAws, workload: drawWorkload, sso: drawSso, rules: drawRules };
  async function setTab(t) {
    S.tab = t; $$("#id-tabs [data-tab]").forEach(b => b.classList.toggle("active", b.dataset.tab === t));
    $("#id-pane").innerHTML = loading();
    try { await TABS[t](); } catch (e) { $("#id-pane").innerHTML = fail(e); }
  }
  async function init() {
    if (!$("#id-pane")) return;
    try { await overview(); } catch (e) { $("#id-pane").innerHTML = fail(e); return; }
    $$("#id-tabs [data-tab]").forEach(b => b.onclick = () => setTab(b.dataset.tab));
    $("#id-elevate").onclick = openElevate;
    setTab(location.hash.slice(1) in TABS ? location.hash.slice(1) : "users");
  }
  document.addEventListener("DOMContentLoaded", () => setTimeout(init, 0));
})();
