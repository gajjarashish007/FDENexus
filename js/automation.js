/* M10 Operations automation workspace. */
(function () {
  "use strict";
  const NX = window.NEXUS, UI = NX.ui, esc = NX.esc, $ = UI.$, $$ = UI.$$;
  const S = { tab: "jobs", ov: null };
  const me = () => NX.session.get() || {};
  const isAdmin = () => (me().role === "admin");
  const TRIGGERS = ["schedule", "event", "incident", "manual"];
  const ACTIONS = ["ec2_start", "ec2_stop", "ec2_terminate", "rds_snapshot", "rds_stop", "eks_update", "lambda_invoke", "s3_copy", "cleanup", "script"];
  const loading = () => '<div class="nx-empty"><i class="bi bi-hourglass-split"></i>Loading…</div>';
  const fail = (e) => `<div class="alert alert-danger small">${esc(UI.errorText(e))}</div>`;
  const tbl = (head, rows, empty) => rows.length ? `<div class="nx-card"><div class="nx-table-wrap"><table class="nx-table"><thead><tr>${head.map(h => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div></div>`
    : `<div class="nx-card"><div class="nx-empty"><i class="bi bi-inbox"></i>${esc(empty)}</div></div>`;
  const badge = (s, map = { success: "success", failed: "danger", retrying: "warning", scheduled: "primary", manual: "secondary" }) => `<span class="nx-badge b-${map[s] || "secondary"}">${esc(s)}</span>`;

  async function overview() {
    S.ov = await NX.api.get("/api/m10/overview");
    const o = S.ov, k = (l, v, i, t, sub) => `<div class="col-6 col-xl-2"><div class="nx-card h-100"><div class="nx-card-body nx-kpi"><div class="nx-kpi-icon tone-${t}"><i class="bi ${i}"></i></div>
      <div><div class="nx-kpi-value" style="font-size:20px">${esc(v)}</div><div class="nx-kpi-label">${esc(l)}</div>${sub ? `<div class="small nx-muted">${esc(sub)}</div>` : ""}</div></div></div></div>`;
    const st = o.runs_by_status || {};
    $("#op-kpis").innerHTML = k("Jobs", o.jobs, "bi-gear-wide-connected", "primary", `${o.enabled} enabled`) +
      k("Runs (7d)", o.runs_7d, "bi-play-circle", "info", `success ${st.success || 0}, failed ${st.failed || 0}`) +
      k("Scheduled", o.by_trigger.schedule || 0, "bi-clock", "secondary") +
      k("Event-driven", o.by_trigger.event || 0, "bi-lightning", "warning") +
      k("Incident", o.by_trigger.incident || 0, "bi-exclamation-triangle", "danger") +
      k("Manual", o.by_trigger.manual || 0, "bi-hand-index", "secondary");
  }

  async function drawJobs() {
    const r = await NX.api.get("/api/m10/jobs");
    const trigIcon = { schedule: "clock", event: "lightning", incident: "exclamation-triangle", manual: "hand-index" };
    $("#op-pane").innerHTML = tbl(["Job", "Trigger", "Owner", "Approval", "Last run", "Status", ""], r.jobs.map(j => `<tr>
      <td><div class="fw-semibold small">${esc(j.name)}</div><div class="nx-mono nx-muted">${esc(j.id)}</div></td>
      <td><i class="bi bi-${trigIcon[j.trigger_type] || "gear"} me-1"></i>${esc(j.trigger_type)}</td>
      <td class="small">${esc(j.owner)}</td>
      <td>${j.approval_required ? '<span class="nx-badge b-warning">required</span>' : '<span class="nx-badge b-secondary">auto</span>'}</td>
      <td class="small nx-muted">${esc(j.last_run || "never")}</td>
      <td>${j.last_status ? badge(j.last_status) : '<span class="nx-muted">-</span>'}</td>
      <td class="text-end" style="white-space:nowrap">
        ${j.enabled ? `<button class="btn btn-sm btn-outline-primary" data-run="${esc(j.id)}" title="Run now"><i class="bi bi-play-fill"></i></button>` : ""}
        ${isAdmin() || j.owner === me().name ? `<button class="btn btn-sm btn-outline-secondary" data-edit="${esc(j.id)}"><i class="bi bi-pencil"></i></button>` : ""}
        ${isAdmin() || j.owner === me().name ? `<button class="btn btn-sm btn-outline-danger" data-del="${esc(j.id)}"><i class="bi bi-trash"></i></button>` : ""}
      </td></tr>`), "No automation jobs. Click New job to create one.");
    $$("[data-run]").forEach(b => b.onclick = async () => {
      try {
        const res = await NX.api.post(`/api/m10/jobs/${b.dataset.run}/run`);
        NX.toast(`Run ${res.run_id}: ${res.status}`, res.status === "success" ? "success" : "warning");
        await overview(); drawJobs();
      } catch (e) {
        if (UI.errorText(e).includes("requires approval")) {
          if (confirm("This job requires approval. Request approval to run?")) {
            const res = await NX.api.post(`/api/m10/jobs/${b.dataset.run}/approve`);
            NX.toast(`Run ${res.run_id}: ${res.status}`, res.status === "success" ? "success" : "warning");
            await overview(); drawJobs();
          }
        } else {
          NX.toast(UI.errorText(e), "danger");
        }
      }
    });
    $$("[data-del]").forEach(b => b.onclick = async () => {
      if (!confirm("Delete this job and its run history?")) return;
      try { await NX.api.call("DELETE", `/api/m10/jobs/${b.dataset.del}`); NX.toast("Deleted.", "success"); await overview(); drawJobs(); }
      catch (e) { NX.toast(UI.errorText(e), "danger"); }
    });
  }

  async function drawRuns() {
    const r = await NX.api.get("/api/m10/runs?limit=100");
    $("#op-pane").innerHTML = tbl(["Run", "Job", "Trigger", "Started", "Status", "Approver", ""], r.runs.map(rn => `<tr>
      <td class="nx-mono small">${esc(rn.id)}</td>
      <td class="small">${esc(rn.job_id)}</td>
      <td>${badge(rn.trigger)}</td>
      <td class="small">${esc(rn.started_at)}</td>
      <td>${badge(rn.status)}</td>
      <td class="small">${esc(rn.approver || "-")}</td>
      <td><button class="btn btn-sm btn-outline-secondary" data-view="${esc(rn.id)}"><i class="bi bi-eye"></i></button></td></tr>`), "No runs yet.");
    $$("[data-view]").forEach(b => b.onclick = async () => {
      const rn = await NX.api.get(`/api/m10/runs/${b.dataset.view}`);
      UI.modal(`Run ${rn.run.id}`, `<pre class="small" style="max-height:400px;overflow:auto">${esc(JSON.stringify(rn.run.evidence || [], null, 2))}</pre>`, { size: "lg" });
    });
  }

  async function drawSchedules() {
    const r = await NX.api.get("/api/m10/jobs");
    const sched = r.jobs.filter(j => j.trigger_type === "schedule");
    $("#op-pane").innerHTML = tbl(["Job", "Cron", "Enabled", "Next run", ""], sched.map(j => `<tr>
      <td class="fw-semibold small">${esc(j.name)}</td>
      <td class="nx-mono small">${esc(j.trigger_config?.cron || "-")}</td>
      <td>${j.enabled ? '<span class="nx-badge b-success">on</span>' : '<span class="nx-badge b-secondary">off</span>'}</td>
      <td class="small">${esc(j.next_run || "-")}</td>
      <td><button class="btn btn-sm btn-outline-secondary" data-toggle="${esc(j.id)}" data-en="${j.enabled}">${j.enabled ? "Disable" : "Enable"}</button></td></tr>`), "No scheduled jobs.");
  }

  async function setTab(t) {
    S.tab = t; $$("#op-tabs [data-tab]").forEach(b => b.classList.toggle("active", b.dataset.tab === t));
    $("#op-pane").innerHTML = loading();
    try { await ({ jobs: drawJobs, runs: drawRuns, schedules: drawSchedules }[t])(); } catch (e) { $("#op-pane").innerHTML = fail(e); }
  }

  async function init() {
    if (!$("#op-pane")) return;
    try { await overview(); } catch (e) { $("#op-pane").innerHTML = fail(e); return; }
    $$("#op-tabs [data-tab]").forEach(b => b.onclick = () => setTab(b.dataset.tab));
    $("#op-new").onclick = () => {
      const m = UI.modal("New automation job", `<div class="row g-3">
        <div class="col-md-6"><label class="form-label small fw-semibold">Name</label><input class="form-control" id="nj-name" placeholder="Stop dev EC2 at night"></div>
        <div class="col-md-6"><label class="form-label small fw-semibold">Trigger</label><select class="form-select" id="nj-trig">${TRIGGERS.map(t => `<option>${t}</option>`).join("")}</select></div>
        <div class="col-12"><label class="form-label small fw-semibold">Cron (if schedule)</label><input class="form-control" id="nj-cron" placeholder="0 22 * * *" value="0 22 * * *"></div>
        <div class="col-12"><label class="form-label small fw-semibold">Actions (JSON)</label><textarea class="form-control" id="nj-acts" rows="3" placeholder='[{"type":"ec2_stop","target":"i-xxx"}]'>[]</textarea></div>
        <div class="col-md-6"><label class="form-label small fw-semibold">Approval required</label><select class="form-select" id="nj-appr"><option value="0">No (auto-run)</option><option value="1">Yes</option></select></div>
        <div class="col-md-6"><label class="form-label small fw-semibold">Timeout (seconds)</label><input class="form-control" id="nj-timeout" value="300"></div>
      </div>`, { footer: '<button class="btn btn-primary" id="nj-go">Create</button>' });
      $("#nj-go", m.el).onclick = async () => {
        try {
          const acts = JSON.parse($("#nj-acts", m.el).value || "[]");
          const trig = $("#nj-trig", m.el).value;
          const job = await NX.api.post("/api/m10/jobs", {
            name: $("#nj-name", m.el).value, trigger_type: trig, trigger_config: trig === "schedule" ? { cron: $("#nj-cron", m.el).value } : {},
            actions: acts, approval_required: +$("#nj-appr", m.el).value, timeout_seconds: +$("#nj-timeout", m.el).value
          });
          m.hide(); NX.toast("Job created.", "success"); await setTab("jobs");
        } catch (e) { NX.toast(UI.errorText(e), "danger"); }
      };
    };
    setTab("jobs");
  }
  document.addEventListener("DOMContentLoaded", () => setTimeout(init, 0));
})();
