/* Launch wizard: resource type -> environment -> options -> review -> submit (M02 -> M03). */
(function () {
  "use strict";
  const NX = window.NEXUS, UI = NX.ui, esc = NX.esc, $ = UI.$, $$ = UI.$$;
  const STEPS = ["Resource", "Environment", "Options", "Review"];
  const S = { step: 0, types: [], envs: [], type: UI.qs("type"), env: UI.qs("env"), values: {}, preview: null, result: null, busy: false,
    net: { vpc_id: "", subnet_ids: [] }, vpcs: null, vpcErr: "" };
  const VPC_TYPES = ["ec2-instance", "efs", "eks-cluster", "alb"];
  const needsNet = () => { const e = envDef(); return e && e.kind === "existing" && (VPC_TYPES.includes(S.type) || (S.type === "route53-zone" && S.values.private_zone)); };

  const typeDef = () => S.types.find(t => t.id === S.type);
  const envDef = () => S.envs.find(e => e.id === S.env);

  function stepType() {
    const cats = [...new Set(S.types.map(t => t.category))];
    return `<h2 class="h6 fw-bold mb-3">What do you want to launch?</h2>` + cats.map(c => `
      <div class="small text-uppercase nx-muted fw-semibold mt-3 mb-2">${esc(c)}</div>
      <div class="row g-3">${S.types.filter(t => t.category === c).map(t => `<div class="col-md-6 col-xl-4">
        <div class="nx-choice ${S.type === t.id ? "selected" : ""}" data-type="${esc(t.id)}" tabindex="0" role="button">
          <div class="d-flex align-items-center gap-2"><i class="bi ${esc(t.icon)} fs-4 text-primary"></i><span class="fw-semibold">${esc(t.label)}</span></div>
          <div class="small nx-muted mt-1">${esc(t.description)}</div></div></div>`).join("")}</div>`).join("");
  }
  function stepEnv() {
    const usable = S.envs.filter(e => ["active", "provisioning"].includes(e.status));
    if (!usable.length) return `<div class="nx-empty"><i class="bi bi-diagram-3"></i>No environment yet. <a href="environments.html">Create a new one</a>, or
      <a href="environments.html#import">use an existing VPC</a> already in your AWS account.</div>`;
    return `<h2 class="h6 fw-bold mb-3">Where should it run?</h2><div class="row g-3">${usable.map(e => `<div class="col-md-6 col-xl-4">
      <div class="nx-choice ${S.env === e.id ? "selected" : ""}" data-env="${esc(e.id)}" tabindex="0" role="button">
        <div class="d-flex justify-content-between"><span class="fw-semibold">${esc(e.id)}</span><span>${e.kind === "existing" ? '<span class="nx-badge b-info">existing VPC</span> ' : ""}${UI.envBadge(e.status)}</span></div>
        ${e.vpc_id ? `<div class="small nx-muted nx-mono">${esc(e.vpc_id)} · ${esc(e.cidr || "")}</div>` : ""}
        <div class="small nx-muted">${esc(e.tier)} · ${esc(e.region)} · account ${esc(e.account_id)}</div>
        <div class="small nx-muted">team ${esc(e.team)} · ${e.component_count} components · ${UI.money(e.monthly)}/mo</div>
        ${e.tier === "production" ? '<div class="small text-warning mt-1"><i class="bi bi-person-check me-1"></i>Needs an approver</div>' : ""}</div></div>`).join("")}</div>`;
  }
  function stepOptions() {
    const t = typeDef();
    return `<h2 class="h6 fw-bold mb-1"><i class="bi ${esc(t.icon)} me-1"></i>${esc(t.label)} options</h2>
      <p class="small nx-muted mb-3">${esc(t.description)}</p>${needsNet() ? netHtml() : ""}<div class="row g-3" id="ln-fields">${UI.fieldsHtml(t.fields, S.values)}</div>`;
  }
  function netHtml() {
    const e = envDef();
    if (S.vpcErr) return `<div class="alert alert-danger small">${esc(S.vpcErr)}</div>`;
    if (!S.vpcs) return `<div class="nx-card mb-3"><div class="nx-card-body small nx-muted"><span class="spinner-border spinner-border-sm me-1"></span>Reading VPCs and subnets from ${esc(e.account_id)} / ${esc(e.region)}…</div></div>`;
    const v = S.vpcs.find(x => x.id === S.net.vpc_id);
    const multi = S.type !== "ec2-instance";
    const hint = { "ec2-instance": "Pick one subnet. Public subnets give the instance a public IP.", "alb": S.values.scheme === "internal" ? "Pick private subnets in 2+ AZs." : "Pick public subnets in 2+ AZs for an internet-facing load balancer.",
      "eks-cluster": "Pick private subnets in at least 2 AZs.", "efs": "One mount target is created in each subnet you pick (one per AZ)." }[S.type] || "";
    return `<div class="nx-card mb-3"><div class="nx-card-body">
      <div class="fw-semibold small mb-2"><i class="bi bi-diagram-3 me-1"></i>Network (live from your account)</div>
      <select class="form-select mb-2" id="ln-vpc"><option value="">Choose a VPC…</option>${S.vpcs.map(x => `<option value="${esc(x.id)}" ${x.id === S.net.vpc_id ? "selected" : ""}>${esc(x.name || x.id)} · ${esc(x.id)} · ${esc(x.cidr)}${x.default ? " (default)" : ""}</option>`).join("")}</select>
      ${v && S.type !== "route53-zone" ? `<div class="small nx-muted mb-1">${esc(hint)}</div><div class="row g-2">${v.subnets.map(sn => `<div class="col-md-6 col-xl-4">
        <label class="nx-choice d-block ${S.net.subnet_ids.includes(sn.id) ? "selected" : ""}" style="cursor:pointer">
          <input type="${multi ? "checkbox" : "radio"}" class="form-check-input me-1" name="ln-sub" value="${esc(sn.id)}" ${S.net.subnet_ids.includes(sn.id) ? "checked" : ""}>
          <span class="fw-semibold small">${esc(sn.name || sn.id)}</span> ${sn.public ? '<span class="nx-badge b-warning">public</span>' : '<span class="nx-badge b-secondary">private</span>'}
          <div class="small nx-muted nx-mono">${esc(sn.id)} · ${esc(sn.az)} · ${esc(sn.cidr)} · ${sn.free_ips} free IPs</div></label></div>`).join("")}</div>` : ""}
    </div></div>`;
  }
  function stepReview() {
    if (S.result) {
      const c = S.result;
      return `<div class="text-center py-4"><div class="display-6 text-${c.status === "blocked" ? "danger" : c.status === "applied" ? "success" : "primary"}">
        <i class="bi bi-${c.status === "blocked" ? "x-octagon" : c.status === "applied" ? "check-circle" : "send-check"}"></i></div>
        <h2 class="h5 mt-2">Change ${esc(c.id)} · ${UI.changeBadge(c.status)}</h2>
        <p class="nx-muted small">${c.status === "applied" ? "Simulation mode recorded the change. In live mode GitLab CI applies it." :
          c.status === "mr_open" ? "Merge request opened in GitLab." : c.status === "pending_approval" ? "Waiting for an approver." : ""}</p>
        ${c.mr && c.mr.web_url ? `<a class="btn btn-outline-primary me-2" href="${esc(c.mr.web_url)}" target="_blank" rel="noopener">Open merge request</a>` : ""}
        <a class="btn btn-primary me-2" href="changes.html?id=${esc(c.id)}">View change</a>
        <button class="btn btn-outline-secondary" id="ln-again">Launch another</button></div>`;
    }
    if (!S.preview) return `<div class="nx-empty"><i class="bi bi-hourglass-split"></i>Running policy, cost and Atmos validation…</div>`;
    return UI.reviewHtml(S.preview);
  }

  function draw() {
    UI.steps($("#ln-steps"), STEPS, S.step, (i) => { S.step = i; S.preview = null; draw(); });
    $("#ln-body").innerHTML = [stepType, stepEnv, stepOptions, stepReview][S.step]();
    $$("[data-type]").forEach(c => c.onclick = () => { if (S.type !== c.dataset.type) S.values = {}; S.type = c.dataset.type; draw(); });
    $$("[data-env]").forEach(c => c.onclick = () => { if (S.env !== c.dataset.env) { S.vpcs = null; S.vpcErr = ""; } S.env = c.dataset.env;
      const e = envDef(); S.net = { vpc_id: (e && e.vpc_id) || "", subnet_ids: [] }; draw(); });
    if (S.step === 2) {
      UI.bindFields($("#ln-fields"), typeDef().fields, S.values, draw);
      if (needsNet() && !S.vpcs && !S.vpcErr) loadVpcs();
      const vs = $("#ln-vpc"); if (vs) vs.onchange = () => { S.net = { vpc_id: vs.value, subnet_ids: [] }; draw(); };
      $$("input[name=ln-sub]").forEach(i => i.onchange = () => { S.net.subnet_ids = $$("input[name=ln-sub]:checked").map(x => x.value); draw(); });
    }
    const again = $("#ln-again");
    if (again) again.onclick = () => { S.result = null; S.preview = null; S.values = {}; S.step = 0; draw(); };
    const next = $("#ln-next"), back = $("#ln-back");
    back.disabled = S.step === 0 || S.busy;
    next.classList.toggle("d-none", !!S.result); back.classList.toggle("d-none", !!S.result);
    next.disabled = S.busy || (S.step === 0 && !S.type) || (S.step === 1 && !envDef()) || (S.step === 3 && (!S.preview || S.preview.status === "blocked"));
    next.innerHTML = S.step === 3 ? '<i class="bi bi-send me-1"></i>Submit change' : 'Next<i class="bi bi-arrow-right ms-1"></i>';
  }

  async function loadVpcs() {
    const e = envDef();
    try { S.vpcs = (await NX.api.get(`/api/m02/live/vpcs?account=${encodeURIComponent(e.account_id)}&region=${encodeURIComponent(e.region)}`)).vpcs;
      if (!S.net.vpc_id && e.vpc_id) S.net.vpc_id = e.vpc_id; }
    catch (er) { S.vpcErr = "Could not read the account's VPCs: " + UI.errorText(er); }
    draw();
  }
  const reqBody = () => ({ environment: S.env, type: S.type, values: S.values, network: needsNet() ? S.net : undefined });
  async function preview() {
    S.preview = null; draw();
    try {
      const r = await NX.api.post("/api/m02/resources/preview", reqBody());
      S.preview = r.preview;
    } catch (e) { S.step = 2; draw(); return NX.toast(UI.errorText(e), "danger"); }
    draw();
  }
  async function submit() {
    S.busy = true; draw();
    try {
      const r = await NX.api.post("/api/m02/resources", reqBody());
      S.result = r.change;
      NX.toast(`${r.change.id}: ${r.change.status.replace("_", " ")}`, r.change.status === "blocked" ? "danger" : "success");
    } catch (e) { NX.toast(UI.errorText(e), "danger"); }
    S.busy = false; draw();
  }

  async function init() {
    if (!$("#ln-body")) return;
    try {
      const [t, e] = await Promise.all([NX.api.get("/api/m02/resource-types"), NX.api.get("/api/m02/environments")]);
      S.types = t.types; S.envs = e.environments;
    } catch (e) { $("#ln-body").innerHTML = `<div class="nx-empty"><i class="bi bi-exclamation-triangle"></i>${esc(e.message)}</div>`; return; }
    if (S.type && typeDef()) S.step = 1;
    if (S.step === 1 && envDef()) { S.step = 2; S.net = { vpc_id: envDef().vpc_id || "", subnet_ids: [] }; }
    $("#ln-back").onclick = () => { if (S.step > 0) { S.step--; S.preview = null; draw(); } };
    $("#ln-next").onclick = () => {
      if (S.step < 2) { S.step++; draw(); }
      else if (S.step === 2) { S.step = 3; preview(); }
      else submit();
    };
    draw();
  }
  document.addEventListener("DOMContentLoaded", () => setTimeout(init, 0));
})();
