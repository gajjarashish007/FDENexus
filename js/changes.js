/* M03 workspace: changes (review/approve/merge), stacks, module registry, policies, GitLab settings. */
(function () {
  "use strict";
  const NX = window.NEXUS, UI = NX.ui, esc = NX.esc, $ = UI.$, $$ = UI.$$;
  const S = { changes: [], settings: null };
  const me = () => NX.session.get() || {};
  const isApprover = () => ["admin", "operator", "approver", "security"].includes(me().role);
  const isOperator = () => ["admin", "operator"].includes(me().role);

  function tab(name) {
    $$("#ch-tabs [data-tab]").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
    $$("[data-pane]").forEach(p => p.classList.toggle("d-none", p.dataset.pane !== name));
    ({ changes: loadChanges, stacks: loadStacks, registry: loadRegistry, policies: loadPolicies, settings: loadSettings })[name]();
  }

  /* ---------------- changes ---------------- */
  async function loadChanges() {
    try { S.changes = (await NX.api.get("/api/m03/changes")).changes; } catch (e) { $("#ch-body").innerHTML = `<tr><td colspan="8">${esc(e.message)}</td></tr>`; return; }
    $("#ch-pending").textContent = S.changes.filter(c => c.status === "pending_approval").length;
    renderChanges();
  }
  function renderChanges() {
    const q = $("#ch-search").value.trim().toLowerCase(), st = $("#ch-status").value;
    const list = S.changes.filter(c => (!q || (c.id + c.title + c.env + c.requester).toLowerCase().includes(q)) && (!st || c.status === st));
    $("#ch-body").innerHTML = list.length ? list.map(c => `<tr>
      <td><a href="#" class="nx-id" data-open="${esc(c.id)}">${esc(c.id)}</a><div class="small">${esc(c.title)}</div></td>
      <td class="nx-mono small">${esc(c.env)}</td><td class="small">${esc(c.action)}</td><td>${UI.riskBadge(c.risk)}</td>
      <td class="small">${c.monthly == null ? "" : UI.money(c.monthly)}</td>
      <td>${UI.changeBadge(c.status)}${c.mr && c.mr.web_url ? `<div><a class="small" href="${esc(c.mr.web_url)}" target="_blank" rel="noopener">!${esc(c.mr.iid)}</a></div>` : ""}</td>
      <td class="small nx-muted">${esc(c.requester)}<br>${esc(c.created_at)}</td>
      <td class="text-end"><button class="btn btn-sm btn-outline-primary" data-open="${esc(c.id)}">Review</button></td></tr>`).join("")
      : `<tr><td colspan="8"><div class="nx-empty"><i class="bi bi-file-diff"></i>No changes yet. Launch a resource or create an environment.</div></td></tr>`;
    $$("[data-open]").forEach(b => b.onclick = (e) => { e.preventDefault(); openChange(b.dataset.open); });
  }

  async function openChange(id) {
    let c;
    try { c = (await NX.api.get("/api/m03/changes/" + encodeURIComponent(id))).change; } catch (e) { return NX.toast(e.message, "danger"); }
    const mine = c.requester === me().name;
    const actions = [];
    if (c.status === "pending_approval" && isApprover() && !mine) {
      actions.push('<button class="btn btn-success" data-act="approve"><i class="bi bi-check-lg me-1"></i>Approve</button>');
      actions.push('<button class="btn btn-outline-danger" data-act="reject">Reject</button>');
    }
    if (["pending_approval", "blocked", "queued"].includes(c.status) && (mine || NX.session.isAdmin())) actions.push('<button class="btn btn-outline-secondary" data-act="cancel">Cancel change</button>');
    if (["mr_open", "merged"].includes(c.status)) actions.push('<button class="btn btn-outline-primary" data-act="refresh"><i class="bi bi-arrow-clockwise me-1"></i>Refresh from GitLab</button>');
    if (c.status === "mr_open" && isApprover()) actions.push('<button class="btn btn-primary" data-act="merge"><i class="bi bi-git me-1"></i>Merge in GitLab</button>');
    if (S.settings && !S.settings.simulated && isOperator()) {
      actions.push('<button class="btn btn-outline-secondary" data-act="plan">Run plan</button>');
      if (S.settings.portal_apply && ["committed", "failed"].includes(c.status)) actions.push('<button class="btn btn-warning" data-act="apply">Apply</button>');
    }
    const ops = Object.entries(c.delta || {}).map(([inst, spec]) => `<li><span class="nx-badge b-${spec ? "primary" : "danger"}">${spec ? "apply" : "destroy"}</span> <span class="nx-mono small">${esc(inst)}</span></li>`).join("");
    const pv = { policy: c.policy, cost: c.cost, validation: c.validation, diff: c.diff, risk: c.risk, status: c.status, stack_file: "" };
    const m = UI.modal(`${c.id} · ${c.title}`, `
      <div class="d-flex flex-wrap gap-2 mb-2">${UI.changeBadge(c.status)} ${UI.riskBadge(c.risk)} <span class="nx-badge b-secondary">${esc(c.action)}</span>
        <span class="nx-badge b-secondary nx-mono">${esc(c.env)}</span><span class="nx-badge b-secondary">from ${esc(c.source_module || "")}</span></div>
      <div class="small nx-muted mb-2">Requested by <b>${esc(c.requester)}</b> ${esc(c.created_at)}${c.approver ? ` · decided by <b>${esc(c.approver)}</b> ${esc(c.decided_at || "")}` : ""}${c.reason ? ` · “${esc(c.reason)}”` : ""}</div>
      ${c.mr ? `<div class="alert alert-primary py-2 small"><i class="bi bi-git me-1"></i>Merge request <a href="${esc(c.mr.web_url)}" target="_blank" rel="noopener">!${esc(c.mr.iid)}</a> · ${esc(c.mr.state || "")}
        ${c.mr.pipeline_status ? ` · pipeline <b>${esc(c.mr.pipeline_status)}</b>` : ""} · branch <span class="nx-mono">${esc(c.mr.branch || "")}</span></div>` : ""}
      ${c.status === "pending_approval" && mine ? '<div class="alert alert-secondary py-2 small">You requested this change, so another approver must review it.</div>' : ""}
      <div class="small fw-semibold">Operations</div><ul class="list-unstyled mb-3">${ops}</ul>
      ${UI.reviewHtml(pv)}
      ${c.log ? `<div class="small fw-semibold mt-3">Log</div><pre class="nx-log">${esc(c.log)}</pre>` : ""}
      <div id="ch-run-out"></div>`, { size: "modal-xl", footer: actions.join(" ") });
    $$("[data-act]", m.el).forEach(b => b.onclick = async () => {
      const act = b.dataset.act;
      let body = {};
      if (act === "reject") { const r = prompt("Reason for rejection:"); if (r === null) return; body = { reason: r }; }
      if (act === "approve") { const r = prompt("Approval note (optional):", ""); if (r === null) return; body = { reason: r }; }
      if (act === "apply" && !confirm("Apply this change to AWS now?")) return;
      b.disabled = true;
      try {
        const r = await NX.api.post(`/api/m03/changes/${encodeURIComponent(c.id)}/${act}`, body);
        if (act === "plan" || act === "apply") { $("#ch-run-out", m.el).innerHTML = `<div class="small fw-semibold mt-3">${act} (exit ${r.code})</div><pre class="nx-log">${esc(r.output)}</pre>`; b.disabled = false; return; }
        NX.toast(`${c.id}: ${r.change.status.replace("_", " ")}`, "success"); m.hide(); loadChanges();
      } catch (e) { NX.toast(UI.errorText(e), "danger"); b.disabled = false; }
    });
  }

  /* ---------------- stacks ---------------- */
  async function loadStacks() {
    let r; try { r = await NX.api.get("/api/m03/stacks"); } catch (e) { $("#st-body").innerHTML = esc(e.message); return; }
    $("#st-body").innerHTML = r.stacks.length ? r.stacks.map(s => `<div class="col-md-6 col-xl-4"><div class="nx-card h-100"><div class="nx-card-body">
      <div class="d-flex justify-content-between"><span class="fw-semibold nx-mono">${esc(s.env)}</span><span class="nx-badge b-secondary">v${s.version}</span></div>
      <div class="small nx-muted">${esc(s.meta.tier)} · ${esc(s.meta.region)} · ${esc(s.meta.account_id)}</div>
      <div class="small nx-muted">${s.components} components · state s3://${esc(s.meta.state_bucket)}</div>
      <button class="btn btn-sm btn-outline-primary mt-2" data-stack="${esc(s.env)}">View YAML &amp; versions</button></div></div></div>`).join("")
      : `<div class="col-12"><div class="nx-empty"><i class="bi bi-layers"></i>No stacks yet.</div></div>`;
    $$("[data-stack]").forEach(b => b.onclick = () => openStack(b.dataset.stack));
    const want = UI.qs("stack"); if (want) openStack(want);
  }
  async function openStack(env) {
    let r; try { r = await NX.api.get("/api/m03/stacks/" + encodeURIComponent(env)); } catch (e) { return NX.toast(e.message, "danger"); }
    const drift = isOperator() || me().role === "security";
    const m = UI.modal(`Stack ${env}`, `
      <div class="small nx-muted mb-2">File <span class="nx-mono">${esc(r.path)}</span> · version ${r.stack.version}</div>
      <pre class="nx-diff">${esc(r.yaml)}</pre>
      <h6 class="fw-bold mt-3">Components</h6>
      ${Object.entries(r.stack.components).map(([i, c]) => `<div class="nx-sum-row"><span class="nx-mono small">${esc(i)}</span>
        <span>${drift ? `<button class="btn btn-sm btn-link p-0" data-drift="${esc(i)}">Check drift</button>` : ""}</span></div>`).join("") || '<div class="small nx-muted">Empty.</div>'}
      <h6 class="fw-bold mt-3">Versions</h6>
      ${r.versions.map(v => `<div class="nx-sum-row"><span>v${v.version} · <span class="nx-id">${esc(v.change_id)}</span> <span class="small nx-muted">${esc(v.created_at)}</span></span>
        <span class="small">${esc(v.components.join(", "))} ${isOperator() && v.version !== r.stack.version ? `<button class="btn btn-sm btn-link p-0 ms-2" data-rb="${v.version}">Roll back</button>` : ""}</span></div>`).join("")}
      <div id="st-out"></div>`, { size: "modal-xl" });
    $$("[data-rb]", m.el).forEach(b => b.onclick = async () => {
      try { const x = await NX.api.post(`/api/m03/stacks/${encodeURIComponent(env)}/rollback`, { version: +b.dataset.rb }); NX.toast(`Rollback proposed: ${x.change.id} (${x.change.status})`, "success"); m.hide(); tab("changes"); }
      catch (e) { NX.toast(UI.errorText(e), "danger"); }
    });
    $$("[data-drift]", m.el).forEach(b => b.onclick = async () => {
      b.disabled = true;
      try { const x = await NX.api.post("/api/m03/drift", { env, instance: b.dataset.drift });
        $("#st-out", m.el).innerHTML = `<div class="small fw-semibold mt-3">Drift: ${esc(x.status)}</div><pre class="nx-log">${esc(x.output)}</pre>`; }
      catch (e) { NX.toast(UI.errorText(e), "danger"); }
      b.disabled = false;
    });
  }

  /* ---------------- registry ---------------- */
  async function loadRegistry() {
    let r; try { r = await NX.api.get("/api/m03/registry"); } catch (e) { $("#rg-body").innerHTML = esc(e.message); return; }
    $("#rg-body").innerHTML = r.components.map(c => {
      const inputs = Object.entries(c.variables).filter(([, v]) => !v.shared);
      return `<div class="col-md-6 col-xl-4"><div class="nx-card h-100"><div class="nx-card-body d-flex flex-column">
        <div class="d-flex justify-content-between"><span class="fw-semibold nx-mono">${esc(c.name)}</span>
          <span><span class="nx-badge b-secondary">v${esc(c.version)}</span> <span class="nx-badge b-${c.status === "active" ? "success" : "warning"}">${esc(c.status)}</span></span></div>
        <div class="small nx-muted">${esc(c.category)}</div><div class="small mt-1 flex-grow-1">${esc(c.description)}</div>
        <div class="small nx-muted mt-2">${inputs.length} inputs (${inputs.filter(([, v]) => v.required).length} required) · ${c.outputs.length} outputs</div>
        <button class="btn btn-sm btn-outline-secondary mt-2 align-self-start" data-src="${esc(c.name)}">Inputs &amp; source</button></div></div></div>`;
    }).join("");
    $$("[data-src]").forEach(b => b.onclick = async () => {
      let x; try { x = await NX.api.get("/api/m03/registry/" + encodeURIComponent(b.dataset.src)); } catch (e) { return NX.toast(e.message, "danger"); }
      const vars = Object.entries(x.component.variables);
      UI.modal(`${x.component.name} v${x.component.version}`, `
        <table class="nx-table mb-3"><thead><tr><th>Input</th><th>Type</th><th>Default</th><th>Notes</th></tr></thead><tbody>
        ${vars.map(([k, v]) => `<tr><td class="nx-mono small">${esc(k)}${v.required ? " *" : ""}</td><td class="nx-mono small">${esc(v.type)}</td>
          <td class="nx-mono small">${v.required ? "" : esc(JSON.stringify(v.default))}</td><td class="small">${v.shared ? "set by the stack" : esc(v.description || (v.options ? "one of " + v.options.join(", ") : ""))}</td></tr>`).join("")}</tbody></table>
        <div class="small fw-semibold">Outputs</div><div class="small nx-mono mb-3">${x.component.outputs.map(esc).join(", ")}</div>
        ${Object.entries(x.files).map(([f, src]) => `<div class="small fw-semibold mt-2">${esc(f)}</div><pre class="nx-diff">${esc(src)}</pre>`).join("")}`, { size: "modal-xl" });
    });
  }

  /* ---------------- policies ---------------- */
  async function loadPolicies() {
    let r; try { r = await NX.api.get("/api/m03/policies"); } catch (e) { $("#po-body").innerHTML = esc(e.message); return; }
    $("#po-body").innerHTML = r.rules.map(p => `<tr><td class="nx-mono small">${esc(p.id)}</td>
      <td><span class="nx-badge b-${p.severity === "deny" ? "danger" : "warning"}">${esc(p.severity)}</span></td><td>${esc(p.title)}</td>
      <td class="small nx-muted">${p.frameworks.map(esc).join(" · ")}</td></tr>`).join("");
  }

  /* ---------------- settings ---------------- */
  async function loadSettings() {
    try { S.settings = await NX.api.get("/api/m03/settings"); } catch (e) { $("#se-body").innerHTML = esc(e.message); return; }
    const s = S.settings, g = s.gitlab, admin = NX.session.isAdmin(), dis = admin ? "" : "disabled";
    const tool = (n, ok) => `<span class="nx-badge b-${ok ? "success" : "secondary"}">${esc(n)} ${ok ? "installed" : "missing"}</span>`;
    $("#se-body").innerHTML = `
      <div class="col-xl-7"><div class="nx-card h-100"><div class="nx-card-body">
        <h2 class="h6 fw-bold"><i class="bi bi-git me-1"></i>GitLab repository</h2>
        <p class="small nx-muted">Approved changes are pushed to a branch and opened as a merge request in this project. Leave empty to write files locally under <span class="nx-mono">${esc(s.iac_dir)}</span>.</p>
        <div class="row g-3">
          <div class="col-md-7"><label class="form-label small fw-semibold" for="g-url">GitLab URL</label><input class="form-control" id="g-url" value="${esc(g.url)}" placeholder="https://gitlab.example.com" ${dis}></div>
          <div class="col-md-5"><label class="form-label small fw-semibold" for="g-proj">Project (id or group/name)</label><input class="form-control" id="g-proj" value="${esc(g.project)}" placeholder="platform/iac" ${dis}></div>
          <div class="col-md-5"><label class="form-label small fw-semibold" for="g-branch">Target branch</label><input class="form-control" id="g-branch" value="${esc(g.target_branch)}" ${dis}></div>
          <div class="col-md-7"><label class="form-label small fw-semibold" for="g-prefix">Path in repository (optional)</label><input class="form-control" id="g-prefix" value="${esc(g.path_prefix)}" placeholder="infra" ${dis}></div>
          <div class="col-12"><div class="small">Access token: ${g.token_present ? '<span class="nx-badge b-success">GITLAB_TOKEN set on host</span>' : '<span class="nx-badge b-warning">GITLAB_TOKEN not set</span>'}
            <span class="nx-muted">The token is read from the host environment only and is never stored or shown. Use a project access token with the api scope (Developer role).</span></div></div>
        </div>
        ${admin ? `<div class="mt-3 d-flex gap-2"><button class="btn btn-primary" id="g-save">Save</button><button class="btn btn-outline-secondary" id="g-test">Test connection</button></div>` : '<div class="small nx-muted mt-3">Only admins can change these settings.</div>'}
        <div id="g-out" class="mt-2"></div>
        <hr class="nx-hr"><div class="small"><b>Pipeline:</b> copy <span class="nx-mono">iac/.gitlab-ci.yml</span>, <span class="nx-mono">iac/scripts/run_change.py</span>, <span class="nx-mono">atmos.yaml</span>, <span class="nx-mono">components/</span> and <span class="nx-mono">stacks/</span> into the repository. MR pipelines validate and plan; merges apply; production applies wait for a manual click.</div>
      </div></div></div>
      <div class="col-xl-5"><div class="nx-card h-100"><div class="nx-card-body">
        <h2 class="h6 fw-bold">Approval policy</h2>
        <div class="form-check form-switch"><input class="form-check-input" type="checkbox" id="g-auto" ${s.auto_approve_nonprod ? "checked" : ""} ${dis}>
          <label class="form-check-label small" for="g-auto">Auto-approve low-risk non-production changes that pass every policy</label></div>
        <div class="small nx-muted mt-1">Production, destroys, staging, EKS and account changes, and anything with a warning always need a human approver. Requesters can never approve their own change.</div>
        <hr class="nx-hr"><h2 class="h6 fw-bold">Execution</h2>
        <div class="small">${s.simulated ? '<span class="nx-badge b-warning">Simulation mode</span> Approved changes are recorded as applied; no AWS call is made. Start with <span class="nx-mono">./start-portal.sh --prod</span> for live mode.'
          : '<span class="nx-badge b-success">Live mode</span> ' + (s.portal_apply ? "Operators can apply from the portal (M03_PORTAL_APPLY=1)." : "Apply runs in GitLab CI after merge.")}</div>
        <div class="small mt-2">State bucket pattern: <span class="nx-mono">${esc(s.state_bucket_pattern)}</span> (S3 native locking)</div>
        <div class="d-flex flex-wrap gap-1 mt-2">${tool("atmos", s.tools.atmos)} ${tool("terraform", s.tools.terraform)} ${tool("checkov", s.tools.checkov)} ${tool("trivy", s.tools.trivy)}</div>
      </div></div></div>`;
    if (!admin) return;
    const body = () => ({ gitlab: { url: $("#g-url").value.trim(), project: $("#g-proj").value.trim(), target_branch: $("#g-branch").value.trim(), path_prefix: $("#g-prefix").value.trim() },
      auto_approve_nonprod: $("#g-auto").checked });
    $("#g-save").onclick = async () => { try { S.settings = await NX.api.call("PUT", "/api/m03/settings", body()); NX.toast("Settings saved.", "success"); modeBadge(); } catch (e) { NX.toast(UI.errorText(e), "danger"); } };
    $("#g-auto").onchange = () => $("#g-save").click();
    $("#g-test").onclick = async () => {
      try { await NX.api.call("PUT", "/api/m03/settings", body()); const r = await NX.api.post("/api/m03/gitlab/test");
        $("#g-out").innerHTML = `<div class="alert alert-success py-2 small mb-0">Connected to <a href="${esc(r.project.web_url)}" target="_blank" rel="noopener">${esc(r.project.path)}</a> (default branch ${esc(r.project.default_branch)}).</div>`; }
      catch (e) { $("#g-out").innerHTML = `<div class="alert alert-danger py-2 small mb-0">${esc(UI.errorText(e))}</div>`; }
    };
  }

  function modeBadge() {
    const s = S.settings; if (!s) return;
    const gl = s.gitlab.url && s.gitlab.project;
    $("#ch-mode").innerHTML = `<span class="nx-badge b-${s.simulated ? "warning" : "success"}">${s.simulated ? "Live data · changes simulated" : "Live AWS"}</span>
      <span class="nx-badge b-${gl ? "primary" : "secondary"} ms-1"><i class="bi bi-git"></i>${gl ? esc(s.gitlab.project) : "Local files (no GitLab)"}</span>`;
  }

  async function init() {
    if (!$("#ch-body")) return;
    try { S.settings = await NX.api.get("/api/m03/settings"); } catch (e) { /* shown per tab */ }
    modeBadge();
    $$("#ch-tabs [data-tab]").forEach(b => b.onclick = () => tab(b.dataset.tab));
    $("#ch-search").oninput = renderChanges; $("#ch-status").onchange = renderChanges; $("#ch-refresh").onclick = loadChanges;
    const want = location.hash.slice(1);
    if (UI.qs("stack")) tab("stacks"); else if (["registry", "policies", "settings", "stacks"].includes(want)) tab(want); else tab("changes");
    if (UI.qs("id")) openChange(UI.qs("id"));
  }
  document.addEventListener("DOMContentLoaded", () => setTimeout(init, 0));
})();
