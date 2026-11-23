/* M09 AI engineering & multi-agent platform workspace. */
(function () {
  "use strict";
  const NX = window.NEXUS, UI = NX.ui, esc = NX.esc, $ = UI.$, $$ = UI.$$;
  const S = { tab: "agents", kinds: [], providers: [], agents: [], tools: [], me: null };
  const role = () => (NX.session.get() || {}).role || "";
  const isAdmin = () => role() === "admin";
  const canBuild = () => ["developer", "approver", "operator", "security", "admin"].includes(role());
  const loading = () => '<div class="nx-empty"><i class="bi bi-hourglass-split"></i>Loading…</div>';
  const fail = (e) => `<div class="alert alert-danger small">${esc(UI.errorText(e))}</div>`;
  const tbl = (head, rows, empty) => rows.length ? `<div class="nx-card"><div class="nx-table-wrap"><table class="nx-table"><thead><tr>${head.map(h => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div></div>`
    : `<div class="nx-card"><div class="nx-empty"><i class="bi bi-inbox"></i>${esc(empty)}</div></div>`;
  const statusBadge = (s) => `<span class="nx-badge b-${{ success: "success", failed: "danger", running: "primary", max_steps: "warning", budget_exhausted: "warning", timeout: "warning", truncated: "warning" }[s] || "secondary"}">${esc(s)}</span>`;
  const money = (v) => v === null || v === undefined ? "-" : "$" + Number(v).toFixed(4);
  const chk = (name, value, label, checked) => `<label class="form-check"><input class="form-check-input" type="checkbox" name="${name}" value="${esc(value)}" ${checked ? "checked" : ""}> <span class="small">${esc(label)}</span></label>`;

  async function loadCore() {
    const [k, p, a, t] = await Promise.all([NX.api.get("/api/m09/kinds"), NX.api.get("/api/m09/providers"), NX.api.get("/api/m09/agents"), NX.api.get("/api/m09/tools")]);
    S.kinds = k.kinds; S.providers = p.providers; S.agents = a.agents; S.tools = t.tools;
  }

  async function overview() {
    const o = await NX.api.get("/api/m09/overview");
    const k = (l, v, i, t, sub) => `<div class="col-6 col-xl-2"><div class="nx-card h-100"><div class="nx-card-body nx-kpi"><div class="nx-kpi-icon tone-${t}"><i class="bi ${i}"></i></div>
      <div><div class="nx-kpi-value" style="font-size:20px">${esc(v)}</div><div class="nx-kpi-label">${esc(l)}</div>${sub ? `<div class="small nx-muted">${esc(sub)}</div>` : ""}</div></div></div></div>`;
    const st = o.runs_by_status || {};
    $("#ai-kpis").innerHTML = k("Agents", o.agents, "bi-robot", "primary", `${o.teams} teams`) +
      k("Providers", o.providers, "bi-cloud", "info") +
      k("Runs (7d)", o.runs_7d, "bi-play-circle", "secondary", `ok ${st.success || 0} · failed ${st.failed || 0}`) +
      k("Tokens (7d)", o.tokens_7d.toLocaleString(), "bi-123", "secondary") +
      k("Cost (7d)", o.cost_7d === null ? "n/a" : "$" + o.cost_7d, "bi-currency-dollar", "warning", o.cost_7d === null ? "set provider prices" : "") +
      k("Tools", o.tools, "bi-tools", "success", "read-only");
    $("#ai-actions").innerHTML = canBuild() ? `<button class="btn btn-primary" id="ai-new-agent"><i class="bi bi-plus-lg me-1"></i>New agent</button>
      <button class="btn btn-outline-primary ms-2" id="ai-new-team"><i class="bi bi-people me-1"></i>New team</button>` : "";
    if ($("#ai-new-agent")) $("#ai-new-agent").onclick = () => agentForm();
    if ($("#ai-new-team")) $("#ai-new-team").onclick = () => teamForm();
  }

  /* ---------------- agents ---------------- */
  const providerName = (id) => (S.providers.find(p => p.id === id) || {}).name || "(missing)";
  async function drawAgents() {
    const r = await NX.api.get("/api/m09/agents");
    S.agents = r.agents;
    $("#ai-pane").innerHTML = tbl(["Agent", "Model", "Tools", "Steps", "Owner", ""], r.agents.map(a => `<tr>
      <td><div class="fw-semibold small">${esc(a.name)}</div><div class="small nx-muted">${esc(a.description || "")}</div></td>
      <td class="small">${esc(providerName(a.provider_id))}<div class="nx-mono nx-muted">${esc(a.model)}</div></td>
      <td class="small">${a.tools.length ? a.tools.map(t => `<span class="nx-badge b-secondary me-1">${esc(t)}</span>`).join("") : '<span class="nx-muted">none (chat only)</span>'}</td>
      <td class="small">${esc(a.max_steps)}</td>
      <td class="small">${esc(a.owner)}</td>
      <td class="text-end" style="white-space:nowrap">
        ${canBuild() ? `<button class="btn btn-sm btn-success" data-run-agent="${esc(a.id)}"><i class="bi bi-play-fill"></i> Run</button>` : ""}
        ${canBuild() && (a.owner === (NX.session.get() || {}).name || isAdmin()) ? `<button class="btn btn-sm btn-outline-secondary" data-edit-agent="${esc(a.id)}"><i class="bi bi-pencil"></i></button>
        <button class="btn btn-sm btn-outline-danger" data-del-agent="${esc(a.id)}"><i class="bi bi-trash"></i></button>` : ""}</td></tr>`),
      "No agents yet. Create one with New agent, then run it.");
    $$("[data-run-agent]").forEach(b => b.onclick = () => runForm("agent", b.dataset.runAgent));
    $$("[data-edit-agent]").forEach(b => b.onclick = () => agentForm(S.agents.find(a => a.id === b.dataset.editAgent)));
    $$("[data-del-agent]").forEach(b => b.onclick = async () => {
      if (!confirm("Delete this agent? Teams that use it must be changed first.")) return;
      try { await NX.api.call("DELETE", `/api/m09/agents/${b.dataset.delAgent}`); NX.toast("Deleted.", "success"); await loadCore(); overview(); drawAgents(); }
      catch (e) { NX.toast(UI.errorText(e), "danger"); }
    });
  }

  function agentForm(cur) {
    const providers = S.providers.filter(p => p.enabled);
    if (!providers.length) return NX.toast(isAdmin() ? "Add a model provider first (Model providers tab)." : "No model provider is set up yet. Ask an administrator.", "warning");
    const sel = cur ? cur.tools : ["current_time"];
    const m = UI.modal(cur ? `Edit ${cur.name}` : "New agent", `<div class="row g-3">
      <div class="col-md-6"><label class="form-label small fw-semibold">Name</label><input class="form-control" id="ag-name" value="${esc(cur?.name || "")}" placeholder="Cost reviewer"></div>
      <div class="col-md-6"><label class="form-label small fw-semibold">Description</label><input class="form-control" id="ag-desc" value="${esc(cur?.description || "")}"></div>
      <div class="col-md-6"><label class="form-label small fw-semibold">Model provider</label><select class="form-select" id="ag-prov">${providers.map(p => `<option value="${esc(p.id)}" data-model="${esc(p.default_model || "")}" ${cur?.provider_id === p.id ? "selected" : ""}>${esc(p.name)} (${esc(p.kind)})</option>`).join("")}</select></div>
      <div class="col-md-6"><label class="form-label small fw-semibold">Model</label><input class="form-control" id="ag-model" value="${esc(cur?.model || providers[0].default_model || "")}" placeholder="model id"></div>
      <div class="col-12"><label class="form-label small fw-semibold">System prompt</label><textarea class="form-control" id="ag-prompt" rows="5" placeholder="You review AWS cost data. Answer with numbers from the tools. Never suggest changes you cannot make yourself.">${esc(cur?.system_prompt || "")}</textarea></div>
      <div class="col-12"><label class="form-label small fw-semibold">Tools (read-only; a user needs the tool's role to use it)</label><div>${S.tools.map(t => chk("ag-tool", t.name, `${t.name} (${t.min_role}+): ${t.description}`, sel.includes(t.name))).join("")}</div></div>
      <div class="col-md-4"><label class="form-label small fw-semibold">Max steps</label><input type="number" class="form-control" id="ag-steps" min="1" max="10" value="${cur?.max_steps || 6}"></div>
      <div class="col-md-4"><label class="form-label small fw-semibold">Max output tokens</label><input type="number" class="form-control" id="ag-max" min="64" max="8192" value="${cur?.max_tokens || 1024}"></div>
      <div class="col-md-4"><label class="form-label small fw-semibold">Temperature (empty = model default)</label><input class="form-control" id="ag-temp" value="${cur?.temperature ?? ""}"></div>
      <div class="alert alert-danger py-2 small d-none" id="ag-err"></div></div>`, { footer: '<button class="btn btn-primary" id="ag-save">Save</button>' });
    $("#ag-prov", m.el).onchange = (e) => { const o = e.target.selectedOptions[0]; if (!$("#ag-model", m.el).value) $("#ag-model", m.el).value = o.dataset.model || ""; };
    $("#ag-save", m.el).onclick = async () => {
      const payload = {
        name: $("#ag-name", m.el).value, description: $("#ag-desc", m.el).value, provider_id: $("#ag-prov", m.el).value,
        model: $("#ag-model", m.el).value, system_prompt: $("#ag-prompt", m.el).value,
        tools: $$("input[name=ag-tool]:checked", m.el).map(i => i.value),
        max_steps: +$("#ag-steps", m.el).value, max_tokens: +$("#ag-max", m.el).value,
        temperature: $("#ag-temp", m.el).value.trim() === "" ? null : +$("#ag-temp", m.el).value,
      };
      try {
        if (cur) await NX.api.call("PUT", `/api/m09/agents/${cur.id}`, payload); else await NX.api.post("/api/m09/agents", payload);
        m.hide(); NX.toast("Agent saved.", "success"); await loadCore(); drawAgents();
      } catch (e) { const x = $("#ag-err", m.el); x.textContent = UI.errorText(e); x.classList.remove("d-none"); }
    };
  }

  /* ---------------- teams ---------------- */
  async function drawTeams() {
    const r = await NX.api.get("/api/m09/teams");
    $("#ai-pane").innerHTML = tbl(["Team", "Lead", "Members", "Owner", ""], r.teams.map(t => `<tr>
      <td class="fw-semibold small">${esc(t.name)}<div class="small nx-muted">${esc(t.description || "")}</div></td>
      <td class="small">${esc(t.lead_name)}</td>
      <td class="small">${t.member_names.map(n => `<span class="nx-badge b-secondary me-1">${esc(n)}</span>`).join("")}</td>
      <td class="small">${esc(t.owner)}</td>
      <td class="text-end" style="white-space:nowrap">${canBuild() ? `<button class="btn btn-sm btn-success" data-run-team="${esc(t.id)}"><i class="bi bi-diagram-3"></i> Run team</button>` : ""}</td></tr>`),
      "No teams yet. A team is a lead agent plus member agents it can delegate to.");
    $$("[data-run-team]").forEach(b => b.onclick = () => runForm("team", b.dataset.runTeam));
  }

  function teamForm() {
    if (S.agents.length < 2) return NX.toast("Create at least two agents first.", "warning");
    const m = UI.modal("New team", `<div class="row g-3">
      <div class="col-md-6"><label class="form-label small fw-semibold">Name</label><input class="form-control" id="tm-name" placeholder="Cost investigation"></div>
      <div class="col-md-6"><label class="form-label small fw-semibold">Lead agent</label><select class="form-select" id="tm-lead">${S.agents.map(a => `<option value="${esc(a.id)}">${esc(a.name)}</option>`).join("")}</select></div>
      <div class="col-12"><label class="form-label small fw-semibold">Members (the lead can delegate to these)</label><div>${S.agents.map(a => chk("tm-mem", a.id, a.name, false)).join("")}</div></div>
      <div class="alert alert-danger py-2 small d-none" id="tm-err"></div></div>`, { footer: '<button class="btn btn-primary" id="tm-save">Create</button>' });
    $("#tm-save", m.el).onclick = async () => {
      const lead = $("#tm-lead", m.el).value;
      try {
        await NX.api.post("/api/m09/teams", { name: $("#tm-name", m.el).value, lead_id: lead, members: $$("input[name=tm-mem]:checked", m.el).map(i => i.value).filter(v => v !== lead) });
        m.hide(); NX.toast("Team created.", "success"); drawTeams();
      } catch (e) { const x = $("#tm-err", m.el); x.textContent = UI.errorText(e); x.classList.remove("d-none"); }
    };
  }

  /* ---------------- run ---------------- */
  function runForm(kind, id) {
    const name = kind === "agent" ? (S.agents.find(a => a.id === id) || {}).name : id;
    const m = UI.modal(`Run ${kind === "agent" ? "agent" : "team"}`, `<p class="small nx-muted">Runs as you. The agent can only use tools you are allowed to use. Nothing is changed in AWS.</p>
      <label class="form-label small fw-semibold">Task</label><textarea class="form-control" id="rn-task" rows="4" placeholder="How many EC2 instances in the dev account are stopped? List their names."></textarea>
      <div class="row g-2 mt-2"><div class="col-md-4"><label class="form-label small fw-semibold">Token budget</label><input class="form-control" id="rn-budget" type="number" value="60000" min="1000" max="300000"></div></div>
      <div id="rn-out" class="mt-3"></div>`, { footer: '<button class="btn btn-success" id="rn-go">Run</button>' });
    $("#rn-go", m.el).onclick = async () => {
      const out = $("#rn-out", m.el);
      out.innerHTML = '<div class="small nx-muted"><i class="bi bi-hourglass-split me-1"></i>Running. This can take up to a few minutes.</div>';
      try {
        const url = kind === "agent" ? `/api/m09/agents/${id}/run` : `/api/m09/teams/${id}/run`;
        const r = (await NX.api.post(url, { task: $("#rn-task", m.el).value, token_budget: +$("#rn-budget", m.el).value })).run;
        out.innerHTML = `<div class="mb-2">${statusBadge(r.status)} <span class="small nx-muted">${esc(r.id)} · ${r.tokens_in + r.tokens_out} tokens · ${money(r.cost)} · ${r.duration_ms} ms</span></div>
          ${r.error ? `<div class="alert alert-warning small py-2">${esc(r.error)}</div>` : ""}
          <div class="small fw-semibold mb-1">Answer</div><div class="nx-card mb-3"><div class="nx-card-body small" style="white-space:pre-wrap">${esc(r.output || "(no answer)")}</div></div>
          <details><summary class="small">Trace (${r.steps.length} steps)</summary>${traceHtml(r.steps)}</details>`;
        loadCore();
      } catch (e) { out.innerHTML = fail(e); }
    };
  }

  function traceHtml(steps) {
    return `<ol class="small mt-2">${steps.map(s => {
      if (s.type === "model") return `<li><b>${esc(s.agent)}</b> model call · ${s.tokens.in}+${s.tokens.out} tokens · ${s.ms} ms · ${esc(s.stop)}${s.text ? `<div class="nx-muted" style="white-space:pre-wrap">${esc(s.text)}</div>` : ""}</li>`;
      if (s.type === "tool") return `<li><b>${esc(s.agent)}</b> tool <code>${esc(s.tool)}</code> ${s.ok ? "" : '<span class="text-danger">(failed)</span>'}<div class="nx-mono nx-muted">${esc(JSON.stringify(s.input))}</div><div class="nx-muted" style="white-space:pre-wrap">${esc((s.output || "").slice(0, 600))}</div></li>`;
      return `<li class="${s.type === "error" ? "text-danger" : "nx-muted"}">${esc(s.text || "")}</li>`;
    }).join("")}</ol>`;
  }

  /* ---------------- run history ---------------- */
  async function drawRuns() {
    const r = await NX.api.get("/api/m09/runs?limit=100");
    $("#ai-pane").innerHTML = tbl(["Run", "Target", "User", "Task", "Status", "Tokens", "Cost", "Started", ""], r.runs.map(x => `<tr>
      <td class="nx-mono small">${esc(x.id)}</td><td class="small">${esc(x.kind)}: ${esc(x.target_name)}</td><td class="small">${esc(x.username)}</td>
      <td class="small" style="max-width:260px">${esc((x.task || "").slice(0, 120))}</td><td>${statusBadge(x.status)}</td>
      <td class="small">${(x.tokens_in || 0) + (x.tokens_out || 0)}</td><td class="small">${money(x.cost)}</td><td class="small">${esc(x.started_at)}</td>
      <td><button class="btn btn-sm btn-outline-secondary" data-view-run="${esc(x.id)}"><i class="bi bi-eye"></i></button></td></tr>`), "No runs yet.");
    $$("[data-view-run]").forEach(b => b.onclick = async () => {
      const x = (await NX.api.get(`/api/m09/runs/${b.dataset.viewRun}`)).run;
      UI.modal(`Run ${x.id}`, `<div class="small mb-2">${statusBadge(x.status)} · ${esc(x.task)}</div>
        ${x.error ? `<div class="alert alert-warning small py-2">${esc(x.error)}</div>` : ""}
        <div class="nx-card mb-3"><div class="nx-card-body small" style="white-space:pre-wrap">${esc(x.output || "(no answer)")}</div></div>${traceHtml(x.steps)}`);
    });
  }

  /* ---------------- providers (admin) ---------------- */
  async function drawProviders() {
    if (!isAdmin()) { $("#ai-pane").innerHTML = '<div class="nx-card"><div class="nx-card-body small">Only administrators manage model providers and API keys.</div></div>'; return; }
    $("#ai-pane").innerHTML = `<div class="d-flex justify-content-end mb-2"><button class="btn btn-sm btn-primary" id="pv-new"><i class="bi bi-plus-lg me-1"></i>Add provider</button></div>` +
      tbl(["Provider", "Kind", "Endpoint / model", "API key", "Last test", ""], S.providers.map(p => `<tr>
        <td class="fw-semibold small">${esc(p.name)}${p.enabled ? "" : ' <span class="nx-badge b-secondary">disabled</span>'}</td>
        <td class="small">${esc(p.kind)}</td>
        <td class="small">${p.kind === "bedrock" ? `Bedrock ${esc(p.region)}` : esc(p.base_url || "default")}<div class="nx-mono nx-muted">${esc(p.default_model || "")}</div></td>
        <td class="small">${esc(p.key_status)}</td>
        <td class="small">${p.last_test ? (p.last_test_ok ? '<span class="text-success">ok</span>' : '<span class="text-danger">failed</span>') + ` <span class="nx-muted">${esc(p.last_test)}</span>` : '<span class="nx-muted">never</span>'}</td>
        <td class="text-end" style="white-space:nowrap">
          <button class="btn btn-sm btn-outline-success" data-pv-test="${esc(p.id)}" data-model="${esc(p.default_model || "")}">Test</button>
          <button class="btn btn-sm btn-outline-secondary" data-pv-edit="${esc(p.id)}"><i class="bi bi-pencil"></i></button></td></tr>`),
        "No providers yet. Add Claude, ChatGPT, Bedrock or a local model server.");
    $("#pv-new").onclick = () => providerForm();
    $$("[data-pv-edit]").forEach(b => b.onclick = () => providerForm(S.providers.find(p => p.id === b.dataset.pvEdit)));
    $$("[data-pv-test]").forEach(b => b.onclick = async () => {
      const model = b.dataset.model || prompt("Model id to test with:", "");
      if (!model) return;
      b.disabled = true; b.textContent = "Testing…";
      try {
        const r = await NX.api.post(`/api/m09/providers/${b.dataset.pvTest}/test`, { model });
        NX.toast(`Connected to ${r.model}: "${r.message}"`, "success");
      } catch (e) { NX.toast(UI.errorText(e), "danger"); }
      drawProviders();
    });
  }

  function providerForm(cur) {
    const kindOpts = S.kinds.map(k => `<option value="${k.id}" ${cur?.kind === k.id ? "selected" : ""}>${esc(k.label)}</option>`).join("");
    const accts = (NX.awsAccounts || []).map(a => `<option value="${esc(a.id)}" ${cur?.aws_account === a.id ? "selected" : ""}>${esc(a.alias)} (${esc(a.id)})</option>`).join("");
    const m = UI.modal(cur ? `Edit ${cur.name}` : "Add model provider", `<div class="row g-3">
      <div class="col-md-6"><label class="form-label small fw-semibold">Name</label><input class="form-control" id="pv-name" value="${esc(cur?.name || "")}" placeholder="Claude production"></div>
      <div class="col-md-6"><label class="form-label small fw-semibold">Kind</label><select class="form-select" id="pv-kind">${kindOpts}</select></div>
      <div class="col-12 pv-http"><label class="form-label small fw-semibold">Base URL</label><input class="form-control" id="pv-url" value="${esc(cur?.base_url || "")}" placeholder="https://api.groq.com/openai/v1 (required for OpenAI-compatible; empty = default)"></div>
      <div class="col-12 pv-bedrock d-none"><div class="row g-2"><div class="col-md-6"><label class="form-label small fw-semibold">AWS account (credentials)</label><select class="form-select" id="pv-acct">${accts}</select></div>
        <div class="col-md-6"><label class="form-label small fw-semibold">Region</label><input class="form-control" id="pv-region" value="${esc(cur?.region || "eu-west-1")}"></div></div></div>
      <div class="col-md-6 pv-http"><label class="form-label small fw-semibold">Default model</label><input class="form-control" id="pv-model" value="${esc(cur?.default_model || "")}" placeholder="model id you have access to"></div>
      <div class="col-md-6 pv-http"><label class="form-label small fw-semibold">API key from host environment variable</label><input class="form-control" id="pv-env" value="${esc(cur?.api_key_env || "")}" placeholder="OPENAI_API_KEY"></div>
      <div class="col-12 pv-http"><label class="form-label small fw-semibold">…or paste the key (stored encrypted, never shown again)</label><input class="form-control" id="pv-key" type="password" autocomplete="new-password" placeholder="${cur?.key_status === "stored" ? "leave empty to keep the stored key" : "optional"}"></div>
      <div class="col-md-6"><label class="form-label small fw-semibold">Price per 1M input tokens (optional, USD)</label><input class="form-control" id="pv-pin" value="${cur?.price_in ?? ""}"></div>
      <div class="col-md-6"><label class="form-label small fw-semibold">Price per 1M output tokens (optional, USD)</label><input class="form-control" id="pv-pout" value="${cur?.price_out ?? ""}"></div>
      <div class="col-12"><label class="form-check"><input class="form-check-input" type="checkbox" id="pv-on" ${cur?.enabled === false ? "" : "checked"}> <span class="small">Enabled</span></label></div>
      <div class="alert alert-danger py-2 small d-none" id="pv-err"></div></div>`, { footer: '<button class="btn btn-primary" id="pv-save">Save</button>' });
    const sync = () => {
      const bedrock = $("#pv-kind", m.el).value === "bedrock";
      $$(".pv-bedrock", m.el).forEach(e => e.classList.toggle("d-none", !bedrock));
      $$(".pv-http", m.el).forEach(e => e.classList.toggle("d-none", bedrock));
      const k = S.kinds.find(x => x.id === $("#pv-kind", m.el).value);
      if (k && !cur && !$("#pv-env", m.el).value) $("#pv-env", m.el).value = k.key_env || "";
      if (k && !cur) $("#pv-url", m.el).placeholder = k.base_url || "(required for OpenAI-compatible)";
    };
    $("#pv-kind", m.el).onchange = sync; sync();
    $("#pv-save", m.el).onclick = async () => {
      const bedrock = $("#pv-kind", m.el).value === "bedrock";
      const payload = { name: $("#pv-name", m.el).value, kind: $("#pv-kind", m.el).value, price_in: $("#pv-pin", m.el).value, price_out: $("#pv-pout", m.el).value, enabled: $("#pv-on", m.el).checked };
      if (bedrock) Object.assign(payload, { aws_account: $("#pv-acct", m.el).value, region: $("#pv-region", m.el).value });
      else Object.assign(payload, { base_url: $("#pv-url", m.el).value, default_model: $("#pv-model", m.el).value, api_key_env: $("#pv-env", m.el).value.trim(), api_key: $("#pv-key", m.el).value });
      try {
        if (cur) await NX.api.call("PUT", `/api/m09/providers/${cur.id}`, payload); else await NX.api.post("/api/m09/providers", payload);
        m.hide(); NX.toast("Provider saved.", "success"); await loadCore(); drawProviders();
      } catch (e) { const x = $("#pv-err", m.el); x.textContent = UI.errorText(e); x.classList.remove("d-none"); }
    };
  }

  /* ---------------- tools ---------------- */
  async function drawTools() {
    $("#ai-pane").innerHTML = tbl(["Tool", "What it does", "Minimum role", "Parameters"], S.tools.map(t => `<tr>
      <td class="nx-mono small">${esc(t.name)}</td><td class="small">${esc(t.description)}</td><td><span class="nx-badge b-primary">${esc(t.min_role)}</span></td>
      <td class="nx-mono small">${esc(Object.keys(t.parameters.properties || {}).join(", ") || "none")}</td></tr>`),
      "No tools registered.") + `<div class="small nx-muted mt-2">Tools are read-only. Write tools need human approval through M03 and are not part of this version.</div>`;
  }

  async function setTab(t) {
    S.tab = t; $$("#ai-tabs [data-tab]").forEach(b => b.classList.toggle("active", b.dataset.tab === t));
    $("#ai-pane").innerHTML = loading();
    try { await ({ agents: drawAgents, teams: drawTeams, runs: drawRuns, providers: drawProviders, tools: drawTools }[t])(); }
    catch (e) { $("#ai-pane").innerHTML = fail(e); }
  }

  async function init() {
    if (!$("#ai-pane")) return;
    try { await loadCore(); await overview(); } catch (e) { $("#ai-pane").innerHTML = fail(e); return; }
    $$("#ai-tabs [data-tab]").forEach(b => b.onclick = () => setTab(b.dataset.tab));
    setTab("agents");
  }
  document.addEventListener("DOMContentLoaded", () => setTimeout(init, 0));
})();
